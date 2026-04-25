# FSD v1.0.050 - 멀티라인 입력 텍스트 편집 기능 개선

## 문서 정보
- **버전**: v1.0.050
- **작성일**: 2026-02-26
- **상태**: Draft
- **선행 문서**: FSD v1.0.015 (Multiline Command), FSD v1.0.041 (Context Multiline Support)
- **대상 파일**:
  - `src/cli_input.py`
  - `gen-ai-chat-code01.py`
  - `claude-ai-chat-code01.py`
  - `gemini-ai-chat-code01.py`

---

## 1. 개요

### 1.1 목적
멀티라인 입력 모드(`/multiline`, `/context`, `/auto_context`)에서 **이전에 입력한 텍스트의 삭제 및 수정**이 가능하도록 기능을 개선합니다.

### 1.2 배경
현재 멀티라인 입력은 `input("... ")`을 한 줄씩 반복 호출하는 방식입니다.

**현재 한계:**
- 이미 입력(Enter)한 줄로 되돌아가 수정할 수 없음
- 붙여넣기된 텍스트에서 오타 발생 시 처음부터 다시 입력해야 함
- 여러 줄의 텍스트를 한번에 편집하는 것이 불가능
- 커서 이동이 현재 줄 내에서만 가능

### 1.3 범위
- `prompt_toolkit`의 멀티라인 `Buffer`를 활용한 새로운 `get_multiline()` 메서드 구현
- `↑↓←→` 키로 전체 텍스트 탐색 및 수정
- 붙여넣기 후 자유로운 편집
- `Meta+Enter` (또는 `Esc → Enter`)로 입력 확정, `/end` 입력으로도 종료
- `prompt_toolkit` 미설치 시 기존 `get_multiline_legacy()` 폴백
- 3개 메인 파일 + `CLIInputHandler` 모두 동일 적용

---

## 2. 요구사항

### 2.1 기능 요구사항

#### FR-1: 멀티라인 텍스트 편집

멀티라인 모드 진입 시 **전체 텍스트를 하나의 편집 영역**으로 표시하여 자유롭게 수정 가능:
- `↑↓` 키: 이전/다음 줄로 커서 이동
- `←→` 키: 줄 내 커서 이동
- `Home/End`: 줄의 처음/끝으로 이동
- `Backspace/Delete`: 글자 삭제
- 텍스트 붙여넣기(Ctrl+V) 후 편집 가능

**사용 예시:**
```
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, Esc로 취소)
... original 폴더에 있는 md 파일을 1개씩
... 한글로 번역해서 hangle 폴더에
... 동일한 파일명으로 저장해줘    ← ↑↓ 키로 이전 줄 수정 가능
```

#### FR-2: 입력 확정/취소 키바인딩

| 키 | 동작 |
|----|------|
| `Enter` | 새 줄 추가 (일반 줄바꿈) |
| `Meta+Enter` (Alt+Enter) | 입력 확정 및 전송 |
| `/end` + `Enter` | 입력 확정 및 전송 (기존 호환) |
| `Esc` | 입력 취소 |
| `Ctrl+C` | 입력 취소 |

> **핵심**: `Enter`는 줄바꿈, `Meta+Enter`는 전송. 기존 `/end` 종료도 유지.

#### FR-3: 적용 대상 명령어

| 명령어 | 호출 위치 | 변경 |
|--------|----------|------|
| `/multiline` | 메인 파일 핸들러 | `get_multiline()` 호출로 변경 |
| `/context` (질문 없는 경우) | 메인 파일 핸들러 | `get_multiline()` 호출로 변경 |
| `/auto_context` (질문 없는 경우) | 메인 파일 핸들러 | `get_multiline()` 호출로 변경 |

#### FR-4: prompt_toolkit 미설치 시 폴백

`prompt_toolkit`이 설치되지 않은 환경에서는 기존 `get_multiline_legacy()` 방식(라인 단위 `input()`)으로 자동 폴백합니다.

#### FR-5: 시각적 가이드

멀티라인 모드 진입 시 안내 메시지:
```
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
```

편집 영역 좌측에 줄 번호 또는 `...` 프롬프트 표시:
```
... 첫 번째 줄
... 두 번째 줄
... 세 번째 줄
```

---

## 3. 설계

### 3.1 `CLIInputHandler.get_multiline()` 신규 메서드

`prompt_toolkit`의 `Application` + 멀티라인 `Buffer`를 사용하여 전체 텍스트 편집 가능한 입력기를 구현합니다.

#### 핵심 구현 방식

| 요소 | 구현 |
|------|------|
| Buffer | `multiline=True`로 설정하여 Enter가 줄바꿈으로 동작 |
| 입력 확정 | `Meta+Enter` 키바인딩으로 `app.exit()` |
| `/end` 감지 | 텍스트 변경 시 마지막 줄이 `/end`이면 해당 줄 제거 후 확정 |
| 취소 | `Esc` 또는 `Ctrl+C`로 빈 문자열 반환 |
| 프롬프트 | `BeforeInput("... ")` 프로세서로 각 줄에 `...` 표시 |
| 폴백 | `prompt_toolkit` 미설치 시 `get_multiline_legacy()` 호출 |

#### 키바인딩 설계

```
Meta+Enter  → 입력 확정 (app.exit)
Esc         → 입력 취소 (빈 문자열 반환)
Ctrl+C      → 입력 취소
Enter       → 줄바꿈 (Buffer 기본 동작)
↑↓←→        → 커서 이동 (Buffer 기본 동작)
```

### 3.2 메인 파일 수정

#### 변경 항목 (동일 적용)

1. `/multiline` 핸들러: 인라인 `input()` 루프 → `input_handler.get_multiline()` 호출
2. `/context` 핸들러: `get_multiline_legacy()` → `get_multiline()` 호출
3. `/auto_context` 핸들러: `get_multiline_legacy()` → `get_multiline()` 호출

#### 파일별 변수명

| 파일 | 핸들러 변수 |
|------|------------|
| `gen-ai-chat-code01.py` | `input_handler` |
| `claude-ai-chat-code01.py` | `input_handler` |
| `gemini-ai-chat-code01.py` | `cli_handler` |

---

## 4. 파일 변경 목록

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `src/cli_input.py` | **수정** | `get_multiline()` 신규 메서드 추가 |
| `gen-ai-chat-code01.py` | **수정** | `/multiline`, `/context`, `/auto_context` 핸들러에서 `get_multiline()` 호출 |
| `claude-ai-chat-code01.py` | **수정** | 동일 적용 |
| `gemini-ai-chat-code01.py` | **수정** | 동일 적용 |

---

## 5. 사용 시나리오

### 시나리오 1: `/multiline` 일반 사용
```
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... 이 코드를 리팩토링해줘
... 특히 에러 핸들링 부분을
... 개선해줘                     ← ↑ 키로 이전 줄 수정 가능
[Meta+Enter 입력으로 전송]
```

### 시나리오 2: `/context` 멀티라인
```
> /context src/*.py
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... 이 코드를 분석하고
... 개선점을 알려줘
[Meta+Enter 입력으로 전송]
```

### 시나리오 3: 붙여넣기 후 편집
```
> /auto_context [original/*.md]
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... [텍스트 붙여넣기 후 ↑↓←→ 키로 자유롭게 수정]
[Meta+Enter 입력으로 전송]
```

### 시나리오 4: 기존 `/end` 방식으로도 종료
```
> /multiline
📝 멀티라인 모드 (Meta+Enter로 전송, /end로 종료, Esc 취소)
... 질문 내용
... /end                         ← 기존 방식 호환
[자동으로 /end 제거 후 전송]
```

---

## 6. 테스트 시나리오

### 6.1 기능 테스트

| # | 시나리오 | 기대 결과 |
|---|---------|----------|
| 1 | `/multiline` → 여러 줄 입력 → `Meta+Enter` | 입력 확정, AI에 전송 |
| 2 | `/multiline` → 여러 줄 입력 → `/end` 입력 | `/end` 줄 제거 후 확정 |
| 3 | `/multiline` → `Esc` | 입력 취소, 빈 문자열 반환 |
| 4 | `/multiline` → `Ctrl+C` | 입력 취소 |
| 5 | `/context src/*.py` → 멀티라인 → 수정 후 전송 | 수정된 텍스트로 전송 |
| 6 | `/auto_context [*.md]` → 멀티라인 → 전송 | 정상 처리 |

### 6.2 편집 기능 테스트

| # | 시나리오 | 기대 결과 |
|---|---------|----------|
| 1 | 3줄 입력 후 `↑` 키로 첫 줄 이동 → 수정 | 수정된 내용 반영 |
| 2 | 텍스트 붙여넣기 후 일부 삭제 | 삭제 반영 |
| 3 | `Backspace`로 줄 간 합치기 | 정상 동작 |
| 4 | `Delete` 키 사용 | 정상 동작 |

### 6.3 3개 메인 파일 동일 동작 검증

모든 시나리오를 3개 파일에서 동일하게 수동 테스트:
- `gen-ai-chat-code01.py`
- `claude-ai-chat-code01.py`
- `gemini-ai-chat-code01.py`

### 6.4 폴백 테스트

- `prompt_toolkit` 미설치 환경에서 `get_multiline_legacy()` 정상 동작 확인

---

## 7. 승인

- [ ] 개발자 검토
- [ ] 테스트 완료
- [ ] 문서 업데이트 완료
