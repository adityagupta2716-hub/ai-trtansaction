"""
Evaluation and Metrics Engine for Research Experiments.

Calculates:
- Statistical ML metrics: PR-AUC, ROC-AUC, F1, Precision, Recall, Brier score, Log Loss.
- Operational & Policy metrics: Review workload %, missed fraud cases, false alarm rate,
  and Expected Decision Cost.
- Generates publication-quality matplotlib diagnostic plots.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
    brier_score_loss,
    log_loss,
)
from sklearn.calibration import calibration_curve


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """Calculates comprehensive classification and probability calibration metrics."""
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))

    metrics = {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fpr": round(fpr, 4),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }

    if y_prob is not None:
        try:
            metrics["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 4)
        except Exception:
            metrics["roc_auc"] = 0.5
        try:
            metrics["pr_auc"] = round(float(average_precision_score(y_true, y_prob)), 4)
        except Exception:
            metrics["pr_auc"] = float(np.mean(y_true))
        try:
            metrics["brier_score"] = round(float(brier_score_loss(y_true, y_prob)), 4)
        except Exception:
            metrics["brier_score"] = None
        try:
            metrics["log_loss"] = round(float(log_loss(y_true, y_prob, labels=[0, 1])), 4)
        except Exception:
            metrics["log_loss"] = None

    return metrics


def compute_policy_cost(
    df: pd.DataFrame,
    decision_col: str = "decision",
    truth_col: str = "is_fraud",
    cost_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Computes operational and financial policy costs:
    - Missed fraud (action == approve while is_fraud == 1)
    - Blocked legit (action == block while is_fraud == 0)
    - Held legit (action == hold while is_fraud == 0)
    - Human review volume (action in [escalate, pending_verification])
    """
    if cost_weights is None:
        cost_weights = {
            "approve_fraud": 100.0,
            "block_legit": 50.0,
            "hold_legit": 8.0,
            "escalate_cost": 15.0,
        }

    total = len(df)
    total_fraud = int(df[truth_col].sum())
    total_legit = total - total_fraud

    missed_fraud = int(((df[decision_col] == "approve") & (df[truth_col] == 1)).sum())
    caught_fraud = total_fraud - missed_fraud

    blocked_legit = int(((df[decision_col] == "block") & (df[truth_col] == 0)).sum())
    held_legit = int(((df[decision_col] == "hold") & (df[truth_col] == 0)).sum())

    review_count = int(df[decision_col].isin(["escalate", "pending_verification"]).sum())
    review_pct = round((review_count / total * 100.0) if total > 0 else 0.0, 2)

    total_decision_cost = (
        missed_fraud * cost_weights["approve_fraud"]
        + blocked_legit * cost_weights["block_legit"]
        + held_legit * cost_weights["hold_legit"]
        + review_count * cost_weights["escalate_cost"]
    )

    return {
        "total_transactions": total,
        "total_fraud": total_fraud,
        "caught_fraud": caught_fraud,
        "missed_fraud": missed_fraud,
        "fraud_recall_pct": round((caught_fraud / total_fraud * 100.0) if total_fraud > 0 else 100.0, 2),
        "blocked_legitimate": blocked_legit,
        "held_legitimate": held_legit,
        "human_review_count": review_count,
        "human_review_pct": review_pct,
        "expected_decision_cost": round(total_decision_cost, 2),
    }


def generate_roc_and_pr_plots(y_true: np.ndarray, model_probs: Dict[str, np.ndarray], output_dir: Path):
    """Generates comparison ROC and PR curves."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. ROC Plot
    plt.figure(figsize=(8, 6))
    for name, probs in model_probs.items():
        from sklearn.metrics import roc_curve
        fpr, tpr, _ = roc_curve(y_true, probs)
        auc = roc_auc_score(y_true, probs)
        plt.plot(fpr, tpr, label=f"{name} (AUC = {auc:.3f})")
    plt.plot([0, 1], [0, 1], "k--", label="Chance")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("Comparative ROC Curves")
    plt.legend(loc="lower right")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_dir / "roc_curve_comparison.png", dpi=150)
    plt.close()

    # 2. PR Plot
    plt.figure(figsize=(8, 6))
    for name, probs in model_probs.items():
        from sklearn.metrics import precision_recall_curve
        p, r, _ = precision_recall_curve(y_true, probs)
        ap = average_precision_score(y_true, probs)
        plt.plot(r, p, label=f"{name} (AP = {ap:.3f})")
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Comparative Precision-Recall Curves")
    plt.legend(loc="upper right")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_dir / "pr_curve_comparison.png", dpi=150)
    plt.close()


def generate_calibration_plot(y_true: np.ndarray, model_probs: Dict[str, np.ndarray], output_dir: Path):
    """Generates probability calibration curves."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 6))
    for name, probs in model_probs.items():
        prob_true, prob_pred = calibration_curve(y_true, probs, n_bins=10)
        brier = brier_score_loss(y_true, probs)
        plt.plot(prob_pred, prob_true, marker="o", label=f"{name} (Brier = {brier:.4f})")
    plt.plot([0, 1], [0, 1], "k--", label="Perfect Calibration")
    plt.xlabel("Mean Predicted Probability")
    plt.ylabel("Fraction of Positives")
    plt.title("Reliability Diagram (Calibration Curves)")
    plt.legend(loc="upper left")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_dir / "calibration_curves.png", dpi=150)
    plt.close()
