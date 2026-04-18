"""
FSD v1.0.088 테스트: os_utils.get_os_shell_hint() 및 AgentRunner._build_system_prompt() OS 힌트 주입

T-088-01 ~ T-088-10
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.os_utils import get_os_shell_hint
from src.agent_runner import AgentRunner


def _make_runner() -> AgentRunner:
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"
    file_manager = MagicMock()
    file_manager.workspace_dir = Path(".")
    return AgentRunner(
        assistant=assistant,
        file_manager=file_manager,
        code_executor=MagicMock(),
        terminal_executor=MagicMock(),
        response_parser=MagicMock(),
        cli_handler=MagicMock(),
    )


class TestGetOsShellHintWindows(unittest.TestCase):
    """T-088-01: Windows 환경 반환값"""

    @patch("src.os_utils.platform.system", return_value="Windows")
    def test_windows_contains_powershell(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("Windows OS", hint)
        self.assertIn("powershell", hint)

    @patch("src.os_utils.platform.system", return_value="Windows")
    def test_windows_warns_about_bash(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("`bash`", hint)
        self.assertIn("실행되지 않습니다", hint)


class TestGetOsShellHintLinux(unittest.TestCase):
    """T-088-02: Linux 환경 반환값"""

    @patch("src.os_utils.platform.system", return_value="Linux")
    def test_linux_contains_bash(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("Linux OS", hint)
        self.assertIn("bash", hint)

    @patch("src.os_utils.platform.system", return_value="Darwin")
    def test_macos_contains_bash(self, _mock):
        hint = get_os_shell_hint()
        self.assertIn("Darwin OS", hint)
        self.assertIn("bash", hint)


class TestAgentRunnerSystemPromptWindows(unittest.TestCase):
    """T-088-03, T-088-05: Windows 에서 _build_system_prompt() 검증"""

    @patch("src.agent_runner.platform.system", return_value="Windows")
    @patch("src.agent_runner.get_os_shell_hint", return_value="[WINDOWS_HINT]")
    def test_env_section_present(self, _mock_hint, _mock_platform):
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("[실행 환경]", prompt)
        self.assertIn("[WINDOWS_HINT]", prompt)

    @patch("src.agent_runner.platform.system", return_value="Windows")
    @patch("src.agent_runner.get_os_shell_hint", return_value="[WINDOWS_HINT]")
    def test_act_section_uses_powershell(self, _mock_hint, _mock_platform):
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("powershell", prompt)
        self.assertNotIn("```bash", prompt)


class TestAgentRunnerSystemPromptLinux(unittest.TestCase):
    """T-088-04, T-088-06: Linux 에서 _build_system_prompt() 검증"""

    @patch("src.agent_runner.platform.system", return_value="Linux")
    @patch("src.agent_runner.get_os_shell_hint", return_value="[LINUX_HINT]")
    def test_env_section_present(self, _mock_hint, _mock_platform):
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("[실행 환경]", prompt)
        self.assertIn("[LINUX_HINT]", prompt)

    @patch("src.agent_runner.platform.system", return_value="Linux")
    @patch("src.agent_runner.get_os_shell_hint", return_value="[LINUX_HINT]")
    def test_act_section_uses_bash(self, _mock_hint, _mock_platform):
        runner = _make_runner()
        prompt = runner._build_system_prompt()
        self.assertIn("```bash", prompt)
        self.assertNotIn("powershell", prompt)


class TestAssistantImportAlias(unittest.TestCase):
    """T-088-07~09: 세 어시스턴트 파일이 _get_os_shell_hint 를 os_utils 에서 임포트"""

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
    """T-088-10: os_utils 독립 import"""

    def test_standalone_import(self):
        from src.os_utils import get_os_shell_hint as fn
        self.assertTrue(callable(fn))
        result = fn()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main()
