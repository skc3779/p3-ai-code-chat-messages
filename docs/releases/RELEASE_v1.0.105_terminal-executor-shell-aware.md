# RELEASE v1.0.105 — TerminalExecutor 쉘 환경 감지 및 DANGEROUS_COMMANDS 환경별 분리

| 항목 | 내용 |
|---|---|
| 릴리즈 버전 | v1.0.105 |
| 릴리즈 일자 | 2026-04-25 |
| 브랜치 | release_v1.0.110 |
| 수정 파일 | [src/terminal_executor.py](../../../src/terminal_executor.py), [tests/test_terminal_executor.py](../../../tests/test_terminal_executor.py) |

---

## 배경 및 문제

### 기존 구조의 한계

`terminal_executor.py` 는 `ALLOWED_COMMANDS` + `ALLOWED_POWERSHELL_CMDLETS` 의 허용 목록 방식을 사용해 왔다.
이 구조는 다음 문제를 가지고 있었다.

1. **과도한 차단** — 허용 목록에 없는 명령어는 무조건 `허용되지 않은 명령어` 오류를 반환한다.
   에이전트가 새로운 도구(`jq`, `bat`, `tree` 등)를 사용하려 할 때마다 목록 추가가 필요했다.
2. **환경 구분 없음** — Windows PowerShell / CMD / Linux / Mac 간 위험 명령어가 뒤섞여
   크로스플랫폼 관리가 어려웠다.
3. **shell_help 단순 분기** — `platform.system() == 'Windows'` 하나로만 분기해
   PowerShell 과 CMD 환경을 동일하게 처리했다.

---

## 해결 내용

### 1. `get_shell_type()` 정적 메서드 신규 추가

현재 실행 환경을 감지해 네 가지 값 중 하나를 반환한다.

```python
@staticmethod
def get_shell_type() -> str:
    """반환값: "Windows PowerShell" | "Windows CMD" | "Linux" | "Mac" """
    system = platform.system()
    if system == 'Windows':
        if os.environ.get('PSModulePath'):   # PowerShell 세션에서만 설정됨
            return 'Windows PowerShell'
        return 'Windows CMD'
    if system == 'Darwin':
        return 'Mac'
    return 'Linux'
```

### 2. DANGEROUS_COMMANDS 환경별 4개 클래스 상수로 분리

기존 단일 `DANGEROUS_COMMANDS` 리스트를 환경별 `Set[str]` 로 분리했다.

| 상수 | 환경 | 핵심 포함 항목 |
|---|---|---|
| `_DANGEROUS_WINDOWS_POWERSHELL` | Windows PowerShell | `remove-item`, `invoke-expression`, `stop-process`, `set-content`, `set-executionpolicy` 등 |
| `_DANGEROUS_WINDOWS_CMD` | Windows CMD | `del`, `rmdir`, `format`, `diskpart`, `taskkill`, `shutdown` 등 |
| `_DANGEROUS_LINUX` | Linux | `rm`, `chmod`, `kill`, `shutdown`, `sudo`, `fdisk`, `dd` 등 |
| `_DANGEROUS_MAC` | macOS | `rm`, `chmod`, `kill`, `diskutil`, `launchctl`, `pmset`, `sudo` 등 |

### 3. ALLOWED_COMMANDS / ALLOWED_POWERSHELL_CMDLETS 제거

허용 목록 방식을 폐기하고 **위험 명령어만 차단**하는 방식으로 전환한다.

```python
# 변경 전 — 허용 목록 + 위험 목록 이중 검사
if base_cmd in self.DANGEROUS_COMMANDS:
    return error(위험 명령어)
if base_cmd not in self._effective_allowed:
    return error(허용되지 않은 명령어)   ← 제거

# 변경 후 — 위험 목록만 검사
if not allow_unsafe and base_cmd in self.DANGEROUS_COMMANDS:
    return error(위험 명령어)
```

이로써 허용 목록에 없는 도구도 위험하지 않으면 자유롭게 실행된다.

### 4. `__init__` — 환경별 DANGEROUS_COMMANDS 인스턴스 속성 설정

```python
def __init__(self, workspace_dir: Path, timeout: int = 60):
    self.workspace_dir = workspace_dir
    self.timeout = timeout
    shell_type = self.get_shell_type()
    if shell_type == 'Windows PowerShell':
        self.DANGEROUS_COMMANDS = self._DANGEROUS_WINDOWS_POWERSHELL
    elif shell_type == 'Windows CMD':
        self.DANGEROUS_COMMANDS = self._DANGEROUS_WINDOWS_CMD
    elif shell_type == 'Mac':
        self.DANGEROUS_COMMANDS = self._DANGEROUS_MAC
    else:
        self.DANGEROUS_COMMANDS = self._DANGEROUS_LINUX
```

`agent_runner.py` 의 `base in self.terminal_executor.DANGEROUS_COMMANDS` 접근 패턴은 그대로 유지된다.

### 5. `get_allowed_commands()` → `get_dangerous_commands()` 로 교체

허용 목록 반환에서 **위험 명령어 목록 반환**으로 의미를 변경했다.

```python
def get_dangerous_commands(self) -> str:
    """현재 환경의 위험 명령어 목록 반환"""
    return ', '.join(sorted(self.DANGEROUS_COMMANDS))
```

### 6. `shell_help()` 환경별 4분기 개편

`platform.system() == 'Windows'` 단일 분기에서 `get_shell_type()` 기반 4분기로 확장.

| 환경 | 특화 내용 |
|---|---|
| Windows PowerShell | `Get-ChildItem`, `Get-Content`, `Select-String`, `Get-Date`, `Get-ComputerInfo` 등 Cmdlet 중심 |
| Windows CMD | `dir`, `type`, `find /i`, `tasklist`, `date /t`, `time /t` 등 CMD 네이티브 명령어 중심 |
| macOS | Linux 공통 명령어 + `sw_vers`, `diskutil` 등 macOS 전용 항목 |
| Linux | `uname`, `df`, `ps aux` 등 Linux 표준 명령어 중심 |

---

## 변경 파일

### 수정

| 파일 | 변경 내용 |
|---|---|
| [src/terminal_executor.py](../../../src/terminal_executor.py) | `get_shell_type()` 추가. `ALLOWED_COMMANDS` / `ALLOWED_POWERSHELL_CMDLETS` 제거. `_DANGEROUS_WINDOWS_POWERSHELL` / `_DANGEROUS_WINDOWS_CMD` / `_DANGEROUS_LINUX` / `_DANGEROUS_MAC` 추가. `__init__` 에서 환경별 `DANGEROUS_COMMANDS` 설정. `execute()` 에서 허용 목록 검사 제거. `get_allowed_commands()` → `get_dangerous_commands()` 로 교체. `shell_help()` 4분기 확장. `_get_dangerous_for_shell()` 헬퍼 추가. |
| [tests/test_terminal_executor.py](../../../tests/test_terminal_executor.py) | `test_get_shell_type_*` 추가. `test_all_allowed_commands_are_permitted` 제거. `test_execute_unknown_command_blocked` → `test_execute_unknown_command_allowed` 로 변경 (알 수 없는 명령어 허용 검증). `test_execute_dangerous_command_blocked` 환경 감지 기반으로 수정. `test_get_allowed_commands` → `test_get_dangerous_commands_*` 로 교체. `test_dangerous_commands_not_in_safe_mode` 추가 (전체 위험 명령어 차단 검증). `test_shell_help_*` 추가. 총 17개 테스트 — 17 passed. |

---

## 설계 원칙

| 원칙 | 적용 내용 |
|---|---|
| **최소 차단** | 허용 목록 제거 → 위험 명령어만 차단. 새 도구 추가 시 목록 갱신 불필요 |
| **환경 격리** | 4개 환경별 독립 Set — 타 환경의 명령어가 오탐을 일으키지 않음 |
| **하위 호환** | `self.DANGEROUS_COMMANDS` 인스턴스 속성 유지 — `agent_runner.py` 코드 변경 없음 |
| **소문자 통일** | 모든 위험 명령어는 소문자 정의. `execute()` 의 `base_cmd.lower()` 와 일관성 유지 |

---

## 적용 전후 비교

### Before — 허용 목록 없으면 차단

```
▶️  $ jq . package.json
허용되지 않은 명령어: jq
hint: 허용 명령어: cat, cmake, date, dir, echo, env, find, git, grep, head...
```

### After — 위험 명령어 아니면 자유 실행

```
▶️  $ jq . package.json
returncode=0
{
  "name": "my-project",
  ...
}
```

---

## 회귀 영향

- **`agent_runner.py`**: `terminal_executor.DANGEROUS_COMMANDS` 접근 패턴 무변경.
- **`claude-ai-chat-code.py` / `gemini-ai-chat-code.py` / `gen-ai-chat-code.py`**: `execute()`, `shell_help()` 시그니처 무변경.
- **`test_bypass_approvals.py`**: `MagicMock()` 으로 `DANGEROUS_COMMANDS` 를 직접 주입하므로 영향 없음.
- **Linux / macOS 안전 모드**: 허용 목록 사라짐 — 기존에 차단되던 미등록 명령어가 이제 실행됨. 위험 명령어(`rm`, `chmod` 등)는 여전히 차단.
- **Windows 안전 모드**: 기존 `ALLOWED_COMMANDS` + `ALLOWED_POWERSHELL_CMDLETS` 에 없던 명령어도 실행 가능. 위험 Cmdlet (`Remove-Item`, `Invoke-Expression` 등)은 여전히 차단.
