# Verification Limit Sensitivity Experiment

| verification_limit   |   numeric_limit |   human_review_count |   human_review_pct |   caught_fraud |   missed_fraud |   blocked_legitimate |   expected_decision_cost |
|:---------------------|----------------:|---------------------:|-------------------:|---------------:|---------------:|---------------------:|-------------------------:|
| $10k                 |       10000     |                   14 |               6.8  |             10 |              0 |                    0 |                      242 |
| $50k                 |       50000     |                   14 |               6.8  |             10 |              0 |                    0 |                      242 |
| $100k                |      100000     |                   13 |               6.31 |             10 |              0 |                    0 |                      227 |
| $250k                |      250000     |                    8 |               3.88 |             10 |              0 |                    0 |                      152 |
| $500k                |      500000     |                    6 |               2.91 |             10 |              0 |                    0 |                      130 |
| $1.0M                |           1e+06 |                    4 |               1.94 |             10 |              0 |                    0 |                      116 |
| No Limit (Inf)       |         inf     |                    3 |               1.46 |             10 |              0 |                    0 |                      101 |