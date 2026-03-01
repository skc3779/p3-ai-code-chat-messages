# SRS v1.0.052 - OpenAI Compatible Provider를 활용한 API 엔드포인트 단일화

**버전**: v1.0.052  
**작성일**: 2026-03-01  
**대상**: `gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py` 및 관련 모듈  
**패키지**: `@ai-sdk/openai-compatible` (npm)  
**공식 문서**: https://sdk.vercel.ai/providers/openai-compatible-providers

---

## 1. 소개

### 1.1 목적

본 문서는 현재 프로젝트에서 각기 다른 방식으로 사용하고 있는 **3개의 AI 공급자 API 엔드포인트**를 **로컬 프록시 서버(OpenAI 호환 API Gateway)** 를 통해 **단일 인터페이스로 통합**하기 위한 기술 사양서입니다.

### 1.2 배경

현재 프로젝트의 API 엔드포인트 현황:

| 공급자 | 엔드포인트 | 모델 | 인증 방식 | API 형식 |
|--------|-----------|------|-----------|----------|
| **GenAI** (Samsung SCI Portal) | `https://scisportaldev.samsungif.net/rest/genAi` | `gpt-oss-120B-medium` | Client Key + Secret | 커스텀 REST |
| **Claude** (Anthropic) | `https://api.anthropic.com` | `claude-3-5-haiku-latest` | `ANTHROPIC_API_KEY` | Anthropic Messages API |
| **Gemini** (Google) | `https://generativelanguage.googleapis.com/v1beta` | `gemini-3-pro-preview` | `GEMINI_API_KEY` | Gemini generateContent API |

> **문제점**: 각 공급자마다 요청/응답 형식, 인증 방식, 스트리밍 프로토콜이 모두 달라 3벌의 어시스턴트 클래스(`GenAICodeAssistant`, `ClaudeCodeAssistant`, `GeminiCodeAssistant`)를 별도로 유지해야 합니다.

### 1.3 목표 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                        현재 (AS-IS)                                  │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │ gen-ai-chat-    │  │ claude-ai-chat- │  │ gemini-ai-chat- │      │
│  │ code.py         │  │ code.py         │  │ code.py         │      │
│  │                 │  │                 │  │                 │      │
│  │ GenAICode       │  │ ClaudeCode      │  │ GeminiCode      │      │
│  │ Assistant       │  │ Assistant       │  │ Assistant       │      │
│  └───────┬─────────┘  └───────┬─────────┘  └───────┬─────────┘      │
│          │ 커스텀 REST         │ Messages API       │ generateContent│
│          ▼                    ▼                    ▼                │
│   SCI Portal            Anthropic             Google               │
│   (원격 서버)            (원격 서버)            (원격 서버)           │
└─────────────────────────────────────────────────────────────────────┘

                          ▼  단일화  ▼

┌─────────────────────────────────────────────────────────────────────┐
│                        목표 (TO-BE)                                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │            Unified Assistant (Python)                       │     │
│  │            OpenAI SDK (openai 패키지)로 통일                  │     │
│  │                                                             │     │
│  │  POST http://localhost:4000/v1/chat/completions             │     │
│  │  Authorization: Bearer <proxy-key>                          │     │
│  │  model: "genai/gpt-oss-120B-medium"                         │     │
│  │       | "claude/claude-3-5-haiku-latest"                     │     │
│  │       | "gemini/gemini-3-pro-preview"                        │     │
│  └────────────────────────┬────────────────────────────────────┘     │
│                           │ OpenAI 호환 형식                         │
│                           ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │         로컬 프록시 서버 (API Gateway)                       │     │
│  │         http://localhost:4000                                │     │
│  │                                                             │     │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐      │     │
│  │  │ GenAI         │ │ Claude        │ │ Gemini        │      │     │
│  │  │ Provider      │ │ Provider      │ │ Provider      │      │     │
│  │  │               │ │               │ │               │      │     │
│  │  │ OpenAI 형식 → │ │ OpenAI 형식 → │ │ OpenAI 형식 → │      │     │
│  │  │ SCI Portal    │ │ Anthropic     │ │ Google        │      │     │
│  │  │ 형식 변환     │ │ 형식 변환     │ │ 형식 변환     │      │     │
│  │  └───────┬───────┘ └───────┬───────┘ └───────┬───────┘      │     │
│  └──────────┼─────────────────┼─────────────────┼──────────────┘     │
│             │                 │                 │                    │
│             ▼                 ▼                 ▼                    │
│       SCI Portal         Anthropic           Google                 │
│       scisportaldev      api.anthropic       googleapis             │
│       .samsungif.net     .com                .com                   │
│       (원격 서버)         (원격 서버)          (원격 서버)             │
└─────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **핵심 구조**: 로컬에 **OpenAI 호환 API를 노출하는 프록시 서버**를 구축합니다. 이 프록시가 각 공급자별 요청/응답 형식 변환을 담당하고, Python 애플리케이션은 **OpenAI SDK 하나만으로 모든 공급자를 호출**합니다.

### 1.4 아키텍처의 핵심 이점

| 이점 | 설명 |
|------|------|
| **클라이언트 코드 단일화** | 3개의 Assistant 클래스 → 1개의 Unified Assistant |
| **기존 Python 코드 호환** | OpenAI Python SDK의 `base_url`만 변경하면 됨 |
| **공급자 추가/변경 용이** | 프록시에 새 Provider만 등록하면 클라이언트 코드 변경 없음 |
| **인증 정보 중앙 관리** | 모든 API 키를 프록시 서버에서 일괄 관리 |
| **형식 변환 캡슐화** | 각 공급자의 API 차이를 프록시 내부에서 흡수 |

---

## 2. 전체 시스템 흐름

### 2.1 요청/응답 흐름

```
[Python 애플리케이션]
       │
       │  ① OpenAI 형식 요청 전송
       │  POST http://localhost:4000/v1/chat/completions
       │  {
       │    "model": "gemini/gemini-3-pro-preview",
       │    "messages": [{"role": "user", "content": "Hello"}]
       │  }
       ▼
[로컬 프록시 서버 (localhost:4000)]
       │
       │  ② model 접두사로 공급자 라우팅
       │     "gemini/..." → Gemini Provider
       │     "claude/..." → Claude Provider
       │     "genai/..."  → GenAI Provider
       │
       │  ③ OpenAI 형식 → 공급자 고유 형식 변환
       │     (transformRequestBody 활용)
       │
       │  ④ 변환된 요청을 원격 API 서버로 전달
       ▼
[원격 API 서버 (Gemini/Claude/GenAI)]
       │
       │  ⑤ 공급자 고유 형식으로 응답
       ▼
[로컬 프록시 서버]
       │
       │  ⑥ 공급자 고유 응답 → OpenAI 형식 변환
       │  {
       │    "choices": [{"message": {"content": "..."}}],
       │    "usage": {"prompt_tokens": 10, "completion_tokens": 20}
       │  }
       ▼
[Python 애플리케이션]
       │
       │  ⑦ OpenAI SDK로 응답 파싱 (모든 공급자 동일)
```

### 2.2 컴포넌트 역할 분리

| 컴포넌트 | 기술 스택 | 역할 |
|----------|----------|------|
| **Python 애플리케이션** | Python + `openai` SDK | 사용자 인터페이스, 대화 관리, 파일 처리 |
| **로컬 프록시 서버** | Node.js + `@ai-sdk/openai-compatible` | 요청/응답 형식 변환, 인증 정보 관리, 공급자 라우팅 |
| **원격 API 서버** | 각 공급자 클라우드 | AI 모델 추론 실행 |

---

## 3. `@ai-sdk/openai-compatible` 핵심 개념

> [!NOTE]
> `@ai-sdk/openai-compatible`는 **로컬 프록시 서버의 내부 구현**에 사용되는 NPM 패키지입니다. Python 클라이언트 코드에서는 직접 사용하지 않습니다.

### 3.1 패키지 개요

`@ai-sdk/openai-compatible`는 Vercel AI SDK의 일부로, **OpenAI API 형식을 구현하는 모든 제공자**를 동일한 인터페이스로 통합할 수 있게 해주는 경량 프로바이더 패키지입니다.

**프록시 서버 내부에서의 역할**:
- 각 공급자의 API 호출을 추상화
- `transformRequestBody`로 요청 형식 변환
- `metadataExtractor`로 응답 메타데이터 추출
- 스트리밍/비스트리밍 응답 통합 처리

### 3.2 설치 (프록시 서버 프로젝트에서)

```bash
# 프록시 서버 프로젝트 초기화
mkdir ai-proxy-server && cd ai-proxy-server
npm init -y

# 필수 패키지
npm install @ai-sdk/openai-compatible ai express
```

### 3.3 핵심 함수: `createOpenAICompatible()`

프록시 서버 내부에서 각 공급자별 Provider 인스턴스를 생성하는 데 사용됩니다.

```typescript
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

// 프록시 서버 내부에서 Provider 인스턴스 생성
const geminiProvider = createOpenAICompatible({
  name: 'gemini',
  apiKey: process.env.GEMINI_API_KEY,
  baseURL: 'https://generativelanguage.googleapis.com/v1beta/openai/',
});
```

---

## 4. `createOpenAICompatible()` 설정 옵션 상세

> [!IMPORTANT]
> 아래 설정 옵션들은 **프록시 서버 내부**에서 각 공급자 Provider를 구성할 때 사용합니다.

### 4.1 기본 설정 옵션

| 옵션 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `name` | `string` | ✅ | 프로바이더 이름. `providerOptions`의 키로도 사용됨 |
| `baseURL` | `string` | ✅ | API 호출 URL 접두사 (예: `https://api.xxx.com/v1`) |
| `apiKey` | `string` | - | API 키. 설정하면 `Authorization: Bearer <apiKey>` 헤더 자동 추가 |
| `headers` | `Record<string, string>` | - | 커스텀 요청 헤더. `apiKey` 헤더 이후에 추가됨 |
| `queryParams` | `Record<string, string>` | - | URL 쿼리 파라미터 (예: Azure의 `api-version`) |
| `fetch` | `Function` | - | 커스텀 fetch 구현체 (미들웨어/테스트용) |
| `includeUsage` | `boolean` | - | 스트리밍 응답에 토큰 사용량 정보 포함 여부 |
| `supportsStructuredOutputs` | `boolean` | - | JSON Schema 기반 구조화 출력 지원 여부 |

### 4.2 고급 설정 옵션 (⭐ 프록시 변환의 열쇠)

#### 4.2.1 `transformRequestBody` — 요청 본문 변환

```typescript
transformRequestBody: (args: Record<string, any>) => Record<string, any>
```

> [!CAUTION]
> **이 옵션이 프록시 서버에서 요청 형식 변환의 핵심입니다!** OpenAI 형식으로 들어온 요청을 각 공급자가 기대하는 형식으로 변환합니다.

**프록시 내부 사용 예시**: SCI Portal GenAI API(`gpt-oss-120B-medium`) 형식 변환:

```typescript
const genaiProvider = createOpenAICompatible({
  name: 'genai',
  baseURL: 'https://scisportaldev.samsungif.net/rest/genAi',
  transformRequestBody: (body) => {
    // 프록시가 OpenAI 형식 → SCI Portal 형식으로 변환
    return {
      ...body,
      client_key: process.env.YOUR_CLIENT_KEY,     // 'API_CLIENT_APP'
      client_secret: process.env.YOUR_CLIENT_SECRET,
    };
  },
});
```

#### 4.2.2 `metadataExtractor` — 응답 메타데이터 추출

```typescript
metadataExtractor: MetadataExtractor
```

프록시에서 원격 API 응답의 공급자 고유 메타데이터를 추출하여 OpenAI 형식 응답에 포함시킵니다.

```typescript
import { MetadataExtractor } from '@ai-sdk/openai-compatible';

const myMetadataExtractor: MetadataExtractor = {
  // 일반 응답에서 메타데이터 추출
  extractMetadata: ({ parsedBody }) => ({
    myProvider: {
      usage: parsedBody.usage,
      modelVersion: parsedBody.model_version,
    },
  }),

  // 스트리밍 응답에서 메타데이터 축적
  createStreamExtractor: () => {
    let accumulated = { timing: [] };
    return {
      processChunk: (chunk) => {
        if (chunk.server_timing) {
          accumulated.timing.push(chunk.server_timing);
        }
      },
      buildMetadata: () => ({
        myProvider: { streamTiming: accumulated.timing },
      }),
    };
  },
};
```

---

## 5. 로컬 프록시 서버 구축

### 5.1 프록시 서버 구조

```
ai-proxy-server/
├── package.json
├── .env                    ← 모든 공급자의 API 키/인증 정보
├── src/
│   ├── server.ts           ← Express 서버 (OpenAI 호환 엔드포인트)
│   ├── providers/
│   │   ├── gemini.ts       ← Gemini Provider 설정
│   │   ├── claude.ts       ← Claude Provider 설정
│   │   └── genai.ts        ← GenAI (SCI Portal) Provider 설정
│   └── router.ts           ← 모델명 기반 Provider 라우팅
└── tsconfig.json
```

### 5.2 프록시 서버 환경변수 (.env)

```ini
# ===== 프록시 서버 설정 =====
PROXY_PORT=4000
PROXY_API_KEY="proxy-secret-key"   # 프록시 접근 인증 키

# ----- Gemini 설정 -----
GEMINI_API_KEY="AIzaSy..."
# baseURL은 코드 내 고정: https://generativelanguage.googleapis.com/v1beta/openai/

# ----- Claude 설정 -----
ANTHROPIC_API_KEY="sk-ant-api03-..."

# ----- GenAI 설정 (Samsung SCI Portal) -----
ENDPOINT_URL="https://scisportaldev.samsungif.net/rest/genAi"
YOUR_CLIENT_KEY="API_CLIENT_APP"
YOUR_CLIENT_SECRET=""
```

### 5.3 Provider 설정 파일

#### 5.3.1 Gemini Provider (`providers/gemini.ts`)

> [!TIP]
> Gemini는 **공식 OpenAI 호환 엔드포인트**를 제공하므로, 프록시에서 가장 간단하게 구성됩니다.

```typescript
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

export const geminiProvider = createOpenAICompatible({
  name: 'gemini',
  apiKey: process.env.GEMINI_API_KEY,
  baseURL: 'https://generativelanguage.googleapis.com/v1beta/openai/',
  includeUsage: true,
});
```

> [!IMPORTANT]
> Gemini의 OpenAI 호환 Base URL은 기존 URL에 `/openai/`를 추가한 형태입니다:
> - **기존 (네이티브)**: `https://generativelanguage.googleapis.com/v1beta`
> - **OpenAI 호환**: `https://generativelanguage.googleapis.com/v1beta/openai/`
> 
> 끝에 `/openai/`를 반드시 포함해야 합니다!

**Gemini OpenAI 호환 API 지원 범위:**

| 기능 | 지원 여부 | 비고 |
|------|:--------:|------|
| Chat Completions | ✅ | `POST /chat/completions` |
| Streaming | ✅ | SSE 형식 |
| Function Calling | ✅ | tools 파라미터 |
| Embeddings | ✅ | `POST /embeddings` |
| Structured Output | ✅ | JSON Schema |
| Thinking (Reasoning) | ✅ | 추론 토큰 |

#### 5.3.2 Claude Provider (`providers/claude.ts`)

> [!WARNING]
> Anthropic Claude는 **공식 OpenAI 호환 엔드포인트를 직접 제공하지 않습니다.** 프록시 내부에서 `transformRequestBody`로 변환하거나, 별도 Anthropic 어댑터를 사용합니다.

```typescript
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

export const claudeProvider = createOpenAICompatible({
  name: 'claude',
  apiKey: process.env.ANTHROPIC_API_KEY,
  baseURL: 'https://api.anthropic.com/v1',
  headers: {
    'anthropic-version': '2023-06-01',
  },
  includeUsage: true,
  transformRequestBody: (body) => ({
    ...body,
    max_tokens: body.max_tokens ?? 4096,  // Claude는 max_tokens 필수
  }),
});
```

**Claude vs OpenAI API 형식 차이 (프록시가 처리):**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Python 앱이 보내는 요청      프록시가 변환         Claude가 받는 요청 │
│  (OpenAI 형식)               ──────────→          (Anthropic 형식)  │
├──────────────────────┬──────────────────────────────────────────────┤
│  POST /v1/chat/       │  POST /v1/messages                          │
│       completions     │                                             │
├──────────────────────┼──────────────────────────────────────────────┤
│  {                   │  {                                           │
│   "model": "claude/  │   "model": "claude-sonnet-4-5",              │
│    claude-sonnet-4-5"│   "messages": [...],                         │
│   "messages": [...]  │   "max_tokens": 4096  ← 프록시가 추가        │
│  }                   │  }                                           │
├──────────────────────┼──────────────────────────────────────────────┤
│  Authorization:      │  x-api-key: sk-ant-...                       │
│    Bearer proxy-key  │  anthropic-version: 2023-06-01                │
└──────────────────────┴──────────────────────────────────────────────┘
```

> [!TIP]
> Claude 전용으로 Vercel AI SDK의 공식 `@ai-sdk/anthropic` 패키지를 프록시 내부에서 사용하면 더 안정적입니다:
> ```bash
> npm install @ai-sdk/anthropic
> ```
> ```typescript
> import { anthropic } from '@ai-sdk/anthropic';
> // 프록시 내부에서 Claude 요청 처리 시 사용
> ```

#### 5.3.3 GenAI Provider (`providers/genai.ts`)

> [!NOTE]
> GenAI는 **Samsung SCI Portal**에서 제공하는 사내 API로, 모델은 `gpt-oss-120B-medium` (120B 파라미터, Medium 버전)입니다. `transformRequestBody`로 요청 형식을 변환합니다.

```typescript
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

export const genaiProvider = createOpenAICompatible({
  name: 'genai',
  baseURL: 'https://scisportaldev.samsungif.net/rest/genAi',

  // SCI Portal은 Client Key/Secret 방식으로 인증
  headers: {
    'X-Client-Key': process.env.YOUR_CLIENT_KEY!,     // 'API_CLIENT_APP'
    'X-Client-Secret': process.env.YOUR_CLIENT_SECRET!,
  },

  includeUsage: true,

  // OpenAI 형식 → SCI Portal 형식 변환
  transformRequestBody: (body) => {
    const { messages, model, temperature, max_tokens, ...rest } = body;

    return {
      model_id: model,  // 'gpt-oss-120B-medium'
      prompt: messages.map((m: any) => ({
        role: m.role,
        text: m.content,
      })),
      parameters: {
        temperature: temperature ?? 0.7,
        max_output_tokens: max_tokens ?? 2048,
      },
      ...rest,
    };
  },

  // SCI Portal 응답 메타데이터 추출
  metadataExtractor: {
    extractMetadata: ({ parsedBody }) => ({
      genai: {
        usage: parsedBody.usage,
        requestId: parsedBody.request_id,
      },
    }),
    createStreamExtractor: () => ({
      processChunk: () => {},
      buildMetadata: () => ({ genai: {} }),
    }),
  },
});
```

### 5.4 모델 라우터 (`router.ts`)

```typescript
import { geminiProvider } from './providers/gemini';
import { claudeProvider } from './providers/claude';
import { genaiProvider } from './providers/genai';

/**
 * 모델 ID의 접두사를 기반으로 적절한 Provider와 실제 모델 ID를 반환합니다.
 * 
 * 모델 ID 형식: "<provider>/<model-name>"
 *   예: "gemini/gemini-3-pro-preview"
 *   예: "claude/claude-3-5-haiku-latest"
 *   예: "genai/gpt-oss-120B-medium"
 */
export function routeModel(modelId: string) {
  const [prefix, ...rest] = modelId.split('/');
  const actualModelId = rest.join('/');

  switch (prefix) {
    case 'gemini':
      return { provider: geminiProvider, modelId: actualModelId };
    case 'claude':
      return { provider: claudeProvider, modelId: actualModelId };
    case 'genai':
      return { provider: genaiProvider, modelId: actualModelId };
    default:
      throw new Error(`Unknown provider prefix: "${prefix}". Use "gemini/", "claude/", or "genai/" prefix.`);
  }
}

// 지원 모델 목록
export const SUPPORTED_MODELS = {
  'gemini/gemini-3-pro-preview': 'Google Gemini 3 Pro',
  'gemini/gemini-3-flash-preview': 'Google Gemini 3 Flash',
  'claude/claude-3-5-haiku-latest': 'Anthropic Claude 3.5 Haiku',
  'claude/claude-sonnet-4-5': 'Anthropic Claude Sonnet 4.5',
  'genai/gpt-oss-120B-medium': 'Samsung SCI Portal GPT-OSS 120B Medium',
};
```

### 5.5 프록시 서버 메인 (`server.ts`)

```typescript
import express from 'express';
import { generateText, streamText } from 'ai';
import { routeModel, SUPPORTED_MODELS } from './router';
import 'dotenv/config';

const app = express();
app.use(express.json());

const PROXY_PORT = process.env.PROXY_PORT ?? 4000;
const PROXY_API_KEY = process.env.PROXY_API_KEY;

// 인증 미들웨어
app.use('/v1/*', (req, res, next) => {
  const authHeader = req.headers.authorization;
  if (PROXY_API_KEY && authHeader !== `Bearer ${PROXY_API_KEY}`) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
});

// OpenAI 호환 Chat Completions 엔드포인트
app.post('/v1/chat/completions', async (req, res) => {
  try {
    const { model, messages, stream, temperature, max_tokens } = req.body;

    // 모델 라우팅
    const { provider, modelId } = routeModel(model);

    if (stream) {
      // 스트리밍 응답 (SSE)
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');

      const result = streamText({
        model: provider(modelId),
        messages,
        temperature,
        maxTokens: max_tokens,
      });

      for await (const chunk of result.textStream) {
        const sseData = {
          choices: [{ delta: { content: chunk }, index: 0 }],
        };
        res.write(`data: ${JSON.stringify(sseData)}\n\n`);
      }
      res.write('data: [DONE]\n\n');
      res.end();
    } else {
      // 일반 응답
      const { text, usage } = await generateText({
        model: provider(modelId),
        messages,
        temperature,
        maxTokens: max_tokens,
      });

      res.json({
        id: `chatcmpl-${Date.now()}`,
        object: 'chat.completion',
        model,
        choices: [{
          index: 0,
          message: { role: 'assistant', content: text },
          finish_reason: 'stop',
        }],
        usage: {
          prompt_tokens: usage?.promptTokens ?? 0,
          completion_tokens: usage?.completionTokens ?? 0,
          total_tokens: (usage?.promptTokens ?? 0) + (usage?.completionTokens ?? 0),
        },
      });
    }
  } catch (error: any) {
    console.error('Proxy error:', error);
    res.status(500).json({
      error: { message: error.message, type: 'proxy_error' },
    });
  }
});

// 모델 목록 엔드포인트
app.get('/v1/models', (req, res) => {
  const models = Object.entries(SUPPORTED_MODELS).map(([id, name]) => ({
    id,
    object: 'model',
    owned_by: id.split('/')[0],
    name,
  }));
  res.json({ object: 'list', data: models });
});

// 프록시 서버 시작
app.listen(PROXY_PORT, () => {
  console.log(`🚀 OpenAI Compatible Proxy Server running on http://localhost:${PROXY_PORT}`);
  console.log(`📋 Supported models:`);
  Object.entries(SUPPORTED_MODELS).forEach(([id, name]) => {
    console.log(`   - ${id}: ${name}`);
  });
});
```

### 5.6 프록시 서버 실행

```bash
# 개발 모드
npx tsx src/server.ts

# 또는 빌드 후 실행
npm run build && node dist/server.js
```

---

## 6. Python 클라이언트 통합

> [!IMPORTANT]
> Python 애플리케이션에서는 `openai` 패키지의 `base_url`을 **로컬 프록시 서버 주소**로 지정하기만 하면 됩니다. 기존 코드의 구조를 거의 그대로 유지할 수 있습니다.

### 6.1 Python 의존성

```bash
pip install openai
```

### 6.2 Unified Assistant 구현

```python
"""
Unified AI Code Assistant - 통합 AI 코딩 어시스턴트

모든 공급자(GenAI, Claude, Gemini)를 로컬 프록시 서버를 통해
OpenAI SDK 하나로 통합 호출합니다.
"""

from openai import OpenAI

# 로컬 프록시 서버에 연결
client = OpenAI(
    api_key="proxy-secret-key",            # 프록시 인증 키
    base_url="http://localhost:4000/v1",   # 로컬 프록시 엔드포인트
)

# ★ 모든 공급자를 동일한 코드로 호출! ★

# GenAI (Samsung SCI Portal) 호출
response = client.chat.completions.create(
    model="genai/gpt-oss-120B-medium",
    messages=[
        {"role": "system", "content": "You are a coding assistant."},
        {"role": "user", "content": "Python으로 정렬 함수를 작성해줘"},
    ],
)
print(response.choices[0].message.content)

# Claude 호출 — 동일한 코드!
response = client.chat.completions.create(
    model="claude/claude-3-5-haiku-latest",
    messages=[
        {"role": "user", "content": "이 코드를 리뷰해줘"},
    ],
)
print(response.choices[0].message.content)

# Gemini 호출 — 동일한 코드!
response = client.chat.completions.create(
    model="gemini/gemini-3-pro-preview",
    messages=[
        {"role": "user", "content": "REST API 설계 패턴을 설명해줘"},
    ],
)
print(response.choices[0].message.content)
```

### 6.3 스트리밍 호출

```python
# 스트리밍도 동일한 인터페이스
stream = client.chat.completions.create(
    model="gemini/gemini-3-pro-preview",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True,
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### 6.4 기존 코드 변경 최소화

현재 3개의 Assistant 클래스 대신, 환경변수로 공급자를 선택하는 단일 코드:

```python
import os
from openai import OpenAI

# .env에서 설정
PROXY_URL = os.getenv("PROXY_URL", "http://localhost:4000/v1")
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "proxy-secret-key")
AI_MODEL = os.getenv("AI_MODEL", "gemini/gemini-3-pro-preview")

client = OpenAI(
    api_key=PROXY_API_KEY,
    base_url=PROXY_URL,
)

def chat(user_message: str, streaming: bool = True):
    """통합 채팅 함수 - 모든 공급자에 동일하게 동작"""
    if streaming:
        stream = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": user_message}],
            stream=True,
        )
        full_response = ""
        for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            print(content, end="", flush=True)
            full_response += content
        print()
        return full_response
    else:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.choices[0].message.content
```

---

## 7. 환경변수 설계

### 7.1 프록시 서버 환경변수 (`ai-proxy-server/.env`)

```ini
# ===== 프록시 서버 =====
PROXY_PORT=4000
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

### 7.2 Python 애플리케이션 환경변수 (`.env`)

```ini
# ===== 통합 AI 설정 =====

# 프록시 서버 연결
PROXY_URL="http://localhost:4000/v1"
PROXY_API_KEY="proxy-secret-key"

# 기본 사용 모델 (변경하여 공급자 전환)
AI_MODEL="gemini/gemini-3-pro-preview"
# AI_MODEL="claude/claude-3-5-haiku-latest"
# AI_MODEL="genai/gpt-oss-120B-medium"
```

> [!TIP]
> Python `.env`에는 각 공급자의 API 키가 **불필요**합니다. 모든 인증 정보는 프록시 서버에서 중앙 관리됩니다.

---

## 8. Provider-Specific Options (프록시 내부 공급자별 옵션)

### 8.1 `providerOptions`를 통한 공급자별 확장

프록시 서버 내부에서 `@ai-sdk/openai-compatible`의 각 공급자에 고유 옵션을 전달할 수 있습니다.

> [!IMPORTANT]
> `providerOptions`의 키 이름은 `createOpenAICompatible()`에서 지정한 `name`을 **camelCase**로 변환한 것입니다.
> - `name: 'my-provider'` → `providerOptions.myProvider`
> - `name: 'gemini'` → `providerOptions.gemini`
> - `name: 'genai'` → `providerOptions.genai`

```typescript
// 프록시 서버 내부: Gemini의 추론 모드 활성화
const { text } = await generateText({
  model: geminiProvider('gemini-3-pro-preview'),
  prompt: 'Step by step, solve: What is 15 * 23?',
  providerOptions: {
    gemini: {
      reasoningEffort: 'high',
    },
  },
});
```

### 8.2 커스텀 쿼리 파라미터

일부 공급자(예: Azure AI)는 URL 쿼리 파라미터를 요구합니다:

```typescript
const azureProvider = createOpenAICompatible({
  name: 'azure',
  apiKey: process.env.AZURE_API_KEY,
  baseURL: 'https://my-resource.openai.azure.com/openai/deployments/my-model',
  queryParams: {
    'api-version': '2024-06-01',
  },
});
// 결과 URL: .../chat/completions?api-version=2024-06-01
```

---

## 9. TypeScript 타입 기반 모델 ID 자동완성

프록시 서버 개발 시 DX(Developer Experience)를 높이기 위해, 타입 매개변수로 모델 ID 자동완성을 설정할 수 있습니다:

```typescript
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

type GeminiModelIds =
  | 'gemini-3-pro-preview'
  | 'gemini-3-flash-preview'
  | (string & {});

type GenAIModelIds =
  | 'gpt-oss-120B-medium'
  | (string & {});

const geminiProvider = createOpenAICompatible<GeminiModelIds>({
  name: 'gemini',
  apiKey: process.env.GEMINI_API_KEY,
  baseURL: 'https://generativelanguage.googleapis.com/v1beta/openai/',
});

// IDE에서 모델 ID 자동완성 지원됨
const model = geminiProvider('gemini-3-pro-preview'); // ✅ 자동완성
```

---

## 10. 주의사항 및 제약사항

> [!CAUTION]
> ### 반드시 확인해야 할 사항

### 10.1 공급자별 호환성 (프록시 변환 난이도)

| 항목 | Gemini | Claude | GenAI (SCI Portal) |
|------|:------:|:------:|:---:|
| 공식 OpenAI 호환 엔드포인트 | ✅ 제공 | ❌ 미제공 | ❌ 커스텀 |
| 프록시 구현 난이도 | 🟢 쉬움 (패스스루) | 🟡 보통 (형식 변환) | 🟠 어려움 (전면 변환) |
| 스트리밍 SSE 호환 | ✅ | ⚠️ 형식 차이 | ❓ 서버 종속 |
| Tool Calling 호환 | ✅ | ⚠️ 파라미터 차이 | ❓ 서버 종속 |

### 10.2 핵심 주의사항

1. **프록시 서버 가용성**: 프록시 서버가 중단되면 모든 AI 기능이 중단됩니다. 프로세스 관리(pm2 등) 필요.

2. **Claude의 `max_tokens` 필수**: Claude API는 `max_tokens`가 필수이지만 OpenAI는 선택 사항입니다. 프록시의 `transformRequestBody`에서 반드시 기본값을 추가해야 합니다.

3. **인증 헤더 차이 (프록시가 처리)**: 
   - OpenAI/Gemini: `Authorization: Bearer <key>`
   - Claude: `x-api-key: <key>` + `anthropic-version: 2023-06-01`
   - GenAI (SCI Portal): 커스텀 헤더 (`X-Client-Key: API_CLIENT_APP`, `X-Client-Secret`)

4. **응답 형식 통일**: 프록시는 모든 공급자의 응답을 OpenAI의 `choices[0].message.content` 형식으로 변환하여 Python 앱에 반환해야 합니다.

5. **`providerOptions` 키 이름 규칙**: 프록시 내부에서 `name`에 하이픈(`-`)을 사용해도 `providerOptions`에서는 **camelCase**로 접근해야 합니다.
   - `name: 'my-provider'` → `providerOptions.myProvider` (O)
   - `providerOptions['my-provider']` (X)

6. **Gemini Beta 상태**: Gemini의 OpenAI 호환 API는 현재 **Beta** 상태이며, 일부 기능이 제한될 수 있습니다.

---

## 11. 마이그레이션 전략

### Phase 1: 프록시 서버 기본 구축
- Node.js 기반 프록시 서버 프로젝트 생성
- Gemini Provider 구현 (가장 간단, 공식 호환 엔드포인트)
- 프록시 서버 동작 검증 (Gemini 단일 모델)

### Phase 2: Claude & GenAI Provider 추가
- Claude Provider 구현 (`transformRequestBody`로 형식 변환)
- GenAI (SCI Portal) Provider 구현 (`gpt-oss-120B-medium` 대응)
- 3개 공급자 모두 프록시를 통한 호출 검증

### Phase 3: Python 클라이언트 통합
- `GenAICodeAssistant`, `ClaudeCodeAssistant`, `GeminiCodeAssistant` → `UnifiedAssistant` 통합
- `gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py` → 단일 `ai-chat-code.py`
- `.env` 환경변수 구조 통합 (`AI_MODEL`로 공급자 선택)

### Phase 4: 운영 안정화
- 프록시 서버 프로세스 관리 (pm2, systemd 등)
- 에러 핸들링 및 폴백 전략
- 로깅 및 모니터링 구축

---

## 12. 대안 솔루션: LiteLLM

> [!TIP]
> 프록시 서버를 직접 구현하지 않고, 검증된 오픈소스 솔루션인 **LiteLLM**을 사용할 수도 있습니다.

### 12.1 LiteLLM Proxy 개요

[LiteLLM](https://github.com/BerriAI/litellm)은 100개 이상의 LLM 공급자를 OpenAI 호환 형식으로 통합하는 오픈소스 프록시입니다.

```bash
pip install litellm[proxy]

# 프록시 시작
litellm --model gemini/gemini-3-pro-preview --port 4000
```

### 12.2 LiteLLM vs 직접 구현 비교

| 항목 | LiteLLM | 직접 구현 (이 문서) |
|------|---------|-----------------|
| 구현 난이도 | 🟢 즉시 사용 | 🟠 개발 필요 |
| 공급자 지원 | 100개 이상 | 3개 (GenAI, Claude, Gemini) |
| 커스텀 API 지원 | ⚠️ 설정 필요 | ✅ 완전 제어 |
| SCI Portal 호환 | ❌ 별도 구현 필요 | ✅ `transformRequestBody` 활용 |
| 의존성 | Python (litellm) | Node.js (ai-sdk) |

---

## 13. 참고 자료

| 자료 | URL |
|------|-----|
| AI SDK 공식 문서 - OpenAI Compatible | https://sdk.vercel.ai/providers/openai-compatible-providers |
| AI SDK - Custom Provider 작성 가이드 | https://sdk.vercel.ai/providers/openai-compatible-providers/custom-providers |
| Gemini OpenAI 호환 API 문서 | https://ai.google.dev/gemini-api/docs/openai |
| Anthropic Claude API 문서 | https://docs.anthropic.com/en/api/messages |
| AI SDK npm 패키지 | https://www.npmjs.com/package/@ai-sdk/openai-compatible |
| LiteLLM (대안 오픈소스 프록시) | https://github.com/BerriAI/litellm |
| OpenAI Python SDK | https://github.com/openai/openai-python |

---

## 14. 승인

- [x] 현재 3개 공급자 엔드포인트 현황 분석 완료
- [x] `@ai-sdk/openai-compatible` 패키지 스펙 분석 완료
- [x] **로컬 프록시 아키텍처** 설계 완료
- [x] 프록시 서버 구현 가이드 작성 완료
- [x] Python 클라이언트 통합 가이드 작성 완료
- [x] 공급자별 OpenAI 호환 가이드 샘플 작성 완료
- [x] 마이그레이션 전략 수립 완료
