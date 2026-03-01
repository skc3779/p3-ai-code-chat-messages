# Gemini Code Assistant

**Gemini AI 코딩 어시스턴트** - Google Gemini API를 활용한 대화형 코드 작성 도구

## 개요

Gemini Code Assistant는 터미널에서 Google Gemini API를 활용하여 코드 작성, 리팩토링, 문서화 등을 지원하는 AI 코딩 어시스턴트입니다. 프로젝트 파일 컨텍스트를 자동으로 분석하여 더 정확한 코드 생성을 지원합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| 💬 **대화형 채팅** | Gemini AI와 실시간 스트리밍 대화 |
| 🎨 **아름다운 UI/UX** | 시작 배너 (ANSI Art) 및 3영역 하단 상태 바 (TUI) |
| 📁 **파일 컨텍스트** | 프로젝트 파일을 자동으로 분석하여 AI에 전달 |
| 🌳 **프로젝트 트리** | 디렉토리 구조 시각화 |
| 💾 **파일 저장** | AI가 생성한 코드를 자동 추출 및 저장 |
| 📜 **대화 히스토리** | 이전 대화 내용 유지 및 관리 |
| 🔨 **Diff Viewer** | 코드 변경 사항 비교 및 표시 |
| 🚀 **코드 실행** | AI가 생성한 코드를 직접 실행 (Python/JS/Bash) |
| 💻 **쉘 명령어** | 터미널 명령어 직접 실행 |
| ⌨️ **스마트 입력** | 커서 네비게이션, 인라인 명령어 제안(Tab/방향키), Meta+Enter 실행 |
| 📝 **멀티라인 컨텍스트** | `/context` 명령어에서 여러 줄 질문 지원 |
| 🔄 **자동 컨텍스트** | `/auto_context`로 파일 단위 자동 분할 반복 질의 지원 |

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```
*참고: `requests`, `sseclient-py`, `python-dotenv`, `readchar` 등이 설치됩니다.*

### 2. 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 추가합니다:

```env
# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL_ID=gemini-3.0-flash
GEMINI_API_ENDPOINT=https://generativelanguage.googleapis.com/v1beta
```

| 환경 변수 | 설명 | 기본값 |
|-----------|------|--------|
| `GEMINI_API_KEY` | Google AI Studio API 키 (필수) | - |
| `GEMINI_MODEL_ID` | 사용할 Gemini 모델 | `gemini-3.0-flash` |
| `GEMINI_API_ENDPOINT` | API 엔드포인트 | `https://generativelanguage.googleapis.com/v1beta` |

## 사용법

### 실행

```bash
python gemini-ai-chat-code01.py
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
| `/history`, `/clear` | 대화 히스토리 관리 | `/history` |
| `/run [lang]` | 마지막 응답의 코드 실행 | `/run python` |
| `/shell <cmd>` | 쉘 명령어 실행 | `/shell pip list` |
| `/diff` | 마지막 응답의 코드를 현재 파일과 비교 | `/diff` |
| `/apply` | Diff 내용을 파일에 적용 | `/apply` |
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

# 멀티라인 입력 (Ctrl+Enter로 실행)
👤 You: 이 코드를 분석해서
... 다음 내용을 포함한
... 문서를 작성해줘
... [Ctrl+Enter]

# 코드 실행
👤 You: /run python
```

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    GeminiCodeAssistant                      │
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
│                    Gemini API (REST)                        │
│         generativelanguage.googleapis.com/v1beta            │
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

## 라이선스

MIT License
