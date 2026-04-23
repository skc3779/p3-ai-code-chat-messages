"""
FSD v1.0.101 테스트: /agents -s <N> 플래그 및 Resume 숫자 인덱스 지원

T-101-01 ~ T-101-18
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents_command import (
    _extract_steps_flag,
    _resolve_resume_target,
    _extract_bypass_flag,
)
from src.agent_runner import AgentRunner, AgentSession, AgentStopReason, IterationRecord


# ─── 헬퍼 ──────────────────────────────────────────────────────
def _make_runner(**env_overrides) -> AgentRunner:
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"

    file_manager = MagicMock()
    file_manager.workspace_dir = Path("/tmp/test_workspace")

    terminal_executor = MagicMock()
    terminal_executor.DANGEROUS_COMMANDS = {"rm", "del", "move", "mv"}

    env = {
        "AGENT_MAX_ITERATIONS": "10",
        "AGENT_SELF_CORRECT_MAX": "3",
        "AGENT_COMPACT_AFTER": "5",
        "AGENT_CODE_TIMEOUT": "30",
        "AGENT_DONE_TOKEN": "[AGENT_DONE]",
        "AGENT_BYPASS_TIMEOUT": "1800",
        "AGENT_BYPASS_STAGNATION_N": "3",
        "AGENT_BYPASS_LOOP_N": "3",
        "AGENT_BYPASS_MAX_DANGEROUS": "5",
    }
    env.update(env_overrides)

    with patch.dict(os.environ, env, clear=False):
        with patch("src.agent_runner.CodeExecutor"):
            runner = AgentRunner(
                assistant=assistant,
                file_manager=file_manager,
                code_executor=MagicMock(),
                terminal_executor=terminal_executor,
                response_parser=MagicMock(),
                cli_handler=MagicMock(),
                context_builder=None,
                streaming=False,
                assistant_role="assistant",
            )
    return runner


def _make_store(sessions: list) -> MagicMock:
    store = MagicMock()
    store.list_sessions.return_value = sessions
    store.load.side_effect = lambda fname: AgentSession(goal=f"goal_{fname}")
    return store


# ═══════════════════════════════════════════════════════════════
# T-101-01 ~ T-101-07: _extract_steps_flag
# ═══════════════════════════════════════════════════════════════

class TestExtractStepsFlag(unittest.TestCase):

    def test_T101_01_short_flag(self):
        """T-101-01: -s 5 goal → (5, 'goal')"""
        override, rest = _extract_steps_flag("-s 5 goal")
        self.assertEqual(override, 5)
        self.assertEqual(rest, "goal")

    def test_T101_02_long_flag_with_pattern(self):
        """T-101-02: --steps 20 [src/*.py] goal → (20, '[src/*.py] goal')"""
        override, rest = _extract_steps_flag("--steps 20 [src/*.py] goal")
        self.assertEqual(override, 20)
        self.assertEqual(rest, "[src/*.py] goal")

    def test_T101_03_zero_value(self):
        """T-101-03: -s 0 goal → (None, 'goal') + 경고"""
        with patch("builtins.print") as mock_print:
            override, rest = _extract_steps_flag("-s 0 goal")
        self.assertIsNone(override)
        self.assertEqual(rest, "goal")
        mock_print.assert_called_once()
        self.assertIn("양의 정수", mock_print.call_args[0][0])

    def test_T101_04_non_numeric_value(self):
        """T-101-04: -s abc goal → (None, 'goal') + 경고"""
        with patch("builtins.print") as mock_print:
            override, rest = _extract_steps_flag("-s abc goal")
        self.assertIsNone(override)
        self.assertEqual(rest, "goal")
        mock_print.assert_called_once()

    def test_T101_05_missing_value(self):
        """T-101-05: -s (값 누락) → (None, '') + 경고"""
        with patch("builtins.print") as mock_print:
            override, rest = _extract_steps_flag("-s")
        self.assertIsNone(override)
        self.assertEqual(rest, "")
        mock_print.assert_called_once()
        self.assertIn("누락", mock_print.call_args[0][0])

    def test_T101_06_combined_with_bypass_pipeline(self):
        """T-101-06: bypass 추출 후 _extract_steps_flag('-s 7 goal') → (7, 'goal')"""
        _, after_bypass = _extract_bypass_flag("-ba -s 7 goal")
        override, rest = _extract_steps_flag(after_bypass)
        self.assertEqual(override, 7)
        self.assertEqual(rest, "goal")

    def test_T101_07_no_flag(self):
        """T-101-07: 플래그 없는 args → (None, 원본)"""
        override, rest = _extract_steps_flag("goal without flag")
        self.assertIsNone(override)
        self.assertEqual(rest, "goal without flag")


# ═══════════════════════════════════════════════════════════════
# T-101-08 ~ T-101-10: AgentRunner.run() 오버라이드
# ═══════════════════════════════════════════════════════════════

class TestRunMaxIterationsOverride(unittest.TestCase):

    def _make_done_assistant(self, done_after: int):
        """done_after 번째 호출에서 [AGENT_DONE] 을 반환하는 assistant mock."""
        call_count = {"n": 0}

        def fake_chat(*_args, **_kwargs):
            call_count["n"] += 1
            if call_count["n"] >= done_after:
                return "[REASON] done\n[ACT] nothing\n[OBSERVE] ok\n[AGENT_DONE]"
            return "[REASON] working\n[ACT] nothing\n[OBSERVE] in progress"

        assistant = MagicMock()
        assistant.conversation_history = []
        assistant.system_prompt = "sys"
        assistant.chat.side_effect = fake_chat
        return assistant

    def test_T101_08_loop_respects_override(self):
        """T-101-08: max_iterations_override=3 이면 최대 3회 후 종료"""
        runner = _make_runner(AGENT_MAX_ITERATIONS="10")
        runner.assistant.chat.return_value = "[REASON] r\n[ACT] a\n[OBSERVE] o"
        runner._ask_continue = MagicMock(return_value=('c', None))
        runner._input_listener = MagicMock()
        runner._input_listener.enabled = False
        runner._input_listener.is_stop_requested = MagicMock(return_value=False)

        with patch("src.agent_session_store.AgentSessionStore"):
            session = runner.run(goal="test", max_iterations_override=3)

        self.assertEqual(session.stop_reason, AgentStopReason.MAX_ITERATIONS)
        self.assertEqual(len(session.iterations), 3)

    def test_T101_09_instance_max_iterations_unchanged(self):
        """T-101-09: run() 후 runner.max_iterations 는 변경 없음"""
        runner = _make_runner(AGENT_MAX_ITERATIONS="10")
        runner.assistant.chat.return_value = "[REASON] r\n[ACT] a\n[OBSERVE] o"

        with patch("src.agent_session_store.AgentSessionStore"):
            runner.run(goal="test", max_iterations_override=3)

        self.assertEqual(runner.max_iterations, 10)

    def test_T101_10_header_shows_override(self):
        """T-101-10: _print_header 출력에 'Iteration 1/3' 포함 (오버라이드=3)"""
        runner = _make_runner(AGENT_MAX_ITERATIONS="10")
        session = AgentSession(goal="test")
        session.effective_max_iterations = 3

        with patch("builtins.print") as mock_print:
            runner._print_header(session, 1)

        output = " ".join(str(c) for c in mock_print.call_args[0])
        self.assertIn("1/3", output)


# ═══════════════════════════════════════════════════════════════
# T-101-11 ~ T-101-13: _resolve_resume_target
# ═══════════════════════════════════════════════════════════════

class TestResolveResumeTarget(unittest.TestCase):

    def test_T101_11_numeric_index(self):
        """T-101-11: '2' → list_sessions()[1] 의 filename 으로 load"""
        sessions = [
            {"filename": "agent_1.json"},
            {"filename": "agent_2.json"},
            {"filename": "agent_3.json"},
        ]
        store = _make_store(sessions)
        result = _resolve_resume_target("2", store)
        store.load.assert_called_once_with("agent_2.json")
        self.assertIsNotNone(result)

    def test_T101_12_out_of_range(self):
        """T-101-12: '0' 및 '999' → None + 에러 메시지"""
        sessions = [{"filename": "agent_1.json"}]
        store = _make_store(sessions)

        with patch("builtins.print") as mock_print:
            result_zero = _resolve_resume_target("0", store)
        self.assertIsNone(result_zero)
        self.assertIn("범위 초과", mock_print.call_args[0][0])

        with patch("builtins.print") as mock_print:
            result_big = _resolve_resume_target("999", store)
        self.assertIsNone(result_big)

    def test_T101_13_filename_passthrough(self):
        """T-101-13: 파일명 문자열 → store.load(filename) 직접 호출"""
        store = _make_store([])
        store.load.return_value = AgentSession(goal="loaded")
        result = _resolve_resume_target("agent_xxx.json", store)
        store.load.assert_called_once_with("agent_xxx.json")
        self.assertIsNotNone(result)


# ═══════════════════════════════════════════════════════════════
# T-101-14: 직렬화 제외 검증
# ═══════════════════════════════════════════════════════════════

class TestSerializeExcludesEffectiveMax(unittest.TestCase):

    def test_T101_14_not_in_json(self):
        """T-101-14: _serialize() 결과 JSON 에 effective_max_iterations 키 없음"""
        import json
        import tempfile
        from src.agent_session_store import AgentSessionStore

        session = AgentSession(goal="test")
        session.effective_max_iterations = 20

        with tempfile.TemporaryDirectory() as tmpdir:
            store = AgentSessionStore(tmpdir)
            json_str = store._serialize(session)

        data = json.loads(json_str)
        self.assertNotIn("effective_max_iterations", data)


# ═══════════════════════════════════════════════════════════════
# T-101-15: Resume 시 effective_max_iterations 재초기화
# ═══════════════════════════════════════════════════════════════

class TestResumeResetsEffectiveMax(unittest.TestCase):

    def test_T101_15_reset_on_resume(self):
        """T-101-15: resume 된 세션의 effective_max_iterations 는 run() 초기에 None → 재계산"""
        runner = _make_runner(AGENT_MAX_ITERATIONS="10")
        runner.assistant.chat.return_value = "[REASON] r\n[ACT] a\n[OBSERVE] o"

        # 이전 실행에서 20으로 설정된 세션을 resume
        prev_session = AgentSession(goal="prev")
        prev_session.effective_max_iterations = 20
        prev_session.iterations = [
            IterationRecord(idx=1, reason_text="r", act_text="a", observe_text="o")
        ]

        with patch("src.agent_session_store.AgentSessionStore"):
            result = runner.run(resume_session=prev_session)

        # override 없이 resume → effective_max = self.max_iterations (10)
        self.assertEqual(result.effective_max_iterations, 10)


# ═══════════════════════════════════════════════════════════════
# T-101-16 ~ T-101-18: handle_agents_command 파싱 통합
# ═══════════════════════════════════════════════════════════════

class TestHandleAgentsCommandParsing(unittest.TestCase):

    def _make_assistant(self):
        assistant = MagicMock()
        assistant.file_manager.workspace_dir = Path("/tmp/ws")
        assistant.code_executor = MagicMock()
        assistant.terminal_executor = MagicMock()
        assistant.terminal_executor.DANGEROUS_COMMANDS = set()
        assistant.response_parser = MagicMock()
        assistant.context_builder = None
        return assistant

    @patch("src.agent_runner.AgentRunner")
    @patch("src.agent_session_store.AgentSessionStore")
    def test_T101_16_bypass_and_override_combined(self, MockStore, MockRunner):
        """T-101-16: '-s 20 -ba goal' → runner.run(bypass=True, override=20)"""
        from src.agents_command import handle_agents_command

        cli_handler = MagicMock()
        cli_handler.get_multiline.return_value = "test goal"

        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run.return_value = AgentSession(goal="test goal")

        handle_agents_command(
            assistant=self._make_assistant(),
            cli_handler=cli_handler,
            streaming=False,
            args="-s 20 -ba",
        )

        call_kwargs = mock_runner_instance.run.call_args
        self.assertTrue(call_kwargs.kwargs.get("bypass_approvals"))
        self.assertEqual(call_kwargs.kwargs.get("max_iterations_override"), 20)

    @patch("src.agent_session_store.AgentSessionStore")
    def test_T101_17_steps_ignored_on_list(self, mock_store_class):
        """T-101-17: '-s 20 list' → 경고 출력 + list 정상 동작"""
        from src.agents_command import handle_agents_command

        mock_store = mock_store_class.return_value
        assistant = self._make_assistant()

        with patch("builtins.print") as mock_print:
            handle_agents_command(
                assistant=assistant,
                cli_handler=MagicMock(),
                streaming=False,
                args="-s 20 list",
            )

        printed = " ".join(str(c[0][0]) for c in mock_print.call_args_list if c[0])
        self.assertIn("-s", printed)
        mock_store.print_session_list.assert_called_once()

    @patch("src.agent_runner.AgentRunner")
    @patch("src.agent_session_store.AgentSessionStore")
    def test_T101_18_steps_resume_by_index(self, MockStore, MockRunner):
        """T-101-18: '-s 30 resume 1' → 1번 세션 복원 + override=30 전달"""
        from src.agents_command import handle_agents_command

        sessions = [{"filename": "agent_abc.json"}]
        mock_store = MockStore.return_value
        mock_store.list_sessions.return_value = sessions
        mock_store.load.return_value = AgentSession(goal="resumed goal")

        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run.return_value = AgentSession(goal="resumed goal")

        handle_agents_command(
            assistant=self._make_assistant(),
            cli_handler=MagicMock(),
            streaming=False,
            args="-s 30 resume 1",
                )

        mock_store.load.assert_called_once_with("agent_abc.json")
        call_kwargs = mock_runner_instance.run.call_args
        self.assertEqual(call_kwargs.kwargs.get("max_iterations_override"), 30)


if __name__ == "__main__":
    unittest.main()
