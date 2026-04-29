"""
GitManager Unit Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.git_manager import GitManager

class TestGitManager(unittest.TestCase):
    """GitManager 클래스 테스트"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.git = GitManager(self.temp_dir)
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    @patch('subprocess.run')
    def test_status(self, mock_run):
        """git status 테스트"""
        # Mock 설정
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "On branch main"
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        status = self.git.status()
        self.assertEqual(status, "On branch main")
        mock_run.assert_called_with(['git', 'status'], cwd=self.temp_dir, capture_output=True, text=True, encoding='utf-8')
        
    @patch('subprocess.run')
    def test_status_fail(self, mock_run):
        """git status 실패 테스트"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "fatal: not a git repository"
        mock_run.return_value = mock_result
        
        status = self.git.status()
        self.assertIn("실패", status)
        self.assertIn("not a git repository", status)

    @patch('subprocess.run')
    def test_add(self, mock_run):
        """git add 테스트"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        result = self.git.add(["file1.py", "file2.py"])
        self.assertIn("성공", result)
        mock_run.assert_called()

if __name__ == '__main__':
    unittest.main()
