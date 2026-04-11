# Tuning Policy Template

## 1. 目的与边界

这个文件只定义当前本地自动化 demo 的结构化调参模板与约束，不代表最终真实 RL 工程的科研策略已经确定。

当前用途：

- 说明 `gpt_decision.json` 中可用的控制面字段
- 说明 `reference_targets` 和 `round_state.json` 如何支持跨轮对比
- 说明这些字段应关联检查哪些 logs / plots
- 约束 GPT / scheduler / Codex 之间的文件握手

当前不包含：

- 最终真实训练系统的全部参数空间
- 已验证的最优策略结论
- 自动改代码或自动实验设计闭环

## 2. 当前自动化系统允许调整的参数

当前协议层只围绕 `fake_train.py` 已支持的参数：

- `turn_penalty`
- `revisit_penalty`
- `entry_k`
- `steps`
- `sleep_sec`
- `seed`

其中真正体现“调参含义”的主要是：

- `turn_penalty`
- `revisit_penalty`
- `entry_k`

其余字段当前更多用于控制 demo 运行形态和可复现性。

## 3. 每个参数对应需要重点关注的 logs / plots

### `turn_penalty`

- 重点看：`logs/train_steps.csv`
- 重点看：`logs/eval_metrics.csv`
- 重点看：`plots/reward_curve.png`
- 重点看：`plots/loss_curve.png`

### `revisit_penalty`

- 重点看：`logs/train_steps.csv`
- 重点看：`logs/final_probe.csv`
- 重点看：`plots/coverage_curve.png`
- 重点看：`plots/success_rate_curve.png`

### `entry_k`

- 重点看：`logs/train_episodes.csv`
- 重点看：`logs/eval_metrics.csv`
- 重点看：`plots/reward_curve.png`
- 重点看：`plots/coverage_curve.png`

## 4. 建议记录的调参理由格式

建议 `parameter_changes` 中每项至少记录：

- `name`
- `old_value`
- `new_value`
- `delta`
- `reason`

建议理由写法：

- 想验证什么现象
- 预计主要影响哪些指标 / 曲线
- 本轮最关心的风险是什么

如需跨轮对比，额外建议在 `gpt_decision.json` 中记录：

- `reference_targets.best_known_reference`
- `reference_targets.manual_compare_targets`

## 5. 风险控制规则

- `decision_status != run_next_round` 时，scheduler 不应启动训练。
- 不要把自然语言长文直接当成 machine-readable 决策协议，参数必须进入 `gpt_decision.json`。
- 不要让 scheduler 直接调用 OpenAI API 或网页端 GPT。
- bridge 调用当前仅限把 `codex_request.md` 单向发送给本地 Codex，不包含报告自动读回。
- `previous_round_run` 必须通过 `round_state.json` 解析为真实 run，不能把裸占位符直接交给 Codex。
- 参数变更理由必须落到 `parameter_changes`，不要只写在聊天上下文里。

## 6. 明确待补充项（TODO）

- 补充真实 RL 工程的参数与指标对应关系
- 明确真实训练中的 baseline / compare target 命名规则
- 明确 `codex_report.md` 如何再交回 GPT 使用
- 明确 bridge 层何时读取 `codex_request.md`、何时写回 `codex_report.md`
- 明确未来是否需要更强的协议版本化与状态机
