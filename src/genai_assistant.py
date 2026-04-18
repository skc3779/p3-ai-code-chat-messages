"""
GenAICodeAssistant - GenAI API 코딩 어시스턴트 모듈
(커스텀 GenAI API 사용)
"""

import json
import platform
import re
import time as _time
from typing import List, Dict, Optional
from pathlib import Path

import requests
import sseclient


def _get_os_shell_hint() -> str:
    if platform.system() == 'Windows':
        return (
            "현재 실행 환경: Windows OS.\n"
            "쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 "
            "코드 블록 언어 태그를 `powershell` 또는 `ps1`로 지정하세요. "
            "`bash`, `sh` 코드 블록은 이 환경에서 실행되지 않습니다."
        )
    return (
        f"현재 실행 환경: {platform.system()} OS.\n"
        "쉘 스크립트 작성 시 bash 구문을 사용하고 "
        "코드 블록 언어 태그를 `bash` 또는 `sh`로 지정하세요."
    )

from .file_manager import FileManager
from .context_builder import ContextBuilder
from .code_executor import CodeExecutor
from .terminal_executor import TerminalExecutor
from .git_manager import GitManager
from .package_manager import PackageManager
from .llm_config import LLMConfigProvider
from .token_manager import TokenManager
from .api_logger import ApiLogger
from .api_retry import APIRetry
from .history_manager import HistoryManager
from .template_manager import TemplateManager
from .response_parser import ResponseParser
from .sensitive_filter import SensitiveWordFilter
from .spinner import WaitSpinner

class GenAICodeAssistant:
    """GenAI API 코딩 어시스턴트 (커스텀 API)"""

    def __init__(self, endpoint_url: str, client_key: str, client_secret: str,
                 model_id: str, workspace_dir: str = "."):
        self.endpoint_url = endpoint_url
        self.headers = {
            "X-Lego-Client-Id": client_key,
            "X-Lego-Client-Secret": client_secret,
            "Content-Type": "application/json"
        }
        self.model_id = model_id
        self.conversation_history: List[Dict] = []

        self.file_manager = FileManager(workspace_dir)
        self.context_builder = ContextBuilder(self.file_manager, max_tokens=TokenManager.MAX_TOKENS_GENAI)
        self.code_executor = CodeExecutor(self.file_manager.workspace_dir)
        self.terminal_executor = TerminalExecutor(self.file_manager.workspace_dir)
        self.git_manager = GitManager(self.file_manager.workspace_dir)
        self.package_manager = PackageManager(self.file_manager.workspace_dir)
        self.package_manager = PackageManager(self.file_manager.workspace_dir)
        self.history_manager = HistoryManager(self.file_manager.workspace_dir)
        self.template_manager = TemplateManager(self.file_manager.workspace_dir)
        self.response_parser = ResponseParser(self.file_manager)

        # REQ-058-001: 민감 단어 필터 초기화
        self.sensitive_filter = SensitiveWordFilter()

        # REQ-064-001: API 로거 초기화
        self.api_logger = ApiLogger("gen-ai", workspace_dir)

        # LLM 언어 설정 (기본값 없음)
        self.llm_config = LLMConfigProvider()

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
- read_file(path)
- write_file(path, content)
- list_files()
- list_directory_tree(depth)

2. Git:
- git_status()
- git_diff(cached=True/False)
- git_log(max_count)
- git_add(files=[])
- git_commit(message)

3. 패키지:
- list_packages(language="python"|"node")

예시:
```tool_code
{"name": "read_file", "input": {"path": "src/main.py"}}
```

주의사항:
- 반드시 ```filename: 형식을 사용하세요 (```python, ```javascript 등 언어 식별자 사용 금지)
- 여러 파일은 각각 별도의 코드 블록으로 작성하세요
- 파일 경로는 프로젝트 루트 기준 상대 경로를 사용하세요
- 문서작성 시 이모지(Emoji) 사용을 하지 마세요

[실행 환경]
""" + _get_os_shell_hint()

        self.system_prompt = self.default_system_prompt

    def set_system_prompt_from_template(self, template_name: str) -> bool:
        """템플릿으로 시스템 프롬프트 변경"""
        prompt = self.template_manager.get_system_prompt(template_name, "genai")
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

    # --------------------------------------------------------------------- #
    # LLM 설정 관련 메서드
    # --------------------------------------------------------------------- #

    def get_llm_config(self) -> Dict:
        """
        LLM 파라미터를 반환합니다.
        기본값에 더해 현재 설정된 언어의 미세 조정된 파라미터를 반환합니다.
        """
        return self.llm_config.get_config()

    def set_llm_language(self, language: str) -> None:
        """
        사용자가 지정한 프로그래밍 언어에 맞춰 LLM 파라미터를 조정합니다.
        현재 구현은 언어에 따라 system_prompt에 간단히 힌트를 추가하는 형태이며,
        필요에 따라 더 정교한 프롬프트 엔지니어링을 적용이 가능합니다.
        """
        if not language: return
        self.llm_config.set_language(language.lower())

    def get_llm_language(self) -> str:
        return self.llm_config.get_language()

    def _execute_tool(self, tool_name: str, tool_input: Dict) -> str:
        """도구 실행"""
        try:
            if tool_name == "read_file":
                path = self.file_manager.workspace_dir / tool_input.get("path")
                content = self.file_manager.read_file(path)
                return content if content is not None else "파일을 찾을 수 없습니다."
            elif tool_name == "write_file":
                path = self.file_manager.workspace_dir / tool_input.get("path")
                success = self.file_manager.write_file(path, tool_input.get("content"))
                return "파일 저장 성공" if success else "파일 저장 실패"
            elif tool_name == "list_files":
                files = self.file_manager.list_files()
                return "\n".join([str(f.relative_to(self.file_manager.workspace_dir)) for f in files])
            elif tool_name == "list_directory_tree":
                return self.context_builder.build_file_tree(max_depth=tool_input.get("depth", 3))
            
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

    def process_tool_calls(self, response: str) -> str:
        """응답 내의 도구 호출을 파싱하고 실행"""
        # ```tool_code ... ``` 패턴 찾기
        pattern = r'```tool_code\s*({.*?})\s*```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        results = []
        for match in matches:
            try:
                tool_call = json.loads(match)
                name = tool_call.get("name")
                input_data = tool_call.get("input", {})
                
                print(f"\n⚙️  도구 실행: {name} {input_data}")
                result = self._execute_tool(name, input_data)
                
                result_str = f"Tool '{name}' Result:\n{result}"
                results.append(result_str)
            except json.JSONDecodeError:
                print(f"\n⚠️ 도구 JSON 파싱 실패: {match}")
                
        return "\n\n".join(results)

    def chat(self, user_message: str, streaming: bool = True,
             include_context: bool = False, file_patterns: Optional[List[str]] = None) -> str:
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

        # 토큰 관리를 위한 히스토리 자동 트리밍 (GenAI 한도 적용)
        self.conversation_history = TokenManager.auto_trim_history(
            self.conversation_history,
            max_tokens=TokenManager.MAX_TOKENS_GENAI
        )

        # API 호출 - GenAI API 형식 (contents: List[str])
        contents = [msg["content"] for msg in self.conversation_history]
        contents.append(full_message)

        # REQ-058-002: 민감 단어 치환 (GenAI 전송 전)
        masked_contents = self.sensitive_filter.mask_contents(contents)
        masked_system_prompt = self.sensitive_filter.mask_system_prompt(self.system_prompt)

        body = {
            "modelIds": [self.model_id],
            "contents": masked_contents,
            "llmConfig": self.get_llm_config(),
            "isStream": streaming,
            "systemPrompt": masked_system_prompt
        }

        api_url = f"{self.endpoint_url}/openapi/chat/v1/messages"

        try:
            response_text = ""
            if streaming:
                response_text = self._chat_streaming(api_url, body, user_message, full_message)
            else:
                response_text = self._chat_non_streaming(api_url, body, user_message, full_message)
            
            # REQ-058-005: 응답에서 치환된 단어 복원
            response_text = self.sensitive_filter.unmask(response_text)

            # 도구 호출 처리
            tool_results = self.process_tool_calls(response_text)
            if tool_results:
                print("\n📤 도구 실행 결과가 생성되었습니다.")
                self.conversation_history.append({"role": "user", "content": f"[System Tool Results]\n{tool_results}"})
                # GenAI는 자동 재귀 호출 시 무한루프 위험이 있으므로 결과만 저장하고 사용자에게 알림
                # 필요시 사용자 요청에 따라 다시 진행하기 위해 여기서는 return response_text (결과 포함 안 함)
                # 단, history에는 포함되었으므로 다음 턴에서 반영됨.
            
            return response_text

        except Exception as e:
            print(f"\n❌ API 호출 오류: {str(e)}")
            return ""

    def _chat_streaming(self, api_url: str, body: Dict,
                        user_message: str, full_message: str) -> str:
        """스트리밍 모드 채팅"""
        # REQ-062-003: Request 로그 저장
        _start = _time.time()
        log_id = self.api_logger.log_request(
            api_url=api_url, headers=self.headers,
            body=body, streaming=True, model_id=self.model_id
        )

        # REQ-066-005: 대기 스피너 시작
        spinner = WaitSpinner()
        spinner.start()

        # 재시도 로직 적용
        response = APIRetry.retry_request(
            requests.post, api_url, headers=self.headers, json=body, stream=True
        )

        if response.status_code != 200:
            spinner.stop() # 에러 발생 시 즉시 종료
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            # REQ-062-004: 에러 Response 로그 저장
            self.api_logger.log_response(
                log_id=log_id, status_code=response.status_code,
                streaming=True, assembled_content=response.text,
                elapsed_ms=int((_time.time() - _start) * 1000)
            )
            return ""

        client = sseclient.SSEClient(response)
        result_message = ""
        chunk_count = 0
        is_first_chunk = True

        for event in client.events():
            if is_first_chunk:
                spinner.stop() # 첫 응답 시작 시 스피너 종료
                print("\n🤖 AI: ", end="", flush=True)
                is_first_chunk = False
                
            if event.data:
                try:
                    data = json.loads(event.data)
                    event_status = data.get('event_status') or data.get('eventStatus')
                    content = data.get('content', '')

                    if event_status == 'CHUNK' and content:
                        print(content, end="", flush=True)
                        result_message += content
                        chunk_count += 1
                    elif event_status == 'DONE':
                        break
                except json.JSONDecodeError:
                    continue

        print("\n")

        # REQ-062-004: 스트리밍 Response 로그 저장
        self.api_logger.log_response(
            log_id=log_id, status_code=response.status_code,
            streaming=True, assembled_content=result_message,
            chunk_count=chunk_count,
            elapsed_ms=int((_time.time() - _start) * 1000)
        )

        # 히스토리에 추가
        self.conversation_history.append({"role": "user", "content": user_message})
        if result_message:
            self.conversation_history.append({"role": "model", "content": result_message})

        return result_message

    def _chat_non_streaming(self, api_url: str, body: Dict,
                            original_message: str, full_message: str) -> str:
        """논스트리밍 모드 채팅"""
        # REQ-062-003: Request 로그 저장
        _start = _time.time()
        log_id = self.api_logger.log_request(
            api_url=api_url, headers=self.headers,
            body=body, streaming=False, model_id=self.model_id
        )

        # REQ-066-005: 논스트리밍 대기 스피너 시작
        spinner = WaitSpinner()
        spinner.start()

        # 재시도 로직 적용
        response = APIRetry.retry_request(
            requests.post, api_url, headers=self.headers, json=body
        )

        spinner.stop() # 응답 완료 시 종료

        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            # REQ-062-004: 에러 Response 로그 저장
            self.api_logger.log_response(
                log_id=log_id, status_code=response.status_code,
                streaming=False, response_body={"error": response.text},
                elapsed_ms=int((_time.time() - _start) * 1000)
            )
            return ""

        result = response.json()
        content = result.get('content', '')

        # REQ-062-004: 논스트리밍 Response 로그 저장
        self.api_logger.log_response(
            log_id=log_id, status_code=response.status_code,
            streaming=False, response_body=result,
            elapsed_ms=int((_time.time() - _start) * 1000)
        )

        print(f"\n🤖 AI: {content}\n")

        # 히스토리에 추가
        self.conversation_history.append({"role": "user", "content": original_message})
        if content:
            self.conversation_history.append({"role": "model", "content": content})

        return content

    def change_workspace(self, new_workspace_dir: str) -> bool:
        """작업 디렉토리를 변경하고 관련 내부 참조를 모두 갱신합니다."""
        new_path = Path(new_workspace_dir).resolve()

        if not new_path.exists() or not new_path.is_dir():
            return False

        self.file_manager = FileManager(str(new_path))
        self.context_builder = ContextBuilder(self.file_manager, max_tokens=TokenManager.MAX_TOKENS_GENAI)
        self.code_executor = CodeExecutor(self.file_manager.workspace_dir)
        self.terminal_executor = TerminalExecutor(self.file_manager.workspace_dir)
        self.git_manager = GitManager(self.file_manager.workspace_dir)
        self.package_manager = PackageManager(self.file_manager.workspace_dir)
        self.history_manager = HistoryManager(self.file_manager.workspace_dir)
        self.template_manager = TemplateManager(self.file_manager.workspace_dir)
        self.response_parser = ResponseParser(self.file_manager)

        return True

    def extract_and_save_files(self, response: str) -> List[str]:
        """
        AI 응답에서 ````filename:```` 로 시작하는 파일 블록을 추출하여 저장합니다.
        파일 내용에 내부 코드 블록(```python, ``` 등)이 포함되어 있어도
        올바르게 전체 내용을 캡처하도록 라인 기반 파서를 사용합니다.
        """
        return self.response_parser.parse_and_save(response)

    def save_history(self, filepath: Optional[str] = None) -> str:
        """대화 히스토리를 JSON 파일로 저장"""
        return self.history_manager.save_genai_history(
            self.conversation_history, self.model_id, filepath
        )
    
    def load_history(self, filepath: str) -> bool:
        """JSON 파일에서 대화 히스토리 로드"""
        data = self.history_manager.load_history(filepath)
        if data and data.get("type") == "genai":
            raw = data.get("messages", [])
            # 구 List[str] 형식 → List[Dict] 마이그레이션
            if raw and isinstance(raw[0], str):
                self.conversation_history = [
                    {"role": "user" if i % 2 == 0 else "model", "content": msg}
                    for i, msg in enumerate(raw)
                ]
            else:
                self.conversation_history = raw
            return True
        return False
    
    def list_history(self) -> List[str]:
        """저장된 히스토리 파일 목록"""
        return self.history_manager.list_history_files()
