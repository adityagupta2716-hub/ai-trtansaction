"""
Active Learning and Utility Policy Adaptation Module.

Adapts the Expected Utility table from human review feedback:
- False alarms (agent flagged, human approved) penalize the action's legit outcome.
- False negatives (agent approved, human blocked) penalize the approve action's fraud outcome.
- True positives (agent flagged, human blocked) reward the action's fraud outcome.
"""

import copy
import json
from pathlib import Path
from typing import Dict, Any
from sqlalchemy.orm import Session
from data.database import SessionLocal
from data.models import Feedback, AppSetting, AuditLog
from agent.utility import DEFAULT_UTILITY, CONFIG_PATH, _validate_utility


def update_utilities(step: float = 1.0) -> Dict[str, Dict[str, float]]:
    """
    Recompute the utility table from DEFAULT_UTILITY plus all recorded human feedback.
    Validates and clamps utility payoffs in [-200, 200].
    """
    util = copy.deepcopy(DEFAULT_UTILITY)
    session: Session = SessionLocal()
    try:
        feedback_entries = session.query(Feedback).order_by(Feedback.id).all()

        for fb in feedback_entries:
            agent_d = fb.agent_decision
            human_d = fb.human_decision

            if agent_d not in util:
                continue

            # 1. False Alarm: Human approves a transaction that agent held/escalated/blocked
            if human_d == "approve" and agent_d in ("hold", "block", "escalate", "pending_verification"):
                action_to_penalize = "hold" if agent_d == "pending_verification" else agent_d
                util[action_to_penalize]["legit"] -= step

            # 2. Under-reaction / False Negative: Agent approved or held, but human confirmed fraud (blocked)
            elif human_d == "block":
                if agent_d in ("approve", "hold"):
                    util[agent_d]["fraud"] -= step  # Penalty for under-reacting
                else:
                    util[agent_d]["fraud"] += step  # Reward for catching fraud

        # Clamp all values to prevent numerical runaway
        for a in util:
            for k in util[a]:
                util[a][k] = max(-200.0, min(200.0, round(float(util[a][k]), 2)))

        # Validate structure before writing
        if not _validate_utility(util):
            raise ValueError("Calculated utility table failed validation.")

        # Save to configuration file
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(util, f, indent=2)

        # Audit the policy update
        audit = AuditLog(
            entity_type="policy",
            entity_id="utility_table",
            action="utility_policy_adapted",
            actor_type="system",
            actor_id="learning_feedback",
            details_json=json.dumps({"feedback_count": len(feedback_entries), "step": step}),
        )
        session.add(audit)
        session.commit()
        return util
    finally:
        session.close()