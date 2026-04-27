"""tests/test_context_processor_quality_check.py

FSD v1.0.123 § 9.2 — ContextProcessor 품질 검사 로직 단위 테스트
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Optional


class _StubFileManager:
    """테스트용 FileManager 스텁"""

    def __init__(self, workspace: str):
        self.workspace_dir = Path(workspace)

    def read_file(self, filepath) -> Optional[str]:
        return "# stub content\nprint('hello')\n"

    def write_file(self, filepath, content: str) -> bool:
        return True

    def list_files(self, extensions=None):
        return []


class _StubAssistant:
    """테스트용 어시스턴트 스텁"""

    def __init__(self):
        self.system_prompt = "original system prompt"
        self.conversation_history = []
        self._chat_responses = []
        self._chat_call_idx = 0

    def set_responses(self, responses):
        """테스트에서 호출 순서대로 반환할 응답 목록 설정"""
        self._chat_responses = responses
        self._chat_call_idx = 0

    def chat(self, message, streaming=False, include_context=False, **kwargs):
        if self._chat_call_idx < len(self._chat_responses):
            resp = self._chat_responses[self._chat_call_idx]
            self._chat_call_idx += 1
            return resp
        return ""


class TestContextProcessorQC(unittest.TestCase):
    """ContextProcessor 2차 품질 검사 테스트"""

    def _make_processor(self, quality_check=True):
        from src.context_processor import ContextProcessor
        fm = _StubFileManager("/tmp/workspace")
        assistant = _StubAssistant()
        processor = ContextProcessor(
            assistant=assistant,
            file_manager=fm,
            streaming=False,
            quality_check=quality_check,
        )
        return processor, assistant, fm

    # ─── TC-QC-01: QC 비활성화 시 2차 호출 없음 ──────────────
    def test_qc_disabled_no_second_call(self):
        """TC-QC-01: quality_check=False 이면 2차 호출 없음"""
        proc, assistant, _ = self._make_processor(quality_check=False)
        assistant.set_responses([
            "```filename:test.py\nprint('hello')\n```"
        ])

        with patch.object(Path, 'relative_to', return_value=Path("test.py")):
            with patch.object(Path, 'exists', return_value=True):
                proc.process_files([Path("/tmp/workspace/test.py")], "질문")

        # 1차 호출만 1회
        self.assertEqual(assistant._chat_call_idx, 1)

    # ─── TC-QC-02: "품질 양호" 단축 응답 처리 ────────────────
    def test_qc_no_changes_response(self):
        """TC-QC-02: '품질 양호' 응답이면 no_changes 처리"""
        proc, _, _ = self._make_processor()
        status, applied, total = proc._apply_qc_patches(
            "품질 양호 — 수정사항 없음", "test.py"
        )
        self.assertEqual(status, "no_changes")
        self.assertEqual(applied, 0)

    # ─── TC-QC-03: ```filename:``` 펜스 거부 ─────────────────
    def test_qc_rejects_filename_fence(self):
        """TC-QC-03: QC 가 filename 펜스만 보내면 rejected"""
        proc, _, _ = self._make_processor()
        response = "여기를 수정합니다:\n```filename:test.py\nprint('world')\n```"
        status, _, _ = proc._apply_qc_patches(response, "test.py")
        self.assertEqual(status, "rejected_filename")

    # ─── TC-QC-04: patch 펜스 추출 ──────────────────────────
    def test_extract_patch_fences(self):
        """TC-QC-04: patch:<path> 펜스 본문 추출"""
        proc, _, _ = self._make_processor()
        response = (
            "수정:\n"
            "```patch:src/test.py\n"
            "<<<<<<< SEARCH\n"
            "old_line\n"
            "=======\n"
            "new_line\n"
            ">>>>>>> REPLACE\n"
            "```"
        )
        pairs = proc._extract_patch_fences(response)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][0], "src/test.py")
        self.assertIn("<<<<<<< SEARCH", pairs[0][1])

    # ─── TC-QC-05: system_prompt 원복 보장 ───────────────────
    def test_system_prompt_restore_on_exception(self):
        """TC-QC-05: 2차 호출 중 예외 발생해도 system_prompt 원복"""
        proc, assistant, _ = self._make_processor()
        original = assistant.system_prompt

        try:
            with proc._temporarily_override_system_prompt("QC 프롬프트"):
                self.assertEqual(assistant.system_prompt, "QC 프롬프트")
                raise RuntimeError("의도적 예외")
        except RuntimeError:
            pass

        self.assertEqual(assistant.system_prompt, original)

    # ─── TC-QC-06: build_qc_prompt 형식 ─────────────────────
    def test_build_qc_prompt_format(self):
        """TC-QC-06: QC 프롬프트에 원래 질문과 파일 내용이 포함"""
        proc, _, _ = self._make_processor()
        result = proc._build_qc_prompt("리팩토링", "src/a.py", "def foo(): pass")
        self.assertIn("리팩토링", result)
        self.assertIn("src/a.py", result)
        self.assertIn("def foo(): pass", result)
        self.assertIn("patch:src/a.py", result)

    # ─── TC-QC-07: 빈 응답 시 no_changes ────────────────────
    def test_qc_empty_response_no_changes(self):
        """TC-QC-07: patch 펜스 없는 일반 텍스트 → no_changes"""
        proc, _, _ = self._make_processor()
        status, _, _ = proc._apply_qc_patches(
            "이 코드는 잘 작성되었습니다.", "test.py"
        )
        self.assertEqual(status, "no_changes")


class TestContextProcessorQCStats(unittest.TestCase):
    """QC 통계 누적 테스트"""

    def test_initial_stats(self):
        """TC-QC-S-01: 초기 통계값이 모두 0"""
        from src.context_processor import ContextProcessor
        fm = _StubFileManager("/tmp/workspace")
        assistant = _StubAssistant()
        proc = ContextProcessor(
            assistant=assistant,
            file_manager=fm,
            streaming=False,
            quality_check=True,
        )
        self.assertEqual(proc._qc_stats["checked"], 0)
        self.assertEqual(proc._qc_stats["applied"], 0)
        self.assertEqual(proc._qc_stats["no_changes"], 0)
        self.assertEqual(proc._qc_stats["failed"], 0)


if __name__ == "__main__":
    unittest.main()
