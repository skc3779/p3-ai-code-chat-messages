"""
PackageManager Unit Tests
"""

import unittest
import tempfile
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.package_manager import PackageManager

class TestPackageManager(unittest.TestCase):
    """PackageManager 클래스 테스트"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.pkg_manager = PackageManager(self.temp_dir)
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    @patch('subprocess.run')
    def test_list_packages_python(self, mock_run):
        """Python 패키지 목록 테스트"""
        # Mock output (pip list --format=json)
        mock_output = json.dumps([
            {"name": "requests", "version": "2.28.1"},
            {"name": "numpy", "version": "1.23.5"}
        ])
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = self.pkg_manager.list_packages("python")
        
        self.assertIn("requests==2.28.1", result)
        self.assertIn("numpy==1.23.5", result)
        
    @patch('subprocess.run')
    def test_list_packages_npm(self, mock_run):
        """Node 패키지 목록 테스트"""
        # Mock output (npm list --json)
        mock_output = json.dumps({
            "dependencies": {
                "react": {"version": "18.2.0"},
                "lodash": {"version": "4.17.21"}
            }
        })
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output
        mock_result.stderr = ""
        mock_run.return_value = mock_result
        
        result = self.pkg_manager.list_packages("npm")
        
        self.assertIn("react@18.2.0", result)
        self.assertIn("lodash@4.17.21", result)
        
    def test_list_packages_unsupported(self):
        """지원하지 않는 언어 테스트"""
        result = self.pkg_manager.list_packages("java")
        self.assertIn("지원하지 않는 언어", result)

if __name__ == '__main__':
    unittest.main()
