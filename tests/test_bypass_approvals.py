"""
FSD v1.0.100 테스트: Bypass Approvals 모드

T-100-01 ~ T-100-14
"""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_runner import (
    AgentRunner,
    AgentSession,
    AgentStopReason,
    ActionResult,
    IterationRecord,
    _BypassAbort,
)
from src.agents_command import _extract_bypass_flag


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
                streaming=True,
            )
    runner.assistant = assistant
    return runner


def _make_iter(act_text: str = "", actions=None) -> IterationRecord:
    return IterationRecord(
        idx=1, reason_text="", act_text=act_text,
        actions=actions or [],
    )


# ─── T-100-01: _ask_continue() 에 'b' 입력 ────────────────────
class TestAskContinueBypass(unittest.TestCase):

    def test_T100_01_b_returns_bypass(self):
        runner = _make_runner()
        with patch("builtins.input", return_value="b"):
            choice, fb = runner._ask_continue()
        self.assertEqual(choice, 'b')
        self.assertIsNone(fb)


# ─── T-100-02: _enter_bypass_mode() 세션 상태 ─────────────────
class TestEnterBypassMode(unittest.TestCase):

    def test_T100_02_session_flags_set(self):
        runner = _make_runner()
        session = AgentSession(goal="test")
        runner._enter_bypass_mode(session)

        self.assertTrue(session.bypass_approvals)
        self.assertTrue(session.auto_approve_dangerous_shell)
        self.assertTrue(session.auto_approve_file_mutation)
        self.assertIsNotNone(session.bypass_started_at)


# ─── T-100-03: bypass 모드에서 _ask_continue 미호출 ───────────
class TestBypassSkipsAskContinue(unittest.TestCase):

    def test_T100_03_ask_continue_not_called(self):
        runner = _make_runner(AGENT_MAX_ITERATIONS="2")
        runner._build_initial_prompt = MagicMock(return_value="plan")
        runner._call_model = MagicMock(return_value="[AGENT_DONE]")
        runner._execute_actions = MagicMock(return_value=[])
        runner._auto_save = MagicMock()
        runner._input_listener = MagicMock()
        runner._input_listener.enabled = False
        runner._input_listener.is_stop_requested = MagicMock(return_value=False)
        runner._input_listener.paused = MagicMock()
        runner._input_listener.__enter__ = MagicMock(return_value=None)
        runner._input_listener.__exit__ = MagicMock(return_value=False)
        runner._ask_continue = MagicMock(return_value=('c', None))

        session = runner.run(goal="test", bypass_approvals=True)

        runner._ask_continue.assert_not_called()
        self.assertEqual(session.stop_reason, AgentStopReason.DONE)


# ─── T-100-04: _extract_bypass_flag — '-ba' 파싱 ──────────────
class TestExtractBypassFlag(unittest.TestCase):

    def test_T100_04_short_flag(self):
        bypass, remaining = _extract_bypass_flag("-ba 테스트 목표")
        self.assertTrue(bypass)
        self.assertEqual(remaining, "테스트 목표")

    def test_T100_05_long_flag(self):
        bypass, remaining = _extract_bypass_flag("--bypassApprovals 리팩토링")
        self.assertTrue(bypass)
        self.assertEqual(remaining, "리팩토링")

    def test_kebab_flag(self):
        bypass, remaining = _extract_bypass_flag("--bypass-approvals goal")
        self.assertTrue(bypass)
        self.assertEqual(remaining, "goal")

    def test_no_flag(self):
        bypass, remaining = _extract_bypass_flag("일반 목표")
        self.assertFalse(bypass)
        self.assertEqual(remaining, "일반 목표")

    def test_bracket_pattern_untouched(self):
        bypass, remaining = _extract_bypass_flag("[src/*.py]")
        self.assertFalse(bypass)
        self.assertIn("[src/*.py]", remaining)

    def test_env_bypass_default(self):
        with patch.dict(os.environ, {"AGENT_BYPASS_DEFAULT": "true"}):
            bypass, remaining = _extract_bypass_flag("일반 목표")
        self.assertTrue(bypass)

    def test_empty_args(self):
        bypass, remaining = _extract_bypass_flag("")
        self.assertFalse(bypass)
        self.assertEqual(remaining, "")


# ─── T-100-06: 시간 예산 초과 ─────────────────────────────────
class TestBypassTimeoutSafety(unittest.TestCase):

    def test_T100_06_timeout_triggers(self):
        runner = _make_runner(AGENT_BYPASS_TIMEOUT="1")
        session = AgentSession(goal="test")
        session.bypass_approvals = True
        session.bypass_started_at = time.monotonic() - 2  # 2초 경과
        result = runner._check_bypass_safety(session)
        self.assertEqual(result, AgentStopReason.BYPASS_TIMEOUT)

    def test_no_timeout_within_budget(self):
        runner = _make_runner(AGENT_BYPASS_TIMEOUT="1800")
        session = AgentSession(goal="test")
        session.bypass_approvals = True
        session.bypass_started_at = time.monotonic()
        result = runner._check_bypass_safety(session)
        self.assertIsNone(result)


# ─── T-100-07: 정체 탐지 ─────────────────────────────────────
class TestBypassStagnation(unittest.TestCase):

    def test_T100_07_stagnation_triggers(self):
        runner = _make_runner(AGENT_BYPASS_STAGNATION_N="3")
        session = AgentSession(goal="test")
        session.bypass_approvals = True
        session.bypass_started_at = time.monotonic()
        # 3회 연속 성공 액션 없음
        for _ in range(3):
            session.iterations.append(_make_iter(actions=[
                ActionResult(kind="shell", target="cmd", success=False)
            ]))
        result = runner._check_bypass_safety(session)
        self.assertEqual(result, AgentStopReason.BYPASS_STAGNATION)

    def test_no_stagnation_with_success(self):
        runner = _make_runner(AGENT_BYPASS_STAGNATION_N="3")
        session = AgentSession(goal="test")
        session.bypass_approvals = True
        session.bypass_started_at = time.monotonic()
        # 성공 액션 있음 + 루프 탐지 방지를 위해 act_text 다르게 설정
        session.iterations.append(_make_iter(
            act_text="act1",
            actions=[ActionResult(kind="file", target="a.py", success=True)]
        ))
        session.iterations.append(_make_iter(act_text="act2", actions=[]))
        session.iterations.append(_make_iter(act_text="act3", actions=[]))
        result = runner._check_bypass_safety(session)
        self.assertIsNone(result)


# ─── T-100-08: 반복 루프 탐지 ─────────────────────────────────
class TestBypassLoopDetection(unittest.TestCase):

    def test_T100_08_loop_triggers(self):
        runner = _make_runner(AGENT_BYPASS_LOOP_N="3")
        session = AgentSession(goal="test")
        session.bypass_approvals = True
        session.bypass_started_at = time.monotonic()
        same_act = "$ pip install requests"
        # 성공 액션을 포함해 정체 탐지를 방지하고 루프 탐지만 검증
        for _ in range(3):
            session.iterations.append(_make_iter(
                act_text=same_act,
                actions=[ActionResult(kind="file", target="f.py", success=True)]
            ))
        result = runner._check_bypass_safety(session)
        self.assertEqual(result, AgentStopReason.BYPASS_LOOP_DETECTED)

    def test_no_loop_when_different_acts(self):
        runner = _make_runner(AGENT_BYPASS_LOOP_N="3")
        session = AgentSession(goal="test")
        session.bypass_approvals = True
        session.bypass_started_at = time.monotonic()
        # 성공 액션 + 다른 act_text — 정체/루프 모두 없어야 함
        for i in range(3):
            session.iterations.append(_make_iter(
                act_text=f"act {i}",
                actions=[ActionResult(kind="file", target=f"f{i}.py", success=True)]
            ))
        result = runner._check_bypass_safety(session)
        self.assertIsNone(result)


# ─── T-100-09: 위험 액션 한도 ─────────────────────────────────
class TestBypassDangerousLimit(unittest.TestCase):

    def test_T100_09_dangerous_limit_raises(self):
        runner = _make_runner(AGENT_BYPASS_MAX_DANGEROUS="2")
        session = AgentSession(goal="test")
        session.bypass_approvals = True
        session.bypass_dangerous_count = 2  # 이미 한도

        act_text = "$ rm -rf tmp/"
        runner.terminal_executor.DANGEROUS_COMMANDS = {"rm"}

        with self.assertRaises(_BypassAbort):
            runner._run_shell_lines(session, act_text)

        self.assertEqual(session.stop_reason, AgentStopReason.BYPASS_DANGEROUS_LIMIT)

    def test_dangerous_count_increments(self):
        runner = _make_runner(AGENT_BYPASS_MAX_DANGEROUS="5")
        session = AgentSession(goal="test")
        # _enter_bypass_mode 처럼 auto_approve 도 True 설정
        session.bypass_approvals = True
        session.auto_approve_dangerous_shell = True
        session.bypass_dangerous_count = 0

        runner.terminal_executor.DANGEROUS_COMMANDS = {"rm"}
        runner.terminal_executor.execute = MagicMock(return_value={"success": True, "stdout": ""})

        runner._run_shell_lines(session, "$ rm old.txt")
        self.assertEqual(session.bypass_dangerous_count, 1)


# ─── T-100-10: Resume 세션 bypass 초기화 ──────────────────────
class TestResumeBypassReset(unittest.TestCase):

    def test_T100_10_bypass_reset_on_resume(self):
        runner = _make_runner()
        runner._input_listener = MagicMock()
        runner._input_listener.enabled = False
        runner._input_listener.is_stop_requested = MagicMock(return_value=False)
        runner._call_model = MagicMock(return_value="[AGENT_DONE]")
        runner._execute_actions = MagicMock(return_value=[])
        runner._auto_save = MagicMock()
        runner._build_iteration_prompt = MagicMock(return_value="iter_prompt")

        session = AgentSession(goal="test")
        session.bypass_approvals = True   # 이전 세션에서 True 였다고 가정
        session.bypass_started_at = 12345.0
        session.bypass_dangerous_count = 3
        session.plan = "old plan"

        # bypass_approvals=False (기본) 로 resume
        runner.run(resume_session=session, bypass_approvals=False)

        self.assertFalse(session.bypass_approvals)
        self.assertIsNone(session.bypass_started_at)
        self.assertEqual(session.bypass_dangerous_count, 0)


# ─── T-100-11: bypass 중 's' 키 → USER_STOP ──────────────────
class TestBypassAsyncStop(unittest.TestCase):

    def test_T100_11_async_stop_during_bypass(self):
        runner = _make_runner(AGENT_MAX_ITERATIONS="5")
        runner._build_initial_prompt = MagicMock(return_value="plan")
        runner._build_iteration_prompt = MagicMock(return_value="iter")
        runner._execute_actions = MagicMock(return_value=[])
        runner._auto_save = MagicMock()

        call_count = 0

        def model_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return "response"

        runner._call_model = MagicMock(side_effect=model_side_effect)

        # 두 번째 호출 후 stop
        stop_flag = {"triggered": False}

        def stop_check(session):
            if call_count >= 2 and not stop_flag["triggered"]:
                stop_flag["triggered"] = True
                session.stop_reason = AgentStopReason.USER_STOP
                return True
            return False

        runner._check_async_stop = MagicMock(side_effect=stop_check)
        runner._input_listener = MagicMock()
        runner._input_listener.enabled = False

        session = runner.run(goal="test", bypass_approvals=True)
        self.assertEqual(session.stop_reason, AgentStopReason.USER_STOP)


# ─── T-100-12: /agents -ba stop → 경고 + 무시 ────────────────
class TestBypassWithStop(unittest.TestCase):

    def test_T100_12_bypass_flag_on_stop_warns(self):
        from src.agents_command import handle_agents_command
        assistant = MagicMock()
        assistant.file_manager.workspace_dir = Path("/tmp")
        cli_handler = MagicMock()

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            handle_agents_command(assistant, cli_handler, True, "-ba stop")
        output = buf.getvalue()
        self.assertIn("-ba", output)
        self.assertIn("stop", output.lower())


# ─── T-100-13: MAX_ITERATIONS 먼저 도달 ───────────────────────
class TestBypassMaxIterations(unittest.TestCase):

    def test_T100_13_max_iterations_wins_over_bypass(self):
        runner = _make_runner(
            AGENT_MAX_ITERATIONS="2",
            AGENT_BYPASS_TIMEOUT="1800",
        )
        runner._build_initial_prompt = MagicMock(return_value="plan")
        runner._build_iteration_prompt = MagicMock(return_value="iter")
        runner._call_model = MagicMock(return_value="normal response")
        runner._execute_actions = MagicMock(return_value=[
            ActionResult(kind="file", target="f.py", success=True)
        ])
        runner._auto_save = MagicMock()
        runner._input_listener = MagicMock()
        runner._input_listener.enabled = False
        runner._input_listener.is_stop_requested = MagicMock(return_value=False)

        session = runner.run(goal="test", bypass_approvals=True)
        self.assertEqual(session.stop_reason, AgentStopReason.MAX_ITERATIONS)


if __name__ == "__main__":
    unittest.main()
