"""
HistoryManager Unit Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.history_manager import HistoryManager

class TestHistoryManager(unittest.TestCase):
    """HistoryManager 클래스 테스트"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.history = HistoryManager(self.temp_dir)
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
    def test_save_load_history(self):
        """히스토리 저장 및 로드 테스트"""
        messages = [{"role": "user", "content": "hello"}]
        filename = "test_chat"
        
        # 저장
        saved_path = self.history.save_claude_history(messages, "claude-3-opus", filename)
        
        # 확인
        expected_path = self.temp_dir / ".chat_history" / "history_test_chat.json"
        self.assertTrue(expected_path.exists())
        
        # 로드
        loaded_data = self.history.load_history("history_test_chat.json")
        self.assertIsNotNone(loaded_data)
        self.assertEqual(loaded_data['model_id'], "claude-3-opus")
        self.assertEqual(loaded_data['messages'], messages)
        
    def test_list_history_files(self):
        """히스토리 파일 목록 테스트"""
        self.history.save_genai_history(["msg1"], "gemini", "chat1")
        self.history.save_genai_history(["msg2"], "gemini", "chat2")
        
        files = self.history.list_history_files()
        self.assertEqual(len(files), 2)
        self.assertIn("history_chat1.json", files)
        self.assertIn("history_chat2.json", files)

if __name__ == '__main__':
    unittest.main()
