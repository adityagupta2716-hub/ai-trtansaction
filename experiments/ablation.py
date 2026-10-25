"""
Ablation Study Framework.

Investigates component contributions:
1. Baseline (Core ML only, no customer history, static threshold p > 0.5 -> block, no limit)
2. + Customer-History Profiling
3. + Expected Utility Action Selection (Approve, Hold, Escalate, Block)
4. + Full System (+ Configurable Human Verification Limit)
"""

from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from model.features import make_features
from model.anomaly import score_transaction
from agent.agent import decide
from agent.utility import choose_action
from backend.responder import get_active_limit_config
from experiments.evaluate import compute_policy_cost

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"


def run_ablation_study():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    db_path = ROOT / "data" / "transactions.db"
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM transactions ORDER BY step, transaction_id", conn)
    conn.close()

    train_val_df, test_df = train_test_split(df, test_size=0.20, stratify=df["is_fraud"], random_state=42)

    ablation_rows = []

    # Variant 1: Pure ML + Static Threshold (No Customer History, No Utility, No Limit)
    v1_decisions = []
    for idx, row in test_df.iterrows():
        s = score_transaction(row.to_dict())
        # Static binary threshold at 0.50
        v1_decisions.append("block" if s["p_fraud"] >= 0.50 else "approve")
    
    df1 = test_df.copy()
    df1["decision"] = v1_decisions
    cost1 = compute_policy_cost(df1)
    cost1["configuration"] = "1. Static ML (No History, No Utility, No Limit)"
    ablation_rows.append(cost1)

    # Variant 2: + Customer-History Profiling (Still static threshold p_adj > 0.50 -> block)
    v2_decisions = []
    neutral_profile = {"num_transactions": 0, "average_amount": 0.0, "past_flags": 0}
    for idx, row in test_df.iterrows():
        s = score_transaction(row.to_dict())
        d = decide(row.to_dict(), s)  # Uses customer history
        p_adj = d["p_fraud"]
        v2_decisions.append("block" if p_adj >= 0.50 else "approve")

    df2 = test_df.copy()
    df2["decision"] = v2_decisions
    cost2 = compute_policy_cost(df2)
    cost2["configuration"] = "2. + Customer History Profiling"
    ablation_rows.append(cost2)

    # Variant 3: + Expected Utility Action Selection (Approve, Hold, Escalate, Block, No Limit)
    v3_decisions = []
    for idx, row in test_df.iterrows():
        s = score_transaction(row.to_dict())
        d = decide(row.to_dict(), s)
        v3_decisions.append(d["decision"])

    df3 = test_df.copy()
    df3["decision"] = v3_decisions
    cost3 = compute_policy_cost(df3)
    cost3["configuration"] = "3. + Expected Utility Theory"
    ablation_rows.append(cost3)

    # Variant 4: Full System (+ Configurable Human Verification Limit)
    limit, _ = get_active_limit_config()
    v4_decisions = []
    for idx, row in test_df.iterrows():
        s = score_transaction(row.to_dict())
        d = decide(row.to_dict(), s)
        if row["amount"] > limit:
            v4_decisions.append("pending_verification")
        else:
            v4_decisions.append(d["decision"])

    df4 = test_df.copy()
    df4["decision"] = v4_decisions
    cost4 = compute_policy_cost(df4)
    cost4["configuration"] = "4. Full System (+ Human Verification Limit)"
    ablation_rows.append(cost4)

    res_df = pd.DataFrame(ablation_rows)[[
        "configuration", "caught_fraud", "missed_fraud", "fraud_recall_pct",
        "blocked_legitimate", "held_legitimate", "human_review_count",
        "human_review_pct", "expected_decision_cost"
    ]]

    res_df.to_csv(REPORTS_DIR / "ablation_study_table.csv", index=False)
    with open(REPORTS_DIR / "ablation_study_table.md", "w", encoding="utf-8") as f:
        f.write("# Ablation Study Analysis\n\n")
        f.write(res_df.to_markdown(index=False))

    return res_df


if __name__ == "__main__":
    df_abl = run_ablation_study()
    print("\n--- Ablation Study Results ---")
    print(df_abl.to_string(index=False))
