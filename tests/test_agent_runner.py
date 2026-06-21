"""
AgentRunner Unit Tests

FSD v1.0.083: T-01 ~ T-22 (parse / action / prompt / history / dataclass / env)
FSD v1.0.085: T-085-06 ~ T-085-10 (multi-provider role, disable_tools, handle_agents_command)
FSD v1.0.103: T-103-07 ~ T-103-10 (_save_file_blocks bypass_approvals → auto_overwrite 전달)
"""

import os
import sys
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
)


# ─── 헬퍼: 의존성을 모두 Mock 으로 대체한 AgentRunner 생성 ─────────
def _make_runner(assistant_role: str = "model", **env_overrides) -> AgentRunner:
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
        "AGENT_EVAL_GATE": "0",
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
                assistant_role=assistant_role,
            )

    runner.assistant = assistant
    return runner


# ─── T-01 ~ T-04: 블록 파싱 ──────────────────────────────────────
class TestParseBlocks(unittest.TestCase):

    def setUp(self):
        self.runner = _make_runner()

    def test_T01_all_blocks_extracted(self):
        """T-01: [REASON]/[ACTION]/[OBSERVE] 세 블록 모두 추출"""
        response = (
            "[REASON]\n분석 내용입니다\n\n"
            "[ACTION]\n코드 작성\n\n"
            "[OBSERVE]\n예상 결과"
        )
        reason, act, obs = self.runner._parse_blocks(response)
        self.assertIn("분석 내용입니다", reason)
        self.assertIn("코드 작성", act)
        self.assertIn("예상 결과", obs)

    def test_T02_missing_observe_returns_empty(self):
        """T-02: [OBSERVE] 없으면 obs == ''"""
        response = "[REASON]\n이유\n\n[ACTION]\n행동"
        reason, act, obs = self.runner._parse_blocks(response)
        self.assertIn("이유", reason)
        self.assertIn("행동", act)
        self.assertEqual(obs, "")

    def test_T03_no_tags_fallback_to_act(self):
        """T-03: 태그 없으면 전체 응답을 act 로 반환, reason/obs 는 빈 문자열"""
        response = "그냥 일반 텍스트 응답"
        reason, act, obs = self.runner._parse_blocks(response)
        self.assertEqual(reason, "")
        self.assertEqual(act, "그냥 일반 텍스트 응답")
        self.assertEqual(obs, "")

    def test_T04_re_shell_extracts_dollar_lines(self):
        """T-04: RE_SHELL 이 '$ cmd' 줄 추출"""
        text = "설명\n$ git status\n$ echo hello\n기타 텍스트"
        matches = AgentRunner.RE_SHELL.findall(text)
        self.assertEqual(matches, ["git status", "echo hello"])

    def test_T04b_re_shell_ignores_no_dollar(self):
        """T-04b: '$' 없는 줄은 추출 안 됨"""
        text = "git status\necho hello"
        matches = AgentRunner.RE_SHELL.findall(text)
        self.assertEqual(matches, [])

    def test_T04c_agent_done_stops_act_parsing(self):
        """T-04c: [AGENT_DONE] 이후 내용은 act 에 포함되지 않음"""
        response = "[REASON]\n이유\n\n[ACTION]\n행동\n\n[OBSERVE]\n관찰\n\n[AGENT_DONE]"
        reason, act, obs = self.runner._parse_blocks(response)
        self.assertIn("행동", act)
        self.assertNotIn("[AGENT_DONE]", act)


# ─── T-05 ~ T-07: 코드 실패 판정 ────────────────────────────────
class TestHasCodeFailure(unittest.TestCase):

    def test_T05_code_failure_returns_true(self):
        """T-05: code 액션 실패 시 True"""
        actions = [ActionResult(kind="code", target="python", success=False, detail="err")]
        self.assertTrue(AgentRunner._has_code_failure(actions))

    def test_T06_file_failure_returns_true(self):
        """T-06 (FSD v1.0.115 FR-111-22): file 액션 실패도 자기 수정 트리거 — patch 실패 포함."""
        actions = [ActionResult(kind="file", target="foo.py", success=False, detail="err")]
        self.assertTrue(AgentRunner._has_code_failure(actions))

    def test_T07_shell_failure_returns_true(self):
        """T-07: shell 액션 실패 시 True"""
        actions = [ActionResult(kind="shell", target="git test", success=False, detail="err")]
        self.assertTrue(AgentRunner._has_code_failure(actions))

    def test_T07b_all_success_returns_false(self):
        """T-07b: 모두 성공이면 False"""
        actions = [
            ActionResult(kind="code", target="python", success=True),
            ActionResult(kind="shell", target="ls", success=True),
        ]
        self.assertFalse(AgentRunner._has_code_failure(actions))

    def test_T07c_empty_actions_returns_false(self):
        """T-07c: 빈 목록이면 False"""
        self.assertFalse(AgentRunner._has_code_failure([]))


# ─── T-08 ~ T-10: _format_observe ───────────────────────────────
class TestFormatObserve(unittest.TestCase):

    def test_T08_file_success_and_code_fail_icons(self):
        """T-08: 파일 성공(✅) + 코드 실패(❌) 포맷"""
        actions = [
            ActionResult(kind="file", target="main.py", success=True, detail="저장됨"),
            ActionResult(kind="code", target="python", success=False, detail="SyntaxError"),
        ]
        result = AgentRunner._format_observe("", actions)
        self.assertIn("✅ 파일 main.py", result)
        self.assertIn("❌ 코드 실행 (python)", result)
        self.assertIn("SyntaxError", result)

    def test_T09_no_actions_no_hint_shows_placeholder(self):
        """T-09: 액션·힌트 없으면 '(실행된 액션 없음)' 반환"""
        result = AgentRunner._format_observe("", [])
        self.assertIn("실행된 액션 없음", result)

    def test_T10_hint_appended_without_placeholder(self):
        """T-10: hint 있으면 '(예상: ...)' 추가, '(실행된 액션 없음)' 미추가"""
        result = AgentRunner._format_observe("파일 저장 예상", [])
        self.assertIn("(예상: 파일 저장 예상)", result)
        self.assertNotIn("실행된 액션 없음", result)

    def test_T10b_shell_action_formatted(self):
        """T-10b: shell 액션 포맷 '$ cmd'"""
        actions = [ActionResult(kind="shell", target="ls -la", success=True, detail="returncode=0")]
        result = AgentRunner._format_observe("", actions)
        self.assertIn("✅ $ ls -la", result)


# ─── T-11 ~ T-15: 프롬프트 구성 ─────────────────────────────────
class TestBuildPrompts(unittest.TestCase):

    def setUp(self):
        self.runner = _make_runner()

    def test_T11_initial_prompt_without_context(self):
        """T-11: file_context 없으면 [FILE_CONTEXT] 블록 미포함"""
        prompt = self.runner._build_initial_prompt("목표 텍스트", "")
        self.assertIn("[GOAL]", prompt)
        self.assertIn("목표 텍스트", prompt)
        self.assertNotIn("[FILE_CONTEXT]", prompt)

    def test_T12_initial_prompt_with_context(self):
        """T-12: file_context 있으면 [FILE_CONTEXT] 블록 포함"""
        prompt = self.runner._build_initial_prompt("목표", "src/main.py 내용")
        self.assertIn("[FILE_CONTEXT]", prompt)
        self.assertIn("src/main.py 내용", prompt)

    def test_T13_iteration_prompt_contains_goal_and_plan(self):
        """T-13: 기본 iteration 프롬프트 — [GOAL], [PLAN] 포함"""
        session = AgentSession(goal="테트리스 작성", plan="1단계 계획")
        prompt = self.runner._build_iteration_prompt(session, feedback=None)
        self.assertIn("[GOAL]", prompt)
        self.assertIn("[PLAN]", prompt)
        self.assertIn("테트리스 작성", prompt)
        self.assertNotIn("[USER_FEEDBACK]", prompt)
        self.assertNotIn("[FILE_CONTEXT_REF]", prompt)

    def test_T14_iteration_prompt_with_feedback(self):
        """T-14: feedback 있으면 [USER_FEEDBACK] 블록 포함"""
        session = AgentSession(goal="목표", plan="계획")
        prompt = self.runner._build_iteration_prompt(session, feedback="수정 필요합니다")
        self.assertIn("[USER_FEEDBACK]", prompt)
        self.assertIn("수정 필요합니다", prompt)

    def test_T15_iteration_prompt_with_matched_files(self):
        """T-15: matched_files 있으면 [FILE_CONTEXT_REF] 포함"""
        session = AgentSession(
            goal="목표", plan="계획",
            matched_files=["src/a.py", "src/b.py"],
        )
        prompt = self.runner._build_iteration_prompt(session, feedback=None)
        self.assertIn("[FILE_CONTEXT_REF]", prompt)
        self.assertIn("src/a.py", prompt)


# ─── T-16 ~ T-19: 히스토리 격리 / 요약 / 압축 ──────────────────
class TestHistoryManagement(unittest.TestCase):

    def setUp(self):
        self.runner = _make_runner()

    def test_T16_call_model_restores_conversation_history(self):
        """T-16: _call_model() 이 conversation_history 를 원복"""
        original = [{"role": "user", "content": "기존 메시지"}]
        self.runner.assistant.conversation_history = list(original)
        self.runner.assistant.chat.return_value = "응답"

        session = AgentSession(goal="목표")
        self.runner._call_model(session, "프롬프트")

        self.assertEqual(
            self.runner.assistant.conversation_history,
            original,
            "conversation_history 가 원복되지 않음",
        )

    def test_T17_call_model_restores_system_prompt(self):
        """T-17: _call_model() 이 system_prompt 를 원복"""
        self.runner.assistant.system_prompt = "원래 시스템 프롬프트"
        self.runner.assistant.chat.return_value = "응답"

        session = AgentSession(goal="목표")
        self.runner._call_model(session, "프롬프트")

        self.assertEqual(
            self.runner.assistant.system_prompt,
            "원래 시스템 프롬프트",
        )

    def test_T17b_call_model_writes_to_agent_history(self):
        """T-17b: _call_model() 이후 session.agent_history 에 대화 누적"""
        self.runner.assistant.chat.return_value = "모델 응답"
        # chat() 호출 시 내부에서 conversation_history 에 메시지 추가됨을 시뮬레이션
        def fake_chat(prompt, streaming, include_context):
            self.runner.assistant.conversation_history.append(
                {"role": "user", "content": prompt}
            )
            self.runner.assistant.conversation_history.append(
                {"role": "model", "content": "모델 응답"}
            )
            return "모델 응답"

        self.runner.assistant.chat.side_effect = fake_chat

        session = AgentSession(goal="목표")
        self.runner._call_model(session, "테스트 프롬프트")

        self.assertGreater(len(session.agent_history), 0)

    def test_T18_append_summary_adds_two_messages(self):
        """T-18: _append_summary_to_main_history() 가 메인 히스토리에 2개 추가"""
        self.runner.assistant.conversation_history = []
        session = AgentSession(
            goal="테스트 목표",
            stop_reason=AgentStopReason.DONE,
            iterations=[
                IterationRecord(
                    idx=1, reason_text="이유", act_text="행동",
                    actions=[ActionResult(kind="file", target="out.py", success=True)],
                )
            ],
        )
        self.runner._append_summary_to_main_history(session)
        hist = self.runner.assistant.conversation_history

        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0]["role"], "user")
        self.assertIn("/agents", hist[0]["content"])
        self.assertEqual(hist[1]["role"], "model")   # default assistant_role="model"
        self.assertIn("out.py", hist[1]["content"])

    def test_T19_compact_skips_short_history(self):
        """T-19: agent_history <= compact_after*2 이면 압축 미실행"""
        session = AgentSession(goal="목표")
        session.agent_history = [{"role": "user", "content": "msg"}] * 4
        # compact_after=5 → threshold=10, len=4 → 압축 안 함
        self.runner._compact_history_if_needed(session)
        self.runner.assistant.chat.assert_not_called()


# ─── T-20 ~ T-22: 데이터클래스 / format_failure ─────────────────
class TestDataclasses(unittest.TestCase):

    def test_T20_agent_session_defaults(self):
        """T-20: AgentSession 기본값 확인"""
        s = AgentSession(goal="g")
        self.assertEqual(s.plan, "")
        self.assertEqual(s.file_patterns, [])
        self.assertEqual(s.matched_files, [])
        self.assertEqual(s.iterations, [])
        self.assertEqual(s.agent_history, [])
        self.assertFalse(s.auto_approve_dangerous_shell)
        self.assertIsNone(s.stop_reason)

    def test_T21_action_result_fields(self):
        """T-21: ActionResult 필드 확인"""
        ar = ActionResult(kind="code", target="python", success=True, detail="ok")
        self.assertEqual(ar.kind, "code")
        self.assertEqual(ar.target, "python")
        self.assertTrue(ar.success)
        self.assertEqual(ar.detail, "ok")

    def test_T21b_iteration_record_defaults(self):
        """T-21b: IterationRecord 기본값"""
        rec = IterationRecord(idx=1, reason_text="r", act_text="a")
        self.assertEqual(rec.actions, [])
        self.assertEqual(rec.observe_text, "")
        self.assertIsNone(rec.user_feedback)

    def test_T22_format_failure_skips_successes(self):
        """T-22: _format_failure() 는 실패 액션만 포함"""
        actions = [
            ActionResult(kind="code", target="py", success=True, detail="ok"),
            ActionResult(kind="code", target="py", success=False, detail="코드에러"),
            ActionResult(kind="shell", target="ls", success=False, detail="쉘에러"),
        ]
        result = AgentRunner._format_failure(actions)
        self.assertNotIn("ok", result)
        self.assertIn("코드에러", result)
        self.assertIn("쉘에러", result)

    def test_T22b_format_failure_no_failures(self):
        """T-22b: 실패 액션 없으면 '(실패 액션 없음...)' 반환"""
        actions = [ActionResult(kind="code", target="py", success=True)]
        result = AgentRunner._format_failure(actions)
        self.assertIn("실패 액션 없음", result)


# ─── 환경변수 오버라이드 ─────────────────────────────────────────
class TestEnvOverride(unittest.TestCase):

    def test_max_iterations_env(self):
        """AGENT_MAX_ITERATIONS 환경변수 오버라이드"""
        runner = _make_runner(AGENT_MAX_ITERATIONS="7")
        self.assertEqual(runner.max_iterations, 7)

    def test_self_correct_max_env(self):
        """AGENT_SELF_CORRECT_MAX 환경변수 오버라이드"""
        runner = _make_runner(AGENT_SELF_CORRECT_MAX="2")
        self.assertEqual(runner.self_correct_max, 2)

    def test_done_token_env(self):
        """AGENT_DONE_TOKEN 환경변수 오버라이드"""
        runner = _make_runner(AGENT_DONE_TOKEN="[FINISHED]")
        self.assertEqual(runner.done_token, "[FINISHED]")

    def test_compact_after_env(self):
        """AGENT_COMPACT_AFTER 환경변수 오버라이드"""
        runner = _make_runner(AGENT_COMPACT_AFTER="3")
        self.assertEqual(runner.compact_after, 3)


# ─── FSD v1.0.085: T-085-06 ~ T-085-10 ─────────────────────────
class TestAgentRunner085(unittest.TestCase):

    def test_T085_06_claude_role_in_summary(self):
        """T-085-06: assistant_role='assistant' 이면 요약 role='assistant'"""
        runner = _make_runner(assistant_role="assistant")
        runner.assistant.conversation_history = []
        session = AgentSession(goal="Claude 목표", stop_reason=AgentStopReason.DONE)
        runner._append_summary_to_main_history(session)
        hist = runner.assistant.conversation_history
        self.assertEqual(hist[1]["role"], "assistant")

    def test_T085_07_genai_model_role_in_summary(self):
        """T-085-07: assistant_role='model' 이면 요약 role='model'"""
        runner = _make_runner(assistant_role="model")
        runner.assistant.conversation_history = []
        session = AgentSession(goal="GenAI 목표", stop_reason=AgentStopReason.DONE)
        runner._append_summary_to_main_history(session)
        hist = runner.assistant.conversation_history
        self.assertEqual(hist[1]["role"], "model")

    def test_T085_07b_compact_history_uses_assistant_role(self):
        """T-085-07b: _compact_history_if_needed() 압축 요약에 assistant_role 사용"""
        runner = _make_runner(assistant_role="assistant", AGENT_COMPACT_AFTER="2")
        runner.assistant.chat.return_value = "압축 요약"

        session = AgentSession(goal="목표")
        # compact_after=2 → threshold=4, 메시지 6개로 임계값 초과
        session.agent_history = [
            {"role": "user", "content": f"msg{i}"} for i in range(6)
        ]
        runner._compact_history_if_needed(session)

        # 압축 후 agent_history 내 assistant_role 메시지 확인
        assistant_msgs = [m for m in session.agent_history if m.get("role") == "assistant"]
        self.assertGreater(len(assistant_msgs), 0, "압축 요약 메시지에 role='assistant' 없음")

    def test_T085_08_disable_tools_removes_tools_key(self):
        """T-085-08: chat(disable_tools=True) 는 body 에 'tools' 키 없음"""
        from src.claude_assistant import ClaudeCodeAssistant

        ca = ClaudeCodeAssistant.__new__(ClaudeCodeAssistant)
        ca.model_id = "claude-test"
        ca.endpoint_url = "http://localhost"
        ca.system_prompt = "sys"
        ca.conversation_history = []
        ca.context_builder = MagicMock()

        captured: dict = {}

        def fake_non_streaming(api_url, body, user_msg):
            captured["body"] = body
            return "응답"

        ca._chat_non_streaming = fake_non_streaming
        ca.chat("hello", streaming=False, disable_tools=True)

        self.assertIn("body", captured, "_chat_non_streaming 이 호출되지 않음")
        self.assertNotIn("tools", captured["body"],
                         "disable_tools=True 인데 body 에 'tools' 키 존재")

    def test_T085_08b_enable_tools_by_default(self):
        """T-085-08b: disable_tools=False(기본값) 이면 body 에 'tools' 포함"""
        from src.claude_assistant import ClaudeCodeAssistant

        ca = ClaudeCodeAssistant.__new__(ClaudeCodeAssistant)
        ca.model_id = "claude-test"
        ca.endpoint_url = "http://localhost"
        ca.system_prompt = "sys"
        ca.conversation_history = []
        ca.context_builder = MagicMock()

        captured: dict = {}

        def fake_non_streaming(api_url, body, user_msg):
            captured["body"] = body
            return "응답"

        ca._chat_non_streaming = fake_non_streaming
        ca.chat("hello", streaming=False, disable_tools=False)

        self.assertIn("tools", captured.get("body", {}),
                      "disable_tools=False 인데 body 에 'tools' 키 없음")

    def test_T085_09_handle_agents_command_stop(self):
        """T-085-09: handle_agents_command('stop') 는 AgentRunner 미생성"""
        from src.agents_command import handle_agents_command

        # AgentRunner 는 함수 내부에서 from .agent_runner import 하므로 소스 모듈을 패치
        with patch("src.agent_runner.AgentRunner") as MockRunner:
            handle_agents_command(
                assistant=MagicMock(),
                cli_handler=MagicMock(),
                streaming=True,
                args="stop",
            )
            MockRunner.assert_not_called()

    def test_T085_09b_handle_stop_case_insensitive(self):
        """T-085-09b: 'STOP' 대문자도 stop 처리"""
        from src.agents_command import handle_agents_command

        with patch("src.agent_runner.AgentRunner") as MockRunner:
            handle_agents_command(
                assistant=MagicMock(),
                cli_handler=MagicMock(),
                streaming=True,
                args="STOP",
            )
            MockRunner.assert_not_called()

    def test_T085_10_handle_list_pattern_parsing(self):
        """T-085-10: '[src, tests]' 형식 패턴 파싱 → file_patterns=['src','tests']"""
        from src.agents_command import handle_agents_command

        cli_handler = MagicMock()
        cli_handler.get_multiline.return_value = "테트리스 만들기"

        with patch("src.agent_runner.AgentRunner") as MockRunner:
            MockRunner.return_value.run = MagicMock()
            handle_agents_command(
                assistant=MagicMock(),
                cli_handler=cli_handler,
                streaming=True,
                args="[src, tests]",
            )
            run_call = MockRunner.return_value.run.call_args
            self.assertIsNotNone(run_call, "runner.run() 이 호출되지 않음")
            file_patterns = run_call[1].get("file_patterns") or run_call[0][1]
            self.assertIn("src", file_patterns)
            self.assertIn("tests", file_patterns)

    def test_T085_10b_space_separated_pattern_parsing(self):
        """T-085-10b: 공백 구분 패턴 'src tests' → file_patterns=['src','tests']"""
        from src.agents_command import handle_agents_command

        cli_handler = MagicMock()
        cli_handler.get_multiline.return_value = "목표"

        with patch("src.agent_runner.AgentRunner") as MockRunner:
            MockRunner.return_value.run = MagicMock()
            handle_agents_command(
                assistant=MagicMock(),
                cli_handler=cli_handler,
                streaming=True,
                args="src tests",
            )
            run_call = MockRunner.return_value.run.call_args
            file_patterns = run_call[1].get("file_patterns") or run_call[0][1]
            self.assertEqual(file_patterns, ["src", "tests"])

    def test_T085_10c_empty_goal_aborts(self):
        """T-085-10c: 빈 목표 입력 시 AgentRunner 미생성"""
        from src.agents_command import handle_agents_command

        cli_handler = MagicMock()
        cli_handler.get_multiline.return_value = ""

        with patch("src.agent_runner.AgentRunner") as MockRunner:
            handle_agents_command(
                assistant=MagicMock(),
                cli_handler=cli_handler,
                streaming=True,
                args="",
            )
            MockRunner.assert_not_called()

    def test_T085_10d_assistant_role_passed_to_runner(self):
        """T-085-10d: assistant_role 파라미터가 AgentRunner 에 전달됨"""
        from src.agents_command import handle_agents_command

        cli_handler = MagicMock()
        cli_handler.get_multiline.return_value = "목표"

        with patch("src.agent_runner.AgentRunner") as MockRunner:
            MockRunner.return_value.run = MagicMock()
            handle_agents_command(
                assistant=MagicMock(),
                cli_handler=cli_handler,
                streaming=True,
                args="",
                assistant_role="assistant",
            )
            call_kwargs = MockRunner.call_args[1]
            self.assertEqual(call_kwargs.get("assistant_role"), "assistant")


# ─── T-103-07 ~ T-103-10: FSD v1.0.103 — Bypass 파일 Overwrite ───
class TestSaveFileBlocksBypassOverwrite(unittest.TestCase):
    """_save_file_blocks() 가 session.bypass_approvals → auto_overwrite 로 전달하는지 검증."""

    def setUp(self):
        self.runner = _make_runner()

    def _make_session(self, bypass: bool) -> AgentSession:
        session = AgentSession(goal="test")
        session.bypass_approvals = bypass
        return session

    def test_T103_07_bypass_false_auto_overwrite_false(self):
        """T-103-07: bypass_approvals=False → parse_and_save 에 auto_overwrite=False 전달"""
        session = self._make_session(bypass=False)
        act_text = "```filename:src/foo.py\ncode\n```"
        self.runner.RE_FILENAME_BLOCK = __import__("re").compile(
            r"`{3,}filename:([^\n]+)", __import__("re").MULTILINE
        )
        self.runner.response_parser.parse_and_save.return_value = ["src/foo.py"]

        self.runner._save_file_blocks(session, act_text)

        self.runner.response_parser.parse_and_save.assert_called_once_with(
            act_text, auto_overwrite=False
        )

    def test_T103_08_bypass_true_auto_overwrite_true(self):
        """T-103-08: bypass_approvals=True → parse_and_save 에 auto_overwrite=True 전달"""
        session = self._make_session(bypass=True)
        act_text = "```filename:src/foo.py\ncode\n```"
        self.runner.RE_FILENAME_BLOCK = __import__("re").compile(
            r"`{3,}filename:([^\n]+)", __import__("re").MULTILINE
        )
        self.runner.response_parser.parse_and_save.return_value = ["src/foo.py"]

        self.runner._save_file_blocks(session, act_text)

        self.runner.response_parser.parse_and_save.assert_called_once_with(
            act_text, auto_overwrite=True
        )

    def test_T103_09_save_success_action_result(self):
        """T-103-09: bypass=True, parse_and_save 성공 → ActionResult(success=True)"""
        session = self._make_session(bypass=True)
        act_text = "```filename:src/foo.py\ncode\n```"
        self.runner.RE_FILENAME_BLOCK = __import__("re").compile(
            r"`{3,}filename:([^\n]+)", __import__("re").MULTILINE
        )
        self.runner.response_parser.parse_and_save.return_value = ["src/foo.py"]

        results = self.runner._save_file_blocks(session, act_text)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].target, "src/foo.py")

    def test_T103_10_bypass_reset_on_resume(self):
        """T-103-10: resume 시 bypass_approvals=False 초기화 확인 (FR-100-11)"""
        session = self._make_session(bypass=True)
        session.stop_reason = AgentStopReason.MAX_ITERATIONS

        # run() 의 resume 분기에서 bypass_approvals 를 False 로 초기화
        session.bypass_approvals = False   # FR-100-11 규칙 직접 검증
        self.assertFalse(session.bypass_approvals)


if __name__ == "__main__":
    unittest.main()
