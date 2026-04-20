# FSD v1.0.100 — 에이전트 Bypass Approvals (사용자 개입 없는 자율 실행 모드)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.100 |
| 작성일 | 2026-04-20 |
| 상태 | 📝 사전 분석 (구현 대기) |
| 선행 문서 | FSD v1.0.083 (`/agents` 자율 에이전트 루프), FSD v1.0.085 (멀티 Provider 분기), FSD v1.0.087 (비동기 stop), FSD v1.0.088 (OS 쉘 힌트) |
| 대상 파일 | [src/agent_runner.py](src/agent_runner.py), [src/agents_command.py](src/agents_command.py), [src/command_registry.py](src/command_registry.py) |
| 신규 파일 | 없음 (기존 파일 수정만) |

---

## 1. 개요

### 1.1 목적

현재 에이전트 루프는 매 iteration 종료 시점마다 `_ask_continue()` 를 통해 사용자에게 [c]ontinue / [f]eedback / [s]top 선택을 요구한다. 이는 사용자가 진행 상황을 관찰하면서 개입할 수 있다는 장점이 있으나, 다음과 같은 경우에는 오히려 생산성을 떨어뜨린다.

- 장시간 실행이 예상되는 대규모 목표 (예: 멀티 파일 리팩토링, 테스트 스위트 작성)
- 야간/백그라운드 실행 (사용자 부재)
- 이미 검증된 워크플로우를 자동화하여 반복 수행
- 파이프라인/CI 환경에서의 배치 실행

본 FSD 는 **사용자 개입 없이 `AGENT_MAX_ITERATIONS` 까지 자율 실행 후 종료**하는 **Bypass Approvals 모드**를 명세한다. 두 가지 진입 경로를 제공한다.

1. **루프 중간 진입**: `_ask_continue()` 프롬프트에서 `[b]ypass` 선택 → 이후 iteration 부터 자동 진행
2. **시작 시점 진입**: `/agents -ba <goal>` 또는 `/agents --bypassApprovals <goal>` → 첫 iteration 부터 자동 진행

또한 자율 실행의 위험성을 고려하여 **강제 종료 안전 장치**를 함께 설계한다.

### 1.2 범위

| 항목 | 포함 여부 |
|---|---|
| `_ask_continue()` 에 `[b]ypass` 선택지 추가 | ✅ |
| `AgentSession.bypass_approvals` 플래그 신규 추가 | ✅ |
| `/agents -ba / --bypassApprovals` 플래그 파싱 | ✅ |
| 강제 종료 안전 장치 (시간/스태그네이션/반복 탐지) | ✅ |
| 비동기 stop ('s' 키 / Ctrl+C) 여전히 유효 | ✅ |
| 위험 shell 명령 / 파일 변경 auto-approve 통합 | ✅ |
| Resume 세션에서의 bypass 플래그 초기화 정책 | ✅ |
| 토큰 예산 관리 (Token budget) | ⚠️ Phase 2 (별도 FSD) |
| 에이전트 출력 자동 검증 (linter/tester) | ❌ 범위 외 |

---

## 2. 현황 분석

### 2.1 `_ask_continue()` 현재 구현

[src/agent_runner.py:602-618](src/agent_runner.py#L602-L618)

```python
def _ask_continue(self) -> Tuple[str, Optional[str]]:
    try:
        ans = input("\n▶ [c]ontinue / [f]eedback / [s]top ? (c): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return ('s', None)
    if not ans:
        ans = 'c'
    if ans == 'f':
        print("💬 피드백 입력 (멀티라인, 종료: /end 또는 Esc+Enter):")
        try:
            feedback = self.cli_handler.get_multiline()
        except Exception:
            feedback = ""
        return ('f', feedback or None)
    if ans == 's':
        return ('s', None)
    return ('c', None)
```

### 2.2 현재 루프 구조 (FSD v1.0.083 기반)

[src/agent_runner.py:197-282](src/agent_runner.py#L197-L282)

```
for i in range(start_iteration, max_iterations + 1):
    ① 체크포인트 1 — 비동기 stop 검사
    ② 모델 호출 → Reason/Act/Observe 파싱
    ③ 체크포인트 2 — 비동기 stop 검사
    ④ 액션 실행 (파일 저장 / 코드 실행 / 쉘 명령)
       └─ 위험 shell: _approve_dangerous() 단건 확인 (A 선택 시 세션 auto-approve)
    ⑤ Self-Correction 루프 (최대 3회)
    ⑥ session.iterations 에 기록
    ⑦ [AGENT_DONE] 종료 체크
    ⑧ 체크포인트 3 — 비동기 stop 검사
    ⑨ 히스토리 압축 (필요 시)
    ⑩ _ask_continue() — [c]/[f]/[s] 턴 사이 프롬프트  ← 여기가 Bypass 진입점
```

### 2.3 기존 Auto-Approve 자산

`AgentSession` 에는 이미 세션 범위 auto-approve 플래그 2종이 존재한다. [src/agent_runner.py:52-62](src/agent_runner.py#L52-L62)

```python
@dataclass
class AgentSession:
    ...
    auto_approve_dangerous_shell: bool = False
    auto_approve_file_mutation: bool = False
    stop_reason: Optional[AgentStopReason] = None
```

이 플래그는 `_approve_dangerous()` 프롬프트에서 사용자가 `A` (Always) 를 선택했을 때 설정된다. Bypass 모드에서는 이 두 플래그도 **자동 True** 로 설정되어야 한다.

### 2.4 `/agents` 인자 파싱 현재 구조

[src/agents_command.py:83-94](src/agents_command.py#L83-L94)

```python
# ── /agents [pattern] — 신규 실행 ──────────────────────
file_patterns: List[str] = []
if stripped:
    if stripped.startswith("["):
        try:
            end_idx = args.index("]")
            file_patterns = [p.strip() for p in args[1:end_idx].split(",") if p.strip()]
        except ValueError:
            print("❌ 닫는 대괄호 ']'가 없습니다.")
            return
    else:
        file_patterns = stripped.split()
```

현재는 **대괄호 블록** 또는 **공백 구분 패턴 리스트** 만 처리한다. 플래그(`-ba` / `--bypassApprovals`) 파싱 로직은 없다.

---

## 3. 설계

### 3.1 `AgentSession` 확장

```python
@dataclass
class AgentSession:
    goal: str
    ...
    auto_approve_dangerous_shell: bool = False
    auto_approve_file_mutation: bool = False
    # FSD v1.0.100 신규
    bypass_approvals: bool = False        # 루프 자율 진행 여부
    bypass_started_at: Optional[float] = None  # bypass 진입 시점 (time.monotonic())
    bypass_dangerous_count: int = 0       # bypass 중 실행된 위험 shell 누적
    stop_reason: Optional[AgentStopReason] = None
```

> `bypass_started_at` 은 FR-100-07 (시간 예산 안전 장치) 에 사용되며, `time.monotonic()` 을 저장한다(벽시계 시간 jitter 무관).

### 3.2 `AgentStopReason` 신규 enum 값

```python
class AgentStopReason(Enum):
    DONE = "done"
    MAX_ITERATIONS = "max_iterations"
    USER_STOP = "user_stop"
    USER_ABORT_ON_ERROR = "user_abort"
    FATAL_ERROR = "fatal_error"
    # 신규 (FSD v1.0.100)
    BYPASS_TIMEOUT = "bypass_timeout"       # 시간 예산 초과
    BYPASS_STAGNATION = "bypass_stagnation" # 진행 정체 탐지
    BYPASS_LOOP_DETECTED = "bypass_loop"    # 반복 루프 탐지
    BYPASS_DANGEROUS_LIMIT = "bypass_danger_limit"  # 위험 액션 한도 초과
```

### 3.3 `_ask_continue()` 수정: `[b]` 선택지 추가

```python
def _ask_continue(self) -> Tuple[str, Optional[str]]:
    try:
        ans = input(
            "\n▶ [c]ontinue / [f]eedback / [b]ypass approvals / [s]top ? (c): "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return ('s', None)
    if not ans:
        ans = 'c'
    if ans == 'f':
        print("💬 피드백 입력 (멀티라인, 종료: /end 또는 Esc+Enter):")
        try:
            feedback = self.cli_handler.get_multiline()
        except Exception:
            feedback = ""
        return ('f', feedback or None)
    if ans == 's':
        return ('s', None)
    if ans == 'b':
        return ('b', None)  # 호출측에서 session.bypass_approvals = True 처리
    return ('c', None)
```

### 3.4 `run()` 루프 수정: bypass 분기

```python
# for i in range(start_iteration, self.max_iterations + 1): 내부

# ⑩ 턴 사이 프롬프트 — bypass 모드에서는 스킵
if session.bypass_approvals:
    # 안전 장치 검사 (3.6 참조)
    brk = self._check_bypass_safety(session)
    if brk is not None:
        session.stop_reason = brk
        completed = True
        break
    # 바로 다음 iteration 으로 (피드백/중단 프롬프트 없음)
    continue

with self._input_listener.paused():
    choice, fb = self._ask_continue()

if choice == 's':
    session.stop_reason = AgentStopReason.USER_STOP
    completed = True
    break
if choice == 'f':
    feedback = fb
if choice == 'b':
    self._enter_bypass_mode(session)
    # 다음 iteration 부터 자율 진행
```

### 3.5 `_enter_bypass_mode()` 헬퍼

```python
def _enter_bypass_mode(self, session: AgentSession) -> None:
    """bypass 플래그 세팅 + 관련 auto-approve 통합 + 시작 시각 기록."""
    import time as _time
    session.bypass_approvals = True
    session.auto_approve_dangerous_shell = True   # 위험 shell 자동 승인
    session.auto_approve_file_mutation = True    # 파일 변경 자동 승인
    session.bypass_started_at = _time.monotonic()
    remaining = self.max_iterations - len(session.iterations)
    print("\n" + "━" * 60)
    print("🚀 BYPASS APPROVALS 활성화")
    print(f"  남은 iteration: 최대 {remaining} 회")
    print(f"  시간 예산      : {self.bypass_timeout_sec}초 "
          f"(env AGENT_BYPASS_TIMEOUT)")
    print(f"  위험 액션 한도 : {self.bypass_max_dangerous} 회 "
          f"(env AGENT_BYPASS_MAX_DANGEROUS)")
    print("  중단 방법      : 's' 키 또는 Ctrl+C")
    print("━" * 60)
```

### 3.6 강제 종료 안전 장치 (🔐 핵심 설계)

자율 실행 모드는 사용자 감독이 없으므로, 의도치 않은 장시간 실행 / 무한 루프 / 리소스 고갈을 방지해야 한다. **5 종의 안전 장치**를 제안한다.

#### S1. 하드 상한 — `AGENT_MAX_ITERATIONS` (기존 유지)

이미 FSD v1.0.083 에서 정의되어 있으며, bypass 모드에서도 동일하게 적용된다.
- 기본값 10, env 로 조정 가능

#### S2. 시간 예산 — `AGENT_BYPASS_TIMEOUT` (신규)

bypass 진입 시점부터 경과된 벽시계 시간이 임계치를 초과하면 종료.

```python
self.bypass_timeout_sec = int(os.getenv("AGENT_BYPASS_TIMEOUT", "1800"))  # 기본 30분

def _check_bypass_safety(self, session) -> Optional[AgentStopReason]:
    import time as _time
    # S2: 시간 예산
    if session.bypass_started_at is not None:
        elapsed = _time.monotonic() - session.bypass_started_at
        if elapsed > self.bypass_timeout_sec:
            print(f"\n⏱️  Bypass 시간 예산 초과 "
                  f"({elapsed:.0f}s > {self.bypass_timeout_sec}s)")
            return AgentStopReason.BYPASS_TIMEOUT
    ...
```

#### S3. 진행 정체 탐지 — Consecutive No-Progress

최근 N 개 iteration 에서 **단 한 건의 성공 액션(file/code/shell)도 없으면** 정체로 판단하고 종료.

```python
self.bypass_stagnation_window = int(os.getenv("AGENT_BYPASS_STAGNATION_N", "3"))

def _check_stagnation(self, session) -> bool:
    if len(session.iterations) < self.bypass_stagnation_window:
        return False
    recent = session.iterations[-self.bypass_stagnation_window:]
    for rec in recent:
        if any(a.success for a in rec.actions):
            return False  # 하나라도 성공 → 정체 아님
    return True  # N 회 연속 전부 실패/빈 액션
```

#### S4. 반복 루프 탐지 — Action Hash Loop

최근 K 개 iteration 의 ACT 텍스트 해시가 모두 동일하면 모델이 루프에 빠진 것으로 간주.

```python
self.bypass_loop_window = int(os.getenv("AGENT_BYPASS_LOOP_N", "3"))

def _check_loop(self, session) -> bool:
    if len(session.iterations) < self.bypass_loop_window:
        return False
    import hashlib
    recent = session.iterations[-self.bypass_loop_window:]
    hashes = {hashlib.md5(rec.act_text.encode("utf-8")).hexdigest()
              for rec in recent}
    return len(hashes) == 1  # 모든 ACT 가 동일
```

#### S5. 위험 액션 한도 — Dangerous Shell Count

bypass 중 누적된 위험 shell 실행 횟수가 임계치 초과 시 즉시 종료.

```python
self.bypass_max_dangerous = int(os.getenv("AGENT_BYPASS_MAX_DANGEROUS", "5"))

# _run_shell_lines() 에서 dangerous 실행 시 카운터 증가
if dangerous:
    if session.bypass_approvals:
        session.bypass_dangerous_count += 1
        if session.bypass_dangerous_count > self.bypass_max_dangerous:
            # 즉시 중단 (이번 명령은 실행하지 않음)
            session.stop_reason = AgentStopReason.BYPASS_DANGEROUS_LIMIT
            raise _BypassAbort("위험 액션 한도 초과")
```

> S5 는 iteration 경계가 아닌 **액션 단위**에서 발동하므로 예외 흐름이 필요하다. 내부 전용 예외 `_BypassAbort(Exception)` 로 상위 `run()` 의 `except Exception` 경로에서 포착하되, `stop_reason` 이 이미 설정되어 있으므로 `FATAL_ERROR` 로 덮어쓰지 않도록 분기한다.

#### S6. 비동기 stop — 기존 메커니즘 유지

's' 키 / Ctrl+C 는 bypass 모드에서도 그대로 작동한다. FSD v1.0.087 의 `AgentInputListener` 가 매 체크포인트에서 polling 하므로 추가 구현 불필요.

### 3.7 `/agents` 플래그 파싱

#### 3.7.1 허용 형식

| 입력 | 의미 |
|---|---|
| `/agents -ba <목표 입력>` | bypass 모드로 신규 실행 |
| `/agents --bypassApprovals <목표 입력>` | 동일 (긴 형식) |
| `/agents --bypass-approvals <목표 입력>` | 동일 (kebab-case 허용) |
| `/agents -ba [pattern1, pattern2]` | bypass + file pattern 조합 |
| `/agents -ba resume [filename]` | bypass + 세션 재개 |
| `/agents -ba list` | ❌ 무효 (list 는 실행 아님) — 경고 후 무시 |
| `/agents -ba stop` | ❌ 무효 — 경고 후 무시 |

#### 3.7.2 파싱 로직 (`agents_command.py`)

```python
BYPASS_FLAGS = {"-ba", "--bypassapprovals", "--bypass-approvals"}

def _extract_bypass_flag(args: str) -> Tuple[bool, str]:
    """args 에서 bypass 플래그를 분리해 (bypass, 남은_args) 로 반환.

    플래그는 대소문자 무관하게 토큰 단위로 매칭된다.
    패턴 리스트(`[p1, p2]`) 내부의 토큰은 건드리지 않는다.
    """
    stripped = args.strip()
    if not stripped:
        return False, ""
    # 대괄호 블록 보존
    if stripped.startswith("["):
        return False, args
    tokens = stripped.split()
    bypass = False
    remaining: List[str] = []
    for tok in tokens:
        if tok.lower() in BYPASS_FLAGS:
            bypass = True
        else:
            remaining.append(tok)
    return bypass, " ".join(remaining)


def handle_agents_command(assistant, cli_handler, streaming, args,
                         assistant_role="model"):
    ...
    # bypass 플래그 선추출
    bypass, args = _extract_bypass_flag(args)
    stripped = args.strip()
    sub = stripped.lower().split()[0] if stripped else ""

    if sub == "stop":
        if bypass:
            print("⚠️  /agents stop 에는 -ba 플래그가 적용되지 않습니다.")
        ...
    if sub == "list":
        if bypass:
            print("⚠️  /agents list 에는 -ba 플래그가 적용되지 않습니다.")
        ...
    if sub == "resume":
        ...
        runner.run(resume_session=session, bypass_approvals=bypass)
        return

    # 신규 실행
    ...
    runner.run(goal, file_patterns=file_patterns or None,
               bypass_approvals=bypass)
```

### 3.8 `AgentRunner.run()` 시그니처 확장

```python
def run(
    self,
    goal: str = "",
    file_patterns: Optional[List[str]] = None,
    resume_session: Optional["AgentSession"] = None,
    bypass_approvals: bool = False,   # 신규
) -> "AgentSession":
    ...
    if bypass_approvals:
        self._enter_bypass_mode(session)
```

> Resume 세션에서 이전에 저장된 `bypass_approvals=True` 상태는 **보안상 초기화**한다 (FSD v1.0.086 이슈#5 원칙과 일치). 사용자는 `/agents -ba resume` 으로 명시적으로 다시 부여해야 한다.

### 3.9 환경 변수 요약

| 변수 | 기본값 | 설명 |
|---|---|---|
| `AGENT_MAX_ITERATIONS` | 10 | (기존) 루프 하드 상한 |
| `AGENT_BYPASS_TIMEOUT` | 1800 (30분) | bypass 진입 후 경과 초 상한 |
| `AGENT_BYPASS_STAGNATION_N` | 3 | 연속 무진행 iteration 한도 |
| `AGENT_BYPASS_LOOP_N` | 3 | 동일 ACT 반복 탐지 창 |
| `AGENT_BYPASS_MAX_DANGEROUS` | 5 | bypass 중 위험 shell 누적 한도 |
| `AGENT_BYPASS_DEFAULT` | false | (선택) 자동 bypass on 시작 (파워 유저용) |

---

## 4. 추가 제안 (Optional Enhancements)

우선순위 순으로 정리하며, **별도 FSD 로 분리하지 않아도 이번 구현에 포함 가능한 것** / **별도 논의 필요한 것** 을 구분한다.

### 4.1 Bypass 상태 UI (권장 ★)

- 각 iteration 헤더에 `[BYPASS i/N · elapsed 03:42]` 표시 (시간 예산 남은 양을 직관화)
- 위험 액션 실행 시 `⚡ BYPASS: 위험 명령 자동 승인 (2/5)` 와 같이 누적 표시

구현 비용: 낮음. 사용자 피드백 경로가 줄어든 만큼 **가시성을 보강**하는 것이 필수.

### 4.2 `AGENT_BYPASS_DEFAULT` 환경 변수 (권장)

`AGENT_BYPASS_DEFAULT=true` 로 설정하면 `/agents` 호출 시 `-ba` 를 명시하지 않아도 기본 bypass. 반복 자동화하는 파워 유저 대상.

구현 비용: 낮음. `_extract_bypass_flag()` 결과를 OR 결합.

### 4.3 Bypass 시작 시 사전 확인 (권장 ★)

`/agents -ba` 실행 즉시 목표를 읽은 다음, **PLAN 을 먼저 출력하고 "정말 bypass 로 진행할까요? [Y/n]"** 을 한 번 묻는다.

- 사용자는 AI 가 세운 PLAN 을 보고 bypass 여부를 최종 판단 가능
- 환경 변수 `AGENT_BYPASS_CONFIRM_PLAN=false` 로 스킵 허용 (CI 환경 대비)

구현 비용: 낮음. PLAN 출력 직후 `input()` 한 번 추가.

### 4.4 Bypass 전용 로그 파일

bypass 모드는 사용자 부재 중 실행될 가능성이 높으므로, 별도 로그 파일에 모든 iteration 을 append 하는 것이 감사(audit)에 유리하다.

- 경로: `<workspace>/.agent_sessions/bypass_<timestamp>.log`
- 내용: iteration 번호, Reason/Act 요약, 액션 결과, 안전장치 트리거 여부
- 기존 `AgentSessionStore` 의 JSON 직렬화와 **별개**: JSON 은 재개용 구조 데이터, 로그는 사람이 읽는 사후 검토용

구현 비용: 중간. `AgentSessionStore` 확장.

### 4.5 단계적 Bypass Level (선택)

| Level | 턴 사이 프롬프트 | 위험 shell | 파일 변경 |
|---|---|---|---|
| L0 (default, 기존) | 매 턴 질문 | 단건 확인 | 단건 확인 |
| L1 (soft bypass) | 스킵 | **여전히 단건 확인** | 자동 승인 |
| L2 (full bypass, 본 FSD) | 스킵 | 자동 승인 | 자동 승인 |

`/agents --bypass=soft` / `/agents --bypass=full` 같은 값 형식 지원. 다만 옵션이 늘면 복잡도가 올라가므로 **1차 구현은 L2 단일 레벨**로 진행하고, 실사용 후 필요 시 도입을 권장한다.

### 4.6 Token 예산 안전 장치 (Phase 2 — 별도 FSD 권장)

- `AGENT_BYPASS_TOKEN_BUDGET=200000` 설정 시, 누적 토큰이 초과되면 종료
- 전제 조건: 세 Provider 모두 토큰 사용량 반환 API 가 일관되어야 함
- 현재 코드베이스의 `token_manager.py` 를 경유하여 집계 가능
- **복잡도 중간** — 본 FSD 에서는 시간 예산으로 간접 달성하고, 토큰 예산은 별도 FSD v1.0.101 로 분리 제안

### 4.7 `s` 키 재입력 시 Bypass 해제 (재검토 필요)

현재 설계: bypass 중 's' 는 **전체 루프 중단**.

대안: **첫 's' 입력은 bypass 해제 → 다시 대화형 모드**, **두 번째 's' 는 루프 중단**.

- 장점: 사용자가 단순히 "잠깐, 보고 싶다" 인 경우 수용 가능
- 단점: UX 복잡성 증가, 리스너 상태 기계 도입 필요

**권장**: 1차는 기존(즉시 중단) 유지 → 사용 패턴 관찰 후 v1.1 에서 도입 검토.

---

## 5. 파일 변경 예정 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [src/agent_runner.py](src/agent_runner.py) | 수정 | `AgentSession` 필드 3개 추가, `AgentStopReason` enum 4개 추가, `_ask_continue()` 에 `[b]` 선택지, `_enter_bypass_mode()` / `_check_bypass_safety()` / `_check_stagnation()` / `_check_loop()` 신규, `run()` 에 `bypass_approvals` 파라미터, `_run_shell_lines()` 에 dangerous 카운터, 루프에 bypass 분기 |
| [src/agents_command.py](src/agents_command.py) | 수정 | `_extract_bypass_flag()` 신규, `handle_agents_command()` 시그니처 유지하면서 내부에서 플래그 분리, `runner.run(..., bypass_approvals=bypass)` 전파 |
| [src/command_registry.py](src/command_registry.py) | 수정 | `/agents` 명령 도움말에 `-ba / --bypassApprovals` 추가 |
| [src/agent_session_store.py](src/agent_session_store.py) | 수정 (선택 4.4 구현 시) | bypass 전용 로그 파일 append |
| [tests/test_agent_runner.py](tests/test_agent_runner.py) | 수정 | T-100-01 ~ T-100-12 추가 |
| [docs/specs/releases/](docs/specs/releases/) | 신규 | 구현 완료 후 `RELEASE_v1.0.100.md` 작성 |

---

## 6. 요구사항 (Functional / Non-Functional)

### 6.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-100-01 | `_ask_continue()` 는 [c/f/b/s] 4선택지를 표시하고 `b` 입력 시 `('b', None)` 반환 | 필수 |
| FR-100-02 | 루프는 `b` 수신 시 `_enter_bypass_mode()` 호출 후 다음 iteration 부터 `_ask_continue()` 를 호출하지 않음 | 필수 |
| FR-100-03 | `/agents -ba <goal>` 또는 `/agents --bypassApprovals <goal>` 은 첫 iteration 부터 bypass 모드로 진입 | 필수 |
| FR-100-04 | bypass 모드에서는 `auto_approve_dangerous_shell` / `auto_approve_file_mutation` 이 자동 True 로 설정 | 필수 |
| FR-100-05 | bypass 모드에서도 `[AGENT_DONE]` 종료 토큰은 정상 작동 | 필수 |
| FR-100-06 | bypass 모드에서 비동기 stop ('s' 키 / Ctrl+C) 은 정상 작동 | 필수 |
| FR-100-07 | bypass 진입 후 경과 시간이 `AGENT_BYPASS_TIMEOUT` 초과 시 `BYPASS_TIMEOUT` 사유로 종료 | 필수 |
| FR-100-08 | 최근 `AGENT_BYPASS_STAGNATION_N` iteration 전부 성공 액션 0건 시 `BYPASS_STAGNATION` 사유로 종료 | 필수 |
| FR-100-09 | 최근 `AGENT_BYPASS_LOOP_N` iteration 의 ACT 텍스트 해시가 모두 동일 시 `BYPASS_LOOP_DETECTED` 사유로 종료 | 필수 |
| FR-100-10 | bypass 중 위험 shell 누적이 `AGENT_BYPASS_MAX_DANGEROUS` 초과 시 **해당 명령 실행 전** 중단 | 필수 |
| FR-100-11 | Resume 세션 복원 시 `bypass_approvals` 는 항상 False 로 초기화 (명시적 `-ba` 재지정 필요) | 필수 |
| FR-100-12 | `/agents list` / `/agents stop` 에 `-ba` 가 붙으면 경고 후 플래그 무시 | 권장 |
| FR-100-13 | `AGENT_BYPASS_DEFAULT=true` 환경변수 지원 | 선택 |
| FR-100-14 | bypass 진입 시 PLAN 출력 후 확인 프롬프트 (`AGENT_BYPASS_CONFIRM_PLAN` 로 토글) | 선택 |

### 6.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-100-01 | 안전장치 검사 오버헤드는 iteration 당 수 밀리초 이하 (해시 계산은 최근 3~5개 ACT 에만 적용) |
| NFR-100-02 | 기존 L0 모드(대화형)의 UX 는 변경되지 않음 (`[b]` 추가만) |
| NFR-100-03 | 세 엔트리 포인트(gemini / claude / gen-ai) 모두 동일한 플래그 파싱 동작 |
| NFR-100-04 | 환경 변수 미설정 시 합리적 기본값으로 동작 |
| NFR-100-05 | `_BypassAbort` 내부 예외는 사용자에게 스택 트레이스로 노출되지 않고 친근한 메시지로 변환 |

---

## 7. 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-100-01 | `_ask_continue()` 에 `b` 입력 | `('b', None)` 반환 |
| T-100-02 | `_enter_bypass_mode()` 호출 후 세션 상태 | `bypass_approvals=True`, `auto_approve_dangerous_shell=True`, `auto_approve_file_mutation=True`, `bypass_started_at` 설정됨 |
| T-100-03 | bypass 모드에서 루프는 `_ask_continue()` 를 호출하지 않음 | Mock 으로 검증 |
| T-100-04 | `/agents -ba 테스트 목표` 파싱 | `bypass=True`, 남은 args 는 "테스트 목표" |
| T-100-05 | `/agents --bypassApprovals [src/*.py] 리팩토링` 파싱 | `bypass=True`, 패턴은 `src/*.py`, goal 에서 수집 |
| T-100-06 | 시간 예산 초과 | `AGENT_BYPASS_TIMEOUT=1` 설정 후 2초 경과 시 `BYPASS_TIMEOUT` |
| T-100-07 | 정체 탐지 | 3회 연속 빈 액션 iteration 후 `BYPASS_STAGNATION` |
| T-100-08 | 반복 탐지 | 3회 동일 ACT 텍스트 iteration 후 `BYPASS_LOOP_DETECTED` |
| T-100-09 | 위험 액션 한도 | `AGENT_BYPASS_MAX_DANGEROUS=2` 에서 3번째 `rm` 실행 시도 시 `BYPASS_DANGEROUS_LIMIT` 으로 종료 (해당 명령 실행되지 않음) |
| T-100-10 | Resume 세션 bypass 초기화 | 세션 JSON 에 `bypass_approvals=True` 기록된 경우에도 `load()` 직후 `run(resume_session=...)` 에서 `bypass_approvals=False` 가 되어야 함 |
| T-100-11 | bypass 중 's' 키 입력 | `USER_STOP` 으로 종료 (BYPASS_* 사유가 아님) |
| T-100-12 | `/agents -ba stop` | 플래그 무시 경고 + stop 정상 처리 |
| T-100-13 | `AGENT_MAX_ITERATIONS=2`, bypass 모드, [AGENT_DONE] 미출력 | `MAX_ITERATIONS` 사유로 종료 (BYPASS_TIMEOUT 보다 우선) |
| T-100-14 | 세 엔트리 포인트에서 `-ba` 플래그가 동일하게 동작 | claude / gemini / gen-ai 모두 bypass 모드 진입 검증 |

---

## 8. 실행 흐름 다이어그램

### 8.1 /agents -ba 진입 플로우

```
사용자: /agents -ba pandas 데이터 정제
  │
  ▼
agents_command._extract_bypass_flag()
  → bypass=True, remaining=""
  │
  ▼
cli_handler.get_multiline() → "pandas ..." goal 수집
  │
  ▼
AgentRunner.run(goal, bypass_approvals=True)
  │
  ▼
_enter_bypass_mode(session)
  ├─ session.bypass_approvals = True
  ├─ session.auto_approve_* = True (2종)
  └─ session.bypass_started_at = monotonic()
  │
  ▼
[루프] for i in 1..MAX_ITERATIONS:
  ├─ _check_async_stop() — 's' 키 감지?
  ├─ model.chat() → Reason/Act/Observe
  ├─ _execute_actions()
  │    └─ 위험 shell 자동 승인 (카운터 증가)
  │    └─ 한도 초과 시 _BypassAbort 발생 → BYPASS_DANGEROUS_LIMIT
  ├─ [AGENT_DONE] 체크
  ├─ bypass 분기:
  │    └─ _check_bypass_safety()
  │         ├─ S2: 시간 예산?
  │         ├─ S3: 정체?
  │         └─ S4: 루프?
  │    └─ 위반 시 stop_reason 설정 후 break
  └─ continue (ask_continue 스킵)
  │
  ▼
_auto_save() → _append_summary_to_main_history() → _print_final_summary()
```

### 8.2 루프 중 [b] 진입 플로우

```
Iteration 3 완료
  │
  ▼
_ask_continue() → 'b' 입력
  │
  ▼
호출측: choice == 'b' → _enter_bypass_mode(session)
  │
  ▼
[이후 루프] 매 iteration 끝에서 bypass 분기로 continue
            턴 사이 프롬프트 없음
  │
  ▼
S2/S3/S4 또는 MAX_ITERATIONS 또는 [AGENT_DONE] 도달 시 종료
```

---

## 9. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | bypass 모드 도중 `AgentSessionStore` 가 중간 저장하는 세션 JSON 에 `bypass_approvals=True` 가 기록된다. 이후 `resume` 할 때 위험 | FR-100-11 — Resume 시 강제 초기화 |
| 2 | `_check_loop()` 는 ACT 텍스트 완전 일치를 검사한다. 모델이 주석 한 줄만 달라도 루프로 감지되지 않음 | 1차에선 단순 해시 유지, 정교화는 v1.1 이후 (편집 거리 / 정규화) |
| 3 | `AGENT_BYPASS_TIMEOUT` 이 API 호출 중 초과하면 응답 반환 후에야 감지됨 | 체크포인트에서만 확인 — 즉시성 한계 명시 |
| 4 | Windows CMD 에서 `-ba` 플래그가 다른 의미로 쓰이지 않는지 확인 필요 | `/agents` 는 인터프리터 내부 파싱이므로 CMD 와 무관 |
| 5 | `_BypassAbort` 내부 예외는 `except Exception` 블록에서 `FATAL_ERROR` 로 덮어씌워질 가능성 | `run()` 에서 `except _BypassAbort as e: ... raise` 를 `except Exception` 보다 **앞에** 배치. `stop_reason` 이 이미 설정되어 있으면 보존 |
| 6 | `S3 정체 탐지` 는 Self-Correction 이 내부적으로 성공한 경우를 고려해야 함 | `IterationRecord.actions` 는 Self-Correction 결과도 포함하므로 기존 로직 그대로 사용 가능 |
| 7 | 사용자가 `AGENT_MAX_ITERATIONS=100` 같이 너무 크게 잡은 후 bypass 진입하면 시간 예산이 실질적 하드 리미트가 됨 | 의도된 동작 — 시간 예산을 주요 안전장치로 설계 |
| 8 | `bypass_started_at` 을 세션 JSON 으로 직렬화 시 `monotonic` 값은 프로세스 간 비교 불가 | FR-100-11 에 의해 Resume 시 초기화되므로 문제 없음. 직렬화 시 None 으로 처리하는 것 권장 |

---

## 10. 후속 작업 (Phase 2)

| 단계 | 내용 | 별도 FSD |
|---|---|---|
| 1 | 토큰 예산 안전 장치 (`AGENT_BYPASS_TOKEN_BUDGET`) | FSD v1.0.101 예정 |
| 2 | Bypass Level 세분화 (soft/full) | FSD v1.0.102 예정 |
| 3 | bypass 전용 감사 로그 (4.4) | FSD v1.0.103 예정 |
| 4 | 's' 2단계 해제 (4.7) | v1.1.x 마이너 버전 |

---

## 11. 승인

- [ ] 설계 검토 (2026-04-20)
- [ ] [src/agent_runner.py](src/agent_runner.py) 수정 및 단위 테스트 통과
- [ ] [src/agents_command.py](src/agents_command.py) 수정 및 파싱 테스트 통과
- [ ] [src/command_registry.py](src/command_registry.py) 도움말 갱신
- [ ] 세 엔트리 포인트(gemini / claude / gen-ai) 통합 동작 확인
- [ ] 안전장치 5종(S1~S5) 각각 실제 트리거 테스트
- [ ] [docs/specs/releases/RELEASE_v1.0.100.md](docs/specs/releases/RELEASE_v1.0.100.md) 작성
