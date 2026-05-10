"""
FSD v1.0.161 [ADD] 보강 테스트 — assistant_type 필터링 및 /template_show.

T-30 ~ T-37 — TemplateManager.list_templates(assistant_type), get_template_info,
어시스턴트의 list_templates 자동 필터, get_active_template_info 동작 검증.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.template_manager import TemplateManager


class TestListTemplatesFilter(unittest.TestCase):
    """T-30 ~ T-33 — assistant_type 으로 list_templates 필터링."""

    def setUp(self):
        self.workspace = str(project_root)
        self.tm = TemplateManager(self.workspace)

    # T-30 — claude 필터: claude-system-prompt 와 공용(code-review) 포함, gemini/genai 제외
    def test_filter_claude_includes_common_excludes_others(self):
        result = self.tm.list_templates(assistant_type="claude")
        names = [t["name"] for t in result]
        self.assertIn("claude-system-prompt", names)
        self.assertIn("code-review", names)  # assistant_type 미지정 → 공용
        self.assertNotIn("gemini-system-prompt", names)
        self.assertNotIn("genai-system-prompt", names)

    # T-31 — gemini 필터
    def test_filter_gemini(self):
        result = self.tm.list_templates(assistant_type="gemini")
        names = [t["name"] for t in result]
        self.assertIn("gemini-system-prompt", names)
        self.assertIn("code-review", names)
        self.assertNotIn("claude-system-prompt", names)
        self.assertNotIn("genai-system-prompt", names)

    # T-32 — genai 필터
    def test_filter_genai(self):
        result = self.tm.list_templates(assistant_type="genai")
        names = [t["name"] for t in result]
        self.assertIn("genai-system-prompt", names)
        self.assertIn("code-review", names)
        self.assertNotIn("claude-system-prompt", names)
        self.assertNotIn("gemini-system-prompt", names)

    # T-33 — None 또는 미지정 시 모든 템플릿 반환 (호환성)
    def test_no_filter_returns_all(self):
        result = self.tm.list_templates()
        names = [t["name"] for t in result]
        for n in ("claude-system-prompt", "gemini-system-prompt",
                  "genai-system-prompt", "code-review"):
            self.assertIn(n, names)

    # T-34 — 반환 dict 에 assistant_type 키가 포함됨
    def test_result_contains_assistant_type_key(self):
        result = self.tm.list_templates()
        for t in result:
            self.assertIn("assistant_type", t)


class TestGetTemplateInfo(unittest.TestCase):
    """T-35 — TemplateManager.get_template_info."""

    def setUp(self):
        self.tm = TemplateManager(str(project_root))

    def test_get_info_by_name(self):
        info = self.tm.get_template_info("claude-system-prompt")
        self.assertIsNotNone(info)
        self.assertEqual(info["name"], "claude-system-prompt")
        self.assertEqual(info["assistant_type"], "claude")
        self.assertTrue(info["description"])

    def test_get_info_unknown_returns_none(self):
        self.assertIsNone(self.tm.get_template_info("ghost-template"))

    def test_get_info_yaml_extension_tolerated(self):
        info = self.tm.get_template_info("gemini-system-prompt.yaml")
        self.assertIsNotNone(info)
        self.assertEqual(info["assistant_type"], "gemini")


class TestAssistantsActiveTemplate(unittest.TestCase):
    """T-36 ~ T-37 — list_templates 자동 필터 + get_active_template_info."""

    def setUp(self):
        self.workspace = str(project_root)

    # T-36 — 어시스턴트의 list_templates() 가 자기 타입으로 자동 필터
    def test_claude_list_templates_auto_filter(self):
        with patch.dict(os.environ, {"DEFAULT_CLAUDE_TEMPLATE": "claude-system-prompt"}):
            from src.claude_assistant import ClaudeCodeAssistant
            a = ClaudeCodeAssistant(api_key="x", workspace_dir=self.workspace)
            names = [t["name"] for t in a.list_templates()]
            self.assertIn("claude-system-prompt", names)
            self.assertNotIn("gemini-system-prompt", names)
            self.assertNotIn("genai-system-prompt", names)

    def test_gemini_list_templates_auto_filter(self):
        with patch.dict(os.environ, {"DEFAULT_GEMINI_TEMPLATE": "gemini-system-prompt"}):
            from src.gemini_assistant import GeminiCodeAssistant
            a = GeminiCodeAssistant(api_key="x", workspace_dir=self.workspace)
            names = [t["name"] for t in a.list_templates()]
            self.assertIn("gemini-system-prompt", names)
            self.assertNotIn("claude-system-prompt", names)

    def test_genai_list_templates_auto_filter(self):
        with patch.dict(os.environ, {"DEFAULT_GENAI_TEMPLATE": "genai-system-prompt"}):
            from src.genai_assistant import GenAICodeAssistant
            a = GenAICodeAssistant(
                endpoint_url="http://x", client_key="k", client_secret="s",
                model_id="m", workspace_dir=self.workspace,
            )
            names = [t["name"] for t in a.list_templates()]
            self.assertIn("genai-system-prompt", names)
            self.assertNotIn("claude-system-prompt", names)

    # T-37 — get_active_template_info: 초기 / 변경 / 리셋 후
    def test_active_template_info_lifecycle(self):
        with patch.dict(os.environ, {"DEFAULT_CLAUDE_TEMPLATE": "claude-system-prompt"}):
            from src.claude_assistant import ClaudeCodeAssistant
            a = ClaudeCodeAssistant(api_key="x", workspace_dir=self.workspace)

            # 초기 상태: .env 의 기본 템플릿
            info = a.get_active_template_info()
            self.assertEqual(info["name"], "claude-system-prompt")
            self.assertEqual(info["assistant_type"], "claude")
            self.assertTrue(info["description"])

            # 다른 템플릿으로 변경
            self.assertTrue(a.set_system_prompt_from_template("code-review"))
            info = a.get_active_template_info()
            self.assertEqual(info["name"], "code-review")

            # 리셋 후 기본으로 복귀
            a.reset_system_prompt()
            info = a.get_active_template_info()
            self.assertEqual(info["name"], "claude-system-prompt")

    # T-37b — 빌트인 fallback 사용 시에도 메타정보가 무난히 반환됨
    def test_active_template_info_fallback(self):
        with patch.dict(os.environ, {"DEFAULT_CLAUDE_TEMPLATE": "ghost-xyz"}):
            from src.claude_assistant import ClaudeCodeAssistant
            a = ClaudeCodeAssistant(api_key="x", workspace_dir=self.workspace)
            info = a.get_active_template_info()
            self.assertEqual(info["assistant_type"], "claude")
            self.assertEqual(info["name"], "ghost-xyz")


if __name__ == "__main__":
    unittest.main()
