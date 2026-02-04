"""
ContextBuilder Unit Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.context_builder import ContextBuilder
from src.file_manager import FileManager

class TestContextBuilder(unittest.TestCase):
    """ContextBuilder 클래스 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.file_manager = FileManager(self.temp_dir)
        self.context_builder = ContextBuilder(self.file_manager)
        
        # 테스트 파일 생성
        (Path(self.temp_dir) / "test.py").write_text("print('test')", encoding='utf-8')
    
    def tearDown(self):
        """테스트 환경 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_build_file_tree(self):
        """파일 트리 빌드 테스트"""
        tree = self.context_builder.build_file_tree()
        
        self.assertIn('프로젝트 구조', tree)
        self.assertIn('test.py', tree)
    
    def test_build_files_context(self):
        """파일 컨텍스트 빌드 테스트"""
        test_file = Path(self.temp_dir) / "test.py"
        context = self.context_builder.build_files_context([test_file])
        
        self.assertIn('test.py', context)
        self.assertIn("print('test')", context)
    
    def test_build_context_with_tree(self):
        """트리 포함 컨텍스트 빌드 테스트"""
        context = self.context_builder.build_context(include_tree=True)
        
        self.assertIn('프로젝트 구조', context)

if __name__ == '__main__':
    unittest.main()
