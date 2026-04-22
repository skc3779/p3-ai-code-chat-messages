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

    # 허용된 기본 명령어 (안전 모드, 크로스플랫폼)
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
        'pwd', 'cd',  # cd는 subprocess에서 의미 없지만 허용 목록에 포함
        'whoami', 'date', 'time', 'hostname',
        'where', 'which', 'env', 'set',
        # Git
        'git',
        # 빌드 도구
        'make', 'cmake', 'gradle', 'mvn',
    ]

    # Windows PowerShell 전용 허용 Cmdlet (읽기/조회 안전 명령어)
    # 모두 소문자 기준 — execute() 에서 base_cmd.lower() 로 비교
    ALLOWED_POWERSHELL_CMDLETS = [
        # ── 파일 시스템 조회 ──────────────────────────────────
        'get-childitem',      # ls / dir 대응 (파일·폴더 목록)
        'get-content',        # cat / type 대응 (파일 내용 출력)
        'get-item',           # 단일 파일·폴더 속성 조회
        'get-location',       # pwd 대응 (현재 디렉토리)
        'resolve-path',       # 절대 경로 확인
        'split-path',         # 경로 분해 (부모/리프)
        'join-path',          # 경로 결합
        'test-path',          # 경로 존재 여부 확인 (읽기 전용)
        # ── 텍스트 검색 / 처리 ───────────────────────────────
        'select-string',      # grep 대응 (정규식 포함 텍스트 검색)
        'measure-object',     # 줄 수·문자 수 등 측정
        'select-object',      # 컬럼 선택·슬라이싱
        'where-object',       # 파이프라인 필터
        'sort-object',        # 정렬
        'group-object',       # 그룹화
        'compare-object',     # 두 컬렉션 비교
        # ── 시스템 정보 조회 ─────────────────────────────────
        'get-date',           # 현재 날짜·시간
        'get-process',        # ps 대응 (실행 중 프로세스 목록)
        'get-host',           # PowerShell 호스트 정보
        'get-computerinfo',   # 시스템·OS 상세 정보
        'get-variable',       # 변수 목록·값 조회
        'get-psdrive',        # 드라이브 목록
        # ── 환경 변수 ────────────────────────────────────────
        'get-itemproperty',   # 레지스트리 읽기 / 파일 속성 조회
        # ── 출력 포맷 ────────────────────────────────────────
        'write-output',       # echo 대응 (파이프라인 출력)
        'write-host',         # 콘솔 직접 출력 (색상 지원)
        'format-list',        # 리스트 형식 출력
        'format-table',       # 테이블 형식 출력
        'out-string',         # 객체를 문자열로 변환
        'out-default',        # 기본 출력
        # ── 기타 유틸 ────────────────────────────────────────
        'get-alias',          # 별칭(alias) 목록
        'get-command',        # 명령어 존재 여부·위치 확인 (which 대응)
        'get-help',           # 도움말 조회
        'get-module',         # 로드된 모듈 목록
        'get-executionpolicy', # 실행 정책 조회 (읽기 전용)
    ]

    # 위험 명령어 (shell! 에서만 허용)
    DANGEROUS_COMMANDS = [
        # 파일/디렉토리 삭제
        'rm', 'del', 'erase', 'rmdir', 'rd',
        'remove-item',        # PowerShell rm 대응
        # 파일 이동/복사 (덮어쓰기 위험)
        'mv', 'move', 'cp', 'copy', 'xcopy', 'robocopy',
        'move-item', 'copy-item',   # PowerShell 대응
        'rename-item',        # 파일 이름 변경
        # 파일 내용 변경
        'set-content', 'add-content', 'clear-content',  # PowerShell 쓰기
        'new-item',           # 파일·폴더 신규 생성 (쓰기 의미)
        # 권한 변경
        'chmod', 'chown', 'attrib', 'icacls',
        'set-acl',            # PowerShell 권한 변경
        # 프로세스 종료
        'kill', 'taskkill', 'pkill',
        'stop-process',       # PowerShell 프로세스 종료
        # 시스템 제어
        'shutdown', 'reboot', 'restart-computer', 'stop-computer',
        # 디스크 작업
        'format', 'fdisk', 'diskpart',
        # 네트워크 (다운로드 등)
        'curl', 'wget', 'ssh', 'scp', 'ftp', 'telnet',
        'invoke-webrequest', 'invoke-restmethod',  # PowerShell HTTP
        # 레지스트리 (Windows)
        'reg',
        'set-itemproperty', 'remove-itemproperty',  # PowerShell 레지스트리 쓰기
        # 실행 정책 변경 (보안)
        'set-executionpolicy',
        # 표현식 임의 실행 (보안)
        'invoke-expression', 'iex',
    ]
    
    def __init__(self, workspace_dir: Path, timeout: int = 60):
        self.workspace_dir = workspace_dir
        self.timeout = timeout
        # Windows 환경에서 PowerShell Cmdlet을 동적으로 허용 목록에 추가
        self._effective_allowed: list = list(self.ALLOWED_COMMANDS)
        if platform.system() == 'Windows':
            self._effective_allowed += self.ALLOWED_POWERSHELL_CMDLETS
    
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

            if base_cmd not in self._effective_allowed:
                hint_cmds = sorted(set(self._effective_allowed))[:10]
                return {
                    'success': False,
                    'error': f'허용되지 않은 명령어: {base_cmd}',
                    'hint': f'허용 명령어: {", ".join(hint_cmds)}...',
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
        """허용된 명령어 목록 반환 (OS별 동적 목록 포함)"""
        return ", ".join(sorted(set(self._effective_allowed)))

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
        all_allowed = list(TerminalExecutor.ALLOWED_COMMANDS)
        if platform.system() == 'Windows':
            all_allowed += TerminalExecutor.ALLOWED_POWERSHELL_CMDLETS
        lines.append(f"  {', '.join(sorted(set(all_allowed)))}")
        lines.append("")
        lines.append("⚠️  /shell! 은 위험 명령어를 허용합니다. 실행 전 확인 프롬프트가 표시됩니다.")
        return "\n".join(lines)
