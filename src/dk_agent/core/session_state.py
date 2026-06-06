from __future__ import annotations

import time
from dataclasses import dataclass, field

from dk_agent.routing.meta_schema import MetaDecision


@dataclass(slots=True)
class PendingClarification:
    original_user_text: str
    clarification_question: str
    missing_info: list[str]
    meta_decision: MetaDecision
    created_at: float = field(default_factory=time.time)
