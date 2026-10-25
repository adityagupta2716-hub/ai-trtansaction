"""
Data Access Interface.
Provides backward-compatible and SQLAlchemy-powered CRUD operations for transactions,
actions, and feedback with tenant isolation support.
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from data.database import SessionLocal, DEFAULT_SQLITE_PATH
from data.models import Transaction, AIDecision, HumanReview, Feedback, Customer

DB_PATH = DEFAULT_SQLITE_PATH
VALID_STATUSES = {"pending", "approve", "hold", "block", "escalate", "pending_verification"}


def get_transaction(txn_id: int, org_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    session: Session = SessionLocal()
    try:
        q = session.query(Transaction).filter(Transaction.transaction_id == txn_id)
        if org_id is not None:
            q = q.filter(Transaction.org_id == org_id)
        t = q.first()
        if not t:
            return None
        return {
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
    finally:
        session.close()


def get_customer_history(customer_id: int, org_id: int = 1) -> Dict[str, Any]:
    from data.profile import build_customer_profile
    return build_customer_profile(customer_id, org_id=org_id)


def update_status(txn_id: int, status: str, org_id: Optional[int] = None) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    session: Session = SessionLocal()
    try:
        q = session.query(Transaction).filter(Transaction.transaction_id == txn_id)
        if org_id is not None:
            q = q.filter(Transaction.org_id == org_id)
        t = q.first()
        if not t:
            return False
        t.status = status
        session.commit()
        return True
    finally:
        session.close()


def log_action(
    transaction_id: int,
    decision: str,
    confidence: float,
    reasoning: str,
    decided_by: str = "agent",
    org_id: int = 1,
):
    if decision not in VALID_STATUSES - {"pending"}:
        raise ValueError(f"Invalid decision: {decision}")

    session: Session = SessionLocal()
    try:
        ai_dec = AIDecision(
            org_id=org_id,
            transaction_id=transaction_id,
            decision=decision,
            decision_margin=confidence,
            reasoning=reasoning,
            decided_by=decided_by,
        )
        session.add(ai_dec)
        session.commit()
    finally:
        session.close()


def add_feedback(transaction_id: int, agent_decision: str, human_decision: str, org_id: int = 1):
    session: Session = SessionLocal()
    try:
        fb = Feedback(
            org_id=org_id,
            transaction_id=transaction_id,
            agent_decision=agent_decision,
            human_decision=human_decision,
        )
        session.add(fb)
        session.commit()
    finally:
        session.close()