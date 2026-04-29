# RELEASE v1.0.064

## 릴리즈 정보
- **버전:** v1.0.064
- **배포일:** 2026-03-03

## 주요 변경 사항
- **전체 플랫폼 통합 API 로깅:** GenAI Provider에만 적용되던 API 요청/응답 파일 로깅 기능을 확장하여, Claude 및 Gemini API 호출 시에도 개별 환경변수(`CLAUDE_AI_LOG_ENABLED`, `GEMINI_AI_LOG_ENABLED`)에 따라 `logs/claude/`, `logs/gemini/` 폴더에 각각 로그가 저장되도록 공통 로깅 모듈(`ApiLogger`)로 재설계되었습니다.

## 관련 문서
- `FSD_v1.0.064_multi-model-api-logging.md`
