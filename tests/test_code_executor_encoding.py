"""
CodeExecutor 자식 프로세스 UTF-8 인코딩 강제 회귀 테스트 (FSD v1.0.102)

자식 Python / PowerShell 가 이모지·한글을 `print()` 해도
`UnicodeEncodeError: 'cp949' codec ...` 로 종료되지 않음을 검증한다.
"""

import os
import platform
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.code_executor import (
    CodeExecutor,
    PS_UTF8_PREAMBLE,
    _wrap_code_for_shell,
)


class TestCodeExecutorEncoding(unittest.TestCase):
    """FSD v1.0.102 — 자식 프로세스 UTF-8 강제 테스트"""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.executor = CodeExecutor(self.temp_dir, timeout=20)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ---- T-102-01 ---------------------------------------------------------
    def test_T_102_01_python_emoji_print(self):
        """이모지 `print()` 가 UnicodeEncodeError 없이 성공한다."""
        result = self.executor.execute("print('\U0001f680 hello')", 'python')
        self.assertTrue(
            result['success'],
            msg=f"returncode={result.get('returncode')}, stderr={result.get('stderr')!r}"
        )
        self.assertEqual(result['returncode'], 0)
        self.assertIn('\U0001f680 hello', result['stdout'])

    # ---- T-102-02 ---------------------------------------------------------
    def test_T_102_02_python_korean_and_emoji(self):
        """한글 + 이모지 혼합 출력도 성공한다."""
        result = self.executor.execute("print('안녕 ✨ world')", 'python')
        self.assertTrue(result['success'], msg=result.get('stderr'))
        self.assertIn('안녕', result['stdout'])
        self.assertIn('✨', result['stdout'])

    # ---- T-102-03 ---------------------------------------------------------
    def test_T_102_03_python_default_open_is_utf8(self):
        """PYTHONUTF8=1 로 자식의 open() 기본 인코딩이 UTF-8 이다."""
        code = textwrap.dedent("""\
            with open('a.txt', 'w') as f:
                f.write('\U0001f680')
            with open('a.txt', 'r') as f:
                print(f.read())
        """)
        result = self.executor.execute(code, 'python')
        self.assertTrue(result['success'], msg=result.get('stderr'))
        self.assertIn('\U0001f680', result['stdout'])

    # ---- T-102-04 ---------------------------------------------------------
    def test_T_102_04_child_stdout_encoding_is_utf8(self):
        """자식 Python 의 sys.stdout.encoding 이 utf-8 으로 설정된다."""
        result = self.executor.execute(
            "import sys; print(sys.stdout.encoding)", 'python'
        )
        self.assertTrue(result['success'], msg=result.get('stderr'))
        self.assertIn('utf-8', result['stdout'].strip().lower())

    # ---- T-102-05 ---------------------------------------------------------
    def test_T_102_05_python_stderr_emoji(self):
        """stderr 로 출력되는 이모지도 UnicodeEncodeError 없이 캡처된다."""
        code = "import sys; print('err\U0001f525', file=sys.stderr)"
        result = self.executor.execute(code, 'python')
        self.assertEqual(result['returncode'], 0)
        self.assertIn('err\U0001f525', result['stderr'])

    # ---- T-102-06 ---------------------------------------------------------
    @unittest.skipUnless(
        platform.system() == 'Windows',
        "PowerShell 전용 테스트 (Windows 에서만 실행)"
    )
    def test_T_102_06_powershell_korean_emoji(self):
        """PowerShell 자식이 한글·이모지 출력을 UTF-8 로 내보낸다."""
        result = self.executor.execute("Write-Host '한글\U0001f680'", 'powershell')
        self.assertTrue(
            result['success'],
            msg=f"returncode={result.get('returncode')}, stderr={result.get('stderr')!r}"
        )
        self.assertIn('한글', result['stdout'])
        self.assertIn('\U0001f680', result['stdout'])

    # ---- T-102-07 ---------------------------------------------------------
    @unittest.skipUnless(
        platform.system() == 'Windows',
        "PowerShell 전용 테스트 (Windows 에서만 실행)"
    )
    def test_T_102_07_powershell_chcp_message_suppressed(self):
        """PS 프리앰블의 `chcp 65001` 메시지가 stdout 에 누출되지 않는다."""
        result = self.executor.execute("Write-Host 'hi'", 'powershell')
        self.assertTrue(result['success'], msg=result.get('stderr'))
        self.assertNotIn('Active code page', result['stdout'])
        self.assertNotIn('65001', result['stdout'])

    # ---- T-102-08 ---------------------------------------------------------
    def test_T_102_08_parent_os_environ_not_polluted(self):
        """_build_child_env() 호출 전후 부모 os.environ 이 변경되지 않는다."""
        before = dict(os.environ)
        env = self.executor._build_child_env()
        after = dict(os.environ)

        self.assertEqual(before, after, "os.environ 이 변경되면 안 됨")
        self.assertEqual(env['PYTHONIOENCODING'], self.executor.DEFAULT_ENCODING)
        self.assertEqual(env['PYTHONUTF8'], '1')
        # 복사본이라 별개 객체여야 함
        self.assertIsNot(env, os.environ)

    # ---- T-102-09 ---------------------------------------------------------
    def test_T_102_09_setdefault_respects_user_locale(self):
        """사용자가 설정해둔 LC_ALL / LANG 을 setdefault 로 존중한다."""
        with patch.dict(os.environ, {'LC_ALL': 'ko_KR.UTF-8', 'LANG': 'ko_KR.UTF-8'},
                        clear=False):
            env = self.executor._build_child_env()
            self.assertEqual(env['LC_ALL'], 'ko_KR.UTF-8')
            self.assertEqual(env['LANG'], 'ko_KR.UTF-8')
            # PYTHONIOENCODING / PYTHONUTF8 은 항상 덮어씀
            self.assertEqual(env['PYTHONIOENCODING'], self.executor.DEFAULT_ENCODING)
            self.assertEqual(env['PYTHONUTF8'], '1')

    # ---- T-102-10 ---------------------------------------------------------
    def test_T_102_10_default_encoding_roundtrip(self):
        """기본 CODE_EXECUTOR_ENCODING(utf-8) 에서 T-102-01 이 여전히 성공한다."""
        self.assertEqual(self.executor.DEFAULT_ENCODING.lower(), 'utf-8')
        result = self.executor.execute("print('\U0001f680')", 'python')
        self.assertTrue(result['success'], msg=result.get('stderr'))
        self.assertIn('\U0001f680', result['stdout'])

    # ---- T-102-11 ---------------------------------------------------------
    def test_T_102_11_readme_slice_with_emoji_golden(self):
        """원인 재현 골든 테스트: readme.md 앞 50자에 🚀 포함 → 성공."""
        readme = self.temp_dir / 'readme.md'
        readme.write_text(
            "# Project Title\n\U0001f680 AI Code Chat — UTF-8 emoji test file\n",
            encoding='utf-8'
        )
        code = (
            "with open('readme.md', 'r', encoding='utf-8') as f:\n"
            "    print(f.read()[:50] + '...')\n"
        )
        result = self.executor.execute(code, 'python')
        self.assertTrue(
            result['success'],
            msg=f"returncode={result.get('returncode')}, stderr={result.get('stderr')!r}"
        )
        self.assertIn('\U0001f680', result['stdout'])
        self.assertNotIn('UnicodeEncodeError', result.get('stderr', ''))

    # ---- 보조: _wrap_code_for_shell 분기 동작 -----------------------------
    def test_wrap_code_for_shell_python_passthrough(self):
        """Python (.py) 은 프리앰블 없이 원본 그대로 반환."""
        self.assertEqual(
            _wrap_code_for_shell("print(1)", {'ext': '.py'}),
            "print(1)",
        )

    def test_wrap_code_for_shell_ps1_prepends_preamble(self):
        """.ps1 은 PS_UTF8_PREAMBLE 이 선두에 삽입된다."""
        wrapped = _wrap_code_for_shell("Write-Host 'x'", {'ext': '.ps1'})
        self.assertTrue(wrapped.startswith(PS_UTF8_PREAMBLE))
        self.assertTrue(wrapped.endswith("Write-Host 'x'"))


if __name__ == '__main__':
    unittest.main()
