# GPT Input Package

## 1. Current Round Basics
- Round id: `round_0001`
- Experiment mode: `formal_train`
- Source of truth repo: `dk0113-Y/DRL-path-finding`
- Local execution repo path: `C:\Users\Dk\Desktop\SCI\代码1`
- Round state status: `success`
- Run directory: `outputs/sched_turn003_revisit010_entry8_20260411_014043`
- Target program: `train_q_agent.py`

## 2. Comparability
- Comparability status: `bootstrap_comparable`
- Comparability group: `formal_mainline_v1__bf21a9e8fbc5`
- Baseline round id: `round_hist_ref`
- Baseline commit sha: `11f198a74d66f6984eaf0e5742bd2761273a4547`
- Checks: `{'baseline_available': True, 'same_comparability_group': True, 'same_train_steps_header': True, 'same_eval_metrics_header': True, 'same_final_probe_header': True, 'same_final_env_steps': True, 'target_has_full_config_snapshot': False, 'baseline_has_full_config_snapshot': False}`
- Historical calibration: `available=True, insufficient_history_for_calibration=True`

## 3. Metric Verdict Layer
- Primary verdict: `regression`
- Secondary verdict: `regression`
- Stability verdict: `regression`
- Efficiency verdict: `hold`
- Overall verdict: `regression`

## 4. Best Eval / Last Eval / Final Probe
- best_eval: `{'reward': 102.2117919921875, 'coverage': 0.9238999485969543, 'success_rate': 0.5833333134651184, 'episode_length': 430.25, 'repeat_visit_ratio': 0.3171675503253937}`
- last_eval: `{'reward': 56.10621643066406, 'coverage': 0.8287083506584167, 'success_rate': 0.3333333432674408, 'episode_length': 530.4166870117188, 'repeat_visit_ratio': 0.41566702723503113}`
- final_probe: `{'reward': 88.30387115478516, 'coverage': 0.8923500180244446, 'success_rate': 0.5625, 'episode_length': 479.75, 'repeat_visit_ratio': 0.32285091280937195}`
- benchmark_summary: `runtime=None, env_steps_to_best=288000`

## 5. Stop Window
- decision_zone: `manual_review_required`
- recommended_action: `pause_for_manual_review`
- plateau_detected: `False`
- manual_review_required: `True`
- reasons: historical_thresholds_are_bootstrap_only, net_regression_detected, comparability_only_bootstrap_confirmed, runtime_summary_missing, backfilled_from_historical_run, train_config_unavailable_in_backfill_context, timing_summary_unavailable, total_runtime_unavailable, complete_train_config_not_recoverable_without_checkpoint_loader, train_config_unavailable, bootstrap_thresholds_required, historical_thresholds_bootstrap_only

## 6. Manual Review / Evidence Gaps
- manual_review_reasons: comparability_only_bootstrap_confirmed, runtime_summary_missing
- insufficient_evidence_flags: backfilled_from_historical_run, train_config_unavailable_in_backfill_context, timing_summary_unavailable, total_runtime_unavailable, complete_train_config_not_recoverable_without_checkpoint_loader, train_config_unavailable, bootstrap_thresholds_required, historical_thresholds_bootstrap_only
- historical_baseline_summary: `path=historical_baseline_summary.json, run_count_total=19, insufficient_history_for_calibration=True`

## 7. What GPT Should Output
- Read `docs/reading_order.md`, `docs/current_mainline.md`, `docs/evaluation_charter.md`, and `docs/output_contract.md` before drafting the next decision.
- Any claim of improvement must remain subordinate to comparability. If comparability failed or evidence is insufficient, do not accumulate a positive formal conclusion.
- Output a single `next_gpt_decision.json` payload aligned with `docs/output_contract.md` and the dual-mode protocol schema.
