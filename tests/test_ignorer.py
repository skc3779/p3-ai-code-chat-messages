"""
Ignorer Unit Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ignorer import Ignorer

class TestIgnorer(unittest.TestCase):
    """Ignorer 클래스 테스트"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_should_ignore(self):
        """무시 로직 테스트"""
        patterns = ["*.log", "temp/", ".git"]
        ignorer = Ignorer(self.temp_dir, patterns)
        
        # 1. 패턴 매칭 (확장자)
        log_file = self.temp_dir / "error.log"
        self.assertTrue(ignorer.should_ignore(log_file))
        
        # 2. 디렉토리 매칭
        temp_dir = self.temp_dir / "temp"
        temp_dir.mkdir()
        # 주의: Ignorer 구현에 따라 디렉토리 자체를 넘길 때와 그 안의 파일을 넘길 때 동작 확인
        self.assertTrue(ignorer.should_ignore(temp_dir))
        
        # 3. 이름 일치 (.git)
        git_dir = self.temp_dir / ".git"
        git_dir.mkdir()
        self.assertTrue(ignorer.should_ignore(git_dir))
        
        # 4. 무시되지 않아야 함
        src_file = self.temp_dir / "main.py"
        self.assertFalse(ignorer.should_ignore(src_file))

if __name__ == '__main__':
    unittest.main()
