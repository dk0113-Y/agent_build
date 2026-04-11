#!/usr/bin/env python
"""Create a new automation round directory with protocol-layer templates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from automation_protocol import (
    ProtocolError,
    build_decision_template,
    ensure_round_state_file,
    next_round_id,
    normalize_round_id,
    render_codex_report_stub,
    render_codex_request_placeholder,
    rounds_root,
    write_json_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a new automation round directory.")
    parser.add_argument("--round-id", help="Optional round id like round_0003 or 3.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        base_dir = rounds_root()
        base_dir.mkdir(parents=True, exist_ok=True)
        round_id = normalize_round_id(args.round_id) if args.round_id else next_round_id(base_dir)
        round_dir = base_dir / round_id
        if round_dir.exists():
            raise ProtocolError(f"Round directory already exists: {round_dir}")
        round_dir.mkdir(parents=True, exist_ok=False)

        decision_file = round_dir / "gpt_decision.json"
        codex_request_path = round_dir / "codex_request.md"
        codex_report_path = round_dir / "codex_report.md"
        round_state_file = round_dir / "round_state.json"

        write_json_file(decision_file, build_decision_template(round_id))
        codex_request_path.write_text(render_codex_request_placeholder(round_id), encoding="utf-8")
        codex_report_path.write_text(render_codex_report_stub(round_id), encoding="utf-8")
        ensure_round_state_file(
            round_dir=round_dir,
            round_id=round_id,
            decision_file=decision_file,
            codex_request_path=codex_request_path,
            codex_report_path=codex_report_path,
        )

        print("status=prepared")
        print(f"round_dir={round_dir}")
        print(f"decision_file={decision_file}")
        print(f"codex_request_path={codex_request_path}")
        print(f"codex_report_path={codex_report_path}")
        print(f"round_state_path={round_state_file}")
        return 0
    except ProtocolError as exc:
        print("status=error", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
