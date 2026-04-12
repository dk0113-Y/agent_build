# Rehearsal Strategy and Control Plane Constraints

## 1. Purpose and Boundaries

This document defines the structured tuning template and constraints for the current local automation rehearsal. It does not represent the final, optimal scientific DRL search strategy.

- `fake_train.py` parameters (`turn_penalty`, `revisit_penalty`, `entry_k`, `steps`, `sleep_sec`, `seed`) used in this rehearsal are simply **control variables to drive observable round changes**. They do not guarantee optimal real-world RL tuning trajectories.
- Current purpose is to ensure changes in parameters can be observed, evaluated by Codex, pushed to GPT, and returned correctly formatted for the next round.

## 2. GPT's Responsibilities

GPT is responsible for reading the context of the current round and generating a valid, ingestible **next round decision JSON**.
GPT must ensure that the following fields in the JSON are reasonable, clean, and actionable based on the current context:
- `compare_targets`
- `questions`
- `controller_notes`

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
1. Supply a valid parameter `name`, `old_value`, `new_value`, `delta`, and a clean, concise `reason`.
2. Do not let the parameter changes cause schema failures. Keep data types consistent.
