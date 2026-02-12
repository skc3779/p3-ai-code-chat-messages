# GenAI Code Assistant

**GenAI 코딩 어시스턴트** - 커스텀 GenAI API를 활용한 대화형 코드 작성 도구

## 개요

GenAI Code Assistant는 터미널에서 커스텀 GenAI API (Lego Platform)를 활용하여 코드 작성, 리팩토링, 문서화 등을 지원하는 AI 코딩 어시스턴트입니다. 프로젝트 파일 컨텍스트를 자동으로 분석하여 더 정확한 코드 생성을 지원합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| 💬 **대화형 채팅** | AI와 실시간 스트리밍 대화 |
| 📁 **파일 컨텍스트** | 프로젝트 파일을 자동으로 분석하여 AI에 전달 |
| 🌳 **프로젝트 트리** | 디렉토리 구조 시각화 |
| 💾 **파일 저장** | AI가 생성한 코드를 자동 추출 및 저장 |
| 📜 **대화 히스토리** | 이전 대화 내용 유지 및 관리 |
| ⚙️ **LLM 설정** | temperature, top_k, top_p 등 파라미터 커스터마이징 |
| 🚀 **코드 실행** | AI가 생성한 코드를 직접 실행 (Python/JS/Bash) |
| 💻 **쉘 명령어** | 터미널 명령어 직접 실행 |
| 📝 **멀티라인 입력** | 여러 줄의 프롬프트 입력 지원 |

## 설치

### 1. 의존성 설치

```bash
pip install requests sseclient-py python-dotenv
```

### 2. 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 추가합니다:

```env
# GenAI API Configuration
ENDPOINT_URL=https://your-genai-endpoint.com
YOUR_CLIENT_KEY=your_client_key_here
YOUR_CLIENT_SECRET=your_client_secret_here
YOUR_MODEL_ID=your_model_id_here
```

| 환경 변수 | 설명 |
|-----------|------|
| `ENDPOINT_URL` | GenAI API 엔드포인트 URL |
| `YOUR_CLIENT_KEY` | Lego Platform Client ID |
| `YOUR_CLIENT_SECRET` | Lego Platform Client Secret |
| `YOUR_MODEL_ID` | 사용할 모델 ID |

## 사용법

### 실행

```bash
python gen-ai-chat-code01.py
```

### 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `/files [ext]` | 프로젝트 파일 목록 | `/files .py .js` |
| `/tree` | 프로젝트 구조 보기 | `/tree` |
| `/read <pattern>` | 파일 읽기 (파일명, 상대경로, 와일드카드 지원) | `/read *.py`, `/read src/utils.py`, `/read src/claude*.py src/gen*.py` |
| `/context <pattern> <질문>` | 파일 컨텍스트 포함 질문 | `/context *.py README 작성해줘` |
| `/save` | AI 응답에서 파일 추출 및 저장 | `/save` |
| `/workspace [path]` | 작업 디렉토리 변경 | `/workspace ./src` |
| `/stream` | 스트리밍 모드 활성화 | `/stream` |
| `/nostream` | 논스트리밍 모드 활성화 | `/nostream` |
| `/history` | 대화 히스토리 보기 | `/history` |
| `/clear` | 대화 히스토리 초기화 | `/clear` |
| `/run [lang]` | 마지막 응답의 코드 실행 | `/run python` |
| `/multiline` | 멀티라인 입력 모드 (종료: /end) | `/multiline` |
| `/shell <cmd>` | 쉘 명령어 실행 (안전 모드) | `/shell pip list` |
| `/shell! <cmd>` | 쉘 명령어 실행 (위험 명령 허용) | `/shell! rm -rf temp/` |
| `/llm_config <lang>` | 언어별 LLM 파라미터 설정 | `/llm_config Python` |
| `/help` | 도움말 보기 | `/help` |
| `/quit` | 종료 | `/quit` |

### 사용 예시

```bash
# 프로젝트 파일 기반으로 README 작성 요청
👤 You: /context *.py 이 프로젝트에 README.md를 작성해줘

# 코드 리팩토링 요청
👤 You: /context src/*.py 이 코드를 리팩토링해줘

# 일반 질문
👤 You: Python에서 데코레이터 사용법을 알려줘

# 생성된 파일 저장
👤 You: /save

# 멀티라인 입력
👤 You: /multiline
📝 멀티라인 모드 (종료: /end)
... 다음 코드를 분석해줘:
... def calculate(x, y):
...     return x + y
... /end

# LLM 설정 변경
👤 You: /llm_config Python
✅ LLM 설정이 'python' 로 적용되었습니다.

# 코드 실행
👤 You: /run python
```

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    GenAICodeAssistant                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ FileManager │  │ TreeBuilder  │  │   ContextBuilder    │ │
│  │  (파일 I/O) │  │ (트리 생성)  │  │  (컨텍스트 구성)    │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                 FilePatternMatcher                       │ │
│  │         (파일 패턴 매칭 및 필터링, .gitignore 처리)      │ │
│  └──────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    GenAI API (SSE Streaming)                │
│            {ENDPOINT_URL}/openapi/chat/v1/messages          │
└─────────────────────────────────────────────────────────────┘
```

## API 사양

### Request

```json
{
  "modelIds": ["your_model_id"],
  "contents": ["대화 내용 배열"],
  "llmConfig": {
    "max_new_tokens": 8192,
    "seed": null,
    "top_k": 14,
    "top_p": 0.94,
    "temperature": 0.4,
    "repetition_penalty": 1.04
  },
  "isStream": true,
  "systemPrompt": "시스템 프롬프트"
}
```

### Headers

```
X-Lego-Client-Id: <YOUR_CLIENT_KEY>
X-Lego-Client-Secret: <YOUR_CLIENT_SECRET>
Content-Type: application/json
```

### SSE Events

| 이벤트 상태 | 설명 |
|-------------|------|
| `CHUNK` | 텍스트 청크 (`content` 필드) |
| `DONE` | 메시지 종료 |

### Response (스트리밍 모드)

SSE(Server-Sent Events) 스트림으로 응답이 전달됩니다.

```json
// 각 SSE 이벤트의 data 필드
{
  "event_status": "CHUNK",
  "content": "응답 텍스트 조각"
}
```

```json
// 스트림 종료 이벤트
{
  "event_status": "DONE"
}
```

**스트리밍 응답 처리 흐름:**

```
┌──────────────────────────────────────────────────────────────────┐
│  SSE Stream                                                       │
├──────────────────────────────────────────────────────────────────┤
│  event: message                                                   │
│  data: {"event_status":"CHUNK","content":"안녕"}                   │
│                                                                   │
│  event: message                                                   │
│  data: {"event_status":"CHUNK","content":"하세요"}                 │
│                                                                   │
│  event: message                                                   │
│  data: {"event_status":"CHUNK","content":"!"}                      │
│                                                                   │
│  event: message                                                   │
│  data: {"event_status":"DONE"}                                     │
└──────────────────────────────────────────────────────────────────┘
```

### Response (논스트리밍 모드)

단일 JSON 응답으로 전달됩니다.

```json
{
  "content": "전체 응답 텍스트",
  "modelId": "사용된 모델 ID",
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 200,
    "total_tokens": 350
  }
}
```

### 응답 필드 상세

| 필드 | 타입 | 설명 |
|------|------|------|
| `event_status` | string | 스트리밍 이벤트 상태 (`CHUNK` / `DONE`) |
| `eventStatus` | string | `event_status`의 대체 키 (호환성) |
| `content` | string | 응답 텍스트 내용 |
| `modelId` | string | 응답을 생성한 모델 ID |
| `usage` | object | 토큰 사용량 정보 (논스트리밍에서만) |

### 응답 파싱 예시 (Python)

```python
import sseclient
import requests

# 스트리밍 모드
response = requests.post(api_url, headers=headers, json=body, stream=True)
client = sseclient.SSEClient(response)

result_message = ""
for event in client.events():
    if event.data:
        data = json.loads(event.data)
        event_status = data.get('event_status') or data.get('eventStatus')
        content = data.get('content', '')
        
        if event_status == 'CHUNK' and content:
            print(content, end="", flush=True)
            result_message += content
        elif event_status == 'DONE':
            break
```

## LLM 설정

`get_llm_config()` 메서드에서 다음 파라미터를 조정할 수 있습니다:

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `max_new_tokens` | 8192 | 최대 생성 토큰 수 |
| `temperature` | 0.4 | 응답의 창의성 (0~1) |
| `top_k` | 14 | 상위 K개 토큰에서 샘플링 |
| `top_p` | 0.94 | 누적 확률 기반 샘플링 |
| `repetition_penalty` | 1.04 | 반복 패널티 |

## 파일 생성 규칙

AI가 코드를 생성할 때 다음 형식을 사용합니다:

~~~markdown
```filename:path/to/file.ext
코드 내용
```
~~~

`/save` 명령어 실행 시 이 형식의 코드 블록이 자동으로 파일로 저장됩니다.

## Claude API 버전

Claude API를 사용하려면 `claude-ai-chat-code01.py` 파일을 참고하세요.

## 라이선스

MIT License
