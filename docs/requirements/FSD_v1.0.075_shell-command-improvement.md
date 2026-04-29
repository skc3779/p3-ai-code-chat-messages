# FSD v1.0.075 — `/shell` 명령 버그 수정 및 `--help`, 히스토리 저장 기능 추가

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.075 |
| 작성일 | 2026-03-06 |
| 상태 | 초안 |
| 대상 파일 | `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `gemini-ai-chat-code.py`, `src/terminal_executor.py`, `src/command_registry.py` |

---

## 1. 개요

현재 `/shell <cmd>` / `/shell! <cmd>` 명령에는 다음 문제가 존재한다.

| # | 파일 | 유형 | 내용 |
|---|---|---|---|
| B-01 | `claude-ai-chat-code.py` | 버그 | 실패 시 `stderr` 출력 블록이 중복 — 오류 메시지 2회 출력 |
| B-02 | `gemini-ai-chat-code.py` | 버그 | `execute(args, allow_dangerous=...)` 호출 — `TerminalExecutor.execute()` 파라미터는 `allow_unsafe` → `TypeError` 발생 |
| B-03 | `gemini-ai-chat-code.py` | 버그 | `result`(Dict)를 `print(f"\n{result}")`로 raw 출력 — JSON 덤프 형태로 표시됨 |
| F-01 | 전체 | 미구현 | `/shell --help` / `/shell -h` — OS별 유용 명령어 힌트 미제공 |
| F-02 | 전체 | 미구현 | 명령어 실행 내용·결과가 `conversation_history`에 저장되지 않아 AI가 실행 결과를 참조 불가 |

---

## 2. 현황 분석

### 2.1 `TerminalExecutor.execute()` 시그니처

```python
# src/terminal_executor.py
def execute(self, command: str, allow_unsafe: bool = False) -> Dict:
```

반환 Dict 구조:
```python
{
    'success': bool,
    'stdout': str,       # 성공 시
    'stderr': str,       # 오류 출력
    'returncode': int,
    'command': str,
    'error': str,        # 실패 원인 설명
    'hint': str,         # 사용자 안내
    'use_unsafe': str    # /shell! 사용 안내
}
```

### 2.2 B-01 — claude stderr 이중 출력 (claude-ai-chat-code.py)

```python
# 아래 블록이 else: 안에 두 번 반복되어 있음
if result.get('stderr'):
    print(f"\n🔴 오류 출력:")
    print(result['stderr'])

if result.get('stderr'):          # ← 중복
    print(f"\n🔴 오류 출력:")
    print(result['stderr'])
```

### 2.3 B-02/B-03 — gemini 잘못된 호출 및 출력 (gemini-ai-chat-code.py)

```python
# B-02: allow_dangerous는 존재하지 않는 파라미터 → TypeError
result = assistant.terminal_executor.execute(args, allow_dangerous=False)

# B-03: result는 Dict → "{...}" 형태로 출력됨
print(f"\n{result}")
```

---

## 3. 요구사항

### 3.1 버그 수정 (필수)

| ID | 파일 | 수정 내용 |
|---|---|---|
| B-01 | `claude-ai-chat-code.py` | 중복 `stderr` 출력 블록 제거 |
| B-02 | `gemini-ai-chat-code.py` | `allow_dangerous=` → `allow_unsafe=` 로 변경 |
| B-03 | `gemini-ai-chat-code.py` | Dict 결과를 포맷 출력 함수로 교체 |

### 3.2 `--help` / `-h` 옵션 (신규)

| ID | 요구사항 |
|---|---|
| FR-001 | `/shell --help` 또는 `/shell -h` 입력 시 OS 감지 후 플랫폼별 유용 명령어 목록 출력 |
| FR-002 | Windows 환경: PowerShell 및 CMD 명령어 힌트 제공 |
| FR-003 | Linux/macOS 환경: Bash 명령어 힌트 제공 |
| FR-004 | 각 명령어에 설명과 `/shell` 사용 예시를 함께 출력 |
| FR-005 | 안전 모드(`/shell`) 허용 명령어 목록 및 위험 모드(`/shell!`) 안내 포함 |

### 3.3 `conversation_history` 저장 (신규)

| ID | 요구사항 |
|---|---|
| FR-006 | 명령 실행 성공·실패 여부와 무관하게 실행한 명령어와 결과를 `conversation_history`에 기록 |
| FR-007 | `role: "user"` 항목에 실행 명령어, `role: "assistant"` 항목에 실행 결과(stdout/stderr/오류) 저장 |
| FR-008 | GenAI(`List[str]`) 플랫폼은 형식에 맞게 문자열로 변환하여 저장 |
| FR-009 | `--help`/`-h` 출력은 히스토리에 저장하지 않는다 |

---

## 4. 구현 사양

### 4.1 `src/terminal_executor.py` — `shell_help()` 추가

```python
import platform

@staticmethod
def shell_help() -> str:
    """OS별 유용 명령어 도움말 반환"""
    is_windows = platform.system() == 'Windows'
    lines = []

    if is_windows:
        lines.append("=== Windows 환경 — PowerShell / CMD 주요 명령어 ===\n")
        lines.append("【파일/디렉토리】")
        lines.append("  /shell dir                    현재 디렉토리 파일 목록 (CMD)")
        lines.append("  /shell Get-ChildItem          현재 디렉토리 파일 목록 (PowerShell)")
        lines.append("  /shell type <file>            파일 내용 출력 (CMD)")
        lines.append("  /shell Get-Content <file>     파일 내용 출력 (PowerShell)")
        lines.append("  /shell mkdir <name>           디렉토리 생성")
        lines.append("  /shell! move <src> <dst>      파일 이동 (위험 모드)")
        lines.append("  /shell! del <file>            파일 삭제 (위험 모드)")
        lines.append("")
        lines.append("【시스템 정보】")
        lines.append("  /shell whoami                 현재 사용자")
        lines.append("  /shell hostname               컴퓨터 이름")
        lines.append("  /shell date /t                현재 날짜 (CMD)")
        lines.append("  /shell Get-Date               현재 날짜·시간 (PowerShell)")
        lines.append("  /shell set                    환경변수 목록 (CMD)")
        lines.append("  /shell Get-Process            실행 중인 프로세스 (PowerShell)")
        lines.append("")
        lines.append("【Python / 패키지】")
        lines.append("  /shell python --version       Python 버전 확인")
        lines.append("  /shell pip list               설치된 패키지 목록")
        lines.append("  /shell pip install <pkg>      패키지 설치")
        lines.append("")
        lines.append("【Git】")
        lines.append("  /shell git status             변경 파일 확인")
        lines.append("  /shell git log --oneline -10  최근 10개 커밋")
        lines.append("  /shell git diff               변경 내용 확인")
        lines.append("")
        lines.append("【네트워크 (위험 모드)】")
        lines.append("  /shell! curl <url>            HTTP 요청")
        lines.append("  /shell! wget <url>            파일 다운로드")
    else:
        lines.append("=== Linux / macOS 환경 — Bash 주요 명령어 ===\n")
        lines.append("【파일/디렉토리】")
        lines.append("  /shell ls -la                 파일 목록 (상세)")
        lines.append("  /shell cat <file>             파일 내용 출력")
        lines.append("  /shell head -20 <file>        파일 앞 20줄 출력")
        lines.append("  /shell tail -20 <file>        파일 끝 20줄 출력")
        lines.append("  /shell find . -name '*.py'    파일 검색")
        lines.append("  /shell grep -r 'text' src/    내용 검색")
        lines.append("  /shell mkdir -p <name>        디렉토리 생성")
        lines.append("  /shell! rm <file>             파일 삭제 (위험 모드)")
        lines.append("  /shell! mv <src> <dst>        파일 이동 (위험 모드)")
        lines.append("")
        lines.append("【시스템 정보】")
        lines.append("  /shell whoami                 현재 사용자")
        lines.append("  /shell date                   현재 날짜·시간")
        lines.append("  /shell env                    환경변수 목록")
        lines.append("  /shell ps aux                 실행 중인 프로세스")
        lines.append("")
        lines.append("【Python / 패키지】")
        lines.append("  /shell python3 --version      Python 버전 확인")
        lines.append("  /shell pip3 list              설치된 패키지 목록")
        lines.append("  /shell pip3 install <pkg>     패키지 설치")
        lines.append("")
        lines.append("【Git】")
        lines.append("  /shell git status             변경 파일 확인")
        lines.append("  /shell git log --oneline -10  최근 10개 커밋")
        lines.append("  /shell git diff               변경 내용 확인")
        lines.append("")
        lines.append("【네트워크 (위험 모드)】")
        lines.append("  /shell! curl <url>            HTTP 요청")
        lines.append("  /shell! wget <url>            파일 다운로드")
        lines.append("  /shell! ssh user@host         원격 접속")

    lines.append("")
    lines.append("【허용 명령어 (안전 모드)】")
    lines.append(f"  {', '.join(sorted(TerminalExecutor.ALLOWED_COMMANDS))}")
    lines.append("")
    lines.append("⚠️  /shell! 은 위험 명령어를 허용합니다. 실행 전 확인 프롬프트가 표시됩니다.")
    return "\n".join(lines)
```

### 4.2 엔트리 포인트 공통 처리 로직 (Claude / GenAI / Gemini)

```python
elif command == '/shell' or command == '/shell!':
    # --help / -h 처리 (히스토리 저장 안 함)
    if args in ('--help', '-h', ''):
        if not args:
            print("❌ 실행할 명령어를 입력하세요.")
            print("💡 도움말: /shell --help")
        else:
            print(assistant.terminal_executor.shell_help())
        continue

    allow_unsafe = command == '/shell!'

    if allow_unsafe:
        print("⚠️  위험 모드: 모든 명령어가 허용됩니다.")
        confirm = input("▶️  정말 실행하시겠습니까? (y/N): ").strip().lower()
        if confirm != 'y':
            print("⏭️  취소됨")
            continue

    print(f"\n💻 명령어 실행: {args}")
    result = assistant.terminal_executor.execute(args, allow_unsafe=allow_unsafe)

    # 출력
    if result.get('success'):
        print(f"\n✅ 실행 성공 (return code: {result.get('returncode', 0)})")
        if result.get('stdout'):
            print(f"\n📤 출력:")
            print(result['stdout'])
    else:
        print(f"\n❌ 실행 실패")
        if result.get('error'):
            print(f"   {result['error']}")
        if result.get('hint'):
            print(f"💡 {result['hint']}")
        if result.get('use_unsafe'):
            print(f"🔓 {result['use_unsafe']}")
        if result.get('stderr'):
            print(f"\n🔴 오류 출력:")
            print(result['stderr'])

    # conversation_history 저장
    user_content = f"[쉘 명령 실행: {command} {args}]"
    if result.get('success'):
        assistant_content = f"[실행 성공 (returncode={result.get('returncode', 0)})]\n{result.get('stdout', '')}"
    else:
        assistant_content = (
            f"[실행 실패]\n"
            f"오류: {result.get('error', '')}\n"
            f"stderr: {result.get('stderr', '')}"
        ).strip()

    # Claude / Gemini: List[Dict]
    assistant.conversation_history.append({"role": "user", "content": user_content})
    assistant.conversation_history.append({"role": "assistant", "content": assistant_content})
```

> **GenAI (`List[str]`) 저장 형태:**
> ```python
> assistant.conversation_history.append(f"user: {user_content}")
> assistant.conversation_history.append(f"assistant: {assistant_content}")
> ```

### 4.3 `command_registry.py` — usage 업데이트

```python
# 변경 전
CommandInfo('/shell',  '시스템 명령어 실행 (안전 모드)',  '/shell <cmd>',  'shell git status'),
CommandInfo('/shell!', '시스템 명령어 실행 (위험 명령 허용)', '/shell! <cmd>', 'shell! rm -rf tmp/'),

# 변경 후
CommandInfo('/shell',  '시스템 명령어 실행 (안전 모드)',  '/shell <cmd|--help|-h>', 'shell git status'),
CommandInfo('/shell!', '시스템 명령어 실행 (위험 명령 허용)', '/shell! <cmd>',         'shell! rm -rf tmp/'),
```

---

## 5. `--help` 출력 예시 (Windows)

```
=== Windows 환경 — PowerShell / CMD 주요 명령어 ===

【파일/디렉토리】
  /shell dir                    현재 디렉토리 파일 목록 (CMD)
  /shell Get-ChildItem          현재 디렉토리 파일 목록 (PowerShell)
  /shell type <file>            파일 내용 출력 (CMD)
  ...

【Git】
  /shell git status             변경 파일 확인
  /shell git log --oneline -10  최근 10개 커밋

【허용 명령어 (안전 모드)】
  cat, cmake, cd, date, dir, echo, env, find, git, ...

⚠️  /shell! 은 위험 명령어를 허용합니다. 실행 전 확인 프롬프트가 표시됩니다.
```

---

## 6. 테스트 시나리오

| # | 입력 | 기대 결과 |
|---|---|---|
| T-01 | `/shell --help` | OS 감지 후 플랫폼별 명령어 힌트 출력, 히스토리 저장 없음 |
| T-02 | `/shell -h` | T-01과 동일 |
| T-03 | `/shell git status` | 실행 결과 출력 + `conversation_history`에 user/assistant 항목 추가 |
| T-04 | `/shell rm file.txt` | 위험 명령 차단 오류 + 히스토리 저장 (`실행 실패`) |
| T-05 | `/shell! rm file.txt` y | 확인 후 실행, 결과 히스토리 저장 |
| T-06 | `/shell! rm file.txt` N | 취소됨, 히스토리 저장 없음 |
| T-07 | `/shell` (인수 없음) | `❌ 실행할 명령어를 입력하세요. 💡 도움말: /shell --help` |
| T-08 | `/shell unknown_cmd` | 허용 안 된 명령 오류 + `실행 실패` 히스토리 저장 |
| T-09 | stderr 발생 명령 | stderr 1회만 출력 (중복 없음) |
| T-10 | Gemini `/shell git status` | `allow_unsafe=False` 정상 호출, 포맷 출력 |

---

## 7. 영향 범위

| 파일 | 변경 유형 |
|---|---|
| `src/terminal_executor.py` | `shell_help()` 정적 메서드 추가 |
| `claude-ai-chat-code.py` | 중복 stderr 제거, `--help` 처리, 히스토리 저장 |
| `gen-ai-chat-code.py` | `--help` 처리, 히스토리 저장 (GenAI 형식) |
| `gemini-ai-chat-code.py` | `allow_dangerous` → `allow_unsafe` 수정, Dict 포맷 출력, `--help` 처리, 히스토리 저장 |
| `src/command_registry.py` | `/shell` usage 문자열 업데이트 |

---

## 8. 이슈 및 제약

- `TerminalExecutor.execute()` 내부에서 `cwd=workspace_dir`로 실행되므로, 실행 결과의 경로 관련 출력은 현재 작업 디렉토리 기준이다.
- `/shell! rm` 등 취소한 경우(`N` 응답)에는 히스토리에 기록하지 않는다.
- `--help`는 읽기 전용 정보 출력이므로 히스토리에 저장하지 않는다.
- GenAI의 `conversation_history`가 `List[str]`이므로, `user:` / `assistant:` 접두사 방식으로 저장한다.
