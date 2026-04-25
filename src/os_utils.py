"""
os_utils - 플랫폼별 유틸리티 함수 (FSD v1.0.088)
"""
import platform


def get_os_shell_hint() -> str:
    """현재 OS 에 맞는 쉘 구문 힌트 문자열을 반환한다."""
    if platform.system() == 'Windows':
        return (
            "현재 실행 환경: Windows OS.\n"
            "쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 "
            "코드 블록 언어 태그를 `powershell` 또는 `ps1`로 지정하세요. "
            "`bash`, `sh` 코드 블록은 이 환경에서 실행되지 않습니다."
        )
    return (
        f"현재 실행 환경: {platform.system()} OS.\n"
        "쉘 스크립트 작성 시 bash 구문을 사용하고 "
        "코드 블록 언어 태그를 `bash` 또는 `sh`로 지정하세요."
    )

