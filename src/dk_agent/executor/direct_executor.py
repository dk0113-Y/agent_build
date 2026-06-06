from __future__ import annotations

import time

from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.llm.gateway import ModelGateway
from dk_agent.routing.meta_schema import MetaDecision


CHAT_SYSTEM_PROMPT = (
    "\u4f60\u662f dk-agent \u7684\u4e2d\u6587\u52a9\u624b\u3002"
    "\u8bf7\u7528\u4e2d\u6587\u76f4\u63a5\u56de\u7b54\u7528\u6237\u7684\u95ee\u9898\u3002"
)
SELECTED_TEXT_SYSTEM_PROMPT = (
    "You are dk-agent, a Chinese assistant. The user provides selected text from your "
    "previous answer and a question about it. Prefer answering around the selected text; "
    "mention insufficient context when necessary."
)
SELECTED_TEXT_LABEL = "\u9009\u4e2d\u6587\u672c"
USER_QUESTION_LABEL = "\u7528\u6237\u95ee\u9898"


class DirectExecutor:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    def run(self, request: AgentRequest, meta_decision: MetaDecision) -> AgentResponse:
        started_at = time.monotonic()
        result = self.gateway.chat(
            self._build_messages(request),
            model_role=meta_decision.executor_role,
        )
        elapsed_seconds = time.monotonic() - started_at

        return AgentResponse(
            reply_text=result.content,
            route="direct-chat",
            model_role=meta_decision.executor_role,
            model_name=result.model_name,
            reasoning_profile=meta_decision.reasoning_profile,
            tools=list(meta_decision.tools),
            skills=list(meta_decision.skills),
            verifiers=list(meta_decision.verifiers),
            usage=result.usage,
            elapsed_seconds=elapsed_seconds,
            error=result.error,
        )

    def _build_messages(self, request: AgentRequest) -> list[tuple[str, str]]:
        if request.mode == "selected_text_question" and request.selected_text:
            return [
                ("system", SELECTED_TEXT_SYSTEM_PROMPT),
                (
                    "human",
                    f"{SELECTED_TEXT_LABEL}:\n{request.selected_text}\n\n"
                    f"{USER_QUESTION_LABEL}: {request.user_text}",
                ),
            ]

        return [
            ("system", CHAT_SYSTEM_PROMPT),
            ("human", request.user_text),
        ]
