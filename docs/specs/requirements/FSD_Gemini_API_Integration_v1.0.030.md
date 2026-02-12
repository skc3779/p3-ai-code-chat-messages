# FSD: Gemini API 통합 (P4-06)

> **문서 버전**: v1.0.030  
> **작성일**: 2026-02-06  
> **상태**: Draft  
> **관련 SRS**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md

---

## 1. 개요

### 1.1 목적
Google Gemini API를 지원하여 사용자가 Claude, GenAI, Gemini 중 원하는 LLM을 선택할 수 있도록 합니다. 기존 아키텍처를 유지하면서 새로운 LLM 백엔드를 추가합니다.

### 1.2 배경
- 현재 시스템은 Claude API와 커스텀 GenAI API를 지원
- 사용자들이 Google Gemini (특히 Gemini 3.0 Flash, Gemini 3.0 Pro)를 요청
- 멀티 LLM 지원으로 비용 최적화 및 기능 비교 가능

### 1.3 범위
- Gemini API 통합 모듈 개발
- 스트리밍/논스트리밍 모드 지원
- Tool Use (Function Calling) 지원
- 기존 명령어와 동일한 사용자 경험 제공

---

## 2. 기능 요구사항

### 2.1 핵심 기능

| ID | 기능 | 설명 | 우선순위 |
|----|------|------|----------|
| F-01 | 기본 채팅 | Gemini API를 통한 대화 기능 | 필수 |
| F-02 | 스트리밍 응답 | Server-Sent Events 기반 실시간 응답 출력 | 필수 |
| F-03 | Tool Use | 파일 읽기/쓰기, Git 등 도구 자동 실행 | 필수 |
| F-04 | 토큰 관리 | 대화 히스토리 자동 트리밍 | 필수 |
| F-05 | 히스토리 저장/로드 | 대화 세션 영속화 | 필수 |
| F-06 | 템플릿 지원 | 시스템 프롬프트 템플릿 적용 | 필수 |

### 2.2 명령어 호환성

Gemini 어시스턴트는 기존 Claude/GenAI 어시스턴트와 동일한 명령어를 지원해야 합니다:

```
/context, /read, /save, /diff, /apply, /run, /shell, /shell!
/files, /tree, /workspace, /history, /clear, /tokens
/save_history, /load_history, /list_history
/template, /template_list, /template_reset
/watch, /unwatch, /watch_list
/stream, /nostream, /multiline, /help, /quit
```

---

## 3. 기술 설계

### 3.1 아키텍처

```
gemini-ai-chat-code01.py (Entry Point) [신규]
├── src/gemini_assistant.py (GeminiCodeAssistant) [신규]
│   ├── src/file_manager.py (FileManager) [기존]
│   ├── src/context_builder.py (ContextBuilder) [기존]
│   ├── src/code_executor.py (CodeExecutor) [기존]
│   ├── src/terminal_executor.py (TerminalExecutor) [기존]
│   ├── src/git_manager.py (GitManager) [기존]
│   ├── src/package_manager.py (PackageManager) [기존]
│   ├── src/diff_viewer.py (DiffViewer) [기존]
│   ├── src/history_manager.py (HistoryManager) [기존]
│   ├── src/template_manager.py (TemplateManager) [기존]
│   └── src/tool_definitions.py (FILESYSTEM_TOOLS) [기존]
```

### 3.2 Gemini API 사양 (REST API 직접 호출)

Claude 어시스턴트와 동일하게 `requests` 및 `sseclient-py` 라이브러리를 사용하여 Gemini REST API를 직접 호출합니다. SDK 의존성 없이 표준 HTTP 요청으로 구현합니다.

**필요 라이브러리** (기존 설치됨):
```bash
pip install requests sseclient-py python-dotenv
```

**환경변수**:
```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL_ID=gemini-3.0-flash
GEMINI_API_ENDPOINT=https://generativelanguage.googleapis.com/v1beta
```

**API 엔드포인트 형식**:
| 기능 | 엔드포인트 |
|------|-----------|
| 논스트리밍 | `{endpoint}/models/{model}:generateContent?key={api_key}` |
| 스트리밍 | `{endpoint}/models/{model}:streamGenerateContent?alt=sse&key={api_key}` |

### 3.3 핵심 클래스 설계

#### 3.3.1 GeminiCodeAssistant 클래스 (REST API 직접 호출)

```python
# src/gemini_assistant.py

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
- 반드시 ```filename: 형식을 사용하세요
- 여러 파일은 각각 별도의 코드 블록으로 작성하세요
- 파일 경로는 프로젝트 루트 기준 상대 경로를 사용하세요"""
        
        self.system_prompt = self.default_system_prompt

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
        if streaming:
            return self._chat_streaming(full_message)
        else:
            return self._chat_non_streaming(full_message)

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
                "maxOutputTokens": 4096,
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
```

### 3.4 대화 히스토리 형식

**Gemini REST API 형식**:
```python
# 요청 본문의 contents 배열
[
    {"role": "user", "parts": [{"text": "Hello"}]},
    {"role": "model", "parts": [{"text": "Hi there!"}]}
]
```

**내부 저장 형식** (Claude/GenAI와 유사):
```python
[
    {"role": "user", "content": "Hello"},
    {"role": "model", "content": "Hi there!"}
]
```

**API 비교 (REST 요청 기준)**:
| 항목 | Claude API | Gemini API |
|------|------------|------------|
| 인증 | `x-api-key` 헤더 | `?key=` 쿼리 파라미터 |
| 사용자 역할 | `role: "user"` | `role: "user"` |
| AI 역할 | `role: "assistant"` | `role: "model"` |
| 시스템 프롬프트 | `system` 필드 | `systemInstruction` 필드 |
| 메시지 내용 | `content` 문자열 | `parts[].text` |
| 스트리밍 | `stream: true` | `?alt=sse` 쿼리 |

### 3.5 스트리밍 응답 처리

**Gemini SSE 응답 형식**:
```json
{
  "candidates": [
    {
      "content": {
        "parts": [{"text": "응답 텍스트 청크"}],
        "role": "model"
      }
    }
  ]
}
```

**처리 로직**:
```python
for event in sseclient.SSEClient(response).events():
    data = json.loads(event.data)
    for candidate in data.get('candidates', []):
        for part in candidate.get('content', {}).get('parts', []):
            text = part.get('text', '')
            print(text, end="", flush=True)
```

### 3.6 토큰 관리

**Gemini 토큰 한도**:
| 모델 | 입력 토큰 | 출력 토큰 |
|------|----------|----------|
| gemini-3.0-flash | 1,048,576 | 8,192 |
| gemini-3.0-pro | 2,097,152 | 8,192 |

**TokenManager 확장**:
```python
class TokenManager:
    MAX_TOKENS_CLAUDE = 180000
    MAX_TOKENS_GENAI = 100000
    MAX_TOKENS_GEMINI = 900000  # 신규: 안전 마진 포함
```

---

## 4. 파일 구조

### 4.1 신규 파일

| 파일 | 설명 |
|------|------|
| `gemini-ai-chat-code01.py` | Gemini 어시스턴트 Entry Point |
| `src/gemini_assistant.py` | GeminiCodeAssistant 클래스 |
| `tests/test_gemini_tool_use.py` | Gemini Tool Use 테스트 |
| `README-gemini-ai-chat-code01.md` | Gemini 어시스턴트 문서 |

### 4.2 수정 파일

| 파일 | 변경 사항 |
|------|-----------|
| `src/__init__.py` | GeminiCodeAssistant import 추가 |
| `src/token_manager.py` | MAX_TOKENS_GEMINI 상수 추가 |
| `src/history_manager.py` | save_gemini_history 메서드 추가 |
| `README.md` | Gemini 어시스턴트 설명 추가 |

---

## 5. 환경 설정

### 5.1 .env 파일

프로젝트 루트에 `.env` 파일을 생성하고 Gemini API 키를 설정합니다:

```env
# Gemini API 설정
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL_ID=gemini-3.0-flash

# 선택적 설정
# GEMINI_PROJECT_ID=your-project-id  # Vertex AI 사용 시
# GEMINI_LOCATION=us-central1         # Vertex AI 사용 시
```

### 5.2 python-dotenv를 사용한 환경변수 로드

`gemini-ai-chat-code01.py` Entry Point에서 `python-dotenv`를 사용하여 `.env` 파일을 로드합니다:

```python
# gemini-ai-chat-code01.py

import os
from dotenv import load_dotenv
from src.gemini_assistant import GeminiCodeAssistant
from src.diff_viewer import DiffViewer
from src.cli_input import CLIInputHandler

# .env 파일 로드
load_dotenv()

def main():
    # 환경변수에서 API 키 및 설정 로드
    api_key = os.getenv("GEMINI_API_KEY")
    model_id = os.getenv("GEMINI_MODEL_ID", "gemini-3.0-flash")
    
    if not api_key:
        print("❌ 오류: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("💡 .env 파일에 GEMINI_API_KEY=your-api-key 를 추가하세요.")
        return
    
    # 현재 작업 디렉토리
    workspace_dir = os.getcwd()
    
    # 어시스턴트 초기화
    assistant = GeminiCodeAssistant(
        api_key=api_key,
        model_id=model_id,
        workspace_dir=workspace_dir
    )
    
    # DiffViewer 및 CLI 핸들러 초기화
    diff_viewer = DiffViewer()
    cli_handler = CLIInputHandler()
    
    print(f"🤖 Gemini Code Assistant ({model_id})")
    print(f"📂 작업 디렉토리: {workspace_dir}")
    print("💡 /help 명령어로 사용 가능한 명령어를 확인하세요.\n")
    
    streaming = True
    last_response = ""
    
    while True:
        try:
            user_input = cli_handler.get_input("👤 You: ")
            
            if not user_input:
                continue
            
            # 명령어 처리
            if user_input.startswith('/'):
                command = user_input.split()[0].lower()
                
                if command == '/quit':
                    print("👋 종료합니다.")
                    break
                    
                elif command == '/stream':
                    streaming = True
                    print("✅ 스트리밍 모드 활성화")
                    
                elif command == '/nostream':
                    streaming = False
                    print("✅ 스트리밍 모드 비활성화")
                    
                elif command == '/diff':
                    # Diff 표시 로직
                    suggestions = diff_viewer.extract_code_suggestions(last_response)
                    if suggestions:
                        for suggestion in suggestions:
                            filepath = suggestion['filepath']
                            new_content = suggestion['content']
                            diff_output = diff_viewer.generate_diff_for_file(
                                filepath, new_content, assistant.file_manager
                            )
                            print(diff_output)
                    else:
                        print("💡 표시할 코드 제안이 없습니다.")
                        
                elif command == '/apply':
                    success, message = diff_viewer.apply_diff(assistant.file_manager)
                    print(message)
                    
                # ... 기타 명령어 처리 (기존 Claude/GenAI와 동일)
                
            else:
                # 일반 채팅
                last_response = assistant.chat(user_input, streaming=streaming)
                
        except KeyboardInterrupt:
            print("\n👋 종료합니다.")
            break


if __name__ == "__main__":
    main()
```

### 5.3 requirements.txt

Gemini API는 REST API를 직접 호출하므로 추가 패키지가 필요 없습니다. 기존 라이브러리만 사용합니다:

```
# 기존 패키지로 충분 (추가 설치 불필요)
requests>=2.28.0          # HTTP 요청
sseclient-py>=1.7.2       # 스트리밍 (SSE)
python-dotenv>=1.0.0      # 환경변수 로드
```

---

## 6. 검증 계획

### 6.1 단위 테스트

| 테스트 항목 | 파일 | 설명 |
|-------------|------|------|
| 기본 채팅 | `test_gemini_tool_use.py` | 논스트리밍 응답 확인 |
| 스트리밍 | `test_gemini_tool_use.py` | 스트리밍 응답 확인 |
| Tool Use | `test_gemini_tool_use.py` | 도구 호출 및 실행 |
| 히스토리 | `test_gemini_tool_use.py` | 대화 히스토리 관리 |

### 6.2 통합 테스트

1. Gemini 어시스턴트로 파일 읽기/쓰기 요청
2. `/context` 명령어로 프로젝트 분석 요청
3. `/diff` 및 `/apply` 명령어로 코드 수정
4. `/save_history` 및 `/load_history`로 세션 관리

---

## 7. 구현 일정

| 단계 | 작업 | 예상 기간 |
|------|------|----------|
| 1 | GeminiCodeAssistant 기본 구조 | 1일 |
| 2 | 스트리밍/논스트리밍 구현 | 1일 |
| 3 | Tool Use (Function Calling) 구현 | 2일 |
| 4 | 기존 명령어 통합 | 1일 |
| 5 | 테스트 및 문서화 | 1일 |

**총 예상 기간**: 약 1주

---

## 8. 참고 자료

### 8.1 Gemini API 문서
- [Gemini API 공식 문서](https://ai.google.dev/docs)
- [Python SDK 가이드](https://github.com/googleapis/python-genai)
- [Function Calling 가이드](https://ai.google.dev/docs/function_calling)

### 8.2 관련 내부 문서
- `src/claude_assistant.py` - Claude API 구현 참조
- `src/genai_assistant.py` - GenAI API 구현 참조
- `FSD_Code_Diff_Display_v1.0.029.md` - Diff 기능 연동

---

## 9. 릴리즈 노트 작성
* `docs/specs/releases/RELEASE_v1.0.030.md`

## 10. requirements.txt 
* `requirements.txt` 파일에 구현에 필요한 패키지 추가

## 11. 버전 히스토리

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|----------|
| v1.0.030 | 2026-02-06 | AI Assistant | Gemini API 통합 FSD 초안 작성 |

