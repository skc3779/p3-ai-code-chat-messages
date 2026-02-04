"""
ClaudeCodeAssistant - Claude AI 코딩 어시스턴트 모듈
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
from .tool_definitions import FILESYSTEM_TOOLS
from .token_manager import TokenManager
from .api_retry import APIRetry
from .history_manager import HistoryManager
from .history_manager import HistoryManager
from .template_manager import TemplateManager
from .response_parser import ResponseParser


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

[필수] 파일 시스템 조작, Git 작업, 패키지 확인이 필요한 경우 제공된 도구(Tools)를 사용하세요.

```tool_code
{"name": "도구이름", "input": {"키": "값"}}
```

사용 가능한 도구:
1. 파일 시스템:
- 파일 읽기: read_file
- 파일 쓰기: write_file
- 파일 목록: list_files
- 디렉토리 구조: list_directory_tree

2. Git 버전 관리:
- 상태 확인: git_status
- 변경 사항 확인: git_diff
- 커밋 로그: git_log
- 파일 추가: git_add
- 커밋: git_commit

3. 환경 분석:
- 패키지 목록: list_packages(language="python"|"node")

예시:
```tool_code
{"name": "read_file", "input": {"path": "src/main.py"}}
```

주의사항:
- 반드시 ```filename: 형식을 사용하세요 (```python, ```javascript 등 언어 식별자 사용 금지)
- 여러 파일은 각각 별도의 코드 블록으로 작성하세요
- 파일 경로는 프로젝트 루트 기준 상대 경로를 사용하세요
- 문서작성 시 이모지(Emoji) 사용을 하지 마세요"""
        
        self.system_prompt = self.default_system_prompt

    def set_system_prompt_from_template(self, template_name: str) -> bool:
        """템플릿으로 시스템 프롬프트 변경"""
        prompt = self.template_manager.get_system_prompt(template_name, "claude")
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

        # 히스토리 자동 트리밍 (Claude 토큰 한도 적용)
        self.conversation_history = TokenManager.auto_trim_history(
            self.conversation_history,
            max_tokens=TokenManager.MAX_TOKENS_CLAUDE
        )

        # API 호출 - Claude API 형식으로 메시지 구성
        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": full_message})

        # print(f"### 요청 메세지 히스토리  : {messages}")

        body = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": 4096,
            "system": self.system_prompt,
            "tools": FILESYSTEM_TOOLS,  # 도구 정의 추가
            "stream": streaming
        }

        api_url = f"{self.endpoint_url}/v1/messages"

        try:
            if streaming:
                return self._chat_streaming(api_url, body, user_message)
            else:
                return self._chat_non_streaming(api_url, body, user_message)
        except Exception as e:
            print(f"\n❌ API 호출 오류: {str(e)}")
            return ""

    def _execute_tool(self, tool_name: str, tool_input: Dict) -> Any:
        """도구 실행"""
        try:
            if tool_name == "read_file":
                path = Path(tool_input.get("path"))
                content = self.file_manager.read_file(self.file_manager.workspace_dir / path)
                if content is None:
                    return "파일을 찾을 수 없거나 읽을 수 없습니다."
                return content
            elif tool_name == "write_file":
                path = Path(tool_input.get("path"))
                content = tool_input.get("content")
                success = self.file_manager.write_file(self.file_manager.workspace_dir / path, content)
                return "파일 저장 성공" if success else "파일 저장 실패"
            elif tool_name == "list_files":
                # 단순화된 구현: 현재는 전체 목록 반환
                files = self.file_manager.list_files()
                return "\n".join([str(f.relative_to(self.file_manager.workspace_dir)) for f in files])
            elif tool_name == "list_directory_tree":
                max_depth = tool_input.get("depth", 3)
                return self.context_builder.build_file_tree(max_depth=max_depth)
            
            # Git Tools
            elif tool_name == "git_status":
                return self.git_manager.status()
            elif tool_name == "git_diff":
                return self.git_manager.diff(cached=tool_input.get("cached", False))
            elif tool_name == "git_log":
                return self.git_manager.log(max_count=tool_input.get("max_count", 5))
            elif tool_name == "git_add":
                return self.git_manager.add(files=tool_input.get("files", []))
            elif tool_name == "git_commit":
                return self.git_manager.commit(message=tool_input.get("message"))
            
            # Package Tools
            elif tool_name == "list_packages":
                return self.package_manager.list_packages(language=tool_input.get("language", "python"))
                
            else:
                return f"알 수 없는 도구: {tool_name}"
        except Exception as e:
            return f"도구 실행 오류: {str(e)}"

    def _chat_streaming(self, api_url: str, body: Dict, user_message: str) -> str:
        """스트리밍 모드 채팅 (Tool Use 지원)"""
        # 재시도 로직 적용
        response = APIRetry.retry_request(
            requests.post, api_url, headers=self.headers, json=body, stream=True
        )

        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            return ""

        client = sseclient.SSEClient(response)
        
        # 스트리밍 상태 관리
        current_message_content = []
        tool_use_block = None
        tool_json_accumulated = ""
        
        print("\n🤖 AI: ", end="", flush=True)

        try:
            for event in client.events():
                if event.data:
                    try:
                        data = json.loads(event.data)
                        event_type = data.get('type')

                        # 텍스트 컨텐츠
                        if event_type == 'content_block_delta':
                            delta = data.get('delta', {})
                            if delta.get('type') == 'text_delta':
                                text = delta.get('text', '')
                                print(text, end="", flush=True)
                                current_message_content.append({"type": "text", "text": text})
                            elif delta.get('type') == 'input_json_delta':
                                # Tool Use JSON 조각 수신
                                tool_json_accumulated += delta.get('partial_json', '')

                        # Tool Use 시작
                        elif event_type == 'content_block_start':
                            content_block = data.get('content_block', {})
                            if content_block.get('type') == 'tool_use':
                                tool_use_block = content_block
                                tool_json_accumulated = ""
                                print(f"\n🔨 도구 호출: {tool_use_block.get('name')}...", end="", flush=True)

                        # Tool Use 종료
                        elif event_type == 'content_block_stop':
                            if tool_use_block:
                                # JSON 파싱 시도
                                try:
                                    tool_input = json.loads(tool_json_accumulated)
                                    tool_use_block['input'] = tool_input
                                    current_message_content.append(tool_use_block)
                                    tool_use_block = None # 리셋
                                except json.JSONDecodeError:
                                    print("\n⚠️ 도구 입력 파싱 실패")

                        elif event_type == 'message_delta':
                            delta = data.get('delta', {})
                            # stop_reason 확인 가능 (필요 시 처리)
                            pass

                        elif event_type == 'message_stop':
                            break
                            
                    except json.JSONDecodeError:
                        continue
        except (requests.exceptions.ChunkedEncodingError, 
                requests.exceptions.ConnectionError, 
                requests.exceptions.ReadTimeout) as e:
            # 스트림 중단 예외 처리
            print(f"\n\n[⚠️ 스트리밍 중단됨: {str(e)}]")
            error_msg = "\n[⚠️ 네트워크 오류로 인해 응답이 중단되었습니다.]"
            current_message_content.append({"type": "text", "text": error_msg})
        except Exception as e:
            # 기타 예외
            print(f"\n\n[❌ 스트리밍 오류: {str(e)}]")
            error_msg = f"\n[❌ 오류 발생: {str(e)}]"
            current_message_content.append({"type": "text", "text": error_msg})

        print("\n")

        # 텍스트 합치기 (단순 문자열 반환용)
        full_text = "".join([c['text'] for c in current_message_content if c['type'] == 'text'])
        
        # 히스토리 업데이트 (User)
        self.conversation_history.append({"role": "user", "content": user_message})
        
        # AI 응답 (Assistant) - 텍스트 + Tool Use 블록 포함
        # 주의: Claude API는 content가 리스트일 수 있음
        assistant_content = []
        text_accumulator = ""
        
        for item in current_message_content:
            if item.get('type') == 'text':
                text_accumulator += item['text']
            elif item.get('type') == 'tool_use':
                if text_accumulator:
                    assistant_content.append({"type": "text", "text": text_accumulator})
                    text_accumulator = ""
                assistant_content.append(item)
        
        if text_accumulator:
             assistant_content.append({"type": "text", "text": text_accumulator})

        self.conversation_history.append({"role": "assistant", "content": assistant_content})

        # 도구 실행 및 결과 전송 (재귀 호출)
        tool_results = []
        for content_block in assistant_content:
            if content_block.get('type') == 'tool_use':
                tool_name = content_block.get('name')
                tool_id = content_block.get('id')
                tool_input = content_block.get('input')
                
                print(f"⚙️  도구 실행 중: {tool_name} {tool_input}")
                result = self._execute_tool(tool_name, tool_input)
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": str(result)
                })
        
        if tool_results:
            # 도구 결과를 User 메시지로 보냄 (role: user)
            self.conversation_history.append({"role": "user", "content": tool_results})
            print("📤 도구 결과 전송 중...")
            
            # 재귀 호출로 후속 응답 받기
            # 도구 결과 전송 시에는 user_message가 아닌 tool_results가 마지막 메시지이므로
            # API 호출만 다시 수행 (chat 메서드 재귀 호출 대신 _chat_streaming 내부 로직 재사용 필요하나,
            # 구조상 chat을 다시 부르되 user_message 없이 history만 사용하는 방식이 적절)
            
            # 여기서 chat 메서드를 다시 호출하고 싶지만, chat 메서드는 user_message를 히스토리에 추가해버림.
            # 해결책: _follow_up_chat 메서드 신설 또는 _chat_streaming 재귀 (api_url 등 인자 필요)
            
            next_body = body.copy()
            next_body['messages'] = list(self.conversation_history)
            return self._chat_streaming(api_url, next_body, "") # original_message는 이미 추가됨

        return full_text

    def _chat_non_streaming(self, api_url: str, body: Dict, original_message: str) -> str:
        """논스트리밍 모드 채팅 (Tool Use 지원)"""
        # 재시도 로직 적용
        response = APIRetry.retry_request(
            requests.post, api_url, headers=self.headers, json=body
        )

        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            return ""

        result = response.json()
        content_blocks = result.get('content', [])
        
        # 화면 출력 및 텍스트 추출
        full_text = ""
        for block in content_blocks:
            if block.get('type') == 'text':
                text = block.get('text', '')
                print(f"\n🤖 AI: {text}\n")
                full_text += text
            elif block.get('type') == 'tool_use':
                print(f"\n🔨 도구 호출: {block.get('name')}")
        
        # 히스토리 추가
        if original_message: # 후속 호출 시에는 비어있을 수 있음
            self.conversation_history.append({"role": "user", "content": original_message})
            
        self.conversation_history.append({"role": "assistant", "content": content_blocks})

        # 도구 실행 확인
        if result.get('stop_reason') == 'tool_use':
            tool_results = []
            for block in content_blocks:
                if block.get('type') == 'tool_use':
                    tool_name = block.get('name')
                    tool_id = block.get('id')
                    tool_input = block.get('input')
                    
                    print(f"⚙️  도구 실행: {tool_name}")
                    exec_result = self._execute_tool(tool_name, tool_input)
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": str(exec_result)
                    })
            
            if tool_results:
                self.conversation_history.append({"role": "user", "content": tool_results})
                print("📤 도구 결과 전송 및 후속 응답 대기...")
                
                next_body = body.copy()
                next_body['messages'] = list(self.conversation_history)
                # 재귀 호출 (original_message는 빈 문자열)
                return self._chat_non_streaming(api_url, next_body, "")

        return full_text

    # 기존 메서드 호환성 유지 (chat 메서드 내에서 호출됨)
    # extract_and_save_files는 이전과 동일하게 유지
    def extract_and_save_files(self, response: str) -> List[str]:
        """
        AI 응답에서 ````filename:```` 로 시작하는 파일 블록을 추출하여 저장합니다.
        파일 내용에 내부 코드 블록(```python, ``` 등)이 포함되어 있어도
        올바르게 전체 내용을 캡처하도록 라인 기반 파서를 사용합니다.
        """
        return self.response_parser.parse_and_save(response)

    def save_history(self, filepath: Optional[str] = None) -> str:
        """대화 히스토리를 JSON 파일로 저장"""
        return self.history_manager.save_claude_history(
            self.conversation_history, self.model_id, filepath
        )
    
    def load_history(self, filepath: str) -> bool:
        """JSON 파일에서 대화 히스토리 로드"""
        data = self.history_manager.load_history(filepath)
        if data and data.get("type") == "claude":
            self.conversation_history = data.get("messages", [])
            return True
        return False
    
    def list_history(self) -> List[str]:
        """저장된 히스토리 파일 목록"""
        return self.history_manager.list_history_files()
