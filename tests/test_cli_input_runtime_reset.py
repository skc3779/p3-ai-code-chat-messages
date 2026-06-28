"""B-071: /agents 복귀 후 CLIInputHandler 런타임 상태 초기화 테스트."""

import sys
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.cli_input import CLIInputHandler, PROMPT_TOOLKIT_AVAILABLE


class TestCLIInputRuntimeReset(unittest.TestCase):

    def test_reset_runtime_state_clears_prompt_toolkit_state(self):
        handler = CLIInputHandler(
            history_file=":memory:",
            workspace="/tmp/workspace",
            model_name="test-model",
            streaming_mode=True,
        )
        if not PROMPT_TOOLKIT_AVAILABLE or not handler._use_prompt_toolkit:
            self.skipTest("prompt_toolkit unavailable")

        handler._filtered = [object()]
        handler._selected_idx = 3
        handler._scroll_offset = 2
        handler._show_suggestions = True
        handler._result = "/agents"
        handler._build_app("> ")
        handler._buffer.text = "/agents"

        handler.reset_runtime_state()

        self.assertEqual(handler._filtered, [])
        self.assertEqual(handler._selected_idx, 0)
        self.assertEqual(handler._scroll_offset, 0)
        self.assertFalse(handler._show_suggestions)
        self.assertIsNone(handler._result)
        self.assertEqual(handler._buffer.text, "")


if __name__ == "__main__":
    unittest.main()
