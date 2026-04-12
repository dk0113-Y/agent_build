#!/usr/bin/env python
"""
Bounded closed-loop rehearsal controller for DRL_automatic.
Runs a finite number of rounds, simulating the codex analysis and GPT decision
process to verify pipeline convergence onto a synthetic optimum.
"""
import argparse
import sys
import subprocess
import json
import random
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser("Rehearsal Loop Controller")
    parser.add_argument("--max-rounds", type=int, default=4)
    parser.add_argument("--exchange-repo", type=Path, default=Path("../RRL_test"))
    
    # Modes
    parser.add_argument("--strict", action="store_true", default=True, help="Halt exactly when a real bridge link fails.")
    parser.add_argument("--no-strict", action="store_false", dest="strict", help="Disable strict error halting.")
    parser.add_argument("--allow-synthetic-codex-fallback", action="store_true", help="Allow codex analysis to mock if UI absent.")
    parser.add_argument("--allow-synthetic-gpt-fallback", action="store_true", help="Allow GPT json to mock if Web bridge absent.")
    parser.add_argument("--gpt-profile-dir", type=Path, help="Persistent browser profile dir for real ChatGPT loop.")
    return parser.parse_args()

def main():
    args = parse_args()
    rounds_dir = Path("automation_rounds")
    rounds_dir.mkdir(exist_ok=True)
    
    # 1. Prepare starter round
    start_round_id = "round_0001"
    start_round_dir = rounds_dir / start_round_id
    start_decision = start_round_dir / "gpt_decision.json"
    
    if not start_decision.exists():
        start_round_dir.mkdir(parents=True, exist_ok=True)
        starter_data = {
            "schema_version": "1.0",
            "round_id": start_round_id,
            "decision_status": "run_next_round",
            "target_program": "fake_train.py",
            "run_args": {
                "turn_penalty": 0.04,
                "revisit_penalty": 0.12,
                "entry_k": 6,
                "steps": 24,
                "sleep_sec": 0.01,
                "seed": 7
            },
            "parameter_changes": [],
            "codex_analysis_focus": {
                "compare_targets": [],
                "required_logs": ["logs/train_steps.csv", "logs/eval_metrics.csv"],
                "required_plots": ["plots/reward_curve.png", "plots/coverage_curve.png"],
                "questions": ["How far are we from target?"],
                "expected_output_style": "Write a structured markdown report."
            },
            "reference_targets": {"best_known_reference": "", "manual_compare_targets": []},
            "controller_notes": "Initial synthetic starter for rehearsal."
        }
        start_decision.write_text(json.dumps(starter_data, indent=2), "utf-8")
        
    current_round_id = start_round_id
    
    summary = {
        "rounds_run": 0,
        "gpt_profile_dir": str(args.gpt_profile_dir.resolve()) if args.gpt_profile_dir else "",
        "gpt_profile_mode": "persistent_profile" if args.gpt_profile_dir else "ephemeral_context",
        "round_log": [],
        "stop_reason": "",
        "success": False
    }

    if args.strict and not args.gpt_profile_dir:
        print("Error: strict mode requires --gpt-profile-dir for a persistent logged-in ChatGPT session.", file=sys.stderr)
        summary["stop_reason"] = "missing_gpt_profile_in_strict_mode"
        print("\n=== Rehearsal Summary ===")
        print(json.dumps(summary, indent=2))
        Path("rehearsal_summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
        sys.exit(1)
    elif not args.gpt_profile_dir:
        print("Warning: Running without --gpt-profile-dir. GPT bridge will use ephemeral context without login state.", file=sys.stderr)

    try:
        for i in range(args.max_rounds):
            print(f"\n=== Starting Rehearsal Round {i+1}/{args.max_rounds}: {current_round_id} ===")
            round_dir = rounds_dir / current_round_id
            decision_file = round_dir / "gpt_decision.json"
            
            # Step 2: scheduler
            print("=> Running scheduler...")
            res = subprocess.run([sys.executable, "scheduler.py", "--decision-file", str(decision_file)])
            if res.returncode != 0:
                summary["stop_reason"] = "scheduler_failed"
                break
                
            state_file = round_dir / "round_state.json"
            if not state_file.exists():
                summary["stop_reason"] = "missing_round_state"
                break
                
            state = json.loads(state_file.read_text("utf-8"))
            run_dir = Path(state["run_dir"])
            
            # Check oracle
            truth_file = run_dir / "synthetic_truth.json"
            truth = json.loads(truth_file.read_text("utf-8"))
            decision_data = json.loads(decision_file.read_text("utf-8"))
            
            run_log = {
                "round_id": current_round_id,
                "run_dir": str(run_dir),
                "params": decision_data.get("run_args", {}),
                "distance": truth.get("current_distance", {}),
                "target_reached": truth.get("target_reached"),
                "used_real_codex": False,
                "codex_bridge_output_json": "",
                "codex_bridge_status": "",
                "codex_bridge_reply_detected": False,
                "triggered_synthetic_codex_fallback": False,
                "used_real_gpt": False,
                "triggered_synthetic_gpt_fallback": False,
                "synthetic_gpt_fallback_strategy": "",
                "gpt_profile_dir": summary["gpt_profile_dir"],
                "gpt_profile_mode": summary["gpt_profile_mode"],
                "publish_pushed": False,
            }
            summary["round_log"].append(run_log)
            summary["rounds_run"] += 1
            
            if truth.get("target_reached"):
                print(">>> Synthetic Truth reports optimal area reached! <<<")
                summary["stop_reason"] = "target_reached"
                summary["success"] = True
                break
            
            # Step 4: Codex
            print("=> Running Codex analysis...")
            req_file = round_dir / "codex_request.md"
            rep_file = round_dir / "codex_report.md"
            
            bridge_out_json = Path("tmp") / f"codex_bridge_out_{current_round_id}.json"
            if bridge_out_json.exists():
                bridge_out_json.unlink()
            
            codex_cmd = [sys.executable, "codex_roundtrip_bridge.py", "--request", str(req_file), "--report", str(rep_file), "--output-json", str(bridge_out_json)]
            if args.allow_synthetic_codex_fallback:
                codex_cmd.append("--allow-synthetic-fallback")
                
            res = subprocess.run(codex_cmd)
            
            run_log["codex_bridge_output_json"] = str(bridge_out_json)
            real_codex_worked = False
            
            if bridge_out_json.exists():
                b_data = json.loads(bridge_out_json.read_text("utf-8"))
                run_log["codex_bridge_status"] = b_data.get("status", "")
                has_reply = bool(b_data.get("reply_text", "").strip())
                run_log["codex_bridge_reply_detected"] = has_reply
                if b_data.get("success", False) and has_reply:
                    real_codex_worked = True
            
            if res.returncode != 0:
                summary["stop_reason"] = "codex_bridge_failed"
                print("Codex bridge strictly failed.")
                break
                
            if real_codex_worked:
                run_log["used_real_codex"] = True
            else:
                run_log["triggered_synthetic_codex_fallback"] = True
                print("Warning: Used synthetic codex fallback.")
                if args.strict and not args.allow_synthetic_codex_fallback:
                    summary["stop_reason"] = "codex_bridge_fallback_used_but_forbidden"
                    break
            
            # Step 5: prepare_gpt_input
            print("=> prepare_gpt_input...")
            res = subprocess.run([sys.executable, "prepare_gpt_input.py", "--round-id", current_round_id])
            if res.returncode != 0:
                summary["stop_reason"] = "prepare_gpt_input_failed"
                break
            
            # Step 6: publish
            print("=> publish to exchange (commit and push)...")
            res = subprocess.run([sys.executable, "publish_round_to_exchange.py", "--round-id", current_round_id, "--exchange-repo-dir", str(args.exchange_repo), "--repo-url", "https://github.com/dk0113-Y/RRL_test", "--force", "--commit", "--push"])
            if res.returncode != 0:
                summary["stop_reason"] = "publish_failed"
                break
            run_log["publish_pushed"] = True
                
            # Step 7: GPT bridge
            print("=> GPT bridge...")
            next_json_path = Path("tmp") / f"next_real_decision_{current_round_id}.json"
            
            # Attempt real exchange bridge
            bridge_cmd = [sys.executable, "exchange_web_bridge.py", "--round-id", current_round_id, "--exchange-repo-dir", str(args.exchange_repo), "--headless", "true"]
            if args.gpt_profile_dir:
                bridge_cmd.extend(["--profile-dir", str(args.gpt_profile_dir)])
                
            res = subprocess.run(bridge_cmd)
            
            if res.returncode != 0 and not next_json_path.exists():
                print("GPT Web bridge failed.")
                if not args.allow_synthetic_gpt_fallback:
                    print("Strict Mode: Rehearsal halted due to missing GPT API response/Playwright failure.")
                    summary["stop_reason"] = "gpt_bridge_failed_strictly"
                    break
                    
                print("Fallback enabled. Generating mock GPT decision...")
                run_log["triggered_synthetic_gpt_fallback"] = True
                run_log["synthetic_gpt_fallback_strategy"] = "neutral_local_perturbation"
                prev_dec = json.loads(decision_file.read_text("utf-8"))
                args_run = prev_dec.get("run_args", {})
                
                # Dynamic neutral local perturbation without pointing towards optimum
                turn = max(0.00, round(args_run.get("turn_penalty", 0.04) + random.uniform(-0.01, 0.01), 3))
                rev = max(0.00, round(args_run.get("revisit_penalty", 0.12) + random.uniform(-0.02, 0.02), 3))
                entry = max(1, args_run.get("entry_k", 6) + random.choice([-1, 0, 1]))
                
                next_dec = {
                    "schema_version": "1.0",
                    "round_id": "round_xxxx",
                    "decision_status": "run_next_round",
                    "target_program": "fake_train.py",
                    "run_args": {
                        "turn_penalty": turn,
                        "revisit_penalty": rev,
                        "entry_k": entry,
                        "steps": 24,
                        "sleep_sec": 0.01,
                        "seed": 7
                    },
                    "parameter_changes": [{"name": "parameters", "old_value": 0, "new_value": 1, "delta": 1, "reason": "Iterative exploratory adjustments based on synthetic debug fallback."}],
                    "codex_analysis_focus": {"compare_targets": [], "required_logs": [], "required_plots": [], "questions": [], "expected_output_style": "markdown"},
                    "reference_targets": {"best_known_reference": "", "manual_compare_targets": []},
                    "controller_notes": "Synthetic automatic ingest."
                }
                next_json_path.parent.mkdir(exist_ok=True)
                next_json_path.write_text(json.dumps(next_dec, indent=2), "utf-8")
                
                print("=> Ingesting synthetic debug decision...")
            else:
                run_log["used_real_gpt"] = True
                print("=> Ingesting real GPT decision...")
                
            res_ing = subprocess.run([sys.executable, "ingest_exchange_decision.py", "--input-file", str(next_json_path), "--source-round-id", current_round_id, "--exchange-repo-dir", str(args.exchange_repo)])
            if res_ing.returncode != 0:
                summary["stop_reason"] = "ingest_failed"
                break
            
            # Find next round
            states = [json.loads(p.read_text("utf-8")) for p in rounds_dir.glob("*/round_state.json")]
            new_states = sorted([s for s in states if s.get("source_round_id") == current_round_id], key=lambda x: x["round_id"])
            if not new_states:
                summary["stop_reason"] = "next_round_not_created"
                break
            
            current_round_id = new_states[-1]["round_id"]
            
        else: # for-else
            summary["stop_reason"] = "max_rounds_reached"
            
    except Exception as e:
        summary["stop_reason"] = f"unhandled_exception: {e}"
        
    print("\n=== Rehearsal Summary ===")
    print(json.dumps(summary, indent=2))
    Path("rehearsal_summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    if summary["stop_reason"] not in ("target_reached", "max_rounds_reached") and args.strict:
        sys.exit(1)
    
if __name__ == "__main__":
    main()
