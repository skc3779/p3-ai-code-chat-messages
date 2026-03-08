"""
ContextProcessor Unit Tests
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil
import sys

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.context_processor import ContextProcessor
from src.file_manager import FileManager

class TestContextProcessorRetry(unittest.TestCase):
    """FSD v1.0.076 — 응답 저장 실패 시 재시도 테스트"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.file_manager = FileManager(self.temp_dir)

        # 테스트 파일 생성
        (self.temp_dir / "file1.md").write_text("Content of file1", encoding="utf-8")
        (self.temp_dir / "file2.md").write_text("Content of file2", encoding="utf-8")
        (self.temp_dir / "file3.md").write_text("Content of file3", encoding="utf-8")

        # Mock assistant
        self.mock_assistant = MagicMock()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # T-01: AI 응답에 filename: 블록 정상 포함 → 1회 시도로 성공
    def test_retry_success_on_first_attempt(self):
        """T-01: 1회 시도로 저장 성공, 재시도 없음"""
        self.mock_assistant.chat.return_value = (
            "```filename:output/file1.md\n번역된 내용\n```"
        )

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 1)
        # AI chat은 1번만 호출되어야 함
        self.assertEqual(self.mock_assistant.chat.call_count, 1)

    # T-02: 1회차 블록 없음 → 2회차 블록 있음 → 재시도 성공
    def test_retry_success_on_second_attempt(self):
        """T-02: 2회차 재시도에서 저장 성공"""
        self.mock_assistant.chat.side_effect = [
            "일반 텍스트 응답 (filename: 블록 없음)",  # 1회차 실패
            "```filename:output/file1.md\n번역된 내용\n```",  # 2회차 성공
        ]

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 1)
        # AI chat은 2번 호출되어야 함
        self.assertEqual(self.mock_assistant.chat.call_count, 2)
        self.assertTrue((self.temp_dir / "output" / "file1.md").exists())

    # T-03: 3회 모두 블록 없음 → 실패
    def test_retry_all_attempts_fail(self):
        """T-03: 3회 모두 실패 → 실패 목록에 추가"""
        self.mock_assistant.chat.return_value = "일반 텍스트 응답만 반환"

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 0)
        # 기본 max_retries=3 → 3번 호출
        self.assertEqual(self.mock_assistant.chat.call_count, 3)

    # T-04: AI 응답이 빈 문자열 → 재시도
    def test_retry_empty_response(self):
        """T-04: AI 응답이 비어있으면 재시도"""
        self.mock_assistant.chat.side_effect = [
            "",  # 1회차: 빈 응답
            "",  # 2회차: 빈 응답
            "```filename:output/file1.md\n결과\n```",  # 3회차 성공
        ]

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 1)
        self.assertEqual(self.mock_assistant.chat.call_count, 3)

    # T-04b: AI 응답이 None → 재시도
    def test_retry_none_response(self):
        """T-04b: AI 응답이 None이면 재시도"""
        self.mock_assistant.chat.side_effect = [
            None,  # 1회차: None
            "```filename:output/file1.md\n결과\n```",  # 2회차 성공
        ]

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 1)
        self.assertEqual(self.mock_assistant.chat.call_count, 2)

    # T-06: 다중 파일 중 일부만 실패
    def test_retry_partial_failure_multiple_files(self):
        """T-06: 다중 파일 처리에서 일부만 실패"""
        # file1: 3회 모두 실패
        # file2: 1회 성공
        # file3: 2회차 성공
        self.mock_assistant.chat.side_effect = [
            "일반 텍스트",  # file1 - 1회차 실패
            "일반 텍스트",  # file1 - 2회차 실패
            "일반 텍스트",  # file1 - 3회차 실패
            "```filename:output/file2.md\n번역2\n```",  # file2 - 1회차 성공
            "일반 텍스트",  # file3 - 1회차 실패
            "```filename:output/file3.md\n번역3\n```",  # file3 - 2회차 성공
        ]

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [
            self.temp_dir / "file1.md",
            self.temp_dir / "file2.md",
            self.temp_dir / "file3.md",
        ]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 3)
        self.assertEqual(saved, 2)
        # file1은 저장 안 됨, file2, file3은 저장
        self.assertFalse((self.temp_dir / "output" / "file1.md").exists())
        self.assertTrue((self.temp_dir / "output" / "file2.md").exists())
        self.assertTrue((self.temp_dir / "output" / "file3.md").exists())

    # T-07: AUTO_CONTEXT_MAX_RETRIES=5 설정
    @patch.dict('os.environ', {'AUTO_CONTEXT_MAX_RETRIES': '5'})
    def test_retry_custom_max_retries(self):
        """T-07: 환경변수로 최대 재시도 횟수 변경"""
        self.mock_assistant.chat.return_value = "일반 텍스트 응답"

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        self.assertEqual(processor.max_retries, 5)

        matched_files = [self.temp_dir / "file1.md"]
        processor.process_files(matched_files, "번역해줘")

        # 5번 호출되어야 함
        self.assertEqual(self.mock_assistant.chat.call_count, 5)

    # T-08: AUTO_CONTEXT_MAX_RETRIES 미설정 → 기본값 3
    @patch.dict('os.environ', {}, clear=False)
    def test_retry_default_max_retries(self):
        """T-08: 기본값 3회 재시도"""
        # AUTO_CONTEXT_MAX_RETRIES가 설정되어 있다면 제거
        import os
        original = os.environ.pop("AUTO_CONTEXT_MAX_RETRIES", None)
        try:
            processor = ContextProcessor(
                assistant=self.mock_assistant,
                file_manager=self.file_manager,
                streaming=False
            )
            self.assertEqual(processor.max_retries, 3)
        finally:
            if original is not None:
                os.environ["AUTO_CONTEXT_MAX_RETRIES"] = original

    # T-09: 부분 저장 성공 → 재시도 안 함
    def test_retry_partial_save_no_retry(self):
        """T-09: 일부 파일 저장 성공 시 재시도하지 않음"""
        # 2개 중 1개만 저장됨 (하나는 write_file 실패) → saved ≠ [] → 재시도 안 함
        self.mock_assistant.chat.return_value = (
            "```filename:output/ok.md\n성공 내용\n```\n"
            "```filename:output/fail.md\n실패 내용\n```"
        )

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "테스트")

        self.assertEqual(processed, 1)
        # 두 파일 모두 정상 저장 시 saved=2 → 재시도 없음
        self.assertGreaterEqual(saved, 1)
        # chat은 1번만 호출
        self.assertEqual(self.mock_assistant.chat.call_count, 1)

    # 파일 읽기 실패 시 실패 목록에 포함
    def test_retry_file_read_failure_in_failed_list(self):
        """파일 읽기 실패 → 실패 목록에 포함"""
        self.mock_assistant.chat.return_value = "```filename:out.md\n결과\n```"

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [
            self.temp_dir / "nonexistent.md",  # 읽기 실패
            self.temp_dir / "file1.md",         # 저장 성공
        ]
        processed, saved = processor.process_files(matched_files, "질문")

        # nonexistent.md는 읽기 실패이므로 processed에 포함 안 됨
        self.assertEqual(processed, 1)
        self.assertEqual(saved, 1)
        # chat은 file1.md에 대해서만 1번 호출
        self.assertEqual(self.mock_assistant.chat.call_count, 1)

    # max_retries 0 이하 설정 → 최소 1 강제
    @patch.dict('os.environ', {'AUTO_CONTEXT_MAX_RETRIES': '0'})
    def test_retry_min_retries_enforced(self):
        """max_retries를 0으로 설정해도 최소 1회 실행"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        self.assertEqual(processor.max_retries, 1)

    # 3회차에 성공하는 경우
    def test_retry_success_on_third_attempt(self):
        """3회차 재시도에서 저장 성공"""
        self.mock_assistant.chat.side_effect = [
            "일반 텍스트",  # 1회차 실패
            "",             # 2회차 빈 응답
            "```filename:output/file1.md\n결과\n```",  # 3회차 성공
        ]

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 1)
        self.assertEqual(self.mock_assistant.chat.call_count, 3)
        self.assertTrue((self.temp_dir / "output" / "file1.md").exists())

    # 3회 모두 빈 응답 → 실패
    def test_retry_all_empty_responses(self):
        """3회 모두 빈 응답 → 실패"""
        self.mock_assistant.chat.return_value = ""

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 0)
        self.assertEqual(self.mock_assistant.chat.call_count, 3)


if __name__ == '__main__':
    unittest.main()

