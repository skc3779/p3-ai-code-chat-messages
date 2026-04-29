# GenAI Code Assistant

**GenAI 코딩 어시스턴트** - Samsung SCI Portal (Lego Platform) GenAI API를 활용한 대화형 코드 작성 도구

## 개요

GenAI Code Assistant는 터미널에서 Samsung SCI Portal의 GenAI API를 활용하여 코드 작성, 리팩토링, 문서화 등을 지원하는 AI 코딩 어시스턴트입니다. 프로젝트 파일 컨텍스트를 자동으로 분석하여 더 정확한 코드 생성을 지원하며, ANSI Art 배너와 Gemini CLI 스타일 TUI를 제공합니다. SCI Portal 보안 필터에 의한 민감 단어 차단 문제를 자동으로 우회하는 필터링 기능을 내장하고 있습니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| 💬 **대화형 채팅** | AI와 실시간 스트리밍 대화 |
| 🎨 **아름다운 UI/UX** | ANSI Art 시작 배너 + 3영역 하단 상태 바 (TUI) |
| ⏳ **응답 대기 스피너** | API 호출 시 동적 로딩 애니메이션 표시 |
| 📁 **파일 컨텍스트** | 프로젝트 파일을 자동으로 분석하여 AI에 전달 |
| 🌳 **프로젝트 트리** | 디렉토리 구조 시각화 |
| 💾 **파일 저장** | AI가 생성한 코드를 자동 추출 및 저장 |
| 📜 **대화 히스토리** | 이전 대화 내용 유지, 저장/로드 관리 |
| ⚙️ **LLM 설정** | temperature, top_k, top_p 등 파라미터 커스터마이징 |
| 🚀 **코드 실행** | AI가 생성한 코드를 직접 실행 (Python/JS/Bash) |
| 💻 **쉘 명령어** | 터미널 명령어 직접 실행 (안전/위험 모드) |
| ⌨️ **스마트 입력** | 커서 네비게이션, 인라인 명령어 제안(Tab/방향키), Meta+Enter 실행 |
| 📝 **멀티라인 컨텍스트** | `/context` 명령어에서 여러 줄 질문 지원 |
| 🔄 **자동 컨텍스트** | `/auto_context`로 파일 단위 자동 분할 반복 질의 지원 |
| 📊 **토큰 관리** | 환경변수 기반 토큰 한도/메시지 수 자동 트리밍 |
| 📐 **Diff Viewer** | 코드 변경 사항 비교 및 Diff 적용 |
| 📋 **프롬프트 템플릿** | `.system-prompts/` YAML 파일 기반 시스템 프롬프트 전환 |
| 👁️ **파일 감시** | watchdog 기반 실시간 파일 변경 감지 및 컨텍스트 자동 갱신 |
| 🔒 **민감 단어 필터** | `password`, `secret` 등 민감 키워드 자동 치환/복원 (SCI Portal 보안 필터 우회) |
| 📝 **API 로깅** | 요청/응답 JSON 파일 로깅 (`GEN_AI_LOG_ENABLED`) |
| 🏗️ **PyInstaller 빌드** | `.exe` 단독 실행 파일 빌드 지원 |

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 추가합니다:

```env
# AI 버전 정보
AI_VERSION=v1.0.067

# GenAI API Configuration
ENDPOINT_URL=https://your-genai-endpoint.com
YOUR_CLIENT_KEY=your_client_key_here
YOUR_CLIENT_SECRET=your_client_secret_here
YOUR_MODEL_ID=your_model_id_here

# TokenManager 설정
MAX_MESSAGES_TO_KEEP=30
MAX_TOKENS_GENAI=96000

# GenAI API 로깅 (true: 켜기 / false: 끄기)
GEN_AI_LOG_ENABLED=false
```

| 환경 변수 | 설명 | 기본값 |
|-----------|------|--------|
| `AI_VERSION` | 배너에 표시할 버전 정보 | `v1.0.040` |
| `ENDPOINT_URL` | GenAI API 엔드포인트 URL (필수) | - |
| `YOUR_CLIENT_KEY` | Lego Platform Client ID (필수) | - |
| `YOUR_CLIENT_SECRET` | Lego Platform Client Secret (필수) | - |
| `YOUR_MODEL_ID` | 사용할 모델 ID | - |
| `MAX_MESSAGES_TO_KEEP` | 히스토리 최대 유지 메시지 수 | `30` |
| `MAX_TOKENS_GENAI` | GenAI 토큰 한도 | `96000` |
| `GEN_AI_LOG_ENABLED` | API 요청/응답 JSON 로깅 활성화 | `false` |

## 사용법

### 실행

```bash
python gen-ai-chat-code.py
```

### 입력 방법

* **Enter**: 새 줄 추가 (멀티라인 입력)
* **Ctrl+Enter** 또는 **Meta+Enter(Alt+Enter)**: 명령어 실행
* **Esc**: 멀티라인 입력 취소
* **Tab** / **↑↓ 방향키**: 인라인 명령어 자동완성 및 제안 리스트 내비게이션

### 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `/files [ext]` | 프로젝트 파일 목록 | `/files .py .js` |
| `/tree` | 프로젝트 구조 보기 | `/tree` |
| `/read <pattern>` | 파일 읽기 (파일명, 상대경로, 와일드카드 지원) | `/read *.py`, `/read src/utils.py` |
| `/context <pattern> [질문]` | 파일 컨텍스트 포함 질문 (질문 생략 시 멀티라인 모드) | `/context *.py` |
| `/auto_context <pattern> [명령어]`| 파일 단위로 컨텍스트를 자동 분할하여 반복 질의 | `/auto_context *.py 리팩토링해줘` |
| `/save` | AI 응답에서 파일 추출 및 저장 | `/save` |
| `/workspace [path]` | 작업 디렉토리 변경 | `/workspace ./src` |
| `/stream`, `/nostream` | 스트리밍 모드 전환 | `/stream` |
| `/history`, `/clear` | 대화 히스토리 조회/초기화 | `/history` |
| `/save_history [name]` | 대화 히스토리 파일로 저장 | `/save_history` |
| `/load_history <name>` | 저장된 히스토리 로드 | `/load_history history_20260125.json` |
| `/list_history` | 저장된 히스토리 목록 | `/list_history` |
| `/tokens` | 토큰 사용량 확인 | `/tokens` |
| `/run [lang]` | 마지막 응답의 코드 실행 | `/run python` |
| `/diff` | 마지막 응답의 코드를 현재 파일과 비교 | `/diff` |
| `/apply` | Diff 내용을 파일에 적용 | `/apply` |
| `/multiline` | 멀티라인 입력 모드 (종료: /end) | `/multiline` |
| `/shell <cmd>` | 쉘 명령어 실행 (안전 모드) | `/shell pip list` |
| `/shell! <cmd>` | 쉘 명령어 실행 (위험 명령 허용) | `/shell! rm -rf temp/` |
| `/llm_config <lang>` | 언어별 LLM 파라미터 설정 | `/llm_config Python` |
| `/template <name>` | 시스템 프롬프트 템플릿 변경 | `/template code-review` |
| `/template_list` | 사용 가능한 템플릿 목록 | `/template_list` |
| `/template_reset` | 기본 시스템 프롬프트로 복귀 | `/template_reset` |
| `/watch <pattern>` | 파일 변경 감시 시작 | `/watch *.py` |
| `/unwatch <pattern>` | 파일 변경 감시 중지 | `/unwatch *.py` |
| `/watch_list` | 감시 중인 패턴 목록 | `/watch_list` |
| `/help` | 도움말 보기 | `/help` |
| `/quit` | 종료 | `/quit` |

### 사용 예시

```bash
# 프로젝트 파일 기반으로 README 작성 요청
👤 You: /context *.py 이 프로젝트에 README.md를 작성해줘

# 다중 패턴 질의
👤 You: /context [src/*.py, docs/*.md] README 작성해줘

# 파일 단위 자동 분할 반복 질의
👤 You: /auto_context src/*.py 이 코드를 리팩토링해줘

# LLM 설정 변경
👤 You: /llm_config Python
✅ LLM 설정이 'python' 로 적용되었습니다.

# 코드 Diff 확인 및 적용
👤 You: /diff
👤 You: /apply

# 토큰 사용량 확인
👤 You: /tokens
```

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    GenAICodeAssistant                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ FileManager │  │ TreeBuilder  │  │   ContextBuilder    │ │
│  │  (파일 I/O) │  │ (트리 생성)  │  │  (컨텍스트 구성)    │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
│  ┌──────────────┐ ┌────────────────┐ ┌─────────────────────┐ │
│  │ TokenManager │ │ ApiLogger      │ │ SensitiveWordFilter │ │
│  │ (토큰 트리밍)│ │ (API 로깅)    │ │ (민감 단어 필터)    │ │
│  └──────────────┘ └────────────────┘ └─────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ FilePatternMatcher · ContextProcessor · ResponseParser   │ │
│  │ DiffViewer · CodeExecutor · TerminalExecutor             │ │
│  │ TemplateManager · CommandRegistry · CLIInputHandler       │ │
│  │ WaitSpinner · LLMConfig                                   │ │
│  └──────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    GenAI API (SSE Streaming)                 │
│            {ENDPOINT_URL}/openapi/chat/v1/messages           │
└─────────────────────────────────────────────────────────────┘
```

## API 사양

### Request

```json
{
  "modelIds": ["your_model_id"],
  "contents": ["대화 내용 배열"],
  "llmConfig": {
    "max_new_tokens": 10240,
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

### Response (논스트리밍 모드)

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

## 민감 단어 필터링

Samsung SCI Portal의 보안 필터가 `password`, `secret`, `credential`, `token`, `api_key`, `apikey` 등의 민감 키워드를 감지하여 요청을 차단하는 문제를 자동으로 해결합니다.

- **전송 전 (mask)**: 민감 단어를 안전한 대체 문자열로 치환 (예: `password` → `p1assw1ord`)
- **수신 후 (unmask)**: 치환된 단어를 원래 단어로 복원
- 대소문자 패턴을 유지하면서 치환/복원 (`PASSWORD` → `P1ASSW1ORD`, `Password` → `P1assw1ord`)

## LLM 설정

`/llm_config` 명령어 또는 `get_llm_config()` 메서드에서 다음 파라미터를 조정할 수 있습니다:

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `max_new_tokens` | 10240 | 최대 생성 토큰 수 |
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

## 빌드 (선택)

PyInstaller를 이용해 `.exe` 단독 실행 파일을 빌드할 수 있습니다:

```powershell
# PowerShell 스크립트로 빌드
.\build_scripts\build_genai.ps1
```

빌드 산출물은 `build_output/dist/` 폴더에 생성됩니다.

## 라이선스

MIT License
