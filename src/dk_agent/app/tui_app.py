from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from dk_agent.core.runtime import create_default_runtime
from dk_agent.core.types import AgentRequest, AgentResponse


AGENT_NAME = "dk-agent"
PROJECT_NAME = "lg-deepagent"


class DkAgentTUI(App):
    """Prototype for dk-agent TUI."""

    TITLE = "dk-agent"
    BINDINGS = [
        ("alt+z", "ask_selected_text", "针对选中文本提问"),
        ("escape", "clear_selected_text", "取消选区"),
    ]
    DEFAULT_CSS = """
    Screen {
        layout: vertical;
        background: #0B1020;
        color: #DCE7FF;
    }

    #topbar {
        height: 3;
        border-bottom: solid #4D6BFD;
        padding: 0 1;
        content-align: left middle;
        background: #0F172A;
        color: #DCE7FF;
    }

    #conversation {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
        background: #0B1020;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #4D6BFD 45%;
        scrollbar-color-hover: #6F8BFF 65%;
        scrollbar-color-active: #8EA2FF 80%;
        scrollbar-background: #0B1020;
    }

    #input {
        height: 3;
        border: solid #4D6BFD;
        padding: 0 1;
        background: #111827;
    }

    Input {
        height: 1;
        border: none;
        background: #111827;
        color: #EAF0FF;
    }

    Input:focus { border: none; }
    .user-message { margin: 1 0 0 0; color: #EAF0FF; }
    .agent-label { margin: 1 0 0 0; color: #6F8BFF; text-style: bold; }
    .agent-meta { margin: 0 0 0 2; padding: 0 1; border: solid #4D6BFD; color: #AFC0FF; background: #0F172A; }
    .agent-body { margin: 0 0 1 2; color: #DCE7FF; }
    .help-box { margin: 1 0; padding: 0 1; border: solid #4D6BFD; color: #DCE7FF; background: #0F172A; }
    .error-box { margin: 1 0; padding: 0 1; border: solid #EF4444; color: #FCA5A5; background: #1F1111; }
    """

    def compose(self) -> ComposeResult:
        yield Static(self._topbar_text(), id="topbar")
        yield VerticalScroll(id="conversation")
        yield Input(placeholder=self._default_placeholder(), id="input")

    def on_mount(self) -> None:
        self.selected_text: str | None = None
        self.runtime = create_default_runtime()
        self.query_one("#input", Input).focus()
        self._append_system_message(
            "TUI v0.4 started: AgentRuntime + MetaController + Clarification Gate + DeepSeek direct executor."
        )

    def _topbar_text(self) -> str:
        return (
            f"Agent: {AGENT_NAME} | "
            "Model: managed-by-runtime | "
            f"Project: {PROJECT_NAME} | "
            "Ctx: --"
        )

    def _default_placeholder(self) -> str:
        return "输入消息，或输入 /help、/exit"

    def on_input_changed(self, event: Input.Changed) -> None:
        try:
            event.input.cursor_position = len(event.value)
        except Exception:
            pass

    def _selection_preview(self, text: str, max_chars: int = 24) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= max_chars:
            return cleaned
        budget = max_chars - 1
        head_len = budget // 2
        tail_len = budget - head_len
        return f"{cleaned[:head_len]}…{cleaned[-tail_len:]}"

    def _selected_agent_body_text(self) -> str | None:
        selections = getattr(self.screen, "selections", None)
        if not selections:
            return None

        selected_parts: list[str] = []
        for widget, selection in list(selections.items()):
            if not getattr(widget, "is_attached", False):
                continue
            try:
                widget_selection = widget.get_selection(selection)
            except Exception:
                return None
            if not widget_selection:
                continue
            widget_text = "".join(widget_selection)
            if not widget_text.strip():
                continue
            if not widget.has_class("agent-body"):
                return None
            selected_parts.append(widget_text)

        selected = "".join(selected_parts).strip()
        return selected or None

    def action_ask_selected_text(self) -> None:
        try:
            selected = self.screen.get_selected_text()
        except Exception:
            selected = None

        if not selected or not selected.strip():
            self._append_error_message("未检测到选中文本。请先在 Agent 回复正文中划词，再按 Alt+Z。")
            self._conversation().scroll_end(animate=False)
            return

        agent_selected = self._selected_agent_body_text()
        if not agent_selected:
            self.selected_text = None
            self._append_error_message("当前只支持划选 Agent 回复正文中的文本。")
            self._conversation().scroll_end(animate=False)
            return

        self.selected_text = agent_selected
        preview = self._selection_preview(self.selected_text)
        input_widget = self.query_one("#input", Input)
        input_widget.placeholder = f"已选择“{preview}”文本，请输入问题"
        input_widget.focus()
        try:
            self.screen.clear_selection()
        except Exception:
            pass

    def action_clear_selected_text(self) -> None:
        self.selected_text = None
        try:
            self.screen.clear_selection()
        except Exception:
            pass
        input_widget = self.query_one("#input", Input)
        input_widget.placeholder = self._default_placeholder()
        input_widget.focus()

    def _append_error_message(self, text: str) -> None:
        self._conversation().mount(Static(text, classes="error-box"))

    def _format_tokens(self, usage: dict[str, Any] | None) -> str:
        if not usage:
            return "--"
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
        total_tokens = usage.get("total_tokens")
        parts = []
        if input_tokens is not None:
            parts.append(f"input: {input_tokens}")
        if output_tokens is not None:
            parts.append(f"output: {output_tokens}")
        if total_tokens is not None:
            parts.append(f"total: {total_tokens}")
        return " / ".join(parts) if parts else "--"

    def _format_capabilities(self, values: list[str]) -> str:
        return ", ".join(values) if values else "off"

    def _append_loading_message(self) -> Static:
        loading = Static("Agent 正在思考...", classes="agent-body")
        self._conversation().mount(loading)
        self._conversation().scroll_end(animate=False)
        return loading

    def _remove_loading_message(self, loading: Static | None) -> None:
        if loading is None:
            return
        try:
            loading.remove()
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        input_widget = self.query_one("#input", Input)
        input_widget.value = ""
        if not text:
            return

        if text in {"/exit", "/退出", "/q", "exit", "quit"}:
            self.action_clear_selected_text()
            self.exit()
            return

        if text in {"/help", "/帮助"}:
            self.action_clear_selected_text()
            self._append_help()
            await self._scroll_to_end()
            return

        loading = None
        try:
            if self.selected_text:
                selected = self.selected_text
                selected_preview = self._selection_preview(selected)
                self._append_user_message(f"针对选中文本“{selected_preview}”提问：{text}")
                request = AgentRequest(user_text=text, selected_text=selected, mode="selected_text_question")
            else:
                self._append_user_message(text)
                request = AgentRequest(user_text=text, mode="chat")

            loading = self._append_loading_message()
            response = await asyncio.to_thread(self.runtime.run, request)
            self._remove_loading_message(loading)
            self._append_agent_reply(response)
        finally:
            if self.selected_text:
                self.action_clear_selected_text()
        await self._scroll_to_end()

    def _conversation(self) -> VerticalScroll:
        return self.query_one("#conversation", VerticalScroll)

    def _append_user_message(self, text: str) -> None:
        self._conversation().mount(Static(f"dk>: {text}", classes="user-message"))

    def _append_agent_reply(self, response: AgentResponse) -> None:
        conv = self._conversation()
        conv.mount(Static("Agent:", classes="agent-label"))
        meta = (
            f"Tokens: {self._format_tokens(response.usage)} | "
            f"Route: {response.route} | "
            f"Role: {response.model_role} | "
            f"Reasoning: {response.reasoning_profile} | "
            f"Model: {response.model_name} | "
            f"Time: {response.elapsed_seconds:.2f}s\n"
            f"Web: off | "
            f"Tools: {self._format_capabilities(response.tools)} | "
            f"Skills: {self._format_capabilities(response.skills)} | "
            f"Verifiers: {self._format_capabilities(response.verifiers)}\n"
            "Meta: medium | "
            f"Clarification: {'pending' if response.pending_clarification else 'off'}"
        )
        conv.mount(Static(meta, classes="agent-meta"))
        conv.mount(Static(response.reply_text, classes="agent-body"))

    def _append_help(self) -> None:
        help_text = (
            "可用命令：\n"
            "/help 或 /帮助  显示帮助\n"
            "/exit 或 /退出  退出 TUI\n\n"
            "当前阶段：V0.4 MetaController + Clarification Gate + DeepSeek direct executor。\n"
            "已接入：AgentRuntime、ModelGateway、MetaDecision、MetaController、PendingClarification。\n"
            "尚未接入：LangGraph、DeepAgents、LiteLLM、Tools、Web、Skills 执行、Memory、上下文压缩、Judge 审查。"
        )
        self._conversation().mount(Static(help_text, classes="help-box"))

    def _append_system_message(self, text: str) -> None:
        self._conversation().mount(Static(text, classes="help-box"))

    async def _scroll_to_end(self) -> None:
        self._conversation().scroll_end(animate=False)


if __name__ == "__main__":
    DkAgentTUI().run()
