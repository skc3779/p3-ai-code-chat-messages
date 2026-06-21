# FSD v1.1.041 — `/agents` 대화형·자율 하이브리드 루프 에이전트

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1.041 |
| 작성일 | 2026-06-22 |
| 상태 | 📝 개선 설계 (AS-IS 정리 + TO-BE 설계, 구현 미착수) |
| 선행 문서 | FSD v1.0.083(자율 루프), v1.0.087(async stop), v1.0.100(bypass), v1.0.101(max-iter/resume), v1.0.107(디스패처), v1.0.115(patch), **v1.1.032(평가 게이트)**, **v1.1.033(patch fuzzy)**, **v1.1.034(잘림 처리)** |
| 관련 모듈 | `src/agent_runner.py`, `src/agent_action_dispatcher.py`, `src/agent_goal_evaluator.py`, `src/agent_patch_applier.py`, `src/agent_input_listener.py`, `src/agent_session_store.py`, `src/agents_command.py`, `src/claude_assistant.py`·`gemini_assistant.py`·`genai_assistant.py` |
| 비고 | 본 문서는 **AS-IS 통합 흐름 정리 + TO-BE 개선 설계 + 검증/테스트 케이스**를 포함한다. 구현은 별도 승인 후 진행한다. |

---

## 1. 목적 / 배경

`/agents` 는 상위 목표를 받아 ReAct(Reason→Act→Observe) 사이클로 자율 수행하는 루프 에이전트다. v1.1.032~034 에서 **완료 기준 검증 게이트 · 패치 유사도 매칭 · 응답 잘림 처리**가 차례로 보강되며 "끝까지 자율 실행" 측면은 견고해졌다.

그러나 현재 루프의 **사용자 경험(UX)** 은 Codex CLI / Claude Code 와 거리가 있다.

- 진행 상황이 `print` 블록으로만 흐르고, **계획 대비 진척도(어디까지 했는지)** 가 한눈에 안 보인다.
- 사용자 개입은 **iteration 사이의 동기 input(c/f/b/s)** 한 가지뿐이고, **실행 중간 끼어들기(steer)** 는 's'(중단)만 가능하다.
- 파일 변경 **diff 미리보기 없이** 곧장 저장된다(위험 파일만 승인).
- 승인 정책이 `bypass on/off` **이진(binary)** 이라, "편집은 자동·셸은 확인" 같은 **중간 단계**가 없다.
- 실행 **시작 전 PLAN 승인 게이트**가 없어, 모델이 잘못된 계획으로 바로 작업에 들어간다.

본 문서는 (A) v1.1.032~034 + 기존 FSD 가 구성하는 **AS-IS 통합 아키텍처 흐름**을 누락 없이 정리하고, (B) 이를 토대로 **대화형(step-by-step)과 자율(autonomous)을 모두 지원하는 하이브리드 루프**의 TO-BE 개선을 설계한다.

---

## 2. AS-IS — 통합 아키텍처 흐름

### 2.1 전체 파이프라인

```text
/agents [-ba] [-s N] [pattern]                         (agents_command.py)
   │  플래그 추출(-ba bypass, -s steps) → 멀티라인 목표 수집 → 패턴 매칭
   ▼
AgentRunner.run(goal, file_patterns, bypass, max_iter_override)
   │
   ├─ [Step 0] PLAN 생성 ───────────────────────────────────────────────┐
   │     _build_initial_prompt(goal, file_context)                       │ ① 목표 프롬프트
   │       · "계획 목록만" 강제 (v1.1.034 FR-034-07)                      │
   │       · @@@criteria 블록으로 모델 추가 기준 허용                       │
   │     _call_model() → 응답                                            │
   │     _classify_response() → COMPLETE | TRUNCATED | EMPTY (v1.1.034)  │ ④ 잘림 처리
   │       · TRUNCATED 면 불완전 꼬리 제거 + 이어받기 예약               │
   │                                                                     │
   ├─ [완료 기준 초기화] _initialize_acceptance_criteria() (v1.1.032) ────┤ ② 완료 기준
   │     · extract_from_goal(): 목표→권위(extracted) 기준 결정론 추출      │
   │     · parse_model_criteria(PLAN): 모델 추가(model) 기준 add-only      │
   │     · 3-tier provenance 병합(_merge_criteria, 최대 32개)             │
   │     · 기준 0개/오류 → 1회 재요청 → 그래도 없으면 GOAL_UNVERIFIED      │
   │       (단 PLAN 잘림이면 0-iter 종료 억제, v1.1.034 FR-034-05)        │
   │                                                                     │
   └─ [Step 1..N] ReAct iteration 루프 ─────────────────────────────────┘
         │  체크포인트: async stop('s' 키) 검사 (v1.0.087)
         │  is_continuation? → _build_continuation_prompt() else _build_iteration_prompt()
         │  _call_model() → 응답 → _classify_response()
         │     ├─ TRUNCATED → 완전 블록만 처리 + 이어받기 + continue        ④ 잘림 처리
         │     │              (게이트/거부 예산 미소모, max_continuations)
         │     ├─ EMPTY     → (관대 폴백)
         │     └─ COMPLETE  → 정상 경로
         │  _parse_blocks() → [REASON]/[ACTION]/[OBSERVE]
         │  _execute_actions() → AgentActionDispatcher.dispatch()         ③ 액션 라우팅
         │     · 펜스 파싱(@@@filename:/patch:, ```python/shell)
         │     · _dedupe(): 동일 shell 중복 제거
         │     · 같은 파일 filename+patch 동시 → filename 우선, patch 보고만 ⑤ 중복 파일 필터링
         │     · file  → _save_file_blocks()
         │     · patch → AgentPatchApplier.apply()                         ⑥ 패치 매칭
         │          exact → ambiguous → fuzzy(공백) → similar(difflib) → no_match
         │     · code  → CodeExecutor / shell → TerminalExecutor(위험검사)
         │  Self-Correction: 코드/패치 실패 시 최대 N회 재시도
         │  [AGENT_DONE]? → _finalize_goal() 게이트                        ② 완료 기준 게이트
         │     ├─ all passed     → DONE
         │     ├─ unverified     → GOAL_UNVERIFIED
         │     └─ unmet          → feedback 주입 → reject cap → GOAL_NOT_MET
         │  bypass? → _check_bypass_safety()(시간/정체/루프/위험한도) else _ask_continue()
         ▼
   _auto_save() · _append_summary_to_main_history() · _print_final_summary()
```

### 2.2 6대 핵심 메커니즘 상세

#### ① 목표 프롬프트 (Goal Prompt)
- **시스템 프롬프트**(`_build_system_prompt`): 의사결정 트리 + 선택지 A-1(파일 전문)/A-2(패치)/B(코드)/C(셸). SEARCH 정확 복사·실패 시 A-1 전환 가이드 포함.
- **3종 사용자 프롬프트**:
  - `_build_initial_prompt`: PLAN 단계 — "계획 목록만" 강제, `@@@criteria` 형식 안내.
  - `_build_iteration_prompt`: GOAL/PLAN/FILE_CONTEXT_REF/RECENT OBSERVATIONS/USER_FEEDBACK 조합.
  - `_build_continuation_prompt`: 잘림 이어받기 — 잘린 파일부터 재출력 지시.

#### ② 완료 기준 (Acceptance Criteria) — v1.1.032
- **3-tier provenance**: `extracted`(목표에서 결정론 추출, 권위·불변) → `model`(모델 추가, add-only) → 없으면 `GOAL_UNVERIFIED`.
- **검증 타입**: `file_exists` / `file_contains` / `cmd_exit_zero` / `llm`.
- **shell-free verifier**: 테스트 명령은 `subprocess.Popen(argv, shell=False)` 전용 실행기로만, pytest/unittest allowlist, workspace 봉쇄, zero-test 위장 차단.
- **게이트 통합**: `[AGENT_DONE]` claim 과 iteration cap 모두 동일한 `_finalize_goal()` 분류.

#### ③ 액션 디스패치 (Action Routing) — v1.0.107
- 라인 단위 depth-counting 펜스 파싱(중첩 펜스 안전), `@@@` 마커 지원.
- `[ACTION:file|code|shell]` 명시 태그 우선, `AGENT_ACTION_TAGS_REQUIRED` 모드.
- 단일 경로 라우팅으로 중복 실행 방지.

#### ④ 잘림 처리 (Truncation Handling) — v1.1.034
- **감지**: 1순위 Provider `last_finish_reason`(max_tokens/MAX_TOKENS/length), 2순위 휴리스틱(`@@@` 펜스 불균형).
- **분류 분기**: `COMPLETE | TRUNCATED | EMPTY` — 불완전 응답과 목표 평가를 분리.
- **이어받기**: 불완전 꼬리 제거 + `agent_history` 동기화 + `[CONTINUATION]` 프롬프트, `AGENT_MAX_CONTINUATIONS` 상한, DONE/거부 예산 미소모.

#### ⑤ 중복 파일 필터링 (Duplicate File Filtering) — v1.0.115 FR-111-25
- 같은 iteration 에서 동일 파일을 `@@@filename:` 과 `@@@patch:` 양쪽으로 작성하면 **filename 우선 적용**, patch 는 "filename 우선 적용됨" 으로 보고만.
- shell 액션은 `_dedupe()` 로 동일 payload 1회 축약.

#### ⑥ 패치 매칭 (Patch Matching) — v1.1.033
- cascade: `exact → ambiguous(exact>1) → fuzzy(공백 정규화) → similar(difflib) → no_match`.
- `difflib.SequenceMatcher` sliding window(`n±flex`), quick-ratio 선차단.
- 판정 상수: `TIE_EPSILON=0.01`, `UNIQUENESS_MARGIN=0.05`, `HIGH_CONFIDENCE_RATIO=0.95`.
- transactional: 한 블록이라도 ambiguous/no_match 면 디스크 무변경. CRLF/indent 복원.

### 2.3 문서에 덜 강조됐던 핵심 보조 메커니즘 (보강)

| 메커니즘 | 위치 | 요지 |
|---|---|---|
| **Self-Correction** | `_self_correct_loop` | 코드/셸/패치 실패 시 최대 `AGENT_SELF_CORRECT_MAX`(기본 3)회, 실패 진단을 프롬프트로 주입해 자가 교정 |
| **bypass 안전장치(S2~S5)** | `_check_bypass_safety` | 자율 모드의 4대 가드: 시간 예산(S2)·진행 정체(S3)·반복 루프(S4)·위험 액션 한도(S5). `_BypassAbort` |
| **async stop 리스너** | `agent_input_listener.py` | 데몬 스레드로 's' 키 비동기 감지(TTY only, msvcrt/select). 3개 체크포인트에서 검사 |
| **세션 직렬화/Resume** | `agent_session_store.py` | JSON 저장·복원. Store 는 타입 복원만, 재추출/재평가는 Runner. forged 기준 폐기 |
| **history compaction** | `_compact_history_if_needed` | `AGENT_COMPACT_AFTER` 초과 시 과거 이력을 요약 1쌍으로 압축(산출물 보존) |
| **Provider 독립** | claude/gemini/genai | `chat()` + `conversation_history` + `last_finish_reason` 인터페이스만 요구. history 격리(`_call_model`) |

### 2.4 AS-IS 한계 (TO-BE 동기)

| # | 한계 | 영향 |
|---|---|---|
| L1 | PLAN 을 사용자가 **승인/수정할 게이트 없음** — 생성 즉시 실행 진입 | 잘못된 계획으로 토큰·시간 낭비 |
| L2 | 진행 상황이 선형 로그뿐, **계획 대비 진척도(체크리스트)** 없음 | "어디까지 됐나" 파악 곤란 |
| L3 | 파일 변경 **diff 미리보기 없음** (위험 파일만 y/N/A) | 의도치 않은 대량 수정 인지 지연 |
| L4 | 승인 정책이 **bypass on/off 이진** | "편집 자동·셸 확인" 등 중간 단계 부재 |
| L5 | 실행 **중간 끼어들기**가 's'(중단)뿐 | 방향만 살짝 틀고 싶어도 중단해야 함 |
| L6 | 모드 전환이 **단방향**(c→b 만, 자율→대화 복귀 불가) | 한번 bypass 면 끝까지 자율 |
| L7 | iteration 사이에만 개입 가능(동기 input) | 긴 iteration 도중 통제 불가 |
| **L8** | **능동적 코드 개선 루프 부재** — 코드 개선은 실패 시 Self-Correction(`_self_correct_loop`)과 DONE-거부 피드백뿐. 목표 미달 시 **이미 생성한 코드를 능동적으로 다시 읽고 개선**하는 1급 메커니즘이 없음 | 첫 산출물 품질에 머무름, "추가 개선/수정" 으로 수렴 못 함 |
| **L9** | **생성 코드 재-grounding 부재** — `_build_iteration_prompt` 는 파일 **경로 목록(FILE_CONTEXT_REF)** 만 주입, 편집 후 **최신 파일 본문**을 다시 주지 않음 | 모델이 기억에 의존해 SEARCH 작성 → v1.1.033 표류·패치 실패 반복 |
| **L10** | **미충족 기준 → 대상 파일 연결 부재** — 평가 게이트 실패가 "어느 파일을 고쳐야 하는지" 안내 안 함 | 개선이 산만해지고 엉뚱한 파일 수정 |

---

## 3. TO-BE — 대화형·자율 하이브리드 루프

### 3.1 목표 경험 (UX 기준선)

Codex CLI / Claude Code 의 핵심 UX 요소를 `/agents` 에 이식한다.

| UX 요소 | Codex/Claude Code | TO-BE `/agents` |
|---|---|---|
| 계획 가시화 | Plan 패널 + 체크리스트 | **PLAN 승인 게이트 + 단계 추적기(TODO)** |
| 승인 단계 | `--ask-for-approval` (untrusted/on-failure/on-request/never) | **4단계 승인 정책** |
| 편집 미리보기 | unified diff 표시 후 승인 | **파일 쓰기/패치 diff 미리보기** |
| 실시간 진행 | 스트리밍 reasoning + 진척 | **스트리밍 + live 진척 라인** |
| 끼어들기 | ESC 로 중단 후 지시 주입 | **인터럽트 & 스티어(피드백 주입)** |
| 자율 실행 | `--full-auto` / `never` | **AUTO 모드(기존 bypass 확장)** |
| **코드 반복 개선** | **read→edit→run→observe→edit 수렴** | **자율 코드 개선 루프(재-grounding + 기준 타겟팅)** |

설계 원칙: **단일 루프, 정책으로 분기.** 대화형과 자율은 별도 코드 경로가 아니라 `InteractionPolicy` 값에 따른 분기로 통일한다(AS-IS 의 binary bypass 를 일반화).

### 3.2 승인 정책 모델 (L4 해소)

`InteractionPolicy` enum 도입 — iteration 종료 시점과 액션 실행 직전에 참조.

| 정책 | 의미 | 파일 편집 | 셸/위험 | iteration 일시정지 |
|---|---|---|---|---|
| `interactive` (기본) | 모든 단계 사용자 확인 | diff 후 승인 | 승인 | 매회 정지 |
| `auto-edit` | 편집은 자동, 명령은 확인 | 자동(diff 표시) | 승인 | 정지 안 함(편집), 정지(셸) |
| `on-failure` | 실패·위험 시에만 확인 | 자동 | 위험만 승인 | 실패 시만 정지 |
| `auto` (=기존 bypass) | 완전 자율(안전장치만) | 자동 | 자동(한도 내) | 정지 안 함 |

- CLI 플래그: `/agents --policy <interactive|auto-edit|on-failure|auto>`. `-ba` 는 `--policy auto` 의 별칭으로 **후방호환 유지**.
- 환경변수: `AGENT_INTERACTION_POLICY` (기본 `interactive`).
- `auto` 정책에서는 기존 `_check_bypass_safety()` S2~S5 가 그대로 적용된다.

### 3.3 PLAN 승인 게이트 (L1 해소)

Step 0 직후, 완료 기준 초기화 **이후**, iteration 진입 **전** 게이트 삽입.

```text
PLAN 생성 + 완료 기준 추출
   ▼
PLAN + extracted/model 기준 요약 출력
   ▼  (policy != auto 일 때만)
사용자 선택: [a]pprove / [e]dit(피드백으로 PLAN 재생성) / [r]un-auto(이후 자율) / [s]top
   ├─ approve → iteration 진입
   ├─ edit    → 피드백 주입 후 PLAN 재생성(1회 이상), 재게이트
   ├─ run-auto→ policy=auto 로 승격 후 진입
   └─ stop    → USER_STOP
```

- `auto` 정책이면 게이트를 건너뛴다(자율 보장).
- PLAN 잘림(v1.1.034) 상태에서는 게이트 대신 **이어받기 우선** → 완전한 PLAN 확보 후 게이트.
- 신규 stop reason: 불필요(기존 `USER_STOP` 재사용).

### 3.4 Diff 미리보기 (L3 해소)

파일 쓰기/패치를 **디스크 반영 전** 통합 diff 로 표시하고 정책에 따라 승인.

- `interactive` / `auto-edit`: 각 파일의 unified diff(신규는 전체, 패치는 적용 결과 diff) 출력.
  - `interactive`: `[y]es / [n]o / [A]ll(세션 자동) / [s]top` 선택.
  - `auto-edit`: diff 표시 후 자동 적용(로그만).
- 패치는 `AgentPatchApplier` 가 이미 결과 문자열을 계산하므로, **적용 직전 dry-run 결과**로 diff 생성(transactional 보장과 정합).
- 신규 메서드(설계): `_preview_file_change(path, before, after) -> str`, `_confirm_change(policy, diff) -> bool`.
- 환경변수: `AGENT_DIFF_PREVIEW` (기본 `1`), `AGENT_DIFF_MAX_LINES`(기본 200, 초과 시 요약).

### 3.5 단계 추적기 / TODO (L2 해소)

PLAN 의 번호 목록을 **체크리스트 상태**로 승격해 매 iteration 진척을 표시.

- 데이터: `AgentSession.plan_steps: List[PlanStep]` — `PlanStep(idx, text, status: pending|in_progress|done|skipped)`.
- 초기화: PLAN 응답의 번호 목록 파싱(`_parse_plan_steps`). 파싱 실패 시 단일 "전체 목표" 스텝으로 폴백.
- 갱신: 각 iteration 의 [REASON] 또는 명시 태그 `[STEP:done N]` 로 상태 전이(모델 자기보고 + 휴리스틱). 완료 기준 통과 시 관련 스텝 자동 done.
- 표시: iteration 헤더에 `진행 3/7 ▰▰▰▱▱▱▱` 형태 live 라인 + 현재 스텝 텍스트.
- 신규 메서드(설계): `_parse_plan_steps`, `_render_progress`, `_advance_step`.
- 평가 게이트와의 관계: 추적기는 **표시·UX 용**이며 종료 판정 권위는 **여전히 완료 기준 게이트(v1.1.032)** 가 가진다(자기보고 신뢰 금지 원칙 유지).

### 3.6 인터럽트 & 스티어 (L5/L7 해소)

기존 async stop 리스너를 확장해 **중단 외 "방향 주입"** 을 지원.

- 키 매핑(TTY): `s`=중단(기존), **`i`=인터럽트 후 피드백 주입**, `p`=일시정지/재개.
- 동작: `i` 입력 시 현재 iteration 완료(또는 안전 지점) 후 멀티라인 피드백을 받아 다음 `_build_iteration_prompt` 의 `USER_FEEDBACK` 으로 주입.
- 모델 호출 도중 인터럽트는 **스트리밍 경계에서만** 반영(부분 응답 폐기 정책은 v1.1.034 잘림 처리와 동일하게 안전 처리).
- `AgentInputListener` 확장: `is_stop_requested()` 외 `pop_steer_request() -> Optional[str]`, `is_pause_requested()`.
- 비-TTY 환경에서는 자동 비활성(기존 정책 유지).

### 3.7 모드 전환 (양방향) (L6 해소)

iteration 사이 프롬프트를 정책 전환 허브로 일반화.

```text
_ask_continue() 확장 → _interaction_turn(policy)
  [c]ontinue / [f]eedback / [s]top
  [1] interactive  [2] auto-edit  [3] on-failure  [4] auto    ← 양방향 전환
```

- `auto`/`on-failure` 로 올렸다가 다시 `interactive` 로 **복귀 가능**(AS-IS 는 불가).
- `auto` 진입 시 기존 `_enter_bypass_mode()` 의 안전장치 초기화 재사용.

### 3.8 자율 코드 개선 루프 (Iterative Code Refinement) — **핵심** (L8/L9/L10 해소)

> 본 절이 사용자 요구 "**자율 루프 내 생성한 코드를 추가 개선·수정해 가며 목표 달성**"의 핵심이다. §3.2~3.7 이 *통제·가시성*이라면, 본 절은 *수렴 능력* 그 자체다.

#### 3.8.1 개선 사이클 모델

자율 루프를 **단발 생성**이 아니라 **read → edit → run → observe → refine 수렴 사이클**로 재정의한다.

```text
[목표 + 완료 기준(v1.1.032)]
   ▼
생성(1차) ──► 실행/테스트 ──► 관찰(OBSERVE + 평가 게이트)
   ▲                                   │
   │                                   ▼
   └──── 타겟 개선 ◄── 미충족 기준 → 대상 파일 매핑 ◄── 미달?
        (재-grounding 된 최신 파일로 patch/rewrite)
   ▼ (모든 기준 passed)
DONE
```

- 종료 권위는 **완료 기준 게이트(v1.1.032)** 가 유지한다. 개선 루프는 "미충족 기준이 남아 있는 한 멈추지 않고 **기존 코드를 고친다**"는 진행 규칙이다.
- 기존 `_self_correct_loop`(실패 트리거)와 **상호 보완**: Self-Correction 은 *액션 실패* 복구, 본 루프는 *목표 미달* 시 **성공한 코드도 능동 개선**.

#### 3.8.2 생성 코드 재-grounding (L9 해소)

편집 직후 **최신 파일 본문을 다음 프롬프트에 다시 주입**해 모델이 실제 디스크 상태 위에서 수정하도록 한다(기억 의존 SEARCH 표류 차단 — v1.1.033 패치 실패의 근본 원인 제거).

- `_build_iteration_prompt` 확장: `FILE_CONTEXT_REF`(경로 목록) → **`[CURRENT_FILES]` 최신 본문 스냅샷**(직전 iteration 에서 생성·수정된 파일 우선).
- 스냅샷은 `file_manager.read_file()` 로 **실시간 재독**(세션 메모리가 아니라 디스크 진실).
- 토큰 보호: `AGENT_REFINE_CONTEXT_MAX_BYTES`(기본 24KB) 상한, 초과 시 변경 파일 우선 + 나머지는 경로만. history compaction(`_compact_history_if_needed`)과 정합.
- 신규 메서드(설계): `_collect_recent_file_snapshots(session) -> Dict[path, body]`.

#### 3.8.3 미충족 기준 → 대상 파일 타겟팅 (L10 해소)

평가 게이트 실패를 **개선 대상 파일 목록**으로 변환해 개선을 집중시킨다.

- `_build_gate_feedback()` 확장: 미충족 기준별로 관련 파일을 명시.
  - `file_exists` 미충족 → 생성해야 할 경로.
  - `file_contains` 미충족 → 수정 대상 파일 + 기대 내용.
  - `cmd_exit_zero`(테스트) 실패 → 실패 테스트 출력 + 관련 소스 추정(스택/파일명 파싱).
- `[REFINE_TARGETS]` 프롬프트 섹션: "다음 파일을 개선해 미충족 기준을 충족시키세요" + 대상 목록.
- 신규 메서드(설계): `_map_unmet_criteria_to_files(criteria) -> List[(path, reason)]`.

#### 3.8.4 개선 수렴 가드 (무한 개선 방지) (G4)

"개선했다고 주장하지만 기준이 계속 미충족"인 품질 정체를 stagnation(성공 액션 0)과 **구분**해 별도 종료.

- `AgentSession.refine_round: int`, `last_unmet_signature: str`(미충족 기준 id 집합 해시).
- 연속 `AGENT_MAX_REFINE_ROUNDS`(기본 5) iteration 동안 **미충족 집합이 동일**(같은 기준이 안 풀림)이면 → `GOAL_NOT_MET` 으로 종료(자율 모드) 또는 사용자에게 에스컬레이션(대화형).
- 미충족 집합이 **줄어들면** 카운터 리셋(전진 중이므로 계속).
- 신규 stop reason: 불필요(`GOAL_NOT_MET` 재사용) — 단 종료 메시지에 "개선 정체" 사유 부기.

#### 3.8.5 개선 vs 신규 작업 구분 (진척 표시 연계)

- `PlanStep` 에 `refine_count` 추가 — 해당 스텝이 몇 번 재개선됐는지 진척 라인에 표시(`스텝 3 ↻2`).
- 평가 게이트 통과로 done 된 스텝은 재개선 대상에서 제외(완료 보존).

### 3.9 아키텍처 변경 요약

| 영역 | 변경 |
|---|---|
| `AgentSession` | `interaction_policy: str`, `plan_steps: List[PlanStep]`, `auto_approve_all_edits: bool`, `plan_approved: bool`, **`refine_round: int`, `last_unmet_signature: str`** (직렬화/Resume 시 정책은 보안 기본값 `interactive` 로 리셋, refine 카운터는 재계산) |
| `AgentRunner` | `_plan_approval_gate()`, `_preview_file_change()`, `_confirm_change()`, `_parse_plan_steps()`, `_render_progress()`, `_advance_step()`, `_interaction_turn()`, **`_collect_recent_file_snapshots()`, `_map_unmet_criteria_to_files()`, `_check_refine_convergence()`**; `run()` 게이트/diff/추적기/**개선 루프** 삽입 |
| `_build_iteration_prompt` | **`[CURRENT_FILES]` 최신 본문 + `[REFINE_TARGETS]` 섹션 추가** |
| `_build_gate_feedback` | **미충족 기준 → 대상 파일 매핑 포함** |
| `AgentActionDispatcher` | `_exec_file`/`_exec_patch` 에 diff 미리보기 + 정책 기반 승인 훅 |
| `AgentInputListener` | steer/pause 요청 큐 추가 |
| `agents_command.py` | `--policy` 파싱, `-ba`→`auto` 별칭 매핑 |
| Provider 3종 | 변경 없음(이미 `last_finish_reason` 노출) |

> ⚠️ Resume 보안: 정책·승인 플래그는 `bypass_approvals` 와 동일하게 **Resume 시 항상 `interactive`/False 로 리셋**한다. 편집된 세션 JSON 으로 자율 모드를 주입할 수 없어야 한다. refine 카운터·미충족 시그니처는 저장값을 신뢰하지 않고 **재평가로 재계산**(v1.1.032 원칙 계승).

---

## 4. 기능 요구사항 (FR)

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-041-01 | `InteractionPolicy`(interactive/auto-edit/on-failure/auto) 도입, `--policy` 플래그 + `AGENT_INTERACTION_POLICY` 연동, `-ba`=auto 별칭 | 필수 |
| FR-041-02 | PLAN 승인 게이트: approve/edit/run-auto/stop. `auto` 정책·PLAN 잘림 시 게이트 우회 규칙 | 필수 |
| FR-041-03 | 파일 쓰기/패치 diff 미리보기 + 정책 기반 승인(`interactive` 확인, `auto-edit` 표시-자동) | 필수 |
| FR-041-04 | PLAN 번호 목록 → `plan_steps` 체크리스트 파싱 및 iteration 헤더 진척 표시 | 필수 |
| FR-041-05 | 스텝 상태 전이(모델 `[STEP:done N]` + 휴리스틱 + 완료기준 통과 시 자동 done) | 권장 |
| FR-041-06 | 인터럽트 & 스티어: `i` 키로 피드백 주입(중단 없이 방향 변경), `p` 일시정지/재개 | 필수 |
| FR-041-07 | iteration 간 양방향 모드 전환(자율↔대화 복귀 포함) | 필수 |
| FR-041-08 | 종료 판정 권위는 **완료 기준 게이트(v1.1.032)** 가 유지 — 추적기/자기보고는 표시용 | 필수 |
| FR-041-09 | Resume 시 정책·승인 플래그를 `interactive`/False 로 강제 리셋 | 필수 |
| FR-041-10 | diff 크기 상한(`AGENT_DIFF_MAX_LINES`) 초과 시 요약 표시 | 권장 |
| FR-041-11 | 비-TTY 환경에서 대화형 요소 자동 비활성(자율 폴백) | 필수 |
| FR-041-12 | 기존 잘림 처리(v1.1.034)/패치 cascade(v1.1.033)/중복 필터(v1.0.115) 흐름과 정합 | 필수 |
| FR-041-13 | **자율 코드 개선 루프**: 미충족 기준이 남는 한 루프가 **기존 코드를 능동 개선**(read→edit→run→observe→refine). Self-Correction(실패 트리거)과 별개로 *목표 미달* 시 성공 코드도 개선 | 필수 |
| FR-041-14 | **생성 코드 재-grounding**: 편집 후 `[CURRENT_FILES]` 로 **최신 파일 본문(디스크 재독)** 을 다음 프롬프트에 주입. `AGENT_REFINE_CONTEXT_MAX_BYTES` 상한 | 필수 |
| FR-041-15 | **미충족 기준 → 대상 파일 타겟팅**: `_build_gate_feedback` 가 미충족 기준별 대상 파일/기대를 `[REFINE_TARGETS]` 로 제시(테스트 실패는 출력+관련 소스 추정) | 필수 |
| FR-041-16 | **개선 수렴 가드**: 동일 미충족 집합이 `AGENT_MAX_REFINE_ROUNDS` 연속 지속 시 `GOAL_NOT_MET`(정체 사유 부기)/대화형 에스컬레이션. 미충족 집합 축소 시 카운터 리셋 | 필수 |

### 4.1 비기능 요구사항 (NFR)

| ID | 요구사항 |
|---|---|
| NFR-041-01 | Provider 독립 — 3개 어시스턴트 공통 동작, 인터페이스 추가 없음 |
| NFR-041-02 | 회귀 없음 — `auto` 정책(=기존 `-ba`)과 게이트 off 경로는 현행 동작 보존 |
| NFR-041-03 | `unittest`/`pytest` 만 사용, 신규 외부 의존성 없음(diff 는 표준 `difflib.unified_diff`) |
| NFR-041-04 | 보안 — 정책 승격은 명시적 사용자 입력/플래그로만, 세션 JSON 주입 불가 |
| NFR-041-05 | 대화형 요소는 `AgentInputListener.paused()` 경계에서만 동기 input(스레드 경합 방지) |

---

## 5. 환경변수

| 변수 | 기본값 | 동작 |
|---|---:|---|
| `AGENT_INTERACTION_POLICY` | `interactive` | interactive/auto-edit/on-failure/auto; 잘못된 값은 `interactive` |
| `AGENT_DIFF_PREVIEW` | `1` | `0`이면 diff 미리보기 비활성(정책 승인만) |
| `AGENT_DIFF_MAX_LINES` | `200` | `1..5000`; 초과 diff 는 요약. 잘못된 값은 `200` |
| `AGENT_PLAN_GATE` | `1` | `0`이면 PLAN 승인 게이트 비활성(즉시 진입) |
| `AGENT_PROGRESS_BAR` | `1` | `0`이면 진척 라인 비표시 |
| `AGENT_REFINE_LOOP` | `1` | `0`이면 자율 코드 개선 루프 비활성(기존 단발 동작) |
| `AGENT_REFINE_CONTEXT_MAX_BYTES` | `24576` | `1024..262144`; `[CURRENT_FILES]` 본문 주입 상한. 잘못된 값은 기본값 |
| `AGENT_MAX_REFINE_ROUNDS` | `5` | `1..50`; 동일 미충족 집합 연속 한도. 잘못된 값은 `5` |

> 기존 변수(`AGENT_EVAL_GATE`, `AGENT_MAX_CONTINUATIONS`, `AGENT_PATCH_*`, `AGENT_BYPASS_*` 등)는 그대로 유지된다.

---

## 6. 검증 및 테스트 케이스

### 6.1 단위 테스트 (`tests/test_agent_interactive.py`, 신규)

| ID | 시나리오 | 기대 |
|---|---|---|
| T-041-01 | `--policy` 파싱 4종 + 잘못된 값 | enum 매핑, 잘못된 값→`interactive` |
| T-041-02 | `-ba` 플래그 | `policy=auto` 로 매핑(후방호환) |
| T-041-03 | PLAN 게이트 approve | iteration 진입 |
| T-041-04 | PLAN 게이트 edit→재생성 | 피드백 주입 후 PLAN 재생성, 재게이트 |
| T-041-05 | PLAN 게이트 run-auto | `policy=auto` 승격, 이후 게이트/정지 없음 |
| T-041-06 | `policy=auto` | PLAN 게이트 우회(자율 보장) |
| T-041-07 | PLAN 잘림(v1.1.034) + 게이트 | 게이트 대신 이어받기 우선 |
| T-041-08 | `_parse_plan_steps` 번호 목록 | PlanStep 리스트 생성 |
| T-041-09 | 번호 목록 파싱 실패 | 단일 폴백 스텝 |
| T-041-10 | `_render_progress` | `3/7` + 진척 바 문자열 |
| T-041-11 | 스텝 자동 done(완료기준 통과) | 관련 스텝 status=done |
| T-041-12 | diff 미리보기(신규 파일) | unified diff 문자열 생성 |
| T-041-13 | diff 미리보기(패치 dry-run) | 적용 결과 diff, 디스크 무변경 |
| T-041-14 | `interactive` 편집 거부(n) | 파일 미저장 |
| T-041-15 | `auto-edit` | diff 표시 + 자동 저장 |
| T-041-16 | `on-failure` 정상 액션 | 정지 없이 진행 |
| T-041-17 | `on-failure` 실패 액션 | 정지/승인 요청 |
| T-041-18 | `AGENT_DIFF_MAX_LINES` 초과 | 요약 표시 |
| T-041-19 | 모드 전환 auto→interactive 복귀 | 다음 iteration 정지 부활 |
| T-041-20 | steer(`i`) 피드백 주입 | 다음 프롬프트 `USER_FEEDBACK` 포함, 중단 아님 |
| T-041-21 | pause(`p`) 토글 | 일시정지/재개 |
| T-041-22 | 비-TTY | 대화형 비활성, 자율 폴백 |
| T-041-23 | Resume 정책 리셋 | 저장값 무관 `interactive`/False |
| T-041-24 | 세션 JSON 으로 auto 주입 시도 | 리셋되어 무효(보안) |

### 6.2 통합 / 회귀 테스트

| ID | 시나리오 | 기대 |
|---|---|---|
| T-041-25 | `policy=auto` 전체 루프 | 기존 `-ba` 와 동일 동작(회귀 없음) |
| T-041-26 | 완료 기준 게이트 + 추적기 동시 | 종료 판정은 게이트가 결정(추적기 무관) |
| T-041-27 | 잘림→이어받기→게이트 | v1.1.034 흐름 보존 |
| T-041-28 | 패치 similar + diff 미리보기 | dry-run diff 후 transactional 적용 |
| T-041-29 | 중복 파일(filename+patch) + diff | filename 우선, patch 보고만 |
| T-041-30 | 기존 `/agents` 회귀 묶음 | 전부 통과 |

### 6.3 자율 코드 개선 루프 테스트 (`tests/test_agent_refine.py`, 신규)

| ID | 시나리오 | 기대 |
|---|---|---|
| T-041-31 | 미충족 기준 잔존 + `AGENT_REFINE_LOOP=1` | 루프가 종료 안 하고 기존 코드 개선 iteration 지속 |
| T-041-32 | `_collect_recent_file_snapshots` | 직전 수정 파일의 **디스크 최신 본문** 반환(세션 메모리 아님) |
| T-041-33 | `[CURRENT_FILES]` 주입 | 다음 iteration 프롬프트에 최신 본문 포함 |
| T-041-34 | `AGENT_REFINE_CONTEXT_MAX_BYTES` 초과 | 변경 파일 우선 + 나머지 경로만, 상한 준수 |
| T-041-35 | `_map_unmet_criteria_to_files` | file_exists/file_contains/cmd_exit_zero 별 대상 파일·사유 매핑 |
| T-041-36 | `[REFINE_TARGETS]` 주입 | gate feedback 에 대상 파일 목록 포함 |
| T-041-37 | 수렴 가드: 동일 미충족 N회 | `AGENT_MAX_REFINE_ROUNDS` 초과 시 `GOAL_NOT_MET`(정체 사유) |
| T-041-38 | 수렴 가드: 미충족 축소 | 카운터 리셋, 루프 계속 |
| T-041-39 | `AGENT_REFINE_LOOP=0` | 개선 루프 비활성, 기존 단발 동작(회귀 없음) |
| T-041-40 | 개선이 stagnation(성공 액션 0)과 구분 | 정체 가드와 bypass S3 가 독립 동작 |

### 6.4 검증 방법 / 완료 기준

```bash
# 신규 + 인접 회귀
python -m pytest tests/test_agent_interactive.py tests/test_agent_refine.py \
  tests/test_agent_runner.py tests/test_agent_truncation.py \
  tests/test_agent_eval_gate.py tests/test_agent_patch_similarity.py \
  tests/test_agent_action_dispatcher.py -q
```

- [ ] T-041-01 ~ T-041-40 전부 통과
- [ ] 기존 `/agents` 회귀 묶음(254+ ) 무회귀
- [ ] `auto` 정책 = 기존 `-ba` 바이트 호환 확인
- [ ] `AGENT_REFINE_LOOP=0` = 기존 단발 동작 호환 확인
- [ ] 독립 code review APPROVE + 보안(정책 주입) adversarial QA CLEAN

---

## 7. 단계적 구현 (Phasing)

```text
P1 (필수, 골격) — 정책 + 게이트:
  FR-041-01  InteractionPolicy + --policy + -ba 별칭
  FR-041-02  PLAN 승인 게이트
  FR-041-09  Resume 정책 리셋
  FR-041-11  비-TTY 폴백

P2 (필수, 핵심 — 수렴 능력) — 자율 코드 개선 루프:
  FR-041-13  자율 코드 개선 루프(목표 미달 시 능동 개선)
  FR-041-14  생성 코드 재-grounding([CURRENT_FILES])
  FR-041-15  미충족 기준 → 대상 파일 타겟팅([REFINE_TARGETS])
  FR-041-16  개선 수렴 가드(무한 개선 방지)
  FR-041-08  종료 권위는 완료 기준 게이트 유지

P3 (필수, 가시성) — diff + 추적기:
  FR-041-03  diff 미리보기 + 정책 승인
  FR-041-04  plan_steps 추적기 + 진척 표시
  FR-041-12  기존 흐름 정합(잘림/패치/중복)

P4 (필수, 통제) — 끼어들기 + 전환:
  FR-041-06  인터럽트 & 스티어
  FR-041-07  양방향 모드 전환

P5 (권장) — 다듬기:
  FR-041-05  스텝 자동 전이
  FR-041-10  diff 요약
```

---

## 8. 잔여 리스크 / 결정 필요 사항

1. **스트리밍 도중 인터럽트 경계**: 현재 `chat()` 은 스트림 완료 후 반환. 진정한 mid-stream 중단은 Provider 계층 변경이 필요하므로, 1차는 **iteration/스트림 경계 인터럽트**로 한정한다(부분 응답은 v1.1.034 잘림 처리 재사용).
2. **모델 자기보고 스텝 신뢰도**: `[STEP:done N]` 은 표시용일 뿐, 종료 권위는 완료 기준 게이트가 유지(FR-041-08). 자기보고만으로 done 처리 금지.
3. **diff 비용**: 대형 파일 전체 diff 는 비용이 크다 → `AGENT_DIFF_MAX_LINES` 요약 + 패치는 변경 hunk 중심 표시.
4. **정책 승격 보안**: 자율(`auto`) 승격은 명시 입력/플래그로만. Resume·세션 JSON 경유 주입 차단(T-041-24).
5. **비-TTY/CI**: 대화형 요소는 자동 비활성, `auto` 또는 `on-failure` 로 폴백해 무한 대기 방지.
6. **개선 루프 토큰 비용**: `[CURRENT_FILES]` 재주입은 토큰을 늘린다 → `AGENT_REFINE_CONTEXT_MAX_BYTES` 상한 + 변경 파일 우선 + history compaction 연계로 억제.
7. **개선 vs 정체 구분**: "성공 액션은 있으나 기준 미충족"(개선 정체)과 "성공 액션 0"(bypass S3 stagnation)은 **다른 신호**다. 전자는 `_check_refine_convergence`(미충족 시그니처 불변), 후자는 기존 S3 가 각각 담당.

---

## 9. 승인

- [ ] AS-IS 통합 흐름 검토
- [ ] TO-BE 설계 확정(3.2 정책 모델 + 3.3 게이트 + **3.8 자율 코드 개선 루프** + 3.6 스티어)
- [ ] 구현 (P1 → P2 → P3 → P4 → P5)
- [ ] 테스트 (T-041-01 ~ T-041-40)
- [ ] 문서 반영(RELEASE 노트)

### 9.1 본 개정(2026-06-22) 개선 체크리스트

사용자 요구 "**자율 루프 내 생성한 코드를 추가 개선·수정해 가며 목표 달성**" 반영 여부.

- [x] **G1 — 능동적 코드 개선 루프**: §3.8.1 개선 사이클 모델 + FR-041-13 추가 (L8 해소)
- [x] **G2 — 생성 코드 재-grounding**: §3.8.2 `[CURRENT_FILES]` 디스크 재독 + FR-041-14 (L9 해소)
- [x] **G3 — 미충족 기준 → 대상 파일 타겟팅**: §3.8.3 `[REFINE_TARGETS]` + FR-041-15 (L10 해소)
- [x] **G4 — 개선 수렴 가드**: §3.8.4 미충족 시그니처 정체 종료 + FR-041-16
- [x] UX 기준선 표(§3.1)에 "코드 반복 개선" 행 추가
- [x] 아키텍처 표(§3.9) 신규 상태/메서드 반영, Resume 재계산 원칙(v1.1.032 계승)
- [x] 환경변수 3종(`AGENT_REFINE_LOOP`, `AGENT_REFINE_CONTEXT_MAX_BYTES`, `AGENT_MAX_REFINE_ROUNDS`)
- [x] 테스트 T-041-31 ~ T-041-40 (개선 루프 전용 10케이스)
- [x] Phasing 에 P2(자율 코드 개선 루프) **핵심 우선순위** 배치
- [x] 종료 권위는 완료 기준 게이트(v1.1.032) 유지 — 자기보고 신뢰 금지 원칙 보존

> 본 문서는 설계 단계이며, 구현 착수는 별도 승인 후 진행한다.
