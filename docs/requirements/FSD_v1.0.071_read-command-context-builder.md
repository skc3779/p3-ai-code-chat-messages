# FSD v1.0.071 — `/read` 명령어 ContextBuilder 통합 개선

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.071 |
| 작성일 | 2026-03-06 |
| 상태 | 초안 |
| 대상 파일 | `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `gemini-ai-chat-code.py` |
| 연관 모듈 | `src/context_builder.py`, `src/file_pattern_matcher.py` |

---

## 1. 개요

`/read` 명령어는 사용자가 지정한 파일 패턴에 해당하는 파일을 읽어 화면에 출력하는 기능이다.  
현재 세 어시스턴트(Claude, GenAI, Gemini)에서 구현 방식이 서로 달라 동작이 불일치하며,  
`context_builder.py`의 `build_context()` 활용이 미흡하다.

이 문서는 다음을 목표로 `/read` 구현을 통일한다.

- `context_builder.build_context(include_tree=False, file_patterns=[...])` 를 사용하여 파일 읽기
- `[pattern1, pattern2, ...]` 다중 패턴 형식 지원(`/context`와 동일)
- 읽은 컨텍스트를 `conversation_history`에 통일된 포맷으로 저장
- 화면 출력은 `build_files_context()` 결과를 그대로 사용

---

## 2. 현황 분석

### 2.1 claude-ai-chat-code.py (현재)

```python
elif command == '/read':
    if not args:
        print("❌ 파일 패턴을 지정하세요. 예: /read src/*.py")
        continue

    pattern_matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
    patterns = args.split()                          # 공백 기준 분리만 지원
    all_files = assistant.file_manager.list_files()
    matched_files = pattern_matcher.filter_files(all_files, patterns)

    if matched_files:
        context = assistant.context_builder.build_files_context(matched_files)
        history_entry = {"role": "user", "content": f"[파일 컨텍스트 로드됨]\n{context}"}
        assistant.conversation_history.append(history_entry)
        print(context)
    else:
        print(f"❌ 패턴 '{args}'에 해당하는 파일이 없습니다.")
```

**문제점:**
- `[pattern1, pattern2]` 다중 패턴 형식 미지원
- `build_context()` 대신 `build_files_context()` 직접 호출
- `FilePatternMatcher`를 별도로 생성 (중복)

---

### 2.2 gen-ai-chat-code.py (현재)

```python
elif command == '/read':
    if not args:
        print("❌ 파일 패턴을 지정하세요. 예: /read src/*.py")
        continue

    pattern_matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
    patterns = args.split()
    all_files = assistant.file_manager.list_files()
    matched_files = pattern_matcher.filter_files(all_files, patterns)

    if matched_files:
        context = assistant.context_builder.build_files_context(matched_files)
        assistant.conversation_history.append(f"[File Context]\n{context}")  # 영문, 포맷 불일치
        print(context)
    else:
        print(f"❌ 패턴 '{args}'에 해당하는 파일이 없습니다.")
```

**문제점:**
- `conversation_history`에 영문으로 저장 (Claude와 포맷 불일치)
- `conversation_history` 항목이 `str` 타입 (Claude는 `dict` 타입 사용)
- `[pattern1, pattern2]` 다중 패턴 형식 미지원

---

### 2.3 gemini-ai-chat-code.py (현재)

```python
elif command == '/read':
    if not args:
        print("❌ 사용법: /read <파일패턴>")
        continue
    patterns = args.split()
    matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
    all_files = assistant.file_manager.list_files()
    matched_files = matcher.filter_files(all_files, patterns)
    if matched_files:
        for filepath in matched_files[:5]:           # 최대 5개 파일 제한
            content = assistant.file_manager.read_file(filepath)
            if content:
                rel_path = filepath.relative_to(assistant.file_manager.workspace_dir)
                print(f"\n📄 {rel_path}:\n{'-' * 40}\n{content[:2000]}")  # 2000자 제한
                if len(content) > 2000:
                    print(f"\n... (생략, 총 {len(content)}자)")
    else:
        print("❌ 일치하는 파일이 없습니다.")
```

**문제점:**
- `build_files_context()` 미사용 — 파일별 직접 읽기 (별도 포맷)
- 최대 5개 파일 제한 (임의 제한)
- 2000자 제한 (`MAX_CONTEXT_SIZE` 미적용)
- `conversation_history`에 저장하지 않음

---

## 3. 개선 요구사항

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-01 | `/read` 패턴 인수를 `/context`와 동일하게 `[p1, p2, ...]` 다중 형식 지원 | 필수 |
| FR-02 | `context_builder.build_context(include_tree=False, file_patterns=[...])` 를 사용하여 파일 내용 구성 | 필수 |
| FR-03 | 읽은 컨텍스트를 화면(`stdout`)에 출력 | 필수 |
| FR-04 | 읽은 컨텍스트를 `conversation_history`에 `{"role": "user", "content": ...}` 포맷으로 저장 | 필수 |
| FR-05 | 파일 매칭 결과 없을 때 패턴과 함께 오류 메시지 출력 | 필수 |
| FR-06 | 세 어시스턴트(Claude, GenAI, Gemini)에 동일한 로직 적용 | 필수 |

### 3.2 비기능 요구사항

| ID | 요구사항 |
|---|---|
| NFR-01 | 파일 수 제한 없음 (기존 Gemini 5개 제한 제거) |
| NFR-02 | 출력 크기는 `MAX_CONTEXT_SIZE` 환경변수로 제어 (`context_builder` 위임) |
| NFR-03 | `build_file_tree` 호출 제외 (`include_tree=False` 고정) |

---

## 4. 설계

### 4.1 패턴 파싱 로직

기존 `/context` 명령어와 동일한 패턴 파싱 로직을 적용한다.

```
args = "[src/*.py, docs/*.md]"
  → file_patterns = ["src/*.py", "docs/*.md"]

args = "src/*.py tests/*.py"
  → file_patterns = ["src/*.py", "tests/*.py"]

args = "src/*.py"
  → file_patterns = ["src/*.py"]
```

### 4.2 통일 구현 (세 어시스턴트 공통)

```python
elif command == '/read':
    if not args:
        print("❌ 파일 패턴을 지정하세요.")
        print("예: /read src/*.py")
        print("예: /read [src/*.py, docs/*.md]")
        continue

    # 패턴 파싱: [p1, p2] 또는 공백 구분 단일/다중 패턴
    if args.startswith('['):
        try:
            end_idx = args.index(']')
            file_patterns = [p.strip() for p in args[1:end_idx].split(',') if p.strip()]
        except ValueError:
            print("❌ 닫는 대괄호 ']'가 없습니다.")
            continue
    else:
        file_patterns = args.split()

    # ContextBuilder를 통해 파일 컨텍스트 구성 (트리 제외)
    context = assistant.context_builder.build_context(
        include_tree=False,
        file_patterns=file_patterns
    )

    if context.strip():
        print(context)
        assistant.conversation_history.append({
            "role": "user",
            "content": f"[파일 읽음: {args}]\n{context}"
        })
    else:
        print(f"❌ 패턴 '{args}'에 해당하는 파일이 없습니다.")
```

### 4.3 conversation_history 저장 포맷

```json
{
  "role": "user",
  "content": "[파일 읽음: src/*.py]\n\n================================================================================\n📄 파일: src/context_builder.py\n================================================================================\n```python\n...\n```\n"
}
```

- `role`: `"user"` 고정 — AI가 이전 컨텍스트로 참조할 수 있도록 함
- `content` 접두사: `[파일 읽음: {args}]` — 히스토리에서 식별 가능하도록 구분자 포함
- 본문: `build_files_context()` 출력 그대로 사용

---

## 5. 변경 대상 파일

| 파일 | 변경 내용 | 변경 범위 |
|---|---|---|
| `claude-ai-chat-code.py` | `/read` 핸들러 교체 | `elif command == '/read':` 블록 |
| `gen-ai-chat-code.py` | `/read` 핸들러 교체 | `elif command == '/read':` 블록 |
| `gemini-ai-chat-code.py` | `/read` 핸들러 교체 | `elif command == '/read':` 블록 |

**변경 없는 파일:**
- `src/context_builder.py` — 기존 `build_context()` 그대로 사용 (변경 불필요)
- `src/file_pattern_matcher.py` — `build_context()` 내부에서 처리
- `src/command_registry.py` — 사용법 문자열만 업데이트

---

## 6. 사용법 변경

### 변경 전

```
/read <pattern>     - 파일 읽기 (예: /read src/*.py)
```

### 변경 후

```
/read <pattern>     - 파일 읽기 및 컨텍스트 저장 (예: /read src/*.py)
                      다중 패턴: /read [src/*.py, docs/*.md]
```

---

## 7. 동작 시나리오

### 시나리오 1: 단일 패턴

```
> /read src/*.py
================================================================================
📄 파일: src/context_builder.py
================================================================================
```python
...
```
...

✅ 파일 컨텍스트가 대화 히스토리에 저장되었습니다.
```

### 시나리오 2: 다중 패턴 `[...]` 형식

```
> /read [src/*.py, tests/*.py]
================================================================================
📄 파일: src/context_builder.py
================================================================================
...
📄 파일: tests/test_context_builder.py
================================================================================
...
```

### 시나리오 3: 패턴 미매칭

```
> /read nonexistent/*.xyz
❌ 패턴 'nonexistent/*.xyz'에 해당하는 파일이 없습니다.
```

### 시나리오 4: MAX_CONTEXT_SIZE 초과

```
> /read **/*.py
...
⚠️ 컨텍스트 크기 제한으로 일부 파일이 생략되었습니다.
=> total:980000 + context:25000 > max_context_size:1000000
```

---

## 8. 테스트 계획

| 테스트 ID | 설명 | 기대 결과 |
|---|---|---|
| TC-01 | 단일 패턴 `/read src/*.py` | 패턴 매칭 파일 내용 출력, history 저장 |
| TC-02 | 다중 패턴 `/read [src/*.py, tests/*.py]` | 두 패턴 모두 매칭 파일 내용 출력 |
| TC-03 | 빈 인수 `/read` | 사용법 안내 출력, history 미저장 |
| TC-04 | 미매칭 패턴 `/read *.xyz` | 오류 메시지 출력, history 미저장 |
| TC-05 | `MAX_CONTEXT_SIZE` 초과 | 생략 경고 메시지 포함, 초과 전 파일까지 출력 |
| TC-06 | `[` 없이 단힌 `]` 패턴 오류 처리 | 닫는 괄호 오류 메시지 출력 |
| TC-07 | conversation_history 저장 포맷 확인 | `role: "user"`, content에 `[파일 읽음: ...]` 접두사 포함 |

---

## 9. 참고

- `build_context()` 내부에서 `fnmatch`를 통해 패턴 매칭 수행 (`src/context_builder.py` 참조)
- `MAX_CONTEXT_SIZE` 환경변수로 출력 크기 제어 (`FSD_v1.0.070` 참조)
- `/context` 명령어의 패턴 파싱 로직과 동일하게 적용하여 사용자 경험 통일
