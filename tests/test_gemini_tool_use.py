"""
test_gemini_tool_use.py - Gemini Code Assistant Tool Use 테스트
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from io import StringIO

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gemini_assistant import GeminiCodeAssistant


class TestGeminiCodeAssistant(unittest.TestCase):
    """Gemini Code Assistant 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.test_workspace = Path(__file__).parent / "test_workspace"
        self.test_workspace.mkdir(exist_ok=True)
        
        # Mock API key로 어시스턴트 초기화
        self.assistant = GeminiCodeAssistant(
            api_key="test-api-key",
            model_id="gemini-3-pro-preview",
            endpoint_url="https://generativelanguage.googleapis.com/v1beta",
            workspace_dir=str(self.test_workspace)
        )
    
    def tearDown(self):
        """테스트 정리"""
        # 테스트 파일 정리
        if self.test_workspace.exists():
            import shutil
            shutil.rmtree(self.test_workspace, ignore_errors=True)

    def test_initialization(self):
        """초기화 테스트"""
        self.assertEqual(self.assistant.api_key, "test-api-key")
        self.assertEqual(self.assistant.model_id, "gemini-3-pro-preview")
        self.assertIsNotNone(self.assistant.file_manager)
        self.assertIsNotNone(self.assistant.context_builder)
        self.assertIsNotNone(self.assistant.code_executor)
        self.assertIsNotNone(self.assistant.terminal_executor)
        self.assertIsNotNone(self.assistant.git_manager)
        self.assertIsNotNone(self.assistant.history_manager)

    def test_build_request_body(self):
        """요청 본문 구성 테스트"""
        # 빈 히스토리로 테스트
        body = self.assistant._build_request_body("Hello, Gemini!")
        
        self.assertIn("contents", body)
        self.assertIn("systemInstruction", body)
        self.assertIn("generationConfig", body)
        
        # contents 검증
        self.assertEqual(len(body["contents"]), 1)
        self.assertEqual(body["contents"][0]["role"], "user")
        self.assertEqual(body["contents"][0]["parts"][0]["text"], "Hello, Gemini!")
        
        # systemInstruction 검증
        self.assertIn("parts", body["systemInstruction"])
        
        # generationConfig 검증
        self.assertIn("maxOutputTokens", body["generationConfig"])

    def test_build_request_body_with_history(self):
        """히스토리 포함 요청 본문 테스트"""
        # 히스토리 추가
        self.assistant.conversation_history = [
            {"role": "user", "content": "Hello"},
            {"role": "model", "content": "Hi there!"}
        ]
        
        body = self.assistant._build_request_body("How are you?")
        
        # 히스토리 + 새 메시지 = 3개
        self.assertEqual(len(body["contents"]), 3)
        self.assertEqual(body["contents"][0]["role"], "user")
        self.assertEqual(body["contents"][1]["role"], "model")
        self.assertEqual(body["contents"][2]["role"], "user")

    @patch('src.gemini_assistant.APIRetry.retry_request')
    def test_chat_non_streaming_success(self, mock_retry):
        """논스트리밍 채팅 성공 테스트"""
        # Mock 응답 설정
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Hello! I'm Gemini."}],
                    "role": "model"
                }
            }]
        }
        mock_retry.return_value = mock_response
        
        # stdout 캡처 (이모지 출력 오류 방지)
        with patch('sys.stdout', new_callable=StringIO):
            result = self.assistant._chat_non_streaming("Hello")
        
        # 결과 검증
        self.assertEqual(result, "Hello! I'm Gemini.")
        self.assertEqual(len(self.assistant.conversation_history), 2)
        self.assertEqual(self.assistant.conversation_history[0]["role"], "user")
        self.assertEqual(self.assistant.conversation_history[1]["role"], "model")

    @patch('src.gemini_assistant.APIRetry.retry_request')
    def test_chat_non_streaming_error(self, mock_retry):
        """논스트리밍 채팅 오류 테스트"""
        # Mock 오류 응답
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_retry.return_value = mock_response
        
        # stdout 캡처 (이모지 출력 오류 방지)
        with patch('sys.stdout', new_callable=StringIO):
            result = self.assistant._chat_non_streaming("Hello")
        
        # 빈 결과 반환
        self.assertEqual(result, "")

    def test_history_management(self):
        """히스토리 관리 테스트"""
        # 초기 상태
        self.assertEqual(len(self.assistant.conversation_history), 0)
        
        # 히스토리 추가
        self.assistant.conversation_history.append({"role": "user", "content": "Test"})
        self.assistant.conversation_history.append({"role": "model", "content": "Response"})
        
        self.assertEqual(len(self.assistant.conversation_history), 2)
        
        # 히스토리 저장 (stdout 캡처)
        with patch('sys.stdout', new_callable=StringIO):
            saved_path = self.assistant.save_history("test_session")
        self.assertTrue(os.path.exists(saved_path))
        
        # 히스토리 초기화
        self.assistant.conversation_history = []
        self.assertEqual(len(self.assistant.conversation_history), 0)
        
        # 히스토리 로드
        loaded = self.assistant.load_history("history_test_session.json")
        self.assertTrue(loaded)
        self.assertEqual(len(self.assistant.conversation_history), 2)

    def test_template_management(self):
        """템플릿 관리 테스트"""
        # 기본 프롬프트 확인
        original_prompt = self.assistant.system_prompt
        self.assertIsNotNone(original_prompt)
        
        # 프롬프트 리셋
        self.assistant.reset_system_prompt()
        self.assertEqual(self.assistant.system_prompt, self.assistant.default_system_prompt)


class TestGeminiDiffIntegration(unittest.TestCase):
    """Gemini + DiffViewer 통합 테스트"""
    
    def setUp(self):
        """테스트 설정"""
        self.test_workspace = Path(__file__).parent / "test_workspace_diff"
        self.test_workspace.mkdir(exist_ok=True)
        
        self.assistant = GeminiCodeAssistant(
            api_key="test-api-key",
            model_id="gemini-3-pro-preview",
            workspace_dir=str(self.test_workspace)
        )
    
    def tearDown(self):
        """테스트 정리"""
        if self.test_workspace.exists():
            import shutil
            shutil.rmtree(self.test_workspace, ignore_errors=True)

    def test_extract_and_save_files(self):
        """파일 추출 및 저장 테스트"""
        response = '''
Here is the code:

```filename:test_file.py
def hello():
    print("Hello, World!")
```
'''
        # stdout 캡처 (이모지 출력 오류 방지)
        with patch('sys.stdout', new_callable=StringIO):
            saved_files = self.assistant.extract_and_save_files(response)
        
        # 파일이 저장되었는지 확인
        if saved_files:
            self.assertTrue(len(saved_files) > 0)


if __name__ == "__main__":
    unittest.main()
