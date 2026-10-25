"""
Feature Engineering Module for Fraud Detection.

Provides:
1. `make_features(df)`: Leakage-safe baseline features matching the trained model pipeline.
2. `make_chronological_features(df)`: Advanced temporal & customer-history features
   for research baseline comparisons (prevents lookahead leakage).
"""

import pandas as pd
import numpy as np


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extracts features for the core anomaly detection model.
    Only uses transaction-level features available strictly at prediction time.
    """
    out = pd.DataFrame(index=df.index)
    out["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    out["old_balance"] = pd.to_numeric(df["old_balance"], errors="coerce").fillna(0.0)
    out["new_balance"] = pd.to_numeric(df["new_balance"], errors="coerce").fillna(0.0)
    
    # Ratio of transaction amount to pre-transaction balance
    out["amount_ratio"] = out["amount"] / (out["old_balance"] + 1.0)
    
    # Account draining flag: entire non-zero balance was removed
    out["drained"] = ((out["new_balance"] == 0.0) & (out["old_balance"] > 0.0)).astype(int)
    
    # One-hot encoded transaction types (handles unseen categories safely)
    type_col = df["type"].astype(str) if "type" in df.columns else pd.Series(["UNKNOWN"] * len(df))
    for t in ["TRANSFER", "CASH_OUT", "PAYMENT"]:
        out["type_" + t] = (type_col == t).astype(int)
        
    return out


def make_chronological_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Constructs chronological customer-history features without future leakage.
    Assumes df is ordered by step / time.
    Computes expanding/rolling customer baselines using only strictly preceding transactions.
    """
    df_sorted = df.copy()
    if "step" in df_sorted.columns:
        df_sorted = df_sorted.sort_values(by=["step", "transaction_id"] if "transaction_id" in df_sorted.columns else ["step"]).reset_index(drop=True)
    
    base_feats = make_features(df_sorted)
    
    # Chronological customer grouping
    customer_series = df_sorted["customer_id"] if "customer_id" in df_sorted.columns else pd.Series(0, index=df_sorted.index)
    
    # Calculate expanding customer mean and count shifted by 1 (strictly prior to current transaction)
    grouped = df_sorted.groupby(customer_series)
    
    # Prior transaction count
    prior_tx_count = grouped.cumcount()
    base_feats["prior_tx_count"] = prior_tx_count
    base_feats["insufficient_history"] = (prior_tx_count < 3).astype(int)
    
    # Expanding average amount of prior transactions
    expanding_sum = grouped["amount"].cumsum() - df_sorted["amount"]
    prior_avg_amount = expanding_sum / prior_tx_count.replace(0, np.nan)
    base_feats["prior_avg_amount"] = prior_avg_amount.fillna(df_sorted["amount"])
    
    # Ratio to prior customer average amount
    base_feats["amount_to_prior_avg_ratio"] = (df_sorted["amount"] / (base_feats["prior_avg_amount"] + 1.0)).clip(0, 50)
    
    # Balance discrepancy check: old_balance - amount != new_balance
    expected_new = (df_sorted["old_balance"] - df_sorted["amount"]).clip(lower=0)
    base_feats["balance_discrepancy"] = (df_sorted["new_balance"] - expected_new).abs()
    
    return base_feats