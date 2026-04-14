# Codex Local Index

## Purpose

This file is the local file-map prompt for Codex.

- Build repo-role awareness before reading implementation details.
- Separate code facts from generated summaries and templates.
- Do not let exchange docs or old rehearsal files override local code truth.

## Three-Repo Roles

- `../代码1`
  - Formal training source of truth.
  - Read this repo when judging real training semantics, emitted artifacts, checkpoint rules, or run outputs.
- Current repo
  - Local control plane for round protocol, bundle construction, comparability, GPT packaging, and exchange publish.
- `../RRL_test`
  - Public exchange surface for GPT.
  - Read this repo to verify what GPT can see, not to replace local code facts.

## Priority Reads By Goal

### If You Need The Real Formal Training Path

Read these first:

- `../代码1/README.md`
  - Fast overview of the current mainline and emitted formal artifacts.
- `../代码1/train_q_agent.py`
  - Real training entry and run wiring, including `budget_mode`, episode-budget scheduling, fixed train episode seed controls, and optional strict reproducibility runtime guards.
- `../代码1/training/formal_artifacts.py`
  - Formal artifact emission contract, including episode-budget metadata and observed run contract fields.
- `../代码1/training/checkpointing.py`
  - `best.pt` / `last.pt` behavior and checkpoint rules.
- `../代码1/tools/backfill_formal_run_artifacts.py`
  - Historical formal backfill path.
- `../代码1/tools/generate_historical_baseline_summary.py`
  - Historical baseline summary generation.

### If You Need The Control-Plane Protocol

Read these first:

- `automation_protocol.py`
  - Round schema, state files, protocol validation, and GPT/Codex text plumbing.
- `comparability.py`
  - Formal comparability logic and observed-run-contract checks.
- `formal_round_summary.py`
  - Structured verdict synthesis and stop-window outputs.
- `build_exchange_bundle.py`
  - Local formal bundle construction from real run artifacts.
- `prepare_gpt_input.py`
  - GPT package generation from completed round artifacts.
- `publish_round_to_exchange.py`
  - Exchange publication and `CURRENT_ROUND.json` updates.
- `exchange_protocol.py`
  - Exchange-facing doc lists, empty-state payload, and publish metadata helpers.

### If You Need The Exchange Entry Surface

Read these first:

- `../RRL_test/CURRENT_ROUND.json`
  - Active-round pointer or clean waiting state.
- `../RRL_test/docs/gpt_index_guide.md`
  - GPT-side file map and evidence hierarchy.
- `../RRL_test/docs/reading_order.md`
  - GPT read sequence across docs and round evidence.
- `../RRL_test/docs/output_contract.md`
  - GPT output contract.

## File Role Boundaries

### Code Fact Sources

- `../代码1/train_q_agent.py`
- `../代码1/training/formal_artifacts.py`
- `../代码1/training/checkpointing.py`
- `automation_protocol.py`
- `comparability.py`
- `formal_round_summary.py`
- `build_exchange_bundle.py`
- `prepare_gpt_input.py`
- `publish_round_to_exchange.py`
- `exchange_protocol.py`

These define behavior. If a README or generated summary disagrees with them, re-check the code.

README is not the only truth source, and it is never deeper than the implementation plus real run artifacts.

### Structured Summary Generators

- `formal_round_summary.py`
- `build_exchange_bundle.py`
- `prepare_gpt_input.py`
- `../代码1/tools/backfill_formal_run_artifacts.py`
- `../代码1/tools/generate_historical_baseline_summary.py`

These generate structured artifacts or packaged views. Read them to understand how summaries are produced.

### Templates

- `templates/`

Templates are not formal fact sources. They help bootstrap files but do not define the current formal truth.

### Runtime Round Files

- `automation_rounds/<round_id>/gpt_decision.json`
- `automation_rounds/<round_id>/round_state.json`
- `automation_rounds/<round_id>/comparability_report.json`
- `automation_rounds/<round_id>/round_summary.json`
- `automation_rounds/<round_id>/metric_snapshot.json`
- `automation_rounds/<round_id>/benchmark_summary.json`
- `automation_rounds/<round_id>/config_snapshot.json`
- `automation_rounds/<round_id>/artifact_index.json`
- `automation_rounds/<round_id>/historical_baseline_summary.json`
- `automation_rounds/<round_id>/codex_report.md`
- `automation_rounds/<round_id>/gpt_input.md`

These are round-level outputs. They are evidence for that round, but generated text files inside them are not deeper than the structured JSON layer.

For formal judgement, prioritize the real run artifacts and the code that emitted them.

### Long-Term Docs

- `README.md`
- `docs/codex_local_index.md`
- `../RRL_test/docs/*.md`
- `../代码1/README.md`

These are maps and contracts. They should guide reading, not replace implementation facts.

### Legacy Demo Or Rehearsal Compatibility Layer

- `fake_train.py`
- `run_rehearsal_loop.py`
- GUI bridge and rehearsal support files
- `rehearsal_summary.json`

These exist for compatibility or bridge validation. They are not the source for `formal_train` conclusions.

## Task-Oriented Reading Paths

### Protocol Consistency Check

Read:

- `automation_protocol.py`
- `formal_round_summary.py`
- `exchange_protocol.py`
- `../RRL_test/docs/gpt_index_guide.md`
- `../RRL_test/docs/output_contract.md`

Goal: confirm schema, decision fields, and exchange-facing contracts line up.

### Comparability Logic Check

Read:

- `comparability.py`
- `formal_round_summary.py`
- `../代码1/training/formal_artifacts.py`
- `../代码1/tools/generate_historical_baseline_summary.py`

Goal: confirm comparability uses emitted run contract fields rather than README-level assumptions.

### Publish Logic Check

Read:

- `publish_round_to_exchange.py`
- `exchange_protocol.py`
- `build_exchange_bundle.py`
- `../RRL_test/CURRENT_ROUND.json`

Goal: confirm exported files, manifest fields, entry docs, and exchange anchor semantics.

### Formal Artifact Contract Check

Read:

- `../代码1/training/formal_artifacts.py`
- `../代码1/training/checkpointing.py`
- `../代码1/train_q_agent.py`
- `comparability.py`
- `build_exchange_bundle.py`

Goal: confirm local run artifacts, checkpoint rules, episode-budget metadata, and bundle expectations match.

### Docs-Implementation Drift Check

Read:

- `docs/codex_local_index.md`
- `README.md`
- `exchange_protocol.py`
- `../RRL_test/docs/gpt_index_guide.md`
- `../RRL_test/docs/reading_order.md`
- The implementation files named by the docs

Goal: confirm the entry docs still describe the current code paths and artifact roles.

## Before Editing vs Before Reviewing

Before editing implementation:

- Read the local code fact source for that feature.
- Read the upstream truth repo file if the feature touches real training semantics.
- Then read the relevant round or exchange files.

Before reviewing or auditing outputs:

- Read `comparability.py` and `formal_round_summary.py` first for judgement logic.
- Read the structured JSON artifacts next.
- Read `codex_report.md` and `gpt_input.md` last.

## Do Not Misuse These Files

- Do not treat rehearsal demos as `formal_train` evidence.
- Do not treat exchange docs as substitutes for local code truth.
- Do not skip `../代码1/training/formal_artifacts.py` and `comparability.py` and then conclude from README text alone.
- Do not treat README text as sufficient when the implementation or emitted artifacts say more.
- Do not use `templates/` as formal behavior evidence.
- Do not use `codex_report.md` or `gpt_input.md` as deeper truth than the structured JSON artifacts.
- Do not use stale old-round files to make a current formal judgement.
