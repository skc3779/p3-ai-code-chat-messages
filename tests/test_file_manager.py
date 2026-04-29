"""
FileManager Unit Tests
"""

import unittest
import tempfile
import sys
from unittest.mock import patch
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.file_manager import FileManager

class TestFileManager(unittest.TestCase):
    """FileManager 클래스 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.file_manager = FileManager(self.temp_dir)
        
        # 테스트 파일 생성
        (Path(self.temp_dir) / "test.py").write_text("print('hello')", encoding='utf-8')
        (Path(self.temp_dir) / "test.js").write_text("console.log('hello')", encoding='utf-8')
        (Path(self.temp_dir) / "subdir").mkdir(exist_ok=True)
        (Path(self.temp_dir) / "subdir" / "nested.py").write_text("# nested", encoding='utf-8')
    
    def tearDown(self):
        """테스트 환경 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_list_files_all(self):
        """모든 파일 목록 테스트"""
        files = self.file_manager.list_files()
        self.assertGreaterEqual(len(files), 3)
    
    def test_list_files_by_extension(self):
        """확장자별 파일 필터링 테스트"""
        py_files = self.file_manager.list_files(extensions=['.py'])
        self.assertEqual(len(py_files), 2)  # test.py, nested.py
        
        js_files = self.file_manager.list_files(extensions=['.js'])
        self.assertEqual(len(js_files), 1)  # test.js
    
    def test_read_file(self):
        """파일 읽기 테스트"""
        content = self.file_manager.read_file(Path(self.temp_dir) / "test.py")
        self.assertEqual(content, "print('hello')")
    
    @patch('builtins.print')
    def test_read_file_not_found(self, mock_print):
        """존재하지 않는 파일 읽기 테스트"""
        content = self.file_manager.read_file(Path(self.temp_dir) / "nonexistent.py")
        self.assertIsNone(content)
        # 에러 메시지가 출력되었는지 확인 (선택 사항)
        # mock_print.assert_called()
    
    def test_write_file(self):
        """파일 쓰기 테스트"""
        new_file = Path(self.temp_dir) / "new_file.txt"
        result = self.file_manager.write_file(new_file, "new content")
        
        self.assertTrue(result)
        self.assertTrue(new_file.exists())
        self.assertEqual(new_file.read_text(encoding='utf-8'), "new content")
    
    def test_write_file_with_subdirectory(self):
        """하위 디렉토리 파일 쓰기 테스트"""
        new_file = Path(self.temp_dir) / "new_subdir" / "file.txt"
        result = self.file_manager.write_file(new_file, "nested content")
        
        self.assertTrue(result)
        self.assertTrue(new_file.exists())
    
    def test_should_ignore(self):
        """무시 패턴 테스트"""
        # 기본 무시 패턴 테스트
        pycache_dir = Path(self.temp_dir) / "__pycache__"
        pycache_dir.mkdir(exist_ok=True)
        self.assertTrue(self.file_manager.should_ignore(pycache_dir))
        
        # 일반 파일은 무시하지 않음
        test_file = Path(self.temp_dir) / "test.py"
        self.assertFalse(self.file_manager.should_ignore(test_file))
    
    def test_get_file_info(self):
        """파일 정보 조회 테스트"""
        test_file = Path(self.temp_dir) / "test.py"
        info = self.file_manager.get_file_info(test_file)
        
        self.assertIn('path', info)
        self.assertIn('size', info)
        self.assertIn('modified', info)
        self.assertIn('extension', info)
        self.assertEqual(info['extension'], '.py')

if __name__ == '__main__':
    unittest.main()
