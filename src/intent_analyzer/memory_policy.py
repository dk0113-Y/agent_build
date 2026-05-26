from __future__ import annotations

from .schemas import MemoryUpdateCandidate


WRITABLE_FEEDBACK_TYPES = {"explicit_confirmation", "explicit_correction"}
NON_WRITABLE_FEEDBACK_TYPES = {
    "ambiguous_confirmation",
    "rejection_without_alternative",
    "repeated_question",
    "unknown",
}


class MemoryPolicyEngine:
    def validate_update(self, candidate: MemoryUpdateCandidate) -> tuple[bool, str]:
        if candidate.feedback_type in NON_WRITABLE_FEEDBACK_TYPES:
            return False, f"feedback_type_not_writable:{candidate.feedback_type}"
        if candidate.feedback_type not in WRITABLE_FEEDBACK_TYPES:
            return False, f"feedback_type_not_allowed:{candidate.feedback_type}"
        if not candidate.should_write_long_term_memory:
            return False, "candidate_not_marked_for_long_term_memory"
        if not candidate.user_id:
            return False, "missing_user_id"
        if not candidate.preferred_intent:
            return False, "missing_preferred_intent"
        if candidate.confidence_delta <= 0:
            return False, "non_positive_confidence_delta"
        if not candidate.pattern:
            return False, "missing_pattern"
        if not candidate.scope:
            return False, "missing_scope"
        return True, "allowed"

