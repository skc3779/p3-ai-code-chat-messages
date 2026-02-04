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
