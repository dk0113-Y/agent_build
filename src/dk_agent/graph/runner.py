from __future__ import annotations

from dk_agent.core.session_state import PendingClarification
from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.executor.direct_executor import DirectExecutor
from dk_agent.graph.graph import build_agent_graph
from dk_agent.graph.state import AgentGraphState
from dk_agent.routing.meta_controller import MetaController


class AgentGraphRunner:
    def __init__(
        self,
        *,
        meta_controller: MetaController,
        direct_executor: DirectExecutor,
    ) -> None:
        self.meta_controller = meta_controller
        self.direct_executor = direct_executor
        self.graph = build_agent_graph(meta_controller, direct_executor)
        self.pending_clarification: PendingClarification | None = None

    def run(self, request: AgentRequest) -> AgentResponse:
        effective_user_text, is_resume = self._prepare_user_text(request)
        initial_state: AgentGraphState = {
            "request": request,
            "effective_user_text": effective_user_text,
            "selected_text": None if is_resume else request.selected_text,
            "is_clarification_resume": is_resume,
            "meta_decision": None,
            "meta_usage": None,
            "meta_model_name": None,
            "meta_elapsed_seconds": 0.0,
            "route": None,
            "response": None,
            "pending_clarification": None,
            "error": None,
        }
        final_state = self.graph.invoke(initial_state)
        self.pending_clarification = final_state.get("pending_clarification")
        response = final_state.get("response")
        if response is None:
            return AgentResponse(
                reply_text="Agent graph did not produce a response.",
                route=final_state.get("route") or "graph-error",
                model_role="runtime",
                model_name=final_state.get("meta_model_name") or "unknown",
                reasoning_profile="none",
                error=final_state.get("error") or "missing response",
            )
        return response

    def _prepare_user_text(self, request: AgentRequest) -> tuple[str, bool]:
        if self.pending_clarification is None:
            return request.user_text, False

        pending = self.pending_clarification
        self.pending_clarification = None
        return (
            self._build_enriched_user_text(
                original_user_text=pending.original_user_text,
                clarification_question=pending.clarification_question,
                current_user_text=request.user_text,
            ),
            True,
        )

    def _build_enriched_user_text(
        self,
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
