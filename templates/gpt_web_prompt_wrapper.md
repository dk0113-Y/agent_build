# ChatGPT Web Bridge Prompt Wrapper

Please analyze the following GPT Input Package and provide the next decision JSON.

IMPORTANT: Your response MUST follow this exact format:

1. A brief explanation of your reasoning.
2. The marker `DECISION_JSON_BEGIN`.
3. A single JSON code block containing the `gpt_decision.json` content.
4. The marker `DECISION_JSON_END`.

Example:
Reasoning: ...

DECISION_JSON_BEGIN
```json
{
  ...
}
```
DECISION_JSON_END

---
INPUT_PACKAGE_BEGIN
{{GPT_INPUT_CONTENT}}
INPUT_PACKAGE_END
