# Gemini Code Assistant

**Gemini AI 코딩 어시스턴트** - Google Gemini API를 활용한 대화형 코드 작성 도구

## 개요

Gemini Code Assistant는 터미널에서 Google Gemini API를 활용하여 코드 작성, 리팩토링, 문서화 등을 지원하는 AI 코딩 어시스턴트입니다. 프로젝트 파일 컨텍스트를 자동으로 분석하여 더 정확한 코드 생성을 지원하며, ANSI Art 배너와 Gemini CLI 스타일 TUI를 제공합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| 💬 **대화형 채팅** | Gemini AI와 실시간 스트리밍 대화 |
| 🎨 **아름다운 UI/UX** | ANSI Art 시작 배너 + 3영역 하단 상태 바 (TUI) |
| ⏳ **응답 대기 스피너** | API 호출 시 동적 로딩 애니메이션 표시 |
| 📁 **파일 컨텍스트** | 프로젝트 파일을 자동으로 분석하여 AI에 전달 |
| 🌳 **프로젝트 트리** | 디렉토리 구조 시각화 |
| 💾 **파일 저장** | AI가 생성한 코드를 자동 추출 및 저장 |
| 📜 **대화 히스토리** | 이전 대화 내용 유지, 저장/로드 관리 |
| 📐 **Diff Viewer** | 코드 변경 사항 비교 및 Diff 적용 |
| 🚀 **코드 실행** | AI가 생성한 코드를 직접 실행 (Python/JS/Bash) |
| 💻 **쉘 명령어** | 터미널 명령어 직접 실행 (안전/위험 모드) |
| ⌨️ **스마트 입력** | 커서 네비게이션, 인라인 명령어 제안(Tab/방향키), Meta+Enter 실행 |
| 📝 **멀티라인 컨텍스트** | `/context` 명령어에서 여러 줄 질문 지원 |
| 🔄 **자동 컨텍스트** | `/auto_context`로 파일 단위 자동 분할 반복 질의 지원 |
| 📊 **토큰 관리** | 환경변수 기반 토큰 한도/메시지 수 자동 트리밍 |
| 📋 **프롬프트 템플릿** | `.system-prompts/` YAML 파일 기반 시스템 프롬프트 전환 |
| 👁️ **파일 감시** | watchdog 기반 실시간 파일 변경 감지 |
| 📝 **API 로깅** | 요청/응답 JSON 파일 로깅 (`GEMINI_AI_LOG_ENABLED`) |
| 🏗️ **PyInstaller 빌드** | `.exe` 단독 실행 파일 빌드 지원 |

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

*주요 의존성: `requests`, `sseclient-py`, `python-dotenv`, `PyYAML`, `prompt_toolkit` (선택), `watchdog` (선택)*

### 2. 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 추가합니다:

```env
# AI 버전 정보
AI_VERSION=v1.0.067

# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL_ID=gemini-3-pro-preview
GEMINI_API_ENDPOINT=https://generativelanguage.googleapis.com/v1beta

# TokenManager 설정
MAX_MESSAGES_TO_KEEP=30
MAX_TOKENS_GEMINI=786000

# API 로깅 (true: 켜기 / false: 끄기)
GEMINI_AI_LOG_ENABLED=false
```

| 환경 변수 | 설명 | 기본값 |
|-----------|------|--------|
| `AI_VERSION` | 배너에 표시할 버전 정보 | `v1.0.040` |
| `GEMINI_API_KEY` | Google AI Studio API 키 (필수) | - |
| `GEMINI_MODEL_ID` | 사용할 Gemini 모델 | `gemini-3.0-flash` |
| `GEMINI_API_ENDPOINT` | API 엔드포인트 | `https://generativelanguage.googleapis.com/v1beta` |
| `MAX_MESSAGES_TO_KEEP` | 히스토리 최대 유지 메시지 수 | `30` |
| `MAX_TOKENS_GEMINI` | Gemini 토큰 한도 | `786000` |
| `GEMINI_AI_LOG_ENABLED` | API 요청/응답 JSON 로깅 활성화 | `false` |

## 사용법

### 실행

```bash
python gemini-ai-chat-code.py
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
| `/auto_context <pattern> [질문]`| 파일 단위로 컨텍스트를 자동 분할하여 반복 질의 | `/auto_context *.py 리팩토링해줘` |
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
| `/shell <cmd>` | 쉘 명령어 실행 | `/shell pip list` |
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

# 파일 단위 자동 분할 반복 질의
👤 You: /auto_context [src/*.py, docs/*.md] README 작성해줘

# 코드 Diff 확인 및 적용
👤 You: /diff
👤 You: /apply

# 멀티라인 입력 (Ctrl+Enter로 실행)
👤 You: 이 코드를 분석해서
... 다음 내용을 포함한
... 문서를 작성해줘
... [Ctrl+Enter]

# 토큰 사용량 확인
👤 You: /tokens
```

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    GeminiCodeAssistant                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ FileManager │  │ TreeBuilder  │  │   ContextBuilder    │ │
│  │  (파일 I/O) │  │ (트리 생성)  │  │  (컨텍스트 구성)    │ │
│  └─────────────┘  └──────────────┘  └─────────────────────┘ │
│  ┌──────────────┐ ┌────────────────┐ ┌─────────────────────┐ │
│  │ TokenManager │ │ ApiLogger      │ │ WaitSpinner         │ │
│  │ (토큰 트리밍)│ │ (API 로깅)    │ │ (대기 애니메이션)   │ │
│  └──────────────┘ └────────────────┘ └─────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ FilePatternMatcher · ContextProcessor · ResponseParser   │ │
│  │ DiffViewer · CodeExecutor · TerminalExecutor             │ │
│  │ TemplateManager · CommandRegistry · CLIInputHandler       │ │
│  └──────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Gemini API (REST)                         │
│         generativelanguage.googleapis.com/v1beta             │
└─────────────────────────────────────────────────────────────┘
```

## API 사양

Gemini API v1beta를 사용합니다.

### Request

```json
{
  "contents": [
    {
      "parts": [{"text": "..."}],
      "role": "user"
    }
  ],
  "generationConfig": {
    "temperature": 0.4,
    "topK": 40,
    "topP": 0.95,
    "maxOutputTokens": 8192
  }
}
```

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
.\build_scripts\build_gemini.ps1
```

빌드 산출물은 `build_output/dist/` 폴더에 생성됩니다.

## 라이선스

MIT License
