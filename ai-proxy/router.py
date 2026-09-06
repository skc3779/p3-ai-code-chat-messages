"""
모델 ID 접두사 기반 Provider 라우팅
FSD v1.0.052 §4.5 / REQ-052-002

모델 ID 형식: "<provider>/<model-name>"
  예: "gemini/gemini-3-pro-preview" → GeminiProvider + "gemini-3-pro-preview"
  예: "claude/claude-3-5-haiku-latest" → ClaudeProvider + "claude-3-5-haiku-latest"
  예: "genai/gpt-oss-120B-medium" → GenAIProvider + "gpt-oss-120B-medium"
"""

from model_registry import (  # noqa: F401  (REQ-111-047: 하위 호환 re-export)
    MODEL_METADATA,
    SUPPORTED_MODELS,
    get_model_max_output,
)
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


def peek_providers() -> dict[str, BaseProvider]:
    """이미 생성된 Provider 인스턴스 딕셔너리의 복사본을 반환 (새로 생성하지 않음) (REQ-111-024)."""
    global _providers
    return dict(_providers)


def reset_providers() -> None:
    """Provider 캐시를 초기화한다 (종료 시 또는 테스트 격리용) (REQ-111-024)."""
    global _providers
    _providers.clear()




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
