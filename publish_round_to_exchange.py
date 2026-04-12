#!/usr/bin/env python
"""
CLI to publish a local round to the GitHub exchange repository.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from automation_protocol import (
    GPT_INPUT_FILENAME,
    ProtocolError,
    load_decision_file,
    load_round_state_file,
    normalize_round_id,
    read_json_file,
    rounds_root,
    write_json_file,
)
from exchange_protocol import (
    EXCHANGE_SCHEMA_VERSION,
    CurrentRound,
    IndexManifest,
    build_web_index_message,
    get_now_iso,
    initialize_exchange_repo,
    parse_round_summary,
    sync_file_to_exchange,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Publish a local round to the exchange repository.")
    parser.add_argument("--round-id", required=True, help="Round ID to publish (e.g., round_0013 or 13)")
    parser.add_argument("--exchange-repo-dir", required=True, type=Path, help="Local path to the RRL_test clone.")
    parser.add_argument("--repo-url", required=True, help="GitHub URL of the exchange repository.")
    parser.add_argument("--branch", default="main", help="Target branch (default: main).")
    parser.add_argument("--commit", action="store_true", help="Automatically commit changes to the exchange repo.")
    parser.add_argument("--push", action="store_true", help="Automatically push changes to the exchange repo.")
    parser.add_argument("--force", action="store_true", help="Force overwrite files in the exchange repo.")
    return parser.parse_args()


def run_git_command(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {' '.join(e.cmd)}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        raise ProtocolError(f"Git execution error: {e.stderr.strip()}")


def main() -> int:
    args = parse_args()
    try:
        if args.push and not args.commit:
            raise ProtocolError("--push requires --commit to be specified.")

        # 1. Validation of local round
        round_id = normalize_round_id(args.round_id)
        local_round_dir = rounds_root() / round_id
        if not local_round_dir.exists():
            raise ProtocolError(f"Local round directory not found: {local_round_dir}")

        # Required files check
        required_files = ["gpt_decision.json", "codex_request.md", "codex_report.md", "round_state.json"]
        for f in required_files:
            if not (local_round_dir / f).exists():
                raise ProtocolError(f"Required file missing in local round: {f}")

        # 2. Validation of exchange repo
        exchange_dir = args.exchange_repo_dir.resolve()
        if not exchange_dir.exists() or not (exchange_dir / ".git").exists():
            raise ProtocolError(f"Exchange repo directory is not a valid git clone: {exchange_dir}")

        print(f"Initializing/Updating exchange repo structure in {exchange_dir}...")
        initialize_exchange_repo(exchange_dir)

        # 3. Export round files
        target_round_dir = exchange_dir / "rounds" / round_id
        target_round_dir.mkdir(parents=True, exist_ok=True)

        exported_files = []
        for f in required_files + ([GPT_INPUT_FILENAME] if (local_round_dir / GPT_INPUT_FILENAME).exists() else []):
            local_path = local_round_dir / f
            # Only export gpt_input.md if it's not a placeholder
            if f == GPT_INPUT_FILENAME:
                content = local_path.read_text(encoding="utf-8")
                if "This file is a placeholder" in content:
                    continue
            
            sync_file_to_exchange(local_path, target_round_dir)
            exported_files.append(f"rounds/{round_id}/{f}")

        # 4. Generate metadata
        decision_payload = read_json_file(local_round_dir / "gpt_decision.json")
        round_state = load_round_state_file(local_round_dir / "round_state.json")
        report_text = (local_round_dir / "codex_report.md").read_text(encoding="utf-8")

        summary = parse_round_summary(local_round_dir, decision_payload, round_state, report_text)
        summary_path = target_round_dir / "round_summary.json"
        write_json_file(summary_path, asdict(summary))
        exported_files.append(f"rounds/{round_id}/round_summary.json")

        manifest = IndexManifest(
            schema_version=EXCHANGE_SCHEMA_VERSION,
            round_id=round_id,
            task_type="experiment_analysis",
            stable_context_files=["docs/project_context.md", "docs/automation_scope.md", "docs/tuning_policy.md"],
            round_files=exported_files,
            expected_output_file="next_gpt_decision.json",
            notes=decision_payload.get("controller_notes", "")
        )
        manifest_path = target_round_dir / "index_manifest.json"
        write_json_file(manifest_path, asdict(manifest))

        # 5. Update CURRENT_ROUND.json
        current_round = CurrentRound(
            schema_version=EXCHANGE_SCHEMA_VERSION,
            project_name="DRL_automatic",
            exchange_repo_url=args.repo_url,
            branch=args.branch,
            current_round_id=round_id,
            current_round_manifest=f"rounds/{round_id}/index_manifest.json",
            recommended_entry_docs=["docs/project_context.md", "docs/automation_scope.md"],
            expected_output_file="next_gpt_decision.json",
            updated_at=get_now_iso()
        )
        write_json_file(exchange_dir / "CURRENT_ROUND.json", asdict(current_round))

        # 6. Generate Index Message
        outbox_dir = exchange_dir / "outbox"
        msg_content = build_web_index_message(args.repo_url, round_id, args.branch)
        msg_path = outbox_dir / f"web_index_message_{round_id}.md"
        msg_path.write_text(msg_content, encoding="utf-8")

        print(f"Round {round_id} published locally to {exchange_dir}")
        print(f"Summary: {summary_path.relative_to(exchange_dir)}")
        print(f"Manifest: {manifest_path.relative_to(exchange_dir)}")
        print(f"Index Message: {msg_path.relative_to(exchange_dir)}")

        # 7. Git operations
        if args.commit:
            print("Committing changes...")
            run_git_command(exchange_dir, ["add", "."])
            run_git_command(exchange_dir, ["commit", "-m", f"Publish round {round_id}"])
            
            if args.push:
                print("Pushing to remote...")
                run_git_command(exchange_dir, ["push", "origin", args.branch])

        print("status=success")
        return 0

    except ProtocolError as e:
        print(f"status=error\nerror={e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"status=error\nunexpected_error={e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
