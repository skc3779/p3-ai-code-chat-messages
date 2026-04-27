# BUG v1.0.121: filename 블록 내부 중첩 펜스에 의한 파싱 조기 종료 문제

## 1. 개요

- **이슈명**: `AgentActionDispatcher._parse()` 가 `filename:` (및 `patch:`) 블록 내부에 중첩된 코드 펜스(`` ``` ``)를 만나면 외부 블록을 조기 종료시켜, 1개 파일 블록이 여러 개의 단편으로 쪼개지는 버그
- **관련 모듈**: `src/agent_action_dispatcher.py`
- **관련 테스트**:
  - `test_T107_16_nested_code_shell_in_filename_block` (FAILED → PASSED)
  - `test_T107_16_nested_not_code_shell_in_filename_block` (FAILED → PASSED)
  - `test_T107_16_nested_not_code_shell_in_multi_filename_block` (FAILED → PASSED)
- **수정 버전**: v1.0.121

---

## 2. 재현 시나리오

아래 ACT 블록을 `dispatch()` 에 전달하면:

````
```filename:file1.md

## 소개
- 항목1

```python
print("hello")
```

```javascript
console.log("hi");
```

$ Write-Host "shell"

```
````

**기대**: `file` 1건, `code` 0건, `shell` 0건  
**실제**: `file` 1건 + `code` 1~2건 + `shell` 1건 (내부 블록이 독립 액션으로 분리됨)

---

## 3. 근본 원인 분석

### 3.1 문제가 된 코드 (`RE_FENCE` 정규식)

```python
RE_FENCE = re.compile(
    r"^[ \t]*(`{3,})(\w*(?::[\S]*)?)[ \t]*\n(.*?)\n[ \t]*\1[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
```

`.*?` 는 **non-greedy** 매칭이다. `re.DOTALL` 로 개행을 포함하지만, 닫힘 패턴(`\1`)에 처음 매칭되는 위치에서 바로 멈춘다.

### 3.2 파싱 흐름 (버그)

```
```filename:file1.md     ← RE_FENCE 캡처 시작
...
```python                 ← 이 시점에서 `RE_FENCE` 가 다른 매치 시작
print("hello")
```                       ← ★ non-greedy 로 인해 file1.md 의 닫힘으로 오인식
```

`finditer` 가 왼쪽-우선, non-greedy 로 실행되므로:

1. `` ```filename:file1.md `` ~ 첫 번째 내부 ` ``` ` 가 **file 블록**으로 매치
2. 남은 텍스트에서 `` ```javascript `` ~ `` ``` `` 가 **code 블록**으로 매치
3. `$ Write-Host "shell"` 이 펜스 외부로 남아 **shell 액션**으로 매치

결국 1개 파일 블록이 분해된다.

### 3.3 멀티 filename 블록의 추가 문제

`test_T107_16_nested_not_code_shell_in_multi_filename_block` 에서는 `file1.py` 와 `file2.py` 각각이 내부 중첩 펜스를 포함한다. non-greedy 매칭으로 인해 `file1.py` 의 닫힘 위치가 `file2.py` 헤더 앞의 빈 ` ``` ` 가 아닌 `file1.py` 내부 첫 번째 ` ``` ` 로 잘못 결정되고, 이후 남은 ` ```sql ... ``` ` 등이 unknown-tag 블록으로 처리되어 `file2.py` 자체가 인식되지 않았다.

---

## 4. 해결 방법

### 4.1 핵심 아이디어: depth-counting 라인 파서

정규식 한 방으로 전체 펜스 범위를 구하려는 접근 대신,  
**라인 단위로 순회하면서 펜스 depth 를 직접 추적**한다.

- 태그가 있는 `` ``` `` 열기 라인 → `depth++`
- 태그가 없는 `` ``` `` 닫기 라인 → `depth--`
- `depth == 0` 이 되는 순간이 진짜 외부 블록의 닫힘

이 방식은 CommonMark 수준의 중첩 구조를 정확히 추적한다.

### 4.2 구현 (`_parse` 교체)

`RE_FENCE` 기반 `finditer` + 마스킹 방식을 제거하고,  
`_RE_FENCE_LINE` (단일 라인 매처) + `covered[]` 배열로 교체했다.

```python
_RE_FENCE_LINE = re.compile(r'^[ \t]*(`{3,})(\S*)[ \t]*$')

def _parse(self, act_text: str) -> List[_ParsedAction]:
    lines = act_text.split('\n')
    covered = [False] * len(lines)

    i = 0
    while i < len(lines):
        m = self._RE_FENCE_LINE.match(lines[i])
        if not m:
            i += 1
            continue

        fence_len = len(m.group(1))
        tag = m.group(2).strip()

        # depth-counting 으로 matching closing fence 탐색
        depth = 1
        j = i + 1
        while j < len(lines):
            inner = self._RE_FENCE_LINE.match(lines[j])
            if inner:
                inner_len = len(inner.group(1))
                inner_tag = inner.group(2).strip()
                if inner_len >= fence_len and not inner_tag:
                    depth -= 1
                    if depth == 0:
                        break
                elif inner_tag:
                    depth += 1
            j += 1

        if depth != 0:   # 닫히지 않은 펜스 — 무시
            i += 1
            continue

        content = '\n'.join(lines[i + 1: j])
        for k in range(i, j + 1):
            covered[k] = True

        # ... (기존 filename/patch/code/shell 분기는 동일)

        i = j + 1

    # 펜스 바깥의 $ 쉘 라인 추출 (covered 배열로 중복 방지)
    for k, line in enumerate(lines):
        if not covered[k]:
            m = self.RE_SHELL_LINE.match(line)
            if m:
                ...
```

**기존 마스킹 방식(`masked = list(act_text)`) 완전 제거** — `covered[]` 배열이 동일 역할을 수행.

### 4.3 depth 규칙 상세

| 조건 | 동작 |
|---|---|
| `` inner_tag != "" `` (예: `` ```python ``) | `depth++` (중첩 블록 열기) |
| `` inner_tag == "" `` AND `inner_len >= fence_len` | `depth--` (닫기 후보) |
| `depth == 0` | **진짜 닫힘 — 탐색 종료** |
| 루프 끝까지 `depth != 0` | 미닫힌 펜스 → 블록 전체 무시 |

---

## 5. 수정 전후 동작 비교

### 5.1 `test_T107_16_nested_code_shell_in_filename_block`

```
입력:
```filename:file1.md
...
```python
print("hello")
```
...
```
```

| | 수정 전 | 수정 후 |
|---|---|---|
| file | 1 (잘린 payload) | 1 (전체 payload) |
| code | 1 (python 블록) | **0** |
| shell | 1 ($ Write-Host) | **0** |

### 5.2 `test_T107_16_nested_not_code_shell_in_multi_filename_block`

| | 수정 전 | 수정 후 |
|---|---|---|
| file | **1** (file2.py 누락) | **2** |
| code | 0 | 0 |
| shell | 0 | 0 |

---

## 6. 영향 범위

- **수정 파일**: `src/agent_action_dispatcher.py` — `_parse()` 메서드 전체 교체, `_RE_FENCE_LINE` 클래스 변수 추가
- **기존 `RE_FENCE`**: 클래스 변수로 유지 (외부 참조 호환), 내부 파싱에는 미사용
- **다른 메서드 변경 없음**: `_classify_shell_block`, `_strip_dollar`, `_dedupe`, 실행 어댑터 계열 모두 그대로
- **기존 23개 테스트 전부 PASSED** 확인
