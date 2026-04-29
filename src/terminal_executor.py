"""
TerminalExecutor - 터미널 명령어 실행 모듈
"""

import os
import platform
import shlex
import subprocess
from pathlib import Path
from typing import Dict, Set


class TerminalExecutor:
    """터미널 명령어 실행 - 안전한 쉘 명령 실행 환경"""

    # PowerShell -Command 인라인용 UTF-8 강제 프리앰블 (CRLF 대신 ; 구분)
    PS_INLINE_PREAMBLE = (
        "$OutputEncoding = [Console]::OutputEncoding = "
        "[System.Text.Encoding]::UTF8; "
        "chcp 65001 > $null; "
    )

    # 환경별 위험 명령어 — shell! 에서만 실행 허용
    _DANGEROUS_WINDOWS_POWERSHELL: Set[str] = {
        # 파일/디렉토리 삭제
        'remove-item',
        # 파일 이동·복사 (덮어쓰기 위험)
        'move-item', 'rename-item', 'copy-item',
        # 파일 내용 쓰기
        'set-content', 'add-content', 'clear-content', 'new-item',
        # 권한 변경
        'set-acl',
        # 프로세스 종료
        'stop-process',
        # 시스템 제어
        'restart-computer', 'stop-computer',
        # 네트워크 / 다운로드
        'invoke-webrequest', 'invoke-restmethod',
        # 레지스트리 쓰기
        'set-itemproperty', 'remove-itemproperty',
        # 실행 정책 변경
        'set-executionpolicy',
        # 임의 코드 실행
        'invoke-expression', 'iex',
    }

    _DANGEROUS_WINDOWS_CMD: Set[str] = {
        # 파일 삭제
        'del', 'erase',
        # 디렉토리 삭제
        'rmdir', 'rd',
        # 파일 이동 (덮어쓰기 위험)
        'move',
        # 디스크 / 파티션
        'format', 'diskpart',
        # 레지스트리
        'reg',
        # 권한 변경
        'attrib', 'icacls',
        # 프로세스 종료
        'taskkill',
        # 시스템 종료
        'shutdown',
        # 네트워크 / 다운로드
        'curl', 'wget', 'ftp', 'telnet', 'ssh', 'scp',
    }

    _DANGEROUS_LINUX: Set[str] = {
        # 파일/디렉토리 삭제
        'rm',
        # 파일 이동·복사 (덮어쓰기 위험)
        'mv', 'cp',
        # 권한 변경
        'chmod', 'chown',
        # 프로세스 종료
        'kill', 'pkill',
        # 시스템 제어
        'shutdown', 'reboot',
        # 디스크 작업
        'fdisk', 'mkfs', 'dd',
        # 네트워크 / 다운로드
        'curl', 'wget', 'ssh', 'scp', 'ftp', 'telnet',
        # 권한 상승
        'sudo', 'su',
    }

    _DANGEROUS_MAC: Set[str] = {
        # 파일/디렉토리 삭제
        'rm',
        # 파일 이동·복사 (덮어쓰기 위험)
        'mv', 'cp',
        # 권한 변경
        'chmod', 'chown',
        # 프로세스 종료
        'kill', 'pkill',
        # 시스템 제어
        'shutdown', 'reboot',
        # 디스크 작업 (macOS)
        'diskutil',
        # 서비스 제어
        'launchctl',
        # 전원 관리
        'pmset',
        # 네트워크 / 다운로드
        'curl', 'wget', 'ssh', 'scp', 'ftp', 'telnet',
        # 권한 상승
        'sudo', 'su',
    }

    @staticmethod
    def get_shell_type() -> str:
        """현재 실행 중인 쉘 환경 감지

        Returns:
            "Windows PowerShell" | "Windows CMD" | "Linux" | "Mac"
        """
        system = platform.system()
        if system == 'Windows':
            # PSModulePath 는 PowerShell 세션에서 항상 설정됨
            if os.environ.get('PSModulePath'):
                return 'Windows PowerShell'
            return 'Windows CMD'
        if system == 'Darwin':
            return 'Mac'
        return 'Linux'

    def __init__(self, workspace_dir: Path, timeout: int = 120):
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

    def _build_child_env(self) -> Dict[str, str]:
        """자식 프로세스용 UTF-8 강제 환경 변수 세트 반환.

        부모 os.environ 은 복사본만 생성하여 변경하지 않는다.
        """
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env.setdefault("LC_ALL", "C.UTF-8")
        env.setdefault("LANG", "C.UTF-8")
        return env

    @staticmethod
    def _compose_argv(shell_type: str, command: str):
        """쉘 타입에 맞는 subprocess argv와 shell 플래그를 반환.

        Returns: (argv, shell_flag)
          - Windows PowerShell : (['powershell.exe', ...], False)
          - Windows CMD        : ('cmd.exe /c "..."',     True)
          - Linux / Mac        : (['/bin/bash', '-c', ..], False)
        """
        def _get_powershell_executable():
            
            if shutil.which("pwsh.exe"):
                return "pwsh.exe"
            return "powershell.exe"      
        if shell_type == 'Windows PowerShell':
            import shutil
            if shutil.which("pwsh.exe"):
                powershell_exe = "pwsh.exe"
            else:
                powershell_exe = "powershell.exe"
            return (
                [
                    powershell_exe, '-NoProfile', '-NonInteractive',
                    '-Command', TerminalExecutor.PS_INLINE_PREAMBLE + command,
                ],
                False,
            )
        if shell_type == 'Windows CMD':
            return (f'cmd.exe /c "chcp 65001 > NUL & {command}"', True)
        # Linux | Mac
        return (['/bin/bash', '-c', command], False)

    def execute(self, command: str, allow_unsafe: bool = False) -> Dict:
        """명령어 실행"""
        if not command.strip():
            return {'success': False, 'error': '명령어가 비어있습니다.'}

        try:
            if platform.system() == 'Windows':
                parts = command.split()
            else:
                parts = shlex.split(command)
        except ValueError as e:
            return {'success': False, 'error': f'명령어 파싱 오류: {e}'}

        base_cmd = parts[0].lower() if parts else ''

        if not allow_unsafe and base_cmd in self.DANGEROUS_COMMANDS:
            return {
                'success': False,
                'error': f'⚠️ 위험 명령어: {base_cmd}',
                'hint': '위험 명령을 실행하려면 /shell! 을 사용하세요.'
            }

        shell_type = self.get_shell_type()
        argv, shell_flag = self._compose_argv(shell_type, command)
        env = self._build_child_env()

        try:
            result = subprocess.run(
                argv,
                shell=shell_flag,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self.timeout,
                cwd=str(self.workspace_dir),
                env=env,
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode,
                'command': command
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': f'⏱️ 타임아웃: {self.timeout}초 초과',
                'command': command
            }
        except FileNotFoundError:
            return {
                'success': False,
                'error': f'❌ 명령어를 찾을 수 없음: {base_cmd}',
                'command': command
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'실행 오류: {e}',
                'command': command
            }

    def get_dangerous_commands(self) -> str:
        """현재 환경의 위험 명령어 목록 반환"""
        return ', '.join(sorted(self.DANGEROUS_COMMANDS))

    @staticmethod
    def shell_help() -> str:
        """현재 쉘 환경에 맞는 명령어 도움말 반환"""
        shell_type = TerminalExecutor.get_shell_type()
        lines = []

        if shell_type == 'Windows PowerShell':
            lines.append("=== Windows PowerShell 환경 — 주요 명령어 ===\n")
            lines.append("【파일/디렉토리】")
            lines.append("  /shell Get-ChildItem            현재 디렉토리 목록")
            lines.append("  /shell Get-Content <file>       파일 내용 출력")
            lines.append("  /shell Get-Item <path>          파일·폴더 속성")
            lines.append("  /shell Get-Location             현재 경로 (pwd)")
            lines.append("  /shell Test-Path <path>         경로 존재 여부 확인")
            lines.append("  /shell Select-String <pat> <f>  텍스트 검색 (grep)")
            lines.append("  /shell mkdir <name>             디렉토리 생성")
            lines.append("  /shell! Remove-Item <path>      파일/폴더 삭제 (위험 모드)")
            lines.append("  /shell! Move-Item <src> <dst>   파일 이동 (위험 모드)")
            lines.append("  /shell! Copy-Item <src> <dst>   파일 복사 (위험 모드)")
            lines.append("  /shell! New-Item -Path <f>      파일 생성 (위험 모드)")
            lines.append("")
            lines.append("【시스템 정보】")
            lines.append("  /shell whoami                   현재 사용자")
            lines.append("  /shell hostname                 컴퓨터 이름")
            lines.append("  /shell Get-Date                 현재 날짜·시간")
            lines.append("  /shell Get-Process              실행 중인 프로세스")
            lines.append("  /shell Get-ComputerInfo         시스템 상세 정보")
            lines.append("  /shell Get-PSDrive              드라이브 목록")
            lines.append("")
            lines.append("【Python / 패키지】")
            lines.append("  /shell python --version         Python 버전 확인")
            lines.append("  /shell pip list                 설치된 패키지 목록")
            lines.append("  /shell pip install <pkg>        패키지 설치")
            lines.append("")
            lines.append("【Git】")
            lines.append("  /shell git status               변경 파일 확인")
            lines.append("  /shell git log --oneline -10    최근 10개 커밋")
            lines.append("  /shell git diff                 변경 내용 확인")
            lines.append("")
            lines.append("【네트워크 (위험 모드)】")
            lines.append("  /shell! Invoke-WebRequest <url>  HTTP 요청")
            lines.append("  /shell! Invoke-RestMethod <url>  REST API 요청")

        elif shell_type == 'Windows CMD':
            lines.append("=== Windows CMD 환경 — 주요 명령어 ===\n")
            lines.append("【파일/디렉토리】")
            lines.append("  /shell dir                      현재 디렉토리 목록")
            lines.append("  /shell type <file>              파일 내용 출력")
            lines.append("  /shell where <cmd>              명령어 경로 확인")
            lines.append("  /shell find /i \"text\" <file>    텍스트 검색")
            lines.append("  /shell mkdir <name>             디렉토리 생성")
            lines.append("  /shell echo <text>              텍스트 출력")
            lines.append("  /shell! del <file>              파일 삭제 (위험 모드)")
            lines.append("  /shell! move <src> <dst>        파일 이동 (위험 모드)")
            lines.append("  /shell! rmdir /s <dir>          폴더 삭제 (위험 모드)")
            lines.append("")
            lines.append("【시스템 정보】")
            lines.append("  /shell whoami                   현재 사용자")
            lines.append("  /shell hostname                 컴퓨터 이름")
            lines.append("  /shell date /t                  현재 날짜")
            lines.append("  /shell time /t                  현재 시간")
            lines.append("  /shell set                      환경변수 목록")
            lines.append("  /shell tasklist                 실행 중인 프로세스")
            lines.append("")
            lines.append("【Python / 패키지】")
            lines.append("  /shell python --version         Python 버전 확인")
            lines.append("  /shell pip list                 설치된 패키지 목록")
            lines.append("  /shell pip install <pkg>        패키지 설치")
            lines.append("")
            lines.append("【Git】")
            lines.append("  /shell git status               변경 파일 확인")
            lines.append("  /shell git log --oneline -10    최근 10개 커밋")
            lines.append("  /shell git diff                 변경 내용 확인")
            lines.append("")
            lines.append("【네트워크 (위험 모드)】")
            lines.append("  /shell! curl <url>              HTTP 요청")
            lines.append("  /shell! ftp <host>              FTP 연결")

        elif shell_type == 'Mac':
            lines.append("=== macOS 환경 — Bash/Zsh 주요 명령어 ===\n")
            lines.append("【파일/디렉토리】")
            lines.append("  /shell ls -la                   파일 목록 (상세)")
            lines.append("  /shell cat <file>               파일 내용 출력")
            lines.append("  /shell head -20 <file>          파일 앞 20줄 출력")
            lines.append("  /shell tail -20 <file>          파일 끝 20줄 출력")
            lines.append("  /shell find . -name '*.py'      파일 검색")
            lines.append("  /shell grep -r 'text' src/      내용 검색")
            lines.append("  /shell mkdir -p <name>          디렉토리 생성")
            lines.append("  /shell! rm <file>               파일 삭제 (위험 모드)")
            lines.append("  /shell! mv <src> <dst>          파일 이동 (위험 모드)")
            lines.append("  /shell! cp <src> <dst>          파일 복사 (위험 모드)")
            lines.append("")
            lines.append("【시스템 정보】")
            lines.append("  /shell whoami                   현재 사용자")
            lines.append("  /shell date                     현재 날짜·시간")
            lines.append("  /shell env                      환경변수 목록")
            lines.append("  /shell ps aux                   실행 중인 프로세스")
            lines.append("  /shell sw_vers                  macOS 버전 확인")
            lines.append("  /shell df -h                    디스크 사용량")
            lines.append("")
            lines.append("【Python / 패키지】")
            lines.append("  /shell python3 --version        Python 버전 확인")
            lines.append("  /shell pip3 list                설치된 패키지 목록")
            lines.append("  /shell pip3 install <pkg>       패키지 설치")
            lines.append("")
            lines.append("【Git】")
            lines.append("  /shell git status               변경 파일 확인")
            lines.append("  /shell git log --oneline -10    최근 10개 커밋")
            lines.append("  /shell git diff                 변경 내용 확인")
            lines.append("")
            lines.append("【네트워크 (위험 모드)】")
            lines.append("  /shell! curl <url>              HTTP 요청")
            lines.append("  /shell! ssh user@host           원격 접속")
            lines.append("  /shell! scp <src> user@host:<d> 파일 원격 복사")

        else:  # Linux
            lines.append("=== Linux 환경 — Bash 주요 명령어 ===\n")
            lines.append("【파일/디렉토리】")
            lines.append("  /shell ls -la                   파일 목록 (상세)")
            lines.append("  /shell cat <file>               파일 내용 출력")
            lines.append("  /shell head -20 <file>          파일 앞 20줄 출력")
            lines.append("  /shell tail -20 <file>          파일 끝 20줄 출력")
            lines.append("  /shell find . -name '*.py'      파일 검색")
            lines.append("  /shell grep -r 'text' src/      내용 검색")
            lines.append("  /shell mkdir -p <name>          디렉토리 생성")
            lines.append("  /shell! rm <file>               파일 삭제 (위험 모드)")
            lines.append("  /shell! mv <src> <dst>          파일 이동 (위험 모드)")
            lines.append("  /shell! cp <src> <dst>          파일 복사 (위험 모드)")
            lines.append("")
            lines.append("【시스템 정보】")
            lines.append("  /shell whoami                   현재 사용자")
            lines.append("  /shell date                     현재 날짜·시간")
            lines.append("  /shell env                      환경변수 목록")
            lines.append("  /shell ps aux                   실행 중인 프로세스")
            lines.append("  /shell uname -a                 커널 정보")
            lines.append("  /shell df -h                    디스크 사용량")
            lines.append("")
            lines.append("【Python / 패키지】")
            lines.append("  /shell python3 --version        Python 버전 확인")
            lines.append("  /shell pip3 list                설치된 패키지 목록")
            lines.append("  /shell pip3 install <pkg>       패키지 설치")
            lines.append("")
            lines.append("【Git】")
            lines.append("  /shell git status               변경 파일 확인")
            lines.append("  /shell git log --oneline -10    최근 10개 커밋")
            lines.append("  /shell git diff                 변경 내용 확인")
            lines.append("")
            lines.append("【네트워크 (위험 모드)】")
            lines.append("  /shell! curl <url>              HTTP 요청")
            lines.append("  /shell! wget <url>              파일 다운로드")
            lines.append("  /shell! ssh user@host           원격 접속")

        lines.append("")
        dangerous_cmds = TerminalExecutor._get_dangerous_for_shell(shell_type)
        lines.append("【위험 명령어 (안전 모드에서 차단)】")
        lines.append(f"  {', '.join(sorted(dangerous_cmds))}")
        lines.append("")
        lines.append("⚠️  /shell! 은 위험 명령어를 허용합니다. 실행 전 확인 프롬프트가 표시됩니다.")
        return "\n".join(lines)

    @staticmethod
    def agent_shell_brief() -> str:
        """에이전트 시스템 프롬프트 삽입용 현 쉘 환경 요약.

        `shell_help()` 의 `/shell <cmd>` 포맷 대신 에이전트가 실제 생성하는
        `$ <cmd>` 포맷으로 안전 명령 예시 9개와 위험 명령 목록을 제공한다.
        """
        shell_type = TerminalExecutor.get_shell_type()
        dangerous = sorted(TerminalExecutor._get_dangerous_for_shell(shell_type))

        if shell_type == 'Windows PowerShell':
            safe_examples = [
                "$ Get-ChildItem                 # 파일 목록",
                "$ Get-Content <file>            # 파일 내용",
                "$ Get-Location                  # 현재 경로",
                "$ Test-Path <path>              # 경로 존재 여부",
                "$ Select-String <pat> <file>    # 텍스트 검색",
                "$ python --version",
                "$ pip list",
                "$ git status",
                "$ git log --oneline -10",
            ]
        elif shell_type == 'Windows CMD':
            safe_examples = [
                "$ dir                           # 파일 목록",
                "$ type <file>                   # 파일 내용",
                "$ where <cmd>                   # 명령어 경로",
                '$ find /i "text" <file>         # 텍스트 검색',
                "$ python --version",
                "$ pip list",
                "$ git status",
                "$ git log --oneline -10",
                "$ tasklist",
            ]
        elif shell_type == 'Mac':
            safe_examples = [
                "$ ls -la",
                "$ cat <file>",
                "$ grep -r 'pat' src/",
                "$ find . -name '*.py'",
                "$ python3 --version",
                "$ pip3 list",
                "$ git status",
                "$ git log --oneline -10",
                "$ sw_vers",
            ]
        else:  # Linux
            safe_examples = [
                "$ ls -la",
                "$ cat <file>",
                "$ grep -r 'pat' src/",
                "$ find . -name '*.py'",
                "$ python3 --version",
                "$ pip3 list",
                "$ git status",
                "$ git log --oneline -10",
                "$ uname -a",
            ]

        lines = [
            f"[쉘 환경 요약 — 현재 쉘: {shell_type}]",
            "",
            "안전 명령 예시 (선택지 C — `$ <cmd>` 형식):",
            *[f"  {ex}" for ex in safe_examples],
            "",
            "위험 명령 (실행 전 승인 프롬프트 표시 · 코드 블록 안에서도 동일 적용):",
            f"  {', '.join(dangerous)}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _get_dangerous_for_shell(shell_type: str) -> Set[str]:
        if shell_type == 'Windows PowerShell':
            return TerminalExecutor._DANGEROUS_WINDOWS_POWERSHELL
        if shell_type == 'Windows CMD':
            return TerminalExecutor._DANGEROUS_WINDOWS_CMD
        if shell_type == 'Mac':
            return TerminalExecutor._DANGEROUS_MAC
        return TerminalExecutor._DANGEROUS_LINUX
