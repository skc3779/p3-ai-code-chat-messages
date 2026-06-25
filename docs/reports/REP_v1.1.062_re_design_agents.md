# REP v1.1.062 — `/agents` 재설계 구현 보고서 (단계별 누적)

| 항목 | 내용 |
|------|------|
| 보고서 | REP_v1.1.062 |
| 대상 설계 | FSD_v1.1.062_re_design_agents.md |
| 선행 | FSD_v1.1.061(삭제) → FSD_v1.1.062(재구현) |
| 실행 방식 | `/team` 파이프라인 (구현 → 테스트 → 검증), CLAUDE.md 3역할 |
| 갱신 규칙 | **각 단계(P0~P5) 종료 시 본 문서에 결과를 누적 기록** |

---

## 진행 현황 요약

| 단계 | 범위 | 상태 | 종료일 |
|------|------|------|--------|
| P0 | 기반 컴포넌트 복원 (ReAct 루프·dispatcher·patch·session·입력리스너·진입점) | ✅ 완료 | 2026-06-24 |
| P1 | 정책 + PLAN 게이트 (InteractionPolicy·--policy·PLAN승인·resume리셋·non-TTY) | ✅ 완료 | 2026-06-24 |
| P2 | 자율 코드 개선 루프 (완료기준 평가기·재-grounding·기준 타겟팅·수렴 가드·probe) | ✅ 완료 | 2026-06-25 |
| P3 | diff 미리보기 + 단계 추적기 (compute/commit·plan_steps) | ✅ 완료 | 2026-06-25 |
| P4 | 인터럽트 & 스티어 + 양방향 전환 + per-action 정책 | ✅ 완료 | 2026-06-26 |
| P5 | 다듬기 (스텝 자동 전이·diff 요약) | ✅ 완료 | 2026-06-26 |
| **전체** | **FSD_v1.1.062 P0~P5 재설계 구현** | **✅ 완료 (GO_WITH_FOLLOWUPS)** | **2026-06-26** |

---

## P0 — 기반 컴포넌트 복원 ✅ (2026-06-24)

### 전략
FSD §2 기반 컴포넌트는 FSD_v1.1.061로 삭제된 원본 모듈의 동작 명세와 동일하므로, **git HEAD blob 복원 + 최소 적응**으로 충실히 재구성. TO-BE 재설계(§3)는 P1+에서 적층.

### 산출물
**구현 (src/)** — git HEAD 원본 복원
- `agent_runner.py` (1142): ReAct 루프, `AgentRunner`/`AgentSession`/`AgentStopReason`/`ActionResult`/`IterationRecord`, `[AGENT_DONE]` 완료, Self-Correction, bypass 안전장치(S2~S4)
- `agent_action_dispatcher.py` (370): 펜스 파싱·file/code/shell 라우팅·중복 필터
- `agent_input_listener.py` (196): async stop('s' 키)
- `agent_session_store.py` (136): JSON 직렬화·resume·보안 리셋
- `agents_command.py` (224): 서브커맨드(list/resume/stop)·플래그(-ba/-s)

**단일 적응** — patch 적용기 중립 모듈화
- `src/agent_patch_applier.py`(`AgentPatchApplier`) → `src/patch_applier.py`(`PatchApplier`), QC(품질검사) 기능과 공용. dispatcher 참조 갱신, QC 무회귀.

**재배선**
- 진입점 3종(claude/gemini/gen-ai-chat-code.py) `/agents` elif 복원
- `src/__init__.py` export(`AgentRunner`/`AgentSession`/`AgentStopReason`)
- `src/command_registry.py` 명령 3건(`/agents`, resume, list)

**테스트 (tests/)** — HEAD 복원 + 적응
- `test_agent_runner.py`, `test_agent_action_dispatcher.py`, `test_agent_dispatcher_patch.py`, `test_agent_input_listener.py`, `test_agent_session_store.py`, `test_agent_chain_danger.py`, `test_agent_system_prompt_v111.py`, `test_agents_flags.py`, `test_bypass_approvals.py`
- `test_patch_applier.py`(이전 반영), `test_agent_system_prompt.py`(분리 신규)

### 검증
| 항목 | 결과 |
|------|------|
| 전체 스위트 | 711 passed / 20 failed(기존 환경 실패만, 신규 0) |
| agent 테스트 | 247 passed |
| `/agents` 레지스트리 | 3건 등록 |
| 진입점 컴파일 | ✅ |
| QC 무회귀 | ✅ |
| 보안(resume bypass 리셋) | ✅ FSD §3.9 |
| 코드 리뷰 | APPROVE_WITH_NITS (Blocker 0) |

### 파이프라인
worker-1(executor/opus, 구현) → worker-2(test-engineer, 테스트) → worker-3(code-reviewer, 검증)

### P1 이월 (P0 리뷰 nits)
- M-1: claude/gen-ai 진입점 중복 구조 → 공통 추출 고려
- N-1: dispatcher `_exec_code` 미사용 import
- N-2: `patch_applier`의 `PatchApplier/PatchResult/BlockResult` `__all__` 미등록

---

## P1 — 정책 + PLAN 게이트 🔄 (진행 중)

### 목표 (FSD FR-062-01·02·09·11)
- **FR-062-01** `InteractionPolicy`(interactive/auto-edit/on-failure/auto) + `--policy` 플래그 + `AGENT_INTERACTION_POLICY` + `-ba`=auto 별칭
- **FR-062-02** PLAN 승인 게이트: `[a]pprove / [e]dit / [r]un-auto / [s]top`, auto·잘림 시 우회, `AGENT_PLAN_EDIT_MAX`
- **FR-062-09** Resume 시 정책 `interactive` 강제 리셋
- **FR-062-11** 비-TTY 안전 폴백(자동 승격 금지, 명시 auto 없으면 안전 종료)

### 통합 지점 (agent_runner.py 분석 결과)
- `run()` 에 `interaction_policy: str` 파라미터 추가
- Resume 분기(L151~)에 정책 리셋 추가
- Step 0 PLAN 직후(L250)·루프 진입 전 `_plan_approval_gate()` 삽입
- 반복 종료 분기(L318~336): 정책 기반 — `auto`→bypass(기존), `interactive`→`_ask_continue`(기존)
- `agents_command.py` `_extract_policy_flag()` + `-ba`→auto 매핑
- `AgentSession` 에 `interaction_policy`, `plan_approved` 필드

### 단계 경계 메모
- `auto-edit`/`on-failure` 의 **per-action 강제**(편집 자동/셸 정지)는 dispatcher·diff 훅에 의존 → **P3(diff 미리보기)에서 완성**. P1 에서는 enum·파싱·배선까지 제공하고 두 정책은 안전 기본(interactive 동작 + 안내)으로 폴백.

### 산출물 (확정)
**신규 src/agent_policy.py** — `InteractionPolicy` 상수(interactive/auto-edit/on-failure/auto), `VALID_POLICIES`/`DEFERRED_POLICIES`, `normalize_policy()`(잘못된 값→interactive), `env_default_policy()`.

**src/agents_command.py** — `_extract_policy_flag()`, `_has_policy_flag()`, precedence `--policy 명시 > -ba(auto) > env > interactive`, `bypass=(policy==auto)`.

**src/agent_runner.py** — `AgentSession.interaction_policy/plan_approved` 필드, `run(interaction_policy=)`, `_plan_approval_gate()`(a/e/r/s), `_regenerate_plan()`, `_is_tty()`, `_env_int()`, `_PlanGateStop`, resume 정책 강제 리셋(L187-191), DEFERRED 안내, `bypass↔auto` 양방향 매핑.

**테스트** — `tests/test_agent_policy_gate.py`(40케이스: 파싱/정규화·precedence·게이트 a/e/r/s·edit 한도·resume 리셋·non-TTY).

### 환경변수 추가
`AGENT_INTERACTION_POLICY`(interactive), `AGENT_PLAN_GATE`(1), `AGENT_PLAN_EDIT_MAX`(3).

### 검증
| 항목 | 결과 |
|------|------|
| 신규 P1 테스트 | 40 passed |
| 전체 스위트 | 751 passed (P0 711 → +40) / 기존 20 실패만, 신규 0 |
| 정책 precedence 스모크 | `--policy interactive -ba`→interactive, `-ba`→auto, none→interactive ✅ |
| resume 보안 리셋 | 위조 세션(auto+plan_approved)→interactive/False 강제 ✅ |
| non-TTY 폴백 | 비-auto→USER_ABORT_ON_ERROR, 자동 승격 없음 ✅ |
| 코드 리뷰 | APPROVE_WITH_NITS (Blocker 0) — 테스트 품질 nit 3건 즉시 보강 |

### 파이프라인
p1-impl(opus, 구현) → p1-test(테스트 40) → p1-review(검증). nit 3건(TB04 무조건 assert·TE01 미사용 변수·TD03 docstring) lead 보강.

### P2 이월 주의 (구현 중 발견)
- **완료 기준 평가기(`AgentGoalEvaluator`, FSD §2.2)는 현 코드베이스에 부재** — P0 복원 대상(HEAD)에 없었음. 현재 완료 판정은 `[AGENT_DONE]` 토큰 신뢰. P2의 개선 루프(§3.8)는 평가기에 의존하므로 **P2에서 평가기를 먼저 구현**한다.

---

## P2 — 자율 코드 개선 루프 ✅ (2026-06-25)

### 선행 발견 → 평가기 신규 구현
완료 기준 평가기(§2.2)가 코드베이스에 부재(P0 복원 대상 HEAD에 없었음)했으므로, P2에서 **신규 구현**한 뒤 그 위에 개선 루프를 적층.

### 산출물
**신규 src/agent_goal_evaluator.py (§2.2)**
- `Criterion`/`CriteriaSnapshot`, `AgentGoalEvaluator(file_manager)`: `extract_from_goal`(결정론 추출), `parse_model_criteria`(@@@criteria 블록), `merge_criteria`(extracted 우선·불변, model add-only, 상한 32), `evaluate`(file_exists/file_contains/cmd_exit_zero/llm).
- **shell-free verifier**: `subprocess.Popen(shell=False)`, allowlist(python/pytest/unittest), workspace 봉쇄, `..` 거부, **zero-test 위장 차단**(collected 0/ran 0), timeout.

**src/agent_runner.py 개선 루프 (§3.8)**
- 게이트: `_finalize_goal`(DONE 단독 권위 FR-062-08, 기준0개→토큰신뢰 폴백, GOAL_UNVERIFIED/GOAL_NOT_MET, eval_reject 한도).
- `_probe_criteria`(비종료 증거점검 FR-062-17), `_collect_recent_file_snapshots`+`_build_current_files_block`(재-grounding `[CURRENT_FILES]` 펜스 escaping + 휘발성 strip FR-062-14/20), `_map_unmet_criteria_to_files`+`_build_refine_targets`(`[REFINE_TARGETS]` authoritative/advisory 2등급 FR-062-15/21), `_evidence_signature`/`_update_refine_convergence`/`_check_refine_convergence`(수렴 가드 FR-062-16), 종료 우선순위(FR-062-18).

**테스트**: `tests/test_agent_goal_evaluator.py`(41) + `tests/test_agent_refine_loop.py`(53→55, fix 후) = 96.

### 환경변수 추가
`AGENT_EVAL_GATE`(1), `AGENT_EVAL_REJECT_MAX`(3), `AGENT_EVAL_CMD_TIMEOUT`(60), `AGENT_REFINE_LOOP`(1), `AGENT_REFINE_PROBE_EVERY`(1), `AGENT_MAX_REFINE_ROUNDS`(5), `AGENT_REFINE_CONTEXT_MAX_BYTES`(24576), `AGENT_COMPACT_MAX_BYTES`(131072).

### 검증
| 항목 | 결과 |
|------|------|
| 신규 P2 테스트 | 96 passed |
| 전체 스위트 | 847 passed (P1 751 → +96) / 기존 20 실패만, 신규 0 |
| shell-free 보안 | allowlist 차단·인젝션 무력화·traversal 거부·zero-test 차단 ✅ |
| 후방호환 | AGENT_REFINE_LOOP=0 / AGENT_EVAL_GATE=0 → 기존 동작 ✅ |
| 코드 리뷰(opus) | APPROVE_WITH_NITS (Blocker 0) |

### 리뷰 Major 2건 → 즉시 수정 (team-fix)
- **Major-2 (FR-062-16)**: 증거 진동(5↔9) 시 수렴 가드 미발화 → **monotonic best-badness**로 교정(개선일 때만 리셋). 검증: flapping→refine_round 누적·converged True, 단조개선→리셋.
- **Major-1 (FR-062-08)**: 모델 주입 `cmd_exit_zero:python -c "sys.exit(0)"` 자기-부여 DONE → **모델 cmd는 테스트러너 형태만** 게이트 자격. 검증: `python -c` 제외·pytest 유지.
- Minor(FR-062-18 종료 우선순위 부분 역전)도 함께 보정.

### 파이프라인
p2a-impl(opus, 평가기) → p2b-impl(opus, 개선루프) → p2-test(94→96) → p2-review(opus) → p2-fix(opus, Major 2건).

### P3 이월
- shell-free verifier의 `python -c <임의코드>` 허용은 **테스트명령 실행기 용도 + workspace 봉쇄** 하에 수용된 알려진 위험(리뷰 문서화).
- 추출 휴리스틱 정밀도(경로 앞 "Create" 동사 미스 등) 개선 여지 — 기능 영향 낮음.

## P3 — diff 미리보기 + 단계 추적기 ✅ (2026-06-25)

### 산출물
**src/patch_applier.py (FR-062-19 compute/commit 분리)**
- `PatchPlan` dataclass(rel_path/computed_text/block_results/success/error/before_text/diff/is_full_file).
- `compute(rel_path, payload)`: 매칭 cascade + diff 산출, **디스크 미변경**, transactional 판정. `compute_full_file(rel_path, new_text)`: 파일 전문 diff. `commit(plan)`: 승인 plan 기록(success=False면 무변경).
- **`apply()` 를 compute+commit wrapper 로 재작성** — 시그니처/반환/on_first_approval/auto_approve 동작 완전 보존(QC 무회귀).

**src/agent_runner.py (FR-062-03 diff / FR-062-04 추적기)**
- `_preview_file_change`(unified diff, `AGENT_DIFF_MAX_LINES` 요약), `_confirm_change`(정책별 승인: interactive y/n/A/s, auto-edit/auto 자동).
- `PlanStep`(idx/text/status/refine_count), `AgentSession.plan_steps`, `_parse_plan_steps`(번호목록→스텝, 실패 폴백), `_render_progress`(`📊 진행 N/M ▰▱`), `_advance_step`(`[STEP:done N]` 태그+보수적 휴리스틱, **종료 권위는 게이트 유지**).

**src/agent_action_dispatcher.py** — `_exec_patch`/`_exec_file`에 compute→diff 미리보기→정책 승인→commit 흐름(거부 시 무변경).

**테스트**: `tests/test_agent_diff_tracker.py`(36).

### 환경변수 추가
`AGENT_DIFF_PREVIEW`(1), `AGENT_DIFF_MAX_LINES`(200), `AGENT_PROGRESS_BAR`(1).

### 검증
| 항목 | 결과 |
|------|------|
| 신규 P3 테스트 | 36 passed |
| 전체 스위트 | 883 passed (P2 847 → +36) / 기존 20 실패만, 신규 0 |
| compute/commit | compute 디스크 무변경·commit 기록·거부 무변경 ✅ |
| **apply() wrapper 후방호환** | PASS (시그니처/콜백/auto_approve 보존) ✅ |
| **QC 무회귀** | PASS (context_processor.apply 정상) ✅ |
| 코드 리뷰(opus) | **APPROVE** (nit 2건, 표시용·P4 이월) |

### 파이프라인
p3-impl(opus) → p3-test(36) → p3-review(opus, APPROVE).

### P4 이월 (P3 리뷰 nit)
- 자동승인 패치 diff 출력이 `AGENT_DIFF_MAX_LINES` 요약을 안 거침(대용량 콘솔 노이즈) — 표시용.
- `patch_applier` unified diff와 `_preview_file_change` 중복 구현 — 통합 여지.

## P4 — 인터럽트 & 스티어 + 양방향 전환 + per-action 정책 ✅ (2026-06-26)

### 산출물
**src/agent_input_listener.py (FR-062-06)** — 키 `s`(중단)/`p`(일시정지 토글)/`i`(스티어). `pop_steer_request`/`is_pause_requested`/`pop_pause_request`/`clear_*`, `_classify_key`/`_apply_key` 우선순위 **s>p>i**(버퍼 flush), stop만 폴링 종료.

**src/agent_policy.py (FR-062-22)** — `per_action_decision(policy, action_kind, *, is_dangerous)` 매트릭스: auto-edit 편집=auto·셸=approve, on-failure 사전 stop, **위험셸 항상 approve**, auto=전부 auto. P1 DEFERRED 폴백 해제.

**src/agent_runner.py** — `_handle_interrupts`(paused 경계 내 steer 수집·pause 대기), `_interaction_turn`(c/f/b/s + `[1~4]` 정책 전환, **auto→interactive 복귀는 인터럽트 키로만**), `per_action_gate`(interactive/auto/bypass→AUTO 후방호환=이중승인 없음, auto-edit/on-failure만 세분), bypass 루프 인터럽트 확인(안전장치 우선).

**src/agent_action_dispatcher.py** — per-action 게이트, STOP 시 **잔여 액션 보존**(`_make_hold_result`, kind="hold", success=True → Self-Correction 미트리거, 재제시 없음).

**테스트**: `tests/test_agent_interrupt_steer.py`(57 + 12 subtests).

### 검증
| 항목 | 결과 |
|------|------|
| 신규 P4 테스트 | 57 passed (+12 subtests) |
| 전체 스위트 | 940 passed (P3 883 → +57) / 기존 20 실패만, 신규 0 |
| 이중 승인 회피 | PASS (interactive 편집은 P3 diff 승인만, per-action 비개입) |
| 위험셸 항상 사전승인 | PASS (input 1회, transient 플래그 finally 원복) |
| 잔여 액션 보존 | PASS (hold, Self-Correction 미트리거) |
| 양방향 전환 보안 | PASS (auto 복귀는 인터럽트 키, 안전장치 우선) |
| 코드 리뷰(opus) | APPROVE_WITH_NITS (Blocker 0) |

### 리뷰 Major 1건 → 즉시 수정 (lead)
- **스레드 안전**: `_plan_approval_gate`의 PLAN 편집 `get_multiline()`(agent_runner.py:1775)이 `paused()` 경계 밖이라 리스너 스레드와 stdin 경합 + P4 i/p 키 거짓 발화 가능 → **`paused()` 경계로 wrap**(input과 동일 패턴). 검증: 전 게이트 입력 지점이 paused 경계 내.

### 파이프라인
p4-impl(opus) → p4-test(57) → p4-review(opus) → lead 픽스(paused 경계).

### P5 이월 (P4 리뷰 nit)
- `_ask_continue`(레거시)는 루프에서 `_interaction_turn`으로 대체됨 — dead path 가드/주석 권고.
- `DEFERRED_POLICIES` 상수 명칭이 "DEFERRED 해제" 의도와 혼동 소지(여전히 _confirm_change에서 사용).

## P5 — 다듬기 ✅ (2026-06-26)

### 산출물
**src/agent_runner.py**
- `_auto_done_by_criteria`+`_criteria_for_step`(FR-062-05): 완료 기준 통과 시 **보수적** 스텝 자동 done(step.text가 criterion.target 명시 포함 + 연결기준 전부 passed만, 모호/llm/미통과 미변경). done 후 포인터 전진(표시용). **종료 권위는 게이트 유지**.
- `_mark_unmet_steps_refined`: 미충족 연결 스텝 `refine_count++`, `_render_progress` `↻N`.
- `_summarize_diff`(FR-062-10): 모든 diff 출력(`_preview_file_change`·`_confirm_change` 3분기·dispatcher 자동승인 patch)을 `AGENT_DIFF_MAX_LINES` 요약으로 통일.
- `_ask_continue` dead-path 주석.

**src/agent_action_dispatcher.py** — 자동승인 patch diff → `_summarize_diff` 경유. **src/agent_policy.py** — `DEFERRED_POLICIES` 용도 주석.

**테스트**: `tests/test_agent_step_diff_polish.py`(51).

### 검증
| 항목 | 결과 |
|------|------|
| 신규 P5 테스트 | 51 passed |
| 전체 스위트 | 991 passed (P4 940 → +51) / 기존 20 실패만, 신규 0 |
| 스텝 자동 전이 보수성 | PASS (종료 권위 게이트 유지) |
| diff 요약 일관성 | PASS (전 출력 사이트 통일) |
| 코드 리뷰(opus) | **APPROVE** (Blocker 0) |

### 파이프라인
p5-impl(opus) → p5-test(51) → p5-review(opus, APPROVE + 전체 통합 검토).

---

## 🏁 전체 완료 — FSD_v1.1.062 P0~P5 (2026-06-26)

### 최종 판정: **GO_WITH_FOLLOWUPS** (opus 통합 검토)
- **FR-062-01 ~ 22: 22/22 충족** (정책/PLAN게이트/diff/추적기/스텝전이/인터럽트·스티어/양방향전환/게이트권위/resume리셋/diff요약/non-TTY/흐름정합/개선루프/재-grounding/타겟팅/수렴가드/probe/종료우선순위/compute·commit/휘발성주입/advisory/per-action).
- **보안 종합: PASS** — shell-free verifier(테스트러너 한정·workspace 봉쇄·zero-test 위장 차단), self-grant 차단(모델 cmd 테스트러너 한정), resume JSON 주입 차단(정책·플래그·카운터 강제 리셋), CURRENT_FILES 펜스 escaping+휘발성, 위험셸 항상 사전승인, non-TTY 자동승격 금지.
- **후방호환: PASS** — `AGENT_EVAL_GATE=0`/`AGENT_REFINE_LOOP=0`/`-ba=auto`/`AGENT_DIFF_PREVIEW=0`/`AGENT_PROGRESS_BAR=0`, QC(context_processor) 무회귀.
- **종료 권위 일원화 (FR-062-08/18): PASS** — DONE 단독권위=평가기 게이트, 실패측=안전한도, 종료 우선순위표 결정적, 추적기/자기보고/자동done은 표시용.

### 신규/변경 모듈
| 구분 | 모듈 |
|------|------|
| 신규 | `src/agent_policy.py`(P1), `src/agent_goal_evaluator.py`(P2) |
| 확장 | `src/agent_runner.py`, `src/agent_action_dispatcher.py`, `src/agent_input_listener.py`, `src/patch_applier.py`, `src/agents_command.py` |

### 테스트 (신규 6파일, P1~P5)
`test_agent_policy_gate.py`(40) · `test_agent_goal_evaluator.py`(41) · `test_agent_refine_loop.py`(55) · `test_agent_diff_tracker.py`(36) · `test_agent_interrupt_steer.py`(57+12) · `test_agent_step_diff_polish.py`(51) — **전체 스위트 991 passed**(기존 20 환경 실패만, agent 신규 실패 0).

### 환경변수 (신규 누계)
`AGENT_INTERACTION_POLICY`·`AGENT_PLAN_GATE`·`AGENT_PLAN_EDIT_MAX`·`AGENT_DIFF_PREVIEW`·`AGENT_DIFF_MAX_LINES`·`AGENT_PROGRESS_BAR`·`AGENT_EVAL_GATE`·`AGENT_EVAL_REJECT_MAX`·`AGENT_EVAL_CMD_TIMEOUT`·`AGENT_REFINE_LOOP`·`AGENT_REFINE_PROBE_EVERY`·`AGENT_MAX_REFINE_ROUNDS`·`AGENT_REFINE_CONTEXT_MAX_BYTES`·`AGENT_COMPACT_MAX_BYTES`.

### 차기 follow-up (머지 차단 아님)
1. `patch_applier`의 unified diff 생성과 `_preview_file_change`가 여전히 2곳 — 생성 로직 통합(P5는 출력 요약만 공통화).
2. shell-free verifier `python <script.py>` 허용은 문서화된 알려진 위험(테스트명령 한정·workspace 봉쇄).
3. 완료 기준 추출 휴리스틱 정밀도(동사 인접 경로 인식 등) — advisory 한정이라 영향 낮음.

### 미커밋 안내
P1~P5 신규/변경 파일은 현재 git 미커밋(staged/untracked) 상태입니다 — 사용자 요청 시 단계별 커밋을 정리해 드립니다.
