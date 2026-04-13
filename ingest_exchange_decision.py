#!/usr/bin/env python
"""
CLI to ingest a GPT decision from the exchange workflow into a local round.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from automation_protocol import (
    GPT_INPUT_FILENAME,
    ProtocolError,
    ingest_decision_payload,
    normalize_round_id,
    read_json_file,
    rounds_root,
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

        # Hash computation
        hasher = hashlib.sha256()
        hasher.update(args.input_file.read_bytes())
        decision_sha256 = hasher.hexdigest()
        
        exchange_decision_sha256 = ""
        source_exchange_commit_sha = ""
        
        if args.exchange_repo_dir:
            exchange_rounds_dir = args.exchange_repo_dir.resolve() / "rounds" / source_round_id
            exchange_decision_file = exchange_rounds_dir / "next_gpt_decision.json"
            if exchange_decision_file.exists():
                ex_hasher = hashlib.sha256()
                ex_hasher.update(exchange_decision_file.read_bytes())
                exchange_decision_sha256 = ex_hasher.hexdigest()
                
                if exchange_decision_sha256 != decision_sha256 and not args.force:
                    raise ProtocolError(
                        f"Consistency error: The local input file hash ({decision_sha256}) "
                        f"does NOT match the exchange repo next_gpt_decision.json hash ({exchange_decision_sha256}). "
                        f"Use --force to ingest anyway."
                    )
            
            # Extract commit SHA if we can
            current_round_json_path = args.exchange_repo_dir.resolve() / "CURRENT_ROUND.json"
            if current_round_json_path.exists():
                try:
                    curr = json.loads(current_round_json_path.read_text(encoding="utf-8"))
                    source_exchange_commit_sha = (
                        curr.get("exchange_anchor_commit_sha")
                        or curr.get("last_exchange_commit_sha", "")
                    )
                except Exception:
                    pass

        # 2. Perform ingestion
        target_id, round_dir = ingest_decision_payload(
            payload=payload,
            target_round_id=args.target_round_id,
            source_round_id=source_round_id,
            force=args.force
        )
        
        # 2.5 Decorate new round state with extensive lineage
        from automation_protocol import update_round_state_file
        update_round_state_file(
            round_dir / "round_state.json",
            source_decision_sha256=decision_sha256,
            source_exchange_decision_sha256=exchange_decision_sha256,
            source_exchange_commit_sha=source_exchange_commit_sha,
        )

        print(f"status=ingested")
        print(f"target_round_id={target_id}")
        print(f"local_round_dir={round_dir}")

        # 3. Sync to exchange
        if args.sync_to_exchange:
            if not args.exchange_repo_dir:
                raise ProtocolError("--exchange-repo-dir is required when --sync-to-exchange is used.")
            
            exchange_rounds_dir = args.exchange_repo_dir / "rounds" / source_round_id
            if not exchange_rounds_dir.exists():
                print(f"Warning: Source round directory not found in exchange repo: {exchange_rounds_dir}")
                exchange_rounds_dir.mkdir(parents=True, exist_ok=True)
            
            local_decision_file = round_dir / "gpt_decision.json"
            target_path = exchange_rounds_dir / "next_gpt_decision.json"
            shutil.copy2(local_decision_file, target_path)
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
