import sqlite3

db_path = r"c:\Users\91904\Documents\antigravity\keen-hubble\data\transactions.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=" * 60)
print("DATABASE OVERVIEW: data/transactions.db")
print("=" * 60)

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
tables = [row[0] for row in cur.fetchall()]

for t in sorted(tables):
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    cnt = cur.fetchone()[0]
    print(f"Table: {t:<22} | Total Rows: {cnt}")

print("\n" + "=" * 60)
print("LATEST 5 TRANSACTIONS")
print("=" * 60)
cur.execute("SELECT transaction_id, customer_id, type, amount, status, created_at FROM transactions ORDER BY transaction_id DESC LIMIT 5")
for r in cur.fetchall():
    print(f"ID #{r[0]:<4} | Cust: {r[1]:<3} | {r[2]:<10} | Rs. {r[3]:>10,.2f} | Status: {r[4]:<20} | Date: {str(r[5])[:19]}")

conn.close()
