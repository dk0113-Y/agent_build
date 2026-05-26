from intent_analyzer import (
    InMemoryMemoryStore,
    JsonMemoryStore,
    MemoryPolicyEngine,
    MemoryUpdateCandidate,
    ReaderSemanticMemory,
    SessionState,
    analyze_intent,
)


def _compute_whats_memory(**overrides) -> ReaderSemanticMemory:
    data = {
        "memory_id": "mem-compute-whats",
        "user_id": "u1",
        "pattern": "<simple_math_expr> 是啥",
        "scope": "math.short_query",
        "intent_distribution": {"compute.arithmetic": 0.9},
        "intent_weights": {"compute.arithmetic": 0.9},
        "confidence": 0.9,
        "positive_evidence_count": 5,
        "negative_evidence_count": 0,
        "conditions": {},
        "evidence": [],
        "last_updated_at": "2026-05-21T00:00:00Z",
    }
    data.update(overrides)
    return ReaderSemanticMemory(**data)


def test_memory_conditions_avoid_math_theory():
    store = InMemoryMemoryStore(
        [
            _compute_whats_memory(
                conditions={"avoid_when": ["current_topic: math_theory"]},
            )
        ]
    )
    state = SessionState(current_topic="math_theory")

    ir = analyze_intent("1+2是啥？", user_id="u1", session_state=state, memory_store=store)

    assert ir.ambiguity is True or ir.selected_intent == "explain.math_concept"
    assert any(
        item["memory_id"] == "mem-compute-whats"
        and item["applied"] is False
        and "avoid_when_matched" in item["reason"]
        for item in ir.diagnostics["memory_bias"]
    )


def test_memory_conditions_prefer_quick_calculation():
    store = InMemoryMemoryStore(
        [
            _compute_whats_memory(
                conditions={"prefer_when": ["current_topic: quick_calculation"]},
            )
        ]
    )
    state = SessionState(current_topic="quick_calculation")

    ir = analyze_intent("1+2是啥？", user_id="u1", session_state=state, memory_store=store)

    assert ir.selected_intent == "compute.arithmetic"
    assert ir.ambiguity is False


def test_session_topic_math_theory_can_override_compute_memory():
    store = InMemoryMemoryStore([_compute_whats_memory()])
    state = SessionState(current_topic="math_theory")

    ir = analyze_intent("1+2是啥？", user_id="u1", session_state=state, memory_store=store)

    assert ir.ambiguity is True or ir.selected_intent == "explain.math_concept"
    assert any(
        item["reason"] == "skipped_current_topic_math_theory"
        for item in ir.diagnostics["memory_bias"]
    )


def test_session_topic_quick_calculation_strengthens_compute_memory():
    store = InMemoryMemoryStore([_compute_whats_memory(confidence=0.7)])
    state = SessionState(current_topic="quick_calculation")

    ir = analyze_intent("1+2是啥？", user_id="u1", session_state=state, memory_store=store)

    assert ir.selected_intent == "compute.arithmetic"
    assert ir.ambiguity is False


def test_json_memory_store_persists_memory(tmp_path):
    path = tmp_path / "reader_memory.json"
    store = JsonMemoryStore(path)
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
    reloaded = JsonMemoryStore(path)

    assert memory is not None
    assert len(reloaded.memories) == 1
    persisted = reloaded.memories[0]
    assert persisted.user_id == "u1"
    assert persisted.pattern == "<simple_math_expr> 是啥"
    assert persisted.scope == "math.short_query"
    assert persisted.evidence == candidate.evidence
    assert persisted.intent_weights is not None
    assert persisted.intent_weights["compute.arithmetic"] > 0.5


def test_memory_policy_rejects_ambiguous_confirmation():
    policy = MemoryPolicyEngine()
    store = InMemoryMemoryStore(policy_engine=policy)
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

    allowed, reason = policy.validate_update(candidate)

    assert allowed is False
    assert "feedback_type_not_writable" in reason
    assert store.apply_update(candidate) is None


def test_memory_policy_rejects_missing_user_id():
    policy = MemoryPolicyEngine()
    store = InMemoryMemoryStore(policy_engine=policy)
    candidate = MemoryUpdateCandidate(
        user_id=None,
        pattern="<simple_math_expr> 是啥",
        scope="math.short_query",
        preferred_intent="compute.arithmetic",
        corrected_intent="compute.arithmetic",
        feedback_type="explicit_correction",
        confidence_delta=0.25,
        evidence=[],
        should_write_long_term_memory=True,
    )

    allowed, reason = policy.validate_update(candidate)

    assert allowed is False
    assert reason == "missing_user_id"
    assert store.apply_update(candidate) is None

