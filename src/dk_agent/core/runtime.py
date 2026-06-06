from __future__ import annotations

from dk_agent.core.session_state import PendingClarification
from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.executor.direct_executor import DirectExecutor
from dk_agent.graph.runner import AgentGraphRunner
from dk_agent.llm.deepseek_client import DeepSeekClient
from dk_agent.llm.gateway import ModelGateway
from dk_agent.routing.meta_controller import MetaController


class AgentRuntime:
    def __init__(
        self,
        gateway: ModelGateway,
        *,
        meta_controller: MetaController | None = None,
        direct_executor: DirectExecutor | None = None,
        graph_runner: AgentGraphRunner | None = None,
        thread_id: str | None = None,
    ) -> None:
        self.gateway = gateway
        self.meta_controller = meta_controller or MetaController(gateway)
        self.direct_executor = direct_executor or DirectExecutor(gateway)
        self.graph_runner = graph_runner or AgentGraphRunner(
            meta_controller=self.meta_controller,
            direct_executor=self.direct_executor,
            thread_id=thread_id,
        )

    @property
    def pending_clarification(self) -> PendingClarification | None:
        return self.graph_runner.pending_clarification

    @pending_clarification.setter
    def pending_clarification(self, value: PendingClarification | None) -> None:
        self.graph_runner.pending_clarification = value

    def run(self, request: AgentRequest) -> AgentResponse:
        return self.graph_runner.run(request)


def create_default_runtime(thread_id: str | None = None) -> AgentRuntime:
    return AgentRuntime(DeepSeekClient(), thread_id=thread_id)
