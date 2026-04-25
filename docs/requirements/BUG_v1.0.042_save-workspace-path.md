# BUG: /save 명령어 파일 저장 경로 오류 - workspace 기준 경로 미적용

> **문서 버전**: v1.0.042  
> **작성일**: 2026-02-25  
> **수정일**: 2026-02-25  
> **대상 파일**: `gemini-ai-chat-code01.py`, `claude-ai-chat-code01.py`  
> **관련 모듈**: `src/response_parser.py`, `src/file_manager.py`  
> **심각도**: High  
> **상태**: ✅ 수정 완료 (방안 A+B 적용)

---

## 1. 증상

### 1.1 현상

`/workspace <경로>` 명령어로 작업 디렉토리를 변경한 후, `/save` 명령어로 AI 응답의 파일을 저장하면 **변경된 workspace 경로가 아닌, 프로그램이 실행된 프로젝트 소스코드 위치(`os.getcwd()`)를 기준**으로 파일이 저장됩니다.

### 1.2 재현 절차

```
# 1. 프로그램 실행 (프로젝트 소스 디렉토리에서 실행)
C:\03_sources\skc3779_srcs\p3-ai-code-chat-messages> python gemini-ai-chat-code01.py

# 2. workspace를 다른 프로젝트 경로로 변경
👤 You: /workspace C:\projects\my-webapp
✅ 작업 디렉토리 변경: C:\projects\my-webapp

# 3. AI에게 파일 생성 요청
👤 You: src/utils/helper.py 파일을 만들어줘

# 4. /save로 파일 저장 시도
👤 You: /save

# ❌ 기대 저장 위치: C:\projects\my-webapp\src\utils\helper.py
# ❌ 실제 저장 위치: 프로젝트 소스 위치 기준으로 잘못 해석될 수 있음
```

### 1.3 예상 동작 vs 실제 동작

| 항목 | 내용 |
|------|------|
| **예상 동작** | `/workspace`로 설정한 경로를 base로 파일 저장 |
| **실제 동작** | 프로그램 실행 위치(`os.getcwd()`)를 base로 인식 |

---

## 2. 원인 분석

### 2.1 초기 workspace 설정 (gemini-ai-chat-code01.py, Line 91)

```python
# gemini-ai-chat-code01.py - Line 91
workspace = os.getcwd()
```

```python
# claude-ai-chat-code01.py - Line 94
workspace = os.getcwd()
```

두 파일 모두 **프로그램이 실행된 현재 디렉토리**를 초기 workspace로 사용합니다.  
이 값은 프로젝트 소스코드가 위치한 경로이므로, `/save` 시 파일이 소스코드 디렉토리에 저장됩니다.

### 2.2 /workspace 명령어의 경로 변경 (gemini-ai-chat-code01.py, Lines 219-231)

```python
# gemini-ai-chat-code01.py
elif command == '/workspace':
    if args:
        new_workspace = Path(args).resolve()
        if new_workspace.exists() and new_workspace.is_dir():
            assistant.file_manager = FileManager(str(new_workspace))
            assistant.context_builder = ContextBuilder(assistant.file_manager)
            file_watcher.stop()
            file_watcher = FileWatcher(str(new_workspace))
            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
        else:
            print(f"❌ 유효하지 않은 디렉토리: {args}")
    else:
        print(f"📂 현재 작업 디렉토리: {assistant.file_manager.workspace_dir}")
```

```python
# claude-ai-chat-code01.py (Lines 217-227)
elif command == '/workspace':
    if args:
        new_workspace = Path(args).resolve()
        if new_workspace.exists() and new_workspace.is_dir():
            assistant.file_manager = FileManager(str(new_workspace))
            assistant.context_builder = ContextBuilder(assistant.file_manager)
            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
        else:
            print(f"❌ 유효하지 않은 디렉토리: {args}")
    else:
        print(f"📂 현재 작업 디렉토리: {assistant.file_manager.workspace_dir}")
```

### 2.3 /save 명령어의 파일 저장 (src/response_parser.py, Line 63)

```python
# response_parser.py - Line 63
file_path = self.file_manager.workspace_dir / current_path
```

### 2.4 근본 원인 정리

| # | 원인 | 설명 |
|---|------|------|
| 1 | **초기 workspace = `os.getcwd()`** | 프로그램 실행 위치(소스코드 디렉토리)가 기본 workspace로 설정됨 |
| 2 | **`/workspace` 변경 시 `file_manager` 재생성** | `FileManager`는 재생성되지만, `response_parser`가 참조하는 `file_manager`가 갱신되지 않을 수 있음 |
| 3 | **`response_parser`의 `file_manager` 참조** | `response_parser`는 assistant 생성 시 전달받은 `file_manager`를 참조하며, `/workspace` 변경 후에도 이전 참조를 유지할 수 있음 |
| 4 | **claude 버전: `file_watcher` 미갱신** | `claude-ai-chat-code01.py`에서는 `/workspace` 변경 시 `file_watcher`를 재초기화하지 않음 (gemini 버전은 재초기화함) |

### 2.5 두 파일 비교 분석

| 항목 | gemini-ai-chat-code01.py | claude-ai-chat-code01.py |
|------|--------------------------|--------------------------|
| 초기 workspace | `os.getcwd()` (Line 91) | `os.getcwd()` (Line 94) |
| `/workspace` 변경 | `FileManager` + `ContextBuilder` + `FileWatcher` 재생성 | `FileManager` + `ContextBuilder` 재생성, ⚠️ **`FileWatcher` 미갱신** |
| `/save` 구현 | `assistant.extract_and_save_files()` (Line 209) | `assistant.extract_and_save_files()` (Line 312) |
| `response_parser` 갱신 | ❌ 미갱신 가능성 | ❌ 미갱신 가능성 |
| **동일 버그 존재** | ✅ 예 | ✅ 예 |

> **결론**: `gemini-ai-chat-code01.py`와 `claude-ai-chat-code01.py` **모두 동일한 버그**가 존재합니다.

---

## 3. 해결 방안

### 3.1 방안 A: `/workspace` 변경 시 `response_parser`의 `file_manager` 참조 동기화 (권장)

`/workspace` 명령어 실행 시 `assistant` 내부의 `response_parser`도 새로운 `file_manager`를 참조하도록 수정합니다.

#### 수정 대상: gemini-ai-chat-code01.py (Lines 219-231)

**수정 전:**
```python
elif command == '/workspace':
    if args:
        new_workspace = Path(args).resolve()
        if new_workspace.exists() and new_workspace.is_dir():
            assistant.file_manager = FileManager(str(new_workspace))
            assistant.context_builder = ContextBuilder(assistant.file_manager)
            file_watcher.stop()
            file_watcher = FileWatcher(str(new_workspace))
            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
```

**수정 후:**
```python
elif command == '/workspace':
    if args:
        new_workspace = Path(args).resolve()
        if new_workspace.exists() and new_workspace.is_dir():
            assistant.file_manager = FileManager(str(new_workspace))
            assistant.context_builder = ContextBuilder(assistant.file_manager)
            # response_parser의 file_manager 참조도 갱신
            assistant.response_parser.file_manager = assistant.file_manager
            file_watcher.stop()
            file_watcher = FileWatcher(str(new_workspace))
            workspace = str(new_workspace)  # 로컬 변수도 갱신
            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
```

#### 수정 대상: claude-ai-chat-code01.py (Lines 217-227)

**수정 전:**
```python
elif command == '/workspace':
    if args:
        new_workspace = Path(args).resolve()
        if new_workspace.exists() and new_workspace.is_dir():
            assistant.file_manager = FileManager(str(new_workspace))
            assistant.context_builder = ContextBuilder(assistant.file_manager)
            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
```

**수정 후:**
```python
elif command == '/workspace':
    if args:
        new_workspace = Path(args).resolve()
        if new_workspace.exists() and new_workspace.is_dir():
            assistant.file_manager = FileManager(str(new_workspace))
            assistant.context_builder = ContextBuilder(assistant.file_manager)
            # response_parser의 file_manager 참조도 갱신
            assistant.response_parser.file_manager = assistant.file_manager
            # file_watcher도 새 workspace로 갱신
            file_watcher.stop()
            file_watcher = FileWatcher(str(new_workspace), callback=on_file_changed)
            workspace = str(new_workspace)  # 로컬 변수도 갱신
            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
```

### 3.2 방안 B: Assistant 클래스에 `change_workspace()` 메서드 추가 (구조적 개선)

workspace 변경 로직을 Assistant 내부로 캡슐화하여, 내부 참조 일관성 보장:

```python
# src/gemini_assistant.py 또는 src/claude_assistant.py에 추가
def change_workspace(self, new_workspace_dir: str) -> bool:
    """작업 디렉토리를 변경하고 관련 내부 참조를 모두 갱신합니다."""
    from pathlib import Path
    new_path = Path(new_workspace_dir).resolve()
    
    if not new_path.exists() or not new_path.is_dir():
        return False
    
    # FileManager 재생성
    self.file_manager = FileManager(str(new_path))
    
    # ContextBuilder 재생성
    self.context_builder = ContextBuilder(self.file_manager)
    
    # ResponseParser의 file_manager 참조 갱신
    self.response_parser.file_manager = self.file_manager
    
    return True
```

**main 함수에서의 사용:**
```python
elif command == '/workspace':
    if args:
        if assistant.change_workspace(args):
            file_watcher.stop()
            file_watcher = FileWatcher(str(Path(args).resolve()))
            workspace = str(Path(args).resolve())
            print(f"✅ 작업 디렉토리 변경: {Path(args).resolve()}")
        else:
            print(f"❌ 유효하지 않은 디렉토리: {args}")
    else:
        print(f"📂 현재 작업 디렉토리: {assistant.file_manager.workspace_dir}")
```

### 3.3 방안 C: `response_parser`가 `file_manager`를 직접 참조하지 않고, 저장 시점에 동적으로 가져오기

```python
# src/response_parser.py 수정

class ResponseParser:
    def __init__(self, get_file_manager):
        """file_manager를 callable로 받아 항상 최신 참조를 사용"""
        self._get_file_manager = get_file_manager

    @property
    def file_manager(self):
        return self._get_file_manager()
```

> **권장**: 방안 A (즉시 적용 가능, 최소 변경) + 방안 B (향후 구조적 개선)

---

## 4. claude-ai-chat-code01.py 추가 버그

### 4.1 `/workspace` 변경 시 `file_watcher` 미갱신

`claude-ai-chat-code01.py`에서는 `/workspace` 변경 시 `file_watcher`를 재초기화하지 않습니다.  
이로 인해 파일 변경 감시가 **이전 workspace 경로**를 계속 감시하게 됩니다.

**현재 코드 (claude-ai-chat-code01.py, Lines 217-227):**
```python
elif command == '/workspace':
    if args:
        new_workspace = Path(args).resolve()
        if new_workspace.exists() and new_workspace.is_dir():
            assistant.file_manager = FileManager(str(new_workspace))
            assistant.context_builder = ContextBuilder(assistant.file_manager)
            # ⚠️ file_watcher가 여전히 이전 workspace를 감시함
            print(f"✅ 작업 디렉토리 변경: {new_workspace}")
```

**비교: gemini-ai-chat-code01.py (Lines 219-227)**는 `file_watcher` 재초기화를 수행:
```python
file_watcher.stop()
file_watcher = FileWatcher(str(new_workspace))
```

---

## 5. 테스트 시나리오

### 5.1 기본 테스트 - workspace 변경 후 /save

```
# Step 1: 프로그램 실행
> python gemini-ai-chat-code01.py

# Step 2: workspace 변경
👤 You: /workspace C:\projects\target-project
✅ 작업 디렉토리 변경: C:\projects\target-project

# Step 3: 현재 workspace 확인
👤 You: /workspace
📂 현재 작업 디렉토리: C:\projects\target-project

# Step 4: AI에게 파일 생성 요청
👤 You: src/hello.py 파일을 만들어줘

# Step 5: /save 실행
👤 You: /save

# 검증: 파일이 C:\projects\target-project\src\hello.py 에 저장되는지 확인
```

### 5.2 경로 확인 테스트

```
# 저장된 파일 경로 로그 출력 개선 (디버깅용)
✅ 파일 저장됨: src/hello.py
   📁 실제 경로: C:\projects\target-project\src\hello.py
```

### 5.3 /workspace 연속 변경 테스트

```
👤 You: /workspace C:\project-A
✅ 작업 디렉토리 변경: C:\project-A

👤 You: (AI에게 파일 생성 요청 → /save)
# 검증: C:\project-A 에 저장

👤 You: /workspace C:\project-B
✅ 작업 디렉토리 변경: C:\project-B

👤 You: (AI에게 파일 생성 요청 → /save)
# 검증: C:\project-B 에 저장 (C:\project-A 가 아님)
```

---

## 6. 영향 범위

| 파일 | 영향 여부 | 설명 |
|------|-----------|------|
| `gemini-ai-chat-code01.py` | ✅ | `/workspace` 변경 후 `/save` 경로 오류 |
| `claude-ai-chat-code01.py` | ✅ | 동일 + `file_watcher` 미갱신 추가 버그 |
| `src/response_parser.py` | ✅ | `file_manager.workspace_dir` 참조 경로의 일관성 문제 |
| `src/file_manager.py` | ⬜ | 직접적 버그 없음 (참조되는 대상) |
| `src/gemini_assistant.py` | ⬜ | 중계 역할만 수행 |
| `src/claude_assistant.py` | ⬜ | 중계 역할만 수행 |

---

## 7. 검증 체크리스트

- [ ] `gemini-ai-chat-code01.py`: `/workspace` 변경 후 `response_parser.file_manager` 갱신 확인
- [ ] `claude-ai-chat-code01.py`: `/workspace` 변경 후 `response_parser.file_manager` 갱신 확인
- [ ] `claude-ai-chat-code01.py`: `/workspace` 변경 후 `file_watcher` 재초기화 확인
- [ ] `/save` 실행 시 변경된 workspace 경로에 파일 저장 확인
- [ ] 연속 workspace 변경 후에도 올바른 경로로 저장되는지 확인
- [ ] `/workspace` (인자 없이) 실행 시 올바른 경로 표시 확인
- [ ] `/tree`, `/files` 명령어도 변경된 workspace 기준으로 동작하는지 확인

---

## 8. 버전별 조치 계획

| 버전 | 조치 사항 | 상태 |
|------|----------|------|
| v1.0.042 | 버그 분석 및 문서화 | ✅ 완료 |
| v1.0.043 | 방안 A+B 적용 (change_workspace 메서드 + 전체 참조 동기화) | ✅ 완료 |
| v1.0.044 | claude 버전 file_watcher 미갱신 추가 버그 수정 | ✅ 완료 |
| v1.0.045 | 테스트 코드 작성 및 검증 | ✅ 완료 (17개 테스트 통과) |

---

## 9. 참고

- **관련 BUG 문서**: `BUG_v1.0.001_save-command-fix.md` (이전 /save 명령어 파일 추출 패턴 문제)
- **관련 파일**: `gemini-ai-chat-code01.py`, `claude-ai-chat-code01.py`, `src/response_parser.py`

---

## 10. 버전 히스토리

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|----------|
| v1.0.042 | 2026-02-25 | AI Assistant | /save 명령어 workspace 경로 인식 버그 분석 및 해결 방안 문서화 |
| v1.0.045 | 2026-02-25 | AI Assistant | 테스트 코드 작성 완료 (tests/test_change_workspace.py, 17 tests) |
