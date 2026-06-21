import unittest
from pathlib import Path

from src.cli_input import parse_context_command_args


class LargeContextCommandTests(unittest.TestCase):
    def test_leading_and_repeated_whitespace(self):
        parsed = parse_context_command_args("  --large   src/*.py   Q")
        self.assertEqual(parsed.file_patterns, ["src/*.py"])
        self.assertEqual(parsed.question, "Q")
        self.assertTrue(parsed.large)

    def test_large_and_no_tree_are_order_independent(self):
        first = parse_context_command_args("--large -nt [src/*.py, docs/*.md] 질문")
        second = parse_context_command_args("-nt --large [src/*.py, docs/*.md] 질문")
        self.assertTrue(first.large and second.large)
        self.assertTrue(first.no_tree and second.no_tree)
        self.assertEqual(first.file_patterns, second.file_patterns)

    def test_short_large_alias(self):
        parsed = parse_context_command_args("-l src/*.py 분석")
        self.assertTrue(parsed.large)
        self.assertEqual(parsed.question, "분석")

    def test_normal_context_remains_single_call_mode(self):
        parsed = parse_context_command_args("src/*.py 분석")
        self.assertFalse(parsed.large)

    def test_all_three_entry_points_use_shared_parser_and_processor(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("claude-ai-chat-code.py", "gen-ai-chat-code.py", "gemini-ai-chat-code.py"):
            source = (root / name).read_text(encoding="utf-8")
            self.assertIn("parse_context_command_args(args)", source, name)
            self.assertIn("LargeContextProcessor(", source, name)
            self.assertIn("if parsed.large:", source, name)


if __name__ == "__main__":
    unittest.main()
