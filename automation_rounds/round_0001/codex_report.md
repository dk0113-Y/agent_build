# Codex Report

## 1. Scope And Evidence

- Round id: `round_0001`
- Experiment mode: `formal_train`
- Target run: `outputs/sched_turn003_revisit010_entry8_20260411_014043`
- Primary baseline: `outputs/sched_turn005_revisit010_entry8_20260410_234142`
- Secondary compare runs:
  - `outputs/sched_turn007_revisit010_entry8_20260410_214225`
  - `outputs/s5_advtraj10_turn007_entry8_20260410_175445`
- Primary evidence:
  - round-local `comparability_report.json`, `round_summary.json`, `metric_snapshot.json`, `benchmark_summary.json`, `config_snapshot.json`
  - source-run `logs/eval_metrics.csv` and `logs/final_probe.csv` for all four runs

All four runs have the required formal JSON artifacts and the required CSV files. Final metric values below were checked against both `metric_snapshot.json` and the original CSV rows.

## 2. Comparability Gate

- Comparability status: `bootstrap_comparable`
- Decision zone: `manual_review_required`
- Recommended controller action from the current formal bundle: `pause_for_manual_review`
- Why bootstrap-only:
  - all four runs are backfilled historical runs
  - `comparability_report.json` confirms matching comparability group, matching CSV headers, and matching `final_env_steps=300000`
  - the same report also flags missing full train config recovery, so the runs are not promoted to fully comparable
- Efficiency limit:
  - all four `benchmark_summary.json` files mark runtime/timing as unavailable
  - the only usable efficiency signal is `env_steps_to_best`

This means the ranking below is useful for choosing the next attempt, but any parameter recommendation must stay provisional.

## 3. Four-Run Metric Table

### Final Probe

| run | success_rate | coverage | reward | episode_length | repeat_visit_ratio | timeout_flag | stall_trigger_count | zero_info_step_count | env_steps_to_best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `sched_turn005_revisit010_entry8_20260410_234142` | 0.8750 | 0.9108 | 120.7926 | 337.6875 | 0.2271 | 0.1250 | 111.6875 | 172.7500 | 288000 |
| `s5_advtraj10_turn007_entry8_20260410_175445` | 0.5625 | 0.9149 | 92.3653 | 472.3125 | 0.2719 | 0.4375 | 229.7500 | 301.3750 | 288000 |
| `sched_turn007_revisit010_entry8_20260410_214225` | 0.6250 | 0.8855 | 83.5029 | 480.0000 | 0.3168 | 0.3750 | 241.3750 | 312.2500 | 300000 |
| `sched_turn003_revisit010_entry8_20260411_014043` | 0.5625 | 0.8924 | 88.3039 | 479.7500 | 0.3229 | 0.4375 | 238.4375 | 313.1250 | 288000 |

### Best Eval And Last Eval

| run | best_eval success / coverage / reward | last_eval success / coverage / reward | readout |
| --- | --- | --- | --- |
| `sched_turn005_revisit010_entry8_20260410_234142` | 0.5833 / 0.8778 / 85.2031 | 0.5833 / 0.8749 / 92.0689 | peak is modest, but final probe is much stronger than both eval snapshots |
| `s5_advtraj10_turn007_entry8_20260410_175445` | 0.4167 / 0.9138 / 78.5878 | 0.4167 / 0.8614 / 58.2689 | eval-side success is weak, but final probe recovers meaningfully |
| `sched_turn007_revisit010_entry8_20260410_214225` | 0.6667 / 0.9409 / 106.1004 | 0.6667 / 0.9409 / 106.1004 | strongest eval snapshot outside baseline, but final probe degrades sharply |
| `sched_turn003_revisit010_entry8_20260411_014043` | 0.5833 / 0.9239 / 102.2118 | 0.3333 / 0.8287 / 56.1062 | strong periodic checkpoint, then large final-eval collapse, then only partial final-probe recovery |

## 4. Run Ranking

### 1) `sched_turn005_revisit010_entry8_20260410_234142` is the strongest overall

Why it wins:

- best final-probe success rate by a large margin: `0.875`
- best final-probe reward: `120.7926`
- lowest final-probe episode length: `337.6875`
- lowest revisit, timeout, stall, and zero-info burden in the four-run set
- reaches its best checkpoint by `288000` env steps, so it is not slower than the others on the one efficiency signal that exists

This is the only run that is simultaneously strong on task quality and clearly better on stability-style metrics.

### 2) `s5_advtraj10_turn007_entry8_20260410_175445` is the second-best practical reference

Why it ranks above the other non-baseline runs:

- best final-probe coverage in the four-run set: `0.9149`
- higher final-probe reward than both `sched_turn007...` and the target run
- materially lower revisit, stall, and zero-info counts than `sched_turn007...` and the target run

Its limit is success: final-probe success stays at `0.5625`, far below the baseline's `0.875`.

### 3) `sched_turn007_revisit010_entry8_20260410_214225` is high-peak but unstable

Why it does not beat the baseline:

- it posts the best non-baseline eval snapshot at the end of training: last eval is `0.6667` success, `0.9409` coverage, `106.1004` reward
- but final probe falls to `0.6250` success, `0.8855` coverage, `83.5029` reward
- revisit and stall burden remain high at final probe: `0.3168` repeat-visit ratio, `241.375` stalls

The run looks attractive if one only reads the last eval row, but it is not the strongest choice after the final probe is considered.

### 4) `sched_turn003_revisit010_entry8_20260411_014043` is the weakest current anchor

Why it ranks last:

- final-probe success is only `0.5625`
- final-probe reward and coverage both trail the baseline
- final-probe repeat-visit ratio is the worst of the four runs: `0.3229`
- final-probe zero-info burden is also the worst: `313.125`
- last eval collapses hardest of the set: `0.3333` success, `0.8287` coverage, `56.1062` reward

The target run does show one positive sign: its best periodic checkpoint is strong (`0.5833` success, `0.9239` coverage, `102.2118` reward at `288000`), which means the run can reach a useful region. The problem is that it does not hold that level through the end-of-run and final-probe checks.

## 5. Target Run Against The Other Three

### Versus the primary baseline

The target loses on every key final-probe field that matters for formal judgment:

- success: `0.5625` vs `0.8750`
- coverage: `0.8924` vs `0.9108`
- reward: `88.3039` vs `120.7926`
- episode length: `479.75` vs `337.6875`
- repeat-visit ratio: `0.3229` vs `0.2271`
- timeout flag: `0.4375` vs `0.1250`

This is a clear regression relative to the primary baseline.

### Versus `sched_turn007_revisit010_entry8_20260410_214225`

The comparison is mixed:

- target has slightly better final-probe coverage and reward
- `sched_turn007...` has better final-probe success, better revisit ratio, and lower timeout
- `sched_turn007...` also has a much stronger last eval

Net result: the target is not a clear improvement over the plain `turn007` variant; it simply fails in a different way.

### Versus `s5_advtraj10_turn007_entry8_20260410_175445`

The target loses the cleaner final-probe comparison:

- same success rate: `0.5625`
- lower coverage: `0.8924` vs `0.9149`
- lower reward: `88.3039` vs `92.3653`
- worse revisit ratio: `0.3229` vs `0.2719`
- identical timeout flag: `0.4375`

This means the target is not the best non-baseline direction either.

## 6. Parameter Direction For The Next Round

## Most Worth Trying First

The next formal round should anchor around the winning run label `sched_turn005_revisit010_entry8_20260410_234142`.

Practical reading of the current four-run sweep:

- `revisit010` and `entry8` are held constant across the clean `sched_turn003/005/007` trio
- the strongest result sits at `turn005`
- moving to `turn003` hurts both quality and stability
- moving to `turn007` preserves strong eval snapshots but does not survive final probe well enough

So the best next step is a narrow local search around the `turn005` setting rather than another large move to either side.

## What Not To Change First

- Do not make `turn003` the next anchor; it is already the weakest result in this four-run set.
- Do not treat `turn007` as the next formal default; its last eval is attractive, but its final probe does not support promotion.
- Do not change `revisit010` or `entry8` first if the goal is to confirm the best local direction, because the cleanest three-run comparison already isolates the strongest point at `turn005`.
- Do not combine multiple extra modifiers in the first confirmation run. The `s5_advtraj10_turn007...` result is informative, but because it changes more than the plain `sched_turn...` trio, it is weaker as a first attribution target.

## 7. Limits And Open Constraints

- Full train configs are not recoverable for these historical backfilled runs, so exact parameter semantics beyond the run-name labels remain partially inferred rather than formally recovered from config.
- Runtime/timing is unavailable in all four `benchmark_summary.json` files, so wall-clock efficiency cannot be ranked.
- The four runs are only `bootstrap_comparable`, not fully comparable. That is strong enough for triage and hypothesis selection, but not strong enough for a hard promotion claim.

## 8. Bottom Line

- Best overall run: `sched_turn005_revisit010_entry8_20260410_234142`
- Target run status: not promotable; it is weaker than the baseline and not clearly better than either secondary compare run
- Best next parameter direction: stay near the `turn005` setting and run a tighter local confirmation around that neighborhood
- Parameters not to move first: avoid jumping back to `turn003`, avoid treating `turn007` as the default, and keep `revisit010` plus `entry8` fixed for the next confirmation test
- Formal caveat: all of the above remains under bootstrap-only comparability and missing runtime metadata
