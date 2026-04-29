"""
System Prompt v1.0.111 회귀 테스트 (FSD v1.0.115)

T-111-40 ~ T-111-44 — 의사결정 트리 헤더, patch 마커 안내,
[ACTION:shell] 보존, 길이 상한, .format() 호환.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent_runner import AgentRunner


def _make_runner() -> AgentRunner:
    assistant = MagicMock()
    assistant.conversation_history = []
    assistant.system_prompt = "sys"
    file_manager = MagicMock()
    file_manager.workspace_dir = Path("/tmp/test_workspace")
    terminal_executor = MagicMock()
    terminal_executor.DANGEROUS_COMMANDS = {"rm"}
    env = {
        "AGENT_MAX_ITERATIONS": "10",
        "AGENT_SELF_CORRECT_MAX": "1",
        "AGENT_COMPACT_AFTER": "5",
        "AGENT_CODE_TIMEOUT": "30",
        "AGENT_DONE_TOKEN": "[AGENT_DONE]",
    }
    with patch.dict(os.environ, env, clear=False):
        with patch("src.agent_runner.CodeExecutor"):
            return AgentRunner(
                assistant=assistant,
                file_manager=file_manager,
                code_executor=MagicMock(),
                terminal_executor=terminal_executor,
                response_parser=MagicMock(),
                cli_handler=MagicMock(),
                context_builder=None,
                streaming=False,
                assistant_role="model",
            )


class TestSystemPromptV111(unittest.TestCase):

    def setUp(self):
        self.runner = _make_runner()
        self.prompt = self.runner._build_system_prompt()

    # ─── T-111-40 ──────────────────────────────────────────
    def test_T111_40_decision_tree_header(self):
        self.assertIn("의사결정 트리", self.prompt)

    # ─── T-111-41 ──────────────────────────────────────────
    def test_T111_41_patch_marker_documented(self):
        self.assertIn("@@@patch:경로/파일명.확장자", self.prompt)
        self.assertIn("<<<<<<< SEARCH", self.prompt)
        self.assertIn(">>>>>>> REPLACE", self.prompt)

    # ─── T-111-42 ──────────────────────────────────────────
    def test_T111_42_action_shell_tag_preserved(self):
        # FR-111-17 / 회귀 — v1.0.107 의 [ACTION:shell] 명시 라우팅 보존
        self.assertIn("[ACTION:shell]", self.prompt)

    # ─── T-111-43 ──────────────────────────────────────────
    def test_T111_43_prompt_length_under_cap(self):
        # FR-111-21 — v1.0.107 대비 ≤ 1.6배. 절대 상한 6000자로 회귀 방지.
        self.assertLess(len(self.prompt), 6000, f"len={len(self.prompt)}")

    # ─── T-111-44 ──────────────────────────────────────────
    def test_T111_44_format_compatible_no_keyerror(self):
        # NFR-111-08 — 시스템 프롬프트는 .format() 충돌 금지
        try:
            self.prompt.format()
        except (KeyError, IndexError, ValueError) as e:
            self.fail(f"prompt.format() 호환 실패: {e}")

    # ─── 추가 회귀 ─────────────────────────────────────────
    def test_filename_a1_documented(self):
        # FR-111-19 — 신규 파일은 ```filename:``` 사용 권장 명시
        self.assertIn("선택지 A-1", self.prompt)
        self.assertIn("@@@filename:", self.prompt)

    def test_no_os_call_in_code_warning(self):
        # FR-111-20 — 코드(B) 안에서 OS 호출 금지 안내
        self.assertIn("subprocess.run", self.prompt)
        self.assertIn("선택지 C", self.prompt)


if __name__ == "__main__":
    unittest.main()
