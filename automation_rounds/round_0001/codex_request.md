# Codex Analysis Request

## 1. Formal Round Scope

- Round id: `round_0001`
- Experiment mode: `formal_train`
- Source of truth repo: `dk0113-Y/DRL-path-finding`
- Local execution repo path: `C:\Users\Dk\Desktop\SCI\代码1`
- Comparability status from current bundle: `bootstrap_comparable`
- Decision zone from current bundle: `manual_review_required`

This round is a historical four-run analysis task. Do not limit the analysis to target vs primary baseline.

## 2. Four Runs That Must Be Compared Together

- Target run:
  - `C:\Users\Dk\Desktop\SCI\代码1\outputs\sched_turn003_revisit010_entry8_20260411_014043`
- Primary baseline run:
  - `C:\Users\Dk\Desktop\SCI\代码1\outputs\sched_turn005_revisit010_entry8_20260410_234142`
- Secondary compare run 1:
  - `C:\Users\Dk\Desktop\SCI\代码1\outputs\sched_turn007_revisit010_entry8_20260410_214225`
- Secondary compare run 2:
  - `C:\Users\Dk\Desktop\SCI\代码1\outputs\s5_advtraj10_turn007_entry8_20260410_175445`

## 3. Required Evidence Sources

Use the current round bundle plus the original run artifacts.

### Round-Local Structured Evidence

- `automation_rounds/round_0001/comparability_report.json`
- `automation_rounds/round_0001/round_summary.json`
- `automation_rounds/round_0001/metric_snapshot.json`
- `automation_rounds/round_0001/benchmark_summary.json`
- `automation_rounds/round_0001/config_snapshot.json`
- `automation_rounds/round_0001/artifact_index.json`
- `automation_rounds/round_0001/historical_baseline_summary.json`

### Original Run Evidence For All Four Runs

For each of the four run directories above, inspect:

- `logs/metric_snapshot.json`
- `logs/benchmark_summary.json`
- `logs/config_snapshot.json`
- `logs/artifact_index.json`
- `logs/eval_metrics.csv`
- `logs/final_probe.csv`
- `logs/train_steps.csv` if needed for clarification

Do not rely on summary text alone when the structured artifacts or CSV rows are available.

## 4. Required Analysis Tasks

1. Compare all four runs jointly, not just target vs primary baseline.
2. Treat formal artifacts and real CSV rows as the primary evidence layer.
3. Inspect `best_eval`, `last_eval`, and `final_probe` together for every run.
4. Focus on:
   - `success_rate`
   - `coverage`
   - `reward`
   - `repeat_visit_ratio`
   - `timeout_flag`
   - `stall_trigger_count`
   - `zero_info_step_count`
   - runtime / timing availability
   - `env_steps_to_best`
5. Keep the comparability gate explicit:
   - say whether conclusions are fully comparable or only bootstrap-comparable
   - keep the historical backfill limits visible

## 5. Questions The Report Must Answer

1. Across the four runs, which run is the strongest overall, and which evidence makes it strongest?
2. Relative to the other three runs, what are the target run's real strengths and real weaknesses?
3. Which next parameter direction is most worth trying first for the next formal round?
4. Which parameters or sweep directions should not be changed first?
5. Which statements remain limited by bootstrap comparability or missing runtime metadata?

## 6. Output Requirement

Write the final report to `automation_rounds/round_0001/codex_report.md`.

The report must:

- be evidence-grounded rather than template-like
- include all four runs
- support GPT in choosing the next parameter direction
- avoid any claim that exceeds the current bootstrap-only comparability status
