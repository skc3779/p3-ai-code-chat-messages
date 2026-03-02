"""
ResponseParser Unit Tests
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import sys

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.response_parser import ResponseParser
from src.file_manager import FileManager

class TestResponseParser(unittest.TestCase):
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.file_manager = FileManager(self.temp_dir)
        self.parser = ResponseParser(self.file_manager)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_single_file(self):
        """단일 파일 추출 테스트"""
        response = """
Here is the code:
```filename:test.py
print('hello')
```
"""
        saved = self.parser.parse_and_save(response)
        
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0], "test.py")
        
        file_path = self.temp_dir / "test.py"
        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_text(encoding='utf-8'), "print('hello')")

    def test_parse_multiple_files(self):
        """여러 파일 추출 테스트"""
        response = """
File 1:
```filename:file1.py
code1
```

File 2:
```filename:src/file2.js
code2
```
"""
        saved = self.parser.parse_and_save(response)
        
        self.assertEqual(len(saved), 2)
        self.assertIn("file1.py", saved)
        self.assertIn("src/file2.js", saved)
        
        self.assertTrue((self.temp_dir / "file1.py").exists())
        self.assertTrue((self.temp_dir / "src" / "file2.js").exists())

    def test_parse_nested_code_blocks(self):
        """중첩된 코드 블록 처리 테스트"""
        response = """
Markdown file with code block:
```filename:README.md
Here is some python code:

## python code 1

```python
def foo():
    pass
```

## python code 2

```python
def bar():
    pass
```

## shell code 

```shell
$> python -version
```

End of file.
```
"""
        saved = self.parser.parse_and_save(response)
        
        file_path = self.temp_dir / "README.md"
        self.assertTrue(file_path.exists())
        
        content = file_path.read_text(encoding='utf-8')
        # print("content => ", content)  
        expected = """Here is some python code:

## python code 1

```python
def foo():
    pass
```

## python code 2

```python
def bar():
    pass
```

## shell code 

```shell
$> python -version
```

End of file."""
        self.assertEqual(content, expected)

    @patch('builtins.input', return_value='y')
    def test_overwrite_confirmed(self, mock_input):
        """덮어쓰기 승인 테스트"""
        # 기존 파일 생성
        (self.temp_dir / "test.txt").write_text("old", encoding='utf-8')
        
        response = """
```filename:test.txt
new
```
"""
        saved = self.parser.parse_and_save(response)
        
        content = (self.temp_dir / "test.txt").read_text(encoding='utf-8')
        self.assertEqual(content, "new")
        self.assertIn("test.txt", saved)

    @patch('builtins.input', return_value='n')
    def test_overwrite_denied(self, mock_input):
        """덮어쓰기 거부 테스트"""
        # 기존 파일 생성
        (self.temp_dir / "test.txt").write_text("old", encoding='utf-8')
        
        response = """
```filename:test.txt
new
```
"""
        saved = self.parser.parse_and_save(response)
        
        content = (self.temp_dir / "test.txt").read_text(encoding='utf-8')
        self.assertEqual(content, "old")
        self.assertNotIn("test.txt", saved)

    def test_parse_untagged_code_block(self):
        """언어 태그 없는 ``` 코드 블록 처리 테스트"""
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
        saved = self.parser.parse_and_save(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "doc.md").read_text(encoding="utf-8")
        self.assertIn("plain code", content)
        self.assertIn("End.", content)

    def test_parse_multiple_untagged_code_blocks(self):
        """다중 언어 태그 없는 코드 블록 처리 테스트"""
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
        saved = self.parser.parse_and_save(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "multi.md").read_text(encoding="utf-8")
        self.assertIn("code block 1", content)
        self.assertIn("code block 2", content)
        self.assertIn("middle text", content)
        self.assertIn("End.", content)

    def test_parse_mixed_tagged_untagged_blocks(self):
        """언어 태그 있는/없는 코드 블록이 혼합된 마크다운 테스트"""
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
        saved = self.parser.parse_and_save(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "mixed.md").read_text(encoding="utf-8")
        self.assertIn("```sql", content)
        self.assertIn("SELECT * FROM table;", content)
        self.assertIn("root", content)
        self.assertIn("├── child1", content)
        self.assertIn("### Final Section", content)
        self.assertIn("* Item 1", content)

    def test_parse_complex_markdown_full(self):
        """사용자 예시: 복잡한 마크다운 (SQL + tree + 테이블) 전체 저장 테스트"""
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
        saved = self.parser.parse_and_save(response)

        self.assertEqual(len(saved), 1)
        content = (self.temp_dir / "md_excel2" / "IF_XXXX.md").read_text(encoding="utf-8")
        self.assertIn("### 1. 실행 정책", content)
        self.assertIn("### 2. 이력", content)
        self.assertIn("```sql", content)
        self.assertIn("SELECT p.prompt_id", content)
        self.assertIn("```tree", content)
        self.assertIn("root: IF_XXXX_PROCESS", content)
        self.assertIn("### 5. 가용 명령어", content)
        self.assertIn("api.example.com", content)

    def test_parse_multi_file_with_untagged_blocks(self):
        """다중 파일 블록에서 언어 태그 없는 코드 블록 처리"""
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
        saved = self.parser.parse_and_save(response)

        self.assertEqual(len(saved), 2)
        content_a = (self.temp_dir / "file_a.md").read_text(encoding="utf-8")
        content_b = (self.temp_dir / "file_b.md").read_text(encoding="utf-8")
        self.assertIn("plain code", content_a)
        self.assertIn("End A.", content_a)
        self.assertIn("print('hello')", content_b)
        self.assertIn("End B.", content_b)


if __name__ == '__main__':
    unittest.main()

