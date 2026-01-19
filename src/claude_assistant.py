"""
ClaudeCodeAssistant - Claude AI 코딩 어시스턴트 모듈
"""

import json
import re
from typing import List, Dict, Optional

import requests
import sseclient

from .file_manager import FileManager
from .context_builder import ContextBuilder
from .code_executor import CodeExecutor
from .terminal_executor import TerminalExecutor


class ClaudeCodeAssistant:
    """Claude AI 코딩 어시스턴트"""

    def __init__(self, api_key: str, model_id: str = "claude-sonnet-4-5",
                 workspace_dir: str = ".", endpoint_url: str = "https://api.anthropic.com"):
        self.endpoint_url = endpoint_url
        self.headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        self.model_id = model_id
        self.conversation_history: List[Dict] = []

        self.file_manager = FileManager(workspace_dir)
        self.context_builder = ContextBuilder(self.file_manager)
        self.code_executor = CodeExecutor(self.file_manager.workspace_dir)
        self.terminal_executor = TerminalExecutor(self.file_manager.workspace_dir)

        self.system_prompt = """당신은 전문 소프트웨어 개발 어시스턴트입니다.
사용자의 프로젝트 파일을 분석하고, 코드를 생성하거나 수정하며, 문서를 작성합니다.

[필수] 코드나 파일을 생성할 때는 반드시 아래 형식을 정확히 따르세요:

```filename:경로/파일명.확장자
코드 내용
```

예시:
```filename:src/main.py
print("Hello, World!")
```

```filename:README.md
# 프로젝트 제목
```

주의사항:
- 반드시 ```filename: 형식을 사용하세요 (```python, ```javascript 등 언어 식별자 사용 금지)
- 여러 파일은 각각 별도의 코드 블록으로 작성하세요
- 파일 경로는 프로젝트 루트 기준 상대 경로를 사용하세요"""

    def chat(self, user_message: str, streaming: bool = True,
             include_context: bool = False, file_patterns: Optional[List[str]] = None) -> str:
        """AI와 채팅"""

        # 컨텍스트 구성
        if include_context:
            context = self.context_builder.build_context(
                include_tree=True,
                file_patterns=file_patterns
            )

            if context:
                full_message = f"{context}\n\n{'=' * 80}\n\n{user_message}"
            else:
                full_message = user_message
        else:
            full_message = user_message

        # API 호출 - Claude API 형식으로 메시지 구성
        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": full_message})

        body = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": 8192,
            "system": self.system_prompt,
            "stream": streaming
        }

        api_url = f"{self.endpoint_url}/v1/messages"

        try:
            if streaming:
                return self._chat_streaming(api_url, body, user_message, full_message)
            else:
                return self._chat_non_streaming(api_url, body, user_message, full_message)
        except Exception as e:
            print(f"\n❌ API 호출 오류: {str(e)}")
            return ""

    def _chat_streaming(self, api_url: str, body: Dict,
                        original_message: str, full_message: str) -> str:
        """스트리밍 모드 채팅"""
        response = requests.post(api_url, headers=self.headers, json=body, stream=True)

        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            return ""

        client = sseclient.SSEClient(response)
        result_message = ""

        print("\n🤖 AI: ", end="", flush=True)

        for event in client.events():
            if event.data:
                try:
                    data = json.loads(event.data)
                    event_type = data.get('type')

                    if event_type == 'content_block_delta':
                        content = data.get('delta', {}).get('text', '')
                        if content:
                            print(content, end="", flush=True)
                            result_message += content
                    elif event_type == 'message_stop':
                        break
                except json.JSONDecodeError:
                    continue

        print("\n")

        # 히스토리에 추가
        self.conversation_history.append({"role": "user", "content": original_message})
        if result_message:
            self.conversation_history.append({"role": "assistant", "content": result_message})

        return result_message

    def _chat_non_streaming(self, api_url: str, body: Dict,
                            original_message: str, full_message: str) -> str:
        """논스트리밍 모드 채팅"""
        response = requests.post(api_url, headers=self.headers, json=body)

        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            return ""

        result = response.json()
        content_blocks = result.get('content', [])
        content = content_blocks[0].get('text', '') if content_blocks else ''

        print(f"\n🤖 AI: {content}\n")

        # 히스토리에 추가
        self.conversation_history.append({"role": "user", "content": original_message})
        if content:
            self.conversation_history.append({"role": "assistant", "content": content})

        return content

    def extract_and_save_files(self, response: str) -> List[str]:
        """AI 응답에서 파일을 추출하여 저장"""
        pattern = r'```filename:(.+?)\n(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)

        saved_files = []

        for filepath_str, content in matches:
            filepath_str = filepath_str.strip()
            filepath = self.file_manager.workspace_dir / filepath_str

            if filepath.exists():
                print(f"\n⚠️  파일이 이미 존재합니다: {filepath_str}")
                confirm = input("덮어쓰시겠습니까? (y/N): ").strip().lower()
                if confirm != 'y':
                    print(f"⏭️  건너뛰기: {filepath_str}")
                    continue

            if self.file_manager.write_file(filepath, content.strip()):
                saved_files.append(filepath_str)
                print(f"✅ 파일 저장됨: {filepath_str}")

        return saved_files
