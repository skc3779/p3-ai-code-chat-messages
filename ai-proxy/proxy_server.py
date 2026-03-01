"""
OpenAI 호환 프록시 서버 (FastAPI)
FSD v1.0.052 §4.2 / REQ-052-001, REQ-052-006, REQ-052-007, REQ-052-008, REQ-052-009, REQ-052-010

엔드포인트:
  POST /v1/chat/completions  - 채팅 완성 (OpenAI 호환)
  GET  /v1/models            - 지원 모델 목록
  GET  /health               - 서버 상태 확인
"""

import os
import logging

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from models import (
    ChatCompletionRequest,
    ErrorResponse,
    ErrorDetail,
)
from router import route_model, SUPPORTED_MODELS
from providers.base import ProviderError

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ai-proxy")

# FastAPI 앱
app = FastAPI(
    title="AI Proxy Server",
    description="OpenAI 호환 로컬 프록시 서버 (GenAI/Claude/Gemini)",
    version="1.0.052",
)

PROXY_API_KEY = os.getenv("AI_PROXY_API_KEY")


# ── 인증 헬퍼 ──

def verify_auth(authorization: str | None):
    """Bearer 토큰 인증 (REQ-052-009)"""
    if not PROXY_API_KEY:
        return  # 키 미설정 시 인증 비활성화

    if not authorization or authorization != f"Bearer {PROXY_API_KEY}":
        logger.error(f"Unauthorized: {authorization}")
        logger.error(f"Expected: Bearer {PROXY_API_KEY}")
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error=ErrorDetail(
                    message="Unauthorized. Provide valid 'Authorization: Bearer <key>' header.",
                    type="authentication_error",
                    code=401,
                )
            ).model_dump(),
        )


# ── 엔드포인트 ──

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: str | None = Header(None),
):
    """
    OpenAI 호환 Chat Completions 엔드포인트 (REQ-052-001)
    
    모델 ID 접두사로 공급자를 자동 라우팅합니다:
      - gemini/... → Google Gemini
      - claude/... → Anthropic Claude
      - genai/...  → Samsung SCI Portal
    """
    verify_auth(authorization)

    # 모델 라우팅 (REQ-052-002)
    try:
        provider, actual_model = route_model(request.model)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=ErrorDetail(message=str(e))
            ).model_dump(),
        )

    # 라우팅된 실제 모델 ID로 교체
    original_model = request.model
    request.model = actual_model

    logger.info(f"→ {original_model} (provider: {original_model.split('/')[0]}, model: {actual_model})")

    try:
        if request.stream:
            # 스트리밍 (REQ-052-008)
            return StreamingResponse(
                provider.stream(request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
        else:
            # 비스트리밍 (REQ-052-007)
            result = await provider.chat(request)
            # 응답에는 원래 model ID(접두사 포함) 반환
            result.model = original_model
            return result

    except ProviderError as e:
        logger.error(f"Provider error ({e.status_code}): {e}")
        raise HTTPException(
            status_code=e.status_code,
            detail=ErrorResponse(
                error=ErrorDetail(
                    message=str(e),
                    type="proxy_error",
                    code=e.status_code,
                )
            ).model_dump(),
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=502,
            detail=ErrorResponse(
                error=ErrorDetail(
                    message=f"Provider error: {str(e)}",
                    type="proxy_error",
                    code=502,
                )
            ).model_dump(),
        )


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)):
    """지원 모델 목록 (REQ-052-006)"""
    verify_auth(authorization)

    models = [
        {
            "id": model_id,
            "object": "model",
            "owned_by": model_id.split("/")[0],
            "name": name,
        }
        for model_id, name in SUPPORTED_MODELS.items()
    ]

    return {"object": "list", "data": models}


@app.get("/health")
async def health():
    """서버 상태 확인 (REQ-052-010)"""
    return {
        "status": "ok",
        "version": "1.0.052",
        "models": list(SUPPORTED_MODELS.keys()),
    }


# ── 서버 실행 ──

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AI_PROXY_PORT", "8000"))
    logger.info(f"🚀 AI Proxy Server starting on http://localhost:{port}")
    logger.info(f"📋 Supported models:")
    for mid, name in SUPPORTED_MODELS.items():
        logger.info(f"   - {mid}: {name}")

    uvicorn.run(app, host="0.0.0.0", port=port)
