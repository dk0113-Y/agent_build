# Codex UI Bridge Demo

这个仓库现在是一个本地控制面仓库，不再是 `fake_train.py` 单一演示仓库。它同时承载两种模式：

- `synthetic_rehearsal`
  - 用于保留原有演示链路与 GUI bridge 验证
- `formal_train`
  - 用于接入真实训练工程 `train_q_agent.py`
  - 以结构化 formal artifact 驱动 comparability、round verdict、publish 和 GPT 决策输入

当前主叙事是 `formal_train`，rehearsal 只是兼容模式。

## Codex 本地入口

先读 `docs/codex_local_index.md`。

- 这份文档负责三仓文件地图、读取顺序、文件角色边界、任务型读取建议。
- README 只保留总览，不再承担全部本地取证说明。

## 角色分工

- `../代码1`
  - 正式训练事实源
  - 真实入口：`train_q_agent.py`
  - 真实 formal artifact：`metric_snapshot.json`、`benchmark_summary.json`、`config_snapshot.json`、`artifact_index.json`
- 当前仓库
  - 本地控制面、round 协议、formal bundle 构建、comparability、exchange publish
- `../RRL_test`
  - 公开交换仓库
  - 新 GPT 聊天读取长期上下文和当前 round 的入口

## 当前协议要点

- schema 版本：`2.0`
- 支持模式：`synthetic_rehearsal`、`formal_train`
- formal 决策动作：
  - `run_next_round`
  - `stop_experiment`
  - `pause_for_manual_review`
  - `analyze_only`
- formal 决策必须先过 comparability，再谈提升/退化/平台期
- exchange-facing `source_of_truth_repo` 使用仓库身份，例如 `dk0113-Y/DRL-path-finding`
- 本地执行路径单独写在 `local_execution_repo_path`

## 关键脚本

- `automation_protocol.py`
  - dual-mode schema、decision/round_state 读写、协议校验、GPT/Codex 文本渲染
- `scheduler.py`
  - 根据 `gpt_decision.json` 启动训练
  - rehearsal 可跑 `fake_train.py`
  - formal 可跑 `train_q_agent.py`
- `build_exchange_bundle.py`
  - 从真实 `outputs/<run>/` 构建 formal round bundle
  - 会纳入 `historical_baseline_summary.json`
  - 会把 exchange-facing JSON 的 truth repo 统一成 repo identity
- `comparability.py`
  - 结构化 comparability 检查
  - 读取 `observed_run_contract`，检查 `final_env_steps`、`train_steps_header`、`eval_metrics_header`、`final_probe_header`
- `formal_round_summary.py`
  - 输出 structured verdict、stop window、manual review reasons、evidence gaps
- `prepare_gpt_input.py`
  - 优先基于 formal JSON 生成 GPT 输入包
- `publish_round_to_exchange.py`
  - 发布 round 到 `../RRL_test`
  - 会同步 `CURRENT_ROUND.json`、`index_manifest.json`、outbox 消息
  - 发布后会写入 `exchange_anchor_commit_sha`
  - `last_exchange_commit_sha` 仅作为 deprecated 兼容别名保留

## formal_train 产物要求

formal round bundle 至少包含：

- `metric_snapshot.json`
- `benchmark_summary.json`
- `config_snapshot.json`
- `artifact_index.json`
- `historical_baseline_summary.json`（若可获得；不足时也会显式标注 `insufficient_history_for_calibration`）
- `comparability_report.json`
- `round_summary.json`

## Exchange Anchor 语义

- `exchange_anchor_commit_sha`
  - 表示本次发布的 bundle anchor commit
  - 这是第一个真实包含 round bundle 的 exchange commit
  - 该 commit 必须非空、真实存在、并且从最终 pushed HEAD 可达
- `last_exchange_commit_sha`
  - deprecated 兼容字段
  - 当前与 `exchange_anchor_commit_sha` 保持相同值
  - 不再表示“包含 CURRENT_ROUND.json 自身的最终 HEAD sha”

这样可以避免 `CURRENT_ROUND.json` 自指：因为 `CURRENT_ROUND.json` 在后续 pointer-update commit 中记录的是前一个已存在的 bundle anchor commit，而不是试图记录自身所在的最终 HEAD。

当前 publish 逻辑也支持从一个已清场的 exchange repo 启动：

- `rounds/` 可以只有 `.gitkeep`
- `outbox/` 可以只有 `.gitkeep`
- `CURRENT_ROUND.json` 可以处于 `exchange_state = awaiting_new_round_publish` 的空态

其中：

- `config_snapshot.json`
  - 必须带 `observed_run_contract`
  - 当前至少包括：
    - `final_env_steps`
    - `train_steps_header`
    - `eval_metrics_header`
    - `final_probe_header`
- `comparability_report.json`
  - 用这些 observed contract 字段做结构化 comparability 判断
- `round_summary.json`
  - 提供 `primary_metric_verdict`
  - `secondary_metric_verdict`
  - `stability_verdict`
  - `efficiency_verdict`
  - `overall_round_verdict`
  - `decision_zone`
  - `stop_window_state`

## 常用流程

### 1. 准备或运行一轮

```bash
python prepare_round.py
python scheduler.py --decision-file automation_rounds/round_0001/gpt_decision.json
```

### 2. 从真实 run 构建 formal round

```bash
python build_exchange_bundle.py ^
  --round-id round_xxxx ^
  --run-dir ../代码1/outputs/<run_name> ^
  --baseline-run-dir ../代码1/outputs/<baseline_run_name> ^
  --baseline-round-id round_xxxx ^
  --force
```

### 3. 生成 GPT 输入包

```bash
python prepare_gpt_input.py --round-id round_xxxx
```

### 4. 发布到交换仓库

```bash
python publish_round_to_exchange.py ^
  --round-id round_xxxx ^
  --exchange-repo-dir ../RRL_test ^
  --repo-url https://github.com/dk0113-Y/RRL_test ^
  --branch main ^
  --force ^
  --commit ^
  --push
```

## reheasal 兼容边界

- `fake_train.py`、GUI bridge、旧 demo 仍然保留
- 但 formal schema、formal docs、formal publish 不再默认绑定 rehearsal
- 不允许再用 synthetic rehearsal 的指标语义去替代真实训练工程的 formal judgement
