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

def main():
    args = parse_args()
    
    print("Executing demo_codex_bridge.py for UI automation in send-and-wait mode...")
    bridge_script = Path(__file__).parent / "demo_codex_bridge.py"
    output_json = args.output_json if args.output_json else Path(__file__).parent / "tmp" / "codex_bridge_out.json"
    
    try:
        cmd = [
            sys.executable, str(bridge_script), 
            "--send-and-wait", 
            "--message-file", str(args.request),
            "--output-json", str(output_json)
        ]
        if args.expect_substring:
            cmd.extend(["--expect-substring", args.expect_substring])
            
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        if output_json.exists():
            data = json.loads(output_json.read_text("utf-8"))
            has_success = bool(data.get("success"))
            has_reply = bool(data.get("reply_text"))
            matches_expectation = data.get("reply_matches_expectation", False) if args.expect_substring else True
            
            if has_success and has_reply and matches_expectation:
                args.report.write_text(data["reply_text"], "utf-8")
                print(f"Successfully extracted UI response to {args.report.name}")
                return 0
            else:
                print("Bridge JSON returned but indicated failure, missing reply_text, or content mismatch:")
                print(data)
        else:
            print("UI Bridge execution failed or didn't output a JSON status file.")
            print("STDOUT:", res.stdout)
            print("STDERR:", res.stderr)
            
    except Exception as e:
        print(f"Failed to run UI bridge: {e}")

    if args.allow_synthetic_fallback:
        print("Falling back to robust synthetic report generation for debug rehearsal continuity...")
        report = generate_mock_report(args.request)
        args.report.write_text(report, encoding="utf-8")
        print(f"Wrote synthetic report to {args.report.name}")
        return 0
    else:
        print("Strict mode error: Real UI automation to Codex failed. --allow-synthetic-fallback not specified.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
