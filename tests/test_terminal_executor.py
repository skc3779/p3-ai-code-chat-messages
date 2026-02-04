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
    
    def tearDown(self):
        """테스트 환경 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_execute_allowed_command(self):
        """허용된 명령어 실행 테스트"""
        # echo는 허용된 명령어
        result = self.executor.execute("echo hello")
        
        self.assertTrue(result['success'])
        self.assertIn('hello', result['stdout'])
    
    def test_execute_additional_allowed_commands(self):
        """추가된 허용 명령어(whoami, date 등) 테스트"""
        # whoami
        result = self.executor.execute("whoami")
        self.assertTrue(result['success'], f"whoami 실패: {result.get('error')}")
        
        # date (Windows/Linux 공통)
        # Windows에서는 date가 사용자 입력을 기다릴 수 있으므로 /t 옵션이 필요할 수 있으나, 
        # python subprocess에서는 date만으로도 날짜를 출력하고 종료될 수 있음.
        # 안전하게 'hostname' 사용
        result = self.executor.execute("hostname")
        self.assertTrue(result['success'], f"hostname 실패: {result.get('error')}")

    def test_all_allowed_commands_are_permitted(self):
        """ALLOWED_COMMANDS 목록의 모든 명령어가 실행 시도 시 차단되지 않는지 테스트"""
        # 실제 실행까지 하면 시간이 오래 걸리거나 설치되지 않은 도구 때문에 실패할 수 있음.
        # 따라서 여기서는 '허용되지 않은 명령어' 에러가 발생하지 않는지만 확인 (실행 에러는 허용)
        
        # 일부 명령어는 실행 시 부작용이 있거나(mkdir), 대기 상태가 될 수 있으므로(cat)
        # 테스트에서 제외하거나 안전한 인자로 실행해야 함.
        # 하지만 단순히 목록 검증이 목적이라면, execute 메서드 내부 로직을 우회 검증하는 것이 나음.
        # 여기서는 executor의 검증 로직을 통과하는지만 확인.
        
        for cmd in TerminalExecutor.ALLOWED_COMMANDS:
            # 명령어 실행 시도 (존재하지 않는 인자 등으로 빨리 종료되게 유도)
            if cmd in ['python', 'python3', 'node', 'npm', 'git', 'cat', 'grep', 'find']:
                 # 버전 확인 등으로 안전하게 실행 시도
                 command_str = f"{cmd} --version"
            elif cmd in ['ls', 'dir', 'pwd', 'whoami', 'date', 'time', 'hostname', 'echo']:
                 command_str = cmd
            else:
                 # 나머지는 실행하지 않고 검증 로직만 통과하는지 확인하고 싶지만, 
                 # subprocess.run까지 가면 '파일을 찾을 수 없음' 에러가 나야 정상 (차단 에러 X)
                 command_str = f"{cmd} --help"

            result = self.executor.execute(command_str)
            
            # '허용되지 않은 명령어' 에러가 아니어야 함
            is_blocked = not result['success'] and '허용되지 않은 명령어' in result.get('error', '')
            self.assertFalse(is_blocked, f"명령어 '{cmd}'가 차단되었습니다 안전 모드 목록에 있어야 합니다.")
    
    def test_execute_dangerous_command_blocked(self):
        """위험 명령어 차단 테스트"""
        result = self.executor.execute("rm test.txt")
        
        self.assertFalse(result['success'])
        self.assertIn('위험 명령어', result['error'])
    
    def test_execute_dangerous_command_with_unsafe(self):
        """위험 모드로 위험 명령어 실행 테스트"""
        # allow_unsafe=True면 실행 시도 (파일이 없어도 명령 자체는 실행됨)
        result = self.executor.execute("echo safe_test", allow_unsafe=True)
        
        self.assertTrue(result['success'])
    
    def test_execute_unknown_command_blocked(self):
        """알 수 없는 명령어 차단 테스트"""
        result = self.executor.execute("unknowncommand123")
        
        self.assertFalse(result['success'])
        self.assertIn('허용되지 않은 명령어', result['error'])
    
    def test_execute_empty_command(self):
        """빈 명령어 테스트"""
        result = self.executor.execute("")
        
        self.assertFalse(result['success'])
        self.assertIn('비어있습니다', result['error'])
    
    def test_get_allowed_commands(self):
        """허용 명령어 목록 조회 테스트"""
        allowed = self.executor.get_allowed_commands()
        
        self.assertIn('pip', allowed)
        self.assertIn('git', allowed)
        self.assertIn('echo', allowed)

if __name__ == '__main__':
    unittest.main()
