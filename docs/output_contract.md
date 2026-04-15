# Output Contract

## Formal Round Inputs

Current formal protocol revision: `formal_last_checkpoint_v2_1`.

For `formal_train`, the controller expects these required artifacts:
- `logs/train_steps.csv`
- `logs/train_episodes.csv`
- `logs/final_probe.csv`
- `logs/metric_snapshot.json`
- `logs/benchmark_summary.json`
- `logs/config_snapshot.json`
- `logs/artifact_index.json`
- `checkpoints/last.pt`

Optional legacy diagnostic artifacts:
- `logs/eval_metrics.csv`
- `checkpoints/best.pt`

Missing optional legacy diagnostics must not cause formal artifact validation failure.

## Metric Snapshot Expectations

New formal rounds should expose:
- `recent_train`
- `final_probe`
- `formal_final_object`
- `training_dynamics_summary`
- `train_final_consistency_summary`
- `recent_train_support_summary`

`best_eval` and `last_eval` may exist for historical compatibility, but v2.1 rounds should omit them unless a legacy diagnostic artifact is actually present.

## Round Summary Expectations

`round_summary.json` for current formal rounds must clearly separate:
- `final_probe_formal_summary`
- `training_dynamics_summary`
- `train_final_consistency_summary`

The controller must not describe the formal verdict as a legacy multi-artifact joint packet.

## GPT Decision Expectations

Formal GPT decisions should prioritize:
- comparability status
- final-probe formal verdicts
- training-dynamics quality
- train-final consistency
- explicit evidence gaps

If comparability fails or evidence is insufficient, the decision must not imply a positive formal improvement claim.
