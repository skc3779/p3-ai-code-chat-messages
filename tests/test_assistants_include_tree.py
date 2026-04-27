"""tests/test_assistants_include_tree.py

FSD v1.0.123 § 9.3 — 어시스턴트 chat() 시그니처 include_tree 테스트
"""

import unittest
from unittest.mock import MagicMock, patch
import inspect


class TestClaudeIncludeTree(unittest.TestCase):
    """Claude chat() 시그니처에 include_tree 가 존재하는지 검증"""

    def test_include_tree_parameter_exists(self):
        """TC-IT-01: ClaudeCodeAssistant.chat()에 include_tree 파라미터 존재"""
        from src.claude_assistant import ClaudeCodeAssistant
        sig = inspect.signature(ClaudeCodeAssistant.chat)
        self.assertIn("include_tree", sig.parameters)

    def test_include_tree_default_true(self):
        """TC-IT-02: include_tree 기본값이 True"""
        from src.claude_assistant import ClaudeCodeAssistant
        sig = inspect.signature(ClaudeCodeAssistant.chat)
        param = sig.parameters["include_tree"]
        self.assertEqual(param.default, True)

    def test_include_tree_keyword_only(self):
        """TC-IT-03: include_tree 가 keyword-only 파라미터"""
        from src.claude_assistant import ClaudeCodeAssistant
        sig = inspect.signature(ClaudeCodeAssistant.chat)
        param = sig.parameters["include_tree"]
        self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)


class TestGeminiIncludeTree(unittest.TestCase):
    """Gemini chat() 시그니처에 include_tree 가 존재하는지 검증"""

    def test_include_tree_parameter_exists(self):
        """TC-IT-04: GeminiCodeAssistant.chat()에 include_tree 파라미터 존재"""
        from src.gemini_assistant import GeminiCodeAssistant
        sig = inspect.signature(GeminiCodeAssistant.chat)
        self.assertIn("include_tree", sig.parameters)

    def test_include_tree_default_true(self):
        """TC-IT-05: include_tree 기본값이 True"""
        from src.gemini_assistant import GeminiCodeAssistant
        sig = inspect.signature(GeminiCodeAssistant.chat)
        param = sig.parameters["include_tree"]
        self.assertEqual(param.default, True)

    def test_include_tree_keyword_only(self):
        """TC-IT-06: include_tree 가 keyword-only 파라미터"""
        from src.gemini_assistant import GeminiCodeAssistant
        sig = inspect.signature(GeminiCodeAssistant.chat)
        param = sig.parameters["include_tree"]
        self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)


class TestGenAIIncludeTree(unittest.TestCase):
    """GenAI chat() 시그니처에 include_tree 가 존재하는지 검증"""

    def test_include_tree_parameter_exists(self):
        """TC-IT-07: GenAICodeAssistant.chat()에 include_tree 파라미터 존재"""
        from src.genai_assistant import GenAICodeAssistant
        sig = inspect.signature(GenAICodeAssistant.chat)
        self.assertIn("include_tree", sig.parameters)

    def test_include_tree_default_true(self):
        """TC-IT-08: include_tree 기본값이 True"""
        from src.genai_assistant import GenAICodeAssistant
        sig = inspect.signature(GenAICodeAssistant.chat)
        param = sig.parameters["include_tree"]
        self.assertEqual(param.default, True)

    def test_include_tree_keyword_only(self):
        """TC-IT-09: include_tree 가 keyword-only 파라미터"""
        from src.genai_assistant import GenAICodeAssistant
        sig = inspect.signature(GenAICodeAssistant.chat)
        param = sig.parameters["include_tree"]
        self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)


if __name__ == "__main__":
    unittest.main()
