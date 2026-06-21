import inspect
import json
import unittest
from types import SimpleNamespace

from src.claude_assistant import ClaudeCodeAssistant
from src.gemini_assistant import GeminiCodeAssistant
from src.genai_assistant import GenAICodeAssistant


class LargeContextProviderContractTests(unittest.TestCase):
    def test_all_chat_adapters_expose_internal_contract(self):
        for cls in (ClaudeCodeAssistant, GenAICodeAssistant, GeminiCodeAssistant):
            parameters = inspect.signature(cls.chat).parameters
            self.assertIn("disable_tools", parameters)
            self.assertIn("raise_on_error", parameters)
            self.assertIn("internal_system_prompt", parameters)
            self.assertTrue(callable(getattr(cls, "prepare_internal_request")))

    def test_claude_preflight_is_exact_tool_free_body(self):
        assistant = ClaudeCodeAssistant.__new__(ClaudeCodeAssistant)
        assistant.model_id = "claude-test"
        assistant._render_system_prompt = lambda: "system"
        prepared = assistant.prepare_internal_request("hello")
        body = {"model": "claude-test", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 4096, "system": "system", "stream": False}
        self.assertEqual(prepared["request_chars"], len(json.dumps(body, ensure_ascii=False, separators=(",", ":"))))
        self.assertNotIn("tools", body)

    def test_genai_preflight_includes_provider_body(self):
        assistant = GenAICodeAssistant.__new__(GenAICodeAssistant)
        assistant.model_id = "genai-test"
        assistant._render_system_prompt = lambda: "system"
        assistant.get_llm_config = lambda: {"maxTokens": 100}
        assistant.sensitive_filter = SimpleNamespace(mask_contents=lambda value: value, mask_system_prompt=lambda value: value)
        prepared = assistant.prepare_internal_request("hello")
        self.assertGreater(prepared["request_chars"], len("hello") + len("system"))

    def test_gemini_preflight_includes_generation_config(self):
        assistant = GeminiCodeAssistant.__new__(GeminiCodeAssistant)
        assistant.model_id = "gemini-test"
        assistant.conversation_history = []
        assistant.system_prompt = "old"
        assistant._render_system_prompt = lambda: "system"
        prepared = assistant.prepare_internal_request("hello")
        self.assertGreater(prepared["request_chars"], len("hello") + len("system"))


if __name__ == "__main__":
    unittest.main()
