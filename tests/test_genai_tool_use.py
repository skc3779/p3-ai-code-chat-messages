"""
GenAI Code Assistant - Tool Use Unit Tests

GenAI API Tool Use 기능에 대한 단위 테스트
Mock을 사용하여 API 응답을 시뮬레이션하고 도구 실행 로직을 검증합니다.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.genai_assistant import GenAICodeAssistant
from src.file_manager import FileManager


class TestGenAIToolUse(unittest.TestCase):
    """GenAICodeAssistant Tool Use 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        self.assistant = GenAICodeAssistant(
            endpoint_url="http://dummy-api",
            client_key="dummy_key",
            client_secret="dummy_secret",
            model_id="test-model",
            workspace_dir="."
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
        
        # 검증 (경로 구분자 정규화)
        result_normalized = result.replace('\\', '/')
        self.assertIn("file1.py", result_normalized)
        self.assertIn("src/file2.py", result_normalized)

    def test_process_tool_calls(self):
        """process_tool_calls 메서드 테스트 (GenAI 전용 패턴)"""
        # GenAI 모델은 ```tool_code ... ``` 형식으로 도구 호출을 반환함
        response = """
Here is a tool call:
```tool_code
{"name": "read_file", "input": {"path": "test.py"}}
```
End of response.
"""
        # _execute_tool Mocking
        self.assistant._execute_tool = MagicMock(return_value="print('hello')")
        
        # 실행
        result = self.assistant.process_tool_calls(response)
        
        # 검증
        self.assistant._execute_tool.assert_called_with("read_file", {"path": "test.py"})
        self.assertIn("Tool 'read_file' Result:", result)
        self.assertIn("print('hello')", result)

    def test_process_tool_calls_multiple(self):
        """여러 도구 호출 처리 테스트"""
        response = """
First tool:
```tool_code
{"name": "read_file", "input": {"path": "a.txt"}}
```
Second tool:
```tool_code
{"name": "write_file", "input": {"path": "b.txt", "content": "B"}}
```
"""
        self.assistant._execute_tool = MagicMock(side_effect=["content_a", "success"])
        
        result = self.assistant.process_tool_calls(response)
        
        self.assertEqual(self.assistant._execute_tool.call_count, 2)
        self.assertIn("Tool 'read_file' Result:", result)
        self.assertIn("Tool 'write_file' Result:", result)

    def test_process_tool_calls_invalid_json(self):
        """잘못된 JSON 처리 테스트"""
        response = """
```tool_code
{invalid_json}
```
"""
        # print 억제
        with patch('builtins.print'):
            result = self.assistant.process_tool_calls(response)
        
        # 결과는 비어있어야 함
        self.assertEqual(result, "")


class TestGenAIDiffViewerIntegration(unittest.TestCase):
    """GenAI 어시스턴트와 DiffViewer 통합 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        from src.diff_viewer import DiffViewer
        self.diff_viewer = DiffViewer()
    
    def test_extract_and_diff_from_genai_response(self):
        """GenAI 응답에서 코드 추출 및 Diff 생성 테스트"""
        # GenAI가 반환하는 형식의 응답
        response = """
Here's the updated code:

```python filename:src/utils.py
def format_number(n):
    \"\"\"Format number with commas\"\"\"
    return f"{n:,}"

def parse_number(s):
    \"\"\"Parse formatted number\"\"\"
    return int(s.replace(",", ""))
```

I've added a parse_number function.
"""
        suggestions = self.diff_viewer.extract_code_suggestions(response)
        
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['filepath'], Path('src/utils.py'))
        self.assertIn('def format_number', suggestions[0]['content'])
        self.assertIn('def parse_number', suggestions[0]['content'])
    
    def test_diff_stats(self):
        """변경 통계 테스트"""
        original = "line1\nline2"
        new = "line1\nline2\nline3\nline4"
        
        stats = self.diff_viewer.get_diff_stats(original, new)
        
        self.assertEqual(stats['added'], 2)
        self.assertEqual(stats['deleted'], 0)
        self.assertEqual(stats['original_lines'], 2)
        self.assertEqual(stats['new_lines'], 4)


if __name__ == '__main__':
    unittest.main()

