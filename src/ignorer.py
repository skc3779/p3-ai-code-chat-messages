import fnmatch
from pathlib import Path
from typing import Iterable

class Ignorer:
    def __init__(self, workspace_dir: Path, ignore_patterns: Iterable[str]) -> None:
        self.workspace_dir = workspace_dir
        self.ignore_patterns = list(ignore_patterns)

    def _match(self, target: str, pattern: str) -> bool:
        """
        `fnmatch` 를 이용해 실제 매칭을 수행.
        - pattern 이 디렉터리 전용(`.../`)이면 target 뒤에 '/' 를 붙여서 매칭한다.
        """
        if pattern.endswith("/"):
            # 디렉터리 전용 패턴 → target 뒤에 '/' 를 붙여서 매칭
            return fnmatch.fnmatch(target + "/", pattern)
        return fnmatch.fnmatch(target, pattern)

    def should_ignore(self, path: Path) -> bool:
        """파일·디렉터리를 무시해야 하는지 확인"""
        # workspace_dir 아래의 상대 경로 문자열
        rel_path = path.relative_to(self.workspace_dir)
        rel_path_str = str(rel_path)

        for pat in self.ignore_patterns:
            # 1) 상대 경로 전체에 대한 매칭
            if self._match(rel_path_str, pat):
                return True

            # 2) 파일·디렉터리 이름만으로 매칭 (예: "README.md", ".git")
            if self._match(path.name, pat):
                return True

            # 3) 디렉터리 전용 패턴이면서 실제 경로가 디렉터리인 경우,
            #    디렉터리 이름에 '/' 를 붙여서 매칭 (예: ".idea/")
            if pat.endswith("/") and path.is_dir():
                if self._match(path.name, pat):
                    return True

        return False
