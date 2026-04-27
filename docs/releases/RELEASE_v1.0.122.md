# RELEASE v1.0.122 — AgentActionDispatcher 중첩 펜스 버그 수정 + patch/ACTION 태그 단위테스트

| 항목 | 내용 |
|---|---|
| 릴리스 버전 | v1.0.122 |
| 작성일 | 2026-04-27 |
| 선행 문서 | BUG v1.0.121 (중첩 펜스 조기 종료), FSD v1.0.115 (Diff/Patch 모드), FSD v1.0.107 (지능형 디스패처) |
| 상태 | ✅ 구현 완료 |

---

## 변경 요약

`AgentActionDispatcher._parse()` 의 **중첩 펜스 파싱 버그(BUG v1.0.121)** 수정과 함께,
**선택지 A-2(patch)** 및 **`[ACTION:*]` 명시 태그** 영역의 단위테스트를 보완한다.

### 핵심 변경사항

| # | 변경 내용 | 파일 |
|---|---|---|
| 1 | **`_parse()` depth-counting 재작성** — `RE_FENCE` non-greedy 방식 → 라인 단위 depth-counting 파서. `filename:`/`patch:` 내부 중첩 펜스를 올바르게 처리 | `src/agent_action_dispatcher.py` |
| 2 | **`explicit_tag` 감지 구현** — `RE_ACTION_TAG` 정규식을 실제 파싱에 연결. `[ACTION:*]` 태그 포함 시 모든 파싱 액션에 `explicit_tag=True` 설정 | `src/agent_action_dispatcher.py` |
| 3 | **TestDispatcherPatch 신규** (T-107-24 ~ T-107-29) — patch: 블록 파싱/dispatch 성공, 실패+diagnostic, filename 우선(FR-111-25), 경로 없음, 다중 SEARCH/REPLACE | `tests/test_agent_action_dispatcher.py` |
| 4 | **TestDispatcherActionTagsExplicit 신규** (T-107-30 ~ T-107-36) — `[ACTION:*]` 태그 explicit_tag 설정, REQUIRED 모드 통과/거부, 다중 액션 일괄 태깅 | `tests/test_agent_action_dispatcher.py` |

---

## 버그 수정 상세 (BUG v1.0.121)

### 증상
`filename:` 블록 내부에 중첩된 코드 펜스(`` ``` ``)가 있을 때, 파서가 외부 블록을 조기 종료시켜
1개 파일 블록이 여러 독립 액션으로 분해되는 현상.

### 원인
```python
# 수정 전 — RE_FENCE non-greedy .*? 가 첫 번째 ``` 에서 멈춤
RE_FENCE = re.compile(
    r"^[ \t]*(`{3,})(\w*(?::[\S]*)?)[ \t]*\n(.*?)\n[ \t]*\1[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
```

### 해결
```python
# 수정 후 — 라인 단위 depth-counting
_RE_FENCE_LINE = re.compile(r'^[ \t]*(`{3,})(\S*)[ \t]*$')

# 열기 태그 있음 → depth++, 닫기(태그 없음) → depth--
# depth==0 이 진짜 닫힘 위치
```

### 수정된 케이스

| 테스트 | 수정 전 | 수정 후 |
|---|---|---|
| `test_T107_16_nested_code_shell_in_filename_block` | FAILED (file 1 + code 1 + shell 1) | PASSED (file 1) |
| `test_T107_16_nested_not_code_shell_in_filename_block` | FAILED | PASSED (file 1) |
| `test_T107_16_nested_not_code_shell_in_multi_filename_block` | FAILED (file 1 누락) | PASSED (file 2) |

---

## explicit_tag 구현 상세

### 기존 상태
`RE_ACTION_TAG` 클래스 변수는 정의되어 있었으나 `_parse()` 에서 실제로 사용되지 않아
`explicit_tag` 가 항상 `False` 로 유지되는 미완성 상태.

### 수정 내용

`_parse()` 마지막에 `RE_ACTION_TAG.search(act_text)` 를 추가, 매칭 시 모든 파싱된
액션에 `explicit_tag=True` 를 일괄 설정:

```python
# [ACTION:*] 태그 감지 → explicit_tag 설정 (AGENT_ACTION_TAGS_REQUIRED 모드 통과용)
if self.RE_ACTION_TAG.search(act_text):
    for a in actions:
        a.explicit_tag = True
```

### 동작 결과

| 시나리오 | AGENT_ACTION_TAGS_REQUIRED | explicit_tag | 결과 |
|---|---|---|---|
| `[ACTION:shell]\n$ git status` | 0 (기본) | True | 정상 실행 |
| `[ACTION:shell]\n$ git status` | 1 | True | **통과** (거부 없음) |
| `$ git status` | 1 | False | 거부 → 안내 메시지 |

---

## 테스트 결과

### 신규 테스트 (14건)

**TestDispatcherPatch (T-107-24 ~ T-107-29)**

| ID | 케이스 | 결과 |
|---|---|---|
| T-107-24 | `patch:path` 블록 → kind='patch', filepath/payload 정확 | ✅ PASSED |
| T-107-25 | dispatch 성공 → AgentPatchApplier 호출, file ActionResult(success=True) | ✅ PASSED |
| T-107-26 | 적용 실패 → success=False + diagnostic detail | ✅ PASSED |
| T-107-27 | 동일 파일 filename+patch → filename 우선, patch 건너뜀 보고 (FR-111-25) | ✅ PASSED |
| T-107-28 | `patch:` 경로 없음 → '미지정' 실패 | ✅ PASSED |
| T-107-29 | 다중 SEARCH/REPLACE 쌍 → payload 에 두 쌍 모두 포함 | ✅ PASSED |

**TestDispatcherActionTagsExplicit (T-107-30 ~ T-107-36)**

| ID | 케이스 | 결과 |
|---|---|---|
| T-107-30 | `[ACTION:shell]` → shell action explicit_tag=True | ✅ PASSED |
| T-107-31 | `[ACTION:code]` → code action explicit_tag=True | ✅ PASSED |
| T-107-32 | `[ACTION:file]` → file action explicit_tag=True | ✅ PASSED |
| T-107-33 | 태그 없음 → explicit_tag=False (기본값) | ✅ PASSED |
| T-107-34 | REQUIRED=1 + `[ACTION:shell]` → 거부 없이 shell 실행 | ✅ PASSED |
| T-107-35 | REQUIRED=1 + 태그 없음 → 안내 메시지 1건 | ✅ PASSED |
| T-107-36 | `[ACTION:shell]` + 다중 shell 라인 → 모든 액션 explicit_tag=True | ✅ PASSED |

### 전체 테스트 현황

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| `tests/test_agent_action_dispatcher.py` | 23 (2 FAILED) | **37 (37 PASSED)** |

---

## 변경 파일 목록

| 파일 | 유형 | 변경 내용 |
|---|---|---|
| `src/agent_action_dispatcher.py` | 수정 | `_RE_FENCE_LINE` 클래스 변수 추가, `_parse()` depth-counting 재작성, `explicit_tag` 감지 로직 추가 |
| `tests/test_agent_action_dispatcher.py` | 수정 | `TestDispatcherPatch` (6건), `TestDispatcherActionTagsExplicit` (7건) 추가 |
| `docs/requirements/BUG_v1.0.121_nested-fence-in-filename-block.md` | **신규** | 버그 원인·해결방법 분석 문서 |

---

## 호환성

- 기존 `dispatch()` 공개 인터페이스 불변
- `RE_FENCE` 클래스 변수 유지 (외부 참조 호환) — 내부 파싱에는 미사용
- `_ParsedAction.explicit_tag` 기본값 `False` 유지 — `[ACTION:*]` 태그 없는 기존 ACT 동작 불변
- `AgentSession`, `ActionResult`, `IterationRecord` 직렬화 호환성 유지
- v1.0.115 patch 라우팅, v1.0.107 디스패처, v1.0.100 bypass 동작 불변
