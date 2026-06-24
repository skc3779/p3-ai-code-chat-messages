# FSD v1.1.032 — `/agents` Goal 기반 검증 게이트(Evaluator-Gated Termination)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1.032 |
| 작성일 | 2026-06-21 |
| 상태 | ✅ 구현 및 집중 검증 완료 |
| 합의 방식 | ralplan: Architect **APPROVE** → Critic **APPROVE** |
| 선행 문서 | FSD v1.0.083, v1.0.100, v1.0.101, REP v1.1.031 |
| 구현 파일 | `src/agent_goal_evaluator.py`, `src/agent_runner.py`, `src/agent_session_store.py` |
| 테스트 파일 | `tests/test_agent_eval_gate.py` 및 기존 `/agents` 회귀 테스트 |

---

## 1. 목적

기존 `/agents`는 모델 응답에 `[AGENT_DONE]`이 포함되면 검증 없이 `DONE`으로 종료했다. 이 방식은 테스트 실행, 산출물 존재, 완료 보고서 작성 같은 사용자 요구가 누락되어도 모델의 자기 선언만으로 성공 처리할 수 있다.

v1.1.032는 `[AGENT_DONE]`을 종료 결정이 아닌 **완료 주장(claim)**으로 취급한다. 검증 게이트가 목표에서 추출한 완료 기준과 모델이 추가한 기준을 현재 워크스페이스 증거로 평가한 뒤에만 `DONE`을 허용한다.

핵심 원칙은 다음과 같다.

1. 사용자 목표에서 결정론적으로 추출한 기준은 권위적이며 모델이 삭제하거나 약화할 수 없다.
2. 모델 기준은 추가 전용이고 엄격한 스키마와 크기 제한을 통과해야 한다.
3. 목표·모델·저장 세션의 경로와 명령은 모두 신뢰하지 않는다.
4. 평가 명령은 셸을 사용하지 않는 전용 argv 실행기만 사용한다.
5. `AgentSessionStore`는 타입 복원만 담당하고, 초기화·재추출·재평가는 `AgentRunner`가 담당한다.
6. `AGENT_EVAL_GATE=0`은 기존 동작을 보존한다.

---

## 2. 종료 상태 계약

| 상태 | 의미 |
|---|---|
| `DONE` | 모든 완료 기준이 현재 증거로 통과 |
| `GOAL_NOT_MET` | 검증 가능한 기준이 존재하지만 하나 이상 미충족 |
| `GOAL_UNVERIFIED` | 기준 없음, 안전하지 않은 명령/경로, 잘못된 실행 설정, 판정 불능 등으로 검증 불가 |
| `MAX_ITERATIONS` | 게이트 비활성화 상태에서 기존 iteration cap 도달 |

게이트 활성화 시 종료 분기는 다음과 같다.

```text
PLAN/Resume criteria initialization
  ├─ criteria 없음 + 1회 재요청 실패 → GOAL_UNVERIFIED
  └─ criteria 있음
       ├─ [AGENT_DONE] claim → evaluate
       │    ├─ all passed → DONE
       │    ├─ unverified → GOAL_UNVERIFIED
       │    └─ unmet → feedback/retry → reject cap 초과 시 GOAL_NOT_MET
       └─ iteration cap → evaluate → DONE | GOAL_NOT_MET | GOAL_UNVERIFIED
```

게이트 비활성화 시에는 기존 호환 동작을 유지한다.

- `[AGENT_DONE]` → 즉시 `DONE`
- 토큰 없이 iteration cap → `MAX_ITERATIONS`

---

## 3. 기능 요구사항

| ID | 요구사항 | 구현 |
|---|---|---|
| FR-032-01 | 목표에서 테스트 통과/작성, 완료 보고서, 명시 파일 생성 기준을 비-LLM 방식으로 추출 | ✅ |
| FR-032-02 | 추출 기준은 `provenance=extracted`, 모델 기준은 `provenance=model`이며 추가만 허용 | ✅ |
| FR-032-03 | 기준이 없거나 criteria 블록이 잘못되면 한 번만 재요청하고 실패 시 `GOAL_UNVERIFIED` | ✅ |
| FR-032-04 | DONE claim과 iteration cap 모두 동일한 `_finalize_goal()` 분류 사용 | ✅ |
| FR-032-05 | `file_exists`, `file_contains`, `cmd_exit_zero`, `llm` 평가 지원 | ✅ |
| FR-032-06 | DONE claim 미충족 시 증거를 feedback으로 주입하고 제한 횟수만 재시도 | ✅ |
| FR-032-07 | 모델 평가 호출은 주 대화 history/system prompt를 깊은 복사본으로 복원 | ✅ |
| FR-032-08 | Resume 시 저장된 extracted 기준을 폐기하고 저장 goal에서 다시 추출 | ✅ |
| FR-032-09 | Resume 시 유효한 model 기준만 복원하고 결정론 기준 상태/증거를 새로 계산 | ✅ |
| FR-032-10 | Resume 시 stale 미충족 결과만으로 즉시 종료하지 않고 새 claim 또는 cap까지 진행 | ✅ |
| FR-032-11 | 기준별 provenance/status/evidence를 최종 요약에 출력 | ✅ |
| FR-032-12 | 게이트 비활성화 시 기존 DONE/MAX_ITERATIONS 의미 보존 | ✅ |

### 3.1 `AcceptanceCriterion`

```python
@dataclass
class AcceptanceCriterion:
    id: str
    description: str
    check_type: str       # file_exists | file_contains | cmd_exit_zero | llm
    target: str = ""
    expected: str = ""
    provenance: str = "extracted"  # extracted | model
    status: str = "pending"         # pending | passed | failed | unverified
    evidence: str = ""
```

`AgentSession`에는 아래 상태가 저장된다.

- `acceptance_criteria`
- `eval_reject_count`
- `criteria_reprompted`

---

## 4. 기준 생성 및 스키마

### 4.1 권위 기준

`AgentGoalEvaluator.extract_from_goal()`은 다음처럼 객관적으로 검증 가능한 문구만 기준으로 만든다.

| 목표 표현 | 생성 기준 |
|---|---|
| 테스트 통과/검증/작성, `tests pass`, `write tests` | 안전한 테스트 명령의 `cmd_exit_zero` |
| 완료 보고서/보고서 작성 | 명시된 `.md` 또는 `AGENT_EVAL_REPORT_PATH`의 `file_exists` |
| `create/write/작성/생성 <path>` | 해당 경로의 `file_exists` |

동일한 `(check_type, normalized target, expected)`는 중복 제거한다. 삭제/수정 기능 같은 자연어를 임의 소스 토큰 검사로 변환하지 않으며, 목표에 검증 가능한 기준이 없으면 fail-loud 경로를 사용한다.

### 4.2 모델 추가 기준

PLAN 또는 1회 criteria 재요청은 다음 형식을 사용한다.

```text
@@@criteria
M1 | file_exists|file_contains|cmd_exit_zero|llm | target | expected | description
@@@end
```

알 수 없는 타입, unsafe 명령, workspace 이탈 경로, 필수 필드 누락, 길이 초과 레코드는 거부한다. 모델이 `A1` 같은 ID를 사용해도 `M*`으로 다시 부여되므로 extracted 기준을 덮어쓸 수 없다.

### 4.3 크기 제한

| 항목 | 상한 |
|---|---:|
| 기준 수 | 32 |
| ID | 32자 |
| 설명 | 1,024자 |
| target/expected | 각 4,096자 |
| evidence | 출력 상한 내에서 제한 |

---

## 5. Shell-free 테스트 검증

### 5.1 명령 탐지

1. `AGENT_EVAL_TEST_CMD`가 있으면 동일한 validator를 통과할 때만 사용
2. pytest marker/config가 있고 pytest 모듈을 사용할 수 있으면 `python -m pytest`
3. 일반 `tests/`, `tests/test_*.py`, `test_*.py` 구조는 `python -m unittest discover -s tests`
4. 탐지 불가 시 빈 target으로 남겨 평가 때 `unverified`

### 5.2 실행 경계

평가 명령은 `TerminalExecutor.execute()`를 사용하지 않는다. 해당 API는 플랫폼 셸(`/bin/bash -c`, PowerShell, CMD)을 사용하기 때문이다.

전용 verifier는 다음 계약을 지킨다.

- `subprocess.Popen(validated_argv, shell=False)` + bounded pipe drain
- cwd는 resolve된 workspace로 고정
- 실행 파일은 현재 Python 인터프리터로 치환
- 모듈은 `pytest` 또는 `unittest`만 허용
- 절대 실행 파일, `-c`, 알 수 없는 모듈, 파이프/리다이렉션/치환/개행 거부
- 외부 절대 경로 및 `..` 인자 거부
- pytest positional 및 unittest `-s`/`-t` 경로를 resolve해 symlink workspace escape 거부
- pytest plugin/root/config/collect-only 우회 옵션 거부
- pytest `@argsfile` 간접 옵션·외부 경로 주입 거부
- trusted `-o addopts=`로 pytest config의 `--collect-only` 같은 addopts 무효화
- `PYTHONPATH`, `PYTEST_ADDOPTS`, provider credential을 자식 환경에 전달하지 않음
- timeout 및 실행 중 hard output cap(초과 즉시 child kill)
- `no tests ran`, `collected 0 items`, `Ran 0 tests`는 exit 0이어도 실패
- exit 0이어도 `N passed` 또는 `Ran N tests`의 실제 실행 증거가 없으면 실패
- `allow_unsafe=True` 사용 금지

목표에 포함된 임의 명령을 실행하는 기존 제안 R8은 제거했다.

---

## 6. 파일 경로 안전성

`file_exists`와 `file_contains`는 다음 조건을 모두 만족해야 한다.

- 상대 경로
- `..` 미포함
- `(workspace / target).resolve(strict=False)`가 workspace 하위
- 기존 symlink를 따라간 결과도 workspace 하위

위반 시 명령/파일 접근 없이 `unverified`가 된다.

---

## 7. Resume 및 저장 책임

### 7.1 Store

`AgentSessionStore`는 다음만 수행한다.

- JSON object 확인
- 알려진 `AgentSession` 필드만 전달
- 최대 32개 criterion을 bounded dataclass로 복원
- enum/길이/status/provenance 기본 스키마 검사
- 레거시 세션의 누락 필드는 dataclass 기본값 사용

Store는 경로 접근, subprocess 실행, LLM 호출, 상태 재평가를 하지 않는다.

### 7.2 Runner Resume

Runner는 Resume 시작 시 다음 순서를 고정한다.

1. 저장된 extracted 기준 전체 폐기
2. `session.goal`에서 authoritative 기준 재추출
3. 저장 PLAN과 저장 criterion 중 유효한 model 기준만 추가
4. 기준이 없거나 PLAN block이 잘못되면 criteria 1회 재요청
5. 결정론/LLM 상태와 evidence 새로 계산
6. 현재 미충족이어도 루프를 계속
7. 이후 DONE claim, cap, 초기화 실패에서만 최종 상태 분류

이로써 사용자가 편집 가능한 session JSON으로 권위 기준을 삭제하거나 forged `passed` 상태를 주입해도 성공 처리되지 않는다.

---

## 8. 환경변수

| 변수 | 기본값 | 유효 범위/동작 |
|---|---:|---|
| `AGENT_EVAL_GATE` | `1` | `0` 또는 `1`; 그 외 값은 안전 기본값 `1` |
| `AGENT_EVAL_MAX_REJECTS` | `3` | `0..20`; 잘못된 명시 값은 보수적 `0` |
| `AGENT_EVAL_TEST_CMD` | 자동 탐지 | validator 통과 시에만 사용 |
| `AGENT_EVAL_TEST_TIMEOUT` | `AGENT_CODE_TIMEOUT` | `1..600`; 잘못된 명시 값은 command criterion `unverified` |
| `AGENT_EVAL_OUTPUT_MAX_BYTES` | `65536` | `1..1048576`; 잘못된 명시 값은 command criterion `unverified` |
| `AGENT_EVAL_REPORT_PATH` | `docs/완료보고서.md` | 최대 4,096자; workspace containment 적용 |

---

## 9. 검증 시나리오

`tests/test_agent_eval_gate.py`는 다음을 직접 검증한다.

- 한/영 목표 추출, 보고서/명시 파일, 중복 제거, unmatched goal
- 앞선 무관 `.md`와 완료 보고서 경로의 연관 추출
- 모델 기준 add-only, unknown/unsafe/malformed block 거부
- shell metacharacter, interpreter `-c`, 절대 실행 파일, unknown module 거부
- pytest/unittest test target의 symlink escape, collect-only 성공 위장, `@argsfile` 우회 차단
- argv 실행, `shell=False`, workspace cwd, `/bin/bash` 미호출
- exit success/failure, timeout, zero tests, invalid bounds
- 상대 파일 성공, traversal 및 symlink escape 거부
- LLM 성공/오류 시 nested history/system prompt 복원
- LLM-only 기준의 자기 인증 차단 및 provider 예외 원문 비노출
- `file_exists`가 디렉터리가 아닌 실제 파일만 통과
- 비 UTF-8 `file_contains`의 bounded failure
- premature DONE 거부, retry 후 통과, cap 분류
- gate-off DONE/MAX_ITERATIONS 호환
- no criteria 1회 재요청 및 `GOAL_UNVERIFIED`
- forged extracted 폐기, legacy resume 추출, stale unmet 비조기 종료
- typed serialization, malformed/oversized record 처리, Store 무실행
- 음수/과대/NaN/inf 환경값

---

## 10. 구현 완료 체크리스트

### 문서/설계

- [x] H1, 버전, FR/NFR/T 식별자를 v1.1.032로 통일
- [x] 구현 전제였던 pending/승인 대기 문구 제거
- [x] gate-off cap을 `MAX_ITERATIONS`로 명확화
- [x] 임의 R8 명령 및 `allow_unsafe=True` 설계 제거
- [x] Store/Runner Resume 책임 분리
- [x] exact bounds, zero-test, workspace/symlink, evidence 계약 명시

### 구현

- [x] `AcceptanceCriterion`과 신규 stop reason 추가
- [x] 결정론 기준 추출 및 모델 add-only 파싱
- [x] one-shot criteria reprompt와 fail-loud 처리
- [x] shell-free argv 테스트 verifier 구현
- [x] file/command/LLM 평가 구현
- [x] DONE claim/cap 통합 finalization
- [x] retry feedback 및 reject cap 구현
- [x] deep history/system prompt 복원
- [x] untrusted persisted criteria와 legacy resume 처리
- [x] 기준별 최종 evidence 출력

### 검증

- [x] `python -m pytest tests/test_agent_eval_gate.py -q` — **64 passed**
- [x] 두 REP 및 `/agents` 관련 회귀 묶음 — **254 passed, 9 subtests passed**
- [x] Python compile smoke — 통과
- [x] 전체 저장소 테스트 실행 — **803 passed, 4 skipped, 63 subtests passed**, 범위 밖 기존 실패 8건/수집 오류 2건 별도 확인
- [x] 독립 code review — 최종 보안 수정 포함 **APPROVE**
- [x] adversarial QA — `@argsfile` 우회 발견·수정·재공격 후 **CLEAN**

전체 테스트의 잔여 실패는 이번 변경과 무관한 기존 항목이다: `auto_context` mock의 `output_dir` 시그니처 2건, WSL PowerShell 부재 1건, `code-review` 템플릿 fixture 부재 5건, `ai-proxy/test_toolcall.py`의 수동 함수 pytest 수집 오류 2건.

---

## 11. 제한 및 후속 범위

- 자연어에서 임의 비즈니스 기능의 완성을 완전하게 결정론 추출하지 않는다. 검증 기준을 만들 수 없으면 모델에 한 번 요청하고, 그래도 없으면 `GOAL_UNVERIFIED`로 종료한다.
- 모델 `llm` 기준은 보조 기준이다. 모든 기준이 `llm` 타입이면 `GOAL_UNVERIFIED`이며, 적어도 하나의 객관 기준이 필요하다.
- pytest/unittest 외 lint/build command family는 v1.1.032 범위에서 실행 allowlist에 포함하지 않았다. 추가 시 별도 위협 모델과 테스트가 필요하다.
