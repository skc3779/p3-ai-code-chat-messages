# FSD v1.0.101 — `/agents` 최대 iteration 제어 · Resume 인덱스 지원

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.101 |
| 작성일 | 2026-04-21 |
| 상태 | ✅ 구현 완료 (2026-04-23) |
| 선행 문서 | FSD v1.0.083 (자율 루프), FSD v1.0.086 (세션 직렬화/Resume), FSD v1.0.100 (Bypass Approvals) |
| 대상 파일 | [src/agent_runner.py](src/agent_runner.py), [src/agents_command.py](src/agents_command.py), [src/agent_session_store.py](src/agent_session_store.py), [src/command_registry.py](src/command_registry.py) |
| 신규 파일 | 없음 (기존 파일 수정만) |

---

## 1. 개요

### 1.1 목적

`/agents` 명령의 실행 제어를 두 가지 축에서 개선한다.

1. **Iteration 상한 즉석 제어** — 현재는 `AGENT_MAX_ITERATIONS` 환경 변수 (기본 10) 만이 루프 하드 상한을 정한다. 목표 규모가 다를 때마다 환경 변수를 재설정하거나 프로세스를 재시작해야 하는 번거로움이 있다. 본 FSD 는 실행 시점에 `/agents -s <N>` (또는 `--steps <N>`) 로 해당 세션에 한해 상한을 덮어쓸 수 있게 한다.

2. **Resume 의 숫자 인덱스 지원** — 현재 `/agents resume` 은 파일명 전체 또는 무인자(→ latest) 만 받는다. `/agents list` 로 확인한 목록의 `#` 번호(예: `1`, `2`, `3`) 를 그대로 `/agents resume 2` 로 입력할 수 있게 하면, 긴 파일명을 복사·붙여넣기하지 않아도 되어 UX 가 개선된다.

두 변경은 독립적이지만 사용자 체감상 "`/agents` 명령 편의성" 이라는 동일 카테고리의 개선이므로 단일 FSD 로 묶는다.

### 1.2 범위

| 항목 | 포함 여부 |
|---|---|
| `-s <N>` / `--steps <N>` 플래그 파싱 | ✅ |
| `AgentRunner.run()` 에 `max_iterations_override` 파라미터 추가 | ✅ |
| Resume 의 숫자 인덱스 해석 (`list_sessions()` 의 1-based) | ✅ |
| `/agents list` 의 출력 포맷과 Resume 인덱스의 정합성 보장 | ✅ |
| 잘못된 `-s 0` / `-s -5` / `-s abc` 입력 검증 | ✅ |
| 잘못된 `resume 0` / `resume 999` / `resume abc` 입력 검증 | ✅ |
| 기존 `/agents -ba` 와의 조합 (`/agents -s 20 -ba ...`) | ✅ |
| 실행 후 `AGENT_MAX_ITERATIONS` 환경 변수 영구 수정 | ❌ 범위 외 (1회성 오버라이드만) |
| `-s` 플래그의 세션 JSON 영속화 | ❌ 범위 외 (실행 인자이지 세션 상태가 아님) |

---

## 2. 현황 분석

### 2.1 `AGENT_MAX_ITERATIONS` 현재 사용처

[src/agent_runner.py:113](src/agent_runner.py#L113)

```python
self.max_iterations = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))
```

- `AgentRunner.__init__` 에서만 읽힘
- 이후 루프 `for i in range(start_iteration, self.max_iterations + 1)` 에서 사용
- 런타임 변경 수단 없음 (새 `AgentRunner` 인스턴스를 만들거나 환경 변수를 재설정 후 재기동해야 함)

### 2.2 Resume 현재 구현

[src/agents_command.py:82-117](src/agents_command.py#L82-L117)

```python
if sub == "resume":
    store = AgentSessionStore(str(assistant.file_manager.workspace_dir))
    parts = stripped.split(maxsplit=1)
    filename = parts[1] if len(parts) > 1 else None
    if filename:
        session = store.load(filename)
        if session is None:
            print(f"❌ 세션 파일을 찾을 수 없습니다: {filename}")
            return
    else:
        session = store.load_latest()
        ...
```

- `filename` 이 문자열 그대로 `store.load(filename)` 에 전달 → `sessions_dir / filename` 경로 읽기
- 숫자를 입력해도 `.json` 파일로 해석되어 `load()` 가 None 반환 → "세션 파일을 찾을 수 없습니다" 에러

### 2.3 `/agents list` 출력의 인덱스

[src/agent_session_store.py:114-126](src/agent_session_store.py#L114-L126)

```python
for i, s in enumerate(sessions, 1):
    print(f"{i:<3} {s['filename']:<40} ...")
```

- 이미 1-based `#` 열을 출력 중
- `list_sessions()` 는 mtime 기준 내림차순 정렬 → `#1` 이 최신
- 따라서 **숫자 인덱스는 `list_sessions()[i-1]` 과 1:1 대응** 하며, 동일 메서드를 resume 에서도 재사용하면 사용자 관점에서 자연스럽다.

### 2.4 `_extract_bypass_flag()` 기존 패턴 (참고)

[src/agents_command.py:13-37](src/agents_command.py#L13-L37)

플래그 분리 후 남은 args 를 반환하는 패턴이 이미 존재한다. `-s` 플래그도 동일 구조를 따르면 유지보수성이 올라간다. 단, `-s` 는 **값을 가진 플래그** 이므로 "다음 토큰이 값" 이라는 추가 처리 필요.

---

## 3. 설계

### 3.1 `-s` / `--steps` 플래그 사양

| 입력 | 의미 |
|---|---|
| `/agents -s 20 <goal>` | 이번 실행만 `max_iterations=20` |
| `/agents --steps 5 <goal>` | 동일 (긴 형식) |
| `/agents -s 20 -ba <goal>` | bypass + 20회 상한 조합 |
| `/agents -s 15 [src/*.py] <goal>` | 패턴 + 상한 조합 |
| `/agents -s 30 resume 2` | resume + 상한 조합 (resume 에도 적용) |
| `/agents -s 0 <goal>` | ❌ 무효 — 경고 + 기본값 사용 |
| `/agents -s -5 <goal>` | ❌ 무효 — 경고 + 기본값 사용 |
| `/agents -s abc <goal>` | ❌ 무효 — 경고 + 기본값 사용 |
| `/agents -s` (값 누락) | ❌ 무효 — 경고 + 기본값 사용 |

#### 3.1.1 플래그 형식

```python
STEPS_FLAGS = {"-s", "--steps"}
```

- 대소문자 무관
- 값은 반드시 **바로 다음 토큰**. `-s=20` 같은 `=` 결합 형식은 1차에선 지원하지 않음 (요구사항 범위 밖)
- 양의 정수만 허용 (`N >= 1`)
- 상한값은 별도 두지 않음 — 사용자가 큰 값을 넣으면 `AGENT_BYPASS_TIMEOUT` 등 다른 안전장치가 커버

### 3.2 `_extract_steps_flag()` 구현

```python
STEPS_FLAGS = {"-s", "--steps"}


def _extract_steps_flag(args: str) -> Tuple[Optional[int], str]:
    """args 에서 `-s N` 또는 `--steps N` 을 분리한다.

    Returns:
        (max_iterations_override or None, 남은_args)

    규칙:
    - 대괄호 블록(`[...]`) 시작 시 플래그 추출 생략 (패턴 파싱 보호)
    - 값이 양의 정수로 파싱되지 않으면 override=None, 원본 args 유지
      (경고는 상위 handler 에서 출력)
    - 플래그와 값 두 토큰은 함께 제거한다.
    """
    stripped = args.strip()
    if not stripped or stripped.startswith("["):
        return None, args

    tokens = stripped.split()
    override: Optional[int] = None
    remaining: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.lower() in STEPS_FLAGS:
            if i + 1 >= len(tokens):
                print(f"⚠️  {tok} 플래그의 값이 누락되어 무시됩니다.")
                i += 1
                continue
            raw = tokens[i + 1]
            try:
                val = int(raw)
                if val < 1:
                    raise ValueError
                override = val
            except ValueError:
                print(f"⚠️  {tok} 값은 양의 정수여야 합니다: {raw!r} → 무시됩니다.")
            i += 2
            continue
        remaining.append(tok)
        i += 1

    return override, " ".join(remaining)
```

> `_extract_bypass_flag` 는 부작용 없이 결과만 반환하지만, `_extract_steps_flag` 는 사용자 입력 오류 피드백이 필요하므로 경고 출력을 허용한다. 테스트에서는 `capsys` 로 검증.

### 3.3 `AgentRunner.run()` 시그니처 확장

```python
def run(
    self,
    goal: str = "",
    file_patterns: Optional[List[str]] = None,
    resume_session: Optional["AgentSession"] = None,
    bypass_approvals: bool = False,
    max_iterations_override: Optional[int] = None,   # 신규
) -> "AgentSession":
    ...
    # 기존: for i in range(start_iteration, self.max_iterations + 1):
    effective_max = max_iterations_override if (
        max_iterations_override and max_iterations_override >= 1
    ) else self.max_iterations

    if max_iterations_override:
        print(f"🔧 max_iterations 오버라이드: {effective_max} "
              f"(기본 {self.max_iterations})")
    ...
    for i in range(start_iteration, effective_max + 1):
        ...
```

#### 3.3.1 `self.max_iterations` 는 변경하지 않는다

오버라이드는 **지역 변수 `effective_max`** 로만 반영한다. `AgentRunner` 인스턴스 상태를 바꾸면:
- 동일 인스턴스로 `run()` 을 재호출할 때 이전 오버라이드가 남아 혼란 유발
- `_print_header()` 등에서 `self.max_iterations` 를 직접 참조하는 기존 코드와의 정합성 문제

대신 `_print_header()` 가 남은 iteration 을 계산할 때 필요하면 `effective_max` 를 받도록 시그니처를 확장한다. 이미 `_print_header()` 는 session 을 받고 있으므로, `AgentSession` 에 **런타임 전용 캐시 필드** `effective_max_iterations` 를 추가하는 것이 깔끔하다.

```python
@dataclass
class AgentSession:
    ...
    # FSD v1.0.101 — 런타임 캐시 (JSON 직렬화에서 제외 권장)
    effective_max_iterations: Optional[int] = None
```

> 직렬화 제외: `AgentSessionStore._serialize()` 에서 `data.pop("effective_max_iterations", None)` 로 저장을 생략한다. Resume 시 필드가 없으면 `AgentSession` 기본값 `None` 으로 초기화되고, `run()` 이 재결정한다.

### 3.4 Resume 숫자 인덱스 해석

#### 3.4.1 동작 사양

| 입력 | 해석 | 기대 결과 |
|---|---|---|
| `/agents resume` | 무인자 → latest | `store.load_latest()` |
| `/agents resume latest.json` | 파일명 | `store.load("latest.json")` |
| `/agents resume agent_20260420_...json` | 파일명 | `store.load("agent_...json")` |
| `/agents resume 1` | 숫자 → `list_sessions()[0]` | 최신 세션 |
| `/agents resume 2` | 숫자 → `list_sessions()[1]` | 두 번째 세션 |
| `/agents resume 0` | 숫자 → 범위 오류 | 경고 + 중단 |
| `/agents resume 999` | 숫자 → 범위 초과 | 경고 + 중단 |
| `/agents resume abc` | 비파일·비숫자 → 파일로 시도 → 실패 | 기존 "세션 파일을 찾을 수 없습니다" |

#### 3.4.2 판별 로직

```python
def _resolve_resume_target(arg: str, store: AgentSessionStore) -> Optional[AgentSession]:
    """resume 인자를 해석해 AgentSession 을 반환.

    - arg 가 전부 숫자 → 인덱스(1-based)로 해석
    - 그 외 → 파일명으로 해석
    실패 시 None 반환 (호출측이 에러 메시지 출력)
    """
    if arg.isdigit():
        idx = int(arg)
        sessions = store.list_sessions()
        if idx < 1 or idx > len(sessions):
            print(f"❌ 세션 인덱스 범위 초과: {idx} "
                  f"(현재 {len(sessions)} 개)")
            return None
        return store.load(sessions[idx - 1]["filename"])
    # 파일명 해석 (기존 동작)
    return store.load(arg)
```

> `str.isdigit()` 은 음수(`-1`)나 부호부 숫자에 대해 False 를 반환하므로 안전. 16진수·공백·쉼표 포함 문자열도 False.

#### 3.4.3 `handle_agents_command()` 통합

```python
if sub == "resume":
    store = AgentSessionStore(str(assistant.file_manager.workspace_dir))
    parts = stripped.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else None

    if arg is None:
        session = store.load_latest()
        if session is None:
            print("❌ 저장된 세션이 없습니다. /agents list 로 확인하세요.")
            return
    else:
        session = _resolve_resume_target(arg, store)
        if session is None:
            # arg 가 숫자가 아니었고 파일명으로도 실패한 경우
            if not arg.isdigit():
                print(f"❌ 세션 파일을 찾을 수 없습니다: {arg}")
            return
    ...
    runner.run(
        resume_session=session,
        bypass_approvals=bypass,
        max_iterations_override=steps_override,
    )
    return
```

### 3.5 `/agents` 파싱 전체 흐름 (갱신)

```
handle_agents_command(args)
  │
  ▼
_extract_bypass_flag(args)       → (bypass, args')
  │
  ▼
_extract_steps_flag(args')       → (steps_override, args'')
  │
  ▼
stripped = args''.strip()
sub = first_token(stripped)
  │
  ├─ "stop"   → (기존) list/stop 은 bypass/steps 모두 무시(경고)
  ├─ "list"   →  동일
  ├─ "resume" → _resolve_resume_target(arg, store) → runner.run(resume_session=..., bypass_approvals=bypass, max_iterations_override=steps_override)
  └─ (그 외)  → 패턴·goal 수집 → runner.run(goal=..., bypass_approvals=bypass, max_iterations_override=steps_override)
```

**플래그 파싱 순서**: `-ba` 먼저, 그 다음 `-s N`. 두 추출 함수 모두 대괄호 블록을 건드리지 않으므로 순서 무관하나, `-ba` 단일 토큰이 먼저 제거되면 `-s` 토큰 위치 계산이 단순해진다.

### 3.6 `/agents list` 의 출력 정렬과 인덱스 계약

`list_sessions()` 는 `mtime` 내림차순 정렬을 보장한다. 사용자가 `list` 로 `#2` 를 확인한 직후 `resume 2` 를 입력하는 동안 새 세션이 자동 저장되면 (`auto_save_interval=3` 기본) 인덱스가 바뀔 수 있다.

**대응**:
- 본 FSD 는 단순히 "입력 시점의 `list_sessions()`" 를 사용 — 경쟁 조건이 실제로 문제가 되려면 루프 실행 중이어야 하는데, 사용자가 동시에 `/agents resume` 을 칠 수 있는 상황이 아님 (REPL 은 단일 스레드).
- `list` 출력 말미에 힌트 추가: `💡 /agents resume <번호> 또는 /agents resume <파일명>` (print_session_list 수정).

### 3.7 `_print_header()` 보강

```python
def _print_header(self, session: AgentSession, i: int) -> None:
    mx = session.effective_max_iterations or self.max_iterations
    header = f"── Iteration {i}/{mx} ──"
    ...
```

> 기존에는 `self.max_iterations` 만 썼으므로 오버라이드 시 헤더가 잘못 표시될 수 있다. 런타임 캐시 `session.effective_max_iterations` 우선.

### 3.8 `AgentSessionStore._serialize` 보강

```python
def _serialize(self, session: AgentSession) -> str:
    data = dataclasses.asdict(session)
    if isinstance(data.get("stop_reason"), AgentStopReason):
        data["stop_reason"] = data["stop_reason"].value
    # FSD v1.0.101 — 런타임 캐시는 직렬화 제외
    data.pop("effective_max_iterations", None)
    data["_workspace"] = str(self.workspace_dir)
    return json.dumps(data, ..., indent=2)
```

### 3.9 `command_registry.py` 도움말 갱신

```python
CommandInfo('/agents',
    "자율 에이전트 루프 실행 (목표 멀티라인, 루프 중 's' 키 또는 Ctrl+C 로 중단)",
    '/agents [-ba|--bypassApprovals] [-s <N>] [pattern | [p1,p2,...] | stop]',
    '[src/*.py, docs/*.md]'),
CommandInfo('/agents resume',
    '마지막(또는 지정 인덱스/파일) 에이전트 세션 복원',
    '/agents resume [N | filename]',
    'agent_20260421_123045_tetris.json  또는  2'),
```

---

## 4. 파일 변경 예정 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [src/agents_command.py](src/agents_command.py) | 수정 | `STEPS_FLAGS`, `_extract_steps_flag()`, `_resolve_resume_target()` 신규. `handle_agents_command()` 내부 파싱 체인에 `-s` 삽입 및 resume 인덱스 해석 연결. `runner.run(..., max_iterations_override=...)` 전파 |
| [src/agent_runner.py](src/agent_runner.py) | 수정 | `AgentSession.effective_max_iterations` 필드 추가. `run()` 시그니처에 `max_iterations_override` 추가, 지역 변수 `effective_max` 로 루프 범위 결정. `_print_header()` 가 `session.effective_max_iterations` 사용 |
| [src/agent_session_store.py](src/agent_session_store.py) | 수정 | `_serialize()` 에서 `effective_max_iterations` 제외. `print_session_list()` 말미에 resume 힌트 한 줄 추가 |
| [src/command_registry.py](src/command_registry.py) | 수정 | `/agents` · `/agents resume` 도움말 문자열 갱신 |
| [tests/test_agents_flags.py](tests/test_agents_flags.py) | 신규 | T-101-01 ~ T-101-14 |
| [docs/specs/releases/](docs/specs/releases/) | 신규 | 구현 완료 후 `RELEASE_v1.0.101_*.md` 작성 |

---

## 5. 요구사항 (Functional / Non-Functional)

### 5.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-101-01 | `/agents -s <N> <goal>` 은 해당 실행에만 `max_iterations=N` 적용 | 필수 |
| FR-101-02 | `--steps <N>` 긴 형식 지원 (대소문자 무관) | 필수 |
| FR-101-03 | `N` 이 양의 정수가 아니거나 누락된 경우 경고 후 기본값 유지 | 필수 |
| FR-101-04 | `-s` 오버라이드는 `self.max_iterations` 를 변경하지 않으며, `AgentSession.effective_max_iterations` 에만 반영 | 필수 |
| FR-101-05 | 이터레이션 헤더 `── Iteration i/N ──` 의 N 은 오버라이드 값을 반영 | 필수 |
| FR-101-06 | `-ba` 와 `-s N` 은 독립적으로 조합 가능 | 필수 |
| FR-101-07 | `-s N` 은 resume 에도 적용 (`/agents -s 30 resume 2`) | 필수 |
| FR-101-08 | `/agents resume <숫자>` 는 `list_sessions()` 의 1-based 인덱스로 해석 | 필수 |
| FR-101-09 | 인덱스 범위 초과 (`< 1` 또는 `> len`) 시 경고 후 중단 | 필수 |
| FR-101-10 | 비숫자 인자는 기존대로 파일명으로 해석 (후방 호환) | 필수 |
| FR-101-11 | `/agents list` 출력 말미에 resume 힌트 한 줄 추가 | 권장 |
| FR-101-12 | `AgentSession.effective_max_iterations` 는 JSON 세션 파일에 직렬화되지 않음 | 필수 |
| FR-101-13 | Resume 시 이전 세션의 `effective_max_iterations` 는 항상 None 으로 재초기화 | 필수 |
| FR-101-14 | `/agents -s 20 list` / `/agents -s 20 stop` 은 `-s` 를 무시하고 경고만 출력 | 권장 |

### 5.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-101-01 | 플래그 파싱 오버헤드는 무시 가능한 수준 (< 1ms) |
| NFR-101-02 | 기존 `/agents` 사용법 (`-s` 없음, `resume <filename>`) 은 100% 후방 호환 |
| NFR-101-03 | 세 엔트리 포인트(gemini / claude / gen-ai) 모두 동일한 동작 |
| NFR-101-04 | 에러 메시지는 `⚠️` (경고) / `❌` (치명) 이모지 관례 준수 |
| NFR-101-05 | `-s` 오버라이드 로그는 한 줄로만 출력하여 루프 헤더 가독성을 해치지 않음 |

---

## 6. 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-101-01 | `_extract_steps_flag("-s 5 goal")` | `(5, "goal")` |
| T-101-02 | `_extract_steps_flag("--steps 20 [src/*.py] goal")` | `(20, "[src/*.py] goal")` |
| T-101-03 | `_extract_steps_flag("-s 0 goal")` | `(None, "goal")` + 경고 출력 |
| T-101-04 | `_extract_steps_flag("-s abc goal")` | `(None, "goal")` + 경고 출력 |
| T-101-05 | `_extract_steps_flag("-s")` (값 누락) | `(None, "")` + 경고 출력 |
| T-101-06 | `_extract_steps_flag("-ba -s 7 goal")` 파이프라인 | bypass 먼저 추출 후 `(7, "goal")` |
| T-101-07 | `_extract_steps_flag("goal without flag")` | `(None, "goal without flag")` |
| T-101-08 | `AgentRunner.run(goal, max_iterations_override=3)` | 루프 최대 3회 후 `MAX_ITERATIONS` 종료 (`AGENT_MAX_ITERATIONS=10` 인 상태에서) |
| T-101-09 | `run()` 호출 후 `runner.max_iterations` 값은 변경 없음 | 인스턴스 상태 보존 |
| T-101-10 | `_print_header` 출력 문자열에 `Iteration 1/3` 포함 (오버라이드=3) | 정확한 헤더 |
| T-101-11 | `_resolve_resume_target("2", store)` | `list_sessions()[1]` 의 filename 을 load |
| T-101-12 | `_resolve_resume_target("0", store)` / `"999"` | None 반환 + `❌ 세션 인덱스 범위 초과` |
| T-101-13 | `_resolve_resume_target("agent_xxx.json", store)` 파일 존재 | 해당 세션 load |
| T-101-14 | `AgentSessionStore._serialize()` 출력 JSON 에 `effective_max_iterations` 키 부재 | 직렬화 제외 검증 |
| T-101-15 | Resume 된 세션의 `effective_max_iterations` 는 None | 재초기화 검증 |
| T-101-16 | `handle_agents_command("-s 20 -ba goal")` 파싱 후 runner.run 호출 인자 | `bypass=True, override=20` |
| T-101-17 | `handle_agents_command("-s 20 list")` | 경고 출력 + list 정상 동작 |
| T-101-18 | `handle_agents_command("-s 30 resume 1")` | 1번 세션 복원 + override 적용 |

---

## 7. 실행 흐름 다이어그램

### 7.1 `/agents -s 20 -ba <goal>` 신규 실행

```
사용자: /agents -s 20 -ba pandas 정제
  │
  ▼
handle_agents_command("-s 20 -ba pandas 정제")
  │
  ├─ _extract_bypass_flag()   → bypass=True, args="-s 20 pandas 정제"
  ├─ _extract_steps_flag()    → override=20, args="pandas 정제"
  │
  ▼
sub == "" (실행 모드)
  │
  ▼
cli_handler.get_multiline() → "pandas 정제" (또는 추가 멀티라인)
  │
  ▼
runner.run(goal, bypass_approvals=True, max_iterations_override=20)
  │
  ├─ session.effective_max_iterations = 20
  ├─ _enter_bypass_mode(session)
  │
  ▼
for i in 1..20:  # 기본 10 대신 20
  ├─ _print_header → "── Iteration 1/20 ──"
  └─ ...
```

### 7.2 `/agents resume 2`

```
사용자: /agents resume 2
  │
  ▼
handle_agents_command("resume 2")
  │
  ├─ _extract_bypass_flag() → (False, "resume 2")
  ├─ _extract_steps_flag()  → (None, "resume 2")
  │
  ▼
sub == "resume", arg == "2"
  │
  ▼
_resolve_resume_target("2", store)
  ├─ "2".isdigit() → True
  ├─ sessions = store.list_sessions()  # [최신, 2번째, ...]
  ├─ idx=2 → sessions[1]
  └─ store.load(sessions[1]["filename"])
  │
  ▼
runner.run(resume_session=session, ...)
```

---

## 8. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | `-s 0` / `-s -1` 등 무효값이 silently 무시될 가능성 | FR-101-03 — 반드시 경고 출력 |
| 2 | `AgentSession.effective_max_iterations` 를 직렬화하면 과거 실행의 오버라이드가 resume 시 되살아날 우려 | FR-101-12 — `_serialize()` 에서 pop, resume 시 None 재초기화 |
| 3 | `list_sessions()` 는 mtime 내림차순 → 사용자가 `list` 후 resume 하는 동안 새 세션이 추가되면 인덱스 이동 | REPL 단일 스레드 특성상 실무 위험 낮음. 경고만 help 에 언급 |
| 4 | 숫자 파일명(예: `123.json`) 이 있는 경우 `resume 123` 이 인덱스로 해석됨 | 파일명 규약 `agent_<timestamp>_<slug>.json` 은 숫자로 시작하지 않음. 사용자가 임의 파일명을 만든 경우만 문제 — 문서화로 대응 |
| 5 | `-s` 를 `stop`/`list` 와 같이 쓸 때 의미 없음 | FR-101-14 — 경고 후 무시 |
| 6 | `-s` 와 `AGENT_BYPASS_TIMEOUT` 상호작용: N=1000 + 30분 예산 → 시간 예산이 실질 상한 | 의도된 동작, 문서화만 |
| 7 | `-s 20` 과 `--steps 30` 중복 지정 시 동작 정의 필요 | `_extract_steps_flag()` 는 선형 스캔으로 마지막 유효 값이 이김 — 테스트 케이스로 명시 |
| 8 | resume 숫자 인덱스는 향후 정렬 기준 변경 시 의미가 흔들림 | `list_sessions()` 정렬 규약 변경 시 본 FSD 도 갱신 필요 — 코멘트로 연결점 명시 |

---

## 9. 후속 작업 (Optional / Phase 2)

| 단계 | 내용 | 비고 |
|---|---|---|
| 1 | `-s=20` / `--steps=20` 등 `=` 결합 형식 지원 | 1차 범위 외, UX 피드백 보고 도입 |
| 2 | `-s` 를 `AgentSession` 에 **기록** 하여 resume 시 기본값으로 복원 (토글 필요) | 현재 설계는 의도적으로 제외 — resume 은 명시적 재지정 원칙 (FSD v1.0.086 정책과 일치) |
| 3 | `/agents resume -1` 같은 역순 인덱스 (마지막 N 번째) | 저수요, 명시 요청 전까진 보류 |
| 4 | `list` 출력에 **절대 인덱스 안정화** (예: hash 기반 ID) | 경쟁 조건 완전 제거를 위해 필요 시 도입 |

---

## 10. 승인

- [x] 설계 검토 (2026-04-21)
- [x] [src/agents_command.py](src/agents_command.py) 플래그 파싱 및 resume 인덱스 해석 구현
- [x] [src/agent_runner.py](src/agent_runner.py) `run()` 시그니처 확장 및 `effective_max_iterations` 도입
- [x] [src/agent_session_store.py](src/agent_session_store.py) 직렬화 제외 및 help 힌트
- [x] [src/command_registry.py](src/command_registry.py) 도움말 갱신
- [x] T-101-01 ~ T-101-18 테스트 통과 (2026-04-23, 18/18 passed)
- [ ] 세 엔트리 포인트(gemini / claude / gen-ai) 통합 동작 확인
- [x] [docs/specs/releases/RELEASE_v1.0.101_agents-max-iterations-and-resume-index.md](docs/specs/releases/RELEASE_v1.0.101_agents-max-iterations-and-resume-index.md) 작성
