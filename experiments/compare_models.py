"""
Comparative Baseline Evaluation Framework.

Compares 6 methods on identical test data splits:
1. Rule-Based Baseline
2. Isolation Forest (Uncalibrated Anomaly Threshold)
3. Supervised Logistic Regression
4. Random Forest Classifier
5. Customer-Aware Calibrated Model
6. Complete AI System (Customer-Aware + Expected Utility + Human Verification Limit)
"""

from pathlib import Path
import sqlite3
import yaml
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from model.features import make_features, make_chronological_features
from model.anomaly import score_transaction
from agent.agent import decide
from backend.responder import get_active_limit_config
from experiments.evaluate import compute_metrics, compute_policy_cost, generate_roc_and_pr_plots, generate_calibration_plot

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"


def run_model_comparison(output_reports: bool = True):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    db_path = ROOT / "data" / "transactions.db"
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM transactions ORDER BY step, transaction_id", conn)
    conn.close()

    # Split: 65% train, 15% val, 20% test (stratified, seed 42)
    train_val_df, test_df = train_test_split(df, test_size=0.20, stratify=df["is_fraud"], random_state=42)
    train_df, val_df = train_test_split(train_val_df, test_size=0.1875, stratify=train_val_df["is_fraud"], random_state=42)

    X_train = make_features(train_df)
    y_train = train_df["is_fraud"]

    X_test = make_features(test_df)
    y_test = test_df["is_fraud"].values

    results = []
    prob_dict = {}

    # -------------------------------------------------------------
    # 1. Simple Rule-Based Baseline
    # Rule: Flag as fraud if (drained == 1 and amount > 10,000 and type in [TRANSFER, CASH_OUT])
    # -------------------------------------------------------------
    rule_pred = (
        (test_df["new_balance"] == 0)
        & (test_df["old_balance"] > 0)
        & (test_df["amount"] > 10000)
        & (test_df["type"].isin(["TRANSFER", "CASH_OUT"]))
    ).astype(int).values
    rule_prob = rule_pred.astype(float)
    rule_metrics = compute_metrics(y_test, rule_pred, rule_prob)
    rule_metrics["model"] = "1. Rule-Based Baseline"
    results.append(rule_metrics)
    prob_dict["Rule-Based"] = rule_prob

    # -------------------------------------------------------------
    # 2. Isolation Forest Alone (Uncalibrated Anomaly Detection)
    # -------------------------------------------------------------
    from sklearn.ensemble import IsolationForest
    iso = IsolationForest(n_estimators=200, contamination=0.05, random_state=42).fit(X_train)
    raw_iso_scores = -iso.score_samples(X_test)
    lo, hi = float(raw_iso_scores.min()), float(raw_iso_scores.max())
    iso_prob = np.clip((raw_iso_scores - lo) / ((hi - lo) if (hi - lo) > 0 else 1.0), 0, 1)
    iso_thresh = np.percentile(iso_prob, 95)
    iso_pred = (iso_prob >= iso_thresh).astype(int)
    iso_metrics = compute_metrics(y_test, iso_pred, iso_prob)
    iso_metrics["model"] = "2. Isolation Forest"
    results.append(iso_metrics)
    prob_dict["Isolation Forest"] = iso_prob

    # -------------------------------------------------------------
    # 3. Supervised Logistic Regression
    # -------------------------------------------------------------
    lr = LogisticRegression(max_iter=1000, random_state=42).fit(X_train, y_train)
    lr_prob = lr.predict_proba(X_test)[:, 1]
    lr_pred = (lr_prob >= 0.50).astype(int)
    lr_metrics = compute_metrics(y_test, lr_pred, lr_prob)
    lr_metrics["model"] = "3. Logistic Regression"
    results.append(lr_metrics)
    prob_dict["Logistic Regression"] = lr_prob

    # -------------------------------------------------------------
    # 4. Supervised Random Forest
    # -------------------------------------------------------------
    rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42).fit(X_train, y_train)
    rf_prob = rf.predict_proba(X_test)[:, 1]
    rf_pred = (rf_prob >= 0.50).astype(int)
    rf_metrics = compute_metrics(y_test, rf_pred, rf_prob)
    rf_metrics["model"] = "4. Random Forest"
    results.append(rf_metrics)
    prob_dict["Random Forest"] = rf_prob

    # -------------------------------------------------------------
    # 5. Customer-Aware Calibrated Approach
    # -------------------------------------------------------------
    cust_probs = []
    cust_preds = []
    for idx, row in test_df.iterrows():
        txn_dict = row.to_dict()
        s = score_transaction(txn_dict)
        d = decide(txn_dict, s)
        p = d["p_fraud"]
        cust_probs.append(p)
        cust_preds.append(1 if d["decision"] in ("block", "escalate") else 0)

    cust_prob = np.array(cust_probs)
    cust_pred = np.array(cust_preds)
    cust_metrics = compute_metrics(y_test, cust_pred, cust_prob)
    cust_metrics["model"] = "5. Customer-Aware Calibrated"
    results.append(cust_metrics)
    prob_dict["Customer-Aware"] = cust_prob

    # -------------------------------------------------------------
    # 6. Complete System (Customer-Aware + Expected Utility + Verification Limit)
    # -------------------------------------------------------------
    final_decisions = []
    limit, policy_ver = get_active_limit_config()
    for idx, row in test_df.iterrows():
        txn_dict = row.to_dict()
        s = score_transaction(txn_dict)
        d = decide(txn_dict, s)
        amt = txn_dict["amount"]
        if amt > limit:
            final_decisions.append("pending_verification")
        else:
            final_decisions.append(d["decision"])

    comp_df = test_df.copy()
    comp_df["decision"] = final_decisions
    comp_cost = compute_policy_cost(comp_df, decision_col="decision")

    complete_pred = np.array([1 if d in ("block", "escalate", "pending_verification") else 0 for d in final_decisions])
    complete_metrics = compute_metrics(y_test, complete_pred, cust_prob)
    complete_metrics["model"] = "6. Complete System (Ours)"
    results.append(complete_metrics)
    prob_dict["Complete System"] = cust_prob

    # Compile Table
    res_df = pd.DataFrame(results)[["model", "precision", "recall", "f1", "fpr", "roc_auc", "pr_auc", "brier_score"]]

    if output_reports:
        # Save Tables & Plots
        res_df.to_csv(REPORTS_DIR / "model_comparison_table.csv", index=False)
        with open(REPORTS_DIR / "model_comparison_table.md", "w", encoding="utf-8") as f:
            f.write("# Model Comparison Benchmark Table\n\n")
            f.write(res_df.to_markdown(index=False))
            f.write("\n\n## Policy Performance (Complete System)\n\n")
            f.write(pd.DataFrame([comp_cost]).to_markdown(index=False))

        generate_roc_and_pr_plots(y_test, prob_dict, REPORTS_DIR)
        generate_calibration_plot(y_test, prob_dict, REPORTS_DIR)
        print("Comparison completed. Reports generated in:", REPORTS_DIR)

    return res_df, comp_cost


if __name__ == "__main__":
    df_res, cost_res = run_model_comparison(output_reports=True)
    print("\n--- Model Comparison Benchmark ---")
    print(df_res.to_string(index=False))
    print("\n--- Policy Cost Analysis ---")
    print(cost_res)
