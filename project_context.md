# AI Code Chat Messages 프로젝트 컨텍스트

AI Code Chat Messages (p3-ai-code-chat-messages)는 오픈 소스 기반의 터미널 중심 AI 코딩 어시스턴트입니다. Claude 및 커스텀 GenAI 모델의 기능을 통합하여 프로젝트 파일을 분석하고, 코드를 생성하며, 안전한 환경 내에서 이를 실행합니다.

## 프로젝트 개요

- **목적:** AI 모델(Claude, GenAI)을 위한 원활한 터미널 인터페이스를 제공하여 코드 이해, 생성, 자동화 및 실행을 지원합니다.
- **주요 기술:**
  - **런타임:** Python 3.8+ (주 사용), Node.js (선택 사항, JS 실행용)
  - **핵심 라이브러리:** `requests`, `sseclient-py`, `python-dotenv`
  - **AI 통합:** Anthropic Claude API, 커스텀 GenAI API
- **아키텍처:** 모듈화된 Python 패키지 구조.
  - **진입점 (Entry Points):**
    - `claude-ai-chat-code01.py`: Claude 기반 어시스턴트 실행 파일.
    - `gen-ai-chat-code01.py`: 커스텀 GenAI 기반 어시스턴트 실행 파일.
  - **핵심 로직 (`src/`):**
    - `claude_assistant.py` / `genai_assistant.py`: 특정 모델에 대한 오케스트레이션 로직.
    - `code_executor.py`: Python, JavaScript, Bash 스니펫 실행을 위한 샌드박스.
    - `terminal_executor.py`: 쉘 명령어 실행 처리 (안전/관리자 모드).
    - `file_manager.py`: 파일 시스템 작업 (읽기, 쓰기, 목록 조회).
    - `git_manager.py`: 버전 관리를 위한 Git 통합.
    - `tool_definitions.py`: AI가 사용할 수 있는 도구 정의.
  - **문서화:** 사양 및 가이드가 포함된 `docs/` 디렉토리.

## 빌드 및 실행

- **의존성 설치:** `pip install requests sseclient-py python-dotenv`
- **환경 설정:**
  - 루트 디렉토리에 `.env` 파일을 생성합니다.
  - API 설정 추가:
    ```env
    # Claude 설정
    ANTHROPIC_API_KEY=sk-...
    CLAUDE_MODEL_ID=claude-3-5-sonnet-...
    
    # GenAI 설정
    ENDPOINT_URL=...
    YOUR_CLIENT_KEY=...
    ```
- **애플리케이션 실행:**
  - Claude: `python claude-ai-chat-code01.py`
  - GenAI: `python gen-ai-chat-code01.py`

## 테스트 및 품질

- **테스트 프레임워크:** 표준 Python `unittest` (`tests/` 구조에서 추론).
- **테스트 명령어:**
  - **명령어 테스트:** `python tests/test_commands.py`
  - **도구 사용 테스트:** `python tests/test_tool_use.py`
- **통합:** 테스트는 `src/`의 모듈을 임포트하여 실제 기능을 검증합니다.

## 개발 규칙

- **구조:** 모든 핵심 로직은 반드시 `src/` 패키지 내에 위치해야 합니다.
- **비밀 관리:** API 키 및 민감한 데이터는 반드시 `.env`를 사용해야 합니다.
- **코드 스타일:** 표준 Python PEP 8 가이드라인을 따릅니다.
- **임포트:** 가능한 경우 `src`로부터의 절대 임포트를 사용하거나, 패키지 내에서는 상대 임포트를 사용합니다.

## 문서화

- **기본:** `README.md`에 주요 사용법 가이드 및 기능 개요가 포함되어 있습니다.
- **사양:** 상세 사양(예: 프롬프트, API)은 `docs/specs/`에 위치합니다.
- **이미지:** 자산 및 스크린샷은 `docs/images/`에 위치합니다.
