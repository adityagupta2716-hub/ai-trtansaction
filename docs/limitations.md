# Assumptions, Limitations, and Operational Considerations

## 1. Data & Environment Assumptions
- **Synthetic Benchmark Data:** Empirical evaluations are conducted on samples derived from the PaySim synthetic simulator. While PaySim models realistic account draining and balance discrepancies, it does not capture complex multi-leg money laundering syndicates, synthetic identity fraud, or cross-border currency conversion fees.
- **Uniform Utility Units:** The payoff matrix values (e.g., -100 for approving fraud, +5 for approving legitimate) represent standardized utility weights in arbitrary project units rather than direct dollar conversions. Real deployment requires calibrating these weights against actual chargeback costs and dispute litigation liabilities.

## 2. Model & Algorithmic Limitations
- **Cold-Start Customers:** Customers with fewer than 3 historical transactions lack reliable empirical baselines. The system defaults their customer adjustment to neutral and assigns an `INSUFFICIENT_HISTORY` risk indicator, falling back directly to the Isolation Forest score.
- **Tree Retraining Overhead:** Online learning is achieved by adapting the Expected Utility payoff matrix (`learning/feedback.py`). The core Isolation Forest trees are not retrained on single instances to avoid catastrophic forgetting and maintain sub-10ms inference latencies. Periodic batch retraining is recommended.

## 3. Human Review & Operational Considerations
- **Simulated vs. Live Human Performance:** In automated benchmark scripts, simulated reviewers are assumed to correctly resolve escalated cases based on ground-truth labels. In real banking operations, human analysts have non-zero error rates, fatigue, and varying review latencies.
- **Review Queue Saturation:** Lowering the verification limit $L$ too aggressively increases the manual review volume. At $L = \$10,000$, review workload reaches 6.8% of all transactions, which may overwhelm compliance teams in high-throughput retail banking environments.

## 4. Security & Compliance
- **Cryptographic Secrets:** In production, `JWT_SECRET_KEY` and database credentials must be injected via secure key vaults (e.g., AWS Secrets Manager, HashiCorp Vault) rather than local `.env` files.
- **Regulatory Governance:** The mandatory human verification limit guarantees compliance with regulatory mandates (such as FinCEN currency transaction reporting thresholds) by preventing automated AI execution on transactions exceeding institutional limits.
