from __future__ import annotations

import os
from typing import Any

from dk_agent.llm.gateway import LLMResult


class DeepSeekClient:
    def __init__(
        self,
        *,
        model_name: str = "deepseek-v4-pro",
        temperature: float = 0.2,
        timeout: int = 60,
        max_retries: int = 1,
    ) -> None:
        self.model_name = model_name
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(
        self,
        messages: list[tuple[str, str]],
        *,
        model_role: str = "pro",
    ) -> LLMResult:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            error = "DeepSeek API Key 未配置。请设置环境变量 DEEPSEEK_API_KEY 后重试。"
            return LLMResult(
                content=error,
                usage=None,
                model_name=self.model_name,
                error=error,
            )

        try:
            from langchain_deepseek import ChatDeepSeek

            llm = ChatDeepSeek(
                model=self.model_name,
                temperature=self.temperature,
                timeout=self.timeout,
                max_retries=self.max_retries,
                api_key=api_key,
            )
            response = llm.invoke(messages)
        except Exception as exc:
            error = (
                f"DeepSeek 调用失败：{type(exc).__name__}。"
                "请检查网络、模型名称或 API Key 配置。"
            )
            return LLMResult(
                content=error,
                usage=None,
                model_name=self.model_name,
                error=error,
            )

        content = self._message_content_to_text(getattr(response, "content", ""))
        if not content:
            content = "DeepSeek 返回了空回复。"

        return LLMResult(
            content=content,
            usage=self._extract_usage_metadata(response),
            model_name=self.model_name,
            error=None,
        )

    def _message_content_to_text(self, content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts).strip()
        return str(content).strip() if content is not None else ""

    def _extract_usage_metadata(self, response: object) -> dict[str, Any] | None:
        usage = getattr(response, "usage_metadata", None)
        if isinstance(usage, dict) and usage:
            return usage

        response_metadata = getattr(response, "response_metadata", None)
        if isinstance(response_metadata, dict):
            for key in ("token_usage", "usage"):
                usage = response_metadata.get(key)
                if isinstance(usage, dict) and usage:
                    return usage

        return None
