# repro_check_0001 Reproducibility Validation

## Scope

This directory is a local reproducibility check, not a published formal mainline round.
It exists to verify that the new `budget_mode=episodes` and fixed train-episode seed flow actually bind the same train episode index to the same map across repeated runs.

## Validation Config

- Decision files:
  - `automation_rounds/repro_check_0001/run_a_gpt_decision.json`
  - `automation_rounds/repro_check_0001/run_b_gpt_decision.json`
- Shared training config:
  - `budget_mode = "episodes"`
  - `total_train_episodes = 20`
  - `warmup_episodes = 2`
  - `eval_interval_episodes = 5`
  - `log_interval_episodes = 5`
  - `train_print_interval_episodes = 5`
  - `use_fixed_train_episode_seeds = true`
  - `fixed_train_episode_seed_base = 20259323`
  - `use_fixed_eval_seeds = true`
  - `fixed_eval_seed_base = 20260323`
  - `fixed_final_probe_seed_base = 20261323`
  - `strict_reproducibility = false`
  - `max_episode_steps = 600`
- Validation-only guardrail:
  - `min_replay_size = 1000000`

The high `min_replay_size` was intentional for this short validation.
It keeps learner updates at `0` so the run can isolate train-map reproducibility without modifying training code or letting the current learner runtime issue dominate the result.

## Real Run Directories

- Run A: `C:\Users\Dk\Desktop\SCI\代码1\outputs\repro_check0001_episode20_run_a_20260414_175615`
- Run B: `C:\Users\Dk\Desktop\SCI\代码1\outputs\repro_check0001_episode20_run_b_20260414_180647`

Both runs completed successfully and produced the expected formal artifacts:

- `logs/train_episodes.csv`
- `logs/train_steps.csv`
- `logs/eval_metrics.csv`
- `logs/final_probe.csv`
- `logs/metric_snapshot.json`
- `logs/benchmark_summary.json`
- `logs/config_snapshot.json`
- `logs/artifact_index.json`
- `checkpoints/best.pt`
- `checkpoints/last.pt`

## Episode-Level Alignment Result

Comparison basis:

- file: `logs/train_episodes.csv`
- filtered rows: `phase == "train"`
- compared fields:
  - `train_episode_idx`
  - `episode_seed`
  - `map_fingerprint`

Result:

- train rows in Run A: `20`
- train rows in Run B: `20`
- mismatched rows on `train_episode_idx / episode_seed / map_fingerprint`: `0`

Because `warmup_episodes = 2`, the first train-phase row starts at `train_episode_idx = 3`.
That is expected: seeds `20259323` and `20259324` are consumed by warmup, and the first formal train episode uses seed `20259325`.

Sample aligned rows:

| train_episode_idx | episode_seed | map_fingerprint |
| --- | --- | --- |
| 3 | 20259325 | `12693710fe5d6ecb` |
| 4 | 20259326 | `47f6cbeced187cd7` |
| 5 | 20259327 | `a560fb273fc1d0ba` |
| 6 | 20259328 | `49b9ba9c4fd7ad56` |
| 7 | 20259329 | `26e286ae7b61746e` |
| 8 | 20259330 | `cdd2adbe337421df` |
| 9 | 20259331 | `3ff58dfb88f979c2` |
| 10 | 20259332 | `219941c069e46dba` |

Conclusion:

- Same `train_episode_idx` mapped to the same `episode_seed` in both runs.
- Same `train_episode_idx` mapped to the same `map_fingerprint` in both runs.
- This is direct evidence that the train-map stream is now reproducible at the episode level.

## Artifact-Level Sanity Check

The paired runs also agreed on the high-level validation summary:

- `budget_mode = episodes`
- `final_train_episode_idx = 20`
- `final_env_steps = 13200`
- `best_checkpoint_train_episode_idx = 5`
- `last_checkpoint_train_episode_idx = 20`
- `learner_steps = 0`

Eval/final-probe summaries also matched in this validation pair.
That is expected here because the run intentionally avoided learner updates.

## Interpretation

What this validation proves:

- The episode-budget path works end-to-end through scheduler execution and formal artifact generation.
- `train_episodes.csv` now exposes the audit fields needed for reproducibility checks:
  - `train_episode_idx`
  - `episode_seed`
  - `map_fingerprint`
- Repeated runs with the same fixed train-episode seed configuration now consume the same train map sequence.

What this validation does not prove:

- It does not yet prove strict learner-path determinism under active updates.
- It does not yet isolate CUDA or optimizer-path nondeterminism, because this short check was run on CPU and held learner updates at zero.

## Remaining Nondeterminism Sources

If a future paired run keeps `episode_seed` and `map_fingerprint` aligned but still diverges in final reward, eval, or final probe, the remaining sources are more likely to be:

- learner update order and floating-point accumulation
- CUDA backend kernel selection and TF32 / cuDNN behavior
- replay sampling or other runtime-side nondeterministic execution paths

Those would be runtime/learner effects, not train-map-stream drift.

## Recommendation

- For the mainline search path, it is reasonable to keep `strict_reproducibility = false` for now.
- If you want a second reproducibility check, do it as a separate A/B validation focused on runtime determinism:
  - keep the same episode-seed configuration
  - re-enable actual learner updates
  - compare `strict_reproducibility = false` vs `true`

This `repro_check_0001` result is already strong enough to say the episode-level train-map reproducibility change is functioning as intended.
