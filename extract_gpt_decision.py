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
    """
    Extracts JSON from text using markers and code blocks.
    Priority:
    1. Content between DECISION_JSON_BEGIN and DECISION_JSON_END
    2. First json code block
    3. First generic code block
    4. First curly-brace object
    """
    # 1. Try to find between markers
    marker_match = re.search(r"DECISION_JSON_BEGIN\s*(.*?)\s*DECISION_JSON_END", text, re.DOTALL | re.IGNORECASE)
    content = text
    if marker_match:
        print("Detected DECISION_JSON_BEGIN/END markers.")
        content = marker_match.group(1).strip()

    # 2. Try to find any json code block in the relevant content
    json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if json_match:
        return json_match.group(1).strip()

    # 3. Try to find any markdown code block
    code_match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
    if code_match:
        return code_match.group(1).strip()

    # 4. Try to find something that looks like a JSON object
    # We start from the first '{' and end at the last '}'
    start = content.find('{')
    end = content.rfind('}')
    if start != -1 and end != -1 and end > start:
        return content[start:end+1].strip()

    return ""

def main():
    args = parse_args()
    
    if args.response_file:
        response_path = args.response_file
    else:
        rid = normalize_round_id(args.round_id)
        response_path = rounds_root() / rid / "gpt_decision_response.md"
    
    if not response_path.exists():
        print(f"Error: Response file not found: {response_path}", file=sys.stderr)
        return 1
    
    output_path = args.output_file
    if not output_path:
        output_path = response_path.parent / "next_gpt_decision.json"

    print(f"Reading response from: {response_path}")
    try:
        text = response_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 1
    
    json_str = extract_json_block(text)
    if not json_str:
        print("Error: Could not extract any text segment that looks like a JSON block.", file=sys.stderr)
        return 1
    
    try:
        # Validate JSON syntax
        try:
            payload = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Error: Extracted text is not syntactically valid JSON: {e}", file=sys.stderr)
            print("--- Extracted text snippet ---")
            print(json_str[:200] + "..." if len(json_str) > 200 else json_str)
            return 1
        
        # Save temporary file for protocol validation
        temp_file = output_path.with_suffix(".temp.json")
        write_json_file(temp_file, payload)
        
        # Validate against protocol
        try:
            print("Validating JSON against protocol schema...")
            load_decision_file(temp_file)
            print("Validation successful.")
        except ProtocolError as e:
            print(f"Error: JSON failed protocol validation mapping: {e}", file=sys.stderr)
            if temp_file.exists():
                temp_file.unlink()
            return 1
        
        # Finalize
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
