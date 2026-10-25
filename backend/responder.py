"""
Response Formulation and Configurable Verification Limit Module.

Replaces hardcoded amount/confidence guardrails with a database-backed,
auditable mandatory human-verification limit per tenant.

Routing logic:
Let A = transaction amount, L = configured verification limit for tenant.
- If A > L: route to mandatory human verification ('pending_verification').
  The transaction cannot be autonomously approved or blocked.
- If A <= L: let the AI decision engine select the appropriate action.
"""

from typing import Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from data.database import SessionLocal, utcnow
from data.models import AppSetting, Transaction, AIDecision, AuditLog
import json

DEFAULT_LIMIT = 500000.0
DEFAULT_POLICY_VERSION = "2.0.0"


def get_active_limit_config(org_id: int = 1) -> Tuple[float, str]:
    """Retrieve active verification limit and policy version from tenant database settings."""
    session: Session = SessionLocal()
    try:
        limit_setting = (
            session.query(AppSetting)
            .filter(AppSetting.org_id == org_id, AppSetting.key == "human_verification_limit")
            .first()
        )
        version_setting = (
            session.query(AppSetting)
            .filter(AppSetting.org_id == org_id, AppSetting.key == "policy_version")
            .first()
        )

        limit = float(limit_setting.value) if limit_setting else DEFAULT_LIMIT
        version = version_setting.value if version_setting else DEFAULT_POLICY_VERSION
        return limit, version
    except Exception:
        return DEFAULT_LIMIT, DEFAULT_POLICY_VERSION
    finally:
        session.close()


def update_verification_limit(new_limit: float, updated_by_username: str, org_id: int = 1) -> Dict[str, Any]:
    """Update tenant verification limit with input validation and audit logging."""
    if new_limit <= 0:
        raise ValueError("Verification limit must be a positive number.")

    session: Session = SessionLocal()
    try:
        setting = (
            session.query(AppSetting)
            .filter(AppSetting.org_id == org_id, AppSetting.key == "human_verification_limit")
            .first()
        )
        old_val = setting.value if setting else str(DEFAULT_LIMIT)
        if not setting:
            setting = AppSetting(
                org_id=org_id,
                key="human_verification_limit",
                value=str(new_limit),
                description="Mandatory human review limit.",
                updated_by=updated_by_username,
            )
            session.add(setting)
        else:
            setting.value = str(new_limit)
            setting.updated_by = updated_by_username
            setting.updated_at = utcnow()

        # Write audit log
        audit = AuditLog(
            org_id=org_id,
            entity_type="setting",
            entity_id="human_verification_limit",
            action="setting_changed",
            actor_type="admin",
            actor_id=updated_by_username,
            details_json=json.dumps({"old_limit": float(old_val), "new_limit": float(new_limit)}),
        )
        session.add(audit)
        session.commit()
        return {
            "old_limit": float(old_val),
            "new_limit": float(new_limit),
            "updated_by": updated_by_username,
            "org_id": org_id,
        }
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def execute_action(decision: Dict[str, Any], org_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Applies the tenant active verification limit policy and records the decision.
    """
    d = dict(decision)
    target_org_id = org_id or d.get("org_id", 1)
    amount = float(d.get("amount", 0.0))
    limit, policy_version = get_active_limit_config(org_id=target_org_id)

    d["org_id"] = target_org_id
    d["policy_version"] = policy_version
    d["active_limit"] = limit

    # Policy Routing: A > L routes to mandatory human verification
    if amount > limit:
        d["decision"] = "pending_verification"
        d["decided_by"] = "limit_policy"
        d["reasoning"] = (
            f"Transaction amount {amount:,.2f} exceeds active mandatory human verification "
            f"limit {limit:,.2f} (Policy v{policy_version}). Routed to human review queue."
        )
    else:
        d["decided_by"] = "agent"

    txn_id = d.get("transaction_id")
    if txn_id is not None:
        session: Session = SessionLocal()
        try:
            # Update transaction status
            txn = (
                session.query(Transaction)
                .filter(Transaction.transaction_id == txn_id, Transaction.org_id == target_org_id)
                .first()
            )
            if txn:
                txn.status = d["decision"]

            # Save AIDecision
            ai_dec = AIDecision(
                org_id=target_org_id,
                transaction_id=txn_id,
                decision=d["decision"],
                decision_margin=float(d.get("decision_margin", d.get("confidence", 0.5))),
                expected_utilities_json=json.dumps(d.get("expected_utilities", {})),
                policy_version=policy_version,
                reasoning=d.get("reasoning", ""),
                decided_by=d["decided_by"],
            )
            session.add(ai_dec)

            # Record Audit Log
            audit = AuditLog(
                org_id=target_org_id,
                entity_type="transaction",
                entity_id=str(txn_id),
                action="decision_executed",
                actor_type=d["decided_by"],
                actor_id=d["decided_by"],
                details_json=json.dumps({
                    "decision": d["decision"],
                    "amount": amount,
                    "active_limit": limit,
                    "p_fraud": d.get("p_fraud", 0.0),
                }),
            )
            session.add(audit)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    if d["decision"] != "approve":
        print(f"[SECURITY ALERT (Org #{target_org_id})] Txn #{d.get('transaction_id')} -> {d['decision'].upper()} | Reason: {d.get('reasoning')}")

    return d