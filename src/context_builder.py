"""
ContextBuilder - AI에게 전달할 컨텍스트 구성 모듈
"""

import fnmatch
from pathlib import Path
from typing import List, Optional

from .file_manager import FileManager
from .tree_builder import TreeBuilder


class ContextBuilder:
    """AI에게 전달할 컨텍스트 구성"""

    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager
        self.max_context_size = 100000  # 최대 컨텍스트 크기 (문자 수)

    def build_file_tree2(self, max_depth: int = 11) -> str:
        """파일 트리 구조 생성 (레거시)"""
        tree_lines = [f"📁 프로젝트 구조 (작업 디렉토리: {self.file_manager.workspace_dir})\n"]

        def add_tree_item(path: Path, prefix: str = "", depth: int = 0):
            if depth > max_depth:
                return

            if self.file_manager.should_ignore(path):
                return

            name = path.name
            if path.is_file():
                tree_lines.append(f"{prefix}📄 {name}")
            elif path.is_dir():
                tree_lines.append(f"{prefix}📁 {name}/")
                try:
                    items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
                    for i, item in enumerate(items):
                        is_last = i == len(items) - 1
                        new_prefix = prefix + ("    " if is_last else "│   ")
                        connector = "└── " if is_last else "├── "
                        tree_lines.append("")
                        tree_lines[-1] = prefix + connector
                        add_tree_item(item, new_prefix, depth + 1)
                except PermissionError:
                    pass

        add_tree_item(self.file_manager.workspace_dir)
        return "\n".join(tree_lines)

    def build_file_tree(self, max_depth: int = 11) -> str:
        """TreeBuilder를 사용하여 파일 트리 구조 생성"""
        builder = TreeBuilder(
            workspace_dir=self.file_manager.workspace_dir,
            should_ignore=self.file_manager.should_ignore,
            max_depth=max_depth,
        )
        return builder.build()

    def build_files_context(self, filepaths: List[Path]) -> str:
        """선택된 파일들의 내용을 컨텍스트로 구성"""
        context_parts = []
        total_size = 0

        for filepath in filepaths:
            content = self.file_manager.read_file(filepath)
            if content is None:
                continue

            rel_path = filepath.relative_to(self.file_manager.workspace_dir)
            file_context = f"\n{'=' * 80}\n"
            file_context += f"📄 파일: {rel_path}\n"
            file_context += f"{'=' * 80}\n"
            file_context += f"```{filepath.suffix[1:] if filepath.suffix else ''}\n"
            file_context += content
            file_context += f"\n```\n"

            if total_size + len(file_context) > self.max_context_size:
                context_parts.append("\n⚠️  컨텍스트 크기 제한으로 일부 파일이 생략되었습니다.\n")
                break

            context_parts.append(file_context)
            total_size += len(file_context)

        return "\n".join(context_parts)

    def build_context(self, include_tree: bool = True, file_patterns: Optional[List[str]] = None) -> str:
        """전체 컨텍스트 구성"""
        context_parts = []

        if include_tree:
            context_parts.append(self.build_file_tree())
            context_parts.append("\n")

        if file_patterns:
            files = []
            all_files = self.file_manager.list_files()

            for pattern in file_patterns:
                matched = [f for f in all_files if
                           fnmatch.fnmatch(str(f.relative_to(self.file_manager.workspace_dir)), pattern)]
                files.extend(matched)

            if files:
                context_parts.append(self.build_files_context(files))

        return "\n".join(context_parts)