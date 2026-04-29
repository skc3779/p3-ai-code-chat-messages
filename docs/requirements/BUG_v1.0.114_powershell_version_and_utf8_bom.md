# BUG v1.0.114: PowerShell 버전 차이 및 UTF-8 BOM 의존성 문제 분석

## 1. 개요
*   **이슈명**: 사용자는 최신 `PowerShell 7.6.1`을 사용 중임에도 `/shell Get-Content README.md` 실행 시 텍스트가 깨지는 구버전(Windows PowerShell 5.1)의 버그가 발생함.
*   **관련 문서**: `BUG_v1.0.113_terminal_executor_powershell_getcontent_garbled.md`
*   **사용자 확인 사항**: `/shell Get-Content -Encoding UTF8 -Path README.md` 실행 시 한글이 깨지지 않고 정상 출력됨을 확인.

## 2. 왜 PowerShell 7.6.1을 쓰는데 구버전 버그가 발생하는가?

사용자님께서 최신 `pwsh`(버전 7.6.1) 터미널 창에서 파이썬 스크립트를 실행하셨더라도, 쉘 명령어를 처리하는 **`TerminalExecutor`의 내부 구현이 `powershell.exe`(Windows PowerShell 5.1)를 강제로 호출하도록 하드코딩**되어 있기 때문입니다.

`src/terminal_executor.py`의 `_compose_argv` 메소드를 보면 다음과 같이 구현되어 있습니다.
```python
if shell_type == 'Windows PowerShell':
    return (
        [
            'powershell.exe', '-NoProfile', '-NonInteractive',
            '-Command', TerminalExecutor.PS_INLINE_PREAMBLE + command,
        ],
        False,
    )
```
이로 인해 겉으로는 PowerShell 7 환경에 있어도, `/shell` 명령어가 실행될 때는 항상 백그라운드에서 구버전인 `powershell.exe` 프로세스가 생성되어 실행되므로 5.1 버전의 고질적인 인코딩 버그가 재현된 것입니다. 사용자가 직접 추가하신 `-Encoding UTF8` 옵션이 잘 동작한 이유도 백그라운드에서 실행된 대상이 5.1 버전의 `powershell.exe`였기 때문입니다.

## 3. UTF-8과 BOM(Byte Order Mark)의 관계

이 문제가 Windows 환경에서만 유독 빈번하게 발생하는 이유는 **UTF-8과 BOM(Byte Order Mark)에 대한 처리 방식이 과거와 현재(그리고 OS 간) 다르기 때문**입니다.

### BOM(Byte Order Mark)이란?
*   원래 BOM은 텍스트 파일의 맨 앞에 2~3바이트의 특수 마커(`EF BB BF` 등)를 넣어, 이 파일이 "어떤 방식으로 인코딩(엔디안 등)되었는지"를 프로그램에게 알려주는 일종의 서명(Signature)입니다.
*   **UTF-8의 특성**: UTF-8은 1바이트 단위로 처리되므로 엔디안(Endian) 문제가 발생하지 않아 **원칙적으로 BOM이 필요 없는 인코딩 방식**입니다. Linux, Mac, 웹 표준, 그리고 최신 개발 도구(VS Code 등)는 모두 "BOM 없는 UTF-8(UTF-8 without BOM)"을 기본으로 사용합니다.

### Windows PowerShell 5.1의 오해
*   Windows는 과거 오랫동안 자국의 기본 로캘(한국은 CP949/ANSI)을 시스템 기본 텍스트 인코딩으로 사용해 왔습니다.
*   구버전인 **PowerShell 5.1 (`powershell.exe`)**은 텍스트 파일을 읽을 때 파일 맨 앞에 **UTF-8 BOM이 존재해야만 해당 파일을 UTF-8로 인식**합니다.
*   만약 BOM이 없다면 (VS Code로 만든 일반적인 UTF-8 `README.md`처럼), PowerShell 5.1은 이 파일을 **시스템 기본값인 CP949로 간주**하고 읽어버립니다. 이때 바이트를 잘못 해석하여 글자가 깨지게 됩니다.

### PowerShell Core 6 이상 (`pwsh`)의 변화
*   **PowerShell 7.6.1 (`pwsh`)**은 현대적인 표준을 따라 **BOM이 없는 파일도 기본적으로 UTF-8로 인식**하도록 동작이 수정되었습니다.
*   따라서 PowerShell 7 터미널에서 직접 `Get-Content README.md`를 치면 깨지지 않지만, `TerminalExecutor`가 5.1을 호출했기 때문에 문제가 발생했던 것입니다.

## 4. 근본적인 해결 방안 (Action Plan)

현재 환경을 완벽하게 지원하기 위해 다음과 같은 단계별 해결 방안을 적용해야 합니다.

### 1단계: TerminalExecutor의 쉘 탐색 로직 개선 (권장)
현재 `os_utils.py` 또는 `TerminalExecutor`에서 `powershell.exe`만 하드코딩된 것을 개선하여, 시스템에 **최신 PowerShell Core(`pwsh.exe`)가 설치되어 있다면 이를 우선적으로 사용**하도록 변경해야 합니다.
```python
# 개선 예시
def _get_powershell_executable():
    import shutil
    if shutil.which("pwsh.exe"):
        return "pwsh.exe"
    return "powershell.exe"
```
이렇게 하면 PowerShell 7이 설치된 환경에서는 `/shell Get-Content README.md`를 인코딩 옵션 없이도 한글 깨짐 없이 곧바로 사용할 수 있게 됩니다.

### 2단계: Fallback 대비 (Windows PowerShell 5.1 환경)
`pwsh`가 설치되지 않은 순정 Windows 10/11 사용자(`powershell.exe`만 있는 경우)를 위해, AI 에이전트 시스템 프롬프트(FSD v1.0.110 등)에 다음 규칙을 명시해야 합니다.
> "Windows PowerShell(powershell.exe)을 사용하여 파일을 다룰 때는, 한글 깨짐 방지를 위해 가급적 `-Encoding UTF8` 파라미터를 추가하여 명령어(예: `Get-Content -Encoding UTF8 README.md`)를 실행할 것."

결론적으로 사용자님께서 직접 검증하신 `-Encoding UTF8` 옵션 추가가 구버전 PowerShell 엔진을 달래는 정확하고 유일한 회피책이 맞으며, 이 과정을 아예 생략하려면 `TerminalExecutor`가 `pwsh`를 호출하도록 코드를 개선하는 것이 가장 이상적인 해결책입니다.
