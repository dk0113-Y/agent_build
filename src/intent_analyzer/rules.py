from __future__ import annotations

import re

from .schemas import DispatchHint, IntentCandidate, InputType, SessionState


INTENT_COMPUTE = "compute.arithmetic"
INTENT_EXPLAIN = "explain.math_concept"
INTENT_ANALYZE_PLAN = "analyze.plan"
INTENT_SUMMARIZE = "summarize.content"
INTENT_REWRITE = "rewrite.content"
INTENT_ASK_CLARIFICATION = "ask.clarification"
INTENT_UNKNOWN = "unknown"

LONG_TEXT_MIN_CHARS = 180

_MATH_EXPR_RE = re.compile(
    r"(?<![\d.])"
    r"([()\d][()\d.\s+\-*/×÷]*[+\-*/×÷][()\d.\s+\-*/×÷]*\d\)*)"
)

_PUNCT_RE = re.compile(r"[，。！？?！、；;：:\s]+")

COMPUTE_KEYWORDS = ("算一下", "计算", "等于几", "多少", "求值", "答案", "结果", "直接算")
EXPLAIN_KEYWORDS = ("数学意义", "意义", "原理", "为什么", "本质", "解释", "什么意思", "是什么含义")
ANALYZE_KEYWORDS = (
    "方案",
    "系统设计",
    "架构",
    "哪里不靠谱",
    "不靠谱",
    "风险",
    "可行性",
    "分析",
    "工程落地",
)
SUMMARIZE_KEYWORDS = ("总结", "概括", "摘要", "提炼")
REWRITE_KEYWORDS = ("改写", "润色", "写成", "变成", "重写")
ANALYSIS_DIMENSION_KEYWORDS = {
    "工程落地": "engineering_delivery",
    "部署": "deployment",
    "性能": "performance",
    "测试": "testing",
    "答辩": "defense",
    "风险": "risk",
    "成本": "cost",
    "稳定性": "stability",
    "可行性": "feasibility",
    "架构": "architecture",
}

REQUIRED_SLOTS = {
    INTENT_COMPUTE: ["expression"],
    INTENT_EXPLAIN: ["topic"],
    INTENT_ANALYZE_PLAN: ["payload"],
    INTENT_SUMMARIZE: ["payload"],
    INTENT_REWRITE: ["payload"],
}

DISPATCH_MODULES = {
    INTENT_COMPUTE: ["calculator", "response_renderer"],
    INTENT_EXPLAIN: ["logic_analyzer", "response_renderer"],
    INTENT_ANALYZE_PLAN: [
        "content_parser",
        "logic_analyzer",
        "risk_analyzer",
        "response_renderer",
    ],
    INTENT_SUMMARIZE: ["content_parser", "response_renderer"],
    INTENT_REWRITE: ["content_parser", "response_renderer"],
}


def normalize_text(text: str) -> str:
    return _PUNCT_RE.sub("", text.strip().lower())


def extract_math_expression(text: str) -> str | None:
    match = _MATH_EXPR_RE.search(text)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1).strip()).replace("×", "*").replace("÷", "/")


def has_math_expression(text: str) -> bool:
    return extract_math_expression(text) is not None


def classify_input(text: str, session_state: SessionState | None = None) -> tuple[InputType, str]:
    stripped = text.strip()
    if session_state and session_state.pending_clarification is not None:
        return "clarification_reply", "pending_clarification"
    if len(stripped) >= LONG_TEXT_MIN_CHARS or stripped.count("\n") >= 2:
        return "long_text", "length_or_multiline"
    if len(stripped) <= 80 and has_math_expression(stripped):
        return "short_query", "short_math_query"
    return "unknown", "fallback_unknown"


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _is_negated_near(text: str, keyword: str) -> bool:
    index = text.find(keyword)
    if index < 0:
        return False
    prefix = text[max(0, index - 8) : index]
    return any(marker in prefix for marker in ("不是", "不想", "并非", "不是问", "不问"))


def detect_explicit_instruction(text: str) -> bool:
    return (
        has_explicit_compute_instruction(text)
        or has_explicit_explain_instruction(text)
        or contains_any(text, ANALYZE_KEYWORDS)
        or contains_any(text, SUMMARIZE_KEYWORDS)
        or contains_any(text, REWRITE_KEYWORDS)
    )


def has_explicit_compute_instruction(text: str) -> bool:
    return any(keyword in text and not _is_negated_near(text, keyword) for keyword in COMPUTE_KEYWORDS)


def has_explicit_explain_instruction(text: str) -> bool:
    return any(keyword in text and not _is_negated_near(text, keyword) for keyword in EXPLAIN_KEYWORDS)


def infer_memory_pattern(text: str) -> tuple[str, str]:
    compact = normalize_text(text)
    expression = extract_math_expression(text)
    if expression and ("是啥" in compact or "是什么" in compact):
        return "<simple_math_expr> 是啥", "math.short_query"
    if expression:
        return "<simple_math_expr>", "math.short_query"
    if len(text) >= LONG_TEXT_MIN_CHARS:
        return "<long_text>", "content.long_text"
    return compact[:80] or "<empty>", "general"


def extract_analysis_dimensions(text: str) -> list[str]:
    return [
        dimension
        for keyword, dimension in ANALYSIS_DIMENSION_KEYWORDS.items()
        if keyword in text
    ]


def extract_instruction_hint(text: str) -> str:
    parts = [part.strip() for part in re.split(r"[\n。！？!?]", text) if part.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][:120]
    return f"{parts[0][:80]} ... {parts[-1][:80]}"


def _candidate(intent: str, confidence: float, slots: dict, evidence: list[str]) -> IntentCandidate:
    return IntentCandidate(
        intent=intent,
        confidence=max(0.0, min(1.0, confidence)),
        slots=slots,
        evidence=evidence,
    )


def generate_intent_candidates(text: str, input_type: InputType) -> list[IntentCandidate]:
    expression = extract_math_expression(text)
    candidates: list[IntentCandidate] = []

    explicit_compute = has_explicit_compute_instruction(text)
    explicit_explain = has_explicit_explain_instruction(text)

    if expression:
        if explicit_compute:
            candidates.append(
                _candidate(
                    INTENT_COMPUTE,
                    0.88,
                    {"expression": expression},
                    ["math_expression", "explicit_compute_keyword"],
                )
            )
        elif "是啥" in normalize_text(text) or "是什么" in normalize_text(text):
            candidates.append(
                _candidate(
                    INTENT_COMPUTE,
                    0.50,
                    {"expression": expression},
                    ["math_expression", "colloquial_whats"],
                )
            )
        else:
            candidates.append(
                _candidate(INTENT_COMPUTE, 0.62, {"expression": expression}, ["math_expression"])
            )

        if explicit_explain:
            candidates.append(
                _candidate(
                    INTENT_EXPLAIN,
                    0.90,
                    {"topic": expression},
                    ["math_expression", "explicit_explain_keyword"],
                )
            )
        elif "是啥" in normalize_text(text) or "是什么" in normalize_text(text):
            candidates.append(
                _candidate(
                    INTENT_EXPLAIN,
                    0.48,
                    {"topic": expression},
                    ["math_expression", "colloquial_whats"],
                )
            )

    if contains_any(text, ANALYZE_KEYWORDS):
        confidence = 0.90 if input_type == "long_text" else 0.72
        candidates.append(
            _candidate(
                INTENT_ANALYZE_PLAN,
                confidence,
                {
                    "payload": text,
                    "instruction_hint": extract_instruction_hint(text),
                    "analysis_dimensions": extract_analysis_dimensions(text),
                },
                ["analysis_keyword"] + (["long_text"] if input_type == "long_text" else []),
            )
        )

    if contains_any(text, SUMMARIZE_KEYWORDS):
        candidates.append(
            _candidate(
                INTENT_SUMMARIZE,
                0.82 if input_type == "long_text" else 0.68,
                {"payload": text, "instruction_hint": extract_instruction_hint(text)},
                ["summarize_keyword"],
            )
        )

    if contains_any(text, REWRITE_KEYWORDS):
        candidates.append(
            _candidate(
                INTENT_REWRITE,
                0.82 if input_type == "long_text" else 0.68,
                {"payload": text, "instruction_hint": extract_instruction_hint(text)},
                ["rewrite_keyword"],
            )
        )

    if not candidates:
        candidates.append(_candidate(INTENT_UNKNOWN, 0.30, {}, ["no_rule_match"]))

    return sorted(candidates, key=lambda item: item.confidence, reverse=True)


def build_dispatch_hint(intent: str, slots: dict) -> DispatchHint | None:
    if intent in (INTENT_UNKNOWN, INTENT_ASK_CLARIFICATION):
        return None
    required_slots = REQUIRED_SLOTS.get(intent, [])
    blocking = [slot for slot in required_slots if slot not in slots or slots[slot] in (None, "")]
    risk_level = "medium" if intent == INTENT_ANALYZE_PLAN else "low"
    return DispatchHint(
        required_modules=DISPATCH_MODULES.get(intent, ["response_renderer"]),
        risk_level=risk_level,
        blocking_missing_slots=blocking,
    )
