"""
ResponseParser Overwrite 단위 테스트

FSD v1.0.103: T-103-01 ~ T-103-06
  - auto_overwrite=False (기본) : 기존 파일 → 덮어쓰기 확인 프롬프트 (대화형)
  - auto_overwrite=True         : 기존 파일 → 프롬프트 없이 즉시 덮어쓰기 (Bypass)
"""

import sys
import unittest
import tempfile
import shutil
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.response_parser import ResponseParser
from src.file_manager import FileManager


SINGLE_FILE_RESPONSE = """\
```filename:target.py
new_content = 42
```
"""


class TestResponseParserOverwrite(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.file_manager = FileManager(self.temp_dir)
        self.parser = ResponseParser(self.file_manager)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── T-103-01: 신규 파일, auto_overwrite=False ──────────────────
    def test_T103_01_new_file_no_overwrite_flag(self):
        """T-103-01: 신규 파일 저장 — auto_overwrite=False, 프롬프트 없이 생성됨"""
        saved = self.parser.parse_and_save(SINGLE_FILE_RESPONSE)
        self.assertEqual(saved, ["target.py"])
        self.assertEqual((self.temp_dir / "target.py").read_text(encoding="utf-8"), "new_content = 42")

    # ── T-103-02: 기존 파일 + auto_overwrite=False + 'y' 입력 ──────
    def test_T103_02_existing_file_user_confirms_overwrite(self):
        """T-103-02: 기존 파일, 사용자가 'y' 입력 → 덮어쓰기 성공"""
        (self.temp_dir / "target.py").write_text("old", encoding="utf-8")

        with patch("builtins.input", return_value="y"):
            saved = self.parser.parse_and_save(SINGLE_FILE_RESPONSE)

        self.assertEqual(saved, ["target.py"])
        self.assertEqual((self.temp_dir / "target.py").read_text(encoding="utf-8"), "new_content = 42")

    # ── T-103-03: 기존 파일 + auto_overwrite=False + 'n' 입력 ──────
    def test_T103_03_existing_file_user_denies_overwrite(self):
        """T-103-03: 기존 파일, 사용자가 'n' 입력 → 건너뛰기, 내용 보존"""
        original = "keep_this"
        (self.temp_dir / "target.py").write_text(original, encoding="utf-8")

        with patch("builtins.input", return_value="n"):
            saved = self.parser.parse_and_save(SINGLE_FILE_RESPONSE)

        self.assertEqual(saved, [])
        self.assertEqual((self.temp_dir / "target.py").read_text(encoding="utf-8"), original)

    # ── T-103-04: 기존 파일 + auto_overwrite=False + EOFError ───────
    def test_T103_04_existing_file_eof_skips(self):
        """T-103-04: stdin 비활성(EOFError) → 건너뛰기, 내용 보존"""
        original = "keep_this"
        (self.temp_dir / "target.py").write_text(original, encoding="utf-8")

        with patch("builtins.input", side_effect=EOFError):
            with patch("builtins.print"):
                saved = self.parser.parse_and_save(SINGLE_FILE_RESPONSE)

        self.assertEqual(saved, [])
        self.assertEqual((self.temp_dir / "target.py").read_text(encoding="utf-8"), original)

    # ── T-103-05: 기존 파일 + auto_overwrite=True ───────────────────
    def test_T103_05_existing_file_auto_overwrite_true(self):
        """T-103-05: Bypass 모드 — input() 미호출, BYPASS 로그 출력, 즉시 덮어쓰기"""
        (self.temp_dir / "target.py").write_text("old", encoding="utf-8")

        printed_lines = []
        with patch("builtins.input") as mock_input, \
             patch("builtins.print", side_effect=lambda *a, **k: printed_lines.append(" ".join(str(x) for x in a))):
            saved = self.parser.parse_and_save(SINGLE_FILE_RESPONSE, auto_overwrite=True)

        mock_input.assert_not_called()
        self.assertEqual(saved, ["target.py"])
        self.assertEqual((self.temp_dir / "target.py").read_text(encoding="utf-8"), "new_content = 42")
        self.assertTrue(any("BYPASS" in line for line in printed_lines))

    # ── T-103-06: 신규 파일 + auto_overwrite=True ───────────────────
    def test_T103_06_new_file_auto_overwrite_true_no_bypass_log(self):
        """T-103-06: 신규 파일, auto_overwrite=True → BYPASS 로그 없음, 정상 저장"""
        printed_lines = []
        with patch("builtins.print", side_effect=lambda *a, **k: printed_lines.append(" ".join(str(x) for x in a))):
            saved = self.parser.parse_and_save(SINGLE_FILE_RESPONSE, auto_overwrite=True)

        self.assertEqual(saved, ["target.py"])
        self.assertFalse(any("BYPASS" in line for line in printed_lines))


if __name__ == "__main__":
    unittest.main()
