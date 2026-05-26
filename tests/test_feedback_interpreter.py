from intent_analyzer import SessionState, analyze_intent
from intent_analyzer.feedback import interpret_feedback


def _pending_state() -> SessionState:
    state = SessionState()
    analyze_intent("1+1是啥？", user_id="u1", session_state=state)
    return state


def test_feedback_result():
    state = _pending_state()

    ir = analyze_intent("结果", user_id="u1", session_state=state)
    record = ir.diagnostics["feedback_record"]

    assert record.feedback_type == "explicit_confirmation"
    assert record.corrected_intent == "compute.arithmetic"
    assert record.should_write_long_term_memory is True
    assert ir.memory_update_candidate is not None
    assert ir.memory_update_candidate.should_write_long_term_memory is True


def test_feedback_dui_is_ambiguous():
    state = _pending_state()

    record = interpret_feedback("对", state)

    assert record.feedback_type == "ambiguous_confirmation"
    assert record.should_write_long_term_memory is False


def test_feedback_no_without_alternative():
    state = _pending_state()

    record = interpret_feedback("不是", state)

    assert record.feedback_type == "rejection_without_alternative"
    assert record.should_write_long_term_memory is False


def test_explicit_correction():
    state = _pending_state()

    record = interpret_feedback("不不不，我只是想知道1+1等于几", state)

    assert record.feedback_type == "explicit_correction"
    assert record.corrected_intent == "compute.arithmetic"
    assert record.should_write_long_term_memory is True


def test_explicit_explain_correction():
    state = _pending_state()

    record = interpret_feedback("不是这个意思，我想知道它的数学意义", state)

    assert record.feedback_type == "explicit_correction"
    assert record.corrected_intent == "explain.math_concept"
    assert record.should_write_long_term_memory is True


def test_repeated_question_is_not_memory_worthy():
    state = _pending_state()

    record = interpret_feedback("我问你1+1是啥", state)

    assert record.feedback_type == "repeated_question"
    assert record.should_write_long_term_memory is False

