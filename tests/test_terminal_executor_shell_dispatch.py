"""
T-110-10 ~ T-110-19 — TerminalExecutor 4-쉘 인터프리터 디스패치 테스트
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.terminal_executor import TerminalExecutor


class TestComposeArgv(unittest.TestCase):
    """_compose_argv() 단위 테스트"""

    # T-110-10
    def test_powershell_argv(self):
        argv, shell_flag = TerminalExecutor._compose_argv("Windows PowerShell", "Get-ChildItem")
        self.assertEqual(argv[0], "powershell.exe")
        self.assertIn("-Command", argv)
        self.assertFalse(shell_flag)

    # T-110-10 (preamble 포함 확인)
    def test_powershell_preamble_in_command(self):
        argv, _ = TerminalExecutor._compose_argv("Windows PowerShell", "Get-ChildItem")
        cmd_arg = argv[-1]
        self.assertIn("OutputEncoding", cmd_arg)
        self.assertIn("Get-ChildItem", cmd_arg)

    # T-110-11
    def test_cmd_argv(self):
        argv, shell_flag = TerminalExecutor._compose_argv("Windows CMD", "dir")
        self.assertIsInstance(argv, str)
        self.assertIn("cmd.exe /c", argv)
        self.assertIn("chcp 65001", argv)
        self.assertIn("dir", argv)
        self.assertTrue(shell_flag)

    # T-110-12
    def test_linux_argv(self):
        argv, shell_flag = TerminalExecutor._compose_argv("Linux", "ls -la")
        self.assertEqual(argv, ["/bin/bash", "-c", "ls -la"])
        self.assertFalse(shell_flag)

    # T-110-13
    def test_mac_argv(self):
        argv, shell_flag = TerminalExecutor._compose_argv("Mac", "ls -la")
        self.assertEqual(argv, ["/bin/bash", "-c", "ls -la"])
        self.assertFalse(shell_flag)


class TestBuildChildEnv(unittest.TestCase):
    """_build_child_env() 단위 테스트"""

    def setUp(self):
        import tempfile
        self.executor = TerminalExecutor(Path(tempfile.mkdtemp()))

    # T-110-17 (부모 오염 없음)
    def test_returns_copy_not_mutating_parent(self):
        original_keys = set(os.environ.keys())
        env = self.executor._build_child_env()
        self.assertEqual(set(os.environ.keys()), original_keys)

    # FR-110-14
    def test_contains_pythonioencoding(self):
        env = self.executor._build_child_env()
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env["PYTHONUTF8"], "1")

    # FR-110-15
    def test_preserves_existing_lc_all(self):
        with patch.dict(os.environ, {"LC_ALL": "en_US.UTF-8"}):
            env = self.executor._build_child_env()
        self.assertEqual(env["LC_ALL"], "en_US.UTF-8")

    def test_sets_lc_all_if_unset(self):
        stripped = {k: v for k, v in os.environ.items() if k not in ("LC_ALL", "LANG")}
        with patch.dict(os.environ, stripped, clear=True):
            child_env = self.executor._build_child_env()
            self.assertEqual(child_env["LC_ALL"], "C.UTF-8")


class TestExecuteShellDispatch(unittest.TestCase):
    """execute() 가 쉘 타입별로 올바른 argv 로 subprocess.run 을 호출하는지 검증"""

    def setUp(self):
        import tempfile
        self.executor = TerminalExecutor(Path(tempfile.mkdtemp()))

    def _run_with_shell(self, shell_type: str, command: str):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok"
        mock_result.stderr = ""

        with patch.object(TerminalExecutor, "get_shell_type", return_value=shell_type), \
             patch("src.terminal_executor.subprocess.run", return_value=mock_result) as mock_run:
            self.executor.execute(command, allow_unsafe=True)
            return mock_run.call_args

    # T-110-10
    def test_dispatch_powershell(self):
        call = self._run_with_shell("Windows PowerShell", "Get-ChildItem")
        argv = call[0][0]
        shell_flag = call[1]["shell"]
        self.assertEqual(argv[0], "powershell.exe")
        self.assertIn("-Command", argv)
        self.assertFalse(shell_flag)

    # T-110-11
    def test_dispatch_cmd(self):
        call = self._run_with_shell("Windows CMD", "dir")
        argv = call[0][0]
        shell_flag = call[1]["shell"]
        self.assertIsInstance(argv, str)
        self.assertIn("cmd.exe /c", argv)
        self.assertTrue(shell_flag)

    # T-110-12
    def test_dispatch_linux(self):
        call = self._run_with_shell("Linux", "ls -la")
        argv = call[0][0]
        shell_flag = call[1]["shell"]
        self.assertEqual(argv, ["/bin/bash", "-c", "ls -la"])
        self.assertFalse(shell_flag)

    # T-110-13
    def test_dispatch_mac(self):
        call = self._run_with_shell("Mac", "ls -la")
        argv = call[0][0]
        self.assertEqual(argv, ["/bin/bash", "-c", "ls -la"])

    # T-110-14 — 위험 명령 차단 (인터프리터 진입 전)
    def test_dangerous_command_blocked_before_interpreter(self):
        import tempfile
        # Linux DANGEROUS_COMMANDS 로 executor 를 초기화해야 rm 이 차단됨
        with patch.object(TerminalExecutor, "get_shell_type", return_value="Linux"):
            linux_executor = TerminalExecutor(Path(tempfile.mkdtemp()))
        with patch("src.terminal_executor.subprocess.run") as mock_run:
            result = linux_executor.execute("rm -rf /tmp/x", allow_unsafe=False)
        self.assertFalse(result["success"])
        self.assertIn("위험 명령어", result["error"])
        mock_run.assert_not_called()

    # T-110-15 — allow_unsafe=True 시 인터프리터 경로 진입
    def test_allow_unsafe_reaches_interpreter(self):
        mock_result = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch.object(TerminalExecutor, "get_shell_type", return_value="Linux"), \
             patch("src.terminal_executor.subprocess.run", return_value=mock_result) as mock_run:
            self.executor.execute("rm test.txt", allow_unsafe=True)
        mock_run.assert_called_once()

    # T-110-18 — 빈 명령
    def test_empty_command(self):
        result = self.executor.execute("")
        self.assertFalse(result["success"])
        self.assertIn("비어있습니다", result["error"])

    # T-110-19 — 알 수 없는 명령 (OS 에러 반환)
    def test_unknown_command_not_blocked(self):
        result = self.executor.execute("unknowncommand123abc")
        self.assertNotIn("위험 명령어", result.get("error", ""))


if __name__ == "__main__":
    unittest.main()
