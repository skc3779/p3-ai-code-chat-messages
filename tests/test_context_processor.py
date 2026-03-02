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


class TestContextProcessor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.file_manager = FileManager(self.temp_dir)

        # 테스트 파일 생성
        (self.temp_dir / "file1.md").write_text("Content of file1", encoding="utf-8")
        (self.temp_dir / "file2.md").write_text("Content of file2", encoding="utf-8")

        # Mock assistant
        self.mock_assistant = MagicMock()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_process_single_file_with_auto_save(self):
        """단일 파일 처리 + 자동 저장 테스트"""
        # AI 응답에 filename: 블록 포함
        self.mock_assistant.chat.return_value = (
            "번역 결과입니다.\n"
            "```filename:output/file1.md\n"
            "번역된 내용\n"
            "```"
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
        self.assertTrue((self.temp_dir / "output" / "file1.md").exists())
        self.assertEqual(
            (self.temp_dir / "output" / "file1.md").read_text(encoding="utf-8"),
            "번역된 내용"
        )

    def test_process_multiple_files(self):
        """여러 파일 순차 처리 테스트"""
        self.mock_assistant.chat.side_effect = [
            "```filename:output/file1.md\n번역1\n```",
            "```filename:output/file2.md\n번역2\n```",
        ]

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [
            self.temp_dir / "file1.md",
            self.temp_dir / "file2.md",
        ]
        processed, saved = processor.process_files(matched_files, "번역해줘")

        self.assertEqual(processed, 2)
        self.assertEqual(saved, 2)
        self.assertEqual(self.mock_assistant.chat.call_count, 2)

    def test_multiple_output_files_per_input(self):
        """1개 입력 → 다중 출력 파일 테스트"""
        self.mock_assistant.chat.return_value = (
            "```filename:src/service.java\nclass Service {}\n```\n"
            "```filename:src/interface.java\ninterface IService {}\n```"
        )

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "코드 생성해줘")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 2)
        self.assertTrue((self.temp_dir / "src" / "service.java").exists())
        self.assertTrue((self.temp_dir / "src" / "interface.java").exists())

    def test_no_filename_block_in_response(self):
        """AI 응답에 filename: 블록이 없는 경우"""
        self.mock_assistant.chat.return_value = "일반 텍스트 응답입니다."

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [self.temp_dir / "file1.md"]
        processed, saved = processor.process_files(matched_files, "질문")

        self.assertEqual(processed, 1)
        self.assertEqual(saved, 0)

    def test_build_prompt(self):
        """프롬프트 조합 테스트"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )
        prompt = processor._build_prompt("번역해줘", Path("file1.md"), "파일 내용")

        self.assertIn("번역해줘", prompt)
        self.assertIn("--- 파일: file1.md ---", prompt)
        self.assertIn("파일 내용", prompt)
        self.assertIn("--- 파일 끝 ---", prompt)

    def test_auto_save_creates_parent_dirs(self):
        """자동 저장 시 상위 디렉토리 자동 생성 테스트"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )

        response = "```filename:deep/nested/dir/file.txt\n내용\n```"
        saved = processor._auto_save_files(response)

        self.assertEqual(len(saved), 1)
        self.assertTrue((self.temp_dir / "deep" / "nested" / "dir" / "file.txt").exists())

    def test_auto_save_overwrites_existing(self):
        """기존 파일 자동 덮어쓰기 테스트 (확인 없이)"""
        existing = self.temp_dir / "existing.txt"
        existing.write_text("old content", encoding="utf-8")

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )

        response = "```filename:existing.txt\nnew content\n```"
        saved = processor._auto_save_files(response)

        self.assertEqual(len(saved), 1)
        self.assertEqual(existing.read_text(encoding="utf-8"), "new content")

    def test_auto_save_nested_code_blocks(self):
        """중첩된 코드 블록 처리 테스트"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )

        response = (
            "```filename:README.md\n"
            "# Hello\n"
            "```python\n"
            "print('hello')\n"
            "```\n"
            "End.\n"
            "```"
        )
        saved = processor._auto_save_files(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "README.md").read_text(encoding="utf-8")
        self.assertIn("```python", content)
        self.assertIn("print('hello')", content)

    def test_file_read_failure_continues(self):
        """파일 읽기 실패 시 다음 파일로 계속"""
        self.mock_assistant.chat.return_value = "```filename:out.md\n결과\n```"

        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
            streaming=False
        )

        matched_files = [
            self.temp_dir / "nonexistent.md",  # 존재하지 않는 파일
            self.temp_dir / "file1.md",         # 존재하는 파일
        ]
        processed, saved = processor.process_files(matched_files, "질문")

        # 첫 번째 파일 실패, 두 번째 파일 성공
        self.assertEqual(processed, 1)
        self.assertEqual(saved, 1)

    def test_auto_save_untagged_code_block(self):
        """언어 태그 없는 ``` 코드 블록 처리 테스트"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )

        response = (
            "```filename:doc.md\n"
            "# Title\n"
            "\n"
            "```\n"
            "plain code\n"
            "```\n"
            "\n"
            "End.\n"
            "```"
        )
        saved = processor._auto_save_files(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "doc.md").read_text(encoding="utf-8")
        self.assertIn("plain code", content)
        self.assertIn("End.", content)

    def test_auto_save_multiple_untagged_code_blocks(self):
        """다중 언어 태그 없는 코드 블록 처리 테스트"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )

        response = (
            "```filename:multi.md\n"
            "# Title\n"
            "\n"
            "```\n"
            "code block 1\n"
            "```\n"
            "\n"
            "middle text\n"
            "\n"
            "```\n"
            "code block 2\n"
            "```\n"
            "\n"
            "End.\n"
            "```"
        )
        saved = processor._auto_save_files(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "multi.md").read_text(encoding="utf-8")
        self.assertIn("code block 1", content)
        self.assertIn("code block 2", content)
        self.assertIn("middle text", content)
        self.assertIn("End.", content)

    def test_auto_save_mixed_tagged_untagged_blocks(self):
        """언어 태그 있는/없는 코드 블록이 혼합된 마크다운 테스트"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )

        response = (
            "```filename:mixed.md\n"
            "## 상세 설계서\n"
            "\n"
            "### SQL Section\n"
            "\n"
            "```sql\n"
            "SELECT * FROM table;\n"
            "```\n"
            "\n"
            "---\n"
            "\n"
            "### Tree Section\n"
            "\n"
            "```\n"
            "root\n"
            "├── child1\n"
            "└── child2\n"
            "```\n"
            "\n"
            "---\n"
            "\n"
            "### Final Section\n"
            "\n"
            "* Item 1\n"
            "* Item 2\n"
            "\n"
            "```"
        )
        saved = processor._auto_save_files(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "mixed.md").read_text(encoding="utf-8")
        self.assertIn("```sql", content)
        self.assertIn("SELECT * FROM table;", content)
        self.assertIn("root", content)
        self.assertIn("├── child1", content)
        self.assertIn("### Final Section", content)
        self.assertIn("* Item 1", content)

    def test_auto_save_complex_markdown_full(self):
        """사용자 예시: 복잡한 마크다운 (SQL + tree + 테이블) 전체 저장 테스트"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )

        response = (
            "```filename:md_excel2/IF_XXXX.md\n"
            "\n"
            "## 📂 IF_XXXX: 상세 설계서\n"
            "\n"
            "### 1. 실행 정책\n"
            "\n"
            "* **트랜잭션**: `None`\n"
            "\n"
            "---\n"
            "\n"
            "### 2. 이력\n"
            "\n"
            "| 버전 | 날짜 |\n"
            "| --- | --- |\n"
            "| v1.0.001 | 2026-01-19 |\n"
            "\n"
            "---\n"
            "\n"
            "### 3. SQL\n"
            "\n"
            "```sql\n"
            "SELECT p.prompt_id\n"
            "FROM IF_PROMPT_CONFIG p\n"
            "WHERE p.if_id = 'IF_XXXX';\n"
            "\n"
            "```\n"
            "\n"
            "---\n"
            "\n"
            "### 4. 프로세스 흐름\n"
            "\n"
            "```tree\n"
            "root: IF_XXXX_PROCESS\n"
            "├── [Step 1] Pre-Processing\n"
            "└── [Step 2] Finalization\n"
            "\n"
            "```\n"
            "\n"
            "---\n"
            "\n"
            "### 5. 가용 명령어\n"
            "\n"
            "* **API Endpoint**: `https://api.example.com`\n"
            "\n"
            "```"
        )
        saved = processor._auto_save_files(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "md_excel2" / "IF_XXXX.md").read_text(encoding="utf-8")
        # 모든 섹션이 포함되어 있어야 함
        self.assertIn("### 1. 실행 정책", content)
        self.assertIn("### 2. 이력", content)
        self.assertIn("```sql", content)
        self.assertIn("SELECT p.prompt_id", content)
        self.assertIn("```tree", content)
        self.assertIn("root: IF_XXXX_PROCESS", content)
        self.assertIn("### 5. 가용 명령어", content)
        self.assertIn("api.example.com", content)

    def test_auto_save_multi_file_with_untagged_blocks(self):
        """다중 파일 블록에서 언어 태그 없는 코드 블록 처리"""
        processor = ContextProcessor(
            assistant=self.mock_assistant,
            file_manager=self.file_manager,
        )

        response = (
            "답변입니다.\n"
            "\n"
            "```filename:file_a.md\n"
            "# File A\n"
            "\n"
            "```\n"
            "plain code\n"
            "```\n"
            "\n"
            "End A.\n"
            "```\n"
            "\n"
            "```filename:file_b.md\n"
            "# File B\n"
            "\n"
            "```python\n"
            "print('hello')\n"
            "```\n"
            "\n"
            "End B.\n"
            "```"
        )
        saved = processor._auto_save_files(response)

        self.assertEqual(len(saved), 2)
        content_a = (self.temp_dir / "file_a.md").read_text(encoding="utf-8")
        content_b = (self.temp_dir / "file_b.md").read_text(encoding="utf-8")
        self.assertIn("plain code", content_a)
        self.assertIn("End A.", content_a)
        self.assertIn("print('hello')", content_b)
        self.assertIn("End B.", content_b)


if __name__ == '__main__':
    unittest.main()

