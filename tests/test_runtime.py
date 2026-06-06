from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dk_agent.core.runtime import AgentRuntime
from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.llm.deepseek_client import DeepSeekClient
from dk_agent.llm.gateway import LLMResult


class FakeGateway:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] | None = None

    def chat(
        self,
        messages: list[tuple[str, str]],
        *,
        model_role: str = "pro",
    ) -> LLMResult:
        self.messages = messages
        return LLMResult(
            content="ok",
            usage={"total_tokens": 3},
            model_name="fake-model",
        )


class RuntimeTests(unittest.TestCase):
    def test_agent_types_are_constructable(self) -> None:
        request = AgentRequest(user_text="你好")
        response = AgentResponse(
            reply_text="你好",
            route="direct-chat",
            model_role="pro",
            model_name="fake-model",
            reasoning_profile="off",
        )

        self.assertEqual(request.mode, "chat")
        self.assertEqual(request.metadata, {})
        self.assertEqual(response.tools, [])
        self.assertIsNone(response.error)

    def test_chat_request_builds_chat_messages(self) -> None:
        gateway = FakeGateway()
        runtime = AgentRuntime(gateway)

        response = runtime.run(AgentRequest(user_text="介绍一下项目", mode="chat"))

        self.assertEqual(response.reply_text, "ok")
        self.assertEqual(gateway.messages[0][0], "system")
        self.assertIn("中文助手", gateway.messages[0][1])
        self.assertEqual(gateway.messages[1], ("human", "介绍一下项目"))

    def test_selected_text_request_builds_selected_text_messages(self) -> None:
        gateway = FakeGateway()
        runtime = AgentRuntime(gateway)

        runtime.run(
            AgentRequest(
                user_text="这句话是什么意思",
                selected_text="一段被选中的回复正文",
                mode="selected_text_question",
            )
        )

        self.assertEqual(gateway.messages[0][0], "system")
        self.assertIn("选中文本", gateway.messages[1][1])
        self.assertIn("一段被选中的回复正文", gateway.messages[1][1])
        self.assertIn("这句话是什么意思", gateway.messages[1][1])

    def test_deepseek_missing_api_key_returns_error(self) -> None:
        old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            result = DeepSeekClient().chat([("human", "hi")])
        finally:
            if old_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_key

        self.assertIsNotNone(result.error)
        self.assertIn("DEEPSEEK_API_KEY", result.content)

    def test_tui_layer_does_not_import_chatdeepseek(self) -> None:
        tui_path = ROOT / "src" / "dk_agent" / "app" / "tui_app.py"
        tui_source = tui_path.read_text(encoding="utf-8")

        self.assertNotIn("ChatDeepSeek", tui_source)
        self.assertNotIn("DEEPSEEK_API_KEY", tui_source)
        self.assertNotIn("deepseek-v4-pro", tui_source)


if __name__ == "__main__":
    unittest.main()
