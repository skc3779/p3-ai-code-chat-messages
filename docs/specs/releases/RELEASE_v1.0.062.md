# RELEASE v1.0.062

## 릴리즈 정보
- **버전:** v1.0.062
- **배포일:** 2026-03-02

## 주요 변경 사항
- **GenAI API 통합 로깅:** 디버깅과 장애 분석을 용이하게 하기 위해 GenAI API로 전송되는 Request Header/Body 및 수신되는 Response를 자동으로 `logs/gen-ai/` 폴더에 JSON 파일로 기록하는 기능이 추가되었습니다. `.env` 파일의 `GEN_AI_LOG_ENABLED` 변수로 제어하며 비밀 값은 로깅 시 마스킹 처리됩니다.
- **코드 블록 추출 버그 수정:** AI 응답에서 언어 태그가 없는 코드 블록(` ``` `)이 포함된 경우 파일 파싱이 도중에 조기 종료되어 일부 내용이 누락되는 버그(`/save`, `/auto_context` 명령어 관련)가 수정되었습니다.

## 관련 문서
- `FSD_v1.0.062_genai-api-logging.md`
- `BUG_v1.0.062_auto-save-untagged-codeblock.md`
