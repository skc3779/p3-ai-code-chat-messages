# FSD v1.1.033 — `/agents` 패치 매칭 실패 개선(difflib 유사도 기반 fuzzy matching)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1.033 |
| 작성일 | 2026-06-21 |
| 상태 | ✅ 구현 감사 및 보강 검증 완료 |
| 선행 문서 | FSD v1.0.115, FSD v1.0.107, REP v1.1.022 |
| 구현 파일 | `src/agent_patch_applier.py`, `src/agent_runner.py` |
| 테스트 파일 | `tests/test_agent_patch_similarity.py`, `tests/test_agent_patch_applier.py` |

---

## 1. 목적

기존 SEARCH/REPLACE 패치는 exact와 공백 정규화 fuzzy가 모두 실패하면 `no_match`를 반환했다. 긴 파일에서 모델이 SEARCH 블록을 거의 정확하게 작성했지만 주석·상수·짧은 내용이 일부 달라진 경우에도 패치가 반복 실패해 self-correction과 iteration을 소진할 수 있었다.

v1.1.033은 기존 cascade 뒤에 표준 라이브러리 `difflib.SequenceMatcher` 기반 `similar` tier를 추가한다.

```text
exact → ambiguous(exact count>1) → fuzzy(whitespace) → similar(difflib) → no_match
```

핵심 구현은 이미 존재하며 이번 감사에서는 알고리즘을 재작성하지 않았다. 다음 증거 기반 공백만 보강했다.

- 문서/코드/테스트 식별자를 v1.1.033으로 통일
- threshold의 NaN/inf/범위 밖 값 처리
- flex의 음수/과대 값 처리
- 성공을 강제하지 않던 indentation 테스트 수정
- 의미가 약했던 CRLF 테스트를 raw-byte 전체 결과 검증으로 수정
- high-confidence와 close runner-up 분기 직접 검증

---

## 2. 알고리즘 계약

### 2.1 후보 생성

1. working/search를 LF로 정규화하고 라인 배열로 분리한다.
2. SEARCH 라인 수를 `n`이라 할 때 `n-flex .. n+flex` 크기의 창을 순회한다.
3. `real_quick_ratio()`와 `quick_ratio()`가 threshold 미만인 후보를 먼저 제거한다.
4. `ratio() >= threshold` 후보를 `(ratio, start, size)`로 수집한다.
5. 동일 위치의 크기 변형은 경쟁 후보로 보지 않고, best와 겹치지 않는 첫 후보를 second로 사용한다.

### 2.2 적용 판정

고정 상수:

| 상수 | 값 | 의미 |
|---|---:|---|
| `TIE_EPSILON` | `0.01` | best-second가 이 값 미만이면 동률 |
| `UNIQUENESS_MARGIN` | `0.05` | 일반 후보가 확보해야 하는 차이 |
| `HIGH_CONFIDENCE_RATIO` | `0.95` | 고신뢰 best 기준 |

판정 순서:

1. second가 threshold 이상이고 `gap < 0.01`이면 `ambiguous`
2. tie가 아니고 `best >= 0.95`이면 `similar` 적용
3. 그 외 `gap < 0.05`이면 `ambiguous`
4. 나머지는 `similar` 적용

동률은 high-confidence여도 적용하지 않는다. 반복 코드의 잘못된 블록을 선택하는 것보다 명시적 실패가 안전하기 때문이다.

### 2.3 적용 및 호환성

- REPLACE는 `_align_replace_indent()`로 실제 매칭 위치의 indentation에 맞춘다.
- 원본에 CRLF가 있으면 결과 전체를 CRLF로 복원한다.
- `similar`는 transactional 성공 상태에 포함된다.
- 한 블록이라도 `ambiguous`/`no_match`면 디스크를 변경하지 않는다.
- exact와 whitespace fuzzy가 항상 similar보다 우선한다.
- 실패 진단은 SEARCH 정확 복사 또는 `@@@filename:` 전체 재작성으로 전환하도록 안내한다.

---

## 3. 요구사항

| ID | 요구사항 | 구현 |
|---|---|---|
| FR-033-01 | whitespace fuzzy 실패 후 difflib similar tier 수행 | ✅ |
| FR-033-02 | threshold 미만 후보는 적용하지 않음 | ✅ |
| FR-033-03 | 겹치지 않는 후보의 tie는 `ambiguous` 및 무변경 | ✅ |
| FR-033-04 | non-tie best가 0.95 이상이면 close runner-up이 있어도 적용 | ✅ |
| FR-033-05 | similar 적용 시 indentation 정렬 | ✅ |
| FR-033-06 | CRLF 원본의 EOL 보존 | ✅ |
| FR-033-07 | exact/fuzzy 우선순위 보존 | ✅ |
| FR-033-08 | 다중 블록 transactional 보장 | ✅ |
| FR-033-09 | no-match/ambiguous 진단에 전체 재작성 전환 안내 | ✅ |
| FR-033-10 | env로 similar 비활성화 및 threshold/flex 조정 | ✅ |
| FR-033-11 | threshold/flex 잘못된 값은 bounded 기본값으로 복원 | ✅ |

비기능 요구사항:

| ID | 요구사항 | 구현 |
|---|---|---|
| NFR-033-01 | 신규 외부 의존성 없이 표준 라이브러리만 사용 | ✅ |
| NFR-033-02 | quick ratio 선차단으로 전체 ratio 계산 축소 | ✅ |
| NFR-033-03 | 기존 patch 승인·쓰기·진단 흐름 보존 | ✅ |
| NFR-033-04 | similarity off 시 기존 cascade 보존 | ✅ |

---

## 4. 환경변수

| 변수 | 기본값 | 유효 계약 |
|---|---:|---|
| `AGENT_PATCH_SIMILARITY` | `1` | `0`이면 비활성, 그 외에는 기존 호환상 활성 |
| `AGENT_PATCH_FUZZY_THRESHOLD` | `0.85` | 유한수 `0.0..1.0`; 문자열/NaN/inf/범위 밖은 `0.85` |
| `AGENT_PATCH_FUZZY_FLEX` | `2` | 정수 `0..20`; 문자열/음수/과대는 `2` |

threshold와 flex 검증은 `AgentPatchApplier.__init__()`에서 수행된다. NaN은 비교식에서 자동 차단되지 않으므로 `math.isfinite()` 검사가 필수다.

---

## 5. 테스트 계약

`tests/test_agent_patch_similarity.py`는 다음 16개 시나리오를 검증한다.

| ID | 검증 |
|---|---|
| T-033-01 | content drift가 `similar`로 적용 |
| T-033-02 | threshold 미만은 `no_match` |
| T-033-03 | 두 유사 블록 tie는 `ambiguous`, 디스크 무변경 |
| T-033-04 | similarity env off 시 기존 `no_match` |
| T-033-05 | threshold override가 낮은 ratio를 차단 |
| T-033-06 | 긴 파일에서 목표 함수만 교체 |
| T-033-07 | exact 우선 |
| T-033-08 | whitespace fuzzy 우선 |
| T-033-09 | similar 성공 강제 + raw bytes 전체 결과로 CRLF/lone LF/lone CR 검증 |
| T-033-10 | 실패 진단의 `@@@filename:` 전환 안내 |
| T-033-11 | similar 성공/status 강제 + 클래스 메서드 indentation 전체 검증 |
| T-033-12 | mixed block 실패 시 transactional 무변경 |
| T-033-13 | `best>=.95`, `.01<=gap<.05`인 close runner-up에서 high-confidence 적용 |
| T-033-14 | threshold NaN/inf/음수/초과/문자열 기본값 복원 |
| T-033-15 | flex 음수/초과/문자열 기본값 복원 |
| T-033-16 | threshold 0에서 second 후보 없음 sentinel을 tie로 오판하지 않음 |

T-033-09와 T-033-11은 `if result.success:` 같은 조건부 assertion을 사용하지 않는다. 먼저 `success=True`와 `status="similar"`를 강제하므로 실패 경로가 테스트를 우회할 수 없다.

---

## 6. 구현 완료 체크리스트

### 문서/코드 정합성

- [x] 파일명, H1, 문서 버전, FR/NFR/T ID를 v1.1.033으로 통일
- [x] `BlockResult.status` 설명에 `similar` 포함
- [x] 코드 주석의 REP 식별자 v1.1.033 통일
- [x] 실제 env bounds와 fallback 문서화
- [x] 범위 밖 RELEASE note를 완료 조건에서 제거

### 구현 감사

- [x] exact → fuzzy → similar cascade 보존
- [x] overlap 제외 second 후보 및 tie/high-confidence/margin 순서 확인
- [x] transactional apply 상태에 `similar` 포함 확인
- [x] indentation 및 CRLF 복원 경로 확인
- [x] threshold 유한 `[0,1]` 검증 추가
- [x] flex 정수 `[0,20]` 검증 추가

### 테스트 보강 및 검증

- [x] vacuous indentation test 제거
- [x] CRLF raw-byte full-output 검증
- [x] high-confidence close-runner-up 직접 테스트
- [x] threshold/flex invalid env 테스트
- [x] `python -m pytest tests/test_agent_patch_similarity.py tests/test_agent_patch_applier.py -q` — **38 passed, 9 subtests passed**
- [x] 두 REP 및 `/agents` 관련 회귀 묶음 — **254 passed, 9 subtests passed**
- [x] 전체 저장소 테스트 실행 — **803 passed, 4 skipped, 63 subtests passed**, 범위 밖 기존 실패 8건/수집 오류 2건 별도 확인
- [x] 독립 code review — **APPROVE**
- [x] adversarial QA — ambiguity/CRLF/indentation/env bounds/transactionality 재검증 **CLEAN**

전체 테스트의 잔여 실패 분류는 REP v1.1.032의 검증 체크리스트와 같으며 fuzzy patch 변경과 관련된 회귀는 없다.

---

## 7. 잔여 리스크와 후속 범위

1. `SequenceMatcher`는 큰 파일과 큰 SEARCH의 조합에서 비용이 증가한다. quick ratio 선차단과 flex 상한으로 제한하지만, 실사용 성능 데이터가 필요하면 별도 benchmark FSD로 다룬다.
2. 반복도가 높은 코드에서 tie는 의도적으로 자동 적용하지 않는다. 더 유일한 SEARCH 또는 전체 재작성이 필요하다.
3. 동일 파일 연속 실패 횟수에 따른 A-1 강제 전환은 세션 상태 변경이 필요하므로 별도 요구사항으로 남긴다.
