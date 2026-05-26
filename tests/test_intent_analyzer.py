from intent_analyzer import (
    InMemoryMemoryStore,
    ReaderSemanticMemory,
    SessionState,
    analyze_intent,
)


def test_compute_direct():
    ir = analyze_intent("帮我算一下1+1")

    assert ir.selected_intent == "compute.arithmetic"
    assert ir.intent_candidates[0].slots["expression"] == "1+1"
    assert ir.ambiguity is False


def test_compute_parenthesized_expression():
    ir = analyze_intent("帮我算一下(1+2)*3")

    assert ir.selected_intent == "compute.arithmetic"
    assert ir.intent_candidates[0].slots["expression"] == "(1+2)*3"


def test_ambiguous_math_whats():
    ir = analyze_intent("1+1是啥？")

    intents = {candidate.intent for candidate in ir.intent_candidates}
    assert "compute.arithmetic" in intents
    assert "explain.math_concept" in intents
    assert ir.ambiguity is True
    assert ir.clarification is not None
    assert ir.clarification.needed is True


def test_user_memory_bias():
    store = InMemoryMemoryStore(
        [
            ReaderSemanticMemory(
                memory_id="mem-1",
                user_id="u1",
                pattern="<simple_math_expr> 是啥",
                scope="math.short_query",
                intent_distribution={"compute.arithmetic": 0.8},
                confidence=0.8,
                positive_evidence_count=3,
                negative_evidence_count=0,
                conditions={},
                evidence=[],
                last_updated_at="2026-05-21T00:00:00Z",
            )
        ]
    )

    ir = analyze_intent("1+2是啥？", user_id="u1", memory_store=store)

    assert ir.selected_intent == "compute.arithmetic"
    assert ir.ambiguity is False


def test_current_explicit_instruction_overrides_memory():
    store = InMemoryMemoryStore(
        [
            ReaderSemanticMemory(
                memory_id="mem-1",
                user_id="u1",
                pattern="<simple_math_expr> 是啥",
                scope="math.short_query",
                intent_distribution={"compute.arithmetic": 0.8},
                confidence=0.8,
                positive_evidence_count=3,
                negative_evidence_count=0,
                conditions={},
                evidence=[],
                last_updated_at="2026-05-21T00:00:00Z",
            )
        ]
    )

    ir = analyze_intent(
        "这次我不是问答案，我想知道1+1的数学意义",
        user_id="u1",
        memory_store=store,
    )

    assert ir.selected_intent == "explain.math_concept"


def test_long_text_plan_analysis():
    text = (
        "我们准备做一个 AI Agent 平台，包含任务规划、工具调用、长期记忆、权限审批和审计日志。\n"
        "第一阶段先接入本地文件、数据库和搜索工具，第二阶段接 GraphRAG，第三阶段做自动部署。\n"
        "当前方案假设所有工具都能稳定返回结构化结果，并且用户不会并发修改同一个任务状态。"
        "权限方面计划后续再补，测试主要依赖人工验收，线上监控暂时只记录错误日志。"
        "请帮我看看这个方案哪里不靠谱，从工程落地、风险、性能、测试和成本角度分析。"
    )

    ir = analyze_intent(text)

    assert ir.selected_intent == "analyze.plan"
    assert ir.intent_candidates[0].slots["payload"] == text
    assert ir.dispatch_hint is not None
    assert ir.dispatch_hint.required_modules == [
        "content_parser",
        "logic_analyzer",
        "risk_analyzer",
        "response_renderer",
    ]


def test_state_is_populated_for_ambiguous_intent():
    state = SessionState()

    ir = analyze_intent("1+1是啥？", session_state=state)

    assert ir.clarification is not None
    assert state.pending_clarification == ir.clarification
    assert state.pending_input_text == "1+1是啥？"
