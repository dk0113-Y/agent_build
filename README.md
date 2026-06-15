# lg-deepagent

`lg-deepagent` is a Python prototype for a terminal-based AI assistant. It focuses on a layered TUI + runtime architecture: Textual renders the chat interface, `AgentRuntime` owns the execution entrypoint, a MetaController decides whether a request can be answered directly or needs clarification, and a DeepSeek-backed executor produces the final response.

The repository is positioned as an internship portfolio project for AI agent application engineering, especially around LLM routing, LangGraph control flow, TUI interaction, and testable runtime boundaries.

## Project Background and Goals

This project explores how to move a simple terminal chatbot toward an agent-style architecture without hiding everything inside the UI layer.

Design goals visible in the current codebase:

- Keep the Textual TUI thin: UI code does not import `ChatDeepSeek`, the concrete model name, or `DEEPSEEK_API_KEY`.
- Route every request through a MetaController before execution.
- Stop ambiguous or high-privilege requests at a clarification gate instead of executing them directly.
- Support follow-up questions about text selected from previous agent replies.
- Keep the prototype easy to test with fake gateways and fake executors.

## Technology Stack

- Python 3.12 style codebase
- Textual and Rich for the terminal UI
- LangGraph for the runtime graph, interrupt, resume, and in-memory checkpoint flow
- Pydantic for strict MetaController decision schema validation
- LangChain DeepSeek integration through `langchain_deepseek.ChatDeepSeek`
- `unittest` for the current test suite

There is currently no `pyproject.toml`, `requirements.txt`, or lockfile in this repository. The dependency list above is inferred from imports in `src/` and `tests/`.

## Core Features

- Terminal chat UI with a top bar, scrollable conversation area, input box, and metadata display.
- Direct DeepSeek chat path through `DeepSeekClient`.
- MetaController that asks the LLM to return strict JSON for routing, risk, clarification, role, reasoning profile, skills, and verifier planning.
- LangGraph flow: `meta -> clarification` for ambiguous or high-privilege requests, and `meta -> execute -> response` for clear answer-only requests.
- Clarification resume flow using LangGraph `Command(resume=...)` and per-thread state.
- Selected-text question mode: only selected text from agent reply bodies is accepted.
- Markdown-to-visible-text rendering helper for headings, bold text, bullets, and backticks.
- Missing API key fallback that returns a readable error instead of crashing.

## System Structure

```text
.
+-- src/
|   `-- dk_agent/
|       +-- app/
|       |   `-- tui_app.py              # Textual UI and selected-text interaction
|       +-- core/
|       |   +-- runtime.py              # AgentRuntime entrypoint
|       |   +-- session_state.py        # Pending clarification state
|       |   `-- types.py                # AgentRequest / AgentResponse dataclasses
|       +-- executor/
|       |   `-- direct_executor.py      # Builds messages and calls the model gateway
|       +-- graph/
|       |   +-- graph.py                # LangGraph StateGraph wiring
|       |   +-- nodes.py                # Meta, clarification, execute, response nodes
|       |   +-- routing.py              # Clarification/execute routing policy
|       |   +-- runner.py               # Graph runner and interrupt/resume handling
|       |   `-- state.py                # Graph state schema
|       +-- llm/
|       |   +-- deepseek_client.py      # DeepSeek client wrapper
|       |   `-- gateway.py              # Gateway protocol and LLM result type
|       +-- prompts/
|       |   `-- meta_controller.md      # MetaController system prompt
|       `-- routing/
|           +-- meta_controller.py      # JSON parsing and fallback behavior
|           `-- meta_schema.py          # Pydantic MetaDecision schema
`-- tests/
    +-- test_graph_flow.py
    +-- test_graph_interrupt.py
    +-- test_graph_runner.py
    +-- test_meta_controller.py
    +-- test_meta_schema.py
    +-- test_runtime.py
    +-- test_runtime_clarification.py
    `-- test_tui_markdown.py
```

## Key Modules

### Textual TUI

`src/dk_agent/app/tui_app.py` defines `DkAgentTUI`. It handles user input, `/help`, `/exit`, selected-text mode via `Alt+Z`, metadata display, loading messages, and lightweight Markdown rendering for agent replies.

### Runtime Layer

`src/dk_agent/core/runtime.py` exposes `AgentRuntime` and `create_default_runtime()`. The runtime wires together the model gateway, MetaController, direct executor, and LangGraph runner so the UI only depends on a stable request/response interface.

### MetaController and Schema

`src/dk_agent/routing/meta_controller.py` calls the model gateway with `prompts/meta_controller.md`, extracts strict JSON, validates it with `MetaDecision`, and falls back to a conservative default when parsing fails. `meta_schema.py` restricts allowed roles, autonomy modes, tools, skills, verifiers, and risk levels.

### LangGraph Flow

`src/dk_agent/graph/graph.py` builds the graph. `routing.py` sends requests to clarification when the MetaDecision requests clarification, requires human approval, or asks for high-privilege autonomy modes such as file edits or command execution. `runner.py` manages thread IDs, interrupt payloads, resume calls, and pending clarification state.

### DeepSeek Gateway

`src/dk_agent/llm/deepseek_client.py` reads `DEEPSEEK_API_KEY` from the environment, calls `ChatDeepSeek`, normalizes response content and usage metadata, and returns structured errors for missing keys or invocation failures.

## What I Built

- Refactored the assistant into explicit UI, runtime, graph, executor, routing, and LLM gateway boundaries.
- Added a MetaController path that validates structured routing decisions instead of letting the UI call the model directly.
- Implemented a clarification gate for ambiguous or high-risk requests using LangGraph interrupt/resume state.
- Added selected-text follow-up behavior in the TUI while keeping model-specific details below the UI layer.
- Built unit tests around runtime behavior, graph routing, schema validation, missing API key handling, and Markdown rendering.

## Quick Start

From the repository root:

```bash
export PYTHONPATH=src
export DEEPSEEK_API_KEY="your_api_key_here"
python -m dk_agent.app.tui_app
```

If you use the existing local virtual environment in this checkout:

```bash
PYTHONPATH=src ./.venv/bin/python -m dk_agent.app.tui_app
```

For a fresh environment, install the imports used by the current code before running:

```bash
python -m pip install textual rich langgraph pydantic langchain-deepseek
```

Do not commit `.env` files or real API keys. The code expects secrets to come from environment variables.

## Testing

Run the current test suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Or with the local virtual environment:

```bash
PYTHONPATH=src ./.venv/bin/python -m unittest discover -s tests
```

The tests use fake gateways and fake executors for most flows, so they do not require live DeepSeek access. The missing-key branch is covered explicitly.

## Current Status and Limitations

- Implemented: layered TUI/runtime/LLM boundaries, MetaController JSON schema, LangGraph clarification gate, selected-text question flow, and unit tests for core runtime behavior.
- Not implemented: real tool execution, web access, memory, DeepAgents integration, LiteLLM routing, judge model verification, context compression, and production packaging.
- No dependency manifest is currently committed, so setup is manual.
- Live DeepSeek success depends on a valid `DEEPSEEK_API_KEY` and network access; the automated tests do not prove live model availability.
- Some Chinese UI strings in `tui_app.py` appear as mojibake in the current source display. This README documents the issue but does not change UI behavior.
- `.env` is ignored by `.gitignore`, but local secret files still need to be kept out of commits and screenshots.

## Internship Skill Mapping

- AI Agent architecture: separates UI, runtime, routing, graph control flow, executor, and LLM gateway instead of coupling model calls directly to the TUI.
- LangGraph: uses `StateGraph`, conditional routing, interrupt payloads, resume commands, and thread-scoped checkpoint state.
- LLM routing and safety: validates MetaController decisions with Pydantic and blocks unclear or high-privilege requests at a clarification gate.
- Tooling boundary design: exposes `tools`, `skills`, and `verifiers` in response metadata while keeping unsupported capabilities disabled in V0.4.
- Terminal UX engineering: builds a Textual chat interface with scroll handling, command handling, selected-text interactions, and reply metadata.
- Testability: uses protocol-style gateways and fake controllers/executors to test graph, runtime, schema, and rendering behavior without relying on live API calls.
