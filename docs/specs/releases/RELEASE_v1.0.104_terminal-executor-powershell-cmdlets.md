# RELEASE v1.0.104 — TerminalExecutor Windows PowerShell Cmdlet 허용 목록 추가

| 항목 | 내용 |
|---|---|
| 릴리즈 버전 | v1.0.104 |
| 릴리즈 일자 | 2026-04-23 |
| 브랜치 | release_v1.0.100 |
| 수정 파일 | [src/terminal_executor.py](../../../src/terminal_executor.py) |

---

## 배경 및 문제

### 핵심 원인

`terminal_executor.py` 의 `ALLOWED_COMMANDS` 는 Unix 스타일 크로스플랫폼 명령어만 포함하고 있었다.

```python
# 기존 — Unix 스타일 명령어만 있음
'ls', 'dir', 'cat', 'type', 'head', 'tail', 'find', 'grep', 'more', ...
```

반면 `agent_runner.py:_build_system_prompt()` 는 `get_os_shell_hint()` 를 통해 모델에게
Windows 환경임을 알리므로, 모델은 `Get-Content`, `Get-ChildItem` 같은 PowerShell Cmdlet 을
자연스럽게 생성한다. 이 Cmdlet 들이 allowlist 에 없어 에이전트 루프에서 차단됐다.

```
허용되지 않은 명령어: get-content
허용되지 않은 명령어: get-childitem
```

### 구조적 문제

`_run_shell_lines()` 의 `base_cmd = cmd.split()[0].lower()` 로 판별하기 때문에
Cmdlet 이름(`Get-Content`)의 소문자 형태(`get-content`)가 allowlist 에 있어야 통과된다.

---

## 해결 내용

### 1. `ALLOWED_POWERSHELL_CMDLETS` 클래스 상수 신규 추가

Windows 에서 안전하게 허용할 수 있는 **읽기/조회 전용** PowerShell Cmdlet 33개를
카테고리별로 분류해 클래스 상수로 추가했다.

| 카테고리 | 추가 Cmdlet |
|---|---|
| 파일 시스템 조회 | `get-childitem`, `get-content`, `get-item`, `get-location`, `resolve-path`, `split-path`, `join-path`, `test-path` |
| 텍스트 검색·처리 | `select-string`, `measure-object`, `select-object`, `where-object`, `sort-object`, `group-object`, `compare-object` |
| 시스템 정보 | `get-date`, `get-process`, `get-host`, `get-computerinfo`, `get-variable`, `get-psdrive` |
| 환경·속성 조회 | `get-itemproperty` |
| 출력 포맷 | `write-output`, `write-host`, `format-list`, `format-table`, `out-string`, `out-default` |
| 기타 유틸 | `get-alias`, `get-command`, `get-help`, `get-module`, `get-executionpolicy` |

### 2. `DANGEROUS_COMMANDS` 에 PowerShell 위험 Cmdlet 추가

기존에 Unix 명령어만 있던 위험 명령어 목록에 PowerShell 대응 명령어를 함께 등록했다.
안전 모드(`/shell`)에서 차단, 위험 모드(`/shell!`)에서만 허용된다.

| 카테고리 | 추가 Cmdlet |
|---|---|
| 파일 삭제 | `remove-item` |
| 파일 이동·복사 | `move-item`, `copy-item`, `rename-item` |
| 파일 내용 변경 | `set-content`, `add-content`, `clear-content`, `new-item` |
| 권한 변경 | `set-acl` |
| 프로세스 종료 | `stop-process` |
| 네트워크 | `invoke-webrequest`, `invoke-restmethod` |
| 레지스트리 쓰기 | `set-itemproperty`, `remove-itemproperty` |
| 보안 정책 | `set-executionpolicy` |
| 임의 코드 실행 | `invoke-expression`, `iex` |

### 3. `__init__` — `_effective_allowed` 동적 목록

인스턴스 생성 시 OS 를 감지해 Windows 인 경우에만 PowerShell Cmdlet 을 허용 목록에 추가한다.
Linux / macOS 에서는 기존 `ALLOWED_COMMANDS` 만 사용하므로 동작 변화 없다.

```python
def __init__(self, workspace_dir: Path, timeout: int = 60):
    self.workspace_dir = workspace_dir
    self.timeout = timeout
    # Windows 환경에서 PowerShell Cmdlet을 동적으로 허용 목록에 추가
    self._effective_allowed: list = list(self.ALLOWED_COMMANDS)
    if platform.system() == 'Windows':
        self._effective_allowed += self.ALLOWED_POWERSHELL_CMDLETS
```

### 4. `execute()` — `_effective_allowed` 사용

기존 `self.ALLOWED_COMMANDS` 비교를 `self._effective_allowed` 로 변경하여
동적 목록이 검증에 반영되도록 했다.

```python
# 변경 전
if base_cmd not in self.ALLOWED_COMMANDS:

# 변경 후
if base_cmd not in self._effective_allowed:
    hint_cmds = sorted(set(self._effective_allowed))[:10]
```

### 5. `get_allowed_commands()` — 동적 목록 반환

```python
def get_allowed_commands(self) -> str:
    """허용된 명령어 목록 반환 (OS별 동적 목록 포함)"""
    return ", ".join(sorted(set(self._effective_allowed)))
```

### 6. `shell_help()` — Windows 허용 목록 표시

정적 메서드인 `shell_help()` 의 허용 명령어 출력 부분도 OS 를 감지해
Windows 인 경우 PowerShell Cmdlet 포함 목록을 출력한다.

```python
all_allowed = list(TerminalExecutor.ALLOWED_COMMANDS)
if platform.system() == 'Windows':
    all_allowed += TerminalExecutor.ALLOWED_POWERSHELL_CMDLETS
lines.append(f"  {', '.join(sorted(set(all_allowed)))}")
```

---

## 변경 파일

### 수정

| 파일 | 변경 내용 |
|---|---|
| [src/terminal_executor.py](../../../src/terminal_executor.py) | `ALLOWED_POWERSHELL_CMDLETS` 클래스 상수 신규 추가 (33 Cmdlet). `DANGEROUS_COMMANDS` 에 PowerShell 위험 Cmdlet 16개 추가. `__init__` 에 `_effective_allowed` 동적 목록 생성 로직 추가. `execute()` 의 허용 검사 및 오류 힌트를 `_effective_allowed` 기반으로 수정. `get_allowed_commands()` 동적 목록 반환. `shell_help()` 허용 목록 출력 OS 감지 추가. |

---

## 설계 원칙

| 원칙 | 적용 내용 |
|---|---|
| **최소 권한** | 읽기/조회 전용 Cmdlet 만 `ALLOWED` 에 추가. 쓰기·실행·네트워크 Cmdlet 은 `DANGEROUS` 등록 |
| **OS 격리** | `_effective_allowed` 는 인스턴스 수준에서 OS 를 감지해 조립. Linux/macOS 동작 무변경 |
| **소문자 통일** | PowerShell 은 대소문자 무감하므로 allowlist 는 소문자로만 정의. `execute()` 의 `base_cmd.lower()` 와 일관성 유지 |
| **안전 우선** | `invoke-expression` / `iex` 는 임의 코드 실행 가능하므로 `DANGEROUS` 에 명시적 등록 |

---

## 적용 전후 비교

### Before (Windows 에서 차단됨)

```
▶️  $ Get-Content src/terminal_executor.py
허용되지 않은 명령어: get-content
hint: 허용 명령어: cat, cmake, date, dir, echo, env, find, git, grep, head...
```

### After (정상 실행)

```
▶️  $ Get-Content src/terminal_executor.py
returncode=0
"""
TerminalExecutor - 터미널 명령어 실행 모듈
...
```

---

## 회귀 영향

- **Linux / macOS**: `platform.system() != 'Windows'` 분기로 `_effective_allowed = ALLOWED_COMMANDS` 그대로. 동작 변화 없음.
- **Windows 안전 모드 (`/shell`)**: PowerShell Cmdlet 33개 추가 허용. 위험 Cmdlet 은 여전히 차단.
- **Windows 위험 모드 (`/shell!`)**: `allow_unsafe=True` 경로는 변경 없음 — `DANGEROUS_COMMANDS` 는 경고 표시 후 실행.
- **에이전트 루프 (`/agents`)**: `_run_shell_lines()` 의 `terminal_executor.execute(cmd, allow_unsafe=dangerous)` 호출 패턴 그대로 — 코드 변경 불필요.

---

## 이슈/후속

- PowerShell 별칭(alias) 문제: `ls` 는 `Get-ChildItem` 의 별칭이므로 기존 허용 목록에서도 실제로는 동작하나, 의미상 명시 추가로 명확화.
- `Get-Content -Tail` 처럼 파라미터가 포함된 복합 명령은 `base_cmd` 추출로 정상 처리됨.
- 향후 필요 시 `ALLOWED_POWERSHELL_CMDLETS` 에 Cmdlet 을 추가하면 `_effective_allowed` 자동 반영.
