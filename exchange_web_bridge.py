#!/usr/bin/env python
"""
Exchange-Mode Web Bridge v2 for ChatGPT.
Automates sending index messages and capturing responses.
"""

import argparse
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
except ImportError:
    print("Error: playwright not installed. Run 'pip install playwright' and 'playwright install chromium'.")
    sys.exit(1)

def parse_args():
    parser = argparse.ArgumentParser(description="Exchange-Mode ChatGPT Web Bridge")
    parser.add_argument("--exchange-repo-dir", required=True, type=Path, help="Path to exchange repo clone.")
    parser.add_argument("--round-id", required=True, help="Round ID to bridge (e.g., round_0015).")
    parser.add_argument("--profile-dir", type=Path, help="Browser profile directory for login persistence.")
    parser.add_argument("--headless", type=str, default="false", help="Run browser in headless mode (true/false).")
    parser.add_argument("--manual-confirm-send", action="store_true", help="Wait for Enter before sending message.")
    parser.add_argument("--timeout-sec", type=int, default=120, help="Wait timeout for response.")
    parser.add_argument("--save-raw-reply", action="store_true", default=True, help="Save raw MD response to tmp/.")
    parser.add_argument("--save-json", action="store_true", default=True, help="Extract and save JSON to tmp/.")
    parser.add_argument("--ingest-after-extract", action="store_true", help="Automatically call ingest script after extraction.")
    parser.add_argument("--url", default="https://chatgpt.com", help="ChatGPT URL.")
    
    return parser.parse_args()

def run_bridge():
    args = parse_args()
    headless = args.headless.lower() == "true"
    round_id = normalize_round_id(args.round_id)
    
    # 1. Check message file
    msg_path = args.exchange_repo_dir / "outbox" / f"web_index_message_{round_id}.md"
    if not msg_path.exists():
        print(f"Error: Index message file not found: {msg_path}", file=sys.stderr)
        return 1
    
    msg_content = msg_path.read_text(encoding="utf-8")
    
    # 2. Browser interaction
    with sync_playwright() as p:
        if args.profile_dir:
            profile_dir = str(args.profile_dir.resolve())
            context = p.chromium.launch_persistent_context(
                profile_dir,
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
        else:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()

        page = context.new_page()
        print(f"Navigating to {args.url}...")
        page.goto(args.url)

        try:
            page.wait_for_selector('textarea[id="prompt-textarea"]', timeout=30000)
            print("Chat interface detected.")
        except TimeoutError:
            print("Timeout waiting for chat interface. Please ensure you are logged in.", file=sys.stderr)
            if not headless:
                print("Waiting for manual login/interaction...")
                page.wait_for_selector('textarea[id="prompt-textarea"]', timeout=300000)
            else:
                return 1

        print("Filling message...")
        textarea = page.locator('textarea[id="prompt-textarea"]')
        textarea.fill(msg_content)

        if args.manual_confirm_send:
            input("Message filled. Press Enter in this console to send...")

        print("Sending message...")
        send_button = page.locator('button[data-testid="send-button"], button[data-testid="fruitjuice-send-button"]')
        send_button.click()

        print("Waiting for response...")
        start_time = time.time()
        completed = False
        time.sleep(3) # Initial wait for generation to start
        
        while time.time() - start_time < args.timeout_sec:
            is_generating = page.locator('button[data-testid="stop-button"], button[aria-label="Stop generating"]').is_visible()
            if not is_generating:
                time.sleep(3) # Wait for stability
                if not page.locator('button[data-testid="stop-button"], button[aria-label="Stop generating"]').is_visible():
                    completed = True
                    break
            time.sleep(1)

        if not completed:
            print("Timeout waiting for response completion.", file=sys.stderr)
            return 1

        print("Extracting response...")
        assistant_messages = page.locator('div.agent-turn, div[data-message-author-role="assistant"]')
        last_message = assistant_messages.last()
        raw_text = last_message.inner_text()
        
        if not raw_text.strip():
            print("Error: Empty response extracted.", file=sys.stderr)
            return 1

        # 3. Save and Process
        tmp_dir = repo_root() / "tmp"
        tmp_dir.mkdir(exist_ok=True)
        
        raw_reply_path = tmp_dir / f"{round_id}_gpt_reply.md"
        raw_reply_path.write_text(raw_text, encoding="utf-8")
        print(f"raw_reply_path={raw_reply_path}")

        if args.save_json:
            json_str = extract_json_block(raw_text)
            if not json_str:
                print("Error: Could not extract JSON from reply.", file=sys.stderr)
                return 1
            
            try:
                # Validate JSON syntax
                payload = json.loads(json_str)
                json_output_path = tmp_dir / f"next_real_decision_{round_id}.json"
                from automation_protocol import write_json_file
                write_json_file(json_output_path, payload)
                print(f"json_output_path={json_output_path}")
            except Exception as e:
                print(f"Error during JSON processing: {e}", file=sys.stderr)
                return 1

            if args.ingest_after_extract:
                print(f"Calling ingest_exchange_decision.py for {round_id}...")
                import subprocess
                cmd = [
                    sys.executable,
                    str(repo_root() / "ingest_exchange_decision.py"),
                    "--input-file", str(json_output_path),
                    "--source-round-id", round_id,
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
