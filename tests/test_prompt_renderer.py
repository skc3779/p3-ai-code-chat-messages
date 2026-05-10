"""
PromptRenderer 단위 테스트 (FSD v1.0.161)

T-01 ~ T-07 — `{{var}}` 1패스 치환, on_missing 정책, find_variables.
"""

import sys
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.prompt_renderer import PromptRenderer


class TestPromptRenderer(unittest.TestCase):
    # T-01 — 기본 치환
    def test_basic_substitution(self):
        out = PromptRenderer.render("hi {{name}}", {"name": "Bob"})
        self.assertEqual(out, "hi Bob")

    # T-02 — 자리표시자 안 공백 허용
    def test_whitespace_inside_braces(self):
        out = PromptRenderer.render("hi {{ name }}", {"name": "Bob"})
        self.assertEqual(out, "hi Bob")

    # T-03 — 누락 변수 keep
    def test_missing_keep(self):
        out = PromptRenderer.render("hi {{age}}", {})
        self.assertEqual(out, "hi {{age}}")

    # T-04 — 누락 변수 raise
    def test_missing_raise(self):
        with self.assertRaises(PromptRenderer.MissingVariableError):
            PromptRenderer.render("hi {{age}}", {}, on_missing="raise")

    # T-04b — 누락 변수 empty
    def test_missing_empty(self):
        out = PromptRenderer.render("[{{age}}]", {}, on_missing="empty")
        self.assertEqual(out, "[]")

    # T-05 — 1패스 비재귀 (값에 자리표시자가 또 있어도 재치환 안 함)
    def test_non_recursive(self):
        out = PromptRenderer.render("{{x}}", {"x": "{{y}}", "y": "Z"})
        self.assertEqual(out, "{{y}}")

    # T-06 — find_variables: 등장순, 중복 제거
    def test_find_variables(self):
        self.assertEqual(
            PromptRenderer.find_variables("{{a}}{{b}}{{a}}"),
            ["a", "b"],
        )

    # T-07 — 잘못된 식별자 (숫자 시작) 는 자리표시자로 인식하지 않음
    def test_invalid_identifier_kept_as_text(self):
        # 패턴이 매칭되지 않으므로 원본 유지
        src = "hello {{1abc}}"
        self.assertEqual(PromptRenderer.render(src, {"1abc": "X"}), src)
        self.assertEqual(PromptRenderer.find_variables(src), [])

    # 추가 — None / 빈 입력 안전성
    def test_none_template(self):
        self.assertEqual(PromptRenderer.render(None, {"a": "1"}), "")
        self.assertEqual(PromptRenderer.find_variables(""), [])

    # 추가 — invalid policy 거부
    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            PromptRenderer.render("x", {}, on_missing="bogus")


if __name__ == "__main__":
    unittest.main()
