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
        'ls', 'dir', 'cat', 'type', 'head', 'tail', 'find', 'grep',
        # 파일 시스템 (쓰기)
        'mkdir', 'touch', 'echo',
        # 기타 유틸리티
        'pwd', 'which', 'where', 'env', 'set',
        # Git
        'git',
        # 빌드 도구
        'make', 'cmake', 'gradle', 'mvn',
    ]
    
    # 위험 명령어 (shell! 에서만 허용)
    DANGEROUS_COMMANDS = [
        'rm', 'del', 'rmdir', 'rd',
        'mv', 'move', 'cp', 'copy', 'xcopy',
        'chmod', 'chown',
        'kill', 'taskkill',
        'shutdown', 'reboot',
        'format', 'fdisk',
        'curl', 'wget',  # 네트워크 요청
        'ssh', 'scp',
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
