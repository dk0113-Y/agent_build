#!/usr/bin/env python
"""
CLI tool to ingest a GPT-produced decision JSON into a new automation round.
"""

from __future__ import annotations

import argparse
import sys
import shutil
from pathlib import Path

from automation_protocol import (
    GPT_INPUT_FILENAME,
    ProtocolError,
    ensure_round_state_file,
    load_decision_file,
    next_round_id,
    normalize_round_id,
    read_json_file,
    render_codex_report_stub,
    render_codex_request_placeholder,
    render_gpt_input_placeholder,
    rounds_root,
    update_round_state_file,
    write_json_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a GPT-produced decision JSON into a new round."
    )
    parser.add_argument(
        "--input-file",
        required=True,
        type=Path,
        help="Path to the JSON file produced by GPT.",
    )
    parser.add_argument(
        "--target-round-id",
        help="Optional target round id (e.g., round_0012 or 12). If not provided, it auto-increments.",
    )
    parser.add_argument(
        "--source-round-id",
        help="Optional source round id that generated this decision (for lineage recording).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target round directory if it already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        # 1. Read and validate input JSON
        if not args.input_file.exists():
            raise ProtocolError(f"Input file not found: {args.input_file}")

        # Basic JSON load for initial inspection
        payload = read_json_file(args.input_file)

        # 2. Determine target round ID
        base_dir = rounds_root()
        base_dir.mkdir(parents=True, exist_ok=True)
        target_round_id = (
            normalize_round_id(args.target_round_id)
            if args.target_round_id
            else next_round_id(base_dir)
        )
        round_dir = base_dir / target_round_id

        # 3. Handle existing directory
        if round_dir.exists():
            if args.force:
                print(f"Warning: Overwriting existing round directory: {round_dir}")
                shutil.rmtree(round_dir)
            else:
                raise ProtocolError(
                    f"Round directory already exists: {round_dir}. Use --force to overwrite."
                )

        round_dir.mkdir(parents=True, exist_ok=False)

        # 4. Prepare files
        decision_file = round_dir / "gpt_decision.json"
        codex_request_path = round_dir / "codex_request.md"
        codex_report_path = round_dir / "codex_report.md"
        gpt_input_path = round_dir / GPT_INPUT_FILENAME
        round_state_path = round_dir / "round_state.json"

        # 5. Normalize and write decision
        # We update the round_id in the payload to match our target
        payload["round_id"] = target_round_id
        write_json_file(decision_file, payload)

        # Validate the resulting file to ensure it's a valid GPTDecision
        try:
            load_decision_file(decision_file)
        except ProtocolError as exc:
            # If invalid, cleanup and error out
            shutil.rmtree(round_dir)
            raise ProtocolError(f"Input JSON failed schema validation: {exc}")

        # 6. Initialize other protocol files
        codex_request_path.write_text(
            render_codex_request_placeholder(target_round_id), encoding="utf-8"
        )
        codex_report_path.write_text(
            render_codex_report_stub(target_round_id), encoding="utf-8"
        )
        gpt_input_path.write_text(
            render_gpt_input_placeholder(target_round_id), encoding="utf-8"
        )

        # 7. Initialize round state with metadata
        ensure_round_state_file(
            round_dir=round_dir,
            round_id=target_round_id,
            decision_file=decision_file,
            codex_request_path=codex_request_path,
            codex_report_path=codex_report_path,
            gpt_input_path=gpt_input_path,
        )

        if args.source_round_id:
            src_id = normalize_round_id(args.source_round_id)
            update_round_state_file(round_state_path, source_round_id=src_id)

        print("status=ingested")
        print(f"target_round_id={target_round_id}")
        print(f"round_dir={round_dir}")
        if args.source_round_id:
            print(f"source_round_id={args.source_round_id}")

        return 0

    except ProtocolError as exc:
        print("status=error", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print("status=error", file=sys.stderr)
        print(f"unexpected_error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
