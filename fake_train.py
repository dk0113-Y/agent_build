#!/usr/bin/env python
"""
Generate training-like artifacts for the local scheduler demo.

This script does not train a real model. It writes a run directory that looks
like a single training output, with gradual CSV updates and periodic plot
refreshes so the scheduler can distinguish "training in progress" from
"training completed".
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


EXPECTED_LOG_FILES = (
    "train_steps.csv",
    "train_episodes.csv",
    "eval_metrics.csv",
    "final_probe.csv",
)
EXPECTED_PLOT_FILES = (
    "reward_curve.png",
    "coverage_curve.png",
    "success_rate_curve.png",
    "loss_curve.png",
)
EXPECTED_CHECKPOINT_FILES = ("best.pt", "last.pt")


@dataclass
class MetricPoint:
    step: int
    reward: float
    coverage: float
    success_rate: float
    loss: float
    episode_length: int
    elapsed_sec: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fake training outputs.")
    parser.add_argument("--turn-penalty", type=float, required=True)
    parser.add_argument("--revisit-penalty", type=float, required=True)
    parser.add_argument("--entry-k", type=int, required=True)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--sleep-sec", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def format_penalty(value: float) -> str:
    scaled = int(round(value * 100))
    if scaled < 0:
        raise ValueError("Penalty values must be non-negative.")
    return f"{scaled:03d}"


def build_run_name(turn_penalty: float, revisit_penalty: float, entry_k: int) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        f"sched_turn{format_penalty(turn_penalty)}"
        f"_revisit{format_penalty(revisit_penalty)}"
        f"_entry{entry_k}_{stamp}"
    )


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def ensure_run_layout(run_dir: Path) -> dict[str, Path]:
    logs_dir = run_dir / "logs"
    plots_dir = run_dir / "plots"
    checkpoints_dir = run_dir / "checkpoints"
    for path in (run_dir, logs_dir, plots_dir, checkpoints_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "logs_dir": logs_dir,
        "plots_dir": plots_dir,
        "checkpoints_dir": checkpoints_dir,
    }


def init_csv(path: Path, header: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)


def append_csv_row(path: Path, row: list[object]) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(row)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_metric_point(
    *,
    step: int,
    total_steps: int,
    turn_penalty: float,
    revisit_penalty: float,
    entry_k: int,
    rng: random.Random,
    elapsed_sec: float,
) -> MetricPoint:
    progress = step / max(total_steps, 1)
    reward_base = 28.0 + 92.0 * (1.0 - math.exp(-3.2 * progress))
    reward_bias = -turn_penalty * 80.0 - revisit_penalty * 55.0 + entry_k * 1.6
    reward_wave = 6.5 * math.sin(step * 0.45) + 2.0 * math.sin(step * 0.12 + 0.5)
    reward_noise = rng.uniform(-3.0, 3.0)
    reward = reward_base + reward_bias + reward_wave + reward_noise

    coverage_base = 0.18 + 0.79 * (1.0 - math.exp(-3.6 * progress))
    coverage_noise = rng.uniform(-0.02, 0.02)
    coverage = clamp(coverage_base + coverage_noise - turn_penalty * 0.08, 0.0, 0.995)

    success_base = 1.0 / (1.0 + math.exp(-8.0 * (progress - 0.55)))
    success_noise = rng.uniform(-0.03, 0.03)
    success_rate = clamp(success_base + success_noise - revisit_penalty * 0.05, 0.0, 0.995)

    loss_base = 1.95 * math.exp(-4.1 * progress) + 0.12
    loss_wave = 0.08 * math.cos(step * 0.55)
    loss_noise = rng.uniform(-0.03, 0.03)
    loss = clamp(loss_base + loss_wave + loss_noise + turn_penalty * 0.2, 0.02, 3.0)

    episode_length = max(18, int(round(110 - progress * 52 + rng.uniform(-6, 6))))

    return MetricPoint(
        step=step,
        reward=reward,
        coverage=coverage,
        success_rate=success_rate,
        loss=loss,
        episode_length=episode_length,
        elapsed_sec=elapsed_sec,
    )


def refresh_plots(plots_dir: Path, history: list[MetricPoint]) -> None:
    x_values = [item.step for item in history]
    series = (
        ("reward_curve.png", "Reward", [item.reward for item in history], "#1f77b4"),
        ("coverage_curve.png", "Coverage", [item.coverage for item in history], "#2ca02c"),
        ("success_rate_curve.png", "Success Rate", [item.success_rate for item in history], "#ff7f0e"),
        ("loss_curve.png", "Loss", [item.loss for item in history], "#d62728"),
    )
    for filename, ylabel, y_values, color in series:
        figure, axis = plt.subplots(figsize=(6.4, 4.0))
        axis.plot(x_values, y_values, color=color, linewidth=2.0)
        axis.set_xlabel("Step")
        axis.set_ylabel(ylabel)
        axis.set_title(ylabel)
        axis.grid(True, linestyle="--", alpha=0.35)
        if len(x_values) == 1:
            axis.set_xlim(0.5, 1.5)
        else:
            axis.set_xlim(1, max(x_values))
        if ylabel in {"Coverage", "Success Rate"}:
            axis.set_ylim(0.0, 1.02)
        figure.tight_layout()
        figure.savefig(plots_dir / filename, dpi=120)
        plt.close(figure)


def write_checkpoint(path: Path, *, label: str, point: MetricPoint) -> None:
    content = (
        f"fake_checkpoint={label}\n"
        f"step={point.step}\n"
        f"reward={point.reward:.4f}\n"
        f"coverage={point.coverage:.4f}\n"
        f"success_rate={point.success_rate:.4f}\n"
        f"loss={point.loss:.4f}\n"
    )
    path.write_text(content, encoding="utf-8")


def recent_average(history: list[MetricPoint], attr_name: str, window: int = 5) -> float:
    values = [getattr(item, attr_name) for item in history[-window:]]
    return sum(values) / max(len(values), 1)


def main() -> int:
    args = parse_args()
    if args.steps <= 0:
        raise ValueError("--steps must be positive.")
    if args.sleep_sec < 0:
        raise ValueError("--sleep-sec must be non-negative.")
    if args.entry_k <= 0:
        raise ValueError("--entry-k must be positive.")

    run_name = build_run_name(args.turn_penalty, args.revisit_penalty, args.entry_k)
    run_dir = repo_root() / "outputs" / run_name
    layout = ensure_run_layout(run_dir)
    logs_dir = layout["logs_dir"]
    plots_dir = layout["plots_dir"]
    checkpoints_dir = layout["checkpoints_dir"]

    train_steps_csv = logs_dir / "train_steps.csv"
    train_episodes_csv = logs_dir / "train_episodes.csv"
    eval_metrics_csv = logs_dir / "eval_metrics.csv"
    final_probe_csv = logs_dir / "final_probe.csv"

    init_csv(
        train_steps_csv,
        ["step", "elapsed_sec", "reward", "coverage", "success_rate", "loss"],
    )
    init_csv(
        train_episodes_csv,
        [
            "episode",
            "step",
            "elapsed_sec",
            "episode_reward",
            "episode_length",
            "coverage",
            "success",
        ],
    )
    init_csv(
        eval_metrics_csv,
        ["eval_index", "step", "eval_reward", "eval_coverage", "eval_success_rate", "eval_loss"],
    )
    init_csv(
        final_probe_csv,
        ["probe_index", "step", "reward_mean_5", "coverage_mean_5", "success_rate_mean_5", "status"],
    )

    rng = random.Random(args.seed)
    history: list[MetricPoint] = []
    best_point: MetricPoint | None = None
    eval_index = 0
    probe_index = 0
    start_time = time.perf_counter()
    plot_every = max(2, args.steps // 4)
    eval_every = max(2, args.steps // 5)

    print("status=started", flush=True)
    print(f"run_dir={run_dir}", flush=True)

    for step in range(1, args.steps + 1):
        elapsed_sec = time.perf_counter() - start_time
        point = build_metric_point(
            step=step,
            total_steps=args.steps,
            turn_penalty=args.turn_penalty,
            revisit_penalty=args.revisit_penalty,
            entry_k=args.entry_k,
            rng=rng,
            elapsed_sec=elapsed_sec,
        )
        history.append(point)

        append_csv_row(
            train_steps_csv,
            [
                point.step,
                f"{point.elapsed_sec:.3f}",
                f"{point.reward:.4f}",
                f"{point.coverage:.4f}",
                f"{point.success_rate:.4f}",
                f"{point.loss:.4f}",
            ],
        )

        append_csv_row(
            train_episodes_csv,
            [
                point.step,
                point.step,
                f"{point.elapsed_sec:.3f}",
                f"{point.reward + rng.uniform(-8.0, 8.0):.4f}",
                point.episode_length,
                f"{point.coverage:.4f}",
                int(point.success_rate >= 0.55),
            ],
        )

        if best_point is None or point.reward > best_point.reward:
            best_point = point

        if step % eval_every == 0 or step == 1 or step == args.steps:
            eval_index += 1
            append_csv_row(
                eval_metrics_csv,
                [
                    eval_index,
                    point.step,
                    f"{point.reward + 2.5:.4f}",
                    f"{clamp(point.coverage + 0.01, 0.0, 1.0):.4f}",
                    f"{clamp(point.success_rate + 0.015, 0.0, 1.0):.4f}",
                    f"{max(point.loss - 0.04, 0.02):.4f}",
                ],
            )

            probe_index += 1
            append_csv_row(
                final_probe_csv,
                [
                    probe_index,
                    point.step,
                    f"{recent_average(history, 'reward'):.4f}",
                    f"{recent_average(history, 'coverage'):.4f}",
                    f"{recent_average(history, 'success_rate'):.4f}",
                    "running" if step < args.steps else "completed",
                ],
            )

        if step % plot_every == 0 or step == 1 or step == args.steps:
            refresh_plots(plots_dir, history)

        print(
            "status=progress "
            f"step={step}/{args.steps} "
            f"reward={point.reward:.3f} "
            f"coverage={point.coverage:.3f} "
            f"success_rate={point.success_rate:.3f} "
            f"loss={point.loss:.3f}",
            flush=True,
        )
        time.sleep(args.sleep_sec)

    assert best_point is not None
    final_point = history[-1]
    refresh_plots(plots_dir, history)
    write_checkpoint(checkpoints_dir / "last.pt", label="last", point=final_point)
    write_checkpoint(checkpoints_dir / "best.pt", label="best", point=best_point)

    print("status=completed", flush=True)
    print(f"run_dir={run_dir}", flush=True)
    print(f"best_reward={best_point.reward:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
