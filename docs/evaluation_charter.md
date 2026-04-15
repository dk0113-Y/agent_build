# Evaluation Charter

## Formal Acceptance Object

Current formal protocol: `formal_last_checkpoint_v2_1`.

Formal acceptance object:
- `checkpoints/last.pt`
- the held-out `final_probe` of that last checkpoint or the equivalent online-last network state

Formal acceptance does not use periodic eval or best-checkpoint selection.

## Automatic Tuning Ranking Basis

Automatic tuning ranking uses two evidence layers.

Final-network outcome:
- `success_rate`
- `coverage`
- `reward`
- `episode_length`
- `repeat_visit_ratio`

Training-dynamics quality:
- `recent_mean_reward`
- `recent_mean_coverage`
- `recent_success_rate`
- `recent_mean_episode_length`
- `recent_mean_repeat_visit_ratio`
- `growth_rate`
- `threshold_reach_steps`
- `late_stage_variance`
- `train_final_consistency`

Formal promotion or regression claims remain subordinate to `final_probe`.
Training dynamics are ranking, screening, and diagnostic support signals.

## Legacy Diagnostic Artifacts

Legacy diagnostic artifacts may still appear in historical rounds:
- `logs/eval_metrics.csv`
- `best_eval`
- `last_eval`
- `checkpoints/best.pt`

These artifacts are diagnostic-only under the current protocol and are not part of the new formal main flow.

## Comparability

Formal comparability for `formal_last_checkpoint_v2_1` is gated by:
- `evaluation_contract.protocol_revision`
- `comparability_group`
- `train_steps_header`
- `final_probe_header`
- `final_env_steps`
- full `config_snapshot`

`same_eval_metrics_header` is diagnostic-only in the last-checkpoint formal protocol family and must not decide v2.1 formal comparability.
