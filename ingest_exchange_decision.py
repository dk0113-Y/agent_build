#!/usr/bin/env python
"""
CLI to ingest a GPT decision from the exchange workflow into a local round.
"""

import argparse
import json
import shutil
import sys
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


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest a GPT-produced decision from the exchange workflow.")
    parser.add_argument("--input-file", required=True, type=Path, help="Path to the JSON file produced by GPT.")
    parser.add_argument("--source-round-id", required=True, help="Round ID that generated this decision.")
    parser.add_argument("--target-round-id", help="Optional target round ID. Auto-increments if not provided.")
    parser.add_argument("--exchange-repo-dir", type=Path, help="Local path to the exchange repo (for syncing).")
    parser.add_argument("--sync-to-exchange", action="store_true", help="Sync the decision JSON back to the exchange repo.")
    parser.add_argument("--force", action="store_true", help="Overwrite the target round directory if it exists.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        # 1. Validation
        if not args.input_file.exists():
            raise ProtocolError(f"Input file not found: {args.input_file}")
        
        payload = read_json_file(args.input_file)
        source_round_id = normalize_round_id(args.source_round_id)

        # 2. Determine target round
        base_dir = rounds_root()
        target_round_id = normalize_round_id(args.target_round_id) if args.target_round_id else next_round_id(base_dir)
        round_dir = base_dir / target_round_id

        # 3. Handle existing directory
        if round_dir.exists():
            if args.force:
                print(f"Warning: Overwriting existing round directory: {round_dir}")
                shutil.rmtree(round_dir)
            else:
                raise ProtocolError(f"Round directory already exists: {round_dir}. Use --force to overwrite.")

        round_dir.mkdir(parents=True, exist_ok=False)

        # 4. Ingest logic (similar to ingest_gpt_decision.py)
        decision_file = round_dir / "gpt_decision.json"
        payload["round_id"] = target_round_id
        write_json_file(decision_file, payload)

        # Validate
        try:
            load_decision_file(decision_file)
        except ProtocolError as exc:
            shutil.rmtree(round_dir)
            raise ProtocolError(f"Input JSON failed schema validation: {exc}")

        # Initialize protocol files
        (round_dir / "codex_request.md").write_text(render_codex_request_placeholder(target_round_id), encoding="utf-8")
        (round_dir / "codex_report.md").write_text(render_codex_report_stub(target_round_id), encoding="utf-8")
        (round_dir / GPT_INPUT_FILENAME).write_text(render_gpt_input_placeholder(target_round_id), encoding="utf-8")

        # Initialize state
        round_state_path = round_dir / "round_state.json"
        ensure_round_state_file(
            round_dir=round_dir,
            round_id=target_round_id,
            decision_file=decision_file,
            codex_request_path=round_dir / "codex_request.md",
            codex_report_path=round_dir / "codex_report.md",
            gpt_input_path=round_dir / GPT_INPUT_FILENAME
        )
        update_round_state_file(round_state_path, source_round_id=source_round_id)

        print(f"status=ingested")
        print(f"target_round_id={target_round_id}")
        print(f"local_round_dir={round_dir}")

        # 5. Sync to exchange
        if args.sync_to_exchange:
            if not args.exchange_repo_dir:
                raise ProtocolError("--exchange-repo-dir is required when --sync-to-exchange is used.")
            
            exchange_rounds_dir = args.exchange_repo_dir / "rounds" / source_round_id
            if not exchange_rounds_dir.exists():
                print(f"Warning: Source round directory not found in exchange repo: {exchange_rounds_dir}")
                exchange_rounds_dir.mkdir(parents=True, exist_ok=True)
            
            target_path = exchange_rounds_dir / "next_gpt_decision.json"
            shutil.copy2(decision_file, target_path)
            print(f"synced_to_exchange={target_path}")

        return 0

    except ProtocolError as e:
        print(f"status=error\nerror={e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"status=error\nunexpected_error={e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
