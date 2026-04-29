# RELEASE v1.0.073 ~ v1.0.075

## 릴리즈 정보

| 항목 | 내용 |
|---|---|
| **버전** | v1.0.073 ~ v1.0.075 |
| **배포일** | 2026-03-06 |
| **대상 파일** | `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `gemini-ai-chat-code.py`, `src/command_registry.py`, `src/terminal_executor.py` |

---

## v1.0.073 — `/history` 선택 삭제 명령 추가

**오래된 히스토리를 선택적으로 삭제**하여 토큰 소비를 절감한다.

| 명령 | 동작 |
|---|---|
| `/history --remove N` / `-r N` | 앞(가장 오래된 항목)부터 N개 삭제 |
| `/history --delete index` / `-d index` | 지정한 1-based 인덱스 항목 1개 삭제 후 목록 재출력 |

- N이 총 항목 수를 초과하면 삭제 거부 메시지 출력
- index가 범위 밖이거나 숫자가 아니면 오류 안내

---

## v1.0.074 — `print_menu()` 단일화 및 명령 메타 정보 통합

세 엔트리 포인트에 중복 정의되어 있던 `/help` 출력 함수를 `command_registry.py` 한 곳으로 통합.

- `CommandInfo` 데이터클래스에 `example` 필드 추가 — 설명·사용법·예제를 한 곳에서 관리
- 각 엔트리 포인트의 로컬 `print_menu()` 제거 → `from src.command_registry import print_menu` 사용

---

## v1.0.075 — `/shell` 버그 수정 및 기능 개선

**버그 수정**

| ID | 파일 | 내용 |
|---|---|---|
| B-01 | `claude-ai-chat-code.py` | 실패 시 `stderr` 블록 중복 출력 제거 |
| B-02 | `gemini-ai-chat-code.py` | `execute(allow_dangerous=)` → `allow_unsafe=` 수정 (`TypeError` 해소) |
| B-03 | `gemini-ai-chat-code.py` | Dict 결과를 raw 출력하던 문제 → 포맷된 출력으로 수정 |

**기능 추가**

- `/shell --help` / `-h` : OS(Windows/Linux)별 허용 명령어 도움말 출력 (`TerminalExecutor.shell_help()`)
- 쉘 실행 결과를 `conversation_history`에 자동 저장 (플랫폼별 형식 준수)
- `gemini`의 분리된 `/shell` · `/shell!` 블록을 Claude/GenAI와 동일한 통합 구조로 개선

---

## 관련 문서

- `FSD_v1.0.073_history-remove-command.md`
- `FSD_v1.0.074_unified-print-menu.md`
- `FSD_v1.0.075_shell-command-improvement.md`
