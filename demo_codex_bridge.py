#!/usr/bin/env python
"""
Local Codex UI bridge demo for Windows desktop automation.

Supported modes:
  python demo_codex_bridge.py --inspect-ui
  python demo_codex_bridge.py --send-only
  python demo_codex_bridge.py --demo
  python demo_codex_bridge.py --demo --manual-confirm-send

The demo deliberately avoids OpenAI APIs. It drives the local Codex desktop app
through Windows UI Automation plus a small amount of mouse/keyboard simulation.
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pyperclip
import uiautomation as auto

try:
    import ctypes
    from ctypes import wintypes
except Exception as exc:  # pragma: no cover
    raise RuntimeError("This demo requires Windows ctypes access.") from exc


USER32 = ctypes.windll.user32
SW_RESTORE = 9
VK_CONTROL = 0x11
VK_V = 0x56
VK_C = 0x43
VK_A = 0x41
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


@dataclass
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center_x(self) -> int:
        return self.left + self.width // 2

    @property
    def center_y(self) -> int:
        return self.top + self.height // 2

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
            "center_x": self.center_x,
            "center_y": self.center_y,
        }


@dataclass
class ControlSnapshot:
    depth: int
    control_type: str
    name: str
    automation_id: str
    rect: Rect | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth": self.depth,
            "control_type": self.control_type,
            "name": self.name,
            "automation_id": self.automation_id,
            "rect": None if self.rect is None else self.rect.to_dict(),
        }


@dataclass
class DemoResult:
    success: bool
    status: str
    message: str
    log_path: Path
    reply_text: str = ""
    sent_prompt: str = ""
    expected_token: str = ""
    sent_message_source: str = "ack"
    message_path: str = ""
    message_probe: str = ""
    send_confirmation_status: str = ""
    send_confirmation_reason: str = ""
    report_ready: bool = False
    report_ready_reason: str = ""
    ui_candidate_rejected: bool = False
    ui_candidate_reject_reason: str = ""


def load_config(config_path: Path) -> dict[str, Any]:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["config_path"] = str(config_path)
    return raw


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_token(prefix: str) -> str:
    rand = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"{prefix}::{now_ts()}::{rand}"


def build_prompt(token: str) -> str:
    return (
        "请忽略其它上下文，只回复下面这一行，不要添加任何其它内容：\n"
        f"{token}"
    )


def build_message_probe(message: str, max_chars: int = 80) -> str:
    generic_heading_prefixes = ("# ", "## ")
    generic_exact_lines = {
        "# Codex Analysis Request",
        "# GPT Input Package",
    }
    non_empty_lines = [raw_line.strip() for raw_line in message.splitlines() if raw_line.strip()]
    for candidate in non_empty_lines:
        if candidate in generic_exact_lines:
            continue
        if candidate.startswith(generic_heading_prefixes):
            continue
        return candidate[:max_chars]
    for candidate in non_empty_lines:
        return candidate[:max_chars]
    collapsed = " ".join(message.split())
    if not collapsed:
        raise RuntimeError("Could not derive a non-empty message probe.")
    return collapsed[:max_chars]


def load_message_override(message_file: Path | None, message_text: str | None) -> tuple[str | None, str, str]:
    if message_file is not None:
        text = message_file.read_text(encoding="utf-8")
        if not text.strip():
            raise RuntimeError(f"Message file was empty: {message_file}")
        return text, "file", str(message_file.resolve())
    if message_text is not None:
        if not message_text.strip():
            raise RuntimeError("Message text was empty.")
        return message_text, "text", ""
    return None, "ack", ""


def ensure_foreground(hwnd: int) -> None:
    USER32.ShowWindow(hwnd, SW_RESTORE)
    USER32.SetForegroundWindow(hwnd)
    time.sleep(0.4)


def key_event(vk: int, key_up: bool = False) -> None:
    USER32.keybd_event(vk, 0, KEYEVENTF_KEYUP if key_up else 0, 0)


def hotkey(*keys: int) -> None:
    for vk in keys:
        key_event(vk, False)
    time.sleep(0.05)
    for vk in reversed(keys):
        key_event(vk, True)
    time.sleep(0.1)


def press_enter() -> None:
    key_event(VK_RETURN, False)
    time.sleep(0.03)
    key_event(VK_RETURN, True)
    time.sleep(0.1)


def click_point(x: int, y: int) -> None:
    USER32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    USER32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    USER32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.15)


def rect_from_control(ctrl: auto.Control) -> Rect | None:
    try:
        rect = ctrl.BoundingRectangle
        return Rect(rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


class CodexBridge:
    def __init__(self, config: dict[str, Any], logs_dir: Path) -> None:
        self.config = config
        self.logs_dir = logs_dir
        self.window: auto.Control | None = None
        self.root: auto.Control | None = None

    def _window_match(self, title: str) -> bool:
        exact = (self.config.get("window_title_exact") or "").strip()
        keyword = (self.config.get("window_title_keyword") or "").strip().lower()
        if exact:
            return title == exact
        return keyword in title.lower()

    def enumerate_windows(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        get_text_length = USER32.GetWindowTextLengthW
        get_text = USER32.GetWindowTextW
        is_visible = USER32.IsWindowVisible

        def callback(hwnd: int, l_param: int) -> bool:
            if not is_visible(hwnd):
                return True
            length = get_text_length(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            get_text(hwnd, buf, length + 1)
            title = buf.value
            if not title:
                return True
            if self._window_match(title):
                results.append({"hwnd": int(hwnd), "title": title})
            return True

        USER32.EnumWindows(EnumWindowsProc(callback), 0)
        return results

    def _pick_best_window(self, matches: list[dict[str, Any]]) -> dict[str, Any]:
        exact = (self.config.get("window_title_exact") or "").strip()
        keyword = (self.config.get("window_title_keyword") or "").strip().lower()

        def score(item: dict[str, Any]) -> tuple[int, int, int]:
            title = item["title"]
            lower = title.lower()
            exact_match = int(bool(exact and title == exact))
            exact_codex = int(title == "Codex")
            keyword_pos = lower.find(keyword) if keyword else 10_000
            return (exact_match or exact_codex, -keyword_pos, -len(title))

        return sorted(matches, key=score, reverse=True)[0]

    def attach(self) -> None:
        matches = self.enumerate_windows()
        if not matches:
            raise RuntimeError("No visible Codex window matched the configured title.")
        best = self._pick_best_window(matches)
        title = best["title"]
        self.window = auto.WindowControl(searchDepth=1, Name=title)
        try:
            direct_root = self.window.DocumentControl(AutomationId="RootWebArea")
            if direct_root.Exists(3):
                self.root = direct_root
                return
        except Exception:
            pass
        self.root = self._find_root_web_area()
        if self.root is None:
            raise RuntimeError("RootWebArea was not found under the Codex window.")
        return

    def activate(self) -> None:
        matches = self.enumerate_windows()
        if not matches:
            raise RuntimeError("No visible Codex window matched the configured title.")
        ensure_foreground(self._pick_best_window(matches)["hwnd"])

    def inspect(self) -> dict[str, Any]:
        self.attach()
        assert self.window is not None
        assert self.root is not None
        snapshots: list[ControlSnapshot] = []
        queue: deque[tuple[auto.Control, int]] = deque([(self.root, 0)])
        max_nodes = int(self.config.get("inspect_max_nodes", 600))
        while queue and len(snapshots) < max_nodes:
            ctrl, depth = queue.popleft()
            try:
                children = ctrl.GetChildren()
            except Exception:
                continue
            for child in children:
                try:
                    snapshot = ControlSnapshot(
                        depth=depth + 1,
                        control_type=child.ControlTypeName,
                        name=child.Name or "",
                        automation_id=child.AutomationId or "",
                        rect=rect_from_control(child),
                    )
                except Exception:
                    continue
                if (
                    snapshot.control_type in {"ButtonControl", "EditControl", "TextControl", "ListItemControl"}
                    or snapshot.name
                    or snapshot.automation_id
                ):
                    snapshots.append(snapshot)
                queue.append((child, depth + 1))
                if len(snapshots) >= max_nodes:
                    break

        add_file = self._find_button_by_name(self.config["toolbar_anchor_button_name"])
        send_button = self._find_send_button(add_file)
        composer_rect = self._find_composer_rect(add_file, send_button)
        return {
            "window_matches": self.enumerate_windows(),
            "window_rect": None if self.window is None or rect_from_control(self.window) is None else rect_from_control(self.window).to_dict(),
            "root_rect": None if self.root is None or rect_from_control(self.root) is None else rect_from_control(self.root).to_dict(),
            "toolbar_anchor_button": self._ctrl_summary(add_file),
            "send_button": self._ctrl_summary(send_button),
            "composer_rect": None if composer_rect is None else composer_rect.to_dict(),
            "interesting_controls": [s.to_dict() for s in snapshots],
        }

    def maybe_new_thread(self) -> bool:
        if not self.config.get("create_new_thread_first", False):
            return False
        btn = self._find_button_by_name(self.config["new_thread_button_name"])
        if btn is None or not btn.Exists(1):
            return False
        try:
            btn.Click(simulateMove=False)
        except Exception:
            rect = rect_from_control(btn)
            if rect is None:
                return False
            click_point(rect.center_x, rect.center_y)
        time.sleep(self.config["after_new_thread_wait_sec"])
        self.root = self._find_root_web_area()
        return True

    def focus_composer(self) -> Rect:
        add_file = self._find_button_by_name(self.config["toolbar_anchor_button_name"])
        if add_file is None:
            raise RuntimeError("Could not find the toolbar anchor button near the composer.")
        send_button = self._find_send_button(add_file)
        composer_rect = self._find_composer_rect(add_file, send_button)
        if composer_rect is None:
            raise RuntimeError("Could not infer the Codex composer area.")
        click_point(composer_rect.center_x, composer_rect.center_y)
        return composer_rect

    def _try_click_send(self, send_method: str, send_button: auto.Control | None) -> str:
        """Attempt to send using the given method. Returns actual method used."""
        if send_method == "button":
            if send_button is not None:
                rect = rect_from_control(send_button)
                if rect is not None:
                    click_point(rect.center_x, rect.center_y)
                    return "button"
            # Fallback to Enter if button not found
            press_enter()
            return "enter_fallback"
        else:
            press_enter()
            return "enter"

    def send_prompt(
        self,
        prompt: str,
        manual_confirm_send: bool = False,
        message_probe: str | None = None,
    ) -> dict[str, Any]:
        """Send prompt with up to 3 attempts, alternating method on retry."""
        assert self.window is not None
        max_attempts = int(self.config.get("send_max_attempts", 3))
        retry_wait_sec = float(self.config.get("send_retry_wait_sec", 3.0))
        base_send_method = self.config.get("send_method", "button")
        alt_send_method = "enter" if base_send_method == "button" else "button"

        self.activate()
        self.maybe_scroll_to_bottom()
        composer_rect = self.focus_composer()
        pyperclip.copy(prompt)
        hotkey(VK_CONTROL, VK_V)
        time.sleep(self.config["after_paste_wait_sec"])

        probe_post_paste_count = None
        if message_probe:
            probe_post_paste_count, _, _ = self.count_token_in_ui(message_probe)

        send_button = self._find_send_button(self._find_button_by_name(self.config["toolbar_anchor_button_name"]))
        if manual_confirm_send:
            input("Prompt is pasted. Press Enter here to continue with send...")

        attempts_log: list[dict[str, Any]] = []

        for attempt_idx in range(max_attempts):
            # Choose method: first attempt uses config, subsequent attempts alternate
            if attempt_idx == 0:
                method = base_send_method
            elif attempt_idx % 2 == 1:
                method = alt_send_method
            else:
                method = base_send_method

            # Refresh send button on retries
            if attempt_idx > 0:
                try:
                    refreshed_root = self._find_root_web_area()
                    if refreshed_root is not None:
                        self.root = refreshed_root
                    send_button = self._find_send_button(
                        self._find_button_by_name(self.config["toolbar_anchor_button_name"])
                    )
                except Exception:
                    pass

                # Check if composer still has content; re-paste if empty or probe missing
                if message_probe:
                    composer_probe = self._probe_in_composer(composer_rect, message_probe)
                    composer_has_probe = composer_probe["probe_present"]
                else:
                    composer_probe = {"probe_present": True, "status": "no_probe_check"}
                    composer_has_probe = True

                if not composer_has_probe:
                    print(f"[send attempt {attempt_idx+1}] Composer missing probe — re-pasting prompt...")
                    self.focus_composer()
                    pyperclip.copy(prompt)
                    hotkey(VK_CONTROL, VK_V)
                    time.sleep(self.config["after_paste_wait_sec"])
                    if message_probe:
                        probe_post_paste_count, _, _ = self.count_token_in_ui(message_probe)
                else:
                    composer_probe = {"probe_present": True, "status": "probe_still_in_composer"}

            attempt_send_btn_summary = self._ctrl_summary(send_button)
            actual_method = self._try_click_send(method, send_button)
            time.sleep(self.config["after_send_wait_sec"])

            # Quick post-send probe check
            post_send_probe_count = None
            post_send_visible = None
            if message_probe:
                post_send_probe_count, _, post_texts = self.count_token_in_ui(message_probe)
                post_send_visible = len(post_texts)

            send_btn_after = self._ctrl_summary(
                self._find_send_button(self._find_button_by_name(self.config["toolbar_anchor_button_name"]))
            )

            attempt_log = {
                "attempt": attempt_idx + 1,
                "method": actual_method,
                "send_button_before": attempt_send_btn_summary,
                "send_button_after": send_btn_after,
                "post_send_probe_count": post_send_probe_count,
                "post_send_visible": post_send_visible,
            }
            attempts_log.append(attempt_log)
            print(f"[send attempt {attempt_idx+1}/{max_attempts}] method={actual_method} post_probe_count={post_send_probe_count}")

            # Early-exit check: if probe count already increased, we are done
            if (
                message_probe
                and post_send_probe_count is not None
                and probe_post_paste_count is not None
                and post_send_probe_count >= probe_post_paste_count + 1
            ):
                print(f"[send attempt {attempt_idx+1}] Early send confirmation by probe count — stopping retries.")
                break

            # Also stop if send button became unavailable (message likely accepted)
            if self._is_send_button_unavailable(send_btn_after):
                print(f"[send attempt {attempt_idx+1}] Send button became unavailable — stopping retries.")
                break

            if attempt_idx < max_attempts - 1:
                print(f"[send attempt {attempt_idx+1}] No immediate confirmation signal; waiting {retry_wait_sec}s before retry...")
                time.sleep(retry_wait_sec)

        return {
            "composer_rect": composer_rect.to_dict(),
            "send_button": self._ctrl_summary(send_button),
            "paste_completed": True,
            "send_attempted": True,
            "send_method": base_send_method,
            "message_probe_post_paste_count": probe_post_paste_count,
            "send_attempts_log": attempts_log,
            "send_attempts_count": len(attempts_log),
        }

    def maybe_scroll_to_bottom(self) -> None:
        btn = self._find_button_by_name(self.config["scroll_to_bottom_button_name"])
        if btn is None or not btn.Exists(1):
            return
        try:
            btn.Click(simulateMove=False)
        except Exception:
            rect = rect_from_control(btn)
            if rect is not None:
                click_point(rect.center_x, rect.center_y)
        time.sleep(0.2)

    def read_visible_text_controls(self) -> list[dict[str, Any]]:
        assert self.root is not None
        queue: deque[tuple[auto.Control, int]] = deque([(self.root, 0)])
        max_depth = int(self.config.get("max_tree_depth", 30))
        max_nodes = int(self.config.get("max_nodes_per_read", 5000))
        visited = 0
        texts: list[dict[str, Any]] = []
        while queue and visited < max_nodes:
            ctrl, depth = queue.popleft()
            visited += 1
            try:
                ctype = ctrl.ControlTypeName
            except Exception:
                ctype = ""
            try:
                name = ctrl.Name or ""
            except Exception:
                name = ""
            if ctype == "TextControl" and name:
                rect = rect_from_control(ctrl)
                texts.append(
                    {
                        "text": name,
                        "rect": None if rect is None else rect.to_dict(),
                        "depth": depth,
                    }
                )
            if depth >= max_depth:
                continue
            try:
                children = ctrl.GetChildren()
            except Exception:
                continue
            for child in children:
                queue.append((child, depth + 1))
        return texts

    def count_token_in_ui(self, token: str) -> tuple[int, list[str], list[dict[str, Any]]]:
        texts = self.read_visible_text_controls()
        matches = [item["text"] for item in texts if token in item["text"]]
        joined_count = sum(item["text"].count(token) for item in texts)
        return joined_count, matches, texts

    def wait_for_reply(self, token: str, baseline_count: int) -> tuple[bool, str, dict[str, Any]]:
        deadline = time.time() + float(self.config["ui_timeout_sec"])
        expected_count = baseline_count + 2
        last_snapshot: dict[str, Any] = {}
        while time.time() < deadline:
            refreshed_root = self._find_root_web_area()
            if refreshed_root is not None:
                self.root = refreshed_root
            self.maybe_scroll_to_bottom()
            count, matches, texts = self.count_token_in_ui(token)
            last_snapshot = {
                "token_occurrence_count": count,
                "matching_texts": matches,
                "visible_text_count": len(texts),
            }
            if count >= expected_count and matches:
                detected_reply_text = "\n".join(matches[-2:])
                return True, detected_reply_text, last_snapshot
            time.sleep(float(self.config["poll_interval_sec"]))

        if self.config.get("enable_clipboard_fallback", False):
            success, fallback_text, extra = self.clipboard_fallback(token, baseline_count)
            extra["ui_last_snapshot"] = last_snapshot
            return success, fallback_text, extra

        return False, "", last_snapshot

    def clipboard_fallback(self, token: str, baseline_count: int) -> tuple[bool, str, dict[str, Any]]:
        assert self.window is not None
        assert self.root is not None
        root_rect = rect_from_control(self.root)
        if root_rect is None:
            return False, "", {"fallback": "clipboard", "reason": "root_rect_unavailable"}
        transcript_x = root_rect.left + int(root_rect.width * 0.6)
        transcript_y = root_rect.top + int(root_rect.height * 0.55)
        click_point(transcript_x, transcript_y)
        hotkey(VK_CONTROL, VK_A)
        hotkey(VK_CONTROL, VK_C)
        time.sleep(0.2)
        text = pyperclip.paste() or ""
        count = text.count(token) if token else 0
        return (
            count >= baseline_count + 2 if token else bool(text),
            text,
            {
                "fallback": "clipboard",
                "clipboard_length": len(text),
                "token_occurrence_count": count,
            },
        )

    def wait_for_arbitrary_reply(self, baseline_visible_count: int, expect_substring: str | None = None, prompt: str | None = None) -> tuple[bool, str, dict[str, Any]]:
        deadline = time.time() + float(self.config.get("ui_timeout_sec", 30.0))
        last_count = baseline_visible_count
        stable_ticks = 0
        last_snapshot: dict[str, Any] = {}
        
        while time.time() < deadline:
            refreshed_root = self._find_root_web_area()
            if refreshed_root is not None:
                self.root = refreshed_root
            self.maybe_scroll_to_bottom()
            texts = self.read_visible_text_controls()
            current_count = len(texts)
            
            last_snapshot = {
                "visible_text_count": current_count,
                "baseline": baseline_visible_count
            }

            if current_count > baseline_visible_count:
                new_texts = texts[baseline_visible_count:]
                
                if expect_substring:
                    # If we have an expected substring, scan all new texts continuously. 
                    # If any contains it and it's not the prompt itself, we consider it a verified success immediately.
                    for item in new_texts:
                        if prompt and prompt.strip() in item["text"]:
                            continue
                        if expect_substring in item["text"]:
                            reply_text = item["text"]
                            last_snapshot["reply_matches_expectation"] = True
                            last_snapshot["expected_substring"] = expect_substring
                            return True, reply_text, last_snapshot
                
                # If we're not looking for a substring, or haven't found it yet, we wait for stability.
                if current_count == last_count:
                    stable_ticks += 1
                    if stable_ticks >= 4:  # roughly 2 seconds stable
                        
                        if expect_substring:
                            # Reached stability but never found expected substring => fail
                            last_snapshot["reply_matches_expectation"] = False
                            last_snapshot["expected_substring"] = expect_substring
                            last_snapshot["failure_reason"] = "Stable but expected substring not found in any new texts."
                            last_snapshot["candidate_text"] = new_texts[-1]["text"] if new_texts else ""
                            return False, last_snapshot["candidate_text"], last_snapshot
                        
                        # Filter to find the best candidate (not the prompt itself, reasonable length)
                        valid_candidates = []
                        for item in new_texts:
                            txt = item["text"]
                            if prompt and prompt in txt:
                                continue # skip echoing the prompt
                            if len(txt.strip()) > 3:
                                valid_candidates.append(txt)
                        
                        reply_text = valid_candidates[-1] if valid_candidates else (new_texts[-1]["text"] if new_texts else "")
                        return True, reply_text, last_snapshot
                else:
                    stable_ticks = 0
            
            last_count = current_count
            time.sleep(float(self.config.get("poll_interval_sec", 0.5)))

        # Timeout reached
        if self.config.get("enable_clipboard_fallback", False) and not expect_substring:
            success, fallback_text, extra = self.clipboard_fallback("", baseline_visible_count)
            extra["ui_last_snapshot"] = last_snapshot
            return True, fallback_text, extra

        if expect_substring:
            last_snapshot["reply_matches_expectation"] = False
            last_snapshot["expected_substring"] = expect_substring
            last_snapshot["failure_reason"] = "Timeout reached. Expected substring not found."

        return False, "", last_snapshot

    def confirm_message_delivery(
        self,
        *,
        message_probe: str,
        baseline_count: int,
        post_paste_count: int,
        composer_rect: Rect,
        report_path: Path | None = None,
        report_started_at: float | None = None,
        observation_window_sec: float = 8.0,
    ) -> dict[str, Any]:
        """
        Expanded send-confirmation with three evidence tiers:
          A (Strong)  : probe count increased after send
          B (Medium)  : send button unavailable + composer cleared of probe
          C (Weak)    : composer cleared of probe + report file appeared/updated
                        -> allows proceeding to file-first wait

        After the primary poll loop times out, a short observation window
        (observation_window_sec) is checked before giving up.
        """
        timeout_sec = float(self.config.get("send_confirmation_timeout_sec", 8.0))
        poll_sec = float(self.config.get("send_confirmation_poll_sec", 0.5))
        deadline = time.time() + timeout_sec
        last_count = post_paste_count
        last_matches: list[str] = []
        last_visible_count = 0
        last_send_button = self._ctrl_summary(
            self._find_send_button(self._find_button_by_name(self.config["toolbar_anchor_button_name"]))
        )

        def _report_file_updated() -> bool:
            """True if report_path exists and mtime > report_started_at."""
            if report_path is None or report_started_at is None:
                return False
            try:
                return report_path.exists() and report_path.stat().st_mtime > report_started_at
            except OSError:
                return False

        while time.time() < deadline:
            refreshed_root = self._find_root_web_area()
            if refreshed_root is not None:
                self.root = refreshed_root
            self.maybe_scroll_to_bottom()
            count, matches, texts = self.count_token_in_ui(message_probe)
            send_button_summary = self._ctrl_summary(
                self._find_send_button(self._find_button_by_name(self.config["toolbar_anchor_button_name"]))
            )
            send_button_unavailable = self._is_send_button_unavailable(send_button_summary)
            last_count = count
            last_matches = matches
            last_visible_count = len(texts)
            last_send_button = send_button_summary

            # Evidence A (Strong): probe count increased
            if count >= max(baseline_count + 1, post_paste_count + 1):
                return {
                    "success": True,
                    "status": "confirmed_by_probe_count_increase",
                    "reason": "Message probe appeared in visible UI text with a new post-send instance.",
                    "message_probe_post_send_count": count,
                    "post_send_matching_texts": matches,
                    "post_send_visible_text_count": len(texts),
                    "post_send_send_button": send_button_summary,
                    "composer_probe_status": "not_checked",
                    "evidence_tier": "A_strong",
                }

            # Evidence B (Medium): send button unavailable + composer cleared
            if send_button_unavailable:
                composer_probe = self._probe_in_composer(composer_rect, message_probe)
                if not composer_probe["probe_present"]:
                    status = (
                        "confirmed_by_button_unavailable_and_cleared_composer"
                        if composer_probe["status"] == "probe_not_present"
                        else "confirmed_by_button_unavailable_composer_empty"
                    )
                    return {
                        "success": True,
                        "status": status,
                        "reason": "Send button became unavailable and composer no longer contains message probe.",
                        "message_probe_post_send_count": count,
                        "post_send_matching_texts": matches,
                        "post_send_visible_text_count": len(texts),
                        "post_send_send_button": send_button_summary,
                        "composer_probe_status": composer_probe["status"],
                        "evidence_tier": "B_medium",
                    }

            # Evidence C (Weak, early): composer cleared + report file already updating
            composer_probe = self._probe_in_composer(composer_rect, message_probe)
            if not composer_probe["probe_present"] and _report_file_updated():
                return {
                    "success": True,
                    "status": "confirmed_by_composer_cleared_and_file_updating",
                    "reason": "Composer no longer contains message probe and report file has appeared/updated.",
                    "message_probe_post_send_count": count,
                    "post_send_matching_texts": matches,
                    "post_send_visible_text_count": len(texts),
                    "post_send_send_button": send_button_summary,
                    "composer_probe_status": composer_probe["status"],
                    "evidence_tier": "C_weak",
                }

            time.sleep(poll_sec)

        # --- Primary loop timed out; run short observation window ---
        obs_deadline = time.time() + observation_window_sec
        print(f"[confirm] Primary poll timeout; running {observation_window_sec}s observation window...")
        while time.time() < obs_deadline:
            time.sleep(1.0)
            refreshed_root = self._find_root_web_area()
            if refreshed_root is not None:
                self.root = refreshed_root
            count, matches, texts = self.count_token_in_ui(message_probe)
            send_button_summary = self._ctrl_summary(
                self._find_send_button(self._find_button_by_name(self.config["toolbar_anchor_button_name"]))
            )
            send_button_unavailable = self._is_send_button_unavailable(send_button_summary)
            last_count = count
            last_matches = matches
            last_visible_count = len(texts)
            last_send_button = send_button_summary

            # Evidence A
            if count >= max(baseline_count + 1, post_paste_count + 1):
                return {
                    "success": True,
                    "status": "confirmed_by_probe_count_increase_obs_window",
                    "reason": "Probe count increased during observation window.",
                    "message_probe_post_send_count": count,
                    "post_send_matching_texts": matches,
                    "post_send_visible_text_count": len(texts),
                    "post_send_send_button": send_button_summary,
                    "composer_probe_status": "not_checked",
                    "evidence_tier": "A_strong_obs",
                }

            # Evidence B
            if send_button_unavailable:
                composer_probe = self._probe_in_composer(composer_rect, message_probe)
                if not composer_probe["probe_present"]:
                    return {
                        "success": True,
                        "status": "confirmed_by_button_unavailable_obs_window",
                        "reason": "Send button unavailable and composer cleared during observation window.",
                        "message_probe_post_send_count": count,
                        "post_send_matching_texts": matches,
                        "post_send_visible_text_count": len(texts),
                        "post_send_send_button": send_button_summary,
                        "composer_probe_status": composer_probe["status"],
                        "evidence_tier": "B_medium_obs",
                    }

            # Evidence C
            composer_probe = self._probe_in_composer(composer_rect, message_probe)
            if not composer_probe["probe_present"] and _report_file_updated():
                return {
                    "success": True,
                    "status": "confirmed_by_file_updating_obs_window",
                    "reason": "Composer cleared and report file updating during observation window.",
                    "message_probe_post_send_count": count,
                    "post_send_matching_texts": matches,
                    "post_send_visible_text_count": len(texts),
                    "post_send_send_button": send_button_summary,
                    "composer_probe_status": composer_probe["status"],
                    "evidence_tier": "C_weak_obs",
                }

        # Nothing confirmed — build diagnostic reason
        composer_probe_final = self._probe_in_composer(composer_rect, message_probe)
        if composer_probe_final["probe_present"]:
            reason = "Message probe was still present in the composer after all send attempts."
        elif not self._is_send_button_unavailable(last_send_button):
            reason = (
                "Message probe did not show a new visible instance and the send button remained "
                "available after all send attempts and observation window. "
                "Composer was cleared but no other confirmation signal appeared."
            )
        elif last_count < baseline_count + 1:
            reason = "Message probe never appeared in visible Codex text after all send attempts."
        else:
            reason = "Message probe did not show a new visible instance beyond the pre-send state."

        return {
            "success": False,
            "status": "send_not_confirmed",
            "reason": reason,
            "message_probe_post_send_count": last_count,
            "post_send_matching_texts": last_matches,
            "post_send_visible_text_count": last_visible_count,
            "post_send_send_button": last_send_button,
            "composer_probe_status": composer_probe_final["status"],
            "evidence_tier": "none",
        }

    def _ctrl_summary(self, ctrl: auto.Control | None) -> dict[str, Any] | None:
        if ctrl is None:
            return None
        rect = rect_from_control(ctrl)
        try:
            return {
                "name": ctrl.Name or "",
                "automation_id": ctrl.AutomationId or "",
                "control_type": ctrl.ControlTypeName or "",
                "enabled": bool(getattr(ctrl, "IsEnabled", True)),
                "rect": None if rect is None else rect.to_dict(),
            }
        except Exception:
            return None

    def _is_send_button_unavailable(self, summary: dict[str, Any] | None) -> bool:
        if summary is None:
            return True
        return summary.get("enabled") is False

    def _probe_in_composer(self, composer_rect: Rect, message_probe: str) -> dict[str, Any]:
        clipboard_before = pyperclip.paste() or ""
        sentinel = f"__CODEX_BRIDGE_SENTINEL__::{now_ts()}__"
        try:
            pyperclip.copy(sentinel)
            click_point(composer_rect.center_x, composer_rect.center_y)
            hotkey(VK_CONTROL, VK_A)
            hotkey(VK_CONTROL, VK_C)
            time.sleep(0.2)
            copied = pyperclip.paste() or ""
        finally:
            try:
                pyperclip.copy(clipboard_before)
            except Exception:
                pass
        if copied == sentinel:
            return {
                "probe_present": False,
                "status": "empty_or_unavailable",
            }
        if message_probe in copied:
            return {
                "probe_present": True,
                "status": "probe_present",
            }
        return {
            "probe_present": False,
            "status": "probe_not_present",
        }

    def _find_button_by_name(self, name: str) -> auto.Control | None:
        assert self.root is not None
        try:
            ctrl = self.root.ButtonControl(Name=name)
            if ctrl.Exists(1):
                return ctrl
        except Exception:
            return None
        return None

    def _find_root_web_area(self) -> auto.Control | None:
        assert self.window is not None
        queue: deque[tuple[auto.Control, int]] = deque([(self.window, 0)])
        while queue:
            ctrl, depth = queue.popleft()
            if depth > 15:
                continue
            try:
                if (ctrl.AutomationId or "") == "RootWebArea":
                    return ctrl
            except Exception:
                pass
            try:
                children = ctrl.GetChildren()
            except Exception:
                continue
            for child in children:
                queue.append((child, depth + 1))
        return None

    def _find_send_button(self, add_file_button: auto.Control | None) -> auto.Control | None:
        assert self.root is not None
        if add_file_button is None:
            return None
        add_rect = rect_from_control(add_file_button)
        if add_rect is None:
            return None
        candidates: list[tuple[int, auto.Control]] = []
        queue: deque[auto.Control] = deque([self.root])
        while queue:
            ctrl = queue.popleft()
            try:
                children = ctrl.GetChildren()
            except Exception:
                continue
            for child in children:
                queue.append(child)
                try:
                    if child.ControlTypeName != "ButtonControl":
                        continue
                    rect = rect_from_control(child)
                    if rect is None:
                        continue
                    same_row = abs(rect.top - add_rect.top) <= 4 and abs(rect.bottom - add_rect.bottom) <= 4
                    if same_row and rect.left >= add_rect.left:
                        candidates.append((rect.right, child))
                except Exception:
                    continue
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[-1][1]

    def _find_composer_rect(self, add_file_button: auto.Control | None, send_button: auto.Control | None) -> Rect | None:
        assert self.root is not None
        add_rect = rect_from_control(add_file_button) if add_file_button is not None else None
        send_rect = rect_from_control(send_button) if send_button is not None else None
        if add_rect is None or send_rect is None:
            return None

        toolbar_top = add_rect.top
        composer_candidates: list[Rect] = []
        queue: deque[auto.Control] = deque([self.root])
        while queue:
            ctrl = queue.popleft()
            try:
                children = ctrl.GetChildren()
            except Exception:
                continue
            for child in children:
                queue.append(child)
                rect = rect_from_control(child)
                if rect is None:
                    continue
                vertical_ok = (
                    rect.bottom < toolbar_top - int(self.config["composer_gap_bottom_px"])
                    and rect.bottom >= toolbar_top - int(self.config["composer_gap_top_px"])
                )
                horizontal_ok = rect.left <= add_rect.left + 10 and rect.right >= send_rect.right - 10
                size_ok = (
                    rect.width >= int(self.config["composer_min_width_px"])
                    and rect.height >= 20
                    and rect.height <= int(self.config["composer_max_height_px"])
                )
                if vertical_ok and horizontal_ok and size_ok:
                    composer_candidates.append(rect)

        if composer_candidates:
            composer_candidates.sort(key=lambda r: (r.bottom, r.width))
            return composer_candidates[-1]

        return Rect(
            left=add_rect.left,
            top=toolbar_top - int(self.config["composer_fallback_height_px"]),
            right=send_rect.right,
            bottom=toolbar_top - int(self.config["composer_gap_bottom_px"]),
        )


def write_log(log_path: Path, payload: dict[str, Any]) -> None:
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def run_inspect(config: dict[str, Any], logs_dir: Path) -> DemoResult:
    bridge = CodexBridge(config, logs_dir)
    info = bridge.inspect()
    stamp = now_ts()
    log_path = logs_dir / f"inspect_{stamp}.json"
    write_log(log_path, info)
    return DemoResult(True, "inspect_ok", "UI inspection completed.", log_path)


# ── UI-noise rejection -──────────────────────────────────────────────────────
_UI_NOISE_BLACKLIST = {
    "要求后续变更", "继续", "处理中", "请稍后", "已收到",
    "done", "continue", "ok", "received", "processing",
}
_UI_NOISE_DOMAIN_WORDS = {
    "reward", "coverage", "loss", "report", "analysis",
    "turn_penalty", "revisit_penalty", "entry_k", "parameter",
    "training", "step", "success rate",
}
_UI_NOISE_MIN_CHARS = 80


def is_ui_candidate_noise(text: str) -> tuple[bool, str]:
    """Return (is_noise, reason). If noise, caller should not treat as a valid report."""
    stripped = text.strip()
    if not stripped:
        return True, "empty"
    if len(stripped) < _UI_NOISE_MIN_CHARS:
        return True, f"too_short ({len(stripped)} chars < {_UI_NOISE_MIN_CHARS})"
    lower = stripped.lower()
    for phrase in _UI_NOISE_BLACKLIST:
        if phrase in lower:
            return True, f"blacklist_phrase: {phrase!r}"
    has_heading = any(line.strip().startswith("#") for line in stripped.splitlines())
    has_list = any(line.strip().startswith(("- ", "* ")) for line in stripped.splitlines())
    domain_count = sum(1 for kw in _UI_NOISE_DOMAIN_WORDS if kw in lower)
    if not has_heading and not has_list and domain_count < 2:
        return True, "no_structure_no_domain_keywords"
    return False, ""


# ── File-first report watcher ─────────────────────────────────────────────────

def wait_for_report_file(
    report_path: Path,
    round_id: str,
    started_at: float,
    timeout_sec: float,
    stub_text: str | None = None,
    poll_interval: float = 3.0,
    stable_reads: int = 2,
) -> tuple[bool, str, dict]:
    """
    Poll report_path until it exists, has been updated after started_at,
    is non-empty, is not the template stub, is stable across consecutive reads,
    and passes codex_report_is_ready().

    Returns (success, reason, diagnostics_dict).
    """
    from automation_protocol import codex_report_is_ready

    diag: dict = {
        "report_path": str(report_path),
        "started_at": started_at,
        "timeout_sec": timeout_sec,
        "report_exists_before_send": report_path.exists(),
        "report_mtime_before_send": report_path.stat().st_mtime if report_path.exists() else None,
        "report_exists_after_wait": False,
        "report_mtime_after_wait": None,
        "report_updated_after_send": False,
        "report_size_after_wait": 0,
        "report_ready": False,
        "report_ready_reason": "",
        "stable_check_count": 0,
    }

    deadline = time.time() + timeout_sec
    last_text = ""
    consecutive_stable = 0

    while time.time() < deadline:
        time.sleep(poll_interval)

        if not report_path.exists():
            continue

        try:
            mtime = report_path.stat().st_mtime
            size = report_path.stat().st_size
        except OSError:
            continue

        try:
            content = report_path.read_text("utf-8").strip()
        except OSError:
            continue

        if not content:
            continue
        if stub_text and content == stub_text.strip():
            continue
        if mtime <= started_at:
            continue  # file not updated since we started

        # Stability check
        if content == last_text:
            consecutive_stable += 1
        else:
            consecutive_stable = 1
        last_text = content
        diag["stable_check_count"] = consecutive_stable

        if consecutive_stable < stable_reads:
            continue

        # Reached stable state — run readiness check
        ready, reason = codex_report_is_ready(round_id, content)
        diag["report_exists_after_wait"] = True
        diag["report_mtime_after_wait"] = mtime
        diag["report_updated_after_send"] = True
        diag["report_size_after_wait"] = size
        diag["report_ready"] = ready
        diag["report_ready_reason"] = reason

        if ready:
            return True, "ok", diag
        else:
            # File is stable but not ready; keep waiting (Codex may still be writing)
            consecutive_stable = 0
            last_text = ""

    # Timeout — record final state
    if report_path.exists():
        try:
            diag["report_exists_after_wait"] = True
            diag["report_mtime_after_wait"] = report_path.stat().st_mtime
            diag["report_size_after_wait"] = report_path.stat().st_size
            content = report_path.read_text("utf-8").strip()
            if content and (not stub_text or content != stub_text.strip()):
                ready, reason = codex_report_is_ready(round_id, content)
                diag["report_ready"] = ready
                diag["report_ready_reason"] = reason
                if ready:
                    return True, "ok_at_timeout_flush", diag
        except OSError:
            pass

    reason = "report_file_not_ready_before_timeout"
    if not diag["report_exists_after_wait"]:
        reason = "report_file_never_appeared"
    elif not diag["report_updated_after_send"]:
        reason = "report_file_not_updated_after_send"
    elif not diag["report_ready"]:
        reason = f"report_not_ready: {diag['report_ready_reason']}"
    return False, reason, diag


def run_send_or_demo(
    config: dict[str, Any],
    logs_dir: Path,
    *,
    send_only: bool,
    manual_confirm_send: bool,
    dry_run: bool,
    prompt_override: str | None = None,
    sent_message_source: str = "ack",
    message_path: str = "",
    expect_substring: str | None = None,
    report_path: Path | None = None,
    round_id: str = "round_xxxx",
    report_wait_sec: float = 300.0,
) -> DemoResult:
    bridge = CodexBridge(config, logs_dir)
    stamp = now_ts()
    log_path = logs_dir / f"run_{stamp}.json"
    transcript_path = logs_dir / f"run_{stamp}_transcript.txt"
    payload: dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "send_only" if send_only else "demo",
        "success": False,
        "status": "starting",
        "config_path": config["config_path"],
        "manual_confirm_send": manual_confirm_send,
        "dry_run": dry_run,
        "sent_message_source": sent_message_source,
        "message_probe": "",
        "message_probe_baseline_count": None,
        "message_probe_post_paste_count": None,
        "message_probe_post_send_count": None,
        "send_confirmed": False,
        "send_confirm_reason": "",
        "send_confirmation_status": "",
        "send_confirmation_reason": "",
        "expect_substring": expect_substring,
        # File-first fields
        "report_path": str(report_path) if report_path else None,
        "report_exists_before_send": report_path.exists() if report_path else False,
        "report_mtime_before_send": report_path.stat().st_mtime if (report_path and report_path.exists()) else None,
        "report_exists_after_wait": False,
        "report_mtime_after_wait": None,
        "report_updated_after_send": False,
        "report_size_after_wait": 0,
        "report_ready": False,
        "report_ready_reason": "",
        "ui_candidate_reply_text": "",
        "ui_candidate_reply_length": 0,
        "ui_candidate_rejected": False,
        "ui_candidate_reject_reason": "",
    }
    if message_path:
        payload["message_path"] = message_path
    try:
        message_probe = ""
        if prompt_override is None:
            token = build_token(config["ack_prefix"])
            prompt = build_prompt(token)
            payload["expected_token"] = token
        else:
            token = ""
            prompt = prompt_override
            payload["expected_token"] = ""
            message_probe = build_message_probe(
                prompt,
                max_chars=int(config.get("message_probe_max_chars", 80)),
            )
            payload["message_probe"] = message_probe
        payload["sent_prompt"] = prompt

        bridge.attach()
        started_at = time.time()

        if token:
            baseline_count, _, baseline_texts = bridge.count_token_in_ui(token)
            payload["baseline_token_occurrence_count"] = baseline_count
            payload["baseline_visible_text_count"] = len(baseline_texts)
        else:
            baseline_count = 0
            payload["baseline_token_occurrence_count"] = None
            payload["baseline_visible_text_count"] = None
            probe_baseline_count, _, baseline_texts = bridge.count_token_in_ui(message_probe)
            payload["message_probe_baseline_count"] = probe_baseline_count
            payload["baseline_visible_text_count"] = len(baseline_texts)

        if dry_run:
            payload["status"] = "dry_run"
            payload["success"] = True
            payload["message"] = "Dry-run only. No prompt was sent."
            write_log(log_path, payload)
            return DemoResult(
                True,
                "dry_run",
                payload["message"],
                log_path,
                sent_prompt=prompt,
                expected_token=token,
                sent_message_source=sent_message_source,
                message_path=message_path,
                message_probe=message_probe,
            )

        send_meta = bridge.send_prompt(
            prompt,
            manual_confirm_send=manual_confirm_send,
            message_probe=message_probe or None,
        )
        send_started_at = time.time()
        payload["send_meta"] = send_meta
        if message_probe:
            payload["message_probe_post_paste_count"] = send_meta["message_probe_post_paste_count"]

        if send_only:
            if message_probe:
                composer_rect_dict = send_meta["composer_rect"]
                confirmation = bridge.confirm_message_delivery(
                    message_probe=message_probe,
                    baseline_count=payload.get("message_probe_baseline_count") or 0,
                    post_paste_count=payload.get("message_probe_post_paste_count") or 0,
                    composer_rect=Rect(
                        left=int(composer_rect_dict["left"]),
                        top=int(composer_rect_dict["top"]),
                        right=int(composer_rect_dict["right"]),
                        bottom=int(composer_rect_dict["bottom"]),
                    ),
                )
                payload["message_probe_post_send_count"] = confirmation["message_probe_post_send_count"]
                payload["send_confirmation_status"] = confirmation["status"]
                payload["send_confirmation_reason"] = confirmation["reason"]
                payload["send_confirmed"] = bool(confirmation["success"])
                payload["send_confirm_reason"] = confirmation["reason"]
                payload["send_confirmation_meta"] = {
                    "post_send_matching_texts": confirmation.get("post_send_matching_texts", []),
                    "post_send_visible_text_count": confirmation.get("post_send_visible_text_count", 0),
                    "post_send_send_button": confirmation.get("post_send_send_button", {}),
                    "composer_probe_status": confirmation.get("composer_probe_status", ""),
                }
                payload["status"] = "sent_only" if confirmation["success"] else "send_not_confirmed"
                payload["success"] = bool(confirmation["success"])
                payload["message"] = (
                    "Prompt was sent and minimally confirmed in the Codex UI."
                    if confirmation["success"]
                    else confirmation["reason"]
                )
            else:
                payload["status"] = "sent_only"
                payload["success"] = True
                payload["message"] = "Prompt was sent without waiting for a reply."
            write_log(log_path, payload)
            return DemoResult(
                bool(payload["success"]),
                payload["status"],
                payload["message"],
                log_path,
                sent_prompt=prompt,
                expected_token=token,
                sent_message_source=sent_message_source,
                message_path=message_path,
                message_probe=message_probe,
                send_confirmation_status=payload.get("send_confirmation_status", ""),
                send_confirmation_reason=payload.get("send_confirmation_reason", ""),
            )

        # ── send-and-wait (file-first) ────────────────────────────────────────
        if token:
            # Legacy ACK-token mode (probe mode, no report path)
            success, reply_text, extra = bridge.wait_for_reply(token, baseline_count=baseline_count)
        else:
            # Step A: Send confirmation gate (with retry and expanded evidence)
            confirmation: dict[str, Any] = {"success": True, "status": "no_probe_required", "reason": "no_probe_required"}
            if message_probe:
                composer_rect_dict = send_meta["composer_rect"]
                confirmation = bridge.confirm_message_delivery(
                    message_probe=message_probe,
                    baseline_count=payload.get("message_probe_baseline_count") or 0,
                    post_paste_count=payload.get("message_probe_post_paste_count") or 0,
                    composer_rect=Rect(
                        left=int(composer_rect_dict["left"]),
                        top=int(composer_rect_dict["top"]),
                        right=int(composer_rect_dict["right"]),
                        bottom=int(composer_rect_dict["bottom"]),
                    ),
                    report_path=report_path,
                    report_started_at=send_started_at,
                )
                payload["message_probe_post_send_count"] = confirmation["message_probe_post_send_count"]
                payload["send_confirmation_status"] = confirmation["status"]
                payload["send_confirmation_reason"] = confirmation["reason"]
                payload["send_confirmed"] = bool(confirmation["success"])
                payload["send_confirm_reason"] = confirmation["reason"]
                payload["send_evidence_tier"] = confirmation.get("evidence_tier", "")

                if confirmation["success"]:
                    print(f"Send confirmed: {confirmation['status']} (tier={confirmation.get('evidence_tier','')})")
                else:
                    print(f"Send confirmation failed: {confirmation['reason']}")
                    # Do NOT early-exit here when report_path is provided —
                    # allow file-first wait to determine if Codex actually received the message.
                    # Only hard-exit if there is no report_path to observe.
                    if report_path is None:
                        payload["status"] = "send_not_confirmed"
                        payload["success"] = False
                        payload["message"] = f"Send not confirmed: {confirmation['reason']}"
                        write_log(log_path, payload)
                        return DemoResult(
                            False, "send_not_confirmed", payload["message"], log_path,
                            sent_prompt=prompt, message_probe=message_probe,
                            sent_message_source=sent_message_source,
                            message_path=message_path,
                            send_confirmation_status=confirmation["status"],
                            send_confirmation_reason=confirmation["reason"],
                        )
                    # With report_path: proceed to file-first wait even on weak/failed confirm.
                    # The file-first result will be the authoritative verdict.
                    print("[send-and-wait] Proceeding to file-first wait despite weak send confirmation.")
            else:
                payload["send_confirmed"] = True
                payload["send_confirm_reason"] = "no_probe_required"

            # Step B: File-first — wait for report file to be written and ready
            if report_path is not None:
                from automation_protocol import render_codex_report_stub as _stub_fn
                stub_text: str | None = None
                try:
                    stub_text = _stub_fn(round_id)
                except Exception:
                    pass

                print(f"[file-first] Waiting up to {report_wait_sec}s for {report_path} ...")
                file_ok, file_reason, file_diag = wait_for_report_file(
                    report_path=report_path,
                    round_id=round_id,
                    started_at=send_started_at,
                    timeout_sec=report_wait_sec,
                    stub_text=stub_text,
                )
                # Propagate file diagnostics
                payload.update({
                    "report_exists_after_wait": file_diag.get("report_exists_after_wait", False),
                    "report_mtime_after_wait": file_diag.get("report_mtime_after_wait"),
                    "report_updated_after_send": file_diag.get("report_updated_after_send", False),
                    "report_size_after_wait": file_diag.get("report_size_after_wait", 0),
                    "report_ready": file_diag.get("report_ready", False),
                    "report_ready_reason": file_diag.get("report_ready_reason", ""),
                })

                # Step C: Optionally read UI candidate as diagnostic only
                try:
                    _, ui_reply, _ = bridge.wait_for_arbitrary_reply(
                        baseline_visible_count=payload.get("baseline_visible_text_count", 0),
                        prompt=prompt,
                    )
                    ui_is_noise, ui_noise_reason = is_ui_candidate_noise(ui_reply)
                    payload["ui_candidate_reply_text"] = ui_reply[:500]
                    payload["ui_candidate_reply_length"] = len(ui_reply)
                    payload["ui_candidate_rejected"] = ui_is_noise
                    payload["ui_candidate_reject_reason"] = ui_noise_reason
                    if ui_reply:
                        save_text(transcript_path, ui_reply)
                        payload["ui_transcript_path"] = str(transcript_path)
                except Exception as ui_exc:
                    payload["ui_candidate_error"] = str(ui_exc)

                if file_ok:
                    payload["success"] = True
                    payload["status"] = "report_file_ready"
                    payload["message"] = f"Codex report file verified ready: {report_path}"
                    payload["reply_text"] = ""  # not from UI
                    write_log(log_path, payload)
                    return DemoResult(
                        True, "report_file_ready", payload["message"], log_path,
                        sent_prompt=prompt, message_probe=message_probe,
                        sent_message_source=sent_message_source,
                        message_path=message_path,
                        send_confirmation_status=payload.get("send_confirmation_status", ""),
                        send_confirmation_reason=payload.get("send_confirmation_reason", ""),
                        report_ready=True, report_ready_reason="ok",
                        ui_candidate_rejected=payload.get("ui_candidate_rejected", False),
                        ui_candidate_reject_reason=payload.get("ui_candidate_reject_reason", ""),
                    )
                else:
                    # If send was never confirmed, prefer send_not_confirmed as primary status
                    send_was_confirmed = bool(payload.get("send_confirmed", True))
                    if not send_was_confirmed:
                        primary_status = "send_not_confirmed"
                        primary_message = (
                            f"Send not confirmed and report file never appeared. "
                            f"Send reason: {payload.get('send_confirm_reason', '')}. "
                            f"File reason: {file_reason}"
                        )
                    else:
                        primary_status = f"report_file_not_ready: {file_reason}"
                        primary_message = f"Report file not ready: {file_reason}"

                    payload["success"] = False
                    payload["status"] = primary_status
                    payload["message"] = primary_message
                    write_log(log_path, payload)
                    return DemoResult(
                        False, primary_status, primary_message, log_path,
                        sent_prompt=prompt, message_probe=message_probe,
                        sent_message_source=sent_message_source,
                        message_path=message_path,
                        send_confirmation_status=payload.get("send_confirmation_status", ""),
                        send_confirmation_reason=payload.get("send_confirmation_reason", ""),
                        report_ready=False, report_ready_reason=file_reason,
                        ui_candidate_rejected=payload.get("ui_candidate_rejected", False),
                        ui_candidate_reject_reason=payload.get("ui_candidate_reject_reason", ""),
                    )


            else:
                # No report_path provided — fall back to UI-based detection (legacy)
                print("Warning: --report-path not provided; falling back to UI text detection.")
                success, reply_text, extra = bridge.wait_for_arbitrary_reply(
                    baseline_visible_count=payload.get("baseline_visible_text_count", 0),
                    expect_substring=payload.get("expect_substring"),
                    prompt=prompt,
                )
                ui_is_noise, ui_noise_reason = is_ui_candidate_noise(reply_text)
                payload["ui_candidate_reply_text"] = reply_text[:500]
                payload["ui_candidate_reply_length"] = len(reply_text)
                payload["ui_candidate_rejected"] = ui_is_noise
                payload["ui_candidate_reject_reason"] = ui_noise_reason

                if ui_is_noise:
                    payload["success"] = False
                    payload["status"] = "ui_noise_only"
                    payload["message"] = f"UI reply rejected as noise: {ui_noise_reason}"
                    if reply_text:
                        save_text(transcript_path, reply_text)
                        payload["ui_transcript_path"] = str(transcript_path)
                    write_log(log_path, payload)
                    return DemoResult(
                        False, "ui_noise_only", payload["message"], log_path,
                        reply_text=reply_text, sent_prompt=prompt, message_probe=message_probe,
                        ui_candidate_rejected=True, ui_candidate_reject_reason=ui_noise_reason,
                    )

                payload["reply_detection"] = extra
                payload["detected_reply_text"] = reply_text
                payload["success"] = bool(success)
                payload["status"] = "reply_detected" if success else "reply_not_detected"
                if payload.get("expect_substring"):
                    payload["reply_matches_expectation"] = extra.get("reply_matches_expectation", False)
                    if payload["reply_matches_expectation"]:
                        payload["status"] = "reply_verified"
                        payload["message"] = "Reply verified to match expected content."
                    else:
                        payload["status"] = extra.get("failure_reason", "reply_content_mismatch")
                        payload["message"] = "Reply verification failed."
                        payload["success"] = False
                else:
                    payload["message"] = (
                        "Reply was detected in the Codex UI." if success
                        else "Reply was not detected before timeout."
                    )
                if reply_text:
                    save_text(transcript_path, reply_text)
                    payload["detected_reply_text_path"] = str(transcript_path)
                write_log(log_path, payload)
                return DemoResult(
                    bool(payload["success"]), payload["status"], payload["message"], log_path,
                    reply_text=reply_text, sent_prompt=prompt, expected_token=token,
                    sent_message_source=sent_message_source, message_path=message_path, message_probe=message_probe,
                )

    except Exception as exc:
        payload["status"] = "error"
        payload["success"] = False
        payload["error"] = f"{type(exc).__name__}: {exc}"
        payload["traceback"] = traceback.format_exc()
        write_log(log_path, payload)
        return DemoResult(False, "error", payload["error"], log_path)





def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local Codex UI bridge demo.")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--inspect-ui", action="store_true", help="Inspect candidate windows/controls and dump JSON.")
    parser.add_argument("--send-only", action="store_true", help="Focus window, paste prompt, optionally send, but do not wait.")
    parser.add_argument("--send-and-wait", action="store_true", help="Send arbitrary message and wait for report file (file-first mode).")
    parser.add_argument("--expect-substring", type=str, help="Optionally verify content-level validation using expected substring text.")
    parser.add_argument("--demo", action="store_true", help="Run the full bridge demo: focus, send, wait, read, log.")
    parser.add_argument("--dry-run", action="store_true", help="Print and log the planned action without sending.")
    parser.add_argument("--manual-confirm-send", action="store_true", help="Pause after paste and wait for Enter in console.")
    parser.add_argument("--message-file", type=Path, help="Read message text from a file and send it to Codex.")
    parser.add_argument("--message-text", help="Send the provided text to Codex.")
    parser.add_argument("--output-json", type=Path, help="Optional specific file to dump machine-readable status dict.")
    parser.add_argument("--report-path", type=Path, default=None, help="Path to codex_report.md to watch as primary success signal (file-first mode).")
    parser.add_argument("--round-id", type=str, default="round_xxxx", help="Round ID used for codex_report_is_ready() check.")
    parser.add_argument("--report-wait-sec", type=float, default=300.0, help="Max seconds to wait for the report file to be ready (file-first mode).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not any([args.inspect_ui, args.send_only, args.demo, args.send_and_wait]):
        print("Choose one of: --inspect-ui, --send-only, --demo, --send-and-wait", file=sys.stderr)
        return 2

    try:
        prompt_override, sent_message_source, message_path = load_message_override(args.message_file, args.message_text)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    
    if prompt_override is not None and not (args.send_only or args.send_and_wait):
        print("Arbitrary message sending requires --send-only or --send-and-wait.", file=sys.stderr)
        return 2

    config = load_config(args.config.resolve())
    logs_dir = Path(__file__).with_name("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    if args.inspect_ui:
        result = run_inspect(config, logs_dir)
    else:
        result = run_send_or_demo(
            config,
            logs_dir,
            send_only=args.send_only and not args.demo and not args.send_and_wait,
            manual_confirm_send=args.manual_confirm_send,
            dry_run=args.dry_run,
            prompt_override=prompt_override,
            sent_message_source=sent_message_source,
            message_path=message_path,
            expect_substring=args.expect_substring,
            report_path=args.report_path,
            round_id=args.round_id,
            report_wait_sec=args.report_wait_sec,
        )

    print(f"status={result.status}")
    print(f"log={result.log_path}")
    print(f"sent_message_source={result.sent_message_source}")
    if result.message_path:
        print(f"message_path={result.message_path}")
    if result.message_probe:
        print(f"message_probe={result.message_probe}")
    if result.send_confirmation_status:
        print(f"send_confirmation_status={result.send_confirmation_status}")
    if result.send_confirmation_reason:
        print(f"send_confirmation_reason={result.send_confirmation_reason}")
    if result.reply_text:
        print("reply_detected=yes")
        
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        # Read the run log payload written by run_send_or_demo and sync all
        # file-first status fields directly — no more slim 5-field dict.
        _FILE_FIRST_FIELDS = [
            "success", "status", "message", "reply_text",
            "send_confirmed", "send_confirm_reason",
            "send_confirmation_status", "send_confirmation_reason",
            "report_path",
            "report_exists_before_send", "report_mtime_before_send",
            "report_exists_after_wait", "report_mtime_after_wait",
            "report_updated_after_send", "report_size_after_wait",
            "report_ready", "report_ready_reason",
            "ui_candidate_reply_text", "ui_candidate_reply_length",
            "ui_candidate_rejected", "ui_candidate_reject_reason",
            "message_probe", "message_probe_baseline_count",
            "message_probe_post_paste_count", "message_probe_post_send_count",
        ]
        out_dict: dict[str, Any] = {
            "success": result.success,
            "status": result.status,
            "message": result.message,
            "log_path": str(result.log_path),
            "reply_text": result.reply_text,
        }
        try:
            with open(result.log_path, "r", encoding="utf-8") as _f:
                saved_payload = json.load(_f)
            for _k in _FILE_FIRST_FIELDS:
                if _k in saved_payload and _k not in out_dict:
                    out_dict[_k] = saved_payload[_k]
            # Legacy compat fields
            if "reply_matches_expectation" in saved_payload:
                out_dict["reply_matches_expectation"] = saved_payload["reply_matches_expectation"]
            if "ui_transcript_path" in saved_payload:
                out_dict["ui_transcript_path"] = saved_payload["ui_transcript_path"]
        except Exception as _e:
            out_dict["output_json_sync_error"] = str(_e)
        args.output_json.write_text(json.dumps(out_dict, indent=2), "utf-8")

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
