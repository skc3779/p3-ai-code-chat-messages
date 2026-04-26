# RELEASE v1.0.115 — `/agents` ACT 최적화: Diff/Patch 모드 + 결정 트리 + 체이닝 위험 명령 검사

| 항목 | 내용 |
|---|---|
| 릴리스 버전 | v1.0.115 |
| 작성일 | 2026-04-27 |
| 선행 문서 | FSD v1.0.115 (Diff/Patch + 선택지 A/B/C 하이브리드 정합) |
| 상태 | ✅ 구현 완료 (수동 확인 대기) |

---

## 변경 요약

`/agents` 자율 루프의 [ACT] 단계에서 발생하던 **파일 전문 재작성으로 인한 토큰
폭증**·**자기 끊김으로 인한 데이터 손실**·**체이닝된 위험 명령 우회** 3 종 문제를
일괄 해결한다.

### 핵심 변경사항

| # | 변경 내용 | 파일 |
|---|---|---|
| 1 | **`AgentPatchApplier` 신규** — ` ```patch:<path>` 펜스의 SEARCH/REPLACE 블록을 exact / fuzzy / appended / ambiguous / no_match 5 가지 상태로 적용. 트랜잭셔널 보장. EOL 보존. | `src/agent_patch_applier.py` |
| 2 | **디스패처 patch 라우팅** — `_parse()` 의 `patch:` 분기 + `_exec_patch()` 어댑터 + filename 우선 정책(FR-111-25) | `src/agent_action_dispatcher.py` |
| 3 | **시스템 프롬프트 v1.0.111** — 의사결정 트리 + 선택지 A-1/A-2/B/C 분리 + 패치 예시 2 종 + "❌ 자주 하는 실수" | `src/agent_runner.py` |
| 4 | **체이닝 위험 명령 검사** — `_split_chained_segments()` / `_is_chain_dangerous()` 신설. 따옴표·이스케이프 인식 분리기. 두 곳의 단일-토큰 검사 치환. | `src/agent_runner.py` |
| 5 | **`_has_code_failure()` 확장** — `file` 액션(=patch 실패) 도 자기 수정 트리거 (FR-111-22) | `src/agent_runner.py` |
| 6 | **`auto_approve_file_mutation` patch 흐름 연동** — bypass / 세션 'A' 플래그가 patch 에도 동일 적용 | `src/agent_action_dispatcher.py` |

### 테스트 결과

| 모듈 | 테스트 수 | 결과 |
|---|---|---|
| `tests/test_agent_patch_applier.py` (신규, T-111-01 ~ T-111-20) | 22 | ✅ OK |
| `tests/test_agent_dispatcher_patch.py` (신규, T-111-30 ~ T-111-39) | 10 | ✅ OK |
| `tests/test_agent_system_prompt_v111.py` (신규, T-111-40 ~ T-111-44 + 회귀) | 7 | ✅ OK |
| `tests/test_agent_chain_danger.py` (신규, T-111-50 ~ T-111-56 + split 검증) | 12 | ✅ OK |
| `tests/test_agent_runner.py` (T-06 회귀 갱신) | 49 | ✅ OK |
| `tests/test_agent_action_dispatcher.py` | 16 | ✅ OK |
| `tests/test_os_utils_and_agent_prompt.py` (T-107-02/06 갱신) | 22 | ✅ OK |
| `tests/test_bypass_approvals.py` | 12 | ✅ OK |
| `tests/test_response_parser*.py` | 38 | ✅ OK |
| 기타 직접 영향 모듈 | 54 | ✅ OK |
| **합계 (직접 영향)** | **242** | **✅ 전체 통과** |

> 사전 환경 의존 실패(`test_api_logger.py`, PowerShell 격리 환경의 `test_code_executor*` /
> `test_terminal_executor_shell_dispatch.py`)는 본 릴리스 변경 이전부터 존재하며
> v1.0.115 와 무관함을 회귀 baseline 으로 확인.

### FSD 요구사항 매핑

| 영역 | 요구사항 | 구현 |
|---|---|---|
| Patch 형식·적용 | FR-111-01 ~ FR-111-10 | `AgentPatchApplier.parse_blocks` / `_apply_one` / `_align_replace_indent` |
| 승인·보안 | FR-111-11 ~ FR-111-16 | `_exec_patch` 의 auto_approve 게이트 + `_is_chain_dangerous` |
| 시스템 프롬프트 | FR-111-17 ~ FR-111-21 | `_build_system_prompt()` v1.0.111 본문 |
| 자기 수정·결과 표시 | FR-111-22 ~ FR-111-25 | `_has_code_failure` 확장 + dispatcher filename 우선 |
| NFR | NFR-111-01 ~ NFR-111-10 | stdlib only · O(N) 매칭 · in-memory 트랜잭션 |

### 미완료 (수동 확인 필요)

- [ ] Windows PowerShell / Linux 환경 `/agents` 자율 루프 patch 모드 수동 검증
  — 1줄 추가 / 함수 교체 / 다중 블록 / ambiguous → 자기 수정

---

## 변경 파일 목록

| 파일 | 유형 | 변경 내용 |
|---|---|---|
| `src/agent_patch_applier.py` | **신규** | `AgentPatchApplier` — SEARCH/REPLACE 파싱·적용·진단·EOL 보존 |
| `src/agent_action_dispatcher.py` | 수정 | `_ParsedAction.kind` 에 "patch" 추가, `_parse()` 의 `patch:` 분기, `dispatch()` 의 filename 우선 정책, `_exec_patch()` 어댑터 |
| `src/agent_runner.py` | 수정 | `_build_system_prompt()` v1.0.111 본문 교체, `_split_chained_segments()` / `_is_chain_dangerous()` 신설, 위험 검사 두 곳 치환, `_has_code_failure()` 에 `"file"` 추가, `_format_failure()` 메시지 갱신 |
| `tests/test_agent_patch_applier.py` | **신규** | T-111-01 ~ T-111-20 + 승인 흐름 |
| `tests/test_agent_dispatcher_patch.py` | **신규** | T-111-30 ~ T-111-39 |
| `tests/test_agent_system_prompt_v111.py` | **신규** | T-111-40 ~ T-111-44 + FR-111-19/20 회귀 |
| `tests/test_agent_chain_danger.py` | **신규** | T-111-50 ~ T-111-56 + 분리기 단위 |
| `tests/test_agent_runner.py` | 수정 | T-06 가 `file` 실패 트리거 정책에 맞춰 갱신 |
| `tests/test_os_utils_and_agent_prompt.py` | 수정 | v1.0.111 프롬프트 변화 반영 (T-107-02 / T-107-06) |
| `docs/requirements/FSD_v1.0.115_diff_patch.md` | 갱신 | § 10 승인 체크리스트 완료 표시 |

---

## 호환성

- 기존 ` ```filename:<path>` 블록 동작 불변 — 신규 파일 / 대규모 재작성 경로 보존 (NFR-111-09)
- `AgentSession` / `IterationRecord` / `ActionResult` 직렬화 호환성 유지
- `[REASON] / [ACT] / [OBSERVE]` 정규식 불변 — Vertex AI / Claude / GenAI 응답 호환
- Bypass Approvals (v1.0.100), Bypass Overwrite (v1.0.103), max_iterations (v1.0.101),
  Action Dispatcher (v1.0.107), Shell-Aware Executors (v1.0.110) 동작 불변

## 보안 강화

| 항목 | 이전 | v1.0.115 |
|---|---|---|
| `echo ok && rm -rf /` | `echo` 만 검사 → **승인 없이 실행** | 모든 세그먼트 검사 → 승인 요구 |
| `ls; rm -rf /` | `ls` 만 검사 → **승인 없이 실행** | `rm -rf /` 검출 → 승인 요구 |
| `false \|\| rm -rf /` | `false` 만 검사 → **승인 없이 실행** | 검출 → 승인 요구 |
| `echo "rm -rf /"` | `echo` (안전) | 따옴표 인식 → 안전(불변) |
| `cmd1 \\&\\& cmd2` | 분리 시도 | 이스케이프 인식 → 단일 세그먼트 |

## 비용 절감 (관찰)

- 1,000 줄 파일에 1 줄 추가 시: 모델 출력 토큰 ~6,000 → ~30 (**~200× 절감**)
- 5 회 iteration 가정: ~30,000 토큰 절약 = $0.10 ~ $0.50 (모델별)

---

## 후속 작업 (Phase 2 — 본 릴리스 비포함)

| 단계 | 내용 |
|---|---|
| 1 | Unified diff(`@@ ... @@`) 자동 변환기 |
| 2 | 멀티 파일 트랜잭션 |
| 3 | patch dry-run 모드 (`PATCH_DRY_RUN=1`) |
| 4 | AST 기반 patch (` ```patch-py:` 등) |
| 5 | git auto-commit per patch |
| 6 | backtick `` `...` `` / `$(...)` 안의 명령 위험 검사 |
