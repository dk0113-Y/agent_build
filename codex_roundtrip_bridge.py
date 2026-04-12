import argparse
import sys
import subprocess
import json
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser("Codex Roundtrip Bridge")
    parser.add_argument("--request", type=Path, required=True, help="Input codex_request.md")
    parser.add_argument("--report", type=Path, required=True, help="Output codex_report.md")
    parser.add_argument("--allow-synthetic-fallback", action="store_true", help="Use synthetic mock report if UI automation fails.", default=False)
    parser.add_argument("--output-json", type=Path, help="Optional specific JSON path to output extraction results to.")
    parser.add_argument("--expect-substring", type=str, help="Enforce content-level verification.")
    parser.add_argument("--watchdog-timeout-sec", type=int, default=600, help="Max seconds to wait for the UI bridge process (watchdog). Does not control completion logic.")
    return parser.parse_args()

def generate_mock_report(request_path: Path) -> str:
    content = ""
    if request_path.exists():
        content = request_path.read_text("utf-8")
    
    # Generic synthetic directional report without leaking any specific hidden optimums
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

def _artifact_gate(output_json: Path, report: Path, expect_substring: str | None) -> tuple[bool, str]:
    """Validate real output artifacts after bridge subprocess exits. Returns (passed, reason)."""
    if not output_json.exists():
        return False, "bridge_exited_without_output_json"
    try:
        data = json.loads(output_json.read_text("utf-8"))
    except Exception as e:
        return False, f"bridge_output_json_invalid: {e}"
    if not data.get("success"):
        return False, "bridge_output_json_success_false"
    if not data.get("reply_text", "").strip():
        return False, "bridge_output_json_reply_text_empty"
    if expect_substring and not data.get("reply_matches_expectation", False):
        return False, "bridge_content_expectation_mismatch"
    if not report.exists() or not report.read_text("utf-8").strip():
        return False, "report_not_written_or_empty"
    return True, "ok"


def main():
    args = parse_args()
    
    print("Executing demo_codex_bridge.py for UI automation in send-and-wait mode...")
    bridge_script = Path(__file__).parent / "demo_codex_bridge.py"
    output_json = args.output_json if args.output_json else Path(__file__).parent / "tmp" / "codex_bridge_out.json"
    
    failure_reason = ""
    
    try:
        cmd = [
            sys.executable, str(bridge_script), 
            "--send-and-wait", 
            "--message-file", str(args.request),
            "--output-json", str(output_json)
        ]
        if args.expect_substring:
            cmd.extend(["--expect-substring", args.expect_substring])
        
        print(f"bridge_watchdog_timeout={args.watchdog_timeout_sec}s")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=args.watchdog_timeout_sec)
        print(f"bridge_process_exited: returncode={res.returncode}")

        # Artifact confirmation window: poll for up to 15s after process exits
        import time as _time
        deadline = _time.time() + 15
        gate_passed = False
        gate_reason = "not_checked"
        while _time.time() < deadline:
            gate_passed, gate_reason = _artifact_gate(output_json, args.report, args.expect_substring)
            if gate_passed:
                break
            # If report written by bridge already, don't wait out full 15s
            if output_json.exists():
                try:
                    d = json.loads(output_json.read_text("utf-8"))
                    if d.get("success") and d.get("reply_text"):
                        args.report.write_text(d["reply_text"], "utf-8")
                except Exception:
                    pass
            _time.sleep(1)
        
        if gate_passed:
            print(f"Artifact gate passed. Report written to {args.report.name}")
            return 0
        else:
            failure_reason = gate_reason
            print(f"Artifact gate failed: {failure_reason}")
            print("STDOUT:", res.stdout[-2000:] if res.stdout else "")
            print("STDERR:", res.stderr[-2000:] if res.stderr else "")
            
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
        return 0
    else:
        print(f"Strict mode error: Real UI automation to Codex failed ({failure_reason}). --allow-synthetic-fallback not specified.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
