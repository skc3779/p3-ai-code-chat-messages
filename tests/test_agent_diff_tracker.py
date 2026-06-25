"""
P3 Diff 미리보기 + 단계 추적기 테스트 (FSD v1.1.062 §3.4, §3.5)

FR-062-03/04/19 커버:
  A. compute/commit 분리 (PatchApplier)
  B. diff 미리보기 + 정책 승인 (AgentRunner)
  C. 단계 추적기 (AgentRunner)
  D. dispatcher 통합 (_exec_patch)
"""

import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.patch_applier import PatchApplier, PatchPlan, PatchResult
from src.agent_runner import AgentRunner, AgentSession, ActionResult, PlanStep
from src.file_manager import FileManager


# ─── 공통 헬퍼 ────────────────────────────────────────────────────────────

def _patch_payload(search: str, replace: str) -> str:
    """단일 SEARCH/REPLACE 페어 페이로드 문자열 생성."""
    return "\n".join([
        "<<<<<<< SEARCH",
        search,
        "=======",
        replace,
        ">>>>>>> REPLACE",
    ])


def _make_runner(**env_overrides) -> AgentRunner:
    """의존성을 모두 Mock 으로 대체한 AgentRunner 인스턴스를 생성한다."""
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
    return runner


# ─── A. compute/commit 분리 (PatchApplier) ───────────────────────────────

class TestComputeCommitSeparation(unittest.TestCase):
    """A. PatchApplier.compute / commit 분리 동작."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ptest_")
        self.fm = FileManager(self.tmp)
        self.applier = PatchApplier(self.fm)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel: str, content: str) -> Path:
        p = Path(self.tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return p

    def _read(self, rel: str) -> str:
        with open(Path(self.tmp) / rel, "r", encoding="utf-8", newline="") as f:
            return f.read()

    # A-1: compute 는 성공 PatchPlan 을 반환하지만 디스크를 변경하지 않는다
    def test_A1_compute_returns_plan_no_disk_change(self):
        """compute 후 디스크 파일은 원본 그대로여야 한다."""
        original = "line one\nline two\nline three\n"
        self._write("a.txt", original)
        payload = _patch_payload("line two", "line TWO")

        plan = self.applier.compute("a.txt", payload)

        self.assertTrue(plan.success)
        self.assertEqual(plan.computed_text, "line one\nline TWO\nline three\n")
        # 디스크 무변경 확인
        self.assertEqual(self._read("a.txt"), original)

    # A-2: compute 성공 plan 의 diff 문자열 생성
    def test_A2_compute_generates_diff(self):
        """compute 성공 시 non-empty diff 가 생성된다."""
        self._write("b.txt", "alpha\nbeta\n")
        payload = _patch_payload("beta", "BETA")

        plan = self.applier.compute("b.txt", payload)

        self.assertTrue(plan.success)
        self.assertIsInstance(plan.diff, str)
        self.assertIn("-beta", plan.diff)
        self.assertIn("+BETA", plan.diff)

    # A-3: transactional — no_match 블록이 있으면 success=False
    def test_A3_compute_transactional_no_match(self):
        """매칭 실패 블록이 있으면 plan.success=False, computed_text=None."""
        self._write("c.txt", "hello world\n")
        payload = _patch_payload("NONEXISTENT TEXT", "replacement")

        plan = self.applier.compute("c.txt", payload)

        self.assertFalse(plan.success)
        self.assertIsNone(plan.computed_text)

    # A-4: transactional — ambiguous 블록 → success=False
    def test_A4_compute_transactional_ambiguous(self):
        """동일 SEARCH 가 2회 이상 등장하면 ambiguous → success=False."""
        self._write("d.txt", "dup\ndup\n")
        payload = _patch_payload("dup", "replaced")

        plan = self.applier.compute("d.txt", payload)

        self.assertFalse(plan.success)
        statuses = [r.status for r in plan.block_results]
        self.assertIn("ambiguous", statuses)

    # A-5: commit 성공 plan → 디스크 기록
    def test_A5_commit_success_plan_writes_disk(self):
        """commit(성공 plan) 은 실제 파일을 디스크에 기록한다."""
        self._write("e.txt", "foo\nbar\n")
        payload = _patch_payload("bar", "BAR")
        plan = self.applier.compute("e.txt", payload)
        self.assertTrue(plan.success)

        result = self.applier.commit(plan)

        self.assertTrue(result.success)
        self.assertEqual(self._read("e.txt"), "foo\nBAR\n")

    # A-6: commit(success=False plan) → 무변경
    def test_A6_commit_failure_plan_no_change(self):
        """success=False plan 을 commit 하면 디스크 변경 없음."""
        original = "unchanged content\n"
        self._write("f.txt", original)
        failed_plan = PatchPlan(
            rel_path="f.txt",
            computed_text=None,
            success=False,
            error="테스트용 실패",
        )

        result = self.applier.commit(failed_plan)

        self.assertFalse(result.success)
        # 디스크 무변경
        self.assertEqual(self._read("f.txt"), original)

    # A-7: compute_full_file — 신규 파일(before='') diff
    def test_A7_compute_full_file_new_file(self):
        """존재하지 않는 파일에 대해 compute_full_file 은 신규 파일 diff 를 만든다."""
        plan = self.applier.compute_full_file("new_file.txt", "hello\nworld\n")

        self.assertTrue(plan.success)
        self.assertTrue(plan.is_full_file)
        self.assertEqual(plan.before_text, "")
        self.assertFalse(plan.existed)
        self.assertIn("+hello", plan.diff)
        self.assertIn("+world", plan.diff)

    # A-8: compute_full_file — 기존 파일 diff
    def test_A8_compute_full_file_existing(self):
        """기존 파일에 대한 compute_full_file 은 before=현재 내용, diff 생성."""
        self._write("existing.txt", "old content\n")
        plan = self.applier.compute_full_file("existing.txt", "new content\n")

        self.assertTrue(plan.success)
        self.assertTrue(plan.is_full_file)
        self.assertTrue(plan.existed)
        self.assertEqual(plan.before_text, "old content\n")
        self.assertIn("-old content", plan.diff)
        self.assertIn("+new content", plan.diff)

    # A-9: apply wrapper — compute+commit 묶음, auto_approve=True
    def test_A9_apply_wrapper_auto_approve(self):
        """apply(auto_approve=True) 는 compute+commit 을 묶어 기존과 동일 결과를 낸다."""
        self._write("g.txt", "start\nmiddle\nend\n")
        payload = _patch_payload("middle", "MIDDLE")

        result = self.applier.apply("g.txt", payload, auto_approve=True)

        self.assertTrue(result.success)
        self.assertEqual(self._read("g.txt"), "start\nMIDDLE\nend\n")

    # A-10: apply wrapper — on_first_approval 콜백이 True 를 반환하면 commit
    def test_A10_apply_on_first_approval_approved(self):
        """on_first_approval 이 True 반환 시 변경이 적용된다."""
        self._write("h.txt", "aaa\nbbb\n")
        payload = _patch_payload("bbb", "BBB")
        callback_called = []

        def approve():
            callback_called.append(True)
            return True

        result = self.applier.apply(
            "h.txt", payload, auto_approve=False, on_first_approval=approve,
        )

        self.assertTrue(result.success)
        self.assertEqual(callback_called, [True])
        self.assertEqual(self._read("h.txt"), "aaa\nBBB\n")

    # A-11: apply wrapper — on_first_approval 콜백이 False 를 반환하면 무변경
    def test_A11_apply_on_first_approval_rejected(self):
        """on_first_approval 이 False 반환 시 디스크 변경 없음."""
        original = "aaa\nbbb\n"
        self._write("i.txt", original)
        payload = _patch_payload("bbb", "BBB")

        result = self.applier.apply(
            "i.txt", payload, auto_approve=False, on_first_approval=lambda: False,
        )

        self.assertFalse(result.success)
        self.assertEqual(self._read("i.txt"), original)


# ─── B. diff 미리보기 + 정책 승인 (AgentRunner) ──────────────────────────

class TestPreviewAndConfirm(unittest.TestCase):
    """B. _preview_file_change / _confirm_change 동작."""

    def setUp(self):
        self.runner = _make_runner()

    # B-1: 신규 파일(before='') — 전체 라인이 '+' 로 표시
    def test_B1_preview_new_file(self):
        """신규 파일(before='') 의 diff 는 전체 내용이 '+' 라인으로 구성된다."""
        diff = self.runner._preview_file_change("new.py", "", "line1\nline2\n")

        self.assertIn("+line1", diff)
        self.assertIn("+line2", diff)
        self.assertIn("/dev/null", diff)

    # B-2: 기존 파일 변경 diff
    def test_B2_preview_modification(self):
        """기존 파일 변경 시 before/after 가 diff 에 반영된다."""
        diff = self.runner._preview_file_change("f.py", "old\n", "new\n")

        self.assertIn("-old", diff)
        self.assertIn("+new", diff)

    # B-3: AGENT_DIFF_MAX_LINES 초과 시 요약 라인 포함
    def test_B3_preview_truncation_summary(self):
        """diff 라인이 AGENT_DIFF_MAX_LINES 를 초과하면 요약 라인이 포함된다."""
        runner = _make_runner(AGENT_DIFF_MAX_LINES="5")
        # 10줄 이상의 diff 를 생성하기 위해 충분한 변경을 만든다
        before = "\n".join(f"line{i}" for i in range(20)) + "\n"
        after  = "\n".join(f"CHANGED{i}" for i in range(20)) + "\n"

        diff = runner._preview_file_change("big.py", before, after)

        self.assertIn("생략", diff)
        self.assertIn("AGENT_DIFF_MAX_LINES", diff)

    # B-4: _confirm_change — interactive, y 입력 → "yes"
    def test_B4_confirm_interactive_yes(self):
        """interactive 정책 + TTY + 'y' 입력 → 'yes' 반환."""
        with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
            with patch("builtins.input", return_value="y"):
                decision = self.runner._confirm_change("interactive", "f.py", "diff")
        self.assertEqual(decision, "yes")

    # B-5: _confirm_change — interactive, n 입력 → "no"
    def test_B5_confirm_interactive_no(self):
        """interactive 정책 + 'n' 입력 → 'no' 반환."""
        with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
            with patch("builtins.input", return_value="n"):
                decision = self.runner._confirm_change("interactive", "f.py", "diff")
        self.assertEqual(decision, "no")

    # B-6: _confirm_change — interactive, 'A' 입력 → "all"
    def test_B6_confirm_interactive_all(self):
        """'a' 입력(대소문자 무관) → 'all' 반환."""
        with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
            with patch("builtins.input", return_value="a"):
                decision = self.runner._confirm_change("interactive", "f.py", "diff")
        self.assertEqual(decision, "all")

    # B-7: _confirm_change — interactive, 's' 입력 → "stop"
    def test_B7_confirm_interactive_stop(self):
        """'s' 입력 → 'stop' 반환."""
        with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
            with patch("builtins.input", return_value="s"):
                decision = self.runner._confirm_change("interactive", "f.py", "diff")
        self.assertEqual(decision, "stop")

    # B-8: _confirm_change — auto 정책 → 무조건 "yes"
    def test_B8_confirm_auto_always_yes(self):
        """auto 정책은 입력 없이 자동 'yes' 를 반환한다."""
        decision = self.runner._confirm_change("auto", "f.py", "diff")
        self.assertEqual(decision, "yes")

    # B-9: _confirm_change — auto-edit 정책 → "yes"
    def test_B9_confirm_auto_edit_yes(self):
        """auto-edit 정책도 자동 'yes' 를 반환한다."""
        decision = self.runner._confirm_change("auto-edit", "f.py", "diff")
        self.assertEqual(decision, "yes")

    # B-10: AGENT_DIFF_PREVIEW=0 — 미리보기 비활성화 (diff 미출력)
    def test_B10_diff_preview_disabled(self):
        """AGENT_DIFF_PREVIEW=0 이면 diff 미리보기 출력이 없어야 한다."""
        runner = _make_runner(AGENT_DIFF_PREVIEW="0")
        self.assertFalse(runner.diff_preview_enabled)

        printed = []
        with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
            with patch("builtins.input", return_value="y"):
                with patch("builtins.print", side_effect=lambda *a, **k: printed.append(str(a))):
                    runner._confirm_change("interactive", "f.py", "a-diff-string")

        # diff 내용이 print 에 포함되지 않아야 함
        combined = " ".join(printed)
        self.assertNotIn("a-diff-string", combined)

    # B-11: 빈 diff (변경 없음) — _preview_file_change 반환값
    def test_B11_preview_no_change(self):
        """before == after 이면 '(변경 없음)' 반환."""
        result = self.runner._preview_file_change("same.py", "abc\n", "abc\n")
        self.assertEqual(result, "(변경 없음)")


# ─── C. 단계 추적기 (AgentRunner) ────────────────────────────────────────

class TestPlanStepTracker(unittest.TestCase):
    """C. _parse_plan_steps / _render_progress / _advance_step 동작."""

    def setUp(self):
        self.runner = _make_runner()

    # C-1: 번호 목록 파싱 → 3개 PlanStep
    def test_C1_parse_plan_steps_numbered(self):
        """'1. x\n2. y\n3. z' → 3개 PlanStep."""
        plan = "1. 파일 생성\n2. 테스트 실행\n3. 검증"
        steps = self.runner._parse_plan_steps(plan)

        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0].idx, 1)
        self.assertEqual(steps[0].text, "파일 생성")
        self.assertEqual(steps[1].idx, 2)
        self.assertEqual(steps[2].idx, 3)
        self.assertEqual(steps[2].text, "검증")

    # C-2: 번호 없는 plan → 단일 폴백 PlanStep
    def test_C2_parse_plan_steps_fallback(self):
        """번호 목록이 없으면 단일 '전체 목표' 폴백 PlanStep 을 반환한다."""
        steps = self.runner._parse_plan_steps("목표만 있고 번호는 없음")

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].idx, 1)
        self.assertEqual(steps[0].text, "전체 목표")

    # C-3: 빈 plan → 폴백
    def test_C3_parse_plan_steps_empty(self):
        """빈 plan 문자열은 단일 폴백을 반환한다."""
        steps = self.runner._parse_plan_steps("")

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].text, "전체 목표")

    # C-4: 1) 괄호형 번호도 파싱됨
    def test_C4_parse_plan_steps_paren_numbering(self):
        """'1) ...' 형식도 파싱된다."""
        plan = "1) 첫 번째\n2) 두 번째"
        steps = self.runner._parse_plan_steps(plan)

        self.assertEqual(len(steps), 2)

    # C-5: _render_progress — 'N/M' 형식 + 바 문자열
    def test_C5_render_progress_format(self):
        """진행 바는 '진행 N/M' 형식 + ▰▱ 바를 포함한다."""
        session = AgentSession(goal="test")
        session.plan_steps = [
            PlanStep(idx=1, text="step one", status="done"),
            PlanStep(idx=2, text="step two", status="pending"),
            PlanStep(idx=3, text="step three", status="pending"),
        ]

        progress = self.runner._render_progress(session)

        self.assertIn("진행", progress)
        self.assertIn("1/3", progress)
        self.assertIn("▰", progress)
        self.assertIn("▱", progress)

    # C-6: _render_progress — AGENT_PROGRESS_BAR=0 → 빈/비표시
    def test_C6_render_progress_disabled(self):
        """AGENT_PROGRESS_BAR=0 이면 _render_progress 가 빈 문자열을 반환한다."""
        runner = _make_runner(AGENT_PROGRESS_BAR="0")
        session = AgentSession(goal="test")
        session.plan_steps = [PlanStep(idx=1, text="step")]

        result = runner._render_progress(session)

        # 빈 문자열이거나 비표시(falsy)
        self.assertFalse(bool(result))

    # C-7: _advance_step — [STEP:done 2] 태그 → idx=2 스텝을 done 처리
    def test_C7_advance_step_explicit_tag(self):
        """[STEP:done 2] 태그가 있으면 idx=2 스텝이 done 으로 전이된다."""
        session = AgentSession(goal="test")
        session.plan_steps = [
            PlanStep(idx=1, text="step one", status="done"),
            PlanStep(idx=2, text="step two", status="in_progress"),
            PlanStep(idx=3, text="step three", status="pending"),
        ]

        self.runner._advance_step(session, "[STEP:done 2] 완료", "reason")

        self.assertEqual(session.plan_steps[1].status, "done")

    # C-8: _advance_step — 명시 태그 없으면 첫 pending 을 in_progress 만 변경
    def test_C8_advance_step_no_tag_conservative(self):
        """명시 태그가 없고 done 신호도 없으면 첫 pending 을 in_progress 로만 표시한다."""
        session = AgentSession(goal="test")
        session.plan_steps = [
            PlanStep(idx=1, text="alpha beta gamma", status="pending"),
            PlanStep(idx=2, text="step two", status="pending"),
        ]

        self.runner._advance_step(session, "no tag here", "작업 진행 중")

        # 첫 pending → in_progress
        self.assertEqual(session.plan_steps[0].status, "in_progress")
        # 두 번째는 여전히 pending
        self.assertEqual(session.plan_steps[1].status, "pending")

    # C-9: _advance_step — 모호한 응답 시 보수적 미변경 (done 신호 없음)
    def test_C9_advance_step_ambiguous_no_auto_done(self):
        """done 신호가 없으면 in_progress 스텝이 자동으로 done 으로 전이되지 않는다."""
        session = AgentSession(goal="test")
        session.plan_steps = [
            PlanStep(idx=1, text="모호한 스텝", status="in_progress"),
            PlanStep(idx=2, text="다음 스텝", status="pending"),
        ]

        # done 관련 키워드 없는 reason
        self.runner._advance_step(session, "어떤 작업을 진행하고 있습니다", "진행 중")

        # in_progress 스텝이 done 으로 자동 전이되지 않아야 함
        self.assertEqual(session.plan_steps[0].status, "in_progress")

    # C-10: PlanStep.refine_count — mark_step_refined 로 증가
    def test_C10_plan_step_refine_count(self):
        """mark_step_refined 는 해당 스텝의 refine_count 를 1 증가시킨다."""
        session = AgentSession(goal="test")
        session.plan_steps = [
            PlanStep(idx=1, text="step", status="in_progress", refine_count=0),
        ]

        self.runner.mark_step_refined(session, 1)

        self.assertEqual(session.plan_steps[0].refine_count, 1)

    # C-11: refine_count 가 있으면 _render_progress 에 ↻N 포함
    def test_C11_render_progress_shows_refine_count(self):
        """refine_count > 0 인 현재 스텝은 진행 바에 '↻N' 이 포함된다."""
        session = AgentSession(goal="test")
        session.plan_steps = [
            PlanStep(idx=1, text="refinable step", status="in_progress", refine_count=2),
        ]

        progress = self.runner._render_progress(session)

        self.assertIn("↻2", progress)


# ─── D. dispatcher 통합 (가벼운 mock) ────────────────────────────────────

class TestDispatcherPatchIntegration(unittest.TestCase):
    """D. AgentActionDispatcher._exec_patch 의 compute→confirm→commit 흐름."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="disp_test_")
        self.runner = _make_runner()
        # runner 의 file_manager 를 실제 FileManager 로 교체
        self.runner.file_manager = FileManager(self.tmp)
        # dispatcher 의 runner 참조도 동일하게 유지됨 (self._dispatcher._runner is self.runner)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel: str, content: str) -> Path:
        p = Path(self.tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return p

    def _read(self, rel: str) -> str:
        with open(Path(self.tmp) / rel, "r", encoding="utf-8", newline="") as f:
            return f.read()

    # D-1: interactive 거부(n) 시 디스크 무변경
    def test_D1_exec_patch_interactive_rejected_no_disk_change(self):
        """interactive 정책 + 'n' 입력 시 commit 없이 디스크 파일이 변경되지 않는다."""
        original = "foo\nbar\nbaz\n"
        self._write("target.txt", original)

        payload = _patch_payload("bar", "BAR")

        from src.agent_action_dispatcher import AgentActionDispatcher, _ParsedAction
        dispatcher = AgentActionDispatcher(self.runner)

        session = AgentSession(goal="test")
        session.interaction_policy = "interactive"

        action = _ParsedAction(kind="patch", payload=payload, filepath="target.txt")

        with patch("src.agent_runner.AgentRunner._is_tty", return_value=True):
            with patch("builtins.input", return_value="n"):
                result = dispatcher._exec_patch(session, action)

        # ActionResult: 거부 실패
        self.assertFalse(result.success)
        # 디스크 무변경
        self.assertEqual(self._read("target.txt"), original)

    # D-2: bypass_approvals=True 시 자동 commit → 디스크 기록
    def test_D2_exec_patch_bypass_approvals_commits(self):
        """bypass_approvals=True 세션은 자동으로 commit 되어 디스크에 기록된다."""
        self._write("auto.txt", "hello\nworld\n")
        payload = _patch_payload("world", "WORLD")

        from src.agent_action_dispatcher import AgentActionDispatcher, _ParsedAction
        dispatcher = AgentActionDispatcher(self.runner)

        session = AgentSession(goal="test")
        session.bypass_approvals = True
        session.auto_approve_file_mutation = True

        action = _ParsedAction(kind="patch", payload=payload, filepath="auto.txt")

        result = dispatcher._exec_patch(session, action)

        self.assertTrue(result.success)
        self.assertEqual(self._read("auto.txt"), "hello\nWORLD\n")

    # D-3: compute 실패(no_match) → commit 없이 실패 ActionResult
    def test_D3_exec_patch_compute_failure_no_commit(self):
        """compute 가 실패하면 commit 이 호출되지 않아 디스크는 무변경이다."""
        original = "some content\n"
        self._write("nomatch.txt", original)
        payload = _patch_payload("DOES NOT EXIST IN FILE", "replacement")

        from src.agent_action_dispatcher import AgentActionDispatcher, _ParsedAction
        dispatcher = AgentActionDispatcher(self.runner)

        session = AgentSession(goal="test")
        session.bypass_approvals = True

        action = _ParsedAction(kind="patch", payload=payload, filepath="nomatch.txt")

        result = dispatcher._exec_patch(session, action)

        self.assertFalse(result.success)
        self.assertEqual(self._read("nomatch.txt"), original)


if __name__ == "__main__":
    unittest.main()
