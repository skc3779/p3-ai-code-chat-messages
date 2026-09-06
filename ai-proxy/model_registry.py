"""
모델 레지스트리 — 모델별 메타데이터 및 지원 모델 목록
REQ-111-045, REQ-111-046

REQ-111-047: router.py 에서 분리한 이유 —
  claude_provider 가 get_model_max_output() 을 필요로 하는데 router 는
  providers 패키지를 import 하므로 순환 import 가 발생한다.
  이 모듈은 providers 에 의존하지 않으므로 양쪽에서 안전하게 import 할 수 있다.
"""

from typing import Any



# REQ-111-045: 모델별 메타데이터 (opencode.json과의 단일 진실 소스)
MODEL_METADATA: dict[str, dict[str, Any]] = {
    "genai/gpt-oss-120B-medium": {
        "name": "Samsung SCI Portal GPT-OSS 120B Medium",
        "limit": {
            "context": 200000,
            "output": 4096,
        },
    },
    "genai/glm5.2": {
        "name": "Samsung SCI Portal GLM 5.2",
        "limit": {
            "context": 128000,
            "output": 4096,
        },
    },
    "claude/claude-haiku-4-5": {
        "name": "Anthropic Claude Haiku 4.5",
        "limit": {
            "context": 200000,
            "output": 65536,
        },
    },
    "claude/claude-sonnet-4-6": {
        "name": "Anthropic Claude Sonnet 4.6",
        "limit": {
            "context": 200000,
            "output": 65536,
        },
    },
    "gemini/gemini-3-pro-preview": {
        "name": "Google Gemini 3 Pro",
        "limit": {
            "context": 1048576,
            "output": 65536,
        },
    },
    "gemini/gemini-3-flash-preview": {
        "name": "Google Gemini 3 Flash",
        "limit": {
            "context": 1048576,
            "output": 65536,
        },
    },
}

# REQ-111-046: 지원 모델 목록 (중복 제거 및 genai/glm5.2 등록)
SUPPORTED_MODELS = {
    "gemini/gemini-3-pro-preview": "Google Gemini 3 Pro",
    "gemini/gemini-3-flash-preview": "Google Gemini 3 Flash",
    "claude/claude-haiku-4-5": "Anthropic Claude Haiku 4.5",
    "claude/claude-sonnet-4-6": "Anthropic Claude Sonnet 4.6",
    "genai/gpt-oss-120B-medium": "Samsung SCI Portal GPT-OSS 120B Medium",
    "genai/glm5.2": "Samsung SCI Portal GLM 5.2",
}


def get_model_max_output(model_id: str, default: int = 4096) -> int:
    """
    모델별 최대 출력 토큰 한도(max_output)를 반환 (REQ-111-045).
    접두사 포함(예: 'claude/claude-sonnet-4-6') 또는 미포함('claude-sonnet-4-6') 모두 지원.
    """
    if model_id in MODEL_METADATA:
        return MODEL_METADATA[model_id].get("limit", {}).get("output", default)

    for prefix in ("claude/", "gemini/", "genai/"):
        full_id = f"{prefix}{model_id}"
        if full_id in MODEL_METADATA:
            return MODEL_METADATA[full_id].get("limit", {}).get("output", default)

    for key, val in MODEL_METADATA.items():
        if key.endswith(f"/{model_id}"):
            return val.get("limit", {}).get("output", default)

    return default
