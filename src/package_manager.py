"""
PackageManager - 패키지 의존성 관리 모듈
"""

import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Union


class PackageManager:
    """패키지 설치 상태 확인 및 의존성 분석"""
    
    def __init__(self, workspace_dir: Union[str, Path]):
        self.workspace_dir = Path(workspace_dir).resolve()
    
    def _run_command(self, args: List[str]) -> Dict[str, str]:
        """명령어 실행"""
        try:
            # shell=True는 보안상 권장되지 않으나, npm 등의 실행을 위해 PATH 환경변수가 필요할 수 있음
            # 여기서는 list 형태이므로 shell=False (기본값) 사용
            # Windows에서 .cmd .bat 등의 실행을 위해 shell=True가 필요할 수도 있으나,
            # subprocess.run은 실행 파일을 찾을 때 확장자까지 정확해야 할 수 있음.
            # 'pip', 'npm'은 보통 PATH에 있는 실행파일.
            
            # Windows에서 'npm'은 'npm.cmd'일 수 있음. shutil.which로 찾는 것이 안전하나,
            # 우선 간단히 try-except 구조로 처리.
            
            shell_option = False
            import platform
            if platform.system() == "Windows":
                 # Windows에서는 shell=True를 써야 PATH의 .cmd 등을 잘 찾음 (특히 npm)
                 shell_option = True
            
            result = subprocess.run(
                args,
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                encoding='utf-8',
                shell=shell_option
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
                "stderr": f"명령어를 찾을 수 없습니다: {args[0]}"
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }

    def list_packages(self, language: str) -> str:
        """설치된 패키지 목록 조회"""
        if language.lower() == "python":
            # pip list --format=json
            result = self._run_command(['pip', 'list', '--format=json'])
            if result['success']:
                try:
                    packages = json.loads(result['stdout'])
                    # 가독성 좋게 포맷팅
                    return "\n".join([f"{p['name']}=={p['version']}" for p in packages])
                except json.JSONDecodeError:
                    return result['stdout'] # JSON 파싱 실패 시 원본 반환
            return f"Python 패키지 조회 실패: {result['stderr']}"

        elif language.lower() in ["node", "javascript", "npm"]:
            # npm list --depth=0 --json
            result = self._run_command(['npm', 'list', '--depth=0', '--json'])
            if result['success']:
                try:
                    data = json.loads(result['stdout'])
                    dependencies = data.get('dependencies', {})
                    if not dependencies:
                        return "(설치된 npm 패키지가 없거나 package.json이 없습니다)"
                    
                    output = []
                    for name, info in dependencies.items():
                        version = info.get('version', 'unknown')
                        output.append(f"{name}@{version}")
                    return "\n".join(output)
                except json.JSONDecodeError:
                    return result['stdout']
            
            # npm list는 의존성 문제 등이 있어도 exit code가 0이 아닐 수 있음 (stderr 참조)
            # 하지만 목록은 stdout에 나올 수 있음.
            return f"Node.js 패키지 조회 실패: {result['stderr'] or result['stdout']}"

        else:
            return f"지원하지 않는 언어입니다: {language}"
