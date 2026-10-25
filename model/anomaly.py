"""
Anomaly Detection and Probability Calibration Engine.

Components:
1. Isolation Forest: Unsupervised anomaly detector.
   - Anomaly Score: -score_samples(X), scaled to [0, 1] relative to training distribution.
   - Interpretation: Higher score = more anomalous / outlier behavior.
2. Calibrator: Logistic Regression mapping [score, drained, amount_ratio, transfer, cash_out]
   to calibrated posterior probability P(fraud) in [0, 1].
3. Explainability Engine: Generates verifiable feature-level reason codes.
"""

import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, List
from model.features import make_features

_bundle = None


def _load():
    global _bundle
    if _bundle is None:
        _bundle = joblib.load("model/model.joblib")
    return _bundle


def score_transaction(txn: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates a transaction dictionary using the calibrated Isolation Forest.

    Returns:
        - score: Anomaly score in [0.0, 1.0] (higher = more anomalous).
        - p_fraud: Calibrated fraud probability in [0.0, 1.0].
        - is_anomaly: Boolean flag if anomaly score exceeds threshold or p_fraud > 0.3.
        - top_reasons: List of explanatory reason statements.
    """
    b = _load()
    X = make_features(pd.DataFrame([txn]))
    
    # Isolation Forest score: negative average depth in trees
    raw = -b["iso"].score_samples(X)[0]
    lo = b.get("lo", 0.0)
    hi = b.get("hi", 1.0)
    
    # Normalized Anomaly Score in [0, 1]
    denom = (hi - lo) if (hi - lo) > 1e-6 else 1.0
    score = float(min(max((raw - lo) / denom, 0.0), 1.0))

    drained_val = float(X["drained"].iloc[0])
    ratio_val = float(min(X["amount_ratio"].iloc[0], 2.0))
    transfer_val = float(X["type_TRANSFER"].iloc[0])
    cash_out_val = float(X["type_CASH_OUT"].iloc[0])

    calib_input = np.array([[score, drained_val, ratio_val, transfer_val, cash_out_val]])
    p_fraud = float(b["calibrator"].predict_proba(calib_input)[0][1])

    # Explainability Factor Generation
    reasons: List[str] = []
    old_b = float(txn.get("old_balance", 0.0))
    new_b = float(txn.get("new_balance", 0.0))
    amt = float(txn.get("amount", 0.0))
    tx_type = str(txn.get("type", ""))

    if old_b > 0 and new_b == 0:
        reasons.append("Account balance was completely drained to zero")
    if (amt / (old_b + 1.0)) > 0.9:
        reasons.append(f"Transaction amount ({amt:,.2f}) accounts for >90% of available funds")
    if tx_type in ("TRANSFER", "CASH_OUT"):
        reasons.append(f"High-risk liquidation transaction type: {tx_type}")
    if score > b.get("threshold", 0.8):
        reasons.append(f"Structural feature outlier in tree partition space (anomaly score: {score:.3f})")
    if not reasons:
        reasons.append("Standard transaction pattern consistent with baseline distribution")

    threshold = b.get("threshold", 0.8)
    is_anomaly = bool(score > threshold or p_fraud > 0.3)

    return {
        "score": round(score, 4),
        "raw_score": round(float(raw), 4),
        "p_fraud": round(p_fraud, 4),
        "is_anomaly": is_anomaly,
        "top_reasons": reasons,
    }