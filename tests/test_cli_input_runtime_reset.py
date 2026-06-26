import unittest

from src.cli_input import CLIInputHandler


class TestCLIInputRuntimeReset(unittest.TestCase):
    def test_reset_runtime_state_clears_prompt_toolkit_state(self):
        handler = CLIInputHandler(
            workspace="/tmp/project",
            model_name="gemini-test",
            streaming_mode=True,
        )
        handler._result = "/agents"
        handler._filtered = ["stale"]
        handler._show_suggestions = True
        handler._selected_idx = 3
        handler._scroll_offset = 2
        handler._buffer = object()

        handler.reset_runtime_state()

        self.assertIsNone(handler._result)
        self.assertEqual(handler._filtered, [])
        self.assertFalse(handler._show_suggestions)
        self.assertEqual(handler._selected_idx, 0)
        self.assertEqual(handler._scroll_offset, 0)
        self.assertIsNone(handler._buffer)


if __name__ == "__main__":
    unittest.main()
