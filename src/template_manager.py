"""
TemplateManager - 시스템 프롬프트 템플릿 관리 모듈

.system-prompts 디렉토리의 YAML 파일을 로드하여 
다양한 시스템 프롬프트를 관리하고 제공합니다.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any


class TemplateManager:
    """프롬프트 템플릿 관리자"""
    
    PROMPTS_DIR = ".system-prompts"
    
    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.prompts_path = self.workspace_dir / self.PROMPTS_DIR
        self._templates: Dict[str, Dict[str, Any]] = {}
        
        # 디렉토리가 없으면 생성 (생성자 호출 시점에는 불필요할 수 있으나 안전장치)
        if not self.prompts_path.exists():
            try:
                self.prompts_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"⚠️ 템플릿 디렉토리 생성 실패: {e}")
                
        # 초기 로드
        self.load_templates()

    def load_templates(self) -> None:
        """템플릿 디렉토리에서 YAML 파일들을 로드합니다."""
        self._templates.clear()
        
        if not self.prompts_path.exists():
            return
            
        for file in self.prompts_path.glob("*.yaml"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    
                if not data or 'name' not in data:
                    continue
                    
                name = data['name']
                self._templates[name] = data
            except Exception as e:
                print(f"⚠️ 템플릿 로드 실패 ({file.name}): {e}")

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """이름으로 템플릿 정보를 반환합니다."""
        # 최신 상태 반영을 위해 매번 로드하지 않고 캐시 사용
        # 필요 시 reload 메서드 제공
        return self._templates.get(name)

    def list_templates(self) -> List[Dict[str, str]]:
        """사용 가능한 템플릿 목록(이름, 설명)을 반환합니다."""
        self.load_templates() # 목록 조회 시에는 갱신
        
        result = []
        for name, data in self._templates.items():
            result.append({
                "name": name,
                "description": data.get("description", "설명 없음")
            })
        return sorted(result, key=lambda x: x['name'])

    def get_system_prompt(self, template_name: str, assistant_type: str = "claude") -> Optional[str]:
        """
        템플릿에서 어시스턴트 타입에 맞는 시스템 프롬프트를 추출합니다.
        
        Args:
            template_name: 템플릿 이름
            assistant_type: 'claude' 또는 'genai'
            
        Returns:
            시스템 프롬프트 문자열 또는 None
        """
        template = self.get_template(template_name)
        if not template:
            return None
            
        # 1. 전용 프롬프트 확인 (예: claude_system_prompt)
        specific_key = f"{assistant_type}_system_prompt"
        if specific_key in template:
            return template[specific_key]
            
        # 2. 공용 프롬프트 확인 (system_prompt)
        if "system_prompt" in template:
            return template["system_prompt"]
            
        return None
