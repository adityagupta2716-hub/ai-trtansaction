# Research Experimentation Suite

This module provides reproducible, leakage-free empirical experiments comparing baseline fraud detection methods, customer-aware utility modeling, ablation variants, and verification limit trade-offs.

## Architecture

- `config.yaml` — Dataset sources, model hyperparameters, split parameters, cost weights.
- `train.py` — Stratified/chronological splits, Isolation Forest training, Logistic Regression calibrator fitting.
- `evaluate.py` — Statistical evaluation metrics (PR-AUC, ROC-AUC, Brier score) and policy cost accounting.
- `compare_models.py` — Benchmarks 6 methods on identical test splits.
- `ablation.py` — Evaluates contributions of customer history, utility decisions, and human verification limits.
- `limit_experiment.py` — Sensitivity analysis across mandatory verification limits ($L$).
- `../reports/` — Output directory containing generated tables (`.csv`, `.md`) and diagnostic plots (`.png`).

## Running Experiments

From the repository root:

```bash
# 1. Run Baseline Model Comparisons
python -m experiments.compare_models

# 2. Run Ablation Study
python -m experiments.ablation

# 3. Run Verification Limit Sensitivity Analysis
python -m experiments.limit_experiment
```

## Generated Artifacts

- `reports/model_comparison_table.csv` and `.md`
- `reports/ablation_study_table.csv` and `.md`
- `reports/limit_experiment_table.csv` and `.md`
- `reports/roc_curve_comparison.png`
- `reports/pr_curve_comparison.png`
- `reports/calibration_curves.png`
- `reports/limit_tradeoff_plot.png`
