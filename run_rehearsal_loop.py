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
    parser.add_argument("--gpt-headless", action="store_true", default=False, help="Run GPT bridge in headless mode. Default: False (headed, matching hand-test path).")
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
            "schema_version": "2.0",
            "round_id": start_round_id,
            "experiment_mode": "synthetic_rehearsal",
            "source_of_truth_repo": str(Path(".").resolve()),
            "decision_status": "run_next_round",
            "evaluation_mode": "synthetic_oracle",
            "comparability_group": "synthetic_rehearsal_demo_v1",
            "baseline_round_id": None,
            "baseline_commit_sha": None,
            "decision_zone": "promotion_candidate",
            "stop_window_state": {"recommended_action": "run_next_round"},
            "manual_review_reasons": [],
            "insufficient_evidence_flags": [],
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
        "gpt_headless": args.gpt_headless,
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
            if decision_file.exists():
                decision_data = json.loads(decision_file.read_text("utf-8"))
                decision_status = decision_data.get("decision_status", "run_next_round")
                if decision_status == "stop_experiment":
                    summary["stop_reason"] = "gpt_requested_stop"
                    summary["success"] = True
                    print("GPT requested to stop the experiment. Halting controller gracefully.")
                    break
                elif decision_status == "pause_for_manual_review":
                    summary["stop_reason"] = "gpt_requested_manual_review"
                    summary["success"] = True
                    print("GPT requested pause for manual review. Halting controller gracefully.")
                    break
                elif decision_status == "analyze_only":
                    summary["stop_reason"] = "analyze_only_not_supported_in_main_loop"
                    print("analyze_only is not supported by this rehearsal loop. Halting.")
                    break

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
            truth = json.loads(truth_file.read_text("utf-8")) if truth_file.exists() else {}
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
                "codex_output_gate_passed": False,
                "codex_report_nonempty": False,
                "codex_output_gate_reason": "",
                "used_real_gpt": False,
                "triggered_synthetic_gpt_fallback": False,
                "synthetic_gpt_fallback_strategy": "",
                "gpt_output_gate_passed": False,
                "gpt_decision_schema_valid": False,
                "gpt_output_gate_reason": "",
                "ingest_output_gate_passed": False,
                "ingest_output_gate_reason": "",
                "gpt_profile_dir": summary["gpt_profile_dir"],
                "gpt_profile_mode": summary["gpt_profile_mode"],
                "gpt_headless": summary["gpt_headless"],
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
            codex_gate_passed = False
            codex_gate_reason = "bridge_not_run"
            codex_report_nonempty = False
            codex_report_ready = False
            codex_report_ready_reason = ""
            codex_send_delivery_state = ""
            codex_send_ui_confirmation_state = ""
            codex_send_ui_confirmation_reason = ""
            codex_send_confirmed_final = False
            codex_send_confirm_reason = ""
            codex_report_updated_after_send = False
            codex_ui_candidate_rejected = False
            codex_ui_candidate_reject_reason = ""
            bridge_success = False

            # --- Read output_json (file-first gate only needs success flag + file on disk) ---
            b_data: dict = {}
            if bridge_out_json.exists():
                try:
                    b_data = json.loads(bridge_out_json.read_text("utf-8"))
                    run_log["codex_bridge_status"] = b_data.get("status", "")
                    bridge_success = bool(b_data.get("success", False))
                    # Read diagnostic fields propagated from demo_codex_bridge
                    codex_send_delivery_state = b_data.get("send_delivery_state", "")
                    codex_send_ui_confirmation_state = b_data.get("send_ui_confirmation_state", "")
                    codex_send_ui_confirmation_reason = b_data.get("send_ui_confirmation_reason", "")
                    codex_send_confirmed_final = bool(b_data.get("send_confirmed", False))
                    codex_send_confirm_reason = b_data.get("send_confirm_reason", b_data.get("send_confirmation_reason", ""))
                    codex_report_updated_after_send = bool(b_data.get("report_updated_after_send", False))
                    codex_ui_candidate_rejected = bool(b_data.get("ui_candidate_rejected", False))
                    codex_ui_candidate_reject_reason = b_data.get("ui_candidate_reject_reason", "")
                    # Note: reply_text is no longer used as a success signal
                    run_log["codex_bridge_reply_detected"] = bool(b_data.get("reply_text", "").strip())
                except Exception as e:
                    codex_gate_reason = f"codex_output_json_parse_error: {e}"

            # --- File-first Codex gate ---
            # L1: output_json must exist and report bridge success
            # L2: codex_report.md must exist and be non-empty
            # L3: codex_report_is_ready() must pass
            if not bridge_out_json.exists():
                codex_gate_reason = "codex_output_json_missing"
            elif not bridge_success:
                # Discriminate sub-reason: send_not_confirmed is more specific than generic failure
                b_status = b_data.get("status", "") if bridge_out_json.exists() else ""
                delivery_state = b_data.get("send_delivery_state", "")
                
                if delivery_state == "failed":
                    reason_msg = b_data.get("send_ui_confirmation_reason") or codex_send_confirm_reason or b_status
                    codex_gate_reason = f"codex_send_failed: {reason_msg}"
                elif delivery_state == "pending_artifact_confirmation":
                    reason_msg = b_data.get("send_ui_confirmation_reason") or codex_send_confirm_reason or b_status
                    codex_gate_reason = f"codex_send_not_confirmed_by_ui_and_no_artifact: {reason_msg}"
                elif not codex_send_confirmed_final or b_status in ("send_not_confirmed",) or "send_not_confirmed" in b_status:
                    codex_gate_reason = f"codex_send_not_confirmed: {codex_send_confirm_reason or b_status}"
                else:
                    codex_gate_reason = "codex_bridge_returned_failure"
            else:
                rep_file_obj = round_dir / "codex_report.md"
                if not rep_file_obj.exists():
                    codex_gate_reason = "codex_report_file_missing"
                else:
                    report_on_disk = rep_file_obj.read_text("utf-8").strip()
                    codex_report_nonempty = bool(report_on_disk)
                    if not codex_report_nonempty:
                        codex_gate_reason = "codex_report_file_not_ready"
                    else:
                        try:
                            from automation_protocol import codex_report_is_ready
                            ready, ready_reason = codex_report_is_ready(current_round_id, report_on_disk)
                            codex_report_ready = ready
                            codex_report_ready_reason = ready_reason
                            if ready:
                                codex_gate_passed = True
                                codex_gate_reason = "ok"
                            else:
                                codex_gate_reason = f"codex_report_file_not_ready: {ready_reason}"
                        except Exception as e:
                            codex_gate_reason = f"codex_output_json_parse_error: {e}"

            run_log["codex_output_gate_passed"] = codex_gate_passed
            run_log["codex_report_nonempty"] = codex_report_nonempty
            run_log["codex_output_gate_reason"] = codex_gate_reason
            run_log["codex_report_ready"] = codex_report_ready
            run_log["codex_report_ready_reason"] = codex_report_ready_reason
            run_log["codex_send_delivery_state"] = codex_send_delivery_state
            run_log["codex_send_ui_confirmation_state"] = codex_send_ui_confirmation_state
            run_log["codex_send_ui_confirmation_reason"] = codex_send_ui_confirmation_reason
            run_log["codex_send_confirmed_final"] = codex_send_confirmed_final
            # Keep legacy field for compatibility but ensure it traces final state
            run_log["codex_send_confirmed"] = codex_send_confirmed_final
            run_log["codex_send_confirm_reason"] = codex_send_confirm_reason
            run_log["codex_report_updated_after_send"] = codex_report_updated_after_send
            run_log["codex_ui_candidate_rejected"] = codex_ui_candidate_rejected
            run_log["codex_ui_candidate_reject_reason"] = codex_ui_candidate_reject_reason

            # Bridge returncode is now only informational — gate is unconditional
            if res.returncode != 0 and not codex_gate_passed:
                summary["stop_reason"] = codex_gate_reason
                print(f"Codex bridge failed (returncode={res.returncode}). Gate reason: {codex_gate_reason}")
                break

            if not codex_gate_passed:
                summary["stop_reason"] = codex_gate_reason
                print(f"Codex artifact gate not satisfied: {codex_gate_reason}")
                break


            # Mark used_real_codex only when bridge reported success (not synthetic fallback)
            if bridge_success:
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
            headless_str = "true" if args.gpt_headless else "false"
            print(f"GPT bridge mode: headless={headless_str}")
            bridge_cmd = [sys.executable, "exchange_web_bridge.py", "--round-id", current_round_id, "--exchange-repo-dir", str(args.exchange_repo), "--headless", headless_str]
            if args.gpt_profile_dir:
                bridge_cmd.extend(["--profile-dir", str(args.gpt_profile_dir)])
                
            res = subprocess.run(bridge_cmd)
            
            # GPT output gate: next_real_decision json must exist, be parseable, and pass schema basics
            gpt_gate_passed = False
            gpt_gate_reason = "bridge_not_run"
            gpt_schema_valid = False
            
            gpt_reply_md = Path("tmp") / f"{current_round_id}_gpt_reply.md"
            if next_json_path.exists():
                try:
                    decision_candidate = json.loads(next_json_path.read_text("utf-8"))
                    required_keys = {"schema_version", "decision_status", "target_program", "run_args"}
                    if required_keys.issubset(decision_candidate.keys()):
                        gpt_schema_valid = True
                        # Optionally check raw reply file
                        if gpt_reply_md.exists() and not gpt_reply_md.read_text("utf-8").strip():
                            gpt_gate_reason = "gpt_reply_md_empty"
                        else:
                            gpt_gate_passed = True
                            gpt_gate_reason = "ok"
                    else:
                        gpt_gate_reason = "decision_json_missing_required_keys"
                except Exception as e:
                    gpt_gate_reason = f"decision_json_parse_failed: {e}"
            else:
                gpt_gate_reason = "next_real_decision_json_missing"
            
            run_log["gpt_output_gate_passed"] = gpt_gate_passed
            run_log["gpt_decision_schema_valid"] = gpt_schema_valid
            run_log["gpt_output_gate_reason"] = gpt_gate_reason
            
            # Unconditional GPT output gate — mirrors Codex gate; returncode is only informational
            if res.returncode != 0 and not gpt_gate_passed:
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

                turn = max(0.00, round(args_run.get("turn_penalty", 0.04) + random.uniform(-0.01, 0.01), 3))
                rev = max(0.00, round(args_run.get("revisit_penalty", 0.12) + random.uniform(-0.02, 0.02), 3))
                entry = max(1, args_run.get("entry_k", 6) + random.choice([-1, 0, 1]))

                next_dec = {
                    "schema_version": "2.0",
                    "round_id": "round_xxxx",
                    "experiment_mode": "synthetic_rehearsal",
                    "source_of_truth_repo": str(Path(".").resolve()),
                    "decision_status": "run_next_round",
                    "evaluation_mode": "synthetic_oracle",
                    "comparability_group": "synthetic_rehearsal_demo_v1",
                    "baseline_round_id": None,
                    "baseline_commit_sha": None,
                    "decision_zone": "promotion_candidate",
                    "stop_window_state": {"recommended_action": "run_next_round"},
                    "manual_review_reasons": [],
                    "insufficient_evidence_flags": [],
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
                # Re-evaluate gate after synthetic json was written
                if next_json_path.exists():
                    try:
                        _d = json.loads(next_json_path.read_text("utf-8"))
                        if {"schema_version", "decision_status", "target_program", "run_args"}.issubset(_d.keys()):
                            gpt_gate_passed = True
                            gpt_gate_reason = "ok_synthetic_fallback"
                            run_log["gpt_output_gate_passed"] = True
                            run_log["gpt_output_gate_reason"] = gpt_gate_reason
                    except Exception:
                        pass

            # Unconditional gate: even if bridge returned 0, artifact must satisfy gate before ingest
            if not gpt_gate_passed:
                summary["stop_reason"] = f"gpt_output_gate_failed: {gpt_gate_reason}"
                print(f"GPT artifact gate not satisfied: {gpt_gate_reason}")
                break

            # Gate passed — safe to proceed to ingest
            if run_log.get("triggered_synthetic_gpt_fallback"):
                print("=> Ingesting synthetic debug decision...")
            else:
                run_log["used_real_gpt"] = True
                print("=> Ingesting real GPT decision...")
                
            res_ing = subprocess.run([sys.executable, "ingest_exchange_decision.py", "--input-file", str(next_json_path), "--source-round-id", current_round_id, "--exchange-repo-dir", str(args.exchange_repo)])
            if res_ing.returncode != 0:
                summary["stop_reason"] = "ingest_failed"
                run_log["ingest_output_gate_reason"] = "ingest_returncode_nonzero"
                break
            
            # Ingest output gate: verify new round dir was actually created with valid lineage
            states_after = [json.loads(p.read_text("utf-8")) for p in rounds_dir.glob("*/round_state.json")]
            new_states = sorted([s for s in states_after if s.get("source_round_id") == current_round_id], key=lambda x: x["round_id"])
            if not new_states:
                run_log["ingest_output_gate_passed"] = False
                run_log["ingest_output_gate_reason"] = "next_round_not_created"
                summary["stop_reason"] = "next_round_not_created"
                break
            
            new_round_id = new_states[-1]["round_id"]
            new_round_dir = rounds_dir / new_round_id
            new_decision = new_round_dir / "gpt_decision.json"
            if not new_decision.exists():
                run_log["ingest_output_gate_passed"] = False
                run_log["ingest_output_gate_reason"] = f"gpt_decision_missing_in_new_round_{new_round_id}"
                summary["stop_reason"] = "next_round_not_created"
                break
            
            run_log["ingest_output_gate_passed"] = True
            run_log["ingest_output_gate_reason"] = "ok"
            current_round_id = new_round_id
            
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
