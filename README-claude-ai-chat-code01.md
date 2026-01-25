# Claude Code Assistant

**Claude AI 코딩 어시스턴트** - Anthropic Claude API를 활용한 대화형 코드 작성 도구

## 개요

Claude Code Assistant는 터미널에서 Anthropic Claude API를 활용하여 코드 작성, 리팩토링, 문서화 등을 지원하는 AI 코딩 어시스턴트입니다. 프로젝트 파일 컨텍스트를 자동으로 분석하여 더 정확한 코드 생성을 지원합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| 💬 **대화형 채팅** | Claude AI와 실시간 스트리밍 대화 |
| 📁 **파일 컨텍스트** | 프로젝트 파일을 자동으로 분석하여 AI에 전달 |
| 🌳 **프로젝트 트리** | 디렉토리 구조 시각화 |
| 💾 **파일 저장** | AI가 생성한 코드를 자동 추출 및 저장 |
| 📜 **대화 히스토리** | 이전 대화 내용 유지 및 관리 |
| 🔨 **Tool Use** | 파일 시스템, Git, 패키지 관리 도구 자동 호출 |
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
# Claude API Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CLAUDE_MODEL_ID=claude-sonnet-4-5
CLAUDE_API_ENDPOINT=https://api.anthropic.com
```

| 환경 변수 | 설명 | 기본값 |
|-----------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API 키 (필수) | - |
| `CLAUDE_MODEL_ID` | 사용할 Claude 모델 | `claude-sonnet-4-5` |
| `CLAUDE_API_ENDPOINT` | API 엔드포인트 | `https://api.anthropic.com` |

## 사용법

### 실행

```bash
python claude-ai-chat-code01.py
```

### 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `/files [ext]` | 프로젝트 파일 목록 | `/files .py .js` |
| `/tree` | 프로젝트 구조 보기 | `/tree` |
| `/read <pattern>` | 파일 읽기 | `/read src/*.py` |
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

# 코드 실행
👤 You: /run python
```

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    ClaudeCodeAssistant                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ FileManager │  │ TreeBuilder  │  │   ContextBuilder    │ │
│  │  (파일 I/O) │  │ (트리 생성)  │  │  (컨텍스트 구성)    │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Claude API (SSE Streaming)               │
│                 https://api.anthropic.com/v1/messages       │
└─────────────────────────────────────────────────────────────┘
```

## API 사양

### Request

```json
{
  "model": "claude-sonnet-4-5",
  "messages": [{"role": "user", "content": "..."}],
  "max_tokens": 8192,
  "system": "시스템 프롬프트",
  "stream": true
}
```

### Headers

```
x-api-key: <ANTHROPIC_API_KEY>
anthropic-version: 2023-06-01
Content-Type: application/json
```

### SSE Events

| 이벤트 타입 | 설명 |
|-------------|------|
| `content_block_delta` | 텍스트 청크 (`delta.text`) |
| `message_stop` | 메시지 종료 |

## 파일 생성 규칙

AI가 코드를 생성할 때 다음 형식을 사용합니다:

~~~markdown
```filename:path/to/file.ext
코드 내용
```
~~~

`/save` 명령어 실행 시 이 형식의 코드 블록이 자동으로 파일로 저장됩니다.

## 라이선스

MIT License
