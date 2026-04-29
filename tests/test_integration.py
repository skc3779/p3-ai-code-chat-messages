"""
Integration Tests
"""

import unittest
import tempfile
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.code_executor import CodeExecutor

class TestIntegration(unittest.TestCase):
    """통합 테스트"""
    
    def test_code_execution_workflow(self):
        """코드 실행 워크플로우 테스트"""
        temp_dir = Path(tempfile.mkdtemp())
        executor = CodeExecutor(temp_dir)
        
        # 1. AI 응답에서 코드 추출
        ai_response = """
다음은 계산기 코드입니다:

```filename:calculator.py
def add(a, b):
    return a + b

print(add(2, 3))
```
"""
        blocks = executor.extract_code_from_response(ai_response)
        self.assertEqual(len(blocks), 1)
        
        # 2. 추출된 코드 실행
        result = executor.execute(blocks[0]['code'], 'python')
        self.assertTrue(result['success'])
        self.assertIn('5', result['stdout'])
        
        # 정리
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
