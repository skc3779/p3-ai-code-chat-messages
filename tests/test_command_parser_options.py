"""tests/test_command_parser_options.py

FSD v1.0.123 § 9.1 — parse_command_options 단위 테스트
"""

import unittest

from src.cli_input import parse_command_options


class TestParseCommandOptions(unittest.TestCase):
    """parse_command_options() 헬퍼 단위 테스트"""

    # ─── /auto_context -qc 별칭 ──────────────────────────────
    _QC_ALIASES = {
        "-qc": "quality_check",
        "--quality-check": "quality_check",
    }

    # ─── /context -nt 별칭 ──────────────────────────────────
    _NT_ALIASES = {
        "-nt": "no_tree",
        "--no-tree": "no_tree",
    }

    # ─── TC-C-01: 옵션 없이 패턴만 ──────────────────────────
    def test_no_options(self):
        """TC-C-01: 옵션 없이 순수 패턴만 전달"""
        opts, remaining = parse_command_options("src/*.py 질문", self._QC_ALIASES)
        self.assertEqual(opts, set())
        self.assertEqual(remaining, "src/*.py 질문")

    # ─── TC-C-02: -qc 단독 ──────────────────────────────────
    def test_qc_option(self):
        """TC-C-02: -qc 옵션만 사용"""
        opts, remaining = parse_command_options("-qc src/*.py 질문", self._QC_ALIASES)
        self.assertIn("quality_check", opts)
        self.assertEqual(remaining, "src/*.py 질문")

    # ─── TC-C-03: --quality-check 긴 이름 ────────────────────
    def test_qc_long_name(self):
        """TC-C-03: --quality-check 장이름 별칭"""
        opts, remaining = parse_command_options("--quality-check src/*.py", self._QC_ALIASES)
        self.assertIn("quality_check", opts)
        self.assertEqual(remaining, "src/*.py")

    # ─── TC-C-04: -nt 단독 ──────────────────────────────────
    def test_nt_option(self):
        """TC-C-04: -nt 옵션만 사용"""
        opts, remaining = parse_command_options("-nt src/*.py 질문", self._NT_ALIASES)
        self.assertIn("no_tree", opts)
        self.assertEqual(remaining, "src/*.py 질문")

    # ─── TC-C-05: --no-tree 긴 이름 ─────────────────────────
    def test_nt_long_name(self):
        """TC-C-05: --no-tree 장이름 별칭"""
        opts, remaining = parse_command_options("--no-tree [src/*.py] 질문", self._NT_ALIASES)
        self.assertIn("no_tree", opts)
        self.assertEqual(remaining, "[src/*.py] 질문")

    # ─── TC-C-06: 대괄호 패턴 시작 → 옵션 파싱 중단 ─────────
    def test_bracket_pattern_stops_parsing(self):
        """TC-C-06: [ 로 시작하는 토큰은 옵션이 아닌 위치 인자"""
        opts, remaining = parse_command_options("[src/*.py] 질문", self._QC_ALIASES)
        self.assertEqual(opts, set())
        self.assertEqual(remaining, "[src/*.py] 질문")

    # ─── TC-C-07: 알 수 없는 옵션 → ValueError ──────────────
    def test_unknown_option_raises(self):
        """TC-C-07: 알 수 없는 옵션은 ValueError"""
        with self.assertRaises(ValueError):
            parse_command_options("-xyz src/*.py", self._QC_ALIASES)

    # ─── TC-C-08: -- 명시적 종료자 ──────────────────────────
    def test_double_dash_terminates(self):
        """TC-C-08: -- 뒤의 -qc 는 옵션이 아닌 위치 인자"""
        opts, remaining = parse_command_options("-- -qc src/*.py", self._QC_ALIASES)
        self.assertEqual(opts, set())
        self.assertEqual(remaining, "-qc src/*.py")

    # ─── TC-C-09: 빈 인자 ───────────────────────────────────
    def test_empty_args(self):
        """TC-C-09: 빈 문자열"""
        opts, remaining = parse_command_options("", self._QC_ALIASES)
        self.assertEqual(opts, set())
        self.assertEqual(remaining, "")

    # ─── TC-C-10: 공백만 있는 인자 ──────────────────────────
    def test_whitespace_only(self):
        """TC-C-10: 공백만 있는 문자열"""
        opts, remaining = parse_command_options("   ", self._QC_ALIASES)
        self.assertEqual(opts, set())
        self.assertEqual(remaining, "   ")

    # ─── TC-C-11: 옵션만 (패턴 없음) ────────────────────────
    def test_option_only_no_pattern(self):
        """TC-C-11: 옵션만 있고 패턴 없음"""
        opts, remaining = parse_command_options("-qc", self._QC_ALIASES)
        self.assertIn("quality_check", opts)
        self.assertEqual(remaining, "")


if __name__ == "__main__":
    unittest.main()
