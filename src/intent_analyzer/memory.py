from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from .rules import detect_explicit_instruction, infer_memory_pattern
from .schemas import IntentCandidate, MemoryUpdateCandidate, ReaderSemanticMemory


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
    def __init__(self, memories: list[ReaderSemanticMemory] | None = None) -> None:
        self._memories: list[ReaderSemanticMemory] = list(memories or [])
        self.proposed_updates: list[MemoryUpdateCandidate] = []

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
        if (
            not candidate.should_write_long_term_memory
            or not candidate.user_id
            or not candidate.preferred_intent
        ):
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
                confidence=confidence,
                positive_evidence_count=1,
                negative_evidence_count=0,
                conditions={},
                evidence=list(candidate.evidence),
                last_updated_at=now,
            )
            self._memories.append(memory)
            return memory

        current = existing.intent_distribution.get(candidate.preferred_intent, 0.0)
        updated = min(1.0, current + candidate.confidence_delta)
        existing.intent_distribution[candidate.preferred_intent] = updated
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


def apply_memory_bias(
    candidates: list[IntentCandidate],
    memories: list[ReaderSemanticMemory],
    text: str,
) -> list[IntentCandidate]:
    if detect_explicit_instruction(text):
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
            continue
        preferred_intent = max(
            memory.intent_distribution,
            key=lambda intent: memory.intent_distribution[intent],
            default=None,
        )
        if not preferred_intent:
            continue
        delta = min(0.30, 0.25 * memory.confidence)
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

    return sorted(adjusted, key=lambda candidate: candidate.confidence, reverse=True)

