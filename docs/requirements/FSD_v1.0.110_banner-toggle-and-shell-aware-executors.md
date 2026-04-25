# FSD v1.0.110 — 배너 출력 토글(`PRINT_BANNER`) + Terminal/Code Executor 4-쉘 인식·실행 일원화 + 한글 인코딩 정합

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.110 |
| 작성일 | 2026-04-25 |
| 상태 | ✅ 구현 완료 (2026-04-25) |
| 선행 문서 | FSD v1.0.067 (배너 버전 .env 연동), FSD v1.0.088 (OS Shell Hint), FSD v1.0.102 (Code Executor UTF-8 자식 인코딩), FSD v1.0.104 (Terminal Executor Shell Hint), FSD v1.0.107 (Agent Action Dispatcher), BUG v1.0.084 (Windows bash 미설치) |
| 대상 파일 | [claude-ai-chat-code.py](claude-ai-chat-code.py), [gemini-ai-chat-code.py](gemini-ai-chat-code.py), [gen-ai-chat-code.py](gen-ai-chat-code.py), [src/terminal_executor.py](src/terminal_executor.py), [src/code_executor.py](src/code_executor.py), [.env.example](.env.example) |
| 신규 파일 | [tests/test_banner_toggle.py](tests/test_banner_toggle.py), [tests/test_terminal_executor_shell_dispatch.py](tests/test_terminal_executor_shell_dispatch.py), [tests/test_code_executor_shell_dispatch.py](tests/test_code_executor_shell_dispatch.py) |

---

## 1. 개요 (Overview)

본 문서는 서로 직교하지만 같은 릴리스 사이클(v1.0.110)에서 함께 처리해야 하는 세 영역의 변경을 묶는다. **공통 축은 "OS·쉘 환경 자동 인식"** 이며, 그 결과로 (a) 배너 출력 제어, (b) 터미널 명령 실행 인터프리터 명시, (c) 코드 실행기 언어 매핑 단순화, (d) 두 실행기 모두에서 한글 깨짐 제거를 동시에 달성한다.

### 1.1 다루는 문제

| # | 영역 | 현 문제 | 본 FSD 의 대응 |
|---|---|---|---|
| A | 배너 출력 | 세 엔트리 포인트(`*-ai-chat-code.py`)는 무조건 ASCII Art 배너를 출력. 터미널 폭이 좁거나 로깅 환경(파이프·CI)에서 잡음을 만든다. 환경별 토글 수단 부재. | `.env` 의 `PRINT_BANNER` 환경 변수로 출력 여부 제어. 기본값 `true`. |
| B | TerminalExecutor 인터프리터 | `subprocess.run(command, shell=True, ...)` 만 사용 — 부모 쉘에 위임. Windows에서 PowerShell 세션이라도 `cmd.exe` 가 호출되거나, Linux 에서 `sh` 가 호출되어 **명령어가 의도한 쉘 문법으로 실행되지 않는** 케이스가 있다. | `get_shell_type()` 결과로 4-쉘 분기 — `powershell.exe -Command <cmd>`, `cmd.exe /c <cmd>`, `/bin/bash -c <cmd>` 명시 호출. |
| C | CodeExecutor 언어 맵 | `_BASE_LANGUAGES` + `_build_shell_config()` + `_SHELL_LANG_KEYS` 가 모듈 레벨로 분리되고 두 단계 결합으로 `SUPPORTED_LANGUAGES` 가 구성됨. 가독성 저하 + Mac/Linux 가 한 분기로 합쳐져 있어 향후 macOS 전용 분기를 도입하기 어렵다. | 4-쉘(`Windows PowerShell` / `Windows CMD` / `Linux` / `Mac`) 인식 → `_resolve_shell_lang_config()` 단일 함수가 환경별 쉘 설정을 반환. 클래스 안에서 `_build_supported_languages()` 정적 메서드로 응집. |
| D | 한글 인코딩 | `CodeExecutor` 는 v1.0.102 로 자식 UTF-8 강제까지 끝났으나 `TerminalExecutor` 는 자식 환경 변수 주입(`PYTHONIOENCODING`, `PYTHONUTF8`, `LC_ALL`) 이 없다. Windows CMD/PowerShell 에서 한글 파일명·내용 출력이 깨진다. | `TerminalExecutor` 에 `_build_child_env()` 도입. PowerShell 에는 `chcp 65001` / `[Console]::OutputEncoding=UTF8` 프리앰블, CMD 에는 `chcp 65001 > NUL & <cmd>` 프리픽스, bash 에는 env 만 주입. |

### 1.2 비범위

| 항목 | 비고 |
|---|---|
| `print_banner()` 의 디자인·색상·폰트 변경 | FSD v1.0.067 / v1.0.051 의 디자인을 유지 |
| `AgentActionDispatcher` 의 분류 로직 변경 | FSD v1.0.107 에서 확정. 본 FSD 는 호출 측만 영향 |
| `os_utils.get_os_shell_hint()` 변경 | 본 FSD 의 변경은 두 Executor 의 내부 분기에 한정. Hint 는 v1.0.107 결과 그대로 사용 |
| 새 언어 지원 (Ruby, Go 등) | `SUPPORTED_LANGUAGES` 정리는 가독성 목적 — 신규 언어는 별도 FSD |
| PowerShell 7(`pwsh`) 우선 호출 | 현재 환경이 `powershell.exe` (5.x) 표준. `pwsh` 자동 감지는 v1.0.111 후속 작업 |

---

## 2. 현황 분석

### 2.1 배너 출력 — 무조건 호출

[claude-ai-chat-code.py:170](claude-ai-chat-code.py#L170), [gemini-ai-chat-code.py:155](gemini-ai-chat-code.py#L155), [gen-ai-chat-code.py:176](gen-ai-chat-code.py#L176) 모두 `main()` 진입 직후 `print_banner()` 를 무조건 호출.

```python
# claude-ai-chat-code.py:111-170 (요약)
def main():
    load_environment()
    TokenManager.reload_from_env()
    ...
    print_banner()                # ← 토글 없음
    print(f"\n📂 현재 작업 디렉토리: {workspace}")
```

`AI_VERSION` 만 환경 변수로 노출되어 있고 출력 여부 자체는 제어 불가.

### 2.2 TerminalExecutor — 인터프리터 미명시

[src/terminal_executor.py:155-166](src/terminal_executor.py#L155-L166)

```python
result = subprocess.run(
    command,
    shell=True,                        # ← 부모 쉘에 전적 위임
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',
    timeout=self.timeout,
    cwd=str(self.workspace_dir),
    env=os.environ.copy()              # ← 자식 인코딩 강제 없음
)
```

문제:

| # | 증상 | 원인 |
|---|---|---|
| 1 | Windows 에서 `Get-ChildItem` 실행 시 "용어가 cmdlet 으로 인식되지 않습니다" | `shell=True` 가 `cmd.exe` 를 호출 — PowerShell 명령이 CMD 에서 실행 |
| 2 | Linux 에서 `[[ -d build ]] && echo ok` 가 `[[ : not found` | `shell=True` 가 `/bin/sh` 를 호출 — bashism 미지원 |
| 3 | Windows 한글 파일명 `dir` 출력 깨짐 | `chcp` 가 `949` (CP949) 인 상태에서 부모가 stdout 을 `utf-8` 로 디코드 → 깨짐 |
| 4 | `/agents` 자율 루프에서 한글 디렉토리 에러 메시지가 `?` 로 표시 | 동일 |

### 2.3 CodeExecutor — `_build_shell_config` 분기와 `_SHELL_LANG_KEYS` 결합

[src/code_executor.py:14-79](src/code_executor.py#L14-L79)

```python
def _build_shell_config() -> dict:
    if platform.system() == 'Windows':
        if os.environ.get('PSModulePath'):
            return {'cmd': 'cmd', 'args': [], 'ext': '.bat', 'icon': '🪟'}   # ← (a)
        return {'cmd': 'powershell', 'args': [...], 'ext': '.ps1', 'icon': '🪟'}
    return {'cmd': '/bin/bash', 'args': [], 'ext': '.sh', 'icon': '🖥️'}      # ← (b)

_BASE_LANGUAGES = { 'python': {...}, 'py': {...}, 'javascript': {...}, 'js': {...} }
_SHELL_LANG_KEYS = ('bash', 'sh', 'shell', 'powershell', 'ps1')

class CodeExecutor:
    def __init__(self, workspace_dir, timeout=30):
        ...
        shell_cfg = _build_shell_config()
        self.SUPPORTED_LANGUAGES = {**_BASE_LANGUAGES, **{k: shell_cfg for k in _SHELL_LANG_KEYS}}
```

평가:

| # | 문제 |
|---|---|
| (a) | `PSModulePath` 가 있으면 `cmd` 를 반환 — **로직 반전 버그**. PowerShell 세션에서는 `powershell` 을 호출해야 하나, `cmd` (`.bat`) 를 호출. 현재 분기 결과로 PS 세션이 .bat 임시 파일을 cmd.exe 로 실행해 한글 리터럴이 손상된다. |
| (b) | macOS 와 Linux 가 한 분기로 합쳐져 있어 macOS 의 `bash` 가 없는 환경(기본 zsh) 대응이 불가. 향후 `pwsh` 도입 시 분기점 부족. |
| (c) | `_BASE_LANGUAGES` 는 모듈 전역, `shell_cfg` 는 인스턴스 초기화 시점 결정 — 두 시점이 달라 단위 테스트에서 mock 하기 어려움. |
| (d) | `_SHELL_LANG_KEYS` 가 `('bash', 'sh', 'shell', 'powershell', 'ps1')` 5개로 하드코딩 — 환경에 따라 불필요한 키도 매핑(예: Linux 에서 `powershell` 키가 `/bin/bash` 로 매핑되어 PS 코드가 bash 로 실행됨). |

### 2.4 인코딩 비교

| Executor | 자식 stdout 디코드 | 자식 환경 변수 | PowerShell 프리앰블 | 결론 |
|---|---|---|---|---|
| `CodeExecutor` (v1.0.102) | `utf-8`, `errors='replace'` | `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`, `LC_ALL/LANG setdefault` | `$OutputEncoding=UTF8 + chcp 65001` | ✅ 한글/이모지 통과 |
| `TerminalExecutor` (현재) | `utf-8`, `errors='replace'` | `os.environ.copy()` (변경 없음) | 없음 | ❌ Windows 한글 깨짐 |

---

## 3. 설계 (Design)

### 3.1 Section A — `PRINT_BANNER` 환경 변수

#### 3.1.1 헬퍼 함수 도입

세 엔트리 포인트가 공유할 토글 헬퍼를 추가한다. 각 파일에 동일 시그니처로 정의(공통 모듈은 `src/` 에 두기에는 과도) 또는 `src/banner_utils.py` 에 단일 함수 도입.

```python
def _should_print_banner() -> bool:
    """`PRINT_BANNER` 환경 변수로 배너 출력 여부 결정.

    값 해석:
      - 'true' / '1' / 'yes' / 'on'  → True
      - 'false' / '0' / 'no' / 'off' → False
      - 미설정 / 빈 문자열            → True (기본 출력)
    대소문자 무시. 알 수 없는 값은 True 로 간주.
    """
    raw = os.getenv("PRINT_BANNER", "").strip().lower()
    if raw in ("false", "0", "no", "off"):
        return False
    return True
```

#### 3.1.2 호출부

```python
# claude-ai-chat-code.py:170 (예)
if _should_print_banner():
    print_banner()
```

> `print_banner()` 함수 내부는 변경하지 않는다. 호출 측에서만 결정 — 사이드 이펙트(예: 색상 모드 활성화) 가 배너에 종속되어 있지 않으므로 안전.

#### 3.1.3 `.env.example` 추가

```env
# 시작 시 ANSI Art 배너 출력 여부 (true/false). 기본값: true
PRINT_BANNER=true
```

### 3.2 Section B — TerminalExecutor 4-쉘 인터프리터

#### 3.2.1 인터프리터 매핑

`get_shell_type()` 결과를 사용해 명시적 인터프리터로 호출.

| 쉘 타입 | `subprocess.run` 인자 | shell= |
|---|---|---|
| Windows PowerShell | `['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', f"{PS_PREAMBLE}; {command}"]` | `False` |
| Windows CMD | `f'cmd.exe /c "chcp 65001 > NUL & {command}"'` | `True` (문자열 형태로 `cmd /c` 가 자체적으로 파싱) |
| Linux | `['/bin/bash', '-c', command]` | `False` |
| Mac | `['/bin/bash', '-c', command]` | `False` (macOS 도 `/bin/bash` 가 항상 존재 — `/bin/zsh` 는 사용자 기본일 뿐) |

> CMD 만 문자열 + `shell=True` 를 유지 — `cmd.exe /c` 는 한 토큰의 명령 문자열을 받아 자체 파서로 분리하는 것이 표준. 인자 리스트로 분해하면 파이프·리다이렉트가 깨진다.

#### 3.2.2 PowerShell 프리앰블

`CodeExecutor` 와 동일하되 `-Command` 인라인 형태로 압축:

```python
PS_INLINE_PREAMBLE = (
    "$OutputEncoding = [Console]::OutputEncoding = "
    "[System.Text.Encoding]::UTF8; "
    "chcp 65001 > $null; "
)
```

> CRLF 대신 `; ` 로 구분 — `-Command` 는 한 줄 인자.

#### 3.2.3 자식 환경 변수 (한글 인코딩)

`CodeExecutor._build_child_env()` 와 동일한 의미:

```python
def _build_child_env(self) -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")
    return env
```

> 두 Executor 가 동일 헬퍼를 갖되, 의도적으로 **공유 모듈로 추출하지 않는다** — 미래에 한 쪽만 정책이 달라질 가능성을 고려해 작은 중복을 허용. (NFR-110-04)

#### 3.2.4 `execute()` 갱신 흐름

```
execute(command, allow_unsafe)
  │
  ├─ 입력 검증 (빈 문자열) / 위험 명령 검사 (변경 없음)
  │
  ├─ shell_type = self.get_shell_type()
  ├─ argv, shell_flag = self._compose_argv(shell_type, command)
  │     └─ 위 표(3.2.1) 매핑
  │
  ├─ env = self._build_child_env()
  │
  ├─ subprocess.run(argv, shell=shell_flag, capture_output=True,
  │                  text=True, encoding='utf-8', errors='replace',
  │                  timeout=self.timeout, cwd=str(self.workspace_dir),
  │                  env=env)
  │
  └─ 결과 dict (스키마 변경 없음)
```

#### 3.2.5 위험 명령 검사 호환성

기존 `parts = command.split()` / `shlex.split()` 로 첫 토큰을 추출하는 로직은 **인터프리터 전환 이전 단계** 에 그대로 적용 — 사용자가 입력한 raw command 의 첫 토큰을 검사. 인터프리터 변경은 검사를 우회하지 않는다. (FR-110-09)

### 3.3 Section C — CodeExecutor 4-쉘 매핑 정리

#### 3.3.1 단일 메서드로 응집

`_build_shell_config` / `_BASE_LANGUAGES` / `_SHELL_LANG_KEYS` 모듈 레벨 3원 분리를 **클래스 내부 정적 메서드 하나로 통합**.

```python
class CodeExecutor:
    # 모든 환경에서 공통인 비-쉘 언어 — 모듈 상수로 충분
    _NATIVE_LANGUAGES = {
        'python':     {'cmd': 'python',  'args': [], 'ext': '.py', 'icon': '🐍'},
        'py':         {'cmd': 'python',  'args': [], 'ext': '.py', 'icon': '🐍'},
        'javascript': {'cmd': 'node',    'args': [], 'ext': '.js', 'icon': '📜'},
        'js':         {'cmd': 'node',    'args': [], 'ext': '.js', 'icon': '📜'},
    }

    @staticmethod
    def _shell_lang_config(shell_type: str) -> dict:
        """현 쉘 환경에 맞는 쉘-스크립트 실행 설정.

        반환 dict 의 의미:
          cmd  : 인터프리터 실행 파일
          args : 인자 리스트 (스크립트 경로는 호출 측에서 append)
          ext  : 임시 스크립트 확장자
          icon : 결과 패널 아이콘
        """
        if shell_type == 'Windows PowerShell':
            return {
                'cmd': 'powershell.exe',
                'args': ['-NoProfile', '-NonInteractive',
                         '-ExecutionPolicy', 'Bypass', '-File'],
                'ext': '.ps1',
                'icon': '🪟',
            }
        if shell_type == 'Windows CMD':
            return {'cmd': 'cmd.exe', 'args': ['/c'], 'ext': '.bat', 'icon': '🪟'}
        if shell_type == 'Mac':
            return {'cmd': '/bin/bash', 'args': [], 'ext': '.sh', 'icon': '🍎'}
        return     {'cmd': '/bin/bash', 'args': [], 'ext': '.sh', 'icon': '🖥️'}  # Linux

    @staticmethod
    def _build_supported_languages(shell_type: str) -> Dict[str, dict]:
        """쉘 타입을 받아 SUPPORTED_LANGUAGES dict 를 합성."""
        shell_cfg = CodeExecutor._shell_lang_config(shell_type)
        shell_keys = ('bash', 'sh', 'shell', 'powershell', 'ps1')
        return {
            **CodeExecutor._NATIVE_LANGUAGES,
            **{key: shell_cfg for key in shell_keys},
        }

    def __init__(self, workspace_dir: Path, timeout: int = 30):
        self.workspace_dir = workspace_dir
        self.timeout = timeout
        # TerminalExecutor 와 동일한 4-쉘 분류기를 재사용 — 분기 기준 일치
        from .terminal_executor import TerminalExecutor
        self.shell_type = TerminalExecutor.get_shell_type()
        self.SUPPORTED_LANGUAGES = self._build_supported_languages(self.shell_type)
```

#### 3.3.2 v1.0.102 와의 정합

`PS_UTF8_PREAMBLE`, `_wrap_code_for_shell()`, `_build_child_env()`, `file_encoding='utf-8-sig'` (.ps1 한정) 는 **그대로 유지**. 본 FSD 의 변경은 `SUPPORTED_LANGUAGES` 를 만드는 방식만 정리한다.

#### 3.3.3 `_build_shell_config()` 의 반전 버그 동시 수정

§ 2.3 (a) 에서 지적한 분기 반전을 `_shell_lang_config()` 으로 이전하면서 **PowerShell 세션 → `powershell.exe`, CMD 세션 → `cmd.exe`** 로 정정한다. 이는 v1.0.102 의 PowerShell UTF-8 프리앰블이 실제로 PowerShell 자식에서 동작하도록 만드는 전제이기도 하다.

### 3.4 Section D — 한글 인코딩 정합

| 항목 | TerminalExecutor | CodeExecutor |
|---|---|---|
| 자식 stdout 디코드 | `encoding='utf-8'`, `errors='replace'` | 동일 (변경 없음) |
| 자식 env 주입 | **본 FSD 신규** — `PYTHONIOENCODING/PYTHONUTF8/LC_ALL/LANG` | 이미 적용 |
| PowerShell 프리앰블 | `-Command` 인라인 (§ 3.2.2) | `.ps1` 헤더 (`PS_UTF8_PREAMBLE`, 기존) |
| CMD 코드페이지 | `chcp 65001 > NUL & <cmd>` | `.bat` 헤더 `@chcp 65001 > NUL` (신규 — § 3.4.1) |
| `.ps1` 파일 BOM | 해당 없음 | `utf-8-sig` (기존, FSD v1.0.102 § 3.6) |
| `.bat` 파일 BOM | 해당 없음 | **금지** — CMD 가 BOM 을 명령으로 오인 (NFR-110-05) |

#### 3.4.1 CMD 분기 (`.bat`) UTF-8 헤더

`CodeExecutor` 가 Windows CMD 환경에서 `.bat` 임시 파일을 만들 때:

```bat
@chcp 65001 > NUL
@echo off
<원본 코드>
```

- `@chcp 65001` : 콘솔 코드페이지를 UTF-8 로 전환. CMD 자체의 인코딩 한계로 한글 명령은 여전히 제한적이지만 **출력 인코딩** 은 UTF-8 로 통일된다.
- 파일은 **UTF-8 (BOM 없음)** 로 기록 — BOM 이 있으면 CMD 가 첫 줄을 명령으로 오인.

```python
def _wrap_code_for_shell(code: str, lang_cfg: dict) -> str:
    if lang_cfg.get("ext") == ".ps1":
        return PS_UTF8_PREAMBLE + code
    if lang_cfg.get("ext") == ".bat":
        return "@chcp 65001 > NUL\r\n@echo off\r\n" + code
    return code
```

---

## 4. 파일 변경 예정 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [claude-ai-chat-code.py](claude-ai-chat-code.py) | 수정 | `_should_print_banner()` 추가, `print_banner()` 호출을 if-가드 |
| [gemini-ai-chat-code.py](gemini-ai-chat-code.py) | 수정 | 동일 |
| [gen-ai-chat-code.py](gen-ai-chat-code.py) | 수정 | 동일 |
| [.env.example](.env.example) | 수정 | `PRINT_BANNER=true` 추가 |
| [src/terminal_executor.py](src/terminal_executor.py) | 수정 | `_build_child_env()`, `_compose_argv()`, `PS_INLINE_PREAMBLE` 신규. `execute()` 가 4-쉘 분기로 인터프리터 호출 |
| [src/code_executor.py](src/code_executor.py) | 수정 | `_NATIVE_LANGUAGES` 클래스 상수, `_shell_lang_config()` / `_build_supported_languages()` 정적 메서드. 모듈 레벨 `_build_shell_config` / `_BASE_LANGUAGES` / `_SHELL_LANG_KEYS` 제거. `_wrap_code_for_shell()` 가 `.bat` 헤더도 처리 |
| [tests/test_banner_toggle.py](tests/test_banner_toggle.py) | 신규 | T-110-01 ~ T-110-05 |
| [tests/test_terminal_executor_shell_dispatch.py](tests/test_terminal_executor_shell_dispatch.py) | 신규 | T-110-10 ~ T-110-19 |
| [tests/test_code_executor_shell_dispatch.py](tests/test_code_executor_shell_dispatch.py) | 신규 | T-110-20 ~ T-110-26 |
| [tests/test_terminal_executor.py](tests/test_terminal_executor.py) | 수정(최소) | 회귀 확인. `shell=True` 단일 호출을 가정한 mock 이 있다면 갱신 |
| [tests/test_code_executor.py](tests/test_code_executor.py) | 수정(최소) | 동일. `_BASE_LANGUAGES` import 가 있다면 클래스 상수 경로로 갱신 |

---

## 5. 요구사항 (Requirements)

### 5.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-110-01 | `PRINT_BANNER=false` (대소문자 무시) 일 때 세 엔트리 포인트는 배너를 출력하지 않는다 | 필수 |
| FR-110-02 | `PRINT_BANNER=true` / 미설정 / 빈 문자열일 때 배너를 출력한다 (기본 동작 유지) | 필수 |
| FR-110-03 | 알 수 없는 값(`PRINT_BANNER=maybe`) 은 `true` 로 간주한다 — 사용자가 의도하지 않은 차단 방지 | 필수 |
| FR-110-04 | `.env.example` 에 `PRINT_BANNER=true` 가 주석과 함께 명시된다 | 필수 |
| FR-110-05 | `TerminalExecutor.execute()` 는 Windows PowerShell 환경에서 `powershell.exe -Command ...` 형식으로 자식 프로세스를 생성한다 | 필수 |
| FR-110-06 | `TerminalExecutor.execute()` 는 Windows CMD 환경에서 `cmd.exe /c <cmd>` 형식으로 실행한다 | 필수 |
| FR-110-07 | `TerminalExecutor.execute()` 는 Linux/Mac 에서 `/bin/bash -c <cmd>` 형식으로 실행한다 | 필수 |
| FR-110-08 | `TerminalExecutor.execute()` 가 한글 파일명·한글 출력을 깨뜨리지 않는다 (모든 4-쉘) | 필수 |
| FR-110-09 | 위험 명령 검사는 인터프리터 전환 **이전** 단계에 적용 — `command` raw 의 첫 토큰 기준 (회귀 방지) | 필수 |
| FR-110-10 | `CodeExecutor.SUPPORTED_LANGUAGES` 는 4-쉘별로 적절한 쉘 인터프리터를 매핑한다 (PowerShell→`powershell.exe`, CMD→`cmd.exe`, Linux/Mac→`/bin/bash`) | 필수 |
| FR-110-11 | `CodeExecutor` 가 PowerShell 세션에서 `.bat` 가 아닌 `.ps1` 임시 파일을 생성한다 (§ 2.3 (a) 반전 버그 수정) | 필수 |
| FR-110-12 | `CodeExecutor` 가 CMD 세션에서 `.bat` 임시 파일에 `@chcp 65001 > NUL` 헤더를 삽입한다 | 필수 |
| FR-110-13 | `_NATIVE_LANGUAGES` (python, py, javascript, js) 는 모든 환경에서 동일하게 매핑된다 | 필수 |
| FR-110-14 | `TerminalExecutor` 의 자식 env 가 `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1` 을 포함한다 | 필수 |
| FR-110-15 | 사용자가 `LC_ALL` 을 미리 설정한 경우 그 값을 보존한다 (`setdefault`) | 필수 |
| FR-110-16 | 두 Executor 의 결과 dict 스키마(`success`, `stdout`, `stderr`, `returncode`, `command`/`language`, `icon`) 는 변경되지 않는다 | 필수 |

### 5.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-110-01 | 변경 후 기존 단위 테스트(`tests/test_code_executor.py`, `tests/test_terminal_executor.py`, `tests/test_code_executor_encoding.py`, `tests/test_os_utils_and_agent_prompt.py`) 가 수정 없이 모두 통과한다 — 단, mock 이 `shell=True` 단일 호출을 강하게 가정한 경우는 예외 (§ 7.1 회귀 점검) |
| NFR-110-02 | `_should_print_banner()` 는 import 사이드 이펙트가 없어야 한다 — `os.getenv` 단일 호출 |
| NFR-110-03 | TerminalExecutor 의 PowerShell 프리앰블은 `-Command` 인라인이므로 라인 번호 왜곡이 발생하지 않는다 |
| NFR-110-04 | `_build_child_env()` 는 두 Executor 가 의도적으로 중복 보유 — 향후 정책 분기 가능성 보존 |
| NFR-110-05 | `.bat` 파일은 BOM 없는 UTF-8 로 기록한다 (BOM 시 CMD 파싱 오류) |
| NFR-110-06 | `_shell_lang_config()` 는 `staticmethod` 로 정의되어 `CodeExecutor` 인스턴스 없이도 단위 테스트 가능 |
| NFR-110-07 | 인터프리터 호출 변경으로 인한 추가 프로세스 시작 오버헤드는 ≤ 50ms 이내 (Windows 기준) |
| NFR-110-08 | `PRINT_BANNER` 환경 변수는 `.env` 로드(`load_environment()`) 이후 평가되어야 한다 (호출 순서 의존) |

---

## 6. 테스트 시나리오

### 6.1 Section A — 배너 토글 (`tests/test_banner_toggle.py`)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-110-01 | `PRINT_BANNER=false` 후 `_should_print_banner()` | `False` |
| T-110-02 | `PRINT_BANNER=FALSE` (대문자) | `False` |
| T-110-03 | `PRINT_BANNER=0` / `no` / `off` | 모두 `False` |
| T-110-04 | `PRINT_BANNER=true` / `1` / `yes` / `on` / 미설정 / 빈 문자열 | 모두 `True` |
| T-110-05 | `PRINT_BANNER=maybe` (알 수 없는 값) | `True` (FR-110-03) |

### 6.2 Section B — TerminalExecutor 4-쉘 디스패치

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-110-10 | `get_shell_type='Windows PowerShell'` mocking 후 `execute('Get-ChildItem')` | argv[0] == `'powershell.exe'`, argv 에 `-Command` 포함, `shell=False` |
| T-110-11 | `get_shell_type='Windows CMD'` mocking 후 `execute('dir')` | command 문자열에 `cmd.exe /c "chcp 65001 > NUL & dir"`, `shell=True` |
| T-110-12 | `get_shell_type='Linux'` mocking 후 `execute('ls -la')` | argv == `['/bin/bash', '-c', 'ls -la']`, `shell=False` |
| T-110-13 | `get_shell_type='Mac'` mocking 후 `execute('ls -la')` | argv == `['/bin/bash', '-c', 'ls -la']`, `shell=False` |
| T-110-14 | 위험 명령 (`rm` / `del` / `Remove-Item`) 호출 → `allow_unsafe=False` | `success=False`, `error` 에 위험 명령 안내. 인터프리터 진입 전 차단 |
| T-110-15 | `allow_unsafe=True` 위험 명령 → 정상 실행 경로 | argv 가 인터프리터 형태로 합성됨 |
| T-110-16 | (Windows) `execute('echo 안녕하세요')` | stdout 에 `안녕하세요` 포함, 깨짐 없음 |
| T-110-17 | (모든 OS) `execute()` 호출 후 부모 `os.environ` 변경 없음 | 부모 오염 없음 |
| T-110-18 | `execute('')` (빈 문자열) | `success=False`, `error='명령어가 비어있습니다.'` (회귀 방지) |
| T-110-19 | 알 수 없는 명령 (`unknowncommand123`) | `success=False`, `returncode != 0` — 인터프리터가 에러 보고 |

### 6.3 Section C — CodeExecutor 4-쉘 매핑

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-110-20 | `_shell_lang_config('Windows PowerShell')['cmd']` | `'powershell.exe'` |
| T-110-21 | `_shell_lang_config('Windows CMD')['ext']` | `'.bat'` |
| T-110-22 | `_shell_lang_config('Linux')['cmd']` | `'/bin/bash'` |
| T-110-23 | `_shell_lang_config('Mac')['cmd']` | `'/bin/bash'` |
| T-110-24 | `_build_supported_languages('Windows PowerShell')` | `'python'`/`'py'`/`'javascript'`/`'js'` 매핑 + `'bash'`/`'sh'`/`'shell'`/`'powershell'`/`'ps1'` 모두 동일한 PowerShell config |
| T-110-25 | (Windows) `execute("Write-Host '한글🚀'", 'powershell')` | `success=True`, stdout 에 `한글🚀` (v1.0.102 회귀 방지) |
| T-110-26 | (Windows CMD 세션) `execute('echo 한글', 'bash')` | `.bat` 임시 파일 사용, 헤더에 `@chcp 65001`, stdout 에 한글 포함 |

### 6.4 회귀 테스트

- 기존 `tests/test_code_executor.py` (9건), `tests/test_code_executor_encoding.py` (T-102-01~11), `tests/test_terminal_executor.py` 전 케이스 통과
- `tests/test_os_utils_and_agent_prompt.py` 는 `get_os_shell_hint()` 4-쉘 분기를 검증 — 본 FSD 의 영향 없음

---

## 7. 실행 흐름 다이어그램

### 7.1 TerminalExecutor (수정 후)

```
TerminalExecutor.execute(command, allow_unsafe)
  │
  ├─ 빈 문자열 검사
  ├─ 위험 명령 검사 (raw command 의 첫 토큰)
  │
  ├─ shell_type = self.get_shell_type()
  │
  ├─ if shell_type == 'Windows PowerShell':
  │     argv = ['powershell.exe', '-NoProfile', '-NonInteractive',
  │             '-Command', PS_INLINE_PREAMBLE + command]
  │     shell_flag = False
  │
  ├─ elif shell_type == 'Windows CMD':
  │     argv = f'cmd.exe /c "chcp 65001 > NUL & {command}"'
  │     shell_flag = True
  │
  ├─ else:   # Linux | Mac
  │     argv = ['/bin/bash', '-c', command]
  │     shell_flag = False
  │
  ├─ env = self._build_child_env()
  │     ├─ PYTHONIOENCODING=utf-8
  │     ├─ PYTHONUTF8=1
  │     └─ LC_ALL/LANG setdefault C.UTF-8
  │
  └─ subprocess.run(argv, shell=shell_flag, ..., env=env, encoding='utf-8',
                    errors='replace')
```

### 7.2 CodeExecutor (수정 후)

```
__init__(workspace_dir, timeout)
  │
  ├─ self.shell_type = TerminalExecutor.get_shell_type()
  └─ self.SUPPORTED_LANGUAGES = self._build_supported_languages(self.shell_type)
        │
        ├─ _NATIVE_LANGUAGES 병합
        └─ _shell_lang_config(shell_type) 결과를 5개 키로 fan-out

execute(code, language)
  │
  ├─ language 검증 / lang_config 조회
  ├─ code_to_write = _wrap_code_for_shell(code, lang_config)
  │     ├─ .ps1 → PS_UTF8_PREAMBLE 삽입 (기존)
  │     └─ .bat → '@chcp 65001 > NUL\r\n@echo off\r\n' 삽입 (신규)
  │
  ├─ file_encoding = 'utf-8-sig' if .ps1 else 'utf-8'
  ├─ temp 파일 작성
  │
  ├─ env = self._build_child_env()  (기존)
  │
  ├─ subprocess.run([cmd, *args, temp_file], env=env, ...)
  │
  └─ finally: os.unlink(temp_file)
```

---

## 8. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | macOS 사용자가 zsh 함수·alias 에 의존하는 명령을 입력할 경우 `/bin/bash -c` 가 인식 못함 | 본 FSD 는 인터프리터 명시 — 사용자의 zsh 환경은 분리. macOS-zsh 분기는 v1.0.111 후속 작업 |
| 2 | Windows 7 이하 / Server Core 에서 `chcp 65001` 미지원 | 본 프로젝트의 지원 OS 는 Windows 10/11 — 범위 외 |
| 3 | `cmd.exe /c` 의 `&` 가 명령 분리 의미를 가지므로 사용자가 `&` 를 포함한 명령을 보낼 경우 헤더와 충돌 | `chcp 65001 > NUL & <cmd>` 를 큰따옴표로 묶어 단일 인자로 전달 — `cmd /c` 가 따옴표 외곽을 떼고 내부 전체를 한 명령으로 파싱 |
| 4 | PowerShell `-Command` 인라인은 따옴표 이스케이프가 까다로움 | 사용자 명령에 따옴표가 있을 경우 PS 문법대로 작성된 입력을 그대로 전달 — 본 FSD 는 별도 sanitization 미수행 |
| 5 | `_should_print_banner()` 가 `load_environment()` 이전에 호출되면 `.env` 값이 반영 안 됨 | 호출 순서 강제: `main()` 에서 `load_environment()` → `print_banner()` 가드 (NFR-110-08) |
| 6 | `CodeExecutor` 의 `.bat` 분기에서 한글 명령 자체는 여전히 깨질 수 있음 | CMD 의 본질적 한계. 출력 인코딩만 통일 — 입력은 사용자 책임 |
| 7 | 두 Executor 의 `_build_child_env()` 가 중복 정의됨 | 의도적 중복 (NFR-110-04). 향후 정책 분기 가능성을 위해 공유 모듈화 보류 |
| 8 | 본 FSD 는 PowerShell 5.x 기준. PowerShell 7(`pwsh`) 사용 시 `chcp 65001` 가 불필요 | 무해(중복 설정). `pwsh` 자동 감지는 v1.0.111 |

---

## 9. 후속 작업 (Optional / Phase 2)

| 단계 | 내용 | 비고 |
|---|---|---|
| 1 | PowerShell 7(`pwsh`) 자동 감지 → 우선 호출 | UTF-8 기본이라 프리앰블 단순화 가능 |
| 2 | macOS 의 zsh 분기 (`/bin/zsh -c`) | 사용자 .zshrc 활용. 호환성 영향 평가 필요 |
| 3 | `PRINT_BANNER` 외 `PRINT_VERSION_LINE`, `PRINT_DIR_LINE` 등 세분화 토글 | 로깅 환경에서 잡음 추가 제거 |
| 4 | `TerminalExecutor` 의 `-Command` 인라인을 임시 `.ps1` 파일 방식으로 전환 | 긴 명령·복합 따옴표 문제 해결 |
| 5 | `CodeExecutor._NATIVE_LANGUAGES` 에 Ruby/Go 추가 | 별도 FSD |

---

## 10. 승인

- [x] 설계 검토
- [x] [claude-ai-chat-code.py](claude-ai-chat-code.py) / [gemini-ai-chat-code.py](gemini-ai-chat-code.py) / [gen-ai-chat-code.py](gen-ai-chat-code.py) `_should_print_banner()` 가드 추가
- [x] [.env.example](.env.example) `PRINT_BANNER=true` 추가
- [x] [src/terminal_executor.py](src/terminal_executor.py) `_compose_argv()` / `_build_child_env()` / `PS_INLINE_PREAMBLE` 도입 및 `execute()` 4-쉘 분기 적용
- [x] [src/code_executor.py](src/code_executor.py) `_NATIVE_LANGUAGES` / `_shell_lang_config()` / `_build_supported_languages()` 정리 및 `_wrap_code_for_shell()` `.bat` 헤더 추가
- [x] [tests/test_banner_toggle.py](tests/test_banner_toggle.py) T-110-01 ~ T-110-05 작성·통과
- [x] [tests/test_terminal_executor_shell_dispatch.py](tests/test_terminal_executor_shell_dispatch.py) T-110-10 ~ T-110-19 작성·통과
- [x] [tests/test_code_executor_shell_dispatch.py](tests/test_code_executor_shell_dispatch.py) T-110-20 ~ T-110-26 작성·통과
- [x] 기존 테스트 회귀 확인 (NFR-110-01) — 83 passed, 1 skipped (CMD 환경 전용), 0 failed
- [ ] 세 엔트리 포인트에서 `PRINT_BANNER=false` 동작 수동 확인
- [ ] Windows PowerShell / CMD / Linux 환경에서 `/agents` 자율 루프 한글 명령·출력 깨짐 없음 확인
- [ ] [docs/specs/releases/RELEASE_v1.0.110_*.md](../releases/) 작성
