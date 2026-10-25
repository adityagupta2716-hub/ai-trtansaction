"""
Model Training and Calibration Pipeline for Research Experiments.

Executes:
1. Leakage-safe chronological or stratified data split.
2. Training of Isolation Forest on normal baseline transactions.
3. Training of Logistic Regression Calibrator on held-out calibration set.
4. Export of model artifacts and split metadata.
"""

from pathlib import Path
import sqlite3
import joblib
import yaml
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from model.features import make_features

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "experiments" / "config.yaml"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def train_models(verbose: bool = True):
    config = load_config()
    db_path = ROOT / config["dataset"]["source"]
    
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM transactions ORDER BY step, transaction_id", conn)
    conn.close()

    if verbose:
        print(f"Loaded {len(df):,} transactions for experimental training.")
        print(f"Fraud prevalence: {df['is_fraud'].sum()} / {len(df)} ({df['is_fraud'].mean():.2%})")

    # Chronological or Stratified Train-Val-Test Split
    test_size = config["dataset"]["test_size"]
    val_size = config["dataset"]["val_size"]
    seed = config["dataset"]["random_seed"]

    # Use stratified split with fixed random seed
    train_val_df, test_df = train_test_split(
        df, test_size=test_size, stratify=df["is_fraud"], random_state=seed
    )
    val_rel_size = val_size / (1.0 - test_size)
    train_df, val_df = train_test_split(
        train_val_df, test_size=val_rel_size, stratify=train_val_df["is_fraud"], random_state=seed
    )

    if verbose:
        print(f"Train set: {len(train_df):,} | Val set: {len(val_df):,} | Test set: {len(test_df):,}")

    # Extract Features strictly on respective splits
    X_train = make_features(train_df)
    y_train = train_df["is_fraud"]

    X_val = make_features(val_df)
    y_val = val_df["is_fraud"]

    X_test = make_features(test_df)
    y_test = test_df["is_fraud"]

    # 1. Fit Isolation Forest on Train Set
    iso_cfg = config["models"]["isolation_forest"]
    iso = IsolationForest(
        n_estimators=iso_cfg["n_estimators"],
        contamination=iso_cfg["contamination"],
        random_state=iso_cfg["random_state"],
    )
    iso.fit(X_train)

    raw_train = -iso.score_samples(X_train)
    lo, hi = float(raw_train.min()), float(raw_train.max())

    def scale_score(raw):
        denom = (hi - lo) if (hi - lo) > 1e-6 else 1.0
        return np.clip((raw - lo) / denom, 0.0, 1.0)

    score_val = scale_score(-iso.score_samples(X_val))

    # 2. Fit Calibrator on Validation Set (held-out from Isolation Forest training)
    def prep_calib_features(feats, scores):
        return np.column_stack([
            scores,
            feats["drained"],
            np.clip(feats["amount_ratio"], 0.0, 2.0),
            feats["type_TRANSFER"],
            feats["type_CASH_OUT"],
        ])

    calib_X_val = prep_calib_features(X_val, score_val)
    lr_cfg = config["models"]["logistic_regression"]
    calibrator = LogisticRegression(max_iter=lr_cfg["max_iter"], random_state=lr_cfg["random_state"])
    calibrator.fit(calib_X_val, y_val)

    threshold = float(np.percentile(scale_score(raw_train), 95))

    # Save Bundle
    model_bundle = {
        "iso": iso,
        "lo": lo,
        "hi": hi,
        "calibrator": calibrator,
        "threshold": threshold,
        "feature_names": list(X_train.columns),
    }

    model_path = ROOT / "model" / "model.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_bundle, model_path)

    if verbose:
        print(f"Model bundle saved to: {model_path}")

    return {
        "train_df": train_df,
        "val_df": val_df,
        "test_df": test_df,
        "bundle": model_bundle,
    }


if __name__ == "__main__":
    train_models(verbose=True)
