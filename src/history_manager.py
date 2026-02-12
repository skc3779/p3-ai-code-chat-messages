"""
HistoryManager - 대화 히스토리 영속화 모듈
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Union


class HistoryManager:
    """대화 히스토리 저장/로드 관리"""
    
    def __init__(self, workspace_dir: Union[str, Path]):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.history_dir = self.workspace_dir / ".chat_history"
        self.history_dir.mkdir(exist_ok=True)
    
    def save_claude_history(self, messages: List[Dict], model_id: str, 
                            filepath: Optional[str] = None) -> str:
        """Claude 형식 히스토리 저장 (Dict 기반)"""
        data = {
            "version": "1.0",
            "type": "claude",
            "created_at": datetime.now().isoformat(),
            "model_id": model_id,
            "messages": messages
        }
        return self._save_json(data, filepath)
    
    def save_genai_history(self, messages: List[str], model_id: str,
                           filepath: Optional[str] = None) -> str:
        """GenAI 형식 히스토리 저장 (String 리스트 기반)"""
        data = {
            "version": "1.0",
            "type": "genai",
            "created_at": datetime.now().isoformat(),
            "model_id": model_id,
            "messages": messages
        }
        return self._save_json(data, filepath)
    
    def save_gemini_history(self, messages: List[Dict], model_id: str,
                            filepath: Optional[str] = None) -> str:
        """Gemini 형식 히스토리 저장 (Dict 기반, role: user/model)"""
        data = {
            "version": "1.0",
            "type": "gemini",
            "created_at": datetime.now().isoformat(),
            "model_id": model_id,
            "messages": messages
        }
        return self._save_json(data, filepath)
    
    def _save_json(self, data: Dict, filepath: Optional[str] = None) -> str:
        """JSON 파일로 저장"""
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"history_{timestamp}.json"
        else:
            filepath = f"history_{filepath}.json"
        
        print(f"💾 히스토리 파일 저장: {filepath}")
        full_path = self.history_dir / filepath
        
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return str(full_path)
    
    def load_history(self, filepath: str) -> Optional[Dict]:
        """히스토리 파일 로드"""
        full_path = self.history_dir / filepath
        
        if not full_path.exists():
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def list_history_files(self) -> List[str]:
        """저장된 히스토리 파일 목록"""
        return [f.name for f in self.history_dir.glob("*.json")]
