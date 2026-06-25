"""
AgentGoalEvaluator 단위 테스트 (FSD v1.1.062 §2.2 / FR-062-08)

대상:
  - extract_from_goal: 결정론적 기준 추출
  - parse_model_criteria: @@@criteria 블록 파싱
  - merge_criteria: extracted 우선·불변, model add-only, 중복 제거, 상한 32
  - evaluate(run_commands=False): file_exists / file_contains / all_passed / unmet / unverified
  - _run_command_shellfree 보안: allowlist, 차단, traversal, zero-test 위장, 정상 실행
"""

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_goal_evaluator import AgentGoalEvaluator, Criterion, CriteriaSnapshot


# ─── 공통 픽스처 ──────────────────────────────────────────────
def _make_evaluator(workspace_dir: str = ".") -> AgentGoalEvaluator:
    """workspace_dir 를 가진 mock file_manager 로 평가기 생성."""
    fm = MagicMock()
    fm.workspace_dir = workspace_dir
    return AgentGoalEvaluator(fm)


# ─── extract_from_goal ────────────────────────────────────────
class TestExtractFromGoal(unittest.TestCase):
    """목표 텍스트에서 결정론적 기준 추출."""

    def setUp(self):
        self.ev = _make_evaluator()

    def test_file_exists_extracted_from_create_goal(self):
        """파일 생성 목표 → file_exists 기준 추출."""
        goal = "utils.py 파일을 생성하세요."
        result = self.ev.extract_from_goal(goal)
        kinds = [c.kind for c in result]
        self.assertIn("file_exists", kinds)
        targets = [c.target for c in result if c.kind == "file_exists"]
        self.assertTrue(any("utils.py" in t for t in targets))

    def test_file_exists_provenance_is_extracted(self):
        """추출된 기준의 provenance 는 'extracted'."""
        goal = "hello.py 파일을 작성하세요."
        result = self.ev.extract_from_goal(goal)
        for c in result:
            self.assertEqual(c.provenance, "extracted")

    def test_pytest_goal_yields_cmd_exit_zero(self):
        """pytest 신호 포함 목표 → cmd_exit_zero 기준 추출."""
        goal = "모든 테스트가 통과하도록 구현하세요."
        result = self.ev.extract_from_goal(goal)
        kinds = [c.kind for c in result]
        self.assertIn("cmd_exit_zero", kinds)

    def test_unittest_goal_yields_cmd_exit_zero(self):
        """unittest 신호 포함 목표 → cmd_exit_zero 기준 추출."""
        goal = "unittest 로 검증하세요."
        result = self.ev.extract_from_goal(goal)
        kinds = [c.kind for c in result]
        self.assertIn("cmd_exit_zero", kinds)

    def test_no_signal_returns_empty(self):
        """명확한 신호 없는 일반 목표 → 빈 리스트."""
        goal = "코드를 정리하세요."
        result = self.ev.extract_from_goal(goal)
        # 파일 경로 패턴이나 테스트 신호가 없으므로 빈 리스트이거나 매우 적어야 함
        kinds = [c.kind for c in result]
        self.assertNotIn("llm", kinds)   # llm 기준은 extract 에서 생성 안 됨

    def test_empty_goal_returns_empty(self):
        """빈 목표 → 빈 리스트."""
        result = self.ev.extract_from_goal("")
        self.assertEqual(result, [])

    def test_none_goal_returns_empty(self):
        """None 목표 → 빈 리스트."""
        result = self.ev.extract_from_goal(None)
        self.assertEqual(result, [])

    def test_result_respects_max_total(self):
        """결과는 MAX_TOTAL(32) 이하."""
        # 많은 파일 경로를 언급
        files = " ".join(f"file{i}.py 파일을 생성" for i in range(40))
        result = self.ev.extract_from_goal(files)
        self.assertLessEqual(len(result), AgentGoalEvaluator.MAX_TOTAL)


# ─── parse_model_criteria ─────────────────────────────────────
class TestParseModelCriteria(unittest.TestCase):
    """@@@criteria 블록 파싱 — 4종 기준 + 엣지 케이스."""

    def setUp(self):
        self.ev = _make_evaluator()

    def test_file_exists_parsed(self):
        """file_exists 줄 파싱."""
        plan = textwrap.dedent("""\
            @@@criteria
            file_exists:src/foo.py
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c.kind, "file_exists")
        self.assertEqual(c.target, "src/foo.py")
        self.assertEqual(c.provenance, "model")

    def test_file_contains_parsed(self):
        """file_contains 줄 파싱 — path::expect 형식."""
        plan = textwrap.dedent("""\
            @@@criteria
            file_contains:src/foo.py::def hello
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c.kind, "file_contains")
        self.assertEqual(c.target, "src/foo.py")
        self.assertEqual(c.expect, "def hello")

    def test_cmd_exit_zero_parsed(self):
        """cmd_exit_zero 줄 파싱."""
        plan = textwrap.dedent("""\
            @@@criteria
            cmd_exit_zero:pytest -q
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c.kind, "cmd_exit_zero")
        self.assertEqual(c.target, "pytest -q")

    def test_model_cmd_non_testrunner_rejected(self):
        """Major-1: 모델 provenance cmd_exit_zero 가 테스트러너가 아니면 게이트 자격 배제.

        `python -c "sys.exit(0)"` 같은 임의 명령 주입(self-grant)은 parse 단계에서
        제외된다. 정당한 pytest/unittest 명령만 게이트 기준으로 인정.
        """
        plan = textwrap.dedent("""\
            @@@criteria
            cmd_exit_zero:python -c "sys.exit(0)"
            cmd_exit_zero:pytest -q
            cmd_exit_zero:python -m unittest
            cmd_exit_zero:python build.py
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        targets = [c.target for c in result]
        # self-grant 주입 명령은 제외됨
        self.assertNotIn('python -c "sys.exit(0)"', targets)
        self.assertNotIn("python build.py", targets)
        # 정당한 테스트러너 명령은 유지됨
        self.assertIn("pytest -q", targets)
        self.assertIn("python -m unittest", targets)

    def test_llm_parsed(self):
        """llm 줄 파싱."""
        plan = textwrap.dedent("""\
            @@@criteria
            llm:코드 품질이 양호해야 함
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        self.assertEqual(len(result), 1)
        c = result[0]
        self.assertEqual(c.kind, "llm")
        self.assertIn("코드 품질", c.target)

    def test_multiple_criteria_parsed(self):
        """여러 기준이 한 블록에 혼재."""
        plan = textwrap.dedent("""\
            @@@criteria
            file_exists:out.txt
            file_contains:out.txt::hello
            cmd_exit_zero:pytest
            llm:결과가 올바름
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        self.assertEqual(len(result), 4)
        kinds = [c.kind for c in result]
        self.assertIn("file_exists", kinds)
        self.assertIn("file_contains", kinds)
        self.assertIn("cmd_exit_zero", kinds)
        self.assertIn("llm", kinds)

    def test_no_block_returns_empty(self):
        """@@@criteria 블록 없는 plan → 빈 리스트."""
        plan = "1. 파일 생성\n2. 테스트 실행"
        result = self.ev.parse_model_criteria(plan)
        self.assertEqual(result, [])

    def test_empty_plan_returns_empty(self):
        """빈 문자열 plan → 빈 리스트."""
        result = self.ev.parse_model_criteria("")
        self.assertEqual(result, [])

    def test_none_plan_returns_empty(self):
        """None plan → 빈 리스트."""
        result = self.ev.parse_model_criteria(None)
        self.assertEqual(result, [])

    def test_comment_lines_ignored(self):
        """# 로 시작하는 줄은 무시."""
        plan = textwrap.dedent("""\
            @@@criteria
            # 이 줄은 무시
            file_exists:src/bar.py
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].kind, "file_exists")

    def test_unknown_kind_ignored(self):
        """알 수 없는 kind 는 무시 (파싱 실패해도 나머지 파싱 계속)."""
        plan = textwrap.dedent("""\
            @@@criteria
            unknown_kind:some_value
            file_exists:valid.py
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        # unknown_kind 는 무시하고 file_exists 만 파싱됨
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].kind, "file_exists")

    def test_file_contains_missing_expect_ignored(self):
        """file_contains 에 :: 없으면 무시."""
        plan = textwrap.dedent("""\
            @@@criteria
            file_contains:src/foo.py
            @@@
        """)
        result = self.ev.parse_model_criteria(plan)
        self.assertEqual(result, [])


# ─── merge_criteria ───────────────────────────────────────────
class TestMergeCriteria(unittest.TestCase):
    """extracted 우선·불변, model add-only, 중복 제거, 상한."""

    def setUp(self):
        self.ev = _make_evaluator()

    def _crit(self, cid, kind="file_exists", prov="extracted", target="x"):
        return Criterion(id=cid, kind=kind, provenance=prov, target=target)

    def test_extracted_comes_first(self):
        """extracted 기준이 결과 앞에 위치."""
        extracted = [self._crit("extracted:file_exists:a", prov="extracted", target="a")]
        model = [self._crit("model:file_exists:b", prov="model", target="b")]
        result = self.ev.merge_criteria(extracted, model)
        self.assertEqual(result[0].id, "extracted:file_exists:a")
        self.assertEqual(result[1].id, "model:file_exists:b")

    def test_extracted_is_immutable_not_overridden_by_model(self):
        """model 에 같은 id 가 있어도 extracted 값이 유지 (add-only)."""
        c_ext = Criterion(
            id="ext:file_exists:a", kind="file_exists", provenance="extracted", target="a"
        )
        c_mod = Criterion(
            id="ext:file_exists:a", kind="file_exists", provenance="model", target="CHANGED"
        )
        result = self.ev.merge_criteria([c_ext], [c_mod])
        # 중복 id 제거 — extracted 가 남고 model 이 추가되지 않음
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].provenance, "extracted")
        self.assertEqual(result[0].target, "a")

    def test_duplicate_model_id_excluded(self):
        """model 내 중복 id 는 1번만 추가."""
        c1 = self._crit("model:file_exists:x", prov="model")
        c2 = self._crit("model:file_exists:x", prov="model")
        result = self.ev.merge_criteria([], [c1, c2])
        ids = [c.id for c in result]
        self.assertEqual(ids.count("model:file_exists:x"), 1)

    def test_max_total_cap_applied(self):
        """max_total 상한 이후 기준은 잘림."""
        extracted = [self._crit(f"e{i}", target=f"f{i}") for i in range(5)]
        model = [self._crit(f"m{i}", prov="model", target=f"g{i}") for i in range(30)]
        result = self.ev.merge_criteria(extracted, model, max_total=10)
        self.assertEqual(len(result), 10)

    def test_default_max_total_is_32(self):
        """기본 MAX_TOTAL=32 적용."""
        extracted = [self._crit(f"e{i}", target=f"f{i}") for i in range(20)]
        model = [self._crit(f"m{i}", prov="model", target=f"g{i}") for i in range(20)]
        result = self.ev.merge_criteria(extracted, model)
        self.assertEqual(len(result), 32)

    def test_empty_inputs_return_empty(self):
        """둘 다 빈 리스트 → 빈 결과."""
        result = self.ev.merge_criteria([], [])
        self.assertEqual(result, [])

    def test_only_model_no_extracted(self):
        """extracted 없이 model 만 있으면 model 기준으로 채워짐."""
        model = [self._crit(f"m{i}", prov="model", target=f"g{i}") for i in range(3)]
        result = self.ev.merge_criteria([], model)
        self.assertEqual(len(result), 3)
        for c in result:
            self.assertEqual(c.provenance, "model")


# ─── evaluate (run_commands=False) ────────────────────────────
class TestEvaluate(unittest.TestCase):
    """파일 기반 검증 + 집계. 명령 실행 없음(run_commands=False)."""

    def setUp(self):
        # 실제 임시 디렉터리 사용
        self.tmpdir = tempfile.mkdtemp()
        self.ev = _make_evaluator(self.tmpdir)
        # file_manager.read_file 은 실제 파일 읽기로 위임
        self.ev.file_manager.read_file = lambda p: Path(p).read_text(encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, rel: str, content: str):
        p = Path(self.tmpdir) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return rel

    # ── file_exists ──
    def test_file_exists_pass(self):
        """존재하는 파일 → passed=True."""
        self._write("hello.py", "# hi")
        c = Criterion(id="t1", kind="file_exists", provenance="model", target="hello.py")
        snap = self.ev.evaluate([c], run_commands=False)
        self.assertTrue(snap.criteria[0].passed)

    def test_file_exists_fail(self):
        """존재하지 않는 파일 → passed=False."""
        c = Criterion(id="t2", kind="file_exists", provenance="model", target="missing.py")
        snap = self.ev.evaluate([c], run_commands=False)
        self.assertFalse(snap.criteria[0].passed)
        self.assertIn("t2", [x.id for x in snap.unmet])

    # ── file_contains ──
    def test_file_contains_pass(self):
        """파일에 기대 문자열 포함 → passed=True."""
        self._write("greet.py", "def hello():\n    return 'world'\n")
        c = Criterion(
            id="t3", kind="file_contains", provenance="model",
            target="greet.py", expect="def hello"
        )
        snap = self.ev.evaluate([c], run_commands=False)
        self.assertTrue(snap.criteria[0].passed)

    def test_file_contains_fail_wrong_expect(self):
        """파일에 기대 문자열 미포함 → passed=False."""
        self._write("greet.py", "def hi():\n    pass\n")
        c = Criterion(
            id="t4", kind="file_contains", provenance="model",
            target="greet.py", expect="def hello"
        )
        snap = self.ev.evaluate([c], run_commands=False)
        self.assertFalse(snap.criteria[0].passed)

    def test_file_contains_fail_file_missing(self):
        """파일 자체가 없으면 → passed=False."""
        c = Criterion(
            id="t5", kind="file_contains", provenance="model",
            target="no_file.py", expect="something"
        )
        snap = self.ev.evaluate([c], run_commands=False)
        self.assertFalse(snap.criteria[0].passed)

    # ── cmd_exit_zero with run_commands=False ──
    def test_cmd_exit_zero_not_run_when_disabled(self):
        """run_commands=False 이면 cmd_exit_zero 는 passed=None(미검증)."""
        c = Criterion(id="t6", kind="cmd_exit_zero", provenance="model", target="pytest -q")
        snap = self.ev.evaluate([c], run_commands=False)
        self.assertIsNone(snap.criteria[0].passed)

    # ── llm → unverified ──
    def test_llm_criterion_yields_unverified(self):
        """llm 기준만 있으면 unverified=True, all_passed=False."""
        c = Criterion(id="t7", kind="llm", provenance="model", target="품질 검토")
        snap = self.ev.evaluate([c], run_commands=False)
        self.assertFalse(snap.all_passed)
        self.assertTrue(snap.unverified)

    # ── all_passed 집계 ──
    def test_all_passed_when_all_file_criteria_pass(self):
        """non-llm 기준이 모두 통과하고 llm 없으면 all_passed=True."""
        self._write("a.py", "pass")
        self._write("b.py", "pass")
        c1 = Criterion(id="c1", kind="file_exists", provenance="model", target="a.py")
        c2 = Criterion(id="c2", kind="file_exists", provenance="model", target="b.py")
        snap = self.ev.evaluate([c1, c2], run_commands=False)
        self.assertTrue(snap.all_passed)
        self.assertEqual(snap.unmet, [])
        self.assertFalse(snap.unverified)

    def test_all_passed_false_when_any_file_fails(self):
        """일부 파일 기준 실패 → all_passed=False."""
        self._write("a.py", "pass")
        c1 = Criterion(id="c1", kind="file_exists", provenance="model", target="a.py")
        c2 = Criterion(id="c2", kind="file_exists", provenance="model", target="missing.py")
        snap = self.ev.evaluate([c1, c2], run_commands=False)
        self.assertFalse(snap.all_passed)
        self.assertEqual(len(snap.unmet), 1)
        self.assertEqual(snap.unmet[0].id, "c2")

    def test_all_passed_false_when_llm_mixed_with_passing_file(self):
        """non-llm 모두 통과해도 llm 기준이 있으면 all_passed=False."""
        self._write("a.py", "pass")
        c1 = Criterion(id="c1", kind="file_exists", provenance="model", target="a.py")
        c2 = Criterion(id="c2", kind="llm", provenance="model", target="검토 필요")
        snap = self.ev.evaluate([c1, c2], run_commands=False)
        self.assertFalse(snap.all_passed)
        self.assertTrue(snap.unverified)

    def test_empty_criteria_returns_unverified(self):
        """기준 0개 → unverified=True, all_passed=False."""
        snap = self.ev.evaluate([], run_commands=False)
        self.assertFalse(snap.all_passed)
        self.assertTrue(snap.unverified)
        self.assertEqual(snap.unmet, [])

    # ── unmet 집계 ──
    def test_unmet_contains_only_failed_criteria(self):
        """unmet 에는 passed=False 인 기준만 포함."""
        self._write("exists.py", "pass")
        c1 = Criterion(id="c1", kind="file_exists", provenance="model", target="exists.py")
        c2 = Criterion(id="c2", kind="file_exists", provenance="model", target="absent.py")
        snap = self.ev.evaluate([c1, c2], run_commands=False)
        unmet_ids = [c.id for c in snap.unmet]
        self.assertNotIn("c1", unmet_ids)
        self.assertIn("c2", unmet_ids)


# ─── _run_command_shellfree 보안 ──────────────────────────────
class TestRunCommandShellfree(unittest.TestCase):
    """shell-free verifier 보안 검증 (실제 실행 포함)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ev = _make_evaluator(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── allowlist 통과 ──
    def test_python_c_allowed(self):
        """python -c 'print(1)' → allowlist 통과, exit 0."""
        rc, out = self.ev._run_command_shellfree("python -c \"print('ok')\"")
        self.assertEqual(rc, 0)
        self.assertIn("ok", out)

    def test_pytest_allowed(self):
        """pytest 명령 → allowlist 통과 (실행 실패여도 rc 만 확인)."""
        # pytest 가 없을 수도 있으므로 rc=-1(실행 파일 없음)도 허용,
        # 단 "차단된 명령" 이 evidence 에 없어야 함.
        rc, out = self.ev._run_command_shellfree("pytest --version")
        self.assertNotIn("차단된 명령", out)
        self.assertNotIn("allowlist 외", out)

    # ── 차단: rm ──
    def test_rm_blocked(self):
        """rm 명령 → allowlist 외 → exit=-1, 차단 메시지."""
        rc, out = self.ev._run_command_shellfree("rm -rf /tmp/foo")
        self.assertEqual(rc, -1)
        self.assertIn("차단", out)

    # ── 차단: git ──
    def test_git_blocked(self):
        """git 명령 → 차단."""
        rc, out = self.ev._run_command_shellfree("git status")
        self.assertEqual(rc, -1)
        self.assertIn("차단", out)

    # ── 차단: curl ──
    def test_curl_blocked(self):
        """curl 명령 → 차단."""
        rc, out = self.ev._run_command_shellfree("curl http://example.com")
        self.assertEqual(rc, -1)
        self.assertIn("차단", out)

    # ── 셸 인젝션 무력화 ──
    def test_shell_injection_semicolon_blocked(self):
        """';' 인젝션 시도: shlex.split 로 파싱하면 argv[0]='python', 뒤는 별도 토큰.
        실제로 rm 이 실행되지 않고 차단 또는 python 경로로만 처리됨을 확인."""
        # "python -c 'x'; rm -rf /" → shlex.split 시 argv[0]='python', '-c', 'x;',
        # 'rm', '-rf', '/'  → _is_allowed 는 python 허용이나 traversal 로 '/'' 거부.
        rc, out = self.ev._run_command_shellfree("python -c 'x'; rm -rf /")
        # rm 이 shell 경유 없이는 실행 불가 → 실제 rm 실행 안 됨.
        # rc=0 이더라도 실제 rm 이 실행된 것이 아니므로 원래 코드 오류 없이 처리됨.
        # 핵심: shell=False 이므로 ';' 이후 명령이 셸에서 실행되지 않음.
        # python -c 'x'; rm → shlex 가 ['python', '-c', 'x;', 'rm', '-rf', '/'] 로 분리
        # '/'' 는 절대경로 인자 → workspace 밖 → 차단.
        self.assertEqual(rc, -1)
        self.assertIn("차단", out)

    # ── .. traversal 거부 ──
    def test_dotdot_traversal_blocked(self):
        """.. 포함 경로 인자 → 차단."""
        rc, out = self.ev._run_command_shellfree("pytest ../outside/test.py")
        self.assertEqual(rc, -1)
        self.assertIn("차단", out)

    # ── zero-test 위장 차단 ──
    def test_zero_test_collected_0_blocked(self):
        """pytest 가 'collected 0 items' 출력 시 passed=False 처리."""
        # evaluate 를 통해 cmd_exit_zero 기준으로 검증
        # tmpdir 에 pytest 가 없는 경우를 대비해 mock 사용
        import unittest.mock as mock

        with mock.patch.object(
            self.ev, "_run_command_shellfree",
            return_value=(0, "collected 0 items\n")
        ):
            c = Criterion(
                id="z1", kind="cmd_exit_zero", provenance="model", target="pytest -q"
            )
            snap = self.ev.evaluate([c], run_commands=True)
            self.assertFalse(snap.criteria[0].passed)
            ev_text = snap.criteria[0].evidence
            self.assertIn("zero-test", ev_text.lower() if ev_text else "")

    def test_zero_test_ran_0_blocked(self):
        """'ran 0 tests' 출력 시 passed=False."""
        import unittest.mock as mock

        with mock.patch.object(
            self.ev, "_run_command_shellfree",
            return_value=(0, "Ran 0 tests in 0.001s\nOK\n")
        ):
            c = Criterion(
                id="z2", kind="cmd_exit_zero", provenance="model", target="python -m unittest"
            )
            snap = self.ev.evaluate([c], run_commands=True)
            self.assertFalse(snap.criteria[0].passed)

    def test_normal_pytest_pass(self):
        """정상 pytest exit=0 + 테스트 수 > 0 → passed=True."""
        import unittest.mock as mock

        with mock.patch.object(
            self.ev, "_run_command_shellfree",
            return_value=(0, "3 passed in 0.12s\n")
        ):
            c = Criterion(
                id="p1", kind="cmd_exit_zero", provenance="model", target="pytest -q"
            )
            snap = self.ev.evaluate([c], run_commands=True)
            self.assertTrue(snap.criteria[0].passed)

    def test_normal_pytest_fail(self):
        """pytest exit=1(실패) → passed=False."""
        import unittest.mock as mock

        with mock.patch.object(
            self.ev, "_run_command_shellfree",
            return_value=(1, "1 failed, 2 passed\n")
        ):
            c = Criterion(
                id="p2", kind="cmd_exit_zero", provenance="model", target="pytest -q"
            )
            snap = self.ev.evaluate([c], run_commands=True)
            self.assertFalse(snap.criteria[0].passed)


if __name__ == "__main__":
    unittest.main()
