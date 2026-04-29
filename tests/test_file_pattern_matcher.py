"""
FilePatternMatcher Unit Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.file_pattern_matcher import FilePatternMatcher

class TestFilePatternMatcher(unittest.TestCase):
    """FilePatternMatcher 클래스 테스트"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.matcher = FilePatternMatcher(self.temp_dir)
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_normalize_pattern(self):
        """패턴 정규화 테스트"""
        # 기본 변환
        self.assertEqual(self.matcher.normalize_pattern("foo\\bar"), "foo/bar")
        self.assertEqual(self.matcher.normalize_pattern("./foo"), "foo")
        self.assertEqual(self.matcher.normalize_pattern(".\\bar"), "bar")
        
        # 절대 경로 변환 (workspace 내)
        abs_path = self.temp_dir / "src" / "test.py"
        self.assertEqual(self.matcher.normalize_pattern(str(abs_path)), "src/test.py")
        
    def test_match(self):
        """패턴 매칭 테스트"""
        target_file = self.temp_dir / "src" / "utils.py"
        
        # 1. 상대 경로 매칭
        self.assertTrue(self.matcher.match(target_file, "src/utils.py"))
        
        # 2. 파일명 매칭
        self.assertTrue(self.matcher.match(target_file, "utils.py"))
        
        # 3. 와일드카드 매칭
        self.assertTrue(self.matcher.match(target_file, "*.py"))
        self.assertTrue(self.matcher.match(target_file, "src/*.py"))
        
        # 4. 불일치
        self.assertFalse(self.matcher.match(target_file, "*.js"))
        self.assertFalse(self.matcher.match(target_file, "other/utils.py"))

    def test_filter_files(self):
        """파일 필터링 테스트"""
        files = [
            self.temp_dir / "a.py",
            self.temp_dir / "b.js",
            self.temp_dir / "src" / "c.py"
        ]
        
        # *.py 필터링
        filtered = self.matcher.filter_files(files, ["*.py"])
        self.assertEqual(len(filtered), 2)
        self.assertIn(self.temp_dir / "a.py", filtered)
        self.assertIn(self.temp_dir / "src" / "c.py", filtered)

if __name__ == '__main__':
    unittest.main()
