<<<<<<< Updated upstream
# FSD v1.1.073 — `/agents` 목표 기준 · 히스토리 가드 계약

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1.073 |
| 작성일 | 2026-06-27 |
| 상태 | ✅ 구현 완료 · 검증 작성 |
| 선행 문서 | FSD v1.1.032 (Goal Evaluator Gate), FSD v1.1.062 (하이브리드 루프 재구현) |
| 구현 파일 | `src/agent_runner.py`, `src/agent_goal_evaluator.py`, `src/agent_session_store.py` |
| 테스트 파일 | `tests/test_agent_goal_criteria_history_guard.py` |

---

## 1. 목적

`/agents` 루프는 `acceptance_criteria`(완료 기준)와 `agent_history`(에이전트 대화 이력)를 모두 `AgentSession`에 보관한다. 두 상태가 서로 오염되면:

- 모델이 `agent_history`를 조작해 `[AGENT_DONE]` 자기보고를 통과시킬 수 있다.
- `[CURRENT_FILES]` 대용량 파일 본문이 history에 누적되어 토큰이 낭비되고 주입 공격에 노출된다.
- 저장된 세션 파일의 위조 기준이 Resume 시 그대로 적용될 수 있다.

본 문서는 기준과 이력을 안전하게 분리·보호하는 **히스토리 가드 계약**을 명시한다.

---

## 2. 핵심 불변식 (Invariants)

| ID | 불변식 |
|---|---|
| INV-073-01 | `acceptance_criteria`는 항상 목표(`session.goal`)에서 재추출하며, 저장 세션의 criterion 객체를 신뢰하지 않는다 |
| INV-073-02 | `agent_history`에는 완료 기준 원문이 포함되지 않는다 (기준 평가 피드백만 주입) |
| INV-073-03 | `[CURRENT_FILES]` 블록은 모델 호출 1회 직후 `agent_history`에서 제거된다 (휘발성) |
| INV-073-04 | 모델 LLM 평가(`llm` 종류 기준)는 `agent_history`의 **깊은 복사본**으로만 호출한다 |
| INV-073-05 | Resume 시 `eval_reject_count`, `refine_round`, `last_unmet_signature`는 0/None으로 리셋된다 |
| INV-073-06 | `_call_model()` 은 `assistant.conversation_history`를 호출 전후 원복한다 |

---

## 3. 기능 요구사항 (FR)

| ID | 요구사항 | 구현 위치 |
|---|---|---|
| FR-073-01 | Resume 시 저장된 `acceptance_criteria`를 폐기하고 `session.goal`에서 재추출 | `AgentRunner.run()` Resume 분기 |
| FR-073-02 | `[CURRENT_FILES]` 주입 직후(`_call_model` 반환 즉시) `agent_history` 최근 user 메시지에서 블록 strip | `_strip_current_files_from_history()` |
| FR-073-03 | Strip 후 `[CURRENT_FILES]` 뒤에 오는 `[USER_FEEDBACK]` 등 다른 섹션 헤더/내용은 보존 | `_strip_current_files_from_history()` |
| FR-073-04 | `[CURRENT_FILES]`가 없는 메시지는 Strip 시 변경 없음 | `_strip_current_files_from_history()` |
| FR-073-05 | `_call_model()`은 호출 전 `assistant.conversation_history`를 저장하고 반환 시 원복 | `_call_model()` |
| FR-073-06 | `_call_model()` 내부에서 `agent_history`를 `assistant.conversation_history`에 교체 후 호출 | `_call_model()` |
| FR-073-07 | `_compact_history_if_needed()`는 `acceptance_criteria` 상태에 영향 없음 | `_compact_history_if_needed()` |
| FR-073-08 | 히스토리 압축 시 `agent_history`는 요약 쌍으로 교체되지만 criteria는 변경 없음 | `_compact_history_if_needed()` |
| FR-073-09 | `eval_reject_count` 는 Resume 시 0으로 리셋 (저장값 무시) | `AgentRunner.run()` Resume 분기 |
| FR-073-10 | `refine_round`, `last_unmet_signature` 는 Resume 시 0/None으로 리셋 | `AgentRunner.run()` Resume 분기 |
| FR-073-11 | `[CURRENT_FILES]` 펜스 내부에 `[AGENT_DONE]`·`@@@`·`[ACTION]` 토큰이 있어도 파싱에 영향 없음 | `AgentRunner` 디스패처 로직 |
| FR-073-12 | 저장 세션 JSON의 `acceptance_criteria` 필드는 역직렬화 후 Resume 시 덮어쓰여 무효화됨 | `AgentRunner.run()` Resume 분기 |

---

## 4. 히스토리 가드 상세 계약

### 4.1 `_strip_current_files_from_history(session)`

`agent_history`의 **가장 최근 user 메시지**에서 `[CURRENT_FILES]` 블록만 제거한다.

제거 대상: `[CURRENT_FILES]`로 시작해 다음 `[HEADER]`(대문자 헤더 태그) 또는 메시지 끝까지.  
대체 텍스트: `"[CURRENT_FILES] (생략됨 — 최신 본문은 휘발성 주입)\n"`.  
`[CURRENT_FILES]`가 없는 메시지는 그대로 유지한다.

```python
# 정규식 (agent_runner.py 구현 기준)
re.sub(
    r"\[CURRENT_FILES\].*?(?=\n\[[A-Z_]+\]\n|\Z)",
    "[CURRENT_FILES] (생략됨 — 최신 본문은 휘발성 주입)\n",
    content,
    flags=re.DOTALL,
)
```

중첩 strip(같은 메시지에 두 번 호출)은 idempotent해야 한다.

### 4.2 `_call_model(session, prompt)` 히스토리 격리

```text
1. saved_main = assistant.conversation_history       # 원본 저장
2. saved_sys  = assistant.system_prompt              # 원본 저장
3. assistant.conversation_history = list(session.agent_history)  # 교체
4. assistant.chat(prompt, ...)                        # 모델 호출
5. session.agent_history = assistant.conversation_history        # 결과 흡수
6. _strip_current_files_from_history(session)         # 휘발성 strip
7. assistant.conversation_history = saved_main       # 원본 원복
8. assistant.system_prompt        = saved_sys        # 원본 원복
```

3단계와 7단계 사이에 예외가 발생해도 finally에서 원복이 보장된다.

### 4.3 Resume 보안 초기화 순서

```text
1. 저장된 acceptance_criteria 전부 폐기
2. eval_reject_count = 0
3. refine_round = 0
4. last_unmet_signature = None
5. auto_approve_dangerous_shell = False   (이슈#5 보안 리셋)
6. auto_approve_file_mutation = False
7. interaction_policy = "interactive"
8. _initialize_acceptance_criteria(session, session.goal)  ← 재추출
```

### 4.4 history 압축과 기준 독립성

`_compact_history_if_needed(session)`:
- `len(session.agent_history)` 기반 또는 `AGENT_COMPACT_MAX_BYTES` 초과 시 발동.
- `agent_history`를 요약 2쌍(user `[COMPACT_HISTORY]` + assistant 요약)으로 교체.
- `session.acceptance_criteria`, `eval_reject_count`, `refine_round`, `plan_steps`는 **변경 없음**.
- 압축 후 평가(`_goal_evaluator.evaluate()`)는 파일/명령 기반이므로 history 내용과 무관.

---

## 5. 환경변수

| 변수 | 기본값 | 설명 |
|---|---:|---|
| `AGENT_EVAL_GATE` | `1` | `0`이면 기준 없이 자기보고 신뢰 (히스토리 가드 비활성) |
| `AGENT_EVAL_REJECT_MAX` | `3` | Resume 시 0으로 리셋 |
| `AGENT_COMPACT_AFTER` | `5` | history 압축 발동 메시지 수 |
| `AGENT_COMPACT_MAX_BYTES` | `131072` | byte 기반 압축 임계 |

---

## 6. 검증 시나리오

| ID | 시나리오 | 기대 |
|---|---|---|
| T-073-01 | Resume 전 세션에 위조 `acceptance_criteria` 삽입 | resume 후 goal 재추출로 교체됨 |
| T-073-02 | `[CURRENT_FILES]` 포함 메시지 → strip 후 확인 | 블록 제거, 요약 대체 텍스트 잔존 |
| T-073-03 | `[CURRENT_FILES]` 뒤에 `[USER_FEEDBACK]` 있는 경우 strip | `[CURRENT_FILES]`만 제거, `[USER_FEEDBACK]`은 보존 |
| T-073-04 | `[CURRENT_FILES]` 없는 메시지 strip | 변경 없음 |
| T-073-05 | strip idempotent (같은 메시지 두 번 strip) | 결과 동일 |
| T-073-06 | `_call_model` 후 `assistant.conversation_history` 원복 확인 | 원본과 동일 |
| T-073-07 | `_compact_history_if_needed` 후 `acceptance_criteria` 불변 | 기준 동일 |
| T-073-08 | history 압축 후 `eval_reject_count` 불변 | 리셋 없음 |
| T-073-09 | Resume 시 `eval_reject_count=99` → 0 리셋 | 0 |
| T-073-10 | Resume 시 `refine_round=10` → 0 리셋 | 0 |
| T-073-11 | `[CURRENT_FILES]` 내부에 `[AGENT_DONE]` 토큰 포함 | done 판정에 영향 없음 |
| T-073-12 | `[CURRENT_FILES]` 내부에 `@@@criteria` 블록 포함 | 기준 파싱에 영향 없음 |
| T-073-13 | 세션 JSON `acceptance_criteria` 에 위조 `passed=True` 포함 후 Resume | 재추출로 무효화 |
| T-073-14 | history 압축 후 `_goal_evaluator.evaluate` 정상 동작 | 파일 기반 평가 unaffected |

---

## 7. 구현 완료 체크리스트

### 구현

- [x] `_strip_current_files_from_history()` — 휘발성 injection strip
- [x] `_call_model()` — save/restore `conversation_history` + `system_prompt`
- [x] Resume 보안 초기화 순서 — `eval_reject_count`, `refine_round`, 기준 재추출
- [x] `_compact_history_if_needed()` — criteria 독립성 보장
- [x] `_initialize_acceptance_criteria()` — Resume 포함 전체 경로에서 호출

### 검증

- [ ] `python -m unittest tests.test_agent_goal_criteria_history_guard -v` — T-073-01 ~ T-073-14 전부 통과
- [ ] 기존 회귀 테스트(`test_agent_refine_loop.py`, `test_agent_runner.py`) 통과 확인

---

## 8. 제한 및 후속 범위

- `llm` 종류 기준의 실제 LLM 평가 시 사용되는 history 깊은 복사 검증은 `agent_goal_evaluator.py` 내 LLM 평가 경로에 의존하며 본 문서 범위 밖이다.
- `agent_history` 자체의 내용 무결성(모델이 role을 위조하는 경우 등)은 Provider 계층에서 처리한다.
=======
# FSD v1.1.073 - /agents 목표 기준 주입 및 Agent 전용 히스토리 보존 개선

## 1. 배경

BUG v1.1.072에서 `/agents`가 명시적인 산출 파일 생성 요청을 수행하지 못하고 조회 명령만 반복한 뒤 `goal_not_met`으로 종료되는 현상이 보고되었다.

추가 확인 결과, 직접 재현 원인은 `.env`의 `MAX_MESSAGES_TO_KEEP=1`이었다. 값을 `30`으로 변경하면 정상 동작한다. 즉, v1.1.072의 실패는 에이전트 본체가 항상 산출 파일 생성을 못 하는 결함이라기보다, 과도한 provider history trimming 때문에 모델이 작업 맥락을 유지하지 못한 현상으로 보는 것이 가장 타당하다.

그러나 BUG v1.1.072의 수정 제안에는 별도 개선 가치가 있는 항목이 있다. 본 FSD는 `/agents`가 일반 대화 히스토리 설정과 분리된 Agent 전용 히스토리 보존 정책을 사용하고, 모델 형식 오류나 조회성 액션 반복에 더 견고하게 동작하도록 필요한 최소 개선 범위를 정의한다.

## 2. 목표

1. `/agents` 실행 중 일반 대화용 `MAX_MESSAGES_TO_KEEP`와 별개로 `MAX_AGENT_MESSAGES_TO_KEEP`를 사용해 필수 목표/완료 기준/최근 관찰이 보존되도록 한다.
2. 추출된 완료 기준을 매 iteration 프롬프트에 명시해 모델이 산출물 목표를 놓치지 않게 한다.
3. 파싱 가능한 ACTION이 없을 때 조용히 통과하지 않고 자기 교정이 가능한 실패로 기록한다.
4. 완료 기준이 미충족된 상태에서 조회성 shell만 반복하는 경우, 남은 목표 기준을 우선 처리하도록 명확한 피드백을 주입한다.

## 3. 타당성 검토

| BUG v1.1.072 제안 | 판단 | 반영 방식 |
|---|---|---|
| `_build_iteration_prompt()`에 `[ACCEPTANCE_CRITERIA]` 항상 포함 | 타당 | 필수 요구사항으로 채택 |
| 미충족 `file_exists` + 조회성 shell 반복 시 강한 피드백 주입 | 타당 | “read-only drift guard”로 채택 |
| 파싱 불가 ACTION을 실패로 기록 | 타당 | dispatcher 실패 결과 + self-correction으로 채택 |
| `/agents` 중 낮은 history trim 하한 보정 | 타당 | 별도 `MAX_AGENT_MESSAGES_TO_KEEP`로 채택 |
| PLAN에 `@@@criteria` 생성을 요구 | 부분 타당 | 이번 버그 직접 원인은 아님. 선택적 모델 기준 보강으로 낮은 우선순위 반영 |

## 4. 현재 동작

### 4.1 히스토리 트리밍

`TokenManager.auto_trim_history()`는 메시지 수가 `MAX_MESSAGES_TO_KEEP` 이상이면 오래된 메시지를 제거한다. 현재 설정은 최솟값 `1`을 허용한다.

`MAX_MESSAGES_TO_KEEP=1`이면 provider 호출마다 `2개 >= 1개` 조건이 반복되어 최근 한 쌍 수준의 대화만 남는다. `/agents`는 별도 `session.iterations[-2:]`를 프롬프트에 넣지만, provider 자체 대화 맥락과 직전 응답 형식 학습은 크게 약화된다.

### 4.2 완료 기준 주입

`AgentGoalEvaluator.extract_from_goal()`은 파일 생성/작성 목표에서 `file_exists:<target>` 기준을 추출한다. 하지만 `_build_iteration_prompt()`는 이 기준을 항상 별도 블록으로 넣지 않는다. 첫 iteration에서는 probe 결과도 없으므로 `[REFINE_TARGETS]`가 없다.

### 4.3 ACTION 파싱 실패

`AgentActionDispatcher`는 `@@@filename:`, `@@@patch:`, fenced code, `$ command` 형식을 실행 대상으로 인식한다. 모델이 `sh\ncat file`처럼 형식을 벗어난 ACTION을 내면 실행 액션이 없는 상태가 되고, 현재는 이를 실패로 강하게 다루지 않는다.

### 4.4 Shell 실행 환경

`/agents` iteration의 shell 액션은 현재 실행 OS에 맞춰 동작해야 한다. 기본 대상은 PowerShell 기반 환경이며, Linux/WSL 환경도 지원한다. 모델 프롬프트와 guard 문구는 특정 shell 하나에 고정된 명령만 강제하지 않고, `TerminalExecutor`의 shell hint와 OS 판별 결과에 맞춰 PowerShell 또는 Linux shell 구문을 안내해야 한다.

## 5. 기능 요구사항

### FR-073-01. Agent 전용 히스토리 보존 설정

`/agents` 내부 모델 호출은 일반 대화용 `MAX_MESSAGES_TO_KEEP`를 사용하지 않고 Agent 전용 `MAX_AGENT_MESSAGES_TO_KEEP`를 사용해야 한다.

- 신규 환경변수: `MAX_AGENT_MESSAGES_TO_KEEP`
- 기본값: `30`
- 허용 범위: `2..200`
- 적용 범위: `/agents`의 AgentRunner 모델 호출과 Agent 전용 history trimming
- 일반 채팅, `/context`, `/auto_context`, `/tokens -k`의 `MAX_MESSAGES_TO_KEEP` 동작에는 영향을 주지 않는다.
- `MAX_MESSAGES_TO_KEEP=1`이어도 `/agents`는 `MAX_AGENT_MESSAGES_TO_KEEP` 값으로 agent history를 보존해야 한다.
- `MAX_AGENT_MESSAGES_TO_KEEP`가 유효하지 않으면 기본값 `30`을 사용한다.

### FR-073-02. 완료 기준 프롬프트 상시 주입

`AgentRunner._build_iteration_prompt()`는 `session.acceptance_criteria`가 있으면 `[ACCEPTANCE_CRITERIA]` 블록을 항상 포함해야 한다.

블록에는 다음을 포함한다.

- criterion kind
- target
- provenance: `extracted` 또는 `model`
- 최근 평가 상태: `passed`, `failed`, `unknown`
- 실패 evidence 요약이 있으면 160자 이내로 포함

예시:

```text
[ACCEPTANCE_CRITERIA]
다음 기준은 목표 달성의 권위 기준입니다. 미충족 기준을 우선 처리하세요.
- [extracted/file_exists/failed] docs/output.md - 파일 없음: docs/output.md
```

### FR-073-03. 미충족 파일 기준 처리 안내

`file_exists` 또는 `file_contains` 기준이 failed이고 target이 workspace 내부 상대 경로이면, `[ACCEPTANCE_CRITERIA]` 또는 `[REFINE_TARGETS]`에 해당 target을 명확히 표시해야 한다.

이 요구사항은 특정 파일명 생성을 강제하지 않는다. 목표에서 추출된 실제 target을 기준으로 남은 작업을 명시하며, 추가 탐색이 필요하면 대상 기준과 연결된 탐색인지 설명하도록 유도한다.

### FR-073-04. Read-only drift guard

최근 iteration이 산출물 기준을 충족하지 못한 채 조회성 shell만 반복하면 다음 iteration에 교정 피드백을 주입해야 한다.

PowerShell 조회성 shell 후보:

- `Get-ChildItem`
- `gci`
- `dir`
- `Get-Content`
- `gc`
- `type`
- `Select-String`
- `sls`

Linux shell 조회성 후보:

- `find`
- `cat`
- `ls`
- `tree`
- `head`
- `tail`
- `sed -n`
- `rg`
- `grep`

판정 조건:

- 미충족 기준 중 `file_exists` 또는 `file_contains`가 있다.
- 최근 `AGENT_READONLY_DRIFT_N`개 iteration의 성공 액션이 모두 조회성 shell이거나 실행 액션 없음이다.
- 해당 기간 동안 성공한 file action이 없다.

환경변수:

- `AGENT_READONLY_DRIFT_N`
- 기본값: `3`
- 허용 범위: `2..10`

동작:

- stop_reason을 즉시 설정하지 않는다.
- 다음 프롬프트에 `[READONLY_DRIFT_GUARD]` 블록을 추가한다.
- 블록은 “조회 결과를 바탕으로 남은 완료 기준을 우선 처리하라”고 지시한다.
- shell 예시는 실행 환경에 맞춰 PowerShell 기본 구문을 우선 안내하고, Linux/WSL에서는 Linux shell 구문을 안내한다.

### FR-073-05. 파싱 불가 ACTION 실패 처리

`AgentActionDispatcher.dispatch()`는 `act_text.strip()`이 비어 있지 않은데 `_parse()` 결과가 비어 있으면 실패 `ActionResult`를 반환해야 한다.

반환 예:

```python
ActionResult(
    kind="code",
    target="dispatcher",
    success=False,
    detail="파싱 가능한 ACTION이 없습니다. 파일 작업은 @@@filename:path ... @@@ 또는 @@@patch:path ... @@@, shell은 '$ command' 형식을 사용하세요.",
)
```

이 실패는 기존 `_has_code_failure()`에 의해 self-correction을 유도해야 한다.

### FR-073-06. PLAN criteria 보강은 선택 기능으로 도입

초기 PLAN 프롬프트는 모델이 원하면 `@@@criteria` 블록을 추가할 수 있음을 안내한다. 단, 모델 기준은 기존 `AgentGoalEvaluator.parse_model_criteria()`의 보안 제한을 그대로 따른다.

필수 요구:

- extracted 기준은 계속 우선한다.
- 모델 기준은 add-only 병합만 허용한다.
- `cmd_exit_zero` 모델 기준은 테스트 러너 형태만 허용한다.

비고:

- 특정 문서 파일명이나 문서 품질 검증을 강제하기 위해 LLM-only 기준을 남발하지 않는다.
- 이번 버그의 직접 해결책은 `FR-073-01`부터 `FR-073-05`다.

### FR-073-07. Shell 힌트는 PowerShell 기본, Linux 지원

`/agents`의 system prompt와 read-only drift guard는 OS별 shell hint를 존중해야 한다.

- Windows/PowerShell 환경: PowerShell 명령 예시를 기본으로 안내한다.
- Linux/WSL 환경: Linux shell 명령 예시를 안내한다.
- 모델이 shell 구문을 잘못 섞으면 dispatcher/self-correction 경로에서 올바른 실행 환경 구문을 재요청한다.

## 6. 설계

### 6.1 Agent history 보존

흐름:

1. `MAX_AGENT_MESSAGES_TO_KEEP`를 로드한다.
2. `/agents` 모델 호출 전 agent history trim에는 `MAX_AGENT_MESSAGES_TO_KEEP`를 사용한다.
3. 일반 대화 history trim에는 기존 `MAX_MESSAGES_TO_KEEP`를 계속 사용한다.
4. provider assistant의 공용 `chat()` 경로를 그대로 사용해야 한다면, `AgentRunner._call_model()`에서 agent 호출에 한정해 trim limit override를 전달하거나 Agent 전용 trim 유틸을 호출한다.
5. 전역 `TokenManager.MAX_MESSAGES_TO_KEEP`를 임시 변경하는 방식은 사용하지 않는다.

권장 구현:

```python
TokenManager.auto_trim_history(
    session.agent_history,
    max_tokens=...,
    max_messages=TokenManager.MAX_AGENT_MESSAGES_TO_KEEP,
)
```

`auto_trim_history()`가 `max_messages` 인자를 받지 않는다면 이를 추가한다. 기존 호출부는 인자를 생략해 기존 `MAX_MESSAGES_TO_KEEP` 동작을 유지한다.

### 6.2 Acceptance criteria prompt block

신규 헬퍼:

```python
def _build_acceptance_criteria_block(self, session: AgentSession) -> str:
    ...
```

입력:

- `session.acceptance_criteria`

출력:

- 기준이 없으면 빈 문자열
- 기준이 있으면 `[ACCEPTANCE_CRITERIA]` 블록

상태 계산:

- `c.passed is True` -> `passed`
- `c.passed is False` -> `failed`
- 그 외 -> `unknown`

`_probe_criteria()`가 아직 실행되지 않은 첫 iteration에서도 기준 target은 표시한다.

### 6.3 Read-only drift detection

신규 헬퍼:

```python
def _build_readonly_drift_guard(self, session: AgentSession, probe_snapshot) -> str:
    ...
```

또는 `_build_iteration_prompt()` 내부에서 `session.iterations`와 `probe_snapshot`을 함께 검사한다.

주의:

- 조회성 shell 반복을 실패로 간주하지 않는다.
- 모델에게 남은 작업 우선순위를 재정렬하는 프롬프트 가드로만 사용한다.
- file/patch action이 한 번이라도 성공하면 guard 카운트를 리셋한다.
- shell 조회 명령 판정은 PowerShell 후보와 Linux 후보를 모두 지원한다.

### 6.4 Dispatcher parse failure

`AgentActionDispatcher.dispatch()`에서 `_parse()` 직후 다음 분기를 추가한다.

```python
if act_text.strip() and not actions:
    return [ActionResult(... success=False ...)]
```

이 변경은 malformed ACTION을 self-correction 경로로 보내는 목적이다.

### 6.5 Shell environment hint

`get_os_shell_hint()`와 `TerminalExecutor.agent_shell_brief()`의 결과를 기준으로 모델에게 현재 shell 구문을 안내한다. `/agents` 문구는 “PowerShell 기본, Linux 지원” 전제를 유지하되 실제 실행 환경이 Linux이면 Linux 명령 예시를 사용한다.

## 7. UX 변경

정상 사용자는 추가 입력을 요구받지 않는다.

모델이 읽기 명령만 반복하면 다음 iteration 프롬프트에 내부 제어 블록이 들어가며, 콘솔에는 필요 시 다음과 같은 짧은 안내만 출력한다.

```text
⚠️ 조회성 액션 반복 감지 — 미충족 산출물 기준을 우선하도록 다음 프롬프트에 반영합니다.
```

`MAX_MESSAGES_TO_KEEP`가 낮더라도 `/agents`는 `MAX_AGENT_MESSAGES_TO_KEEP`를 사용한다. 값이 서로 다르면 `/agents` 시작 또는 첫 모델 호출 시 1회만 안내한다.

```text
ℹ️ /agents는 일반 대화 MAX_MESSAGES_TO_KEEP=1 과 별개로 MAX_AGENT_MESSAGES_TO_KEEP=30 을 사용합니다.
```

## 8. 테스트 계획

### 단위 테스트

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| T-073-01 | `MAX_MESSAGES_TO_KEEP=1`, `MAX_AGENT_MESSAGES_TO_KEEP=30`에서 `/agents` 모델 호출 | agent history는 30 기준으로 trim, 일반 history 설정은 변경 없음 |
| T-073-02 | `session.acceptance_criteria`에 `file_exists:docs/output.md` 존재 | `_build_iteration_prompt()`에 `[ACCEPTANCE_CRITERIA]` 포함 |
| T-073-03 | 첫 iteration, criteria 평가 전 | 상태 `unknown`으로 기준 표시 |
| T-073-04 | probe 후 `docs/output.md` failed | 기준 블록에 failed/evidence 및 target 표시 포함 |
| T-073-05 | 최근 3회가 `Get-ChildItem`, `Get-Content`, `Select-String`이고 file 기준 미충족 | `[READONLY_DRIFT_GUARD]` 주입 |
| T-073-06 | 최근 iteration에 file action 성공 존재 | read-only drift guard 미주입 |
| T-073-07 | 최근 3회가 `find`, `cat`, `rg`이고 file 기준 미충족 | Linux 조회성 액션으로 판정해 `[READONLY_DRIFT_GUARD]` 주입 |
| T-073-08 | `act_text="sh\ncat docs/output.md"` | dispatcher 실패 ActionResult 반환 |
| T-073-09 | dispatcher 실패 ActionResult | `_has_code_failure()`가 True 반환 |
| T-073-10 | PLAN에 안전한 `@@@criteria file_exists:docs/output.md` 포함 | model criterion 파싱/병합 |
| T-073-11 | PLAN에 비테스트 `cmd_exit_zero:python build.py` 포함 | 기존 보안 정책대로 무시 |

### 통합 테스트

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| IT-073-01 | fake assistant가 `MAX_MESSAGES_TO_KEEP=1`, `MAX_AGENT_MESSAGES_TO_KEEP=30`에서 산출 파일 생성 요청 수행 | 최종 `DONE`, 요청된 산출 파일 포함 |
| IT-073-02 | fake assistant가 조회 명령만 3회 반복 | read-only drift guard 이후 file action으로 전환 |
| IT-073-03 | fake assistant가 malformed ACTION 출력 | self-correction 후 올바른 ACTION 재시도 |
| IT-073-04 | PowerShell 환경에서 조회성 명령 반복 | PowerShell 후보로 drift 판정 |
| IT-073-05 | Linux/WSL 환경에서 조회성 명령 반복 | Linux 후보로 drift 판정 |

## 9. 수용 기준

- `MAX_MESSAGES_TO_KEEP=1`이어도 `/agents`는 `MAX_AGENT_MESSAGES_TO_KEEP` 기준으로 필수 목표, PLAN, 완료 기준, 최근 관찰을 유지한다.
- 파일 생성/작성 목표의 첫 iteration 프롬프트에 해당 target 완료 기준이 포함된다.
- 모델이 조회 명령만 반복하면 남은 완료 기준을 우선하라는 guard가 주입된다.
- malformed ACTION은 조용히 무시되지 않고 self-correction으로 이어진다.
- 기존 `MAX_MESSAGES_TO_KEEP=30` 정상 흐름은 회귀하지 않는다.
- PowerShell 기반 환경과 Linux/WSL 환경 모두에서 조회성 shell 판정과 shell 힌트가 올바르게 동작한다.
- 기존 보안 정책, 위험 shell 승인 정책, `@@@filename`/`@@@patch` 저장 정책은 유지된다.

## 10. 리스크와 완화

| 리스크 | 설명 | 완화 |
|---|---|---|
| 프롬프트 과밀 | 기준 블록 추가로 매 iteration 프롬프트가 길어짐 | 기준은 최대 32개 기존 상한, evidence 160자 제한 |
| 과도한 산출물 작업 유도 | 탐색이 더 필요한 상황에서 action을 서두를 수 있음 | read-only drift는 N회 반복 후에만 발동, 즉시 중단하지 않음 |
| trim 설정 혼동 | `MAX_MESSAGES_TO_KEEP`와 `MAX_AGENT_MESSAGES_TO_KEEP`의 역할이 혼동될 수 있음 | `/tokens`와 `/agents` 안내 문구에 역할 분리 명시 |
| shell 후보 누락 | PowerShell/Linux 조회성 명령 변형을 놓칠 수 있음 | 후보 목록을 보수적으로 시작하고 실제 로그 기반으로 확장 |
| malformed ACTION 실패가 너무 엄격 | 설명만 하는 응답도 실패로 잡힐 수 있음 | 대상은 `[ACTION]` 블록 내부의 non-empty act_text이며, PLAN 응답에는 적용하지 않음 |

## 11. 구현 파일

예상 수정 파일:

- `src/agent_runner.py`
  - `MAX_AGENT_MESSAGES_TO_KEEP` 기반 agent history trim
  - acceptance criteria block
  - read-only drift guard
  - PLAN criteria 안내
- `src/token_manager.py`
  - `MAX_AGENT_MESSAGES_TO_KEEP` 로딩
  - `auto_trim_history(..., max_messages=...)` 선택 인자
- `src/agent_action_dispatcher.py`
  - 파싱 불가 ACTION 실패 결과
- `tests/test_agent_runner.py`
  - 프롬프트/히스토리 guard 테스트
- `tests/test_agent_action_dispatcher.py`
  - malformed ACTION 테스트
- 필요 시 `tests/test_agent_refine_loop.py`
  - read-only drift guard 통합 테스트

## 12. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v1.1.073 | 2026-06-27 | BUG v1.1.072 후속 FSD 작성. `MAX_MESSAGES_TO_KEEP=1` 원인 확인 후 agent 전용 히스토리 보존, 완료 기준 상시 주입, read-only drift guard, malformed ACTION 실패 처리 요구사항 정의 |
| v1.1.073-r1 | 2026-06-27 | `MAX_AGENT_MESSAGES_TO_KEEP` 독립 설정으로 변경, 제외 범위 섹션 삭제, 특정 파일 생성 강제 표현 제거, `/agents` shell 기본 PowerShell 및 Linux 지원 요구사항 반영 |
>>>>>>> Stashed changes
