# FSD v1.0.055 - GenAI Provider Endpoint URL 구조 수정

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.055 |
| 제목 | GenAI Provider Endpoint URL 및 API 형식 구조 수정 |
| 작성일 | 2026-03-02 |
| 상태 | 구현 완료 |
| 선행 FSD | [FSD v1.0.054](./FSD_v1.0.054_genai-provider-toolcall_v2.md) — GenAI Provider Tool Call 지원 |
| 참조 소스 | [genai_assistant.py](../../../src/genai_assistant.py), [gen-ai-chat-code.py](../../../gen-ai-chat-code.py), [llm_config.py](../../../src/llm_config.py) |
| 수정 대상 | [genai_provider.py](../../../ai-proxy/providers/genai_provider.py) |
| 참조 문서 | [README-gen-ai-chat-code.md](../../../README-gen-ai-chat-code.md) — GenAI API 사양 |

---

## 1. 개요 (Overview)

`genai_provider.py`에서 SCI Portal GenAI API를 호출할 때 **Endpoint URL 경로, 인증 헤더, Request Body 구조, Response 파싱** 등이 실제 GenAI API 사양과 일치하지 않는 오류가 발견되었습니다.

기존에 정상 동작하고 있는 `genai_assistant.py`, `gen-ai-chat-code.py`, `llm_config.py`의 구현과 `README-gen-ai-chat-code.md`의 API 사양을 기준으로 `genai_provider.py`를 수정합니다.

---

## 2. 오류 분석 (Bug Analysis)

### 2.1 전체 오류 비교표

| # | 항목 | `genai_assistant.py` (정상) | `genai_provider.py` (오류) | 심각도 |
|---|------|---------------------------|---------------------------|--------|
| 1 | **Endpoint URL 경로** | `{ENDPOINT_URL}/openapi/chat/v1/messages` | `{ENDPOINT_URL}` (하위 경로 누락) | **Critical** |
| 2 | **인증 헤더 키(Client ID)** | `X-Lego-Client-Id` | `X-Client-Key` | **Critical** |
| 3 | **인증 헤더 키(Client Secret)** | `X-Lego-Client-Secret` | `X-Client-Secret` | **Critical** |
| 4 | **Request Body: 모델 ID 키** | `modelIds: ["model_id"]` (배열) | `model_id: "model_id"` (문자열) | **Critical** |
| 5 | **Request Body: 대화 내용 키** | `contents: [...]` (문자열 배열) | `prompt: [{role, text}]` (객체 배열) | **Critical** |
| 6 | **Request Body: LLM 설정 키** | `llmConfig: {max_new_tokens, seed, top_k, top_p, temperature, repetition_penalty}` | `parameters: {temperature, max_output_tokens}` | **Critical** |
| 7 | **Request Body: 스트리밍 키** | `isStream: true/false` | 없음 | **High** |
| 8 | **Request Body: 시스템 프롬프트** | `systemPrompt: "..."` (최상위 키) | system role을 prompt 배열에 포함 | **High** |
| 9 | **Response 파싱 (스트리밍)** | SSE 이벤트: `{event_status: "CHUNK", content: "..."}` | `{response, text, result}` 필드 검색 | **Critical** |
| 10 | **Response 파싱 (논스트리밍)** | `{content: "...", modelId: "...", usage: {...}}` | `{response, text, result}` 필드 검색 | **Critical** |

### 2.2 오류 상세

#### 오류 1: Endpoint URL 경로 누락 (Critical)

```python
# genai_assistant.py (정상) — Line 241
api_url = f"{self.endpoint_url}/openapi/chat/v1/messages"

# genai_provider.py (오류) — Line 273
resp = await self._retry_on_429(
    lambda: self.client.post(self.base_url, json=payload)  # ← 하위 경로 없음!
)
```

`ENDPOINT_URL` 환경변수는 `https://scisportaldev.samsungif.net/rest/genAi`까지만 포함하고 있으며, 실제 API 엔드포인트는 그 뒤에 `/openapi/chat/v1/messages`가 추가되어야 합니다.

#### 오류 2-3: 인증 헤더 키 불일치 (Critical)

```python
# genai_assistant.py (정상) — Line 33-36
self.headers = {
    "X-Lego-Client-Id": client_key,       # ← 올바른 헤더 키
    "X-Lego-Client-Secret": client_secret, # ← 올바른 헤더 키
    "Content-Type": "application/json"
}

# genai_provider.py (오류) — Line 72-75
self.client = httpx.AsyncClient(
    headers={
        "X-Client-Key": client_key,        # ← 잘못된 헤더 키
        "X-Client-Secret": client_secret,   # ← 잘못된 헤더 키
        ...
    },
)
```

#### 오류 4-8: Request Body 구조 불일치 (Critical)

```python
# genai_assistant.py (정상) — Line 233-239
body = {
    "modelIds": [self.model_id],          # ← 배열 형식
    "contents": contents,                  # ← 문자열 배열
    "llmConfig": self.get_llm_config(),    # ← 6개 파라미터 포함
    "isStream": streaming,                 # ← 스트리밍 제어
    "systemPrompt": self.system_prompt     # ← 최상위 키
}

# genai_provider.py (오류) — Line 208-215
return {
    "model_id": request.model,             # ← 문자열 형식 (배열 아님!)
    "prompt": prompt,                      # ← 객체 배열 (문자열 아님!)
    "parameters": {                        # ← 키 이름 다르고 파라미터 부족!
        "temperature": ...,
        "max_output_tokens": ...,          # ← max_new_tokens 여야 함
    },
}
```

#### 오류 9-10: Response 파싱 불일치 (Critical)

```python
# genai_assistant.py (정상 - 스트리밍) — Line 285-293
data = json.loads(event.data)
event_status = data.get('event_status') or data.get('eventStatus')
content = data.get('content', '')

if event_status == 'CHUNK' and content:
    result_message += content
elif event_status == 'DONE':
    break

# genai_provider.py (오류 - 논스트리밍) — Line 279
content = data.get("response", data.get("text", data.get("result", str(data))))
# ← 실제 응답에는 "content" 키가 사용됨!
```

---

## 3. 수정 설계 (Fix Design)

### 3.1 수정 항목

#### REQ-055-001: Endpoint URL 경로 추가

```python
# 수정 전
resp = await self._retry_on_429(
    lambda: self.client.post(self.base_url, json=payload)
)

# 수정 후
api_url = f"{self.base_url}/openapi/chat/v1/messages"
resp = await self._retry_on_429(
    lambda: self.client.post(api_url, json=payload)
)
```

#### REQ-055-002: 인증 헤더 키 수정

```python
# 수정 전
self.client = httpx.AsyncClient(
    headers={
        "X-Client-Key": client_key,
        "X-Client-Secret": client_secret,
        ...
    },
)

# 수정 후
self.client = httpx.AsyncClient(
    headers={
        "X-Lego-Client-Id": client_key,
        "X-Lego-Client-Secret": client_secret,
        "Content-Type": "application/json",
    },
)
```

#### REQ-055-003: Request Body 구조 변환 수정

`_transform_request()` 메서드를 GenAI API 사양에 맞게 전면 수정합니다.

```python
def _transform_request(self, request: ChatCompletionRequest) -> dict:
    """OpenAI 형식 → GenAI API 형식 변환."""
    
    # 1. contents 배열 구성 (문자열 배열)
    contents = []
    for m in request.messages:
        if m.role == "system":
            continue  # systemPrompt로 별도 처리
        elif m.role == "assistant" and m.tool_calls:
            # assistant + tool_calls → 텍스트 변환 (REQ-054-008)
            tool_text_parts = []
            if m.content:
                tool_text_parts.append(m.content)
            for tc in m.tool_calls:
                tool_text_parts.append(
                    f"[Tool Call] {tc.function.name}({tc.function.arguments})"
                )
            contents.append("\n".join(tool_text_parts))
        elif m.role == "tool":
            # tool role → 텍스트 변환 (REQ-054-003)
            tool_name = ""
            if m.tool_call_id:
                for prev in request.messages:
                    if prev.role == "assistant" and prev.tool_calls:
                        for tc in prev.tool_calls:
                            if tc.id == m.tool_call_id:
                                tool_name = tc.function.name
                                break
            contents.append(
                f"[Tool Result{' for ' + tool_name if tool_name else ''}]\n{m.content or ''}"
            )
        else:
            # user/assistant → 문자열로 변환
            prefix = "[User Context]" if m.role == "user" else "[Assistant Context]"
            contents.append(f"{prefix}\n{m.content or ''}")

    # 2. systemPrompt 구성
    system_prompt = ""
    for m in request.messages:
        if m.role == "system":
            system_prompt += (m.content or "")
            break

    # tools → 시스템 프롬프트에 도구 정의 삽입 (REQ-054-001)
    tools_prompt = self._build_tools_prompt(request)
    if tools_prompt:
        system_prompt += tools_prompt

    # 3. llmConfig 구성 (llm_config.py 기본값 기반)
    llm_config = {
        "max_new_tokens": request.max_tokens or 10240,
        "seed": None,
        "top_k": 14,
        "top_p": 0.94,
        "temperature": request.temperature if request.temperature is not None else 0.4,
        "repetition_penalty": 1.04,
    }

    return {
        "modelIds": [request.model],
        "contents": contents,
        "llmConfig": llm_config,
        "isStream": False,  # 프록시에서는 논스트리밍으로 수신 후 변환
        "systemPrompt": system_prompt,
    }
```

#### REQ-055-004: Response 파싱 수정 (논스트리밍)

```python
# 수정 전
content = data.get("response", data.get("text", data.get("result", str(data))))

# 수정 후 (README-gen-ai-chat-code.md 응답 사양 기반)
content = data.get("content", "")
```

#### REQ-055-005: Response 파싱 수정 (스트리밍 버퍼링)

프록시의 `chat()` 메서드에서 SCI Portal API를 스트리밍 모드(`isStream: true`)로 호출하고 SSE 이벤트를 수집하는 방식도 지원해야 합니다.

```python
# SSE 응답 파싱
async def _collect_streaming_response(self, response) -> str:
    """SCI Portal SSE 스트리밍 응답을 수집하여 전체 텍스트 반환"""
    result = ""
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if not data_str:
                continue
            try:
                data = json.loads(data_str)
                event_status = data.get("event_status") or data.get("eventStatus")
                chunk_content = data.get("content", "")
                
                if event_status == "CHUNK" and chunk_content:
                    result += chunk_content
                elif event_status == "DONE":
                    break
            except json.JSONDecodeError:
                continue
    return result
```

### 3.2 수정 전후 대비표

| 항목 | 수정 전 (`genai_provider.py`) | 수정 후 |
|------|-------------------------------|---------|
| Endpoint URL | `self.base_url` | `f"{self.base_url}/openapi/chat/v1/messages"` |
| 인증 헤더 (ID) | `X-Client-Key` | `X-Lego-Client-Id` |
| 인증 헤더 (Secret) | `X-Client-Secret` | `X-Lego-Client-Secret` |
| 모델 ID 키 | `model_id: "모델"` | `modelIds: ["모델"]` |
| 대화 내용 키 | `prompt: [{role, text}]` | `contents: ["문자열"]` |
| LLM 설정 키 | `parameters: {temperature, max_output_tokens}` | `llmConfig: {max_new_tokens, seed, top_k, top_p, temperature, repetition_penalty}` |
| 스트리밍 키 | 없음 | `isStream: true/false` |
| 시스템 프롬프트 | prompt 배열 내 system role | `systemPrompt: "..."`  (최상위 키) |
| 응답 파싱 | `data.get("response")` | `data.get("content")` |

---

## 4. 요구사항 (Requirements)

### 4.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-055-001 | Endpoint URL에 `/openapi/chat/v1/messages` 하위 경로를 추가한다 | 필수 |
| REQ-055-002 | 인증 헤더를 `X-Lego-Client-Id` / `X-Lego-Client-Secret`로 수정한다 | 필수 |
| REQ-055-003 | Request Body를 GenAI API 사양(`modelIds`, `contents`, `llmConfig`, `isStream`, `systemPrompt`)에 맞게 수정한다 | 필수 |
| REQ-055-004 | 논스트리밍 Response 파싱을 `content` 키 기반으로 수정한다 | 필수 |
| REQ-055-005 | 스트리밍 Response의 SSE 이벤트(`event_status: CHUNK/DONE`) 파싱을 올바르게 수정한다 | 필수 |
| REQ-055-006 | 기존 Tool Call 에뮬레이션(FSD v1.0.054)을 수정된 Request/Response 구조에 맞게 유지한다 | 필수 |
| REQ-055-007 | `llmConfig`에 `llm_config.py`의 기본값(`max_new_tokens`, `seed`, `top_k`, `top_p`, `temperature`, `repetition_penalty`)을 반영한다 | 권장 |

### 4.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-055-001 | 수정 후에도 FSD v1.0.054의 Tool Call 에뮬레이션 기능이 정상 동작해야 한다 |
| NREQ-055-002 | 기존 `genai_assistant.py`와 동일한 API 요청/응답 구조를 사용해야 한다 |

---

## 5. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `ai-proxy/providers/genai_provider.py` | **수정** | Endpoint URL, 인증 헤더, Request Body, Response 파싱 전면 수정 |

---

## 6. 참조 소스 코드

### 6.1 `genai_assistant.py` — 올바른 API 호출 구조

```python
# Line 30-37: 초기화
def __init__(self, endpoint_url, client_key, client_secret, model_id, workspace_dir="."):
    self.endpoint_url = endpoint_url
    self.headers = {
        "X-Lego-Client-Id": client_key,
        "X-Lego-Client-Secret": client_secret,
        "Content-Type": "application/json"
    }
    self.model_id = model_id

# Line 233-241: API 요청 구성
body = {
    "modelIds": [self.model_id],
    "contents": contents,
    "llmConfig": self.get_llm_config(),
    "isStream": streaming,
    "systemPrompt": self.system_prompt
}
api_url = f"{self.endpoint_url}/openapi/chat/v1/messages"
```

### 6.2 `llm_config.py` — LLM 설정 기본값

```python
# baseline 설정 (기본값)
"baseline": {
    "temperature": 0.30,
    "top_k": 12,
    "top_p": 0.90,
    "repetition_penalty": 1.20,
    "max_new_tokens": 10240,
}
```

### 6.3 `gen-ai-chat-code.py` — 환경변수 로드

```python
# Line 139-142
ENDPOINT_URL = os.getenv("ENDPOINT_URL")
YOUR_CLIENT_KEY = os.getenv("YOUR_CLIENT_KEY")
YOUR_CLIENT_SECRET = os.getenv("YOUR_CLIENT_SECRET")
YOUR_MODEL_ID = os.getenv("YOUR_MODEL_ID")
```

### 6.4 `README-gen-ai-chat-code.md` — API 사양

```
Endpoint: {ENDPOINT_URL}/openapi/chat/v1/messages

Headers:
  X-Lego-Client-Id: <YOUR_CLIENT_KEY>
  X-Lego-Client-Secret: <YOUR_CLIENT_SECRET>
  Content-Type: application/json

Request Body:
  {
    "modelIds": ["your_model_id"],
    "contents": ["대화 내용 배열"],
    "llmConfig": { max_new_tokens, seed, top_k, top_p, temperature, repetition_penalty },
    "isStream": true,
    "systemPrompt": "시스템 프롬프트"
  }

Response (스트리밍): SSE event_status: "CHUNK" → content, "DONE" → 종료
Response (논스트리밍): { "content": "전체 응답", "modelId": "...", "usage": {...} }
```

---

## 7. 테스트 계획 (Test Plan)

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-055-001 | GenAI 모델로 논스트리밍 채팅 요청 | SCI Portal API 정상 호출 및 OpenAI 형식 응답 반환 |
| TC-055-002 | GenAI 모델로 스트리밍 채팅 요청 | SSE 이벤트 수집 후 OpenAI SSE 형식으로 변환 |
| TC-055-003 | Tool Call 포함 요청 (tools 파라미터 포함) | 시스템 프롬프트에 도구 정의 삽입 후 tool_calls 응답 변환 |
| TC-055-004 | 인증 헤더 정상 전달 확인 (로그 검증) | `X-Lego-Client-Id`, `X-Lego-Client-Secret` 헤더 전송 |
| TC-055-005 | Request Body 구조 검증 (로그 검증) | `modelIds`, `contents`, `llmConfig`, `isStream`, `systemPrompt` 키 포함 |

```bash
# 테스트 명령
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"genai/gpt-oss-120B-medium","messages":[{"role":"user","content":"Hello"}]}'
```

---

## 8. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.055 | 2026-03-02 | - | 최초 작성: GenAI Provider의 Endpoint URL, 인증 헤더, Request Body, Response 파싱 구조 오류 분석 및 수정 설계 |
