"""
FastAPI Application for AI Transaction Monitor.

Provides:
- Strict Multi-Tenant Isolation with validated organization contexts.
- Secure JWT-based Authentication & Role-Based Access Control (Platform Admin, Org Admin, Analyst, Reviewer).
- Tenant-scoped transaction ingestion, scoring, and utility-based routing.
- Mandatory Human Verification Limit configuration & auditability per organization.
- Human review queue with safe concurrency state transitions and tenant boundary enforcement.
- Individual customer profiling and historical behavior analysis scoped to tenant.
- Active learning through feedback policy adaptation.
- Organization and user membership management.
"""

from typing import Literal, Optional, List, Dict, Any
from datetime import datetime, timezone
import json
from fastapi import FastAPI, HTTPException, Depends, Header, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from data.database import get_db, utcnow
from data.models import (
    User,
    Organization,
    Membership,
    Customer,
    Transaction,
    AIDecision,
    HumanReview,
    AuditLog,
    AppSetting,
    Feedback,
)
from backend.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    get_tenant_context,
    require_roles,
    TenantContext,
)
from backend.pipeline import process_transaction
from backend.responder import get_active_limit_config, update_verification_limit
from data.profile import get_detailed_customer_profile
from learning.feedback import update_utilities

app = FastAPI(
    title="AI Transaction Monitor",
    description="Research-Grade Multi-Tenant Financial Fraud Detection, Utility Agent & Guardrails Platform",
    version="2.1.0",
)


# ==========================================
# Pydantic Schemas
# ==========================================

class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)
    email: Optional[str] = None
    role: Literal["admin", "org_admin", "analyst", "reviewer"] = "analyst"
    org_id: Optional[int] = None


class UserLogin(BaseModel):
    username: str
    password: str
    org_id: Optional[int] = None


class OrgSummary(BaseModel):
    org_id: int
    name: str
    slug: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    org_id: int
    org_name: str
    org_slug: str
    available_organizations: List[OrgSummary] = []


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    slug: str = Field(min_length=2, max_length=64)


class AddMemberRequest(BaseModel):
    username: str
    role: Literal["org_admin", "analyst", "reviewer"] = "analyst"


class NewTransaction(BaseModel):
    customer_id: int = Field(ge=1)
    type: Literal["TRANSFER", "CASH_OUT", "PAYMENT"]
    amount: float = Field(gt=0)
    old_balance: float = Field(ge=0)
    new_balance: float = Field(ge=0)


class HumanReviewSubmission(BaseModel):
    review_outcome: Literal["approve", "block", "unresolved"]
    fraud_confirmed: Optional[int] = Field(None, description="1 if confirmed fraud, 0 if confirmed legitimate, None if unresolved")
    review_reason: str = Field(min_length=3, description="Justification for reviewer decision")


class VerificationLimitUpdate(BaseModel):
    new_limit: float = Field(gt=0, description="New mandatory human review threshold amount")


class FeedbackLegacy(BaseModel):
    transaction_id: int
    human_decision: Literal["approve", "block"]


# ==========================================
# Authentication & Multi-Tenant Endpoints
# ==========================================

@app.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """Registers a new platform user and assigns organization membership."""
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username is already registered.")

    # Determine organization to join
    target_org = None
    if user_in.org_id:
        target_org = db.query(Organization).filter(Organization.id == user_in.org_id, Organization.is_active == True).first()
        if not target_org:
            raise HTTPException(status_code=404, detail=f"Organization #{user_in.org_id} does not exist.")
    else:
        # Default to first active organization
        target_org = db.query(Organization).filter(Organization.is_active == True).first()
        if not target_org:
            target_org = Organization(name="Default Enterprise", slug="default", is_active=True)
            db.add(target_org)
            db.flush()

    hashed_pw = get_password_hash(user_in.password)
    user = User(
        username=user_in.username,
        email=user_in.email or f"{user_in.username}@example.com",
        hashed_password=hashed_pw,
        role=user_in.role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    # Assign Membership
    membership = Membership(
        user_id=user.id,
        org_id=target_org.id,
        role=user_in.role,
        is_active=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "sub": user.username,
        "role": user_in.role,
        "org_id": target_org.id,
    })

    return TokenResponse(
        access_token=token,
        role=user_in.role,
        username=user.username,
        org_id=target_org.id,
        org_name=target_org.name,
        org_slug=target_org.slug,
        available_organizations=[
            OrgSummary(org_id=target_org.id, name=target_org.name, slug=target_org.slug, role=user_in.role)
        ],
    )


@app.post("/auth/login", response_model=TokenResponse)
def login(login_in: UserLogin, db: Session = Depends(get_db)):
    """Authenticates user and returns JWT bearer token scoped to authorized active organization."""
    user = db.query(User).filter(User.username == login_in.username).first()
    if not user or not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    # Fetch all active memberships for this user
    memberships = (
        db.query(Membership)
        .join(Organization, Membership.org_id == Organization.id)
        .filter(Membership.user_id == user.id, Membership.is_active == True, Organization.is_active == True)
        .all()
    )

    if not memberships and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="User account has no active organization memberships.")

    available_orgs: List[OrgSummary] = []
    if user.is_platform_admin:
        all_orgs = db.query(Organization).filter(Organization.is_active == True).all()
        available_orgs = [
            OrgSummary(org_id=o.id, name=o.name, slug=o.slug, role="platform_admin")
            for o in all_orgs
        ]
    else:
        available_orgs = [
            OrgSummary(org_id=m.organization.id, name=m.organization.name, slug=m.organization.slug, role=m.role)
            for m in memberships
        ]

    # Select active organization
    selected_org = None
    selected_role = user.role
    if login_in.org_id:
        for opt in available_orgs:
            if opt.org_id == login_in.org_id:
                selected_org = db.query(Organization).filter(Organization.id == opt.org_id).first()
                selected_role = opt.role
                break
        if not selected_org:
            raise HTTPException(status_code=403, detail=f"User is not authorized for organization #{login_in.org_id}.")
    else:
        # Default to first available organization
        first_opt = available_orgs[0]
        selected_org = db.query(Organization).filter(Organization.id == first_opt.org_id).first()
        selected_role = first_opt.role

    # Record login in audit log
    audit = AuditLog(
        org_id=selected_org.id,
        entity_type="user",
        entity_id=str(user.id),
        action="user_login",
        actor_type=selected_role,
        actor_id=user.username,
        details_json=json.dumps({"org_id": selected_org.id, "login_time": utcnow().isoformat()}),
    )
    db.add(audit)
    db.commit()

    token = create_access_token({
        "sub": user.username,
        "role": selected_role,
        "org_id": selected_org.id,
    })

    return TokenResponse(
        access_token=token,
        role=selected_role,
        username=user.username,
        org_id=selected_org.id,
        org_name=selected_org.name,
        org_slug=selected_org.slug,
        available_organizations=available_orgs,
    )


@app.get("/auth/me")
def get_current_user_profile(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Returns currently authenticated user profile and active organization context."""
    user = ctx.user
    memberships = (
        db.query(Membership)
        .join(Organization, Membership.org_id == Organization.id)
        .filter(Membership.user_id == user.id, Membership.is_active == True)
        .all()
    )

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": ctx.role,
        "is_platform_admin": user.is_platform_admin,
        "active_organization": {
            "id": ctx.org.id,
            "name": ctx.org.name,
            "slug": ctx.org.slug,
            "role": ctx.role,
        },
        "available_organizations": [
            {
                "org_id": m.organization.id,
                "name": m.organization.name,
                "slug": m.organization.slug,
                "role": m.role,
            }
            for m in memberships
        ],
    }


@app.post("/auth/switch-org/{target_org_id}", response_model=TokenResponse)
def switch_active_org(
    target_org_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Switch active tenant context and return a newly scoped JWT token."""
    user = ctx.user
    # Validate membership in target org
    org = db.query(Organization).filter(Organization.id == target_org_id, Organization.is_active == True).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")

    matched_role = None
    if user.is_platform_admin:
        matched_role = "platform_admin"
    else:
        membership = (
            db.query(Membership)
            .filter(Membership.user_id == user.id, Membership.org_id == target_org_id, Membership.is_active == True)
            .first()
        )
        if not membership:
            raise HTTPException(status_code=403, detail=f"Access denied: No active membership in organization #{target_org_id}.")
        matched_role = membership.role

    token = create_access_token({
        "sub": user.username,
        "role": matched_role,
        "org_id": org.id,
    })

    return TokenResponse(
        access_token=token,
        role=matched_role,
        username=user.username,
        org_id=org.id,
        org_name=org.name,
        org_slug=org.slug,
    )


# ==========================================
# Organization & Membership Management
# ==========================================

@app.get("/organizations")
def list_organizations(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Lists organizations accessible by current user."""
    if ctx.user.is_platform_admin:
        orgs = db.query(Organization).filter(Organization.is_active == True).all()
        return [{"id": o.id, "name": o.name, "slug": o.slug} for o in orgs]
    else:
        memberships = (
            db.query(Membership)
            .join(Organization, Membership.org_id == Organization.id)
            .filter(Membership.user_id == ctx.user.id, Membership.is_active == True)
            .all()
        )
        return [{"id": m.organization.id, "name": m.organization.name, "slug": m.organization.slug, "role": m.role} for m in memberships]


@app.post("/organizations", status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: CreateOrganizationRequest,
    ctx: TenantContext = Depends(require_roles(["platform_admin", "admin"])),
    db: Session = Depends(get_db),
):
    """Creates a new organization (Platform Administrator or Org Admin)."""
    existing = db.query(Organization).filter(
        (Organization.name == payload.name) | (Organization.slug == payload.slug)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Organization name or slug already exists.")

    new_org = Organization(name=payload.name, slug=payload.slug, is_active=True)
    db.add(new_org)
    db.flush()

    # Automatically add current user as org_admin
    m = Membership(user_id=ctx.user.id, org_id=new_org.id, role="org_admin", is_active=True)
    db.add(m)

    # Initialize default settings for this new tenant
    default_limit = AppSetting(
        org_id=new_org.id,
        key="human_verification_limit",
        value="500000.0",
        description="Mandatory human review limit.",
        updated_by=ctx.user.username,
    )
    policy_ver = AppSetting(
        org_id=new_org.id,
        key="policy_version",
        value="2.0.0",
        description="Active fraud policy version.",
        updated_by=ctx.user.username,
    )
    db.add_all([default_limit, policy_ver])
    db.commit()

    return {"id": new_org.id, "name": new_org.name, "slug": new_org.slug}


@app.get("/organizations/{org_id}/members")
def get_organization_members(
    org_id: int,
    ctx: TenantContext = Depends(require_roles(["admin", "org_admin", "platform_admin"])),
    db: Session = Depends(get_db),
):
    """Lists members of the authorized organization."""
    if not ctx.user.is_platform_admin and ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot view members of another organization.")

    members = (
        db.query(Membership)
        .join(User, Membership.user_id == User.id)
        .filter(Membership.org_id == org_id, Membership.is_active == True)
        .all()
    )
    return [
        {
            "membership_id": m.id,
            "user_id": m.user.id,
            "username": m.user.username,
            "email": m.user.email,
            "role": m.role,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in members
    ]


@app.post("/organizations/{org_id}/members", status_code=status.HTTP_201_CREATED)
def add_organization_member(
    org_id: int,
    payload: AddMemberRequest,
    ctx: TenantContext = Depends(require_roles(["admin", "org_admin", "platform_admin"])),
    db: Session = Depends(get_db),
):
    """Adds an existing user to the organization with assigned role."""
    if not ctx.user.is_platform_admin and ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="Cannot manage members for another organization.")

    target_user = db.query(User).filter(User.username == payload.username).first()
    if not target_user:
        raise HTTPException(status_code=404, detail=f"User '{payload.username}' not found.")

    existing_m = db.query(Membership).filter(
        Membership.user_id == target_user.id,
        Membership.org_id == org_id,
    ).first()

    if existing_m:
        existing_m.role = payload.role
        existing_m.is_active = True
    else:
        new_m = Membership(user_id=target_user.id, org_id=org_id, role=payload.role, is_active=True)
        db.add(new_m)

    audit = AuditLog(
        org_id=org_id,
        entity_type="membership",
        entity_id=str(target_user.id),
        action="member_added",
        actor_type="admin",
        actor_id=ctx.user.username,
        details_json=json.dumps({"target_user": payload.username, "role": payload.role}),
    )
    db.add(audit)
    db.commit()

    return {"ok": True, "org_id": org_id, "username": payload.username, "role": payload.role}


# ==========================================
# Tenant-Scoped Transaction Processing
# ==========================================

@app.post("/submit")
def submit(
    tx: NewTransaction,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Submits a transaction scoped to the authenticated tenant organization.
    Ensures customer exists strictly within the tenant boundary.
    """
    tenant_org_id = ctx.org_id

    # Ensure customer exists within this organization
    customer = (
        db.query(Customer)
        .filter(Customer.customer_id == tx.customer_id, Customer.org_id == tenant_org_id)
        .first()
    )
    if not customer:
        customer = Customer(customer_id=tx.customer_id, org_id=tenant_org_id, risk_level="low")
        db.add(customer)
        db.commit()

    # Determine next transaction_id
    max_id = db.query(func.max(Transaction.transaction_id)).scalar() or 0
    new_id = max_id + 1

    new_txn = Transaction(
        transaction_id=new_id,
        org_id=tenant_org_id,
        customer_id=tx.customer_id,
        step=0,
        type=tx.type,
        amount=tx.amount,
        old_balance=tx.old_balance,
        new_balance=tx.new_balance,
        is_fraud=0,
        status="pending",
    )
    db.add(new_txn)
    db.commit()

    result = process_transaction(new_id, org_id=tenant_org_id)
    return result


@app.post("/process/{txn_id}")
def process(
    txn_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Evaluates an existing transaction belonging to the authorized tenant."""
    result = process_transaction(txn_id, org_id=ctx.org_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Transaction not found in active organization.")
    return result


@app.get("/transactions")
def get_transactions(
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    tx_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieves paginated and filtered list of transactions strictly within tenant scope."""
    q = db.query(Transaction).filter(Transaction.org_id == ctx.org_id)
    if status:
        q = q.filter(Transaction.status == status)
    if customer_id:
        q = q.filter(Transaction.customer_id == customer_id)
    if tx_type:
        q = q.filter(Transaction.type == tx_type)

    txns = q.order_by(Transaction.transaction_id).offset(skip).limit(limit).all()

    return [
        {
            "transaction_id": t.transaction_id,
            "org_id": t.org_id,
            "customer_id": t.customer_id,
            "step": t.step,
            "type": t.type,
            "amount": t.amount,
            "old_balance": t.old_balance,
            "new_balance": t.new_balance,
            "is_fraud": t.is_fraud,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in txns
    ]


@app.get("/alerts")
def alerts(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Returns transactions requiring alert attention strictly within authorized organization."""
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.org_id == ctx.org_id,
            Transaction.status.in_(["hold", "block", "escalate", "pending_verification"]),
        )
        .order_by(desc(Transaction.transaction_id))
        .all()
    )
    return [
        {
            "transaction_id": t.transaction_id,
            "org_id": t.org_id,
            "customer_id": t.customer_id,
            "step": t.step,
            "type": t.type,
            "amount": t.amount,
            "old_balance": t.old_balance,
            "new_balance": t.new_balance,
            "is_fraud": t.is_fraud,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in txns
    ]


@app.get("/review-queue")
def review_queue(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Returns transactions awaiting human review strictly for the authorized tenant."""
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.org_id == ctx.org_id,
            Transaction.status.in_(["escalate", "pending_verification"]),
        )
        .order_by(Transaction.transaction_id)
        .all()
    )
    return [
        {
            "transaction_id": t.transaction_id,
            "org_id": t.org_id,
            "customer_id": t.customer_id,
            "step": t.step,
            "type": t.type,
            "amount": t.amount,
            "old_balance": t.old_balance,
            "new_balance": t.new_balance,
            "is_fraud": t.is_fraud,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in txns
    ]


# ==========================================
# Human Review Workflow Endpoints
# ==========================================

@app.post("/review/{txn_id}")
def submit_human_review(
    txn_id: int,
    review_in: HumanReviewSubmission,
    ctx: TenantContext = Depends(require_roles(["reviewer", "admin", "org_admin"])),
    db: Session = Depends(get_db),
):
    """
    Submits a human review judgment for an escalated or pending-verification transaction.
    Strictly verifies transaction belongs to user's authorized organization.
    """
    txn = (
        db.query(Transaction)
        .filter(Transaction.transaction_id == txn_id, Transaction.org_id == ctx.org_id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail=f"Transaction #{txn_id} not found in active organization.")

    if txn.status not in ("escalate", "pending_verification"):
        raise HTTPException(
            status_code=400,
            detail=f"Transaction #{txn_id} is in status '{txn.status}' and is not pending human review.",
        )

    # 1. Record HumanReview
    review_record = HumanReview(
        org_id=ctx.org_id,
        transaction_id=txn_id,
        reviewer_id=ctx.user.id,
        reviewer_username=ctx.user.username,
        review_outcome=review_in.review_outcome,
        fraud_confirmed=review_in.fraud_confirmed,
        review_reason=review_in.review_reason,
    )
    db.add(review_record)

    # 2. Update Transaction Status if resolved
    if review_in.review_outcome in ("approve", "block"):
        txn.status = review_in.review_outcome

    # 3. Add to Feedback table for active learning
    last_decision = (
        db.query(AIDecision)
        .filter(AIDecision.transaction_id == txn_id, AIDecision.org_id == ctx.org_id)
        .order_by(desc(AIDecision.id))
        .first()
    )
    agent_d = last_decision.decision if last_decision else "unknown"

    if review_in.review_outcome in ("approve", "block"):
        fb = Feedback(
            org_id=ctx.org_id,
            transaction_id=txn_id,
            agent_decision=agent_d,
            human_decision=review_in.review_outcome,
        )
        db.add(fb)

    # 4. Record Audit Log
    audit = AuditLog(
        org_id=ctx.org_id,
        entity_type="transaction",
        entity_id=str(txn_id),
        action="human_reviewed",
        actor_type="reviewer",
        actor_id=ctx.user.username,
        details_json=json.dumps({
            "outcome": review_in.review_outcome,
            "fraud_confirmed": review_in.fraud_confirmed,
            "reason": review_in.review_reason,
            "org_id": ctx.org_id,
        }),
    )
    db.add(audit)
    db.commit()

    return {
        "ok": True,
        "transaction_id": txn_id,
        "org_id": ctx.org_id,
        "new_status": txn.status,
        "reviewer": ctx.user.username,
    }


@app.post("/feedback")
def legacy_feedback(
    fb: FeedbackLegacy,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Legacy feedback endpoint scoped to active tenant."""
    txn = (
        db.query(Transaction)
        .filter(Transaction.transaction_id == fb.transaction_id, Transaction.org_id == ctx.org_id)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found in active organization.")

    last_decision = (
        db.query(AIDecision)
        .filter(AIDecision.transaction_id == fb.transaction_id, AIDecision.org_id == ctx.org_id)
        .order_by(desc(AIDecision.id))
        .first()
    )
    agent_d = last_decision.decision if last_decision else "unknown"

    feedback_record = Feedback(
        org_id=ctx.org_id,
        transaction_id=fb.transaction_id,
        agent_decision=agent_d,
        human_decision=fb.human_decision,
    )
    db.add(feedback_record)

    # Audit log
    audit = AuditLog(
        org_id=ctx.org_id,
        entity_type="transaction",
        entity_id=str(fb.transaction_id),
        action="human_feedback_saved",
        actor_type="human",
        actor_id=ctx.user.username,
        details_json=json.dumps({"decision": fb.human_decision, "org_id": ctx.org_id}),
    )
    db.add(audit)
    txn.status = fb.human_decision
    db.commit()

    return {"ok": True}


# ==========================================
# Tenant-Scoped Customer Profiling
# ==========================================

@app.get("/customers/{customer_id}")
def get_customer(
    customer_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Returns detailed individual customer profile strictly isolated to current organization."""
    profile = get_detailed_customer_profile(customer_id, org_id=ctx.org_id)
    return profile


# ==========================================
# Configurable Settings Endpoints (Tenant-Scoped)
# ==========================================

@app.get("/settings/verification-limit")
def get_verification_limit(ctx: TenantContext = Depends(get_tenant_context)):
    """Retrieves current mandatory human-verification limit for active tenant organization."""
    limit, version = get_active_limit_config(org_id=ctx.org_id)
    return {
        "limit": limit,
        "policy_version": version,
        "currency": "USD",
        "org_id": ctx.org_id,
        "org_name": ctx.org.name,
    }


@app.post("/settings/verification-limit")
def set_verification_limit(
    payload: VerificationLimitUpdate,
    ctx: TenantContext = Depends(require_roles(["admin", "org_admin", "platform_admin"])),
):
    """Updates mandatory human-verification limit for the authorized tenant organization."""
    result = update_verification_limit(payload.new_limit, ctx.user.username, org_id=ctx.org_id)
    return result


# ==========================================
# Audit & Learning Endpoints (Tenant-Scoped)
# ==========================================

@app.get("/actions")
def get_actions(
    limit: int = 200,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Returns recent decisions and actions strictly within authorized tenant organization."""
    decisions = (
        db.query(AIDecision)
        .filter(AIDecision.org_id == ctx.org_id)
        .order_by(desc(AIDecision.id))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": d.id,
            "org_id": d.org_id,
            "transaction_id": d.transaction_id,
            "decision": d.decision,
            "confidence": d.decision_margin,
            "decision_margin": d.decision_margin,
            "reasoning": d.reasoning,
            "decided_by": d.decided_by,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in decisions
    ]


@app.get("/audit-logs")
def get_audit_logs(
    limit: int = 200,
    entity_type: Optional[str] = None,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Returns tamper-evident system audit log strictly scoped to current tenant organization."""
    q = db.query(AuditLog).filter(AuditLog.org_id == ctx.org_id)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    logs = q.order_by(desc(AuditLog.id)).limit(limit).all()
    return [
        {
            "id": l.id,
            "org_id": l.org_id,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "action": l.action,
            "actor_type": l.actor_type,
            "actor_id": l.actor_id,
            "details": json.loads(l.details_json) if l.details_json else {},
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@app.post("/feedback/learn")
def adapt_policy(ctx: TenantContext = Depends(require_roles(["admin", "org_admin", "analyst"]))):
    """Triggers feedback-based policy adaptation on expected utility matrix."""
    new_utility = update_utilities(step=1.0)
    return {"ok": True, "updated_utility": new_utility, "org_id": ctx.org_id}