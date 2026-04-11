# Codex UI Bridge Demo

这是一个独立于当前 DRL 主工程的本地自动化 demo 仓库。当前仓库里有三层彼此分开的内容：

1. `demo_codex_bridge.py`
   本地 Codex GUI 通信 demo。通过 Windows UI Automation 和少量键鼠模拟，与已经打开的 Codex 桌面应用交互。
2. `fake_train.py + scheduler.py`
   假训练 + 完成检测 demo。通过假训练脚本逐步生成训练样式产物，再由最小调度器判断“训练是否完成”。
3. 协议层 / round 层
   通过 `gpt_decision.json`、`codex_request.md`、`codex_report.md`、`gpt_input.md`、`tuning_policy.md`、`prepare_round.py`、`prepare_gpt_input.py` 把控制平面协议和文件握手层搭起来。

当前仓库仍然不是成熟闭环系统。它没有接入 OpenAI API，没有依赖网页接口，也没有把“训练完成 -> 自动唤醒 Codex -> 自动改代码”串起来。

## 依赖安装

建议使用你本机已有的 Python 环境：

```bash
pip install -r requirements.txt
```

当前依赖：

- `uiautomation`
- `pyperclip`
- `matplotlib`

## 当前文件说明

- `demo_codex_bridge.py`
  Codex GUI 通信主脚本。支持 `--inspect-ui`、`--send-only`、`--demo`、`--dry-run`、`--manual-confirm-send`，并支持通过 `--message-file` / `--message-text` 发送任意文本。当前 `--send-only --message-file` / `--message-text` 会做最小送达确认。
- `config.json`
  Codex GUI 定位与等待参数。
- `config_new_thread.json`
  与 `config.json` 基本一致，但会先点击 `新线程`，便于把自动发送隔离到新的会话中。
- `fake_train.py`
  生成单次假训练输出。会在 `outputs/<run_name>/` 下逐步写入 `checkpoints/`、`logs/`、`plots/`。
- `scheduler.py`
  最小调度器。支持直参模式和 `--decision-file` 模式。它自己启动 `fake_train.py` 子进程，等待新的 run 目录出现，再等待子进程退出，最后做关键产物校验。
- `automation_protocol.py`
  协议层 helper。定义 decision schema、round 编号、模板读取、decision 校验、`codex_request.md` 渲染等辅助函数。
- `prepare_round.py`
  round 初始化工具。创建 `automation_rounds/round_0001/` 这种目录，并放入 `gpt_decision.json`、`codex_request.md`、`codex_report.md`、`gpt_input.md`、`round_state.json`。
- `prepare_gpt_input.py`
  GPT 输入包生成工具。读取 round 下的 decision / state / request / report，并生成给 GPT 消费的 `gpt_input.md`。
- `templates/gpt_decision.template.json`
  `gpt_decision.json` 模板。
- `templates/codex_report.template.md`
  `codex_report.md` 模板。
- `tuning_policy.md`
  当前自动化骨架允许的调参字段、记录方式和待补充项模板。
- `logs/`
  Codex GUI bridge 的 inspect / run 日志目录。
- `outputs/`
  假训练 run 输出目录。该目录已加入 `.gitignore`。
- `automation_rounds/`
  协议层 round 运行目录。该目录已加入 `.gitignore`，运行时由 `prepare_round.py` 创建。

## 第一层：Codex GUI 通信 demo

目标链路：

1. 聚焦本地 `Codex` 窗口
2. 定位底部聊天 composer
3. 自动粘贴一条只要求返回 ack token 的消息
4. 等待 Codex 回复
5. 通过 UI Automation 读取可见文本并搜索 token
6. 把发送内容、期望 token、检测到的回复、成功/失败状态写入本地日志

### 运行方式

1. 先做 UI 探测

```bash
python demo_codex_bridge.py --inspect-ui
```

2. 只发送，不等待

```bash
python demo_codex_bridge.py --send-only
```

也可以直接发送任意 Markdown / 文本，并做最小送达确认：

```bash
python demo_codex_bridge.py --send-only --message-file automation_rounds/round_0001/codex_request.md --config config_new_thread.json
```

3. 完整 demo

```bash
python demo_codex_bridge.py --demo
```

4. 粘贴后手工确认再发送

```bash
python demo_codex_bridge.py --demo --manual-confirm-send
```

5. 只打印动作，不真正发送

```bash
python demo_codex_bridge.py --demo --dry-run
```

### 当前限制

1. 当前 Codex 桌面 UI 的聊天输入区并没有稳定暴露成标准 `EditControl`。
2. 发送按钮通常只能通过“与 `添加文件等` 同一行的最右侧按钮”推断。
3. 回复读取优先走 `RootWebArea` 下的 `TextControl`，失败后才回退到剪贴板复制。
4. `status=sent_only` 现在表示“消息已发送并通过最小送达确认”；如果只是粘贴成功但未确认送达，会返回 `send_not_confirmed`。
5. 当前仍然没有实现自动读回 Codex 分析结果，bridge demo 仍是本地 GUI 自动化验证，不是稳定闭环。

## 第二层：假训练 + 最小调度器 demo

当前 phase 1 的目标只有两个：

1. 验证假训练输出能否对齐真实训练的顶层目录风格
2. 验证 `scheduler.py` 能否可靠判断“它自己启动的训练子进程已经完成”

这里的“训练完成”不是通过发现 `outputs/` 下有新文件来判定，而是同时要求：

1. 调度器启动的训练子进程正常退出
2. 对应 run 目录中的关键产物完整

### 假训练输出结构

`fake_train.py` 会在仓库根目录生成：

```text
outputs/<run_name>/
  checkpoints/
  logs/
  plots/
```

其中 `run_name` 风格如下：

```text
sched_turn003_revisit010_entry8_20260411_014043
```

顶层子目录固定对齐为：

- `checkpoints/`
- `logs/`
- `plots/`

`logs/` 下会逐步写入：

- `train_steps.csv`
- `train_episodes.csv`
- `eval_metrics.csv`
- `final_probe.csv`

`plots/` 下会周期性刷新：

- `reward_curve.png`
- `coverage_curve.png`
- `success_rate_curve.png`
- `loss_curve.png`

`checkpoints/` 下会在结束时补齐：

- `best.pt`
- `last.pt`

### 运行方式

直接运行假训练：

```bash
python fake_train.py --turn-penalty 0.03 --revisit-penalty 0.10 --entry-k 8
```

通过最小调度器运行并校验：

```bash
python scheduler.py --turn-penalty 0.03 --revisit-penalty 0.10 --entry-k 8
```

### 当前边界

1. `scheduler.py` 当前只检测它自己启动的训练子进程，不负责接管任意外部训练任务。
2. `scheduler.py` 当前可以选择性调用 `demo_codex_bridge.py` 把 `codex_request.md` 单向发给本地 Codex，但不会自动读回报告。
3. 当前 phase 只验证“训练输出形态”“完成检测逻辑”“request 单向发送”，不是完整自动决策系统。

## 第三层：协议层 / round 层

这一层的目标是把未来自动化链路的控制平面协议搭起来：

`GPT -> gpt_decision.json -> scheduler 启动训练 -> 训练完成 -> scheduler 生成 codex_request.md -> 后续由 bridge 发给 Codex -> Codex 产出 codex_report.md -> 后续再交回 GPT`

当前只实现到：

- `prepare_round.py` 创建 round 目录和模板文件
- 每个 round 目录会有一份 `round_state.json` 记录真实 lineage / run 状态
- `scheduler.py --decision-file ...` 读取 `gpt_decision.json`
- 训练成功后由 scheduler 自动生成 `codex_request.md`
- `previous_round_run` 会自动解析为上一轮成功 run 的真实路径
- `best_known_reference` 可由 `gpt_decision.json.reference_targets.best_known_reference` 显式提供
- round 目录中预置 `codex_report.md` 模板
- `prepare_gpt_input.py` 可在 `codex_report.md` 有真实内容后生成 `gpt_input.md`
- 可选地由 scheduler 自动调用 bridge，把 request 单向发送到本地 Codex

当前还没有：

- 网页端 GPT bridge
- OpenAI API
- Codex 自动写回 `codex_report.md`
- GPT 输出自动回写为下一轮 `gpt_decision.json`
- GPT 决策自动回流

### round 目录结构

`prepare_round.py` 默认会创建：

```text
automation_rounds/round_0001/
  gpt_decision.json
  codex_request.md
  codex_report.md
  gpt_input.md
  round_state.json
```

### 运行方式

初始化一个新的 round：

```bash
python prepare_round.py
```

也可以显式指定 round id：

```bash
python prepare_round.py --round-id round_0003
```

用 decision file 驱动 scheduler：

```bash
python scheduler.py --decision-file automation_rounds/round_0001/gpt_decision.json
```

在训练成功后，把生成的 `codex_request.md` 自动发送到本地已打开的 Codex：

```bash
python scheduler.py --decision-file automation_rounds/round_0001/gpt_decision.json --invoke-codex-bridge
```

调试版：

```bash
python scheduler.py --decision-file automation_rounds/round_0001/gpt_decision.json --invoke-codex-bridge --bridge-manual-confirm-send
```

当 `codex_report.md` 已经有真实内容后，生成给 GPT 使用的输入包：

```bash
python prepare_gpt_input.py --round-id round_0001
```

### `gpt_decision.json` 的最小 schema

当前协议层至少包含这些字段：

- `schema_version`
- `round_id`
- `decision_status`
- `target_program`
- `run_args`
- `parameter_changes`
- `codex_analysis_focus`
- `reference_targets`
- `controller_notes`

其中：

- `decision_status` 当前允许：`run_next_round`、`hold`、`stop`
- `target_program` 当前实际支持的是 `fake_train.py`
- `run_args` 当前映射到 `fake_train.py` 的参数
- `codex_analysis_focus` 用于后续生成结构化 `codex_request.md`
- `reference_targets.best_known_reference` 可显式指定基线 / 参考 run
- `reference_targets.manual_compare_targets` 可追加其它比较对象

### `round_state.json` 的作用

现在每个 round 目录都会有一份 `round_state.json`，它用于记录：

- 当前 round 的状态
- 对应的真实 `run_dir`
- 训练返回码
- bridge 是否被调用以及调用结果
- 对应的 `gpt_input.md` 路径

系统会通过这些 state 文件建立最小 lineage：

- `previous_round_run` 会自动解析为“当前 round 之前最近一个成功 round”的真实 `run_dir`
- 如果找不到上一轮成功 run，`codex_request.md` 会写出明确的未解析说明
- 如果 `best_known_reference` 没在 `gpt_decision.json` 中提供，`codex_request.md` 也会写出明确未解析说明，而不是保留裸占位符

### `codex_request.md` 的作用

`scheduler.py` 在 `decision_status=run_next_round` 且训练完成校验成功后，会结合：

- 本轮 `gpt_decision.json`
- 实际检测到的 `run_dir`
- 已解析的 compare targets

自动渲染 `codex_request.md`。这个文件是给后续 bridge / Codex 使用的固定握手面，不应该再重新发明协议。

当前 `scheduler.py` 还可以在 `codex_request.md` 写出后，选择性自动调用 `demo_codex_bridge.py`，把这份 request 发送到本地 Codex 聊天窗口。
这一步目前仍然只是单向发送 request，还没有实现分析结果自动读回、`codex_report.md` 自动回写或 GPT 决策回流。

### `codex_report.md` 的作用

`codex_report.md` 当前只是模板 / stub，供后续 Codex 填写。当前仓库还没有自动生成该报告。

### `gpt_input.md` 的作用

`gpt_input.md` 是给后续 GPT 消费的标准输入包。它会把同一 round 中的：

- `gpt_decision.json`
- `round_state.json`
- `codex_request.md`
- `codex_report.md`

整理成一份稳定 Markdown 文件，便于后续人工或自动发送给 GPT。

`prepare_gpt_input.py` 会拒绝使用空模板状态的 `codex_report.md` 来生成 `gpt_input.md`。当前仓库仍然没有实现网页端 GPT 自动发送，也没有实现 GPT 输出自动回写为下一轮 decision。

### `tuning_policy.md` 的作用

`tuning_policy.md` 当前不是最终科研调参结论，只是：

- 当前自动化 demo 已支持参数的结构化说明
- 建议记录方式
- 风险控制规则
- 明确待补充项

## Codex bridge 配置提示

如果控件定位失败，优先调整这些配置：

- `window_title_keyword`
- `toolbar_anchor_button_name`
- `scroll_to_bottom_button_name`
- `composer_gap_top_px`
- `composer_gap_bottom_px`
- `composer_min_width_px`
- `send_method`

## Codex bridge 日志字段

每次运行后的 JSON 日志至少会记录：

- `started_at`
- `sent_prompt`
- `expected_token`
- `detected_reply_text`
- `success`
- `status`
- `message_probe`（`--send-only --message-file` / `--message-text` 时，默认取消息第一条非空行）
- `message_probe_baseline_count`
- `message_probe_post_paste_count`
- `message_probe_post_send_count`
- `send_confirmation_status`
- `send_confirmation_reason`
- `error` / `traceback`（失败时）

其中 `--send-only --message-file` / `--message-text` 的状态语义是：

- `sent_only` 表示文本已发送并通过最小送达确认。
- `send_not_confirmed` 表示文本可能已经粘贴，但没有足够证据确认它已进入聊天记录区。
- `send_confirmation_status` / `send_confirmation_reason` 用于记录最小确认的判定结果和原因。
