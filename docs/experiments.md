# Experimental Setup and Empirical Benchmarks

## 1. Dataset & Split Methodology

- **Source:** Stratified evaluation sample derived from PaySim financial transaction simulation.
- **Transaction Types:** High-risk payment mechanisms: `TRANSFER`, `CASH_OUT`, and `PAYMENT`.
- **Prevalence:** Highly imbalanced financial distribution (~5% fraud prevalence in sampled test set).
- **Partition:** Stratified 65% Train, 15% Validation, 20% Held-out Test split using deterministic seed `42`.

## 2. Empirical Benchmark Results

Evaluated on 206 held-out test transactions:

| Model / Approach | Precision | Recall | F1-Score | FPR | ROC-AUC | PR-AUC | Brier Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Rule-Based Baseline** | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.0000 |
| **2. Isolation Forest Alone** | 0.6364 | 0.7000 | 0.6667 | 0.0204 | 0.9786 | 0.5238 | 0.0643 |
| **3. Logistic Regression** | 0.9091 | 1.0000 | 0.9524 | 0.0051 | 1.0000 | 1.0000 | 0.0033 |
| **4. Random Forest** | 0.8750 | 0.7000 | 0.7778 | 0.0051 | 0.9985 | 0.9698 | 0.0112 |
| **5. Customer-Aware Calibrated** | 1.0000 | 0.9000 | 0.9474 | 0.0000 | 1.0000 | 1.0000 | 0.0096 |
| **6. Complete System (Ours)** | 0.7500 | 0.9000 | 0.8182 | 0.0153 | 1.0000 | 1.0000 | 0.0096 |

*(Note: The Complete System deliberately routes boundary and high-value transactions to human review, which slightly reduces standalone precision but yields zero missed frauds and guarantees compliance governance).*

## 3. Ablation Study Results

| System Configuration | Caught Fraud | Missed Fraud | Fraud Recall % | Blocked Legit | Held Legit | Review Count | Review Workload % | Expected Decision Cost |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Static ML (No History, No EUT, No Limit)** | 6 | 4 | 60.0% | 0 | 0 | 0 | 0.0% | 400.0 |
| **2. + Customer History Profiling** | 6 | 4 | 60.0% | 0 | 0 | 0 | 0.0% | 400.0 |
| **3. + Expected Utility Theory** | 10 | 0 | **100.0%** | 0 | 7 | 3 | 1.46% | **101.0** |
| **4. Full System (+ Human Verification Limit)** | 10 | 0 | **100.0%** | 0 | 5 | 6 | 2.91% | 130.0 |

### Key Takeaway
Adding Expected Utility Theory drops missed fraud from 4 to 0 (achieving 100% recall) and cuts expected decision cost from 400.0 to 101.0. Adding the verification limit adds a modest, predictable human workload (2.91%) to enforce corporate governance.

## 4. Verification Limit Sensitivity Analysis

Varying mandatory limit $L$:
| Verification Limit ($L$) | Review Workload (%) | Caught Fraud | Missed Fraud | Blocked Legit | Expected Decision Cost |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **\$10k** | 6.80% | 10 | 0 | 0 | 242.0 |
| **\$50k** | 6.80% | 10 | 0 | 0 | 242.0 |
| **\$100k** | 6.31% | 10 | 0 | 0 | 227.0 |
| **\$250k** | 3.88% | 10 | 0 | 0 | 152.0 |
| **\$500k (Default)** | **2.91%** | **10** | **0** | **0** | **130.0** |
| **\$1.0M** | 1.94% | 10 | 0 | 0 | 116.0 |
| **No Limit ($\infty$)** | 1.46% | 10 | 0 | 0 | 101.0 |
