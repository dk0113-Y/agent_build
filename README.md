# Codex UI Bridge Demo

这是一个独立于当前 DRL 主工程的本地自动化 demo 仓库。当前仓库里有两条彼此分开的本地链路：

1. `demo_codex_bridge.py`
   本地 Codex GUI 通信 demo。通过 Windows UI Automation 和少量键鼠模拟，与已经打开的 Codex 桌面应用交互。
2. `fake_train.py + scheduler.py`
   本地训练完成检测 demo。通过假训练脚本逐步生成训练样式产物，再由最小调度器判断“训练是否完成”。

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
  Codex GUI 通信主脚本。支持 `--inspect-ui`、`--send-only`、`--demo`、`--dry-run`、`--manual-confirm-send`。
- `config.json`
  Codex GUI 定位与等待参数。
- `fake_train.py`
  生成单次假训练输出。会在 `outputs/<run_name>/` 下逐步写入 `checkpoints/`、`logs/`、`plots/`。
- `scheduler.py`
  最小调度器。它自己启动 `fake_train.py` 子进程，等待新的 run 目录出现，再等待子进程退出，最后做关键产物校验。
- `requirements.txt`
  运行本仓库 demo 所需的最小依赖列表。
- `logs/`
  Codex GUI bridge 的 inspect / run 日志目录。
- `outputs/`
  假训练 run 输出目录。该目录已加入 `.gitignore`。

## 链路一：Codex GUI 通信 demo

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

### 当前 ack prompt 模板

脚本会自动生成唯一 token，例如：

`AUTOMATION_DEMO_ACK::20260411_142401::96NTI9`

实际发送的消息模板是：

```text
请忽略其它上下文，只回复下面这一行，不要添加任何其它内容：
AUTOMATION_DEMO_ACK::<timestamp>::<random_id>
```

### 当前限制

1. 当前 Codex 桌面 UI 的聊天输入区并没有稳定暴露成标准 `EditControl`。
2. 发送按钮通常只能通过“与 `添加文件等` 同一行的最右侧按钮”推断。
3. 回复读取优先走 `RootWebArea` 下的 `TextControl`，失败后才回退到剪贴板复制。
4. 当前 bridge demo 仍不是稳定闭环，只能视为本地 GUI 自动化验证。

## 链路二：假训练 + 最小调度器 demo

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
2. `scheduler.py` 当前不会自动唤醒 Codex，也不会调用 `demo_codex_bridge.py`。
3. 当前 phase 只验证“训练输出形态”和“完成检测逻辑”，不是完整自动决策系统。

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
- `error` / `traceback`（失败时）
