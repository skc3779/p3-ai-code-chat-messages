# RELEASE v1.0.071 ~ v1.0.072

## 릴리즈 정보

| 항목 | 내용 |
|---|---|
| **버전** | v1.0.071 ~ v1.0.072 |
| **배포일** | 2026-03-06 |
| **대상 파일** | `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `gemini-ai-chat-code.py`, `src/context_builder.py`, `src/claude_assistant.py`, `src/genai_assistant.py`, `src/gemini_assistant.py` |

---

## v1.0.071 — `/read` 명령 ContextBuilder 통합

세 어시스턴트에서 개별 구현되어 있던 `/read` 처리를 통일.

- `context_builder.build_context(include_tree=False, file_patterns=[...])` 사용으로 일원화
- `/context`와 동일한 `[pattern1, pattern2, ...]` 다중 패턴 형식 지원
- `FilePatternMatcher` 별도 생성 제거 — `ContextBuilder` 내부 처리로 위임
- `conversation_history` 저장 포맷을 플랫폼별 규칙에 맞게 통일

---

## v1.0.072 — ContextBuilder 크기 제한을 TokenManager 토큰 한도로 통합

`ContextBuilder`의 독립적인 문자 수(chars) 제한을 제거하고 `TokenManager`의 플랫폼별 토큰 한도로 대체.

- `MAX_CONTEXT_SIZE` 환경변수 및 `max_context_size` 필드 제거
- 각 어시스턴트 생성 시 `TokenManager`의 플랫폼 토큰 한도를 `ContextBuilder`에 전달
- 문자 수 환산 기준(`chars_per_token = 3.5`) 적용 — 플랫폼별 실제 컨텍스트 윈도우 반영
- Claude · GenAI · Gemini가 각자의 토큰 한도에 맞는 컨텍스트 크기 제한 사용

---

## 관련 문서

- `FSD_v1.0.071_read-command-context-builder.md`
- `FSD_v1.0.072_context-builder-token-limit.md`
