# Fraud Detection & Decision Methodology

## 1. Feature Engineering & Leakage Prevention

The system computes features strictly from information available prior to the execution of a transaction.

### Core Features
- $\text{amount}$: Numerical transaction value.
- $\text{old\_balance}$: Sender pre-transaction balance.
- $\text{new\_balance}$: Sender post-transaction balance.
- $\text{amount\_ratio} = \frac{\text{amount}}{\text{old\_balance} + 1.0}$
- $\text{drained} = \mathbb{I}(\text{new\_balance} == 0 \land \text{old\_balance} > 0)$
- Categorical one-hot encodings for `TRANSFER`, `CASH_OUT`, and `PAYMENT`.

### Chronological Customer History
To prevent lookahead leakage, historical baselines (prior transaction frequency, expanding mean, and past anomaly flags) are computed using temporal cutoff gating:
$$\text{Filter: } \text{step} < \text{cutoff\_step}$$

## 2. Anomaly Detection: Calibrated Isolation Forest

### Isolation Forest Anomaly Score
Isolation Forest isolates anomalies by randomly partitioning feature space. Shorter average path lengths across ensemble trees correspond to structural outliers.
The raw score is defined as:
$$\text{raw\_score} = -\frac{1}{M}\sum_{i=1}^M h_i(x)$$
This is normalized into an anomaly score $s \in [0, 1]$ relative to the empirical training bounds $[lo, hi]$.

### Probability Calibration
An anomaly score is an outlierness metric, not a probability measure. A **Logistic Regression Calibrator** maps the vector:
$$z = [s, \text{drained}, \min(\text{amount\_ratio}, 2.0), \text{is\_TRANSFER}, \text{is\_CASH\_OUT}]$$
into a posterior calibrated probability:
$$P(\text{fraud}) = \frac{1}{1 + e^{-(\beta^T z + \beta_0)}}$$

## 3. Context-Aware Probability Adjustment

The agent adjusts $P(\text{fraud})$ using established customer profiles:
- If customer has $\ge 5$ past transactions and current amount $> 10\times$ average: $+0.15$
- Else if amount $> 5\times$ average: $+0.07$
- If customer has $\ge 2$ past review flags: $+0.05$
- Bounded strictly within $[0.0, 1.0]$.

## 4. Expected Utility Theory (EUT)

Let $A = \{\text{approve}, \text{hold}, \text{escalate}, \text{block}\}$.  
Let $p = P(\text{fraud})$. The expected utility of action $a$ is:
$$\mathbb{E}[U(a)] = p \cdot U(a, \text{fraud}) + (1 - p) \cdot U(a, \text{legit})$$

### Payoff Matrix
| Action ($a$) | Utility if Fraud ($U_{\text{fraud}}$) | Utility if Legit ($U_{\text{legit}}$) |
| :--- | :---: | :---: |
| **Approve** | **-100** | **+5** |
| **Hold** | **+30** | **-8** |
| **Escalate** | **+55** | **-15** |
| **Block** | **+80** | **-50** |

The optimal action is selected via:
$$a^* = \arg\max_{a \in A} \mathbb{E}[U(a)]$$

### Decision Margin Heuristic
$$\Delta U = \mathbb{E}[U(a^*)] - \mathbb{E}[U(a_{\text{second}})]$$
$$\text{Normalized Margin} = 0.5 + 0.5 \times \min\left(1.0, \frac{\Delta U}{30.0}\right)$$
*(Note: Labeled strictly as a decision-margin heuristic rather than a calibrated statistical confidence).*

## 5. Configurable Mandatory Human Verification Limit

Let $A$ represent transaction amount and $L$ the active database-backed limit.
$$\text{If } A > L \implies \text{Route to } \texttt{pending\_verification} \text{ (decided by limit policy)}$$
$$\text{If } A \le L \implies \text{Execute autonomous agent action } a^*$$

Transactions in `pending_verification` cannot be autonomously approved or blocked, guaranteeing compliance sign-off.
