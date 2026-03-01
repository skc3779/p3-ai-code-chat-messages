# FSD v1.0.052 - 로컬 프록시 서버 (Python FastAPI) 구축

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.052 |
| 제목 | OpenAI 호환 로컬 프록시 서버 구축 (Python FastAPI) |
| 작성일 | 2026-03-01 |
| 상태 | 초안 |
| 참조 SRS | [SRS v1.0.052 v2](../api-specs/SRS_v1.0.052_openai-compatible-provider_v2.md) |
| 참조 REP | [REP v1.0.052 LiteLLM 검토](../reports/REP_v1.0.052_litellm-proxy-review.md) — LiteLLM 불필요 판정, FastAPI 직접 구현 유지 |
| 검증 대상 | FastAPI 프록시 서버 + OpenCode Custom Provider 연동 |

---

## 1. 개요 (Overview)

본 문서는 **GenAI, Claude, Gemini** 3개 AI 공급자의 API 엔드포인트를 **OpenAI 호환 인터페이스로 단일화**하기 위한 **로컬 프록시 서버(Python FastAPI)**를 구축하는 기능 설계 문서입니다.

전체 코드 개선에 앞서, 다음 2가지의 정상 동작을 먼저 검증합니다:

1. **로컬 프록시 서버** — FastAPI 기반 OpenAI 호환 API 프록시
2. **OpenCode Custom Provider** — 프록시 서버를 OpenCode의 AI Provider로 등록하여 사용

---

## 2. 배경 (Background)

### 2.1 현재 구조와 문제점

| 문제 | 설명 |
|------|------|
| 3벌의 코드 | `GenAICodeAssistant`, `ClaudeCodeAssistant`, `GeminiCodeAssistant` 별도 유지 |
| API 형식 불일치 | 각 공급자마다 요청/응답 형식, 인증 방식이 다름 |
| 확장 어려움 | 새 공급자 추가 시 전용 Assistant 클래스 신규 개발 필요 |

### 2.2 해결 목표 아키텍처

```
[Python 앱 / OpenCode]
        │  
        │  POST http://localhost:8000/v1/chat/completions
        │  (OpenAI 형식 통일)
        ▼
[FastAPI 프록시 서버 (localhost:8000)]
        │  모델 접두사로 라우팅 + 형식 변환
        ├──→ SCI Portal (GenAI: gpt-oss-120B-medium)
        ├──→ Anthropic  (Claude: claude-3-5-haiku-latest)
        └──→ Google     (Gemini: gemini-3-pro-preview)
```

---

## 3. 요구사항 (Requirements)

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| REQ-052-001 | FastAPI 기반 OpenAI 호환 `/v1/chat/completions` 엔드포인트를 제공해야 한다 | 필수 |
| REQ-052-002 | 모델 ID 접두사(`gemini/`, `claude/`, `genai/`)로 공급자를 라우팅해야 한다 | 필수 |
| REQ-052-003 | Gemini Provider: Google OpenAI 호환 엔드포인트로 패스스루해야 한다 | 필수 |
| REQ-052-004 | Claude Provider: OpenAI 형식 → Anthropic Messages API 형식으로 변환해야 한다 | 필수 |
| REQ-052-005 | GenAI Provider: OpenAI 형식 → SCI Portal 형식으로 변환해야 한다 | 필수 |
| REQ-052-006 | `/v1/models` 엔드포인트로 지원 모델 목록을 조회할 수 있어야 한다 | 필수 |
| REQ-052-007 | 비스트리밍(일반) 응답을 지원해야 한다 | 필수 |
| REQ-052-008 | 스트리밍(SSE) 응답을 지원해야 한다 | 권장 |
| REQ-052-009 | `Authorization: Bearer <key>` 기반 프록시 인증을 지원해야 한다 | 권장 |
| REQ-052-010 | `/health` 엔드포인트로 서버 상태를 확인할 수 있어야 한다 | 권장 |

### 3.2 OpenCode 연동 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| REQ-052-011 | OpenCode의 Custom Provider로 프록시 서버를 등록할 수 있어야 한다 | 필수 |
| REQ-052-012 | `opencode.json`에 프록시 provider 설정을 정의해야 한다 | 필수 |
| REQ-052-013 | OpenCode `/connect` 명령으로 프록시 인증 키를 등록할 수 있어야 한다 | 필수 |
| REQ-052-014 | OpenCode `/models` 명령에서 프록시 모델이 표시되어야 한다 | 필수 |

### 3.3 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-052-001 | Python 3.10 이상에서 동작해야 한다 |
| NREQ-052-002 | 의존 패키지: `fastapi`, `uvicorn`, `httpx`, `python-dotenv`, `pydantic` |
| NREQ-052-003 | 프록시 응답 지연은 원격 API 응답 시간 + 100ms 이내여야 한다 |
| NREQ-052-004 | 에러 발생 시 OpenAI 형식 에러 응답(`{"error": {...}}`)을 반환해야 한다 |

---

## 4. 설계 (Design)

### 4.1 프로젝트 구조

```
ai-proxy/
├── proxy_server.py              ← FastAPI 메인 서버 + uvicorn 실행
├── models.py                    ← Pydantic 요청/응답/에러 스키마
├── router.py                    ← 모델명 접두사 기반 Provider 라우팅
├── providers/
│   ├── __init__.py              ← Provider 클래스 일괄 export
│   ├── base.py                  ← Provider 추상 클래스 (chat, stream)
│   ├── gemini_provider.py       ← Gemini (OpenAI 호환 패스스루)
│   ├── claude_provider.py       ← Claude (Anthropic ↔ OpenAI 변환)
│   └── genai_provider.py        ← GenAI SCI Portal (커스텀 ↔ OpenAI 변환)
├── .env                         ← API 키 (프록시 전용, Git 미추적)
├── .env.example                 ← .env 템플릿 (Git 추적)
└── requirements.txt             ← Python 의존성 (pip install -r)
```

### 4.2 API 엔드포인트 설계

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/v1/chat/completions` | 채팅 완성 (OpenAI 호환) |
| `GET` | `/v1/models` | 지원 모델 목록 |
| `GET` | `/health` | 서버 상태 확인 |

### 4.3 요청/응답 형식

**요청 (OpenAI Chat Completions 형식)**:

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

**응답 (OpenAI Chat Completions 형식)**:

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
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 8,
    "total_tokens": 20
  }
}
```

**에러 응답 (OpenAI 형식, REQ-052-004)**:

```json
{
  "error": {
    "message": "Unknown model: 'invalid/model'. Use prefix: gemini/, claude/, genai/",
    "type": "invalid_request_error",
    "code": 400
  }
}
```

**스트리밍 응답 (SSE 형식, `stream: true` 시, REQ-052-008)**:

```
data: {"choices":[{"delta":{"content":"Hello"},"index":0}]}

data: {"choices":[{"delta":{"content":"! How"},"index":0}]}

data: {"choices":[{"delta":{"content":" can I help?"},"index":0}]}

data: [DONE]
```

### 4.4 공급자별 변환 로직

#### 4.4.1 Gemini (패스스루)

```
Python 앱 요청 (OpenAI 형식)
    │
    ▼ 그대로 전달 (패스스루)
    │
Google OpenAI 호환 API
https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
```

- Gemini는 공식 OpenAI 호환 엔드포인트 제공 → 변환 불필요
- baseURL 끝에 `/openai/` 필수

#### 4.4.2 Claude (형식 변환)

```
OpenAI 형식                         →  Anthropic 형식
─────────────────────────────────────────────────────
model: "claude-3-5-haiku-latest"   →  model: "claude-3-5-haiku-latest" (그대로)
messages[role=system]          →  system: "..." (별도 파라미터)
messages[role=user/assistant]       →  messages: [...]
(선택) max_tokens                   →  max_tokens: 4096 (필수! 미지정 시 기본값 추가)
Authorization: Bearer               →  x-api-key + anthropic-version: 2023-06-01
─────────────────────────────────────────────────
choices[0].message.content          ←  content[0].text
usage.prompt_tokens                 ←  usage.input_tokens
usage.completion_tokens             ←  usage.output_tokens
```

> **주의**: 프록시의 라우터가 접두사(`claude/`)를 분리한 후 실제 모델 ID(`claude-3-5-haiku-latest`)를 Anthropic API에 그대로 전달합니다. 모델 ID 자체의 변환은 하지 않습니다.

#### 4.4.3 GenAI / SCI Portal (커스텀 변환)

```
OpenAI 형식                    →  SCI Portal 형식
─────────────────────────────────────────────────
model: "gpt-oss-120B-medium"  →  model_id: "gpt-oss-120B-medium"
messages: [{role, content}]    →  prompt: [{role, text}]
temperature: 0.7               →  parameters.temperature: 0.7
max_tokens: 2048               →  parameters.max_output_tokens: 2048
Authorization: Bearer          →  X-Client-Key + X-Client-Secret
```

### 4.5 모델 ID 라우팅 규칙

```
요청 model 값                        Provider          실제 모델 ID
──────────────────────────────────────────────────────────────────
"gemini/gemini-3-pro-preview"    →  GeminiProvider  →  "gemini-3-pro-preview"
"gemini/gemini-3-flash-preview"  →  GeminiProvider  →  "gemini-3-flash-preview"
"claude/claude-3-5-haiku-latest" →  ClaudeProvider  →  "claude-3-5-haiku-latest"
"claude/claude-sonnet-4-5"       →  ClaudeProvider  →  "claude-sonnet-4-5"
"genai/gpt-oss-120B-medium"     →  GenAIProvider   →  "gpt-oss-120B-medium"
```

---

## 5. OpenCode Custom Provider 연동 설계

### 5.1 OpenCode Custom Provider 스펙

OpenCode는 `opencode.json` 설정 파일을 통해 Custom Provider를 등록할 수 있습니다. 내부적으로 `@ai-sdk/openai-compatible` NPM 패키지를 사용하여 OpenAI 호환 API와 통신합니다.

**설정 옵션:**

| 옵션 | 설명 |
|------|------|
| `npm` | AI SDK 패키지명 (`@ai-sdk/openai-compatible`) |
| `name` | UI 표시 이름 |
| `options.baseURL` | API 엔드포인트 URL |
| `options.apiKey` | API 키 (환경변수 참조 가능: `{env:VAR_NAME}`) |
| `options.headers` | 커스텀 HTTP 헤더 |
| `models` | 사용 가능한 모델 목록 |
| `models.*.name` | 모델 표시 이름 |
| `models.*.limit.context` | 최대 입력 토큰 수 |
| `models.*.limit.output` | 최대 출력 토큰 수 |

### 5.2 `opencode.json` 설정

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ai-proxy": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "AI Proxy (GenAI/Claude/Gemini)",
      "options": {
        "baseURL": "http://localhost:8000/v1",
        "apiKey": "{env:PROXY_API_KEY}"
      },
      "models": {
        "genai/gpt-oss-120B-medium": {
          "name": "GenAI GPT-OSS 120B Medium (SCI Portal)",
          "limit": {
            "context": 32000,
            "output": 4096
          }
        },
        "claude/claude-3-5-haiku-latest": {
          "name": "Claude 3.5 Haiku (Anthropic)",
          "limit": {
            "context": 200000,
            "output": 8192
          }
        },
        "gemini/gemini-3-pro-preview": {
          "name": "Gemini 3 Pro (Google)",
          "limit": {
            "context": 1048576,
            "output": 65536
          }
        },
        "gemini/gemini-3-flash-preview": {
          "name": "Gemini 3 Flash (Google)",
          "limit": {
            "context": 1048576,
            "output": 65536
          }
        }
      }
    }
  }
}
```

### 5.3 OpenCode 연동 절차

```
① 프록시 서버 실행
   $ cd ai-proxy && python proxy_server.py

② OpenCode에서 Custom Provider 등록
   $ opencode
   > /connect
   > Other 선택
   > Provider ID: ai-proxy
   > API Key: proxy-secret-key

③ opencode.json 파일을 **OpenCode를 실행하는 작업 프로젝트의 루트**에 배치 (§5.2 참조)
   ※ ai-proxy/ 폴더가 아닌, OpenCode가 동작하는 프로젝트 루트 (예: C:/Users/<username>/.config/opencode/ or C:/Tools/OpenCode/ )

④ 모델 선택
   > /models
   > "GenAI GPT-OSS 120B Medium (SCI Portal)" 선택

⑤ 정상 동작 확인
   > 코드 관련 질문 입력
   > 프록시 → SCI Portal → 응답 확인
```

### 5.4 연동 흐름도

```
┌──────────────┐      ┌──────────────────────┐      ┌──────────────┐
│   OpenCode   │      │  FastAPI 프록시 서버   │      │  원격 API    │
│   (클라이언트) │      │  (localhost:8000)     │      │  서버        │
└──────┬───────┘      └──────────┬───────────┘      └──────┬───────┘
       │  ① OpenAI 형식 요청     │                         │
       │  model: "genai/gpt-    │                         │
       │    oss-120B-medium"    │                         │
       │───────────────────────>│                         │
       │                        │  ② 접두사 라우팅          │
       │                        │  "genai/" → GenAIProvider│
       │                        │                         │
       │                        │  ③ 형식 변환              │
       │                        │  OpenAI → SCI Portal    │
       │                        │                         │
       │                        │  ④ 변환된 요청 전달       │
       │                        │────────────────────────>│
       │                        │                         │
       │                        │  ⑤ SCI Portal 형식 응답  │
       │                        │<────────────────────────│
       │                        │                         │
       │                        │  ⑥ 응답 변환             │
       │                        │  SCI Portal → OpenAI    │
       │                        │                         │
       │  ⑦ OpenAI 형식 응답     │                         │
       │<───────────────────────│                         │
       │                        │                         │
```

---

## 6. 환경변수 설계

### 6.1 프록시 서버 (`ai-proxy/.env`)

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

### 6.2 OpenCode 환경변수

```ini
# OpenCode에서 프록시 인증에 사용
PROXY_API_KEY=proxy-secret-key
```

---

## 7. 구현 계획 (Implementation Plan)

### 7.1 단계별 구현

| 단계 | 작업 | 산출물 |
|------|------|--------|
| **Step 1** | 프로젝트 구조 생성 및 의존성 설치 | `ai-proxy/`, `requirements.txt` |
| **Step 2** | Pydantic 스키마 정의 | `models.py` |
| **Step 3** | Provider 추상 클래스 구현 | `providers/base.py` |
| **Step 4** | Gemini Provider 구현 (패스스루) | `providers/gemini_provider.py` |
| **Step 5** | Claude Provider 구현 (형식 변환) | `providers/claude_provider.py` |
| **Step 6** | GenAI Provider 구현 (SCI Portal 변환) | `providers/genai_provider.py` |
| **Step 7** | 라우터 구현 | `router.py` |
| **Step 8** | FastAPI 서버 구현 | `proxy_server.py` |
| **Step 9** | OpenCode `opencode.json` 작성 | `opencode.json` |
| **Step 10** | 통합 검증 | 테스트 결과 |

### 7.2 변경/생성 파일 목록

| 파일 | 유형 | 설명 |
|------|------|------|
| `ai-proxy/proxy_server.py` | 신규 | FastAPI 메인 서버 |
| `ai-proxy/models.py` | 신규 | Pydantic 스키마 (요청/응답/에러) |
| `ai-proxy/router.py` | 신규 | 모델 라우팅 |
| `ai-proxy/providers/__init__.py` | 신규 | Provider 클래스 일괄 export |
| `ai-proxy/providers/base.py` | 신규 | Provider 추상 클래스 |
| `ai-proxy/providers/gemini_provider.py` | 신규 | Gemini Provider |
| `ai-proxy/providers/claude_provider.py` | 신규 | Claude Provider |
| `ai-proxy/providers/genai_provider.py` | 신규 | GenAI Provider |
| `ai-proxy/.env` | 신규 | 프록시 환경변수 (Git 미추적) |
| `ai-proxy/.env.example` | 신규 | .env 템플릿 (Git 추적) |
| `ai-proxy/requirements.txt` | 신규 | Python 의존성 |
| `opencode.json` | 신규 | OpenCode Custom Provider 설정 (작업 프로젝트 루트) |

### 7.3 `requirements.txt` 내용

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
httpx>=0.28.0
python-dotenv>=1.0.0
pydantic>=2.0.0
```

### 7.4 프록시 서버 실행 방법

```bash
# 의존성 설치
cd ai-proxy
pip install -r requirements.txt

# 개발 모드 (자동 리로드)
uvicorn proxy_server:app --reload --port 8000

# 또는 직접 실행
python proxy_server.py

# 백그라운드 실행 (Windows)
start /b python proxy_server.py

# 백그라운드 실행 (Linux/macOS)
nohup python proxy_server.py &
```

---

## 8. 테스트 계획 (Test Plan)

### 8.1 프록시 서버 테스트

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-052-001 | 프록시 서버 시작 (`python proxy_server.py`) | `localhost:8000`에서 정상 리스닝 |
| TC-052-002 | `GET /health` 호출 | `{"status": "ok"}` 응답 |
| TC-052-003 | `GET /v1/models` 호출 | 지원 모델 목록 반환 |
| TC-052-004 | Gemini 모델로 `/v1/chat/completions` 호출 | 정상 응답 (OpenAI 형식) |
| TC-052-005 | Claude 모델로 `/v1/chat/completions` 호출 | 정상 응답 (OpenAI 형식) |
| TC-052-006 | GenAI 모델로 `/v1/chat/completions` 호출 | 정상 응답 (OpenAI 형식) |
| TC-052-007 | 잘못된 모델 ID로 호출 | 400 에러 + OpenAI 형식 에러 응답 |
| TC-052-008 | 인증 없이 호출 | 401 Unauthorized |
| TC-052-009 | 스트리밍 요청 (`stream: true`) | SSE 형식 스트리밍 응답 |

### 8.2 OpenCode 연동 테스트

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-052-010 | OpenCode `/connect`로 ai-proxy 등록 | 인증 정보 저장 성공 |
| TC-052-011 | OpenCode `/models`에서 프록시 모델 표시 | 등록한 모델 목록 표시 |
| TC-052-012 | OpenCode에서 Gemini 모델 선택 후 질문 | 프록시 경유 정상 응답 |
| TC-052-013 | OpenCode에서 Claude 모델 선택 후 질문 | 프록시 경유 정상 응답 |
| TC-052-014 | OpenCode에서 GenAI 모델 선택 후 질문 | 프록시 경유 정상 응답 |

### 8.3 curl 테스트 명령

```bash
# 서버 상태 확인
curl http://localhost:8000/health

# 모델 목록
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer proxy-secret-key"

# Gemini 호출
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini/gemini-3-pro-preview","messages":[{"role":"user","content":"Hello"}]}'

# Claude 호출
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude/claude-3-5-haiku-latest","messages":[{"role":"user","content":"Hello"}]}'

# GenAI 호출
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"genai/gpt-oss-120B-medium","messages":[{"role":"user","content":"Hello"}]}'
```

---

## 9. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.052 | 2026-03-01 | - | 최초 작성 |
| v1.0.052 rev.1 | 2026-03-01 | - | 검토 반영: 에러/SSE 형식 추가, requirements.txt 상세화, 실행 방법 보강, Claude 변환 설명 수정, REP 참조 추가 |
