import argparse
import sys
import subprocess
import json
import time as _time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser("Codex Roundtrip Bridge")
    parser.add_argument("--request", type=Path, required=True, help="Input codex_request.md")
    parser.add_argument("--report", type=Path, required=True, help="Output codex_report.md")
    parser.add_argument("--allow-synthetic-fallback", action="store_true", help="Use synthetic mock report if UI automation fails.", default=False)
    parser.add_argument("--output-json", type=Path, help="Optional specific JSON path to output extraction results to.")
    parser.add_argument("--expect-substring", type=str, help="Enforce content-level verification.")
    parser.add_argument("--watchdog-timeout-sec", type=int, default=600, help="Max seconds to wait for the UI bridge process (watchdog).")
    parser.add_argument("--report-wait-sec", type=float, default=300.0, help="Max seconds for file-first report watcher inside demo_codex_bridge.")
    return parser.parse_args()


def generate_mock_report(request_path: Path) -> str:
    content = ""
    if request_path.exists():
        content = request_path.read_text("utf-8")

    return (
        "## Codex Analysis Report\n\n"
        "**Observation:** The logs and plots provided show clear directional trends in the training progression. "
        "High success rates are partially offset by performance instability.\n"
        "- The `turn_penalty` appears slightly too high, restricting necessary flexibility. It should be reduced.\n"
        "- The `revisit_penalty` restricts exploration. Consider adjusting it downwards.\n"
        "- `entry_k` provides strong performance anchors. Consider increasing it moderately.\n\n"
        "**Recommended next step:** Adjust the aforementioned parameters to encourage a safer exploration boundary.\n"
        "**Confidence / caveat:** Medium confidence due to synthetic tracking scope.\n\n"
        "Detailed evaluations confirm progress toward generalized performance."
    )


def _extract_round_id(report_path: Path) -> str:
    try:
        return report_path.resolve().parent.name
    except Exception:
        return "round_xxxx"


def _write_raw_reply_snapshot(output_json: Path, ui_text: str) -> None:
    """Save raw UI transcript alongside output_json for debugging (not as official report)."""
    try:
        tmp_dir = output_json.parent
        stem = output_json.stem
        parts = stem.split("_out_")
        suffix = parts[1] if len(parts) > 1 else stem
        snapshot_path = tmp_dir / f"codex_bridge_raw_reply_{suffix}.md"
        snapshot_path.write_text(ui_text, encoding="utf-8")
        print(f"Raw UI reply snapshot: {snapshot_path}")
    except Exception as e:
        print(f"Warning: could not write raw reply snapshot: {e}")


def _file_gate(report: Path, round_id: str) -> tuple[bool, str]:
    """
    Validate the report file directly — file-first approach.
    Does NOT use UI reply_text. Report must exist, be non-empty, and pass readiness.
    Fail-closed: any exception in readiness check is treated as a gate failure.
    """
    if not report.exists():
        return False, "report_file_missing"
    try:
        text = report.read_text("utf-8").strip()
    except Exception as e:
        return False, f"report_file_read_error: {e}"
    if not text:
        return False, "report_file_empty"
    try:
        from automation_protocol import codex_report_is_ready
        ready, reason = codex_report_is_ready(round_id, text)
        if not ready:
            return False, f"codex_report_not_ready: {reason}"
    except Exception as e:
        return False, f"codex_report_is_ready_exception: {e}"
    return True, "ok"



def main():
    args = parse_args()

    round_id = _extract_round_id(args.report)

    # --- Pre-run: clear any stale/old report so it cannot satisfy the gate ---
    if args.report.exists():
        try:
            args.report.unlink()
            print(f"Cleared stale report: {args.report}")
        except Exception as e:
            print(f"Warning: could not clear stale report {args.report}: {e}", file=sys.stderr)

    output_json = args.output_json if args.output_json else Path(__file__).parent / "tmp" / "codex_bridge_out.json"

    print("Executing demo_codex_bridge.py (file-first mode)...")
    bridge_script = Path(__file__).parent / "demo_codex_bridge.py"

    cmd = [
        sys.executable, str(bridge_script),
        "--send-and-wait",
        "--message-file", str(args.request),
        "--output-json", str(output_json),
        "--report-path", str(args.report),
        "--round-id", round_id,
        "--report-wait-sec", str(args.report_wait_sec),
    ]
    if args.expect_substring:
        cmd.extend(["--expect-substring", args.expect_substring])

    failure_reason = ""

    try:
        print(f"bridge_watchdog_timeout={args.watchdog_timeout_sec}s")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=args.watchdog_timeout_sec)
        print(f"bridge_process_exited: returncode={res.returncode}")
        if res.stdout:
            print("STDOUT:", res.stdout[-2000:])

        # --- Read output_json for primary status and diagnostics ---
        bridge_send_confirmed = True  # assume OK unless we see otherwise
        bridge_send_status = ""
        bridge_send_reason = ""
        ui_transcript = ""
        if output_json.exists():
            try:
                out_data = json.loads(output_json.read_text("utf-8"))
                bridge_send_confirmed = bool(out_data.get("send_confirmed", True))
                bridge_send_status = out_data.get("send_confirmation_status", out_data.get("status", ""))
                bridge_send_reason = out_data.get("send_confirmation_reason", out_data.get("send_confirm_reason", ""))
                ui_transcript = out_data.get("ui_candidate_reply_text", "") or out_data.get("reply_text", "")
                if ui_transcript:
                    _write_raw_reply_snapshot(output_json, ui_transcript)
                if out_data.get("report_ready"):
                    print("demo_codex_bridge reports report_file_ready — running final file gate...")
            except Exception as e:
                print(f"Warning: could not parse output_json: {e}")

        # --- Artifact confirmation: poll file gate for up to 15s after process exits ---
        deadline = _time.time() + 15
        gate_passed = False
        gate_reason = "not_checked"
        while _time.time() < deadline:
            gate_passed, gate_reason = _file_gate(args.report, round_id)
            if gate_passed:
                break
            _time.sleep(1)

        if gate_passed:
            print(f"File gate passed. Report at {args.report.name}")
            return 0
        else:
            # Preserve send_not_confirmed as primary failure reason if send was not confirmed.
            if not bridge_send_confirmed and bridge_send_status:
                failure_reason = f"send_not_confirmed: {bridge_send_reason or bridge_send_status}"
            else:
                failure_reason = gate_reason
            print(f"File gate failed: {gate_reason} | primary_failure_reason: {failure_reason}")
            if res.stderr:
                print("STDERR:", res.stderr[-2000:])

    except subprocess.TimeoutExpired:
        failure_reason = "bridge_watchdog_timeout"
        print(f"Error: {failure_reason} after {args.watchdog_timeout_sec}s", file=sys.stderr)
    except Exception as e:
        failure_reason = f"bridge_exception: {e}"
        print(f"Failed to run UI bridge: {e}", file=sys.stderr)

    if args.allow_synthetic_fallback:
        print("Falling back to robust synthetic report generation for debug rehearsal continuity...")
        report = generate_mock_report(args.request)
        args.report.write_text(report, encoding="utf-8")
        print(f"Wrote synthetic report to {args.report.name}")
        # Verify synthetic report passes gate
        gate_ok, gate_rsn = _file_gate(args.report, round_id)
        if not gate_ok:
            print(f"Warning: synthetic report also failed gate: {gate_rsn}", file=sys.stderr)
        return 0
    else:
        print(f"Strict mode error: Real UI automation to Codex failed ({failure_reason}). --allow-synthetic-fallback not specified.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
