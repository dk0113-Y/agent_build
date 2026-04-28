# Numbered Protocol Dry-Run Post-Patch Audit

## Scope

This audit only verifies the numbered-protocol `dry_run_no_train` P0 patch on `codex/numbered-protocol-dry-run`.

- No source code was modified.
- No training was launched.
- No merge was performed.
- No PR was created.
- No real `RRL_test/rounds/round_0002` was written.

## Commit Under Audit

- branch: `codex/numbered-protocol-dry-run`
- commit: `c3ad043468ed266e570867597aa1ae9c892c9c76`
- working tree status before audit: clean

## Static Checks

### `py_compile`

Command:

```powershell
python -m py_compile scheduler.py rrl_numbered_protocol.py prepare_numbered_dry_run.py
```

Result:

- passed

### Old Dependency Scan

Targeted scan files:

- `rrl_numbered_protocol.py`
- `prepare_numbered_dry_run.py`
- `scheduler.py`

Findings:

- `rrl_numbered_protocol.py` references numbered docs only:
  - `docs/00_gpt_entry_guide.md`
  - `docs/01_project_context.md`
  - `docs/02_system_architecture.md`
  - `docs/03_current_mainline.md`
  - `docs/04_automation_scope.md`
  - `docs/05_round_protocol.md`
  - `docs/06_formal_artifact_map.md`
  - `docs/07_tuning_policy.md`
  - `docs/08_evaluation_charter.md`
  - `docs/09_stopping_policy.md`
  - `docs/10_output_contract.md`
  - `docs/README.md`
- `rrl_numbered_protocol.py` does not depend on:
  - `gpt_index_guide.md`
  - `reading_order.md`
  - `next_gpt_decision.json`
  - `metric_snapshot.json`
  - `benchmark_summary.json`
  - `artifact_index.json`
  - `fake_train.py`
  - `train_q_agent.py`
  - `DRL-path-finding`
- `prepare_numbered_dry_run.py` does not depend on:
  - old docs names
  - `metric_snapshot.json`
  - `benchmark_summary.json`
  - `artifact_index.json`
  - `fake_train.py`
  - `train_q_agent.py`
  - `DRL-path-finding`
- `prepare_numbered_dry_run.py` only mentions `outbox` / `next_gpt_decision` as explicit negative markers:
  - `outbox_used: false`
  - `next_gpt_decision_used: false`
  - `outbox_created=false`
  - `next_gpt_decision_created=false`
- `scheduler.py` still contains legacy training paths and legacy formal artifact validation strings:
  - `fake_train.py`
  - `train_q_agent.py`
  - `metric_snapshot.json`
  - `benchmark_summary.json`
  - `artifact_index.json`
  - these belong to legacy rehearsal / formal paths, not to the numbered dry-run path

Legacy-only files still containing old dependencies:

- `automation_protocol.py`
- `exchange_protocol.py`
- `publish_round_to_exchange.py`
- `ingest_exchange_decision.py`
- `exchange_web_bridge.py`
- `extract_gpt_decision.py`
- `build_exchange_bundle.py`
- `formal_round_summary.py`

These legacy dependencies were not called by the audited numbered dry-run path.

### Scheduler Dry-Run Guard

Static finding:

- `scheduler.py` inspects `round_type` / `operating_mode` before `load_decision_file(...)` training resolution.
- If either equals `dry_run_no_train`, it returns:
  - `should_launch=False`
  - `exit_status="dry_run_no_train_blocked"`
- This blocks the training launcher before `launch_training_process(...)`.

## Fresh Dry-Run Generation

Command:

```powershell
python prepare_numbered_dry_run.py `
  --exchange-root C:\Users\Dk\Desktop\SCI\RRL_test `
  --staging-root C:\Users\Dk\AppData\Local\Temp\codex_numbered_dry_run_audit_20260428_184143 `
  --target-round-id round_0002 `
  --baseline-round-id round_0001 `
  --no-publish
```

Staging root:

- `C:\Users\Dk\AppData\Local\Temp\codex_numbered_dry_run_audit_20260428_184143`

Stdout / stderr summary:

- `status=staged`
- `round_dir=...\\rounds\\round_0002`
- `current_round=...\\CURRENT_ROUND.json`
- `training_launched=false`
- `checkpoint_copied=false`
- `outbox_created=false`
- `next_gpt_decision_created=false`
- `published_to_exchange=false`
- `baseline_round_id=round_0001`
- `preflight_status=passed`

Generated files:

- `CURRENT_ROUND.json`
- `rounds/round_0002/index_manifest.json`
- `rounds/round_0002/round_summary.json`
- `rounds/round_0002/artifact_digest.json`
- `rounds/round_0002/config_diff.json`
- `rounds/round_0002/comparability_report.json`
- `rounds/round_0002/gpt_decision_placeholder.json`

Absent forbidden files:

- no `rounds/round_0002/gpt_decision.json`
- no `rounds/round_0002/controller_action.json`
- no `rounds/round_0002/next_gpt_decision.json`
- no `outbox/`
- no `rounds/round_0002/checkpoints/`
- no `.pt`
- no `.pth`
- no `.ckpt`

## JSON Validation

### Parse Result

All of the following parsed successfully:

- `CURRENT_ROUND.json`
- `rounds/round_0002/index_manifest.json`
- `rounds/round_0002/round_summary.json`
- `rounds/round_0002/artifact_digest.json`
- `rounds/round_0002/config_diff.json`
- `rounds/round_0002/comparability_report.json`
- `rounds/round_0002/gpt_decision_placeholder.json`

### Key Field Checks

`round_summary.json`

- `round_type == "dry_run_no_train"`
- `operating_mode == "dry_run_no_train"`
- `training_launched == false`
- `checkpoint_copied == false`
- `outbox_used == false`
- `next_gpt_decision_used == false`
- `decision_required_from_gpt == false`
- `claim_boundary == ["protocol_review_only", "analysis_only"]`
- `evidence_condition == ["no formal training evidence", "no method-performance claim"]`

`artifact_digest.json`

- `dry_run == true`
- `artifacts == []`
- `copied_files == []`
- `skipped_large_or_binary_files == []`
- note explicitly states training artifacts are intentionally absent

`config_diff.json`

- `changed_fields == []`
- `unknown_fields_present == false`
- `frozen_field_violations == []`
- `manual_review_required == false`
- `preflight_status == "passed"`

`comparability_report.json`

- `comparability_status == "not_applicable"`
- `same_group_claim_allowed == false`
- `formal_improvement_claim_allowed == false`

`gpt_decision_placeholder.json`

- `schema_version == "output_contract_v1"`
- `decision_status == "not_requested"`
- no executable training instruction fields are present

`CURRENT_ROUND.json`

- includes:
  - `current_round_id`
  - `current_round_path`
  - `current_phase`
  - `status`
  - `baseline_run_name`
  - `next_expected_action`
  - `decision_required_from_gpt`

## Preflight Validation

Tested by directly calling `rrl_numbered_protocol.run_preflight(...)` without training.

### A. Empty Dry-Run Config

- input: `{}`
- mode: `dry_run_no_train`
- result: passed

### B. Unknown Field Fail-Closed

- input: `{"changes": {"unknown_param_x": 1}}`
- result:
  - `unknown_fields_present == true`
  - `preflight_status == "failed_closed"`
  - `blocked_reasons == ["unknown_fields_fail_closed"]`

### C. Frozen Field Fail-Closed

- input: `{"changes": {"state_tensor_schema": "changed"}}`
- result:
  - `frozen_field_violations == ["state tensor schema"]`
  - `preflight_status == "failed_closed"`
  - `blocked_reasons == ["frozen_field_violation_fail_closed"]`

### D. Manual-Review Field

- input: `{"changes": {"reward_coefficients": {"x": 1}}}`
- result:
  - `manual_review_required == true`
  - `preflight_status == "manual_review_required"`

### E. Runtime Toggle Deviation

- input: `{"runtime_toggles": {"amp": true}}`
- result:
  - `manual_review_required == true`
  - `preflight_status == "manual_review_required"`
  - `blocked_reasons == ["runtime_toggle_manual_review_required"]`

## Scheduler Fail-Closed Validation

Temporary decision file content:

```json
{
  "round_id": "round_0002",
  "round_type": "dry_run_no_train",
  "operating_mode": "dry_run_no_train",
  "decision_status": "not_requested"
}
```

Command:

```powershell
python scheduler.py --decision-file C:\Users\Dk\AppData\Local\Temp\scheduler_dry_run_decision_20260428_184228.json
```

Observed result:

- exit code: `0`
- stdout included:
  - `status=dry_run_no_train_blocked`
  - `bridge_status=skipped_dry_run_no_train_blocked`
- no new `outputs/` run directory was created
- no `fake_train.py` launch occurred
- no `train_q_agent.py` launch occurred

## RRL_test Pollution Check

Verified after audit:

- `C:\Users\Dk\Desktop\SCI\RRL_test\rounds\round_0002` does not exist
- `C:\Users\Dk\Desktop\SCI\RRL_test\outbox` does not exist
- no new `.pt` / `.pth` / `.ckpt` files were written under `RRL_test`

## Verdict

`p0_passed_with_minor_notes`

Minor notes:

- `scheduler.py` correctly blocks `dry_run_no_train` before training launch, but its blocked summary still prints a derived `codex_request_path` under the decision file's parent directory even though no such request file is generated in the blocked path.
- Legacy publish / exchange files still contain old docs names, outbox handling, and `next_gpt_decision.json` semantics. They are not active dependencies of the audited numbered dry-run path, but the codebase is still mixed-protocol overall.

## Remaining Work

P1

- Extend the numbered protocol beyond staging-only dry-run into numbered formal publication and numbered decision-ingest flow.
- Add automated tests for `prepare_numbered_dry_run.py`, `run_preflight(...)`, and `scheduler.py` dry-run blocking.

P2

- Refactor or retire legacy exchange helpers that still depend on old doc names, global outbox, and `next_gpt_decision.json`.
- Unify legacy `automation_rounds/` semantics with the numbered `rounds/` protocol model.
