"""
FileManager - 로컬 파일 시스템 관리 모듈
"""

import fnmatch
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class FileManager:
    """로컬 파일 시스템 관리"""

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.ignore_patterns = self._load_ignore_patterns()

    def _load_ignore_patterns(self) -> List[str]:
        """gitignore 스타일 패턴 로드"""
        patterns = [
            '*.pyc', '__pycache__', '.git', '.venv', 'venv',
            'node_modules', '.DS_Store', '*.log', '.env'
        ]

        gitignore_path = self.workspace_dir / '.gitignore'
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                patterns.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])

        return patterns

    def should_ignore(self, path: Path) -> bool:
        """파일/디렉토리를 무시해야 하는지 확인"""
        rel_path = path.relative_to(self.workspace_dir)
        path_str = str(rel_path)

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
        return False

    def list_files(self, extensions: Optional[List[str]] = None, max_depth: int = 5) -> List[Path]:
        """작업 공간의 파일 목록 반환"""
        files = []

        def scan_directory(directory: Path, current_depth: int = 0):
            if current_depth > max_depth:
                return

            try:
                for item in directory.iterdir():
                    if self.should_ignore(item):
                        continue

                    if item.is_file():
                        if extensions is None or item.suffix in extensions:
                            files.append(item)
                    elif item.is_dir():
                        scan_directory(item, current_depth + 1)
            except PermissionError:
                pass

        scan_directory(self.workspace_dir)
        return sorted(files)

    def read_file(self, filepath: Path) -> Optional[str]:
        """파일 내용 읽기"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    return f.read()
            except Exception as e:
                print(f"⚠️  파일 읽기 실패 ({filepath}): {e}")
                return None
        except Exception as e:
            print(f"⚠️  파일 읽기 실패 ({filepath}): {e}")
            return None

    def write_file(self, filepath: Path, content: str) -> bool:
        """파일 쓰기"""
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"❌ 파일 쓰기 실패 ({filepath}): {e}")
            return False

    def get_file_info(self, filepath: Path) -> Dict:
        """파일 정보 반환"""
        try:
            stat = filepath.stat()
            return {
                'path': str(filepath.relative_to(self.workspace_dir)),
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'extension': filepath.suffix
            }
        except Exception:
            return {}
