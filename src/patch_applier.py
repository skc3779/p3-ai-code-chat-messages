"""
PatchApplier (FSD v1.0.115, FSD v1.1.061 중립 모듈 이전)

```patch:<path>``` 블록을 SEARCH/REPLACE 방식으로 적용한다.
컨텍스트 품질검사(QC, context_processor) 등에서 공용으로 사용한다.

- 한 펜스에 N 개의 SEARCH/REPLACE 쌍 허용
- exact / fuzzy / appended / ambiguous / no_match 5 가지 상태 보고
- 트랜잭셔널: 한 블록이라도 실패하면 디스크에 쓰지 않음
- 빈 SEARCH 는 파일 끝 append 또는 신규 파일 생성으로 동작
- 정규식 미사용 — 리터럴 매칭 보장 (NFR-111-04)
- workspace 밖 경로(traversal)는 거부
"""

import difflib
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
    status: str                    # "exact" | "fuzzy" | "appended" | "ambiguous" | "no_match"
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


@dataclass
class PatchPlan:
    """compute() 산출물 — 디스크 미변경 dry-run 결과 (FSD v1.1.062 §3.4, FR-062-19).

    승인 워크플로(preview → confirm → commit)의 중간 표현. commit() 의 입력.
    """
    rel_path: str
    computed_text: Optional[str]                       # 적용 결과 전문 (실패 시 None)
    block_results: List[BlockResult] = field(default_factory=list)
    success: bool = False                              # transactional 판정
    error: Optional[str] = None                        # 파싱/IO/경로 오류
    before_text: str = ""                              # 현재 디스크 본문 (없으면 '')
    diff: str = ""                                     # unified diff (before→after)
    existed: bool = False                              # 적용 대상 파일이 이미 존재했는지
    is_full_file: bool = False                         # compute_full_file 경로 여부


class PatchApplier:
    """SEARCH/REPLACE 패치 적용기.

    의존성: FileManager (read_file / write_file / workspace_dir)
    """

    SNIPPET_CONTEXT_LINES = 5
    DIAGNOSTIC_MAX_CHARS = 500

    def __init__(self, file_manager):
        self.file_manager = file_manager

    # ─── compute (dry-run) ────────────────────────────────────
    def compute(self, relative_path: str, payload: str) -> PatchPlan:
        """패치 본문을 매칭·적용해 결과를 산출하되 **디스크는 변경하지 않는다**.

        FSD v1.1.062 §3.4 / FR-062-19. cascade(exact→fuzzy→similar) 수행 후
        결과 문자열·block statuses·transactional 판정·unified diff 만 만든다.

        Args:
            relative_path: 워크스페이스 상대 경로
            payload: ```patch:...``` 펜스의 본문 (마커 포함)
        """
        # ── 1) 경로 정규화 + traversal 차단 ──
        try:
            abs_path = self._safe_path(relative_path)
        except IOError as e:
            return PatchPlan(
                rel_path=relative_path, computed_text=None,
                success=False, error=f"잘못된 경로: {e}",
            )

        # ── 2) 펜스 본문 파싱 ──
        try:
            blocks = self.parse_blocks(payload)
        except ValueError as e:
            return PatchPlan(
                rel_path=relative_path, computed_text=None,
                success=False, error=f"패치 본문 파싱 실패: {e}",
            )
        if not blocks:
            return PatchPlan(
                rel_path=relative_path, computed_text=None,
                success=False, error="patch 빈 본문",
            )

        # ── 3) 원본 읽기 (EOL 보존) ──
        existed = abs_path.exists()
        if existed:
            original = self._read_preserving_eol(abs_path)
            if original is None:
                return PatchPlan(
                    rel_path=relative_path, computed_text=None,
                    success=False, existed=True,
                    block_results=[],
                    error=f"파일 읽기 실패: {relative_path}",
                )
        else:
            # 신규 파일 — 모든 블록이 빈 SEARCH 여야 함
            if not all(b.search == "" for b in blocks):
                return PatchPlan(
                    rel_path=relative_path, computed_text=None,
                    success=False, existed=False,
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
            r.status in ("exact", "fuzzy", "appended") for r in results
        )

        if not all_ok:
            # 부분 실패 — transactional 폐기, 디스크 미변경
            return PatchPlan(
                rel_path=relative_path, computed_text=None,
                success=False, existed=existed,
                block_results=results, before_text=original,
            )

        diff = self._unified_diff(original, working, relative_path, existed)
        return PatchPlan(
            rel_path=relative_path, computed_text=working,
            success=True, existed=existed,
            block_results=results, before_text=original, diff=diff,
        )

    def compute_full_file(self, relative_path: str, new_text: str) -> PatchPlan:
        """파일 전문(A-1) 경로의 dry-run 결과 — before(현 디스크) vs after diff.

        SEARCH/REPLACE 와 무관하게 항상 success=True (전문 덮어쓰기). 디스크 미변경.
        """
        try:
            abs_path = self._safe_path(relative_path)
        except IOError as e:
            return PatchPlan(
                rel_path=relative_path, computed_text=None,
                success=False, error=f"잘못된 경로: {e}", is_full_file=True,
            )
        existed = abs_path.exists()
        before = ""
        if existed:
            before = self._read_preserving_eol(abs_path) or ""
        diff = self._unified_diff(before, new_text, relative_path, existed)
        return PatchPlan(
            rel_path=relative_path, computed_text=new_text,
            success=True, existed=existed, before_text=before,
            diff=diff, is_full_file=True,
        )

    # ─── commit (디스크 반영) ──────────────────────────────────
    def commit(self, plan: PatchPlan) -> PatchResult:
        """승인된 PatchPlan 을 실제 디스크에 원자적으로 기록한다.

        plan.success 가 False 면 무변경 PatchResult(success=False).
        """
        total = len(plan.block_results)
        if not plan.success or plan.computed_text is None:
            return PatchResult(
                success=False, applied_count=0, total_count=total,
                block_results=plan.block_results, error=plan.error,
            )

        try:
            abs_path = self._safe_path(plan.rel_path)
        except IOError as e:
            return PatchResult(
                success=False, applied_count=0, total_count=total,
                block_results=plan.block_results, error=f"잘못된 경로: {e}",
            )

        try:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return PatchResult(
                success=False, applied_count=0, total_count=total,
                block_results=plan.block_results,
                error=f"디렉터리 생성 실패: {e}",
            )

        ok = self._write_preserving_eol(abs_path, plan.computed_text)
        if not ok:
            return PatchResult(
                success=False, applied_count=0, total_count=total,
                block_results=plan.block_results, error="디스크 쓰기 실패",
            )

        return PatchResult(
            success=True, applied_count=total, total_count=total,
            block_results=plan.block_results, new_text=plan.computed_text,
        )

    @staticmethod
    def _unified_diff(
        before: str, after: str, rel_path: str, existed: bool
    ) -> str:
        """before→after 통합 diff. EOL 은 LF 로 정규화해 비교(노이즈 억제)."""
        b_lf = before.replace("\r\n", "\n").replace("\r", "\n")
        a_lf = after.replace("\r\n", "\n").replace("\r", "\n")
        if b_lf == a_lf:
            return ""
        fromfile = f"a/{rel_path}" if existed else "/dev/null"
        tofile = f"b/{rel_path}"
        diff = difflib.unified_diff(
            b_lf.splitlines(keepends=False),
            a_lf.splitlines(keepends=False),
            fromfile=fromfile, tofile=tofile, lineterm="",
        )
        return "\n".join(diff)

    # ─── 진입 (compute + commit wrapper) ──────────────────────
    def apply(
        self,
        relative_path: str,
        payload: str,
        *,
        auto_approve: bool = False,
        on_first_approval: Optional[Callable[[], bool]] = None,
    ) -> PatchResult:
        """패치 본문을 적용한다 (compute + commit 묶음 wrapper).

        FSD v1.1.062 §3.4: 내부적으로 compute()(dry-run) → 승인 → commit() 로
        분해되었으나 외부 시그니처·반환·동작은 기존과 동일하다. QC·디스패처 등
        기존 호출부 무회귀가 최우선.

        Args:
            relative_path: 워크스페이스 상대 경로
            payload: ```patch:...``` 펜스의 본문 (마커 포함)
            auto_approve: True 면 사용자 승인 프롬프트 생략
            on_first_approval: auto_approve=False 일 때 호출 — True 반환 시 적용
        """
        plan = self.compute(relative_path, payload)

        # 매칭 실패/파싱 실패 — 기존 apply 와 동일한 PatchResult 형태로 반환
        if not plan.success:
            return PatchResult(
                success=False,
                applied_count=0,
                total_count=len(plan.block_results),
                block_results=plan.block_results,
                error=plan.error,
            )

        # 승인 검사 (compute 성공 후에만 — 기존 동작 보존)
        if not auto_approve and on_first_approval is not None:
            try:
                approved = bool(on_first_approval())
            except Exception:
                approved = False
            if not approved:
                return PatchResult(
                    success=False,
                    applied_count=0,
                    total_count=len(plan.block_results),
                    block_results=plan.block_results,
                    error="사용자 거부",
                )

        return self.commit(plan)

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

        # no_match
        return (
            working,
            "no_match",
            self._format_diagnostic(working, search, kind="no_match"),
        )

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
