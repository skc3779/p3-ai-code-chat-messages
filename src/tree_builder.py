"""
TreeBuilder - 파일·디렉터리 트리 생성 모듈
"""

from pathlib import Path
from typing import List, Callable


class TreeBuilder:
    """
    파일·디렉터리 트리를 문자열 형태로 만들어 반환합니다.

    Parameters
    ----------
    workspace_dir : Path
        트리를 시작할 루트 디렉터리.
    should_ignore : Callable[[Path], bool]
        파일·디렉터리를 무시할지 판단하는 함수.
    max_depth : int, optional
        표시할 최대 깊이 (0이면 루트만, 1이면 바로 아래 레벨까지 …)
    """

    def __init__(
            self,
            workspace_dir: Path,
            should_ignore: Callable[[Path], bool],
            max_depth: int = 11,
    ) -> None:
        self.root = workspace_dir
        self.should_ignore = should_ignore
        self.max_depth = max_depth

    def _add_children(
        self,
        dir_path: Path,
        prefix: str,
        depth: int,
        out: List[str],
    ) -> None:
        """
        ``dir_path`` 의 **직접적인 자식**들을 ``out`` 에 추가한다.
        """
        if depth >= self.max_depth:
            return

        try:
            children = sorted(
                dir_path.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except PermissionError:
            return

        for idx, child in enumerate(children):
            if self.should_ignore(child):
                continue

            is_last = idx == len(children) - 1
            connector = "└── " if is_last else "├── "

            icon = "📁 " if child.is_dir() else "📄 "
            suffix = "/" if child.is_dir() else ""

            out.append(f"{prefix}{connector}{icon}{child.name}{suffix}")

            if child.is_dir():
                next_prefix = prefix + ("    " if is_last else "│   ")
                self._add_children(child, next_prefix, depth + 1, out)

    def build(self) -> str:
        """루트 디렉터리부터 시작해 전체 트리를 만든 뒤 문자열로 반환합니다."""
        lines: List[str] = [f"📁 프로젝트 구조 (작업 디렉터리: {self.root})"]
        lines.append(f"📁 {self.root.name}/")
        self._add_children(self.root, "", 0, lines)
        return "\n".join(lines)
