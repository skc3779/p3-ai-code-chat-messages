"""
AgentActionDispatcher Unit Tests (FSD v1.0.107)

T-107-07 ~ T-107-23: 디스패처 분기 / 중복 제거 / 위험 명령 / ACTION 태그
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_action_dispatcher import AgentActionDispatcher, _ParsedAction
from src.agent_runner import (
    AgentRunner,
    AgentSession,
    AgentStopReason,
    ActionResult,
    _BypassAbort,
)


# ─── 헬퍼 ────────────────────────────────────────────────────
def _make_dispatcher(**env_overrides) -> AgentActionDispatcher:
    """Mock 으로 구성된 AgentRunner 에 연결된 디스패처 생성."""
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"

    file_manager = MagicMock()
    file_manager.workspace_dir = Path("/tmp/test_workspace")

    terminal_executor = MagicMock()
    terminal_executor.DANGEROUS_COMMANDS = {
        "rm", "del", "move", "mv", "remove-item", "rmdir",
    }
    terminal_executor.execute.return_value = {
        "success": True, "stdout": "ok", "returncode": 0,
    }

    code_executor_mock = MagicMock()
    code_executor_mock.execute.return_value = {
        "success": True, "stdout": "hello", "returncode": 0,
    }

    response_parser = MagicMock()
    response_parser.parse_and_save.return_value = []

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
                code_executor=code_executor_mock,
                terminal_executor=terminal_executor,
                response_parser=response_parser,
                cli_handler=MagicMock(),
                context_builder=None,
                streaming=True,
                assistant_role="model",
            )

    runner.assistant = assistant
    runner.code_executor = code_executor_mock
    runner.terminal_executor = terminal_executor
    runner.response_parser = response_parser

    return runner._dispatcher


def _make_session(**kwargs) -> AgentSession:
    defaults = dict(goal="test", auto_approve_dangerous_shell=True)
    defaults.update(kwargs)
    return AgentSession(**defaults)


# ─── T-107-07 ~ T-107-23: 디스패처 분기 ─────────────────────
class TestDispatcherBasic(unittest.TestCase):
    """기본 라우팅 검증."""

    def setUp(self):
        self.d = _make_dispatcher()
        self.session = _make_session()

    def test_T107_07_single_shell_line(self):
        """T-107-07: 단독 $ 라인 → shell 1건."""
        results = self.d.dispatch(self.session, "$ git status")
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(shells), 1)
        self.assertEqual(shells[0].target, "git status")

    def test_T107_08_single_python_block(self):
        """T-107-08: 단독 python 블록 → code 1건."""
        act = '```python\nprint("hi")\n```'
        results = self.d.dispatch(self.session, act)
        codes = [r for r in results if r.kind == "code"]
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0].target, "python")

    def test_T107_09_single_filename_block(self):
        """T-107-09: 단독 filename 블록 → file 1건, code 0건."""
        act = "@@@filename:a.py\ndef foo(): pass\n@@@"
        self.d._runner.response_parser.parse_and_save.return_value = ["a.py"]
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        self.assertEqual(len(files), 1)
        self.assertEqual(len(codes), 0)

    def test_T107_10_failure_pattern_A_shell_in_powershell_block(self):
        """T-107-10: 실패 패턴 A — powershell 블록의 $ 라인 → shell 라우팅."""
        act = "```powershell\n$ git status\n$ git log\n```"
        results = self.d.dispatch(self.session, act)
        shells = [r for r in results if r.kind == "shell"]
        codes = [r for r in results if r.kind == "code"]
        self.assertEqual(len(shells), 2)
        self.assertEqual(len(codes), 0)
        targets = {s.target for s in shells}
        self.assertIn("git status", targets)
        self.assertIn("git log", targets)

    def test_T107_11_failure_pattern_B_dollar_python(self):
        """T-107-11: $ python -c '...' → shell 1건."""
        act = '$ python -c "print(\'x\')"'
        results = self.d.dispatch(self.session, act)
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(shells), 1)

    def test_T107_12_failure_pattern_C_mixed_routes(self):
        """T-107-12: python + $ 라인 + file 블록 → 3건."""
        act = (
            '```python\nprint("step1")\n```\n\n'
            '$ echo step2\n\n'
            '@@@filename:src/foo.py\ndef foo(): ...\n@@@'
        )
        self.d._runner.response_parser.parse_and_save.return_value = ["src/foo.py"]
        results = self.d.dispatch(self.session, act)
        kinds = [r.kind for r in results]
        self.assertIn("code", kinds)
        self.assertIn("shell", kinds)
        self.assertIn("file", kinds)
        self.assertGreaterEqual(len(results), 3)


    def test_T107_13_multi_filename_block(self):
        """T-107-13: 멀티 filename 블록 → file 2건, code 0건, shell 0건."""
        act = """
File 1:
@@@filename:file1.py
code1
@@@

File 2:
@@@filename:src/file2.js
code2
@@@
"""
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(files), 2)
        self.assertEqual(len(codes), 0)
        self.assertEqual(len(shells), 0)

    def test_T107_14_multi_code_block(self):
        """T-107-14: 멀티 code 블록 → file 0건, code 2건, shell 0건."""
        act = """
# code1
```javascript
let x = 1;
console.log(x);
```

# code2
```python
print("hello")
```
"""
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(files), 0)
        self.assertEqual(len(codes), 2)
        self.assertEqual(len(shells), 0)

    def test_T107_14_multi_shell_block(self):
        """T-107-14: 멀티 shell 블록 → file 0건, code 0건, shell 2건."""
        act = """
# shell1
$ Write-Host "hello1"

# shell2
$ Write-Host "hello2"
"""
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(files), 0)
        self.assertEqual(len(codes), 0)
        self.assertEqual(len(shells), 2)

    def test_T107_15_filename_code_shell_block(self):
        """T-107-15: file, code, shell 블록 → file 1건, code 1건, shell 1건."""
        act = """
# file1
@@@filename:file1.md
## introduce
- number1
- number2
@@@

# code2
```python
print("hello")
```

# shell3
$ Write-Host "hello2"
"""
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(files), 1)
        self.assertEqual(len(codes), 1)
        self.assertEqual(len(shells), 1)

    def test_T107_16_nested_code_shell_in_filename_block(self):
        """T-107-16:복잡한 file 마크다운(code+shell) → file 1건, code 0건, shell 0건."""
        act = """
# file1
@@@filename:file1.md

## introduce
- number1
- number2

# code2-1
```python
print("hello")
```

# code2-2
```javascript
console.log("hello");
```

# shell3
$ Write-Host "hello2"

```

"""
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(files), 1)
        self.assertEqual(len(codes), 0)
        self.assertEqual(len(shells), 0)


    def test_T107_16_nested_not_code_shell_in_filename_block(self):
        """T-107-16:복잡한 file 마크다운(not code+shell) → file 1건, code 0건, shell 0건."""
        act = """
# file1
@@@filename:file1.py

## introduce
- number1
- number2

```sql
SELECT * FROM table;
```

```tree
root
└── child1
    └── child2
```

@@@
"""
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(files), 1)
        self.assertEqual(len(codes), 0)
        self.assertEqual(len(shells), 0)

    def test_T107_16_nested_not_code_shell_in_multi_filename_block(self):
        """T-107-16:복잡한 멀티 file 마크다운(not code+shell) → file 2건, code 0건, shell 0건."""
        act = """
# file1
@@@filename:file1.py

## introduce1
- number1
- number2

```sql
SELECT * FROM table1;
```

```tree
root
└── child1
    └── child2
```

@@@

# file2
@@@filename:file2.py

## introduce2
- number1
- number2

```sql
SELECT * FROM table2;
```

```tree
root
└── child1
    └── child2
```

@@@
"""
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(files), 2)
        self.assertEqual(len(codes), 0)
        self.assertEqual(len(shells), 0)

    def test_T107_17_mixed_filename_code_shell_block(self):
        """T-107-17:복잡 file 마크다운(code+shell) + code + shell → file 1건, code 2건, shell 1건."""
        act = """
# file1
@@@filename:file1.md

## introduce
- number1
- number2

# code2-1
```python
print("hello")
```

# code2-2
```javascript
console.log("hello");
```

# shell3
$ Write-Host "hello2"

@@@

# code2-1
```python
print("hello")
```

# code2-2
```javascript
console.log("hello");
```

# shell3
$ Write-Host "hello2"

"""
        results = self.d.dispatch(self.session, act)
        files = [r for r in results if r.kind == "file"]
        codes = [r for r in results if r.kind == "code"]
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(files), 1)
        self.assertEqual(len(codes), 2)
        self.assertEqual(len(shells), 1)


class TestDispatcherDangerous(unittest.TestCase):
    """위험 명령 검사 (G5)."""

    def setUp(self):
        self.d = _make_dispatcher()

    def test_T107_13_failure_pattern_D_dangerous_in_powershell_block(self):
        """T-107-13: powershell 블록의 Remove-Item → 위험 명령 승인 플로우."""
        session = _make_session(auto_approve_dangerous_shell=False)
        act = "```powershell\nRemove-Item -Recurse .\\build\n```"

        # _approve_dangerous 를 False 로 → 사용자 거부
        self.d._runner._approve_dangerous = MagicMock(return_value=False)
        results = self.d.dispatch(session, act)

        # 거부 시 success=False
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(shells), 1)
        self.assertFalse(shells[0].success)
        self.assertIn("거부", shells[0].detail)


class TestDispatcherDedupe(unittest.TestCase):
    """중복 제거 (FR-107-16)."""

    def setUp(self):
        self.d = _make_dispatcher()
        self.session = _make_session()

    def test_T107_14_fence_and_bare_same_cmd_dedupe(self):
        """T-107-14: 펜스 안팎 동일 cmd → 1건."""
        act = "$ ls\n```powershell\n$ ls\n```"
        results = self.d.dispatch(self.session, act)
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(shells), 1)

    def test_T107_21_triple_repeat_dedupe(self):
        """T-107-21: 같은 명령 3회 반복 → 1건."""
        act = "$ ls\n$ ls\n$ ls"
        results = self.d.dispatch(self.session, act)
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(shells), 1)


class TestDispatcherScript(unittest.TestCase):
    """다중라인 스크립트 분류 (FR-107-07)."""

    def setUp(self):
        self.d = _make_dispatcher()
        self.session = _make_session()

    def test_T107_15_multiline_powershell_script(self):
        """T-107-15: function 키워드 → script(code) 1건."""
        act = "```powershell\nfunction Foo { Get-ChildItem }\nFoo\n```"
        results = self.d.dispatch(self.session, act)
        codes = [r for r in results if r.kind == "code"]
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0].target, "powershell")

    def test_T107_16_multiline_bash_for_loop(self):
        """T-107-16: for 루프 → script(code) 1건."""
        act = "```bash\nfor f in *.py; do echo $f; done\n```"
        results = self.d.dispatch(self.session, act)
        codes = [r for r in results if r.kind == "code"]
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0].target, "bash")


class TestDispatcherActionTags(unittest.TestCase):
    """[ACTION:*] 태그 (FR-107-11, FR-107-12)."""

    def test_T107_18_tags_required_no_tag(self):
        """T-107-18: AGENT_ACTION_TAGS_REQUIRED=1 + 태그 없는 입력 → 0건 + 안내."""
        d = _make_dispatcher(AGENT_ACTION_TAGS_REQUIRED="1")
        session = _make_session()
        results = d.dispatch(session, "$ git status")
        # 태그 필수 모드: 결과가 안내 메시지 1건
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("ACTION", results[0].detail)


class TestDispatcherEmpty(unittest.TestCase):
    """빈 입력."""

    def test_T107_19_empty_act(self):
        """T-107-19: 빈 act_text → 0건."""
        d = _make_dispatcher()
        results = d.dispatch(_make_session(), "")
        self.assertEqual(len(results), 0)


class TestDispatcherMalformed(unittest.TestCase):
    """망가진 펜스."""

    def test_T107_20_unclosed_fence(self):
        """T-107-20: 마지막 ``` 누락 → 펜스 미인식, code 0건."""
        d = _make_dispatcher()
        session = _make_session()
        # 마지막 ``` 없음
        act = '```python\nprint(1)\n'
        results = d.dispatch(session, act)
        codes = [r for r in results if r.kind == "code"]
        self.assertEqual(len(codes), 0)


class TestDispatcherBypass(unittest.TestCase):
    """Bypass 모드 + 위험 명령 한도 (FR-107-10)."""

    def setUp(self):
        self.d = _make_dispatcher()

    def test_T107_22_bypass_count_increment(self):
        """T-107-22: bypass + 한도 미달 → count 증가."""
        session = _make_session(
            bypass_approvals=True,
            auto_approve_dangerous_shell=True,
        )
        session.bypass_dangerous_count = 2
        self.d._runner.bypass_max_dangerous = 5

        results = self.d.dispatch(session, "$ rm tmp")
        self.assertEqual(session.bypass_dangerous_count, 3)
        self.assertEqual(len(results), 1)

    def test_T107_23_bypass_limit_exceeded(self):
        """T-107-23: bypass + 한도 초과 → _BypassAbort."""
        session = _make_session(
            bypass_approvals=True,
            auto_approve_dangerous_shell=True,
        )
        session.bypass_dangerous_count = 5
        self.d._runner.bypass_max_dangerous = 5

        with self.assertRaises(_BypassAbort):
            self.d.dispatch(session, "$ rm tmp")


class TestDispatcherPatch(unittest.TestCase):
    """선택지 A-2 — patch: 블록 라우팅 및 FR-111-25 filename 우선 정책."""

    def setUp(self):
        self.d = _make_dispatcher()
        self.session = _make_session()

    def test_T107_24_single_patch_block_parsed(self):
        """T-107-24: patch:path 블록 → _ParsedAction(kind='patch') 1건, filepath/payload 정확."""
        act = (
            "```patch:src/foo.py\n"
            "<<<<<<< SEARCH\n"
            "old_code\n"
            "=======\n"
            "new_code\n"
            ">>>>>>> REPLACE\n"
            "```"
        )
        actions = self.d._parse(act)
        patches = [a for a in actions if a.kind == "patch"]
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0].filepath, "src/foo.py")
        self.assertIn("SEARCH", patches[0].payload)
        self.assertIn("REPLACE", patches[0].payload)

    def test_T107_25_patch_dispatch_success(self):
        """T-107-25: patch: 블록 dispatch → AgentPatchApplier 호출, file ActionResult(success=True)."""
        act = (
            "```patch:src/foo.py\n"
            "<<<<<<< SEARCH\n"
            "old_code\n"
            "=======\n"
            "new_code\n"
            ">>>>>>> REPLACE\n"
            "```"
        )
        mock_block = MagicMock()
        mock_block.status = "applied"
        mock_block.diagnostic = None

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.applied_count = 1
        mock_result.total_count = 1
        mock_result.block_results = [mock_block]
        mock_result.error = None

        with patch("src.agent_patch_applier.AgentPatchApplier") as MockCls:
            MockCls.return_value.apply.return_value = mock_result
            results = self.d.dispatch(self.session, act)

        file_results = [r for r in results if r.kind == "file"]
        self.assertEqual(len(file_results), 1)
        self.assertTrue(file_results[0].success)
        self.assertEqual(file_results[0].target, "src/foo.py")
        self.assertIn("patched 1/1", file_results[0].detail)

    def test_T107_26_patch_failure_reported_with_diagnostic(self):
        """T-107-26: patch 적용 실패 → success=False + diagnostic 포함 detail."""
        act = (
            "```patch:src/bar.py\n"
            "<<<<<<< SEARCH\n"
            "nonexistent\n"
            "=======\n"
            "replacement\n"
            ">>>>>>> REPLACE\n"
            "```"
        )
        mock_block = MagicMock()
        mock_block.status = "no_match"
        mock_block.diagnostic = "SEARCH 블록 매칭 실패"

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.applied_count = 0
        mock_result.total_count = 1
        mock_result.block_results = [mock_block]
        mock_result.error = "patch 실패"

        with patch("src.agent_patch_applier.AgentPatchApplier") as MockCls:
            MockCls.return_value.apply.return_value = mock_result
            results = self.d.dispatch(self.session, act)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("no_match", results[0].detail)
        self.assertIn("SEARCH 블록 매칭 실패", results[0].detail)

    def test_T107_27_patch_and_filename_same_file_filename_wins(self):
        """T-107-27: 동일 파일 filename + patch → filename 우선, patch 는 건너뜀 보고 (FR-111-25)."""
        act = (
            "@@@filename:src/foo.py\n"
            "def new(): pass\n"
            "@@@\n\n"
            "@@@patch:src/foo.py\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
            "@@@"
        )
        self.d._runner.response_parser.parse_and_save.return_value = ["src/foo.py"]

        results = self.d.dispatch(self.session, act)

        file_results = [r for r in results if r.kind == "file"]
        # filename 성공 1건 + patch 건너뜀(실패 보고) 1건
        self.assertEqual(len(file_results), 2)
        skipped = [r for r in file_results if not r.success and "filename" in r.detail]
        self.assertEqual(len(skipped), 1)
        saved = [r for r in file_results if r.success]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].target, "src/foo.py")

    def test_T107_28_patch_empty_path_failure(self):
        """T-107-28: patch: 경로 없음 → 'patch path 미지정' 실패."""
        act = (
            "```patch:\n"
            "<<<<<<< SEARCH\n"
            "old\n"
            "=======\n"
            "new\n"
            ">>>>>>> REPLACE\n"
            "```"
        )
        with patch("src.agent_patch_applier.AgentPatchApplier"):
            results = self.d.dispatch(self.session, act)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("미지정", results[0].detail)

    def test_T107_29_patch_multi_block_payload(self):
        """T-107-29: patch 블록 내 다중 SEARCH/REPLACE 쌍 → payload 에 두 쌍 모두 포함."""
        act = (
            "```patch:src/foo.py\n"
            "<<<<<<< SEARCH\n"
            "line_a\n"
            "=======\n"
            "line_A\n"
            ">>>>>>> REPLACE\n"
            "<<<<<<< SEARCH\n"
            "line_b\n"
            "=======\n"
            "line_B\n"
            ">>>>>>> REPLACE\n"
            "```"
        )
        actions = self.d._parse(act)
        patches = [a for a in actions if a.kind == "patch"]
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0].payload.count("SEARCH"), 2)
        self.assertEqual(patches[0].payload.count("REPLACE"), 2)


class TestDispatcherActionTagsExplicit(unittest.TestCase):
    """[ACTION:*] 명시 태그 — explicit_tag 설정 및 REQUIRED 모드 통과 (FR-107-11/12)."""

    def test_T107_30_action_shell_tag_sets_explicit_tag(self):
        """T-107-30: [ACTION:shell] 태그 포함 → action.explicit_tag=True."""
        d = _make_dispatcher()
        act = "[ACTION:shell]\n$ git status"
        actions = d._parse(act)
        shells = [a for a in actions if a.kind == "shell"]
        self.assertEqual(len(shells), 1)
        self.assertTrue(shells[0].explicit_tag)

    def test_T107_31_action_code_tag_sets_explicit_tag(self):
        """T-107-31: [ACTION:code] 태그 포함 → python 블록 explicit_tag=True."""
        d = _make_dispatcher()
        act = "[ACTION:code]\n```python\nprint('hello')\n```"
        actions = d._parse(act)
        codes = [a for a in actions if a.kind == "code"]
        self.assertEqual(len(codes), 1)
        self.assertTrue(codes[0].explicit_tag)

    def test_T107_32_action_file_tag_sets_explicit_tag(self):
        """T-107-32: [ACTION:file] 태그 포함 → filename 블록 explicit_tag=True."""
        d = _make_dispatcher()
        act = "[ACTION:file]\n@@@filename:src/foo.py\ndef bar(): pass\n@@@"
        actions = d._parse(act)
        files = [a for a in actions if a.kind == "file"]
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].explicit_tag)

    def test_T107_33_no_action_tag_explicit_tag_false(self):
        """T-107-33: [ACTION:*] 태그 없음 → explicit_tag=False (기본값)."""
        d = _make_dispatcher()
        act = "$ git status"
        actions = d._parse(act)
        self.assertTrue(all(not a.explicit_tag for a in actions))

    def test_T107_34_tags_required_with_action_tag_proceeds(self):
        """T-107-34: AGENT_ACTION_TAGS_REQUIRED=1 + [ACTION:shell] → 거부 없이 shell 실행."""
        d = _make_dispatcher(AGENT_ACTION_TAGS_REQUIRED="1")
        session = _make_session()
        act = "[ACTION:shell]\n$ git status"
        results = d.dispatch(session, act)
        # ACTION 태그 있으면 explicit_tag=True → 거부 조건 미충족 → shell 1건 실행
        shells = [r for r in results if r.kind == "shell"]
        self.assertEqual(len(shells), 1)

    def test_T107_35_tags_required_without_tag_rejected(self):
        """T-107-35: AGENT_ACTION_TAGS_REQUIRED=1 + 태그 없음 → 안내 메시지 1건 (T-107-18 보완)."""
        d = _make_dispatcher(AGENT_ACTION_TAGS_REQUIRED="1")
        session = _make_session()
        act = "$ git status"
        results = d.dispatch(session, act)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("ACTION", results[0].detail)

    def test_T107_36_action_tag_all_actions_get_explicit(self):
        """T-107-36: [ACTION:shell] + 다중 shell 라인 → 모든 action explicit_tag=True."""
        d = _make_dispatcher()
        act = "[ACTION:shell]\n$ git status\n$ git log"
        actions = d._parse(act)
        shells = [a for a in actions if a.kind == "shell"]
        self.assertEqual(len(shells), 2)
        self.assertTrue(all(a.explicit_tag for a in shells))


if __name__ == "__main__":
    unittest.main()
