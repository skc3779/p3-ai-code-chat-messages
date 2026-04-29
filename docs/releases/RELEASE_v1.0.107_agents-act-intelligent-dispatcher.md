# RELEASE v1.0.107 — `/agents` 시스템 프롬프트 재작성 + `[ACT]` 지능형 디스패처

| 항목 | 내용 |
|---|---|
| 릴리스 버전 | v1.0.107 |
| 작성일 | 2026-04-25 |
| 선행 문서 | FSD v1.0.107 |
| 상태 | ✅ 구현 완료 (수동 확인 대기) |

---

## 변경 요약

FSD v1.0.107 에 따라 `/agents` 에이전트 루프의 시스템 프롬프트와 액션 라우팅을
전면 개편하여, AI 모델이 `코드 실행`과 `쉘 명령 실행` 경로를 혼동하는 4가지
실패 패턴(A/B/C/D)을 자동 교정한다.

### 핵심 변경사항

| # | 변경 내용 | 파일 |
|---|---|---|
| 1 | **시스템 프롬프트 재작성** — 선택지 A/B/C 3분할, 금지 패턴 4종, 쉘 환경 요약 삽입 | `src/agent_runner.py` |
| 2 | **`AgentActionDispatcher` 신규** — 단일 진입점 라우팅, 쉘 블록 분류기, 중복 제거, 위험 명령 일원 검사 | `src/agent_action_dispatcher.py` |
| 3 | **`agent_shell_brief()` 추가** — 에이전트 프롬프트용 쉘 환경 요약 (안전 명령 9개 + 위험 목록) | `src/terminal_executor.py` |
| 4 | **`get_os_shell_hint()` 4-쉘 분기** — TerminalExecutor.get_shell_type() 기반 PS/CMD/Linux/Mac 분기 | `src/os_utils.py` |
| 5 | **`_execute_actions()` 디스패처 위임** — 기존 3-파서 독립 호출 → 디스패처 단일 경로 | `src/agent_runner.py` |
| 6 | **`_exec_single_shell_command()` 추가** — 디스패처 전용 쉘 실행 + bypass 위험 명령 통합 | `src/agent_runner.py` |

### 테스트 결과

| 모듈 | 테스트 수 | 결과 |
|---|---|---|
| `tests/test_agent_action_dispatcher.py` (신규) | 16 | ✅ OK |
| `tests/test_os_utils_and_agent_prompt.py` (갱신) | 22 | ✅ OK |
| `tests/test_agent_runner.py` | 49 | ✅ OK |
| `tests/test_terminal_executor.py` | 17 | ✅ OK |
| `tests/test_agent_session_store.py` | 10 | ✅ OK |
| `tests/test_bypass_approvals.py` | 12 | ✅ OK |
| **합계** | **126** | **✅ 전체 통과** |

### 실패 패턴 해결 현황

| 패턴 | 설명 | 해결 |
|---|---|---|
| A | 쉘 명령을 코드 블록으로 감싸기 (````powershell\n$ git status\n```) | ✅ 디스패처가 쉘 블록 분류 → `commands` → 라인별 TerminalExecutor |
| B | 코드 실행을 `$` 라인으로 표현 (`$ python -c "..."`) | ✅ 그대로 쉘 경로 유지 (현 의도대로) |
| C | 한 iteration에 두 경로 혼재 | ✅ 디스패처가 각 블록을 독립 분류 → 단일 경로 보장 |
| D | 위험 명령을 코드 블록으로 우회 | ✅ 쉘 블록의 `commands` 분해 결과도 DANGEROUS_COMMANDS 검사 통과 |

### 미완료 (수동 확인 필요)

- [ ] `/agents` 실사용 수동 확인 — 4가지 실패 패턴 재현 시 단일 경로 라우팅 + 위험 명령 승인 정상 동작

---

## 변경 파일 목록

| 파일 | 유형 | 변경 내용 |
|---|---|---|
| `src/agent_runner.py` | 수정 | `_build_system_prompt()` 재작성, `_execute_actions()` 디스패처 위임, `_exec_single_shell_command()` 추가, `AgentActionDispatcher` import |
| `src/agent_action_dispatcher.py` | 신규 | 의도 분류 + 단일 경로 라우팅 + 위험 명령 일원 검사 |
| `src/terminal_executor.py` | 수정 | `agent_shell_brief()` 정적 메서드 추가 |
| `src/os_utils.py` | 수정 | `get_os_shell_hint()` — TerminalExecutor 기반 4-쉘 분기 |
| `tests/test_agent_action_dispatcher.py` | 신규 | T-107-07 ~ T-107-23 (16건) |
| `tests/test_os_utils_and_agent_prompt.py` | 갱신 | T-107-01 ~ T-107-06, T-107-29 ~ T-107-32 추가 (22건) |
| `docs/specs/requirements/FSD_v1.0.107_agents-act-intelligent-dispatcher.md` | 갱신 | § 13 승인 체크리스트 완료 표시 |

---

## 호환성

- `CodeExecutor.SUPPORTED_LANGUAGES` 변경 없음 — `/run` 명령 호환 보장
- `AgentSession` / `IterationRecord` / `ActionResult` 직렬화 호환성 유지
- `[REASON]/[ACT]/[OBSERVE]` 정규식 불변 — Vertex AI / Claude / GenAI 응답 호환
- `get_os_shell_hint()` 시그니처 불변 — FSD v1.0.088 / v1.0.104 호출자 무수정
- Bypass Approvals (v1.0.100), Bypass Overwrite (v1.0.103), max_iterations (v1.0.101) 동작 불변
