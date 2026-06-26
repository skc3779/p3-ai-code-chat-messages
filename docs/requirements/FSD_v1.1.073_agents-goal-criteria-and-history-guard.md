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
