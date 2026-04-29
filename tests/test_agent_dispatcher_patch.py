"""
AgentActionDispatcher patch 통합 테스트 (FSD v1.0.115)

T-111-30 ~ T-111-39 — @@@patch:<path>``` 펜스의 파싱, 라우팅, 승인 흐름,
filename 우선 적용(FR-111-25), 자기 수정 트리거.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_action_dispatcher import AgentActionDispatcher
from src.agent_runner import AgentRunner, AgentSession
from src.file_manager import FileManager


def _patch_payload(*pairs: str) -> str:
    out: list = []
    for i in range(0, len(pairs), 2):
        s, r = pairs[i], pairs[i + 1]
        out.append("<<<<<<< SEARCH")
        out.append(s)
        out.append("=======")
        out.append(r)
        out.append(">>>>>>> REPLACE")
    return "\n".join(out)


def _make_runner(workspace: Path) -> AgentRunner:
    """실제 FileManager 를 사용하는 (다른 의존성은 Mock 으로 채운) AgentRunner."""
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"

    fm = FileManager(str(workspace))

    terminal_executor = MagicMock()
    terminal_executor.DANGEROUS_COMMANDS = {"rm", "del"}
    terminal_executor.execute.return_value = {
        "success": True, "stdout": "", "returncode": 0,
    }

    code_exec = MagicMock()
    code_exec.execute.return_value = {
        "success": True, "stdout": "ok", "returncode": 0,
    }

    response_parser = MagicMock()
    response_parser.parse_and_save.side_effect = (
        lambda act_text, auto_overwrite=False: _save_via_fm(fm, act_text)
    )

    env = {
        "AGENT_MAX_ITERATIONS": "10",
        "AGENT_SELF_CORRECT_MAX": "1",
        "AGENT_COMPACT_AFTER": "5",
        "AGENT_CODE_TIMEOUT": "30",
        "AGENT_DONE_TOKEN": "[AGENT_DONE]",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("src.agent_runner.CodeExecutor"):
            runner = AgentRunner(
                assistant=assistant,
                file_manager=fm,
                code_executor=code_exec,
                terminal_executor=terminal_executor,
                response_parser=response_parser,
                cli_handler=MagicMock(),
                context_builder=None,
                streaming=False,
                assistant_role="model",
            )
    runner.code_executor = code_exec
    runner.terminal_executor = terminal_executor
    return runner


def _save_via_fm(fm: FileManager, act_text: str):
    """간이 filename 블록 저장기 — 테스트용."""
    import re
    saved = []
    pattern = re.compile(
        r"@@@filename:([^\n]+)\n(.*?)\n@@@", re.DOTALL,
    )
    for m in pattern.finditer(act_text):
        rel = m.group(1).strip()
        body = m.group(2)
        target = fm.workspace_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(body)
        saved.append(rel)
    return saved


class TestDispatcherPatch(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dispatch_patch_")
        self.workspace = Path(self.tmp)
        self.runner = _make_runner(self.workspace)
        self.dispatcher: AgentActionDispatcher = self.runner._dispatcher
        self.session = AgentSession(goal="test")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed(self, rel: str, content: str) -> Path:
        p = self.workspace / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return p

    def _read(self, rel: str) -> str:
        with open(self.workspace / rel, "r", encoding="utf-8", newline="") as f:
            return f.read()

    # ─── T-111-30 ──────────────────────────────────────────
    def test_T111_30_patch_fence_parsed(self):
        act = (
            "@@@patch:src/x.py\n"
            "<<<<<<< SEARCH\n"
            "foo\n"
            "=======\n"
            "bar\n"
            ">>>>>>> REPLACE\n"
            "@@@\n"
        )
        actions = self.dispatcher._parse(act)
        kinds = [a.kind for a in actions]
        self.assertIn("patch", kinds)
        patch_a = next(a for a in actions if a.kind == "patch")
        self.assertEqual(patch_a.filepath, "src/x.py")

    # ─── T-111-31 ──────────────────────────────────────────
    def test_T111_31_patch_path_missing(self):
        # patch: 만 있고 path 누락 — dispatcher 가 처리
        act = (
            "@@@patch:\n"
            "<<<<<<< SEARCH\n"
            "foo\n"
            "=======\n"
            "bar\n"
            ">>>>>>> REPLACE\n"
            "@@@\n"
        )
        results = self.dispatcher.dispatch(self.session, act)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("path 미지정", results[0].detail)

    # ─── T-111-32 ──────────────────────────────────────────
    def test_T111_32_filename_wins_over_patch(self):
        """FR-111-25 — 같은 파일에 filename + patch → filename 우선, patch 는 보고만."""
        self._seed("a.txt", "foo\n")
        act = (
            "@@@filename:a.txt\n"
            "WHOLE_FILE_CONTENT\n"
            "@@@\n"
            "@@@patch:a.txt\n"
            "<<<<<<< SEARCH\n"
            "foo\n"
            "=======\n"
            "bar\n"
            ">>>>>>> REPLACE\n"
            "@@@\n"
        )
        self.session.bypass_approvals = True
        results = self.dispatcher.dispatch(self.session, act)
        # 첫 결과 = file 액션 (filename), 두 번째 = patch 보고
        self.assertTrue(any(
            r.target == "a.txt" and r.success for r in results
        ))
        skipped = [r for r in results if not r.success]
        self.assertTrue(any(
            "filename 블록이 우선" in (r.detail or "") for r in skipped
        ))
        # 파일 내용은 filename 의 전문으로 덮어쓰임
        self.assertEqual(self._read("a.txt"), "WHOLE_FILE_CONTENT")

    # ─── T-111-33 ──────────────────────────────────────────
    def test_T111_33_patch_plus_python_both_run(self):
        self._seed("a.txt", "foo\n")
        act = (
            "@@@patch:a.txt\n"
            "<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE\n"
            "@@@\n"
            "```python\n"
            "print('hello')\n"
            "```\n"
        )
        self.session.bypass_approvals = True
        results = self.dispatcher.dispatch(self.session, act)
        kinds = [r.kind for r in results]
        self.assertIn("file", kinds)
        self.assertIn("code", kinds)

    # ─── T-111-34 ──────────────────────────────────────────
    def test_T111_34_bypass_approvals_no_prompt(self):
        self._seed("a.txt", "foo\n")
        act = "@@@patch:a.txt\n<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE\n@@@\n"
        self.session.bypass_approvals = True
        # _approve_dangerous 는 호출되어선 안 됨 (auto_approve=True 경로)
        with patch.object(self.runner, "_approve_dangerous") as m_approve:
            results = self.dispatcher.dispatch(self.session, act)
            m_approve.assert_not_called()
        self.assertTrue(results[0].success)
        self.assertEqual(self._read("a.txt"), "bar\n")

    # ─── T-111-35 ──────────────────────────────────────────
    def test_T111_35_user_choses_always(self):
        """bypass=False, auto_approve_file_mutation=False, 사용자 'A' → flag True."""
        self._seed("a.txt", "foo\n")
        self._seed("b.txt", "alpha\n")
        act_a = "@@@patch:a.txt\n<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE\n@@@\n"
        act_b = "@@@patch:b.txt\n<<<<<<< SEARCH\nalpha\n=======\nbeta\n>>>>>>> REPLACE\n@@@\n"

        # 첫 호출은 _approve_dangerous 가 호출되며 'A' 선택 → flag 세팅 + True 반환
        def fake_approve(session, attr, _label):
            setattr(session, attr, True)
            return True

        with patch.object(self.runner, "_approve_dangerous", side_effect=fake_approve) as m:
            results_a = self.dispatcher.dispatch(self.session, act_a)
            self.assertTrue(results_a[0].success)
            self.assertTrue(self.session.auto_approve_file_mutation)
            self.assertEqual(m.call_count, 1)

            # 두 번째 패치 — flag 가 True 이므로 _approve_dangerous 미호출
            results_b = self.dispatcher.dispatch(self.session, act_b)
            self.assertTrue(results_b[0].success)
            self.assertEqual(m.call_count, 1)  # 증가 없음

    # ─── T-111-36 ──────────────────────────────────────────
    def test_T111_36_self_correction_trigger_with_snippet(self):
        """patch 실패가 _has_code_failure=True 를 만들고 detail 에 snippet 포함."""
        self._seed("a.txt", "alpha\nbeta\ngamma\ndelta\n")
        # SEARCH 가 매칭되지 않음
        act = (
            "@@@patch:a.txt\n"
            "<<<<<<< SEARCH\nzeta\n=======\nx\n>>>>>>> REPLACE\n"
            "@@@\n"
        )
        self.session.bypass_approvals = True
        results = self.dispatcher.dispatch(self.session, act)
        self.assertFalse(results[0].success)
        # FR-111-22
        self.assertTrue(AgentRunner._has_code_failure(results))
        # FR-111-23 — snippet 라인 번호 포함
        self.assertIn("L", results[0].detail or "")
        # _format_failure 가 file 실패를 포함
        failure_text = AgentRunner._format_failure(results)
        self.assertIn("a.txt", failure_text)

    # ─── T-111-37 ──────────────────────────────────────────
    def test_T111_37_patch_not_deduped_by_filepath(self):
        """같은 path 두 번 들어와도 두 번 시도된다 (file 과 동일 정책)."""
        self._seed("a.txt", "alpha\nbravo\n")
        act = (
            "@@@patch:a.txt\n<<<<<<< SEARCH\nalpha\n=======\nALPHA\n>>>>>>> REPLACE\n@@@\n"
            "@@@patch:a.txt\n<<<<<<< SEARCH\nbravo\n=======\nBRAVO\n>>>>>>> REPLACE\n@@@\n"
        )
        self.session.bypass_approvals = True
        results = self.dispatcher.dispatch(self.session, act)
        # 두 번 모두 라우팅 (kind=file 의 ActionResult 두 건)
        self.assertEqual(len([r for r in results if r.kind == "file"]), 2)
        # 두 패치 모두 적용됨
        self.assertEqual(self._read("a.txt"), "ALPHA\nBRAVO\n")

    # ─── T-111-38 ──────────────────────────────────────────
    def test_T111_38_action_result_kind_is_file(self):
        self._seed("a.txt", "foo\n")
        act = "@@@patch:a.txt\n<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE\n@@@\n"
        self.session.bypass_approvals = True
        results = self.dispatcher.dispatch(self.session, act)
        self.assertEqual(results[0].kind, "file")

    # ─── T-111-39 ──────────────────────────────────────────
    def test_T111_39_empty_patch_body(self):
        # 마커가 전혀 없는 빈 본문
        act = "@@@patch:a.txt\n\n@@@\n"
        self.session.bypass_approvals = True
        results = self.dispatcher.dispatch(self.session, act)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("빈 본문", results[0].detail)


if __name__ == "__main__":
    unittest.main()
