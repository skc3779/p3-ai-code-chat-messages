# FSD v1.0.053 - Tool Call 기능 추가 (OpenAI 호환 프록시)

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.053 |
| 제목 | OpenAI 호환 프록시 서버 — Tool Call 기능 추가 |
| 작성일 | 2026-03-01 |
| 상태 | 구현 완료 |
| 선행 FSD | [FSD v1.0.052](./FSD_v1.0.052_openai-compatible-proxy.md) — 프록시 서버 기본 구축 |
| 참조 SRS | [SRS v1.0.052 v2](../api-specs/SRS_v1.0.052_openai-compatible-provider_v2.md) |
| 참조 스펙 | [AI SDK OpenAI Compatible](https://sdk.vercel.ai/providers/openai-compatible-providers) — Tool calling 지원 확인 |

---

## 1. 개요 (Overview)

FSD v1.0.052에서 구축한 FastAPI 프록시 서버에 **Tool Call(Function Calling)** 기능을 추가합니다.

OpenCode 등 AI 코딩 도구는 파일 읽기/쓰기, 명령어 실행 등의 기능을 **Tool Call**로 구현합니다. AI SDK(`@ai-sdk/openai-compatible`)는 Tool Calling을 지원하며, 프록시 서버가 이를 올바르게 **패스스루/변환**해야 OpenCode에서 정상 동작합니다.

### 1.1 Tool Call이란?

```
┌────────────┐          ┌──────────────┐          ┌────────────┐
│  OpenCode  │  ① 요청  │  AI 모델     │  ② 응답  │  OpenCode  │
│  (클라이언트)│ ────────→│  (프록시경유) │ ────────→│  (클라이언트)│
│            │ tools:   │              │ tool_calls│            │
│            │ [{name,  │              │ [{id,     │            │
│            │   params}]│             │   name,   │  ③ 도구 실행│
│            │          │              │   args}]  │ ───────┐   │
│            │          │              │           │        │   │
│            │  ④ 결과   │              │  ⑤ 최종   │  ┌─────┘   │
│            │ ────────→│              │ ────────→│  │ 결과 전달│
│            │ tool_call│              │ content  │  │         │
│            │ _result  │              │          │  ▼         │
└────────────┘          └──────────────┘          └────────────┘
```

1. 클라이언트가 `tools` 정의와 함께 요청
2. AI 모델이 `tool_calls`를 포함한 응답 반환 (실행 요청)
3. 클라이언트가 도구를 실제 실행
4. 실행 결과를 `tool` role 메시지로 다시 전송
5. AI 모델이 최종 응답 생성

---

## 2. 배경 (Background)

### 2.1 FSD v1.0.052의 한계

FSD v1.0.052에서 구현한 프록시 서버는 **텍스트 응답만 처리**합니다:

```python
# 현재 models.py — 텍스트만 지원
class ChatMessage(BaseModel):
    role: str       # "system" | "user" | "assistant"
    content: str    # ← 텍스트만
```

OpenCode 등의 도구가 Tool Call을 요청하면:
- `tools` 필드가 프록시에서 무시됨
- `tool_calls` 응답이 파싱되지 않음
- `tool` role 메시지가 처리되지 않음

### 2.2 AI SDK Tool Call 지원

AI SDK `@ai-sdk/openai-compatible`는 다음을 지원합니다:

> **Supported Capabilities:**
> - Tool calling — Call tools/functions **with streaming support**

즉, OpenCode가 프록시를 통해 Tool Call을 사용하려면, 프록시가 **OpenAI Tool Call 형식을 완전히 지원**해야 합니다.

---

## 3. 요구사항 (Requirements)

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| REQ-053-001 | 요청의 `tools` 필드를 공급자 API로 전달해야 한다 | 필수 |
| REQ-053-002 | 요청의 `tool_choice` 필드를 공급자 API로 전달해야 한다 | 필수 |
| REQ-053-003 | 응답의 `tool_calls` 필드를 OpenAI 형식으로 반환해야 한다 | 필수 |
| REQ-053-004 | `role: "tool"` 메시지(도구 실행 결과)를 공급자 API로 전달해야 한다 | 필수 |
| REQ-053-005 | 스트리밍 응답에서 `tool_calls` 델타를 SSE로 전달해야 한다 | 필수 |
| REQ-053-006 | Gemini Provider: `tools` / `tool_calls` 패스스루 | 필수 |
| REQ-053-007 | Claude Provider: OpenAI `tools` → Anthropic `tools` 형식 변환 | 필수 |
| REQ-053-008 | GenAI Provider: Tool Call 미지원 시 에러 메시지 반환 | 권장 |

### 3.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-053-001 | 기존 텍스트 전용 요청과 하위 호환되어야 한다 (tools 없이도 동작) |
| NREQ-053-002 | Tool Call 응답은 OpenAI Chat Completions API 형식을 정확히 따라야 한다 |

---

## 4. 설계 (Design)

### 4.1 OpenAI Tool Call 요청 형식

```json
{
  "model": "gemini/gemini-3-pro-preview",
  "messages": [
    {"role": "user", "content": "서울 날씨를 알려줘"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "지정된 도시의 현재 날씨를 조회합니다",
        "parameters": {
          "type": "object",
          "properties": {
            "city": {
              "type": "string",
              "description": "도시 이름"
            }
          },
          "required": ["city"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

### 4.2 OpenAI Tool Call 응답 형식

**① AI가 도구 호출을 요청할 때:**

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "gemini/gemini-3-pro-preview",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_abc123",
          "type": "function",
          "function": {
            "name": "get_weather",
            "arguments": "{\"city\": \"서울\"}"
          }
        }
      ]
    },
    "finish_reason": "tool_calls"
  }],
  "usage": { ... }
}
```

**② 도구 실행 결과를 포함한 후속 요청:**

```json
{
  "model": "gemini/gemini-3-pro-preview",
  "messages": [
    {"role": "user", "content": "서울 날씨를 알려줘"},
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {"name": "get_weather", "arguments": "{\"city\": \"서울\"}"}
      }]
    },
    {
      "role": "tool",
      "tool_call_id": "call_abc123",
      "content": "{\"temperature\": 15, \"condition\": \"맑음\"}"
    }
  ]
}
```

**③ 스트리밍 Tool Call 응답 (SSE):**

```
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_abc123","type":"function","function":{"name":"get_weather","arguments":""}}]},"index":0}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\"city\""}}]},"index":0}]}

data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":": \"서울\"}"}}]},"index":0}]}

data: {"choices":[{"delta":{},"finish_reason":"tool_calls","index":0}]}

data: [DONE]
```

### 4.3 Pydantic 스키마 변경 (`models.py`)

```python
# ── 추가 스키마 ──

class FunctionDefinition(BaseModel):
    """도구 함수 정의"""
    name: str
    description: Optional[str] = None
    parameters: Optional[dict] = None      # JSON Schema

class ToolDefinition(BaseModel):
    """도구 정의"""
    type: str = "function"
    function: FunctionDefinition

class FunctionCall(BaseModel):
    """도구 호출 응답"""
    name: str
    arguments: str                          # JSON 문자열

class ToolCall(BaseModel):
    """도구 호출"""
    id: str
    type: str = "function"
    function: FunctionCall

# ── 기존 스키마 수정 ──

class ChatMessage(BaseModel):
    """채팅 메시지 (tool call 지원)"""
    role: str                               # "system"|"user"|"assistant"|"tool"
    content: Optional[str] = None           # ★ None 허용 (tool_calls 시)
    tool_calls: Optional[list[ToolCall]] = None   # assistant의 도구 호출
    tool_call_id: Optional[str] = None      # tool role 메시지의 호출 ID

class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions 요청 (tool call 지원)"""
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list[ToolDefinition]] = None     # ★ 추가
    tool_choice: Optional[str | dict] = None         # ★ 추가

class ChatCompletionChoice(BaseModel):
    """응답 선택지 (tool call 지원)"""
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"   # ★ "tool_calls" 추가 가능
```

### 4.4 공급자별 Tool Call 변환

#### 4.4.1 Gemini (패스스루 + 정규화)

Gemini의 OpenAI 호환 엔드포인트는 `tools`, `tool_calls`를 지원하지만,
**스트리밍 응답에 OpenAI 스펙과 차이**가 있어 정규화 처리가 필요합니다.

```
요청: tools, tool_choice → 그대로 전달
응답(비스트리밍): tool_calls → 그대로 반환
응답(스트리밍):  tool_calls → ★ 정규화 후 반환
```

**★ 구현 중 발견된 이슈: 스트리밍 tool_calls 정규화**

Gemini 스트리밍 응답의 `tool_calls` 델타가 AI SDK(OpenCode) 스키마 검증에 실패:

```
Gemini 원본 (스트리밍):
─────────────────────────────────────────
tool_calls: [{
  "function": {...},
  "id": "...",
  "type": "function",
  "extra_content": {"google": {...}}   ← ① 비표준 필드
                                       ← ② index 필드 누락!
}]

프록시 정규화 후:
─────────────────────────────────────────
tool_calls: [{
  "index": 0,                          ← ② 자동 추가
  "function": {...},
  "id": "...",
  "type": "function"
                                       ← ① extra_content 제거
}]
```

`_normalize_stream_chunk()` 메서드에서 처리:

```python
def _normalize_stream_chunk(self, chunk_data: dict) -> dict:
    for choice in chunk_data.get("choices", []):
        delta = choice.get("delta", {})
        tool_calls = delta.get("tool_calls")
        if tool_calls:
            for i, tc in enumerate(tool_calls):
                if "index" not in tc:
                    tc["index"] = i          # ★ index 자동 추가
                tc.pop("extra_content", None) # ★ 비표준 필드 제거
    return chunk_data
```

#### 4.4.2 Claude (형식 변환)

Claude Anthropic API는 자체 Tool Use 형식을 사용합니다:

```
OpenAI 형식                         →  Anthropic 형식
──────────────────────────────────────────────────────────
tools[{function:{name,params}}]     →  tools[{name, input_schema}]
tool_choice: "auto"                 →  tool_choice: {type: "auto"}
tool_choice: "none"                 →  (tools 제거)
tool_choice: {function:{name:"x"}}  →  tool_choice: {type:"tool", name:"x"}
messages[role=tool]                 →  messages[role=user, 
                                        content=[{type:"tool_result",
                                                  tool_use_id, content}]]
──────────────────────────────────────────────────────────
응답 변환 (역방향):
content[{type:"tool_use",           →  tool_calls[{id, function:
  id, name, input}]                       {name, arguments(JSON)}}]
stop_reason: "tool_use"             →  finish_reason: "tool_calls"
```

#### 4.4.3 GenAI / SCI Portal

SCI Portal은 현재 Tool Call을 지원하지 않습니다.

```
요청에 tools가 포함된 경우:
→ 에러 응답: "GenAI (SCI Portal) does not support tool calling."
```

### 4.5 공통 유틸리티 (`providers/base.py`)

구현 과정에서 추가된 공통 유틸리티:

```python
def truncate_for_log(data, max_len: int = 300) -> str:
    """
    로그 출력용 문자열 변환 + 잘라내기.
    - dict/list → JSON 문자열로 변환
    - 문자열이 max_len보다 짧으면 전체 반환
    - 길면 max_len까지만 반환 + '...(truncated)' 접미사
    """
```

모든 Provider에서 요청/응답 로그 출력에 사용합니다.

### 4.6 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|---------|
| `ai-proxy/models.py` | **수정** | `ToolDefinition`, `ToolCall`, `FunctionCall` 등 스키마 추가, `ChatMessage.content` Optional 변경, `ChatCompletionRequest`에 `tools`/`tool_choice` 추가 |
| `ai-proxy/providers/base.py` | **수정** | `truncate_for_log()` 로그 유틸리티 추가 |
| `ai-proxy/providers/gemini_provider.py` | **수정** | `tools`, `tool_choice` 패스스루, `tool_calls` 응답 파싱, ★ `_normalize_stream_chunk()` 스트리밍 정규화 추가 |
| `ai-proxy/providers/claude_provider.py` | **수정** | `_transform_request()`에 tools 변환, 응답에서 `tool_use` → `tool_calls` 변환, `tool` role 메시지 변환, 상세 이벤트별 로그 추가 |
| `ai-proxy/providers/genai_provider.py` | **수정** | tools 요청 시 에러 반환 |
| `ai-proxy/proxy_server.py` | 변경 없음 | (스키마 변경이 자동 반영됨) |

---

## 5. 구현 계획 (Implementation Plan)

### 5.1 단계별 구현

| 단계 | 작업 | 산출물 |
|------|------|--------|
| **Step 1** | `models.py` 스키마 확장 (Tool 관련 모델 추가) | `models.py` |
| **Step 2** | Gemini Provider에 tools/tool_calls 패스스루 추가 | `gemini_provider.py` |
| **Step 3** | Claude Provider에 Tool Use ↔ OpenAI Tool Call 변환 추가 | `claude_provider.py` |
| **Step 4** | GenAI Provider에 tools 미지원 에러 처리 추가 | `genai_provider.py` |
| **Step 5** | 통합 테스트 (OpenCode tool call 시나리오) | 테스트 결과 |

### 5.2 구현 우선순위

```
Step 1 (스키마) → Step 2 (Gemini) → Step 3 (Claude) → Step 4 (GenAI) → Step 5 (테스트)
       ↓               ↓                ↓                ↓
   필수: 모든        필수: 가장       필수: 변환       권장: 에러
   Provider 공통    간단 (패스스루)   로직 복잡       메시지만
```

---

## 6. 테스트 계획 (Test Plan)

### 6.1 Tool Call 테스트

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-053-001 | tools 필드 포함 요청 (Gemini) | tool_calls 응답 반환 |
| TC-053-002 | tool role 메시지 포함 후속 요청 (Gemini) | 최종 텍스트 응답 |
| TC-053-003 | tools 필드 포함 요청 (Claude) | tool_calls 응답 (OpenAI 형식) |
| TC-053-004 | tool role 메시지 포함 후속 요청 (Claude) | 최종 텍스트 응답 |
| TC-053-005 | tools 스트리밍 요청 (Gemini) | SSE tool_calls 델타 |
| TC-053-006 | tools 스트리밍 요청 (Claude) | SSE tool_calls 델타 |
| TC-053-007 | tools 필드 포함 요청 (GenAI) | 에러 응답 (미지원) |
| TC-053-008 | tools 없는 기존 텍스트 요청 | 기존과 동일 동작 (하위 호환) |

### 6.2 curl 테스트 명령

```bash
# Tool Call 요청 (Gemini)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ai-proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini/gemini-3-pro-preview",
    "messages": [{"role": "user", "content": "서울 날씨를 알려줘"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "도시의 현재 날씨 조회",
        "parameters": {
          "type": "object",
          "properties": {"city": {"type": "string"}},
          "required": ["city"]
        }
      }
    }],
    "tool_choice": "auto"
  }'
```

---

## 7. 주의사항

| 항목 | 설명 |
|------|------|
| **Claude tool_use ID** | Anthropic은 `tool_use` 블록에 자체 ID를 생성합니다. 이 ID를 `tool_calls[].id`로 매핑해야 합니다. |
| **arguments 형식** | OpenAI는 `arguments`를 **JSON 문자열**로 전달하고, Anthropic은 `input`을 **JSON 객체**로 전달합니다. `json.dumps()` / `json.loads()` 변환이 필요합니다. |
| **tool_choice 변환** | OpenAI의 `"auto"` / `"none"` / `{"function":{"name":"x"}}` → Anthropic의 `{"type":"auto"}` / (tools 제거) / `{"type":"tool","name":"x"}` 형식 차이. |
| **finish_reason** | Tool Call 응답의 `finish_reason`은 `"tool_calls"` (OpenAI) / `"tool_use"` (Anthropic)입니다. 프록시에서 통일합니다. |
| **스트리밍 tool_calls** | 스트리밍 시 `tool_calls` 델타는 `arguments`가 조각별로 전달됩니다. Gemini는 **정규화 후 전달**, Claude는 `content_block_delta`에서 변환해야 합니다. |
| **다중 Tool Call** | 하나의 응답에서 여러 tool_calls가 반환될 수 있습니다. `index` 필드로 구분합니다. |
| **하위 호환** | `tools` 필드가 없는 기존 요청은 기존과 동일하게 동작해야 합니다 (Optional 처리). |
| **★ Gemini index 누락** | Gemini 스트리밍 tool_calls에 `index` 필드가 누락됩니다. AI SDK는 이를 필수로 요구하므로 프록시에서 자동 추가해야 합니다. |
| **★ Gemini extra_content** | Gemini 스트리밍 응답에 `extra_content.google.thought_signature` 등 비표준 필드가 포함됩니다. AI SDK 스키마 검증 실패를 방지하기 위해 제거합니다. |

---

## 8. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.053 | 2026-03-01 | - | 최초 작성 |
| v1.0.053.1 | 2026-03-01 | - | 구현 완료. Gemini 스트리밍 정규화(`_normalize_stream_chunk`) 추가, `truncate_for_log` 유틸 추가, 주의사항에 Gemini index/extra_content 이슈 추가 |
