"""
os_utils - 플랫폼별 유틸리티 함수 (FSD v1.0.088 / v1.0.107)
"""


def get_os_shell_hint() -> str:
    """현재 OS/쉘 타입을 기반으로 쉘 구문 힌트를 반환.

    `TerminalExecutor.get_shell_type()` 로 4쉘 분기 (Windows PowerShell /
    Windows CMD / Linux / Mac). 순환 import 방지를 위해 함수 내부 import.
    """
    from .terminal_executor import TerminalExecutor

    shell_type = TerminalExecutor.get_shell_type()
    if shell_type == 'Windows PowerShell':
        return (
            "OS          : Windows\n"
            "쉘 타입     : Windows PowerShell\n"
            "파일 인코딩 : UTF-8\n"
            "쉘 명령은 PowerShell 구문을 사용하세요. "
            "`bash`/`sh` 구문은 이 환경에서 실행되지 않습니다."
        )
    if shell_type == 'Windows CMD':
        return (
            "OS          : Windows\n"
            "쉘 타입     : Windows CMD\n"
            "파일 인코딩 : UTF-8\n"
            "쉘 명령은 CMD 구문을 사용하세요. "
            "`bash`/`sh` 구문은 이 환경에서 실행되지 않습니다."
        )
    if shell_type == 'Mac':
        return (
            "OS          : macOS\n"
            "쉘 타입     : Bash/Zsh\n"
            "파일 인코딩 : UTF-8\n"
            "쉘 명령은 bash/zsh 구문을 사용하세요."
        )
    return (
        "OS          : Linux\n"
        "쉘 타입     : Bash\n"
        "파일 인코딩 : UTF-8\n"
        "쉘 명령은 bash 구문을 사용하세요."
    )
