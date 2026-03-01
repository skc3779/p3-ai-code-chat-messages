"""
모델 ID 접두사 기반 Provider 라우팅
FSD v1.0.052 §4.5 / REQ-052-002

모델 ID 형식: "<provider>/<model-name>"
  예: "gemini/gemini-3-pro-preview" → GeminiProvider + "gemini-3-pro-preview"
  예: "claude/claude-3-5-haiku-latest" → ClaudeProvider + "claude-3-5-haiku-latest"
  예: "genai/gpt-oss-120B-medium" → GenAIProvider + "gpt-oss-120B-medium"
"""

from providers import GeminiProvider, ClaudeProvider, GenAIProvider
from providers.base import BaseProvider

# Provider 싱글톤 인스턴스
_providers: dict[str, BaseProvider] = {}


def _get_providers() -> dict[str, BaseProvider]:
    """Provider 인스턴스를 lazy 초기화 (환경변수 로드 후 호출되도록)"""
    global _providers
    if not _providers:
        _providers = {
            "gemini": GeminiProvider(),
            "claude": ClaudeProvider(),
            "genai": GenAIProvider(),
        }
    return _providers


# 지원 모델 목록
SUPPORTED_MODELS = {
    "gemini/gemini-3-pro-preview": "Google Gemini 3 Pro",
    "gemini/gemini-3-flash-preview": "Google Gemini 3 Flash",
    "claude/claude-3-5-haiku-latest": "Anthropic Claude 3.5 Haiku",
    "claude/claude-sonnet-4-5": "Anthropic Claude Sonnet 4.5",
    "genai/gpt-oss-120B-medium": "Samsung SCI Portal GPT-OSS 120B Medium",
}


def route_model(model_id: str) -> tuple[BaseProvider, str]:
    """
    모델 ID에서 접두사를 분리하여 Provider와 실제 모델명을 반환.
    
    Args:
        model_id: "gemini/gemini-3-pro-preview" 형식

    Returns:
        (Provider 인스턴스, 실제 모델 ID)

    Raises:
        ValueError: 알 수 없는 접두사
    """
    providers = _get_providers()

    parts = model_id.split("/", 1)
    if len(parts) != 2 or parts[0] not in providers:
        available = ", ".join(f'"{k}/"' for k in providers.keys())
        raise ValueError(
            f"Unknown model: '{model_id}'. "
            f"Use prefix: {available}"
        )

    return providers[parts[0]], parts[1]
