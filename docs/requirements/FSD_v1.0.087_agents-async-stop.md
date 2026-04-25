# FSD v1.0.087 — 비동기 `/agents stop` (루프 중 입력 수신)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.087 |
| 작성일 | 2026-04-18 |
| 상태 | 📝 사전 분석 (구현 대기) |
| 선행 문서 | FSD v1.0.083 (`/agents` 자율 에이전트 루프) |
| 대상 파일 | `src/agent_runner.py`, 각 엔트리 포인트 |
| 관련 이슈 | FSD v1.0.083 §10 이슈 #2: "루프 실행 중 메인 while True 가 블로킹이므로 비동기 중단은 Ctrl+C 에 의존" |

---

## 1. 개요

### 1.1 목적

현재 에이전트 루프가 실행 중일 때 사용자가 `/agents stop` 을 입력할 수 없다. 메인 `while True` 루프의 입력이 `AgentRunner.run()` 에서 블로킹되기 때문이다. 유일한 중단 수단은 `Ctrl+C` (KeyboardInterrupt) 인데, 이는:

- Windows 에서 `Ctrl+C` 가 Python `input()` 을 통과하지 않는 경우가 있음 (특히 멀티스레드 환경)
- 사용자 UX 로서 직관적이지 않음 — `Ctrl+C` 는 프로그램 전체 종료로 오해할 수 있음
- `Ctrl+C` 시점이 API 호출 중이면 `requests` 연결이 불안정하게 끊어짐

본 FSD 는 에이전트 루프 실행 중에도 사용자 입력을 비동기적으로 수신하여, **`stop` 또는 `s` 입력으로 루프를 안전하게 중단**할 수 있는 메커니즘을 도입한다.

### 1.2 범위

| 항목 | 포함 여부 |
|---|---|
| 루프 실행 중 비동기 `stop` 입력 수신 | ✅ |
| 루프 실행 중 비동기 `feedback` 입력 수신 | ✅ (선택) |
| `Ctrl+C` 핸들링 개선 | ✅ |
| 플랫폼 호환성 (Windows / Linux / macOS) | ✅ |
| GUI 기반 중단 버튼 | ❌ |

---

## 2. 현황 분석

### 2.1 현재 루프 구조 (동기 블로킹)

```
메인 while True                 AgentRunner.run()
     │                               │
     ├─ user_input = get_input()     │
     │   (블로킹)                    │
     │                               │
     ├─ /agents 분기 ──┐             │
     │                 │             │
     │                 └──────────→ run(goal)
     │                               │
     │             (run 내부 for 루프 │
     │              blocking:        │
     │              chat(), input()) │
     │                               │
     │                 ┌──────────── return session
     │                 │
     ├─ last_response  │
     └─ 다음 입력 대기
```

> `run()` 이 반환되기 전까지 메인 루프의 `get_input()` 은 호출되지 않으므로 `/agents stop` 입력을 받을 수 없다.

### 2.2 `run()` 내부의 차단점 (blocking points)

| 차단점 | 코드 위치 | 소요 시간 |
|---|---|---|
| `self._call_model(session, prompt)` | agent_runner.py:170 | 수 초 ~ 수십 초 (API 응답 대기) |
| `self._ask_continue()` → `input()` | agent_runner.py:511 | 사용자 입력 대기 (무제한) |
| `self.code_executor.execute()` | agent_runner.py:405 | 최대 30초 (AGENT_CODE_TIMEOUT) |
| `self.terminal_executor.execute()` | agent_runner.py:444 | 가변 (명령 실행 시간) |

---

## 3. 문제점 사전 분석

### 3.1 🔴 [P1] 비동기 입력 수신 방식 선택

**문제:**
에이전트 루프가 블로킹 호출(API 응답 대기, 코드 실행 등) 중일 때 별도 스레드에서 사용자 입력을 수신해야 한다.

**해결 방안 비교:**

| 방안 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. `threading.Thread` + `input()` 리스너** | 별도 스레드에서 `input()` 으로 대기, Queue 에 입력을 넣음. 메인 루프에서 Queue 폴링 | 표준 라이브러리만 사용, 구현 단순 | `input()` 이 스레드에서 동작하지 않는 환경 존재 (일부 Windows 터미널). `input()` 은 readline 과 경합 가능 |
| **B. `msvcrt.kbhit()` (Windows) / `select.select()` (Unix)** | 키 입력 폴링 (non-blocking). 매 iteration 의 특정 시점에서 입력 확인 | 스레드 불필요, 안정적 | 플랫폼별 분기 필요. API 호출 중에는 폴링 불가 (blocking). char 단위 입력 처리 필요 |
| **C. `signal.SIGINT` 핸들러 강화** | `Ctrl+C` 시그널을 커스텀 핸들러로 잡아서 "stop 확인" 프롬프트 표시 | 추가 스레드 불필요, OS 네이티브 | `Ctrl+C` 만 지원 (키보드 단독 입력 안 됨). Windows 에서 `signal.SIGINT` 는 메인 스레드에서만 처리 가능 |
| **D. `concurrent.futures.ThreadPoolExecutor` + Event** | API 호출 자체를 별도 스레드에서 실행하고, 메인 스레드는 입력 대기 + Event 모니터링 | 메인 스레드가 입력 담당이므로 readline/TUI 호환성 유지 | 기존 코드 구조 대규모 변경 필요. `assistant.chat()` 이 스레드 안전한지 검증 필요 |
| **E. Non-blocking stdin + `select`** | Unix: `select.select([sys.stdin], [], [], 0)` 로 stdin 폴링. Windows: `msvcrt.kbhit()` + `msvcrt.getch()` | 성숙한 패턴, 게임 루프에서 자주 사용 | API 호출 중(blocking) 에는 폴링 불가 → 별도 스레드 조합 필요 |

**권장: 방안 D (메인-스레드 입력 + 워커-스레드 모델 호출) 또는 방안 A (리스너 스레드)**

---

### 3.2 🔴 [P2] 스레드 안전성 — `assistant.chat()`

**문제:**
방안 A/D 모두 `assistant.chat()` 이 메인 스레드가 아닌 곳에서 호출되거나, 별도 스레드가 메인 스레드의 상태를 변경할 수 있다.

`_call_model()` 은 `assistant.conversation_history` 를 임시 교체/원복한다:

```python
def _call_model(self, session, user_prompt):
    saved_main = self.assistant.conversation_history  # 원본 저장
    self.assistant.conversation_history = ...          # 교체
    try:
        response = self.assistant.chat(...)
    finally:
        self.assistant.conversation_history = saved_main  # 원복
```

만약 `input()` 리스너 스레드에서 stop 플래그를 설정하고 메인 스레드가 이를 감지하여 루프를 탈출하면, **`finally` 블록이 정상 실행되므로** 히스토리 원복은 보장된다. 하지만:

- `chat()` 호출 중에 stop 신호가 와도 **API 응답이 완료될 때까지 블로킹**됨 → 즉시 중단은 불가
- 스트리밍 모드에서는 `for event in client.events():` 루프가 블로킹 → 스트림 abort 메커니즘 필요

**해결 방안:**

| 방안 | 설명 |
|---|---|
| **A. "다음 checkpoint 에서 중단"** | stop 플래그를 설정하되, 실제 중단은 현재 진행 중인 모델 호출 / 코드 실행이 완료된 후 다음 checkpoint (iteration 경계) 에서 수행 |
| **B. HTTP 연결 강제 종료** | `requests.Session.close()` 또는 `response.close()` 를 호출하여 스트리밍 중인 응답을 강제 종료 |

**권장: 방안 A** — 가장 안전하며, 히스토리 정합성을 보장한다. "즉시 중단" 이 아닌 "다음 절에서 중단" UX 를 채택.

---

### 3.3 🟡 [P3] Windows 환경에서의 `input()` 스레드 동작

**문제:**
Python `input()` 은 Windows 의 일부 터미널 (특히 Git Bash, Windows Terminal 의 특정 모드) 에서 **데몬 스레드** 내 호출 시 정상 동작하지 않을 수 있다. 또한 메인 스레드에서 `readline` 기반 자동 완성 (`CLIInputHandler`) 을 사용 중이면, 별도 스레드의 `input()` 이 readline 과 충돌할 수 있다.

**해결 방안:**

| 방안 | 설명 |
|---|---|
| **A. 리스너 스레드에서 `msvcrt.getch()` 사용** | Windows 전용 non-blocking char 읽기. `s` + Enter 감지. readline 과 독립적 |
| **B. 리스너 스레드에서 raw `sys.stdin.readline()` 사용** | `input()` 대신 저수준 읽기. readline 과 충돌 회피 가능성 높음 |
| **C. 상태 표시줄에 "Press 'q' to stop" + `msvcrt.kbhit()` 폴링** | 매 iteration 중간중간 키 입력 체크. Enter 불필요 |

**권장: 방안 C (Windows) + `select.select()` (Unix)** 의 조합. 단, 가장 단순한 구현은 방안 A.

---

### 3.4 🟡 [P4] 스트리밍 출력 중 사용자 입력 시 화면 깨짐

**문제:**
에이전트가 API 스트리밍 응답을 `print(..., end="", flush=True)` 로 출력하는 도중에 사용자가 키를 입력하면, 출력과 입력이 서로 섞여 터미널 화면이 깨질 수 있다.

**해결 방안:**

| 방안 | 설명 |
|---|---|
| **A. 입력 에코 비활성화** | 리스너 스레드 동작 중 터미널 echo 를 끔 (`termios` / `msvcrt`). stop 키 입력이 화면에 표시되지 않음 |
| **B. 별도 줄에 상태 표시** | 스트리밍 출력 완료 후 분리된 라인에 "Press Ctrl+C or type 's' to stop" 안내 |
| **C. ANSI 커서 제어** | 화면 하단에 고정 상태 줄을 유지 (TUI 라이브러리 사용) |

**권장: 방안 B** — 가장 단순하며, 현재 UX 패턴(iteration 경계에서 프롬프트) 과 호환됨.

---

### 3.5 🟡 [P5] `_ask_continue()` 와의 관계

**문제:**
현재 매 iteration 끝에 `_ask_continue()` 가 `input()` 으로 `[c]/[f]/[s]` 를 받는다. 비동기 stop 을 도입하면:

1. **iteration 경계** 에서는 기존 `_ask_continue()` 가 여전히 작동 (동기 입력)
2. **iteration 중간** (API 호출 / 코드 실행 중) 에서는 비동기 리스너가 `stop` 을 감지

두 입력 채널이 공존하면 혼란이 생길 수 있다.

**해결 방안:**

| 방안 | 설명 |
|---|---|
| **A. _ask_continue() 유지 + 비동기 stop 리스너 추가** | iteration 경계에서는 동기 프롬프트, 중간에서는 비동기 감지. 리스너는 _ask_continue() 중에는 비활성화. |
| **B. _ask_continue() 를 비동기 방식으로 대체** | 타임아웃 기반 입력 (`select` + timeout). 일정 시간 입력이 없으면 자동 continue |

**권장: 방안 A** — 기존 UX 를 유지하면서 비동기 stop 만 추가. 복잡도 최소화.

---

### 3.6 🟢 [P6] Ctrl+C 핸들링 개선

**현재 동작:**
```python
except KeyboardInterrupt:
    session.stop_reason = AgentStopReason.USER_STOP
    print("\n\n⚠️  사용자 중단 (Ctrl+C)")
```

**개선 사항:**
- `Ctrl+C` 는 여전히 유효한 비상 정지 수단으로 유지
- 단, API 호출 중 `Ctrl+C` 가 `requests` 에서 `ConnectionError` 를 유발할 수 있으므로, `_call_model()` 의 `except` 에서 이를 `KeyboardInterrupt` 로 재발생시키거나 안전하게 처리
- 비동기 stop 이 도입되면 `Ctrl+C` 사용 빈도가 줄어들 것이므로, `Ctrl+C` 발생 시 "비동기 stop 사용을 권장합니다" 안내 표시

---

### 3.7 🟢 [P7] 비동기 feedback (선택)

비동기 stop 메커니즘이 확립되면, 동일한 채널로 피드백도 수신할 수 있다:

```
[루프 실행 중]
💡 's' = 중단, 'f' = 피드백 입력, Enter = 현재 단계 완료 대기

사용자: f
💬 피드백 입력 (멀티라인):
블록 회전이 안 돼. 수정해줘.
/end

→ 다음 iteration 프롬프트에 [USER_FEEDBACK] 주입
```

이 기능은 **방안 A (리스너 스레드)** 가 채택되어야 자연스럽게 확장 가능하다.

---

## 4. 구현 사양 (초안)

### 4.1 권장 아키텍처: 리스너 스레드 + 이벤트 플래그

```python
import threading
import queue

class AgentInputListener:
    """에이전트 루프 실행 중 비동기 입력 리스너"""

    def __init__(self):
        self._stop_event = threading.Event()
        self._feedback_queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._active = False

    def start(self):
        """리스너 스레드 시작"""
        self._stop_event.clear()
        self._active = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="agent-input-listener"
        )
        self._thread.start()

    def stop(self):
        """리스너 정지"""
        self._active = False
        # 주의: input() 이 blocking 중이면 스레드가 즉시 종료되지 않음
        # daemon=True 이므로 메인 스레드 종료 시 함께 종료됨

    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def get_feedback(self) -> Optional[str]:
        try:
            return self._feedback_queue.get_nowait()
        except queue.Empty:
            return None

    def _listen_loop(self):
        """입력 리스너 루프 (daemon 스레드)"""
        while self._active:
            try:
                if _is_windows():
                    self._poll_windows()
                else:
                    self._poll_unix()
            except Exception:
                break

    def _poll_windows(self):
        import msvcrt
        import time
        while self._active:
            if msvcrt.kbhit():
                ch = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                if ch == 's':
                    self._stop_event.set()
                    return
                elif ch == 'q':
                    self._stop_event.set()
                    return
            time.sleep(0.1)

    def _poll_unix(self):
        import sys, select, time
        while self._active:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                line = sys.stdin.readline().strip().lower()
                if line in ('s', 'stop', 'q', 'quit'):
                    self._stop_event.set()
                    return
```

### 4.2 AgentRunner 통합

```python
class AgentRunner:
    def __init__(self, ...):
        ...
        self._input_listener = AgentInputListener()

    def run(self, goal, ...):
        ...
        self._input_listener.start()
        try:
            for i in range(start, self.max_iterations + 1):
                # ── 체크포인트 1: iteration 시작 ──
                if self._input_listener.is_stop_requested():
                    session.stop_reason = AgentStopReason.USER_STOP
                    print("\n⚠️  사용자 중단 (비동기 stop)")
                    break

                response = self._call_model(session, prompt)

                # ── 체크포인트 2: 모델 호출 후 ──
                if self._input_listener.is_stop_requested():
                    session.stop_reason = AgentStopReason.USER_STOP
                    break

                actions = self._execute_actions(session, act)

                # ── 체크포인트 3: 액션 실행 후 ──
                if self._input_listener.is_stop_requested():
                    session.stop_reason = AgentStopReason.USER_STOP
                    break

                # _ask_continue() — 여기서는 리스너 일시 정지
                self._input_listener.stop()
                choice, fb = self._ask_continue()
                self._input_listener.start()
                ...
        finally:
            self._input_listener.stop()
```

### 4.3 UX 안내 메시지

에이전트 시작 시:
```
🤖 에이전트 시작 — 목표:
  python으로 테트리스 작성해줘

💡 루프 중 's' 키로 안전하게 중단할 수 있습니다.
```

스트리밍 출력 완료 후 (각 블록 사이):
```
[Press 's' to stop]
```

---

## 5. 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-087-01 | 에이전트 실행 중 's' 키 입력 (Windows) | 현재 작업 완료 후 다음 체크포인트에서 안전 중단 |
| T-087-02 | 에이전트 실행 중 's' + Enter 입력 (Unix) | 동일 |
| T-087-03 | API 스트리밍 중 's' 입력 | 스트리밍 완료 후 iteration 경계에서 중단 |
| T-087-04 | 코드 실행 중 's' 입력 | 코드 실행 완료 후 중단 |
| T-087-05 | `_ask_continue()` 프롬프트 중에는 리스너 비활성 | 동기 입력이 정상 동작 (s = stop, c = continue) |
| T-087-06 | Ctrl+C 는 여전히 유효 | KeyboardInterrupt 로 즉시 중단 |
| T-087-07 | 리스너 시작/정지 반복 안정성 | 5회 이상 start/stop 후에도 정상 동작 |
| T-087-08 | Windows Git Bash 에서 `msvcrt.kbhit()` 동작 확인 | 정상 작동 (또는 fallback 처리) |
| T-087-09 | 리스너 스레드가 daemon 이므로 메인 종료 시 자동 정리 | 좀비 스레드 없음 |
| T-087-10 | 에이전트 미실행 중 `/agents stop` 입력 | 기존과 동일: "실행 중이 아닙니다" 안내 |

---

## 6. 파일 변경 예정 목록

| 파일 | 변경 유형 | 설명 |
|---|---|---|
| `src/agent_input_listener.py` | **신규** | `AgentInputListener` 클래스 (스레드 기반 비동기 입력) |
| `src/agent_runner.py` | 수정 | 리스너 통합, 체크포인트 삽입, `_ask_continue()` 개선 |
| 각 엔트리 포인트 | 수정 (최소) | 안내 메시지 업데이트 (선택) |
| `src/command_registry.py` | 수정 | `/agents stop` 설명 업데이트 ("루프 중 's' 키 또는 Ctrl+C") |

---

## 7. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | `msvcrt.getch()` 는 Windows 전용이며, WSL / Git Bash 에서는 동작하지 않을 수 있음 | 플랫폼 감지 후 fallback: `sys.platform == 'win32'` 이면 msvcrt, 아니면 select. Git Bash 는 Unix 경로로 처리 |
| 2 | 데몬 스레드의 `input()` 은 메인 스레드의 readline 과 충돌 가능 | msvcrt/select 기반 구현은 `input()` 을 사용하지 않으므로 충돌 없음 |
| 3 | "즉시 중단"이 아닌 "다음 체크포인트에서 중단" 이므로 사용자가 기대하는 것보다 지연될 수 있음 | 안내 메시지에 "현재 작업 완료 후 중단됩니다" 명시. 장시간 API 호출(>30초) 시에는 timeout 으로 자연 중단 |
| 4 | `_ask_continue()` 가 동기 `input()` 을 사용하므로, 리스너가 활성 상태이면 두 곳에서 stdin 을 읽으려는 경합 발생 | `_ask_continue()` 진입 전 리스너 stop, 종료 후 start. 리스너의 poll 간격을 100ms 로 짧게 유지하여 start/stop 전환 지연 최소화 |
| 5 | 일부 CI/IDE 터미널에서는 stdin 이 TTY 가 아니므로 `kbhit()` / `select()` 가 동작하지 않음 | `sys.stdin.isatty()` 확인 후 리스너 비활성화 → 기존 `Ctrl+C` 전용 모드로 fallback |
| 6 | `AgentInputListener` 의 `stop()` 호출 시 `input()` / `getch()` 가 블로킹 중이면 스레드가 즉시 종료되지 않음 | `daemon=True` 이므로 메인 프로세스 종료 시 자동 정리. `_active` 플래그 + poll 간격으로 최대 100ms 이내 반응 |
| 7 | 비동기 feedback (`f` 키) 구현 시, 멀티라인 입력은 동기 `input()` 이 필요하므로 리스너에서 직접 처리 불가 | feedback 은 여전히 `_ask_continue()` (동기) 에서만 지원. 비동기로는 stop/continue 만 지원 |

---

## 8. 대안 분석: 전체 루프 비동기화 (asyncio)

향후 고려할 수 있는 근본적 대안으로, 에이전트 루프 전체를 `asyncio` 로 전환하는 방법이 있다:

```python
async def run(self, goal, ...):
    async for line in self._read_stdin():
        if line.strip() == 'stop':
            break
    ...
```

**장점:**
- 진정한 비동기 I/O, 스레드 없음
- `aiohttp` 로 API 호출도 비동기화 가능

**단점:**
- 기존 동기 코드 (`requests`, `input()`, `CodeExecutor.execute()`) 를 전면 교체해야 함
- 각 Provider 의 `chat()` 메서드를 async 로 변환해야 함 — **변경 범위 극대**
- 1단계로는 과잉 설계

**결론:** 1단계에서는 스레드 기반 리스너(방안 A) 를 채택하고, asyncio 전환은 장기 로드맵으로 관리.

---

## 9. 승인

- [ ] 사전 분석 검토 (2026-04-18)
- [ ] 비동기 입력 방안 확정 (방안 A/B/C/D/E)
- [ ] 플랫폼 호환성 검증 (Windows/Linux/macOS)
- [ ] 구현
- [ ] 테스트
- [ ] 문서 반영
