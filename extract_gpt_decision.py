#!/usr/bin/env python
"""
Extract gpt_decision.json from a GPT response file.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from automation_protocol import (
    ProtocolError,
    load_decision_file,
    normalize_round_id,
    rounds_root,
    write_json_file,
)

def parse_args():
    parser = argparse.ArgumentParser(description="Extract decision JSON from GPT response")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--round-id", help="Round ID (e.g., round_0013 or 13)")
    group.add_argument("--response-file", type=Path, help="Path to gpt_decision_response.md")
    
    parser.add_argument("--output-file", type=Path, help="Path to save next_gpt_decision.json")
    
    return parser.parse_args()

def extract_json_block(text: str) -> str:
    # 1. Try to find between markers
    marker_match = re.search(r"DECISION_JSON_BEGIN\s*(.*?)\s*DECISION_JSON_END", text, re.DOTALL | re.IGNORECASE)
    if marker_match:
        content = marker_match.group(1).strip()
        # Find json block inside markers if present
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if json_match:
            return json_match.group(1).strip()
        return content

    # 2. Try to find any json code block
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if json_match:
        return json_match.group(1).strip()

    # 3. Try to find any markdown code block
    code_match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if code_match:
        return code_match.group(1).strip()

    # 4. Try to find something that looks like a JSON object
    object_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if object_match:
        return object_match.group(1).strip()

    return ""

def main():
    args = parse_args()
    
    if args.response_file:
        response_path = args.response_file
    else:
        rid = normalize_round_id(args.round_id)
        response_path = rounds_root() / rid / "gpt_decision_response.md"
    
    if not response_path.exists():
        print(f"Error: Response file not found: {response_path}")
        return 1
    
    output_path = args.output_file
    if not output_path:
        output_path = response_path.parent / "next_gpt_decision.json"

    print(f"Reading response from: {response_path}")
    text = response_path.read_text(encoding="utf-8")
    
    json_str = extract_json_block(text)
    if not json_str:
        print("Error: Could not extract JSON block from response.")
        return 1
    
    try:
        # Save temporary file for validation
        temp_file = output_path.with_suffix(".temp.json")
        try:
            payload = json.loads(json_str)
            write_json_file(temp_file, payload)
        except json.JSONDecodeError as e:
            print(f"Error: Extracted text is not valid JSON: {e}")
            return 1
        
        # Validate against protocol
        try:
            print("Validating JSON against protocol...")
            load_decision_file(temp_file)
            print("Validation successful.")
        except ProtocolError as e:
            print(f"Error: JSON failed protocol validation: {e}")
            # Keep the bad JSON for debugging? The user said "明确报错"
            temp_file.unlink()
            return 1
        
        # Rename temp to final
        if output_path.exists():
            output_path.unlink()
        temp_file.rename(output_path)
        print(f"Decision JSON saved to: {output_path}")

    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
