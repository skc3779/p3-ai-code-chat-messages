"""
TreeBuilder Unit Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tree_builder import TreeBuilder

class TestTreeBuilder(unittest.TestCase):
    """TreeBuilder 클래스 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # 테스트 디렉토리 구조 생성
        (self.temp_dir / "file1.py").write_text("# file1", encoding='utf-8')
        (self.temp_dir / "file2.js").write_text("// file2", encoding='utf-8')
        (self.temp_dir / "subdir").mkdir()
        (self.temp_dir / "subdir" / "nested.py").write_text("# nested", encoding='utf-8')
    
    def tearDown(self):
        """테스트 환경 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_build_tree(self):
        """트리 빌드 테스트"""
        builder = TreeBuilder(
            workspace_dir=self.temp_dir,
            should_ignore=lambda p: False,
            max_depth=3
        )
        tree = builder.build()
        
        self.assertIn('프로젝트 구조', tree)
        self.assertIn('file1.py', tree)
        self.assertIn('subdir', tree)
    
    def test_build_tree_with_ignore(self):
        """무시 패턴 포함 트리 빌드 테스트"""
        builder = TreeBuilder(
            workspace_dir=self.temp_dir,
            should_ignore=lambda p: p.name == 'subdir',
            max_depth=3
        )
        tree = builder.build()
        
        self.assertIn('file1.py', tree)
        self.assertNotIn('nested.py', tree)  # subdir이 무시되므로 nested.py도 없음

if __name__ == '__main__':
    unittest.main()
