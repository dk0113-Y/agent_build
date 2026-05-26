from __future__ import annotations

from uuid import uuid4

from .confidence import is_ambiguous, sort_candidates
from .feedback import build_memory_update_candidate, interpret_feedback
from .memory import InMemoryMemoryStore, MemoryStore, apply_memory_bias
from .rules import (
    INTENT_COMPUTE,
    INTENT_EXPLAIN,
    build_dispatch_hint,
    classify_input,
    extract_math_expression,
    generate_intent_candidates,
    infer_memory_pattern,
)
from .schemas import (
    ClarificationOption,
    ClarificationRequest,
    IntentCandidate,
    SessionState,
    UserIntentIR,
)


class UserIntentAnalyzer:
    def __init__(self, memory_store: MemoryStore | None = None) -> None:
        self.memory_store = memory_store or InMemoryMemoryStore()

    def analyze_intent(
        self,
        raw_text: str,
        user_id: str | None = None,
        session_state: SessionState | None = None,
        context: dict | None = None,
        input_id: str | None = None,
    ) -> UserIntentIR:
        return analyze_intent(
            raw_text=raw_text,
            user_id=user_id,
            session_state=session_state,
            memory_store=self.memory_store,
            context=context,
            input_id=input_id,
        )


def analyze_intent(
    raw_text: str,
    user_id: str | None = None,
    session_state: SessionState | None = None,
    memory_store: MemoryStore | None = None,
    context: dict | None = None,
    input_id: str | None = None,
) -> UserIntentIR:
    input_id = input_id or str(uuid4())
    context = context or {}
    input_type, input_reason = classify_input(raw_text, session_state)
    diagnostics: dict = {"input_type_reason": input_reason}

    if input_type == "clarification_reply":
        return _analyze_clarification_reply(
            raw_text=raw_text,
            user_id=user_id,
            session_state=session_state,
            memory_store=memory_store,
            context=context,
            input_id=input_id,
            diagnostics=diagnostics,
        )

    candidates = generate_intent_candidates(raw_text, input_type)
    memories = []
    if memory_store is not None:
        memories = memory_store.query_reader_semantic_memory(user_id, raw_text, context)
        candidates = apply_memory_bias(candidates, memories, raw_text)

    candidates = sort_candidates(candidates)
    ambiguity, ambiguity_reason = is_ambiguous(candidates, raw_text, session_state)
    diagnostics["ambiguity_reason"] = ambiguity_reason
    diagnostics["memory_matches"] = [memory.memory_id for memory in memories]

    clarification = _build_clarification(raw_text, candidates, ambiguity, ambiguity_reason)
    selected_intent = None if ambiguity else candidates[0].intent
    dispatch_hint = (
        build_dispatch_hint(selected_intent, candidates[0].slots)
        if selected_intent is not None
        else None
    )

    if session_state is not None and clarification is not None and clarification.needed:
        session_state.set_pending(clarification, raw_text, candidates)

    return UserIntentIR(
        input_id=input_id,
        user_id=user_id,
        raw_text=raw_text,
        input_type=input_type,
        intent_candidates=candidates,
        selected_intent=selected_intent,
        ambiguity=ambiguity,
        clarification=clarification,
        dispatch_hint=dispatch_hint,
        memory_update_candidate=None,
        diagnostics=diagnostics,
    )


def _analyze_clarification_reply(
    raw_text: str,
    user_id: str | None,
    session_state: SessionState | None,
    memory_store: MemoryStore | None,
    context: dict,
    input_id: str,
    diagnostics: dict,
) -> UserIntentIR:
    feedback = interpret_feedback(raw_text, session_state)
    diagnostics["feedback_record"] = feedback

    selected_intent = feedback.corrected_intent
    candidates = _candidates_from_feedback(selected_intent, session_state)
    ambiguity = not feedback.should_write_long_term_memory or selected_intent is None
    clarification = session_state.pending_clarification if ambiguity and session_state else None
    dispatch_hint = build_dispatch_hint(selected_intent, candidates[0].slots) if selected_intent and candidates else None

    memory_update_candidate = None
    if feedback.should_write_long_term_memory:
        basis_text = session_state.pending_input_text if session_state and session_state.pending_input_text else raw_text
        pattern, scope = infer_memory_pattern(basis_text)
        memory_update_candidate = build_memory_update_candidate(
            feedback=feedback,
            user_id=user_id,
            raw_text=raw_text,
            session_state=session_state,
            pattern=pattern,
            scope=scope,
        )
        if memory_store is not None:
            memory_store.propose_update(memory_update_candidate)

    if session_state is not None and selected_intent is not None:
        session_state.clear_pending()

    return UserIntentIR(
        input_id=input_id,
        user_id=user_id,
        raw_text=raw_text,
        input_type="clarification_reply",
        intent_candidates=candidates,
        selected_intent=selected_intent,
        ambiguity=ambiguity,
        clarification=clarification,
        dispatch_hint=dispatch_hint,
        memory_update_candidate=memory_update_candidate,
        diagnostics=diagnostics,
    )


def _candidates_from_feedback(
    selected_intent: str | None,
    session_state: SessionState | None,
) -> list[IntentCandidate]:
    pending_candidates = session_state.pending_intent_candidates if session_state else []
    if selected_intent is None:
        return list(pending_candidates)

    for candidate in pending_candidates:
        if candidate.intent == selected_intent:
            return [
                IntentCandidate(
                    intent=candidate.intent,
                    confidence=max(candidate.confidence, 0.90),
                    slots=dict(candidate.slots),
                    evidence=list(candidate.evidence) + ["feedback_resolution"],
                )
            ]

    slots = {}
    if selected_intent == INTENT_COMPUTE and session_state and session_state.pending_input_text:
        expression = extract_math_expression(session_state.pending_input_text)
        if expression:
            slots["expression"] = expression
    elif selected_intent == INTENT_EXPLAIN and session_state and session_state.pending_input_text:
        expression = extract_math_expression(session_state.pending_input_text)
        if expression:
            slots["topic"] = expression

    return [IntentCandidate(selected_intent, 0.90, slots, ["feedback_resolution"])]


def _build_clarification(
    raw_text: str,
    candidates: list[IntentCandidate],
    ambiguity: bool,
    ambiguity_reason: str,
) -> ClarificationRequest | None:
    if not ambiguity:
        return None

    top_intents = [candidate.intent for candidate in candidates[:3]]
    expression = extract_math_expression(raw_text)
    if INTENT_COMPUTE in top_intents and INTENT_EXPLAIN in top_intents:
        subject = expression or "这个表达"
        return ClarificationRequest(
            needed=True,
            question=f"你是想让我直接算出 {subject} 的结果，还是解释 {subject} 的数学意义？",
            options=[
                ClarificationOption(
                    label="A",
                    intent=INTENT_COMPUTE,
                    description="直接计算结果",
                ),
                ClarificationOption(
                    label="B",
                    intent=INTENT_EXPLAIN,
                    description="解释数学意义",
                ),
            ],
            reason=ambiguity_reason,
        )

    options = [
        ClarificationOption(
            label=chr(ord("A") + index),
            intent=candidate.intent,
            description=candidate.intent,
        )
        for index, candidate in enumerate(candidates[:2])
    ]
    return ClarificationRequest(
        needed=True,
        question="我还不能确定你的具体意图，请选择你想让我处理的方向。",
        options=options,
        reason=ambiguity_reason,
    )

