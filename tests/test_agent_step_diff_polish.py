"""
P5 다듬기 테스트 (FSD v1.1.062 §3.5 / §3.8.5 / FR-062-05 / FR-062-10)

대상:
  A. 스텝 자동 전이: _auto_done_by_criteria / _criteria_for_step
  B. refine_count:   _mark_unmet_steps_refined / _render_progress
  C. diff 요약:      _summarize_diff / _preview_file_change / _confirm_change
     + dispatcher 자동승인 patch diff 경로
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_goal_evaluator import Criterion, CriteriaSnapshot
from src.agent_runner import AgentRunner, AgentSession, PlanStep


# ─── 공통 픽스처 ──────────────────────────────────────────────

def _make_runner(env_overrides: dict = None) -> AgentRunner:
    """최소 mock 으로 AgentRunner 생성 (환경변수 오버라이드 가능)."""
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"
    assistant.chat = MagicMock(return_value="")

    file_manager = MagicMock()
    file_manager.workspace_dir = Path(tempfile.mkdtemp())

    env = env_overrides or {}
    with patch.dict(os.environ, env, clear=False):
        with patch("src.agent_runner.CodeExecutor"):
            runner = AgentRunner(
                assistant=assistant,
                file_manager=file_manager,
                code_executor=MagicMock(),
                terminal_executor=MagicMock(),
                response_parser=MagicMock(),
                cli_handler=MagicMock(),
                streaming=False,
            )
    return runner


def _make_session() -> AgentSession:
    return AgentSession(goal="test goal")


def _step(idx: int, text: str, status: str = "pending", refine_count: int = 0) -> PlanStep:
    return PlanStep(idx=idx, text=text, status=status, refine_count=refine_count)


def _criterion(cid: str, kind: str = "file_exists", target: str = "x.py",
               passed=None, evidence: str = "") -> Criterion:
    return Criterion(
        id=cid, kind=kind, provenance="extracted",
        target=target, passed=passed, evidence=evidence,
    )


def _snapshot(criteria, unmet=None) -> CriteriaSnapshot:
    return CriteriaSnapshot(
        criteria=criteria,
        all_passed=False,
        unmet=unmet if unmet is not None else [],
        unverified=False,
    )


# ─── A. 스텝 자동 전이 ────────────────────────────────────────

class TestAutoDoneByCriteria(unittest.TestCase):
    """_auto_done_by_criteria 보수적 매핑 + 포인터 전진 (FR-062-05, §3.5)."""

    def setUp(self):
        self.runner = _make_runner()

    # A-1: 명시 참조 + passed → done
    def test_explicit_ref_and_passed_marks_done(self):
        """step.text 에 criterion.target 이 들어 있고 passed=True → done."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py file")]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=True),
        ]
        self.runner._auto_done_by_criteria(session)
        self.assertEqual(session.plan_steps[0].status, "done")

    # A-2: 연결 기준 미통과 → 미변경
    def test_linked_criterion_not_passed_no_change(self):
        """연결 기준이 passed=False 이면 스텝 상태 변경 없음."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py file", status="in_progress")]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=False),
        ]
        self.runner._auto_done_by_criteria(session)
        self.assertEqual(session.plan_steps[0].status, "in_progress")

    # A-3: 연결 기준 미검증(passed=None) → done 안 됨 (포인터 전진은 허용)
    def test_linked_criterion_unverified_not_marked_done(self):
        """연결 기준이 passed=None(미검증)이면 done 처리 안 됨.
        포인터 전진(pending→in_progress)은 별도 UX 동작이므로 done 이 아님을 검증."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py file", status="pending")]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=None),
        ]
        self.runner._auto_done_by_criteria(session)
        # passed=None → all(passed is True) 불충족 → done 아님.
        # 포인터 전진으로 in_progress 가 되는 것은 의도된 동작(done 이 아니면 됨).
        self.assertNotEqual(session.plan_steps[0].status, "done")

    # A-4: 비연결 step → done 안 됨 (target 이 text 에 없음)
    def test_unlinked_step_not_marked_done(self):
        """step.text 에 criterion.target 이 없으면 연결 없음 → done 안 됨."""
        session = _make_session()
        session.plan_steps = [_step(1, "setup project structure", status="pending")]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=True),
        ]
        self.runner._auto_done_by_criteria(session)
        # 연결 없으므로 done 이 아니어야 함; in_progress 로 전진될 수는 있음
        self.assertNotEqual(session.plan_steps[0].status, "done")

    # A-5: llm 기준 → 연결 제외(매핑 안 됨)
    def test_llm_criterion_excluded_from_mapping(self):
        """llm 기준은 자동 검증 불가 → 연결에서 제외, step 상태 변경 없음."""
        session = _make_session()
        session.plan_steps = [_step(1, "implement utils.py logic", status="in_progress")]
        session.acceptance_criteria = [
            _criterion("c1", kind="llm", target="utils.py", passed=True),
        ]
        self.runner._auto_done_by_criteria(session)
        self.assertNotEqual(session.plan_steps[0].status, "done")

    # A-6: target<3자 → 스킵(과잉매칭 방지)
    def test_short_target_skipped(self):
        """criterion.target 길이 3 미만 → 과잉매칭 방지로 연결 제외."""
        session = _make_session()
        session.plan_steps = [_step(1, "run ok test", status="in_progress")]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="ok", passed=True),  # len=2
        ]
        self.runner._auto_done_by_criteria(session)
        # 연결 없으므로 done 안 됨
        self.assertNotEqual(session.plan_steps[0].status, "done")

    # A-7: done 보존(재변경 없음)
    def test_done_status_preserved(self):
        """이미 done 된 step 은 재변경 없이 그대로 보존."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py file", status="done")]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=False),
        ]
        self.runner._auto_done_by_criteria(session)
        self.assertEqual(session.plan_steps[0].status, "done")

    # A-8: 다수 기준 중 하나라도 미통과 → 미변경
    def test_one_unmet_criterion_among_many_prevents_done(self):
        """연결 기준 여럿 중 하나라도 미통과이면 done 안 됨.
        step.text 에 두 criterion target 이 모두 부분문자열로 포함돼야 연결됨."""
        session = _make_session()
        # 스텝 텍스트에 두 target('utils.py', 'run pytest') 모두 포함
        session.plan_steps = [_step(1, "create utils.py and run pytest suite", status="in_progress")]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=True),
            _criterion("c2", kind="cmd_exit_zero", target="run pytest", passed=False),
        ]
        self.runner._auto_done_by_criteria(session)
        # c2 가 연결되고 passed=False 이므로 all(passed is True) 불충족 → done 안 됨
        self.assertNotEqual(session.plan_steps[0].status, "done")

    # A-9: 포인터 전진 — done 후 in_progress 없으면 다음 pending → in_progress
    def test_pointer_advance_after_all_done(self):
        """done 전이 후 in_progress 없으면 다음 pending 이 in_progress 로 전진."""
        session = _make_session()
        session.plan_steps = [
            _step(1, "create utils.py file", status="pending"),
            _step(2, "write tests", status="pending"),
        ]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=True),
        ]
        self.runner._auto_done_by_criteria(session)
        # step1 이 done 됐으면 in_progress 없으므로 step2 가 in_progress 로 전진
        self.assertEqual(session.plan_steps[0].status, "done")
        self.assertEqual(session.plan_steps[1].status, "in_progress")

    # A-10: 포인터 전진 불필요 — in_progress 이미 있으면 그대로
    def test_pointer_advance_skipped_if_in_progress_exists(self):
        """이미 in_progress 가 있으면 포인터 전진 안 함."""
        session = _make_session()
        session.plan_steps = [
            _step(1, "create utils.py file", status="pending"),
            _step(2, "write tests", status="in_progress"),
            _step(3, "final step", status="pending"),
        ]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=True),
        ]
        self.runner._auto_done_by_criteria(session)
        # step2 가 in_progress 이므로 step3 으로 전진 안 함
        self.assertEqual(session.plan_steps[2].status, "pending")

    # A-11: 종료 권위 불변 — stop_reason 변경 없음
    def test_stop_reason_unchanged(self):
        """_auto_done_by_criteria 는 stop_reason 을 변경하지 않음(표시용)."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py file", status="pending")]
        session.acceptance_criteria = [
            _criterion("c1", kind="file_exists", target="utils.py", passed=True),
        ]
        session.stop_reason = None
        self.runner._auto_done_by_criteria(session)
        self.assertIsNone(session.stop_reason)


class TestCriteriaForStep(unittest.TestCase):
    """_criteria_for_step 보수적 매핑 (§3.5)."""

    def setUp(self):
        self.runner = _make_runner()

    def test_exact_substring_match(self):
        """target 이 step.text 의 부분문자열 → 연결됨."""
        step = _step(1, "create utils.py module")
        c = _criterion("c1", target="utils.py", passed=True)
        result = AgentRunner._criteria_for_step(step, [c])
        self.assertEqual(len(result), 1)

    def test_no_match_returns_empty(self):
        """target 이 step.text 에 없으면 빈 리스트."""
        step = _step(1, "setup environment")
        c = _criterion("c1", target="utils.py", passed=True)
        result = AgentRunner._criteria_for_step(step, [c])
        self.assertEqual(result, [])

    def test_llm_kind_excluded(self):
        """llm 기준은 반환 목록에서 제외."""
        step = _step(1, "create utils.py")
        c = _criterion("c1", kind="llm", target="utils.py", passed=True)
        result = AgentRunner._criteria_for_step(step, [c])
        self.assertEqual(result, [])

    def test_short_target_excluded(self):
        """target 길이 < 3 이면 제외 (과잉매칭 방지)."""
        step = _step(1, "run ok")
        c = _criterion("c1", target="ok", passed=True)  # len=2
        result = AgentRunner._criteria_for_step(step, [c])
        self.assertEqual(result, [])

    def test_exactly_3_chars_target_included(self):
        """target 길이 == 3 이면 포함 (경계값)."""
        step = _step(1, "create abc module")
        c = _criterion("c1", target="abc", passed=True)  # len=3
        result = AgentRunner._criteria_for_step(step, [c])
        self.assertEqual(len(result), 1)

    def test_case_insensitive_match(self):
        """대소문자 무관 매핑 (step.text 와 target 모두 lower())."""
        step = _step(1, "create Utils.py file")
        c = _criterion("c1", target="utils.py", passed=True)
        result = AgentRunner._criteria_for_step(step, [c])
        self.assertEqual(len(result), 1)

    def test_multiple_criteria_filtered(self):
        """여러 기준 중 매칭되는 것만 반환."""
        step = _step(1, "create utils.py and tests.py")
        c1 = _criterion("c1", target="utils.py", passed=True)
        c2 = _criterion("c2", target="other.py", passed=True)
        c3 = _criterion("c3", target="tests.py", passed=False)
        result = AgentRunner._criteria_for_step(step, [c1, c2, c3])
        ids = [c.id for c in result]
        self.assertIn("c1", ids)
        self.assertIn("c3", ids)
        self.assertNotIn("c2", ids)


# ─── B. refine_count 테스트 ──────────────────────────────────

class TestMarkUnmetStepsRefined(unittest.TestCase):
    """_mark_unmet_steps_refined: probe 당 미충족 연결 step refine_count++ (FR-062-05)."""

    def setUp(self):
        self.runner = _make_runner()

    def test_refine_count_incremented_for_linked_unmet_step(self):
        """미충족 기준에 연결된 미완료 step 의 refine_count 가 1 증가."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py file", status="in_progress")]
        c1 = _criterion("c1", target="utils.py", passed=False)
        snap = _snapshot([c1], unmet=[c1])
        self.runner._mark_unmet_steps_refined(session, snap)
        self.assertEqual(session.plan_steps[0].refine_count, 1)

    def test_done_step_excluded_from_refine(self):
        """done 스텝은 refine_count 증가 대상에서 제외."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py file", status="done")]
        c1 = _criterion("c1", target="utils.py", passed=False)
        snap = _snapshot([c1], unmet=[c1])
        self.runner._mark_unmet_steps_refined(session, snap)
        self.assertEqual(session.plan_steps[0].refine_count, 0)

    def test_unlinked_step_not_incremented(self):
        """미충족 기준과 연결 없는 step 은 refine_count 불변."""
        session = _make_session()
        session.plan_steps = [_step(1, "setup environment", status="in_progress")]
        c1 = _criterion("c1", target="utils.py", passed=False)
        snap = _snapshot([c1], unmet=[c1])
        self.runner._mark_unmet_steps_refined(session, snap)
        self.assertEqual(session.plan_steps[0].refine_count, 0)

    def test_one_increment_per_probe_even_with_multiple_unmet(self):
        """한 probe 에서 중복 기준이 있어도 step 당 최대 1회만 증가."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py and tests", status="pending")]
        c1 = _criterion("c1", target="utils.py", passed=False)
        c2 = _criterion("c2", target="utils.py tests", passed=False)
        snap = _snapshot([c1, c2], unmet=[c1, c2])
        self.runner._mark_unmet_steps_refined(session, snap)
        self.assertEqual(session.plan_steps[0].refine_count, 1)

    def test_multiple_probes_accumulate(self):
        """여러 probe 호출 시 refine_count 가 누적됨."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py", status="in_progress")]
        c1 = _criterion("c1", target="utils.py", passed=False)
        snap = _snapshot([c1], unmet=[c1])
        self.runner._mark_unmet_steps_refined(session, snap)
        self.runner._mark_unmet_steps_refined(session, snap)
        self.assertEqual(session.plan_steps[0].refine_count, 2)

    def test_empty_unmet_no_change(self):
        """미충족 기준 없으면 refine_count 변화 없음."""
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py", status="in_progress")]
        snap = _snapshot([], unmet=[])
        self.runner._mark_unmet_steps_refined(session, snap)
        self.assertEqual(session.plan_steps[0].refine_count, 0)

    def test_empty_steps_no_error(self):
        """plan_steps 없어도 오류 없음."""
        session = _make_session()
        session.plan_steps = []
        c1 = _criterion("c1", target="utils.py", passed=False)
        snap = _snapshot([c1], unmet=[c1])
        # 예외 없이 통과해야 함
        self.runner._mark_unmet_steps_refined(session, snap)


class TestRenderProgress(unittest.TestCase):
    """_render_progress: ↻N 표시 (§3.5, §3.8.5)."""

    def setUp(self):
        self.runner = _make_runner()

    def test_refine_count_shown_in_progress(self):
        """refine_count>0 이면 ↻N 이 출력 문자열에 포함됨."""
        session = _make_session()
        session.plan_steps = [
            _step(1, "create utils.py", status="in_progress", refine_count=3),
        ]
        result = self.runner._render_progress(session)
        self.assertIn("↻3", result)

    def test_no_refine_count_not_shown(self):
        """refine_count=0 이면 ↻ 가 출력되지 않음."""
        session = _make_session()
        session.plan_steps = [
            _step(1, "create utils.py", status="in_progress", refine_count=0),
        ]
        result = self.runner._render_progress(session)
        self.assertNotIn("↻", result)

    def test_progress_bar_disabled_returns_empty(self):
        """AGENT_PROGRESS_BAR=0 이면 빈 문자열 반환."""
        runner = _make_runner({"AGENT_PROGRESS_BAR": "0"})
        session = _make_session()
        session.plan_steps = [_step(1, "create utils.py", status="in_progress")]
        result = runner._render_progress(session)
        self.assertEqual(result, "")

    def test_render_shows_done_fraction(self):
        """완료/전체 비율이 출력 문자열에 포함됨."""
        session = _make_session()
        session.plan_steps = [
            _step(1, "step one", status="done"),
            _step(2, "step two", status="pending"),
        ]
        result = self.runner._render_progress(session)
        self.assertIn("1/2", result)

    def test_refine_count_shown_for_pending_current(self):
        """in_progress 없을 때 첫 pending 스텝의 ↻N 이 표시됨."""
        session = _make_session()
        session.plan_steps = [
            _step(1, "create utils.py", status="pending", refine_count=2),
        ]
        result = self.runner._render_progress(session)
        self.assertIn("↻2", result)


# ─── C. diff 요약 테스트 ──────────────────────────────────────

class TestSummarizeDiff(unittest.TestCase):
    """_summarize_diff: AGENT_DIFF_MAX_LINES 초과 시 요약 (FR-062-10)."""

    def test_short_diff_returned_verbatim(self):
        """AGENT_DIFF_MAX_LINES 이하 diff 는 전문 그대로 반환."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "100"})
        diff = "\n".join([f"+line {i}" for i in range(5)])
        result = runner._summarize_diff(diff)
        self.assertEqual(result, diff)

    def test_long_diff_truncated_with_omission_line(self):
        """AGENT_DIFF_MAX_LINES 초과 diff → 앞부분 + 생략 줄 수 요약 라인."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "5"})
        diff = "\n".join([f"+line {i}" for i in range(20)])
        result = runner._summarize_diff(diff)
        lines = result.split("\n")
        # 처음 5줄만 내용
        self.assertEqual(lines[0], "+line 0")
        self.assertEqual(lines[4], "+line 4")
        # 마지막 줄에 생략 정보
        self.assertIn("생략", lines[-1])
        self.assertIn("15", lines[-1])  # 20-5=15 줄 생략

    def test_empty_diff_returned_as_is(self):
        """빈 diff 는 그대로 반환 (오류 없음)."""
        runner = _make_runner()
        result = runner._summarize_diff("")
        self.assertEqual(result, "")

    def test_exactly_max_lines_not_truncated(self):
        """diff 줄 수 == AGENT_DIFF_MAX_LINES 이면 생략 없음."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "5"})
        diff = "\n".join([f"+line {i}" for i in range(5)])
        result = runner._summarize_diff(diff)
        self.assertNotIn("생략", result)

    def test_omission_line_contains_max_lines_env(self):
        """생략 줄 수 요약에 AGENT_DIFF_MAX_LINES 값이 포함됨."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "3"})
        diff = "\n".join([f"+line {i}" for i in range(10)])
        result = runner._summarize_diff(diff)
        self.assertIn("AGENT_DIFF_MAX_LINES=3", result)


class TestPreviewFileChange(unittest.TestCase):
    """_preview_file_change: _summarize_diff 경유 확인 (FR-062-10)."""

    def test_new_file_returns_non_empty_diff(self):
        """신규 파일(before 없음) → 전체 내용이 diff 로 반환됨."""
        runner = _make_runner()
        result = runner._preview_file_change("utils.py", "", "def foo(): pass")
        self.assertIn("foo", result)

    def test_no_change_returns_no_change_marker(self):
        """before == after → '(변경 없음)' 반환."""
        runner = _make_runner()
        content = "def foo(): pass"
        result = runner._preview_file_change("utils.py", content, content)
        self.assertEqual(result, "(변경 없음)")

    def test_large_diff_summarized(self):
        """large diff 는 AGENT_DIFF_MAX_LINES 요약을 거쳐 생략 줄 포함."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "5"})
        before = "\n".join([f"old line {i}" for i in range(50)])
        after = "\n".join([f"new line {i}" for i in range(50)])
        result = runner._preview_file_change("f.py", before, after)
        self.assertIn("생략", result)

    def test_small_diff_not_summarized(self):
        """소규모 diff 는 생략 없이 전문 반환."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "100"})
        before = "def foo(): pass"
        after = "def foo(): return 1"
        result = runner._preview_file_change("f.py", before, after)
        self.assertNotIn("생략", result)


class TestConfirmChange(unittest.TestCase):
    """_confirm_change: 3분기 모두 _summarize_diff 경유 검증 (FR-062-10)."""

    def setUp(self):
        self.runner = _make_runner()

    def _make_large_diff(self, lines: int = 300) -> str:
        return "\n".join([f"+line {i}" for i in range(lines)])

    def test_auto_policy_returns_yes_no_prompt(self):
        """auto 정책 → 바로 'yes' 반환 (프롬프트 없음)."""
        diff = "+some change"
        result = self.runner._confirm_change("auto", "f.py", diff)
        self.assertEqual(result, "yes")

    def test_auto_edit_policy_returns_yes_no_prompt(self):
        """auto-edit 정책 → 바로 'yes' 반환 (파일 편집 자동)."""
        diff = "+some change"
        result = self.runner._confirm_change("auto-edit", "f.py", diff)
        self.assertEqual(result, "yes")

    def test_auto_policy_large_diff_summarized_in_print(self):
        """auto 정책에서 대용량 diff → _summarize_diff 경유(출력에 생략 포함)."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "5"})
        large_diff = self._make_large_diff(100)
        printed = []
        with patch("builtins.print", side_effect=lambda *a, **kw: printed.append(str(a))):
            runner._confirm_change("auto", "f.py", large_diff)
        all_output = " ".join(printed)
        # 출력에 생략 줄 요약이 포함되어야 함
        self.assertIn("생략", all_output)

    def test_auto_edit_policy_large_diff_summarized_in_print(self):
        """auto-edit 정책에서 대용량 diff → _summarize_diff 경유(출력에 생략 포함)."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "5"})
        large_diff = self._make_large_diff(100)
        printed = []
        with patch("builtins.print", side_effect=lambda *a, **kw: printed.append(str(a))):
            runner._confirm_change("auto-edit", "f.py", large_diff)
        all_output = " ".join(printed)
        self.assertIn("생략", all_output)

    def test_interactive_non_tty_returns_no(self):
        """interactive 정책 + 비-TTY → 'no' 반환 (편집 보류)."""
        with patch.object(self.runner, "_is_tty", return_value=False):
            result = self.runner._confirm_change("interactive", "f.py", "+change")
        self.assertEqual(result, "no")

    def test_interactive_non_tty_large_diff_summarized(self):
        """interactive + 비-TTY 도 출력 경로에서 diff 요약 적용됨."""
        runner = _make_runner({"AGENT_DIFF_MAX_LINES": "5"})
        large_diff = self._make_large_diff(100)
        printed = []
        with patch.object(runner, "_is_tty", return_value=False):
            with patch("builtins.print", side_effect=lambda *a, **kw: printed.append(str(a))):
                runner._confirm_change("interactive", "f.py", large_diff)
        all_output = " ".join(printed)
        self.assertIn("생략", all_output)

    def test_interactive_tty_yes_answer(self):
        """interactive + TTY + 'y' 입력 → 'yes' 반환."""
        with patch.object(self.runner, "_is_tty", return_value=True):
            with patch.object(self.runner._input_listener, "paused"):
                with patch("builtins.input", return_value="y"):
                    result = self.runner._confirm_change("interactive", "f.py", "+change")
        self.assertEqual(result, "yes")

    def test_interactive_tty_no_answer(self):
        """interactive + TTY + 'n' 입력 → 'no' 반환."""
        with patch.object(self.runner, "_is_tty", return_value=True):
            with patch.object(self.runner._input_listener, "paused"):
                with patch("builtins.input", return_value="n"):
                    result = self.runner._confirm_change("interactive", "f.py", "+change")
        self.assertEqual(result, "no")

    def test_interactive_tty_stop_answer(self):
        """interactive + TTY + 's' 입력 → 'stop' 반환."""
        with patch.object(self.runner, "_is_tty", return_value=True):
            with patch.object(self.runner._input_listener, "paused"):
                with patch("builtins.input", return_value="s"):
                    result = self.runner._confirm_change("interactive", "f.py", "+change")
        self.assertEqual(result, "stop")

    def test_interactive_tty_all_answer(self):
        """interactive + TTY + 'a' 입력 → 'all' 반환(세션 자동 승인)."""
        with patch.object(self.runner, "_is_tty", return_value=True):
            with patch.object(self.runner._input_listener, "paused"):
                with patch("builtins.input", return_value="a"):
                    result = self.runner._confirm_change("interactive", "f.py", "+change")
        self.assertEqual(result, "all")


class TestDispatcherPatchDiffSummarize(unittest.TestCase):
    """dispatcher 자동승인 경로: plan.diff → _summarize_diff 경유 (FR-062-10)."""

    def setUp(self):
        self.runner = _make_runner({"AGENT_DIFF_MAX_LINES": "5"})

    def test_auto_approve_patch_large_diff_summarized(self):
        """자동승인 경로에서 plan.diff 가 크면 _summarize_diff 경유 출력됨."""
        from src.agent_action_dispatcher import AgentActionDispatcher, _ParsedAction

        session = _make_session()
        session.bypass_approvals = True
        session.auto_approve_file_mutation = True

        # large diff 를 반환하는 mock PlanResult
        large_diff = "\n".join([f"+line {i}" for i in range(100)])
        mock_plan = MagicMock()
        mock_plan.success = True
        mock_plan.diff = large_diff
        mock_plan.block_results = [MagicMock(status="ok", diagnostic=None)]

        mock_applier = MagicMock()
        mock_applier.compute.return_value = mock_plan
        mock_applier.commit.return_value = MagicMock(
            success=True, applied_count=1, total_count=1,
            block_results=[MagicMock(status="ok")],
        )

        printed = []
        # PatchApplier 는 _exec_patch 내부에서 지역 import 되므로 모듈 소스에서 패치
        with patch("src.patch_applier.PatchApplier", return_value=mock_applier):
            with patch("builtins.print", side_effect=lambda *a, **kw: printed.append(str(a))):
                dispatcher = AgentActionDispatcher(self.runner)
                action = _ParsedAction(kind="patch", payload="dummy", filepath="f.py")
                dispatcher._exec_patch(session, action)

        all_output = " ".join(printed)
        # 자동승인 경로에서 large diff 가 요약되어 '생략' 이 출력에 포함되어야 함
        self.assertIn("생략", all_output)

    def test_non_auto_approve_patch_diff_summarized_via_confirm(self):
        """비자동승인(interactive+비-TTY) 경로에서도 _summarize_diff 경유됨."""
        from src.agent_action_dispatcher import AgentActionDispatcher, _ParsedAction

        session = _make_session()
        session.bypass_approvals = False
        session.auto_approve_file_mutation = False
        session.interaction_policy = "interactive"

        large_diff = "\n".join([f"+line {i}" for i in range(100)])
        mock_plan = MagicMock()
        mock_plan.success = True
        mock_plan.diff = large_diff

        mock_applier = MagicMock()
        mock_applier.compute.return_value = mock_plan

        printed = []
        # PatchApplier 는 _exec_patch 내부에서 지역 import 되므로 모듈 소스에서 패치
        with patch("src.patch_applier.PatchApplier", return_value=mock_applier):
            with patch.object(self.runner, "_is_tty", return_value=False):
                with patch("builtins.print", side_effect=lambda *a, **kw: printed.append(str(a))):
                    dispatcher = AgentActionDispatcher(self.runner)
                    action = _ParsedAction(kind="patch", payload="dummy", filepath="f.py")
                    dispatcher._exec_patch(session, action)

        all_output = " ".join(printed)
        self.assertIn("생략", all_output)


if __name__ == "__main__":
    unittest.main()
