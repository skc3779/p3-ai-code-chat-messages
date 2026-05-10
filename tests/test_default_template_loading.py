"""
기본 시스템 프롬프트 YAML 외부화 테스트 (FSD v1.0.161)

T-10 ~ T-16 — TemplateManager.resolve_default_template, 어시스턴트의
.env 기반 기본 템플릿 로딩, {{os_shell_hint}} 치환, fallback.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.template_manager import TemplateManager


class TestResolveDefaultTemplate(unittest.TestCase):
    """`TemplateManager.resolve_default_template` 단위 테스트."""

    def setUp(self):
        # 실제 워크스페이스의 .system_prompts 디렉토리를 사용한다
        # (claude/gemini/genai-system-prompt.yaml 이 존재해야 함).
        self.workspace = str(project_root)
        self.tm = TemplateManager(self.workspace)

    # T-10 — DEFAULT_CLAUDE_TEMPLATE=claude-system-prompt → 본문 로드
    def test_claude_default_loaded(self):
        raw = self.tm.resolve_default_template("claude-system-prompt", "claude")
        self.assertIsNotNone(raw)
        self.assertIn("{{os_shell_hint}}", raw)

    # T-10 — DEFAULT_GEMINI_TEMPLATE=gemini-system-prompt-english-tutor → 본문 로드
    def test_gemini_default_loaded(self):
        raw = self.tm.resolve_default_template("gemini-system-prompt-english-tutor", "gemini")
        # print(f"gemini-system-prompt-english-tutor raw: {raw}")
        self.assertIsNotNone(raw)
        self.assertIn("{{os_shell_hint}}", raw)

    # T-10 — DEFAULT_GENAI_TEMPLATE=genai-system-prompt → 본문 로드
    def test_genai_default_loaded(self):
        raw = self.tm.resolve_default_template("genai-system-prompt", "genai")
        self.assertIsNotNone(raw)
        self.assertIn("{{os_shell_hint}}", raw)

    # T-11 — None / 빈 문자열이면 어시스턴트 타입별 기본 파일명을 사용
    def test_default_falls_back_to_type_name(self):
        for assistant_type in ("claude", "gemini", "genai"):
            raw = self.tm.resolve_default_template(None, assistant_type)
            self.assertIsNotNone(raw, f"{assistant_type} default 본문이 None")
            raw2 = self.tm.resolve_default_template("", assistant_type)
            self.assertIsNotNone(raw2)

    # T-12 — 존재하지 않는 이름 → None 반환 (호출자가 fallback 처리)
    def test_unknown_name_returns_none(self):
        raw = self.tm.resolve_default_template("ghost-template", "claude")
        self.assertIsNone(raw)

    # T-13 — .yaml 확장자 포함된 값도 정상 처리
    def test_yaml_extension_tolerated(self):
        raw = self.tm.resolve_default_template("gemini-system-prompt.yaml", "gemini")
        self.assertIsNotNone(raw)
        self.assertIn("{{os_shell_hint}}", raw)


class TestAssistantsDefaultPromptLoading(unittest.TestCase):
    """3개 어시스턴트의 기본 프롬프트가 YAML 에서 로드되고 변수가 치환되는지."""

    def setUp(self):
        # 작업 디렉토리는 .system_prompts 자산이 있는 프로젝트 루트
        self.workspace = str(project_root)

    # T-10b — Claude 어시스턴트 system_prompt 에 OS 힌트가 치환되어 들어 있는지
    def test_claude_assistant_uses_yaml_with_substitution(self):
        with patch.dict(os.environ, {"DEFAULT_CLAUDE_TEMPLATE": "claude-system-prompt"}):
            from src.claude_assistant import ClaudeCodeAssistant
            a = ClaudeCodeAssistant(api_key="x", workspace_dir=self.workspace)
            self.assertNotIn("{{os_shell_hint}}", a.system_prompt)
            # OS 힌트의 핵심 키워드 중 하나는 반드시 포함되어야 한다.
            text = a.system_prompt.lower()
            self.assertTrue(
                any(k in text for k in ("windows", "powershell", "linux", "bash", "macos")),
                f"OS shell hint 가 치환되지 않았습니다: {a.system_prompt[:200]}",
            )

    def test_gemini_assistant_uses_yaml_with_substitution(self):
        with patch.dict(os.environ, {"DEFAULT_GEMINI_TEMPLATE": "gemini-system-prompt"}):
            from src.gemini_assistant import GeminiCodeAssistant
            a = GeminiCodeAssistant(api_key="x", workspace_dir=self.workspace)
            self.assertNotIn("{{os_shell_hint}}", a.system_prompt)

    def test_genai_assistant_uses_yaml_with_substitution(self):
        with patch.dict(os.environ, {"DEFAULT_GENAI_TEMPLATE": "genai-system-prompt"}):
            from src.genai_assistant import GenAICodeAssistant
            a = GenAICodeAssistant(
                endpoint_url="http://x", client_key="k", client_secret="s",
                model_id="m", workspace_dir=self.workspace,
            )
            self.assertNotIn("{{os_shell_hint}}", a.system_prompt)

    # T-11b — DEFAULT_*_TEMPLATE 미설정 → 타입별 기본 파일명 사용
    def test_unset_env_uses_type_default(self):
        env = dict(os.environ)
        env.pop("DEFAULT_GEMINI_TEMPLATE", None)
        with patch.dict(os.environ, env, clear=True):
            from src.gemini_assistant import GeminiCodeAssistant
            a = GeminiCodeAssistant(api_key="x", workspace_dir=self.workspace)
            self.assertEqual(a._default_template_name, "gemini-system-prompt")
            self.assertNotIn("{{os_shell_hint}}", a.system_prompt)

    # T-12b — 존재하지 않는 이름 → 빌트인 fallback 으로 인스턴스 생성 성공
    def test_unknown_template_falls_back(self):
        with patch.dict(os.environ, {"DEFAULT_CLAUDE_TEMPLATE": "ghost-xyz"}):
            from src.claude_assistant import ClaudeCodeAssistant
            a = ClaudeCodeAssistant(api_key="x", workspace_dir=self.workspace)
            # fallback 본문도 동일한 렌더 경로를 통과 → {{os_shell_hint}} 치환되어야 함
            self.assertNotIn("{{os_shell_hint}}", a.system_prompt)
            self.assertIn("Anthropic", a.system_prompt)

    # T-13b — .yaml 확장자 포함된 값도 정상 처리
    def test_yaml_extension_in_env_value(self):
        with patch.dict(os.environ, {"DEFAULT_CLAUDE_TEMPLATE": "claude-system-prompt.yaml"}):
            from src.claude_assistant import ClaudeCodeAssistant
            a = ClaudeCodeAssistant(api_key="x", workspace_dir=self.workspace)
            self.assertNotIn("{{os_shell_hint}}", a.system_prompt)

    # T-14 — set_system_prompt_from_template 도 변수 치환 적용
    def test_set_template_applies_substitution(self):
        with patch.dict(os.environ, {"DEFAULT_CLAUDE_TEMPLATE": "claude-system-prompt"}):
            from src.claude_assistant import ClaudeCodeAssistant
            a = ClaudeCodeAssistant(api_key="x", workspace_dir=self.workspace)
            ok = a.set_system_prompt_from_template("claude-system-prompt")
            self.assertTrue(ok)
            self.assertNotIn("{{os_shell_hint}}", a.system_prompt)

    # T-15 — reset_system_prompt 후 default_system_prompt 로 복귀
    def test_reset_returns_to_default(self):
        with patch.dict(os.environ, {"DEFAULT_CLAUDE_TEMPLATE": "claude-system-prompt"}):
            from src.claude_assistant import ClaudeCodeAssistant
            a = ClaudeCodeAssistant(api_key="x", workspace_dir=self.workspace)
            a.set_system_prompt_from_template("code-review")
            a.reset_system_prompt()
            self.assertEqual(a.system_prompt, a.default_system_prompt)
            self.assertEqual(a._active_raw_system_prompt, a._raw_system_prompt)


if __name__ == "__main__":
    unittest.main()
