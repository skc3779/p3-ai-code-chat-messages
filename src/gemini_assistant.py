"""
GeminiCodeAssistant - Google Gemini API 코딩 어시스턴트 모듈
(REST API 직접 호출)
"""

import json
import os
import re
from typing import List, Dict, Optional, Any
from pathlib import Path

import requests
# pyrefly: ignore [missing-import]
import sseclient

from .os_utils import get_os_shell_hint as _get_os_shell_hint
from .file_manager import FileManager
from .context_builder import ContextBuilder
from .code_executor import CodeExecutor
from .terminal_executor import TerminalExecutor
from .git_manager import GitManager
from .package_manager import PackageManager
from .token_manager import TokenManager
from .api_logger import ApiLogger
from .api_retry import APIRetry
from .history_manager import HistoryManager
from .template_manager import TemplateManager
from .prompt_renderer import PromptRenderer
from .spinner import WaitSpinner
from .response_parser import ResponseParser


# FSD v1.0.161: `.system_prompts/gemini-system-prompt.yaml` 미존재 시의 비상용 fallback.
# 정상 경로는 YAML 자산이며, 본 상수는 빌드물에 자산이 동봉되지 않은 경우의 안전망.
_BUILTIN_FALLBACK_GEMINI = """당신은 Google의 최첨단 AI 모델인 Gemini를 기반으로 한, 세계 최고 수준의 전문 소프트웨어 엔지니어 및 코딩 어시스턴트입니다.

[역할 및 태도]
- 사용자의 코딩 문제를 해결하고, 프로젝트 구조를 분석하며, 최적의 솔루션을 제안합니다.
- 답변은 전문적이고 논리적이며, 불필요한 서두 없이 본론으로 바로 들어갑니다.
- 복잡한 개념은 명확하고 간결하게 설명합니다.
- 사용자가 별도로 요청하지 않는 한 항상 한국어로 답변합니다.

[코드 작성 규칙]
1. 항상 최신 언어 표준과 모범 사례(Best Practices)를 따릅니다.
2. 코드는 가독성이 높아야 하며, 중요한 로직에는 명확한 주석을 답니다.
3. 변수명과 함수명은 직관적이고 의미 있게 작명합니다.
4. 에러 처리와 예외 상황을 고려하여 견고한 코드를 작성합니다.

[파일 생성 및 수정]
사용자가 코드 작성을 요청하거나 파일을 수정해야 할 경우, 반드시 다음 형식을 엄격히 준수해야 합니다. 이 형식은 시스템이 파일을 자동으로 생성하는 데 사용되므로 절대 변경하면 안 됩니다.

@@@filename:경로/파일명.확장자
코드 내용...
@@@

- 예시:
@@@filename:src/utils.py
def add(a, b):
    return a + b
@@@

- 주의사항:
    - 파일 생성 요청이 있으면 코드블럭은 반드시 `@@@filename:경로/파일명.확장자` 시작하고 `@@@` 으로 끝나야함
    - `@@@filename:` 뒤에 공백 없이 바로 경로 및 파일명을 작성하세요.
    - 여러 파일을 생성할 때는 각 파일마다 별도의 코드 블록을 작성하세요.
    - 기존 파일을 수정할 때는 변경된 부분만이 아니라 파일 전체 코드를 제공하는 것이 좋습니다.

[문서 작성]
- 기술 문서는 markdown 형식으로 깔끔하게 정리합니다.
- 이모지(Emoji)와 같은 기호는 사용하지 말고, 전문적인 어조를 유지합니다.

[실행 환경]
{{os_shell_hint}}

이제 사용자의 요청을 듣고 최고의 코딩 지원을 제공하세요.
"""


class GeminiCodeAssistant:
    """Google Gemini API 코딩 어시스턴트 (REST API 직접 호출)"""
    
    def __init__(
        self, 
        api_key: str, 
        model_id: str = "gemini-3.0-flash",
        workspace_dir: str = ".",
        endpoint_url: str = "https://aiplatform.googleapis.com/v1/publishers/google/models/"
    ):
        self.api_key = api_key
        self.endpoint_url = endpoint_url
        self.model_id = model_id
        self.headers = {
            "Content-Type": "application/json"
        }
        
        # API 로거 초기화 (Provider 명시)
        self.api_logger = ApiLogger("gemini", workspace_dir)
        self.conversation_history: List[Dict] = []
        
        # 공용 모듈 초기화 (Claude/GenAI와 동일)
        self.file_manager = FileManager(workspace_dir)
        self.context_builder = ContextBuilder(self.file_manager, max_tokens=TokenManager.MAX_TOKENS_GEMINI)
        self.code_executor = CodeExecutor(self.file_manager.workspace_dir)
        self.terminal_executor = TerminalExecutor(self.file_manager.workspace_dir)
        self.git_manager = GitManager(self.file_manager.workspace_dir)
        self.package_manager = PackageManager(self.file_manager.workspace_dir)
        self.history_manager = HistoryManager(self.file_manager.workspace_dir)
        self.template_manager = TemplateManager(self.file_manager.workspace_dir)
        self.response_parser = ResponseParser(self.file_manager)

        # FSD v1.0.161: 기본 시스템 프롬프트를 .system_prompts YAML 에서 로드
        default_name = os.getenv("DEFAULT_GEMINI_TEMPLATE") or "gemini-system-prompt"
        self._default_template_name = default_name
        # FSD v1.0.161 [ADD]: /template_show 용 — 현재 적용 중인 템플릿 이름 추적
        self._active_template_name = default_name
        raw = self.template_manager.resolve_default_template(default_name, "gemini")
        if raw is None:
            print(f"⚠️ 기본 템플릿 '{default_name}' 을 찾지 못해 내장 fallback 을 사용합니다.")
            raw = _BUILTIN_FALLBACK_GEMINI
        self._raw_system_prompt = raw
        self._active_raw_system_prompt = raw

        self.default_system_prompt = self._render_system_prompt(raw)
        self.system_prompt = self.default_system_prompt

    def _build_template_context(self) -> Dict[str, str]:
        """렌더 컨텍스트 — 현재는 os_shell_hint 만 제공.
        향후 변수 추가는 이 메서드에 한 줄씩 추가하면 된다."""
        return {
            "os_shell_hint": _get_os_shell_hint(),
        }

    def _render_system_prompt(self, raw: Optional[str] = None) -> str:
        """현재 컨텍스트로 raw 프롬프트의 {{변수}} 를 치환한 최종 본문을 반환."""
        if raw is None:
            raw = getattr(self, "_active_raw_system_prompt", None) or getattr(self, "system_prompt", "")
        ctx = self._build_template_context()
        return PromptRenderer.render(raw, ctx, on_missing="keep")

    def set_system_prompt_from_template(self, template_name: str) -> bool:
        """템플릿으로 시스템 프롬프트 변경 (FSD v1.0.161: 변수 치환 적용)"""
        raw = self.template_manager.get_system_prompt(template_name, "gemini")
        if raw is None:
            return False
        self._active_raw_system_prompt = raw
        self._active_template_name = template_name  # FSD v1.0.161 [ADD]
        self.system_prompt = self._render_system_prompt(raw)
        return True

    def reset_system_prompt(self) -> None:
        """기본 시스템 프롬프트로 복원"""
        self._active_raw_system_prompt = self._raw_system_prompt
        self._active_template_name = self._default_template_name  # FSD v1.0.161 [ADD]
        self.system_prompt = self.default_system_prompt

    def list_templates(self) -> List[Dict[str, str]]:
        """사용 가능한 템플릿 목록 (FSD v1.0.161 [ADD]: assistant_type 으로 필터링)"""
        return self.template_manager.list_templates(assistant_type="gemini")

    def get_active_template_info(self) -> Dict[str, str]:
        """
        FSD v1.0.161 [ADD]: 현재 적용 중인 템플릿의 메타정보를 반환한다.
        반환 키: name, description, assistant_type. 메타가 없으면 fallback 표시.
        """
        name = getattr(self, "_active_template_name", "(unknown)")
        info = self.template_manager.get_template_info(name)
        if info:
            return info
        return {
            "name": name,
            "description": "(메타정보를 찾을 수 없음 — 빌트인 fallback 사용 중일 수 있음)",
            "assistant_type": "gemini",
        }

    def chat(
        self, 
        user_message: str, 
        streaming: bool = True,
        include_context: bool = False,
        file_patterns: Optional[List[str]] = None,
        *,
        include_tree: bool = True,
    ) -> str:
        """AI와 채팅"""
        # 컨텍스트 구성
        if include_context:
            context = self.context_builder.build_context(
                include_tree=include_tree,
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
        import time as _time
        api_url = f"{self.endpoint_url}/models/{self.model_id}:streamGenerateContent?alt=sse&key={self.api_key}"
        # FSD v1.0.161: 요청 본문 구성 직전에 {{변수}} 재치환
        self.system_prompt = self._render_system_prompt()
        body = self._build_request_body(user_message)
        
        # REQ-064-006: Request 로그 저장
        _start = _time.time()
        log_id = self.api_logger.log_request(
            api_url=api_url, headers=self.headers,
            body=body, streaming=True, model_id=self.model_id
        )

        # REQ-066-004: 대기 스피너 시작
        spinner = WaitSpinner()
        spinner.start()

        # 재시도 로직 적용
        response = APIRetry.retry_request(
            requests.post, api_url, headers=self.headers, json=body, stream=True
        )
        
        if response.status_code != 200:
            spinner.stop() # 에러 발생 시 스피너 즉시 종료
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            # REQ-064-006: 에러 Response 로그 저장
            self.api_logger.log_response(
                log_id=log_id, status_code=response.status_code,
                streaming=True, assembled_content=response.text,
                elapsed_ms=int((_time.time() - _start) * 1000)
            )
            return ""
        
        client = sseclient.SSEClient(response)
        result_message = ""
        is_first_chunk = True

        try:
            for event in client.events():
                if is_first_chunk:
                    spinner.stop() # 첫 응답 시작 시 스피너 종료
                    print(f"\n🤖 AI: ", end="", flush=True)
                    is_first_chunk = False
                    
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
            spinner.stop()
            print(f"\n\n[⚠️ 스트리밍 중단됨: {str(e)}]")
        
        print("\n")
        
        # REQ-064-006: 스트리밍 Response 로그 저장
        self.api_logger.log_response(
            log_id=log_id, status_code=response.status_code,
            streaming=True, assembled_content=result_message,
            chunk_count=1, # 단위 측정 불가하므로 임의 1 할당 또는 패킷 카운트 대체
            elapsed_ms=int((_time.time() - _start) * 1000)
        )

        # 히스토리에 추가
        self.conversation_history.append({"role": "user", "content": user_message})
        if result_message:
            self.conversation_history.append({"role": "model", "content": result_message})
        
        return result_message

    def _chat_non_streaming(self, user_message: str) -> str:
        """논스트리밍 모드 채팅"""
        import time as _time
        api_url = f"{self.endpoint_url}/models/{self.model_id}:generateContent?key={self.api_key}"
        # FSD v1.0.161: 요청 본문 구성 직전에 {{변수}} 재치환
        self.system_prompt = self._render_system_prompt()
        body = self._build_request_body(user_message)
        
        # REQ-064-006: Request 로그 저장
        _start = _time.time()
        log_id = self.api_logger.log_request(
            api_url=api_url, headers=self.headers,
            body=body, streaming=False, model_id=self.model_id
        )

        # REQ-066-004: 논스트리밍 대기 스피너 시작
        spinner = WaitSpinner()
        spinner.start()

        # 재시도 로직 적용
        response = APIRetry.retry_request(
            requests.post, api_url, headers=self.headers, json=body
        )
        
        spinner.stop() # 응답 완료 시 스피너 종료
        
        if response.status_code != 200:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            # REQ-064-006: 에러 Response 로그 저장
            self.api_logger.log_response(
                log_id=log_id, status_code=response.status_code,
                streaming=False, response_body={"error": response.text},
                elapsed_ms=int((_time.time() - _start) * 1000)
            )
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
        
        # REQ-064-006: 논스트리밍 Response 로그 저장
        self.api_logger.log_response(
            log_id=log_id, status_code=response.status_code,
            streaming=False, response_body=result,
            elapsed_ms=int((_time.time() - _start) * 1000)
        )

        # 히스토리에 추가
        self.conversation_history.append({"role": "user", "content": user_message})
        if content:
            self.conversation_history.append({"role": "model", "content": content})
        
        return content

    def change_workspace(self, new_workspace_dir: str) -> bool:
        """작업 디렉토리를 변경하고 관련 내부 참조를 모두 갱신합니다."""
        new_path = Path(new_workspace_dir).resolve()

        if not new_path.exists() or not new_path.is_dir():
            return False

        self.file_manager = FileManager(str(new_path))
        self.context_builder = ContextBuilder(self.file_manager, max_tokens=TokenManager.MAX_TOKENS_GEMINI)
        self.code_executor = CodeExecutor(self.file_manager.workspace_dir)
        self.terminal_executor = TerminalExecutor(self.file_manager.workspace_dir)
        self.git_manager = GitManager(self.file_manager.workspace_dir)
        self.package_manager = PackageManager(self.file_manager.workspace_dir)
        self.history_manager = HistoryManager(self.file_manager.workspace_dir)
        self.template_manager = TemplateManager(self.file_manager.workspace_dir)
        self.response_parser = ResponseParser(self.file_manager)

        return True

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
