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
except ImportError:
    print("Error: playwright not installed. Run 'pip install playwright' and 'playwright install chromium'.")
    sys.exit(1)

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
    parser.add_argument("--timeout-sec", type=int, default=120, help="Wait timeout for response.")
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

            prompt_locator, matched_selector = wait_for_prompt(page, timeout_ms=30000)
            if not prompt_locator:
                print("Error: Could not find prompt interface.", file=sys.stderr)
                if not headless:
                    print("Waiting for manual login/interaction...")
                    prompt_locator, matched_selector = wait_for_prompt(page, timeout_ms=300000)
                
                if not prompt_locator:
                    return 1

            print(f"Filling message using {matched_selector}...")
            prompt_locator.fill(msg_content)

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

            # Save raw reply (standard behavior)
            raw_reply_path.write_text(raw_text, encoding="utf-8")
            print(f"raw_reply_path={raw_reply_path}")

    # 3. Save and Process JSON (standard behavior)
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
