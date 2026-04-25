"""
T-110-01 ~ T-110-05 — PRINT_BANNER 환경 변수 토글 테스트

_should_print_banner() 는 세 엔트리 포인트에 동일하게 복사된 함수이므로,
로직 테스트는 여기에 동일 구현을 인라인으로 정의하고 검증한다.
각 파일이 실제로 가드를 포함하는지는 소스 텍스트로 검증한다.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def _should_print_banner() -> bool:
    """`PRINT_BANNER` 환경 변수로 배너 출력 여부 결정. 미설정 시 True."""
    raw = os.getenv("PRINT_BANNER", "").strip().lower()
    if raw in ("false", "0", "no", "off"):
        return False
    return True


class TestShouldPrintBannerLogic(unittest.TestCase):
    """_should_print_banner() 로직 검증 (T-110-01 ~ T-110-05)"""

    def _call(self, value):
        with patch.dict(os.environ, {"PRINT_BANNER": value}, clear=False):
            return _should_print_banner()

    def _call_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "PRINT_BANNER"}
        with patch.dict(os.environ, env, clear=True):
            return _should_print_banner()

    # T-110-01
    def test_false_lowercase(self):
        self.assertFalse(self._call("false"))

    # T-110-02
    def test_false_uppercase(self):
        self.assertFalse(self._call("FALSE"))

    # T-110-03
    def test_false_variants(self):
        for val in ("0", "no", "off"):
            with self.subTest(val=val):
                self.assertFalse(self._call(val))

    # T-110-04
    def test_true_variants(self):
        for val in ("true", "1", "yes", "on", "True", "TRUE"):
            with self.subTest(val=val):
                self.assertTrue(self._call(val))

    def test_empty_string_defaults_to_true(self):
        self.assertTrue(self._call(""))

    def test_unset_defaults_to_true(self):
        self.assertTrue(self._call_unset())

    # T-110-05
    def test_unknown_value_defaults_to_true(self):
        self.assertTrue(self._call("maybe"))


class TestEntryPointsContainGuard(unittest.TestCase):
    """각 엔트리 포인트 파일에 _should_print_banner 정의와 가드가 존재하는지 검증"""

    ENTRY_POINTS = [
        "claude-ai-chat-code.py",
        "gemini-ai-chat-code.py",
        "gen-ai-chat-code.py",
    ]

    def _read(self, filename: str) -> str:
        return (project_root / filename).read_text(encoding="utf-8")

    def test_function_defined(self):
        for ep in self.ENTRY_POINTS:
            with self.subTest(file=ep):
                self.assertIn("def _should_print_banner()", self._read(ep))

    def test_banner_call_is_guarded(self):
        for ep in self.ENTRY_POINTS:
            with self.subTest(file=ep):
                src = self._read(ep)
                self.assertIn("if _should_print_banner():", src)

    def test_bare_print_banner_not_called_in_main(self):
        """main() 본문에서 가드 없이 4-스페이스 들여쓰기 단독 호출이 없음.

        가드가 있으면 print_banner() 는 8-스페이스 들여쓰기(if 블록 안)에 있어야 한다.
        """
        for ep in self.ENTRY_POINTS:
            with self.subTest(file=ep):
                lines = (project_root / ep).read_text(encoding="utf-8").splitlines()
                in_main = False
                for line in lines:
                    stripped = line.lstrip()
                    if stripped.startswith("def main("):
                        in_main = True
                    elif in_main and stripped.startswith("def "):
                        in_main = False  # 다음 함수 정의로 진입 → main 종료
                    # 4-스페이스 단독 호출(가드 없는 직접 호출) 감지
                    if in_main and line == "    print_banner()":
                        self.fail(f"{ep}: 가드 없이 print_banner() 단독 호출 발견")


if __name__ == "__main__":
    unittest.main()
