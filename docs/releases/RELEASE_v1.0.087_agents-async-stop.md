# RELEASE v1.0.087 — 비동기 `/agents stop` (루프 중 입력 수신)

| 항목 | 내용 |
|---|---|
| 릴리스 버전 | v1.0.087 |
| 릴리스 일자 | 2026-04-18 |
| 선행 문서 | [FSD v1.0.087](../specs/requirements/FSD_v1.0.087_agents-async-stop.md) |
| 선행 릴리스 | v1.0.083 (자율 에이전트 루프) |
| 상태 | ✅ 구현 완료 · 테스트 통과 |

---

## 1. 개요

에이전트 루프 실행 중에도 사용자가 별도 **`s` 키 입력** 으로 루프를 안전하게
중단할 수 있는 비동기 stop 메커니즘을 도입했다. 기존에는 `Ctrl+C`(KeyboardInterrupt)
가 유일한 중단 수단이었으나, Windows 환경에서 `input()` 을 통과하지 못하거나
API 호출 중 `requests` 연결이 불안정하게 끊기는 문제가 있었다.

FSD v1.0.087 §3.1 의 **방안 A/E 조합**(리스너 스레드 + 플랫폼별 non-blocking
stdin 폴링)을 채택하였으며, §3.2 의 **"다음 체크포인트에서 중단"** 전략으로
히스토리 정합성을 보장한다.

---

## 2. 동작 요약

```
[루프 시작]
 💡 루프 중 's' 키로 안전하게 중단할 수 있습니다 (Ctrl+C 도 여전히 유효).

┌─ AgentInputListener (daemon thread) ─┐
│ Windows: msvcrt.kbhit() 폴링 (100ms) │
│ Unix:    select.select([stdin]) 폴링 │
│ TTY 아님: 비활성화 (Ctrl+C 만 가능)  │
└──────────────────────────────────────┘
        │
        │  's' / 'q' 감지 → _stop_event.set()
        ▼
┌─ AgentRunner.run() 체크포인트 ───────┐
│ CP1: iteration 시작 전              │
│ CP2: _call_model() 후               │
│ CP3: _execute_actions() 후          │
│                                     │
│ _ask_continue()/위험 승인 진입 시   │
│   → listener.paused() 로 일시 정지  │
└─────────────────────────────────────┘
```

### 체크포인트 동작

| 시점 | stop 감지 시 |
|---|---|
| iteration 시작 전 (CP1) | 즉시 종료, 현 iteration 미수행 |
| 모델 호출 후 (CP2) | 액션 미실행 상태에서 종료 |
| 액션 실행 후 (CP3) | 현재 iteration 기록은 유지한 채 종료 |
| `_ask_continue()` 진입 | 리스너 일시 정지 → 기존 동기 `[c]/[f]/[s]` 동작 |

---

## 3. 변경 파일

| 파일 | 변경 유형 | 설명 |
|---|---|---|
| [src/agent_input_listener.py](../../src/agent_input_listener.py) | **신규** | `AgentInputListener` + `_PauseContext` — 플랫폼별 non-blocking stdin 폴링 |
| [src/agent_runner.py](../../src/agent_runner.py) | 수정 | 리스너 수명주기 + 3개 체크포인트 + `_ask_continue`/`_approve_dangerous` 주변 `paused()` |
| [src/command_registry.py](../../src/command_registry.py) | 수정 | `/agents` 설명에 "`'s'` 키 또는 Ctrl+C" 명시 |
| [src/agents_command.py](../../src/agents_command.py) | 수정 | `/agents stop` 안내 메시지를 `'s'` 키 중심으로 재작성 |
| [tests/test_agent_input_listener.py](../../tests/test_agent_input_listener.py) | **신규** | 리스너 및 runner 통합 테스트 19건 |

---

## 4. 주요 설계 결정

### 4.1 체크포인트 방식 (즉시 중단 대신)

**선택:** FSD §3.2 **방안 A** — "다음 체크포인트에서 중단"

- API 응답 / 코드 실행이 진행 중이면 해당 작업이 완료된 후 반응
- `_call_model()` 의 `try / finally` 히스토리 원복을 항상 보장
- 사용자 UX 에서 지연은 크지 않음 — `AGENT_CODE_TIMEOUT` 이 최대 30초

HTTP 연결 강제 종료(방안 B) 는 1차 범위에서 제외.

### 4.2 플랫폼 구현

| OS | 구현 | 트리거 |
|---|---|---|
| Windows | `msvcrt.kbhit()` + `msvcrt.getch()` | `s` 또는 `q` char (Enter 불필요) |
| Unix / macOS | `select.select([sys.stdin], ..., 0.1)` + `readline()` | `s` / `stop` / `q` / `quit` + Enter |
| TTY 아님 (CI/pipe) | `sys.stdin.isatty() == False` → 리스너 비활성화 | Ctrl+C 만 지원 |

### 4.3 입력 경합 방지

`_ask_continue()` / `_approve_dangerous()` 가 `input()` 으로 stdin 을 읽을 때
리스너와 경합하지 않도록 `listener.paused()` 컨텍스트 매니저로 일시 정지 →
`with` 탈출 시 자동 재개.

### 4.4 데몬 스레드 수명

`AgentInputListener` 스레드는 `daemon=True` 로 생성되므로 메인 프로세스 종료
시 자동 정리된다. `stop()` 호출 시 `_active` 플래그만 낮추며, 블로킹된
`msvcrt.getch()` / `readline()` 을 깨우지는 않는다 — 다음 폴링 주기(기본
100ms) 내에 자연 종료된다.

---

## 5. 테스트 결과

**신규 추가:** 19개 (모두 통과)

| # | 항목 | 분류 |
|---|---|---|
| T-087-A01 | 초기 상태 — stop 플래그 False | 리스너 단독 |
| T-087-A02 | `clear_stop()` 동작 | 리스너 단독 |
| T-087-A03 | non-TTY 환경에서 `enabled=False` | 리스너 단독 |
| T-087-A04 | 비활성 시 `start()` 가 스레드 생성 안 함 | 리스너 단독 |
| T-087-A05 | `stop()` idempotent | 리스너 단독 |
| T-087-A06 | `start/stop` 5회 반복 안정성 (≈FSD T-087-07) | 리스너 단독 |
| T-087-A07 | `paused()` 진입/탈출 시 스레드 중지/재개 | 리스너 단독 |
| T-087-A08 | 비실행 상태에서 `paused()` 안전 | 리스너 단독 |
| T-087-01 | CP1 — iteration 시작 전 stop 감지 | Runner 통합 |
| T-087-03 | CP2 — 모델 호출 후 stop 감지 | Runner 통합 |
| T-087-04 | CP3 — 액션 실행 후 stop 감지 | Runner 통합 |
| T-087-05 | `_ask_continue()` 진입 시 `paused()` 호출 | Runner 통합 |
| T-087-06 | `Ctrl+C` 는 여전히 USER_STOP 으로 처리 | Runner 통합 |
| T-087-B | `finally` 에서 `listener.stop()` 보장 | Runner 통합 |
| T-087-B2 | 진입 시 `start()` + `clear_stop()` 호출 | Runner 통합 |
| T-087-B3 | `_check_async_stop()` 세션 반영 | Runner 통합 |
| T-087-B4 | stop 요청 없으면 세션 변경 없음 | Runner 통합 |
| T-087-10 | `/agents stop` 안내 메시지에 `'s'` 포함 | 명령 |
| T-087-11 | CommandRegistry `/agents` 설명에 `'s'` 포함 | 명령 |

**회귀 검증:** 기존 테스트 스위트 통과 상태 유지
- `tests/test_agent_runner.py` · 46개 통과
- `tests/test_agent_session_store.py` · 28개 통과
- `tests/test_integration.py` · 1개 통과

```
$ python -m pytest tests/test_agent_input_listener.py \
                   tests/test_agent_runner.py \
                   tests/test_agent_session_store.py \
                   tests/test_integration.py
============================= 94 passed in ~2s =============================
```

> `tests/test_api_logger.py` 의 10건 실패는 본 릴리스 이전부터 존재하는
> 무관한 실패로, 변경 전/후 동일하게 재현된다.

---

## 6. 사용자 관점 변경점

### 6.1 기존 UX (v1.0.086)

```
▶ [c]ontinue / [f]eedback / [s]top ? (c): _
```
iteration 경계에서만 `s` 입력 가능. 루프 중 중단은 `Ctrl+C` 만 허용.

### 6.2 신규 UX (v1.0.087)

```
🤖 에이전트 시작 — 목표:
  python으로 테트리스 작성해줘

💡 루프 중 's' 키로 안전하게 중단할 수 있습니다 (Ctrl+C 도 여전히 유효).

━━━ Iteration 1/10 ━━━
...
```
루프 실행 중 언제든 `s` 키로 중단 가능. 현재 진행 중인 API 호출 / 코드 실행이
끝난 직후 체크포인트에서 안전하게 종료된다.

### 6.3 `/agents stop` 명령

에이전트 미실행 상태에서는 다음과 같이 안내된다:
```
💡 에이전트는 현재 실행 중이 아닙니다. 루프 도중에는 's' 키(또는 Ctrl+C)로
   안전하게 중단할 수 있습니다.
```

---

## 7. 제약 및 Future Work

| # | 제약 | 회피/대응 |
|---|---|---|
| 1 | API 응답 스트리밍 중에는 즉시 중단 안 됨 (다음 CP 대기) | 장시간(>30s) 호출은 `AGENT_CODE_TIMEOUT` 에 의해 자연 종료 |
| 2 | TTY 아닌 환경(CI, 파이프)에서는 리스너 비활성 | `Ctrl+C` 경로 유지 |
| 3 | 비동기 **feedback** (`f` 키) 는 미지원 — 멀티라인 입력이 필요해 `_ask_continue()` 경로에서만 제공 | 향후 TUI 기반 상태바로 확장 가능 (선택) |
| 4 | Git Bash / MSYS 일부 구성은 `msvcrt` 를 노출하지 않을 수 있음 | 예외 시 리스너 조용히 종료, `Ctrl+C` 경로로 fallback |

향후 고려 (FSD §8): 전체 루프의 `asyncio` 전환은 변경 범위가 커서 1단계에서
제외. 현재 구조로 UX 요구는 충족.

---

## 8. 체크리스트

- [x] `AgentInputListener` 구현 (Windows / Unix / non-TTY 분기)
- [x] `AgentRunner.run()` 에 3개 체크포인트 삽입
- [x] `_ask_continue()` / `_approve_dangerous()` 주변 `paused()` 처리
- [x] `Ctrl+C` 호환성 유지
- [x] `/agents stop` 안내 메시지 갱신
- [x] CommandRegistry `/agents` 설명 갱신
- [x] 단위/통합 테스트 19건 추가 · 전부 통과
- [x] 회귀 테스트 확인 — `test_agent_runner` / `test_agent_session_store` / `test_integration`
- [x] FSD §5 테스트 시나리오 매핑 완료

---

## 9. 관련 문서

- [FSD v1.0.087](../specs/requirements/FSD_v1.0.087_agents-async-stop.md) — 원 요구 사항 및 사전 분석
- [src/agent_input_listener.py](../../src/agent_input_listener.py) — 구현체
- [src/agent_runner.py](../../src/agent_runner.py) — 통합 지점
- [tests/test_agent_input_listener.py](../../tests/test_agent_input_listener.py) — 검증
