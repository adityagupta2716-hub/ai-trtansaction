import requests, json

BASE = "http://127.0.0.1:8000"

# Login as admin
login = requests.post(f"{BASE}/auth/login", json={"username": "admin", "password": "adminPassword123!"}).json()
token = login["access_token"]
H = {"Authorization": f"Bearer {token}"}

SEP = "=" * 62

# -------------------------------------------------------------------
print(SEP)
print("SCENARIO 1 — Normal everyday payment (Rs. 450)")
print(SEP)
r1 = requests.post(f"{BASE}/submit", json={
    "customer_id": 1, "type": "PAYMENT",
    "amount": 450.0, "old_balance": 12000.0, "new_balance": 11550.0
}, headers=H).json()
print(f"  Amount        : Rs. 450")
print(f"  Type          : PAYMENT")
print(f"  Anomaly Score : {r1['anomaly_score']:.3f}  (closer to 0 = normal)")
print(f"  P(Fraud)      : {r1['p_fraud']:.1%}")
print(f"  EU Utilities  : {r1.get('expected_utilities', {})}")
print(f"  Decision      : {r1['decision'].upper()}")
print(f"  Decided By    : {r1['decided_by']}")
print(f"  Reason        : {r1['reasoning'][:130]}")
print()

# -------------------------------------------------------------------
print(SEP)
print("SCENARIO 2 — Suspicious cash-out (account fully drained)")
print(SEP)
r2 = requests.post(f"{BASE}/submit", json={
    "customer_id": 2, "type": "CASH_OUT",
    "amount": 95000.0, "old_balance": 95000.0, "new_balance": 0.0
}, headers=H).json()
print(f"  Amount        : Rs. 95,000")
print(f"  Type          : CASH_OUT  (balance wiped to zero)")
print(f"  Anomaly Score : {r2['anomaly_score']:.3f}")
print(f"  P(Fraud)      : {r2['p_fraud']:.1%}")
print(f"  EU Utilities  : {r2.get('expected_utilities', {})}")
print(f"  Decision      : {r2['decision'].upper()}")
print(f"  Decided By    : {r2['decided_by']}")
print(f"  Reason        : {r2['reasoning'][:130]}")
print()

# -------------------------------------------------------------------
print(SEP)
print("SCENARIO 3 — Large transfer (exceeds Rs. 5,00,000 limit)")
print(SEP)
r3 = requests.post(f"{BASE}/submit", json={
    "customer_id": 3, "type": "TRANSFER",
    "amount": 650000.0, "old_balance": 800000.0, "new_balance": 150000.0
}, headers=H).json()
print(f"  Amount        : Rs. 6,50,000")
print(f"  Active Limit  : Rs. {r3.get('active_limit', 500000):,.0f}")
print(f"  Type          : TRANSFER")
print(f"  Anomaly Score : {r3['anomaly_score']:.3f}")
print(f"  P(Fraud)      : {r3['p_fraud']:.1%}")
print(f"  Decision      : {r3['decision'].upper()}")
print(f"  Decided By    : {r3['decided_by']}")
print(f"  Reason        : {r3['reasoning'][:130]}")
txn_id = r3.get("transaction_id", "N/A")
print(f"  Transaction ID: {txn_id}  --> Sent to Human Review Queue")
print()

# -------------------------------------------------------------------
print(SEP)
print("STEP 4 — Reviewer logs in and resolves the pending case")
print(SEP)
rev_login = requests.post(f"{BASE}/auth/login", json={"username": "reviewer", "password": "reviewerPassword123!"}).json()
RH = {"Authorization": f"Bearer {rev_login['access_token']}"}
queue = requests.get(f"{BASE}/review-queue", headers=RH).json()
print(f"  Pending cases in queue : {len(queue)}")

if queue:
    case = queue[0]
    tid = case["transaction_id"]
    print(f"  Reviewing case        : #{tid}  Amount Rs. {case['amount']:,.0f}")
    review_result = requests.post(f"{BASE}/review/{tid}", json={
        "review_outcome": "approve",
        "fraud_confirmed": 0,
        "review_reason": "KYC verified. Customer confirmed large transfer for property purchase."
    }, headers=RH).json()
    print(f"  Reviewer Decision     : APPROVE (Confirmed Legitimate)")
    print(f"  Review Reason         : KYC verified. Customer confirmed large transfer.")
    print(f"  Result                : {review_result}")
print()

# -------------------------------------------------------------------
print(SEP)
print("STEP 5 — Audit trail (last 5 entries)")
print(SEP)
audit = requests.get(f"{BASE}/audit-logs", params={"limit": 5}, headers=H).json()
for entry in audit[:5]:
    print(f"  [{entry['created_at'][:19]}] {entry['actor_type']:8} | {entry['action']:30} | {str(entry.get('details',''))[:60]}")
