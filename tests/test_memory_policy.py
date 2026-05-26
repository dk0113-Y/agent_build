from intent_analyzer import InMemoryMemoryStore, MemoryUpdateCandidate


def test_memory_apply_update_requires_write_permission():
    store = InMemoryMemoryStore()
    candidate = MemoryUpdateCandidate(
        user_id="u1",
        pattern="<simple_math_expr> 是啥",
        scope="math.short_query",
        preferred_intent="compute.arithmetic",
        corrected_intent="compute.arithmetic",
        feedback_type="ambiguous_confirmation",
        confidence_delta=0.0,
        evidence=[],
        should_write_long_term_memory=False,
    )

    assert store.apply_update(candidate) is None
    assert store.memories == []


def test_memory_apply_update_creates_auditable_memory():
    store = InMemoryMemoryStore()
    candidate = MemoryUpdateCandidate(
        user_id="u1",
        pattern="<simple_math_expr> 是啥",
        scope="math.short_query",
        preferred_intent="compute.arithmetic",
        corrected_intent="compute.arithmetic",
        feedback_type="explicit_correction",
        confidence_delta=0.25,
        evidence=[{"raw_feedback": "不不不，我只是想知道1+1等于几"}],
        should_write_long_term_memory=True,
    )

    memory = store.apply_update(candidate)

    assert memory is not None
    assert memory.user_id == "u1"
    assert memory.pattern == "<simple_math_expr> 是啥"
    assert memory.intent_distribution["compute.arithmetic"] > 0.5
    assert memory.positive_evidence_count == 1
    assert memory.evidence == candidate.evidence

