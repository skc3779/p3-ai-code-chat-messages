"""
FilePatternMatcher - 파일 패턴 매칭 유틸리티 모듈

다양한 경로 형식(절대경로, 상대경로, ./접두어, 파일명)을 지원하는
파일 패턴 매칭 기능을 제공합니다.

v1.0.068: ** 재귀 글로빙 지원 추가
"""

import fnmatch
from pathlib import Path, PurePosixPath
from typing import List


class FilePatternMatcher:
    """파일 패턴 매칭 유틸리티 클래스"""
    
    def __init__(self, workspace_dir: Path):
        """
        Args:
            workspace_dir: 작업 디렉토리 경로
        """
        self.workspace_dir = Path(workspace_dir).resolve()
    
    def normalize_pattern(self, pattern: str) -> str:
        """
        패턴을 정규화합니다.
        
        - ./ 또는 .\\ 접두어 제거
        - 백슬래시를 슬래시로 통일
        - 절대 경로를 상대 경로로 변환
        
        Args:
            pattern: 원본 패턴 문자열
            
        Returns:
            정규화된 패턴 문자열
        """
        normalized = pattern
        
        # ./ 또는 .\ 접두어 제거 (startswith 사용)
        if normalized.startswith('./'):
            normalized = normalized[2:]
        elif normalized.startswith('.\\'):
            normalized = normalized[2:]
        
        # 백슬래시 → 슬래시 통일
        normalized = normalized.replace('\\', '/')
        
        # 절대 경로 패턴인 경우: workspace 기준 상대 경로로 변환 시도
        try:
            pattern_path = Path(pattern)
            if pattern_path.is_absolute():
                try:
                    normalized = str(pattern_path.relative_to(self.workspace_dir)).replace('\\', '/')
                except ValueError:
                    pass  # workspace 외부 경로면 그대로 사용
        except Exception:
            pass
        
        return normalized
    
    def _match_recursive(self, rel_path: str, pattern: str) -> bool:
        """
        ** 패턴을 포함한 재귀 글로빙 매칭
        
        PurePosixPath.match()를 사용하여 ** 패턴을 지원합니다.
        ** 는 0개 이상의 디렉토리를 매칭합니다.
        
        Python 3.12의 PurePosixPath.match()는 **를 "최소 1개 디렉토리"로
        해석하므로, **를 제거한 직하위 패턴도 fnmatch로 추가 매칭합니다.
        예: src/**/*.py → src/deep/file.py (PurePosixPath) + src/file.py (fnmatch)
        
        Args:
            rel_path: 워크스페이스 기준 상대 경로 (슬래시 정규화 완료)
            pattern: ** 를 포함한 글로브 패턴
            
        Returns:
            매칭 여부
        """
        # 1. PurePosixPath.match()로 하위 디렉토리 재귀 매칭
        if PurePosixPath(rel_path).match(pattern):
            return True
        
        # 2. ** 를 제거한 직하위 패턴으로 fnmatch 폴백
        #    src/**/*.py → src/*.py, src/**/gen*.py → src/gen*.py
        flat_pattern = pattern.replace('**/', '').replace('/**', '')
        if fnmatch.fnmatch(rel_path, flat_pattern):
            return True
        
        return False
    
    def match(self, filepath: Path, pattern: str) -> bool:
        """
        파일 경로가 패턴과 일치하는지 확인합니다.
        
        다양한 형식 지원:
        - 상대 경로 (src/file.py)
        - 파일명만 (file.py)
        - ./ 접두어 경로 (./src/file.py)
        - 절대 경로 (c:/workspace/src/file.py)
        - 와일드카드 (*.py, src/*.py)
        - ** 재귀 글로빙 (src/**/*.py)
        
        Args:
            filepath: 검사할 파일 경로
            pattern: 매칭할 패턴
            
        Returns:
            매칭 여부
        """
        normalized_pattern = self.normalize_pattern(pattern)
        
        # 파일의 상대 경로 계산 및 정규화
        try:
            rel_path = str(filepath.relative_to(self.workspace_dir)).replace('\\', '/')
        except ValueError:
            rel_path = str(filepath).replace('\\', '/')
        
        filename = filepath.name
        
        # ** 패턴이 포함된 경우: 재귀 글로빙 사용
        if '**' in normalized_pattern:
            return self._match_recursive(rel_path, normalized_pattern)
        
        # 1. 상대 경로와 매칭
        if fnmatch.fnmatch(rel_path, normalized_pattern):
            return True
        
        # 2. 파일명만으로 매칭
        if fnmatch.fnmatch(filename, normalized_pattern):
            return True
        
        # 3. 패턴이 경로의 일부인 경우 (예: .system-prompts/code-review.yaml)
        if fnmatch.fnmatch(rel_path, '*/' + normalized_pattern):
            return True
        
        if fnmatch.fnmatch(rel_path, normalized_pattern.lstrip('*/')):
            return True
        
        return False
    
    def filter_files(self, files: List[Path], patterns: List[str]) -> List[Path]:
        """
        파일 목록에서 패턴과 일치하는 파일들을 필터링합니다.
        
        Args:
            files: 파일 경로 목록
            patterns: 매칭할 패턴 목록
            
        Returns:
            매칭된 파일 경로 목록
        """
        matched_files = []
        
        for pattern in patterns:
            for f in files:
                if self.match(f, pattern) and f not in matched_files:
                    matched_files.append(f)
        
        return matched_files

