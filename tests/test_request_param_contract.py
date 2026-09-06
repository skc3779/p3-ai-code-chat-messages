"""
TASK-CORE-1 Provider 계약 검증 테스트 — 요청 JSON -> Provider payload 계약 검증.
REQ-111-005, REQ-111-006, REQ-111-008, REQ-111-010 (MAJOR-4)

검증 범위:
1. 세 Provider(Gemini, Claude, GenAI) 각각에 대해 미지원 필드 포함 요청 시 경고 정확히 1회 발생 (caplog)
2. 경고 메시지에 미지원 필드명 포함
3. 미지정 최상위 필드(reasoning_effort 등)도 경고에 포함
4. 지원 필드만 있는 요청에서는 경고가 발생하지 않음 (0회)
5. Gemini payload에 미지원 필드가 포함되지 않음 (패스스루 제한 계약)
6. 명시적 stream=False와 미지정 stream의 구별 (GenAI Provider)
7. stream() 비동기 제너레이터 진입부 경고 및 GenAI chat() 연계 시 중복 경고 방지 (1회 보장)
"""

import json
import logging
import sys
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest

# ai-proxy 디렉토리를 sys.path에 추가
PROXY_DIR = Path(__file__).resolve().parent.parent / "ai-proxy"
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))

from models import ChatCompletionRequest, ChatMessage
from providers.claude_provider import ClaudeProvider
from providers.gemini_provider import GeminiProvider
from providers.genai_provider import GenAIProvider


# ── 목(Mock) Provider 생성 헬퍼 ──

def make_mock_gemini_provider(recorded_requests: list[httpx.Request]) -> GeminiProvider:
    """GeminiProvider를 httpx.MockTransport 기반으로 생성."""
    def handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        body = json.loads(request.content)
        if body.get("stream"):
            content = (
                b'data: {"id":"cmpl-gemini-1","choices":[{"delta":{"content":"gemini stream"},"index":0}]}\n\n'
                b'data: [DONE]\n\n'
            )
            return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "id": "chatcmpl-gemini-test",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gemini-3-pro-preview",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "gemini response"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    provider = GeminiProvider()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )
    return provider


def make_mock_claude_provider(recorded_requests: list[httpx.Request]) -> ClaudeProvider:
    """ClaudeProvider를 httpx.MockTransport 기반으로 생성."""
    def handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        body = json.loads(request.content)
        if body.get("stream"):
            content = (
                b'event: content_block_delta\n'
                b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"claude stream"}}\n\n'
                b'event: message_stop\n'
                b'data: {"type":"message_stop"}\n\n'
            )
            return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "id": "msg-claude-test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "claude response"}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 12, "output_tokens": 6},
        })

    provider = ClaudeProvider()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    return provider


def make_mock_genai_provider(recorded_requests: list[httpx.Request]) -> GenAIProvider:
    """GenAIProvider를 httpx.MockTransport 기반으로 생성."""
    def handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        return httpx.Response(200, json={
            "content": "genai response",
            "usage": {"prompt_tokens": 15, "completion_tokens": 7, "total_tokens": 22},
        })

    provider = GenAIProvider()
    provider.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://scisportal.samsungif.net/rest/genAi",
    )
    return provider


# ── 로거 필터링 헬퍼 (REQ-111-020, MINOR-7) ──

def get_proxy_warnings(caplog) -> list[logging.LogRecord]:
    """ai-proxy 로거의 WARNING 레코드만 엄격하게 필터링."""
    return [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]


# ── 1. 미지원 파라미터 경고 발생 및 메시지 검증 (세 Provider 공통) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_unsupported_params_warning_once(caplog, provider_factory, model_name):
    """미지원 파라미터(seed, top_p) 포함 요청 시 경고가 정확히 1회 발생하고 필드명이 포함되는지 검증 (REQ-111-005, REQ-111-010)."""
    recorded: list[httpx.Request] = []
    provider = provider_factory(recorded)

    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.7,
        "top_p": 0.9,       # 세 Provider 모두 미지원
        "seed": 42,         # 세 Provider 모두 미지원
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        resp = await provider.chat(req)

    assert resp is not None
    proxy_warnings = get_proxy_warnings(caplog)
    assert len(proxy_warnings) == 1, f"Expected exactly 1 warning, got {len(proxy_warnings)}"
    warning_msg = proxy_warnings[0].message
    assert "top_p" in warning_msg
    assert "seed" in warning_msg
    assert model_name in warning_msg


# ── 2. 미지정 최상위 필드(reasoning_effort 등) 경고 포함 검증 ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_extra_top_level_fields_warning(caplog, provider_factory, model_name):
    """최상위 미지정 필드(reasoning_effort, custom_opt)가 model_extra를 통해 경고에 포함되는지 검증 (REQ-111-006, MAJOR-1)."""
    recorded: list[httpx.Request] = []
    provider = provider_factory(recorded)

    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "reasoning_effort": "high",
        "custom_opt": 123,
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        resp = await provider.chat(req)

    assert resp is not None
    proxy_warnings = get_proxy_warnings(caplog)
    assert len(proxy_warnings) == 1
    warning_msg = proxy_warnings[0].message
    assert "reasoning_effort" in warning_msg
    assert "custom_opt" in warning_msg


# ── 3. 지원 필드만 있는 경우 경고 없음 (0회) 및 Payload 전송값 검증 (REQ-111-020) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_all_supported_params_no_warning(caplog, provider_factory, model_name):
    """
    지원 필드만 있는 요청에서는 경고가 0회인지 검증하고,
    실제 전송 payload에 temperature, max_tokens 값이 정확히 실렸는지 검증 (REQ-111-005, REQ-111-010, REQ-111-020).
    """
    recorded: list[httpx.Request] = []
    provider = provider_factory(recorded)

    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.5,
        "max_tokens": 1024,
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        resp = await provider.chat(req)

    assert resp is not None
    proxy_warnings = get_proxy_warnings(caplog)
    assert len(proxy_warnings) == 0, f"Expected 0 warnings, got {len(proxy_warnings)}"

    # 실제 전송 payload 검증 (REQ-111-020)
    assert len(recorded) == 1
    payload = json.loads(recorded[0].content)

    if "gemini" in model_name:
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 1024
    elif "claude" in model_name:
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 1024
    elif "genai" in model_name:
        assert payload["llmConfig"]["temperature"] == 0.5
        assert payload["llmConfig"]["max_new_tokens"] == 1024


# ── 4. 세 Provider 모두 payload에 미지원 필드가 실리지 않음 검증 (REQ-111-006, REQ-111-020) ──

@pytest.mark.anyio
async def test_gemini_payload_excludes_unsupported_params():
    """Gemini Provider가 미지원 파라미터를 업스트림 payload에 넣지 않는지 검증 (MAJOR-4)."""
    recorded: list[httpx.Request] = []
    provider = make_mock_gemini_provider(recorded)

    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "hello gemini"}],
        "temperature": 0.8,
        "max_tokens": 2048,
        "top_p": 0.95,
        "seed": 999,
        "n": 2,
        "stop": ["END_OF_TEXT"],
        "presence_penalty": 0.5,
        "frequency_penalty": -0.5,
        "reasoning_effort": "high",
        "custom_param": "ignore_me",
    })

    resp = await provider.chat(req)
    assert resp is not None
    assert len(recorded) == 1

    payload = json.loads(recorded[0].content)
    assert payload["model"] == "gemini/gemini-3-pro-preview"
    assert payload["temperature"] == 0.8
    assert payload["max_tokens"] == 2048
    assert payload["stream"] is False

    # 미지원 필드 부재 확인
    for p in ["top_p", "seed", "n", "stop", "presence_penalty", "frequency_penalty", "reasoning_effort", "custom_param"]:
        assert p not in payload, f"Gemini payload unexpectedly contains {p}"


@pytest.mark.anyio
async def test_claude_payload_excludes_unsupported_params():
    """Claude Provider가 미지원 파라미터를 업스트림 payload에 넣지 않는지 검증 (REQ-111-020)."""
    recorded: list[httpx.Request] = []
    provider = make_mock_claude_provider(recorded)

    req = ChatCompletionRequest.model_validate({
        "model": "claude/claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hello claude"}],
        "temperature": 0.7,
        "max_tokens": 1000,
        "top_p": 0.9,
        "seed": 123,
        "n": 3,
        "stop": ["STOP"],
        "presence_penalty": 0.1,
        "frequency_penalty": -0.1,
        "reasoning_effort": "low",
        "custom_param": "ignore_claude",
    })

    resp = await provider.chat(req)
    assert resp is not None
    assert len(recorded) == 1

    payload = json.loads(recorded[0].content)
    assert payload["model"] == "claude/claude-sonnet-4-6"
    assert payload["temperature"] == 0.7
    assert payload["max_tokens"] == 1000

    # 미지원 필드 부재 확인
    for p in ["top_p", "seed", "n", "stop", "presence_penalty", "frequency_penalty", "reasoning_effort", "custom_param"]:
        assert p not in payload, f"Claude payload unexpectedly contains {p}"


@pytest.mark.anyio
async def test_genai_payload_excludes_unsupported_params():
    """GenAI Provider가 미지원 파라미터를 업스트림 payload에 넣지 않는지 검증 (REQ-111-020)."""
    recorded: list[httpx.Request] = []
    provider = make_mock_genai_provider(recorded)

    req = ChatCompletionRequest.model_validate({
        "model": "genai/gpt-oss-120B-medium",
        "messages": [{"role": "user", "content": "hello genai"}],
        "temperature": 0.6,
        "max_tokens": 512,
        "top_p": 0.77,       # 사용자가 보낸 값은 무시되어야 함
        "seed": 888,         # 사용자가 보낸 값은 무시되어야 함
        "n": 2,
        "stop": ["END"],
        "presence_penalty": 0.3,
        "reasoning_effort": "medium",
        "custom_param": "ignore_genai",
    })

    resp = await provider.chat(req)
    assert resp is not None
    assert len(recorded) == 1

    payload = json.loads(recorded[0].content)
    llm_cfg = payload.get("llmConfig", {})
    assert llm_cfg["temperature"] == 0.6
    assert llm_cfg["max_new_tokens"] == 512

    # 사용자 임의의 미지원 필드가 payload 최상위 및 llmConfig에 유입되지 않았는지 검증
    for p in ["custom_param", "reasoning_effort", "n", "stop", "presence_penalty"]:
        assert p not in payload, f"GenAI payload unexpectedly contains {p}"
        assert p not in llm_cfg, f"GenAI llmConfig unexpectedly contains {p}"
    # seed도 사용자의 888이 아니라 None 유지
    assert llm_cfg.get("seed") is None



# ── 5. 명시적 stream=False 와 미지정 stream 의 구별 (GenAI Provider) (REQ-111-019) ──

@pytest.mark.anyio
async def test_stream_unspecified_vs_explicit_false_genai(caplog):
    """
    GenAI Provider 스트림 파라미터 경고 계약 (REQ-111-019, MINOR-6):
    1) stream 미지정 시 (기본값 False): 경고 없음
    2) stream=False 명시 지정 시: 비스트리밍 요청 충족이므로 경고 없음 (거짓 경고 제거)
    3) stream=True 요청 시: '실시간 스트리밍 미지원 — 버퍼링 후 SSE 반환' 경고 정확히 1회 발생
    """
    recorded: list[httpx.Request] = []
    provider = make_mock_genai_provider(recorded)

    # Case 1: stream 미지정 (기본값 False) -> 경고 없음
    req_unspecified = ChatCompletionRequest.model_validate({
        "model": "genai/gpt-oss-120B-medium",
        "messages": [{"role": "user", "content": "hello"}],
    })
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        await provider.chat(req_unspecified)

    proxy_warnings_1 = get_proxy_warnings(caplog)
    assert len(proxy_warnings_1) == 0

    # Case 2: 명시적 stream=False -> 거짓 경고 없이 경고 0회
    req_explicit_false = ChatCompletionRequest.model_validate({
        "model": "genai/gpt-oss-120B-medium",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    })
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        await provider.chat(req_explicit_false)

    proxy_warnings_2 = get_proxy_warnings(caplog)
    assert len(proxy_warnings_2) == 0, f"Expected 0 warnings for stream=False, got {len(proxy_warnings_2)}"

    # Case 3: stream=True -> '실시간 스트리밍 미지원 — 버퍼링 후 SSE 반환' 경고 1회 발생
    req_stream_true = ChatCompletionRequest.model_validate({
        "model": "genai/gpt-oss-120B-medium",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    })
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        chunks = [c async for c in provider.stream(req_stream_true)]

    assert len(chunks) > 0
    proxy_warnings_3 = get_proxy_warnings(caplog)
    assert len(proxy_warnings_3) == 1
    assert "실시간 스트리밍 미지원 — 버퍼링 후 SSE 반환" in proxy_warnings_3[0].message


@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
])
async def test_stream_param_supported_for_gemini_and_claude(caplog, provider_factory, model_name):
    """Gemini와 Claude는 stream을 지원하므로 stream=False 명시 지정 시에도 stream 경고가 발생하지 않음."""
    recorded: list[httpx.Request] = []
    provider = provider_factory(recorded)

    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        await provider.chat(req)

    proxy_warnings = get_proxy_warnings(caplog)
    assert len(proxy_warnings) == 0


# ── 6. stream() async generator 진입부 경고 및 GenAI chat() 연계 시 중복 방지 (REQ-111-020) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_stream_entrypoint_warning_and_deduplication(caplog, provider_factory, model_name):
    """
    stream() 비동기 제너레이터 실행 시:
    1) 진입부에서 경고가 발생하며, GenAIProvider의 chat() 연계 시에도 중복 없이 1회 보장
    2) 모든 청크에 'error' 부재 확인
    3) 실제 delta 내용 확인
    4) 종료 이벤트([DONE]) 확인 (REQ-111-020, MINOR-7)
    """
    recorded: list[httpx.Request] = []
    provider = provider_factory(recorded)

    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "stream request"}],
        "stream": True,
        "top_p": 0.85,  # 미지원 파라미터
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        stream_gen = provider.stream(req)
        chunks = [chunk async for chunk in stream_gen]

    assert len(chunks) > 0

    # 1. 모든 청크에 오류('error')가 없어야 함
    for c in chunks:
        assert '"error"' not in c, f"Stream chunk unexpectedly contained error: {c}"

    # 2. 실제 delta 내용 확인
    if "gemini" in model_name:
        assert any("gemini stream" in c for c in chunks), "Gemini delta content missing"
    elif "claude" in model_name:
        assert any("claude stream" in c for c in chunks), "Claude delta content missing"
    elif "genai" in model_name:
        assert any("genai response" in c for c in chunks), "GenAI delta content missing"

    # 3. 종료 이벤트([DONE]) 확인
    assert any("[DONE]" in c for c in chunks), "Stream missing [DONE] terminal event"

    # 4. 경고 발생 검증
    proxy_warnings = get_proxy_warnings(caplog)
    if "genai" in model_name:
        # top_p 미지원 경고 1회 + stream_buffering 경고 1회 = 총 2회 (중복 호출 없음)
        assert len(proxy_warnings) == 2, f"Expected 2 warnings for GenAI stream, got {len(proxy_warnings)}"
        assert any("top_p" in w.message for w in proxy_warnings)
        assert any("실시간 스트리밍 미지원 — 버퍼링 후 SSE 반환" in w.message for w in proxy_warnings)
    else:
        # Gemini / Claude: top_p 미지원 경고 1회
        assert len(proxy_warnings) == 1, f"Expected 1 warning for {model_name}, got {len(proxy_warnings)}"
        assert "top_p" in proxy_warnings[0].message


# ── 7. 유니코드 extra 키 이스케이프 및 페이로드 누락 방지 검증 (REQ-111-017, REQ-111-020) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_unicode_control_characters_in_extra_keys(caplog, provider_factory, model_name):
    """
    유니코드 제어문자가 포함된 extra 키 요청 시:
    1) 원시 제어문자가 경고 로그에 남지 않고 이스케이프됨
    2) 로그 메시지 전체 길이가 500자 이하임
    3) 업스트림 payload에 해당 extra 키가 실리지 않음 (REQ-111-017, REQ-111-020)
    """
    recorded: list[httpx.Request] = []
    provider = provider_factory(recorded)

    unicode_key = "x\u2028[ERROR] forged\u202E"
    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        unicode_key: "forged_value",
        "nel\u0085key": "val",
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        resp = await provider.chat(req)

    assert resp is not None
    proxy_warnings = get_proxy_warnings(caplog)
    assert len(proxy_warnings) == 1
    log_msg = proxy_warnings[0].message

    # 원시 유니코드 제어문자 없음
    assert "\u2028" not in log_msg
    assert "\u202e" not in log_msg
    assert "\u0085" not in log_msg

    # 이스케이프 확인
    assert "\\u2028" in log_msg
    assert "\\u202e" in log_msg
    assert "\\u0085" in log_msg

    # 메시지 길이 상한 (500자)
    assert len(log_msg) <= 500

    # 업스트림 payload에 유니코드 extra 키가 실리지 않음
    assert len(recorded) == 1
    payload = json.loads(recorded[0].content)
    assert unicode_key not in payload
    assert "nel\u0085key" not in payload
    if "llmConfig" in payload:
        assert unicode_key not in payload["llmConfig"]
        assert "nel\u0085key" not in payload["llmConfig"]

