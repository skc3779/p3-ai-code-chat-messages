# AI Proxy Server

**OpenAI 호환 로컬 프록시 서버** — GenAI, Claude, Gemini를 단일 API 엔드포인트로 통합 (Tool Call 지원)

## 개요

AI Proxy Server는 Python FastAPI 기반의 로컬 프록시 서버로, 3개 AI 공급자(GenAI/SCI Portal, Anthropic Claude, Google Gemini)의 API를 **OpenAI 호환 형식의 단일 엔드포인트**로 통합합니다. **Tool Call(도구 호출)** 기능을 포함하여 모든 공급자에서 동일한 OpenAI tools 인터페이스를 사용할 수 있습니다. 클라이언트에서는 OpenAI SDK의 `base_url`만 프록시 주소로 변경하면, 모델명만 바꿔서 모든 공급자를 동일한 코드로 사용할 수 있습니다.

## 아키텍처

```
┌─────────────────────────────────┐
│  Python 앱 / OpenCode           │
│  OpenAI SDK (openai 패키지)     │
│  base_url: localhost:8000/v1    │
└──────────────┬──────────────────┘
               │ POST /v1/chat/completions
               │ model: "gemini/gemini-3-pro-preview"
               ▼
┌──────────────────────────────────────────────┐
│        AI Proxy Server (FastAPI)             │
│        http://localhost:8000                 │
│                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐│
│  │  Gemini    │ │  Claude    │ │  GenAI     ││
│  │  Provider  │ │  Provider  │ │  Provider  ││
│  │ (패스스루  │ │ (형식변환  │ │ (형식변환  ││
│  │ +TC 정규화)│ │ +TC 변환)  │ │ +TC 에뮬) ││
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘│
└────────┼──────────────┼──────────────┼───────┘
         ▼              ▼              ▼
   Google API      Anthropic      SCI Portal
   (원격 서버)      (원격 서버)     (원격 서버)
```

## 프로젝트 구조

```
ai-proxy/
├── proxy_server.py              ← FastAPI 메인 서버 + uvicorn 실행
├── models.py                    ← Pydantic 요청/응답/에러/Tool Call 스키마
│                                   (content: str | list 유연 타입 지원)
├── router.py                    ← 모델명 접두사 기반 Provider 라우팅
├── providers/
│   ├── __init__.py              ← Provider 클래스 일괄 export
│   ├── base.py                  ← Provider 추상 클래스 + 공통 유틸
│   │                               (truncate_for_log, _retry_on_429)
│   ├── gemini_provider.py       ← Gemini (패스스루 + Tool Call 정규화)
│   │                               (_normalize_stream_chunk)
│   ├── claude_provider.py       ← Claude (Tool Use ↔ OpenAI Tool Call 변환)
│   └── genai_provider.py        ← GenAI SCI Portal (Tool Call 에뮬레이션)
│                                   (민감 단어 필터링, 429 재시도)
├── test_toolcall.py             ← Tool Call 통합 테스트 스크립트
├── .env                         ← API 키 (Git 미추적)
├── .env.example                 ← .env 템플릿 (Git 추적)
└── requirements.txt             ← Python 의존성
```

## 설치

### 1. 의존성 설치

```bash
cd ai-proxy
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env.example`을 복사하여 `.env`를 만들고, 실제 API 키를 입력합니다:

```bash
cp .env.example .env
```

```ini
# ===== 프록시 서버 =====
PROXY_PORT=8000
PROXY_API_KEY=proxy-secret-key

# ----- Gemini -----
GEMINI_API_KEY=AIzaSy...

# ----- Claude -----
ANTHROPIC_API_KEY=sk-ant-api03-...

# ----- GenAI (Samsung SCI Portal) -----
ENDPOINT_URL=https://scisportaldev.samsungif.net/rest/genAi
YOUR_CLIENT_KEY=API_CLIENT_APP
YOUR_CLIENT_SECRET=
```

| 환경 변수 | 설명 |
|-----------|------|
| `PROXY_PORT` | 프록시 서버 포트 (기본 8000) |
| `PROXY_API_KEY` | 프록시 접근용 인증 키 |
| `GEMINI_API_KEY` | Google Gemini API 키 |
| `ANTHROPIC_API_KEY` | Anthropic Claude API 키 |
| `ENDPOINT_URL` | GenAI SCI Portal 엔드포인트 URL |
| `YOUR_CLIENT_KEY` | SCI Portal Client Key |
| `YOUR_CLIENT_SECRET` | SCI Portal Client Secret |

## 사용법

### 서버 실행

```bash
# 직접 실행
cd ai-proxy
python proxy_server.py

# 개발 모드 (자동 리로드)
uvicorn proxy_server:app --reload --port 8000

# 백그라운드 실행 (Windows)
start /b python proxy_server.py

# 백그라운드 실행 (Linux/macOS)
nohup python proxy_server.py &
```

### Python 클라이언트

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="ai-proxy-secret-key",
)

# ★ 모델명만 바꾸면 공급자 전환!
# Gemini
response = client.chat.completions.create(
    model="gemini/gemini-3-pro-preview",
    messages=[{"role": "user", "content": "Hello"}],
)

# Claude
response = client.chat.completions.create(
    model="claude/claude-3-5-haiku-latest",
    messages=[{"role": "user", "content": "Hello"}],
)

# GenAI (SCI Portal)
response = client.chat.completions.create(
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "Hello"}],
)

print(response.choices[0].message.content)
```

### curl 테스트

```bash
# 서버 상태 확인
curl http://localhost:8000/health

# 모델 목록
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer ai-proxy-secret-key"

# Gemini 호출
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ai-proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini/gemini-3-pro-preview","messages":[{"role":"user","content":"Hello"}]}'

# Claude 호출
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ai-proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude/claude-3-5-haiku-latest","messages":[{"role":"user","content":"Hello"}]}'

# GenAI 호출
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ai-proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"genai/gpt-oss-120B-medium","messages":[{"role":"user","content":"Hello"}]}'
```

## 지원 모델

| 모델 ID | 공급자 | 설명 | Tool Call |
|---------|--------|------|:---------:|
| `gemini/gemini-3-pro-preview` | Google | Gemini 3 Pro | ✅ 네이티브 |
| `gemini/gemini-3-flash-preview` | Google | Gemini 3 Flash | ✅ 네이티브 |
| `claude/claude-haiku-4-5` | Anthropic | Claude Haiku 4.5 | ✅ 변환 |
| `claude/claude-sonnet-4-6` | Anthropic | Claude Sonnet 4.6 | ✅ 변환 |
| `genai/gpt-oss-120B-medium` | Samsung SCI Portal | GPT-OSS 120B Medium | ✅ 에뮬레이션 |

## API 사양

### 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/v1/chat/completions` | 채팅 완성 (OpenAI 호환) |
| `GET` | `/v1/models` | 지원 모델 목록 |
| `GET` | `/health` | 서버 상태 확인 |

### Request (텍스트)

```json
{
  "model": "gemini/gemini-3-pro-preview",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello"}
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 2048
}
```

### Request (Tool Call)

```json
{
  "model": "gemini/gemini-3-pro-preview",
  "messages": [
    {"role": "user", "content": "Get weather for Seoul"}
  ],
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get current weather for a city",
      "parameters": {
        "type": "object",
        "properties": {
          "city": {"type": "string", "description": "City name"}
        },
        "required": ["city"]
      }
    }
  }],
  "tool_choice": "auto"
}
```

> **참고:** `content` 필드는 문자열뿐만 아니라 `[{"type": "text", "text": "..."}]` 형태의 content parts 배열도 지원합니다 (멀티모달 호환).

### Response (텍스트)

```json
{
  "id": "chatcmpl-1709312345",
  "object": "chat.completion",
  "model": "gemini/gemini-3-pro-preview",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello! How can I help?"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
}
```

### Response (Tool Call)

```json
{
  "id": "chatcmpl-1709312345",
  "object": "chat.completion",
  "model": "gemini/gemini-3-pro-preview",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"city\":\"Seoul\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

### Error Response

```json
{
  "error": {
    "message": "Unknown model: 'invalid/model'. Use prefix: gemini/, claude/, genai/",
    "type": "invalid_request_error",
    "code": 400
  }
}
```

### 스트리밍 응답 (SSE)

`stream: true` 설정 시 Server-Sent Events 형식으로 응답:

```
data: {"choices":[{"delta":{"role":"assistant"},"index":0}]}

data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}

data: {"choices":[{"delta":{"content":" world!"},"index":0}]}

data: {"choices":[{"delta":{},"finish_reason":"stop","index":0}]}

data: [DONE]
```

## 공급자별 변환 로직

### Gemini (패스스루 + Tool Call 정규화)

- Google 공식 OpenAI 호환 엔드포인트 사용
- Base URL: `https://generativelanguage.googleapis.com/v1beta/openai`
- 요청/응답 그대로 전달 (tools/tool_choice 포함)
- ★ **스트리밍 tool_calls 정규화**: `index` 자동 추가, `extra_content` 제거

### Claude (형식 변환 + Tool Use 양방향 변환)

**기본 메시지 변환:**

| OpenAI 형식 | → | Anthropic 형식 |
|-------------|---|----------------|
| `messages[role=system]` | → | `system` (별도 파라미터) |
| `max_tokens` (선택) | → | `max_tokens` (필수, 기본값 4096) |
| `Authorization: Bearer` | → | `x-api-key` + `anthropic-version` |
| `choices[0].message.content` | ← | `content[0].text` |
| `usage.prompt_tokens` | ← | `usage.input_tokens` |

**Tool Call 변환:**

| OpenAI 형식 | ↔ | Anthropic 형식 |
|-------------|---|----------------|
| `tools[{function:{name,parameters}}]` | → | `tools[{name,input_schema}]` |
| `tool_choice: "auto"` | → | `{type: "auto"}` |
| `tool_choice: "required"` | → | `{type: "any"}` |
| `tool_calls[{id,function}]` | ← | `content[{type:"tool_use"}]` |
| `finish_reason: "tool_calls"` | ← | `stop_reason: "tool_use"` |

### GenAI / SCI Portal (커스텀 변환 + Tool Call 에뮬레이션)

**기본 메시지 변환:**

| OpenAI 형식 | → | SCI Portal 형식 |
|-------------|---|-----------------|
| `model` | → | `modelIds` (배열) |
| `messages[{role, content}]` | → | `contents` (문자열 배열) + `systemPrompt` |
| `temperature` | → | `llmConfig.temperature` |
| `max_tokens` | → | `llmConfig.max_new_tokens` |
| `Authorization: Bearer` | → | `X-Lego-Client-Id` + `X-Lego-Client-Secret` |

**★ Tool Call 에뮬레이션** (SCI Portal은 네이티브 Tool Calling 미지원):

| OpenAI 형식 | → | 에뮬레이션 방식 |
|-------------|---|---------|
| `tools` 배열 | → | 시스템 프롬프트에 도구 정의 텍스트 삽입 |
| `tool_choice` | → | 프롬프트 지시문 (`"none"`=미삽입, `"required"`=강제 사용) |
| `tool` role 메시지 | → | `[Tool Result for {name}]` 텍스트로 변환 |
| AI 응답 `` ```tool_call``` `` | ← | 파싱하여 `tool_calls` 형식으로 변환 |

**★ 민감 단어 필터링**: GenAI Provider 요청 시 `password`, `secret`, `token` 등의 민감 키워드를 자동으로 치환하여 SCI Portal 보안 필터 차단을 방지하고, 응답 수신 후 원래 단어로 복원합니다.

## OpenCode 연동

`opencode.json`을 OpenCode가 동작하는 프로젝트 루트에 배치하면, OpenCode의 Custom Provider로 프록시를 사용할 수 있습니다.

```bash
# OpenCode에서 Provider 등록
> /connect
> Other 선택
> Provider ID: ai-proxy
> API Key: proxy-secret-key

# 모델 선택
> /models
> 원하는 모델 선택
```

## 관련 문서

| 문서 | 설명 |
|------|------|
| [SRS v1.0.052 v2](docs/specs/api-specs/SRS_v1.0.052_openai-compatible-provider_v2.md) | 소프트웨어 요구사항 명세 (FastAPI 아키텍처) |
| [FSD v1.0.052](docs/specs/requirements/FSD_v1.0.052_openai-compatible-proxy.md) | 기능 설계 — 프록시 서버 기본 구축 |
| [FSD v1.0.053](docs/specs/requirements/FSD_v1.0.053_openai-compatible-proxy-toolcall.md) | 기능 설계 — Tool Call 기능 추가 |
| [FSD v1.0.054 v2](docs/specs/requirements/FSD_v1.0.054_genai-provider-toolcall_v2.md) | 기능 설계 — GenAI Tool Call 에뮬레이션 |
| [FSD v1.0.055](docs/specs/requirements/FSD_v1.0.055_genai-provider-endpoint-fix.md) | 기능 설계 — GenAI Endpoint URL 수정 |
| [FSD v1.0.058](docs/specs/requirements/FSD_v1.0.058_sensitive-word-filter.md) | 기능 설계 — 민감 단어 필터링 |
| [BUG v1.0.057](docs/specs/requirements/BUG_v1.0.057_genai-content-string-validation.md) | 버그 수정 — content 타입 유연성 개선 |
| [REP v1.0.052](docs/specs/reports/REP_v1.0.052_litellm-proxy-review.md) | LiteLLM 검토 보고서 (불필요 판정) |
| [REP v1.0.054](docs/specs/reports/REP_v1.0.054_toolcall-implementation.md) | Tool Call 구현 보고서 |

## 라이선스

MIT License
