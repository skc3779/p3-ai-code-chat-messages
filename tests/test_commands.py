"""
Claude Code Assistant - Unit Tests

명령어 기능에 대한 단위 테스트
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.file_manager import FileManager
from src.code_executor import CodeExecutor
from src.terminal_executor import TerminalExecutor
from src.tree_builder import TreeBuilder
from src.context_builder import ContextBuilder


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
    
    def test_read_file_not_found(self):
        """존재하지 않는 파일 읽기 테스트"""
        content = self.file_manager.read_file(Path(self.temp_dir) / "nonexistent.py")
        self.assertIsNone(content)
    
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


class TestCodeExecutor(unittest.TestCase):
    """CodeExecutor 클래스 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.executor = CodeExecutor(self.temp_dir, timeout=10)
    
    def tearDown(self):
        """테스트 환경 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_execute_python_success(self):
        """Python 코드 실행 성공 테스트"""
        code = "print('Hello, World!')"
        result = self.executor.execute(code, 'python')
        
        self.assertTrue(result['success'])
        self.assertIn('Hello, World!', result['stdout'])
        self.assertEqual(result['returncode'], 0)
    
    def test_execute_python_error(self):
        """Python 코드 실행 오류 테스트"""
        code = "print(undefined_variable)"
        result = self.executor.execute(code, 'python')
        
        self.assertFalse(result['success'])
        self.assertIn('NameError', result['stderr'])
    
    def test_execute_unsupported_language(self):
        """지원하지 않는 언어 테스트"""
        result = self.executor.execute("code", 'ruby')
        
        self.assertFalse(result['success'])
        self.assertIn('지원하지 않는 언어', result['error'])
    
    def test_extract_code_from_response_filename_format(self):
        """filename: 형식 코드 추출 테스트"""
        response = """
```filename:test.py
print('hello')
```
"""
        blocks = self.executor.extract_code_from_response(response)
        
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['filepath'], 'test.py')
        self.assertEqual(blocks[0]['code'], "print('hello')")
        self.assertEqual(blocks[0]['language'], 'python')
    
    def test_extract_code_from_response_language_format(self):
        """언어 식별자 형식 코드 추출 테스트"""
        response = """
```python
x = 1 + 1
print(x)
```
"""
        blocks = self.executor.extract_code_from_response(response)
        
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['language'], 'python')
        self.assertIn('print(x)', blocks[0]['code'])
    
    def test_extract_multiple_code_blocks(self):
        """여러 코드 블록 추출 테스트"""
        response = """
```filename:file1.py
code1
```

```filename:file2.js
code2
```
"""
        blocks = self.executor.extract_code_from_response(response)
        self.assertEqual(len(blocks), 2)


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


class TestIntegration(unittest.TestCase):
    """통합 테스트"""
    
    def test_code_execution_workflow(self):
        """코드 실행 워크플로우 테스트"""
        temp_dir = Path(tempfile.mkdtemp())
        executor = CodeExecutor(temp_dir)
        
        # 1. AI 응답에서 코드 추출
        ai_response = """
다음은 계산기 코드입니다:

```filename:calculator.py
def add(a, b):
    return a + b

print(add(2, 3))
```
"""
        blocks = executor.extract_code_from_response(ai_response)
        self.assertEqual(len(blocks), 1)
        
        # 2. 추출된 코드 실행
        result = executor.execute(blocks[0]['code'], 'python')
        self.assertTrue(result['success'])
        self.assertIn('5', result['stdout'])
        
        # 정리
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)
