from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dk_agent.routing.meta_schema import MetaDecision


def valid_payload() -> dict[str, object]:
    return {
        "user_goal": "Explain LangGraph",
        "task_boundary": None,
        "need_clarification": False,
        "clarification_question": None,
        "missing_info": [],
        "need_meta_high": False,
        "meta_high_reason": None,
        "executor_role": "pro",
        "reasoning_profile": "medium",
        "autonomy_mode": "answer_only",
        "tools": [],
        "skills": ["general"],
        "verifiers": ["self_check"],
        "risk_level": "low",
        "need_human_approval": False,
        "short_reason": "clear answer request",
    }


class MetaDecisionSchemaTests(unittest.TestCase):
    def test_valid_payload_parses(self) -> None:
        decision = MetaDecision.model_validate(valid_payload())

        self.assertEqual(decision.executor_role, "pro")
        self.assertEqual(decision.autonomy_mode, "answer_only")
        self.assertEqual(decision.tools, [])

    def test_invalid_executor_role_fails(self) -> None:
        payload = valid_payload()
        payload["executor_role"] = "judge"

        with self.assertRaises(ValidationError):
            MetaDecision.model_validate(payload)

    def test_invalid_autonomy_mode_fails(self) -> None:
        payload = valid_payload()
        payload["autonomy_mode"] = "invalid_mode"

        with self.assertRaises(ValidationError):
            MetaDecision.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
