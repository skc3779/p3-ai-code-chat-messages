"""
CodeExecutor - 코드 실행 환경 모듈
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict


class CodeExecutor:
    """코드 실행 환경 - 다양한 언어의 코드를 실행하고 결과를 반환"""
    
    SUPPORTED_LANGUAGES = {
        'python': {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
        'py': {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
        'javascript': {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
        'js': {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
        'bash': {'cmd': 'bash', 'ext': '.sh', 'icon': '🖥️'},
        'sh': {'cmd': 'bash', 'ext': '.sh', 'icon': '🖥️'},
    }
    
    def __init__(self, workspace_dir: Path, timeout: int = 30):
        self.workspace_dir = workspace_dir
        self.timeout = timeout
    
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
        
        # 임시 파일에 코드 작성
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix=lang_config['ext'], 
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(code)
                temp_file = f.name
        except Exception as e:
            return {'success': False, 'error': f'임시 파일 생성 실패: {e}'}
        
        try:
            result = subprocess.run(
                [lang_config['cmd'], temp_file],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.workspace_dir)
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
                if lang.lower() in self.SUPPORTED_LANGUAGES or lang.lower() in ['python', 'javascript', 'bash']:
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
