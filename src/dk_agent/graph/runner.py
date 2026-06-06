from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from dk_agent.core.session_state import PendingClarification
from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.executor.direct_executor import DirectExecutor
from dk_agent.graph.graph import build_agent_graph
from dk_agent.graph.state import AgentGraphState
from dk_agent.routing.meta_controller import MetaController
from dk_agent.routing.meta_schema import MetaDecision


class AgentGraphRunner:
    def __init__(
        self,
        *,
        meta_controller: MetaController,
        direct_executor: DirectExecutor,
        thread_id: str | None = None,
        checkpointer=None,
    ) -> None:
        self.meta_controller = meta_controller
        self.direct_executor = direct_executor
        self.graph = build_agent_graph(meta_controller, direct_executor, checkpointer=checkpointer)
        self.thread_id = thread_id or str(uuid4())
        self.config = {"configurable": {"thread_id": self.thread_id}}
        self.awaiting_clarification = False
        self.last_interrupt_payload: dict[str, Any] | None = None

    def run(self, request: AgentRequest) -> AgentResponse:
        if self.awaiting_clarification:
            result = self.graph.invoke(Command(resume=request.user_text), config=self.config)
        else:
            result = self.graph.invoke(self._initial_state(request), config=self.config)

        interrupt_payload = self._extract_interrupt_payload(result)
        if interrupt_payload is not None:
            self.awaiting_clarification = True
            self.last_interrupt_payload = interrupt_payload
            return self._response_from_interrupt(interrupt_payload)

        self.awaiting_clarification = False
        self.last_interrupt_payload = None
        return self._response_from_result(result)

    @property
    def pending_clarification(self) -> PendingClarification | None:
        if not self.awaiting_clarification or self.last_interrupt_payload is None:
            return None
        decision_data = self.last_interrupt_payload.get("meta_decision") or {}
        return PendingClarification(
            original_user_text=str(self.last_interrupt_payload.get("original_user_text") or ""),
            clarification_question=str(self.last_interrupt_payload.get("question") or ""),
            missing_info=list(self.last_interrupt_payload.get("missing_info") or []),
            meta_decision=MetaDecision.model_validate(decision_data),
        )

    @pending_clarification.setter
    def pending_clarification(self, value: PendingClarification | None) -> None:
        if value is None:
            self.awaiting_clarification = False
            self.last_interrupt_payload = None
            return
        self.awaiting_clarification = True
        self.last_interrupt_payload = {
            "type": "clarification",
            "question": value.clarification_question,
            "original_user_text": value.original_user_text,
            "missing_info": list(value.missing_info),
            "meta_decision": value.meta_decision.model_dump(),
            "route": "meta->clarify",
        }

    def _initial_state(self, request: AgentRequest) -> AgentGraphState:
        return {
            "request_data": asdict(request),
            "original_user_text": request.user_text,
            "effective_user_text": request.user_text,
            "selected_text": request.selected_text,
            "mode": request.mode,
            "is_clarification_resume": False,
            "meta_decision": None,
            "meta_usage": None,
            "meta_model_name": None,
            "meta_elapsed_seconds": 0.0,
            "route": None,
            "response_data": None,
            "pending_interrupt": False,
            "error": None,
        }

    def _extract_interrupt_payload(self, result: object) -> dict[str, Any] | None:
        if not isinstance(result, dict):
            return None
        interrupts = result.get("__interrupt__")
        if not interrupts:
            return None
        first_interrupt = interrupts[0]
        value = getattr(first_interrupt, "value", first_interrupt)
        if isinstance(value, dict):
            return value
        return None

    def _response_from_interrupt(self, payload: dict[str, Any]) -> AgentResponse:
        decision_value = payload.get("meta_decision") or {}
        decision = decision_value if isinstance(decision_value, dict) else {}
        response = AgentResponse(
            reply_text=str(payload.get("question") or "Please clarify your request."),
            route=str(payload.get("route") or "meta->clarify"),
            model_role="meta",
            model_name=str(payload.get("meta_model_name") or "meta"),
            reasoning_profile="medium",
            tools=list(decision.get("tools") or []),
            skills=list(decision.get("skills") or []),
            verifiers=list(decision.get("verifiers") or []),
            usage=payload.get("meta_usage"),
            elapsed_seconds=float(payload.get("meta_elapsed_seconds") or 0.0),
            error=None,
            metadata={
                "interrupt_payload": payload,
                "thread_id": self.thread_id,
                "pending_clarification": True,
            },
            meta_decision=decision,
            meta_route="meta->clarify",
            need_clarification=True,
            pending_clarification=True,
        )
        return response

    def _response_from_result(self, final_state: object) -> AgentResponse:
        if not isinstance(final_state, dict):
            return self._missing_response("graph returned invalid state")

        response_data = final_state.get("response_data")
        if isinstance(response_data, dict):
            response = AgentResponse(**response_data)
            response.metadata.setdefault("thread_id", self.thread_id)
            response.pending_clarification = False
            response.need_clarification = False
            return response

        return self._missing_response(str(final_state.get("error") or "missing response"))

    def _missing_response(self, error: str) -> AgentResponse:
        return AgentResponse(
            reply_text="Agent graph did not produce a response.",
            route="graph-error",
            model_role="runtime",
            model_name="unknown",
            reasoning_profile="none",
            error=error,
        )
