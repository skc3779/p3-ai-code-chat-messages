"""
AgentPatchApplier 유사도 매칭 Unit Tests (REP v1.1.033)

T-033-01 ~ T-033-12: difflib 기반 similar tier — content drift 허용,
임계값/유일성 마진, env 토글, 들여쓰기 정렬, CRLF 보존, 진단 메시지,
exact/fuzzy 우선순위(회귀 방지).

실행: python -m unittest tests.test_agent_patch_similarity -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_patch_applier import AgentPatchApplier
from src.file_manager import FileManager


def _patch_payload(*pairs: str) -> str:
    out: list = []
    for i in range(0, len(pairs), 2):
        s, r = pairs[i], pairs[i + 1]
        out.append("<<<<<<< SEARCH")
        out.append(s)
        out.append("=======")
        out.append(r)
        out.append(">>>>>>> REPLACE")
    return "\n".join(out)


# 긴 파일을 흉내 내는 헬퍼 — 함수 N개를 가진 모듈
def _long_module(n: int = 40) -> str:
    lines = ["import os", "import sys", ""]
    for i in range(n):
        lines.append(f"def func_{i}(a, b):")
        lines.append(f"    # 함수 {i} 의 설명")
        lines.append(f"    result = a + b + {i}")
        lines.append(f"    return result")
        lines.append("")
    return "\n".join(lines)


class TestAgentPatchSimilarity(unittest.TestCase):

    def setUp(self):
        # env 격리 — 각 테스트가 자체 설정으로 applier 를 생성
        self._saved_env = {
            k: os.environ.get(k)
            for k in (
                "AGENT_PATCH_SIMILARITY",
                "AGENT_PATCH_FUZZY_THRESHOLD",
                "AGENT_PATCH_FUZZY_FLEX",
            )
        }
        for k in self._saved_env:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="patch_sim_test_")
        self.fm = FileManager(self.tmp)
        self.applier = AgentPatchApplier(self.fm)

    def tearDown(self):
        import shutil
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel: str, content: str) -> Path:
        p = Path(self.tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return p

    def _read(self, rel: str) -> str:
        with open(Path(self.tmp) / rel, "r", encoding="utf-8", newline="") as f:
            return f.read()

    # ─── T-033-01 — content drift 1줄 차이 → similar 적용 ──────
    def test_T033_01_content_drift_applies_similar(self):
        """SEARCH 가 주석 한 줄 누락(원본과 미세하게 다름)이어도 similar 로 적용."""
        original = (
            "def calc(a, b):\n"
            "    # 합을 계산한다\n"
            "    total = a + b\n"
            "    return total\n"
        )
        self._write("m.py", original)
        # LLM 이 주석을 빠뜨린 SEARCH (exact/fuzzy 로는 매칭 실패)
        payload = _patch_payload(
            "def calc(a, b):\n"
            "    total = a + b\n"
            "    return total",
            "def calc(a, b):\n"
            "    total = a + b\n"
            "    return total * 2",
        )
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertTrue(result.success, msg=result.block_results)
        self.assertEqual(result.block_results[0].status, "similar")
        self.assertIn("return total * 2", self._read("m.py"))
        # 원본 주석은 보존되지 않을 수 있으나(블록 전체 교체), 결과는 유효한 코드
        self.assertIn("def calc(a, b):", self._read("m.py"))

    # ─── T-033-02 — 임계값 미만 → no_match (오적용 방지) ───────
    def test_T033_02_below_threshold_no_match(self):
        """유사도가 임계값 미만이면 적용하지 않고 no_match."""
        self._write("m.py", "def alpha():\n    return 1\n")
        payload = _patch_payload(
            "def completely_different_function(x, y, z):\n"
            "    print('nothing alike at all')\n"
            "    return x * y * z",
            "REPLACED",
        )
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertEqual(result.block_results[0].status, "no_match")

    # ─── T-033-03 — 유일성 마진 위반 → ambiguous ──────────────
    def test_T033_03_two_similar_blocks_ambiguous(self):
        """거의 동일한 두 블록이 있고 SEARCH 가 둘 다와 비슷하면 ambiguous."""
        original = (
            "def handler_a():\n"
            "    value = compute(1)\n"
            "    return value\n"
            "\n"
            "def handler_b():\n"
            "    value = compute(1)\n"
            "    return value\n"
        )
        self._write("m.py", original)
        # 두 블록 모두와 높은 유사도를 갖는 SEARCH
        payload = _patch_payload(
            "def handler_x():\n"
            "    value = compute(1)\n"
            "    return value",
            "REPLACED",
        )
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertEqual(result.block_results[0].status, "ambiguous")
        # 디스크 미변경 (트랜잭셔널)
        self.assertEqual(self._read("m.py"), original)

    # ─── T-033-04 — env 로 비활성화 시 similar 미동작 ─────────
    def test_T033_04_disabled_via_env(self):
        """AGENT_PATCH_SIMILARITY=0 이면 content drift 는 no_match."""
        os.environ["AGENT_PATCH_SIMILARITY"] = "0"
        applier = AgentPatchApplier(self.fm)
        self._write("m.py", "def calc(a, b):\n    # 주석\n    return a + b\n")
        payload = _patch_payload(
            "def calc(a, b):\n    return a + b",  # 주석 누락
            "def calc(a, b):\n    return a - b",
        )
        result = applier.apply("m.py", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertEqual(result.block_results[0].status, "no_match")

    # ─── T-033-05 — 임계값 상향 시 경계 동작 ──────────────────
    def test_T033_05_threshold_override_blocks_low_ratio(self):
        """임계값을 0.99 로 올리면 약한 유사도는 적용되지 않는다."""
        os.environ["AGENT_PATCH_FUZZY_THRESHOLD"] = "0.99"
        applier = AgentPatchApplier(self.fm)
        original = (
            "def calc(a, b):\n"
            "    # 합을 계산한다\n"
            "    total = a + b\n"
            "    return total\n"
        )
        self._write("m.py", original)
        payload = _patch_payload(
            "def calc(a, b):\n    total = a + b\n    return total",
            "def calc(a, b):\n    total = a + b\n    return total + 1",
        )
        result = applier.apply("m.py", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertEqual(result.block_results[0].status, "no_match")

    # ─── T-033-06 — 긴 파일에서 정확한 함수만 교체 ────────────
    def test_T033_06_long_file_targets_correct_block(self):
        """40개 함수 모듈에서 drift 있는 SEARCH 가 올바른 함수만 교체."""
        self._write("big.py", _long_module(40))
        # func_17 을 노린다. 주석을 살짝 바꿔 drift 유발.
        payload = _patch_payload(
            "def func_17(a, b):\n"
            "    # 함수 17 설명\n"            # 원본: "# 함수 17 의 설명"
            "    result = a + b + 17\n"
            "    return result",
            "def func_17(a, b):\n"
            "    # 함수 17 (개선됨)\n"
            "    result = a * b + 17\n"
            "    return result",
        )
        result = self.applier.apply("big.py", payload, auto_approve=True)
        self.assertTrue(result.success, msg=result.block_results)
        self.assertEqual(result.block_results[0].status, "similar")
        new = self._read("big.py")
        self.assertIn("result = a * b + 17", new)
        # 인접 함수는 영향 없음
        self.assertIn("result = a + b + 16", new)
        self.assertIn("result = a + b + 18", new)

    # ─── T-033-07 — exact 우선 (회귀 방지) ────────────────────
    def test_T033_07_exact_still_preferred(self):
        """정확히 일치하면 similar 가 아니라 exact 로 보고."""
        self._write("m.py", "x = 1\ny = 2\n")
        payload = _patch_payload("x = 1\ny = 2", "x = 10\ny = 20")
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(result.block_results[0].status, "exact")

    # ─── T-033-08 — fuzzy(공백) 우선 (회귀 방지) ──────────────
    def test_T033_08_whitespace_fuzzy_still_preferred(self):
        """공백만 다르면 similar 가 아니라 fuzzy 로 보고."""
        self._write("m.py", "def f():\n    return    1\n")
        payload = _patch_payload("def f():\n    return 1", "def f():\n    return 2")
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertTrue(result.success)
        self.assertEqual(result.block_results[0].status, "fuzzy")

    # ─── T-033-09 — CRLF 보존 ─────────────────────────────────
    def test_T033_09_crlf_preserved_on_similar(self):
        """CRLF 원본은 similar 적용 후에도 CRLF 유지."""
        original = (
            "def calc(a, b):\r\n"
            "    # 주석\r\n"
            "    total = a + b\r\n"
            "    return total\r\n"
        )
        self._write("m.py", original)
        payload = _patch_payload(
            "def calc(a, b):\n    total = a + b\n    return total",
            "def calc(a, b):\n    total = a + b\n    return total + 1",
        )
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertTrue(result.success, msg=result.block_results)
        self.assertEqual(result.block_results[0].status, "similar")
        raw = (Path(self.tmp) / "m.py").read_bytes()
        expected = (
            b"def calc(a, b):\r\n"
            b"    total = a + b\r\n"
            b"    return total + 1\r\n"
        )
        self.assertEqual(raw, expected)
        self.assertNotIn(b"\r\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertNotIn(b"\r", raw.replace(b"\r\n", b""))

    # ─── T-033-10 — 진단 메시지에 전문 재작성 유도 포함 ───────
    def test_T033_10_no_match_diagnostic_has_escalation_hint(self):
        """no_match 진단에 A-1 전문 재작성 전환 안내가 포함된다."""
        self._write("m.py", "def alpha():\n    return 1\n")
        payload = _patch_payload(
            "def totally_unrelated(p, q, r):\n        raise NotImplementedError()",
            "X",
        )
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertFalse(result.success)
        diag = result.block_results[0].diagnostic or ""
        self.assertIn("filename", diag)  # @@@filename: 전환 안내

    # ─── T-033-11 — 들여쓰기 정렬 (similar) ───────────────────
    def test_T033_11_similar_aligns_indent(self):
        """원본 들여쓰기에 맞춰 REPLACE 들여쓰기가 정렬된다."""
        original = (
            "class C:\n"
            "    def m(self):\n"
            "        a = 1\n"
            "        b = 2\n"
            "        c = 3\n"
            "        d = 4\n"
            "        e = 5\n"
            "        f = 6\n"
            "        g = 7\n"
            "        h = 8\n"
            "        return a + b + c + d + e + f + g + h\n"
        )
        self._write("m.py", original)
        payload = _patch_payload(
            "def m(self):\n"
            "    a = 1\n    b = 2\n    c = 3\n    d = 4\n"
            "    e = 5\n    f = 60\n    g = 7\n    h = 8\n"
            "    return a + b + c + d + e + f + g + h",
            "def m(self):\n"
            "    a = 10\n    b = 2\n    c = 3\n    d = 4\n"
            "    e = 5\n    f = 6\n    g = 7\n    h = 8\n"
            "    return a + b + c + d + e + f + g + h",
        )
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertTrue(result.success, msg=result.block_results)
        self.assertEqual(result.block_results[0].status, "similar")
        new = self._read("m.py")
        self.assertIn("    def m(self):", new)
        self.assertIn("        a = 10", new)
        self.assertIn("        return a + b + c + d + e + f + g + h", new)

    def test_T033_13_high_confidence_wins_over_close_runner_up(self):
        """best>=.95 and .01<=gap<.05 selects the closest non-tied block."""
        import difflib

        best = (
            "def target():\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n"
            "    e = 5\n    f = 6\n    g = 7\n    h = 8\n"
            "    return a+b+c+d+e+f+g+h"
        )
        second = best.replace("def target():", "def target_two():").replace("    e = 5", "    e = 50")
        search = best.replace("    f = 6", "    f = 60")
        best_ratio = difflib.SequenceMatcher(None, search, best, autojunk=False).ratio()
        second_ratio = difflib.SequenceMatcher(None, search, second, autojunk=False).ratio()
        self.assertGreaterEqual(best_ratio, self.applier.HIGH_CONFIDENCE_RATIO)
        self.assertGreaterEqual(best_ratio - second_ratio, self.applier.TIE_EPSILON)
        self.assertLess(best_ratio - second_ratio, self.applier.UNIQUENESS_MARGIN)

        self._write("m.py", best + "\n\n" + second + "\n")
        result = self.applier.apply(
            "m.py", _patch_payload(search, best.replace("    a = 1", "    a = 10")), auto_approve=True
        )
        self.assertTrue(result.success, msg=result.block_results)
        self.assertEqual(result.block_results[0].status, "similar")
        new = self._read("m.py")
        self.assertIn("def target():\n    a = 10", new)
        self.assertIn("def target_two():\n    a = 1", new)

    def test_T033_14_invalid_threshold_values_use_default(self):
        for value in ("nan", "inf", "-0.1", "1.1", "not-a-number"):
            with self.subTest(value=value):
                os.environ["AGENT_PATCH_FUZZY_THRESHOLD"] = value
                self.assertEqual(AgentPatchApplier(self.fm).fuzzy_threshold, 0.85)

    def test_T033_15_invalid_flex_values_use_default(self):
        for value in ("-1", "21", "nan", "not-a-number"):
            with self.subTest(value=value):
                os.environ["AGENT_PATCH_FUZZY_FLEX"] = value
                self.assertEqual(AgentPatchApplier(self.fm).fuzzy_flex, 2)

    def test_T033_16_zero_threshold_single_candidate_is_not_sentinel_tie(self):
        os.environ["AGENT_PATCH_FUZZY_THRESHOLD"] = "0"
        os.environ["AGENT_PATCH_FUZZY_FLEX"] = "0"
        applier = AgentPatchApplier(self.fm)
        self._write("m.py", "alpha = 1\n")
        result = applier.apply(
            "m.py",
            _patch_payload("alpha = 2", "alpha = 3"),
            auto_approve=True,
        )
        self.assertTrue(result.success, msg=result.block_results)
        self.assertEqual(result.block_results[0].status, "similar")

    # ─── T-033-12 — 트랜잭셔널: 한 블록 실패 시 전체 미적용 ───
    def test_T033_12_transactional_on_mixed(self):
        """두 블록 중 하나가 no_match 면 디스크 미변경."""
        original = "def a():\n    return 1\n\ndef b():\n    return 2\n"
        self._write("m.py", original)
        payload = _patch_payload(
            "def a():\n    return 1", "def a():\n    return 11",      # 적용 가능
            "def zzz_nonexistent(x):\n    return x * 999", "X",       # 실패
        )
        result = self.applier.apply("m.py", payload, auto_approve=True)
        self.assertFalse(result.success)
        self.assertEqual(self._read("m.py"), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
