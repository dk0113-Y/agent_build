# GPT Decision Output Contract

To ensure the automation pipeline can ingest your decisions, please provide your output as a single, valid JSON object following the schema below.

## 1. Output Format Requirements

1. **Strict JSON**: The output must be a single JSON object. Do not include introductory prose, explanations, or markdown formatting outside the JSON block.
2. **Schema Compliance**: All required fields must be present.
3. **Field Types**: Ensure numeric fields are numbers, and lists are arrays.

## 2. Required JSON Structure

```json
{
  "schema_version": "1.0",
  "round_id": "round_xxxx",
  "decision_status": "run_next_round",
  "target_program": "fake_train.py",
  "run_args": {
    "turn_penalty": 0.03,
    "revisit_penalty": 0.1,
    "entry_k": 8,
    "steps": 24,
    "sleep_sec": 0.35,
    "seed": 7
  },
  "parameter_changes": [
    {
      "name": "parameter_name",
      "old_value": 0.0,
      "new_value": 0.0,
      "delta": 0.0,
      "reason": "Detailed explanation of why this change was made."
    }
  ],
  "codex_analysis_focus": {
    "compare_targets": ["previous_round_run", "best_known_reference"],
    "required_logs": ["logs/train_steps.csv", "logs/eval_metrics.csv"],
    "required_plots": ["plots/reward_curve.png", "plots/coverage_curve.png"],
    "questions": ["Specific question about the training results..."],
    "expected_output_style": "Write a structured markdown report for GPT using the codex_report.md sections."
  },
  "reference_targets": {
    "best_known_reference": "path/to/baseline/run",
    "manual_compare_targets": []
  },
  "controller_notes": "Summary of experimental intent."
}
```

## 3. Key Notes for GPT

- **`round_id`**: You can use a placeholder like `"round_xxxx"`. The ingestion tool will automatically replace it with the correct target round ID.
- **`decision_status`**: Use `"run_next_round"` to continue the experiment, `"hold"` to pause, or `"stop"` to terminate.
- **`parameter_changes`**: Every change must be documented with a reason. DO NOT skip this.
- **`codex_analysis_focus`**:
    - `compare_targets`: Use `"previous_round_run"` to compare with the last successful round.
    - `questions`: These will be passed directly to the Codex analyzer. Be specific.
- **`reference_targets`**: If you want to compare against a specific historical best run, provide its path in `best_known_reference`.
