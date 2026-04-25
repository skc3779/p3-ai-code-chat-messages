# RELEASE v1.0.082

## 1. 개요
* **버전**: v1.0.082
* **일자**: 2026-04-18
* **목적**: API 로거(api_logger.py)의 파일 이름 규칙 개선으로 request와 response 로그의 타임스탬프 일치

## 2. 주요 변경 사항

### 2.1 API 로그 파일명 규칙 변경
API 통합 시스템(Claude, Gemini, GenAI 등) 호출 시 저장되는 JSON 로그 파일의 식별을 명확하게 하기 위해 파일명 규칙을 다음과 같이 일관성 있게 변경하였습니다.

**기존 규칙**:
- Request: `{provider}-{UUID}-request-{YYYYMMDDHHMMSS}.json`
- Response: `{provider}-{UUID}-response-{YYYYMMDDHHMMSS}.json`
> 문제점: Request 시점과 Response 시점의 타임스탬프가 달라 로그 식별이 직관적이지 않았음.

**변경된 규칙**:
- Request: `{provider}-{YYYYMMDDHHMMSS}-{UUID}-request.json`
- Response: `{provider}-{YYYYMMDDHHMMSS}-{UUID}-response.json`
> 개선점: UUID와 함께 동일한 타임스탬프를 부여하여, 같은 요청과 응답 로그 쌍이 알파벳/시간순으로 완벽하게 정렬 및 매칭되도록 개선함.

### 2.2 구현 세부 내용
- `src/api_logger.py` 내의 `_generate_log_id()` 메서드를 수정하여 기존의 `{UUID}` 대신 타임스탬프를 포함한 `{YYYYMMDDHHMMSS}-{UUID}` 형식으로 `log_id`를 생성하도록 변경.
- 생성 시점에 확정된 고정 타임스탬프를 `log_id` 단일 변수로 묶어 관리하므로 `log_request` 와 `log_response` 모두 동일한 파일명을 안전하게 공유할 수 있음.

## 3. 영향 범위
- `src/api_logger.py` 모듈만 변경되었으므로 사용자 인터페이스(CLI) 영향 없음.
- `logs/{provider}/` 디렉토리 아래에 생성되는 파일들의 정렬 기준이 더욱 직관적이 됨.

## 4. 검증 내역
- `log_request` 함수가 `log_id`를 안전하게 생성하고 이 값이 `log_response`와 오류 없이 연계되는 것을 코드 레벨에서 확인 및 통합 완료함.
