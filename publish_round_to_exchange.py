#!/usr/bin/env python
"""Publish a local automation round to the exchange repository."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

from automation_protocol import (
    GPT_INPUT_FILENAME,
    ProtocolError,
    load_round_state_file,
    normalize_round_id,
    read_json_file,
    rounds_root,
    write_json_file,
)
from exchange_protocol import (
    EXCHANGE_ANCHOR_DEFINITION,
    EXCHANGE_SCHEMA_VERSION,
    build_web_index_message,
    build_empty_current_round,
    get_now_iso,
    initialize_exchange_repo,
    load_round_summary,
    project_name_for_mode,
    recommended_entry_docs_for_mode,
    stable_context_files_for_mode,
    sync_file_to_exchange,
)


PREFERRED_EXCHANGE_ANCHOR_FIELD = "exchange_anchor_commit_sha"
DEPRECATED_EXCHANGE_ANCHOR_FIELD = "last_exchange_commit_sha"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a local round to the exchange repository.")
    parser.add_argument("--round-id", required=True, help="Round ID to publish (for example round_0022).")
    parser.add_argument("--exchange-repo-dir", required=True, type=Path, help="Local path to the exchange repo clone.")
    parser.add_argument("--repo-url", required=True, help="Public URL of the exchange repository.")
    parser.add_argument("--branch", default="main", help="Target branch name.")
    parser.add_argument("--commit", action="store_true", help="Commit exchange repo changes after publishing.")
    parser.add_argument("--push", action="store_true", help="Push after commit.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing target round directory.")
    return parser.parse_args()


def run_git_command(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ProtocolError(exc.stderr.strip() or exc.stdout.strip() or "git command failed") from exc


def sha256_of_file(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def export_file_if_present(
    *,
    source_path: Path,
    target_round_dir: Path,
    exported_files: list[str],
    artifact_hashes: dict[str, str],
    round_id: str,
) -> None:
    if not source_path.exists():
        return
    sync_file_to_exchange(source_path, target_round_dir)
    exported_files.append(f"rounds/{round_id}/{source_path.name}")
    artifact_hashes[source_path.name] = sha256_of_file(source_path)


def formal_round_extra_files(local_round_dir: Path) -> list[Path]:
    names = [
        "metric_snapshot.json",
        "benchmark_summary.json",
        "config_snapshot.json",
        "artifact_index.json",
        "historical_baseline_summary.json",
        "comparability_report.json",
        "round_summary.json",
        "training_summary.txt",
    ]
    return [local_round_dir / name for name in names]


def set_exchange_anchor_fields(payload: dict[str, object], anchor_sha: str | None) -> dict[str, object]:
    payload[PREFERRED_EXCHANGE_ANCHOR_FIELD] = anchor_sha
    payload[DEPRECATED_EXCHANGE_ANCHOR_FIELD] = anchor_sha
    payload["exchange_anchor_definition"] = EXCHANGE_ANCHOR_DEFINITION
    return payload


def main() -> int:
    args = parse_args()
    try:
        if args.push and not args.commit:
            raise ProtocolError("--push requires --commit.")

        round_id = normalize_round_id(args.round_id)
        local_round_dir = rounds_root() / round_id
        if not local_round_dir.exists():
            raise ProtocolError(f"Local round directory was not found: {local_round_dir}")

        required_files = [
            local_round_dir / "gpt_decision.json",
            local_round_dir / "codex_request.md",
            local_round_dir / "codex_report.md",
            local_round_dir / "round_state.json",
        ]
        for path in required_files:
            if not path.exists():
                raise ProtocolError(f"Required local round file is missing: {path.name}")

        decision_payload = read_json_file(local_round_dir / "gpt_decision.json")
        round_state = load_round_state_file(local_round_dir / "round_state.json")
        experiment_mode = str(decision_payload.get("experiment_mode", "synthetic_rehearsal")).strip() or "synthetic_rehearsal"

        exchange_dir = args.exchange_repo_dir.resolve()
        if not exchange_dir.exists() or not (exchange_dir / ".git").exists():
            raise ProtocolError(f"Exchange repo directory is not a git clone: {exchange_dir}")

        initialize_exchange_repo(exchange_dir)
        target_round_dir = exchange_dir / "rounds" / round_id
        if target_round_dir.exists():
            if not args.force:
                raise ProtocolError(f"Target round directory already exists: {target_round_dir}")
            import shutil

            shutil.rmtree(target_round_dir)
        target_round_dir.mkdir(parents=True, exist_ok=True)

        exported_files: list[str] = []
        artifact_hashes: dict[str, str] = {}
        for path in required_files:
            export_file_if_present(
                source_path=path,
                target_round_dir=target_round_dir,
                exported_files=exported_files,
                artifact_hashes=artifact_hashes,
                round_id=round_id,
            )

        gpt_input_path = local_round_dir / GPT_INPUT_FILENAME
        if gpt_input_path.exists():
            content = gpt_input_path.read_text(encoding="utf-8")
            if "This file is a placeholder" not in content:
                export_file_if_present(
                    source_path=gpt_input_path,
                    target_round_dir=target_round_dir,
                    exported_files=exported_files,
                    artifact_hashes=artifact_hashes,
                    round_id=round_id,
                )

        if experiment_mode == "formal_train":
            for path in formal_round_extra_files(local_round_dir):
                export_file_if_present(
                    source_path=path,
                    target_round_dir=target_round_dir,
                    exported_files=exported_files,
                    artifact_hashes=artifact_hashes,
                    round_id=round_id,
                )

        round_summary = load_round_summary(local_round_dir, decision_payload, read_json_file(local_round_dir / "round_state.json"))
        summary_path = target_round_dir / "round_summary.json"
        write_json_file(summary_path, round_summary)
        if f"rounds/{round_id}/round_summary.json" not in exported_files:
            exported_files.append(f"rounds/{round_id}/round_summary.json")
            artifact_hashes["round_summary.json"] = sha256_of_file(summary_path)

        recommended_entry_docs = recommended_entry_docs_for_mode(experiment_mode)
        stable_context_files = stable_context_files_for_mode(experiment_mode)
        manifest = set_exchange_anchor_fields({
            "schema_version": EXCHANGE_SCHEMA_VERSION,
            "round_id": round_id,
            "project_name": project_name_for_mode(experiment_mode),
            "exchange_state": "round_published",
            "experiment_mode": experiment_mode,
            "source_of_truth_repo": decision_payload.get("source_of_truth_repo", ""),
            "local_execution_repo_path": decision_payload.get("local_execution_repo_path", ""),
            "evaluation_mode": decision_payload.get("evaluation_mode", ""),
            "baseline_round_id": decision_payload.get("baseline_round_id"),
            "baseline_commit_sha": decision_payload.get("baseline_commit_sha"),
            "comparability_group": decision_payload.get("comparability_group"),
            "decision_zone": decision_payload.get("decision_zone"),
            "stop_window_state": decision_payload.get("stop_window_state", {}),
            "stable_context_files": stable_context_files,
            "recommended_entry_docs": recommended_entry_docs,
            "round_files": exported_files,
            "artifact_hashes": artifact_hashes,
            "expected_output_file": "next_gpt_decision.json",
            "notes": decision_payload.get("controller_notes", ""),
            "updated_at": get_now_iso(),
        }, None)
        manifest_path = target_round_dir / "index_manifest.json"
        write_json_file(manifest_path, manifest)

        current_round_payload = set_exchange_anchor_fields({
            **build_empty_current_round(exchange_url=args.repo_url, branch=args.branch),
            "schema_version": EXCHANGE_SCHEMA_VERSION,
            "project_name": project_name_for_mode(experiment_mode),
            "exchange_repo_url": args.repo_url,
            "branch": args.branch,
            "exchange_state": "round_published",
            "current_round_id": round_id,
            "current_round_manifest": f"rounds/{round_id}/index_manifest.json",
            "experiment_mode": experiment_mode,
            "source_of_truth_repo": decision_payload.get("source_of_truth_repo", ""),
            "local_execution_repo_path": decision_payload.get("local_execution_repo_path", ""),
            "evaluation_mode": decision_payload.get("evaluation_mode", ""),
            "decision_zone": decision_payload.get("decision_zone"),
            "stop_window_state": decision_payload.get("stop_window_state", {}),
            "recommended_entry_docs": recommended_entry_docs,
            "stable_context_files": stable_context_files,
            "expected_output_file": "next_gpt_decision.json",
            "notes": [
                "Read `exchange_anchor_commit_sha` as the published bundle anchor commit.",
                "That anchor commit is the first commit that contains the published round bundle.",
                "The final pushed HEAD may be a later CURRENT_ROUND pointer-update commit.",
                "`last_exchange_commit_sha` is kept only as a deprecated compatibility alias.",
            ],
            "updated_at": get_now_iso(),
        }, None)
        current_round_path = exchange_dir / "CURRENT_ROUND.json"
        write_json_file(current_round_path, current_round_payload)

        outbox_path = exchange_dir / "outbox" / f"web_index_message_{round_id}.md"
        outbox_path.write_text(
            build_web_index_message(
                exchange_url=args.repo_url,
                round_id=round_id,
                branch=args.branch,
                experiment_mode=experiment_mode,
                manifest_path=f"rounds/{round_id}/index_manifest.json",
                recommended_entry_docs=recommended_entry_docs,
            ),
            encoding="utf-8",
        )

        print("status=published")
        print(f"round_id={round_id}")
        print(f"exchange_round_dir={target_round_dir}")
        print(f"manifest={manifest_path.relative_to(exchange_dir)}")
        print(f"current_round={current_round_path.relative_to(exchange_dir)}")
        print(f"outbox={outbox_path.relative_to(exchange_dir)}")

        bundle_commit_sha = ""
        final_commit_sha = ""
        if args.commit:
            run_git_command(exchange_dir, ["add", "."])
            status_result = run_git_command(exchange_dir, ["status", "--porcelain"])
            if not status_result.stdout.strip():
                print("status=no_changes")
                return 0
            run_git_command(exchange_dir, ["commit", "-m", f"Publish {round_id}"])
            bundle_commit_sha = run_git_command(exchange_dir, ["rev-parse", "HEAD"]).stdout.strip()
            set_exchange_anchor_fields(current_round_payload, bundle_commit_sha)
            round_summary = set_exchange_anchor_fields(round_summary, bundle_commit_sha)
            manifest = set_exchange_anchor_fields(manifest, bundle_commit_sha)
            write_json_file(current_round_path, current_round_payload)
            write_json_file(summary_path, round_summary)
            artifact_hashes["round_summary.json"] = sha256_of_file(summary_path)
            manifest["artifact_hashes"] = artifact_hashes
            write_json_file(manifest_path, manifest)
            run_git_command(
                exchange_dir,
                [
                    "add",
                    "CURRENT_ROUND.json",
                    str(manifest_path.relative_to(exchange_dir)),
                    str(summary_path.relative_to(exchange_dir)),
                ],
            )
            status_result = run_git_command(exchange_dir, ["status", "--porcelain"])
            if status_result.stdout.strip():
                run_git_command(exchange_dir, ["commit", "-m", f"Record exchange anchor for {round_id}"])
            final_commit_sha = run_git_command(exchange_dir, ["rev-parse", "HEAD"]).stdout.strip()
            if args.push:
                run_git_command(exchange_dir, ["push", "origin", args.branch])

        if bundle_commit_sha:
            from automation_protocol import update_round_state_file

            update_round_state_file(
                local_round_dir / "round_state.json",
                source_exchange_commit_sha=final_commit_sha or bundle_commit_sha,
            )
            print(f"{PREFERRED_EXCHANGE_ANCHOR_FIELD}={bundle_commit_sha}")
            print(f"{DEPRECATED_EXCHANGE_ANCHOR_FIELD}={bundle_commit_sha}")
            print(f"final_commit_sha={final_commit_sha or bundle_commit_sha}")
        return 0
    except ProtocolError as exc:
        print("status=error", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
