"""
TerminalExecutor Unit Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.terminal_executor import TerminalExecutor


class TestTerminalExecutor(unittest.TestCase):
    """TerminalExecutor 클래스 테스트"""

    def setUp(self):
        """테스트 환경 설정"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.executor = TerminalExecutor(self.temp_dir, timeout=10)
        self.shell_type = TerminalExecutor.get_shell_type()

    def tearDown(self):
        """테스트 환경 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── get_shell_type ────────────────────────────────────────────────────────

    def test_get_shell_type_returns_valid_value(self):
        """get_shell_type 반환 값이 지정된 네 가지 중 하나여야 함"""
        valid = {'Windows PowerShell', 'Windows CMD', 'Linux', 'Mac'}
        self.assertIn(self.shell_type, valid)

    def test_get_shell_type_consistent(self):
        """같은 환경에서 두 번 호출해도 동일한 값 반환"""
        self.assertEqual(TerminalExecutor.get_shell_type(), self.shell_type)

    # ── execute — 기본 실행 ───────────────────────────────────────────────────

    def test_execute_allowed_command(self):
        """echo 명령어 실행 — 모든 환경에서 성공해야 함"""
        result = self.executor.execute("echo hello")

        self.assertTrue(result['success'])
        self.assertIn('hello', result['stdout'])

    def test_execute_additional_allowed_commands(self):
        """whoami, hostname 실행 — 모든 환경에서 성공해야 함"""
        for cmd in ('whoami', 'hostname'):
            result = self.executor.execute(cmd)
            self.assertTrue(result['success'], f"{cmd} 실패: {result.get('error')}")

    def test_execute_unknown_command_allowed(self):
        """알 수 없는 명령어는 차단하지 않고 실행 시도해야 함 (위험 명령어 아님)"""
        result = self.executor.execute("unknowncommand123")

        # 위험 명령어 차단 메시지가 없어야 함 (실행 시도 후 OS 에러는 허용)
        self.assertNotIn('위험 명령어', result.get('error', ''))

    def test_execute_empty_command(self):
        """빈 명령어는 에러 반환"""
        result = self.executor.execute("")

        self.assertFalse(result['success'])
        self.assertIn('비어있습니다', result['error'])

    # ── execute — 위험 명령어 차단 ───────────────────────────────────────────

    def test_execute_dangerous_command_blocked(self):
        """현재 환경에 맞는 위험 명령어가 안전 모드에서 차단되어야 함"""
        if self.shell_type == 'Windows PowerShell':
            cmd = 'Remove-Item test.txt'
        elif self.shell_type == 'Windows CMD':
            cmd = 'del test.txt'
        else:  # Linux / Mac
            cmd = 'rm test.txt'

        result = self.executor.execute(cmd)

        self.assertFalse(result['success'])
        self.assertIn('위험 명령어', result['error'])

    def test_execute_dangerous_command_with_unsafe(self):
        """allow_unsafe=True 시 위험 명령어도 실행 시도"""
        result = self.executor.execute("echo safe_test", allow_unsafe=True)

        self.assertTrue(result['success'])

    def test_dangerous_commands_not_in_safe_mode(self):
        """현재 환경의 DANGEROUS_COMMANDS 목록은 모두 안전 모드에서 차단되어야 함"""
        for cmd in self.executor.DANGEROUS_COMMANDS:
            result = self.executor.execute(cmd)
            is_blocked = not result['success'] and '위험 명령어' in result.get('error', '')
            self.assertTrue(is_blocked, f"'{cmd}' 가 차단되지 않았습니다.")

    # ── DANGEROUS_COMMANDS 환경별 검증 ──────────────────────────────────────

    def test_dangerous_commands_windows_powershell(self):
        """Windows PowerShell 위험 명령어 목록에 핵심 항목 포함 여부"""
        dangerous = TerminalExecutor._DANGEROUS_WINDOWS_POWERSHELL
        for expected in ('remove-item', 'invoke-expression', 'stop-process', 'set-content'):
            self.assertIn(expected, dangerous)

    def test_dangerous_commands_windows_cmd(self):
        """Windows CMD 위험 명령어 목록에 핵심 항목 포함 여부"""
        dangerous = TerminalExecutor._DANGEROUS_WINDOWS_CMD
        for expected in ('del', 'rmdir', 'format', 'taskkill', 'shutdown'):
            self.assertIn(expected, dangerous)

    def test_dangerous_commands_linux(self):
        """Linux 위험 명령어 목록에 핵심 항목 포함 여부"""
        dangerous = TerminalExecutor._DANGEROUS_LINUX
        for expected in ('rm', 'chmod', 'kill', 'shutdown', 'sudo'):
            self.assertIn(expected, dangerous)

    def test_dangerous_commands_mac(self):
        """Mac 위험 명령어 목록에 핵심 항목 포함 여부"""
        dangerous = TerminalExecutor._DANGEROUS_MAC
        for expected in ('rm', 'chmod', 'diskutil', 'launchctl', 'sudo'):
            self.assertIn(expected, dangerous)

    # ── get_dangerous_commands ────────────────────────────────────────────────

    def test_get_dangerous_commands_returns_string(self):
        """get_dangerous_commands 는 위험 명령어 목록을 문자열로 반환"""
        result = self.executor.get_dangerous_commands()

        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_get_dangerous_commands_contains_env_specific(self):
        """get_dangerous_commands 반환값에 현재 환경의 핵심 위험 명령어 포함"""
        result = self.executor.get_dangerous_commands()

        if self.shell_type == 'Windows PowerShell':
            self.assertIn('remove-item', result)
        elif self.shell_type == 'Windows CMD':
            self.assertIn('del', result)
        elif self.shell_type == 'Mac':
            self.assertIn('diskutil', result)
        else:  # Linux
            self.assertIn('rm', result)

    # ── shell_help ───────────────────────────────────────────────────────────

    def test_shell_help_contains_shell_type(self):
        """shell_help 출력에 현재 환경 이름이 포함되어야 함"""
        help_text = TerminalExecutor.shell_help()

        if self.shell_type == 'Windows PowerShell':
            self.assertIn('PowerShell', help_text)
        elif self.shell_type == 'Windows CMD':
            self.assertIn('CMD', help_text)
        elif self.shell_type == 'Mac':
            self.assertIn('macOS', help_text)
        else:
            self.assertIn('Linux', help_text)

    def test_shell_help_contains_dangerous_section(self):
        """shell_help 출력에 위험 명령어 섹션이 포함되어야 함"""
        help_text = TerminalExecutor.shell_help()
        self.assertIn('위험 명령어', help_text)


if __name__ == '__main__':
    unittest.main()
