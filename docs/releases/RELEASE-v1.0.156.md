# Release v1.0.156

## 주요 변경 사항

### `/tokens` 명령어 개선
- **`MAX_MESSAGES_TO_KEEP` 런타임 수정**:
  - `/tokens -k <number>`: 메시지 보관 한도를 애플리케이션 재시작 없이 런타임에 즉시 변경합니다.
  - `/tokens -k default`: 메시지 보관 한도를 `.env` 파일에 설정된 기본값으로 복원합니다.
- **출력 형식 통일**: 
  - `claude`, `gemini`, `gen-ai` 세 엔트리포인트의 `/tokens` 출력 형식이 동일해졌습니다.
  - 현재 보관 중인 메시지 수와 한도를 `메시지 수: N / MAX` 형태로 직관적으로 표시합니다.
- **플랫폼별 토큰 한계값 표시**: 
  - `.env` 파일을 열지 않아도 `/tokens` 명령어 출력 내에서 Claude, GenAI, Gemini의 토큰 한계 설정값(MAX_TOKENS_*)을 한눈에 확인할 수 있습니다.

## 변경된 파일
- `src/token_manager.py`
- `claude-ai-chat-code.py`
- `gemini-ai-chat-code.py`
- `gen-ai-chat-code.py`
- `src/command_registry.py`
- `tests/test_tokens_command.py`
