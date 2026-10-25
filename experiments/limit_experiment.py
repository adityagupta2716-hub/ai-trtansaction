"""
Verification Limit Experimentation.

Evaluates how varying the mandatory human verification limit L affects:
- Human review workload (count and %)
- Missed fraud cases
- Legitimate transaction friction
- Expected decision cost

Outputs:
- reports/limit_experiment_table.csv & .md
- reports/limit_tradeoff_plot.png
"""

from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from model.anomaly import score_transaction
from agent.agent import decide
from experiments.evaluate import compute_policy_cost

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"


def run_limit_experiments():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    db_path = ROOT / "data" / "transactions.db"
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM transactions ORDER BY step, transaction_id", conn)
    conn.close()

    train_val_df, test_df = train_test_split(df, test_size=0.20, stratify=df["is_fraud"], random_state=42)

    candidate_limits = [10000.0, 50000.0, 100000.0, 250000.0, 500000.0, 1000000.0, float("inf")]

    # Precompute agent decisions on test set
    agent_decisions = []
    for idx, row in test_df.iterrows():
        s = score_transaction(row.to_dict())
        d = decide(row.to_dict(), s)
        agent_decisions.append(d["decision"])

    test_df_cached = test_df.copy()
    test_df_cached["agent_decision"] = agent_decisions

    results = []
    for L in candidate_limits:
        final_decisions = []
        for idx, row in test_df_cached.iterrows():
            amt = row["amount"]
            if amt > L:
                final_decisions.append("pending_verification")
            else:
                final_decisions.append(row["agent_decision"])

        eval_df = test_df_cached.copy()
        eval_df["decision"] = final_decisions
        cost_res = compute_policy_cost(eval_df)
        cost_res["verification_limit"] = "$10k" if L == 10000 else (
            "$50k" if L == 50000 else (
                "$100k" if L == 100000 else (
                    "$250k" if L == 250000 else (
                        "$500k" if L == 500000 else (
                            "$1.0M" if L == 1000000 else "No Limit (Inf)"
                        )
                    )
                )
            )
        )
        cost_res["numeric_limit"] = L
        results.append(cost_res)

    res_df = pd.DataFrame(results)[[
        "verification_limit", "numeric_limit", "human_review_count",
        "human_review_pct", "caught_fraud", "missed_fraud",
        "blocked_legitimate", "expected_decision_cost"
    ]]

    # Save Markdown and CSV
    res_df.to_csv(REPORTS_DIR / "limit_experiment_table.csv", index=False)
    with open(REPORTS_DIR / "limit_experiment_table.md", "w", encoding="utf-8") as f:
        f.write("# Verification Limit Sensitivity Experiment\n\n")
        f.write(res_df.to_markdown(index=False))

    # Generate Trade-off Plot
    plot_df = res_df[res_df["numeric_limit"] != float("inf")].copy()
    fig, ax1 = plt.subplots(figsize=(9, 5))

    color = "tab:blue"
    ax1.set_xlabel("Verification Limit L ($)")
    ax1.set_ylabel("Human Review Workload (%)", color=color)
    ax1.plot(plot_df["numeric_limit"], plot_df["human_review_pct"], marker="o", color=color, linewidth=2)
    ax1.tick_params(axis="y", labelcolor=color)
    ax1.grid(True, linestyle="--", alpha=0.5)

    ax2 = ax1.twinx()
    color = "tab:red"
    ax2.set_ylabel("Expected Decision Cost", color=color)
    ax2.plot(plot_df["numeric_limit"], plot_df["expected_decision_cost"], marker="s", color=color, linewidth=2, linestyle="--")
    ax2.tick_params(axis="y", labelcolor=color)

    plt.title("Workload vs Decision Cost Across Verification Limits")
    fig.tight_layout()
    plt.savefig(REPORTS_DIR / "limit_tradeoff_plot.png", dpi=150)
    plt.close()

    print("Verification limit experiments complete. Saved to:", REPORTS_DIR)
    return res_df


if __name__ == "__main__":
    df_limits = run_limit_experiments()
    print("\n--- Limit Sensitivity Analysis ---")
    print(df_limits.to_string(index=False))
