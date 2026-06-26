"""
AgentInputListener Unit Tests (FSD v1.0.087)

T-087-01 ~ T-087-10: 비동기 stop 리스너 및 AgentRunner 통합 테스트
"""

import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_input_listener import AgentInputListener
from src.agent_runner import (
    AgentRunner,
    AgentSession,
    AgentStopReason,
)


# ─── 헬퍼 ────────────────────────────────────────────────────────
def _make_runner(**env_overrides) -> AgentRunner:
    """의존성을 모두 Mock 으로 대체한 AgentRunner 생성."""
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"

    file_manager = MagicMock()
    file_manager.workspace_dir = Path("/tmp/test_workspace")

    terminal_executor = MagicMock()
    terminal_executor.DANGEROUS_COMMANDS = {"rm", "del", "move", "mv"}

    env = {
        "AGENT_MAX_ITERATIONS": "5",
        "AGENT_SELF_CORRECT_MAX": "3",
        "AGENT_COMPACT_AFTER": "5",
        "AGENT_CODE_TIMEOUT": "30",
        "AGENT_DONE_TOKEN": "[AGENT_DONE]",
        "AGENT_AUTO_SAVE_INTERVAL": "0",
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
                assistant_role="model",
            )
    runner.assistant = assistant
    return runner


# ─── T-087-A: AgentInputListener 자체 동작 ─────────────────────
class TestInputListenerCore(unittest.TestCase):

    def test_T087_A01_initial_state_no_stop(self):
        """T-087-A01: 초기 상태에서 is_stop_requested() == False"""
        listener = AgentInputListener()
        self.assertFalse(listener.is_stop_requested())

    def test_T087_A02_clear_stop_resets_flag(self):
        """T-087-A02: clear_stop() 호출 시 플래그가 초기화됨"""
        listener = AgentInputListener()
        listener._stop_event.set()
        self.assertTrue(listener.is_stop_requested())
        listener.clear_stop()
        self.assertFalse(listener.is_stop_requested())

    def test_T087_A03_disabled_when_not_tty(self):
        """T-087-A03: stdin 이 TTY 가 아니면 enabled=False"""
        with patch.object(AgentInputListener, "_detect_tty", return_value=False):
            listener = AgentInputListener()
            self.assertFalse(listener.enabled)

    def test_T087_A04_start_does_nothing_when_disabled(self):
        """T-087-A04: enabled=False 이면 start() 가 스레드를 만들지 않음"""
        with patch.object(AgentInputListener, "_detect_tty", return_value=False):
            listener = AgentInputListener()
            listener.start()
            self.assertFalse(listener.is_listening)

    def test_T087_A05_stop_is_idempotent(self):
        """T-087-A05: stop() 반복 호출 안전성"""
        with patch.object(AgentInputListener, "_detect_tty", return_value=False):
            listener = AgentInputListener()
            listener.stop()
            listener.stop()  # 에러 없이 동작해야 함

    def test_T087_A06_start_stop_repeatable(self):
        """T-087-A06 (≈T-087-07): 리스너 start/stop 을 5회 반복해도 안정적"""
        with patch.object(AgentInputListener, "_detect_tty", return_value=True):
            listener = AgentInputListener(poll_interval=0.02)
            # _listen_loop 을 짧게 끝나도록 오버라이드
            listener._listen_loop = lambda: None  # type: ignore[method-assign]
            for _ in range(5):
                listener.start()
                listener.stop()

    def test_T087_A07_paused_context_pauses_and_resumes(self):
        """T-087-A07: paused() 컨텍스트 진입 시 스레드 중지, 탈출 시 재개"""
        with patch.object(AgentInputListener, "_detect_tty", return_value=True):
            listener = AgentInputListener(poll_interval=0.02)
            # 폴링 루프는 단순히 _active 가 False 가 될 때까지 대기
            def fake_loop():
                while listener._active.is_set():
                    time.sleep(0.01)
            listener._listen_loop = fake_loop  # type: ignore[method-assign]

            listener.start()
            time.sleep(0.05)
            self.assertTrue(listener.is_listening)

            with listener.paused():
                # 잠깐 기다려 스레드가 _active=False 를 감지하게 한다
                time.sleep(0.1)
                self.assertFalse(listener.is_listening)

            # 컨텍스트 탈출 후 다시 실행 중이어야 함
            time.sleep(0.05)
            self.assertTrue(listener.is_listening)
            listener.stop()

    def test_T087_A08_paused_when_not_listening_is_noop(self):
        """T-087-A08: 리스너가 실행 중이 아닐 때 paused() 는 부작용 없음"""
        with patch.object(AgentInputListener, "_detect_tty", return_value=False):
            listener = AgentInputListener()
            with listener.paused():
                self.assertFalse(listener.is_listening)
            self.assertFalse(listener.is_listening)

    def test_T087_A09_unix_poll_reads_single_stop_key_without_enter(self):
        """Unix/WSL: canonical readline 없이 단일 's' 키로 stop 을 감지."""
        class FakeStdin:
            def fileno(self):
                return 99

        fake_stdin = FakeStdin()
        with patch.object(AgentInputListener, "_detect_tty", return_value=True):
            listener = AgentInputListener(poll_interval=0.01)

        listener._active.set()
        with patch("src.agent_input_listener.sys.stdin", fake_stdin):
            with patch("select.select", return_value=([fake_stdin], [], [])):
                with patch("src.agent_input_listener.os.read", return_value=b"s"):
                    listener._poll_unix()

        self.assertTrue(listener.is_stop_requested())

    def test_T087_A10_stop_restores_saved_terminal_state(self):
        """stop() 은 리스너가 바꾼 Unix 터미널 속성을 즉시 원복한다."""
        import fcntl
        import termios

        with patch.object(AgentInputListener, "_detect_tty", return_value=True):
            listener = AgentInputListener(poll_interval=0.01)
        listener._terminal_fd = 99
        listener._terminal_attrs = ["old-attrs"]
        listener._terminal_flags = 123

        with patch.object(termios, "tcsetattr") as mock_tcsetattr:
            with patch.object(fcntl, "fcntl") as mock_fcntl:
                listener.stop()

        mock_tcsetattr.assert_called_once_with(99, termios.TCSADRAIN, ["old-attrs"])
        mock_fcntl.assert_called_once_with(99, fcntl.F_SETFL, 123)


# ─── T-087-B: AgentRunner 통합 (checkpoint 동작) ──────────────
class TestRunnerAsyncStop(unittest.TestCase):
    """AgentRunner 가 비동기 stop 을 각 체크포인트에서 감지하는지 검증."""

    def _patch_listener(self, runner: AgentRunner) -> MagicMock:
        """runner._input_listener 를 Mock 으로 교체하고 반환."""
        fake = MagicMock()
        fake.enabled = False        # 안내 메시지 생략
        fake.is_stop_requested = MagicMock(return_value=False)
        fake.is_stop_requested.side_effect = None
        # paused() 는 컨텍스트 매니저 반환
        class _Ctx:
            def __enter__(self_inner): return fake
            def __exit__(self_inner, *exc): return False
        fake.paused = MagicMock(return_value=_Ctx())
        runner._input_listener = fake
        return fake

    def test_T087_01_stop_at_iteration_start(self):
        """T-087-01: iteration 시작 체크포인트에서 stop 감지 → 즉시 종료"""
        runner = _make_runner()
        fake = self._patch_listener(runner)

        # 첫 번째 호출에서 stop 요청
        fake.is_stop_requested.return_value = True

        runner.assistant.chat.return_value = "[REASON]r[ACTION]a[OBSERVE]o"

        session = AgentSession(goal="g", plan="p")
        # resume_session 경로로 진입하여 PLAN 호출 없이 바로 루프로
        result = runner.run(resume_session=session)

        self.assertEqual(result.stop_reason, AgentStopReason.USER_STOP)
        self.assertEqual(len(result.iterations), 0, "iteration 이 실행되지 않아야 함")

    def test_T087_03_stop_after_model_call(self):
        """T-087-03: 모델 호출 후 체크포인트에서 stop 감지"""
        runner = _make_runner()
        fake = self._patch_listener(runner)

        # 첫 체크포인트(iteration 시작)는 False, 두 번째(모델 호출 후)는 True
        fake.is_stop_requested.side_effect = [False, True]

        def fake_chat(prompt, streaming, include_context):
            return "[REASON]이유[ACTION]행동[OBSERVE]관찰"
        runner.assistant.chat.side_effect = fake_chat

        session = AgentSession(goal="g", plan="p")
        result = runner.run(resume_session=session)

        self.assertEqual(result.stop_reason, AgentStopReason.USER_STOP)
        # _call_model 은 실행되었지만, 액션은 실행되지 않고 중단
        self.assertEqual(len(result.iterations), 0,
                         "체크포인트 2 에서 중단 → iterations 에 추가되지 않음")

    def test_T087_03b_stop_after_initial_plan_model_call(self):
        """신규 세션 PLAN 생성 중 's' 입력 → 승인 프롬프트 없이 USER_STOP."""
        runner = _make_runner()
        fake = self._patch_listener(runner)
        fake.is_stop_requested.return_value = True
        runner.assistant.chat.return_value = "1. plan"

        result = runner.run(goal="g")

        self.assertEqual(result.stop_reason, AgentStopReason.USER_STOP)
        self.assertEqual(result.plan, "1. plan")
        self.assertEqual(len(result.iterations), 0)

    def test_T087_04_stop_after_actions(self):
        """T-087-04: 액션 실행 후 체크포인트에서 stop 감지"""
        runner = _make_runner()
        fake = self._patch_listener(runner)

        # cp1=False, cp2=False, cp3=True
        fake.is_stop_requested.side_effect = [False, False, True]
        runner.assistant.chat.return_value = "[REASON]r[ACTION]a[OBSERVE]o"

        session = AgentSession(goal="g", plan="p")
        result = runner.run(resume_session=session)

        self.assertEqual(result.stop_reason, AgentStopReason.USER_STOP)
        self.assertEqual(len(result.iterations), 1,
                         "한 iteration 은 완료되어 기록됨")

    def test_T087_05_ask_continue_pauses_listener(self):
        """T-087-05: _ask_continue 진입 시 listener.paused() 호출"""
        runner = _make_runner(AGENT_MAX_ITERATIONS="2")
        fake = self._patch_listener(runner)
        fake.is_stop_requested.return_value = False

        runner.assistant.chat.return_value = "[REASON]r[ACTION]a[OBSERVE]o"

        # _ask_continue 을 's' 로 즉시 중단 — 한 번만 호출되도록
        runner._ask_continue = MagicMock(return_value=('s', None))

        session = AgentSession(goal="g", plan="p")
        runner.run(resume_session=session)

        # paused() 가 최소 1회 이상 사용되어야 함 (_ask_continue 진입 시)
        self.assertGreaterEqual(
            fake.paused.call_count, 1,
            "_ask_continue 호출 전 listener.paused() 가 사용되어야 함",
        )

    def test_T087_06_ctrlc_still_works(self):
        """T-087-06: KeyboardInterrupt 는 여전히 USER_STOP 으로 처리됨"""
        runner = _make_runner()
        fake = self._patch_listener(runner)
        fake.is_stop_requested.return_value = False

        def raise_kb(*_args, **_kwargs):
            raise KeyboardInterrupt()
        runner.assistant.chat.side_effect = raise_kb

        session = AgentSession(goal="g", plan="p")
        result = runner.run(resume_session=session)

        self.assertEqual(result.stop_reason, AgentStopReason.USER_STOP)

    def test_T087_runner_stops_listener_in_finally(self):
        """T-087-B: run() 종료 시 listener.stop() 이 반드시 호출됨"""
        runner = _make_runner()
        fake = self._patch_listener(runner)
        fake.is_stop_requested.return_value = True  # 즉시 중단

        session = AgentSession(goal="g", plan="p")
        runner.run(resume_session=session)

        fake.stop.assert_called()

    def test_T087_runner_starts_listener_on_entry(self):
        """T-087-B2: run() 진입 시 listener.start() 가 호출됨"""
        runner = _make_runner()
        fake = self._patch_listener(runner)
        fake.is_stop_requested.return_value = True

        session = AgentSession(goal="g", plan="p")
        runner.run(resume_session=session)

        fake.start.assert_called_once()
        # P4: run() 진입 시 clear_all() 로 stop/steer/pause 플래그를 모두 초기화.
        fake.clear_all.assert_called_once()

    def test_T087_check_async_stop_helper(self):
        """T-087-B3: _check_async_stop() 이 세션의 stop_reason 설정"""
        runner = _make_runner()
        fake = self._patch_listener(runner)
        fake.is_stop_requested.return_value = True

        session = AgentSession(goal="g")
        self.assertTrue(runner._check_async_stop(session))
        self.assertEqual(session.stop_reason, AgentStopReason.USER_STOP)

    def test_T087_check_async_stop_false_keeps_session(self):
        """T-087-B4: stop 요청 없으면 세션 stop_reason 변경 없음"""
        runner = _make_runner()
        fake = self._patch_listener(runner)
        fake.is_stop_requested.return_value = False

        session = AgentSession(goal="g")
        self.assertFalse(runner._check_async_stop(session))
        self.assertIsNone(session.stop_reason)


# ─── T-087-10: /agents stop 명령 메시지 갱신 ────────────────────
class TestAgentsStopCommandMessage(unittest.TestCase):

    def test_T087_10_stop_prints_new_guidance(self):
        """T-087-10: '/agents stop' 안내 메시지에 's' 키 언급 포함"""
        from src.agents_command import handle_agents_command

        with patch("builtins.print") as mock_print:
            handle_agents_command(
                assistant=MagicMock(),
                cli_handler=MagicMock(),
                streaming=True,
                args="stop",
            )
        # 출력 문자열을 합쳐서 확인
        printed = "\n".join(
            " ".join(str(a) for a in call.args)
            for call in mock_print.call_args_list
        )
        self.assertIn("'s'", printed, "'s' 키 안내가 누락됨")


# ─── T-087-11: 커맨드 레지스트리 설명 갱신 ─────────────────────
class TestCommandRegistryDescription(unittest.TestCase):

    def test_T087_11_registry_mentions_s_key(self):
        """T-087-11: CommandRegistry 의 '/agents' 설명에 's' 키 명시"""
        from src.command_registry import CommandRegistry

        registry = CommandRegistry()
        cmd = registry.get_command("/agents")
        self.assertIsNotNone(cmd)
        self.assertIn("'s'", cmd.description,
                      "'/agents' 설명에 's' 키 중단 안내가 없음")


if __name__ == "__main__":
    unittest.main()
