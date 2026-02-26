# FSD v1.0.049 - `/auto_context` 파일 단위 자동 처리 명령어

## 문서 정보
- **버전**: v1.0.049
- **작성일**: 2026-02-26
- **상태**: Draft
- **선행 문서**: FSD v1.0.041 (Context Command Multiline Support)
- **대상 파일**: 
  - `gen-ai-chat-code01.py`
  - `claude-ai-chat-code01.py`
  - `gemini-ai-chat-code01.py`
  - `src/context_processor.py` (신규)
  - `src/__init__.py`
  - `src/command_registry.py`

---

## 1. 개요

### 1.1 목적
새로운 `/auto_context` 명령어를 추가하여, 매칭된 파일을 **1개씩 순차적으로 읽고, AI에 전달하고, 응답에 포함된 결과 파일을 자동 저장**하는 배치 처리 기능을 구현합니다.

> **기존 `/context` 명령어는 변경 없이 유지**됩니다.

### 1.2 배경
기존 `/context`는 매칭된 모든 파일을 한꺼번에 컨텍스트로 묶어 AI에 전송합니다.
이 방식의 한계:
- 파일이 많으면 토큰 한도를 초과
- 개별 파일에 대한 작업(번역, 요약, 소스 생성 등)을 반복 수행할 수 없음
- AI 응답에 포함된 결과 파일을 수동으로 `/save`해야 함

### 1.3 범위
- `/auto_context` 신규 명령어 추가 (기존 `/context`와 별도)
- 파일 패턴 매칭 → 파일 단위 자동 반복 처리
- AI 응답의 ` ```filename: ` 블록 자동 감지 및 파일 저장
- 단일/다중 파일 패턴, 대괄호 패턴 모두 지원
- 1개 요구 파일 당 1개 이상의 결과 파일 생성 지원
- 3개 메인 파일 모두 동일 구현

---

## 2. 요구사항

### 2.1 기능 요구사항

#### FR-1: 파일 단위 자동 반복 처리

`/auto_context` + 파일 패턴 + 작업 지시문을 입력하면, 매칭된 파일 목록을 구한 뒤 **1개씩 순차적으로** 다음 흐름을 자동 수행합니다:

```
1. 파일 한 개 읽기
2. (명령어 + 파일 내용) AI에 전송
3. AI 응답에서 ```filename: 블록 추출 → 자동 저장
4. 다음 파일로 반복
5. 모든 파일 완료 후 종료
```

**사용 예시 (번역)**:
```
> /auto_context [original/*.md]
📝 멀티라인 모드 (종료: /end)
... original 폴더에 있는 md 파일을 1개씩 한글로 번역해서 hangle 폴더에 동일한 파일명으로 저장해줘
... /end

📂 매칭된 파일 3개:
  1. original/PART 01_01 주제·제목 파악하기_문제지.md
  2. original/PART 01_02 요지·주장 파악하기_문제지.md
  3. original/PART 01_03 목적 파악하기_문제지.md

▶ 자동 처리를 시작하시겠습니까? (Y/n): y

━━━ [1/3] PART 01_01 주제·제목 파악하기_문제지.md ━━━
📖 파일 읽는 중...
🤖 AI 처리 중...
✅ 파일 저장됨: hangle/PART 01_01 주제·제목 파악하기_문제지.md

━━━ [2/3] PART 01_02 요지·주장 파악하기_문제지.md ━━━
📖 파일 읽는 중...
🤖 AI 처리 중...
✅ 파일 저장됨: hangle/PART 01_02 요지·주장 파악하기_문제지.md

━━━ [3/3] PART 01_03 목적 파악하기_문제지.md ━━━
📖 파일 읽는 중...
🤖 AI 처리 중...
✅ 파일 저장됨: hangle/PART 01_03 목적 파악하기_문제지.md

✅ 자동 처리 완료: 3개 파일 처리, 3개 파일 저장
```

#### FR-2: 다중 결과 파일 생성 지원

AI 응답에 ` ```filename: ` 블록이 **여러 개** 포함될 수 있으며, 모두 자동 저장합니다.

**사용 예시 (소스 코드 생성)**:
```
> /auto_context [specs/*.md]
📝 멀티라인 모드 (종료: /end)
... specs 폴더의 md 파일을 읽고 Java 서비스와 인터페이스 코드를 작성해서 src 폴더에 저장해줘
... /end

━━━ [1/2] specs/file1.md ━━━
📖 파일 읽는 중...
🤖 AI 처리 중...
✅ 파일 저장됨: src/file1_service.java
✅ 파일 저장됨: src/file1_interface.java

━━━ [2/2] specs/file2.md ━━━
📖 파일 읽는 중...
🤖 AI 처리 중...
✅ 파일 저장됨: src/file2_service.java
✅ 파일 저장됨: src/file2_interface.java

✅ 자동 처리 완료: 2개 파일 처리, 4개 파일 저장
```

#### FR-3: 파일 패턴 입력 형식

| 형식 | 예시 | 설명 |
|------|------|------|
| 단일 패턴 | `/auto_context src/*.py` | 한 개의 패턴 |
| 대괄호 단일 | `/auto_context [src/*.py]` | 대괄호로 감싸도 동일 |
| 대괄호 다중 | `/auto_context [original/*.md, src/*.py]` | 콤마 구분 다중 패턴 |

> **참고**: 다중 패턴의 경우 모든 패턴에서 매칭된 파일들을 병합(중복 제거)하여 순차 처리합니다.

#### FR-4: 명령어 사용 패턴

| 사용법 | 동작 |
|--------|------|
| `/auto_context src/*.py 간단한 질문` | 한 줄 질문 + 파일 단위 자동 반복 처리 |
| `/auto_context src/*.py` → 멀티라인 | 멀티라인 질문 + 파일 단위 자동 반복 처리 |
| `/auto_context [pattern]` → 멀티라인 | 대괄호 패턴 + 멀티라인 + 자동 반복 처리 |
| `/auto_context [p1, p2]` → 멀티라인 | 다중 패턴 자동 반복 처리 |

> **기존 `/context` 명령어는 변경 없이 유지**되며, `/auto_context`는 항상 파일 단위 자동 반복 처리를 수행합니다.

#### FR-5: 처리 상태 표시 및 에러 핸들링

| 상황 | 동작 |
|------|------|
| 파일을 찾을 수 없음 | `❌ 패턴에 해당하는 파일이 없습니다.` 출력 후 종료 |
| AI 응답에 `filename:` 블록 없음 | `⚠️ 저장할 파일 블록이 없습니다.` 출력 후 다음 파일로 계속 |
| AI API 호출 실패 | `❌ AI 처리 실패: {오류 메시지}` 출력 → 사용자에게 계속/중단 확인 |
| 파일 저장 실패 | `❌ 파일 저장 실패: {경로}` 출력 후 다음 파일로 계속 |
| 사용자 인터럽트 (Ctrl+C) | 현재 처리 중인 파일까지 완료 후 중단, 진행 결과 요약 출력 |

---

## 3. 설계

### 3.1 작업 흐름 다이어그램

```
사용자 입력: /auto_context [original/*.md]
       │
       ▼
① 파일 패턴 파싱 (단일 패턴 or [대괄호] 다중 패턴)
       │
       ▼
② 질문이 없으면 멀티라인 입력 수집 → /end 종료
       │
       ▼  
③ 파일 매칭 (FilePatternMatcher)
       │
       ▼
④ 매칭 파일 목록 표시 + 확인 질의
       │
       ▼
⑤ for each file in matched_files:
       │
       ├─→ ⑤-1. 파일 읽기
       ├─→ ⑤-2. 프롬프트 조합 (질문 + 파일 내용)
       ├─→ ⑤-3. AI 전송 (include_context=False)
       ├─→ ⑤-4. 응답에서 ```filename: 블록 추출 → 자동 저장 (자동 덮어쓰기)
       └─→ ⑤-5. 저장 결과 출력
       
       ▼
⑥ 전체 요약 출력
```

### 3.2 신규 모듈: `src/context_processor.py`

파일 단위 자동 반복 처리 로직을 별도 `ContextProcessor` 클래스로 분리합니다.

#### 클래스 구조

| 메서드 | 역할 |
|--------|------|
| `__init__(assistant, file_manager, streaming)` | AI 어시스턴트, FileManager, 스트리밍 모드 초기화 |
| `process_files(matched_files, question)` → `(int, int)` | 매칭 파일 순차 처리, `(처리 수, 저장 수)` 반환 |
| `_build_prompt(question, rel_path, content)` → `str` | 질문 + 파일 내용 프롬프트 조합 |
| `_auto_save_files(response)` → `List[str]` | AI 응답에서 `filename:` 블록 추출 후 자동 저장 |

#### 핵심 동작 원리

- `process_files`: 매칭 파일을 for 루프로 순회. 각 파일마다 읽기 → 프롬프트 조합 → AI 전송 → 자동 저장 수행
- `_auto_save_files`: 기존 `ResponseParser.parse_and_save()`와 동일한 파싱 로직이나 **확인 프롬프트 없이 자동 덮어쓰기** + **상위 디렉토리 자동 생성**
- 에러 발생 시 계속/중단 사용자 확인, Ctrl+C 시 진행 요약 출력

### 3.3 메인 파일 수정

3개 메인 파일 모두 동일한 로직으로 `/auto_context` 명령어 핸들러를 **기존 `/context` 핸들러 뒤에 추가**합니다.

#### 핸들러 구현 개요

1. **패턴 파싱**: `[대괄호]` 형식이면 콤마 분리, 아니면 단일 패턴
2. **질문 수집**: 인라인 질문이 없으면 `get_multiline_legacy()` 호출
3. **파일 매칭**: `FilePatternMatcher`로 매칭 파일 목록 가져오기
4. **확인 질의**: 매칭 목록 표시 후 사용자 확인
5. **자동 처리**: `ContextProcessor.process_files()` 호출

#### 파일별 변수명 참고

| 파일 | 스트리밍 변수 | 입력 핸들러 변수 |
|------|-------------|----------------|
| `gen-ai-chat-code01.py` | `streaming_mode` | `input_handler` |
| `claude-ai-chat-code01.py` | `streaming_mode` | `input_handler` |
| `gemini-ai-chat-code01.py` | `streaming` | `cli_handler` |

### 3.4 프롬프트 전달 형식

파일 단위 자동 처리 시 AI에 전달하는 프롬프트:

```
{사용자 입력 질문}

--- 파일: original/PART 01_01 주제·제목 파악하기_문제지.md ---
{파일 내용}
--- 파일 끝 ---
```

> **중요**: 자동 처리 모드에서는 `include_context=False`로 호출합니다.
> 파일 내용을 프롬프트에 직접 삽입하므로 별도의 컨텍스트 빌드가 불필요합니다.

### 3.5 AI 응답 파일 블록 형식

AI가 결과 파일을 생성할 때 사용하는 형식 (기존 `ResponseParser`와 동일):

````
```filename: hangle/PART 01_01 주제·제목 파악하기_문제지.md
번역된 내용...
```
````

다중 파일 생성 예:
````
```filename: src/file1_service.java
소스 내용
```

```filename: src/file1_interface.java
소스 내용
```
````

---

## 4. 사용 케이스

### 케이스 1: 파일 번역
```
> /auto_context [original/*.md]
📝 멀티라인 모드 (종료: /end)
... original 폴더에 있는 md 파일을 1개씩 한글로 번역해서 hangle 폴더에 동일한 파일명으로 저장해줘
... /end
```

### 케이스 2: 소스 코드 생성
```
> /auto_context [specs/*.md]
📝 멀티라인 모드 (종료: /end)
... 각 spec 파일을 읽고 Java 서비스 코드와 인터페이스를 작성해서 src 폴더에 저장해줘
... 파일명 규칙: {원본파일명}_service.java, {원본파일명}_interface.java
... /end
```

### 케이스 3: 요약문 작성
```
> /auto_context [docs/*.md]
📝 멀티라인 모드 (종료: /end)
... 각 문서를 읽고 200자 이내 요약문을 summary 폴더에 저장해줘
... /end
```

### 케이스 4: 다중 패턴 분석
```
> /auto_context [original/*.md, src/*.py]
📝 멀티라인 모드 (종료: /end)
... 각 파일을 분석하고 리뷰 결과를 reviews 폴더에 저장해줘
... /end
```

---

## 5. 파일 변경 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/context_processor.py` | **신규** | `ContextProcessor` 클래스 — 파일 단위 자동 반복 처리 + 자동 저장 |
| `src/__init__.py` | **수정** | `ContextProcessor` export 추가 |
| `src/command_registry.py` | **수정** | `/auto_context` 명령어 등록 |
| `gen-ai-chat-code01.py` | **수정** | `/auto_context` 핸들러 추가 + 도움말 메뉴 추가 |
| `claude-ai-chat-code01.py` | **수정** | 동일 적용 |
| `gemini-ai-chat-code01.py` | **수정** | 동일 적용 |

---

## 6. 테스트 시나리오

### 6.1 기본 자동 처리 테스트

| # | 시나리오 | 기대 결과 |
|---|---------|----------|
| 1 | `/auto_context [src/*.py]` + 멀티라인 질문 | 매칭 파일 목록 표시 → 확인 → 파일 단위 순차 처리 |
| 2 | 자동 처리 중 AI 응답에 `filename:` 블록 포함 | 파일 자동 저장 |
| 3 | AI 응답에 `filename:` 블록 없음 | `⚠️` 경고 출력 후 다음 파일 계속 |
| 4 | AI 응답에 다중 `filename:` 블록 포함 | 모든 파일 자동 저장 |

### 6.2 패턴 형식 테스트

| # | 시나리오 | 기대 결과 |
|---|---------|----------|
| 1 | `/auto_context [src/*.py, docs/*.md]` + 멀티라인 | 두 패턴 매칭 파일 병합 표시 |
| 2 | `/auto_context src/*.py` (대괄호 없이) | 단일 패턴 → 정상 동작 |
| 3 | `/auto_context src/*.py 한줄 질문` | 한줄 질문 → 자동 반복 처리 |
| 4 | 매칭 파일 없음 | `❌` 오류 메시지 |

### 6.3 에러 핸들링 테스트

| # | 시나리오 | 기대 결과 |
|---|---------|----------|
| 1 | 자동 처리 중 Ctrl+C | 현재까지 진행 결과 요약 출력 |
| 2 | 확인 질의에서 `n` 입력 | 처리 취소 |
| 3 | AI API 호출 실패 | 계속/중단 확인 |
| 4 | 대상 디렉토리 미존재 | 자동 생성 후 저장 |

### 6.4 3개 메인 파일 동일 동작 테스트

모든 시나리오를 다음 3개 파일에서 동일하게 검증:
- `gen-ai-chat-code01.py`
- `claude-ai-chat-code01.py`
- `gemini-ai-chat-code01.py`

---

## 7. 도움말 업데이트

3개 메인 파일의 `print_menu()` 함수에 다음 항목 추가:

```
/auto_context <pattern> - 파일 단위 자동 반복 처리 (예: /auto_context [original/*.md])
```

---

## 8. 승인

- [ ] 개발자 검토
- [ ] 테스트 완료
- [ ] 문서 업데이트 완료
