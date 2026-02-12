"""
DiffViewer - 코드 Diff 표시 모듈

기존 코드와 AI가 생성한 코드 간의 차이를 시각적으로 표시합니다.
Python 내장 difflib 모듈을 사용하여 Unified Diff를 생성하고,
터미널 색상 코드를 사용하여 추가/삭제된 라인을 강조합니다.
"""

import difflib
from pathlib import Path
from typing import Optional, Dict, List, Tuple


class DiffViewer:
    """두 코드 간의 차이를 분석하고 색상 정보가 포함된 Diff 텍스트를 생성합니다."""

    # ANSI 터미널 색상 코드
    COLORS = {
        'reset': '\033[0m',
        'red': '\033[91m',      # 삭제된 라인 (빨간색)
        'green': '\033[92m',    # 추가된 라인 (초록색)
        'yellow': '\033[93m',   # 변경된 라인 헤더 (노란색)
        'cyan': '\033[96m',     # 파일명 (시안색)
        'bold': '\033[1m',      # 굵게
    }

    def __init__(self):
        """DiffViewer 초기화"""
        # 마지막 diff 정보 저장 (apply용)
        self._last_diff: Optional[Dict] = None

    def generate_colored_diff(
        self,
        original: str,
        new: str,
        original_name: str = "original",
        new_name: str = "modified",
        context_lines: int = 3
    ) -> str:
        """
        두 문자열(코드) 간의 차이를 분석하고 색상 정보가 포함된 Diff 텍스트를 생성합니다.

        Args:
            original: 원본 코드 문자열
            new: 새로운 코드 문자열
            original_name: 원본 파일명 (표시용)
            new_name: 새로운 파일명 (표시용)
            context_lines: Diff 컨텍스트 라인 수

        Returns:
            색상 정보가 포함된 Diff 문자열
        """
        original_lines = original.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        # Unified Diff 생성
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=original_name,
            tofile=new_name,
            n=context_lines
        )

        result = []
        for line in diff:
            colored_line = self._colorize_line(line)
            result.append(colored_line)

        if not result:
            return f"{self.COLORS['cyan']}변경 사항 없음{self.COLORS['reset']}"

        return ''.join(result)

    def _colorize_line(self, line: str) -> str:
        """
        Diff 라인에 색상 코드를 적용합니다.

        Args:
            line: Diff 라인

        Returns:
            색상이 적용된 라인
        """
        if line.startswith('+++') or line.startswith('---'):
            # 파일명 헤더
            return f"{self.COLORS['bold']}{self.COLORS['cyan']}{line}{self.COLORS['reset']}"
        elif line.startswith('@@'):
            # 섹션 헤더
            return f"{self.COLORS['yellow']}{line}{self.COLORS['reset']}"
        elif line.startswith('+') and not line.startswith('+++'):
            # 추가된 라인
            return f"{self.COLORS['green']}{line}{self.COLORS['reset']}"
        elif line.startswith('-') and not line.startswith('---'):
            # 삭제된 라인
            return f"{self.COLORS['red']}{line}{self.COLORS['reset']}"
        else:
            # 컨텍스트 라인
            return line

    def generate_diff_for_file(
        self,
        filepath: Path,
        new_content: str,
        file_manager
    ) -> Tuple[str, bool]:
        """
        파일과 새로운 내용 간의 Diff를 생성합니다.

        Args:
            filepath: 원본 파일 경로
            new_content: 새로운 파일 내용
            file_manager: FileManager 인스턴스

        Returns:
            (색상 Diff 문자열, 파일 존재 여부) 튜플
        """
        if filepath.exists():
            original_content = file_manager.read_file(filepath)
            if original_content is None:
                return (f"❌ 파일 읽기 실패: {filepath}", False)
            
            # 마지막 diff 정보 저장
            self._last_diff = {
                'filepath': filepath,
                'original': original_content,
                'new': new_content
            }
            
            diff = self.generate_colored_diff(
                original_content,
                new_content,
                original_name=str(filepath),
                new_name=f"{filepath} (제안)"
            )
            return (diff, True)
        else:
            # 새 파일인 경우
            self._last_diff = {
                'filepath': filepath,
                'original': '',
                'new': new_content
            }
            
            diff = self.generate_colored_diff(
                '',
                new_content,
                original_name="(새 파일)",
                new_name=str(filepath)
            )
            return (diff, False)

    def get_diff_stats(self, original: str, new: str) -> Dict:
        """
        두 코드 간의 변경 통계를 반환합니다.

        Args:
            original: 원본 코드
            new: 새로운 코드

        Returns:
            변경 통계 딕셔너리 (added, deleted, modified)
        """
        original_lines = original.splitlines()
        new_lines = new.splitlines()

        # SequenceMatcher를 사용하여 상세 통계 계산
        matcher = difflib.SequenceMatcher(None, original_lines, new_lines)
        
        added = 0
        deleted = 0
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                deleted += (i2 - i1)
                added += (j2 - j1)
            elif tag == 'delete':
                deleted += (i2 - i1)
            elif tag == 'insert':
                added += (j2 - j1)

        return {
            'added': added,
            'deleted': deleted,
            'total_changes': added + deleted,
            'original_lines': len(original_lines),
            'new_lines': len(new_lines)
        }

    def extract_code_suggestions(self, response: str) -> List[Dict]:
        """
        AI 응답에서 코드 제안을 추출합니다.
        
        ```filename:path/to/file.ext 형식을 찾아서 파일별로 분리합니다.

        Args:
            response: AI 응답 문자열

        Returns:
            코드 제안 목록 [{filepath, content}, ...]
        """
        suggestions = []
        lines = response.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # ```filename: 또는 ```language filename: 패턴 찾기
            if line.strip().startswith('```'):
                stripped = line.strip()[3:]  # ``` 제거
                
                # ```filename:path 형식
                if stripped.startswith('filename:'):
                    filepath = stripped[9:].strip()
                # ```python filename:path 형식 등
                elif 'filename:' in stripped:
                    idx = stripped.index('filename:')
                    filepath = stripped[idx + 9:].strip()
                else:
                    i += 1
                    continue
                
                # 코드 블록 내용 수집
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                
                if filepath and code_lines:
                    suggestions.append({
                        'filepath': Path(filepath),
                        'content': '\n'.join(code_lines)
                    })
            
            i += 1
        
        return suggestions

    def get_last_diff(self) -> Optional[Dict]:
        """마지막 diff 정보를 반환합니다."""
        return self._last_diff

    def clear_last_diff(self):
        """마지막 diff 정보를 초기화합니다."""
        self._last_diff = None

    def apply_diff(self, file_manager) -> Tuple[bool, str]:
        """
        마지막 diff를 파일에 적용합니다.

        Args:
            file_manager: FileManager 인스턴스

        Returns:
            (성공 여부, 메시지) 튜플
        """
        if not self._last_diff:
            return (False, "적용할 diff가 없습니다. 먼저 /diff 명령어를 실행하세요.")
        
        filepath = self._last_diff['filepath']
        new_content = self._last_diff['new']
        
        try:
            if file_manager.write_file(filepath, new_content):
                msg = f"✅ 파일이 성공적으로 업데이트되었습니다: {filepath}"
                self.clear_last_diff()
                return (True, msg)
            else:
                return (False, f"❌ 파일 쓰기 실패: {filepath}")
        except Exception as e:
            return (False, f"❌ 오류 발생: {str(e)}")

    def format_stats_display(self, stats: Dict) -> str:
        """
        변경 통계를 포맷팅된 문자열로 반환합니다.

        Args:
            stats: get_diff_stats()의 반환값

        Returns:
            포맷팅된 통계 문자열
        """
        lines = [
            f"📊 변경 통계:",
            f"   {self.COLORS['green']}+ {stats['added']} 라인 추가{self.COLORS['reset']}",
            f"   {self.COLORS['red']}- {stats['deleted']} 라인 삭제{self.COLORS['reset']}",
            f"   총 {stats['total_changes']} 라인 변경",
            f"   원본: {stats['original_lines']}줄 → 수정: {stats['new_lines']}줄"
        ]
        return '\n'.join(lines)
