# FSD v1.1.034 — `/agents` 응답 잘림(truncation) 처리 및 루프 응답 분기 개선

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1.034 |
| 작성일 | 2026-06-21 |
| 상태 | 📝 **문제 분석 / 개선 요구 (구현 미착수)** |
| 선행 문서 | REP v1.1.032(평가 게이트), FSD v1.0.083(자율 루프), v1.0.107(디스패처), v1.0.115(patch) |
| 관련 모듈 | `src/agent_runner.py`, `src/agent_goal_evaluator.py`, `src/agent_action_dispatcher.py`, `src/claude_assistant.py`·`gemini_assistant.py`·`genai_assistant.py` |
| 비고 | 본 문서는 **문제 분석 + 개선 요구사항** 만 정리한다. 구현 코드는 포함하지 않는다. |

---

## 1. 증상 (관찰된 현상)

장문(긴 코드 다수 파일) 목표 실행 시, **모델 응답이 토큰 한도로 중간에 잘려** 다음과 같이 종료된다.

```
@@@filename:src/main/java/com/siis/scheduler/db/MyBatisUtil.java
package com.siis.scheduler.db;
...
        SqlSessionFactory factory = factoryCache.computeIfAbsent(dbAlias, key -> {
            synchronized (MyBatisUtil.class) {
                if (factoryCache.containsKey(key)) {
                    return factoryCache.get(key);
                }
                return createSqlSessionFactory(        ← 여기서 응답이 끊김 (닫는 @@@ 없음)

⛔ 검증 가능한 완료 기준을 확정하지 못했습니다.
💾 세션 저장: agent_20260621_183444_FSD_v1_0_001_JAVA8_SCHEDULER.json
============================================================
✅ 에이전트 종료 (stop_reason=goal_unverified, 0 iterations)
📁 생성/수정 파일: 없음
🎯 완료 기준 검증:
  - A1 [extracted/pending] 요청된 테스트가 실제로 실행되어 모두 통과해야 함 —
  - A2 [extracted/pending] 요청된 완료 보고서가 워크스페이스에 존재해야 함 —
============================================================
```

**정상 형식** vs **비정상(잘림) 형식**:

```
정상:                          비정상(잘림):
@@@filename:경로/파일.확장자     @@@filename:경로/파일.확장자
코드 내용 ...                    코드 내용 ...
@@@                            (닫는 @@@ 없이 응답 종료)
```

핵심: **응답이 `@@@` 로 닫히기 전에 토큰 한도로 잘리고**, 그 결과 에이전트가 **0 iteration 에서 `goal_unverified` 로 즉시 포기**한다. 생성된 파일은 0개.

---

## 2. 근본 원인 분석 (소스 검증)

### 2.1 원인 체인

```
① 모델이 PLAN 단계(Step 0)에서 '계획' 대신 전체 파일 구현을 덤프
   (목표가 "전체 코드 구현 및 완료 보고서" 이므로 모델이 곧장 코드 출력)
        │
② 출력이 Provider 토큰 한도 초과 → 응답이 @@@filename 블록 중간에서 잘림
   (Claude: max_tokens=4096 하드코딩 — claude_assistant.py:217,252)
        │
③ assistant.chat() 은 str 만 반환 → 잘림 여부(finish_reason)가 runner 로 전달 안 됨
   (agent_runner.py:820-839 _call_model — finish_reason/stop_reason 미수신)
        │
④ 잘린 PLAN 이 _initialize_acceptance_criteria() 로 전달 → 완료 기준 확정 실패(False)
        │
⑤ run() 이 GOAL_UNVERIFIED 로 즉시 종료 (agent_runner.py:288-294) — iteration 0
        │
⑥ 닫히지 않은 @@@filename 블록은 디스패처가 폐기 → 파일 미저장
   (agent_action_dispatcher.py _parse: depth != 0 → 블록 무시)
```

### 2.2 모듈별 결함

| # | 위치 | 결함 | 영향 |
|---|---|---|---|
| C1 | `claude_assistant.py:217,252` 등 | `max_tokens: 4096` **하드코딩**, env 미연동 | 장문 멀티파일 응답이 쉽게 잘림 |
| C2 | `agent_runner.py:820-839` `_call_model` | `chat()` 반환이 `str` 뿐 — **finish_reason/stop_reason 미수신** | runner 가 잘림을 인지 불가 (가장 근본) |
| C3 | `agent_action_dispatcher.py` `_parse` | `depth != 0`(닫히지 않은 펜스) → **블록 조용히 폐기** | 잘린 파일의 부분 코드 손실, 저장 0건 |
| C4 | `agent_runner.py:288-294` | `_initialize_acceptance_criteria()==False` → **즉시 GOAL_UNVERIFIED 종료** | 작업 시작 전 0 iteration 포기 |
| C5 | `agent_runner.py:281-286` PLAN 단계 | PLAN 프롬프트가 "계획만" 을 강제하지 않음 → 모델이 전체 코드 덤프 | Step 0 응답 비대 → 잘림 유발 |
| C6 | `agent_goal_evaluator.py:759-769` `_finalize_goal` | "응답 미완성" 과 "목표 미달성" 을 구분하지 않음 | 잘림이 목표 평가 결과로 오분류 |

### 2.3 설계상 핵심 결함

**루프가 모델 응답을 단일 경로로만 처리한다.** 현재 `run()` 은 응답을 받으면 곧바로 (PLAN 단계) 기준 확정 또는 (iteration) 액션 실행/완료 게이트로 보낸다. **"응답이 완전한가?"** 를 먼저 분기하는 단계가 없다. 그래서 *불완전 응답(truncation)* 이 *목표 평가 실패(GOAL_UNVERIFIED/GOAL_NOT_MET)* 로 잘못 매핑된다.

> **truncation 은 종료 사유가 아니라 "응답을 이어받아야 하는 상태" 이다.** 이를 평가 게이트로 보내는 것이 설계 오류의 본질이다.

---

## 3. 개선 요구사항 (FR)

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-034-01 | 모델 응답의 **잘림(truncation)** 을 감지한다. 1순위: Provider 의 finish_reason/stop_reason(`MAX_TOKENS`/`max_tokens`/`length`)을 `chat()` 을 통해 runner 로 전달. 2순위(폴백): 휴리스틱(불균형 `@@@` 펜스, 응답이 열린 `@@@filename:`/`@@@patch:` 블록 안에서 종료). | 필수 |
| FR-034-02 | 잘림이 감지되면 **`GOAL_NOT_MET` / `GOAL_UNVERIFIED` 로 종료하지 않는다.** 잘림은 별도의 비종료(continuation) 상태로 처리한다. | 필수 |
| FR-034-03 | 잘린 응답에서 **닫히지 않은 마지막 `@@@filename:`/`@@@patch:` 블록(불완전 블록)은 출력/파싱/저장에서 제외**한다. 이미 `@@@` 로 닫힌 완전한 블록은 정상 저장한다. | 필수 |
| FR-034-04 | 잘림 발생 시 **다음 iteration 에서 이어서 처리**한다. 잘린 파일(및 그 이후 미작성 파일)을 다음 요청 프롬프트에 명시해 모델이 **해당 파일부터 다시 완전한 블록으로 출력**하도록 가이드한다. | 필수 |
| FR-034-05 | 잘린 PLAN(Step 0)이 **완료 기준 확정을 방해하지 않도록** 한다. 불완전 블록 제거 후 기준을 추출하며, 기준이 실제로 추출되었으면(예: A1/A2) **0 iteration 종료를 하지 않고 루프를 진행**한다. | 필수 |
| FR-034-06 | continuation 은 **완료 주장(DONE)·거부(reject) 예산을 소모하지 않는다.** 무한 잘림 루프 방지를 위해 `AGENT_MAX_CONTINUATIONS`(기본 예: 3) 상한을 둔다. | 필수 |
| FR-034-07 | PLAN 단계 프롬프트는 **"계획만" 출력**을 강제하고 파일 전문 덤프를 금지한다(파일은 iteration 에서 생성). 이를 통해 Step 0 응답 비대를 예방한다. | 권장 |
| FR-034-08 | Provider 출력 토큰 한도(`max_tokens`)를 **env 로 설정 가능**하게 하고 합리적 상향 기본값을 둔다(잘림 빈도 감소). | 권장 |
| FR-034-09 | 한 iteration 에서 **파일 1~소수 개씩** 생성하도록 가이드해 응답 크기를 제한한다. | 권장 |

### 3.1 비기능/제약

- NFR-034-01: Provider 독립 — 세 어시스턴트(gemini/claude/gen-ai)에서 동일하게 동작.
- NFR-034-02: 기존 동작 회귀 없음 — 잘림이 없는 정상 응답은 현행 경로 그대로.
- NFR-034-03: `unittest` 만 사용, 신규 의존성 없음.
- NFR-034-04: continuation 으로 인한 부분 코드/히스토리 오염 없음(불완전 블록은 agent_history·저장에서 일관 제외).

---

## 4. 개선안 (권장 설계 방향)

### 4.1 응답 분류 기반 루프 분기 (핵심 — 더 나은 방안)

현재의 "응답 → 곧장 게이트" 단일 경로를, **응답 분류 → 분기** 구조로 바꾼다.

```
응답 수신
   │
   ▼
_classify_response(response, finish_reason) → {COMPLETE | TRUNCATED | EMPTY}
   │
   ├─ COMPLETE  → (기존) 액션 실행 → Observe → [AGENT_DONE] 게이트 → 사용자 개입
   │
   ├─ TRUNCATED → ① 완전한 @@@블록만 저장 / 불완전 꼬리 제거
   │              ② continuation 프롬프트 주입(잘린 파일부터 재출력 지시)
   │              ③ 게이트/거부예산 건드리지 않고 continue
   │              ④ AGENT_MAX_CONTINUATIONS 초과 시에만 별도 처리
   │
   └─ EMPTY     → 1회 재요청(reprompt)
```

이 분기는 **"불완전 응답" 과 "목표 평가" 를 분리**하여 C4·C6 의 오분류를 근본 해소한다.

### 4.2 잘림 감지 (FR-034-01)

| 방안 | 설명 | 비고 |
|---|---|---|
| **A. finish_reason 전달 (권장)** | 각 Provider 의 종료 사유(Gemini `finishReason=MAX_TOKENS`, Claude `stop_reason=max_tokens`, GenAI 상응값)를 `chat()` 이 반환하거나 `assistant.last_finish_reason` 로 노출 → runner 가 판독 | 정확. 약간의 인터페이스 확장 필요(C2 해소) |
| **B. 휴리스틱 폴백** | `@@@` 펜스 개수 불균형 / 응답이 열린 `@@@filename:`·`@@@patch:` 안에서 종료 / `[OBSERVE]`·`[AGENT_DONE]` 부재로 종료 | 신호 미제공 Provider 대비 안전망 |

> **권장: A + B 병행.** A 를 1순위, 미지원/불명확 시 B 로 보강.

### 4.3 불완전 블록 제거 (FR-034-03)

- 응답에서 **마지막으로 열렸으나 닫히지 않은** `@@@filename:`/`@@@patch:` 블록을 식별해 그 시작 지점부터 잘라낸다.
- 그 앞의 **완전히 닫힌** 블록들은 정상적으로 디스패처/패처로 전달해 저장.
- agent_history 에 누적되는 응답도 동일하게 불완전 꼬리를 제외해 다음 호출 컨텍스트 오염 방지.

### 4.4 continuation 프롬프트 (FR-034-04)

다음 iteration 프롬프트에 다음을 명시한다(예시 문안):

```
[CONTINUATION]
직전 응답이 토큰 한도로 잘렸습니다.
- 마지막으로 완성된 파일: <닫힌 파일 목록>
- 잘린 파일: <path> (이 파일은 저장되지 않았습니다)
지시:
1) 잘린 <path> 부터 다시 **완전한 @@@filename:...@@@ 블록**으로 출력하세요.
2) 이미 완성·저장된 파일은 반복하지 마세요.
3) 한 번에 1~2개 파일만 출력해 응답이 잘리지 않게 하세요.
```

- 잘린 파일 경로는 세션 상태(예: `session.pending_file` / `continuation_count`)에 보관.
- continuation iteration 은 **완료 게이트·거부 예산을 건드리지 않는다**(FR-034-06).

### 4.5 게이트 타이밍 교정 (FR-034-05 / C4·C5)

- `_initialize_acceptance_criteria()` 가 False 라도 **0 iteration 즉시 종료를 지양**한다.
  - 기준이 실제 추출됨(A1/A2 등)에도 잘린 PLAN 때문에 `malformed`/혼란으로 False 가 되는 경로를 차단.
  - 잘림이면 4.1 의 TRUNCATED 경로로 보내 PLAN 을 이어받게 한다(기준 확정은 완전한 PLAN 확보 후).
- PLAN 단계는 "계획만" 출력하도록 프롬프트를 강화(FR-034-07)해 Step 0 잘림 자체를 예방.

### 4.6 잘림 예방 (방어적, FR-034-08/09)

- `max_tokens` env 연동 + 상향(예: `AGENT_MAX_OUTPUT_TOKENS`).
- iteration 당 파일 수 제한 가이드(1~2개).

---

## 5. 변경 영향 범위 (예상)

| 파일 | 예상 변경 | 비고 |
|---|---|---|
| `src/agent_runner.py` | `_classify_response` 도입, 루프 분기, continuation 상태/프롬프트, 게이트 타이밍 교정, PLAN 프롬프트 강화 | 핵심 |
| `src/agent_goal_evaluator.py` | "응답 미완성" 과 "목표 미달성" 분리(잘림은 평가 대상 아님) | C6 |
| `src/claude_assistant.py`·`gemini_assistant.py`·`genai_assistant.py` | finish_reason/stop_reason 노출, `max_tokens` env 연동 | C1·C2 |
| `src/agent_action_dispatcher.py` | 불완전 펜스 제외 정책 명시(현재도 폐기하나, "잘림 보고" 신호 제공 고려) | C3 |
| `AgentSession` | `continuation_count` 등 상태 필드(직렬화/Resume 시 초기화) | — |

> ⚠️ 인터페이스 확장(`chat()` finish_reason)은 세 Provider 공통 변경이므로 후방호환(기존 호출부) 보장 필요.

---

## 6. 검증 / 테스트 시나리오 (구현 시 추가, `python -m unittest`)

| # | 시나리오 | 기대 |
|---|---|---|
| T-034-01 | finish_reason=MAX_TOKENS 응답 | `_classify_response` → TRUNCATED |
| T-034-02 | 닫히지 않은 `@@@filename:` 로 끝나는 응답(신호 없음) | 휴리스틱으로 TRUNCATED 판정 |
| T-034-03 | 잘린 응답 처리 | `GOAL_NOT_MET`/`GOAL_UNVERIFIED` 로 종료하지 않음(FR-034-02) |
| T-034-04 | 잘린 응답에 완전 블록 1개 + 불완전 블록 1개 | 완전 블록만 저장, 불완전 블록 제외(FR-034-03) |
| T-034-05 | 잘림 후 다음 iteration 프롬프트 | `[CONTINUATION]` + 잘린 파일 경로 포함(FR-034-04) |
| T-034-06 | 잘린 PLAN + 기준 추출됨(A1/A2) | 0 iteration 종료 안 함, 루프 진행(FR-034-05) |
| T-034-07 | continuation 반복 | DONE/거부 예산 미소모, `AGENT_MAX_CONTINUATIONS` 초과 시에만 종료(FR-034-06) |
| T-034-08 | 정상(완전) 응답 | 기존 경로 그대로(회귀 없음, NFR-034-02) |
| T-034-09 | agent_history 오염 검사 | 불완전 꼬리가 히스토리에 누적되지 않음(NFR-034-04) |
| T-034-10 | PLAN 단계 프롬프트 | "계획만" 지시 포함, 파일 덤프 억제 가이드(FR-034-07) |

---

## 7. 잔여 리스크 / 결정 필요 사항

1. **부분 코드 활용 여부:** 잘린 파일의 부분 코드를 (a) 폐기하고 처음부터 재출력(단순·권장) vs (b) 스크래치에 보존해 이어쓰기(복잡). 1차는 (a) 권장 — "해당 파일부터 다음 응답으로 재처리".
2. **finish_reason 표준화:** 세 Provider 의 종료 사유 명칭이 달라 매핑 테이블 필요(공통 enum 권장).
3. **continuation 과 iteration 카운트:** continuation 을 iteration 으로 셀지 여부 — 셈하지 않되 별도 상한(`AGENT_MAX_CONTINUATIONS`)으로 무한루프 방지 권장.
4. **PLAN 의 코드 덤프 성향:** 모델이 지시를 무시하고 코드를 덤프하는 경향 — 프롬프트 강화 + Step 0 응답 길이 모니터링 병행.
5. **휴리스틱 오탐:** 정상 응답이 우연히 `@@@` 불균형(예: 본문 내 `@@@` 문자열)일 가능성 — finish_reason 우선, 휴리스틱은 보조로 한정.

---

## 8. 우선순위 요약

```
P1 (필수, 즉시) — 오분류 차단:
  FR-034-02  truncation → GOAL_* 종료 금지
  FR-034-05  잘린 PLAN 의 0-iteration 종료 방지
  FR-034-01  truncation 감지(finish_reason + 휴리스틱)
  FR-034-03  불완전 블록 제외

P2 (필수, 연속) — 이어받기:
  FR-034-04  continuation 프롬프트(잘린 파일부터 재출력)
  FR-034-06  continuation 예산/상한
  4.1        응답 분류 기반 루프 분기 도입

P3 (권장) — 예방:
  FR-034-07  PLAN "계획만" 강제
  FR-034-08  max_tokens env 연동/상향
  FR-034-09  iteration 당 파일 수 제한
```

---

## 9. 승인

- [x] 문제 분석 (2026-06-21)
- [x] 개선 방안 확정 (4.1 응답 분류 분기 + 4.2 감지 방식) — 2026-06-21
- [x] 구현 (P1 → P2 → P3) — 2026-06-21
- [x] 테스트 (T-034-01 ~ T-034-10) — 32/32 통과 (2026-06-21)
- [ ] 문서 반영(RELEASE 노트)

## 10. 구현 결과 (2026-06-21)

### 변경 파일 요약

| 파일 | 변경 내용 |
|---|---|
| `src/claude_assistant.py` | `last_finish_reason` 속성, `message_delta` stop_reason 캡처, non-streaming stop_reason 캡처, `AGENT_MAX_OUTPUT_TOKENS` env 연동 |
| `src/gemini_assistant.py` | `last_finish_reason` 속성, streaming/non-streaming `finishReason` 캡처, `AGENT_MAX_OUTPUT_TOKENS` env 연동 |
| `src/genai_assistant.py` | `last_finish_reason` 속성, `chat()` 진입 시 리셋 |
| `src/agent_runner.py` | `AgentSession.continuation_count/pending_truncated_file`, `AgentRunner.max_continuations`, `_classify_response()`, `_has_unclosed_fence()`, `_strip_incomplete_fence_tail()`, `_handle_truncated_response()`, `_build_continuation_prompt()`, `run()` PLAN 분기·criteria 종료 억제·iteration 잘림 분기, `_build_initial_prompt()` "계획만" 제한 |
| `tests/test_agent_truncation.py` | T-034-01 ~ T-034-10 (32 케이스) 신규 |

### 환경 변수 (신규)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `AGENT_MAX_OUTPUT_TOKENS` | 4096 (Claude) / 8192 (Gemini) | Provider max_tokens 상향 가능 |
| `AGENT_MAX_CONTINUATIONS` | 3 | 연속 잘림 이어받기 최대 횟수 |

### 검증 결과

```
tests/test_agent_truncation.py  32 passed (0.80s)
회귀 테스트 (6개 파일)         183 passed, 9 subtests passed (3.56s)
```
