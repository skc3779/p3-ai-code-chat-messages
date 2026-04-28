"""
CodeExecutor Unit Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.code_executor import CodeExecutor
from src.terminal_executor import TerminalExecutor

class TestCodeExecutor(unittest.TestCase):
    """CodeExecutor 클래스 테스트"""
    
    def setUp(self):
        """테스트 환경 설정"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.executor = CodeExecutor(self.temp_dir, timeout=10)

        # print(f"support language: ${self.executor.SUPPORTED_LANGUAGES}")
    
    def tearDown(self):
        """테스트 환경 정리"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_execute_python_success(self):
        """Python 코드 실행 성공 테스트"""
        code = "print('Hello, World!')"
        result = self.executor.execute(code, 'python')
        
        self.assertTrue(result['success'])
        self.assertIn('Hello, World!', result['stdout'])
        self.assertEqual(result['returncode'], 0)

    def test_execute_powershell_success(self):
        """powershell 코드 실행 성공 테스트"""
        code = "write-Host 'Hello, World!'"
        result = self.executor.execute(code, 'powershell')
        
        self.assertTrue(result['success'])
        self.assertIn('Hello, World!', result['stdout'])
        self.assertEqual(result['returncode'], 0)

    def test_execute_python_error(self):
        """Python 코드 실행 오류 테스트"""
        code = "print(undefined_variable)"
        result = self.executor.execute(code, 'python')
        
        self.assertFalse(result['success'])
        self.assertIn('NameError', result['stderr'])
    
    def test_execute_unsupported_language(self):
        """지원하지 않는 언어 테스트"""
        result = self.executor.execute("code", 'ruby')
        
        self.assertFalse(result['success'])
        self.assertIn('지원하지 않는 언어', result['error'])
    
    def test_extract_code_from_response_filename_format(self):
        """filename: 형식 코드 추출 테스트"""
        response = """
```filename:test.py
print('hello')
```
"""
        blocks = self.executor.extract_code_from_response(response)
        
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['filepath'], 'test.py')
        self.assertEqual(blocks[0]['code'], "print('hello')")
        self.assertEqual(blocks[0]['language'], 'python')
    
    def test_extract_code_from_response_language_powershell_format(self):
        """언어 식별자 형식 powershell 코드 추출 테스트"""
        response = """
```powershell
write-Host "hello"
```
"""
        blocks = self.executor.extract_code_from_response(response)
        
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['language'], 'powershell')
        self.assertIn('write-Host "hello"', blocks[0]['code'])

    def test_extract_code_from_response_language_python_format(self):
        """언어 식별자 형식 python 코드 추출 테스트"""
        response = """
```python
x = 1 + 1
print(x)
```
"""
        blocks = self.executor.extract_code_from_response(response)
        
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['language'], 'python')
        self.assertIn('print(x)', blocks[0]['code'])
    
    def test_extract_multiple_code_blocks(self):
        """여러 코드 블록 추출 테스트"""
        response = """
```filename:file1.py
code1
```

```filename:file2.js
code2
```
"""
        blocks = self.executor.extract_code_from_response(response)
        self.assertEqual(len(blocks), 2)

    @patch.object(TerminalExecutor, 'get_shell_type', return_value='Windows PowerShell')
    def test_shell_config_windows(self, _mock):
        """Windows PowerShell 환경에서 쉘(bash/powershell) 설정 테스트"""
        executor = CodeExecutor(self.temp_dir)

        self.assertIn('bash', executor.SUPPORTED_LANGUAGES)
        lang_config = executor.SUPPORTED_LANGUAGES['bash']
        self.assertEqual(lang_config['cmd'], 'pwsh.exe')
        self.assertEqual(lang_config['ext'], '.ps1')
        self.assertIn('-File', lang_config['args'])

        self.assertIn('powershell', executor.SUPPORTED_LANGUAGES)
        self.assertEqual(executor.SUPPORTED_LANGUAGES['powershell']['cmd'], 'pwsh.exe')
        self.assertEqual(executor.SUPPORTED_LANGUAGES['ps1']['cmd'], 'pwsh.exe')

    @patch.object(TerminalExecutor, 'get_shell_type', return_value='Linux')
    def test_shell_config_linux(self, _mock):
        """Linux 환경에서 쉘(bash/sh) 설정 테스트"""
        executor = CodeExecutor(self.temp_dir)

        self.assertIn('bash', executor.SUPPORTED_LANGUAGES)
        lang_config = executor.SUPPORTED_LANGUAGES['bash']
        self.assertEqual(lang_config['cmd'], '/bin/bash')
        self.assertEqual(lang_config['ext'], '.sh')
        self.assertEqual(lang_config['args'], [])

        self.assertIn('sh', executor.SUPPORTED_LANGUAGES)
        self.assertEqual(executor.SUPPORTED_LANGUAGES['sh']['cmd'], '/bin/bash')

    def test_execute_shell_basic(self):
        """현재 OS 환경에서 기본적인 쉘 명령 실행 테스트"""
        # 간단한 메아리(echo) 명령 실행
        code = "echo hello"
        result = self.executor.execute(code, 'bash')
        
        self.assertTrue(result['success'])
        self.assertIn('hello', result['stdout'].lower())
        self.assertEqual(result['returncode'], 0)

if __name__ == '__main__':
    unittest.main()
