#!/usr/bin/env python
"""
Exchange-Mode Web Bridge v2 for ChatGPT.
Automates sending index messages and capturing responses.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from automation_protocol import (
    ProtocolError,
    normalize_round_id,
    repo_root,
    read_json_file,
)
from extract_gpt_decision import extract_json_block

try:
    from playwright.sync_api import sync_playwright, TimeoutError
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

def is_placeholder(text: str) -> bool:
    """Detect if the text is just an intermediate state/loading indicator."""
    t = text.strip()
    if not t:
        return True
    # Often placeholders are short sentences like 'Received app response', '正在思考', 'Analyzing...'
    if len(t) < 40 and ("思考" in t or "App" in t or "Received" in t or "response" in t or "Thought" in t or "Search" in t or "Analyz" in t):
        return True
    return False

def wait_for_prompt(page, timeout_ms=30000):
    """
    Wait for ChatGPT prompt input using a sequence of possible selectors.
    Returns (locator, selector_string) or (None, None).
    """
    selectors = [
        '#prompt-textarea',
        'textarea#prompt-textarea',
        'div#prompt-textarea[contenteditable="true"]',
        '[contenteditable="true"]#prompt-textarea'
    ]
    
    start_time = time.time()
    while (time.time() - start_time) * 1000 < timeout_ms:
        for selector in selectors:
            try:
                if page.locator(selector).is_visible():
                    print(f"Prompt selector matched: {selector}")
                    return page.locator(selector), selector
            except:
                continue
        time.sleep(0.5)
    
    # Failure logging
    print(f"Error: Timeout waiting for prompt interface after {timeout_ms}ms.", file=sys.stderr)
    print(f"Current URL: {page.url}", file=sys.stderr)
    print(f"Page Title: {page.title()}", file=sys.stderr)
    print("Selector scan results:", file=sys.stderr)
    for selector in selectors:
        try:
            count = page.locator(selector).count()
            visible = page.locator(selector).is_visible() if count > 0 else False
            print(f"  - {selector}: count={count}, visible={visible}", file=sys.stderr)
        except Exception as e:
            print(f"  - {selector}: error checking ({e})", file=sys.stderr)
    
    return None, None

def parse_args():
    parser = argparse.ArgumentParser(description="Exchange-Mode ChatGPT Web Bridge")
    parser.add_argument("--exchange-repo-dir", required=True, type=Path, help="Path to exchange repo clone.")
    parser.add_argument("--round-id", required=True, help="Round ID to bridge (e.g., round_0015).")
    parser.add_argument("--source-round-id", help="Optional source round ID for ingestion lineage.")
    parser.add_argument("--profile-dir", type=Path, help="Browser profile directory for login persistence.")
    parser.add_argument("--headless", type=str, default="false", help="Run browser in headless mode (true/false).")
    parser.add_argument("--manual-confirm-send", action="store_true", help="Wait for Enter before sending message.")
    parser.add_argument("--timeout-sec", type=int, default=300, help="Watchdog timeout seconds. Bridge succeeds only when output artifact is produced, not when this expires.")
    parser.add_argument("--extract-only", action="store_true", help="Only extract JSON from existing raw reply (skip browser).")
    parser.add_argument("--ingest-after-extract", action="store_true", help="Automatically call ingest script after extraction.")
    parser.add_argument("--url", default="https://chatgpt.com", help="ChatGPT URL.")
    
    return parser.parse_args()

def run_bridge():
    args = parse_args()
    headless = args.headless.lower() == "true"
    round_id = normalize_round_id(args.round_id)
    source_id = normalize_round_id(args.source_round_id) if args.source_round_id else round_id
    
    tmp_dir = repo_root() / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    raw_reply_path = tmp_dir / f"{round_id}_gpt_reply.md"
    
    raw_text = ""

    if args.extract_only:
        print(f"Extract-only mode enabled. Looking for {raw_reply_path}...")
        if not raw_reply_path.exists():
            print(f"Error: Raw reply file not found for extraction: {raw_reply_path}", file=sys.stderr)
            return 1
        raw_text = raw_reply_path.read_text(encoding="utf-8")
    else:
        # 1. Check message file
        msg_path = args.exchange_repo_dir / "outbox" / f"web_index_message_{round_id}.md"
        if not msg_path.exists():
            print(f"Error: Index message file not found: {msg_path}", file=sys.stderr)
            return 1
        
        msg_content = msg_path.read_text(encoding="utf-8")
        
        # 2. Browser interaction
        if not HAS_PLAYWRIGHT:
            print("Error: playwright not installed. Run 'pip install playwright' and 'playwright install chromium'.")
            sys.exit(1)
            
        with sync_playwright() as p:
            if args.profile_dir:
                profile_dir_path = args.profile_dir.resolve()
                profile_dir_path.mkdir(parents=True, exist_ok=True)
                profile_dir_str = str(profile_dir_path)
                print(f"using persistent profile: {profile_dir_str}")
                profile_mode = "persistent_profile"
                context = p.chromium.launch_persistent_context(
                    profile_dir_str,
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"]
                )
            else:
                print("Warning: no GPT profile dir specified; launching ephemeral browser context without login persistence.", file=sys.stderr)
                profile_mode = "ephemeral_context"
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context()

            page = context.new_page()
            print(f"Navigating to {args.url}...")
            page.goto(args.url)

            prompt_locator, matched_selector = wait_for_prompt(page, timeout_ms=30000)
            if not prompt_locator:
                error_msg = f"Error: Could not find prompt interface. URL: {page.url}. Suspected unlogged state/initial screen."
                print(error_msg, file=sys.stderr)
                if not headless:
                    print("Waiting for manual login/interaction...")
                    prompt_locator, matched_selector = wait_for_prompt(page, timeout_ms=300000)
                
                if not prompt_locator:
                    # Write debug stub to avoid black-holing
                    debug_info_early = {
                        "round_id": round_id,
                        "gpt_profile_mode": profile_mode,
                        "extract_error": error_msg,
                        "url_at_failure": page.url
                    }
                    debug_path = tmp_dir / f"{round_id}_gpt_bridge_debug.json"
                    from automation_protocol import write_json_file
                    write_json_file(debug_path, debug_info_early)
                    return 1

            print(f"Filling message using {matched_selector}...")
            prompt_locator.fill(msg_content)

            if args.manual_confirm_send:
                input("Message filled. Press Enter in this console to send...")

            assistant_messages = page.locator('div.agent-turn, div[data-message-author-role="assistant"]')
            initial_assistant_count = assistant_messages.count()
            
            debug_info = {
               "round_id": round_id,
               "gpt_profile_mode": profile_mode,
               "index_message_path": str(msg_path),
               "initial_assistant_count": initial_assistant_count,
               "final_assistant_count": initial_assistant_count,
               "stop_button_visible": False,
               "composer_editable": False,
               "last_text_length": 0,
               "last_candidate_text": "",
               "last_candidate_is_placeholder": True,
               "placeholder_only_seen": True,
               "assistant_count_increased": False,
               "generation_still_active_at_timeout": False,
               "completion_stage": "waiting_for_first_assistant_node",
               "marker_begin_found": False,
               "marker_end_found": False,
               "json_code_block_found": False,
               "completed": False,
               "completed_reason": "",
               "extract_error": ""
            }

            print("Sending message...")
            send_button = page.locator('button[data-testid="send-button"], button[data-testid="fruitjuice-send-button"]')
            send_button.click()

            print("Waiting for response...")
            start_time = time.time()
            completed = False
            completed_reason = ""
            time.sleep(2) # Initial wait for generation to start
            
            latest_text = ""
            best_candidate_text = ""
            best_candidate_length = 0
            stable_ticks = 0
            extra_grace_time_used = 0
            MAX_GRACE_TIME = 30
            completion_stage = "waiting_for_first_assistant_node"
            
            while time.time() - start_time < args.timeout_sec + extra_grace_time_used:
                current_count = assistant_messages.count()
                debug_info["final_assistant_count"] = current_count
                
                is_generating = page.locator('button[data-testid="stop-button"], button[aria-label="Stop generating"]').is_visible()
                debug_info["stop_button_visible"] = is_generating
                
                composer_editable = False
                try:
                    composer_editable = page.locator('#prompt-textarea, textarea#prompt-textarea, div#prompt-textarea[contenteditable="true"], [contenteditable="true"]#prompt-textarea').first.is_visible()
                except:
                    pass
                debug_info["composer_editable"] = composer_editable
                
                if current_count > initial_assistant_count:
                    debug_info["assistant_count_increased"] = True
                    current_candidates = []
                    
                    for k in range(initial_assistant_count, current_count):
                        try:
                            # Use inner_text without forcing timeout block
                            t = assistant_messages.nth(k).inner_text(timeout=200).strip()
                            current_candidates.append(t)
                        except:
                            pass
                            
                    if not current_candidates and current_count > 0:
                        try:
                            current_candidates.append(assistant_messages.last.inner_text(timeout=200).strip())
                        except:
                            pass
                    
                    current_best = ""
                    current_best_is_placeholder = True
                    for cand in current_candidates:
                        cand_placeholder = is_placeholder(cand)
                        if not cand_placeholder and current_best_is_placeholder:
                            current_best = cand
                            current_best_is_placeholder = False
                        elif cand_placeholder == current_best_is_placeholder:
                            if len(cand) > len(current_best):
                                current_best = cand
                                
                    latest_text = current_best
                    
                    if not current_best_is_placeholder:
                        debug_info["placeholder_only_seen"] = False
                        if len(current_best) > best_candidate_length:
                            best_candidate_text = current_best
                            best_candidate_length = len(current_best)
                    else:
                        if debug_info["placeholder_only_seen"]:
                            best_candidate_text = current_best
                            best_candidate_length = len(current_best)
                            
                    debug_info["last_candidate_text"] = best_candidate_text
                    debug_info["last_candidate_is_placeholder"] = current_best_is_placeholder
                else:
                    debug_info["last_candidate_text"] = ""
                    debug_info["last_candidate_is_placeholder"] = True
                    latest_text = ""

                debug_info["last_text_length"] = best_candidate_length
                has_begin = "DECISION_JSON_BEGIN" in latest_text
                has_end = "DECISION_JSON_END" in latest_text
                has_code = "```json" in latest_text
                
                debug_info["marker_begin_found"] = has_begin
                debug_info["marker_end_found"] = has_end
                debug_info["json_code_block_found"] = has_code
                
                # Check stages
                if not debug_info["assistant_count_increased"]:
                    completion_stage = "waiting_for_first_assistant_node"
                elif debug_info["placeholder_only_seen"]:
                    completion_stage = "waiting_for_substantive_content"
                    if is_generating and extra_grace_time_used < MAX_GRACE_TIME:
                        extra_grace_time_used += 1
                else:
                    completion_stage = "waiting_for_completion_after_substantive_content"
                
                # Try completion
                if completion_stage not in ["waiting_for_first_assistant_node", "waiting_for_substantive_content"]:
                    if has_begin and has_end and has_code:
                        completed = True
                        completed_reason = "markers_found_early_exit"
                        completion_stage = "ready_to_extract"
                        break
                        
                    if not is_generating:
                        stable_ticks += 1
                        if stable_ticks >= 3:
                            completed = True
                            completed_reason = "stable_ui_signals"
                            completion_stage = "ready_to_extract"
                            break
                    else:
                        stable_ticks = 0
                else:
                    stable_ticks = 0
                
                time.sleep(1)

            debug_info["completion_stage"] = completion_stage
            debug_info["generation_still_active_at_timeout"] = is_generating
            debug_info["completed"] = completed
            debug_info["completed_reason"] = completed_reason
            
            debug_path = tmp_dir / f"{round_id}_gpt_bridge_debug.json"
            from automation_protocol import write_json_file
            write_json_file(debug_path, debug_info)

            raw_text = best_candidate_text
            if raw_text:
                partial_path = tmp_dir / f"{round_id}_gpt_reply_last_visible.md"
                partial_path.write_text(raw_text, encoding="utf-8")

            if not completed:
                debug_info["extract_error"] = "watchdog_timeout_before_output_json"
                print(f"Error: {debug_info['extract_error']}. Debug state logged.", file=sys.stderr)
                return 1

            if current_count == 0 or not raw_text.strip():
                debug_info["extract_error"] = "reply_seen_but_output_not_extractable"
                print(f"Error: {debug_info['extract_error']}. URL: {page.url}", file=sys.stderr)
                write_json_file(debug_path, debug_info)
                return 1

            raw_reply_path.write_text(raw_text, encoding="utf-8")
            print(f"raw_reply_path={raw_reply_path}")

    # 3. Save and Process JSON (standard behavior)
    json_str = extract_json_block(raw_text)
    
    debug_path = tmp_dir / f"{round_id}_gpt_bridge_debug.json"
    if debug_path.exists():
        from automation_protocol import read_json_file
        debug_info = read_json_file(debug_path)
    else:
        debug_info = {}
        
    if not json_str:
        if not raw_text.strip():
            debug_info["extract_error"] = "No reply text available"
        elif "DECISION_JSON_BEGIN" not in raw_text:
            debug_info["extract_error"] = "No marker DECISION_JSON_BEGIN found"
        elif "DECISION_JSON_END" not in raw_text:
            debug_info["extract_error"] = "No marker DECISION_JSON_END found"
        else:
            debug_info["extract_error"] = "Markers found but no ```json ... ``` code block inside"
            
        print(f"Error: Extraction failed: {debug_info['extract_error']}", file=sys.stderr)
        from automation_protocol import write_json_file
        write_json_file(debug_path, debug_info)
        return 1
    
    try:
        payload = json.loads(json_str)
        json_output_path = tmp_dir / f"next_real_decision_{round_id}.json"
        from automation_protocol import write_json_file
        write_json_file(json_output_path, payload)
        print(f"json_output_path={json_output_path}")
        # Anchor: only verify success after output file is actually on disk
        if not json_output_path.exists():
            debug_info["extract_error"] = "reply_text_written_but_json_not_written"
            write_json_file(debug_path, debug_info)
            print(f"Error: {debug_info['extract_error']}", file=sys.stderr)
            return 1
    except Exception as e:
        debug_info["extract_error"] = f"reply_text_written_but_json_not_written: JSON parse failed: {e}"
        from automation_protocol import write_json_file
        write_json_file(debug_path, debug_info)
        print(f"Error during JSON processing: {e}", file=sys.stderr)
        return 1

    if args.ingest_after_extract:
        print(f"Calling ingest_exchange_decision.py for {round_id}...")
        import subprocess
        cmd = [
            sys.executable,
            str(repo_root() / "ingest_exchange_decision.py"),
            "--input-file", str(json_output_path),
            "--source-round-id", source_id,
            "--exchange-repo-dir", str(args.exchange_repo_dir)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(res.stdout)
        else:
            print(f"Ingest failed: {res.stderr}", file=sys.stderr)
            return 1

    return 0

if __name__ == "__main__":
    sys.exit(run_bridge())
