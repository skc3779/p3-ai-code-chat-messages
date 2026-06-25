"""
FSD v1.0.088 테스트: os_utils.get_os_shell_hint() 검증

T-088-01 ~ T-088-10  (v1.0.088 호환)
T-107-29 ~ T-107-32  (4-쉘 분기)

(FSD v1.1.061: 기존 AgentRunner._build_system_prompt() 검증 케이스는
 /agents 삭제와 함께 제거되었고, os_utils 단독 커버리지만 유지한다.)
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.os_utils import get_os_shell_hint

# 공통 패치 경로: TerminalExecutor.get_shell_type 는 정적 메서드.
# os_utils 가 TerminalExecutor 를 내부 import 하므로
# 원본 클래스의 정적 메서드를 패치하면 영향을 받는다.
_SHELL_TYPE_PATCH = "src.terminal_executor.TerminalExecutor.get_shell_type"


# ─── T-107-29 ~ T-107-32: 4-쉘 분기 (os_utils) ─────────────
class TestGetOsShellHint107_Windows_PS(unittest.TestCase):
    """T-107-29: Windows PowerShell 환경 반환값."""

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_contains_powershell(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("Windows PowerShell", hint)
        self.assertIn("PowerShell 구문", hint)


class TestGetOsShellHint107_Windows_CMD(unittest.TestCase):
    """T-107-30: Windows CMD 환경 반환값."""

    @patch(_SHELL_TYPE_PATCH, return_value="Windows CMD")
    def test_contains_cmd(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("Windows CMD", hint)
        self.assertIn("CMD 구문", hint)


class TestGetOsShellHint107_Mac(unittest.TestCase):
    """T-107-31: macOS 환경 반환값."""

    @patch(_SHELL_TYPE_PATCH, return_value="Mac")
    def test_contains_macos(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("macOS", hint)
        self.assertIn("bash/zsh", hint)


class TestGetOsShellHint107_Linux(unittest.TestCase):
    """T-107-32: Linux 환경 반환값."""

    @patch(_SHELL_TYPE_PATCH, return_value="Linux")
    def test_contains_linux(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("Linux", hint)
        self.assertIn("bash", hint)


# ─── T-088 호환: Windows/Linux 힌트 기본 검증 ────────────────
class TestGetOsShellHintWindows(unittest.TestCase):
    """T-088-01: Windows 환경 반환값 (PowerShell 기본)."""

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_windows_contains_powershell(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("Windows", hint)
        self.assertIn("PowerShell", hint)

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_windows_warns_about_bash(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("bash", hint)
        self.assertIn("실행되지 않습니다", hint)


class TestGetOsShellHintLinux(unittest.TestCase):
    """T-088-02: Linux 환경 반환값."""

    @patch(_SHELL_TYPE_PATCH, return_value="Linux")
    def test_linux_contains_bash(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("Linux", hint)
        self.assertIn("bash", hint)

    @patch(_SHELL_TYPE_PATCH, return_value="Mac")
    def test_macos_contains_bash(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("macOS", hint)
        self.assertIn("bash", hint)


class TestAssistantImportAlias(unittest.TestCase):
    """T-088-07~09: 세 어시스턴트 파일이 _get_os_shell_hint 를 os_utils 에서 임포트."""

    def test_claude_assistant_uses_os_utils(self):
        import src.claude_assistant as m
        self.assertIs(m._get_os_shell_hint, get_os_shell_hint)

    def test_gemini_assistant_uses_os_utils(self):
        import src.gemini_assistant as m
        self.assertIs(m._get_os_shell_hint, get_os_shell_hint)

    def test_genai_assistant_uses_os_utils(self):
        import src.genai_assistant as m
        self.assertIs(m._get_os_shell_hint, get_os_shell_hint)


class TestOsUtilsStandaloneImport(unittest.TestCase):
    """T-088-10: os_utils 독립 import."""

    def test_standalone_import(self):
        from src.os_utils import get_os_shell_hint as fn
        self.assertTrue(callable(fn))
        result = fn()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main()
