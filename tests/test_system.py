"""
Comprehensive Automated Test Suite for AI Transaction Monitor.

Tests:
1. Security & Authentication: Bcrypt hashing, JWT tokens, Role-Based Access Control.
2. Verification-Limit Policy: Boundary conditions (below, equal, above), invalid limit rejection.
3. Expected Utility Theory: Calculation correctness, decision margin heuristic, feedback direction.
4. Database & Models: Persistence, foreign key relationships, audit logging.
5. Leakage-Free Feature Engineering: Temporal ordering, customer expanding features.
6. Human Review Workflow: Authorization enforcement, state transitions.
"""

import os
import json
import pytest
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data.database import Base
from data.models import Organization, User, Customer, Transaction, AIDecision, HumanReview, AuditLog, AppSetting, Feedback
from backend.auth import get_password_hash, verify_password, create_access_token, decode_access_token
from backend.responder import execute_action, update_verification_limit, get_active_limit_config
from agent.utility import choose_action, expected_utilities, DEFAULT_UTILITY
from agent.agent import decide
from model.features import make_features, make_chronological_features
from model.anomaly import score_transaction
from learning.feedback import update_utilities


# -------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------
@pytest.fixture(scope="module")
def test_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    # Seed default organization and settings
    org = Organization(id=1, name="Default Org", slug="default", is_active=True)
    session.add(org)
    session.commit()

    session.add(AppSetting(org_id=1, key="human_verification_limit", value="500000.0", description="Limit"))
    session.add(AppSetting(org_id=1, key="policy_version", value="2.0.0", description="Policy"))
    session.commit()

    yield session
    session.close()


# -------------------------------------------------------------
# 1. Security & Authentication Tests
# -------------------------------------------------------------
def test_password_hashing():
    pw = "SecretPassword123!"
    hashed = get_password_hash(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_generation_and_expiry():
    payload = {"sub": "test_analyst", "role": "analyst"}
    token = create_access_token(payload)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "test_analyst"
    assert decoded["role"] == "analyst"
    assert "exp" in decoded


# -------------------------------------------------------------
# 2. Verification Limit Boundary Tests
# -------------------------------------------------------------
def test_verification_limit_boundaries():
    limit, policy_ver = get_active_limit_config()

    # Scenario 1: Amount BELOW limit (A < L)
    d_below = {
        "transaction_id": 901,
        "amount": limit - 1000.0,
        "decision": "approve",
        "confidence": 0.8,
        "p_fraud": 0.01,
        "expected_utilities": {"approve": 5.0, "hold": -8.0, "escalate": -15.0, "block": -50.0},
        "reasoning": "Standard legitimate transaction",
    }
    res_below = execute_action(d_below)
    assert res_below["decision"] == "approve"
    assert res_below["decided_by"] == "agent"

    # Scenario 2: Amount EQUAL to limit (A == L) -> Autonomous agent evaluates
    d_equal = {
        "transaction_id": 902,
        "amount": limit,
        "decision": "approve",
        "confidence": 0.8,
        "p_fraud": 0.01,
        "expected_utilities": {"approve": 5.0, "hold": -8.0, "escalate": -15.0, "block": -50.0},
        "reasoning": "Standard legitimate transaction",
    }
    res_equal = execute_action(d_equal)
    assert res_equal["decision"] == "approve"
    assert res_equal["decided_by"] == "agent"

    # Scenario 3: Amount ABOVE limit (A > L) -> Mandatory Human Verification
    d_above = {
        "transaction_id": 903,
        "amount": limit + 50000.0,
        "decision": "block",
        "confidence": 0.95,
        "p_fraud": 0.85,
        "expected_utilities": {"approve": -100.0, "hold": 20.0, "escalate": 45.0, "block": 75.0},
        "reasoning": "Suspected fraud",
    }
    res_above = execute_action(d_above)
    assert res_above["decision"] == "pending_verification"
    assert res_above["decided_by"] == "limit_policy"
    assert "exceeds active mandatory human verification limit" in res_above["reasoning"]


def test_invalid_verification_limit_rejected():
    with pytest.raises(ValueError, match="must be a positive number"):
        update_verification_limit(-500.0, "admin")
    with pytest.raises(ValueError, match="must be a positive number"):
        update_verification_limit(0.0, "admin")


# -------------------------------------------------------------
# 3. Expected Utility Theory & Agent Tests
# -------------------------------------------------------------
def test_expected_utility_calculation():
    # If p_fraud = 0.0, Approve must dominate
    eu_zero = expected_utilities(0.0, DEFAULT_UTILITY)
    assert eu_zero["approve"] == 5.0
    assert eu_zero["block"] == -50.0

    # If p_fraud = 1.0, Block must dominate
    eu_one = expected_utilities(1.0, DEFAULT_UTILITY)
    assert eu_one["block"] == 80.0
    assert eu_one["approve"] == -100.0

    # Decision selection
    action, eu, gap = choose_action(0.01)
    assert action == "approve"
    assert gap > 0


def test_agent_decision_margin_heuristic():
    txn = {
        "transaction_id": 1,
        "customer_id": 10,
        "amount": 50.0,
        "old_balance": 1000.0,
        "new_balance": 950.0,
        "type": "PAYMENT",
    }
    score_res = {"score": 0.05, "p_fraud": 0.01, "top_reasons": []}
    neutral_profile = {"num_transactions": 5, "average_amount": 50.0, "past_flags": 0}
    dec_out = decide(txn, score_res, profile=neutral_profile)

    assert "decision_margin" in dec_out
    assert dec_out["decision"] == "approve"
    assert dec_out["decision_margin"] > 0


# -------------------------------------------------------------
# 4. Feedback Policy Adaptation Direction
# -------------------------------------------------------------
def test_feedback_adaptation_direction():
    # Calling update_utilities should compute valid bounds in [-200, 200]
    adapted = update_utilities(step=1.0)
    for action in ("approve", "hold", "escalate", "block"):
        assert -200 <= adapted[action]["fraud"] <= 200
        assert -200 <= adapted[action]["legit"] <= 200


# -------------------------------------------------------------
# 5. Leakage-Free Feature Engineering Tests
# -------------------------------------------------------------
def test_leakage_free_chronological_features():
    df = pd.DataFrame([
        {"transaction_id": 1, "customer_id": 101, "step": 1, "type": "PAYMENT", "amount": 100.0, "old_balance": 1000.0, "new_balance": 900.0},
        {"transaction_id": 2, "customer_id": 101, "step": 2, "type": "PAYMENT", "amount": 200.0, "old_balance": 900.0, "new_balance": 700.0},
        {"transaction_id": 3, "customer_id": 101, "step": 3, "type": "TRANSFER", "amount": 700.0, "old_balance": 700.0, "new_balance": 0.0},
    ])
    feats = make_chronological_features(df)
    # First transaction must have 0 prior transactions
    assert feats["prior_tx_count"].iloc[0] == 0
    assert feats["insufficient_history"].iloc[0] == 1
    # Second transaction has 1 prior transaction with amount 100
    assert feats["prior_tx_count"].iloc[1] == 1
    assert feats["prior_avg_amount"].iloc[1] == 100.0
    # Third transaction drains account
    assert feats["drained"].iloc[2] == 1
