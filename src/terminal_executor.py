"""
TerminalExecutor - 터미널 명령어 실행 모듈
"""

import os
import platform
import shlex
import subprocess
from pathlib import Path
from typing import Dict


class TerminalExecutor:
    """터미널 명령어 실행 - 안전한 쉘 명령 실행 환경"""
    
    # 허용된 기본 명령어 (안전 모드)
    ALLOWED_COMMANDS = [
        # Python 관련
        'python', 'python3', 'pip', 'pip3', 'pipenv', 'poetry',
        # Node.js 관련
        'node', 'npm', 'npx', 'yarn',
        # 파일 시스템 (읽기)
        'ls', 'dir', 'cat', 'type', 'head', 'tail', 'find', 'grep', 'more',
        # 파일 시스템 (쓰기 - 제한적)
        'mkdir', 'touch', 'echo',
        # 기타 유틸리티
        'pwd', 'cd', # cd는 subprocess에서 의미 없지만 허용 목록에 포함
        'whoami', 'date', 'time', 'hostname',
        'where', 'which', 'env', 'set',
        # Git
        'git',
        # 빌드 도구
        'make', 'cmake', 'gradle', 'mvn',
    ]
    
    # 위험 명령어 (shell! 에서만 허용)
    DANGEROUS_COMMANDS = [
        # 파일/디렉토리 삭제
        'rm', 'del', 'erase', 'rmdir', 'rd',
        # 파일 이동/복사 (덮어쓰기 위험)
        'mv', 'move', 'cp', 'copy', 'xcopy', 'robocopy',
        # 권한 변경
        'chmod', 'chown', 'attrib', 'icacls',
        # 프로세스 종료
        'kill', 'taskkill', 'pkill',
        # 시스템 제어
        'shutdown', 'reboot', 'restart-computer', 'stop-computer',
        # 디스크 작업
        'format', 'fdisk', 'diskpart',
        # 네트워크 (다운로드 등)
        'curl', 'wget', 'ssh', 'scp', 'ftp', 'telnet',
        # 레지스트리 (Windows)
        'reg',
    ]
    
    def __init__(self, workspace_dir: Path, timeout: int = 60):
        self.workspace_dir = workspace_dir
        self.timeout = timeout
    
    def execute(self, command: str, allow_unsafe: bool = False) -> Dict:
        """명령어 실행"""
        if not command.strip():
            return {'success': False, 'error': '명령어가 비어있습니다.'}
        
        # 명령어 파싱
        try:
            if platform.system() == 'Windows':
                parts = command.split()
            else:
                parts = shlex.split(command)
        except ValueError as e:
            return {'success': False, 'error': f'명령어 파싱 오류: {e}'}
        
        base_cmd = parts[0].lower() if parts else ''
        
        # 명령어 검증
        if not allow_unsafe:
            if base_cmd in self.DANGEROUS_COMMANDS:
                return {
                    'success': False,
                    'error': f'⚠️ 위험 명령어: {base_cmd}',
                    'hint': '위험 명령을 실행하려면 /shell! 을 사용하세요.'
                }
            
            if base_cmd not in self.ALLOWED_COMMANDS:
                return {
                    'success': False,
                    'error': f'허용되지 않은 명령어: {base_cmd}',
                    'hint': f'허용 명령어: {", ".join(sorted(set(self.ALLOWED_COMMANDS[:10])))}...',
                    'use_unsafe': '모든 명령 허용: /shell!'
                }
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self.timeout,
                cwd=str(self.workspace_dir),
                env=os.environ.copy()
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
    
    def get_allowed_commands(self) -> str:
        """허용된 명령어 목록 반환"""
        return ", ".join(sorted(set(self.ALLOWED_COMMANDS)))

    @staticmethod
    def shell_help() -> str:
        """OS별 유용 명령어 도움말 반환"""
        is_windows = platform.system() == 'Windows'
        lines = []

        if is_windows:
            lines.append("=== Windows 환경 — PowerShell / CMD 주요 명령어 ===\n")
            lines.append("【파일/디렉토리】")
            lines.append("  /shell dir                      현재 디렉토리 파일 목록 (CMD)")
            lines.append("  /shell Get-ChildItem            현재 디렉토리 파일 목록 (PowerShell)")
            lines.append("  /shell type <file>              파일 내용 출력 (CMD)")
            lines.append("  /shell Get-Content <file>       파일 내용 출력 (PowerShell)")
            lines.append("  /shell mkdir <name>             디렉토리 생성")
            lines.append("  /shell! move <src> <dst>        파일 이동 (위험 모드)")
            lines.append("  /shell! del <file>              파일 삭제 (위험 모드)")
            lines.append("")
            lines.append("【시스템 정보】")
            lines.append("  /shell whoami                   현재 사용자")
            lines.append("  /shell hostname                 컴퓨터 이름")
            lines.append("  /shell date /t                  현재 날짜 (CMD)")
            lines.append("  /shell Get-Date                 현재 날짜·시간 (PowerShell)")
            lines.append("  /shell set                      환경변수 목록 (CMD)")
            lines.append("  /shell Get-Process              실행 중인 프로세스 (PowerShell)")
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
            lines.append("  /shell! wget <url>              파일 다운로드")
        else:
            lines.append("=== Linux / macOS 환경 — Bash 주요 명령어 ===\n")
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
            lines.append("")
            lines.append("【시스템 정보】")
            lines.append("  /shell whoami                   현재 사용자")
            lines.append("  /shell date                     현재 날짜·시간")
            lines.append("  /shell env                      환경변수 목록")
            lines.append("  /shell ps aux                   실행 중인 프로세스")
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
        lines.append("【허용 명령어 (안전 모드)】")
        lines.append(f"  {', '.join(sorted(set(TerminalExecutor.ALLOWED_COMMANDS)))}")
        lines.append("")
        lines.append("⚠️  /shell! 은 위험 명령어를 허용합니다. 실행 전 확인 프롬프트가 표시됩니다.")
        return "\n".join(lines)
