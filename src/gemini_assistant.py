"""
GeminiCodeAssistant - Google Gemini API 코딩 어시스턴트 모듈
(REST API 직접 호출)
"""

import json
import re
from typing import List, Dict, Optional, Any
from pathlib import Path

import requests
import sseclient

from .file_manager import FileManager
from .context_builder import ContextBuilder
from .code_executor import CodeExecutor
from .terminal_executor import TerminalExecutor
from .git_manager import GitManager
from .package_manager import PackageManager
from .token_manager import TokenManager
from .api_retry import APIRetry
from .history_manager import HistoryManager
from .template_manager import TemplateManager
from .response_parser import ResponseParser


class GeminiCodeAssistant:
    """Google Gemini API 코딩 어시스턴트 (REST API 직접 호출)"""
    
    def __init__(
        self, 
        api_key: str, 
        model_id: str = "gemini-3.0-flash",
        workspace_dir: str = ".",
        endpoint_url: str = "https://generativelanguage.googleapis.com/v1beta"
    ):
        self.api_key = api_key
        self.endpoint_url = endpoint_url
        self.model_id = model_id
        self.headers = {
            "Content-Type": "application/json"
        }
        self.conversation_history: List[Dict] = []
        
        # 공용 모듈 초기화 (Claude/GenAI와 동일)
        self.file_manager = FileManager(workspace_dir)
        self.context_builder = ContextBuilder(self.file_manager)
        self.code_executor = CodeExecutor(self.file_manager.workspace_dir)
        self.terminal_executor = TerminalExecutor(self.file_manager.workspace_dir)
        self.git_manager = GitManager(self.file_manager.workspace_dir)
        self.package_manager = PackageManager(self.file_manager.workspace_dir)
        self.history_manager = HistoryManager(self.file_manager.workspace_dir)
        self.template_manager = TemplateManager(self.file_manager.workspace_dir)
        self.response_parser = ResponseParser(self.file_manager)
        
        self.default_system_prompt = """당신은 전문 소프트웨어 개발 어시스턴트입니다.
사용자의 프로젝트 파일을 분석하고, 코드를 생성하거나 수정하며, 문서를 작성합니다.

[필수] 코드나 파일을 생성할 때는 반드시 아래 형식을 정확히 따르세요:

```filename:경로/파일명.확장자
코드 내용
```

주의사항:
- 반드시 ```filename: 형식을 사용하세요 (```python, ```javascript 등 언어 식별자 사용 금지)
- 여러 파일은 각각 별도의 코드 블록으로 작성하세요
- 파일 경로는 프로젝트 루트 기준 상대 경로를 사용하세요
- 문서작성 시 이모지(Emoji) 사용을 하지 마세요"""
        
        self.system_prompt = self.default_system_prompt

    def set_system_prompt_from_template(self, template_name: str) -> bool:
        """템플릿으로 시스템 프롬프트 변경"""
        prompt = self.template_manager.get_system_prompt(template_name, "gemini")
        if prompt:
            self.system_prompt = prompt
            return True
        return False

    def reset_system_prompt(self) -> None:
        """기본 시스템 프롬프트로 복원"""
        self.system_prompt = self.default_system_prompt

    def list_templates(self) -> List[Dict[str, str]]:
        """사용 가능한 템플릿 목록"""
        return self.template_manager.list_templates()

    def chat(
        self, 
        user_message: str, 
        streaming: bool = True,
        include_context: bool = False,
        file_patterns: Optional[List[str]] = None
    ) -> str:
        """AI와 채팅"""
        # 컨텍스트 구성
        if include_context:
            context = self.context_builder.build_context(
                include_tree=True,
                file_patterns=file_patterns
            )
            full_message = f"{context}\n\n{'=' * 80}\n\n{user_message}" if context else user_message
        else:
            full_message = user_message
        
        # 히스토리 자동 트리밍 (Gemini 토큰 한도 적용)
        self.conversation_history = TokenManager.auto_trim_history(
            self.conversation_history,
            max_tokens=TokenManager.MAX_TOKENS_GEMINI
        )
        
        # API 호출
        try:
            if streaming:
                return self._chat_streaming(full_message)
            else:
                return self._chat_non_streaming(full_message)
        except Exception as e:
            print(f"\n❌ API 호출 오류: {str(e)}")
            return ""

    def _build_request_body(self, user_message: str) -> Dict:
        """Gemini API 요청 본문 구성"""
        # 대화 히스토리 + 새 메시지 구성
        contents = []
        
        for msg in self.conversation_history:
            contents.append({
                "role": msg["role"],
                "parts": [{"text": msg["content"]}]
            })
        
        # 새 사용자 메시지 추가
        contents.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })
        
        return {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": self.system_prompt}]
            },
            "generationConfig": {
                "maxOutputTokens": 8192,
                "temperature": 0.7
            }
        }

    def _chat_streaming(self, user_message: str) -> str:
        """스트리밍 모드 채팅 (SSE)"""
        api_url = f"{self.endpoint_url}/models/{self.model_id}:streamGenerateContent?alt=sse&key={self.api_key}"
        body = self._build_request_body(user_message)
        
        # 재시도 로직 적용
        response = APIRetry.retry_request(
            requests.post, api_url, headers=self.headers, json=body, stream=True
        )
        
        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            return ""
        
        client = sseclient.SSEClient(response)
        result_message = ""
        
        print("\n🤖 AI: ", end="", flush=True)
        
        try:
            for event in client.events():
                if event.data:
                    try:
                        data = json.loads(event.data)
                        # Gemini 응답 구조에서 텍스트 추출
                        candidates = data.get('candidates', [])
                        for candidate in candidates:
                            content = candidate.get('content', {})
                            parts = content.get('parts', [])
                            for part in parts:
                                text = part.get('text', '')
                                if text:
                                    print(text, end="", flush=True)
                                    result_message += text
                    except json.JSONDecodeError:
                        continue
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout) as e:
            print(f"\n\n[⚠️ 스트리밍 중단됨: {str(e)}]")
        
        print("\n")
        
        # 히스토리에 추가
        self.conversation_history.append({"role": "user", "content": user_message})
        if result_message:
            self.conversation_history.append({"role": "model", "content": result_message})
        
        return result_message

    def _chat_non_streaming(self, user_message: str) -> str:
        """논스트리밍 모드 채팅"""
        api_url = f"{self.endpoint_url}/models/{self.model_id}:generateContent?key={self.api_key}"
        body = self._build_request_body(user_message)
        
        # 재시도 로직 적용
        response = APIRetry.retry_request(
            requests.post, api_url, headers=self.headers, json=body
        )
        
        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            return ""
        
        result = response.json()
        
        # Gemini 응답 구조에서 텍스트 추출
        content = ""
        candidates = result.get('candidates', [])
        for candidate in candidates:
            candidate_content = candidate.get('content', {})
            parts = candidate_content.get('parts', [])
            for part in parts:
                content += part.get('text', '')
        
        print(f"\n🤖 AI: {content}\n")
        
        # 히스토리에 추가
        self.conversation_history.append({"role": "user", "content": user_message})
        if content:
            self.conversation_history.append({"role": "model", "content": content})
        
        return content

    def extract_and_save_files(self, response: str) -> List[str]:
        """AI 응답에서 파일 블록 추출 및 저장"""
        return self.response_parser.parse_and_save(response)

    def save_history(self, filepath: Optional[str] = None) -> str:
        """대화 히스토리를 JSON 파일로 저장"""
        return self.history_manager.save_gemini_history(
            self.conversation_history, self.model_id, filepath
        )
    
    def load_history(self, filepath: str) -> bool:
        """JSON 파일에서 대화 히스토리 로드"""
        data = self.history_manager.load_history(filepath)
        if data and data.get("type") == "gemini":
            self.conversation_history = data.get("messages", [])
            return True
        return False
    
    def list_history(self) -> List[str]:
        """저장된 히스토리 파일 목록"""
        return self.history_manager.list_history_files()
