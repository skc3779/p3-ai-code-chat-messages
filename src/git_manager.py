"""
GitManager - Git 작업 관리 모듈
"""

import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Union


class GitManager:
    """Git 명령어 실행 및 상태 관리"""
    
    def __init__(self, workspace_dir: Union[str, Path]):
        self.workspace_dir = Path(workspace_dir).resolve()
    
    def _run_git(self, args: List[str]) -> Dict[str, str]:
        """Git 명령어 실행"""
        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                encoding='utf-8' # Windows 한글 처리
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()
            }
        except FileNotFoundError:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Git이 설치되어 있지 않거나 PATH에 없습니다."
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }

    def status(self) -> str:
        """git status 실행"""
        result = self._run_git(['status'])
        if result['success']:
            return result['stdout']
        return f"Git 상태 확인 실패: {result['stderr']}"

    def diff(self, cached: bool = False) -> str:
        """git diff 실행"""
        args = ['diff']
        if cached:
            args.append('--cached')
        
        result = self._run_git(args)
        if result['success']:
            return result['stdout'] or "(변경 사항 없음)"
        return f"Git Diff 확인 실패: {result['stderr']}"

    def log(self, max_count: int = 5) -> str:
        """git log 실행"""
        result = self._run_git(['log', f'-n {max_count}', '--oneline'])
        if result['success']:
            return result['stdout']
        return f"Git 로그 확인 실패: {result['stderr']}"

    def add(self, files: List[str]) -> str:
        """git add 실행"""
        if not files:
            return "추가할 파일이 지정되지 않았습니다."
        
        result = self._run_git(['add'] + files)
        if result['success']:
            return f"파일 추가 성공: {', '.join(files)}"
        return f"파일 추가 실패: {result['stderr']}"

    def commit(self, message: str) -> str:
        """git commit 실행"""
        result = self._run_git(['commit', '-m', message])
        if result['success']:
            return f"커밋 성공: {result['stdout']}"
        return f"커밋 실패: {result['stderr']}"
