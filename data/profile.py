"""
Customer Profile and Historical Behavior Module.

Computes:
- Historical baselines (leakage-safe with temporal cutoff).
- Comprehensive individual customer profiles distinguishing confirmed fraud,
  confirmed legitimate outcomes, unconfirmed AI alerts, and active risk indicators.
- Strictly isolated by organization / tenant ID.
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from data.database import SessionLocal
from data.models import Customer, Transaction, FraudPrediction, AIDecision, HumanReview


def build_customer_profile(
    customer_id: int,
    before_txn_id: Optional[int] = None,
    org_id: int = 1,
) -> Dict[str, Any]:
    """
    Leakage-safe customer profile for the decision agent.
    If before_txn_id is supplied, strictly excludes transactions occurring at or after that transaction's step.
    Strictly tenant-isolated by org_id.
    """
    session: Session = SessionLocal()
    try:
        cutoff_step = None
        if before_txn_id is not None:
            curr_txn = (
                session.query(Transaction)
                .filter(Transaction.transaction_id == before_txn_id, Transaction.org_id == org_id)
                .first()
            )
            if curr_txn:
                cutoff_step = curr_txn.step

        query = session.query(
            func.count(Transaction.transaction_id).label("n"),
            func.avg(Transaction.amount).label("avg_amount"),
            func.max(Transaction.amount).label("max_amount"),
        ).filter(Transaction.customer_id == customer_id, Transaction.org_id == org_id)

        if cutoff_step is not None:
            query = query.filter(Transaction.step < cutoff_step)

        row = query.first()
        n = row.n or 0
        avg_amount = float(row.avg_amount or 0.0)
        max_amount = float(row.max_amount or 0.0)

        # Count past flags from decisions for this tenant
        flag_query = (
            session.query(func.count(AIDecision.id))
            .join(Transaction, AIDecision.transaction_id == Transaction.transaction_id)
            .filter(
                Transaction.customer_id == customer_id,
                Transaction.org_id == org_id,
                AIDecision.org_id == org_id,
                AIDecision.decision.in_(["hold", "block", "escalate", "pending_verification"]),
            )
        )
        if cutoff_step is not None:
            flag_query = flag_query.filter(Transaction.step < cutoff_step)

        past_flags = flag_query.scalar() or 0

        return {
            "customer_id": customer_id,
            "org_id": org_id,
            "num_transactions": n,
            "average_amount": avg_amount,
            "max_amount": max_amount,
            "past_flags": past_flags,
        }
    finally:
        session.close()


def get_detailed_customer_profile(customer_id: int, org_id: int = 1) -> Dict[str, Any]:
    """
    Comprehensive customer profile for analyst inspection in the dashboard.
    Strictly distinguishes confirmed fraud, confirmed legitimate transactions,
    unresolved reviews, and unconfirmed AI anomaly alerts.
    Strictly isolated to authorized organization.
    """
    session: Session = SessionLocal()
    try:
        customer = (
            session.query(Customer)
            .filter(Customer.customer_id == customer_id, Customer.org_id == org_id)
            .first()
        )
        if not customer:
            # Create a profile stub for this customer within this organization
            customer = Customer(customer_id=customer_id, org_id=org_id, risk_level="low")
            session.add(customer)
            session.commit()

        # Query all customer transactions within this organization
        txns = (
            session.query(Transaction)
            .filter(Transaction.customer_id == customer_id, Transaction.org_id == org_id)
            .order_by(desc(Transaction.transaction_id))
            .all()
        )

        num_txns = len(txns)
        total_volume = sum(t.amount for t in txns) if num_txns > 0 else 0.0
        avg_amount = total_volume / num_txns if num_txns > 0 else 0.0
        max_amount = max((t.amount for t in txns), default=0.0)
        min_amount = min((t.amount for t in txns), default=0.0)

        # Transaction frequency (steps spanned)
        steps = [t.step for t in txns]
        step_span = (max(steps) - min(steps) + 1) if steps else 1
        freq = num_txns / max(step_span, 1)

        # Human Reviews breakdown within this organization
        txn_ids = [t.transaction_id for t in txns]
        reviews = (
            session.query(HumanReview)
            .filter(HumanReview.transaction_id.in_(txn_ids), HumanReview.org_id == org_id)
            .order_by(desc(HumanReview.created_at))
            .all()
            if txn_ids
            else []
        )

        confirmed_fraud_cases = [r for r in reviews if r.fraud_confirmed == 1]
        confirmed_legit_cases = [r for r in reviews if r.fraud_confirmed == 0]
        unresolved_reviews = [r for r in reviews if r.fraud_confirmed is None]

        # AI Alerts breakdown within this organization
        decisions = (
            session.query(AIDecision)
            .filter(AIDecision.transaction_id.in_(txn_ids), AIDecision.org_id == org_id)
            .order_by(desc(AIDecision.created_at))
            .all()
            if txn_ids
            else []
        )
        ai_alert_count = sum(1 for d in decisions if d.decision in ("hold", "block", "escalate", "pending_verification"))

        # Risk Indicators with verifiable evidence
        risk_indicators = []
        if len(confirmed_fraud_cases) > 0:
            risk_indicators.append({
                "type": "CONFIRMED_FRAUD_HISTORY",
                "severity": "HIGH",
                "evidence": f"Customer has {len(confirmed_fraud_cases)} past confirmed fraud case(s) verified by human review.",
            })

        if ai_alert_count > 0:
            risk_indicators.append({
                "type": "AI_ANOMALY_ALERTS",
                "severity": "MEDIUM",
                "evidence": f"{ai_alert_count} transaction(s) triggered AI anomaly holds, escalations, or verification limits (Note: AI alerts are risk signals, not verified fraud).",
            })

        drained_count = sum(1 for t in txns if t.new_balance == 0 and t.old_balance > 0)
        if drained_count > 0:
            risk_indicators.append({
                "type": "ACCOUNT_DRAINING_PATTERN",
                "severity": "MEDIUM",
                "evidence": f"Customer executed {drained_count} transaction(s) that completely emptied the account balance.",
            })

        if num_txns < 3:
            risk_indicators.append({
                "type": "INSUFFICIENT_HISTORY",
                "severity": "LOW",
                "evidence": f"Customer has only {num_txns} recorded transaction(s); profile baseline confidence is limited.",
            })

        # Calculate overall customer risk tier
        if len(confirmed_fraud_cases) > 0:
            overall_risk = "HIGH"
        elif ai_alert_count >= 2 or drained_count >= 2:
            overall_risk = "MEDIUM"
        else:
            overall_risk = "LOW"

        return {
            "customer_id": customer_id,
            "org_id": org_id,
            "overall_risk": overall_risk,
            "notes": customer.notes or "",
            "num_transactions": num_txns,
            "total_volume": round(total_volume, 2),
            "average_amount": round(avg_amount, 2),
            "max_amount": round(max_amount, 2),
            "min_amount": round(min_amount, 2),
            "frequency_per_step": round(freq, 2),
            "confirmed_fraud_count": len(confirmed_fraud_cases),
            "confirmed_legit_count": len(confirmed_legit_cases),
            "unresolved_review_count": len(unresolved_reviews),
            "ai_alert_count": ai_alert_count,
            "risk_indicators": risk_indicators,
            "recent_transactions": [
                {
                    "transaction_id": t.transaction_id,
                    "step": t.step,
                    "type": t.type,
                    "amount": t.amount,
                    "old_balance": t.old_balance,
                    "new_balance": t.new_balance,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in txns[:25]
            ],
            "reviews": [
                {
                    "review_id": r.id,
                    "transaction_id": r.transaction_id,
                    "reviewer": r.reviewer_username,
                    "outcome": r.review_outcome,
                    "fraud_confirmed": r.fraud_confirmed,
                    "reason": r.review_reason,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reviews
            ],
            "decisions": [
                {
                    "decision_id": d.id,
                    "transaction_id": d.transaction_id,
                    "decision": d.decision,
                    "decision_margin": d.decision_margin,
                    "decided_by": d.decided_by,
                    "reasoning": d.reasoning,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in decisions
            ],
        }
    finally:
        session.close()