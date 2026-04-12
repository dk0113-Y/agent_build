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
    ingest_decision_payload,
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

        payload = read_json_file(args.input_file)

        # 2. Perform ingestion
        target_id, round_dir = ingest_decision_payload(
            payload=payload,
            target_round_id=args.target_round_id,
            source_round_id=args.source_round_id,
            force=args.force
        )

        print("status=ingested")
        print(f"target_round_id={target_id}")
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
