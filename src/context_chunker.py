"""Provider-budgeted file chunking for large context requests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable, List

from .token_manager import TokenManager


CHUNK_SCHEMA_VERSION = 1
OVERLAP_LINES = 20


@dataclass(frozen=True)
class ContextBudget:
    request_budget_tokens: int
    output_reserve_tokens: int
    prompt_reserve_tokens: int
    safety_reserve_tokens: int
    usable_input_tokens: int
    map_payload_tokens: int
    map_payload_chars: int
    reduce_payload_chars: int

    @classmethod
    def from_request_budget(cls, request_budget_tokens: int) -> "ContextBudget":
        output = min(8192, int(request_budget_tokens * 0.10))
        prompt = 4096
        safety = int(request_budget_tokens * 0.10)
        usable = request_budget_tokens - output - prompt - safety
        if request_budget_tokens <= 0 or usable < 8192:
            raise ValueError(
                "대규모 컨텍스트 토큰 한도가 너무 작습니다: "
                f"현재 {request_budget_tokens:,}, 예약 후 최소 8,192 토큰이 필요합니다."
            )
        map_tokens = min(32768, usable)
        return cls(
            request_budget_tokens=request_budget_tokens,
            output_reserve_tokens=output,
            prompt_reserve_tokens=prompt,
            safety_reserve_tokens=safety,
            usable_input_tokens=usable,
            map_payload_tokens=map_tokens,
            map_payload_chars=int(map_tokens * TokenManager.CHARS_PER_TOKEN),
            reduce_payload_chars=int(usable * TokenManager.CHARS_PER_TOKEN),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FileRecord:
    path: str
    absolute_path: Path
    content: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ChunkPart:
    path: str
    content: str
    file_sha256: str
    start_line: int
    end_line: int
    part_index: int = 1
    part_count: int = 1
    overlap_lines: int = 0
    line_fragment: bool = False

    def render(self) -> str:
        header = (
            f"\n===== FILE: {self.path} "
            f"L{self.start_line}-L{self.end_line} "
            f"PART {self.part_index}/{self.part_count} =====\n"
        )
        return header + self.content


@dataclass(frozen=True)
class ContextChunk:
    index: int
    parts: tuple[ChunkPart, ...]
    payload: str
    fingerprint: str


class ContextChunker:
    def __init__(self, budget: ContextBudget, overlap_lines: int = OVERLAP_LINES):
        self.budget = budget
        self.overlap_lines = overlap_lines

    @staticmethod
    def hash_text(text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()

    def make_record(self, workspace: Path, path: Path, content: str) -> FileRecord:
        rel = path.resolve().relative_to(workspace.resolve()).as_posix()
        return FileRecord(rel, path.resolve(), content, self.hash_text(content), len(content.encode("utf-8")))

    def chunk(self, records: Iterable[FileRecord], identity: str = "") -> List[ContextChunk]:
        all_parts: List[ChunkPart] = []
        for record in sorted(records, key=lambda item: item.path):
            all_parts.extend(self._split_record(record))

        chunks: List[ContextChunk] = []
        current: List[ChunkPart] = []
        current_chars = 0
        for part in all_parts:
            rendered = part.render()
            if current and current_chars + len(rendered) > self.budget.map_payload_chars:
                chunks.append(self._build_chunk(len(chunks) + 1, current, identity))
                current, current_chars = [], 0
            current.append(part)
            current_chars += len(rendered)
        if current:
            chunks.append(self._build_chunk(len(chunks) + 1, current, identity))
        return chunks

    def _split_record(self, record: FileRecord) -> List[ChunkPart]:
        whole = ChunkPart(record.path, record.content, record.sha256, 1, max(1, record.content.count("\n") + 1))
        if len(whole.render()) <= self.budget.map_payload_chars:
            return [whole]

        lines = record.content.splitlines(keepends=True) or [""]
        raw_parts: List[tuple[int, int, str, int, bool]] = []
        start = 0
        while start < len(lines):
            end = start
            used = 0
            fragment = False
            selected: List[str] = []
            while end < len(lines):
                available = self.budget.map_payload_chars - 160 - used
                if available <= 0:
                    break
                line = lines[end]
                if len(line) > available and not selected:
                    selected.append(line[:available])
                    lines[end] = line[available:]
                    fragment = True
                    used += available
                    break
                if len(line) > available:
                    break
                selected.append(line)
                used += len(line)
                end += 1
            if not selected:
                raise ValueError(f"청크 예산으로 파일을 분할할 수 없습니다: {record.path}")
            logical_end = max(start + 1, end)
            overlap = 0 if not raw_parts else min(self.overlap_lines, max(0, logical_end - start))
            raw_parts.append((start + 1, logical_end, "".join(selected), overlap, fragment))
            if fragment:
                continue
            if end >= len(lines):
                break
            start = max(start + 1, end - self.overlap_lines)

        count = len(raw_parts)
        return [
            ChunkPart(record.path, text, record.sha256, first, last, idx, count, overlap, fragment)
            for idx, (first, last, text, overlap, fragment) in enumerate(raw_parts, 1)
        ]

    def _build_chunk(self, index: int, parts: List[ChunkPart], identity: str) -> ContextChunk:
        payload = "".join(part.render() for part in parts)
        if len(payload) > self.budget.map_payload_chars:
            raise ValueError("생성된 Map payload가 토큰 예산을 초과했습니다.")
        material = "\n".join(
            [identity, str(self.budget.map_payload_tokens)]
            + [f"{p.path}:{p.file_sha256}:{p.start_line}:{p.end_line}:{p.part_index}" for p in parts]
        )
        return ContextChunk(index, tuple(parts), payload, sha256(material.encode("utf-8")).hexdigest())
