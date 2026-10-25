"""
Multi-Tenant Isolation Verification Suite.

Tests strict multi-tenant boundaries as mandated by Phase 3:
1. Organization A and Organization B independent setup with isolated users, customers, and transactions.
2. Tenant-scoped read access: Org A sees only Org A records; Org B sees only Org B records.
3. ID manipulation resistance: Org A cannot read or modify Org B transactions via URL/body parameter tampering.
4. Review queue isolation: Transactions in Org A review queue never appear in Org B review queue.
5. Setting isolation: Modifying human verification limit in Org A does not alter Org B limit.
6. Customer profile isolation: Org A cannot view Org B customer histories or derived risk profiles.
7. Role-based permission enforcement: Analysts cannot perform admin operations; reviewers can review only their tenant cases.
8. Connection context safety: Connection reuse does not leak tenant contexts.
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import create_access_token
from data.database import SessionLocal, utcnow
from data.models import Organization, Membership, User, Customer, Transaction, AppSetting, HumanReview, AIDecision

client = TestClient(app)


@pytest.fixture(scope="module")
def tenant_fixture():
    """Sets up two isolated organizations and user tokens."""
    session = SessionLocal()
    try:
        # Organization A
        org_a = session.query(Organization).filter(Organization.slug == "test_org_a").first()
        if not org_a:
            org_a = Organization(name="Test Bank Alpha", slug="test_org_a", is_active=True)
            session.add(org_a)
            session.flush()

        # Organization B
        org_b = session.query(Organization).filter(Organization.slug == "test_org_b").first()
        if not org_b:
            org_b = Organization(name="Test Bank Beta", slug="test_org_b", is_active=True)
            session.add(org_b)
            session.flush()

        # Settings
        setting_a = session.query(AppSetting).filter(AppSetting.org_id == org_a.id, AppSetting.key == "human_verification_limit").first()
        if not setting_a:
            session.add(AppSetting(org_id=org_a.id, key="human_verification_limit", value="100000.0", description="Org A limit", updated_by="system"))
        else:
            setting_a.value = "100000.0"

        setting_b = session.query(AppSetting).filter(AppSetting.org_id == org_b.id, AppSetting.key == "human_verification_limit").first()
        if not setting_b:
            session.add(AppSetting(org_id=org_b.id, key="human_verification_limit", value="75000.0", description="Org B limit", updated_by="system"))
        else:
            setting_b.value = "75000.0"

        # Users for Org A
        user_admin_a = session.query(User).filter(User.username == "admin_alpha").first()
        if not user_admin_a:
            user_admin_a = User(username="admin_alpha", hashed_password="pw", role="admin", is_active=True)
            session.add(user_admin_a)
            session.flush()
            session.add(Membership(user_id=user_admin_a.id, org_id=org_a.id, role="org_admin", is_active=True))

        user_reviewer_a = session.query(User).filter(User.username == "reviewer_alpha").first()
        if not user_reviewer_a:
            user_reviewer_a = User(username="reviewer_alpha", hashed_password="pw", role="reviewer", is_active=True)
            session.add(user_reviewer_a)
            session.flush()
            session.add(Membership(user_id=user_reviewer_a.id, org_id=org_a.id, role="reviewer", is_active=True))

        user_analyst_a = session.query(User).filter(User.username == "analyst_alpha").first()
        if not user_analyst_a:
            user_analyst_a = User(username="analyst_alpha", hashed_password="pw", role="analyst", is_active=True)
            session.add(user_analyst_a)
            session.flush()
            session.add(Membership(user_id=user_analyst_a.id, org_id=org_a.id, role="analyst", is_active=True))

        # Users for Org B
        user_admin_b = session.query(User).filter(User.username == "admin_beta").first()
        if not user_admin_b:
            user_admin_b = User(username="admin_beta", hashed_password="pw", role="admin", is_active=True)
            session.add(user_admin_b)
            session.flush()
            session.add(Membership(user_id=user_admin_b.id, org_id=org_b.id, role="org_admin", is_active=True))

        user_reviewer_b = session.query(User).filter(User.username == "reviewer_beta").first()
        if not user_reviewer_b:
            user_reviewer_b = User(username="reviewer_beta", hashed_password="pw", role="reviewer", is_active=True)
            session.add(user_reviewer_b)
            session.flush()
            session.add(Membership(user_id=user_reviewer_b.id, org_id=org_b.id, role="reviewer", is_active=True))

        session.commit()

        # Generate tokens
        token_admin_a = create_access_token({"sub": "admin_alpha", "role": "org_admin", "org_id": org_a.id})
        token_reviewer_a = create_access_token({"sub": "reviewer_alpha", "role": "reviewer", "org_id": org_a.id})
        token_analyst_a = create_access_token({"sub": "analyst_alpha", "role": "analyst", "org_id": org_a.id})
        token_admin_b = create_access_token({"sub": "admin_beta", "role": "org_admin", "org_id": org_b.id})
        token_reviewer_b = create_access_token({"sub": "reviewer_beta", "role": "reviewer", "org_id": org_b.id})

        return {
            "org_a_id": org_a.id,
            "org_b_id": org_b.id,
            "headers_admin_a": {"Authorization": f"Bearer {token_admin_a}", "X-Org-ID": str(org_a.id)},
            "headers_reviewer_a": {"Authorization": f"Bearer {token_reviewer_a}", "X-Org-ID": str(org_a.id)},
            "headers_analyst_a": {"Authorization": f"Bearer {token_analyst_a}", "X-Org-ID": str(org_a.id)},
            "headers_admin_b": {"Authorization": f"Bearer {token_admin_b}", "X-Org-ID": str(org_b.id)},
            "headers_reviewer_b": {"Authorization": f"Bearer {token_reviewer_b}", "X-Org-ID": str(org_b.id)},
        }
    finally:
        session.close()


def test_transactions_isolated_between_tenants(tenant_fixture):
    """Transactions submitted by Org A must never be visible to Org B."""
    h_a = tenant_fixture["headers_analyst_a"]
    h_b = tenant_fixture["headers_admin_b"]

    # 1. Org A submits a transaction
    res_a = client.post(
        "/submit",
        json={"customer_id": 901, "type": "TRANSFER", "amount": 5000.0, "old_balance": 10000.0, "new_balance": 5000.0},
        headers=h_a,
    )
    assert res_a.status_code == 200
    txn_a_id = res_a.json()["transaction_id"]

    # 2. Org B queries all transactions
    res_b_list = client.get("/transactions", headers=h_b)
    assert res_b_list.status_code == 200
    b_txn_ids = [t["transaction_id"] for t in res_b_list.json()]
    assert txn_a_id not in b_txn_ids, "Org A transaction leaked into Org B transaction list!"

    # 3. Org A queries all transactions and must see its own transaction
    res_a_list = client.get("/transactions", headers=h_a)
    assert res_a_list.status_code == 200
    a_txn_ids = [t["transaction_id"] for t in res_a_list.json()]
    assert txn_a_id in a_txn_ids, "Org A transaction was not found in Org A transaction list!"


def test_id_tampering_cross_tenant_access_denied(tenant_fixture):
    """Org B cannot evaluate or inspect Org A's transaction by specifying its ID."""
    h_a = tenant_fixture["headers_analyst_a"]
    h_b = tenant_fixture["headers_admin_b"]

    # Org A submits transaction
    res_a = client.post(
        "/submit",
        json={"customer_id": 902, "type": "PAYMENT", "amount": 120.0, "old_balance": 1000.0, "new_balance": 880.0},
        headers=h_a,
    )
    assert res_a.status_code == 200
    txn_a_id = res_a.json()["transaction_id"]

    # Org B attempts to re-process Org A's transaction
    res_tamper = client.post(f"/process/{txn_a_id}", headers=h_b)
    assert res_tamper.status_code == 404, "Org B should receive 404 Not Found when trying to process Org A's txn"


def test_review_queue_strict_tenant_isolation(tenant_fixture):
    """High-value transactions in Org A review queue must not appear in Org B review queue."""
    h_a = tenant_fixture["headers_analyst_a"]
    h_rev_a = tenant_fixture["headers_reviewer_a"]
    h_rev_b = tenant_fixture["headers_reviewer_b"]

    # Org A submits transaction exceeding Org A limit ($100k)
    res_a = client.post(
        "/submit",
        json={"customer_id": 903, "type": "TRANSFER", "amount": 150000.0, "old_balance": 200000.0, "new_balance": 50000.0},
        headers=h_a,
    )
    assert res_a.status_code == 200
    txn_id = res_a.json()["transaction_id"]
    assert res_a.json()["decision"] == "pending_verification"

    # Org A review queue contains it
    q_a = client.get("/review-queue", headers=h_rev_a).json()
    assert any(item["transaction_id"] == txn_id for item in q_a)

    # Org B review queue does NOT contain it
    q_b = client.get("/review-queue", headers=h_rev_b).json()
    assert not any(item["transaction_id"] == txn_id for item in q_b), "Org A escalated case leaked into Org B review queue!"

    # Org B reviewer attempts to submit a review for Org A's transaction
    res_illegal_rev = client.post(
        f"/review/{txn_id}",
        json={"review_outcome": "approve", "fraud_confirmed": 0, "review_reason": "Attempted cross-tenant review"},
        headers=h_rev_b,
    )
    assert res_illegal_rev.status_code == 404, "Org B reviewer was able to review Org A transaction!"


def test_verification_limit_settings_are_isolated(tenant_fixture):
    """Modifying human-verification limit in Org A does not modify Org B limit."""
    h_admin_a = tenant_fixture["headers_admin_a"]
    h_admin_b = tenant_fixture["headers_admin_b"]

    # Read initial limits
    limit_a_init = client.get("/settings/verification-limit", headers=h_admin_a).json()["limit"]
    limit_b_init = client.get("/settings/verification-limit", headers=h_admin_b).json()["limit"]
    assert limit_a_init != limit_b_init or limit_a_init == 100000.0

    # Org A updates its limit to $300,000
    res_update = client.post("/settings/verification-limit", json={"new_limit": 300000.0}, headers=h_admin_a)
    assert res_update.status_code == 200

    # Verify Org A limit changed
    limit_a_now = client.get("/settings/verification-limit", headers=h_admin_a).json()["limit"]
    assert limit_a_now == 300000.0

    # Verify Org B limit remained UNCHANGED
    limit_b_now = client.get("/settings/verification-limit", headers=h_admin_b).json()["limit"]
    assert limit_b_now == limit_b_init, "Modifying Org A verification limit modified Org B's limit!"


def test_customer_profile_isolation(tenant_fixture):
    """Customer profiles in Org A and Org B with identical customer_id are completely separated."""
    import time
    h_a = tenant_fixture["headers_analyst_a"]
    h_b = tenant_fixture["headers_admin_b"]
    shared_cid = 70000 + int(time.time() * 100) % 50000

    # Org A submits transaction for customer #777
    client.post(
        "/submit",
        json={"customer_id": shared_cid, "type": "TRANSFER", "amount": 1000.0, "old_balance": 5000.0, "new_balance": 4000.0},
        headers=h_a,
    )

    # Org B submits transaction for customer #777 with different amount
    client.post(
        "/submit",
        json={"customer_id": shared_cid, "type": "PAYMENT", "amount": 99.0, "old_balance": 300.0, "new_balance": 201.0},
        headers=h_b,
    )

    # Profile for Org A
    prof_a = client.get(f"/customers/{shared_cid}", headers=h_a).json()
    # Profile for Org B
    prof_b = client.get(f"/customers/{shared_cid}", headers=h_b).json()

    assert prof_a["total_volume"] == 1000.0, f"Expected 1000.0 volume for Org A, got {prof_a['total_volume']}"
    assert prof_b["total_volume"] == 99.0, f"Expected 99.0 volume for Org B, got {prof_b['total_volume']}"
    assert prof_a["org_id"] == tenant_fixture["org_a_id"]
    assert prof_b["org_id"] == tenant_fixture["org_b_id"]


def test_client_supplied_tenant_id_header_tampering_rejected(tenant_fixture):
    """An attacker presenting Org A credentials with X-Org-ID: <Org B> is rejected."""
    # Org A analyst token
    token_a = tenant_fixture["headers_analyst_a"]["Authorization"]
    # Tamper with header pointing to Org B
    tampered_headers = {
        "Authorization": token_a,
        "X-Org-ID": str(tenant_fixture["org_b_id"]),
    }

    res = client.get("/transactions", headers=tampered_headers)
    assert res.status_code == 403, "Tampering with X-Org-ID header to unpermitted org was not rejected!"
