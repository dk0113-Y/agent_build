from __future__ import annotations

from dk_agent.core.session_state import PendingClarification
from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.executor.direct_executor import DirectExecutor
from dk_agent.llm.deepseek_client import DeepSeekClient
from dk_agent.llm.gateway import ModelGateway
from dk_agent.routing.meta_controller import MetaController, MetaControllerResult


class AgentRuntime:
    def __init__(
        self,
        gateway: ModelGateway,
        *,
        meta_controller: MetaController | None = None,
        direct_executor: DirectExecutor | None = None,
    ) -> None:
        self.gateway = gateway
        self.meta_controller = meta_controller or MetaController(gateway)
        self.direct_executor = direct_executor or DirectExecutor(gateway)
        self.pending_clarification: PendingClarification | None = None

    def run(self, request: AgentRequest) -> AgentResponse:
        effective_request, is_resume = self._prepare_request(request)
        meta_result = self.meta_controller.analyze(
            user_text=effective_request.user_text,
            selected_text=effective_request.selected_text,
            is_clarification_resume=is_resume,
        )

        if self._should_stop_at_clarification_gate(meta_result.decision):
            return self._clarification_response(meta_result, effective_request)

        response = self.direct_executor.run(effective_request, meta_result.decision)
        response.route = "meta->direct-chat"
        response.meta_route = response.route
        response.meta_decision = meta_result.decision.to_metadata()
        response.need_clarification = False
        response.pending_clarification = False
        response.metadata.update(
            {
                "meta_decision": meta_result.decision.to_metadata(),
                "meta_usage": meta_result.meta_usage,
                "meta_model_name": meta_result.meta_model_name,
                "meta_elapsed_seconds": meta_result.meta_elapsed_seconds,
                "executor_usage": response.usage,
                "executor_elapsed_seconds": response.elapsed_seconds,
            }
        )
        return response

    def _should_stop_at_clarification_gate(self, decision: object) -> bool:
        autonomy_mode = getattr(decision, "autonomy_mode", None)
        high_privilege_modes = {
            "read_files",
            "edit_files",
            "execute_commands",
            "external_delegate",
        }
        return bool(
            getattr(decision, "need_clarification", False)
            or getattr(decision, "need_human_approval", False)
            or autonomy_mode in high_privilege_modes
        )

    def _prepare_request(self, request: AgentRequest) -> tuple[AgentRequest, bool]:
        if self.pending_clarification is None:
            return request, False

        pending = self.pending_clarification
        self.pending_clarification = None
        enriched_user_text = self._build_enriched_user_text(
            original_user_text=pending.original_user_text,
            clarification_question=pending.clarification_question,
            current_user_text=request.user_text,
        )
        return (
            AgentRequest(
                user_text=enriched_user_text,
                mode="chat",
                selected_text=None,
                metadata=dict(request.metadata),
            ),
            True,
        )

    def _clarification_response(
        self,
        meta_result: MetaControllerResult,
        request: AgentRequest,
    ) -> AgentResponse:
        decision = meta_result.decision
        question = decision.clarification_question or (
            "This V0.4 prototype cannot execute high-privilege actions directly. "
            "Please clarify a safe answer-only or plan-only scope."
        )
        self.pending_clarification = PendingClarification(
            original_user_text=request.user_text,
            clarification_question=question,
            missing_info=list(decision.missing_info),
            meta_decision=decision,
        )
        return AgentResponse(
            reply_text=question,
            route="meta->clarify",
            model_role="meta",
            model_name=meta_result.meta_model_name,
            reasoning_profile="medium",
            tools=list(decision.tools),
            skills=list(decision.skills),
            verifiers=list(decision.verifiers),
            usage=meta_result.meta_usage,
            elapsed_seconds=meta_result.meta_elapsed_seconds,
            error=None,
            metadata={
                "meta_decision": decision.to_metadata(),
                "meta_usage": meta_result.meta_usage,
                "pending_clarification": True,
            },
            meta_decision=decision.to_metadata(),
            meta_route="meta->clarify",
            need_clarification=True,
            pending_clarification=True,
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


def create_default_runtime() -> AgentRuntime:
    return AgentRuntime(DeepSeekClient())
