"""
TemplateManager - 시스템 프롬프트 템플릿 관리 모듈

.system-prompts 디렉토리의 YAML 파일을 로드하여 
다양한 시스템 프롬프트를 관리하고 제공합니다.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any


class TemplateManager:
    """프롬프트 템플릿 관리자"""
    
    PROMPTS_DIR = ".system_prompts"
    
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

    def list_templates(self, assistant_type: Optional[str] = None) -> List[Dict[str, str]]:
        """
        사용 가능한 템플릿 목록(이름, 설명, assistant_type)을 반환합니다.

        Args:
            assistant_type: 지정 시 해당 타입의 템플릿만 포함한다.
                YAML 의 `assistant_type` 필드가 일치하거나 필드가 없는 경우(공용)
                모두 포함된다. `None` 이면 모든 템플릿을 반환한다 (호환성 유지).
        """
        self.load_templates()  # 목록 조회 시에는 갱신

        result = []
        for name, data in self._templates.items():
            tpl_type = data.get("assistant_type")
            if assistant_type is not None and tpl_type and tpl_type != assistant_type:
                continue  # 타입 지정이 있고 명시된 타입과 다르면 제외
            result.append({
                "name": name,
                "description": data.get("description", "설명 없음"),
                "assistant_type": tpl_type or "",
            })
        return sorted(result, key=lambda x: x['name'])

    def get_template_info(self, name: str) -> Optional[Dict[str, str]]:
        """
        템플릿의 메타정보(name, description, assistant_type)를 반환합니다.

        파일명 stem 으로 직접 로드한 템플릿(`.env` 의 `DEFAULT_*_TEMPLATE` 으로
        지정되었지만 `name:` 필드가 다른 경우)도 처리하기 위해, 캐시 미스 시
        파일 시스템에서 직접 읽는다.
        """
        # 1) 캐시 (name 필드 기준) 우선
        data = self._templates.get(name)
        if data:
            return {
                "name": data.get("name", name),
                "description": data.get("description", "설명 없음"),
                "assistant_type": data.get("assistant_type", ""),
            }

        # 2) 파일명 stem 으로 직접 로드 시도
        stem = name
        if stem.lower().endswith(".yaml"):
            stem = stem[:-5]
        file_path = self.prompts_path / f"{stem}.yaml"
        if file_path.is_file():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                return {
                    "name": data.get("name", stem),
                    "description": data.get("description", "설명 없음"),
                    "assistant_type": data.get("assistant_type", ""),
                }
            except Exception as e:
                print(f"⚠️ 템플릿 메타 로드 실패 ({file_path.name}): {e}")
        return None

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

    # ─── FSD v1.0.161: 파일명 stem 우선 조회 ─────────────────────────────
    def resolve_default_template(
        self,
        env_value: Optional[str],
        assistant_type: str,
    ) -> Optional[str]:
        """
        `.env` 의 DEFAULT_*_TEMPLATE 값을 파일명 stem 으로 해석해 raw 본문을 반환한다.

        조회 순서:
          1) `<workspace>/.system_prompts/<stem>.yaml` 파일이 있으면 직접 로드
          2) 없으면 `name:` 필드 기준으로 캐시 조회 (`get_system_prompt`)

        Args:
            env_value: `.env` 에 정의된 값 (`None` / 빈 문자열 가능).
                       `.yaml` 확장자가 포함되어도 자동으로 제거한다.
            assistant_type: `claude` | `gemini` | `genai`.

        Returns:
            원본(raw) 시스템 프롬프트 문자열, 없으면 `None`.
        """
        if not env_value:
            env_value = f"{assistant_type}-system-prompt"
        stem = env_value.strip()
        if stem.lower().endswith(".yaml"):
            stem = stem[:-5]

        # 1) 파일명으로 직접 로드
        file_path = self.prompts_path / f"{stem}.yaml"
        # print(f"⚠️ Trying to load template from file: {file_path}")
        if file_path.is_file():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                specific = data.get(f"{assistant_type}_system_prompt")
                if specific:
                    return specific
                common = data.get("system_prompt")
                if common:
                    return common
            except Exception as e:
                print(f"⚠️ 기본 템플릿 로드 실패 ({file_path.name}): {e}")

        # 2) name: 필드로 fallback 조회
        return self.get_system_prompt(stem, assistant_type)
