"""
AgentRunner truncation handling tests (FSD v1.1.034)

T-034-01 : finish_reason=max_tokens    → TRUNCATED
T-034-02 : 미닫힌 @@@ 펜스 (신호 없음) → 휴리스틱 TRUNCATED
T-034-03 : TRUNCATED 응답              → GOAL_NOT_MET / GOAL_UNVERIFIED 종료 없음
T-034-04 : 완전 블록 + 불완전 블록    → 완전 블록만 처리, 불완전 제외
T-034-05 : continuation 프롬프트      → [CONTINUATION] + 잘린 파일 경로
T-034-06 : 잘린 PLAN + 기준 추출됨   → 0-iteration GOAL_UNVERIFIED 종료 억제
T-034-07 : AGENT_MAX_CONTINUATIONS    → 초과 시 MAX_ITERATIONS 종료
T-034-08 : 정상(완전) 응답             → 기존 경로 그대로 (회귀 없음)
T-034-09 : agent_history              → 불완전 꼬리 누적 안 됨 (NFR-034-04)
T-034-10 : PLAN 프롬프트              → '계획만' 지시 포함 (FR-034-07)
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_runner import AgentRunner, AgentSession, AgentStopReason


# ─── 공통 헬퍼 ───────────────────────────────────────────────────────────────

def _make_runner(**env_overrides) -> AgentRunner:
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"
    assistant.last_finish_reason = None

    file_manager = MagicMock()
    file_manager.workspace_dir = Path("/tmp/test_workspace")

    terminal_executor = MagicMock()
    terminal_executor.DANGEROUS_COMMANDS = {"rm", "del", "move", "mv"}

    env = {
        "AGENT_MAX_ITERATIONS": "5",
        "AGENT_SELF_CORRECT_MAX": "1",
        "AGENT_COMPACT_AFTER": "10",
        "AGENT_CODE_TIMEOUT": "30",
        "AGENT_DONE_TOKEN": "[AGENT_DONE]",
        "AGENT_EVAL_GATE": "0",
        "AGENT_MAX_CONTINUATIONS": "3",
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
            )
    runner.assistant = assistant
    return runner


# ─── T-034-01 / T-034-02 / T-034-08(EMPTY): _classify_response ──────────────

class TestClassifyResponse(unittest.TestCase):

    def setUp(self):
        self.runner = _make_runner()

    def test_T034_01_finish_reason_max_tokens(self):
        """T-034-01: finish_reason=max_tokens → TRUNCATED."""
        self.runner.assistant.last_finish_reason = "max_tokens"
        response = "[REASON]\n작업\n[ACTION]\n$ echo hi\n[OBSERVE]\n완료"
        self.assertEqual(self.runner._classify_response(response), "TRUNCATED")

    def test_T034_01b_gemini_MAX_TOKENS(self):
        """T-034-01b: Gemini finishReason=MAX_TOKENS → TRUNCATED."""
        self.runner.assistant.last_finish_reason = "MAX_TOKENS"
        self.assertEqual(self.runner._classify_response("some text"), "TRUNCATED")

    def test_T034_01c_length_finish_reason(self):
        """T-034-01c: finish_reason=length → TRUNCATED."""
        self.runner.assistant.last_finish_reason = "length"
        self.assertEqual(self.runner._classify_response("some text"), "TRUNCATED")

    def test_T034_02_unclosed_fence_heuristic(self):
        """T-034-02: 닫히지 않은 @@@filename: (신호 없음) → 휴리스틱 TRUNCATED."""
        self.runner.assistant.last_finish_reason = None
        response = (
            "@@@filename:src/a.py\n"
            "def a(): pass\n"
            "@@@\n\n"
            "@@@filename:src/b.py\n"
            "class B:\n"
            "    # cut here"
        )
        self.assertEqual(self.runner._classify_response(response), "TRUNCATED")

    def test_T034_02b_balanced_fences_complete(self):
        """T-034-02b: 균형 잡힌 펜스 → COMPLETE."""
        self.runner.assistant.last_finish_reason = None
        response = "@@@filename:src/ok.py\ndef f(): pass\n@@@\n[AGENT_DONE]"
        self.assertEqual(self.runner._classify_response(response), "COMPLETE")

    def test_T034_08_empty_response(self):
        """T-034-08(EMPTY): 빈 응답 → EMPTY."""
        self.runner.assistant.last_finish_reason = None
        self.assertEqual(self.runner._classify_response(""), "EMPTY")
        self.assertEqual(self.runner._classify_response("  \n  "), "EMPTY")

    def test_T034_08b_patch_fence_balanced(self):
        """T-034-08b: 닫힌 @@@patch: 펜스 → COMPLETE."""
        self.runner.assistant.last_finish_reason = None
        response = (
            "@@@patch:src/foo.py\n"
            "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
            "@@@\n[AGENT_DONE]"
        )
        self.assertEqual(self.runner._classify_response(response), "COMPLETE")


# ─── _has_unclosed_fence ─────────────────────────────────────────────────────

class TestHasUnclosedFence(unittest.TestCase):

    def test_unclosed_filename(self):
        """미닫힌 @@@filename: → True."""
        self.assertTrue(AgentRunner._has_unclosed_fence(
            "@@@filename:src/x.py\n# incomplete"
        ))

    def test_closed_filename(self):
        """닫힌 @@@filename: → False."""
        self.assertFalse(AgentRunner._has_unclosed_fence(
            "@@@filename:src/x.py\ncode\n@@@"
        ))

    def test_multiple_files_last_unclosed(self):
        """완전 블록 + 불완전 블록 → True."""
        response = (
            "@@@filename:a.py\ncode\n@@@\n\n"
            "@@@filename:b.py\n# cut"
        )
        self.assertTrue(AgentRunner._has_unclosed_fence(response))

    def test_no_fences(self):
        """펜스 없는 텍스트 → False."""
        self.assertFalse(AgentRunner._has_unclosed_fence(
            "[REASON]\n분석\n[ACTION]\n$ echo hi"
        ))

    def test_unclosed_patch_fence(self):
        """미닫힌 @@@patch: → True."""
        self.assertTrue(AgentRunner._has_unclosed_fence(
            "@@@patch:src/x.py\n<<<<<<< SEARCH\nold"
        ))


# ─── T-034-04 / T-034-09: _strip_incomplete_fence_tail / _handle_truncated ───

class TestStripIncompleteTail(unittest.TestCase):

    def setUp(self):
        self.runner = _make_runner()

    def test_T034_04_complete_block_preserved_incomplete_removed(self):
        """T-034-04: 완전 블록 보존, 불완전 블록 제거."""
        response = (
            "@@@filename:src/a.py\n"
            "print('a')\n"
            "@@@\n\n"
            "@@@filename:src/b.py\n"
            "# incomplete"
        )
        clean, pending = AgentRunner._strip_incomplete_fence_tail(response)
        self.assertIn("src/a.py", clean)
        self.assertIn("print('a')", clean)
        self.assertNotIn("src/b.py", clean)
        self.assertEqual(pending, "src/b.py")

    def test_T034_04b_no_incomplete_fence_unchanged(self):
        """T-034-04b: 불완전 펜스 없으면 원본 그대로, pending=None."""
        response = "@@@filename:src/a.py\ncode\n@@@\n[AGENT_DONE]"
        clean, pending = AgentRunner._strip_incomplete_fence_tail(response)
        self.assertEqual(clean, response)
        self.assertIsNone(pending)

    def test_T034_04c_only_incomplete_fence(self):
        """T-034-04c: 불완전 펜스만 있으면 clean=빈 문자열."""
        response = "@@@filename:src/x.py\n// incomplete"
        clean, pending = AgentRunner._strip_incomplete_fence_tail(response)
        self.assertEqual(clean.strip(), "")
        self.assertEqual(pending, "src/x.py")

    def test_T034_04d_patch_fence_incomplete(self):
        """T-034-04d: 미닫힌 @@@patch: 블록도 제거."""
        response = (
            "@@@filename:a.py\ncode\n@@@\n\n"
            "@@@patch:b.py\n<<<<<<< SEARCH\nold"
        )
        clean, pending = AgentRunner._strip_incomplete_fence_tail(response)
        self.assertNotIn("@@@patch:", clean)
        self.assertEqual(pending, "b.py")

    def test_T034_09_agent_history_str_content_patched(self):
        """T-034-09: agent_history 마지막 항목(str) 에서 불완전 꼬리 제거."""
        truncated = (
            "@@@filename:ok.py\nok\n@@@\n\n"
            "@@@filename:cut.py\n# cut"
        )
        session = AgentSession(goal="test")
        session.agent_history = [
            {"role": "user", "content": "prompt"},
            {"role": "assistant", "content": truncated},
        ]
        clean, pending = self.runner._handle_truncated_response(session, truncated)
        last = session.agent_history[-1]["content"]
        self.assertNotIn("cut.py", last)
        self.assertEqual(last, clean)
        self.assertEqual(pending, "cut.py")

    def test_T034_09b_agent_history_list_content_patched(self):
        """T-034-09b: agent_history content 가 list(Claude 형식) 일 때도 패치."""
        truncated = "@@@filename:src/x.py\n# cut"
        session = AgentSession(goal="test")
        session.agent_history = [
            {"role": "user", "content": "prompt"},
            {"role": "assistant", "content": [
                {"type": "text", "text": truncated}
            ]},
        ]
        clean, _ = self.runner._handle_truncated_response(session, truncated)
        block = session.agent_history[-1]["content"][0]
        self.assertEqual(block["text"], clean)

    def test_T034_09c_model_role_also_patched(self):
        """T-034-09c: role='model'(Gemini) 도 패치 대상."""
        truncated = "@@@filename:src/y.py\n# cut"
        session = AgentSession(goal="test")
        session.agent_history = [
            {"role": "user", "content": "p"},
            {"role": "model", "content": truncated},
        ]
        clean, _ = self.runner._handle_truncated_response(session, truncated)
        self.assertEqual(session.agent_history[-1]["content"], clean)


# ─── T-034-05: continuation 프롬프트 ─────────────────────────────────────────

class TestContinuationPrompt(unittest.TestCase):

    def setUp(self):
        self.runner = _make_runner()

    def test_T034_05_prompt_contains_continuation_tag(self):
        """T-034-05: [CONTINUATION] 태그 포함."""
        session = AgentSession(goal="구현 목표")
        session.pending_truncated_file = "src/MyService.java"
        prompt = self.runner._build_continuation_prompt(session)
        self.assertIn("[CONTINUATION]", prompt)

    def test_T034_05b_prompt_contains_pending_file(self):
        """T-034-05b: 잘린 파일 경로 포함."""
        session = AgentSession(goal="목표")
        session.pending_truncated_file = "src/MyService.java"
        prompt = self.runner._build_continuation_prompt(session)
        self.assertIn("src/MyService.java", prompt)

    def test_T034_05c_prompt_contains_no_repeat_instruction(self):
        """T-034-05c: '반복하지 마세요' 지시 포함."""
        session = AgentSession(goal="목표")
        session.pending_truncated_file = "src/X.java"
        prompt = self.runner._build_continuation_prompt(session)
        self.assertIn("반복하지 마세요", prompt)

    def test_T034_05d_prompt_fallback_without_pending(self):
        """T-034-05d: pending_truncated_file=None 이어도 프롬프트 생성."""
        session = AgentSession(goal="목표")
        session.pending_truncated_file = None
        prompt = self.runner._build_continuation_prompt(session)
        self.assertIn("[CONTINUATION]", prompt)


# ─── T-034-06: PLAN 잘림 → 0-iteration 종료 억제 ─────────────────────────────

class TestPlanTruncationSuppressTermination(unittest.TestCase):

    def test_T034_06_truncated_plan_does_not_terminate_at_zero_iterations(self):
        """T-034-06: PLAN 잘림 + criteria 실패 → 0-iter GOAL_UNVERIFIED 없음."""
        runner = _make_runner(
            AGENT_EVAL_GATE="1",
            AGENT_MAX_ITERATIONS="1",
        )

        calls = [0]

        def fake_chat(prompt, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                # PLAN 호출 — 잘림
                runner.assistant.last_finish_reason = "max_tokens"
                return "@@@filename:src/Foo.java\n// truncated here"
            # 이후 호출 — criteria reprompt or iteration
            runner.assistant.last_finish_reason = None
            return "[REASON]\n작업 중\n[ACTION]\n[OBSERVE]\n완료"

        runner.assistant.chat.side_effect = fake_chat
        runner.assistant.conversation_history = []

        with patch.object(runner, "_initialize_acceptance_criteria", return_value=False):
            with patch.object(runner, "_finalize_goal",
                              return_value=AgentStopReason.MAX_ITERATIONS):
                with patch("src.agent_runner.AgentRunner._auto_save"):
                    with patch("src.agent_runner.AgentRunner._append_summary_to_main_history"):
                        session = runner.run(goal="구현 목표", bypass_approvals=True)

        # 핵심: 0-iteration GOAL_UNVERIFIED 로 즉시 종료하면 안 됨
        self.assertNotEqual(session.stop_reason, AgentStopReason.GOAL_UNVERIFIED)
        # 루프에 진입했어야 함
        self.assertGreater(len(session.iterations), 0,
                           "PLAN 잘림이 iteration 루프 진입을 막으면 안 됨")


# ─── T-034-07: max_continuations 초과 ────────────────────────────────────────

class TestMaxContinuations(unittest.TestCase):

    def test_T034_07_exceeding_max_continuations_stops_loop(self):
        """T-034-07: continuation_count > max_continuations → MAX_ITERATIONS 종료."""
        runner = _make_runner(
            AGENT_EVAL_GATE="0",
            AGENT_MAX_ITERATIONS="10",
            AGENT_MAX_CONTINUATIONS="2",
        )

        def always_truncated(prompt, **kwargs):
            runner.assistant.last_finish_reason = "max_tokens"
            return "@@@filename:src/Foo.java\n// always truncated"

        runner.assistant.chat.side_effect = always_truncated
        runner.assistant.conversation_history = []

        with patch("src.agent_runner.AgentRunner._auto_save"):
            with patch("src.agent_runner.AgentRunner._append_summary_to_main_history"):
                session = runner.run(goal="목표", bypass_approvals=True)

        self.assertEqual(session.stop_reason, AgentStopReason.MAX_ITERATIONS)

    def test_T034_07b_continuation_does_not_increment_eval_reject(self):
        """T-034-07b: TRUNCATED 응답은 eval_reject_count 를 소모하지 않는다."""
        runner = _make_runner()
        session = AgentSession(goal="목표")
        session.eval_reject_count = 0

        # TRUNCATED 경로는 DONE 게이트를 건드리지 않으므로 reject count 불변
        runner.assistant.last_finish_reason = "max_tokens"
        response_class = runner._classify_response(
            "@@@filename:x.py\n// cut"
        )
        self.assertEqual(response_class, "TRUNCATED")
        # eval_reject_count 는 오직 DONE gate 에서만 증가 — truncation path 에선 불변
        self.assertEqual(session.eval_reject_count, 0)


# ─── T-034-08: 정상 응답 회귀 guard ──────────────────────────────────────────

class TestNormalResponseRegression(unittest.TestCase):

    def test_T034_08_complete_response_stays_complete(self):
        """T-034-08: 정상 응답 → COMPLETE, pending_truncated_file 건드리지 않음."""
        runner = _make_runner()
        runner.assistant.last_finish_reason = None
        response = (
            "[REASON]\n분석\n"
            "[ACTION]\n$ echo ok\n"
            "[OBSERVE]\n완료\n[AGENT_DONE]"
        )
        self.assertEqual(runner._classify_response(response), "COMPLETE")

    def test_T034_08b_no_false_positive_from_triple_at_in_text(self):
        """T-034-08b: 텍스트 내 @@@ 기호가 펜스 오탐 유발하지 않음."""
        runner = _make_runner()
        runner.assistant.last_finish_reason = None
        # 본문 안에 @@@ 가 있어도 filename:/patch: 없으면 무시
        response = (
            "[REASON]\n규칙: @@@금지어@@@ 는 허용 안 됨\n"
            "[ACTION]\n$ echo ok\n"
            "[OBSERVE]\n완료\n[AGENT_DONE]"
        )
        self.assertEqual(runner._classify_response(response), "COMPLETE")

    def test_T034_08c_stop_reason_none_not_finish_reason(self):
        """T-034-08c: finish_reason=stop_reason (Claude STOP) → COMPLETE."""
        runner = _make_runner()
        runner.assistant.last_finish_reason = "end_turn"  # Claude normal stop
        response = "[REASON]\n완료\n[ACTION]\n[OBSERVE]\n[AGENT_DONE]"
        self.assertEqual(runner._classify_response(response), "COMPLETE")


# ─── T-034-10: PLAN 프롬프트 '계획만' 제한 ────────────────────────────────────

class TestPlanPromptRestriction(unittest.TestCase):

    def test_T034_10_plan_prompt_contains_plan_only_instruction(self):
        """T-034-10: _build_initial_prompt → '계획만' 지시 포함 (FR-034-07)."""
        runner = _make_runner()
        prompt = runner._build_initial_prompt("목표 달성하기")
        self.assertIn("계획 목록만", prompt)

    def test_T034_10b_plan_prompt_forbids_code_dump(self):
        """T-034-10b: PLAN 프롬프트에 코드 전문 출력 금지 명시."""
        runner = _make_runner()
        prompt = runner._build_initial_prompt("코드 구현")
        self.assertIn("절대 출력하지 마세요", prompt)

    def test_T034_10c_plan_prompt_iteration_instruction(self):
        """T-034-10c: '이후 각 iteration' 지시 포함."""
        runner = _make_runner()
        prompt = runner._build_initial_prompt("구현")
        self.assertIn("iteration", prompt)


if __name__ == "__main__":
    unittest.main()
