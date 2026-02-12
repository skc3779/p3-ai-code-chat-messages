"""
Claude Code Assistant - Tool Use Unit Tests

Claude API Tool Use 기능에 대한 단위 테스트
Mock을 사용하여 API 응답을 시뮬레이션하고 도구 실행 로직을 검증합니다.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.claude_assistant import ClaudeCodeAssistant
from src.file_manager import FileManager


class TestClaudeToolUse(unittest.TestCase):
    """ClaudeCodeAssistant Tool Use 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        self.assistant = ClaudeCodeAssistant(
            api_key="dummy_key",
            workspace_dir=".",
            model_id="test-model"
        )
        # FileManager Mocking
        self.assistant.file_manager = MagicMock(spec=FileManager)
        self.assistant.file_manager.workspace_dir = Path("/mock/workspace")
    
    def test_execute_tool_read_file(self):
        """read_file 도구 실행 테스트"""
        # 설정
        self.assistant.file_manager.read_file.return_value = "file content"
        
        # 실행
        result = self.assistant._execute_tool("read_file", {"path": "src/main.py"})
        
        # 검증
        self.assistant.file_manager.read_file.assert_called_with(Path("/mock/workspace/src/main.py"))
        self.assertEqual(result, "file content")
        
    def test_execute_tool_write_file(self):
        """write_file 도구 실행 테스트"""
        # 설정
        self.assistant.file_manager.write_file.return_value = True
        
        # 실행
        result = self.assistant._execute_tool("write_file", {"path": "test.txt", "content": "hello"})
        
        # 검증
        self.assistant.file_manager.write_file.assert_called_with(Path("/mock/workspace/test.txt"), "hello")
        self.assertEqual(result, "파일 저장 성공")
        
    def test_execute_tool_list_files(self):
        """list_files 도구 실행 테스트"""
        # 설정
        self.assistant.file_manager.list_files.return_value = [
            self.assistant.file_manager.workspace_dir / "file1.py",
            self.assistant.file_manager.workspace_dir / "src/file2.py"
        ]
        
        # 실행
        result = self.assistant._execute_tool("list_files", {"path": "."})
        
        # 검증
        # 경로 구분자 불일치 해결을 위해 replace로 정규화하여 비교
        result_normalized = result.replace('\\', '/')
        self.assertIn("file1.py", result_normalized)
        self.assertIn("src/file2.py", result_normalized)

    def test_execute_tool_git_status(self):
        """git_status 도구 실행 테스트"""
        # GitManager Mock 설정
        self.assistant.git_manager = MagicMock()
        self.assistant.git_manager.status.return_value = "On branch main\nChanges to be committed:..."
        
        result = self.assistant._execute_tool("git_status", {})
        
        self.assistant.git_manager.status.assert_called_once()
        self.assertEqual(result, "On branch main\nChanges to be committed:...")

    def test_execute_tool_git_commit(self):
        """git_commit 도구 실행 테스트"""
        self.assistant.git_manager = MagicMock()
        self.assistant.git_manager.commit.return_value = "커밋 성공: [main 1234567] message"
        
        result = self.assistant._execute_tool("git_commit", {"message": "test commit"})
        
        self.assistant.git_manager.commit.assert_called_with(message="test commit")
        self.assertIn("커밋 성공", result)

    def test_execute_tool_list_packages(self):
        """list_packages 도구 실행 테스트"""
        # PackageManager Mock 설정
        self.assistant.package_manager = MagicMock()
        self.assistant.package_manager.list_packages.return_value = "numpy==1.0.0\npandas==1.0.0"
        
        result = self.assistant._execute_tool("list_packages", {"language": "python"})
        
        self.assistant.package_manager.list_packages.assert_called_with(language="python")
        self.assertEqual(result, "numpy==1.0.0\npandas==1.0.0")

    def test_chat_non_streaming_tool_use(self):
        """논스트리밍 모드에서 Tool Use 처리 테스트"""
        
        # Mock Response 1 (Tool Use 요청)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool_1",
                    "name": "read_file",
                    "input": {"path": "test.py"}
                }
            ],
            "stop_reason": "tool_use"
        }

        # Mock Response 2 (최종 응답)
        final_response = MagicMock()
        final_response.status_code = 200
        final_response.json.return_value = {
            "content": [{"type": "text", "text": "파일 내용은..."}],
            "stop_reason": "end_turn"
        }
        
        # requests.post MOCK
        with patch('requests.post') as mock_post:
            mock_post.side_effect = [mock_response, final_response]
            
            # 도구 실행 결과 Mock
            self.assistant._execute_tool = MagicMock(return_value="print('hello')")
            
            # 실행
            self.assistant.chat("test.py 읽어줘", streaming=False)
            
            # 검증
            # 1. _execute_tool 호출 확인
            self.assistant._execute_tool.assert_called_with("read_file", {"path": "test.py"})
            
            # 2. API 호출 횟수 확인 (재귀 호출 포함 2회)
            self.assertEqual(mock_post.call_count, 2)
            
            # 3. 두 번째 호출(재귀 호출)의 메시지 구조 검사
            # Tool Result가 User 역할로 마지막 메시지에 포함되어 있어야 함
            last_call = mock_post.call_args_list[-1]
            last_body = last_call.kwargs.get('json', last_call[1].get('json')) # kwargs 안전 접근
            last_message = last_body['messages'][-1]
            
            self.assertEqual(last_message['role'], 'user')
            
            content = last_message['content']
            self.assertIsInstance(content, list)
            self.assertEqual(content[0]['type'], 'tool_result')
            self.assertEqual(content[0]['tool_use_id'], 'tool_1')
            self.assertEqual(content[0]['content'], "print('hello')")


class TestClaudeDiffViewerIntegration(unittest.TestCase):
    """Claude 어시스턴트와 DiffViewer 통합 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        from src.diff_viewer import DiffViewer
        self.diff_viewer = DiffViewer()
    
    def test_extract_and_diff_from_claude_response(self):
        """Claude 응답에서 코드 추출 및 Diff 생성 테스트"""
        # Claude가 반환하는 형식의 응답
        response = """
Here's the updated code:

```filename:src/calculator.py
def add(a, b):
    \"\"\"Add two numbers\"\"\"
    return a + b

def subtract(a, b):
    \"\"\"Subtract b from a\"\"\"
    return a - b
```

I've added a new subtract function.
"""
        suggestions = self.diff_viewer.extract_code_suggestions(response)
        
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['filepath'], Path('src/calculator.py'))
        self.assertIn('def add', suggestions[0]['content'])
        self.assertIn('def subtract', suggestions[0]['content'])
    
    def test_diff_with_original_file(self):
        """원본 파일과의 Diff 생성 테스트"""
        original = "def add(a, b):\n    return a + b"
        new = "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b"
        
        diff = self.diff_viewer.generate_colored_diff(original, new)
        
        self.assertIn('+def subtract', diff)


if __name__ == '__main__':
    unittest.main()

