# BUG v1.0.062 - 다중 마크다운 코드 블록 파싱 시 파일 내용 일부 누락

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.062 |
| 제목 | `_auto_save_files` / `parse_and_save` — 언어 태그 없는 코드 블록 포함 시 파일 내용 조기 종료 |
| 작성일 | 2026-03-02 |
| 상태 | 수정 완료 |
| 관련 FSD | [FSD v1.0.049](./FSD_v1.0.049_context-file-auto-processing.md) — Context 파일 자동 처리 |
| 수정 대상 | [context_processor.py](../../../src/context_processor.py), [response_parser.py](../../../src/response_parser.py) |

---

## 1. 버그 설명

### 1.1 증상

`/auto_context` 명령어 또는 `/save` 명령어로 AI 응답의 파일 블록을 저장할 때, **마크다운 내부에 언어 태그가 없는 코드 블록**이 포함되어 있으면 해당 코드 블록의 시작 위치에서 **파일 내용이 조기 종료**되어 일부만 저장됩니다.

### 1.2 재현 조건

AI 응답에 다음과 같이 언어 태그가 없는 코드 블록(` ``` `)이 포함된 마크다운 파일 블록이 있을 때 발생합니다:

````
```filename:md_excel2/IF_XXXX.md

## 상세 설계서

### 3. SQL

```sql
SELECT * FROM table;
```

### 4. 프로세스 흐름

```
root
├── child1          ← 이 블록의 ``` 가 파일 종료로 오인됨
└── child2
```

### 5. 가용 명령어    ← 이 섹션 이후 내용이 모두 누락됨

* Item 1

```
````

**저장 결과**: Section 1~3까지만 저장되고, Section 4의 tree 구조 블록 이후 내용 전체가 누락됩니다.

### 1.3 원인 분석

#### 근본 원인: 중첩 코드 블록 시작 감지 조건의 한계

```python
# context_processor.py / response_parser.py (수정 전)
if stripped.startswith(delimiter) and len(stripped) > len(delimiter):
    nested_block_depth += 1        # 중첩 블록 시작
elif stripped == delimiter:
    if nested_block_depth > 0:
        nested_block_depth -= 1    # 중첩 블록 종료
    else:
        # ← 파일 블록 종료로 처리 (조기 종료!)
```

중첩 코드 블록 시작을 판별하는 조건이 `len(stripped) > len(delimiter)` 으로, **언어 태그가 있는 경우에만** 동작합니다:

| 내부 블록 형태 | `startswith("` `` ` `` `")` | `len > 3` | 중첩 감지 | 결과 |
|---|---|---|---|---|
| ` ```sql ` | ✅ | ✅ (len=6) | ✅ 감지됨 | 정상 |
| ` ```python ` | ✅ | ✅ (len=9) | ✅ 감지됨 | 정상 |
| ` ```tree ` | ✅ | ✅ (len=7) | ✅ 감지됨 | 정상 |
| ` ``` ` (태그 없음) | ✅ | ❌ (len=3) | ❌ **미감지** | **조기 종료** |

언어 태그 없는 ` ``` `는 중첩 시작으로 인식되지 않고, `stripped == delimiter` 조건에 따라 **파일 블록 종료**로 처리됩니다.

#### 영향 범위

| 모듈 | 메서드 | 사용처 |
|------|--------|--------|
| `ContextProcessor` | `_auto_save_files()` | `/auto_context` 명령어 — 확인 없이 자동 저장 |
| `ResponseParser` | `parse_and_save()` | `/save` 명령어 — 확인 후 저장 |

두 메서드가 동일한 파싱 로직을 사용하므로, 동일한 버그가 발생합니다.

---

## 2. 수정 내역

### 2.1 핵심 변경: `nested_block_depth` → `in_nested_block` + lookahead

기존의 단순 depth 카운터 방식을 **플래그 기반 + 다음 줄 선행 확인(lookahead)** 방식으로 변경합니다.

#### 수정 전 (context_processor.py L152-159)

```python
# 중첩 코드 블록 시작
if stripped.startswith(delimiter) and len(stripped) > len(delimiter):
    nested_block_depth += 1
# 코드 블록 종료 후보
elif stripped == delimiter:
    if nested_block_depth > 0:
        nested_block_depth -= 1
    else:
        # 파일 저장 (조기 종료!)
```

#### 수정 후

```python
# 1) 언어 태그가 있는 코드 블록 시작 (```python, ```sql 등)
if stripped.startswith(delimiter) and len(stripped) > len(delimiter):
    in_nested_block = True
    current_content.append(line)
    continue

# 2) 정확히 delimiter만 있는 줄
if stripped == delimiter:
    # 2-a) 내부 블록이 열려있으면 → 내부 블록 종료
    if in_nested_block:
        in_nested_block = False
        current_content.append(line)
        continue

    # 2-b) 다음 줄을 확인하여 내부 코드 블록 시작 vs 파일 종료 판별
    next_idx = idx + 1
    if next_idx < len(lines):
        next_stripped = lines[next_idx].strip()
        is_next_delimiter = next_stripped == delimiter
        is_next_filename = re.match(r"^`{3,}filename:.+$", next_stripped)
        if (
            next_stripped
            and not is_next_delimiter
            and not is_next_filename
        ):
            in_nested_block = True      # 언어 태그 없는 내부 코드 블록 시작
            current_content.append(line)
            continue

    # 2-c) 파일 블록 종료 → 저장
```

#### 판별 로직 요약

` ``` `가 나타났을 때의 처리 흐름:

```
``` 발견
 ├── in_nested_block == True → 내부 블록 종료 (컨텐츠에 포함)
 └── in_nested_block == False
      ├── 다음 줄이 비어있지 않고 ``` 또는 ```filename:이 아님
      │    → 언어 태그 없는 내부 코드 블록 시작
      └── 다음 줄이 비어있거나 ``` 또는 ```filename: 또는 EOF
           → 파일 블록 종료 → 저장
```

### 2.2 `context_processor.py` 수정

| 변경 항목 | 수정 전 | 수정 후 |
|-----------|---------|---------|
| 상태 변수 | `nested_block_depth: int = 0` | `in_nested_block: bool = False` |
| 루프 | `for line in lines:` | `for idx, line in enumerate(lines):` |
| 태그 있는 블록 시작 | `nested_block_depth += 1` | `in_nested_block = True` + 컨텐츠 추가 |
| 태그 없는 블록 시작 | ❌ 미지원 | ✅ lookahead로 판별 |
| 블록 종료 | `nested_block_depth -= 1` | `in_nested_block = False` + 컨텐츠 추가 |

### 2.3 `response_parser.py` 수정

`context_processor.py`와 동일한 로직을 `parse_and_save()` 메서드에 적용합니다. 파일 이미 존재 시 확인 프롬프트 로직은 유지합니다.

---

## 3. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `src/context_processor.py` | **수정** | `_auto_save_files()` 중첩 블록 감지 로직 개선 |
| `src/response_parser.py` | **수정** | `parse_and_save()` 동일 로직 적용 |
| `tests/test_context_processor.py` | **추가** | 신규 테스트 케이스 5개 추가 |

---

## 4. 검증 시나리오

### 4.1 단위 테스트 (신규 추가)

| # | 테스트명 | 시나리오 | 판정 |
|---|---------|---------|:----:|
| 1 | `test_auto_save_untagged_code_block` | 언어 태그 없는 단일 ` ``` ` 블록이 포함된 파일 저장 | ✅ |
| 2 | `test_auto_save_multiple_untagged_code_blocks` | 태그 없는 블록 2개가 연속으로 포함된 파일 저장 | ✅ |
| 3 | `test_auto_save_mixed_tagged_untagged_blocks` | SQL(태그 있음) + tree(태그 없음) 혼합 파일 저장 | ✅ |
| 4 | `test_auto_save_complex_markdown_full` | SQL + tree + 테이블 + 5개 섹션 전체 저장 (사용자 예시 기반) | ✅ |
| 5 | `test_auto_save_multi_file_with_untagged_blocks` | 다중 파일 블록에서 각각 태그 없는 코드 블록 처리 | ✅ |

### 4.2 기존 테스트 회귀 검증

| # | 테스트명 | 시나리오 | 판정 |
|---|---------|---------|:----:|
| 1 | `test_process_single_file_with_auto_save` | 단일 파일 처리 + 자동 저장 | ✅ |
| 2 | `test_process_multiple_files` | 여러 파일 순차 처리 | ✅ |
| 3 | `test_multiple_output_files_per_input` | 1개 입력 → 다중 출력 | ✅ |
| 4 | `test_no_filename_block_in_response` | filename 블록 없는 응답 | ✅ |
| 5 | `test_build_prompt` | 프롬프트 조합 | ✅ |
| 6 | `test_auto_save_creates_parent_dirs` | 상위 디렉토리 자동 생성 | ✅ |
| 7 | `test_auto_save_overwrites_existing` | 기존 파일 자동 덮어쓰기 | ✅ |
| 8 | `test_auto_save_nested_code_blocks` | 중첩 코드 블록 (태그 있음) | ✅ |
| 9 | `test_file_read_failure_continues` | 파일 읽기 실패 시 다음 파일 계속 | ✅ |

### 4.3 전체 테스트

```
Ran 171 tests in 63.554s
OK
```

---

## 5. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1.0.062 | 2026-03-02 | 최초 작성: `_auto_save_files` / `parse_and_save` 언어 태그 없는 코드 블록 파싱 버그 수정 |
