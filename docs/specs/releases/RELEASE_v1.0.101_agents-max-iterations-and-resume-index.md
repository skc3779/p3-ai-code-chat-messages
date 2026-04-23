# RELEASE v1.0.101 — `/agents` 최대 Iteration 제어 · Resume 숫자 인덱스 지원

| 항목 | 내용 |
|---|---|
| 릴리즈 버전 | v1.0.101 |
| 릴리즈 일자 | 2026-04-23 |
| 브랜치 | release_v1.0.110 |
| 요구 문서 | FSD v1.0.101 (`docs/specs/requirements/FSD_v1.0.101_agents-max-iterations-and-resume-index.md`) |

---

## 변경 요약

`/agents` 명령의 실행 편의성을 두 축에서 개선했다.

1. **`-s <N>` / `--steps <N>` 플래그** — 환경변수 재설정 없이 실행 시점에 해당 세션의 최대 iteration 상한을 덮어쓸 수 있다. 인스턴스 상태(`self.max_iterations`)는 변경하지 않으며, 지역 변수 `effective_max`와 런타임 캐시 필드 `AgentSession.effective_max_iterations`로만 반영된다.

2. **Resume 숫자 인덱스** — `/agents list` 에서 확인한 `#` 번호를 그대로 `/agents resume 2` 처럼 입력할 수 있다. 긴 파일명 복사·붙여넣기 없이 resume이 가능해진다.

---

## 변경 파일

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| `src/agents_command.py` | 수정 | `STEPS_FLAGS` 상수, `_extract_steps_flag()` 신규, `_resolve_resume_target()` 신규, `handle_agents_command()` 파싱 체인에 `-s` 삽입 및 resume 숫자 인덱스 연결, `runner.run()` 에 `max_iterations_override` 전파 |
| `src/agent_runner.py` | 수정 | `AgentSession.effective_max_iterations` 필드 추가, `run()` 시그니처에 `max_iterations_override` 추가, 루프를 `effective_max` 기준으로 변경, `_print_header()` 및 `_enter_bypass_mode()` 오버라이드 값 반영, resume 분기에서 `effective_max_iterations = None` 재초기화 |
| `src/agent_session_store.py` | 수정 | `_serialize()` 에서 `effective_max_iterations` 직렬화 제외, `print_session_list()` 말미에 resume 힌트 한 줄 추가 |
| `src/command_registry.py` | 수정 | `/agents` 도움말에 `[-s <N>]` 추가, `/agents resume` 도움말 업데이트 |
| `tests/test_agents_flags.py` | 신규 | T-101-01 ~ T-101-18 (18 케이스) |

---

## 핵심 변경 내용

### `-s` / `--steps` 플래그

| 입력 | 동작 |
|---|---|
| `/agents -s 20 <goal>` | 이번 실행만 `max_iterations=20` |
| `/agents --steps 5 <goal>` | 동일 (긴 형식) |
| `/agents -s 20 -ba <goal>` | bypass + 20회 상한 조합 |
| `/agents -s 30 resume 2` | resume + 30회 상한 조합 |
| `/agents -s 0 <goal>` | 경고 출력 후 기본값 사용 |
| `/agents -s 20 list` | 경고 출력 후 `-s` 무시, list 정상 동작 |

플래그 추출 순서: `_extract_bypass_flag()` → `_extract_steps_flag()`. 두 함수 모두 대괄호 블록(`[...]`)을 건드리지 않는다.

### `AgentSession` 신규 필드

```python
# FSD v1.0.101 — 런타임 캐시 (JSON 직렬화에서 제외)
effective_max_iterations: Optional[int] = None
```

- `run()` 호출 시 `max_iterations_override` 값이 유효하면 해당 값으로, 그렇지 않으면 `self.max_iterations`로 설정
- `_serialize()` 에서 `data.pop("effective_max_iterations", None)` 으로 JSON 저장 제외
- Resume 시 항상 `None`으로 재초기화 후 `run()` 이 재결정

### 이터레이션 헤더

오버라이드 적용 시 헤더가 `effective_max_iterations` 기준으로 표시된다.

```
━━━ Iteration 1/20 ━━━   ← max_iterations_override=20 인 경우
━━━ Iteration 1/10 ━━━   ← 오버라이드 없음 (기본 10)
```

### Resume 숫자 인덱스 (`_resolve_resume_target`)

```
/agents list
→ #1  agent_20260423_183045_tetris.json  ...
→ #2  agent_20260422_120000_pandas.json  ...

/agents resume 2   ← #2 세션 직접 복원
```

- `arg.isdigit()` 가 True 이면 1-based 인덱스로 해석 (`list_sessions()[idx-1]`)
- 범위 초과 시 `❌ 세션 인덱스 범위 초과: N (현재 M 개)` 출력 후 중단
- 숫자가 아닌 입력은 기존대로 파일명으로 해석 (후방 호환)

### `/agents list` resume 힌트

```
💡 /agents resume <번호> 또는 /agents resume <파일명>
```

---

## 테스트 결과

```
tests/test_agents_flags.py  18 passed in 0.30s
```

| 테스트 ID | 시나리오 | 결과 |
|---|---|---|
| T-101-01 | `_extract_steps_flag("-s 5 goal")` → `(5, "goal")` | ✅ |
| T-101-02 | `--steps 20 [src/*.py] goal` → `(20, "[src/*.py] goal")` | ✅ |
| T-101-03 | `-s 0 goal` → `(None, "goal")` + 경고 | ✅ |
| T-101-04 | `-s abc goal` → `(None, "goal")` + 경고 | ✅ |
| T-101-05 | `-s` 값 누락 → `(None, "")` + 경고 | ✅ |
| T-101-06 | bypass 추출 후 `-s 7` 파이프라인 → `(7, "goal")` | ✅ |
| T-101-07 | 플래그 없는 args → `(None, 원본)` | ✅ |
| T-101-08 | `run(override=3)` → 3회 후 `MAX_ITERATIONS` 종료 | ✅ |
| T-101-09 | `run()` 후 `runner.max_iterations` 변경 없음 | ✅ |
| T-101-10 | `_print_header` 출력에 `Iteration 1/3` 포함 | ✅ |
| T-101-11 | `_resolve_resume_target("2", store)` → `list_sessions()[1]` load | ✅ |
| T-101-12 | `"0"` / `"999"` → None + `❌ 세션 인덱스 범위 초과` | ✅ |
| T-101-13 | 파일명 문자열 → `store.load(filename)` 직접 호출 | ✅ |
| T-101-14 | `_serialize()` JSON 에 `effective_max_iterations` 키 없음 | ✅ |
| T-101-15 | resume 세션의 `effective_max_iterations` 는 `self.max_iterations` 로 재계산 | ✅ |
| T-101-16 | `-s 20 -ba goal` → `bypass=True, override=20` | ✅ |
| T-101-17 | `-s 20 list` → 경고 출력 + list 정상 동작 | ✅ |
| T-101-18 | `-s 30 resume 1` → 1번 세션 복원 + `override=30` 전달 | ✅ |

---

## 회귀 영향

- `-s` / `--steps` 플래그가 없는 기존 `/agents` 호출은 `max_iterations_override=None` → `effective_max = self.max_iterations` 으로 기존과 동일하게 동작
- `resume <filename>` 기존 파일명 방식 100% 후방 호환
- `bypass_approvals` 동작 변경 없음 — `_enter_bypass_mode()` 의 `remaining` 계산만 `effective_max_iterations` 참조로 갱신
- 세 엔트리 포인트(gemini/claude/gen-ai) 모두 `handle_agents_command()` 를 통해 동일하게 적용됨
