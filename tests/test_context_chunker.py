import tempfile
import unittest
from pathlib import Path

from src.context_chunker import ContextBudget, ContextChunker


class ContextChunkerTests(unittest.TestCase):
    def test_uses_safe_cap_without_second_75_percent(self):
        budget = ContextBudget.from_request_budget(96000)
        self.assertEqual(budget.request_budget_tokens, 96000)
        self.assertEqual(budget.usable_input_tokens, 74112)
        self.assertEqual(budget.map_payload_tokens, 32768)

    def test_all_provider_default_safe_caps_are_used_as_request_budgets(self):
        for request_budget in (150000, 96000, 786000):
            with self.subTest(request_budget=request_budget):
                self.assertEqual(
                    ContextBudget.from_request_budget(request_budget).request_budget_tokens,
                    request_budget,
                )

    def test_rejects_too_small_budget(self):
        with self.assertRaises(ValueError):
            ContextBudget.from_request_budget(0)
        with self.assertRaises(ValueError):
            ContextBudget.from_request_budget(12000)

    def test_large_file_splits_on_lines_with_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "large.txt"
            content = "".join(f"line-{i:05d} data data data\n" for i in range(4000))
            path.write_text(content, encoding="utf-8")
            budget = ContextBudget.from_request_budget(20000)
            chunker = ContextChunker(budget)
            record = chunker.make_record(root, path, content)
            chunks = chunker.chunk([record], identity="test")
            parts = [part for chunk in chunks for part in chunk.parts]
            self.assertGreater(len(parts), 1)
            self.assertEqual(parts[1].overlap_lines, 20)
            self.assertTrue(all(len(chunk.payload) <= budget.map_payload_chars for chunk in chunks))

    def test_single_oversized_line_uses_character_fragments_without_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "long.txt"
            content = "x" * 80000
            path.write_text(content, encoding="utf-8")
            budget = ContextBudget.from_request_budget(20000)
            chunker = ContextChunker(budget)
            parts = [part for chunk in chunker.chunk([chunker.make_record(root, path, content)]) for part in chunk.parts]
            self.assertGreater(len(parts), 1)
            self.assertTrue(any(part.line_fragment for part in parts))
            self.assertEqual("".join(part.content for part in parts), content)


if __name__ == "__main__":
    unittest.main()
