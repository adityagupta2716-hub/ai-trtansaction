"""
Repeatable Database Migration & Initialization Script with Multi-Tenant Support.

- Creates all SQLAlchemy tables (Organizations, Memberships, Customers, Transactions, etc.).
- Safely upgrades existing SQLite or PostgreSQL tables with missing tenant columns.
- Seeds initial organizations (Acme Financial Corp & Beta Payments Ltd).
- Seeds tenant-scoped role-based memberships (platform_admin, org_admin, analyst, reviewer).
- Seeds tenant-scoped application settings (verification limits).
- Backfills existing records with the default organization ID (org_id=1).
- Preserves existing data without data loss.
"""

import os
import json
import sqlite3
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from data.database import engine, Base, SessionLocal, DEFAULT_SQLITE_PATH, utcnow
from data.models import Organization, Membership, User, Customer, Transaction, FraudPrediction, AIDecision, HumanReview, AuditLog, AppSetting, Feedback
from backend.auth import get_password_hash


def _upgrade_sqlite_schema():
    """If using SQLite, ensure existing tables have org_id, created_at, and composite constraints."""
    if not engine.url.drivername.startswith("sqlite"):
        return
    if not DEFAULT_SQLITE_PATH.exists() or DEFAULT_SQLITE_PATH.stat().st_size == 0:
        return

    conn = sqlite3.connect(DEFAULT_SQLITE_PATH)
    try:
        cur = conn.cursor()
        cur.execute("DROP INDEX IF EXISTS ix_app_settings_key")
        conn.commit()

        # Handle customers table transition to composite PRIMARY KEY (customer_id, org_id)
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='customers'")
        cust_sql = cur.fetchone()
        if cust_sql and "PRIMARY KEY (customer_id)" in cust_sql[0]:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS customers_migrated (
                    customer_id INTEGER NOT NULL,
                    org_id INTEGER NOT NULL DEFAULT 1,
                    risk_level VARCHAR(32) NOT NULL DEFAULT 'low',
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (customer_id, org_id)
                )
            """)
            cur.execute("INSERT OR IGNORE INTO customers_migrated (customer_id, org_id, risk_level, notes, created_at) SELECT customer_id, COALESCE(org_id, 1), risk_level, notes, created_at FROM customers")
            cur.execute("DROP TABLE customers")
            cur.execute("ALTER TABLE customers_migrated RENAME TO customers")
            conn.commit()

        # Handle app_settings table transition from UNIQUE(key) to UNIQUE(org_id, key)
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='app_settings'")
        app_settings_sql = cur.fetchone()
        if app_settings_sql and ("UNIQUE" in app_settings_sql[0].upper() and "ORG_ID" not in app_settings_sql[0].upper()):
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_settings_migrated (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL DEFAULT 1,
                    key VARCHAR(64) NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_by VARCHAR(64),
                    updated_at DATETIME,
                    UNIQUE (org_id, key)
                )
            """)
            try:
                cur.execute("PRAGMA table_info(app_settings)")
                cols = [r[1] for r in cur.fetchall()]
                if "org_id" in cols:
                    cur.execute("INSERT OR IGNORE INTO app_settings_migrated (id, org_id, key, value, description, updated_by, updated_at) SELECT id, org_id, key, value, description, updated_by, updated_at FROM app_settings")
                else:
                    cur.execute("INSERT OR IGNORE INTO app_settings_migrated (id, org_id, key, value, description, updated_by, updated_at) SELECT id, 1, key, value, description, updated_by, updated_at FROM app_settings")
                cur.execute("DROP TABLE app_settings")
                cur.execute("ALTER TABLE app_settings_migrated RENAME TO app_settings")
                conn.commit()
            except Exception as ex:
                print(f"Warning during app_settings migration: {ex}")

        # Check and add columns for remaining tables
        tables_to_upgrade = {
            "transactions": ["org_id INTEGER DEFAULT 1", "created_at TEXT DEFAULT '2026-10-20 00:00:00'"],
            "customers": ["org_id INTEGER DEFAULT 1", "created_at TEXT DEFAULT '2026-10-20 00:00:00'"],
            "fraud_predictions": ["org_id INTEGER DEFAULT 1"],
            "ai_decisions": ["org_id INTEGER DEFAULT 1"],
            "human_reviews": ["org_id INTEGER DEFAULT 1"],
            "audit_logs": ["org_id INTEGER DEFAULT 1"],
            "feedback": ["org_id INTEGER DEFAULT 1"],
            "users": ["is_platform_admin INTEGER DEFAULT 0", "email TEXT"],
        }

        for table, col_defs in tables_to_upgrade.items():
            cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if cur.fetchone():
                cur.execute(f"PRAGMA table_info({table})")
                existing_cols = {row[1] for row in cur.fetchall()}
                for col_def in col_defs:
                    col_name = col_def.split()[0]
                    if col_name not in existing_cols:
                        try:
                            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
                        except Exception as e:
                            print(f"Warning adding column {col_def} to {table}: {e}")
        conn.commit()
    finally:
        conn.close()


def init_and_migrate(verbose: bool = True):
    if verbose:
        print(f"Connecting to database via engine: {engine.url.render_as_string(hide_password=True)}")

    # Upgrade SQLite columns if existing DB
    _upgrade_sqlite_schema()

    # 1. Create all tables in the target database
    Base.metadata.create_all(bind=engine)
    if verbose:
        print("SQLAlchemy multi-tenant tables created/verified successfully.")

    session: Session = SessionLocal()
    try:
        # 2. Seed Default Organizations
        org_acme = session.query(Organization).filter(Organization.slug == "acme").first()
        if not org_acme:
            org_acme = Organization(name="Acme Financial Corp", slug="acme", is_active=True)
            session.add(org_acme)
            session.flush()

        org_beta = session.query(Organization).filter(Organization.slug == "beta").first()
        if not org_beta:
            org_beta = Organization(name="Beta Payments Ltd", slug="beta", is_active=True)
            session.add(org_beta)
            session.flush()

        session.commit()
        if verbose:
            print(f"Organizations verified: Acme (#{org_acme.id}), Beta (#{org_beta.id}).")

        # 3. Seed Default Users & Memberships
        default_users = [
            ("admin", "adminPassword123!", "admin", True, [
                (org_acme.id, "org_admin"),
                (org_beta.id, "org_admin"),
            ]),
            ("analyst", "analystPassword123!", "analyst", False, [
                (org_acme.id, "analyst"),
            ]),
            ("reviewer", "reviewerPassword123!", "reviewer", False, [
                (org_acme.id, "reviewer"),
            ]),
            ("beta_analyst", "betaPassword123!", "analyst", False, [
                (org_beta.id, "analyst"),
            ]),
            ("beta_reviewer", "betaPassword123!", "reviewer", False, [
                (org_beta.id, "reviewer"),
            ]),
        ]

        for username, plain_pw, role, is_platform_admin, org_roles in default_users:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                hashed = get_password_hash(plain_pw)
                user = User(
                    username=username,
                    email=f"{username}@example.com",
                    hashed_password=hashed,
                    role=role,
                    is_platform_admin=is_platform_admin,
                    is_active=True,
                )
                session.add(user)
                session.flush()

            # Ensure memberships
            for org_id, m_role in org_roles:
                existing_m = (
                    session.query(Membership)
                    .filter(Membership.user_id == user.id, Membership.org_id == org_id)
                    .first()
                )
                if not existing_m:
                    m = Membership(user_id=user.id, org_id=org_id, role=m_role, is_active=True)
                    session.add(m)

        session.commit()
        if verbose:
            print("Users and tenant memberships verified.")

        # 4. Seed Tenant-Scoped Application Settings
        tenant_configs = [
            (org_acme.id, "500000.0", "USD"),
            (org_beta.id, "250000.0", "USD"),
        ]

        for org_id, limit_val, curr in tenant_configs:
            settings_to_seed = [
                ("human_verification_limit", limit_val, "Mandatory human review limit."),
                ("currency", curr, "Currency denomination used by tenant."),
                ("policy_version", "2.0.0", "Active fraud and utility decision policy version."),
                ("min_confidence_heuristic", "0.70", "Decision margin threshold for review recommendation."),
            ]
            for key, val, desc in settings_to_seed:
                existing = (
                    session.query(AppSetting)
                    .filter(AppSetting.org_id == org_id, AppSetting.key == key)
                    .first()
                )
                if not existing:
                    session.add(AppSetting(
                        org_id=org_id,
                        key=key,
                        value=val,
                        description=desc,
                        updated_by="system",
                    ))
        session.commit()
        if verbose:
            print("Tenant-specific application settings verified.")

        # 5. Backfill existing records with org_id=1 if null
        for model in (Transaction, Customer, FraudPrediction, AIDecision, HumanReview, AuditLog, AppSetting, Feedback):
            try:
                session.query(model).filter(model.org_id == None).update({model.org_id: org_acme.id})
            except Exception:
                pass
        session.commit()

        # 6. Ensure Customer entities exist for all transactions within each organization
        txn_pairs = session.execute(text("SELECT DISTINCT customer_id, org_id FROM transactions")).fetchall()
        for cid, oid in txn_pairs:
            target_org = oid or org_acme.id
            cust = (
                session.query(Customer)
                .filter(Customer.customer_id == cid, Customer.org_id == target_org)
                .first()
            )
            if not cust:
                session.add(Customer(customer_id=cid, org_id=target_org, risk_level="low"))
        session.commit()
        if verbose:
            print("Customer profiles synchronized for all transactions.")

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    init_and_migrate()
