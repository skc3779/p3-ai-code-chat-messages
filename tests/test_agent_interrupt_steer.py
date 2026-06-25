"""
FSD v1.1.062 P4 테스트: 인터럽트·스티어 + 양방향 전환 + per-action 정책

A. 인터럽트 리스너 우선순위·소비·비-TTY (AgentInputListener)
B. per_action_decision 매트릭스 (agent_policy)
C. per_action_gate 후방호환 핵심 (agent_runner)
D. 잔여 액션 보존 (AgentActionDispatcher)
E. 스티어/전환 (agent_runner mock)
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_input_listener import AgentInputListener
from src.agent_policy import (
    ACTION_APPROVE,
    ACTION_AUTO,
    ACTION_STOP,
    ACTKIND_CODE,
    ACTKIND_FILE,
    ACTKIND_SHELL,
    POLICY_AUTO,
    POLICY_AUTO_EDIT,
    POLICY_INTERACTIVE,
    POLICY_ON_FAILURE,
    per_action_decision,
)
from src.agent_runner import (
    AgentRunner,
    AgentSession,
    AgentStopReason,
    _InterruptOutcome,
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
        "AGENT_EVAL_GATE": "0",
        "AGENT_REFINE_LOOP": "0",
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
                assistant_role="model",
            )
    runner.assistant = assistant
    return runner


def _make_session(**kwargs) -> AgentSession:
    """기본값이 채워진 AgentSession 생성."""
    defaults = dict(
        goal="test goal",
        interaction_policy=POLICY_INTERACTIVE,
        bypass_approvals=False,
        auto_approve_dangerous_shell=False,
        auto_approve_file_mutation=False,
    )
    defaults.update(kwargs)
    return AgentSession(**defaults)


# ═══════════════════════════════════════════════════════════════
# A. 인터럽트 리스너 우선순위·소비·비-TTY
# ═══════════════════════════════════════════════════════════════

class TestInterruptListenerPriority(unittest.TestCase):
    """A. AgentInputListener 우선순위 (s > p > i)."""

    def test_A01_stop_beats_pause_and_steer(self):
        """s+p+i 동시 버퍼: stop 최우선 — pause/steer flush."""
        listener = AgentInputListener()
        # 세 이벤트 직접 세팅
        listener._steer_event.set()
        listener._pause_event.set()
        # stop 적용 — _apply_key 호출
        stopped = listener._apply_key("stop")
        self.assertTrue(stopped)
        self.assertTrue(listener.is_stop_requested())
        self.assertFalse(listener.is_pause_requested())
        self.assertFalse(listener.is_steer_requested())

    def test_A02_pause_beats_steer(self):
        """p+i 동시 버퍼: pause 우선 — steer flush."""
        listener = AgentInputListener()
        listener._steer_event.set()
        # pause 적용
        stopped = listener._apply_key("pause")
        self.assertFalse(stopped)
        self.assertTrue(listener.is_pause_requested())
        self.assertFalse(listener.is_steer_requested())

    def test_A03_steer_ignored_when_stop_buffered(self):
        """stop 이미 버퍼됐을 때 steer 입력 → 무시."""
        listener = AgentInputListener()
        listener._stop_event.set()
        listener._apply_key("steer")
        # steer 이벤트가 세팅되지 않아야 한다
        self.assertFalse(listener.is_steer_requested())

    def test_A04_steer_ignored_when_pause_buffered(self):
        """pause 이미 버퍼됐을 때 steer 입력 → 무시."""
        listener = AgentInputListener()
        listener._pause_event.set()
        listener._apply_key("steer")
        self.assertFalse(listener.is_steer_requested())

    def test_A05_pop_steer_consume_then_none(self):
        """pop_steer_request: 첫 번째 호출 True, 두 번째 None (소비)."""
        listener = AgentInputListener()
        listener._steer_event.set()
        first = listener.pop_steer_request()
        second = listener.pop_steer_request()
        self.assertTrue(first)
        self.assertIsNone(second)

    def test_A06_pop_pause_consume(self):
        """pop_pause_request: 있으면 True, 없으면 False."""
        listener = AgentInputListener()
        listener._pause_event.set()
        self.assertTrue(listener.pop_pause_request())
        self.assertFalse(listener.pop_pause_request())

    def test_A07_clear_all_resets_all_flags(self):
        """clear_all: stop/steer/pause 모두 초기화."""
        listener = AgentInputListener()
        listener._stop_event.set()
        listener._steer_event.set()
        listener._pause_event.set()
        listener.clear_all()
        self.assertFalse(listener.is_stop_requested())
        self.assertFalse(listener.is_steer_requested())
        self.assertFalse(listener.is_pause_requested())

    def test_A08_disabled_listener_noop(self):
        """비-TTY(enabled=False): 모든 인터럽트 no-op (start 무시, 플래그 조작 유지)."""
        listener = AgentInputListener()
        listener._enabled = False
        # start 는 무시
        listener.start()
        self.assertFalse(listener.is_listening)
        # 플래그 직접 세팅은 still 작동 (메인 루프가 직접 세팅 가능성)
        listener._steer_event.set()
        self.assertTrue(listener.is_steer_requested())

    def test_A09_classify_key_stop(self):
        """_classify_key: Unix s → 'stop'."""
        listener = AgentInputListener()
        self.assertEqual(listener._classify_key("s", char_mode=False), "stop")
        self.assertEqual(listener._classify_key("stop", char_mode=False), "stop")

    def test_A10_classify_key_pause_steer(self):
        """_classify_key: Unix p → 'pause', i → 'steer'."""
        listener = AgentInputListener()
        self.assertEqual(listener._classify_key("p", char_mode=False), "pause")
        self.assertEqual(listener._classify_key("i", char_mode=False), "steer")

    def test_A11_classify_key_unknown_returns_none(self):
        """_classify_key: 알 수 없는 키 → None."""
        listener = AgentInputListener()
        self.assertIsNone(listener._classify_key("x", char_mode=False))
        self.assertIsNone(listener._classify_key("z", char_mode=True))


# ═══════════════════════════════════════════════════════════════
# B. per_action_decision 매트릭스
# ═══════════════════════════════════════════════════════════════

class TestPerActionDecisionMatrix(unittest.TestCase):
    """B. per_action_decision 매트릭스 — 7+ 케이스."""

    # auto-edit
    def test_B01_auto_edit_file_is_auto(self):
        self.assertEqual(
            per_action_decision(POLICY_AUTO_EDIT, ACTKIND_FILE), ACTION_AUTO
        )

    def test_B02_auto_edit_shell_is_approve(self):
        self.assertEqual(
            per_action_decision(POLICY_AUTO_EDIT, ACTKIND_SHELL), ACTION_APPROVE
        )

    def test_B03_auto_edit_code_is_approve(self):
        self.assertEqual(
            per_action_decision(POLICY_AUTO_EDIT, ACTKIND_CODE), ACTION_APPROVE
        )

    def test_B04_auto_edit_dangerous_shell_is_approve(self):
        """auto-edit + 위험 셸 → approve (is_dangerous 우선)."""
        self.assertEqual(
            per_action_decision(POLICY_AUTO_EDIT, ACTKIND_SHELL, is_dangerous=True),
            ACTION_APPROVE,
        )

    # on-failure
    def test_B05_on_failure_file_is_stop(self):
        self.assertEqual(
            per_action_decision(POLICY_ON_FAILURE, ACTKIND_FILE), ACTION_STOP
        )

    def test_B06_on_failure_shell_is_stop(self):
        self.assertEqual(
            per_action_decision(POLICY_ON_FAILURE, ACTKIND_SHELL), ACTION_STOP
        )

    def test_B07_on_failure_dangerous_shell_is_approve(self):
        """on-failure + 위험 셸 → approve (is_dangerous 우선)."""
        self.assertEqual(
            per_action_decision(POLICY_ON_FAILURE, ACTKIND_SHELL, is_dangerous=True),
            ACTION_APPROVE,
        )

    # interactive
    def test_B08_interactive_any_is_approve(self):
        for kind in (ACTKIND_FILE, ACTKIND_SHELL, ACTKIND_CODE):
            with self.subTest(kind=kind):
                self.assertEqual(
                    per_action_decision(POLICY_INTERACTIVE, kind), ACTION_APPROVE
                )

    def test_B09_interactive_dangerous_is_approve(self):
        self.assertEqual(
            per_action_decision(POLICY_INTERACTIVE, ACTKIND_SHELL, is_dangerous=True),
            ACTION_APPROVE,
        )

    # auto
    def test_B10_auto_everything_is_auto(self):
        """auto: 위험 셸 포함 전부 auto."""
        for kind in (ACTKIND_FILE, ACTKIND_SHELL, ACTKIND_CODE):
            for dangerous in (False, True):
                with self.subTest(kind=kind, dangerous=dangerous):
                    self.assertEqual(
                        per_action_decision(POLICY_AUTO, kind, is_dangerous=dangerous),
                        ACTION_AUTO,
                    )

    def test_B11_dangerous_shell_non_auto_always_approve(self):
        """비-auto 모든 정책에서 위험 셸 → approve."""
        for policy in (POLICY_INTERACTIVE, POLICY_AUTO_EDIT, POLICY_ON_FAILURE):
            with self.subTest(policy=policy):
                result = per_action_decision(policy, ACTKIND_SHELL, is_dangerous=True)
                self.assertEqual(result, ACTION_APPROVE)


# ═══════════════════════════════════════════════════════════════
# C. per_action_gate 후방호환 핵심
# ═══════════════════════════════════════════════════════════════

class TestPerActionGateBackcompat(unittest.TestCase):
    """C. per_action_gate — interactive/auto/bypass → ACTION_AUTO (이중승인 없음)."""

    def setUp(self):
        self.runner = _make_runner()

    def test_C01_interactive_file_returns_auto(self):
        """interactive 정책: 파일 → AUTO (per-action 비개입)."""
        session = _make_session(interaction_policy=POLICY_INTERACTIVE)
        result = self.runner.per_action_gate(session, ACTKIND_FILE)
        self.assertEqual(result, ACTION_AUTO)

    def test_C02_interactive_shell_returns_auto(self):
        """interactive 정책: 셸 → AUTO."""
        session = _make_session(interaction_policy=POLICY_INTERACTIVE)
        result = self.runner.per_action_gate(session, ACTKIND_SHELL)
        self.assertEqual(result, ACTION_AUTO)

    def test_C03_interactive_dangerous_shell_returns_auto(self):
        """interactive 정책: 위험 셸도 → AUTO (실행기 내부 경로가 담당)."""
        session = _make_session(interaction_policy=POLICY_INTERACTIVE)
        result = self.runner.per_action_gate(
            session, ACTKIND_SHELL, is_dangerous=True
        )
        self.assertEqual(result, ACTION_AUTO)

    def test_C04_auto_policy_returns_auto(self):
        """auto 정책: → AUTO."""
        session = _make_session(
            interaction_policy=POLICY_AUTO, bypass_approvals=True
        )
        result = self.runner.per_action_gate(session, ACTKIND_SHELL)
        self.assertEqual(result, ACTION_AUTO)

    def test_C05_bypass_approvals_returns_auto(self):
        """bypass_approvals=True: → AUTO (정책 무관)."""
        session = _make_session(
            interaction_policy=POLICY_INTERACTIVE, bypass_approvals=True
        )
        result = self.runner.per_action_gate(session, ACTKIND_SHELL, is_dangerous=True)
        self.assertEqual(result, ACTION_AUTO)

    # auto-edit per-action 세분
    def test_C06_auto_edit_file_returns_auto(self):
        """auto-edit + 파일 → AUTO."""
        session = _make_session(interaction_policy=POLICY_AUTO_EDIT)
        result = self.runner.per_action_gate(session, ACTKIND_FILE)
        self.assertEqual(result, ACTION_AUTO)

    def test_C07_auto_edit_shell_tty_returns_approve_or_reject(self):
        """auto-edit + 셸 (TTY): 사용자 응답 y → approve."""
        session = _make_session(interaction_policy=POLICY_AUTO_EDIT)
        with patch.object(self.runner, "_is_tty", return_value=True):
            with patch("builtins.input", return_value="y"):
                result = self.runner.per_action_gate(
                    session, ACTKIND_SHELL, label="test_cmd"
                )
        self.assertEqual(result, "approve")

    def test_C08_auto_edit_shell_non_tty_returns_stop(self):
        """auto-edit + 셸 + 비-TTY → STOP (자동 승격 금지)."""
        session = _make_session(interaction_policy=POLICY_AUTO_EDIT)
        with patch.object(self.runner, "_is_tty", return_value=False):
            result = self.runner.per_action_gate(session, ACTKIND_SHELL)
        self.assertEqual(result, ACTION_STOP)

    def test_C09_on_failure_file_returns_stop(self):
        """on-failure + 파일 → STOP (사전 정지)."""
        session = _make_session(interaction_policy=POLICY_ON_FAILURE)
        result = self.runner.per_action_gate(session, ACTKIND_FILE)
        self.assertEqual(result, ACTION_STOP)

    def test_C10_on_failure_code_returns_stop(self):
        """on-failure + 코드 → STOP."""
        session = _make_session(interaction_policy=POLICY_ON_FAILURE)
        result = self.runner.per_action_gate(session, ACTKIND_CODE)
        self.assertEqual(result, ACTION_STOP)

    def test_C11_on_failure_dangerous_shell_tty_returns_approve(self):
        """on-failure + 위험 셸 (TTY) → approve (위험 우선)."""
        session = _make_session(interaction_policy=POLICY_ON_FAILURE)
        with patch.object(self.runner, "_is_tty", return_value=True):
            with patch("builtins.input", return_value="y"):
                result = self.runner.per_action_gate(
                    session, ACTKIND_SHELL, is_dangerous=True, label="rm -rf /tmp/x"
                )
        self.assertEqual(result, "approve")

    def test_C12_auto_edit_shell_tty_reject(self):
        """auto-edit + 셸 (TTY): 사용자 응답 n → reject."""
        session = _make_session(interaction_policy=POLICY_AUTO_EDIT)
        with patch.object(self.runner, "_is_tty", return_value=True):
            with patch("builtins.input", return_value="n"):
                result = self.runner.per_action_gate(session, ACTKIND_SHELL)
        self.assertEqual(result, "reject")

    def test_C13_auto_edit_shell_tty_stop(self):
        """auto-edit + 셸 (TTY): 사용자 응답 s → stop."""
        session = _make_session(interaction_policy=POLICY_AUTO_EDIT)
        with patch.object(self.runner, "_is_tty", return_value=True):
            with patch("builtins.input", return_value="s"):
                result = self.runner.per_action_gate(session, ACTKIND_SHELL)
        self.assertEqual(result, ACTION_STOP)


# ═══════════════════════════════════════════════════════════════
# D. 잔여 액션 보존 (dispatcher)
# ═══════════════════════════════════════════════════════════════

class TestDispatcherHoldBehavior(unittest.TestCase):
    """D. dispatcher stop → hold ActionResult, 잔여 액션 미실행, Self-Correction 미트리거."""

    def setUp(self):
        self.runner = _make_runner()
        self.dispatcher = self.runner._dispatcher

    def test_D01_hold_result_on_stop(self):
        """on-failure 첫 액션 STOP → hold ActionResult(kind='hold', success=True) 반환."""
        session = _make_session(interaction_policy=POLICY_ON_FAILURE)

        act_text = (
            "@@@filename:src/foo.py\nprint('hello')\n@@@\n"
            "@@@filename:src/bar.py\nprint('world')\n@@@\n"
        )

        # per_action_gate 가 첫 파일 액션에서 STOP 반환하도록
        with patch.object(self.dispatcher, "_per_action_gate", return_value=ACTION_STOP):
            results = self.dispatcher.dispatch(session, act_text)

        self.assertEqual(len(results), 1)
        hold = results[0]
        self.assertEqual(hold.kind, "hold")
        self.assertTrue(hold.success)

    def test_D02_hold_does_not_trigger_self_correction(self):
        """hold result는 _has_code_failure 를 트리거하지 않는다."""
        from src.agent_runner import ActionResult

        hold = ActionResult(kind="hold", target="per-action-hold", success=True)
        # _has_code_failure 는 file/code/shell 만 봄
        # 직접 구현 확인: kind != file/code/shell 은 실패로 보지 않는다
        from src.agent_runner import AgentRunner as AR
        # runner instance method 직접 호출
        result = self.runner._has_code_failure([hold])
        self.assertFalse(result)

    def test_D03_reject_only_fails_that_action(self):
        """reject → 해당 액션만 실패, 나머지는 계속 (hold 아님)."""
        session = _make_session(interaction_policy=POLICY_AUTO_EDIT)

        # 두 번째 액션부터는 AUTO 반환하여 정상 실행 시뮬레이션
        call_count = {"n": 0}

        def gate_side_effect(s, a):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "reject"
            return ACTION_AUTO

        with patch.object(self.dispatcher, "_per_action_gate", side_effect=gate_side_effect):
            with patch.object(self.dispatcher, "_exec_shell") as mock_exec:
                mock_exec.return_value = MagicMock(kind="shell", success=True, detail="ok")
                results = self.dispatcher.dispatch(session, "$ ls\n$ pwd\n")

        # 첫 번째 reject: ActionResult(success=False)
        self.assertFalse(results[0].success)
        self.assertIn("거부", results[0].detail)
        # 두 번째: 실행됨(mock_exec 호출)
        mock_exec.assert_called_once()

    def test_D04_hold_preserves_remaining_actions_in_detail(self):
        """hold detail 에 보류된 액션 수가 표시된다."""
        session = _make_session(interaction_policy=POLICY_ON_FAILURE)

        # 파일 3개 ACT
        act_text = (
            "@@@filename:src/a.py\npass\n@@@\n"
            "@@@filename:src/b.py\npass\n@@@\n"
            "@@@filename:src/c.py\npass\n@@@\n"
        )
        with patch.object(self.dispatcher, "_per_action_gate", return_value=ACTION_STOP):
            results = self.dispatcher.dispatch(session, act_text)

        self.assertEqual(len(results), 1)
        self.assertIn("3", results[0].detail)  # "3개 미실행" 포함


# ═══════════════════════════════════════════════════════════════
# E. 스티어/전환 (agent_runner mock)
# ═══════════════════════════════════════════════════════════════

class TestHandleInterruptsAndTurn(unittest.TestCase):
    """E. _handle_interrupts / _interaction_turn 동작."""

    def setUp(self):
        self.runner = _make_runner()

    # E-1: 비활성 리스너 → no-op
    def test_E01_disabled_listener_no_interrupt(self):
        """비활성 리스너(enabled=False): _handle_interrupts → no-op."""
        self.runner._input_listener._enabled = False
        session = _make_session()
        outcome = self.runner._handle_interrupts(session)
        self.assertFalse(outcome.stop_requested)
        self.assertIsNone(outcome.steer_feedback)
        self.assertFalse(outcome.enter_turn)

    # E-2: stop 요청 → stop_requested
    def test_E02_stop_event_sets_stop_requested(self):
        """stop 이벤트 세팅 → _handle_interrupts stop_requested=True."""
        self.runner._input_listener._enabled = True
        self.runner._input_listener._stop_event.set()
        session = _make_session()
        outcome = self.runner._handle_interrupts(session)
        self.assertTrue(outcome.stop_requested)
        self.assertEqual(session.stop_reason, AgentStopReason.USER_STOP)

    # E-3: steer 'i' → 피드백 반환 (중단 아님)
    def test_E03_steer_request_collects_feedback(self):
        """steer 이벤트 → _collect_steer_feedback 호출, feedback 반환, 중단 아님."""
        self.runner._input_listener._enabled = True
        self.runner._input_listener._steer_event.set()

        expected_fb = "fix the bug"
        with patch.object(
            self.runner, "_collect_steer_feedback", return_value=expected_fb
        ):
            session = _make_session()
            outcome = self.runner._handle_interrupts(session)

        self.assertFalse(outcome.stop_requested)
        self.assertEqual(outcome.steer_feedback, expected_fb)
        self.assertTrue(outcome.enter_turn)

    # E-4: pause 'p' → paused 경계 사용, enter_turn=True
    def test_E04_pause_request_sets_enter_turn(self):
        """pause 이벤트 → _wait_for_resume 호출 후 enter_turn=True."""
        self.runner._input_listener._enabled = True
        self.runner._input_listener._pause_event.set()

        with patch.object(self.runner, "_wait_for_resume") as mock_wait:
            session = _make_session()
            outcome = self.runner._handle_interrupts(session)

        mock_wait.assert_called_once_with(session)
        self.assertTrue(outcome.enter_turn)
        self.assertFalse(outcome.stop_requested)

    # E-5: pause 후 stop → stop 우선
    def test_E05_pause_then_stop_yields_stop(self):
        """pause 대기 중 stop 들어오면 stop_requested=True."""
        self.runner._input_listener._enabled = True
        self.runner._input_listener._pause_event.set()

        def set_stop_during_wait(session):
            self.runner._input_listener._stop_event.set()

        with patch.object(
            self.runner, "_wait_for_resume", side_effect=set_stop_during_wait
        ):
            session = _make_session()
            outcome = self.runner._handle_interrupts(session)

        self.assertTrue(outcome.stop_requested)

    # E-6: _interaction_turn 정책 전환 '1'~'4'
    def test_E06_interaction_turn_policy_1_interactive(self):
        """'1' 입력 → interactive 정책 전환."""
        session = _make_session(interaction_policy=POLICY_AUTO_EDIT)
        with patch("builtins.input", side_effect=["1", "c"]):
            result, fb = self.runner._interaction_turn(session)
        self.assertEqual(session.interaction_policy, POLICY_INTERACTIVE)
        self.assertEqual(result, "c")

    def test_E07_interaction_turn_policy_2_auto_edit(self):
        """'2' 입력 → auto-edit 정책 전환."""
        session = _make_session(interaction_policy=POLICY_INTERACTIVE)
        with patch("builtins.input", side_effect=["2", "c"]):
            result, fb = self.runner._interaction_turn(session)
        self.assertEqual(session.interaction_policy, POLICY_AUTO_EDIT)
        self.assertEqual(result, "c")

    def test_E08_interaction_turn_policy_3_on_failure(self):
        """'3' 입력 → on-failure 정책 전환."""
        session = _make_session(interaction_policy=POLICY_INTERACTIVE)
        with patch("builtins.input", side_effect=["3", "c"]):
            result, fb = self.runner._interaction_turn(session)
        self.assertEqual(session.interaction_policy, POLICY_ON_FAILURE)
        self.assertEqual(result, "c")

    def test_E09_interaction_turn_policy_4_auto_returns_b(self):
        """'4' 입력 → auto 정책, 'b' 반환 (_enter_bypass_mode 호출측에서 수행)."""
        session = _make_session(interaction_policy=POLICY_INTERACTIVE)
        with patch("builtins.input", return_value="4"):
            result, fb = self.runner._interaction_turn(session)
        self.assertEqual(result, "b")
        self.assertEqual(session.interaction_policy, POLICY_AUTO)

    def test_E10_auto_to_interactive_clears_bypass(self):
        """auto/bypass → '1'(interactive): bypass 플래그 해제."""
        session = _make_session(
            interaction_policy=POLICY_AUTO,
            bypass_approvals=True,
            auto_approve_dangerous_shell=True,
            auto_approve_file_mutation=True,
        )
        with patch("builtins.input", side_effect=["1", "c"]):
            result, _ = self.runner._interaction_turn(session)
        self.assertFalse(session.bypass_approvals)
        self.assertFalse(session.auto_approve_dangerous_shell)
        self.assertFalse(session.auto_approve_file_mutation)
        self.assertEqual(session.interaction_policy, POLICY_INTERACTIVE)

    def test_E11_interaction_turn_c_continue(self):
        """'c' 입력 → ('c', None)."""
        session = _make_session()
        with patch("builtins.input", return_value="c"):
            result, fb = self.runner._interaction_turn(session)
        self.assertEqual(result, "c")
        self.assertIsNone(fb)

    def test_E12_interaction_turn_s_stop(self):
        """'s' 입력 → ('s', None)."""
        session = _make_session()
        with patch("builtins.input", return_value="s"):
            result, fb = self.runner._interaction_turn(session)
        self.assertEqual(result, "s")

    def test_E13_interaction_turn_eof_non_tty_returns_a(self):
        """비-TTY EOF → ('a', None)."""
        session = _make_session()
        with patch.object(self.runner, "_is_tty", return_value=False):
            with patch("builtins.input", side_effect=EOFError):
                result, fb = self.runner._interaction_turn(session)
        self.assertEqual(result, "a")

    def test_E14_interaction_turn_empty_returns_c(self):
        """빈 입력 → ('c', None)."""
        session = _make_session()
        with patch("builtins.input", return_value=""):
            result, fb = self.runner._interaction_turn(session)
        self.assertEqual(result, "c")

    def test_E15_handle_interrupts_no_events_returns_empty_outcome(self):
        """이벤트 없음 → 빈 _InterruptOutcome 반환."""
        self.runner._input_listener._enabled = True
        # 모든 플래그 클리어
        self.runner._input_listener.clear_all()
        session = _make_session()
        outcome = self.runner._handle_interrupts(session)
        self.assertFalse(outcome.stop_requested)
        self.assertIsNone(outcome.steer_feedback)
        self.assertFalse(outcome.enter_turn)


# ═══════════════════════════════════════════════════════════════
# _has_code_failure — hold 미트리거 확인 (Self-Correction 오발 방지)
# ═══════════════════════════════════════════════════════════════

class TestHasCodeFailureHold(unittest.TestCase):
    """hold ActionResult 는 Self-Correction 을 트리거하지 않아야 한다."""

    def setUp(self):
        self.runner = _make_runner()

    def test_F01_hold_success_not_failure(self):
        """hold(success=True) → _has_code_failure False."""
        from src.agent_runner import ActionResult
        hold = ActionResult(kind="hold", target="per-action-hold", success=True)
        self.assertFalse(self.runner._has_code_failure([hold]))

    def test_F02_file_failure_is_failure(self):
        """파일 실패 → _has_code_failure True (대조군)."""
        from src.agent_runner import ActionResult
        fail = ActionResult(kind="file", target="x.py", success=False, detail="err")
        self.assertTrue(self.runner._has_code_failure([fail]))

    def test_F03_mixed_hold_and_success_not_failure(self):
        """hold + 성공 액션 → _has_code_failure False."""
        from src.agent_runner import ActionResult
        hold = ActionResult(kind="hold", target="per-action-hold", success=True)
        ok = ActionResult(kind="code", target="python", success=True)
        self.assertFalse(self.runner._has_code_failure([hold, ok]))


if __name__ == "__main__":
    unittest.main()
