"""
FSD v1.0.088 / v1.0.107 테스트: os_utils.get_os_shell_hint() 및 AgentRunner._build_system_prompt() 검증

T-088-01 ~ T-088-10  (v1.0.088 호환)
T-107-01 ~ T-107-06  (v1.0.107 프롬프트 구성)
T-107-29 ~ T-107-32  (v1.0.107 4-쉘 분기)
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.os_utils import get_os_shell_hint
from src.agent_runner import AgentRunner

# 공통 패치 경로: TerminalExecutor.get_shell_type 는 정적 메서드.
# os_utils 와 agent_runner 둘 다 TerminalExecutor 를 내부 import 하므로
# 원본 클래스의 정적 메서드를 패치하면 양쪽 모두 영향을 받는다.
_SHELL_TYPE_PATCH = "src.terminal_executor.TerminalExecutor.get_shell_type"


def _make_runner() -> AgentRunner:
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"
    file_manager = MagicMock()
    file_manager.workspace_dir = Path(".")
    with patch("src.agent_runner.CodeExecutor"):
        return AgentRunner(
            assistant=assistant,
            file_manager=file_manager,
            code_executor=MagicMock(),
            terminal_executor=MagicMock(),
            response_parser=MagicMock(),
            cli_handler=MagicMock(),
        )


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


# ─── T-107-01 ~ T-107-06: 프롬프트 구성 ─────────────────────
class TestBuildSystemPrompt107(unittest.TestCase):
    """FSD v1.0.107: _build_system_prompt() 검증."""

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_T107_01_three_choices_present(self, _m):
        """T-107-01: 프롬프트에 선택지 A/B/C 세 문자열 모두 포함."""
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("선택지 A", prompt)
        self.assertIn("선택지 B", prompt)
        self.assertIn("선택지 C", prompt)

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_T107_02_forbidden_patterns_section(self, _m):
        """T-107-02 (v1.0.115 update): 프롬프트에 ❌ 자주 하는 실수 가이드 존재.

        v1.0.111 부터 [❌ 금지 패턴] 섹션은 선택지 A-2 의 "❌ 자주 하는 실수"
        목록으로 재구성되었다.
        """
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("❌ 자주 하는 실수", prompt)

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_T107_03_shell_brief_header(self, _m):
        """T-107-03: 프롬프트에 [쉘 환경 요약 — 현재 쉘:] 헤더 포함."""
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("[쉘 환경 요약 — 현재 쉘:", prompt)

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_T107_04_windows_powershell_in_prompt(self, _m):
        """T-107-04: Windows PowerShell 환경 시 프롬프트에 'Windows PowerShell' 포함."""
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("Windows PowerShell", prompt)

    @patch(_SHELL_TYPE_PATCH, return_value="Linux")
    def test_T107_05_linux_bash_in_prompt(self, _m):
        """T-107-05: Linux 환경 시 'Linux' + 'bash' 포함."""
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("Linux", prompt)
        self.assertIn("bash", prompt)

    @patch(_SHELL_TYPE_PATCH, return_value="Linux")
    def test_T107_06_choice_B_shell_auto_routing_note(self, _m):
        """T-107-06: 선택지 B 에 쉘 태그 자동 라우팅 안내 포함."""
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        # v1.0.111: "자동으로 쉘로 라우팅" 으로 표현 변경
        self.assertIn("쉘로 라우팅", prompt)


# ─── T-088 호환: AgentRunner._build_system_prompt() ──────────
class TestAgentRunnerSystemPromptWindows(unittest.TestCase):
    """T-088-03, T-088-05: Windows 에서 _build_system_prompt() 검증."""

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_env_section_present(self, _m):
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("[실행 환경]", prompt)
        self.assertIn("Windows PowerShell", prompt)

    @patch(_SHELL_TYPE_PATCH, return_value="Windows PowerShell")
    def test_act_section_uses_powershell(self, _m):
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("powershell", prompt)


class TestAgentRunnerSystemPromptLinux(unittest.TestCase):
    """T-088-04, T-088-06: Linux 에서 _build_system_prompt() 검증."""

    @patch(_SHELL_TYPE_PATCH, return_value="Linux")
    def test_env_section_present(self, _m):
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("[실행 환경]", prompt)
        self.assertIn("Linux", prompt)

    @patch(_SHELL_TYPE_PATCH, return_value="Linux")
    def test_act_section_uses_bash(self, _m):
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("bash", prompt)


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
