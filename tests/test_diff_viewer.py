"""
DiffViewer - 단위 테스트

DiffViewer 클래스의 핵심 기능에 대한 단위 테스트입니다.
- Diff 생성
- 색상 적용
- 코드 제안 추출
- 변경 통계
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.diff_viewer import DiffViewer


class TestDiffViewer(unittest.TestCase):
    """DiffViewer 단위 테스트"""

    def setUp(self):
        """테스트 환경 설정"""
        self.diff_viewer = DiffViewer()

    def test_generate_colored_diff_no_changes(self):
        """변경 사항이 없을 때 테스트"""
        original = "line1\nline2\nline3"
        new = "line1\nline2\nline3"
        
        result = self.diff_viewer.generate_colored_diff(original, new)
        
        self.assertIn("변경 사항 없음", result)

    def test_generate_colored_diff_with_additions(self):
        """라인 추가 Diff 테스트"""
        original = "line1\nline2"
        new = "line1\nline2\nline3"
        
        result = self.diff_viewer.generate_colored_diff(original, new)
        
        # 초록색(추가) 색상 코드가 포함되어야 함
        self.assertIn(DiffViewer.COLORS['green'], result)
        self.assertIn('+line3', result)

    def test_generate_colored_diff_with_deletions(self):
        """라인 삭제 Diff 테스트"""
        original = "line1\nline2\nline3"
        new = "line1\nline2"
        
        result = self.diff_viewer.generate_colored_diff(original, new)
        
        # 빨간색(삭제) 색상 코드가 포함되어야 함
        self.assertIn(DiffViewer.COLORS['red'], result)
        self.assertIn('-line3', result)

    def test_generate_colored_diff_with_modifications(self):
        """라인 수정 Diff 테스트"""
        original = "line1\nold_content\nline3"
        new = "line1\nnew_content\nline3"
        
        result = self.diff_viewer.generate_colored_diff(original, new)
        
        # 삭제(빨간색) + 추가(초록색) 모두 포함
        self.assertIn(DiffViewer.COLORS['red'], result)
        self.assertIn(DiffViewer.COLORS['green'], result)
        self.assertIn('-old_content', result)
        self.assertIn('+new_content', result)

    def test_colorize_line_header(self):
        """헤더 라인 색상화 테스트"""
        # 파일명 헤더
        result = self.diff_viewer._colorize_line('--- original.py')
        self.assertIn(DiffViewer.COLORS['cyan'], result)
        self.assertIn(DiffViewer.COLORS['bold'], result)
        
        # 섹션 헤더
        result = self.diff_viewer._colorize_line('@@ -1,3 +1,4 @@')
        self.assertIn(DiffViewer.COLORS['yellow'], result)

    def test_colorize_line_added(self):
        """추가 라인 색상화 테스트"""
        result = self.diff_viewer._colorize_line('+new line')
        self.assertIn(DiffViewer.COLORS['green'], result)

    def test_colorize_line_deleted(self):
        """삭제 라인 색상화 테스트"""
        result = self.diff_viewer._colorize_line('-old line')
        self.assertIn(DiffViewer.COLORS['red'], result)

    def test_colorize_line_context(self):
        """컨텍스트 라인은 색상이 없어야 함"""
        result = self.diff_viewer._colorize_line(' unchanged line')
        # 색상 코드가 없어야 함
        self.assertNotIn(DiffViewer.COLORS['green'], result)
        self.assertNotIn(DiffViewer.COLORS['red'], result)

    def test_get_diff_stats(self):
        """변경 통계 테스트"""
        original = "line1\nline2\nline3"
        new = "line1\nnew_line\nline3\nline4"
        
        stats = self.diff_viewer.get_diff_stats(original, new)
        
        self.assertIn('added', stats)
        self.assertIn('deleted', stats)
        self.assertIn('total_changes', stats)
        self.assertEqual(stats['original_lines'], 3)
        self.assertEqual(stats['new_lines'], 4)

    def test_extract_code_suggestions_single_file(self):
        """단일 파일 코드 제안 추출 테스트"""
        response = """
Here is the code:

```filename:src/main.py
def hello():
    print("Hello, World!")
```

That's it!
"""
        suggestions = self.diff_viewer.extract_code_suggestions(response)
        
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['filepath'], Path('src/main.py'))
        self.assertIn('def hello():', suggestions[0]['content'])

    def test_extract_code_suggestions_multiple_files(self):
        """다중 파일 코드 제안 추출 테스트"""
        response = """
```filename:file1.py
content1
```

```filename:file2.py
content2
```
"""
        suggestions = self.diff_viewer.extract_code_suggestions(response)
        
        self.assertEqual(len(suggestions), 2)
        self.assertEqual(suggestions[0]['filepath'], Path('file1.py'))
        self.assertEqual(suggestions[1]['filepath'], Path('file2.py'))

    def test_extract_code_suggestions_with_language(self):
        """언어 태그가 있는 코드 블록 추출 테스트"""
        response = """
```python filename:test.py
print("test")
```
"""
        suggestions = self.diff_viewer.extract_code_suggestions(response)
        
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['filepath'], Path('test.py'))

    def test_generate_diff_for_existing_file(self):
        """기존 파일에 대한 Diff 생성 테스트"""
        # FileManager Mock
        file_manager = MagicMock()
        file_manager.read_file.return_value = "original content"
        
        # 임시 파일 경로 생성
        with patch.object(Path, 'exists', return_value=True):
            filepath = Path("test.py")
            new_content = "new content"
            
            diff, exists = self.diff_viewer.generate_diff_for_file(
                filepath, new_content, file_manager
            )
            
            self.assertTrue(exists)
            self.assertIn('-original content', diff)
            self.assertIn('+new content', diff)

    def test_generate_diff_for_new_file(self):
        """새 파일에 대한 Diff 생성 테스트"""
        file_manager = MagicMock()
        
        with patch.object(Path, 'exists', return_value=False):
            filepath = Path("new_file.py")
            new_content = "new content"
            
            diff, exists = self.diff_viewer.generate_diff_for_file(
                filepath, new_content, file_manager
            )
            
            self.assertFalse(exists)
            self.assertIn('+new content', diff)
            self.assertIn('(새 파일)', diff)

    def test_last_diff_storage(self):
        """마지막 Diff 저장 테스트"""
        file_manager = MagicMock()
        file_manager.read_file.return_value = "original"
        
        with patch.object(Path, 'exists', return_value=True):
            filepath = Path("test.py")
            self.diff_viewer.generate_diff_for_file(filepath, "new", file_manager)
            
            last_diff = self.diff_viewer.get_last_diff()
            
            self.assertIsNotNone(last_diff)
            self.assertEqual(last_diff['filepath'], filepath)
            self.assertEqual(last_diff['original'], "original")
            self.assertEqual(last_diff['new'], "new")

    def test_apply_diff_success(self):
        """Diff 적용 성공 테스트"""
        file_manager = MagicMock()
        file_manager.write_file.return_value = True
        
        # Diff 정보 설정
        self.diff_viewer._last_diff = {
            'filepath': Path("test.py"),
            'original': "old",
            'new': "new"
        }
        
        success, message = self.diff_viewer.apply_diff(file_manager)
        
        self.assertTrue(success)
        self.assertIn("성공", message)
        self.assertIsNone(self.diff_viewer.get_last_diff())

    def test_apply_diff_no_diff(self):
        """Diff 없이 적용 시도 테스트"""
        file_manager = MagicMock()
        
        success, message = self.diff_viewer.apply_diff(file_manager)
        
        self.assertFalse(success)
        self.assertIn("적용할 diff가 없습니다", message)

    def test_apply_diff_write_failure(self):
        """Diff 적용 실패 테스트"""
        file_manager = MagicMock()
        file_manager.write_file.return_value = False
        
        self.diff_viewer._last_diff = {
            'filepath': Path("test.py"),
            'original': "old",
            'new': "new"
        }
        
        success, message = self.diff_viewer.apply_diff(file_manager)
        
        self.assertFalse(success)
        self.assertIn("실패", message)

    def test_clear_last_diff(self):
        """Diff 초기화 테스트"""
        self.diff_viewer._last_diff = {'test': 'data'}
        
        self.diff_viewer.clear_last_diff()
        
        self.assertIsNone(self.diff_viewer.get_last_diff())

    def test_format_stats_display(self):
        """통계 표시 포맷팅 테스트"""
        stats = {
            'added': 5,
            'deleted': 3,
            'total_changes': 8,
            'original_lines': 10,
            'new_lines': 12
        }
        
        result = self.diff_viewer.format_stats_display(stats)
        
        self.assertIn("5 라인 추가", result)
        self.assertIn("3 라인 삭제", result)
        self.assertIn("8 라인 변경", result)


class TestDiffViewerIntegration(unittest.TestCase):
    """DiffViewer 통합 테스트"""

    def test_full_workflow(self):
        """전체 워크플로우 테스트: 추출 -> Diff 생성 -> 적용"""
        diff_viewer = DiffViewer()
        
        # 1. AI 응답에서 코드 추출
        response = """
Here's the updated code:

```filename:calculator.py
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
```
"""
        suggestions = diff_viewer.extract_code_suggestions(response)
        self.assertEqual(len(suggestions), 1)
        
        # 2. Diff 생성
        original = "def add(a, b):\n    return a + b"
        new = suggestions[0]['content']
        
        diff = diff_viewer.generate_colored_diff(original, new)
        self.assertIn('+def subtract', diff)
        
        # 3. 통계 확인
        stats = diff_viewer.get_diff_stats(original, new)
        self.assertGreater(stats['added'], 0)


if __name__ == '__main__':
    unittest.main()
