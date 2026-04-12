# GPT Decision Output Contract

To ensure the automation pipeline can ingest your decisions cleanly, you **MUST** provide your output using the single standard format described below.

## 1. Required Output Format

Your entire response must be structured exactly as follows:

DECISION_JSON_BEGIN
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
DECISION_JSON_END

## 2. Formatting Rules & Prohibitions

1. **One Single JSON**: The output must contain one and only one JSON block between the `DECISION_JSON_BEGIN` and `DECISION_JSON_END` markers.
2. **Top-level Object**: The JSON itself must be a single top-level object (`{...}`).
3. **No Outer Text**: Do NOT include any introductory prose, explanations, or conclusions outside the markers.
4. **No Inner Text**: Do NOT include any comments (e.g. `// comment`), trailing commas, or explanatory text inside the JSON code block.
5. **Clean Strings**: Ensure all text inside the JSON is clean and free of polling markers or citation references (e.g., avoid `:contentReference[...]`).
6. **Round ID Mapping**: Using `"round_id": "round_xxxx"` is perfectly acceptable and expected, as the ingestion layer will replace it with the correct ID.
