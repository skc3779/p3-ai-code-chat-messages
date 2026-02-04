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

if __name__ == '__main__':
    unittest.main()
