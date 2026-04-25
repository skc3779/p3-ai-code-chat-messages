# FSD v1.0.064 - Multi-Model API Logging

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.064 |
| 제목 | Claude 및 Gemini API 요청/응답 공통 로깅 지원 |
| 작성일 | 2026-03-03 |
| 상태 | 설계 완료 |
| 선행 FSD | [FSD v1.0.062](./FSD_v1.0.062_genai-api-logging.md) -- GenAI API Logging |
| 대상 소스 | `src/api_logger.py` (신규/리팩터링), `src/claude_assistant.py`, `src/gemini_assistant.py`, `src/genai_assistant.py` |

---

## 1. 개요 (Overview)

기존 GenAI(SCI Portal)에 한정적으로 적용되어 있던 JSON 파일 기반 API 요청/응답 로깅 기능(`GEN_AI_LOG_ENABLED`)을 확장하여, **Claude** 및 **Gemini** API 호출에 대해서도 각각 `CLAUDE_AI_LOG_ENABLED`, `GEMINI_AI_LOG_ENABLED` 환경변수를 통해 동일한 형태의 파일 로깅(Request Headers, Body 및 Response JSON)이 생성될 수 있도록 공통/범용 구조로 개선합니다.

### 1.1 개선 목표

| # | 목표 | 설명 |
|---|------|------|
| 1 | 로깅 모듈 범용화 | `GenAIApiLogger`를 `ApiLogger`로 이름을 변경하고 Provider 명칭(claude, gemini, gen-ai)에 따라 동적으로 환경변수 및 디렉토리를 처리하도록 리팩터링합니다. |
| 2 | 환경변수 추가 | `.env` 파일에 `GEMINI_AI_LOG_ENABLED=true`, `CLAUDE_AI_LOG_ENABLED=true` 제어 변수를 추가합니다. |
| 3 | Claude 로깅 지원 | `ClaudeCodeAssistant`의 `_chat_streaming`, `_chat_non_streaming` 메서드 호출 직전/직후에 API Request/Response를 로깅합니다. |
| 4 | Gemini 로깅 지원 | `GeminiCodeAssistant`의 `_chat_streaming`, `_chat_non_streaming` 메서드 호출 직전/직후에 API Request/Response를 로깅합니다. |
| 5 | 개별 로그 디렉토리 생성 | 로그가 `logs/claude/`, `logs/gemini/` 등 제공자(provider) 이름의 하위 폴더에 따로 분리 저장되도록 합니다. |

---

## 2. 설계 상세 (Design)

### 2.1 통합 로거 클래스 (`ApiLogger`)

기존 `genai_api_logger.py`는 `api_logger.py`로 대체됩니다.
`ApiLogger` 클래스의 초기화 과정에서 `provider` 문자열을 넘겨받아 동적으로 매핑합니다.

#### 환경변수 매핑 규칙
* `provider == "claude"` -> `CLAUDE_AI_LOG_ENABLED`
* `provider == "gemini"` -> `GEMINI_AI_LOG_ENABLED`
* `provider == "gen-ai"` -> `GEN_AI_LOG_ENABLED`

#### 디렉토리 및 파일명 규칙
* 로그 디렉토리: `logs/{provider}` 
* 파일명: `{provider}-{UUID}-request-{YYYYMMDDHHMMSS}.json`

### 2.2 Claude / Gemini Assistant 수정

각 Assistant 클래스 초기화 단계(`__init__`)에서 자신의 로거 인스턴스를 생성합니다.
* Claude: `self.api_logger = ApiLogger(provider="claude", workspace_dir=workspace_dir)`
* Gemini: `self.api_logger = ApiLogger(provider="gemini", workspace_dir=workspace_dir)`

스트리밍 및 논스트리밍 호출 과정 전/후로 아래를 수행합니다.
* Request 이전: `log_id = self.api_logger.log_request(api_url, headers, body, streaming, model_id)`
* Response(또는 스트림 Error) 이후: `self.api_logger.log_response(log_id, status_code, streaming, ...)`

---

## 3. 요구사항 (Requirements)

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-064-001 | 통합 공통 로거 모듈인 `ApiLogger`(`src/api_logger.py`)를 개발(또는 리팩터링)한다. | 필수 |
| REQ-064-002 | `ApiLogger`는 초기화 시 전달받은 `provider`를 기준으로 개별 환경변수(`[PROVIDER]_AI_LOG_ENABLED`)를 읽어 동작을 제어한다. | 필수 |
| REQ-064-003 | API 로그 파일들은 프로젝트 디렉토리 내 `logs/{provider}/` 위치에 저장되어야 한다. | 필수 |
| REQ-064-004 | 기존 `GenAIAssistant` 모듈은 공통 `ApiLogger`를 사용할 수 있도록 의존성이 교체되어야 한다. (동작 호환성 유지) | 필수 |
| REQ-064-005 | `ClaudeCodeAssistant`의 API 호출 시 원본 HTTP Request 헤더/바디, Response 내역이 로깅되어야 한다. | 필수 |
| REQ-064-006 | `GeminiCodeAssistant`의 API 호출 시 원본 HTTP Request 헤더/바디, Response 내역이 로깅되어야 한다. | 필수 |

### 3.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-064-001 | 로깅 수행 중 에러나 디렉토리 권한 문제 등이 발생하더라도 Assistant의 핵심 동작(채팅 등)이 차단되어서는 안 된다. |
| NREQ-064-002 | 로그 파일에 저장되는 API Secret Key (ex: `x-api-key`, 헤더 내 `Authorization` 등)는 `***MASKED***` 처리되어야 한다. |

---

## 4. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `docs/specs/requirements/FSD_v1.0.064_multi-model-api-logging.md` | **신규** | 현재 문서 생성 |
| `src/genai_api_logger.py` | **삭제** | 범용성 확보를 위해 제거/위치 이동 |
| `src/api_logger.py` | **신규** | `provider` 인자를 통해 모든 벤더를 지원하는 `ApiLogger` 생성 |
| `src/claude_assistant.py` | **수정** | `ApiLogger("claude")` 도입, `log_request`, `log_response` 연동 |
| `src/gemini_assistant.py` | **수정** | `ApiLogger("gemini")` 도입, `log_request`, `log_response` 연동 |
| `src/genai_assistant.py` | **수정** | 기존 `GenAIApiLogger`를 `ApiLogger("gen-ai")`로 교체 |
| `.env` & `.env.example` | **수정** | `GEMINI_AI_LOG_ENABLED=true`, `CLAUDE_AI_LOG_ENABLED=true` 추가 가이드 반영 |
