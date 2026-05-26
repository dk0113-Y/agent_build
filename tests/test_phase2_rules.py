from intent_analyzer import analyze_intent
from intent_analyzer.rules import extract_math_expression


def test_math_expression_does_not_match_date():
    ir = analyze_intent("今天是2026-05-21")

    assert extract_math_expression("今天是2026-05-21") is None
    assert ir.selected_intent != "compute.arithmetic"


def test_math_expression_does_not_match_version():
    ir = analyze_intent("版本是v1.2-3")

    assert extract_math_expression("版本是v1.2-3") is None
    assert ir.selected_intent != "compute.arithmetic"


def test_math_expression_does_not_match_numbering_or_range():
    assert extract_math_expression("任务编号为A-123-456") is None
    assert extract_math_expression("范围是1-3章") is None
    assert extract_math_expression("RK3588-8G版本") is None


def test_math_expression_minus_with_compute_context():
    ir = analyze_intent("帮我算一下5-3")

    assert ir.selected_intent == "compute.arithmetic"
    assert ir.intent_candidates[0].slots["expression"] == "5-3"


def test_math_expression_keeps_common_operators():
    assert extract_math_expression("1+1") == "1+1"
    assert extract_math_expression("1 + 2") == "1+2"
    assert extract_math_expression("帮我算一下(1+2)*3") == "(1+2)*3"
    assert extract_math_expression("3*5") == "3*5"
    assert extract_math_expression("10/2") == "10/2"
    assert extract_math_expression("帮我算一下 6÷2") == "6/2"
    assert extract_math_expression("2×3是多少") == "2*3"


def test_long_text_instruction_head():
    text = (
        "请从工程落地角度分析下面方案：\n"
        "方案正文第一段，包含部署流程、依赖服务和上线节奏。\n"
        "方案正文第二段，包含权限审批、监控和回滚策略。"
    )

    ir = analyze_intent(text)
    slots = ir.intent_candidates[0].slots

    assert ir.selected_intent == "analyze.plan"
    assert "请从工程落地角度分析" in slots["instruction"]
    assert "方案正文第一段" in slots["payload"]
    assert slots["instruction_position"] == "head"


def test_long_text_instruction_tail():
    text = (
        "方案正文第一段，包含部署流程、依赖服务和上线节奏。\n"
        "方案正文第二段，包含权限审批、监控和回滚策略。\n"
        "以上是方案，请帮我看看哪里不靠谱。"
    )

    ir = analyze_intent(text)
    slots = ir.intent_candidates[0].slots

    assert ir.selected_intent == "analyze.plan"
    assert "请帮我看看哪里不靠谱" in slots["instruction"]
    assert "方案正文第一段" in slots["payload"]
    assert slots["instruction_position"] == "tail"

