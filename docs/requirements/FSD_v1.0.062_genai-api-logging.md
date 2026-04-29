# FSD v1.0.062 - GenAI API 요청/응답 로깅

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.062 |
| 제목 | GenAI API 요청/응답 JSON 파일 로깅 |
| 작성일 | 2026-03-02 |
| 상태 | 설계 완료 |
| 선행 FSD | [FSD v1.0.055](./FSD_v1.0.055_genai-provider-endpoint-fix.md) -- GenAI Provider Endpoint 수정 |
|  | [FSD v1.0.058](./FSD_v1.0.058_sensitive-word-filter.md) -- 민감 단어 필터링 |
| 참조 소스 | [genai_assistant.py](../../../src/genai_assistant.py), [gen-ai-chat-code.py](../../../gen-ai-chat-code.py) |
| 수정 대상 | [genai_assistant.py](../../../src/genai_assistant.py) |
| 신규 모듈 | `src/genai_api_logger.py` |

---

## 1. 개요 (Overview)

GenAI (Samsung SCI Portal) API로 전송되는 Request Header, Request Body와 수신되는 Response를 JSON 파일로 저장하는 로깅 기능을 추가합니다.

API 디버깅, 장애 분석, 요청/응답 이력 추적을 위해 실제 API 호출 시점의 데이터를 파일로 기록합니다. 이 로깅은 `.env` 파일의 `GEN_AI_LOG_ENABLED` 플래그를 통해 켜고 끌 수 있습니다.

---

## 2. 현재 구조 분석

### 2.1 API 호출 위치 (`genai_assistant.py`)

GenAI API 호출은 `GenAICodeAssistant` 클래스의 두 메서드에서 수행됩니다:

| 메서드 | 위치 | API 호출 방식 | 설명 |
|--------|------|-------------|------|
| `_chat_streaming()` | L274-313 | `APIRetry.retry_request(requests.post, api_url, headers=self.headers, json=body, stream=True)` | 스트리밍 모드 |
| `_chat_non_streaming()` | L315-337 | `APIRetry.retry_request(requests.post, api_url, headers=self.headers, json=body)` | 논스트리밍 모드 |

### 2.2 Request 구조

```python
# Request Header (self.headers) — L34-37
headers = {
    "X-Lego-Client-Id": client_key,
    "X-Lego-Client-Secret": client_secret,
    "Content-Type": "application/json"
}

# Request Body (body) — chat() L239-245
body = {
    "modelIds": [self.model_id],
    "contents": masked_contents,        # 민감 단어 치환 후
    "llmConfig": self.get_llm_config(),
    "isStream": streaming,
    "systemPrompt": masked_system_prompt  # 민감 단어 치환 후
}

# API URL — L247
api_url = f"{self.endpoint_url}/openapi/chat/v1/messages"
```

### 2.3 Response 구조

#### 스트리밍 응답 (SSE)

```json
// 각 SSE 이벤트
{"event_status": "CHUNK", "content": "응답 텍스트 조각"}
{"event_status": "CHUNK", "content": "..."}
{"eventStatus": "DONE"}
```

#### 논스트리밍 응답

```json
{
  "content": "전체 응답 텍스트",
  "modelId": "gpt-oss-120B-medium",
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801
  }
}
```

### 2.4 환경변수 구조 (`.env`)

```env
# gen-ai-chat-code.py
ENDPOINT_URL=""
YOUR_CLIENT_KEY=""
YOUR_CLIENT_SECRET=""
YOUR_MODEL_ID=""
```

현재 `GEN_AI_LOG_ENABLED` 환경변수는 존재하지 않으며, 신규 추가가 필요합니다.

---

## 3. 설계 (Design)

### 3.1 로그 파일 구조

#### 디렉토리

```
프로젝트 루트/
└── logs/
    └── gen-ai/
        ├── gen-ai-a1b2c3d4-request-20260302195800.json
        ├── gen-ai-a1b2c3d4-response-20260302195801.json
        ├── gen-ai-e5f6g7h8-request-20260302200100.json
        └── gen-ai-e5f6g7h8-response-20260302200102.json
```

#### 파일명 형식

| 구분 | 파일명 패턴 | 예시 |
|------|-----------|------|
| Request | `gen-ai-{UUID}-request-{YYYYMMDDHHMMSS}.json` | `gen-ai-a1b2c3d4-request-20260302195800.json` |
| Response | `gen-ai-{UUID}-response-{YYYYMMDDHHMMSS}.json` | `gen-ai-a1b2c3d4-response-20260302195801.json` |

- **UUID**: `uuid.uuid4().hex[:8]` (8자리 축약 UUID, 동일 요청-응답 쌍을 연결)
- **YYYYMMDDHHMMSS**: 로그 생성 시각 (로컬 시간)

### 3.2 Request 로그 형식

```json
{
  "log_type": "request",
  "log_id": "a1b2c3d4",
  "timestamp": "2026-03-02T19:58:00+09:00",
  "api_url": "https://scisportaldev.samsungif.net/rest/genAi/openapi/chat/v1/messages",
  "method": "POST",
  "headers": {
    "X-Lego-Client-Id": "API_CLIENT_APP",
    "X-Lego-Client-Secret": "***MASKED***",
    "Content-Type": "application/json"
  },
  "body": {
    "modelIds": ["gpt-oss-120B-medium"],
    "contents": ["[User Context]\nhello.md 파일을 만들어줘"],
    "llmConfig": {
      "max_new_tokens": 10240,
      "seed": null,
      "top_k": 14,
      "top_p": 0.94,
      "temperature": 0.4,
      "repetition_penalty": 1.04
    },
    "isStream": true,
    "systemPrompt": "당신은 전문 소프트웨어 개발 어시스턴트입니다. ..."
  },
  "streaming": true,
  "model_id": "gpt-oss-120B-medium"
}
```

> **보안:** `X-Lego-Client-Secret` 헤더의 값은 `***MASKED***`로 마스킹하여 저장합니다. 원본 시크릿이 로그 파일에 노출되지 않도록 합니다.

### 3.3 Response 로그 형식

#### 논스트리밍 응답

```json
{
  "log_type": "response",
  "log_id": "a1b2c3d4",
  "timestamp": "2026-03-02T19:58:01+09:00",
  "status_code": 200,
  "streaming": false,
  "response_body": {
    "content": "전체 응답 텍스트...",
    "modelId": "gpt-oss-120B-medium",
    "usage": {
      "prompt_tokens": 1234,
      "completion_tokens": 567,
      "total_tokens": 1801
    }
  },
  "elapsed_ms": 3250
}
```

#### 스트리밍 응답

```json
{
  "log_type": "response",
  "log_id": "a1b2c3d4",
  "timestamp": "2026-03-02T19:58:01+09:00",
  "status_code": 200,
  "streaming": true,
  "assembled_content": "전체 조립된 응답 텍스트...",
  "chunk_count": 42,
  "elapsed_ms": 5120
}
```

### 3.4 모듈 설계

#### 3.4.1 `GenAIApiLogger` 클래스 (`src/genai_api_logger.py`)

```python
import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class GenAIApiLogger:
    """
    GenAI API 요청/응답을 JSON 파일로 로깅하는 모듈.
    FSD v1.0.062 / REQ-062-001~008
    """

    LOG_DIR = "logs/gen-ai"

    def __init__(self, workspace_dir: str = "."):
        """
        Args:
            workspace_dir: 프로젝트 루트 디렉토리 (logs 폴더의 기준 경로)
        """
        self.workspace_dir = Path(workspace_dir)
        self.enabled = self._check_enabled()
        self.log_dir = self.workspace_dir / self.LOG_DIR
        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _check_enabled() -> bool:
        """환경변수 GEN_AI_LOG_ENABLED를 확인하여 로깅 활성화 여부를 반환."""
        value = os.getenv("GEN_AI_LOG_ENABLED", "false")
        return value.lower() in ("true", "1", "yes")

    def _generate_log_id(self) -> str:
        """고유 로그 ID 생성 (UUID 8자리)."""
        return uuid.uuid4().hex[:8]

    def _get_timestamp(self) -> str:
        """현재 시각을 ISO 형식 문자열로 반환."""
        return datetime.now().astimezone().isoformat()

    def _get_file_timestamp(self) -> str:
        """파일명용 타임스탬프 (YYYYMMDDHHMMSS)."""
        return datetime.now().strftime("%Y%m%d%H%M%S")

    def _mask_headers(self, headers: Dict) -> Dict:
        """보안: Secret 헤더 값을 마스킹."""
        masked = dict(headers)
        for key in masked:
            if "secret" in key.lower():
                masked[key] = "***MASKED***"
        return masked

    def _save_log(self, filename: str, data: dict) -> Optional[str]:
        """JSON 로그 파일 저장."""
        if not self.enabled:
            return None
        filepath = self.log_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(filepath)

    def log_request(self, api_url: str, headers: Dict, body: Dict,
                    streaming: bool, model_id: str,
                    log_id: str = None) -> str:
        """
        Request 로그를 JSON 파일로 저장.

        Returns:
            log_id: 동일 요청-응답 쌍을 연결하는 고유 ID
        """
        if not self.enabled:
            return log_id or ""

        if not log_id:
            log_id = self._generate_log_id()

        ts = self._get_file_timestamp()
        filename = f"gen-ai-{log_id}-request-{ts}.json"

        data = {
            "log_type": "request",
            "log_id": log_id,
            "timestamp": self._get_timestamp(),
            "api_url": api_url,
            "method": "POST",
            "headers": self._mask_headers(headers),
            "body": body,
            "streaming": streaming,
            "model_id": model_id,
        }

        self._save_log(filename, data)
        return log_id

    def log_response(self, log_id: str, status_code: int,
                     streaming: bool, response_body: dict = None,
                     assembled_content: str = None,
                     chunk_count: int = 0,
                     elapsed_ms: int = 0) -> Optional[str]:
        """
        Response 로그를 JSON 파일로 저장.

        Returns:
            저장된 파일 경로 (비활성화 시 None)
        """
        if not self.enabled:
            return None

        ts = self._get_file_timestamp()
        filename = f"gen-ai-{log_id}-response-{ts}.json"

        data = {
            "log_type": "response",
            "log_id": log_id,
            "timestamp": self._get_timestamp(),
            "status_code": status_code,
            "streaming": streaming,
            "elapsed_ms": elapsed_ms,
        }

        if streaming:
            data["assembled_content"] = assembled_content
            data["chunk_count"] = chunk_count
        else:
            data["response_body"] = response_body

        return self._save_log(filename, data)
```

### 3.5 적용 위치 (`genai_assistant.py`)

#### 3.5.1 초기화 (`__init__`)

```diff
+from .genai_api_logger import GenAIApiLogger

 def __init__(self, endpoint_url, client_key, client_secret, model_id, workspace_dir="."):
     ...
+    # REQ-062-001: API 로거 초기화
+    self.api_logger = GenAIApiLogger(workspace_dir)
```

#### 3.5.2 `_chat_streaming()` 메서드

```diff
 def _chat_streaming(self, api_url, body, user_message, full_message):
+    # REQ-062-003: Request 로그 저장
+    import time as _time
+    _start = _time.time()
+    log_id = self.api_logger.log_request(
+        api_url=api_url, headers=self.headers,
+        body=body, streaming=True, model_id=self.model_id
+    )

     response = APIRetry.retry_request(
         requests.post, api_url, headers=self.headers, json=body, stream=True
     )

     if response.status_code != 200:
         print(f"\n❌ API Error: {response.status_code} - {response.text}")
+        # REQ-062-004: 에러 Response 로그 저장
+        self.api_logger.log_response(
+            log_id=log_id, status_code=response.status_code,
+            streaming=True, assembled_content=response.text,
+            elapsed_ms=int((_time.time() - _start) * 1000)
+        )
         return ""

     client = sseclient.SSEClient(response)
     result_message = ""
+    chunk_count = 0
     ...

     for event in client.events():
         if event.data:
             ...
             if event_status == 'CHUNK' and content:
                 result_message += content
+                chunk_count += 1
             elif event_status == 'DONE':
                 break

+    # REQ-062-004: 스트리밍 Response 로그 저장
+    self.api_logger.log_response(
+        log_id=log_id, status_code=response.status_code,
+        streaming=True, assembled_content=result_message,
+        chunk_count=chunk_count,
+        elapsed_ms=int((_time.time() - _start) * 1000)
+    )

     return result_message
```

#### 3.5.3 `_chat_non_streaming()` 메서드

```diff
 def _chat_non_streaming(self, api_url, body, original_message, full_message):
+    import time as _time
+    _start = _time.time()
+    log_id = self.api_logger.log_request(
+        api_url=api_url, headers=self.headers,
+        body=body, streaming=False, model_id=self.model_id
+    )

     response = APIRetry.retry_request(
         requests.post, api_url, headers=self.headers, json=body
     )

     if response.status_code != 200:
+        self.api_logger.log_response(
+            log_id=log_id, status_code=response.status_code,
+            streaming=False, response_body={"error": response.text},
+            elapsed_ms=int((_time.time() - _start) * 1000)
+        )
         ...

     result = response.json()
+    # REQ-062-004: 논스트리밍 Response 로그 저장
+    self.api_logger.log_response(
+        log_id=log_id, status_code=response.status_code,
+        streaming=False, response_body=result,
+        elapsed_ms=int((_time.time() - _start) * 1000)
+    )

     return content
```

### 3.6 환경변수 설정 (`.env`)

```diff
 # gen-ai-chat-code.py
 ENDPOINT_URL=""
 YOUR_CLIENT_KEY=""
 YOUR_CLIENT_SECRET=""
 YOUR_MODEL_ID=""
+
+# GenAI API 로깅 (true: 켜기 / false: 끄기)
+GEN_AI_LOG_ENABLED=false
```

### 3.7 처리 흐름

```
사용자 입력
    │
    ▼
chat() — body 구성
    │
    ├─ 민감 단어 치환 (REQ-058)
    │
    ▼
_chat_streaming() 또는 _chat_non_streaming()
    │
    ├─[1] GEN_AI_LOG_ENABLED 확인
    │     ├─ false → 로깅 스킵 (성능 영향 없음)
    │     └─ true  → 계속
    │
    ├─[2] Request 로그 저장
    │     └─ gen-ai-{UUID}-request-{TS}.json
    │        (headers는 secret 마스킹)
    │
    ├─[3] API 호출 (APIRetry.retry_request)
    │
    ├─[4] Response 로그 저장
    │     └─ gen-ai-{UUID}-response-{TS}.json
    │        (status_code, content, elapsed_ms 포함)
    │
    └─[5] 응답 반환
```

---

## 4. 요구사항 (Requirements)

### 4.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-062-001 | `GenAIApiLogger` 클래스를 `src/genai_api_logger.py`에 구현한다 | 필수 |
| REQ-062-002 | 로그 파일은 `logs/gen-ai/` 폴더에 JSON 형식으로 생성한다 | 필수 |
| REQ-062-003 | Request 로그는 `gen-ai-{UUID}-request-{YYYYMMDDHHMMSS}.json` 파일명으로 Header와 Body를 저장한다 | 필수 |
| REQ-062-004 | Response 로그는 `gen-ai-{UUID}-response-{YYYYMMDDHHMMSS}.json` 파일명으로 상태코드, 응답 본문, 소요시간을 저장한다 | 필수 |
| REQ-062-005 | UUID는 `uuid.uuid4().hex[:8]` (8자리)을 사용하며, 동일 요청-응답 쌍은 같은 UUID를 공유한다 | 필수 |
| REQ-062-006 | `.env` 파일의 `GEN_AI_LOG_ENABLED=true` 설정으로 로깅을 켜고 끌 수 있다 | 필수 |
| REQ-062-007 | `X-Lego-Client-Secret` 등 비밀 헤더는 `***MASKED***`로 마스킹하여 저장한다 | 필수 |
| REQ-062-008 | `_chat_streaming()`과 `_chat_non_streaming()` 양쪽 모두에 로깅을 적용한다 | 필수 |

### 4.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-062-001 | `GEN_AI_LOG_ENABLED=false` (기본값)인 경우 로깅 로직이 성능에 영향을 주지 않아야 한다 |
| NREQ-062-002 | 로그 파일 저장 실패가 API 호출 자체를 방해하지 않아야 한다 (예외 처리) |
| NREQ-062-003 | 로그 폴더(`logs/gen-ai/`)가 없으면 자동으로 생성한다 |
| NREQ-062-004 | 로그 파일은 UTF-8 인코딩, `ensure_ascii=False`, indent=2 형식으로 저장한다 |

---

## 5. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `src/genai_api_logger.py` | **신규** | `GenAIApiLogger` 클래스 구현 |
| `src/genai_assistant.py` | **수정** | `__init__`에서 로거 초기화, `_chat_streaming()`과 `_chat_non_streaming()`에 request/response 로그 호출 추가 |
| `src/__init__.py` | **수정** | `GenAIApiLogger` export 추가 |
| `.env` | **수정** | `GEN_AI_LOG_ENABLED=false` 추가 |
| `.gitignore` | **수정** | `logs/` 폴더 제외 추가 (이미 포함된 경우 생략) |

---

## 6. 로그 파일 예시

### 6.1 Request 로그 예시

**파일명:** `gen-ai-a1b2c3d4-request-20260302195800.json`

```json
{
  "log_type": "request",
  "log_id": "a1b2c3d4",
  "timestamp": "2026-03-02T19:58:00+09:00",
  "api_url": "https://scisportaldev.samsungif.net/rest/genAi/openapi/chat/v1/messages",
  "method": "POST",
  "headers": {
    "X-Lego-Client-Id": "API_CLIENT_APP",
    "X-Lego-Client-Secret": "***MASKED***",
    "Content-Type": "application/json"
  },
  "body": {
    "modelIds": ["gpt-oss-120B-medium"],
    "contents": [
      "[User Context]\nhello.md 파일을 만들어줘"
    ],
    "llmConfig": {
      "max_new_tokens": 10240,
      "seed": null,
      "top_k": 14,
      "top_p": 0.94,
      "temperature": 0.4,
      "repetition_penalty": 1.04
    },
    "isStream": true,
    "systemPrompt": "당신은 전문 소프트웨어 개발 어시스턴트입니다. ..."
  },
  "streaming": true,
  "model_id": "gpt-oss-120B-medium"
}
```

### 6.2 Response 로그 예시 (스트리밍)

**파일명:** `gen-ai-a1b2c3d4-response-20260302195805.json`

```json
{
  "log_type": "response",
  "log_id": "a1b2c3d4",
  "timestamp": "2026-03-02T19:58:05+09:00",
  "status_code": 200,
  "streaming": true,
  "elapsed_ms": 5120,
  "assembled_content": "hello.md 파일을 생성하겠습니다.\n\n```filename:hello.md\nHello World!\n```",
  "chunk_count": 42
}
```

### 6.3 Response 로그 예시 (논스트리밍)

**파일명:** `gen-ai-e5f6g7h8-response-20260302200102.json`

```json
{
  "log_type": "response",
  "log_id": "e5f6g7h8",
  "timestamp": "2026-03-02T20:01:02+09:00",
  "status_code": 200,
  "streaming": false,
  "elapsed_ms": 3250,
  "response_body": {
    "content": "hello.md 파일을 생성하겠습니다.",
    "modelId": "gpt-oss-120B-medium",
    "usage": {
      "prompt_tokens": 1234,
      "completion_tokens": 567,
      "total_tokens": 1801
    }
  }
}
```

### 6.4 에러 Response 로그 예시

```json
{
  "log_type": "response",
  "log_id": "a1b2c3d4",
  "timestamp": "2026-03-02T19:58:01+09:00",
  "status_code": 400,
  "streaming": true,
  "elapsed_ms": 120,
  "assembled_content": "{\"content\":\"The content was blocked by the filter.\",\"status\":\"FILTER_INVALID\"}",
  "chunk_count": 0
}
```

---

## 7. 테스트 계획 (Test Plan)

### 7.1 단위 테스트

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-062-001 | `GEN_AI_LOG_ENABLED=true`일 때 Request 로그 생성 | `logs/gen-ai/gen-ai-*-request-*.json` 파일 생성 |
| TC-062-002 | `GEN_AI_LOG_ENABLED=true`일 때 Response 로그 생성 | `logs/gen-ai/gen-ai-*-response-*.json` 파일 생성 |
| TC-062-003 | `GEN_AI_LOG_ENABLED=false`일 때 로그 미생성 | 파일 생성 없음 |
| TC-062-004 | 환경변수 미설정 시 기본값 `false` | 파일 생성 없음 |
| TC-062-005 | Request-Response 쌍 UUID 동일 | 같은 log_id 공유 |
| TC-062-006 | Secret 헤더 마스킹 | `X-Lego-Client-Secret: "***MASKED***"` |
| TC-062-007 | `logs/gen-ai/` 폴더 자동 생성 | 폴더 없어도 에러 없이 생성 |
| TC-062-008 | 스트리밍 응답 chunk_count 기록 | 실제 청크 수와 일치 |
| TC-062-009 | elapsed_ms 기록 | 0 이상의 정수 |
| TC-062-010 | JSON 형식 검증 | 유효한 JSON, UTF-8, indent=2 |

### 7.2 통합 테스트

```bash
# 1. .env에 로깅 활성화
# GEN_AI_LOG_ENABLED=true

# 2. 어시스턴트 실행
python gen-ai-chat-code.py

# 3. 대화 후 로그 확인
ls logs/gen-ai/

# 4. 로그 파일 내용 확인
cat logs/gen-ai/gen-ai-*-request-*.json | python -m json.tool
cat logs/gen-ai/gen-ai-*-response-*.json | python -m json.tool
```

---

## 8. 주의사항

| 항목 | 설명 |
|------|------|
| **보안** | `X-Lego-Client-Secret` 등 비밀 정보는 반드시 마스킹. `systemPrompt`와 `contents`에는 민감 단어 치환 후(mask 후) 데이터가 저장됨 |
| **디스크 용량** | 대용량 컨텍스트 전송 시 로그 파일 크기가 클 수 있음. 로그 정리는 사용자 책임 |
| **성능** | `GEN_AI_LOG_ENABLED=false` 시 `self.enabled` 플래그만 체크하고 즉시 반환하여 성능 영향 없음 |
| **.gitignore** | `logs/` 폴더를 `.gitignore`에 추가하여 로그 파일이 Git에 포함되지 않도록 함 |
| **동시성** | CLI 어시스턴트는 단일 스레드이므로 로그 파일 동시 쓰기 이슈 없음 |
| **로그 저장 시점** | Request는 API 호출 **직전**, Response는 API 응답 수신 **직후** 저장 |

---

## 9. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.062 | 2026-03-02 | - | 최초 작성: GenAI API 요청/응답 JSON 파일 로깅 설계 |
