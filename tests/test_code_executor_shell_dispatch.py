"""
T-110-20 ~ T-110-26 — CodeExecutor 4-쉘 언어 매핑 테스트
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.code_executor import CodeExecutor
from src.terminal_executor import TerminalExecutor


def _executor(shell_type: str) -> CodeExecutor:
    """지정된 쉘 타입으로 CodeExecutor 생성."""
    import tempfile
    with patch.object(TerminalExecutor, "get_shell_type", return_value=shell_type):
        return CodeExecutor(Path(tempfile.mkdtemp()))


class TestShellLangConfig(unittest.TestCase):
    """CodeExecutor._shell_lang_config() 단위 테스트 (T-110-20 ~ T-110-23)"""

    # T-110-20
    def test_powershell_cmd(self):
        cfg = CodeExecutor._shell_lang_config("Windows PowerShell")
        self.assertEqual(cfg["cmd"], "powershell.exe")
        self.assertEqual(cfg["ext"], ".ps1")

    # T-110-21
    def test_cmd_ext(self):
        cfg = CodeExecutor._shell_lang_config("Windows CMD")
        self.assertEqual(cfg["ext"], ".bat")
        self.assertEqual(cfg["cmd"], "cmd.exe")

    # T-110-22
    def test_linux_cmd(self):
        cfg = CodeExecutor._shell_lang_config("Linux")
        self.assertEqual(cfg["cmd"], "/bin/bash")

    # T-110-23
    def test_mac_cmd(self):
        cfg = CodeExecutor._shell_lang_config("Mac")
        self.assertEqual(cfg["cmd"], "/bin/bash")


class TestBuildSupportedLanguages(unittest.TestCase):
    """CodeExecutor._build_supported_languages() 테스트 (T-110-24)"""

    # T-110-24
    def test_powershell_all_shell_keys_point_to_powershell(self):
        langs = CodeExecutor._build_supported_languages("Windows PowerShell")
        for key in ("bash", "sh", "shell", "powershell", "ps1"):
            with self.subTest(key=key):
                self.assertEqual(langs[key]["cmd"], "powershell.exe")
                self.assertEqual(langs[key]["ext"], ".ps1")

    def test_native_languages_always_present(self):
        for shell_type in ("Windows PowerShell", "Windows CMD", "Linux", "Mac"):
            langs = CodeExecutor._build_supported_languages(shell_type)
            for key in ("python", "py", "javascript", "js"):
                with self.subTest(shell=shell_type, key=key):
                    self.assertIn(key, langs)

    # FR-110-13 — 네이티브 언어는 모든 환경에서 동일
    def test_native_languages_identical_across_shells(self):
        langs_ps = CodeExecutor._build_supported_languages("Windows PowerShell")
        langs_linux = CodeExecutor._build_supported_languages("Linux")
        for key in ("python", "py", "javascript", "js"):
            with self.subTest(key=key):
                self.assertEqual(langs_ps[key], langs_linux[key])

    def test_cmd_shell_keys_point_to_cmd(self):
        langs = CodeExecutor._build_supported_languages("Windows CMD")
        for key in ("bash", "sh", "shell", "powershell", "ps1"):
            with self.subTest(key=key):
                self.assertEqual(langs[key]["cmd"], "cmd.exe")
                self.assertEqual(langs[key]["ext"], ".bat")

    def test_linux_shell_keys_point_to_bash(self):
        langs = CodeExecutor._build_supported_languages("Linux")
        for key in ("bash", "sh", "shell"):
            with self.subTest(key=key):
                self.assertEqual(langs[key]["cmd"], "/bin/bash")


class TestWrapCodeForShell(unittest.TestCase):
    """_wrap_code_for_shell .bat 헤더 테스트"""

    def test_bat_header_inserted(self):
        from src.code_executor import _wrap_code_for_shell
        cfg = {"ext": ".bat"}
        result = _wrap_code_for_shell("echo hello", cfg)
        self.assertIn("@chcp 65001", result)
        self.assertIn("@echo off", result)
        self.assertIn("echo hello", result)

    def test_bat_no_bom(self):
        from src.code_executor import _wrap_code_for_shell
        cfg = {"ext": ".bat"}
        result = _wrap_code_for_shell("echo hi", cfg)
        self.assertFalse(result.startswith("﻿"))

    def test_ps1_preamble_inserted(self):
        from src.code_executor import _wrap_code_for_shell, PS_UTF8_PREAMBLE
        cfg = {"ext": ".ps1"}
        result = _wrap_code_for_shell("Write-Host 'hi'", cfg)
        self.assertTrue(result.startswith(PS_UTF8_PREAMBLE))

    def test_other_lang_unchanged(self):
        from src.code_executor import _wrap_code_for_shell
        cfg = {"ext": ".py"}
        code = "print('hello')"
        self.assertEqual(_wrap_code_for_shell(code, cfg), code)


class TestCodeExecutorInit(unittest.TestCase):
    """CodeExecutor.__init__ 이 get_shell_type() 을 사용하는지 검증"""

    def test_shell_type_stored(self):
        executor = _executor("Linux")
        self.assertEqual(executor.shell_type, "Linux")

    def test_powershell_executor_has_ps1_ext(self):
        executor = _executor("Windows PowerShell")
        self.assertEqual(executor.SUPPORTED_LANGUAGES["bash"]["ext"], ".ps1")

    def test_cmd_executor_has_bat_ext(self):
        executor = _executor("Windows CMD")
        self.assertEqual(executor.SUPPORTED_LANGUAGES["bash"]["ext"], ".bat")

    # T-110-25 — Windows PS 에서 한글 출력 (실제 실행, PS 환경에서만 의미 있음)
    @unittest.skipUnless(
        TerminalExecutor.get_shell_type() == "Windows PowerShell",
        "Windows PowerShell 환경에서만 실행"
    )
    def test_powershell_korean_output(self):
        executor = _executor("Windows PowerShell")
        result = executor.execute("Write-Host '한글🚀'", "powershell")
        self.assertTrue(result["success"], result.get("stderr", ""))
        self.assertIn("한글", result["stdout"])

    # T-110-26 — Windows CMD 에서 .bat 경로 사용 (CMD 환경에서만 의미 있음)
    @unittest.skipUnless(
        TerminalExecutor.get_shell_type() == "Windows CMD",
        "Windows CMD 환경에서만 실행"
    )
    def test_cmd_bat_korean_echo(self):
        executor = _executor("Windows CMD")
        result = executor.execute("echo 한글", "bash")
        self.assertTrue(result["success"], result.get("stderr", ""))
        self.assertIn("한글", result["stdout"])


if __name__ == "__main__":
    unittest.main()
