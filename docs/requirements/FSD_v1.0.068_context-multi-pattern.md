# FSD v1.0.068 - `/context` 명령어 다중 파일 패턴 지원 통일

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.068 |
| 제목 | `/context` 명령어 다중 파일 패턴 지원 통일 |
| 작성일 | 2026-03-05 |
| 상태 | 설계 완료 |
| 관련 FSD | [FSD v1.0.041](./FSD_v1.0.041_context-multiline-support.md) — Context 멀티라인 지원 |
| 대상 소스 | `gemini-ai-chat-code.py` |

---

## 1. 개요 (Overview)

현재 `/auto_context` 명령어는 `[pattern1, pattern2]` 대괄호 구문을 통한 **다중 파일 패턴** 입력을 3개 스크립트(`gen-ai`, `claude`, `gemini`) 모두에서 공통으로 지원하고 있습니다.

그러나 `/context` 명령어는 스크립트별로 파일 패턴 파싱 로직이 **불일치**하는 상태입니다:

| 스크립트 | `/context` 패턴 파싱 | `[p1, p2]` 지원 | 멀티라인 폴백 |
|----------|----------------------|:---------------:|:-------------:|
| `gen-ai-chat-code.py` | ✅ `[...]` 대괄호 분석 + 단일 패턴 | ✅ | ✅ |
| `claude-ai-chat-code.py` | ✅ `[...]` 대괄호 분석 + 단일 패턴 | ✅ | ✅ |
| `gemini-ai-chat-code.py` | ❌ `split(',')` 단순 분리 | ❌ 부분적 | ✅ |

`gemini-ai-chat-code.py`의 `/context` 명령어가 `/auto_context`와 동일한 다중 패턴 파싱 로직을 사용하도록 수정하여, 3개 스크립트 간 사용자 경험을 통일합니다.

### 1.1 개선 목표

| # | 목표 | 설명 |
|---|------|------|
| 1 | 패턴 파싱 통일 | `/context`가 `/auto_context`와 동일한 `[pattern1, pattern2]` 구문을 지원 |
| 2 | 스크립트 간 일관성 | 3개 스크립트 모두 동일한 `/context` 패턴 파싱 로직 적용 |
| 3 | 도움말 표준화 | 사용법 안내 메시지에 다중 패턴 예시를 명확히 포함 |
| 4 | 고유 기능 유지 | 패턴 파싱 로직 통일 시 각 명령어의 고유 동작을 변경하지 않음 |

### 1.2 `/context` vs `/auto_context` 고유 기능 비교

본 FSD에서 통일하는 것은 **`<파일패턴>` 파싱 로직**에 한정합니다. 두 명령어는 패턴 파싱 이후의 **실행 방식이 근본적으로 다르며**, 이 고유 기능은 반드시 유지되어야 합니다.

| 구분 | `/context` | `/auto_context` |
|------|-----------|----------------|
| **핵심 기능** | 파일 컨텍스트 포함 질문 | 파일 단위 자동 분할 반복 질의 |
| **AI 호출 방식** | 매칭된 전체 파일을 컨텍스트로 **합쳐서 1회** AI 호출 | 매칭된 파일을 **1개씩 순차적으로 N회** AI 호출 |
| **AI 호출 코드** | `assistant.chat(include_context=True, file_patterns=...)` | `ContextProcessor.process_files(matched_files, question)` |
| **파일 매칭 주체** | `assistant.chat()` 내부에서 자동 처리 | 명령어 핸들러에서 `FilePatternMatcher`로 직접 매칭 |
| **사용자 확인** | 없음 (즉시 실행) | `▶ 자동 처리를 시작하시겠습니까? (Y/n)` 확인 후 실행 |
| **매칭 파일 목록** | 표시하지 않음 | `📂 매칭된 파일 N개:` 목록 표시 |
| **응답 파일 저장** | ❌ 수동 (`/save` 필요) | ✅ `_auto_save_files()` 자동 저장 |
| **진행률 표시** | 없음 | `━━━ [1/5] src/file.py ━━━` 표시 |
| **에러 시 계속** | 없음 | `▶ 다음 파일로 계속하시겠습니까? (Y/n)` |
| **중단 처리** | 없음 | `Ctrl+C` 로 중단 시 처리 현황 요약 |

**흐름 비교:**

```
/context src/*.py 코드 분석해줘
  ├── 패턴 파싱: ['src/*.py']
  └── assistant.chat(question, include_context=True, file_patterns=['src/*.py'])
       └── 내부에서 매칭 파일 전체를 시스템 프롬프트에 합산 → 1회 AI 호출 → 응답 반환

/auto_context src/*.py 코드 분석해줘
  ├── 패턴 파싱: ['src/*.py']                              ← 동일한 파싱 로직
  ├── FilePatternMatcher로 매칭: [file1.py, file2.py, ...]
  ├── 매칭 파일 목록 표시 + 사용자 확인 (Y/n)
  └── ContextProcessor.process_files()
       ├── [1/N] file1.py 읽기 → AI 호출 → 자동 저장
       ├── [2/N] file2.py 읽기 → AI 호출 → 자동 저장
       └── ...완료 요약 출력
```

> **⚠️ 주의사항:** 본 FSD의 패턴 파싱 통일은 위 흐름도에서 **`패턴 파싱`** 단계만 수정합니다. 그 이후의 **실행 경로는 각 명령어 고유 로직을 그대로 유지**합니다.

---

## 2. 현재 상태 분석 (AS-IS)

### 2.1 GenAI / Claude (정상 — 변경 불필요)

`gen-ai-chat-code.py`와 `claude-ai-chat-code.py`는 이미 `/auto_context`와 동일한 패턴 파싱 로직을 사용합니다:

```python
elif command == '/context':
    if not args:
        print("❌ 형식: /context <파일패턴> [질문]")
        print("💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.")
        print("예: /context src/*.py")
        print("예: /context src/*.py 이 코드를 리팩토링해줘")
        print("예: /context [src/*.py, docs/*.md] README 작성해줘")
        continue

    file_patterns = []
    question = ""

    # [pattern1, pattern2] 형식 확인
    if args.startswith('['):
        try:
            end_idx = args.index(']')
            patterns_str = args[1:end_idx]
            file_patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]
            question = args[end_idx+1:].strip()
        except ValueError:
            print("❌ 닫는 대괄호 ']'가 없습니다.")
            continue
    else:
        # 기존 단일 패턴 지원
        parts = args.split(maxsplit=1)
        file_patterns = [parts[0]]
        question = parts[1] if len(parts) >= 2 else ""

    # 질문이 없는 경우 멀티라인 입력
    if not question:
        question = input_handler.get_multiline()
        if not question.strip():
            print("❌ 질문을 입력하세요.")
            continue

    last_response = assistant.chat(
        question,
        streaming=streaming_mode,
        include_context=True,
        file_patterns=file_patterns
    )
```

### 2.2 Gemini (수정 대상)

`gemini-ai-chat-code.py`의 `/context` 명령어는 구식의 단순 분리 방식을 사용하고 있어, 대괄호 구문이 정상 동작하지 않습니다:

```python
elif command == '/context':
    if not args:
        print("❌ 사용법: /context <파일패턴> [질문]")
        print("💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.")
        continue
    
    context_parts = args.split(maxsplit=1)
    patterns = context_parts[0].split(',')
    
    # 질문이 포함된 경우 (한 줄 입력)
    if len(context_parts) >= 2:
        question = context_parts[1]
    else:
        # 질문이 없는 경우 (멀티라인 입력)
        question = cli_handler.get_multiline()
        if not question.strip():
            print("❌ 질문을 입력하세요.")
            continue
    
    last_response = assistant.chat(
        question, streaming=streaming,
        include_context=True, file_patterns=patterns
    )
```

**문제점:**

| # | 입력 예시 | 기대 동작 | 현재 동작 |
|---|----------|----------|----------|
| 1 | `/context src/*.py 코드 분석해줘` | 패턴: `src/*.py`, 질문: `코드 분석해줘` | ✅ 정상 |
| 2 | `/context [src/*.py, docs/*.md] README 작성해줘` | 패턴: `['src/*.py', 'docs/*.md']`, 질문: `README 작성해줘` | ❌ 패턴: `['[src/*.py']`, 질문이 잘못 분리됨 |
| 3 | `/context src/*.py` | 패턴: `src/*.py`, 멀티라인 입력 진입 | ✅ 정상 |

---

## 3. 설계 (Design)

### 3.1 수정 대상: `gemini-ai-chat-code.py` — `/context` 핸들러

Gemini 스크립트의 `/context` 명령어 핸들러를 GenAI/Claude와 동일한 패턴 파싱 로직으로 교체합니다.

#### 수정 전 (`gemini-ai-chat-code.py` L260~L282)

```python
elif command == '/context':
    if not args:
        print("❌ 사용법: /context <파일패턴> [질문]")
        print("💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.")
        continue
    
    context_parts = args.split(maxsplit=1)
    patterns = context_parts[0].split(',')
    
    if len(context_parts) >= 2:
        question = context_parts[1]
    else:
        question = cli_handler.get_multiline()
        if not question.strip():
            print("❌ 질문을 입력하세요.")
            continue
    
    last_response = assistant.chat(
        question, streaming=streaming,
        include_context=True, file_patterns=patterns
    )
```

#### 수정 후

```python
elif command == '/context':
    if not args:
        print("❌ 형식: /context <파일패턴> [질문]")
        print("💡 질문을 생략하면 멀티라인 입력 모드로 전환됩니다.")
        print("예: /context src/*.py")
        print("예: /context src/*.py 이 코드를 리팩토링해줘")
        print("예: /context [src/*.py, docs/*.md] README 작성해줘")
        continue

    file_patterns = []
    question = ""

    # [pattern1, pattern2] 형식 확인
    if args.startswith('['):
        try:
            end_idx = args.index(']')
            patterns_str = args[1:end_idx]
            file_patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]
            question = args[end_idx+1:].strip()
        except ValueError:
            print("❌ 닫는 대괄호 ']'가 없습니다.")
            continue
    else:
        # 기존 단일 패턴 지원
        parts = args.split(maxsplit=1)
        file_patterns = [parts[0]]
        question = parts[1] if len(parts) >= 2 else ""

    # 질문이 없는 경우 멀티라인 입력
    if not question:
        question = cli_handler.get_multiline()
        if not question.strip():
            print("❌ 질문을 입력하세요.")
            continue

    last_response = assistant.chat(
        question, streaming=streaming,
        include_context=True, file_patterns=file_patterns
    )
```

### 3.2 변경 사항 요약

| 변경 항목 | 수정 전 (Gemini) | 수정 후 |
|-----------|-----------------|---------|
| 도움말 메시지 | 2줄 (예시 없음) | 5줄 (3가지 사용 예시 포함) |
| `[p1, p2]` 대괄호 파싱 | ❌ 미지원 | ✅ `args.startswith('[')` 분기 |
| 단일 패턴 분리 | `split(',')` | `split(maxsplit=1)` → 첫 토큰이 패턴, 나머지가 질문 |
| 질문 분리 로직 | `split(maxsplit=1)` 단순 분리 | 패턴 유형에 따른 정확한 분리 |
| 에러 처리 | 없음 | `]` 누락 시 오류 메시지 출력 |
| 변수명 | `patterns` | `file_patterns` (다른 스크립트와 통일) |

### 3.3 입력 형식 사양 (통일된 파싱 규칙)

```
/context <파일패턴> [질문]

형식 1: 단일 패턴
  /context src/*.py                          → 패턴: ['src/*.py'], 멀티라인 입력 진입
  /context src/*.py 이 코드를 분석해줘       → 패턴: ['src/*.py'], 질문: '이 코드를 분석해줘'

형식 2: 다중 패턴 (대괄호)
  /context [src/*.py, docs/*.md]             → 패턴: ['src/*.py', 'docs/*.md'], 멀티라인 입력 진입
  /context [src/*.py, docs/*.md] README 작성  → 패턴: ['src/*.py', 'docs/*.md'], 질문: 'README 작성'
```

**파싱 흐름:**

```
args 입력
 ├── args.startswith('[')  →  대괄호 모드
 │    ├── ']' 찾기 성공  →  내부를 ','로 분리 → 다중 패턴, ']' 이후 → 질문
 │    └── ']' 없음       →  "❌ 닫는 대괄호 ']'가 없습니다." 출력 → continue
 └── 일반 모드
      └── split(maxsplit=1)  →  첫 토큰 → 패턴, 나머지 → 질문

질문이 비어있으면 → 멀티라인 입력 (get_multiline)
```

---

## 4. 요구사항 (Requirements)

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-068-001 | `gemini-ai-chat-code.py`의 `/context` 명령어가 `[pattern1, pattern2]` 대괄호 구문으로 다중 파일 패턴을 지원해야 한다. | 필수 |
| REQ-068-002 | 단일 패턴 입력(`/context src/*.py 질문`)이 기존과 동일하게 정상 동작해야 한다 (하위 호환성). | 필수 |
| REQ-068-003 | 닫는 대괄호 `]`가 누락된 경우 적절한 에러 메시지를 출력해야 한다. | 필수 |
| REQ-068-004 | 질문이 생략된 경우 멀티라인 입력 모드(`get_multiline`)로 전환되어야 한다. | 필수 |
| REQ-068-005 | 도움말 메시지에 단일 패턴, 단일 패턴+질문, 다중 패턴+질문의 3가지 사용 예시를 포함해야 한다. | UI 개선 |
| REQ-068-006 | 변수명 `patterns`를 `file_patterns`로 변경하여 다른 스크립트와 명명 규칙을 통일해야 한다. | 코드 품질 |

---

## 5. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `gemini-ai-chat-code.py` | **수정** | `/context` 핸들러 패턴 파싱 로직을 GenAI/Claude와 동일하게 교체 |

---

## 6. 검증 시나리오

| # | 입력 | 기대 결과 |
|---|------|----------|
| 1 | `/context` | 도움말 + 3가지 예시 출력 |
| 2 | `/context src/*.py` | 패턴 `['src/*.py']` 매칭 후 멀티라인 입력 진입 |
| 3 | `/context src/*.py 이 코드 분석해줘` | 패턴 `['src/*.py']`, 질문 `이 코드 분석해줘`로 AI 호출 |
| 4 | `/context [src/*.py, docs/*.md]` | 패턴 `['src/*.py', 'docs/*.md']` 매칭 후 멀티라인 입력 진입 |
| 5 | `/context [src/*.py, docs/*.md] README 작성해줘` | 패턴 2개 매칭, 질문 `README 작성해줘`로 AI 호출 |
| 6 | `/context [src/*.py` | `❌ 닫는 대괄호 ']'가 없습니다.` 오류 출력 |

---

## 7. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.068 | 2026-03-05 | - | 최초 작성: Gemini `/context` 다중 파일 패턴 지원 통일 |


