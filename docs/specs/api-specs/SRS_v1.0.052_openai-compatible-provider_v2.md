# SRS v1.0.052 v2 - OpenAI 호환 API 프록시 (Python FastAPI 기반)

**버전**: v1.0.052 v2  
**작성일**: 2026-03-01  
**대상**: `gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py` 및 관련 모듈  
**프록시 기술**: Python FastAPI + httpx  
**참고**: [SRS v1.0.052 v1 (Node.js 기반)](./SRS_v1.0.052_openai-compatible-provider.md)

---

## 1. v1 → v2 변경 사유

### 1.1 Node.js vs Python FastAPI 비교

| 항목 | v1: Node.js + @ai-sdk/openai-compatible | v2: Python FastAPI + httpx |
|------|----------------------------------------|----------------------------|
| **언어 통일** | ❌ Python + Node.js 이중 관리 | ✅ **Python 단일 언어** |
| **유지보수** | 🟠 2개 런타임/패키지 관리 필요 | 🟢 기존 팀 역량으로 즉시 가능 |
| **배포 복잡도** | 🟠 Node.js 런타임 추가 설치 | 🟢 기존 Python 환경 그대로 |
| **의존성** | npm + pip 이중 관리 | pip 단일 관리 |
| **기존 코드 재사용** | ❌ 별도 구현 | ✅ 기존 Assistant 로직 활용 가능 |
| **비동기 성능** | ✅ 우수 (Node.js 이벤트 루프) | ✅ 우수 (FastAPI + asyncio) |
| **OpenAI 호환 구현** | ✅ @ai-sdk 패키지 자동 처리 | 🟡 직접 구현 (단, 명확한 스펙) |

> [!IMPORTANT]
> **결론**: 프로젝트 전체가 Python 기반이므로, **Python FastAPI로 프록시를 구현**하는 것이 유지보수와 운영 관점에서 압도적으로 유리합니다. `@ai-sdk/openai-compatible`의 `transformRequestBody` 개념을 Python으로 직접 구현합니다.

---

## 2. 목표 아키텍처 (변경 없음)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        목표 (TO-BE)                                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │            Unified Assistant (Python)                       │     │
│  │            OpenAI SDK (openai 패키지)로 통일                  │     │
│  │  model: "genai/gpt-oss-120B-medium"                         │     │
│  │       | "claude/claude-3-5-haiku-latest"                     │     │
│  │       | "gemini/gemini-3-pro-preview"                        │     │
│  └────────────────────────┬────────────────────────────────────┘     │
│                           │ POST localhost:8000/v1/chat/completions  │
│                           ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │         로컬 프록시 서버 (Python FastAPI)                    │     │
│  │         http://localhost:8000                                │     │
│  │                                                             │     │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐      │     │
│  │  │ GenAI         │ │ Claude        │ │ Gemini        │      │     │
│  │  │ Provider      │ │ Provider      │ │ Provider      │      │     │
│  │  │ (httpx 변환)  │ │ (httpx 변환)  │ │ (httpx 패스스루)│     │     │
│  │  └───────┬───────┘ └───────┬───────┘ └───────┬───────┘      │     │
│  └──────────┼─────────────────┼─────────────────┼──────────────┘     │
│             ▼                 ▼                 ▼                    │
│       SCI Portal         Anthropic           Google                 │
│       (원격 서버)         (원격 서버)          (원격 서버)             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 프록시 서버 기술 스택

### 3.1 Python 의존성

```bash
pip install fastapi uvicorn httpx python-dotenv pydantic
pip install openai   # Python 클라이언트용
```

### 3.2 프로젝트 구조

```
ai-proxy/
├── proxy_server.py          ← FastAPI 메인 서버
├── providers/
│   ├── __init__.py
│   ├── base.py              ← Provider 추상 클래스
│   ├── gemini_provider.py   ← Gemini (OpenAI 호환 패스스루)
│   ├── claude_provider.py   ← Claude (Anthropic 형식 변환)
│   └── genai_provider.py    ← GenAI SCI Portal (커스텀 형식 변환)
├── models.py                ← Pydantic 요청/응답 스키마
├── router.py                ← 모델명 기반 라우팅
├── .env                     ← API 키 (프록시 전용)
└── requirements.txt
```

---

## 4. 핵심 구현

### 4.1 Pydantic 스키마 (`models.py`)

```python
"""OpenAI Chat Completions API 호환 스키마"""
from pydantic import BaseModel
from typing import Optional

class ChatMessage(BaseModel):
    role: str       # "system" | "user" | "assistant"
    content: str

class ChatCompletionRequest(BaseModel):
    model: str                          # "gemini/gemini-3-pro-preview"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage
```

### 4.2 Provider 추상 클래스 (`providers/base.py`)

```python
"""Provider 추상 클래스 - @ai-sdk/openai-compatible의 createOpenAICompatible() 역할"""
from abc import ABC, abstractmethod
from typing import AsyncIterator
from models import ChatCompletionRequest, ChatCompletionResponse

class BaseProvider(ABC):
    """
    @ai-sdk/openai-compatible의 핵심 개념을 Python으로 구현:
    - transform_request(): transformRequestBody 역할
    - transform_response(): 응답 형식 변환 역할
    - stream(): 스트리밍 응답 처리
    """

    @abstractmethod
    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """OpenAI 형식 요청 → 공급자 API 호출 → OpenAI 형식 응답 반환"""
        pass

    @abstractmethod
    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """스트리밍 응답을 SSE 청크로 반환"""
        pass
```

### 4.3 Gemini Provider (`providers/gemini_provider.py`)

> [!TIP]
> Gemini는 공식 OpenAI 호환 엔드포인트를 제공하므로, **요청을 그대로 전달(패스스루)** 하면 됩니다.

```python
"""Gemini Provider - OpenAI 호환 엔드포인트 패스스루"""
import os, json, time, httpx
from typing import AsyncIterator
from providers.base import BaseProvider
from models import *

class GeminiProvider(BaseProvider):
    """
    Google Gemini - 공식 OpenAI 호환 엔드포인트 사용
    baseURL: https://generativelanguage.googleapis.com/v1beta/openai/
    
    ★ 핵심: 끝에 /openai/ 필수!
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120.0,
        )

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        # Gemini는 OpenAI 형식 그대로 전달 (패스스루)
        payload = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        resp = await self.client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{int(time.time())}"),
            model=request.model,
            choices=[ChatCompletionChoice(
                message=ChatMessage(
                    role="assistant",
                    content=data["choices"][0]["message"]["content"],
                ),
            )],
            usage=Usage(**data.get("usage", {})),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        payload = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": True,
        }
        async with self.client.stream("POST", "/chat/completions", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield line + "\n\n"
```

### 4.4 Claude Provider (`providers/claude_provider.py`)

> [!WARNING]
> Claude는 OpenAI 호환 엔드포인트가 없으므로, **요청/응답 형식을 변환**해야 합니다.

```python
"""Claude Provider - Anthropic Messages API ↔ OpenAI 형식 변환"""
import os, json, time, httpx
from typing import AsyncIterator
from providers.base import BaseProvider
from models import *

class ClaudeProvider(BaseProvider):
    """
    Anthropic Claude - /v1/messages 형식을 OpenAI 형식으로 변환
    
    ★ 핵심 차이:
    - max_tokens 필수
    - system 메시지는 별도 파라미터
    - 인증: x-api-key 헤더
    - 응답: content[0].text (choices[0].message.content 아님)
    """

    BASE_URL = "https://api.anthropic.com"

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    def _transform_request(self, request: ChatCompletionRequest) -> dict:
        """OpenAI 형식 → Anthropic 형식 변환 (transformRequestBody 역할)"""
        system_msg = None
        messages = []
        for m in request.messages:
            if m.role == "system":
                system_msg = m.content
            else:
                messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,  # ★ Claude 필수!
        }
        if system_msg:
            payload["system"] = system_msg
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload = self._transform_request(request)
        resp = await self.client.post("/v1/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{int(time.time())}"),
            model=request.model,
            choices=[ChatCompletionChoice(
                message=ChatMessage(
                    role="assistant",
                    content=data["content"][0]["text"],  # Claude 응답 형식
                ),
            )],
            usage=Usage(
                prompt_tokens=data.get("usage", {}).get("input_tokens", 0),
                completion_tokens=data.get("usage", {}).get("output_tokens", 0),
                total_tokens=data.get("usage", {}).get("input_tokens", 0)
                             + data.get("usage", {}).get("output_tokens", 0),
            ),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        payload = self._transform_request(request)
        payload["stream"] = True

        async with self.client.stream("POST", "/v1/messages", json=payload) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                raw = json.loads(line[6:])
                if raw.get("type") == "content_block_delta":
                    text = raw["delta"].get("text", "")
                    chunk = {"choices": [{"delta": {"content": text}, "index": 0}]}
                    yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"
```

### 4.5 GenAI Provider (`providers/genai_provider.py`)

```python
"""GenAI Provider - Samsung SCI Portal (gpt-oss-120B-medium) 형식 변환"""
import os, json, time, httpx
from typing import AsyncIterator
from providers.base import BaseProvider
from models import *

class GenAIProvider(BaseProvider):
    """
    Samsung SCI Portal - 커스텀 REST API 형식 변환
    모델: gpt-oss-120B-medium (120B 파라미터, Medium 등급)
    인증: X-Client-Key / X-Client-Secret 헤더
    """

    def __init__(self):
        self.base_url = os.getenv("ENDPOINT_URL",
                                   "https://scisportaldev.samsungif.net/rest/genAi")
        self.client = httpx.AsyncClient(
            headers={
                "X-Client-Key": os.getenv("YOUR_CLIENT_KEY", "API_CLIENT_APP"),
                "X-Client-Secret": os.getenv("YOUR_CLIENT_SECRET", ""),
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    def _transform_request(self, request: ChatCompletionRequest) -> dict:
        """OpenAI 형식 → SCI Portal 형식 (transformRequestBody 역할)"""
        return {
            "model_id": request.model,  # gpt-oss-120B-medium
            "prompt": [
                {"role": m.role, "text": m.content} for m in request.messages
            ],
            "parameters": {
                "temperature": request.temperature or 0.7,
                "max_output_tokens": request.max_tokens or 2048,
            },
        }

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        payload = self._transform_request(request)
        resp = await self.client.post(self.base_url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        # SCI Portal 응답 → OpenAI 형식 변환
        content = data.get("response", data.get("text", str(data)))
        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            model=request.model,
            choices=[ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=content),
            )],
            usage=Usage(**data.get("usage", {})) if "usage" in data else Usage(),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        # SCI Portal이 스트리밍을 지원하지 않으면 논스트리밍 폴백
        result = await self.chat(request)
        content = result.choices[0].message.content
        chunk = {"choices": [{"delta": {"content": content}, "index": 0}]}
        yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"
```

### 4.6 모델 라우터 (`router.py`)

```python
"""모델 ID 접두사 기반 Provider 라우팅"""
from providers.gemini_provider import GeminiProvider
from providers.claude_provider import ClaudeProvider
from providers.genai_provider import GenAIProvider

# Provider 싱글톤 인스턴스
_providers = {
    "gemini": GeminiProvider(),
    "claude": ClaudeProvider(),
    "genai": GenAIProvider(),
}

SUPPORTED_MODELS = {
    "gemini/gemini-3-pro-preview": "Google Gemini 3 Pro",
    "gemini/gemini-3-flash-preview": "Google Gemini 3 Flash",
    "claude/claude-3-5-haiku-latest": "Anthropic Claude 3.5 Haiku",
    "claude/claude-sonnet-4-5": "Anthropic Claude Sonnet 4.5",
    "genai/gpt-oss-120B-medium": "Samsung SCI Portal GPT-OSS 120B Medium",
}

def route_model(model_id: str):
    """
    모델 ID에서 접두사를 분리하여 Provider와 실제 모델명을 반환
    예: "gemini/gemini-3-pro-preview" → (GeminiProvider, "gemini-3-pro-preview")
    """
    parts = model_id.split("/", 1)
    if len(parts) != 2 or parts[0] not in _providers:
        raise ValueError(
            f'Unknown model: "{model_id}". '
            f'Use prefix: {", ".join(_providers.keys())}/'
        )
    return _providers[parts[0]], parts[1]
```

### 4.7 FastAPI 메인 서버 (`proxy_server.py`)

```python
"""OpenAI 호환 프록시 서버 (FastAPI)"""
import os, json
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from models import ChatCompletionRequest
from router import route_model, SUPPORTED_MODELS

app = FastAPI(title="AI Proxy Server", version="1.0.052")

PROXY_API_KEY = os.getenv("PROXY_API_KEY")

def verify_auth(authorization: str = Header(None)):
    if PROXY_API_KEY and authorization != f"Bearer {PROXY_API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---- OpenAI 호환 엔드포인트 ----

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest,
                           authorization: str = Header(None)):
    verify_auth(authorization)

    try:
        provider, actual_model = route_model(request.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 라우팅된 실제 모델 ID로 교체
    request.model = actual_model

    if request.stream:
        return StreamingResponse(
            provider.stream(request),
            media_type="text/event-stream",
        )
    else:
        result = await provider.chat(request)
        return result

@app.get("/v1/models")
async def list_models(authorization: str = Header(None)):
    verify_auth(authorization)
    return {
        "object": "list",
        "data": [
            {"id": mid, "object": "model", "owned_by": mid.split("/")[0], "name": name}
            for mid, name in SUPPORTED_MODELS.items()
        ],
    }

@app.get("/health")
async def health():
    return {"status": "ok", "models": list(SUPPORTED_MODELS.keys())}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PROXY_PORT", "8000"))
    print(f"🚀 AI Proxy Server starting on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
```

---

## 5. 환경변수

### 5.1 프록시 서버 (`ai-proxy/.env`)

```ini
# ===== 프록시 서버 =====
PROXY_PORT=8000
PROXY_API_KEY="proxy-secret-key"

# ----- Gemini -----
GEMINI_API_KEY="AIzaSy..."

# ----- Claude -----
ANTHROPIC_API_KEY="sk-ant-api03-..."

# ----- GenAI (Samsung SCI Portal) -----
ENDPOINT_URL="https://scisportaldev.samsungif.net/rest/genAi"
YOUR_CLIENT_KEY="API_CLIENT_APP"
YOUR_CLIENT_SECRET=""
```

### 5.2 Python 애플리케이션 (`.env`)

```ini
# 프록시 연결 (API 키는 프록시에서 중앙 관리)
PROXY_URL="http://localhost:8000/v1"
PROXY_API_KEY="proxy-secret-key"
AI_MODEL="gemini/gemini-3-pro-preview"
```

---

## 6. Python 클라이언트 사용법 (변경 없음)

```python
from openai import OpenAI

client = OpenAI(
    api_key="proxy-secret-key",
    base_url="http://localhost:8000/v1",
)

# 모든 공급자를 동일한 코드로 호출
response = client.chat.completions.create(
    model="genai/gpt-oss-120B-medium",     # ← 모델명만 바꾸면 공급자 전환
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

---

## 7. `@ai-sdk/openai-compatible` 개념 매핑

> [!IMPORTANT]
> v1에서 사용한 `@ai-sdk/openai-compatible`의 핵심 개념을 Python으로 1:1 매핑했습니다.

| @ai-sdk/openai-compatible (Node.js) | Python FastAPI 구현 |
|--------------------------------------|---------------------|
| `createOpenAICompatible({name, baseURL, ...})` | `class GeminiProvider(BaseProvider)` |
| `transformRequestBody` | `Provider._transform_request()` 메서드 |
| `metadataExtractor` | `Provider.chat()` 내 응답 파싱 로직 |
| `headers` 옵션 | `httpx.AsyncClient(headers={...})` |
| `apiKey` → `Authorization: Bearer` | `httpx.AsyncClient(headers={"Authorization": ...})` |
| `providerOptions` | FastAPI 요청 body의 추가 필드로 전달 |
| `includeUsage: true` | `Usage` 모델로 응답에 포함 |
| Express 라우팅 | FastAPI `@app.post("/v1/chat/completions")` |
| `provider('model-id')` | `route_model("prefix/model-id")` |

---

## 8. 실행 및 테스트

```bash
# 프록시 서버 시작
cd ai-proxy
python proxy_server.py

# 테스트 (curl)
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "gemini/gemini-3-pro-preview",
       "messages": [{"role": "user", "content": "Hello"}]}'

# 모델 목록 확인
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer proxy-secret-key"
```

---

## 9. 마이그레이션 전략

### Phase 1: FastAPI 프록시 기본 구축
- Python FastAPI 기반 프록시 서버 구현
- Gemini Provider 구현 (패스스루, 가장 간단)
- 동작 검증

### Phase 2: Claude & GenAI Provider 추가
- Claude Provider (`_transform_request`로 Anthropic 형식 변환)
- GenAI Provider (`gpt-oss-120B-medium`, SCI Portal 형식 변환)
- 3개 공급자 검증

### Phase 3: Python 클라이언트 통합
- 3개 Assistant 클래스 → `UnifiedAssistant` 통합
- 3개 `.py` 파일 → 단일 `ai-chat-code.py`
- `.env`에서 `AI_MODEL`로 공급자 선택

### Phase 4: 운영 안정화
- uvicorn 프로세스 관리 (`--workers`, systemd 등)
- 에러 핸들링, 로깅, 모니터링

---

## 10. 참고 자료

| 자료 | URL |
|------|-----|
| FastAPI 공식 문서 | https://fastapi.tiangolo.com/ |
| httpx 비동기 HTTP 클라이언트 | https://www.python-httpx.org/ |
| Gemini OpenAI 호환 API | https://ai.google.dev/gemini-api/docs/openai |
| Anthropic Claude API | https://docs.anthropic.com/en/api/messages |
| OpenAI Python SDK | https://github.com/openai/openai-python |
| AI SDK (v1 참고) | https://sdk.vercel.ai/providers/openai-compatible-providers |
| LiteLLM (대안 프록시) | https://github.com/BerriAI/litellm |

---

## 11. 승인

- [x] Node.js → Python FastAPI 전환 타당성 검토 완료
- [x] `@ai-sdk/openai-compatible` 핵심 개념의 Python 매핑 완료
- [x] FastAPI 프록시 서버 구현 가이드 작성 완료
- [x] 공급자별 Provider 구현 (Gemini 패스스루, Claude 변환, GenAI 변환)
- [x] Python 클라이언트 통합 가이드 (v1과 동일)
- [x] 마이그레이션 전략 수립 완료
