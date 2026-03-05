# RELEASE v1.0.063

## 릴리즈 정보
- **버전:** v1.0.063
- **배포일:** 2026-03-03

## 주요 변경 사항
- **대화 내역 토큰 관리 정책 고도화:** `TokenManager`의 토큰 한도 및 최대 유지 메시지 수를 `.env` 파일 환경변수(`MAX_TOKENS_CLAUDE`, `MAX_TOKENS_GENAI`, `MAX_TOKENS_GEMINI`, `MAX_MESSAGES_TO_KEEP`)로 분리하여 운영 유연성을 높였습니다. 메시지가 지정된 개수를 초과하거나 토큰 수의 75%를 초과할 때 오래된 내역을 자동 삭감하도록 트리밍 조건이 합리적으로 개선되었습니다.

## 관련 문서
- `FSD_v1.0.063_token-manager-env-config.md`
