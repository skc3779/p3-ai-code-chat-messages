# RELEASE v1.0.100 — 에이전트 Bypass Approvals (사용자 개입 없는 자율 실행 모드)

| 항목 | 내용 |
|---|---|
| 릴리즈 버전 | v1.0.100 |
| 릴리즈 일자 | 2026-04-20 |
| 브랜치 | release_v1.0.090 |
| 요구 문서 | FSD v1.0.100 (`docs/specs/requirements/FSD_v1.0.100_agents-bypass-approvals.md`) |

---

## 변경 요약

에이전트 루프에 **Bypass Approvals 모드**를 추가했다. 매 iteration 종료 시 발생하던 `[c]/[f]/[s]` 사용자 프롬프트를 건너뛰고 `AGENT_MAX_ITERATIONS` 까지 자율 실행한다. 5종의 안전 장치(시간 예산 / 정체 탐지 / 루프 탐지 / 위험 액션 한도 / 비동기 stop)가 과잉 실행을 방지한다.

---

## 변경 파일

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| `src/agent_runner.py` | 수정 | `AgentSession` 필드 3개, `AgentStopReason` enum 4개, `_BypassAbort` 내부 예외, `run()` `bypass_approvals` 파라미터, `_enter_bypass_mode()` / `_check_bypass_safety()` / `_check_stagnation()` / `_check_loop()` 신규, `_ask_continue()` `[b]` 선택지, `_run_shell_lines()` S5 카운터, `_print_header()` bypass UI |
| `src/agents_command.py` | 수정 | `_extract_bypass_flag()` 신규, `handle_agents_command()` bypass 전파, list/stop 경고 |
| `src/command_registry.py` | 수정 | `/agents` 도움말에 `-ba/--bypassApprovals` 추가 |
| `tests/test_bypass_approvals.py` | 신규 | T-100-01 ~ T-100-13 (22 케이스) |

---

## 핵심 변경 내용

### 진입 경로 2종

| 방법 | 예시 | 설명 |
|---|---|---|
| 시작 시점 | `/agents -ba <목표>` | 첫 iteration 부터 자율 진행 |
| 루프 중간 | `[b]ypass approvals` 선택 | 이후 iteration 부터 자율 진행 |

**플래그 형식**: `-ba`, `--bypassApprovals`, `--bypass-approvals` (대소문자 무관)

### `AgentSession` 신규 필드

```python
bypass_approvals: bool = False
bypass_started_at: Optional[float] = None   # time.monotonic()
bypass_dangerous_count: int = 0
```

### `AgentStopReason` 신규 enum

```python
BYPASS_TIMEOUT = "bypass_timeout"
BYPASS_STAGNATION = "bypass_stagnation"
BYPASS_LOOP_DETECTED = "bypass_loop"
BYPASS_DANGEROUS_LIMIT = "bypass_danger_limit"
```

### 안전 장치 5종

| # | 이름 | 환경변수 | 기본값 | 트리거 조건 |
|---|---|---|---|---|
| S1 | 하드 상한 | `AGENT_MAX_ITERATIONS` | 10 | 기존 — 변경 없음 |
| S2 | 시간 예산 | `AGENT_BYPASS_TIMEOUT` | 1800초 (30분) | 경과 시간 초과 |
| S3 | 정체 탐지 | `AGENT_BYPASS_STAGNATION_N` | 3 | 연속 N회 성공 액션 0건 |
| S4 | 루프 탐지 | `AGENT_BYPASS_LOOP_N` | 3 | 최근 K회 ACT 해시 동일 |
| S5 | 위험 한도 | `AGENT_BYPASS_MAX_DANGEROUS` | 5 | 위험 shell 누적 초과 시 해당 명령 실행 전 중단 |
| S6 | 비동기 stop | — | — | 기존 's' 키 / Ctrl+C 그대로 작동 |

### Resume 안전 정책 (FR-100-11)

Resume 시 `bypass_approvals`, `bypass_started_at`, `bypass_dangerous_count` 는 항상 초기화된다. 이전 세션에 bypass 상태가 저장되어 있더라도 `/agents -ba resume` 으로 명시적 재지정이 필요하다.

### 선택 사항 구현 포함

- **`AGENT_BYPASS_DEFAULT`** 환경변수 지원 (FR-100-13): `true` 설정 시 `-ba` 없이도 bypass
- **Bypass 상태 UI** (4.1): iteration 헤더에 `[BYPASS · elapsed MM:SS]` 표시
- **위험 액션 표시**: `⚡ BYPASS: 위험 명령 자동 승인 (N/MAX)`

---

## 테스트 결과

```
tests/test_bypass_approvals.py  22 passed in 0.34s
```

| 테스트 ID | 시나리오 | 결과 |
|---|---|---|
| T-100-01 | `_ask_continue()` 에 `b` → `('b', None)` | ✅ |
| T-100-02 | `_enter_bypass_mode()` 후 세션 플래그 3종 | ✅ |
| T-100-03 | bypass 모드에서 `_ask_continue` 미호출 | ✅ |
| T-100-04 | `-ba 테스트 목표` 파싱 | ✅ |
| T-100-05 | `--bypassApprovals 리팩토링` 파싱 | ✅ |
| T-100-06 | 시간 예산 초과 → `BYPASS_TIMEOUT` | ✅ |
| T-100-07 | 3회 연속 무진행 → `BYPASS_STAGNATION` | ✅ |
| T-100-08 | 3회 동일 ACT → `BYPASS_LOOP_DETECTED` | ✅ |
| T-100-09 | 위험 한도 초과 → `BYPASS_DANGEROUS_LIMIT` (명령 미실행) | ✅ |
| T-100-10 | Resume 시 bypass 초기화 | ✅ |
| T-100-11 | bypass 중 async stop → `USER_STOP` | ✅ |
| T-100-12 | `/agents -ba stop` → 경고 + 무시 | ✅ |
| T-100-13 | `MAX_ITERATIONS=2` bypass → `MAX_ITERATIONS` 종료 | ✅ |
| 부가 | 케밥 플래그 / env default / 빈 args / 브래킷 보존 | ✅ (9개) |

---

## 회귀 영향

- `_ask_continue()` 프롬프트 문자열 변경 (`[b]` 추가) — 기존 `c`/`f`/`s` 동작 유지
- bypass 비활성(기본) 상태에서 루프 흐름 변경 없음
- 세 엔트리 포인트(gemini/claude/gen-ai) 모두 `handle_agents_command` 를 통해 동일하게 적용됨
