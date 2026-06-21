import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.file_manager import FileManager
from unittest.mock import patch

from src.context_chunker import ContextBudget
from src.large_context_processor import MAX_REDUCE_LEVELS, LargeContextError, LargeContextProcessor


class MockAssistant:
    def __init__(self, workspace, *, fail_on=None, interrupt_on=None, long_maps=False,
                 nonshrinking=False, mutate_path=None, add_path=None, remove_path=None):
        self.file_manager = FileManager(str(workspace))
        self.context_builder = SimpleNamespace(max_tokens=20000, build_file_tree=lambda: "tree-once")
        self.system_prompt = ""
        self.conversation_history = [{"role": "user", "content": "existing"}]
        self.model_id = "mock-model"
        self.fail_on = fail_on
        self.interrupt_on = interrupt_on
        self.long_maps = long_maps
        self.nonshrinking = nonshrinking
        self.mutate_path = mutate_path
        self.add_path = add_path
        self.remove_path = remove_path
        self.calls = []

    def chat(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs, list(self.conversation_history)))
        if self.mutate_path is not None and len(self.calls) == 1:
            self.mutate_path.write_text("changed during map\n", encoding="utf-8")
        if self.add_path is not None and len(self.calls) == 1:
            self.add_path.write_text("added during map\n", encoding="utf-8")
        if self.remove_path is not None and len(self.calls) == 1:
            self.remove_path.unlink()
        if self.fail_on == len(self.calls):
            return ""
        if self.interrupt_on == len(self.calls):
            raise KeyboardInterrupt
        if "read-only Map pass" in prompt:
            return "M" * 15000 if self.long_maps else "## Evidence\n- file:L1-L2 — fact"
        if "intermediate evidence-preserving" in prompt:
            return "R" * 30000 if self.nonshrinking else "## Evidence\ncondensed"
        return "final answer"


class LargeContextProcessorTests(unittest.TestCase):
    def _workspace(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / ".gitignore").write_text(".large_context_cache/\n", encoding="utf-8")
        return temp, root

    def test_history_isolated_tools_disabled_and_final_pair_committed(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("print('a')\n", encoding="utf-8")
        assistant = MockAssistant(root)
        result = LargeContextProcessor(assistant, assistant.file_manager, provider="genai").process(["*.py"], "분석", include_tree=False)
        self.assertEqual(result, "final answer")
        self.assertTrue(all(call[1]["disable_tools"] for call in assistant.calls))
        self.assertTrue(all(call[2] == [] for call in assistant.calls))
        self.assertEqual(len(assistant.conversation_history), 3)

    def test_failed_map_resumes_without_recalling_completed_map(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        for name in ("a.py", "b.py"):
            (root / name).write_text((name + "\n") * 7000, encoding="utf-8")
        first = MockAssistant(root, fail_on=2)
        with self.assertRaisesRegex(LargeContextError, "성공했지만"):
            LargeContextProcessor(first, first.file_manager, provider="claude").process(["*.py"], "분석", include_tree=False)
        manifest = next((root / ".large_context_cache").glob("*/manifest.json")).read_text(encoding="utf-8")
        self.assertIn('"status": "failed"', manifest)
        second = MockAssistant(root)
        processor = LargeContextProcessor(second, second.file_manager, provider="claude")
        self.assertEqual(processor.process(["*.py"], "분석", include_tree=False), "final answer")
        self.assertGreaterEqual(processor.reused["map"], 1)

    def test_hierarchical_reduce_converges(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        for index in range(3):
            (root / f"f{index}.txt").write_text((f"file-{index}\n") * 5000, encoding="utf-8")
        assistant = MockAssistant(root, long_maps=True)
        processor = LargeContextProcessor(assistant, assistant.file_manager, provider="gemini")
        self.assertEqual(processor.process(["*.txt"], "분석", include_tree=True), "final answer")
        self.assertGreater(processor.calls["reduce"], 1)
        self.assertEqual(sum("tree-once" in prompt for prompt, _, _ in assistant.calls), 1)

    def test_reduce_failure_resume_reuses_all_maps(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        for index in range(3):
            (root / f"f{index}.txt").write_text((f"file-{index}\n") * 5000, encoding="utf-8")
        first = MockAssistant(root, long_maps=True, fail_on=4)
        with self.assertRaises(LargeContextError):
            LargeContextProcessor(first, first.file_manager, provider="gemini").process(["*.txt"], "분석", include_tree=False)
        second = MockAssistant(root, long_maps=True)
        processor = LargeContextProcessor(second, second.file_manager, provider="gemini")
        self.assertEqual(processor.process(["*.txt"], "분석", include_tree=False), "final answer")
        self.assertEqual(processor.reused["map"], 3)

    def test_nonshrinking_reduce_stops_with_checkpoint(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        for index in range(3):
            (root / f"f{index}.txt").write_text((f"file-{index}\n") * 5000, encoding="utf-8")
        assistant = MockAssistant(root, long_maps=True, nonshrinking=True)
        with self.assertRaisesRegex(LargeContextError, "작아지지"):
            LargeContextProcessor(assistant, assistant.file_manager, provider="gemini").process(["*.txt"], "분석", include_tree=False)

    def test_reduce_level_limit_is_bounded(self):
        self.assertEqual(MAX_REDUCE_LEVELS, 8)
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        for index in range(3):
            (root / f"f{index}.txt").write_text((f"file-{index}\n") * 5000, encoding="utf-8")
        assistant = MockAssistant(root, long_maps=True)
        with patch("src.large_context_processor.MAX_REDUCE_LEVELS", 0):
            with self.assertRaisesRegex(LargeContextError, "0단계"):
                LargeContextProcessor(assistant, assistant.file_manager, provider="gemini").process(["*.txt"], "분석", include_tree=False)

    def test_file_change_is_automatically_remapped_once(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        target = root / "a.py"
        target.write_text("x = 1\n", encoding="utf-8")
        assistant = MockAssistant(root, mutate_path=target)
        processor = LargeContextProcessor(assistant, assistant.file_manager, provider="claude")
        self.assertEqual(processor.process(["*.py"], "분석", include_tree=False), "final answer")
        self.assertEqual(processor.calls["map"], 2)

    def test_new_matching_file_is_discovered_before_reduce(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        assistant = MockAssistant(root, add_path=root / "b.py")
        processor = LargeContextProcessor(assistant, assistant.file_manager, provider="claude")
        self.assertEqual(processor.process(["*.py"], "분석", include_tree=False), "final answer")
        self.assertGreaterEqual(processor.calls["map"], 2)

    def test_removed_matching_file_rebuilds_inventory_before_reduce(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        removed = root / "b.py"
        removed.write_text("y = 2\n", encoding="utf-8")
        assistant = MockAssistant(root, remove_path=removed)
        processor = LargeContextProcessor(assistant, assistant.file_manager, provider="claude")
        self.assertEqual(processor.process(["*.py"], "분석", include_tree=False), "final answer")
        self.assertFalse(removed.exists())

    def test_valid_final_cache_avoids_all_llm_calls(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        first = MockAssistant(root)
        LargeContextProcessor(first, first.file_manager, provider="claude").process(["*.py"], "분석", include_tree=False)
        second = MockAssistant(root)
        result = LargeContextProcessor(second, second.file_manager, provider="claude").process(["*.py"], "분석", include_tree=False)
        self.assertEqual(result, "final answer")
        self.assertEqual(second.calls, [])

    def test_keyboard_interrupt_persists_interrupted_manifest(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        for name in ("a.py", "b.py"):
            (root / name).write_text((name + "\n") * 7000, encoding="utf-8")
        assistant = MockAssistant(root, interrupt_on=2)
        with self.assertRaises(KeyboardInterrupt):
            LargeContextProcessor(assistant, assistant.file_manager, provider="claude").process(["*.py"], "분석", include_tree=False)
        manifests = list((root / ".large_context_cache").glob("*/manifest.json"))
        self.assertEqual(len(manifests), 1)
        self.assertIn('"status": "interrupted"', manifests[0].read_text(encoding="utf-8"))

    def test_budget_change_invalidates_cache_identity(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        first = MockAssistant(root)
        LargeContextProcessor(first, first.file_manager, provider="genai").process(["*.py"], "분석", include_tree=False)
        second = MockAssistant(root)
        second.context_builder.max_tokens = 21000
        processor = LargeContextProcessor(second, second.file_manager, provider="genai")
        processor.process(["*.py"], "분석", include_tree=False)
        self.assertEqual(processor.reused["map"], 0)
        self.assertEqual(len(list((root / ".large_context_cache").iterdir())), 2)

    def test_rendered_request_overflow_rejected_before_call(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        assistant = MockAssistant(root)
        with self.assertRaises(LargeContextError):
            LargeContextProcessor(assistant, assistant.file_manager, provider="claude").process(["*.py"], "Q" * 50000, include_tree=False)
        self.assertEqual(assistant.calls, [])

    def test_system_prompt_overhead_is_in_rendered_preflight(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        assistant = MockAssistant(root)
        assistant.system_prompt = "S" * 50000
        with self.assertRaises(LargeContextError):
            LargeContextProcessor(assistant, assistant.file_manager, provider="claude").process(["*.py"], "분석", include_tree=False)
        self.assertEqual(assistant.calls, [])

    def test_all_unreadable_files_create_failed_manifest_without_call(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        (root / "a.py").write_text("x = 1\n", encoding="utf-8")
        assistant = MockAssistant(root)
        assistant.file_manager.read_file = lambda path: None
        with self.assertRaises(LargeContextError):
            LargeContextProcessor(assistant, assistant.file_manager, provider="claude").process(["*.py"], "분석")
        manifest = next((root / ".large_context_cache").glob("*/manifest.json")).read_text(encoding="utf-8")
        self.assertIn('"status": "failed"', manifest)
        self.assertIn('"status": "read_error"', manifest)
        self.assertEqual(assistant.calls, [])

    def test_outside_workspace_symlink_is_rejected_before_read(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        outside_dir = tempfile.TemporaryDirectory()
        self.addCleanup(outside_dir.cleanup)
        outside = Path(outside_dir.name) / "secret.py"
        outside.write_text("secret\n", encoding="utf-8")
        link = root / "linked.py"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        assistant = MockAssistant(root)
        with self.assertRaises(LargeContextError):
            LargeContextProcessor(assistant, assistant.file_manager, provider="claude").process(["*.py"], "분석")
        self.assertEqual(assistant.calls, [])

    def test_internal_symlink_does_not_duplicate_target(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        target = root / "target.py"
        target.write_text("value = 1\n", encoding="utf-8")
        try:
            (root / "alias.py").symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable")
        assistant = MockAssistant(root)
        processor = LargeContextProcessor(assistant, assistant.file_manager, provider="claude")
        budget = ContextBudget.from_request_budget(assistant.context_builder.max_tokens)
        records, errors = processor._read_records(root, ["*.py"], budget)
        self.assertEqual(len(records), 1)
        self.assertEqual(errors, [])

    def test_symlink_cannot_bypass_ignore_rules(self):
        temp, root = self._workspace()
        self.addCleanup(temp.cleanup)
        ignored = root / ".env"
        ignored.write_text("API_KEY=secret\n", encoding="utf-8")
        try:
            (root / "config.txt").symlink_to(ignored)
        except OSError:
            self.skipTest("symlinks unavailable")
        assistant = MockAssistant(root)
        with self.assertRaises(LargeContextError):
            LargeContextProcessor(assistant, assistant.file_manager, provider="claude").process(["*.txt"], "분석")
        self.assertEqual(assistant.calls, [])
        manifest = next((root / ".large_context_cache").glob("*/manifest.json")).read_text(encoding="utf-8")
        self.assertIn('"error_type": "ignored_target"', manifest)


if __name__ == "__main__":
    unittest.main()
