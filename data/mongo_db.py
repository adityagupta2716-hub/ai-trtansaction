import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://adityagupta2716_db_user:aditya2704@cluster0.dyn9y7o.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "ai_transaction_monitor")

_client = None

def get_mongo_client() -> MongoClient:
    """Singleton MongoDB client."""
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
    return _client

def get_mongo_db():
    """Returns the main database instance."""
    client = get_mongo_client()
    return client[MONGODB_DB_NAME]

# Collection accessors
def get_collection(name: str):
    db = get_mongo_db()
    return db[name]

def init_mongo_indexes():
    """Create optimal indexes for fraud detection and transaction queries."""
    db = get_mongo_db()
    
    # Drop existing indexes to recreate cleanly
    for col in ["transactions", "customers", "users", "app_settings", "audit_logs"]:
        try:
            db[col].drop_indexes()
        except Exception:
            pass

    # Transactions indexes
    db.transactions.create_index("transaction_id", unique=True)
    db.transactions.create_index("customer_id")
    db.transactions.create_index("status")
    db.transactions.create_index("created_at")
    db.transactions.create_index("org_id")
    
    # Customers indexes (customer_id + org_id is unique across tenants)
    db.customers.create_index([("customer_id", 1), ("org_id", 1)], unique=True)
    db.customers.create_index("customer_id")
    
    # Users indexes
    db.users.create_index("username", unique=True)
    
    # Audit logs indexes
    db.audit_logs.create_index("created_at")
    db.audit_logs.create_index("actor_id")
    db.audit_logs.create_index("org_id")
    
    # App settings indexes (key + org_id is unique per tenant)
    db.app_settings.create_index([("key", 1), ("org_id", 1)], unique=True)

