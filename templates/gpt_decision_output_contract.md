# GPT Decision Output Contract

To ensure the automation pipeline can ingest your decisions, please follow this response format.

## 1. Response Structure

1. **Reasoning**: Provide a brief explanation of your analysis and the reasoning behind your decisions.
2. **Marker**: The literal string `DECISION_JSON_BEGIN` on a new line.
3. **JSON Block**: A single JSON code block containing the `gpt_decision.json` content.
4. **Marker**: The literal string `DECISION_JSON_END` on a new line.

Example:
Reasoning: I am adjusting parameters to improve exploration based on the recent logs.

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
      "name": "revisit_penalty",
      "old_value": 0.1,
      "new_value": 0.12,
      "delta": 0.02,
      "reason": "Slight increase to encourage exploring new states."
    }
  ],
  "codex_analysis_focus": {
    "compare_targets": ["previous_round_run", "best_known_reference"],
    "required_logs": ["logs/train_steps.csv", "logs/eval_metrics.csv"],
    "required_plots": ["plots/reward_curve.png", "plots/coverage_curve.png"],
    "questions": ["Is the agent discovering significantly more unique tiles?"],
    "expected_output_style": "Write a structured markdown report for GPT using the codex_report.md sections."
  },
  "reference_targets": {
    "best_known_reference": "outputs/baseline_run",
    "manual_compare_targets": []
  },
  "controller_notes": "Experimenting with revisit penalty impact on exploration."
}
```
DECISION_JSON_END

## 2. JSON Schema Requirements

1. **Schema Compliance**: All required fields must be present.
2. **Round ID**: Use `"round_xxxx"` for the `round_id` field. The system will automatically resolve this to the correct next round ID.
3. **Field Types**: Ensure numeric fields are numbers, and lists are arrays.
4. **Decision Status**: Use `"run_next_round"` to continue, `"hold"` to pause, or `"stop"` to terminate.
