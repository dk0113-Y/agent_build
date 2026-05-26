from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


InputType = Literal["short_query", "long_text", "clarification_reply", "unknown"]
RiskLevel = Literal["low", "medium", "high"]
FeedbackType = Literal[
    "explicit_confirmation",
    "explicit_correction",
    "ambiguous_confirmation",
    "rejection_without_alternative",
    "repeated_question",
    "unrelated",
    "unknown",
]


@dataclass(slots=True)
class IntentCandidate:
    intent: str
    confidence: float
    slots: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClarificationOption:
    label: str
    intent: str
    description: str


@dataclass(slots=True)
class ClarificationRequest:
    needed: bool
    question: str
    options: list[ClarificationOption] = field(default_factory=list)
    reason: str = ""


@dataclass(slots=True)
class DispatchHint:
    required_modules: list[str]
    risk_level: RiskLevel = "low"
    blocking_missing_slots: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FeedbackRecord:
    feedback_type: FeedbackType
    corrected_intent: str | None = None
    rejected_intents: list[str] = field(default_factory=list)
    confidence_delta: float = 0.0
    should_write_long_term_memory: bool = False
    reason: str = ""


@dataclass(slots=True)
class MemoryUpdateCandidate:
    pattern: str
    scope: str
    preferred_intent: str | None
    feedback_type: FeedbackType
    confidence_delta: float
    evidence: list[dict] = field(default_factory=list)
    should_write_long_term_memory: bool = False
    user_id: str | None = None
    corrected_intent: str | None = None


@dataclass(slots=True)
class ReaderSemanticMemory:
    memory_id: str
    user_id: str
    pattern: str
    scope: str
    intent_distribution: dict[str, float]
    confidence: float
    positive_evidence_count: int
    negative_evidence_count: int
    conditions: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)
    last_updated_at: str = ""


@dataclass(slots=True)
class UserIntentIR:
    input_id: str
    user_id: str | None
    raw_text: str
    input_type: InputType
    intent_candidates: list[IntentCandidate] = field(default_factory=list)
    selected_intent: str | None = None
    ambiguity: bool = False
    clarification: ClarificationRequest | None = None
    dispatch_hint: DispatchHint | None = None
    memory_update_candidate: MemoryUpdateCandidate | None = None
    diagnostics: dict = field(default_factory=dict)


@dataclass(slots=True)
class SessionState:
    pending_clarification: ClarificationRequest | None = None
    pending_input_text: str | None = None
    pending_intent_candidates: list[IntentCandidate] = field(default_factory=list)
    current_topic: str | None = None
    project_context: dict = field(default_factory=dict)

    def set_pending(
        self,
        clarification: ClarificationRequest,
        raw_text: str,
        candidates: list[IntentCandidate],
    ) -> None:
        self.pending_clarification = clarification
        self.pending_input_text = raw_text
        self.pending_intent_candidates = list(candidates)

    def clear_pending(self) -> None:
        self.pending_clarification = None
        self.pending_input_text = None
        self.pending_intent_candidates = []

