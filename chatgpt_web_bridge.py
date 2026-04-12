#!/usr/bin/env python
"""
Web bridge for ChatGPT using Playwright.
This tool sends gpt_input.md to the ChatGPT web interface and saves the response.
"""

import argparse
import os
import sys
import time
from pathlib import Path

from automation_protocol import (
    GPT_INPUT_FILENAME,
    ProtocolError,
    normalize_round_id,
    rounds_root,
)

try:
    from playwright.sync_api import sync_playwright, TimeoutError
except ImportError:
    print("Error: playwright not installed. Please run 'pip install playwright' and 'playwright install chromium'")
    sys.exit(1)

def parse_args():
    parser = argparse.ArgumentParser(description="ChatGPT Web Bridge via Playwright")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--round-id", help="Round ID (e.g., round_0013 or 13)")
    group.add_argument("--input-file", type=Path, help="Path to gpt_input.md")
    
    parser.add_argument("--output-file", type=Path, help="Path to save gpt_decision_response.md")
    parser.add_argument("--headless", type=str, default="false", help="Run browser in headless mode (true/false)")
    parser.add_argument("--profile-dir", type=Path, help="Directory for browser profile (to reuse login)")
    parser.add_argument("--manual-confirm-send", action="store_true", help="Wait for manual confirmation before sending")
    parser.add_argument("--timeout-sec", type=int, default=120, help="Wait timeout for GPT response")
    parser.add_argument("--url", default="https://chatgpt.com", help="ChatGPT URL")
    
    return parser.parse_args()

def get_input_content(args):
    if args.input_file:
        input_path = args.input_file
    else:
        rid = normalize_round_id(args.round_id)
        input_path = rounds_root() / rid / GPT_INPUT_FILENAME
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    return input_path.read_text(encoding="utf-8"), input_path

def get_output_path(args, input_path):
    if args.output_file:
        return args.output_file
    return input_path.parent / "gpt_decision_response.md"

def wrap_prompt(content):
    template_path = Path(__file__).parent / "templates" / "gpt_web_prompt_wrapper.md"
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
        return template.replace("{{GPT_INPUT_CONTENT}}", content)
    return content

def run_bridge():
    args = parse_args()
    headless = args.headless.lower() == "true"
    
    try:
        content, input_path = get_input_content(args)
        output_path = get_output_path(args, input_path)
        prompt = wrap_prompt(content)
    except Exception as e:
        print(f"Error preparing input: {e}")
        return 1

    print(f"Target Input: {input_path}")
    print(f"Target Output: {output_path}")

    with sync_playwright() as p:
        # Use persistent context if profile_dir is provided
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

        # Wait for either the chat interface or login page
        try:
            # Check if we are at the chat interface
            page.wait_for_selector('textarea[id="prompt-textarea"]', timeout=30000)
            print("Chat interface detected.")
        except TimeoutError:
            print("Timeout waiting for 'prompt-textarea'. Please ensure you are logged in.")
            if not headless:
                print("Waiting for manual login or page load...")
                page.wait_for_selector('textarea[id="prompt-textarea"]', timeout=300000)
            else:
                return 1

        # Fill the prompt
        print("Filling prompt...")
        textarea = page.locator('textarea[id="prompt-textarea"]')
        textarea.fill(prompt)

        if args.manual_confirm_send:
            input("Prompt filled. Press Enter in this console to send...")

        # Click send
        print("Sending message...")
        send_button = page.locator('button[data-testid="send-button"], button[data-testid="fruitjuice-send-button"]')
        send_button.click()

        # Wait for response completion
        print("Waiting for response...")
        # Common patterns for "generating" state: 
        # 1. Presence of a "Stop" button: button[aria-label="Stop generating"]
        # 2. Absence of "Send" button (it becomes "Stop")
        # 3. Streaming class on last message
        
        # A simple robust way is to wait for the "Stop" button to appear and then disappear, 
        # or wait for the "Send" button to become enabled again.
        
        start_time = time.time()
        completed = False
        
        # Give it a moment to start
        time.sleep(2)
        
        while time.time() - start_time < args.timeout_sec:
            # Look for indicators of completion
            # Usually the send button becomes visible/enabled again
            is_sending = page.locator('button[data-testid="stop-button"], button[aria-label="Stop generating"]').is_visible()
            if not is_sending:
                # Double check with a small stabilizer wait
                time.sleep(3)
                if not page.locator('button[data-testid="stop-button"], button[aria-label="Stop generating"]').is_visible():
                    completed = True
                    break
            time.sleep(1)

        if not completed:
            print("Timeout waiting for response completion.")
            return 1

        # Extract the last response
        print("Extracting last response...")
        # Messages usually are in [data-testid^="conversation-turn-"]
        # The assistant messages have some specific role/class
        # We take the last one.
        
        assistant_messages = page.locator('div.agent-turn, div[data-message-author-role="assistant"]')
        last_message = assistant_messages.last()
        response_text = last_message.inner_text()

        if not response_text.strip():
            print("Error: Empty response extracted.")
            return 1

        print(f"Response received ({len(response_text)} chars). Saving to {output_path}...")
        output_path.write_text(response_text, encoding="utf-8")
        
        print("Success.")
        
        if not args.profile_dir:
            browser.close()
        else:
            context.close()

    return 0

if __name__ == "__main__":
    sys.exit(run_bridge())
