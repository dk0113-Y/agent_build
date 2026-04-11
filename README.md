# Codex UI Bridge Demo

这是一个独立于当前 DRL 工程的本地 Windows GUI 自动化 demo。它不调用 OpenAI API，只尝试通过桌面 UI 自动化与已经打开的 Codex 桌面应用交互。

目标链路：

1. 聚焦本地 `Codex` 窗口
2. 定位底部聊天 composer
3. 自动粘贴一条只要求返回 ack token 的消息
4. 等待 Codex 回复
5. 通过 UI Automation 读取可见文本并搜索 token
6. 把发送内容、期望 token、检测到的回复、成功/失败状态写入本地日志

## 依赖安装

建议使用你本机已有的 Python 环境：

```bash
pip install -r requirements.txt
```

当前依赖：

- `uiautomation`
- `pyperclip`

## 文件说明

- `demo_codex_bridge.py`
  主脚本。支持 `--inspect-ui`、`--send-only`、`--demo`、`--dry-run`、`--manual-confirm-send`。
- `config.json`
  UI 定位与等待参数。包含窗口标题关键词、等待超时、轮询间隔、toolbar 锚点按钮名、是否启用剪贴板回退等。
- `requirements.txt`
  最小依赖列表。
- `logs/`
  每次运行写入一个 `run_*.json` 或 `inspect_*.json`。完整 demo 成功时还会额外写 `run_*_transcript.txt`。

## 运行方式

### 1. 先做 UI 探测

```bash
python demo_codex_bridge.py --inspect-ui
```

这会：

- 枚举标题匹配 `Codex` 的窗口
- 读取 `RootWebArea`
- 尝试定位 toolbar 锚点按钮、推断 composer 区域、推断发送按钮
- 把结果写到 `logs/inspect_*.json`

### 2. 只发送，不等待

```bash
python demo_codex_bridge.py --send-only
```

### 3. 完整 demo

```bash
python demo_codex_bridge.py --demo
```

### 4. 粘贴后手工确认再发送

```bash
python demo_codex_bridge.py --demo --manual-confirm-send
```

### 5. 只打印动作，不真正发送

```bash
python demo_codex_bridge.py --demo --dry-run
```

## 当前 ack prompt 模板

脚本会自动生成唯一 token，例如：

`AUTOMATION_DEMO_ACK::20260411_142401::96NTI9`

实际发送的消息模板是：

```text
请忽略其它上下文，只回复下面这一行，不要添加任何其它内容：
AUTOMATION_DEMO_ACK::<timestamp>::<random_id>
```

脚本默认要求在 UI 中看到这个 token 至少出现两次：

1. 一次来自刚发出的用户消息
2. 一次来自 Codex 的独立 ack 回复

## 回复读取策略

### A. 优先策略

直接遍历 `RootWebArea` 下的 `TextControl`，收集可见文本并统计 token 出现次数。

### B. 回退策略

如果直接遍历直到超时仍未拿到回复，会尝试：

1. 聚焦对话区域
2. 发送 `Ctrl+A`
3. 发送 `Ctrl+C`
4. 从剪贴板搜索 token

## 已知限制

1. 当前 Codex 桌面 UI 的聊天输入区并没有稳定暴露成标准 `EditControl`。这个 demo 目前是通过“底部 toolbar 按钮行 + 上方宽矩形区域”的几何关系来推断 composer 区域，然后点击该区域。
2. 当前发送按钮在现行 UI 树里通常是 toolbar 行最右侧的一个无名按钮，因此脚本通过“与 `添加文件等` 同一行的最右侧按钮”来推断发送按钮。
3. `uiautomation` 在动态刷新时偶尔会抛 COM 错误。脚本已经在读取路径上尽量吞掉单点异常，但仍建议在 Codex 空闲、窗口无遮挡时运行。
4. 剪贴板回退依赖当前焦点落在对话区域。如果某个侧栏、终端、差异面板抢走焦点，回退复制可能失败。
5. 如果你的本地 Codex UI 文案不同，例如不是中文按钮名 `添加文件等` / `滚动到底部` / `新线程`，请修改 `config.json` 对应字段。

## 若控件定位失败，优先调整这些配置

- `window_title_keyword`
- `toolbar_anchor_button_name`
- `scroll_to_bottom_button_name`
- `composer_gap_top_px`
- `composer_gap_bottom_px`
- `composer_min_width_px`
- `send_method`

## 日志内容

每次运行后的 JSON 日志至少会记录：

- `started_at`
- `sent_prompt`
- `expected_token`
- `detected_reply_text`
- `success`
- `status`
- `error` / `traceback`（失败时）
