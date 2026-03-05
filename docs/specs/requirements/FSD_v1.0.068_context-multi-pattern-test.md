# FSD v1.0.068 - `/context` · `/auto_context` 파일 패턴 매칭 테스트

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.068 (테스트) |
| 제목 | `/context` · `/auto_context` 파일 패턴 매칭 테스트 |
| 작성일 | 2026-03-05 |
| 상태 | 작성 완료 |
| 관련 FSD | [FSD v1.0.068](./FSD_v1.0.068_context-multi-pattern.md) — `/context` 다중 파일 패턴 지원 통일 |
| 대상 소스 | `gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py` |

---

## 1. 개요 (Overview)

FSD v1.0.068에서 정의한 `/context` 명령어의 다중 파일 패턴 지원이 3개 스크립트(`gen-ai`, `claude`, `gemini`)에서 올바르게 동작하는지 검증하는 테스트 시나리오입니다. `/auto_context`도 `/context`와 동일한 패턴 파싱 로직을 사용하므로, 아래 모든 시나리오는 두 명령어 모두에 동일하게 적용됩니다.

### 1.1 테스트 대상

| 항목 | 설명 |
|------|------|
| 명령어 파싱 | 사용자 입력에서 파일 패턴과 질문을 정확히 분리하는가 |
| 파일 패턴 매칭 | 분리된 패턴으로 `FilePatternMatcher`가 올바른 파일을 선별하는가 |
| 멀티라인 폴백 | 질문이 생략된 경우 멀티라인 입력 모드로 전환되는가 |
| 에러 처리 | 잘못된 입력에 대해 적절한 에러 메시지를 출력하는가 |

### 1.2 패턴 매칭 엔진 사양

현재 프로젝트의 `FilePatternMatcher`(`src/file_pattern_matcher.py`)는 Python 표준 라이브러리 **`fnmatch`** 를 사용합니다. `fnmatch`가 지원하는 패턴 문법은 다음과 같습니다:

| 패턴 | 의미 | 예시 |
|------|------|------|
| `*` | 경로 구분자(`/`)를 제외한 0개 이상의 임의 문자 | `*.py` → `file.py` ✅, `src/file.py` ❌ |
| `?` | 임의 1글자 | `file?.py` → `file1.py` ✅ |
| `[seq]` | `seq` 중 1글자 | `file[0-9].py` → `file3.py` ✅ |
| `[!seq]` | `seq` 이외의 1글자 | `file[!0-9].py` → `fileA.py` ✅ |

> **⚠️ 주의:** `fnmatch`는 `**`(재귀 글로빙)과 정규식(`\d{4}`, `(jpg|png)`)을 **지원하지 않습니다**.  
> - `src/**/*.py` → `**`는 `*`와 동일하게 동작하여, `src/하위폴더/file.py`와 같은 깊은 경로는 매칭되지 않습니다.  
> - `\d{4}`, `(jpg|png)` 등 정규표현식 구문은 패턴으로 인식되지 않습니다.

### 1.3 매칭 우선순위

`FilePatternMatcher.match()` 메서드는 다음 순서로 매칭을 시도합니다:

```
1. 상대경로 전체 매칭:  fnmatch(rel_path, pattern)
     예: "src/*.py" → "src/file.py" ✅
2. 파일명만 매칭:       fnmatch(filename, pattern)
     예: "*.py" → 모든 .py 파일 ✅
3. 경로 부분 매칭:      fnmatch(rel_path, "*/" + pattern)
     예: "file.py" → "src/file.py" ✅
4. 선행 */ 제거 후 매칭:  fnmatch(rel_path, pattern.lstrip("*/"))
```

---

## 2. 테스트 시나리오

> 아래 모든 시나리오는 `/context`와 `/auto_context` **양쪽** 명령어에 동일하게 적용됩니다.  
> 표기는 `/context`로 통일하되, `/auto_context`로 치환하여 동일하게 테스트합니다.

### 2.1 명령어 파싱 테스트 (입력 분리)

명령어에서 파일 패턴과 질문을 올바르게 분리하는지 검증합니다.

| # | 입력 | 기대: file_patterns | 기대: question | 기대 동작 |
|---|------|-------------------|---------------|----------|
| TC-01 | `/context` | — | — | 도움말 출력 (3가지 사용 예시 포함), 다음 입력 대기 |
| TC-02 | `/context src/*.py` | `['src/*.py']` | (없음) | 멀티라인 입력 모드 진입 |
| TC-03 | `/context src/*.py 이 코드 분석해줘` | `['src/*.py']` | `이 코드 분석해줘` | AI 호출 |
| TC-04 | `/context [src/*.py, docs/*.md]` | `['src/*.py', 'docs/*.md']` | (없음) | 멀티라인 입력 모드 진입 |
| TC-05 | `/context [src/*.py, docs/*.md] README 작성해줘` | `['src/*.py', 'docs/*.md']` | `README 작성해줘` | AI 호출 |
| TC-06 | `/context [src/*.py` | — | — | `❌ 닫는 대괄호 ']'가 없습니다.` 오류 출력 |

### 2.2 파일 패턴 매칭 테스트 (fnmatch 기반)

`FilePatternMatcher`가 패턴에 맞는 파일을 정확히 선별하는지 검증합니다.

> **테스트 전제 — 워크스페이스에 다음 파일이 존재한다고 가정:**
> ```
> src/
> ├── __init__.py
> ├── file_manager.py
> ├── gen_utils.py
> ├── generator.py
> ├── context_processor.py
> ├── file1.py
> ├── file2.py
> ├── deep/
> │   ├── nested.py
> │   └── gen_deep.py
> docs/
> ├── readme.md
> ├── guide.md
> logs/
> ├── log_2026-03-05.log
> ├── log_2026-03-04.log
> images/
> ├── logo.jpg
> ├── banner.png
> ├── icon.jpeg
> ├── data.csv
> ```

#### 2.2.1 기본 와일드카드 (`*`)

| # | 명령어 | 패턴 | 매칭되는 파일 | 매칭 안 되는 파일 | 비고 |
|---|--------|------|-------------|-----------------|------|
| TC-07 | `/context src/*.py` | `src/*.py` | `src/__init__.py`, `src/file_manager.py`, `src/gen_utils.py`, `src/generator.py`, `src/context_processor.py`, `src/file1.py`, `src/file2.py` | `src/deep/nested.py` (하위 폴더) | `*`는 `/`를 포함하지 않음 |
| TC-08 | `/context *.py` | `*.py` | 워크스페이스 내 모든 `.py` 파일 (파일명만 매칭) | — | 파일명 매칭 우선순위 2번 적용 |
| TC-09 | `/context docs/*.md` | `docs/*.md` | `docs/readme.md`, `docs/guide.md` | — | 상대경로 전체 매칭 |

#### 2.2.2 문자 범위 (`[seq]`)

| # | 명령어 | 패턴 | 매칭되는 파일 | 매칭 안 되는 파일 | 비고 |
|---|--------|------|-------------|-----------------|------|
| TC-10 | `/context src/file[0-9].py` | `src/file[0-9].py` | `src/file1.py`, `src/file2.py` | `src/file_manager.py` | `[0-9]`는 숫자 1글자 매칭 |
| TC-11 | `/context src/file[!0-9].py` | `src/file[!0-9].py` | — | `src/file1.py` | `[!0-9]`는 숫자 이외 1글자 |

#### 2.2.3 접두어 패턴 (`gen*`)

| # | 명령어 | 패턴 | 매칭되는 파일 | 매칭 안 되는 파일 | 비고 |
|---|--------|------|-------------|-----------------|------|
| TC-12 | `/context src/gen*.py` | `src/gen*.py` | `src/gen_utils.py`, `src/generator.py` | `src/deep/gen_deep.py` | `*`는 `/`를 포함하지 않음 |
| TC-13 | `/context gen*.py` | `gen*.py` | `src/gen_utils.py`, `src/generator.py`, `src/deep/gen_deep.py` | — | 파일명만 매칭 (우선순위 2번) |

#### 2.2.4 다중 패턴 (대괄호 구문)

| # | 명령어 | 패턴 | 매칭되는 파일 | 비고 |
|---|--------|------|-------------|------|
| TC-14 | `/context [src/*.py, docs/*.md]` | `['src/*.py', 'docs/*.md']` | `src/` 직하위 모든 `.py` 파일 + `docs/` 직하위 모든 `.md` 파일 | 두 패턴의 합집합 |
| TC-15 | `/context [*.py, *.md]` | `['*.py', '*.md']` | 워크스페이스 내 모든 `.py` + `.md` 파일 | 파일명 매칭 |
| TC-16 | `/context [src/gen*.py, docs/*.md] README 작성해줘` | `['src/gen*.py', 'docs/*.md']` | `src/gen_utils.py`, `src/generator.py`, `docs/readme.md`, `docs/guide.md` | 패턴 2개 + 질문 분리 |

#### 2.2.5 `**` 재귀 글로빙 (⚠️ 비지원 — 한계 확인)

> **현재 `fnmatch` 기반 구현에서 `**`는 `*`와 동일하게 동작합니다.**  
> 따라서 하위 디렉토리 재귀 탐색이 되지 않습니다.

| # | 명령어 | 패턴 | 기대 동작 (현재) | 이상적 기대 동작 | 결과 |
|---|--------|------|----------------|----------------|------|
| TC-17 | `/context src/**/*.py` | `src/**/*.py` | `**`는 `/`를 포함하지 않으므로 `src/deep/nested.py` **매칭 실패** | 재귀 탐색으로 하위 폴더 포함 매칭 | ⚠️ 한계 |
| TC-18 | `/context src/**/*.py 이 코드 분석해줘` | `src/**/*.py` | `src/` 직하위 `.py` 파일만 매칭 (하위 폴더 제외) | 전체 하위 `.py` 포함 | ⚠️ 한계 |
| TC-19 | `/context src/**/gen*.py 이 코드 분석해줘` | `src/**/gen*.py` | `**`가 단일 경로 구성요소로만 매칭 → `src/deep/gen_deep.py` **매칭 실패** | 재귀 탐색 후 `gen` 접두어 매칭 | ⚠️ 한계 |

#### 2.2.6 정규식 패턴 (⚠️ 비지원 — 한계 확인)

> **`fnmatch`는 정규표현식을 지원하지 않습니다.** `\d{4}`, `(jpg|png)` 등의 정규식 구문은 리터럴 문자로 처리됩니다.

| # | 명령어 | 패턴 | 기대 동작 (현재) | 결과 |
|---|--------|------|----------------|------|
| TC-20 | `/context [src/*_[0-9].py, logs/log_\d{4}-\d{2}-\d{2}\.log, images/*\.(jpg\|png\|jpeg)]` | 3개 패턴 | `src/*_[0-9].py` → ✅ fnmatch `[0-9]` 정상 동작 | 부분 성공 |
| | | | `logs/log_\d{4}-\d{2}-\d{2}\.log` → ❌ `\d{4}` 등은 정규식이므로 매칭 실패 | ⚠️ 한계 |
| | | | `images/*\.(jpg\|png\|jpeg)` → ❌ `(jpg\|png\|jpeg)` 그룹 구문 미지원 | ⚠️ 한계 |

**TC-20 대체 패턴 (fnmatch 호환):**

| 원본 패턴 (정규식) | fnmatch 대체 패턴 | 설명 |
|------|------|------|
| `logs/log_\d{4}-\d{2}-\d{2}\.log` | `logs/log_????-??-??.log` | `?`는 임의 1글자 |
| `images/*\.(jpg\|png\|jpeg)` | `images/*.jpg`, `images/*.png`, `images/*.jpeg` | 확장자별 개별 패턴 |

대체 명령어:
```
/context [src/*_[0-9].py, logs/log_????-??-??.log, images/*.jpg, images/*.png, images/*.jpeg]
```

---

## 3. 도움말 출력 테스트

TC-01에서 인수 없이 `/context`를 입력했을 때 출력되는 도움말 메시지를 검증합니다.

### 3.1 기대 출력 (3개 스크립트 공통)

```
❌ 형식: /context <파일패턴> [질문]
💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.
예: /context src/*.py
예: /context src/*.py 이 코드를 리팩토링해줘
예: /context [src/*.py, docs/*.md] README 작성해줘
```

### 3.2 `/auto_context` 도움말 기대 출력

```
❌ 형식: /auto_context <파일패턴> [질문]
💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.
예: /auto_context src/*.py
예: /auto_context src/*.py 이 코드를 리팩토링해줘
예: /auto_context [src/*.py, docs/*.md] README 작성해줘
```

---

## 4. 스크립트별 동작 일관성 테스트

3개 스크립트 모두에서 동일한 동작이 보장되는지 검증합니다.

| TC | 테스트 항목 | gen-ai | claude | gemini |
|----|-----------|:------:|:------:|:------:|
| TC-21 | `/context` 도움말 메시지 5줄 출력 | ✅ | ✅ | ✅ |
| TC-22 | 단일 패턴 + 질문 분리 | ✅ | ✅ | ✅ |
| TC-23 | `[p1, p2]` 대괄호 다중 패턴 파싱 | ✅ | ✅ | ✅ (v1.0.068 적용) |
| TC-24 | `]` 누락 에러 메시지 | ✅ | ✅ | ✅ (v1.0.068 적용) |
| TC-25 | 질문 생략 시 멀티라인 진입 | ✅ | ✅ | ✅ |
| TC-26 | 변수명 `file_patterns` 사용 | ✅ | ✅ | ✅ (v1.0.068 적용) |

---

## 5. 한계 사항 및 향후 개선

### 5.1 현재 한계

| # | 한계 | 원인 | 영향 |
|---|------|------|------|
| 1 | `**` 재귀 글로빙 미지원 | `fnmatch`는 `**`를 `*`와 동일하게 처리 | 하위 폴더 재귀 탐색 불가 |
| 2 | 정규표현식 미지원 | `fnmatch`는 정규식 구문 미인식 | `\d`, `(a|b)` 등 사용 불가 |
| 3 | 부정 패턴 미지원 | `!pattern` 제외 로직 없음 | 특정 파일 제외 불가 |

### 5.2 향후 개선 제안

| # | 개선안 | 방법 | 효과 |
|---|--------|------|------|
| 1 | `**` 재귀 글로빙 지원 | `pathlib.Path.glob()` 또는 `glob.glob(recursive=True)` 도입 | `src/**/*.py` 하위 폴더 포함 탐색 |
| 2 | 정규식 패턴 지원 | `re.match()` 옵션 분기 추가 | 복잡한 파일명 패턴 사용 가능 |
| 3 | 부정 패턴 지원 | `!` 접두어 패턴 감지 후 결과에서 제외 | `[*.py, !test_*.py]` 등 |

---

## 6. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.068 | 2026-03-05 | - | 최초 작성: `/context` · `/auto_context` 파일 패턴 매칭 테스트 시나리오 |
