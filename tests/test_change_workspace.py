"""
BUG v1.0.042 - change_workspace 테스트

/workspace 명령어로 작업 디렉토리를 변경한 후,
/save 가 변경된 workspace 경로에 파일을 올바르게 저장하는지 검증합니다.

대상 클래스:
  - GeminiCodeAssistant.change_workspace()
  - ClaudeCodeAssistant.change_workspace()
  - GenAICodeAssistant.change_workspace()
  - ResponseParser (workspace 경로 동기화)
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.file_manager import FileManager
from src.context_builder import ContextBuilder
from src.response_parser import ResponseParser


class TestChangeWorkspaceBase(unittest.TestCase):
    """change_workspace 기본 동작 테스트 (Assistant 클래스 공통)"""

    def setUp(self):
        # 초기 workspace (프로그램 실행 위치 역할)
        self.original_workspace = Path(tempfile.mkdtemp(prefix="ws_original_"))
        # 변경할 workspace (타깃 프로젝트 역할)
        self.target_workspace = Path(tempfile.mkdtemp(prefix="ws_target_"))

    def tearDown(self):
        shutil.rmtree(self.original_workspace, ignore_errors=True)
        shutil.rmtree(self.target_workspace, ignore_errors=True)


class TestResponseParserWorkspaceSync(TestChangeWorkspaceBase):
    """ResponseParser 가 workspace 변경 후 올바른 경로로 파일을 저장하는지 검증"""

    def test_save_to_original_workspace(self):
        """기본 workspace에 파일이 저장되는지 확인"""
        fm = FileManager(str(self.original_workspace))
        parser = ResponseParser(fm)

        response = """
```filename:src/hello.py
print('hello')
```
"""
        saved = parser.parse_and_save(response)

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0], "src/hello.py")
        self.assertTrue((self.original_workspace / "src" / "hello.py").exists())
        self.assertFalse((self.target_workspace / "src" / "hello.py").exists())

    def test_save_to_changed_workspace(self):
        """workspace 변경 후 새 경로에 파일이 저장되는지 확인"""
        # 초기 workspace로 시작
        fm = FileManager(str(self.original_workspace))
        parser = ResponseParser(fm)

        # workspace 변경 시뮬레이션 (change_workspace 내부 로직 동일)
        new_fm = FileManager(str(self.target_workspace))
        parser.file_manager = new_fm

        response = """
```filename:src/hello.py
print('hello from target')
```
"""
        saved = parser.parse_and_save(response)

        self.assertEqual(len(saved), 1)
        # 타깃 workspace에 저장되어야 함
        self.assertTrue((self.target_workspace / "src" / "hello.py").exists())
        # 원래 workspace에는 저장되지 않아야 함
        self.assertFalse((self.original_workspace / "src" / "hello.py").exists())

        content = (self.target_workspace / "src" / "hello.py").read_text(encoding='utf-8')
        self.assertEqual(content, "print('hello from target')")

    def test_consecutive_workspace_changes(self):
        """연속적인 workspace 변경 후에도 올바른 경로로 저장되는지 확인"""
        third_workspace = Path(tempfile.mkdtemp(prefix="ws_third_"))

        try:
            fm = FileManager(str(self.original_workspace))
            parser = ResponseParser(fm)

            response_a = """
```filename:file_a.txt
content_a
```
"""
            # 1차: original workspace에 저장
            saved_a = parser.parse_and_save(response_a)
            self.assertTrue((self.original_workspace / "file_a.txt").exists())

            # 2차: target workspace로 변경 후 저장
            parser.file_manager = FileManager(str(self.target_workspace))
            response_b = """
```filename:file_b.txt
content_b
```
"""
            saved_b = parser.parse_and_save(response_b)
            self.assertTrue((self.target_workspace / "file_b.txt").exists())
            self.assertFalse((self.original_workspace / "file_b.txt").exists())

            # 3차: third workspace로 변경 후 저장
            parser.file_manager = FileManager(str(third_workspace))
            response_c = """
```filename:file_c.txt
content_c
```
"""
            saved_c = parser.parse_and_save(response_c)
            self.assertTrue((third_workspace / "file_c.txt").exists())
            self.assertFalse((self.original_workspace / "file_c.txt").exists())
            self.assertFalse((self.target_workspace / "file_c.txt").exists())

        finally:
            shutil.rmtree(third_workspace, ignore_errors=True)


class TestGeminiChangeWorkspace(TestChangeWorkspaceBase):
    """GeminiCodeAssistant.change_workspace() 테스트"""

    def _create_assistant(self):
        """API 호출 없이 Assistant를 초기화 (workspace 관련 모듈만 테스트)"""
        from src.gemini_assistant import GeminiCodeAssistant
        return GeminiCodeAssistant(
            api_key="test_key",
            model_id="test_model",
            workspace_dir=str(self.original_workspace)
        )

    def test_change_workspace_success(self):
        """유효한 디렉토리로 workspace 변경 성공"""
        assistant = self._create_assistant()

        self.assertEqual(
            assistant.file_manager.workspace_dir,
            self.original_workspace
        )

        result = assistant.change_workspace(str(self.target_workspace))

        self.assertTrue(result)
        self.assertEqual(
            assistant.file_manager.workspace_dir,
            self.target_workspace
        )

    def test_change_workspace_invalid_dir(self):
        """존재하지 않는 디렉토리로 변경 시 실패"""
        assistant = self._create_assistant()
        non_existent = str(self.target_workspace / "non_existent_dir_12345")

        result = assistant.change_workspace(non_existent)

        self.assertFalse(result)
        # 원래 workspace가 유지되어야 함
        self.assertEqual(
            assistant.file_manager.workspace_dir,
            self.original_workspace
        )

    def test_change_workspace_file_not_dir(self):
        """파일 경로로 변경 시 실패"""
        assistant = self._create_assistant()
        temp_file = self.target_workspace / "not_a_dir.txt"
        temp_file.write_text("test", encoding='utf-8')

        result = assistant.change_workspace(str(temp_file))

        self.assertFalse(result)
        self.assertEqual(
            assistant.file_manager.workspace_dir,
            self.original_workspace
        )

    def test_response_parser_synced_after_change(self):
        """change_workspace 후 response_parser의 file_manager가 갱신되는지 확인"""
        assistant = self._create_assistant()

        # 변경 전: response_parser가 original workspace를 참조
        self.assertEqual(
            assistant.response_parser.file_manager.workspace_dir,
            self.original_workspace
        )

        assistant.change_workspace(str(self.target_workspace))

        # 변경 후: response_parser가 target workspace를 참조
        self.assertEqual(
            assistant.response_parser.file_manager.workspace_dir,
            self.target_workspace
        )

    def test_save_after_workspace_change(self):
        """workspace 변경 후 /save가 올바른 경로에 저장하는지 E2E 검증"""
        assistant = self._create_assistant()
        assistant.change_workspace(str(self.target_workspace))

        response = """
@@@filename:src/app.py
print('saved to target workspace')
@@@
"""
        saved = assistant.extract_and_save_files(response)

        self.assertEqual(len(saved), 1)
        self.assertTrue((self.target_workspace / "src" / "app.py").exists())
        self.assertFalse((self.original_workspace / "src" / "app.py").exists())

        content = (self.target_workspace / "src" / "app.py").read_text(encoding='utf-8')
        self.assertEqual(content, "print('saved to target workspace')")

    def test_all_internal_refs_updated(self):
        """change_workspace 후 모든 내부 참조가 갱신되는지 확인"""
        assistant = self._create_assistant()
        assistant.change_workspace(str(self.target_workspace))

        expected = self.target_workspace

        self.assertEqual(assistant.file_manager.workspace_dir, expected)
        self.assertEqual(assistant.response_parser.file_manager.workspace_dir, expected)
        self.assertEqual(assistant.code_executor.workspace_dir, expected)
        self.assertEqual(assistant.terminal_executor.workspace_dir, expected)


class TestClaudeChangeWorkspace(TestChangeWorkspaceBase):
    """ClaudeCodeAssistant.change_workspace() 테스트"""

    def _create_assistant(self):
        from src.claude_assistant import ClaudeCodeAssistant
        return ClaudeCodeAssistant(
            api_key="test_key",
            model_id="test_model",
            workspace_dir=str(self.original_workspace)
        )

    def test_change_workspace_success(self):
        """유효한 디렉토리로 workspace 변경 성공"""
        assistant = self._create_assistant()

        result = assistant.change_workspace(str(self.target_workspace))

        self.assertTrue(result)
        self.assertEqual(
            assistant.file_manager.workspace_dir,
            self.target_workspace
        )

    def test_change_workspace_invalid_dir(self):
        """존재하지 않는 디렉토리로 변경 시 실패"""
        assistant = self._create_assistant()
        non_existent = str(self.target_workspace / "non_existent")

        result = assistant.change_workspace(non_existent)

        self.assertFalse(result)
        self.assertEqual(
            assistant.file_manager.workspace_dir,
            self.original_workspace
        )

    def test_response_parser_synced_after_change(self):
        """change_workspace 후 response_parser가 갱신되는지 확인"""
        assistant = self._create_assistant()
        assistant.change_workspace(str(self.target_workspace))

        self.assertEqual(
            assistant.response_parser.file_manager.workspace_dir,
            self.target_workspace
        )

    def test_save_after_workspace_change(self):
        """workspace 변경 후 /save 경로 E2E 검증"""
        assistant = self._create_assistant()
        assistant.change_workspace(str(self.target_workspace))

        response = """
```filename:views/index.html
<h1>Hello</h1>
```
"""
        saved = assistant.extract_and_save_files(response)

        self.assertEqual(len(saved), 1)
        self.assertTrue((self.target_workspace / "views" / "index.html").exists())
        self.assertFalse((self.original_workspace / "views" / "index.html").exists())


class TestGenAIChangeWorkspace(TestChangeWorkspaceBase):
    """GenAICodeAssistant.change_workspace() 테스트"""

    def _create_assistant(self):
        from src.genai_assistant import GenAICodeAssistant
        return GenAICodeAssistant(
            endpoint_url="http://test",
            client_key="test_key",
            client_secret="test_secret",
            model_id="test_model",
            workspace_dir=str(self.original_workspace)
        )

    def test_change_workspace_success(self):
        """유효한 디렉토리로 workspace 변경 성공"""
        assistant = self._create_assistant()

        result = assistant.change_workspace(str(self.target_workspace))

        self.assertTrue(result)
        self.assertEqual(
            assistant.file_manager.workspace_dir,
            self.target_workspace
        )

    def test_change_workspace_invalid_dir(self):
        """존재하지 않는 디렉토리로 변경 시 실패"""
        assistant = self._create_assistant()
        non_existent = str(self.target_workspace / "non_existent")

        result = assistant.change_workspace(non_existent)

        self.assertFalse(result)
        self.assertEqual(
            assistant.file_manager.workspace_dir,
            self.original_workspace
        )

    def test_response_parser_synced_after_change(self):
        """change_workspace 후 response_parser가 갱신되는지 확인"""
        assistant = self._create_assistant()
        assistant.change_workspace(str(self.target_workspace))

        self.assertEqual(
            assistant.response_parser.file_manager.workspace_dir,
            self.target_workspace
        )

    def test_save_after_workspace_change(self):
        """workspace 변경 후 /save 경로 E2E 검증"""
        assistant = self._create_assistant()
        assistant.change_workspace(str(self.target_workspace))

        response = """
@@@filename:lib/utils.js
console.log('hello');
@@@
"""
        saved = assistant.extract_and_save_files(response)

        self.assertEqual(len(saved), 1)
        self.assertTrue((self.target_workspace / "lib" / "utils.js").exists())
        self.assertFalse((self.original_workspace / "lib" / "utils.js").exists())


if __name__ == '__main__':
    unittest.main()
