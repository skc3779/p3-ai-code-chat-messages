# BUG v1.0.081 - Gemini Express Mode 스트리밍 응답 파싱 실패

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.081 |
| 제목 | `_chat_streaming` — Gemini Express Mode 스트리밍 응답 형식 불일치로 API 호출 실패 |
| 작성일 | 2026-04-18 |
| 상태 | 분석 완료 |
| 관련 FSD | [FSD v1.0.030](./FSD_v1.0.030_gemini-api-integration.md) — Gemini API 통합 |
| 수정 대상 | [gemini_assistant.py](../../../src/gemini_assistant.py) |

---

## 1. 버그 설명

### 1.1 증상

`gemini-ai-chat-code.py` 실행 시 사용자 질문을 입력하면 스트리밍 모드에서 **API 응답을 정상적으로 수신하지 못합니다.** 대기 스피너만 회전하다가 타임아웃 되거나, 응답 데이터를 파싱하지 못해 빈 결과가 반환됩니다.

### 1.2 재현 조건

1. `.env` 파일에 Express Mode API Key 방식으로 설정:
   ```
   GEMINI_API_KEY="AQ.Ab8RN6Kwlu..."
   GEMINI_MODEL_ID="gemini-3.1-pro-preview"
   GEMINI_API_ENDPOINT="https://aiplatform.googleapis.com/v1/publishers/google"
   ```
2. `python gemini-ai-chat-code.py` 실행
3. 질문 입력 (예: `2차방정식 간단 설명?`)
4. **결과**: 응답이 출력되지 않거나 파싱 오류 발생

### 1.3 원인 분석

#### 근본 원인: 응답 형식(Response Format) 불일치

Gemini Express Mode API(`?key=API_KEY`)의 `streamGenerateContent` 엔드포인트는 **두 가지 응답 형식**을 지원합니다:

| 모드 | URL 파라미터 | 응답 형식 | Content-Type |
|------|-------------|-----------|-------------|
| **기본 모드 (JSON Array)** | 없음 | `[{chunk1}, {chunk2}, ...]` | `application/json` |
| **SSE 모드** | `?alt=sse` | `data: {chunk1}\n\ndata: {chunk2}\n\n` | `text/event-stream` |

현재 코드는 **SSE 클라이언트(`sseclient`)를 사용하여 파싱**하지만, URL에 `alt=sse` 파라미터를 **추가하지 않아** 서버가 JSON Array 형식으로 응답합니다. 결과적으로 SSE 클라이언트가 JSON Array를 SSE 이벤트로 파싱하지 못합니다.

---

## 2. 상세 분석

### 2.1 BUG-01: `alt=sse` 쿼리 파라미터 누락 (Critical)

#### 코드 위치: `src/gemini_assistant.py` L183

```python
# 현재 코드 (수정 전)
api_url = f"{self.endpoint_url}/models/{self.model_id}:streamGenerateContent?key={self.api_key}"
```

API 호출 시 `alt=sse` 쿼리 파라미터가 누락되어 있습니다. Gemini REST API Reference에 따르면,
`streamGenerateContent` 엔드포인트에서 SSE 형식 응답을 받으려면 반드시 `alt=sse`를 명시해야 합니다.

> [!IMPORTANT]
> **Gemini API Reference (REST) 원문 규격:**
> ```
> POST /v1/publishers/google/models/{MODEL_ID}:streamGenerateContent?alt=sse&key={API_KEY}
> Host: aiplatform.googleapis.com
> ```
> `alt=sse` 파라미터가 없으면 서버는 **JSON Array** 형식으로 청크를 반환합니다.

#### 실제 API 응답 비교

**현재 (alt=sse 누락) → JSON Array 반환:**
```json
[
    {
        "candidates": [{
            "content": {
                "role": "model",
                "parts": [{"text": "**2차방정식**을 가장 알기 쉽게 핵심만 요약해 드릴"}]
            }
        }],
        "usageMetadata": {"trafficType": "ON_DEMAND"},
        "modelVersion": "gemini-3.1-pro-preview",
        "responseId": "r6LiaeKYEKai0ckP-La26Qg"
    },
    {
        "candidates": [{
            "content": {
                "role": "model",
                "parts": [{"text": "게요!\n\n### 1. 2차방정식이란?\n미지수(보통 $x$)를"}]
            }
        }],
        ...
    },
    ...
]
```

**수정 후 (alt=sse 추가) → SSE 이벤트 스트림 반환:**
```
data: {"candidates":[{"content":{"role":"model","parts":[{"text":"**2차방정식**을 가장"}]}}],"modelVersion":"gemini-3.1-pro-preview"}

data: {"candidates":[{"content":{"role":"model","parts":[{"text":"알기 쉽게 핵심만"}]}}],"modelVersion":"gemini-3.1-pro-preview"}

data: [DONE]
```

#### 영향

`sseclient.SSEClient(response)` 라이브러리는 `text/event-stream` 형식의 `data:` 접두사 라인만 파싱할 수 있으므로, JSON Array를 수신하면 이벤트를 인식하지 못해 빈 결과가 반환됩니다.

---

### 2.2 BUG-02: JSON Array 폴백 처리 미구현 (Medium)

#### 코드 위치: `src/gemini_assistant.py` L213-238

```python
# 현재 코드 — SSE 전용 파싱 로직만 존재
client = sseclient.SSEClient(response)
result_message = ""
is_first_chunk = True

try:
    for event in client.events():
        if is_first_chunk:
            spinner.stop()
            print(f"\n🤖 AI: ", end="", flush=True)
            is_first_chunk = False
            
        if event.data:
            try:
                data = json.loads(event.data)
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
```

`alt=sse`를 추가하더라도, 서버 측 설정이나 프록시 환경에 따라 JSON Array 형식으로 폴백될 가능성이 있습니다. 현재 코드에는 이에 대한 폴백 처리가 전혀 없습니다.

---

### 2.3 BUG-03: 논스트리밍 URL 경로에도 동일한 패턴 존재 (Low)

#### 코드 위치: `src/gemini_assistant.py` L265

```python
# 논스트리밍 모드 (참고)
api_url = f"{self.endpoint_url}/models/{self.model_id}:generateContent?key={self.api_key}"
```

논스트리밍 `generateContent`는 SSE가 아닌 단일 JSON 응답이므로 `alt=sse`가 불필요합니다. 논스트리밍은 현재 코드가 정상 동작하나, 아래 두 가지 개선 사항이 필요합니다:

| 항목 | 현재 | 개선 |
|------|------|------|
| `endpoint_url` 기본값 불일치 | `__init__` 기본값에 `/models/` 포함, `main()` 기본값에 미포함 | 통일 필요 |
| `conversation_history` role 값 | `"model"` 사용 | Gemini API와 일치 (정상) |

---

## 3. 수정 방안

### 3.1 방안 A: `alt=sse` 쿼리 파라미터 추가 (권장)

기존 SSE 파싱 로직을 유지하면서 URL에 `alt=sse`만 추가하는 최소 변경 방안입니다.

#### 수정 전 (`gemini_assistant.py` L183)

```python
api_url = f"{self.endpoint_url}/models/{self.model_id}:streamGenerateContent?key={self.api_key}"
```

#### 수정 후

```python
api_url = f"{self.endpoint_url}/models/{self.model_id}:streamGenerateContent?alt=sse&key={self.api_key}"
```

> [!TIP]
> `alt=sse`를 추가하면 서버가 `text/event-stream` 형식으로 응답하므로, 기존 `sseclient.SSEClient` 파싱 로직이 정상 동작합니다.

### 3.2 방안 B: JSON Array 폴백 + SSE 이중 지원 (선택 강화)

`alt=sse`를 추가하되, 응답의 `Content-Type` 헤더를 확인하여 JSON Array 폴백도 지원합니다.

```python
def _chat_streaming(self, user_message: str) -> str:
    """스트리밍 모드 채팅 (SSE 우선, JSON Array 폴백)"""
    import time as _time
    api_url = f"{self.endpoint_url}/models/{self.model_id}:streamGenerateContent?alt=sse&key={self.api_key}"
    body = self._build_request_body(user_message)
    
    # ... (기존 로거/스피너 로직 유지) ...
    
    response = APIRetry.retry_request(
        requests.post, api_url, headers=self.headers, json=body, stream=True
    )
    
    if response.status_code != 200:
        spinner.stop()
        print(f"\n❌ API Error: {response.status_code} - {response.text}")
        return ""
    
    # Content-Type 확인으로 응답 형식 판별
    content_type = response.headers.get('Content-Type', '')
    
    if 'text/event-stream' in content_type:
        # SSE 모드: 기존 sseclient 로직 사용
        result_message = self._parse_sse_response(response, spinner)
    else:
        # JSON Array 폴백: 청크를 순차 파싱
        result_message = self._parse_json_array_response(response, spinner)
    
    # ... (이하 히스토리 추가 등 기존 로직 유지) ...
```

#### JSON Array 파싱 메서드 (신규 추가)

```python
def _parse_json_array_response(self, response, spinner) -> str:
    """JSON Array 형식의 스트리밍 응답 파싱"""
    result_message = ""
    is_first_chunk = True
    
    try:
        # 전체 응답을 JSON Array로 파싱
        chunks = response.json()
        
        for chunk in chunks:
            if is_first_chunk:
                spinner.stop()
                print(f"\n🤖 AI: ", end="", flush=True)
                is_first_chunk = False
            
            candidates = chunk.get('candidates', [])
            for candidate in candidates:
                content = candidate.get('content', {})
                parts = content.get('parts', [])
                for part in parts:
                    text = part.get('text', '')
                    if text:
                        print(text, end="", flush=True)
                        result_message += text
    except (json.JSONDecodeError, requests.exceptions.RequestException) as e:
        spinner.stop()
        print(f"\n\n[⚠️ 응답 파싱 실패: {str(e)}]")
    
    if is_first_chunk:
        spinner.stop()
    
    print("\n")
    return result_message
```

### 3.3 `__init__` 기본값 통일

#### 수정 전 (`gemini_assistant.py` L37)

```python
endpoint_url: str = "https://aiplatform.googleapis.com/v1/publishers/google/models/"
```

#### 수정 후

```python
endpoint_url: str = "https://aiplatform.googleapis.com/v1/publishers/google"
```

> [!WARNING]
> 기존 `__init__`의 기본값에는 `/models/`가 포함되어 있어, L183/L265의 URL 조합 시 `/models//models/`로 중복될 수 있습니다.
> `.env`에서 값을 오버라이드하고 있어 현재는 문제가 발생하지 않지만, `.env` 미설정 시 URL이 깨집니다.

---

## 4. 영향 분석

### 4.1 영향 범위

| 모듈 | 메서드 | 영향 | 설명 |
|------|--------|:----:|------|
| `GeminiCodeAssistant` | `_chat_streaming()` | 🔴 Critical | SSE 파싱 불가로 스트리밍 응답 수신 불가 |
| `GeminiCodeAssistant` | `_chat_non_streaming()` | 🟢 정상 | JSON 단일 응답이므로 영향 없음 |
| `GeminiCodeAssistant` | `_build_request_body()` | 🟢 정상 | 요청 본문 구성은 정상 |
| `gemini-ai-chat-code.py` | `main()` | 🟡 간접 | 기본 streaming=True로 영향 받음 |

### 4.2 데이터 흐름 분석

```
[현재 — 실패 흐름]
사용자 입력
  → _chat_streaming()
    → POST .../streamGenerateContent?key=... (alt=sse 누락)
      → 서버: JSON Array 응답 반환
        → sseclient.SSEClient: SSE 이벤트 감지 실패
          → for event in client.events(): 빈 이벤트
            → result_message = "" (빈 응답)

[수정 후 — 정상 흐름]
사용자 입력
  → _chat_streaming()
    → POST .../streamGenerateContent?alt=sse&key=...
      → 서버: SSE 이벤트 스트림 반환
        → sseclient.SSEClient: data: 이벤트 파싱 성공
          → for event in client.events(): 텍스트 추출
            → result_message = "완성된 응답" (정상 출력)
```

---

## 5. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `src/gemini_assistant.py` | **수정** | L183: `alt=sse` 파라미터 추가 |
| `src/gemini_assistant.py` | **수정** | L37: `endpoint_url` 기본값 통일 |
| `src/gemini_assistant.py` | **추가** (선택) | `_parse_json_array_response()` 폴백 메서드 |

---

## 6. 검증 시나리오

### 6.1 수동 검증

| # | 시나리오 | 예상 결과 | 판정 |
|---|---------|----------|:----:|
| 1 | 스트리밍 모드에서 간단한 질문 (예: "안녕") | SSE로 실시간 응답 출력 | ⬜ |
| 2 | 스트리밍 모드에서 긴 응답 유도 (예: "2차방정식 설명") | 청크 단위로 순차 출력 | ⬜ |
| 3 | `/nostream` 후 동일 질문 | 논스트리밍 JSON 응답 정상 출력 | ⬜ |
| 4 | `/stream` 으로 복귀 후 질문 | 다시 SSE 스트리밍 정상 동작 | ⬜ |
| 5 | `.env` 미설정 시 기본값으로 실행 | `endpoint_url` 기본값으로 정상 URL 조합 | ⬜ |

### 6.2 curl 검증 (Express Mode)

```bash
# SSE 모드 검증 (alt=sse 추가)
curl -X POST \
  "https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-3.1-pro-preview:streamGenerateContent?alt=sse&key=YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{"role":"user","parts":[{"text":"2차방정식 간단 설명?"}]}]
  }'

# 기대 응답 (SSE 형식):
# data: {"candidates":[{"content":{"role":"model","parts":[{"text":"..."}]}}]}
# 
# data: {"candidates":[{"content":{"role":"model","parts":[{"text":"..."}]}}]}
# 
# data: [DONE]
```

---

## 7. 참고 자료

### 7.1 Gemini API Reference (REST)

- **Express Mode API**: `https://aiplatform.googleapis.com/v1/publishers/google/models/{MODEL_ID}:streamGenerateContent`
- **REST 문서**: [Vertex AI에서 Gemini API로 콘텐츠 생성](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference?hl=ko)
- **Express Mode streamGenerateContent**: [REST v1 streamGenerateContent](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/express-mode/rest/v1/publishers.models/streamGenerateContent)

### 7.2 Try Gemini 3 Pro Preview (사용자 제공 curl 검증 결과)

사용자가 Express Mode로 직접 호출한 결과, 서버는 **JSON Array** 형식으로 응답을 반환합니다:

```http
POST /v1/publishers/google/models/gemini-3.1-pro-preview:streamGenerateContent?key=XXX HTTP/1.1
Host: aiplatform.googleapis.com
Content-Type: application/json

# 응답: JSON Array (SSE가 아님)
[
    {"candidates":[{"content":{"role":"model","parts":[{"text":"..."}]}}], ...},
    {"candidates":[{"content":{"role":"model","parts":[{"text":"..."}]}}], ...},
    ...
]
```

이 응답 형식은 `alt=sse` 파라미터 없이 호출했기 때문이며, 현재 소스코드의 `_chat_streaming()` 메서드도 동일한 방식으로 호출하고 있어 `sseclient`가 파싱할 수 없는 형식을 수신하게 됩니다.

### 7.3 버그 발견 경위 요약

```
┌─────────────────────────────────────────────────────────────┐
│  .env 설정                                                   │
│  GEMINI_API_ENDPOINT = .../v1/publishers/google              │
│  GEMINI_API_KEY      = AQ.Ab8RN6Kwlu...                     │
│  GEMINI_MODEL_ID     = gemini-3.1-pro-preview               │
├─────────────────────────────────────────────────────────────┤
│  URL 조합 (L183)                                             │
│  {endpoint}/models/{model}:streamGenerateContent?key={key}  │
│  → .../models/gemini-3.1-pro-preview:streamGenerateContent  │
│    ?key=AQ.Ab8RN6Kwlu...                                    │
│                                                              │
│  ⚠️ alt=sse 쿼리 파라미터 누락!                               │
├─────────────────────────────────────────────────────────────┤
│  서버 응답: JSON Array (SSE가 아님)                           │
│  [{"candidates":[...]}, {"candidates":[...]}, ...]          │
├─────────────────────────────────────────────────────────────┤
│  sseclient.SSEClient(response)                               │
│  → "data:" 접두사가 없으므로 이벤트 감지 실패                  │
│  → for event in client.events() → 빈 이터레이션              │
│  → result_message = "" → 빈 응답 반환                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1.0.081 | 2026-04-18 | 최초 작성: Gemini Express Mode `streamGenerateContent` SSE 응답 파싱 실패 버그 분석 |
