"""
체이닝 위험 명령 검사 테스트 (FSD v1.0.115 §3.5)

T-111-50 ~ T-111-56: `&&`, `||`, `;` 분리 후 각 세그먼트의 첫 토큰 검사.
따옴표·이스케이프 인식.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_runner import AgentRunner


def _make_runner(dangerous_set):
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"
    file_manager = MagicMock()
    file_manager.workspace_dir = Path("/tmp/test_workspace")
    terminal_executor = MagicMock()
    terminal_executor.DANGEROUS_COMMANDS = set(dangerous_set)
    env = {
        "AGENT_MAX_ITERATIONS": "10",
        "AGENT_SELF_CORRECT_MAX": "1",
        "AGENT_COMPACT_AFTER": "5",
        "AGENT_CODE_TIMEOUT": "30",
        "AGENT_DONE_TOKEN": "[AGENT_DONE]",
        "AGENT_EVAL_GATE": "0",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("src.agent_runner.CodeExecutor"):
            return AgentRunner(
                assistant=assistant,
                file_manager=file_manager,
                code_executor=MagicMock(),
                terminal_executor=terminal_executor,
                response_parser=MagicMock(),
                cli_handler=MagicMock(),
                context_builder=None,
                streaming=False,
                assistant_role="model",
            )


class TestChainDangerous(unittest.TestCase):
    """T-111-50..56 — 체이닝 위험 명령 검사."""

    def setUp(self):
        # 위험 명령 셋: rm, del
        self.runner = _make_runner({"rm", "del"})

    # ─── T-111-50 ──────────────────────────────────────────
    def test_T111_50_simple_dangerous(self):
        is_dang, bad = self.runner._is_chain_dangerous("rm -rf /")
        self.assertTrue(is_dang)
        self.assertEqual(bad, ["rm -rf /"])

    # ─── T-111-51 ──────────────────────────────────────────
    def test_T111_51_amp_chained_after_safe(self):
        is_dang, bad = self.runner._is_chain_dangerous("echo ok && rm -rf /")
        self.assertTrue(is_dang)
        self.assertIn("rm -rf /", bad)

    # ─── T-111-52 ──────────────────────────────────────────
    def test_T111_52_semicolon_chained(self):
        is_dang, bad = self.runner._is_chain_dangerous("ls; rm -rf /")
        self.assertTrue(is_dang)
        self.assertIn("rm -rf /", bad)

    # ─── T-111-53 ──────────────────────────────────────────
    def test_T111_53_or_chained(self):
        is_dang, bad = self.runner._is_chain_dangerous("false || rm -rf /")
        self.assertTrue(is_dang)
        self.assertIn("rm -rf /", bad)

    # ─── T-111-54 ──────────────────────────────────────────
    def test_T111_54_quoted_dangerous_safe(self):
        # NFR-111-07 — 따옴표 안의 분리자/명령은 분리/검사 대상 아님
        is_dang, _ = self.runner._is_chain_dangerous('echo "rm -rf /"')
        self.assertFalse(is_dang)

    def test_T111_54_quoted_chain_separator_preserved(self):
        # `;` 가 따옴표 안 — 분리하지 않음
        segments = self.runner._split_chained_segments('echo "a;b"')
        self.assertEqual(segments, ['echo "a;b"'])

    # ─── T-111-55 ──────────────────────────────────────────
    def test_T111_55_chained_safe_commands(self):
        is_dang, bad = self.runner._is_chain_dangerous("git status && git diff")
        self.assertFalse(is_dang)
        self.assertEqual(bad, [])

    # ─── T-111-56 ──────────────────────────────────────────
    def test_T111_56_escaped_amp(self):
        # 이스케이프된 `&&` 는 분리하지 않음
        segments = self.runner._split_chained_segments(r"cmd1 \&\& cmd2")
        self.assertEqual(segments, [r"cmd1 \&\& cmd2"])
        is_dang, _ = self.runner._is_chain_dangerous(r"cmd1 \&\& cmd2")
        self.assertFalse(is_dang)


class TestSegmentSplit(unittest.TestCase):
    """_split_chained_segments 직접 검증."""

    def setUp(self):
        self.runner = _make_runner({"rm"})

    def test_simple_no_chain(self):
        self.assertEqual(
            self.runner._split_chained_segments("ls -la"),
            ["ls -la"],
        )

    def test_three_way_amp(self):
        self.assertEqual(
            self.runner._split_chained_segments("a && b && c"),
            ["a", "b", "c"],
        )

    def test_mixed_separators(self):
        self.assertEqual(
            self.runner._split_chained_segments("a && b; c || d"),
            ["a", "b", "c", "d"],
        )

    def test_empty_input(self):
        self.assertEqual(self.runner._split_chained_segments(""), [])


if __name__ == "__main__":
    unittest.main()
