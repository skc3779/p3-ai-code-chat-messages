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
from src.token_manager import TokenManager

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

    def test_build_context_with_multiple_file_patterns(self):
        """다중 파일 패턴으로 컨텍스트 빌드 테스트 (*.py, src/*.py)"""

        print(f"Temporary directory for test: {self.temp_dir}")  # 디버깅용 출력

        # 루트 추가 Python 파일 생성
        (Path(self.temp_dir) / "main.py").write_text("# main module", encoding='utf-8')

        # src 서브디렉토리 및 Python 파일 생성
        src_dir = Path(self.temp_dir) / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("# src module", encoding='utf-8')
        (src_dir / "utils.py").write_text("# src utils", encoding='utf-8')

        # 패턴에 매칭되지 않을 파일 생성
        (Path(self.temp_dir) / "readme.txt").write_text("readme content", encoding='utf-8')

        # 다중 패턴으로 컨텍스트 빌드 (트리 제외)
        context = self.context_builder.build_context(
            include_tree=False,
            file_patterns=["*.py", "src/*.py"]
        )

        # *.py 패턴 — 루트 Python 파일 포함 확인
        self.assertIn("test.py", context)
        self.assertIn("main.py", context)
        self.assertIn("# main module", context)

        # src/*.py 패턴 — src 디렉토리 Python 파일 포함 확인
        self.assertIn("module.py", context)
        self.assertIn("# src module", context)
        self.assertIn("utils.py", context)
        self.assertIn("# src utils", context)

        # .txt 파일은 패턴에 미포함 확인
        self.assertNotIn("readme.txt", context)
        self.assertNotIn("readme content", context)

    def test_max_tokens_default(self):
        """max_tokens 미전달 시 TokenManager.DEFAULT_MAX_TOKENS 사용 확인"""
        cb = ContextBuilder(self.file_manager)
        self.assertEqual(cb.max_tokens, TokenManager.DEFAULT_MAX_TOKENS)

    def test_max_tokens_explicit(self):
        """max_tokens 직접 전달 시 해당 값 적용 확인"""
        cb = ContextBuilder(self.file_manager, max_tokens=50000)
        self.assertEqual(cb.max_tokens, 50000)

    def test_max_tokens_platform_claude(self):
        """Claude 플랫폼 토큰 한도 전달 확인"""
        cb = ContextBuilder(self.file_manager, max_tokens=TokenManager.MAX_TOKENS_CLAUDE)
        self.assertEqual(cb.max_tokens, TokenManager.MAX_TOKENS_CLAUDE)

    def test_context_truncated_when_exceeds_max_tokens(self):
        """max_tokens 기반 max_chars 초과 시 파일 생략 경고 메시지 포함 확인"""
        large_content = "x" * 200
        (Path(self.temp_dir) / "large.py").write_text(large_content, encoding='utf-8')
        (Path(self.temp_dir) / "small.py").write_text("# small", encoding='utf-8')

        # max_tokens를 매우 작게 설정하여 두 번째 파일에서 초과되도록 유도
        # max_chars = 10 * 3.5 = 35자
        self.context_builder.max_tokens = 10
        test_files = [
            Path(self.temp_dir) / "large.py",
            Path(self.temp_dir) / "small.py",
        ]
        context = self.context_builder.build_files_context(test_files)
        self.assertIn("컨텍스트 크기 제한으로 일부 파일이 생략", context)
        self.assertIn("tokens", context)

if __name__ == '__main__':
    unittest.main()
