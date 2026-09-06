"""
TASK-CORE-3 계약 테스트 — OpenAI 규격 에러 응답 및 보안/리소스 하드닝 검증.
REQ-111-011: OpenAI 규격 최상위 error 응답 (@app.exception_handler: HTTPException, RequestValidationError)
REQ-111-012: 인증 보안 하드닝 (평문 API 키 및 Authorization 헤더 로깅 제거, hmac.compare_digest 타이밍 방어)
REQ-111-013: FastAPI lifespan 을 통한 Provider httpx AsyncClient 정상 종료 (aclose)
REQ-111-014: 로깅 정책 환경변수 게이팅 (LOG_PAYLOAD, LOG_CHUNK, DEFAULT_LOG_MAX_LEN=2000)
REQ-111-015: /health 및 /v1/models 응답에 created 정수 epoch 포함
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ai-proxy 디렉토리를 sys.path에 추가하여 내부 모듈 import 보장
PROXY_DIR = Path(__file__).resolve().parent.parent / "ai-proxy"
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))

import providers.base as base_module
from models import ChatCompletionRequest, ChatMessage
from providers.base import (
    BaseProvider,
    ProviderError,
    _sanitize_log_input,
    _scrub_secrets,
    _validate_api_key,
    truncate_for_log,
)
from providers.claude_provider import ClaudeProvider
from providers.gemini_provider import GeminiProvider
from providers.genai_provider import GenAIProvider
import proxy_server
from proxy_server import (
    DEFAULT_ERROR_CODE,
    SERVER_START_TIME,
    STATUS_CODE_TO_ERROR_CODE,
    app,
    verify_auth,
)
from router import (
    SUPPORTED_MODELS,
    _get_providers,
    peek_providers,
    reset_providers,
    route_model,
)


@pytest.fixture(autouse=True)
def cleanup_providers():
    """모든 테스트 전후로 router Provider 캐시를 정리하여 테스트 간 격리 보장."""
    reset_providers()
    yield
    reset_providers()


@pytest.fixture
def client(monkeypatch):
    """FastAPI TestClient 픽스처 (인증 비활성화 기본 환경)"""
    monkeypatch.delenv("AI_PROXY_API_KEY", raising=False)
    with TestClient(app) as test_client:
        yield test_client


# ── REQ-111-011: OpenAI 규격 에러 응답 계약 검증 ──

def test_invalid_model_returns_400_openai_error_contract(client):
    """잘못된 모델 ID 요청 시 400 상태 코드와 최상위 error 키 반환 및 detail 부재 검증 (REQ-111-011)."""
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "unknown_provider/non-existent-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 400
    data = response.json()

    # 최상위 error 키 존재 및 detail 키 부재 검증
    assert "error" in data, f"Expected 'error' in response, got: {data}"
    assert "detail" not in data, f"Expected no 'detail' in response, got: {data}"

    error_obj = data["error"]
    assert isinstance(error_obj, dict)
    assert "message" in error_obj
    assert "Unknown model" in error_obj["message"]

    # code 필드가 문자열이어야 함
    assert "code" in error_obj
    assert isinstance(error_obj["code"], str)
    assert error_obj["code"] == "invalid_request_error"
    assert error_obj.get("type") == "invalid_request_error"


def test_auth_failure_returns_401_openai_error_contract(monkeypatch):
    """인증 실패 시 401 상태 코드와 최상위 error 키 반환 및 detail 부재 검증 (REQ-111-011, REQ-111-012)."""
    secret_key = "test-secret-proxy-key-12345"
    monkeypatch.setenv("AI_PROXY_API_KEY", secret_key)

    with TestClient(app) as auth_client:
        # 1. Authorization 헤더 누락
        resp_no_auth = auth_client.post(
            "/v1/chat/completions",
            json={
                "model": "claude/claude-sonnet-4-6",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp_no_auth.status_code == 401
        data_no_auth = resp_no_auth.json()
        assert "error" in data_no_auth
        assert "detail" not in data_no_auth
        assert isinstance(data_no_auth["error"]["code"], str)
        assert data_no_auth["error"]["code"] == "authentication_error"
        assert data_no_auth["error"]["type"] == "authentication_error"

        # 2. 잘못된 Authorization Bearer 키
        resp_wrong = auth_client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer wrong-token-xyz"},
            json={
                "model": "claude/claude-sonnet-4-6",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp_wrong.status_code == 401
        data_wrong = resp_wrong.json()
        assert "error" in data_wrong
        assert "detail" not in data_wrong
        assert isinstance(data_wrong["error"]["code"], str)
        assert data_wrong["error"]["code"] == "authentication_error"


def test_schema_validation_error_returns_422_openai_error_contract(client):
    """요청 스키마 위반(top_p 범위 초과 등) 시 422 상태 코드와 최상위 error 키 반환 및 detail 부재 검증 (REQ-111-011)."""
    # top_p=-1 은 Field(ge=0.0, le=1.0) 범위를 위반하여 RequestValidationError 발생
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "claude/claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hello"}],
            "top_p": -1.0,
        },
    )

    assert response.status_code == 422
    data = response.json()

    # 최상위 error 키 존재 및 detail 키 부재 검증
    assert "error" in data, f"Expected 'error' in response, got: {data}"
    assert "detail" not in data, f"Expected no 'detail' in response, got: {data}"

    error_obj = data["error"]
    assert isinstance(error_obj, dict)
    assert "message" in error_obj
    assert len(error_obj["message"]) > 0

    # code가 문자열이어야 함
    assert "code" in error_obj
    assert isinstance(error_obj["code"], str)
    assert error_obj["code"] == "invalid_request_error"
    assert error_obj.get("type") == "invalid_request_error"


def test_missing_messages_validation_error_returns_422_openai_error(client):
    """필수 필드 messages 누락 시 422 최상위 error 형식 반환 검증 (REQ-111-011)."""
    response = client.post(
        "/v1/chat/completions",
        json={"model": "claude/claude-sonnet-4-6"},
    )
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert "detail" not in data
    assert data["error"]["code"] == "invalid_request_error"
    assert "messages" in data["error"]["message"]


# ── REQ-111-012: 인증 로깅 제거 및 타이밍 공격 방어 검증 ──

def test_auth_failure_caplog_contains_no_api_key_or_token(monkeypatch, caplog):
    """인증 실패 유발 시 caplog에 서버 PROXY_API_KEY 및 클라이언트 토큰 문자열이 일체 없음을 검증 (REQ-111-012)."""
    server_api_key = "super-secret-production-proxy-key-8899"
    client_wrong_token = "malicious-user-attempt-token-1122"
    monkeypatch.setenv("AI_PROXY_API_KEY", server_api_key)

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="ai-proxy"):
        with TestClient(app) as auth_client:
            resp = auth_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {client_wrong_token}"},
                json={
                    "model": "claude/claude-sonnet-4-6",
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
            assert resp.status_code == 401

    log_content = caplog.text

    # 서버 정답 키가 로그에 절대로 남지 않아야 함
    assert server_api_key not in log_content, "Security violation: Server API key logged!"
    assert f"Expected: Bearer {server_api_key}" not in log_content

    # 클라이언트 토큰 원문도 로그에 남지 않아야 함
    assert client_wrong_token not in log_content, "Security violation: Client bearer token logged!"
    assert f"authorization: Bearer {client_wrong_token}" not in log_content

    # 허용된 로그 메시지 확인: "Unauthorized (key mismatch)"
    assert "Unauthorized (key mismatch)" in log_content


def test_auth_success_with_valid_token(monkeypatch):
    """올바른 Bearer 토큰 전달 시 verify_auth가 예외 없이 정상 통과하는지 검증 (REQ-111-012)."""
    valid_key = "correct-test-key-3344"
    monkeypatch.setenv("AI_PROXY_API_KEY", valid_key)

    # verify_auth 직접 호출 시 예외 없이 통과
    verify_auth(f"Bearer {valid_key}")


def test_auth_disabled_when_key_empty(monkeypatch):
    """AI_PROXY_API_KEY 미설정 시 인증이 비활성화되어 무인증 요청도 허용되는지 검증 (REQ-111-012)."""
    monkeypatch.delenv("AI_PROXY_API_KEY", raising=False)

    # verify_auth 직접 호출 시 예외 없이 통과
    verify_auth(None)
    verify_auth("")


# ── REQ-111-015: /v1/models 및 /health created 타임스탬프 검증 ──

def test_models_endpoint_has_created_epoch(client):
    """GET /v1/models 응답의 각 모델 항목에 created 정수 epoch가 포함되어 있는지 검증 (REQ-111-015, REQ-111-025)."""
    response = client.get("/v1/models")

    assert response.status_code == 200
    data = response.json()

    assert data.get("object") == "list"
    models_list = data.get("data", [])
    assert len(models_list) > 0

    for m in models_list:
        assert "created" in m, f"Model {m.get('id')} missing 'created' field"
        assert isinstance(m["created"], int), f"'created' must be an int in model {m.get('id')}"
        assert m["created"] == SERVER_START_TIME


def test_health_endpoint_has_created_epoch(client):
    """GET /health 응답에 created 정수 epoch가 포함되어 있는지 검증 (REQ-111-015, REQ-111-025)."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data.get("status") == "ok"
    assert "created" in data, "GET /health response missing 'created' field"
    assert isinstance(data["created"], int)
    assert data["created"] == SERVER_START_TIME


# ── REQ-111-014: 로깅 정책 환경변수 게이팅 검증 ──

def test_default_log_max_len_is_2000():
    """DEFAULT_LOG_MAX_LEN 이 2000으로 설정되어 있는지 검증 (REQ-111-014)."""
    assert base_module.DEFAULT_LOG_MAX_LEN == 2000


def test_logging_policy_env_gating_helpers(monkeypatch):
    """LOG_PAYLOAD 및 LOG_CHUNK 환경변수 게이팅 헬퍼 동작 검증 (REQ-111-014)."""
    # 1. 기본값: off (False)
    monkeypatch.delenv("LOG_PAYLOAD", raising=False)
    monkeypatch.delenv("LOG_CHUNK", raising=False)
    assert base_module.should_log_payload() is False
    assert base_module.should_log_chunk() is False
    assert base_module.LOG_PAYLOAD is False
    assert base_module.LOG_CHUNK is False

    # 2. 활성화 ("1", "true")
    monkeypatch.setenv("LOG_PAYLOAD", "1")
    monkeypatch.setenv("LOG_CHUNK", "true")
    assert base_module.should_log_payload() is True
    assert base_module.should_log_chunk() is True
    assert base_module.LOG_PAYLOAD is True
    assert base_module.LOG_CHUNK is True

    # 3. 비활성화 ("0", "false")
    monkeypatch.setenv("LOG_PAYLOAD", "0")
    monkeypatch.setenv("LOG_CHUNK", "false")
    assert base_module.should_log_payload() is False
    assert base_module.should_log_chunk() is False
    assert base_module.LOG_PAYLOAD is False
    assert base_module.LOG_CHUNK is False


def test_truncate_for_log_signature_and_behavior():
    """truncate_for_log() 시그니처 및 동작 호환성 검증 (REQ-111-014)."""
    # 1. 2000자 이하 데이터는 온전히 반환
    short_data = {"key": "value"}
    result_short = base_module.truncate_for_log(short_data)
    assert "key" in result_short
    assert "...(truncated)" not in result_short

    # 2. 2000자 초과 데이터는 잘라내고 ...(truncated) 접미사 추가
    long_text = "x" * 3000
    result_long = base_module.truncate_for_log(long_text)
    assert len(result_long) <= 2050
    assert "...(truncated)" in result_long

    # 3. max_len 인자 명시적 전달 호환성
    custom_trunc = base_module.truncate_for_log("abcdefghij", max_len=5)
    assert "abcde...(truncated)" in custom_trunc


# ── REQ-111-013, REQ-111-024: FastAPI lifespan 리소스 종료 및 전역 오염 제거 검증 ──

def test_peek_providers_does_not_instantiate_new():
    """peek_providers()는 싱글톤 캐시에 없는 Provider를 새로 생성하지 않음을 검증 (REQ-111-024)."""
    reset_providers()
    providers = peek_providers()
    assert len(providers) == 0


def test_lifespan_closes_only_existing_providers_without_polluting(monkeypatch):
    """lifespan 종료 시 이미 생성된 Provider만 aclose()되고 전역 Provider가 오염되지 않음을 검증 (REQ-111-024)."""
    reset_providers()

    # 1. Claude Provider 하나만 명시적으로 초기화
    providers_dict = _get_providers()
    claude_p = providers_dict["claude"]
    claude_mock_aclose = AsyncMock()
    monkeypatch.setattr(claude_p, "aclose", claude_mock_aclose)

    # 2. TestClient 실행 후 종료 -> lifespan yield 후 정리
    with TestClient(app) as test_client:
        resp = test_client.get("/health")
        assert resp.status_code == 200

    # 3. Claude의 aclose는 호출되었어야 함
    assert claude_mock_aclose.await_count >= 1

    # 4. lifespan 종료 후 reset_providers()가 호출되어 peek_providers()가 비어있어야 함
    assert len(peek_providers()) == 0


def test_lifespan_continues_on_individual_aclose_failure(monkeypatch, caplog):
    """한 Provider의 aclose()가 실패해도 나머지 Provider들의 정리가 중단되지 않음을 검증 (REQ-111-024)."""
    reset_providers()
    providers_dict = _get_providers()

    fail_aclose = AsyncMock(side_effect=RuntimeError("aclose failed"))
    success_aclose = AsyncMock()

    monkeypatch.setattr(providers_dict["claude"], "aclose", fail_aclose)
    monkeypatch.setattr(providers_dict["gemini"], "aclose", success_aclose)

    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        with TestClient(app) as test_client:
            pass

    assert fail_aclose.await_count >= 1
    assert success_aclose.await_count >= 1
    assert "Error closing AsyncClient for provider" in caplog.text


# ── 1. [P0-BLOCKER] 자격증명 클라이언트 유출 방지 및 비밀값 스크러빙 (REQ-111-020) ──

def test_scrub_secrets_masks_keys_and_patterns():
    """_scrub_secrets가 API 키 환경변수 및 Bearer/sk-ant/AIza 패턴을 마스킹하는지 검증 (REQ-111-020)."""
    secret_text = "error with key sk-ant-api03-abcdef1234567890 and AIzaSyD12345678901234567890 and Bearer secret-token-xyz"
    scrubbed = _scrub_secrets(secret_text)

    assert "sk-ant-api03-abcdef1234567890" not in scrubbed
    assert "AIzaSyD12345678901234567890" not in scrubbed
    assert "secret-token-xyz" not in scrubbed
    assert "***REDACTED***" in scrubbed


def test_scrub_secrets_masks_configured_env_vars(monkeypatch):
    """환경변수에 등록된 키 리터럴이 텍스트에 포함되었을 때 마스킹되는지 검증 (REQ-111-020)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "my-super-secret-claude-key")
    text = "Failed to connect using key my-super-secret-claude-key in request"
    scrubbed = _scrub_secrets(text)
    assert "my-super-secret-claude-key" not in scrubbed
    assert "***REDACTED***" in scrubbed


def test_validate_api_key_rejects_newlines_without_leaking():
    """_validate_api_key가 개행이나 제어문자가 포함된 키를 값 노출 없이 차단하는지 검증 (REQ-111-020)."""
    bad_key = "secret_key\ninjected_header: bad"
    with pytest.raises(ValueError) as excinfo:
        _validate_api_key(bad_key, "TEST_KEY")

    err_str = str(excinfo.value)
    assert "contains illegal control or newline characters" in err_str
    assert "secret_key" not in err_str
    assert "injected_header" not in err_str


def test_provider_error_separates_public_and_internal_messages():
    """ProviderError가 클라이언트용 public_message와 내부 로그용 message를 분리하는지 검증 (REQ-111-020)."""
    err = ProviderError(
        status_code=500,
        message="Upstream raw secret sk-ant-12345 crashed with database error",
        public_message=None,  # 자동 일반 문구 생성
        request_id="abc123def456",
    )

    assert err.request_id == "abc123def456"
    assert "abc123def456" in err.public_message
    assert "sk-ant-12345" not in err.public_message
    assert "database error" not in err.public_message
    assert "Upstream raw secret" in err.internal_message


def test_sse_error_chunk_contains_code():
    """BaseProvider._error_chunk가 code 필드를 올바르게 포함하는지 검증 (REQ-111-020)."""
    chunk = BaseProvider._error_chunk("Rate limit error", code="rate_limit_error")
    assert chunk.startswith("data: ")
    assert "data: [DONE]" in chunk

    first_event = chunk.strip().split("\n\n")[0]
    payload = json.loads(first_event.replace("data: ", ""))
    assert "error" in payload
    assert payload["error"]["message"] == "Rate limit error"
    assert payload["error"]["code"] == "rate_limit_error"
    assert payload["error"]["type"] == "proxy_error"


# ── 2. [MAJOR] LOG_PAYLOAD=0 / LOG_CHUNK=0 게이팅 및 조건 내 직렬화 (REQ-111-014, REQ-111-020) ──

def test_log_payload_zero_gates_sensitive_prompt(monkeypatch, caplog):
    """LOG_PAYLOAD=0 일 때 Provider의 요청/응답 페이로드가 로그에 일체 남지 않음을 검증 (REQ-111-014)."""
    import asyncio
    monkeypatch.setenv("LOG_PAYLOAD", "0")
    monkeypatch.setenv("LOG_CHUNK", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

    provider = GeminiProvider()
    secret_prompt = "TOP_SECRET_USER_PAYLOAD_XYZ987"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 123456,
        "model": "gemini-2.5-flash",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "TOP_SECRET_RESPONSE_DATA_777"},
            "finish_reason": "stop",
        }],
    }

    provider.client.post = AsyncMock(return_value=mock_resp)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ai-proxy"):
        req = ChatCompletionRequest(
            model="gemini/gemini-2.5-flash",
            messages=[ChatMessage(role="user", content=secret_prompt)],
        )
        asyncio.run(provider.chat(req))

    log_text = caplog.text
    assert secret_prompt not in log_text
    assert "TOP_SECRET_RESPONSE_DATA_777" not in log_text


# ── 3. [MAJOR] 비-ASCII 인증 헤더 401 처리 (REQ-111-020) ──

def test_non_ascii_authorization_header_returns_401(monkeypatch):
    """비-ASCII 문자가 포함된 Authorization 헤더 전달 시 500이 아닌 401 반환 검증 (REQ-111-020)."""
    from fastapi import HTTPException
    monkeypatch.setenv("AI_PROXY_API_KEY", "valid-ascii-server-key-555")

    # verify_auth 직접 호출 시 utf-8 인코딩 및 안전한 비교로 500 크래시 없이 401 HTTPException 발생
    for bad_header in ["Bearer café", "Bearer 🔑secret", "Bearer \ud83d\ude00"]:
        with pytest.raises(HTTPException) as exc_info:
            verify_auth(bad_header)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["error"]["code"] == "authentication_error"


def test_non_ascii_server_key_does_not_crash(monkeypatch):
    """서버 측 AI_PROXY_API_KEY에 비-ASCII 문자가 포함되어 있어도 크래시 없이 401 반환 검증 (REQ-111-020)."""
    monkeypatch.setenv("AI_PROXY_API_KEY", "서버키12345")

    with TestClient(app) as auth_client:
        resp = auth_client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer wrong-key"},
            json={
                "model": "claude/claude-sonnet-4-6",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 401


# ── 4. [MAJOR] 에러 계약 확장 (Starlette 404/405 및 500 Unhandled Exception) (REQ-111-023) ──

def test_404_not_found_returns_openai_error_contract(client):
    """존재하지 않는 엔드포인트 호출 시 최상위 error 키 형식의 404 응답 검증 (REQ-111-023)."""
    resp = client.get("/v1/nonexistent_path")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert "detail" not in data
    assert data["error"]["code"] == "not_found_error"
    assert data["error"]["type"] == "not_found_error"


def test_405_method_not_allowed_returns_openai_error_contract(client):
    """지원되지 않는 메소드 호출 시 최상위 error 키 형식의 405 응답 검증 (REQ-111-023)."""
    resp = client.post("/health")
    assert resp.status_code == 405
    data = resp.json()
    assert "error" in data
    assert "detail" not in data
    assert data["error"]["code"] == "proxy_error"


def test_unhandled_exception_returns_500_with_request_id(monkeypatch):
    """처리되지 않은 내부 예외 발생 시 스택트레이스 미노출, request_id 부여, 500 최상위 error 응답 검증 (REQ-111-021)."""
    monkeypatch.delenv("AI_PROXY_API_KEY", raising=False)

    def crash_route(model):
        raise RuntimeError("Unexpected internal crash with database /var/secret/db")

    monkeypatch.setattr(proxy_server, "route_model", crash_route)

    with TestClient(app, raise_server_exceptions=False) as no_raise_client:
        resp = no_raise_client.post(
            "/v1/chat/completions",
            json={
                "model": "claude/claude-sonnet-4-6",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
        assert "detail" not in data
        assert data["error"]["code"] == "internal_error"
        assert "request_id=" in data["error"]["message"]
        assert "/var/secret/db" not in data["error"]["message"]


def test_streaming_error_yields_error_chunk_and_done(monkeypatch):
    """스트리밍 도중 Provider에서 예외 발생 시 클라이언트에 SSE error 청크가 방출되는지 검증 (REQ-111-023)."""
    monkeypatch.delenv("AI_PROXY_API_KEY", raising=False)

    async def failing_stream(request):
        yield "data: {\"choices\": [{\"delta\": {\"content\": \"hello\"}}]}\n\n"
        raise ProviderError(500, "Upstream stream broke", "Stream disconnected safely", "req-stream-1")

    mock_provider = MagicMock()
    mock_provider.stream = failing_stream

    monkeypatch.setattr(proxy_server, "route_model", lambda m: (mock_provider, "claude-sonnet-4-6"))

    with TestClient(app) as test_client:
        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "claude/claude-sonnet-4-6",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        text = resp.text
        assert "Stream disconnected safely" in text
        assert "proxy_error" in text


# ── 7. [MINOR] 모델 식별자 100자 상한 및 로그 인젝션 방어 (REQ-111-021) ──

def test_model_identifier_over_100_chars_rejected(client):
    """모델 식별자가 100자를 초과하면 400 Bad Request로 거부되는지 검증 (REQ-111-021)."""
    long_model = "claude/" + "a" * 105
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": long_model,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    assert "Model identifier exceeds maximum length of 100 characters" in data["error"]["message"]


def test_model_log_injection_sanitized(client, caplog):
    """모델 식별자에 개행 문자가 포함되어 있을 때 _sanitize_log_input에 의해 로그 스푸핑이 차단되는지 검증 (REQ-111-021)."""
    malicious_model = "claude/model\n[CRITICAL] Fake audit log\r\n"

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="ai-proxy"):
        client.post(
            "/v1/chat/completions",
            json={
                "model": malicious_model,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    log_text = caplog.text
    assert "\n[CRITICAL] Fake audit log" not in log_text
    assert "\\n[CRITICAL]" in log_text or "Fake audit log" in log_text


# ── 8. [MINOR] /v1/models created 고정 epoch 검증 (REQ-111-025) ──

def test_models_and_health_created_epoch_is_constant(client):
    """GET /v1/models 및 /health 호출 시 created 값이 서버 시작 시간 SERVER_START_TIME으로 고정되어 있는지 검증 (REQ-111-025)."""
    resp1 = client.get("/v1/models")
    time.sleep(0.01)
    resp2 = client.get("/v1/models")
    resp_health = client.get("/health")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp_health.status_code == 200

    created1 = resp1.json()["data"][0]["created"]
    created2 = resp2.json()["data"][0]["created"]
    created_health = resp_health.json()["created"]

    assert created1 == SERVER_START_TIME
    assert created2 == SERVER_START_TIME
    assert created_health == SERVER_START_TIME


# ── 9. [NIT] 인증 설정 동적 단일 원천화 (REQ-111-022) ──

def test_proxy_api_key_module_attribute_is_dynamic(monkeypatch):
    """proxy_server.PROXY_API_KEY 모듈 속성 접근 시 최신 os.getenv 값이 동적으로 반환되는지 검증 (REQ-111-022)."""
    monkeypatch.setenv("AI_PROXY_API_KEY", "first-key")
    assert proxy_server.PROXY_API_KEY == "first-key"

    monkeypatch.setenv("AI_PROXY_API_KEY", "second-key")
    assert proxy_server.PROXY_API_KEY == "second-key"

    monkeypatch.delenv("AI_PROXY_API_KEY", raising=False)
    assert proxy_server.PROXY_API_KEY is None
