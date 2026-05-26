from __future__ import annotations

from .rules import (
    INTENT_COMPUTE,
    INTENT_EXPLAIN,
    extract_math_expression,
    has_explicit_compute_instruction,
    has_explicit_explain_instruction,
    normalize_text,
)
from .schemas import FeedbackRecord, MemoryUpdateCandidate, SessionState


AMBIGUOUS_CONFIRMATIONS = {"对", "是", "嗯", "好", "可以", "没错"}
REJECTIONS = {"不是", "不对", "否", "不是这个"}
FIRST_OPTION_WORDS = {"a", "A", "第一个", "一", "选A", "选a"}
SECOND_OPTION_WORDS = {"b", "B", "第二个", "二", "选B", "选b"}
RESULT_WORDS = ("结果", "等于几", "答案", "直接算", "算出来")
EXPLAIN_WORDS = ("原理", "数学意义", "意义", "为什么", "解释")
CORRECTION_MARKERS = ("不不不", "不是这个意思", "我只是", "其实", "不是问")


def interpret_feedback(text: str, session_state: SessionState | None = None) -> FeedbackRecord:
    stripped = text.strip()
    compact = normalize_text(stripped)
    pending_options = (
        session_state.pending_clarification.options
        if session_state and session_state.pending_clarification
        else []
    )
    pending_intents = [option.intent for option in pending_options]

    corrected_by_instruction = _intent_from_explicit_reply(stripped)
    has_correction_marker = any(marker in stripped for marker in CORRECTION_MARKERS)
    if corrected_by_instruction and has_correction_marker:
        return FeedbackRecord(
            feedback_type="explicit_correction",
            corrected_intent=corrected_by_instruction,
            rejected_intents=[intent for intent in pending_intents if intent != corrected_by_instruction],
            confidence_delta=0.25,
            should_write_long_term_memory=True,
            reason="correction_marker_with_explicit_intent",
        )

    selected_from_option = _intent_from_option_reply(stripped, pending_options)
    if selected_from_option:
        return FeedbackRecord(
            feedback_type="explicit_confirmation",
            corrected_intent=selected_from_option,
            rejected_intents=[intent for intent in pending_intents if intent != selected_from_option],
            confidence_delta=0.12,
            should_write_long_term_memory=True,
            reason="selected_clarification_option",
        )

    if corrected_by_instruction:
        return FeedbackRecord(
            feedback_type="explicit_confirmation",
            corrected_intent=corrected_by_instruction,
            rejected_intents=[intent for intent in pending_intents if intent != corrected_by_instruction],
            confidence_delta=0.12,
            should_write_long_term_memory=True,
            reason="explicit_intent_reply",
        )

    if stripped in AMBIGUOUS_CONFIRMATIONS or compact in {normalize_text(item) for item in AMBIGUOUS_CONFIRMATIONS}:
        return FeedbackRecord(
            feedback_type="ambiguous_confirmation",
            rejected_intents=[],
            confidence_delta=0.0,
            should_write_long_term_memory=False,
            reason="confirmation_without_option",
        )

    if stripped in REJECTIONS or compact in {normalize_text(item) for item in REJECTIONS}:
        return FeedbackRecord(
            feedback_type="rejection_without_alternative",
            rejected_intents=pending_intents,
            confidence_delta=0.0,
            should_write_long_term_memory=False,
            reason="rejection_without_corrected_intent",
        )

    if _is_repeated_question(stripped, session_state):
        return FeedbackRecord(
            feedback_type="repeated_question",
            rejected_intents=[],
            confidence_delta=0.0,
            should_write_long_term_memory=False,
            reason="repeated_pending_question",
        )

    return FeedbackRecord(
        feedback_type="unknown",
        rejected_intents=[],
        confidence_delta=0.0,
        should_write_long_term_memory=False,
        reason="no_feedback_rule_match",
    )


def build_memory_update_candidate(
    feedback: FeedbackRecord,
    user_id: str | None,
    raw_text: str,
    session_state: SessionState | None,
    pattern: str,
    scope: str,
) -> MemoryUpdateCandidate:
    pending_text = session_state.pending_input_text if session_state else None
    return MemoryUpdateCandidate(
        user_id=user_id,
        pattern=pattern,
        scope=scope,
        preferred_intent=feedback.corrected_intent,
        corrected_intent=feedback.corrected_intent,
        feedback_type=feedback.feedback_type,
        confidence_delta=feedback.confidence_delta,
        should_write_long_term_memory=feedback.should_write_long_term_memory,
        evidence=[
            {
                "raw_feedback": raw_text,
                "pending_text": pending_text,
                "reason": feedback.reason,
            }
        ],
    )


def _intent_from_explicit_reply(text: str) -> str | None:
    if has_explicit_compute_instruction(text) or any(word in text for word in RESULT_WORDS):
        return INTENT_COMPUTE
    if has_explicit_explain_instruction(text) or any(word in text for word in EXPLAIN_WORDS):
        return INTENT_EXPLAIN
    return None


def _intent_from_option_reply(text: str, options) -> str | None:
    stripped = text.strip()
    compact = normalize_text(stripped)
    if len(options) >= 1 and (stripped in FIRST_OPTION_WORDS or compact in {normalize_text(x) for x in FIRST_OPTION_WORDS}):
        return options[0].intent
    if len(options) >= 2 and (stripped in SECOND_OPTION_WORDS or compact in {normalize_text(x) for x in SECOND_OPTION_WORDS}):
        return options[1].intent
    return None


def _is_repeated_question(text: str, session_state: SessionState | None) -> bool:
    if not session_state or not session_state.pending_input_text:
        return False
    current_expr = extract_math_expression(text)
    pending_expr = extract_math_expression(session_state.pending_input_text)
    if current_expr and pending_expr and current_expr == pending_expr:
        return "问你" in text or normalize_text(text) == normalize_text(session_state.pending_input_text)
    return normalize_text(text) == normalize_text(session_state.pending_input_text)

