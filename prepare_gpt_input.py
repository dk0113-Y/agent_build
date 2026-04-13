#!/usr/bin/env python
"""Render a GPT-consumable input package for a completed automation round."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from automation_protocol import (
    GPT_INPUT_FILENAME,
    ProtocolError,
    codex_report_is_ready,
    ensure_round_state_file,
    load_decision_file,
    load_round_state_file,
    normalize_round_id,
    render_gpt_input_package,
    rounds_root,
    update_round_state_file,
)
from formal_round_summary import load_formal_bundle, read_json, render_formal_gpt_input, round_is_formal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render gpt_input.md for a round that already has a Codex report.")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--round-dir", type=Path, help="Absolute or relative path to the round directory.")
    target_group.add_argument("--round-id", help="Round id like round_0001 or 1.")
    return parser.parse_args()


def resolve_round_dir(args: argparse.Namespace) -> Path:
    if args.round_dir is not None:
        return args.round_dir.resolve()
    return (rounds_root() / normalize_round_id(args.round_id)).resolve()


def main() -> int:
    args = parse_args()
    try:
        round_dir = resolve_round_dir(args)
        if not round_dir.exists() or not round_dir.is_dir():
            raise ProtocolError(f"Round directory was not found: {round_dir}")

        decision_file = round_dir / "gpt_decision.json"
        codex_request_path = round_dir / "codex_request.md"
        codex_report_path = round_dir / "codex_report.md"
        gpt_input_path = round_dir / GPT_INPUT_FILENAME

        decision = load_decision_file(decision_file)
        round_state_path = ensure_round_state_file(
            round_dir=round_dir,
            round_id=decision.round_id,
            decision_file=decision_file,
            codex_request_path=codex_request_path,
            codex_report_path=codex_report_path,
            gpt_input_path=gpt_input_path,
        )
        round_state = load_round_state_file(round_state_path)

        if round_is_formal(round_dir):
            bundle = load_formal_bundle(round_dir)
            if not bundle["comparability_report"] or not bundle["round_summary"]:
                raise ProtocolError(
                    "formal_train round is missing comparability_report.json or round_summary.json."
                )
            gpt_input_text = render_formal_gpt_input(
                decision=read_json(decision_file),
                round_state=read_json(round_state_path),
                round_summary=bundle["round_summary"],
                comparability_report=bundle["comparability_report"],
                metric_snapshot=bundle["metric_snapshot"],
                benchmark_summary=bundle["benchmark_summary"],
            )
        else:
            codex_request_text = codex_request_path.read_text(encoding="utf-8")
            codex_report_text = codex_report_path.read_text(encoding="utf-8")
            is_ready, reason = codex_report_is_ready(decision.round_id, codex_report_text)
            if not is_ready:
                raise ProtocolError(reason)

            gpt_input_text = render_gpt_input_package(
                decision=decision,
                round_state=round_state,
                codex_request_text=codex_request_text,
                codex_report_text=codex_report_text,
            )
        gpt_input_path.write_text(gpt_input_text, encoding="utf-8")
        update_round_state_file(round_state_path, gpt_input_path=gpt_input_path)

        print("status=gpt_input_ready")
        print(f"round_dir={round_dir}")
        print(f"gpt_input_path={gpt_input_path}")
        return 0
    except ProtocolError as exc:
        print("status=error", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
