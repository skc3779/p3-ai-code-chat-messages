"""
OpenAI 호환 프록시 서버 (FastAPI)
FSD v1.0.052 §4.2 / REQ-052-001, REQ-052-006, REQ-052-007, REQ-052-008, REQ-052-009, REQ-052-010

엔드포인트:
  POST /v1/chat/completions  - 채팅 완성 (OpenAI 호환)
  GET  /v1/models            - 지원 모델 목록
  GET  /health               - 서버 상태 확인
"""

import hmac
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from models import (
    ChatCompletionRequest,
    ErrorDetail,
    ErrorResponse,
)
from router import SUPPORTED_MODELS, _get_providers, peek_providers, reset_providers, route_model
from providers.base import BaseProvider, ProviderError, _sanitize_log_input, _scrub_secrets

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ai-proxy")

# REQ-111-015, REQ-111-025: 서버 시작 시 고정 타임스탬프 (연속 요청 시 일관성 보장)
SERVER_START_TIME: int = int(time.time())


# REQ-111-013, REQ-111-024: FastAPI lifespan 컨텍스트 매니저를 통한 종료 시 리소스 정상 종료 및 캐시 리셋
@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 생명주기 관리: 종료 시 이미 생성된 Provider의 httpx AsyncClient 정상 종료 및 캐시 초기화 (REQ-111-013, REQ-111-024)"""
    try:
        yield
    finally:
        # peek_providers()를 사용하여 미생성된 Provider를 불필요하게 인스턴스화하지 않음
        providers = peek_providers()
        for name, provider in providers.items():
            try:
                if hasattr(provider, "aclose") and callable(provider.aclose):
                    await provider.aclose()
                elif hasattr(provider, "client") and hasattr(provider.client, "aclose") and callable(provider.client.aclose):
                    await provider.client.aclose()
            except Exception as e:
                logger.warning(f"Error closing AsyncClient for provider '{name}': {_scrub_secrets(str(e))}")
        reset_providers()


# FastAPI 앱 (REQ-111-013: lifespan 적용)
app = FastAPI(
    title="AI Proxy Server",
    description="OpenAI 호환 로컬 프록시 서버 (GenAI/Claude/Gemini)",
    version="1.0.052",
    lifespan=lifespan,
)


def __getattr__(name: str):
    """동적 속성 지원: PROXY_API_KEY의 단일 원천화 (REQ-111-022)"""
    if name == "PROXY_API_KEY":
        return os.getenv("AI_PROXY_API_KEY")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# REQ-111-003: HTTP 상태 코드 -> OpenAI 에러 코드 매핑 테이블
STATUS_CODE_TO_ERROR_CODE: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    404: "not_found_error",
    405: "proxy_error",
    429: "rate_limit_error",
}
DEFAULT_ERROR_CODE: str = "proxy_error"


# ── REQ-111-011, REQ-111-021: OpenAI 규격 에러 응답 전역 예외 핸들러 ──

@app.exception_handler(StarletteHTTPException)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException | HTTPException) -> JSONResponse:
    """
    HTTPException / StarletteHTTPException 발생 시 OpenAI 스펙 최상위 error 키 형식으로 재직렬화 (REQ-111-011).
    FastAPI 기본 {"detail": ...} 래핑을 제거하고 {"error": {"message": ..., "type": ..., "code": ...}} 반환.
    404, 405 등 프레임워크 오류도 포괄 처리.
    """
    error_code = STATUS_CODE_TO_ERROR_CODE.get(exc.status_code, DEFAULT_ERROR_CODE)

    if isinstance(exc.detail, dict):
        if "error" in exc.detail and isinstance(exc.detail["error"], dict):
            inner = exc.detail["error"]
            message = str(inner.get("message", ""))
            code = inner.get("code")
            if not isinstance(code, str) or not code:
                code = error_code
            err_type = inner.get("type") or error_code
        else:
            message = exc.detail.get("message", str(exc.detail))
            code = exc.detail.get("code")
            if not isinstance(code, str) or not code:
                code = error_code
            err_type = exc.detail.get("type", error_code)
    else:
        message = str(exc.detail)
        code = error_code
        err_type = error_code

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": message,
                "type": str(err_type),
                "code": str(code),
            }
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    요청 스키마 유효성 검증 실패(422) 발생 시 OpenAI 규격 최상위 error 키 형식으로 반환 (REQ-111-011).
    """
    error_messages = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []) if l != "body")
        msg = err.get("msg", "")
        if loc:
            error_messages.append(f"{loc}: {msg}")
        else:
            error_messages.append(msg)
    message = "; ".join(error_messages) if error_messages else "Request validation failed"

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": "invalid_request_error",
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    미처리 서버 내부 예외(500) 발생 시 OpenAI 규격으로 안전하게 반환 (REQ-111-021).
    스택트레이스나 내부 경로는 노출하지 않고 고유 request_id를 포함.
    """
    req_id = uuid.uuid4().hex[:12]
    logger.error(f"[{req_id}] Unhandled server exception: {_scrub_secrets(str(exc))}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": f"Internal server error (request_id={req_id})",
                "type": "internal_error",
                "code": "internal_error",
            }
        },
    )


# ── 인증 헬퍼 ──

def verify_auth(authorization: str | None):
    """Bearer 토큰 인증 (REQ-052-009, REQ-111-011, REQ-111-012, REQ-111-020). 비-ASCII 문자열 안전 처리."""
    active_key = os.getenv("AI_PROXY_API_KEY")
    if not active_key:
        return  # 키 미설정 시 인증 비활성화

    if not authorization:
        logger.warning("Unauthorized (missing authorization header)")
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error=ErrorDetail(
                    message="Unauthorized. Provide valid 'Authorization: Bearer <key>' header.",
                    type="authentication_error",
                    code="authentication_error",
                )
            ).model_dump(),
        )

    expected = f"Bearer {active_key}"
    try:
        # REQ-111-020: hmac.compare_digest에 bytes 전달하여 비-ASCII 입력 시 TypeError/500 방지
        auth_bytes = authorization.encode("utf-8")
        expected_bytes = expected.encode("utf-8")
        is_match = hmac.compare_digest(auth_bytes, expected_bytes)
    except Exception:
        is_match = False

    if not is_match:
        logger.warning("Unauthorized (key mismatch)")
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error=ErrorDetail(
                    message="Unauthorized. Provide valid 'Authorization: Bearer <key>' header.",
                    type="authentication_error",
                    code="authentication_error",
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
    request_id = uuid.uuid4().hex[:12]
    verify_auth(authorization)

    # REQ-111-021: 모델 식별자 길이 상한 검증 (로그 인젝션/DoS 방지)
    if len(request.model) > 100:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=ErrorDetail(
                    message="Model identifier exceeds maximum length of 100 characters",
                    type="invalid_request_error",
                    code="invalid_request_error",
                )
            ).model_dump(),
        )

    # 모델 라우팅 (REQ-052-002)
    try:
        provider, actual_model = route_model(request.model)
    except ValueError as e:
        safe_msg = _sanitize_log_input(str(e), max_len=200)
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=ErrorDetail(
                    message=safe_msg,
                    type="invalid_request_error",
                    code="invalid_request_error",
                )
            ).model_dump(),
        )

    # 라우팅된 실제 모델 ID로 교체 (REQ-111-021: 로그 인젝션 방지를 위해 모델 식별자 새니타이즈 적용)
    original_model = request.model
    safe_actual = _sanitize_log_input(actual_model, max_len=100)
    request.model = safe_actual

    # REQ-111-021: 모델 로깅 시 새니타이징 적용 및 request_id 포함
    safe_original = _sanitize_log_input(original_model, max_len=100)
    provider_prefix = safe_original.split('/')[0]
    logger.info(f"[{request_id}] → {safe_original} (provider: {provider_prefix}, model: {safe_actual})")

    if request.stream:
        # 스트리밍 (REQ-052-008, REQ-111-020, REQ-111-023: 안전한 스트림 래퍼로 예외 차단 및 SSE 변환)
        async def stream_generator():
            try:
                stream_iter = provider.stream(request)
                async for chunk in stream_iter:
                    yield chunk
            except ProviderError as pe:
                logger.error(f"[{request_id}] Stream ProviderError ({pe.status_code}): {_scrub_secrets(str(pe))}")
                pub_msg = getattr(pe, "public_message", None) or f"Upstream provider error (request_id={request_id})"
                code = STATUS_CODE_TO_ERROR_CODE.get(pe.status_code, DEFAULT_ERROR_CODE)
                yield BaseProvider._error_chunk(pub_msg, code=code)
            except Exception as se:
                logger.error(f"[{request_id}] Stream error: {_scrub_secrets(str(se))}", exc_info=True)
                yield BaseProvider._error_chunk(f"Upstream provider error (request_id={request_id})", code=DEFAULT_ERROR_CODE)

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        # 비스트리밍 (REQ-052-007, REQ-111-020: 클라이언트 공개 메시지와 내부 로그 분리)
        try:
            result = await provider.chat(request)
            result.model = original_model
            return result
        except ProviderError as e:
            logger.error(f"[{request_id}] Provider error ({e.status_code}): {_scrub_secrets(str(e))}")
            error_code = STATUS_CODE_TO_ERROR_CODE.get(e.status_code, DEFAULT_ERROR_CODE)
            pub_msg = getattr(e, "public_message", None) or f"Upstream provider error (request_id={request_id})"
            raise HTTPException(
                status_code=e.status_code,
                detail=ErrorResponse(
                    error=ErrorDetail(
                        message=pub_msg,
                        type="proxy_error",
                        code=error_code,
                    )
                ).model_dump(),
            )
        except Exception as e:
            logger.error(f"[{request_id}] Unexpected error: {_scrub_secrets(str(e))}", exc_info=True)
            raise HTTPException(
                status_code=502,
                detail=ErrorResponse(
                    error=ErrorDetail(
                        message=f"Upstream provider error (request_id={request_id})",
                        type="proxy_error",
                        code="proxy_error",
                    )
                ).model_dump(),
            )


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(None)):
    """지원 모델 목록 (REQ-052-006, REQ-111-015, REQ-111-025: 서버 시작 시점 고정 created 타임스탬프)"""
    verify_auth(authorization)

    models = [
        {
            "id": model_id,
            "object": "model",
            "created": SERVER_START_TIME,
            "owned_by": model_id.split("/")[0],
            "name": name,
        }
        for model_id, name in SUPPORTED_MODELS.items()
    ]

    return {"object": "list", "data": models}


@app.get("/health")
async def health():
    """서버 상태 확인 (REQ-052-010, REQ-111-015, REQ-111-025)"""
    return {
        "status": "ok",
        "version": "1.0.052",
        "created": SERVER_START_TIME,
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
