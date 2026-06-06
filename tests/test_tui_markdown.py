from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dk_agent.app.tui_app import markdown_to_text, markdown_to_visible_text


class TuiMarkdownTests(unittest.TestCase):
    def test_markdown_visible_text_strips_heading_and_bold_markers(self) -> None:
        visible = markdown_to_visible_text("### Title\nThis is **important**.")

        self.assertEqual(visible, "Title\nThis is important.")
        self.assertNotIn("###", visible)
        self.assertNotIn("**", visible)

    def test_markdown_visible_text_normalizes_bullets(self) -> None:
        visible = markdown_to_visible_text("- one\n- **two**")

        self.assertEqual(visible, "\u2022 one\n\u2022 two")
        self.assertNotIn("- ", visible)
        self.assertNotIn("**", visible)

    def test_markdown_visible_text_strips_backticks(self) -> None:
        visible = markdown_to_visible_text("Use `value`\n```")

        self.assertEqual(visible, "Use value")
        self.assertNotIn("`", visible)

    def test_rendered_text_string_is_visible_text(self) -> None:
        rendered = markdown_to_text("### Title\n- **item**")

        selected_text = str(rendered)
        self.assertEqual(selected_text, "Title\n\u2022 item")
        self.assertNotIn("###", selected_text)
        self.assertNotIn("**", selected_text)


if __name__ == "__main__":
    unittest.main()
