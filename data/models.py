from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    Text,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    Boolean,
    Index,
)
from sqlalchemy.orm import relationship
from data.database import Base, utcnow


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    slug = Column(String(64), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="organization", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="organization", cascade="all, delete-orphan")
    settings = relationship("AppSetting", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=False, default="analyst")  # platform_admin, org_admin, analyst, reviewer
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_membership_user_org"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="analyst")  # Global fallback role
    is_platform_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True, index=True)
    risk_level = Column(String(32), default="low", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    organization = relationship("Organization", back_populates="customers")
    transactions = relationship(
        "Transaction",
        back_populates="customer",
        cascade="all, delete-orphan",
        primaryjoin="and_(Customer.customer_id==Transaction.customer_id, Customer.org_id==Transaction.org_id)",
        overlaps="organization,transactions",
    )


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(Integer, primary_key=True, autoincrement=False, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True, default=1)
    customer_id = Column(Integer, nullable=False, index=True)
    step = Column(Integer, default=0, nullable=False, index=True)
    type = Column(String(32), nullable=False, index=True)  # TRANSFER, CASH_OUT, PAYMENT
    amount = Column(Float, nullable=False, index=True)
    old_balance = Column(Float, nullable=False)
    new_balance = Column(Float, nullable=False)
    is_fraud = Column(Integer, default=0, nullable=False)  # Ground-truth label for evaluation only
    status = Column(String(32), default="pending", nullable=False, index=True)  # pending, approve, hold, block, escalate, pending_verification
    created_at = Column(DateTime, default=utcnow, nullable=False)

    organization = relationship("Organization", back_populates="transactions", overlaps="customer,transactions")
    customer = relationship(
        "Customer",
        back_populates="transactions",
        primaryjoin="and_(Transaction.customer_id==Customer.customer_id, Transaction.org_id==Customer.org_id)",
        overlaps="organization,transactions",
    )
    predictions = relationship("FraudPrediction", back_populates="transaction", cascade="all, delete-orphan")
    decisions = relationship("AIDecision", back_populates="transaction", cascade="all, delete-orphan")
    human_reviews = relationship("HumanReview", back_populates="transaction", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="transaction", cascade="all, delete-orphan")

    __table_args__ = (
        ForeignKeyConstraint(
            ["customer_id", "org_id"],
            ["customers.customer_id", "customers.org_id"],
            ondelete="CASCADE",
            name="fk_transaction_customer_org",
        ),
        Index("idx_transactions_org_cust_step", "org_id", "customer_id", "step"),
        Index("idx_transactions_org_status", "org_id", "status"),
    )


class FraudPrediction(Base):
    __tablename__ = "fraud_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True, default=1)
    transaction_id = Column(Integer, ForeignKey("transactions.transaction_id", ondelete="CASCADE"), nullable=False, index=True)
    anomaly_score = Column(Float, nullable=False)
    raw_p_fraud = Column(Float, nullable=False)
    adjusted_p_fraud = Column(Float, nullable=False)
    decision_margin = Column(Float, nullable=False)
    model_version = Column(String(64), default="1.0.0", nullable=False)
    feature_values_json = Column(Text, nullable=True)
    reasons_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    transaction = relationship("Transaction", back_populates="predictions")


class AIDecision(Base):
    __tablename__ = "ai_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True, default=1)
    transaction_id = Column(Integer, ForeignKey("transactions.transaction_id", ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(String(32), nullable=False)  # approve, hold, escalate, block, pending_verification
    decision_margin = Column(Float, nullable=False)
    expected_utilities_json = Column(Text, nullable=True)
    policy_version = Column(String(64), default="2.0.0", nullable=False)
    reasoning = Column(Text, nullable=True)
    decided_by = Column(String(32), default="agent", nullable=False)  # agent, limit_policy, guardrail
    created_at = Column(DateTime, default=utcnow, nullable=False)

    transaction = relationship("Transaction", back_populates="decisions")


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True, default=1)
    transaction_id = Column(Integer, ForeignKey("transactions.transaction_id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_username = Column(String(64), nullable=False)
    review_outcome = Column(String(32), nullable=False)  # approve, block, unresolved
    fraud_confirmed = Column(Integer, nullable=True)  # 1 = confirmed fraud, 0 = confirmed legit, None = unresolved
    review_reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    transaction = relationship("Transaction", back_populates="human_reviews")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    entity_type = Column(String(64), nullable=False)  # transaction, setting, user, organization, policy
    entity_id = Column(String(64), nullable=False)
    action = Column(String(64), nullable=False)  # decision_executed, limit_override, human_reviewed, setting_changed, user_login, member_added
    actor_type = Column(String(32), nullable=False)  # agent, system, platform_admin, org_admin, reviewer, analyst
    actor_id = Column(String(64), nullable=False)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    organization = relationship("Organization", back_populates="audit_logs")


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True, default=1)
    key = Column(String(64), nullable=False, index=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=utcnow, nullable=False)

    organization = relationship("Organization", back_populates="settings")

    __table_args__ = (
        UniqueConstraint("org_id", "key", name="uq_appsetting_org_key"),
    )


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True, default=1)
    transaction_id = Column(Integer, ForeignKey("transactions.transaction_id", ondelete="CASCADE"), nullable=False, index=True)
    agent_decision = Column(String(32), nullable=False)
    human_decision = Column(String(32), nullable=False)  # approve or block
    created_at = Column(DateTime, default=utcnow, nullable=False)

    transaction = relationship("Transaction", back_populates="feedback")


Index("idx_audit_org_entity", AuditLog.org_id, AuditLog.entity_type, AuditLog.entity_id)
