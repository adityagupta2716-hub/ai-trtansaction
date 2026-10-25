# Ablation Study Analysis

| configuration                                   |   caught_fraud |   missed_fraud |   fraud_recall_pct |   blocked_legitimate |   held_legitimate |   human_review_count |   human_review_pct |   expected_decision_cost |
|:------------------------------------------------|---------------:|---------------:|-------------------:|---------------------:|------------------:|---------------------:|-------------------:|-------------------------:|
| 1. Static ML (No History, No Utility, No Limit) |              6 |              4 |                 60 |                    0 |                 0 |                    0 |               0    |                      400 |
| 2. + Customer History Profiling                 |              6 |              4 |                 60 |                    0 |                 0 |                    0 |               0    |                      400 |
| 3. + Expected Utility Theory                    |             10 |              0 |                100 |                    0 |                 7 |                    3 |               1.46 |                      101 |
| 4. Full System (+ Human Verification Limit)     |             10 |              0 |                100 |                    0 |                 5 |                    6 |               2.91 |                      130 |