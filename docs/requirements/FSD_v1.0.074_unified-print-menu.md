# FSD v1.0.074 — `print_menu()` 중복 제거 및 `CommandRegistry` 단일 출처 통합

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.074 |
| 작성일 | 2026-03-06 |
| 상태 | 완료 |
| 대상 파일 | `src/command_registry.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `gemini-ai-chat-code.py` |

---

## 1. 개요

`/help` 명령 실행 시 출력하는 `print_menu()` 함수가 세 엔트리 포인트에 **거의 동일한 내용으로 중복** 정의되어 있었다.  
명령 하나를 추가하거나 설명을 바꾸려면 세 파일을 모두 수정해야 하는 유지보수 문제가 존재했다.

또한 명령 설명이 `CommandRegistry`와 `print_menu()` 양쪽에 이중으로 관리되어 불일치 위험이 있었다.

이 문서는 `print_menu()` 를 `command_registry.py` 로 이동하고,  
`CommandInfo`에 `example` 필드를 추가해 설명·예제를 **한 곳에서만** 관리하는 설계를 정의한다.

---

## 2. 현황 분석

### 2.1 문제점

| 문제 | 설명 |
|---|---|
| 중복 코드 | 세 엔트리 포인트에 거의 동일한 `print_menu()` 50+ 줄이 각각 존재 |
| 이중 관리 | `CommandRegistry`의 `description`과 `print_menu()`의 출력 문자열이 두 곳에 따로 운영 |
| 예제 부재 | `CommandInfo`에 example 필드가 없어 레지스트리에서 예제를 관리 불가 |
| 플랫폼 불일치 | Gemini의 `print_menu()`에 "✨ AI 자동 기능" 블록이 없어 Claude/GenAI와 내용 차이 존재 |

### 2.2 변경 전 구조

```
claude-ai-chat-code.py  →  def print_menu():  (50줄)
gen-ai-chat-code.py     →  def print_menu():  (50줄)
gemini-ai-chat-code.py  →  def print_menu():  (46줄)

CommandRegistry._commands  →  description만 있고 example 없음
```

---

## 3. 설계

### 3.1 `CommandInfo` — `example` 필드 추가

```python
@dataclass
class CommandInfo:
    name: str
    description: str
    usage: str = ""
    example: str = ""   # 추가: 사용 예제 (예: '[src/*.py, docs/*.md]')
```

### 3.2 `print_menu(title)` — `command_registry.py`로 이동

```python
def print_menu(title: str = "AI Code Assistant") -> None:
    registry = CommandRegistry()
    print("\n" + "=" * 80)
    print(f"🤖 {title}")
    print("=" * 80)
    print("명령어:")
    for cmd in registry.get_commands():
        usage_col = f"  {cmd.usage:<36}"
        example_part = f"   예) {cmd.example}" if cmd.example else ""
        print(f"{usage_col}{cmd.description}{example_part}")
    print("=" * 80)
    print("\n💡 사용 예시:")
    ...
    print("=" * 80)
```

### 3.3 엔트리 포인트 변경

각 파일에서:

| 변경 전 | 변경 후 |
|---|---|
| `def print_menu(): ...` (50줄) | 제거 |
| (없음) | `from src.command_registry import print_menu` 추가 |
| (없음) | `_MENU_TITLE = "<플랫폼> Code Assistant - AI 코딩 어시스턴트"` 상수 추가 |
| `print_menu()` | `print_menu(_MENU_TITLE)` |

---

## 4. 명령 설명 개선

`CommandInfo` 전체 목록을 논리적 그룹으로 재구성하고 설명·예제를 개선했다.

### 그룹 구조

| 그룹 | 명령 |
|---|---|
| 파일 탐색 | `/files`, `/tree` |
| 컨텍스트 읽기 | `/read`, `/context`, `/auto_context` |
| 응답 처리 | `/save`, `/run`, `/diff`, `/apply` |
| 대화 히스토리 | `/history`, `/clear`, `/save_history`, `/load_history`, `/list_history` |
| 입력 모드 | `/multiline`, `/stream`, `/nostream` |
| 시스템 명령 | `/shell`, `/shell!`, `/workspace`, `/watch`, `/unwatch`, `/watch_list` |
| 설정 | `/tokens`, `/llm_config`, `/template`, `/template_list`, `/template_reset` |
| 기타 | `/help`, `/quit` |

### 설명 개선 예시

| 명령 | 변경 전 설명 | 변경 후 설명 | 예제 |
|---|---|---|---|
| `/files` | 프로젝트 파일 목록 | 프로젝트 파일 목록 조회 | `.py .js` |
| `/read` | 파일 읽기 및 컨텍스트 저장 | 파일 읽기 → 대화 컨텍스트에 추가 | `[src/*.py, docs/*.md]` |
| `/history` | 대화 히스토리 보기/삭제 | 대화 히스토리 보기 / 앞부터 N개 삭제 | `-r 5` |
| `/save` | AI 응답에서 파일 추출 및 저장 | AI 응답의 코드 블록 추출·파일로 저장 | (없음) |
| `/shell` | 쉘 명령어 실행 (안전 모드) | 시스템 명령어 실행 (안전 모드) | `shell git status` |
| `/multiline` | 멀티라인 입력 모드 | 여러 줄 입력 모드 (종료: /end) | (없음) |

---

## 5. 출력 형식

```
================================================================================
🤖 Claude Code Assistant - AI 코딩 어시스턴트
================================================================================
명령어:
  /files [ext]                       프로젝트 파일 목록 조회   예) .py .js
  /tree                              디렉토리 트리 출력
  /read <pattern | [p1, p2, ...]>    파일 읽기 → 대화 컨텍스트에 추가   예) [src/*.py, docs/*.md]
  /context <pattern> [질문]          파일 컨텍스트와 함께 AI에게 질문   예) src/*.py 이 코드 리뷰해줘
  ...
================================================================================

💡 사용 예시:
  /context src/*.py 이 코드를 리뷰해줘
  /read [src/*.py, docs/*.md]
  /history --remove 5
  /auto_context original/*.md 한글로 번역해줘

✨ AI 자동 기능:
  - 파일 시스템 조작 (읽기/쓰기/목록)
  - Git 버전 관리 (상태/diff/커밋)
  - 패키지 의존성 분석 (pip/npm)
================================================================================
```

---

## 6. 영향 범위

| 파일 | 변경 내용 |
|---|---|
| `src/command_registry.py` | `CommandInfo`에 `example` 추가, 전체 명령 설명·예제 개선, `print_menu(title)` 추가 |
| `claude-ai-chat-code.py` | 로컬 `print_menu()` 제거, `print_menu` import, `_MENU_TITLE` 상수, 호출부 수정 |
| `gen-ai-chat-code.py` | 동일 |
| `gemini-ai-chat-code.py` | 동일 (기존에 없던 "✨ AI 자동 기능" 블록도 포함됨) |

`src/history_manager.py`, `tests/` — **변경 없음**

---

## 7. 검증

```powershell
python -c "import py_compile; [py_compile.compile(f, doraise=True) for f in \
  ['claude-ai-chat-code.py','gen-ai-chat-code.py','gemini-ai-chat-code.py','src/command_registry.py']]; \
  print('OK')"
# → OK

python -m unittest discover -s tests -v
# → 기존 테스트 모두 통과
```
