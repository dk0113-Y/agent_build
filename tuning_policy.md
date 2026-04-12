# Rehearsal Strategy and Control Plane Constraints

## 1. Purpose and Boundaries

This document defines the structured tuning template and constraints for the current local **bounded synthetic rehearsal**. It does not represent the final, optimal scientific DRL search strategy.

- `fake_train.py` parameters (`turn_penalty`, `revisit_penalty`, `entry_k`, `steps`, `sleep_sec`, `seed`) used in this rehearsal are simply **control variables to drive observable round changes**. They do not guarantee optimal real-world RL tuning trajectories.
- Current purpose is to ensure changes in parameters can be observed, evaluated by Codex, pushed to GPT, and returned correctly formatted for the next round.
- **Do not assume any hidden target values, explicit termination thresholds, or unwritten bounds.**
- The local execution controller handles stopping conditions independently. 

## 2. GPT's Parameter Search Philosophy

GPT must infer next steps **only from publicly shared round materials** (e.g., current metrics, previous deltas, plots, and codex validation files):

1. **Do not assume monotonic trends**: A parameter shouldn't blindly increase/decrease indefinitely. Analyze the actual effect seen between rounds.
2. **Prioritize small, interpretable adjustments**: Rather than jumping drastically, provide step-by-step local adjustments with explicit reasoning.
3. **Handle mixed signals conservatively**: Provide a conservative, smaller magnitude change (or even a zero-delta "hold") if recent improvements are insignificant, if reward/success signals conflict, or if public evidence does not clearly support a large jump.
4. **Hold state representation**: If evidence shows continuing the search offers diminishing returns, you may recommend no-change ("hold") values, though ultimate pipeline suspension is managed locally by the controller. 

## 3. Current Automation State

Please be aware of the strictly defined state of the automation loop:

- **Operationally Passing:** 
  - Standardizing local runs into requests.
  - Codex generating markdown reports.
  - Exporting packages to the `RRL_test` exchange repository.
  - GPT replies being mapped and ingested to spawn a new round directory.

- **Available but needing validation / Polish:** 
  - The comprehensive linkage to make the system loop fully unattended without manual trigger calls.
  - *Note: Previous statements claiming the bridge was strictly unidirectional (Codex only, no report read-back) are now obsolete. The system now includes bidirectional workflow for both metrics analysis and ingestion.*

- **Not Covered in Current Rehearsals:**
  - Automated modification of the underlying training codebase.
  - Executing full, authentic unconstrained hyperparameter sweeps for complex real-world agents.

## 4. Parameter Modifications

When proposing a parameter change in the output, you must:
1. Supply a valid parameter `name`, `old_value`, `new_value`, `delta`, and a clean, concise `reason` strictly tied to public analysis indicators.
2. Do not let the parameter changes cause schema failures. Keep data types consistent.
