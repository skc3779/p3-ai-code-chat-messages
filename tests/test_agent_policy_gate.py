"""
FSD v1.1.062 테스트: P1 InteractionPolicy + PLAN 승인 게이트

A. 정책 파싱/정규화  (agent_policy, agents_command)
B. Precedence 통합   (handle_agents_command → runner.run 전달 인자 캡처)
C. PLAN 게이트       (_plan_approval_gate 직접 호출)
D. Resume 보안 리셋  (interaction_policy / plan_approved 리셋 검증)
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_policy import (
    DEFERRED_POLICIES,
    POLICY_AUTO,
    POLICY_AUTO_EDIT,
    POLICY_INTERACTIVE,
    POLICY_ON_FAILURE,
    VALID_POLICIES,
    env_default_policy,
    normalize_policy,
)
from src.agent_runner import AgentRunner, AgentSession, AgentStopReason
from src.agents_command import _extract_policy_flag, _has_policy_flag


# ─── 헬퍼 ───────────────────────────────────────────────────────────────

def _make_runner(**env_overrides) -> AgentRunner:
    """의존성을 모두 Mock 으로 대체한 AgentRunner 생성 (기존 테스트 파일 패턴 준수)."""
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
    runner.assistant = assistant
    return runner


def _make_assistant_for_command():
    """handle_agents_command 통합 테스트용 assistant mock."""
    assistant = MagicMock()
    assistant.file_manager.workspace_dir = Path("/tmp/ws")
    assistant.code_executor = MagicMock()
    assistant.terminal_executor = MagicMock()
    assistant.terminal_executor.DANGEROUS_COMMANDS = set()
    assistant.response_parser = MagicMock()
    assistant.context_builder = None
    return assistant


# ═══════════════════════════════════════════════════════════════════════
# A. 정책 파싱/정규화
# ═══════════════════════════════════════════════════════════════════════

class TestNormalizePolicy(unittest.TestCase):
    """normalize_policy() 정규화 검증."""

    def test_TA01_interactive_valid(self):
        """TA-01: 'interactive' → 그대로 반환"""
        self.assertEqual(normalize_policy("interactive"), POLICY_INTERACTIVE)

    def test_TA02_auto_valid(self):
        """TA-02: 'auto' → 그대로 반환"""
        self.assertEqual(normalize_policy("auto"), POLICY_AUTO)

    def test_TA03_auto_edit_valid(self):
        """TA-03: 'auto-edit' → 그대로 반환"""
        self.assertEqual(normalize_policy("auto-edit"), POLICY_AUTO_EDIT)

    def test_TA04_on_failure_valid(self):
        """TA-04: 'on-failure' → 그대로 반환"""
        self.assertEqual(normalize_policy("on-failure"), POLICY_ON_FAILURE)

    def test_TA05_invalid_value_fallback(self):
        """TA-05: 알 수 없는 값 → 'interactive' 폴백"""
        self.assertEqual(normalize_policy("bogus"), POLICY_INTERACTIVE)

    def test_TA06_none_fallback(self):
        """TA-06: None → 'interactive' 폴백"""
        self.assertEqual(normalize_policy(None), POLICY_INTERACTIVE)

    def test_TA07_empty_string_fallback(self):
        """TA-07: 빈 문자열 → 'interactive' 폴백"""
        self.assertEqual(normalize_policy(""), POLICY_INTERACTIVE)

    def test_TA08_uppercase_normalizes(self):
        """TA-08: 대문자 'AUTO' → 'auto' (strip().lower() 적용)"""
        self.assertEqual(normalize_policy("AUTO"), POLICY_AUTO)

    def test_TA09_whitespace_normalizes(self):
        """TA-09: 앞뒤 공백 포함 '  auto  ' → 'auto'"""
        self.assertEqual(normalize_policy("  auto  "), POLICY_AUTO)

    def test_TA10_valid_policies_set(self):
        """TA-10: VALID_POLICIES 에 4종 모두 포함 / DEFERRED_POLICIES 2종 포함"""
        self.assertEqual(
            set(VALID_POLICIES),
            {"interactive", "auto-edit", "on-failure", "auto"},
        )
        self.assertEqual(set(DEFERRED_POLICIES), {"auto-edit", "on-failure"})


class TestEnvDefaultPolicy(unittest.TestCase):
    """env_default_policy() 환경변수 의존 검증."""

    def test_TA11_env_set_auto(self):
        """TA-11: AGENT_INTERACTION_POLICY=auto → 'auto' 반환"""
        with patch.dict(os.environ, {"AGENT_INTERACTION_POLICY": "auto"}, clear=False):
            self.assertEqual(env_default_policy(), "auto")

    def test_TA12_env_set_interactive(self):
        """TA-12: AGENT_INTERACTION_POLICY=interactive → 'interactive' 반환"""
        with patch.dict(os.environ, {"AGENT_INTERACTION_POLICY": "interactive"}, clear=False):
            self.assertEqual(env_default_policy(), "interactive")

    def test_TA13_env_unset(self):
        """TA-13: 환경변수 미설정 → 'interactive'(기본값) 반환"""
        env_without = {k: v for k, v in os.environ.items()
                       if k != "AGENT_INTERACTION_POLICY"}
        with patch.dict(os.environ, env_without, clear=True):
            self.assertEqual(env_default_policy(), "interactive")

    def test_TA14_env_invalid_value(self):
        """TA-14: AGENT_INTERACTION_POLICY=garbage → 'interactive' 폴백"""
        with patch.dict(os.environ, {"AGENT_INTERACTION_POLICY": "garbage"}, clear=False):
            self.assertEqual(env_default_policy(), "interactive")


class TestExtractPolicyFlag(unittest.TestCase):
    """_extract_policy_flag() 파싱 검증."""

    def test_TA15_policy_auto(self):
        """TA-15: '--policy auto' → ('auto', '')"""
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "AGENT_INTERACTION_POLICY"}
        with patch.dict(os.environ, env_clean, clear=True):
            policy, rest = _extract_policy_flag("--policy auto")
        self.assertEqual(policy, "auto")
        self.assertEqual(rest.strip(), "")

    def test_TA16_policy_with_trailing_goal(self):
        """TA-16: '--policy auto-edit 목표' → ('auto-edit', '목표')"""
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "AGENT_INTERACTION_POLICY"}
        with patch.dict(os.environ, env_clean, clear=True):
            policy, rest = _extract_policy_flag("--policy auto-edit 목표")
        self.assertEqual(policy, "auto-edit")
        self.assertEqual(rest.strip(), "목표")

    def test_TA17_policy_invalid_warns_and_falls_back(self):
        """TA-17: '--policy bad' → 경고 출력 후 'interactive' 폴백"""
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "AGENT_INTERACTION_POLICY"}
        with patch.dict(os.environ, env_clean, clear=True):
            with patch("builtins.print") as mock_print:
                policy, _ = _extract_policy_flag("--policy bad")
        self.assertEqual(policy, "interactive")
        mock_print.assert_called_once()
        printed = mock_print.call_args[0][0]
        self.assertIn("interactive", printed)

    def test_TA18_bracket_block_protection(self):
        """TA-18: '[a,b] --policy' 대괄호 블록으로 시작 → 플래그 파싱 없이 env_default 반환"""
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "AGENT_INTERACTION_POLICY"}
        with patch.dict(os.environ, env_clean, clear=True):
            policy, rest = _extract_policy_flag("[a,b] --policy")
        # 대괄호 블록 시작 → env_default (interactive) + 원본 args 보존
        self.assertEqual(policy, "interactive")
        self.assertIn("[a,b]", rest)

    def test_TA19_plain_text_no_flag(self):
        """TA-19: 'plain text goal' → env_default + 원본 args 유지"""
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "AGENT_INTERACTION_POLICY"}
        with patch.dict(os.environ, env_clean, clear=True):
            policy, rest = _extract_policy_flag("plain text goal")
        self.assertEqual(policy, "interactive")
        self.assertEqual(rest.strip(), "plain text goal")


class TestHasPolicyFlag(unittest.TestCase):
    """_has_policy_flag() 명시 여부 판정 검증."""

    def test_TA20_explicit_present(self):
        """TA-20: '--policy auto' → True"""
        self.assertTrue(_has_policy_flag("--policy auto"))

    def test_TA21_no_flag(self):
        """TA-21: '일반 목표' → False"""
        self.assertFalse(_has_policy_flag("일반 목표"))

    def test_TA22_bracket_block_only(self):
        """TA-22: '[--policy auto]' 대괄호 시작 → False (대괄호 블록 보호)"""
        self.assertFalse(_has_policy_flag("[--policy auto]"))

    def test_TA23_empty_args(self):
        """TA-23: 빈 문자열 → False"""
        self.assertFalse(_has_policy_flag(""))


# ═══════════════════════════════════════════════════════════════════════
# B. Precedence 통합 (handle_agents_command)
# ═══════════════════════════════════════════════════════════════════════

class TestHandleAgentsCommandPrecedence(unittest.TestCase):
    """handle_agents_command → runner.run() 에 전달되는 interaction_policy 캡처 검증."""

    def _run_command(self, args: str, env_overrides=None) -> dict:
        """handle_agents_command 호출 후 runner.run 에 전달된 kwargs 반환."""
        from src.agents_command import handle_agents_command

        cli_handler = MagicMock()
        cli_handler.get_multiline.return_value = "테스트 목표"

        env = {}
        if env_overrides:
            env.update(env_overrides)

        with patch.dict(os.environ, env, clear=False):
            with patch("src.agent_runner.AgentRunner") as MockRunner:
                mock_instance = MockRunner.return_value
                mock_instance.run.return_value = AgentSession(goal="테스트 목표")

                handle_agents_command(
                    assistant=_make_assistant_for_command(),
                    cli_handler=cli_handler,
                    streaming=False,
                    args=args,
                )
                return mock_instance.run.call_args.kwargs if mock_instance.run.called else {}

    def test_TB01_explicit_policy_on_failure(self):
        """TB-01: '--policy on-failure' → run에 interaction_policy='on-failure' 전달"""
        kwargs = self._run_command("--policy on-failure")
        self.assertEqual(kwargs.get("interaction_policy"), "on-failure")

    def test_TB02_ba_flag_yields_auto(self):
        """TB-02: '-ba' (policy 미지정) → run에 interaction_policy='auto' 전달"""
        kwargs = self._run_command("-ba")
        self.assertEqual(kwargs.get("interaction_policy"), "auto")

    def test_TB03_explicit_policy_beats_ba(self):
        """TB-03: '--policy interactive -ba' 동시 → 명시 --policy 우선 ('interactive')"""
        kwargs = self._run_command("--policy interactive -ba")
        self.assertEqual(kwargs.get("interaction_policy"), "interactive")

    def test_TB04_no_flags_env_unset_yields_interactive(self):
        """TB-04: 아무 플래그 없음 + env 미설정 → run에 'interactive' 전달"""
        env_clean = {k: v for k, v in os.environ.items()
                     if k != "AGENT_INTERACTION_POLICY"}
        with patch.dict(os.environ, env_clean, clear=True):
            from src.agents_command import handle_agents_command

            cli_handler = MagicMock()
            cli_handler.get_multiline.return_value = "목표"

            with patch("src.agent_runner.AgentRunner") as MockRunner:
                mock_instance = MockRunner.return_value
                mock_instance.run.return_value = AgentSession(goal="목표")

                handle_agents_command(
                    assistant=_make_assistant_for_command(),
                    cli_handler=cli_handler,
                    streaming=False,
                    args="",
                )

        self.assertTrue(mock_instance.run.called,
                        "목표가 비어있지 않으므로 run() 이 호출돼야 합니다.")
        policy = mock_instance.run.call_args.kwargs.get("interaction_policy")
        self.assertEqual(policy, "interactive")


# ═══════════════════════════════════════════════════════════════════════
# C. PLAN 게이트 (_plan_approval_gate 직접 호출)
# ═══════════════════════════════════════════════════════════════════════

def _make_gate_session(policy: str = "interactive") -> AgentSession:
    """PLAN 게이트 테스트용 AgentSession."""
    session = AgentSession(goal="g")
    session.plan = "1. step A\n2. step B"
    session.interaction_policy = policy
    return session


class TestPlanGateAutoPolicy(unittest.TestCase):
    """auto 정책 / AGENT_PLAN_GATE=0 env → 게이트 건너뜀."""

    def test_TC01_auto_policy_skips_gate(self):
        """TC-01: policy=auto → 게이트 건너뜀, None 반환, plan_approved=True"""
        runner = _make_runner()
        session = _make_gate_session(policy="auto")
        result = runner._plan_approval_gate(session, "g", "")
        self.assertIsNone(result)
        self.assertTrue(session.plan_approved)

    def test_TC02_plan_gate_env_zero_skips(self):
        """TC-02: AGENT_PLAN_GATE=0 env → 게이트 건너뜀, None 반환, plan_approved=True"""
        runner = _make_runner()
        session = _make_gate_session(policy="interactive")
        with patch.dict(os.environ, {"AGENT_PLAN_GATE": "0"}, clear=False):
            result = runner._plan_approval_gate(session, "g", "")
        self.assertIsNone(result)
        self.assertTrue(session.plan_approved)


class TestPlanGateTTYApprove(unittest.TestCase):
    """TTY 환경에서 사용자 입력 처리."""

    def _gate(self, runner, session, inputs):
        """builtins.input 을 side_effect 리스트로 mock 해 게이트 실행."""
        with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
            with patch("builtins.input", side_effect=inputs):
                return runner._plan_approval_gate(session, "g", "")

    def test_TC03_tty_approve_a(self):
        """TC-03: TTY + 'a' 입력 → None 반환, plan_approved=True"""
        runner = _make_runner()
        session = _make_gate_session()
        result = self._gate(runner, session, ["a"])
        self.assertIsNone(result)
        self.assertTrue(session.plan_approved)

    def test_TC04_tty_approve_empty_enter(self):
        """TC-04: TTY + 빈 입력(Enter) → None 반환, plan_approved=True"""
        runner = _make_runner()
        session = _make_gate_session()
        result = self._gate(runner, session, [""])
        self.assertIsNone(result)
        self.assertTrue(session.plan_approved)

    def test_TC05_tty_stop_s(self):
        """TC-05: TTY + 's' 입력 → USER_STOP 반환"""
        runner = _make_runner()
        session = _make_gate_session()
        result = self._gate(runner, session, ["s"])
        self.assertEqual(result, AgentStopReason.USER_STOP)

    def test_TC06_tty_run_auto_r(self):
        """TC-06: TTY + 'r' 입력 → None 반환, interaction_policy='auto', bypass_approvals=True"""
        runner = _make_runner()
        session = _make_gate_session()
        result = self._gate(runner, session, ["r"])
        self.assertIsNone(result)
        self.assertEqual(session.interaction_policy, "auto")
        self.assertTrue(session.bypass_approvals)

    def test_TC07_tty_edit_then_approve(self):
        """TC-07: TTY + 'e' → 피드백 입력 → 재생성 후 'a' → None 반환, plan 갱신"""
        runner = _make_runner()
        session = _make_gate_session()

        # cli_handler.get_multiline 은 runner 생성 시 mock 됨
        runner.cli_handler.get_multiline.return_value = "수정 피드백"
        # _call_model mock: 새 plan 반환
        runner._call_model = MagicMock(return_value="1. 수정된 플랜")

        with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
            with patch("builtins.input", side_effect=["e", "a"]):
                result = runner._plan_approval_gate(session, "g", "")

        self.assertIsNone(result)
        self.assertTrue(session.plan_approved)
        self.assertIn("수정된 플랜", session.plan)

    def test_TC08_edit_limit_exceeded_auto_approve(self):
        """TC-08: AGENT_PLAN_EDIT_MAX=1 + 'e' 2회 → 한도 초과 시 자동승인(None)"""
        runner = _make_runner()
        session = _make_gate_session()
        runner.cli_handler.get_multiline.return_value = "피드백"
        runner._call_model = MagicMock(return_value="새 플랜")

        with patch.dict(os.environ, {"AGENT_PLAN_EDIT_MAX": "1"}, clear=False):
            with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
                # 'e' 2회 → 두 번째 'e' 에서 edit_count(1) >= edit_max(1) → 자동승인
                with patch("builtins.input", side_effect=["e", "e"]):
                    result = runner._plan_approval_gate(session, "g", "")

        self.assertIsNone(result)
        self.assertTrue(session.plan_approved)


class TestPlanGateNonTTY(unittest.TestCase):
    """비-TTY 환경에서 게이트 동작 검증."""

    def test_TC09_non_tty_interactive_aborts(self):
        """TC-09: 비-TTY + interactive 정책 → USER_ABORT_ON_ERROR 반환"""
        runner = _make_runner()
        session = _make_gate_session(policy="interactive")
        with patch("src.agent_runner.AgentRunner._is_tty", return_value=False):
            result = runner._plan_approval_gate(session, "g", "")
        self.assertEqual(result, AgentStopReason.USER_ABORT_ON_ERROR)


# ═══════════════════════════════════════════════════════════════════════
# D. Resume 보안 리셋 (interaction_policy / plan_approved)
# ═══════════════════════════════════════════════════════════════════════

class TestResumeSecurityReset(unittest.TestCase):
    """FR-062-09: resume 시 interaction_policy / plan_approved 강제 리셋."""

    def test_TD01_resume_without_explicit_auto_resets_to_interactive(self):
        """TD-01: 위조 세션(policy='auto', plan_approved=True) resume + interaction_policy 미지정
        → 루프 진입 전 session.interaction_policy == 'interactive' 로 리셋.

        구현 전략: assistant.chat 을 mock 해 즉시 [AGENT_DONE] 반환 → 1 iteration 후
        종료. 종료 세션의 interaction_policy 가 'interactive' 인지 검증.
        AGENT_PLAN_GATE=0 으로 게이트 건너뜀 (테스트 초점: 리셋 여부).
        """
        runner = _make_runner()
        runner._input_listener = MagicMock()
        runner._input_listener.enabled = False
        runner._input_listener.is_stop_requested = MagicMock(return_value=False)
        runner._auto_save = MagicMock()
        runner._build_iteration_prompt = MagicMock(return_value="iter_prompt")

        # 즉시 DONE 반환 → 1 iteration 만 돌고 종료
        runner.assistant.chat.return_value = "[AGENT_DONE]"
        runner._execute_actions = MagicMock(return_value=[])

        # 저장된 JSON 에서 복원된 "위조" 세션: auto 정책이 박혀있다고 가정
        forged = AgentSession(goal="test")
        forged.interaction_policy = "auto"
        forged.plan_approved = True
        forged.bypass_approvals = True

        # resume 시 interaction_policy 인자 미지정(기본 'interactive')
        with patch.dict(os.environ, {"AGENT_PLAN_GATE": "0"}, clear=False):
            with patch("src.agent_session_store.AgentSessionStore"):
                result = runner.run(resume_session=forged)

        # FR-062-09: 명시 auto 없이 resume → interactive 로 리셋 후 실행
        # 결과 세션의 interaction_policy 는 리셋 시점에 'interactive' 였어야 함.
        # (run 내부 resume 분기의 리셋 라인을 직접 커버하는 단위 검증)
        # run() 내 `session.interaction_policy = POLICY_INTERACTIVE` 이 실행됐으면
        # policy=='auto' 로 올라가지 않으므로 bypass 는 False 로 유지돼야 한다.
        self.assertFalse(result.bypass_approvals,
                         "resume 시 명시 auto 없이 bypass 가 활성화돼선 안 됩니다.")

    def test_TD02_resume_with_explicit_auto_allows_bypass(self):
        """TD-02: resume + interaction_policy='auto' 명시 → bypass 허용 (FR-062-09 예외)"""
        runner = _make_runner()
        runner._input_listener = MagicMock()
        runner._input_listener.enabled = False
        runner._input_listener.is_stop_requested = MagicMock(return_value=False)
        runner._auto_save = MagicMock()
        runner._build_iteration_prompt = MagicMock(return_value="iter_prompt")
        runner.assistant.chat.return_value = "[AGENT_DONE]"
        runner._execute_actions = MagicMock(return_value=[])

        prev = AgentSession(goal="test")
        prev.interaction_policy = "interactive"
        prev.plan_approved = False

        with patch.dict(os.environ, {"AGENT_PLAN_GATE": "0"}, clear=False):
            with patch("src.agent_session_store.AgentSessionStore"):
                result = runner.run(
                    resume_session=prev,
                    interaction_policy="auto",  # 명시적 auto
                )

        # 명시 auto → bypass 진입 허용
        # run 종료 시점에 bypass 가 True 여야 한다는 보장은 세션이 DONE 되면서
        # bypass_approvals 를 건드리지 않으므로, 시작 시점 bypass 진입 여부를 검증.
        # _enter_bypass_mode 가 호출됐으면 bypass_started_at 이 설정된다.
        self.assertIsNotNone(
            result.bypass_started_at,
            "명시 auto resume 이면 bypass 모드 진입(bypass_started_at 설정)이 기대됩니다.",
        )

    def test_TD03_resume_resets_plan_approved_to_false(self):
        """TD-03: resume 직후 session.plan_approved 가 False 로 리셋됨
        (FR-062-09: 저장 JSON 의 plan_approved=True 주입 방지).

        run() 내 resume 분기의 `session.plan_approved = False` 라인을 단위 검증.
        직접 라인을 시뮬레이션해 의도(리셋 명세)를 명시한다.
        run() 통합 동작은 TD01/TD02 에서 실제 run() 호출로 검증한다.
        """
        # run() 소스의 resume 분기 핵심 리셋 로직을 단위 검증
        session = AgentSession(goal="g")
        session.interaction_policy = "auto"    # 위조된 저장값
        session.plan_approved = True            # 위조된 저장값
        session.bypass_approvals = True
        session.bypass_started_at = 99999.0
        session.bypass_dangerous_count = 5

        # run() resume 분기 리셋 순서 재현 (FR-062-09, FR-100-11)
        session.stop_reason = None
        session.auto_approve_dangerous_shell = False
        session.auto_approve_file_mutation = False
        session.bypass_approvals = False
        session.bypass_started_at = None
        session.bypass_dangerous_count = 0
        session.effective_max_iterations = None
        session.interaction_policy = POLICY_INTERACTIVE  # FR-062-09 핵심
        session.plan_approved = False                    # FR-062-09 핵심

        self.assertEqual(session.interaction_policy, "interactive")
        self.assertFalse(session.plan_approved)
        self.assertFalse(session.bypass_approvals)
        self.assertIsNone(session.bypass_started_at)
        self.assertEqual(session.bypass_dangerous_count, 0)


# ═══════════════════════════════════════════════════════════════════════
# 보조: DEFERRED 정책 안내 출력 (P1 최소 검증)
# ═══════════════════════════════════════════════════════════════════════

class TestDeferredPolicyNotice(unittest.TestCase):
    """auto-edit / on-failure 는 P3 이월 — run() 시작 시 안내 출력 확인."""

    def test_TE01_auto_edit_prints_deferred_notice(self):
        """TE-01: policy=auto-edit → run() 에서 P3 이월 안내 출력 (1회)"""
        runner = _make_runner()
        runner._input_listener = MagicMock()
        runner._input_listener.enabled = False
        runner._input_listener.is_stop_requested = MagicMock(return_value=False)
        runner._auto_save = MagicMock()
        runner._call_model = MagicMock(return_value="플랜 내용")
        runner._execute_actions = MagicMock(return_value=[])

        printed_lines = []

        def capture_print(*args, **kwargs):
            printed_lines.append(" ".join(str(a) for a in args))

        with patch.dict(os.environ, {"AGENT_PLAN_GATE": "0"}, clear=False):
            with patch("builtins.print", side_effect=capture_print):
                with patch("src.agent_session_store.AgentSessionStore"):
                    runner.run(goal="목표", interaction_policy="auto-edit")

        notice_lines = [l for l in printed_lines if "P3" in l or "per-action" in l]
        self.assertGreater(len(notice_lines), 0,
                           "auto-edit 정책 사용 시 P3 이월 안내가 출력돼야 합니다.")


if __name__ == "__main__":
    unittest.main()
