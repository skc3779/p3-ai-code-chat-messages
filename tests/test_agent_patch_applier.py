"""
AgentPatchApplier Unit Tests (FSD v1.0.115)

T-111-01 ~ T-111-20: SEARCH/REPLACE 파싱·exact/fuzzy/ambiguous/no_match·
트랜잭셔널 적용·신규 파일·들여쓰기 정렬·path traversal 등.
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_patch_applier import AgentPatchApplier
from src.file_manager import FileManager


def _patch_payload(*pairs: str) -> str:
    """주어진 (search, replace) 쌍들을 합쳐 펜스 본문을 만든다."""
    out: list = []
    for i in range(0, len(pairs), 2):
        s, r = pairs[i], pairs[i + 1]
        out.append("<<<<<<< SEARCH")
        out.append(s)
        out.append("=======")
        out.append(r)
        out.append(">>>>>>> REPLACE")
    return "\n".join(out)


class TestAgentPatchApplier(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="patch_test_")
        self.fm = FileManager(self.tmp)
        self.applier = AgentPatchApplier(self.fm)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel: str, content: str) -> Path:
        """EOL 보존 모드(`newline=""`)로 파일을 쓴다 — 테스트 입력 결정성 확보."""
        p = Path(self.tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return p

    def _read(self, rel: str) -> str:
        """EOL 보존 모드로 파일을 읽는다."""
        with open(Path(self.tmp) / rel, "r", encoding="utf-8", newline="") as f:
            return f.read()

    # ─── T-111-01 ─────────────────────────────────────────
    def test_T111_01_exact_single_pair(self):
        """exact 매칭 — 정확 1회 → 적용."""
        self._write("a.py", "import os\nimport re\n")
        payload = _patch_payload(
            "import os\nimport re",
            "import os\nimport re\nimport json",
        )
        result = self.applier.apply("a.py", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(result.block_results[0].status, "exact")
        self.assertEqual(self._read("a.py"), "import os\nimport re\nimport json\n")

    # ─── T-111-02 ─────────────────────────────────────────
    def test_T111_02_no_match_disk_unchanged(self):
        original = "alpha\nbeta\ngamma\ndelta\n"
        self._write("a.py", original)
        payload = _patch_payload("zeta\nepsilon", "X")
        result = self.applier.apply("a.py", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertEqual(result.block_results[0].status, "no_match")
        self.assertIn("L", result.block_results[0].diagnostic or "")
        self.assertEqual(self._read("a.py"), original)

    # ─── T-111-03 ─────────────────────────────────────────
    def test_T111_03_ambiguous_two_matches(self):
        original = "X\nX\n"
        self._write("a.py", original)
        payload = _patch_payload("X", "Y")
        result = self.applier.apply("a.py", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertEqual(result.block_results[0].status, "ambiguous")
        self.assertIn("multiple_matches=2", result.block_results[0].diagnostic or "")
        self.assertEqual(self._read("a.py"), original)

    # ─── T-111-04 ─────────────────────────────────────────
    def test_T111_04_fuzzy_indent_only_difference(self):
        original = "    def foo():\n        return 1\n"
        self._write("a.py", original)
        payload = _patch_payload(
            "  def foo():\n      return 1",
            "  def foo():\n      return 2",
        )
        result = self.applier.apply("a.py", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(result.block_results[0].status, "fuzzy")
        # 원본의 4-space 들여쓰기에 정렬됨
        self.assertEqual(
            self._read("a.py"),
            "    def foo():\n        return 2\n",
        )

    # ─── T-111-05 ─────────────────────────────────────────
    def test_T111_05_crlf_original_lf_search(self):
        original = "line1\r\nline2\r\nline3\r\n"
        self._write("a.txt", original)
        payload = _patch_payload("line1\nline2", "lineA\nlineB")
        result = self.applier.apply("a.txt", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(result.block_results[0].status, "fuzzy")
        # 원본 EOL(CRLF) 유지
        self.assertEqual(self._read("a.txt"), "lineA\r\nlineB\r\nline3\r\n")

    # ─── T-111-06 ─────────────────────────────────────────
    def test_T111_06_three_blocks_all_succeed(self):
        original = "A\nB\nC\nD\nE\n"
        self._write("a.txt", original)
        payload = _patch_payload(
            "A", "A1",
            "C", "C1",
            "E", "E1",
        )
        result = self.applier.apply("a.txt", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(len(result.block_results), 3)
        self.assertEqual(self._read("a.txt"), "A1\nB\nC1\nD\nE1\n")

    # ─── T-111-07 ─────────────────────────────────────────
    def test_T111_07_three_blocks_second_ambiguous_rollback(self):
        original = "A\nDUP\nC\nDUP\n"
        self._write("a.txt", original)
        payload = _patch_payload(
            "A", "A1",
            "DUP", "DUPX",
            "C", "C1",
        )
        result = self.applier.apply("a.txt", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertEqual(len(result.block_results), 3)
        self.assertEqual(result.block_results[1].status, "ambiguous")
        # 디스크 미변경 (트랜잭셔널 롤백)
        self.assertEqual(self._read("a.txt"), original)

    # ─── T-111-08 ─────────────────────────────────────────
    def test_T111_08_empty_search_appends(self):
        self._write("a.txt", "head")  # no trailing \n
        payload = _patch_payload("", "tail")
        result = self.applier.apply("a.txt", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(result.block_results[0].status, "appended")
        self.assertEqual(self._read("a.txt"), "head\ntail")

    # ─── T-111-09 ─────────────────────────────────────────
    def test_T111_09_empty_search_creates_new_file(self):
        payload = _patch_payload("", "hello world\n")
        result = self.applier.apply("new.txt", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(self._read("new.txt"), "hello world\n")

    # ─── T-111-10 ─────────────────────────────────────────
    def test_T111_10_replace_empty_deletes_block(self):
        original = "before\nDELETE_ME\nafter\n"
        self._write("a.txt", original)
        payload = _patch_payload("DELETE_ME\n", "")
        result = self.applier.apply("a.txt", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(self._read("a.txt"), "before\nafter\n")

    # ─── T-111-11 ─────────────────────────────────────────
    def test_T111_11_perf_1mb_under_100ms(self):
        big = ("line_%05d\n" % i for i in range(80000))
        body = "".join(big)
        # 약 1MB 정도 (실제 크기는 약 880KB ~ 1MB)
        self._write("big.txt", body)
        payload = _patch_payload("line_00042", "line_42_PATCHED")
        t0 = time.monotonic()
        result = self.applier.apply("big.txt", payload, auto_approve=True)
        elapsed = time.monotonic() - t0
        self.assertTrue(result.success)
        # NFR-111-02 — 100ms 이내. CI 환경 변동을 고려해 500ms 까지 허용.
        self.assertLess(elapsed, 0.5, f"elapsed={elapsed:.3f}s")

    # ─── T-111-12 ─────────────────────────────────────────
    def test_T111_12_utf8_korean(self):
        original = "안녕하세요\n반갑습니다\n"
        self._write("ko.txt", original)
        payload = _patch_payload("안녕하세요", "안녕히가세요")
        result = self.applier.apply("ko.txt", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(self._read("ko.txt"), "안녕히가세요\n반갑습니다\n")

    # ─── T-111-13 ─────────────────────────────────────────
    def test_T111_13_regex_metacharacters_treated_literally(self):
        original = "(a*b[c])"
        self._write("a.txt", original)
        payload = _patch_payload("(a*b[c])", "REPLACED")
        result = self.applier.apply("a.txt", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(self._read("a.txt"), "REPLACED")

    # ─── T-111-14 ─────────────────────────────────────────
    def test_T111_14_path_traversal_rejected(self):
        payload = _patch_payload("a", "b")
        result = self.applier.apply("../etc/passwd", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertIn("경로", result.error or "")

    # ─── T-111-15 ─────────────────────────────────────────
    def test_T111_15_invalid_marker_count_rejected(self):
        # 6개의 `<` — 잘못된 마커
        bad_payload = "<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE\n"
        self._write("a.txt", "foo\n")
        result = self.applier.apply("a.txt", bad_payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertIn("invalid SEARCH marker", result.error or "")

    # ─── T-111-16 ─────────────────────────────────────────
    def test_T111_16_unclosed_block_rejected(self):
        # REPLACE 마커가 없음
        bad_payload = "<<<<<<< SEARCH\nfoo\n=======\nbar\n"
        self._write("a.txt", "foo\n")
        result = self.applier.apply("a.txt", bad_payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertIn("unclosed", result.error or "")

    # ─── T-111-17 ─────────────────────────────────────────
    def test_T111_17_trailing_newline_difference_fuzzy(self):
        original = "foo\nbar\nbaz\n"
        self._write("a.txt", original)
        # SEARCH 끝에 줄바꿈 + 빈 라인 (원본은 trailing 공백 없음)
        payload = "<<<<<<< SEARCH\nbar  \n=======\nBAR\n>>>>>>> REPLACE\n"
        result = self.applier.apply("a.txt", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(result.block_results[0].status, "fuzzy")
        self.assertEqual(self._read("a.txt"), "foo\nBAR\nbaz\n")

    # ─── T-111-18 ─────────────────────────────────────────
    def test_T111_18_io_error_disk_unchanged(self):
        # 쓰기 단계에서 IOError — applier 의 _write_preserving_eol 을 monkey-patch
        self._write("a.txt", "foo\n")
        original = "foo\n"
        self.applier._write_preserving_eol = lambda p, c: False
        try:
            payload = _patch_payload("foo", "bar")
            result = self.applier.apply("a.txt", payload, auto_approve=True)
        finally:
            del self.applier._write_preserving_eol
        self.assertFalse(result.success)
        self.assertIn("쓰기 실패", result.error or "")
        self.assertEqual(self._read("a.txt"), original)

    # ─── T-111-19 ─────────────────────────────────────────
    def test_T111_19_partial_failure_results_visible(self):
        original = "A\nDUP\nDUP\n"
        self._write("a.txt", original)
        payload = _patch_payload(
            "A", "A1",         # exact
            "DUP", "X",        # ambiguous
        )
        result = self.applier.apply("a.txt", payload, auto_approve=True)
        self.assertFalse(result.success)
        # 두 블록 결과 모두 보고됨
        self.assertEqual(len(result.block_results), 2)
        self.assertEqual(result.block_results[0].status, "exact")
        self.assertEqual(result.block_results[1].status, "ambiguous")
        # 디스크 미변경
        self.assertEqual(self._read("a.txt"), original)

    # ─── T-111-20 ─────────────────────────────────────────
    def test_T111_20_two_calls_same_file_sequential(self):
        self._write("a.txt", "foo\nbar\n")
        # 1st call
        r1 = self.applier.apply(
            "a.txt", _patch_payload("foo", "FOO"), auto_approve=True,
        )
        self.assertTrue(r1.success)
        # 2nd call uses post-1st-call state
        r2 = self.applier.apply(
            "a.txt", _patch_payload("FOO", "F0"), auto_approve=True,
        )
        self.assertTrue(r2.success)
        self.assertEqual(self._read("a.txt"), "F0\nbar\n")


class TestApprovalFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="patch_app_")
        self.fm = FileManager(self.tmp)
        self.applier = AgentPatchApplier(self.fm)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel: str, content: str):
        p = Path(self.tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def test_user_denied_no_disk_change(self):
        self._write("a.txt", "foo\n")
        payload = _patch_payload("foo", "bar")
        result = self.applier.apply(
            "a.txt", payload, auto_approve=False, on_first_approval=lambda: False,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "사용자 거부")
        self.assertEqual(
            (Path(self.tmp) / "a.txt").read_text(encoding="utf-8"),
            "foo\n",
        )

    def test_user_approved_applies(self):
        self._write("a.txt", "foo\n")
        payload = _patch_payload("foo", "bar")
        result = self.applier.apply(
            "a.txt", payload, auto_approve=False, on_first_approval=lambda: True,
        )
        self.assertTrue(result.success)
        self.assertEqual(
            (Path(self.tmp) / "a.txt").read_text(encoding="utf-8"),
            "bar\n",
        )


if __name__ == "__main__":
    unittest.main()
