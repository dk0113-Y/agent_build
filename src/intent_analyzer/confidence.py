from __future__ import annotations

from .schemas import IntentCandidate, SessionState


AMBIGUOUS_REPLY_WORDS = {"对", "是", "嗯", "随便", "你说呢", "都行", "好", "可以"}


def sort_candidates(candidates: list[IntentCandidate]) -> list[IntentCandidate]:
    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)


def is_ambiguous(
    candidates: list[IntentCandidate],
    text: str,
    session_state: SessionState | None = None,
) -> tuple[bool, str]:
    if session_state and session_state.pending_clarification is not None:
        if text.strip() in AMBIGUOUS_REPLY_WORDS:
            return True, "ambiguous_clarification_reply"

    if not candidates:
        return True, "no_candidates"

    ordered = sort_candidates(candidates)
    top = ordered[0]
    if top.confidence < 0.55:
        return True, "top_confidence_below_threshold"

    if len(ordered) > 1 and (top.confidence - ordered[1].confidence) < 0.15:
        return True, "top_two_candidates_too_close"

    return False, "clear_top_candidate"

