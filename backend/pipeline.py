"""
Transaction Processing Pipeline.
Orchestrates anomaly scoring, risk estimation, expected utility evaluation,
configurable verification limit routing, and persistence with multi-tenant isolation.
"""

import json
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from data.database import SessionLocal, utcnow
from data.models import Transaction, FraudPrediction
from data.db import get_transaction
from model.anomaly import score_transaction
from agent.agent import decide
from backend.responder import execute_action


def process_transaction(txn_id: int, org_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    txn = get_transaction(txn_id, org_id=org_id)
    if txn is None:
        return None

    target_org_id = txn.get("org_id", 1)

    # 1. ML Anomaly Scoring & Probability Calibration
    score_result = score_transaction(txn)

    # 2. Persist FraudPrediction in Database
    session: Session = SessionLocal()
    try:
        pred = FraudPrediction(
            org_id=target_org_id,
            transaction_id=txn_id,
            anomaly_score=float(score_result["score"]),
            raw_p_fraud=float(score_result["p_fraud"]),
            adjusted_p_fraud=float(score_result["p_fraud"]),
            decision_margin=0.0,
            model_version="1.0.0",
            reasons_json=json.dumps(score_result.get("top_reasons", [])),
            created_at=utcnow(),
        )
        session.add(pred)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()

    # 3. Utility-Based Decision Agent
    decision = decide(txn, score_result)
    decision["amount"] = txn["amount"]
    decision["raw_p_fraud"] = score_result["p_fraud"]
    decision["org_id"] = target_org_id

    # 4. Configurable Verification Limit & Execution
    final = execute_action(decision, org_id=target_org_id)
    final["anomaly_score"] = score_result["score"]
    final["raw_p_fraud"] = score_result["p_fraud"]
    final["customer_id"] = txn["customer_id"]
    final["type"] = txn["type"]
    final["org_id"] = target_org_id

    return final