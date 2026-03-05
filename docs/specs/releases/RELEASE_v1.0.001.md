# RELEASE v1.0.001

## 릴리즈 정보
- **버전:** v1.0.001
- **배포일:** 2026-01-25

## 주요 변경 사항
- **Claude API 전환:** 기존 Custom GenAI API에서 Anthropic Claude API로 전환 및 요청 구조(Endpoint, 인증, 메시지 형식) 변경
- **`/read` 명령어 오류 수정:** `/read` 명령어 결과를 System Role 대신 User Role로 컨텍스트 히스토리에 저장하도록 수정하여 Claude API(`400 Bad Request`) 호출 오류 해결
- **`/save` 명령어 개선:** 시스템 프롬프트 강화를 통해 AI가 정확한 생성 코드 블록 형식(`` ```filename: ... ``)을 따르도록 유도하여 파일 저장 기능 개선

## 관련 문서
- `BUG_v1.0.001_read-command-system-role.md`
- `BUG_v1.0.001_save-command-fix.md`
- `FSD_v1.0.001_claude-api-migration.md`
