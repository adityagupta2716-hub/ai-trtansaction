# Model Comparison Benchmark Table

| model                        |   precision |   recall |     f1 |    fpr |   roc_auc |   pr_auc |   brier_score |
|:-----------------------------|------------:|---------:|-------:|-------:|----------:|---------:|--------------:|
| 1. Rule-Based Baseline       |      1      |      1   | 1      | 0      |    1      |   1      |        0      |
| 2. Isolation Forest          |      0.6364 |      0.7 | 0.6667 | 0.0204 |    0.9786 |   0.5238 |        0.0643 |
| 3. Logistic Regression       |      0.9091 |      1   | 0.9524 | 0.0051 |    1      |   1      |        0.0033 |
| 4. Random Forest             |      0.875  |      0.7 | 0.7778 | 0.0051 |    0.9985 |   0.9698 |        0.0112 |
| 5. Customer-Aware Calibrated |      1      |      0.9 | 0.9474 | 0      |    1      |   1      |        0.0096 |
| 6. Complete System (Ours)    |      0.75   |      0.9 | 0.8182 | 0.0153 |    1      |   1      |        0.0096 |

## Policy Performance (Complete System)

|   total_transactions |   total_fraud |   caught_fraud |   missed_fraud |   fraud_recall_pct |   blocked_legitimate |   held_legitimate |   human_review_count |   human_review_pct |   expected_decision_cost |
|---------------------:|--------------:|---------------:|---------------:|-------------------:|---------------------:|------------------:|---------------------:|-------------------:|-------------------------:|
|                  206 |            10 |             10 |              0 |                100 |                    0 |                 5 |                    6 |               2.91 |                      130 |