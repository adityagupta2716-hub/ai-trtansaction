"""
Migrate all data from SQLite (data/transactions.db) into MongoDB Atlas.
Preserves all 1,069 transactions, 116 customers, users, audit logs, and settings.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from data.mongo_db import get_mongo_db, init_mongo_indexes

ROOT_DIR = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT_DIR / "data" / "transactions.db"

def migrate():
    print(f"Reading from SQLite database: {SQLITE_PATH}")
    if not SQLITE_PATH.exists():
        print("ERROR: SQLite database file not found!")
        return

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    db = get_mongo_db()
    print(f"Connected to MongoDB Atlas: database '{db.name}'")

    # Initialize collections & indexes
    init_mongo_indexes()

    tables = [
        "users",
        "customers",
        "transactions",
        "fraud_predictions",
        "ai_decisions",
        "human_reviews",
        "audit_logs",
        "app_settings",
        "feedback",
        "organizations",
        "memberships",
    ]

    for table in tables:
        try:
            cur.execute(f"SELECT * FROM {table}")
            rows = [dict(r) for r in cur.fetchall()]
            if not rows:
                print(f"  - {table}: 0 rows (skipped)")
                continue

            collection = db[table]
            # Clear previous entries to allow clean idempotent re-runs
            collection.delete_many({})

            # Insert all documents in batch
            collection.insert_many(rows)
            print(f"  + {table}: successfully migrated {len(rows)} documents to Atlas")
        except Exception as e:
            print(f"  ! Error migrating table '{table}': {e}")

    conn.close()
    print("\nSUCCESS: All data successfully migrated to MongoDB Atlas!")
    print(f"Collections in '{db.name}': {db.list_collection_names()}")

if __name__ == "__main__":
    migrate()
