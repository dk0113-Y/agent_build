from __future__ import annotations

import time

from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.llm.gateway import ModelGateway


CHAT_SYSTEM_PROMPT = "你是 dk-agent 的中文助手。请用中文直接回答用户的问题。"
SELECTED_TEXT_SYSTEM_PROMPT = (
    "你是 dk-agent 的中文助手。用户会给出一段从你上一条回复中划选的文本，"
    "以及一个针对该文本的问题。请优先围绕选中文本作答，必要时指出上下文不足。"
)


class AgentRuntime:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    def run(self, request: AgentRequest) -> AgentResponse:
        started_at = time.monotonic()
        model_role = "pro"
        messages = self._build_messages(request)
        result = self.gateway.chat(messages, model_role=model_role)
        elapsed_seconds = time.monotonic() - started_at

        return AgentResponse(
            reply_text=result.content,
            route="direct-chat",
            model_role=model_role,
            model_name=result.model_name,
            reasoning_profile="off",
            tools=[],
            skills=[],
            verifiers=[],
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
                    f"选中文本：\n{request.selected_text}\n\n用户问题：{request.user_text}",
                ),
            ]

        return [
            ("system", CHAT_SYSTEM_PROMPT),
            ("human", request.user_text),
        ]
