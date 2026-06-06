from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.executor.direct_executor import DirectExecutor
from dk_agent.graph.routing import decision_value, meta_decision_to_dict
from dk_agent.graph.state import AgentGraphState
from dk_agent.routing.meta_controller import MetaController
from dk_agent.routing.meta_schema import MetaDecision
from langgraph.types import interrupt


SAFE_CLARIFICATION_FALLBACK = (
    "This V0.4 prototype cannot execute high-privilege actions directly. "
    "Please clarify a safe answer-only or plan-only scope."
)


def make_meta_node(meta_controller: MetaController) -> Callable[[AgentGraphState], dict[str, Any]]:
    def meta_node(state: AgentGraphState) -> dict[str, Any]:
        result = meta_controller.analyze(
            user_text=state["effective_user_text"],
            selected_text=state.get("selected_text"),
            is_clarification_resume=state.get("is_clarification_resume", False),
        )
        return {
            "meta_decision": meta_decision_to_dict(result.decision),
            "meta_usage": result.meta_usage,
            "meta_model_name": result.meta_model_name,
            "meta_elapsed_seconds": result.meta_elapsed_seconds,
        }

    return meta_node


def make_clarification_node() -> Callable[[AgentGraphState], dict[str, Any]]:
    def clarification_node(state: AgentGraphState) -> dict[str, Any]:
        decision = state["meta_decision"]
        question = decision_value(decision, "clarification_question") or SAFE_CLARIFICATION_FALLBACK
        decision_metadata = meta_decision_to_dict(decision)
        payload = {
            "type": "clarification",
            "question": question,
            "original_user_text": state.get("original_user_text") or state["effective_user_text"],
            "missing_info": list(decision_value(decision, "missing_info", [])),
            "meta_decision": decision_metadata,
            "route": "meta->clarify",
            "meta_model_name": state.get("meta_model_name"),
            "meta_usage": state.get("meta_usage"),
            "meta_elapsed_seconds": state.get("meta_elapsed_seconds", 0.0),
        }
        user_supplement = interrupt(payload)
        enriched_user_text = _build_enriched_user_text(
            original_user_text=payload["original_user_text"],
            clarification_question=question,
            current_user_text=str(user_supplement),
        )
        return {
            "effective_user_text": enriched_user_text,
            "selected_text": None,
            "mode": "chat",
            "is_clarification_resume": True,
            "route": "meta->clarify",
            "pending_interrupt": False,
        }

    return clarification_node


def make_execute_node(direct_executor: DirectExecutor) -> Callable[[AgentGraphState], dict[str, Any]]:
    def execute_node(state: AgentGraphState) -> dict[str, Any]:
        request_data = state.get("request_data", {})
        effective_request = AgentRequest(
            user_text=state["effective_user_text"],
            mode=state.get("mode", "chat") if not state.get("is_clarification_resume", False) else "chat",
            selected_text=state.get("selected_text"),
            metadata=dict(request_data.get("metadata") or {}),
        )
        decision = _decision_model(state["meta_decision"])
        response = direct_executor.run(effective_request, decision)
        decision_metadata = meta_decision_to_dict(decision)
        response.route = "meta->direct-chat"
        response.meta_route = response.route
        response.meta_decision = decision_metadata
        response.need_clarification = False
        response.pending_clarification = False
        response.metadata.update(
            {
                "meta_decision": decision_metadata,
                "meta_usage": state.get("meta_usage"),
                "meta_model_name": state.get("meta_model_name"),
                "meta_elapsed_seconds": state.get("meta_elapsed_seconds", 0.0),
                "executor_usage": response.usage,
                "executor_elapsed_seconds": response.elapsed_seconds,
            }
        )
        return {
            "response_data": asdict(response),
            "route": "meta->direct-chat",
            "pending_interrupt": False,
        }

    return execute_node


def make_response_node() -> Callable[[AgentGraphState], dict[str, Any]]:
    def response_node(state: AgentGraphState) -> dict[str, Any]:
        if state.get("response_data") is not None:
            return {}
        return {
            "response_data": asdict(AgentResponse(
                reply_text="Agent graph did not produce a response.",
                route=state.get("route") or "graph-error",
                model_role="runtime",
                model_name=state.get("meta_model_name") or "unknown",
                reasoning_profile="none",
                error=state.get("error") or "missing response",
            )),
            "route": state.get("route") or "graph-error",
        }

    return response_node


def _decision_model(meta_decision: object) -> MetaDecision:
    if isinstance(meta_decision, MetaDecision):
        return meta_decision
    if isinstance(meta_decision, dict):
        return MetaDecision.model_validate(meta_decision)
    raise TypeError("meta_decision is missing or invalid")


def _build_enriched_user_text(
    *,
    original_user_text: str,
    clarification_question: str,
    current_user_text: str,
) -> str:
    return (
        "Original user request:\n"
        f"{original_user_text}\n\n"
        "Previous clarification question:\n"
        f"{clarification_question}\n\n"
        "User supplement:\n"
        f"{current_user_text}"
    )
