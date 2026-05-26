from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .memory_policy import MemoryPolicyEngine
from .rules import (
    INTENT_COMPUTE,
    detect_explicit_instruction,
    extract_math_expression,
    infer_memory_pattern,
)
from .schemas import IntentCandidate, MemoryUpdateCandidate, ReaderSemanticMemory, SessionState


class MemoryStore(Protocol):
    def query_reader_semantic_memory(
        self,
        user_id: str | None,
        text: str,
        context: dict | None = None,
    ) -> list[ReaderSemanticMemory]:
        ...

    def propose_update(self, candidate: MemoryUpdateCandidate) -> MemoryUpdateCandidate:
        ...

    def apply_update(self, candidate: MemoryUpdateCandidate) -> ReaderSemanticMemory | None:
        ...


class InMemoryMemoryStore:
    def __init__(
        self,
        memories: list[ReaderSemanticMemory] | None = None,
        policy_engine: MemoryPolicyEngine | None = None,
    ) -> None:
        self._memories: list[ReaderSemanticMemory] = list(memories or [])
        self.proposed_updates: list[MemoryUpdateCandidate] = []
        self.policy_engine = policy_engine or MemoryPolicyEngine()

    @property
    def memories(self) -> list[ReaderSemanticMemory]:
        return list(self._memories)

    def query_reader_semantic_memory(
        self,
        user_id: str | None,
        text: str,
        context: dict | None = None,
    ) -> list[ReaderSemanticMemory]:
        if not user_id:
            return []
        pattern, scope = infer_memory_pattern(text)
        return [
            memory
            for memory in self._memories
            if memory.user_id == user_id
            and memory.pattern == pattern
            and (memory.scope == scope or memory.scope == "global")
        ]

    def propose_update(self, candidate: MemoryUpdateCandidate) -> MemoryUpdateCandidate:
        self.proposed_updates.append(candidate)
        return candidate

    def apply_update(self, candidate: MemoryUpdateCandidate) -> ReaderSemanticMemory | None:
        allowed, _reason = self.policy_engine.validate_update(candidate)
        if not allowed:
            return None

        now = datetime.now(UTC).isoformat()
        existing = self._find(candidate.user_id, candidate.pattern, candidate.scope)
        if existing is None:
            confidence = min(1.0, max(0.0, 0.5 + candidate.confidence_delta))
            memory = ReaderSemanticMemory(
                memory_id=str(uuid4()),
                user_id=candidate.user_id,
                pattern=candidate.pattern,
                scope=candidate.scope,
                intent_distribution={candidate.preferred_intent: confidence},
                intent_weights={candidate.preferred_intent: confidence},
                confidence=confidence,
                positive_evidence_count=1,
                negative_evidence_count=0,
                conditions={},
                evidence=list(candidate.evidence),
                last_updated_at=now,
            )
            self._memories.append(memory)
            return memory

        weights = get_intent_weights(existing)
        current = weights.get(candidate.preferred_intent, 0.0)
        updated = min(1.0, current + candidate.confidence_delta)
        weights[candidate.preferred_intent] = updated
        existing.intent_weights = dict(weights)
        existing.intent_distribution = dict(weights)
        existing.confidence = min(1.0, max(existing.confidence, updated))
        existing.positive_evidence_count += 1
        existing.evidence.extend(candidate.evidence)
        existing.last_updated_at = now
        return existing

    def _find(self, user_id: str, pattern: str, scope: str) -> ReaderSemanticMemory | None:
        for memory in self._memories:
            if memory.user_id == user_id and memory.pattern == pattern and memory.scope == scope:
                return memory
        return None


class JsonMemoryStore(InMemoryMemoryStore):
    def __init__(
        self,
        path: str | Path,
        policy_engine: MemoryPolicyEngine | None = None,
    ) -> None:
        self.path = Path(path)
        super().__init__(memories=[], policy_engine=policy_engine)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._memories = []
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        raw_memories = data.get("memories", data if isinstance(data, list) else [])
        self._memories = [_reader_semantic_memory_from_dict(item) for item in raw_memories]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "memories": [asdict(memory) for memory in self._memories],
        }
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def apply_update(self, candidate: MemoryUpdateCandidate) -> ReaderSemanticMemory | None:
        memory = super().apply_update(candidate)
        if memory is not None:
            self.save()
        return memory


def get_intent_weights(memory: ReaderSemanticMemory) -> dict[str, float]:
    if memory.intent_weights:
        return dict(memory.intent_weights)
    return dict(memory.intent_distribution)


def apply_memory_bias(
    candidates: list[IntentCandidate],
    memories: list[ReaderSemanticMemory],
    text: str,
    context: dict | None = None,
    session_state: SessionState | None = None,
    diagnostics: dict | None = None,
) -> list[IntentCandidate]:
    diagnostics = diagnostics if diagnostics is not None else {}
    memory_diagnostics = diagnostics.setdefault("memory_bias", [])
    if detect_explicit_instruction(text):
        for memory in memories:
            memory_diagnostics.append(
                {
                    "memory_id": memory.memory_id,
                    "applied": False,
                    "reason": "skipped_current_explicit_instruction",
                }
            )
        return candidates

    adjusted = [
        IntentCandidate(
            intent=candidate.intent,
            confidence=candidate.confidence,
            slots=dict(candidate.slots),
            evidence=list(candidate.evidence),
        )
        for candidate in candidates
    ]

    for memory in memories:
        if memory.confidence < 0.65:
            memory_diagnostics.append(
                {
                    "memory_id": memory.memory_id,
                    "applied": False,
                    "reason": "memory_confidence_below_threshold",
                }
            )
            continue
        weights = get_intent_weights(memory)
        preferred_intent = max(weights, key=lambda intent: weights[intent], default=None)
        if not preferred_intent:
            memory_diagnostics.append(
                {
                    "memory_id": memory.memory_id,
                    "applied": False,
                    "reason": "missing_preferred_intent",
                }
            )
            continue

        should_apply, strength, reason = _evaluate_memory_applicability(
            memory=memory,
            preferred_intent=preferred_intent,
            text=text,
            context=context,
            session_state=session_state,
        )
        if not should_apply:
            memory_diagnostics.append(
                {
                    "memory_id": memory.memory_id,
                    "applied": False,
                    "preferred_intent": preferred_intent,
                    "reason": reason,
                }
            )
            continue

        delta = min(0.30, 0.25 * memory.confidence * strength)
        for candidate in adjusted:
            if candidate.intent == preferred_intent:
                candidate.confidence = min(0.95, candidate.confidence + delta)
                candidate.evidence.append(f"memory_bias:{memory.memory_id}")
                break
        else:
            adjusted.append(
                IntentCandidate(
                    intent=preferred_intent,
                    confidence=min(0.75, 0.50 + delta),
                    slots={},
                    evidence=[f"memory_bias:{memory.memory_id}"],
                )
            )
        memory_diagnostics.append(
            {
                "memory_id": memory.memory_id,
                "applied": True,
                "preferred_intent": preferred_intent,
                "delta": delta,
                "reason": reason,
            }
        )

    return sorted(adjusted, key=lambda candidate: candidate.confidence, reverse=True)


def _evaluate_memory_applicability(
    memory: ReaderSemanticMemory,
    preferred_intent: str,
    text: str,
    context: dict | None,
    session_state: SessionState | None,
) -> tuple[bool, float, str]:
    current_topic = _current_topic(context, session_state)
    conditions = memory.conditions or {}
    avoid_when = conditions.get("avoid_when", [])
    for condition in avoid_when:
        if _condition_matches(condition, text, context, session_state):
            return False, 0.0, f"avoid_when_matched:{condition}"

    prefer_when = conditions.get("prefer_when", [])
    if prefer_when:
        unmet = [
            condition
            for condition in prefer_when
            if not _condition_matches(condition, text, context, session_state)
        ]
        if unmet:
            return False, 0.0, f"prefer_when_not_satisfied:{unmet[0]}"

    if (
        current_topic == "math_theory"
        and preferred_intent == INTENT_COMPUTE
        and _contains_colloquial_math_whats(text)
    ):
        return False, 0.0, "skipped_current_topic_math_theory"

    strength = 1.0
    if current_topic == "quick_calculation" and preferred_intent == INTENT_COMPUTE:
        strength = 1.35
    return True, strength, "conditions_satisfied"


def _condition_matches(
    condition: str,
    text: str,
    context: dict | None,
    session_state: SessionState | None,
) -> bool:
    condition = condition.strip()
    if condition == "input_contains_simple_math_expression":
        return extract_math_expression(text) is not None
    if condition.startswith("input_contains:"):
        keywords = _condition_keywords(condition, "input_contains:")
        return any(keyword in text for keyword in keywords)
    if condition.startswith("no_keywords:"):
        keywords = _condition_keywords(condition, "no_keywords:")
        return all(keyword not in text for keyword in keywords)
    if condition.startswith("current_topic:"):
        expected = condition.removeprefix("current_topic:").strip()
        return _current_topic(context, session_state) == expected
    return False


def _condition_keywords(condition: str, prefix: str) -> list[str]:
    return [
        keyword.strip()
        for keyword in condition.removeprefix(prefix).split(",")
        if keyword.strip()
    ]


def _current_topic(context: dict | None, session_state: SessionState | None) -> str | None:
    if session_state and session_state.current_topic:
        return session_state.current_topic
    if context:
        topic = context.get("current_topic")
        if isinstance(topic, str):
            return topic
    return None


def _contains_colloquial_math_whats(text: str) -> bool:
    return extract_math_expression(text) is not None and ("是啥" in text or "是什么" in text)


def _reader_semantic_memory_from_dict(data: dict) -> ReaderSemanticMemory:
    names = {field.name for field in fields(ReaderSemanticMemory)}
    filtered = {key: value for key, value in data.items() if key in names}
    if "intent_weights" not in filtered:
        filtered["intent_weights"] = None
    return ReaderSemanticMemory(**filtered)
