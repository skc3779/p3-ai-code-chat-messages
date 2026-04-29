# RELEASE v1.0.141 — `@@@filename:` / `@@@patch:` 신규 펜스 패턴 지원

**릴리스 일자**: 2026-04-28
**관련 모듈**: `AgentActionDispatcher`, `AgentRunner`

---

## 1. 변경 요약

AI 모델 응답 품질 개선을 위해 파일 저장(`filename:`) 및 패치(`patch:`)
액션의 펜스 마커를 백틱(```` ``` ````) 외에 `@@@`도 허용하도록 디스패처를
확장했다. 두 마커는 상호 호환되며, 기존 백틱 기반 응답도 그대로 동작한다.

| 패턴 | 기존 (v1.0.140 이하) | 신규 (v1.0.141) |
|---|---|---|
| 파일 저장 | ```` ```filename:경로/파일.py ... ``` ```` | `@@@filename:경로/파일.py ... @@@` |
| 패치 적용 | ```` ```patch:경로/파일.py ... ``` ```` | `@@@patch:경로/파일.py ... @@@` |
| 코드 블록 | ```` ```python ... ``` ```` | (변경 없음 — 표준 마크다운 펜스 유지) |
| 쉘 블록 | ```` ```bash ... ``` ```` | (변경 없음) |

> 시스템 프롬프트(`agent_runner.py::_build_system_prompt`)에서 신규 패턴을
> 모델에 안내하므로, 모델 응답이 `@@@`로 통일되어도 디스패처가 정상
> 라우팅한다.

---

## 2. 수정 파일

| 파일 | 변경 내용 |
|---|---|
| [src/agent_action_dispatcher.py](../../src/agent_action_dispatcher.py) | `_RE_FENCE_LINE` 정규식에 `@{3,}` 분기 추가 — 백틱과 `@@@`를 동등 펜스로 인식. depth-counting 로직은 길이 비교(`inner_len >= fence_len`)만 수행하므로 두 마커가 자연스럽게 호환된다. |
| [src/agent_runner.py](../../src/agent_runner.py) | `RE_FILENAME_BLOCK` 정규식을 `(?:` `{3,}` `\|@{3,})filename:` 로 확장 — `_save_file_blocks`가 `@@@filename:` 선언을 인식하도록 보강. |

### 변경 상세

**[src/agent_action_dispatcher.py:118-119](../../src/agent_action_dispatcher.py#L118-L119)**
```python
# v1.0.141 — `@@@` 도 펜스 마커로 인식 (filename:/patch: 전용 신규 패턴)
_RE_FENCE_LINE = re.compile(r'^[ \t]*(`{3,}|@{3,})(\S*)[ \t]*$')
```

**[src/agent_runner.py:91-92](../../src/agent_runner.py#L91-L92)**
```python
# v1.0.141 — `@@@filename:` 신규 패턴도 인식
RE_FILENAME_BLOCK = re.compile(r"(?:`{3,}|@{3,})filename:([^\n]+)", re.MULTILINE)
```

---

## 3. 테스트 결과

| 테스트 모듈 | 결과 | 건수 |
|---|---|---|
| `tests.test_agent_action_dispatcher` | ✅ OK | 37 |
| `tests.test_agent_dispatcher_patch` | ✅ OK | 10 |
| `tests.test_response_parser` (회귀) | ✅ OK | 13 |
| `tests.test_response_parser_overwrite` (회귀) | ✅ OK | 3 |
| **합계** | **✅ 전체 통과** | **63** |

> Windows 콘솔(cp949)에서 이모지 출력 시 `UnicodeEncodeError`가 발생할 수
> 있다. `PYTHONIOENCODING=utf-8` 환경 변수로 회피한다 (테스트 동작에는
> 영향 없음, 디스패처 로깅 출력 문제).

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m unittest tests.test_agent_action_dispatcher -v
python -m unittest tests.test_agent_dispatcher_patch -v
```

---

## 4. 동작 검증 케이스

테스트 케이스에서 확인된 핵심 시나리오:

| 케이스 | 입력 형태 | 결과 |
|---|---|---|
| T-107-09 | `@@@filename:a.py ... @@@` 단독 | file 1건 |
| T-107-13 | 멀티 `@@@filename:` 블록 | file 2건 |
| T-107-16 | `@@@filename:` 안에 ` ```python `, ` ```sql `, ` ```tree ` 중첩 | file 1건 (중첩 무시) |
| T-107-17 | filename 블록 내부 코드 + 외부 code/shell 혼합 | file 1, code 2, shell 1 |
| T-107-27 | 동일 파일 `@@@filename:` + `@@@patch:` | filename 우선, patch 보고만 (FR-111-25) |
| T-111-30 | `@@@patch:src/x.py ... @@@` 단독 | patch 1건 |
| T-111-32 | `@@@filename:` + `@@@patch:` 동일 파일 | filename 적용 + patch 스킵 보고 |
| T-111-37 | `@@@patch:a.txt` 두 번 연속 | 두 패치 모두 적용 |

---

## 5. 하위 호환성

- 기존 ```` ```filename: ```` / ```` ```patch: ```` 백틱 패턴은 그대로 동작
  (`_RE_FENCE_LINE`가 두 마커를 OR로 매칭).
- depth-counting 시 두 마커는 길이가 동일하므로(둘 다 3자) 상호 닫힘이
  허용된다 — 한 응답에 백틱과 `@@@`이 섞여 있어도 파싱이 끊기지 않는다.
- 모델 프롬프트에서 신규 패턴을 권장하지만, 구 패턴 응답은 그대로 처리.

---

## 6. 영향 범위

- 시스템 프롬프트(`agent_runner.py::_build_system_prompt`)가 `@@@` 패턴을
  안내하는 부분과 정합. 모델이 `@@@`로 응답하면 디스패처가 정상 라우팅.
- `response_parser.py`는 이미 `@@@filename:`을 인식하므로 추가 수정 없음
  ([src/response_parser.py:50-51](../../src/response_parser.py#L50-L51)).
- 코드/쉘 블록(```` ```python ````, ```` ```bash ```` 등)은 표준 마크다운
  펜스 그대로 유지 — `@@@`는 도입하지 않음 (혼란 방지).
