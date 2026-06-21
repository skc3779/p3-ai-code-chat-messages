"""
AgentPatchApplier (FSD v1.0.115)

`/agents` ACT 의 ```patch:<path>``` 블록을 SEARCH/REPLACE 방식으로 적용한다.

- 한 펜스에 N 개의 SEARCH/REPLACE 쌍 허용
- exact / fuzzy / similar / appended / ambiguous / no_match 상태 보고
- 트랜잭셔널: 한 블록이라도 실패하면 디스크에 쓰지 않음
- 빈 SEARCH 는 파일 끝 append 또는 신규 파일 생성으로 동작
- 정규식 미사용 — 리터럴/시퀀스 매칭 보장 (NFR-111-04)
- REP v1.1.033: difflib 유사도 기반 윈도우 매칭 tier 추가 — 긴 파일에서
  LLM 이 생성한 SEARCH 가 원본과 '거의' 같지만 완전히 일치하지 않을 때 처리
- workspace 밖 경로(traversal)는 거부
"""

import difflib
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple


_MARK_SEARCH = "<<<<<<< SEARCH"
_MARK_DIVIDER = "======="
_MARK_REPLACE = ">>>>>>> REPLACE"


@dataclass
class _Block:
    search: str
    replace: str


@dataclass
class BlockResult:
    """단일 SEARCH/REPLACE 블록의 적용 결과."""
    status: str                    # exact | fuzzy | similar | appended | ambiguous | no_match
    diagnostic: Optional[str] = None


@dataclass
class PatchResult:
    """한 ```patch:<path>``` 펜스의 전체 적용 결과."""
    success: bool
    applied_count: int = 0
    total_count: int = 0
    block_results: List[BlockResult] = field(default_factory=list)
    error: Optional[str] = None       # 파싱 실패 / IO 실패 / 거부 등
    new_text: Optional[str] = None    # 성공 시 디스크에 쓰여진 본문 (테스트용)


class AgentPatchApplier:
    """SEARCH/REPLACE 패치 적용기.

    의존성: FileManager (read_file / write_file / workspace_dir)
    """

    SNIPPET_CONTEXT_LINES = 5
    DIAGNOSTIC_MAX_CHARS = 500
    # REP v1.1.033 — 유사도 기반 fuzzy 매칭: 최우선/차순위 ratio 차이가
    # 이 값보다 작고 둘 다 임계값 이상이면 모호(ambiguous)로 간주한다.
    UNIQUENESS_MARGIN = 0.05
    # 최우선 ratio 가 이 값 이상이면 (거의 정확한 매칭) 차순위와 무관하게 적용.
    # 반복적 코드에서 정수만 다른 인접 블록을 정확히 겨냥하기 위함.
    HIGH_CONFIDENCE_RATIO = 0.95
    # 최우선/차순위 ratio 차가 이 값 미만이면 '동률(tie)' — 진짜로 구별 불가
    # (예: 본문이 동일한 두 함수). HIGH_CONFIDENCE 여도 적용하지 않는다.
    TIE_EPSILON = 0.01

    def __init__(self, file_manager):
        self.file_manager = file_manager
        # REP v1.1.033 — difflib 유사도 매칭 설정 (env 오버라이드 가능)
        self.similarity_enabled = os.getenv("AGENT_PATCH_SIMILARITY", "1") != "0"
        try:
            threshold = float(
                os.getenv("AGENT_PATCH_FUZZY_THRESHOLD", "0.85")
            )
        except (TypeError, ValueError):
            threshold = 0.85
        self.fuzzy_threshold = (
            threshold if math.isfinite(threshold) and 0.0 <= threshold <= 1.0 else 0.85
        )
        try:
            flex = int(os.getenv("AGENT_PATCH_FUZZY_FLEX", "2"))
        except (TypeError, ValueError):
            flex = 2
        self.fuzzy_flex = flex if 0 <= flex <= 20 else 2

    # ─── 진입 ─────────────────────────────────────────────────
    def apply(
        self,
        relative_path: str,
        payload: str,
        *,
        auto_approve: bool = False,
        on_first_approval: Optional[Callable[[], bool]] = None,
    ) -> PatchResult:
        """패치 본문을 적용한다.

        Args:
            relative_path: 워크스페이스 상대 경로
            payload: ```patch:...``` 펜스의 본문 (마커 포함)
            auto_approve: True 면 사용자 승인 프롬프트 생략
            on_first_approval: auto_approve=False 일 때 호출 — True 반환 시 적용
        """
        # ── 1) 경로 정규화 + traversal 차단 ──
        try:
            abs_path = self._safe_path(relative_path)
        except IOError as e:
            return PatchResult(
                success=False, total_count=0,
                error=f"잘못된 경로: {e}",
            )

        # ── 2) 펜스 본문 파싱 ──
        try:
            blocks = self.parse_blocks(payload)
        except ValueError as e:
            return PatchResult(
                success=False, total_count=0,
                error=f"패치 본문 파싱 실패: {e}",
            )
        if not blocks:
            return PatchResult(
                success=False, total_count=0,
                error="patch 빈 본문",
            )

        # ── 3) 원본 읽기 ──
        # newline="" 로 EOL 보존 — FileManager.read_file 은 universal newlines
        # 변환을 거치므로 patch 의 CRLF 보존을 위해 직접 읽는다.
        existed = abs_path.exists()
        if existed:
            original = self._read_preserving_eol(abs_path)
            if original is None:
                return PatchResult(
                    success=False, total_count=len(blocks),
                    error=f"파일 읽기 실패: {relative_path}",
                )
        else:
            # 신규 파일 — 모든 블록이 빈 SEARCH 여야 함
            if not all(b.search == "" for b in blocks):
                return PatchResult(
                    success=False, total_count=len(blocks),
                    block_results=[
                        BlockResult(
                            status="no_match",
                            diagnostic=(
                                "파일이 존재하지 않습니다. 신규 파일은 "
                                "```filename:``` 또는 빈 SEARCH 블록을 사용하세요."
                            ),
                        ) for _ in blocks
                    ],
                    error="파일 없음 — 빈 SEARCH 만 허용",
                )
            original = ""

        # ── 4) 블록별 적용 (in-memory) ──
        working = original
        results: List[BlockResult] = []

        for block in blocks:
            working, status, diag = self._apply_one(
                working, block.search, block.replace,
            )
            results.append(BlockResult(status=status, diagnostic=diag))

        all_ok = all(
            r.status in ("exact", "fuzzy", "similar", "appended") for r in results
        )

        if not all_ok:
            # 부분 실패 — 디스크 미변경
            return PatchResult(
                success=False,
                applied_count=0,
                total_count=len(blocks),
                block_results=results,
            )

        # ── 5) 승인 검사 ──
        if not auto_approve and on_first_approval is not None:
            try:
                approved = bool(on_first_approval())
            except Exception:
                approved = False
            if not approved:
                return PatchResult(
                    success=False,
                    applied_count=0,
                    total_count=len(blocks),
                    block_results=results,
                    error="사용자 거부",
                )

        # ── 6) 디스크 쓰기 ──
        try:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return PatchResult(
                success=False,
                applied_count=0,
                total_count=len(blocks),
                block_results=results,
                error=f"디렉터리 생성 실패: {e}",
            )

        ok = self._write_preserving_eol(abs_path, working)
        if not ok:
            return PatchResult(
                success=False,
                applied_count=0,
                total_count=len(blocks),
                block_results=results,
                error="디스크 쓰기 실패",
            )

        return PatchResult(
            success=True,
            applied_count=len(blocks),
            total_count=len(blocks),
            block_results=results,
            new_text=working,
        )

    # ─── EOL 보존 입출력 ──────────────────────────────────────
    @staticmethod
    def _read_preserving_eol(abs_path: Path) -> Optional[str]:
        """파일을 EOL 보존(`newline=""`) 모드로 읽는다.

        FileManager.read_file 은 universal newlines 변환으로 CRLF→LF 가
        일어나므로 patch 의 EOL 충실도를 보장하지 못한다.
        """
        for enc in ("utf-8", "latin-1"):
            try:
                with open(abs_path, "r", encoding=enc, newline="") as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
            except Exception:
                return None
        return None

    @staticmethod
    def _write_preserving_eol(abs_path: Path, content: str) -> bool:
        """파일을 EOL 보존(`newline=""`) 모드로 쓴다.

        Windows 의 기본 텍스트 모드(`\\n` → `\\r\\n`) 변환을 회피한다.
        """
        try:
            with open(abs_path, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            return True
        except Exception:
            return False

    # ─── 경로 정규화 ──────────────────────────────────────────
    def _safe_path(self, relative_path: str) -> Path:
        if not relative_path or not relative_path.strip():
            raise IOError("빈 경로")
        rel = relative_path.strip()
        if Path(rel).is_absolute():
            raise IOError("절대 경로 사용 불가")
        workspace = Path(self.file_manager.workspace_dir).resolve()
        candidate = (workspace / rel).resolve()
        try:
            candidate.relative_to(workspace)
        except ValueError:
            raise IOError("워크스페이스 외부 경로")
        return candidate

    # ─── 펜스 본문 파싱 ───────────────────────────────────────
    def parse_blocks(self, payload: str) -> List[_Block]:
        """payload 의 SEARCH/REPLACE 쌍을 추출한다.

        Returns:
            blocks: 0 개 이상의 _Block. 마커 미존재면 [] (비어 있음).

        Raises:
            ValueError: 마커 갯수 불일치 / 닫히지 않은 블록 등 구조 오류
        """
        if not payload:
            return []

        lines = payload.splitlines()
        # 잘못된 SEARCH 마커 갯수(< 7개) 사전 검출
        for raw in lines:
            stripped = raw.strip()
            if (
                stripped.startswith("<<")
                and "SEARCH" in stripped
                and stripped != _MARK_SEARCH
            ):
                raise ValueError("invalid SEARCH marker")
            if (
                stripped.startswith(">>")
                and "REPLACE" in stripped
                and stripped != _MARK_REPLACE
            ):
                raise ValueError("invalid REPLACE marker")

        if _MARK_SEARCH not in payload:
            return []

        blocks: List[_Block] = []
        state = "OUT"            # "OUT" | "IN_SEARCH" | "IN_REPLACE"
        cur_search: List[str] = []
        cur_replace: List[str] = []

        def _is(line: str, marker: str) -> bool:
            return line.strip() == marker

        for raw in lines:
            if state == "OUT":
                if _is(raw, _MARK_SEARCH):
                    state = "IN_SEARCH"
                    cur_search = []
                    cur_replace = []
                continue

            if state == "IN_SEARCH":
                if _is(raw, _MARK_DIVIDER):
                    state = "IN_REPLACE"
                    continue
                if _is(raw, _MARK_SEARCH):
                    raise ValueError("nested SEARCH marker")
                if _is(raw, _MARK_REPLACE):
                    raise ValueError("REPLACE before divider")
                cur_search.append(raw)
                continue

            if state == "IN_REPLACE":
                if _is(raw, _MARK_REPLACE):
                    blocks.append(_Block(
                        search="\n".join(cur_search),
                        replace="\n".join(cur_replace),
                    ))
                    state = "OUT"
                    cur_search = []
                    cur_replace = []
                    continue
                if _is(raw, _MARK_DIVIDER):
                    raise ValueError("duplicate divider")
                if _is(raw, _MARK_SEARCH):
                    raise ValueError("nested SEARCH marker")
                cur_replace.append(raw)
                continue

        if state != "OUT":
            raise ValueError("unclosed SEARCH/REPLACE block")

        return blocks

    # ─── 단일 블록 적용 ───────────────────────────────────────
    def _apply_one(
        self,
        working: str,
        search: str,
        replace: str,
    ) -> Tuple[str, str, Optional[str]]:
        # 빈 SEARCH — append 또는 신규 파일 작성
        if search == "":
            if working == "":
                return (replace, "appended", None)
            sep = "" if working.endswith("\n") else "\n"
            return (working + sep + replace, "appended", None)

        # exact 매칭
        count = working.count(search)
        if count == 1:
            return (working.replace(search, replace, 1), "exact", None)
        if count > 1:
            return (
                working,
                "ambiguous",
                self._format_diagnostic(
                    working, search, kind=f"multiple_matches={count}"
                ),
            )

        # fuzzy — 공백 정규화 후 재시도
        norm_search = self._normalize_text(search)
        norm_working, mapping = self._normalize_with_mapping(working)
        if norm_search and norm_working.count(norm_search) == 1:
            new_text = self._apply_fuzzy(
                working, mapping, norm_working, norm_search, search, replace,
            )
            return (new_text, "fuzzy", None)

        # similar — REP v1.1.033: difflib 유사도 기반 블록 매칭
        #   (공백 정규화로도 못 찾은 content drift 처리)
        sim = self._apply_similarity(working, search, replace)
        if sim is not None:
            return sim

        # no_match
        return (
            working,
            "no_match",
            self._format_diagnostic(working, search, kind="no_match"),
        )

    # ─── 유사도 기반 블록 매칭 (REP v1.1.033) ────────────────
    def _apply_similarity(
        self, working: str, search: str, replace: str
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """difflib 유사도 기반 블록 매칭.

        공백 정규화로도 못 찾은 경우, LLM 이 생성한 SEARCH 가 원본과
        '거의' 같지만 완전히 일치하지 않을 때(긴 파일에서 흔함)를 처리한다.
        파일을 라인 윈도우로 슬라이딩하며 `SequenceMatcher.ratio()` 가
        가장 높은 구간을 찾아, 임계값(`fuzzy_threshold`)과 유일성 마진
        (`UNIQUENESS_MARGIN`)을 만족하면 그 구간을 교체한다.

        성능: `real_quick_ratio()` / `quick_ratio()` 로 임계값 미만 윈도우를
        선차단하여 전체 ratio 계산을 최소화한다.

        Returns:
            (new_text, "similar", None)         — 적용 성공
            (working, "ambiguous", diagnostic)  — 후보가 둘 이상 (위험 → 미적용)
            None                                — 적용 불가 (호출측이 no_match 처리)
        """
        if not self.similarity_enabled:
            return None

        working_lf = working.replace("\r\n", "\n").replace("\r", "\n")
        search_lf = search.replace("\r\n", "\n").replace("\r", "\n")
        work_lines = working_lf.split("\n")
        search_lines = search_lf.split("\n")
        # join 잔재로 생긴 끝의 빈 라인 제거
        while search_lines and search_lines[-1] == "":
            search_lines.pop()
        n = len(search_lines)
        if n == 0 or not work_lines:
            return None

        search_block = "\n".join(search_lines)
        sm = difflib.SequenceMatcher(autojunk=False)
        sm.set_seq2(search_block)

        # 임계값 이상 후보를 (ratio, start, size) 로 모두 수집한다.
        # 윈도우 크기 n-flex .. n+flex 변형은 같은 위치의 경계 차이일 뿐이므로
        # 유일성 판정은 '겹치지 않는 영역' 끼리만 비교한다 (REP v1.1.033).
        lo_size = max(1, n - self.fuzzy_flex)
        hi_size = n + self.fuzzy_flex
        candidates: List[Tuple[float, int, int]] = []
        for size in range(lo_size, hi_size + 1):
            if size > len(work_lines):
                break
            for start in range(0, len(work_lines) - size + 1):
                window = "\n".join(work_lines[start:start + size])
                sm.set_seq1(window)
                if sm.real_quick_ratio() < self.fuzzy_threshold:
                    continue
                if sm.quick_ratio() < self.fuzzy_threshold:
                    continue
                r = sm.ratio()
                if r >= self.fuzzy_threshold:
                    candidates.append((r, start, size))

        if not candidates:
            return None

        # ratio 내림차순 → 최우선 후보 결정
        candidates.sort(key=lambda c: c[0], reverse=True)
        best_ratio, best_start, best_size = candidates[0]

        def _overlaps(s1: int, sz1: int, s2: int, sz2: int) -> bool:
            return s1 < s2 + sz2 and s2 < s1 + sz1

        # 최우선 영역과 겹치지 않는 첫 후보 = 진짜 경쟁 후보
        second_ratio: Optional[float] = None
        for r, st, sz in candidates[1:]:
            if not _overlaps(best_start, best_size, st, sz):
                second_ratio = r
                break

        # 유일성 판정 (겹치지 않는 차순위 후보 기준):
        #  - 동률(tie, 차 < TIE_EPSILON): 본문이 같은 두 블록 등 진짜 구별 불가
        #    → HIGH_CONFIDENCE 여도 ambiguous.
        #  - 그 외엔 최우선이 HIGH_CONFIDENCE 이상이면 적용, 아니면 마진 검사.
        gap = best_ratio - second_ratio if second_ratio is not None else 1.0
        is_tie = (
            second_ratio is not None
            and second_ratio >= self.fuzzy_threshold
            and gap < self.TIE_EPSILON
        )
        margin_fail = (
            second_ratio is not None
            and second_ratio >= self.fuzzy_threshold
            and gap < self.UNIQUENESS_MARGIN
        )
        if is_tie or (
            best_ratio < self.HIGH_CONFIDENCE_RATIO and margin_fail
        ):
            return (
                working,
                "ambiguous",
                self._format_diagnostic(
                    working, search,
                    kind=(
                        f"similar_ambiguous(best={best_ratio:.2f}, "
                        f"second={second_ratio:.2f})"
                    ),
                ),
            )

        # 매칭 구간의 문자 오프셋 계산 (work_lines 는 "\n" join 으로 무손실 복원)
        span_start = sum(len(l) for l in work_lines[:best_start]) + best_start
        block = "\n".join(work_lines[best_start:best_start + best_size])
        span_end = span_start + len(block)

        adjusted_replace = self._align_replace_indent(
            working_lf, span_start, search, replace,
        )
        new_lf = working_lf[:span_start] + adjusted_replace + working_lf[span_end:]
        # 원본이 CRLF 였다면 결과도 CRLF 로 복원
        if "\r\n" in working:
            new_lf = new_lf.replace("\n", "\r\n")
        return (new_lf, "similar", None)

    # ─── 공백 정규화 ──────────────────────────────────────────
    @classmethod
    def _normalize_text(cls, text: str) -> str:
        norm, _ = cls._normalize_with_mapping(text)
        return norm

    @classmethod
    def _normalize_with_mapping(cls, text: str) -> Tuple[str, List[int]]:
        """원본을 정규화하고, 정규화된 문자열 인덱스 → LF 변환 원본 인덱스 매핑을 만든다.

        정규화 규칙:
        - CRLF / CR → LF
        - 라인 끝 공백/탭 제거
        - 라인 안의 모든 공백/탭 연속을 1개의 공백으로 압축 (들여쓰기 포함)
        """
        text_lf = text.replace("\r\n", "\n").replace("\r", "\n")
        result_chars: List[str] = []
        mapping: List[int] = []

        n = len(text_lf)
        i = 0
        while i < n:
            line_end = text_lf.find("\n", i)
            if line_end == -1:
                line_end = n
            # 라인 끝 공백 trim 후의 본문 끝 위치
            body_end = line_end
            while body_end > i and text_lf[body_end - 1] in (" ", "\t"):
                body_end -= 1
            prev_space = False
            for j in range(i, body_end):
                ch = text_lf[j]
                if ch in (" ", "\t"):
                    if not prev_space:
                        result_chars.append(" ")
                        mapping.append(j)
                    prev_space = True
                else:
                    result_chars.append(ch)
                    mapping.append(j)
                    prev_space = False
            if line_end < n:
                result_chars.append("\n")
                mapping.append(line_end)
                i = line_end + 1
            else:
                i = n
        return "".join(result_chars), mapping

    def _apply_fuzzy(
        self,
        original: str,
        mapping: List[int],
        normalized: str,
        norm_search: str,
        search: str,
        replace: str,
    ) -> str:
        """정규화된 검색 결과로부터 원본 텍스트의 해당 영역을 교체."""
        idx = normalized.find(norm_search)
        if idx < 0:
            return original  # 안전망

        end = idx + len(norm_search)
        if not mapping:
            return original

        original_lf = original.replace("\r\n", "\n").replace("\r", "\n")
        start_orig = mapping[idx]
        end_orig = mapping[min(end - 1, len(mapping) - 1)] + 1

        # 들여쓰기 정렬 (FSD § 3.2.4)
        adjusted_replace = self._align_replace_indent(
            original_lf, start_orig, search, replace,
        )

        new_lf = (
            original_lf[:start_orig]
            + adjusted_replace
            + original_lf[end_orig:]
        )
        # 원본이 CRLF 였다면 결과도 CRLF 로 복원
        if "\r\n" in original:
            new_lf = new_lf.replace("\n", "\r\n")
        return new_lf

    @staticmethod
    def _align_replace_indent(
        original_lf: str, start_orig: int, search: str, replace: str
    ) -> str:
        """fuzzy 모드에서 REPLACE 들여쓰기를 원본 매칭 위치에 맞춰 시프트.

        delta = (원본 매칭 시작 라인의 들여쓰기 길이)
              - (SEARCH 첫 라인의 들여쓰기 길이)
        delta 만큼 REPLACE 의 모든 라인 앞에 공백을 추가/제거한다.
        """
        if not replace:
            return replace

        # 원본 매칭 시작 라인의 들여쓰기 추출
        line_start = original_lf.rfind("\n", 0, start_orig) + 1
        next_nl = original_lf.find("\n", line_start)
        if next_nl < 0:
            next_nl = len(original_lf)
        first_orig_line = original_lf[line_start:next_nl]
        orig_indent = first_orig_line[
            : len(first_orig_line) - len(first_orig_line.lstrip(" \t"))
        ]

        # SEARCH 첫 비-빈 라인의 들여쓰기 (CRLF 변환 후)
        search_lf = search.replace("\r\n", "\n").replace("\r", "\n")
        search_first = ""
        for line in search_lf.split("\n"):
            if line:
                search_first = line
                break
        search_indent = search_first[
            : len(search_first) - len(search_first.lstrip(" \t"))
        ]

        if orig_indent == search_indent:
            return replace

        delta = len(orig_indent) - len(search_indent)
        repl_lines = replace.split("\n")

        if delta > 0:
            prefix = orig_indent[: delta] if delta <= len(orig_indent) else " " * delta
            return "\n".join(
                (prefix + line) if line else line for line in repl_lines
            )

        # delta < 0: REPLACE 라인 앞에서 strip_n 만큼 공백 제거 (있을 때만)
        strip_n = -delta
        out_lines: List[str] = []
        for line in repl_lines:
            if not line:
                out_lines.append(line)
                continue
            stripped_lead = line[:strip_n]
            if all(c in (" ", "\t") for c in stripped_lead) and len(stripped_lead) == strip_n:
                out_lines.append(line[strip_n:])
            else:
                out_lines.append(line)
        return "\n".join(out_lines)

    # ─── 진단(diagnostic) ─────────────────────────────────────
    def _format_diagnostic(
        self, working: str, search: str, *, kind: str
    ) -> str:
        """매칭 실패 시 가장 가까운 스니펫을 라인 번호와 함께 반환."""
        snippet = self._nearest_snippet(working, search)
        out = f"{kind}\n{snippet}" if snippet else kind
        if len(out) > self.DIAGNOSTIC_MAX_CHARS:
            out = out[: self.DIAGNOSTIC_MAX_CHARS] + "…"
        # REP v1.1.033 — 반복 실패 → 정확 복사 또는 전문 재작성 유도
        if kind.startswith(("no_match", "similar_ambiguous", "multiple_matches")):
            out += (
                "\n💡 SEARCH 가 원본과 정확히 일치해야 합니다. 위 스니펫의 "
                "텍스트를 그대로 복사해 SEARCH 를 재작성하거나, 변경 범위가 "
                "크면 `@@@filename:` 전문 재작성(A-1)으로 전환하세요."
            )
        return out

    def _nearest_snippet(self, working: str, search: str) -> str:
        """SEARCH 의 첫 비-공백 라인과 가장 유사한 원본 라인을 찾아 ±5줄 반환."""
        if not working:
            return "(원본 비어있음)"

        search_lines = [
            ln for ln in search.splitlines() if ln.strip()
        ]
        if not search_lines:
            return ""
        anchor = search_lines[0].strip()

        working_lines = working.splitlines()
        best_idx = -1
        best_score = 0
        for i, line in enumerate(working_lines):
            score = self._line_similarity(line.strip(), anchor)
            if score > best_score:
                best_score = score
                best_idx = i

        ctx = self.SNIPPET_CONTEXT_LINES
        if best_idx < 0 or best_score == 0:
            # 토큰 매칭 실패 — 파일 시작 ±5 줄을 폴백으로 제공
            hi = min(len(working_lines), 2 * ctx + 1)
            return "\n".join(
                f"  L{i + 1:>4}: {working_lines[i]}" for i in range(hi)
            )

        lo = max(0, best_idx - ctx)
        hi = min(len(working_lines), best_idx + ctx + 1)
        out_lines = []
        for i in range(lo, hi):
            marker = ">>" if i == best_idx else "  "
            out_lines.append(f"{marker} L{i + 1:>4}: {working_lines[i]}")
        return "\n".join(out_lines)

    @staticmethod
    def _line_similarity(a: str, b: str) -> int:
        """두 문자열의 공통 토큰 수 (정규식 미사용)."""
        if not a or not b:
            return 0
        a_tokens = set(t for t in a.split() if t)
        b_tokens = set(t for t in b.split() if t)
        return len(a_tokens & b_tokens)
