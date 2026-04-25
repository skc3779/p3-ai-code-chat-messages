"""
CodeExecutor - 코드 실행 환경 모듈
"""

import os
import platform
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict


def _build_shell_config() -> dict:
    """OS에 따라 쉘 실행 설정을 반환"""
    if platform.system() == 'Windows':
        if os.environ.get('PSModulePath'):
            return {
                'cmd': 'cmd',
                'args': [],
                'ext': '.bat',
                'icon': '🪟',
            }
        return {
            'cmd': 'powershell',
            'args': ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File'],
            'ext': '.ps1',
            'icon': '🪟',
        }
    return {
        'cmd': '/bin/bash',
        'args': [],
        'ext': '.sh',
        'icon': '🖥️',
    }

_BASE_LANGUAGES = {
    'python':     {'cmd': 'python', 'args': [], 'ext': '.py',  'icon': '🐍'},
    'py':         {'cmd': 'python', 'args': [], 'ext': '.py',  'icon': '🐍'},
    'javascript': {'cmd': 'node',   'args': [], 'ext': '.js',  'icon': '📜'},
    'js':         {'cmd': 'node',   'args': [], 'ext': '.js',  'icon': '📜'},
}

_SHELL_LANG_KEYS = ('bash', 'sh', 'shell', 'powershell', 'ps1')


# PowerShell 자식 출력/콘솔 코드 페이지를 UTF-8 로 강제하는 프리앰블.
# - $OutputEncoding / [Console]::OutputEncoding : PS 내부 파이프·리다이렉트의 인코딩
# - chcp 65001 > $null                         : 활성 콘솔 코드 페이지 (출력 버림)
PS_UTF8_PREAMBLE = (
    "$OutputEncoding = [Console]::OutputEncoding = "
    "[System.Text.Encoding]::UTF8\r\n"
    "chcp 65001 > $null\r\n"
)


def _wrap_code_for_shell(code: str, lang_cfg: dict) -> str:
    """쉘별 특수 프리앰블을 사용자 코드 앞에 덧붙인다.

    현재 .ps1(PowerShell) 자식만 UTF-8 강제 프리앰블이 필요하다. 다른 언어는
    `PYTHONIOENCODING` / `LC_ALL` 환경 변수 주입만으로 충분하므로 원본 코드를
    그대로 돌려준다.
    """
    if lang_cfg.get("ext") == ".ps1":
        return PS_UTF8_PREAMBLE + code
    return code


class CodeExecutor:
    """코드 실행 환경 - 다양한 언어의 코드를 실행하고 결과를 반환"""

    def __init__(self, workspace_dir: Path, timeout: int = 30):
        self.workspace_dir = workspace_dir
        self.timeout = timeout
        shell_cfg = _build_shell_config()
        self.SUPPORTED_LANGUAGES = {
            **_BASE_LANGUAGES,
            **{key: shell_cfg for key in _SHELL_LANG_KEYS},
        }

    # 기본 인코딩 (UTF‑8) – 필요 시 환경 변수로 재정의 가능.
    # NOTE: 이 값은 부모가 자식 stdout/stderr 바이트를 디코드할 때 사용되며,
    # 동시에 자식 프로세스의 PYTHONIOENCODING 으로도 주입된다(_build_child_env).
    # 따라서 CODE_EXECUTOR_ENCODING 을 바꾸면 부모/자식 인코딩이 함께 바뀐다.
    DEFAULT_ENCODING = os.getenv("CODE_EXECUTOR_ENCODING", "utf-8")

    def _build_child_env(self) -> Dict[str, str]:
        """자식 프로세스용 UTF-8 강제 환경 변수 세트를 반환.

        - PYTHONIOENCODING : 자식 Python 의 stdin/stdout/stderr 인코딩
        - PYTHONUTF8=1     : Python 3.7+ UTF-8 Mode (open() 기본 인코딩까지 UTF-8)
        - LC_ALL / LANG    : POSIX 쉘·로캘 대비 (사용자 설정이 있으면 존중)

        부모의 `os.environ` 은 복사본만 생성하여 변경하지 않는다.
        """
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = self.DEFAULT_ENCODING
        env["PYTHONUTF8"] = "1"
        env.setdefault("LC_ALL", "C.UTF-8")
        env.setdefault("LANG", "C.UTF-8")
        return env

    def execute(self, code: str, language: str = 'python') -> Dict:
        """코드 실행 및 결과 반환"""
        language = language.lower()
        
        if language not in self.SUPPORTED_LANGUAGES:
            return {
                'success': False, 
                'error': f'지원하지 않는 언어: {language}',
                'hint': f'지원 언어: {", ".join(set(v["cmd"] for v in self.SUPPORTED_LANGUAGES.values()))}'
            }
        
        lang_config = self.SUPPORTED_LANGUAGES[language]

        # 쉘별 프리앰블 삽입 (현재는 .ps1 UTF-8 강제만 해당)
        code_to_write = _wrap_code_for_shell(code, lang_config)

        # PowerShell 5.x 는 BOM 없는 UTF-8 .ps1 을 ANSI(CP949 등) 로 오인해 스크립트
        # 내부 한글·이모지 리터럴을 파싱 시점에 손상시킨다. .ps1 한정으로 BOM 을 기록.
        file_encoding = 'utf-8-sig' if lang_config.get('ext') == '.ps1' else 'utf-8'

        # 임시 파일에 코드 작성
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix=lang_config['ext'],
                delete=False,
                encoding=file_encoding,
            ) as f:
                f.write(code_to_write)
                temp_file = f.name
        except Exception as e:
            return {'success': False, 'error': f'임시 파일 생성 실패: {e}'}

        try:
            cmd_parts = [lang_config['cmd']] + lang_config.get('args', []) + [temp_file]
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                encoding=self.DEFAULT_ENCODING,
                errors='replace',               # 디코딩 실패 시 스레드를 죽이지 않고 '?'나 ''로 대체
                timeout=self.timeout,
                cwd=str(self.workspace_dir),
                env=self._build_child_env(),    # 자식 stdout/open() 을 UTF-8 로 강제
            )
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode,
                'language': lang_config['cmd'],
                'icon': lang_config['icon']
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False, 
                'error': f'⏱️ 타임아웃: {self.timeout}초 초과',
                'icon': lang_config['icon']
            }
        except FileNotFoundError:
            return {
                'success': False,
                'error': f'❌ 실행 환경 없음: {lang_config["cmd"]}가 설치되어 있지 않습니다.',
                'icon': lang_config['icon']
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'실행 오류: {e}',
                'icon': lang_config['icon']
            }
        finally:
            try:
                os.unlink(temp_file)
            except:
                pass
    
    def extract_code_from_response(self, response: str) -> List[Dict]:
        """AI 응답에서 코드 블록 추출"""
        code_blocks = []
        
        # ```filename:path 형식
        pattern1 = r'```filename:(.+?)\n(.*?)```'
        matches1 = re.findall(pattern1, response, re.DOTALL)
        for filepath, content in matches1:
            ext = Path(filepath.strip()).suffix.lower()
            lang = self._ext_to_language(ext)
            code_blocks.append({
                'filepath': filepath.strip(),
                'code': content.strip(),
                'language': lang
            })
        
        # ```language 형식 (언어 식별자)
        pattern2 = r'```(\w+)\n(.*?)```'
        matches2 = re.findall(pattern2, response, re.DOTALL)
        for lang, content in matches2:
            if lang.lower() not in ['filename', 'text', 'markdown', 'md', 'json', 'xml', 'html', 'css']:
                if lang.lower() in self.SUPPORTED_LANGUAGES:
                    code_blocks.append({
                        'filepath': None,
                        'code': content.strip(),
                        'language': lang.lower()
                    })
        
        return code_blocks
    
    def _ext_to_language(self, ext: str) -> str:
        """파일 확장자를 언어로 변환"""
        ext_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.sh': 'bash',
        }
        return ext_map.get(ext.lower(), 'python')
