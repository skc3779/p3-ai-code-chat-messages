"""
TASK-CORE-2 SSE 청크 빌더 공통화 계약 검증 테스트.
REQ-111-030 ~ REQ-111-035 (BaseProvider._chunk, _new_stream_id, SSE 계약)

검증 범위:
1. 청크 필수 필드 6종 (id, object, created, model, choices[0].index, choices[0].delta, choices[0].finish_reason)
2. 스트림 시작 시 delta={"role": "assistant"} 첫 청크 정확히 1회 방출
3. 종료 시 finish_reason 청크 -> [DONE] 순서 및 [DONE] 정확히 1회 방출
4. 한 스트림 생명주기 동안 동일한 chunk_id 유지
5. 업스트림 비정상 조기 종료(finish_reason/[DONE] 누락) 시 프록시 보정 방출
6. 에러 청크(_error_chunk) 발생 시 [DONE] 1회 방출 (이중 방출 없음)
7. stream_options.include_usage=True 시 [DONE] 직전 choices: [] usage 청크 방출 및 미제공 시 0-fill
8. messages[].name 정보 유실 추적 (Claude 경고, GenAI 인코딩 보존, Gemini 경고 없음)
9. 한글 텍스트 깨짐 없음 (ensure_ascii=False)
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx
import pytest

# ai-proxy 디렉토리를 sys.path에 추가
PROXY_DIR = Path(__file__).resolve().parent.parent / "ai-proxy"
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))

from models import ChatCompletionRequest, ChatMessage, StreamOptions
from providers.base import BaseProvider
from providers.claude_provider import ClaudeProvider
from providers.gemini_provider import GeminiProvider
from providers.genai_provider import GenAIProvider


# ── 검증 헬퍼 ──

def parse_sse_chunk(chunk_str: str) -> dict[str, Any]:
    """SSE 청크 문자열을 파싱하여 딕셔너리로 반환."""
    assert chunk_str.startswith("data: "), f"Chunk must start with 'data: ': {chunk_str!r}"
    assert chunk_str.endswith("\n\n"), f"Chunk must end with '\\n\\n': {chunk_str!r}"
    raw_json = chunk_str[len("data: "):-2].strip()
    return json.loads(raw_json)


def assert_valid_sse_chunk(chunk_str: str, expected_model: str, is_usage: bool = False) -> dict[str, Any]:
    """
    OpenAI 호환 Chat Completion SSE 청크 규격 검증 (REQ-111-030, REQ-111-033).
    - 6종 필수 필드: id, object, created, model, choices, (index, delta, finish_reason)
    """
    data = parse_sse_chunk(chunk_str)

    # 1. 공통 필수 필드 4종
    assert "id" in data and isinstance(data["id"], str) and len(data["id"]) > 0, "Missing or invalid 'id'"
    assert data["object"] == "chat.completion.chunk", f"Invalid object: {data.get('object')}"
    assert "created" in data and isinstance(data["created"], int) and data["created"] > 0, "Invalid 'created'"
    assert data["model"] == expected_model, f"Expected model '{expected_model}', got '{data.get('model')}'"

    # 2. choices 구조 검증
    assert "choices" in data and isinstance(data["choices"], list), "Missing 'choices' list"

    if is_usage:
        # REQ-111-033: usage 청크는 choices가 빈 배열이어야 함
        assert data["choices"] == [], f"Usage chunk choices must be empty, got: {data['choices']}"
        assert "usage" in data and isinstance(data["usage"], dict), "Missing 'usage' in usage chunk"
        usage = data["usage"]
        assert "prompt_tokens" in usage and isinstance(usage["prompt_tokens"], int)
        assert "completion_tokens" in usage and isinstance(usage["completion_tokens"], int)
        assert "total_tokens" in usage and isinstance(usage["total_tokens"], int)
    else:
        # 일반 청크: choices[0] 에 index, delta, finish_reason 포함
        assert len(data["choices"]) == 1, f"Expected 1 choice, got {len(data['choices'])}"
        choice = data["choices"][0]
        assert choice.get("index") == 0, f"Expected index 0, got {choice.get('index')}"
        assert "delta" in choice and isinstance(choice["delta"], dict), "Missing or invalid 'delta'"
        assert "finish_reason" in choice, "Missing 'finish_reason' key"
        assert choice["finish_reason"] is None or isinstance(choice["finish_reason"], str)

    return data


# ── 목(Mock) Provider 생성 헬퍼 ──

def make_mock_claude_provider(
    sse_lines: list[bytes] | None = None,
    status_code: int = 200,
) -> ClaudeProvider:
    if sse_lines is None:
        sse_lines = [
            b'event: message_start\n',
            b'data: {"type":"message_start","message":{"usage":{"input_tokens":10}}}\n\n',
            b'event: content_block_delta\n',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"안녕 Claude"}}\n\n'.encode("utf-8"),
            b'event: message_delta\n',
            b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}\n\n',
            b'event: message_stop\n',
            b'data: {"type":"message_stop"}\n\n',
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code, json={"error": "mock error"})
        body = json.loads(request.content)
        if body.get("stream"):
            content = b"".join(sse_lines)
            return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "id": "msg-123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "안녕"}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })

    p = ClaudeProvider()
    p.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.anthropic.com",
    )
    return p


def make_mock_gemini_provider(
    sse_lines: list[bytes] | None = None,
    status_code: int = 200,
) -> GeminiProvider:
    if sse_lines is None:
        sse_lines = [
            'data: {"id":"cmpl-1","choices":[{"delta":{"content":"안녕 Gemini"},"index":0}],"usage":{"prompt_tokens":8,"completion_tokens":4,"total_tokens":12}}\n\n'.encode("utf-8"),
            b'data: {"id":"cmpl-1","choices":[{"delta":{},"finish_reason":"stop","index":0}]}\n\n',
            b'data: [DONE]\n\n',
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code, json={"error": "mock error"})
        body = json.loads(request.content)
        if body.get("stream"):
            content = b"".join(sse_lines)
            return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "id": "chatcmpl-gemini",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gemini-3-pro-preview",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "안녕"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        })

    p = GeminiProvider()
    p.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )
    return p


def make_mock_genai_provider(
    content: str = "안녕 GenAI",
    status_code: int = 200,
    has_usage: bool = True,
) -> GenAIProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code, json={"error": "mock error"})
        resp_data = {"content": content}
        if has_usage:
            resp_data["usage"] = {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18}
        return httpx.Response(200, json=resp_data)

    p = GenAIProvider()
    p.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://api.genai.example.com",
    )
    return p


# ── 1. 첫 청크 delta.role == "assistant" 및 청크 필수 필드 6종 검증 (REQ-111-030, REQ-111-031) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_first_chunk_role_assistant_and_fields(provider_factory, model_name):
    """모든 Provider는 스트림 시작 시 delta={"role": "assistant"} 첫 청크를 방출하며 6종 필수 필드를 준수해야 함."""
    provider = provider_factory()
    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    assert len(chunks) >= 3  # role chunk + content chunk + finish_reason chunk + [DONE]
    assert chunks[-1] == "data: [DONE]\n\n"

    # 첫 번째 청크 검증
    first_chunk = assert_valid_sse_chunk(chunks[0], expected_model=model_name)
    assert first_chunk["choices"][0]["delta"] == {"role": "assistant"}
    assert first_chunk["choices"][0]["finish_reason"] is None


# ── 2. 한 스트림 동안 동일한 chunk_id 유지 (REQ-111-030) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_consistent_chunk_id_across_stream(provider_factory, model_name):
    """한 스트림 동안 모든 청크가 동일한 chunk_id (chatcmpl-...)를 유지해야 함."""
    provider = provider_factory()
    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    json_chunks = [parse_sse_chunk(c) for c in chunks if c != "data: [DONE]\n\n"]

    chunk_ids = {c["id"] for c in json_chunks}
    assert len(chunk_ids) == 1, f"Multiple chunk IDs found: {chunk_ids}"
    stream_id = chunk_ids.pop()
    assert stream_id.startswith("chatcmpl-"), f"Invalid ID format: {stream_id}"


# ── 3. 종료 청크 순서 (finish_reason -> [DONE]) 및 [DONE] 1회 방출 (REQ-111-032, REQ-111-034) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_stream_termination_order_and_single_done(provider_factory, model_name):
    """
    스트림 종료 시 finish_reason 청크 -> [DONE] 순서로 방출되며,
    [DONE]은 정확히 1회만 방출되고 finish_reason도 중복되지 않아야 함.
    """
    provider = provider_factory()
    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]

    # [DONE] 정확히 1회 방출
    done_count = sum(1 for c in chunks if c.strip() == "data: [DONE]")
    assert done_count == 1
    assert chunks[-1] == "data: [DONE]\n\n"

    # [DONE] 직전 청크는 finish_reason이 non-None
    penultimate = assert_valid_sse_chunk(chunks[-2], expected_model=model_name)
    assert penultimate["choices"][0]["finish_reason"] in ("stop", "tool_calls")

    # 전체 스트림에서 finish_reason이 non-None인 청크는 정확히 1개
    finish_reasons = [
        parse_sse_chunk(c)["choices"][0]["finish_reason"]
        for c in chunks[:-1]
        if parse_sse_chunk(c).get("choices")
        and parse_sse_chunk(c)["choices"][0].get("finish_reason") is not None
    ]
    assert len(finish_reasons) == 1, f"finish_reason emitted multiple times: {finish_reasons}"


# ── 4. 업스트림 비정상 조기 종료 시 프록시 finish_reason/DONE 보정 (REQ-111-032, REQ-111-034) ──

@pytest.mark.anyio
async def test_gemini_upstream_disconnect_without_done_or_finish_reason():
    """Gemini 업스트림이 finish_reason 및 [DONE] 없이 연결을 끊어도 프록시가 보정 방출해야 함."""
    # 업스트림이 [DONE] 없이 콘텐츠 청크만 보내고 끊김
    truncated_lines = [
        'data: {"id":"cmpl-trunc","choices":[{"delta":{"content":"끊김 테스트"},"index":0}]}\n\n'.encode("utf-8"),
    ]
    provider = make_mock_gemini_provider(sse_lines=truncated_lines)
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    assert chunks[-1] == "data: [DONE]\n\n"

    # 보정된 finish_reason="stop" 청크 확인
    compensated = assert_valid_sse_chunk(chunks[-2], expected_model="gemini/gemini-3-pro-preview")
    assert compensated["choices"][0]["finish_reason"] == "stop"


@pytest.mark.anyio
async def test_claude_upstream_disconnect_without_message_delta():
    """Claude 업스트림이 message_delta 없이 연결을 끊어도 프록시가 보정 방출해야 함."""
    # text_delta 이후 message_delta 없이 조기 종료
    truncated_lines = [
        b'event: content_block_delta\n',
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"안녕"}}\n\n'.encode("utf-8"),
    ]
    provider = make_mock_claude_provider(sse_lines=truncated_lines)
    req = ChatCompletionRequest.model_validate({
        "model": "claude/claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    assert chunks[-1] == "data: [DONE]\n\n"

    compensated = assert_valid_sse_chunk(chunks[-2], expected_model="claude/claude-sonnet-4-6")
    assert compensated["choices"][0]["finish_reason"] == "stop"


# ── 5. 에러 청크(_error_chunk) 발생 시 [DONE] 단 1회 방출 보장 (REQ-111-020, REQ-111-032) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (lambda: make_mock_claude_provider(status_code=429), "claude/claude-sonnet-4-6"),
    (lambda: make_mock_claude_provider(status_code=500), "claude/claude-sonnet-4-6"),
    (lambda: make_mock_gemini_provider(status_code=429), "gemini/gemini-3-pro-preview"),
    (lambda: make_mock_gemini_provider(status_code=500), "gemini/gemini-3-pro-preview"),
    (lambda: make_mock_genai_provider(status_code=500), "genai/gpt-oss-120B-medium"),
])
async def test_error_chunk_emits_done_only_once(provider_factory, model_name):
    """에러 발생 시 _error_chunk()가 방출되며, [DONE]은 정확히 1회만 포함되어야 함."""
    provider = provider_factory()
    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    full_output = "".join(chunks)

    # 전체 출력에서 [DONE]은 정확히 1회
    assert full_output.count("[DONE]") == 1
    assert "error" in full_output


# ── 6. stream_options.include_usage=True 검증 (REQ-111-033) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_stream_options_include_usage(provider_factory, model_name):
    """include_usage=True 설정 시 [DONE] 직전에 choices: [] 인 usage 청크가 방출되어야 함."""
    provider = provider_factory()
    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "stream_options": {"include_usage": True},
    })

    chunks = [c async for c in provider.stream(req)]
    assert chunks[-1] == "data: [DONE]\n\n"

    # [DONE] 직전 청크는 usage 청크
    usage_chunk_str = chunks[-2]
    usage_chunk = assert_valid_sse_chunk(usage_chunk_str, expected_model=model_name, is_usage=True)

    assert usage_chunk["choices"] == []
    usage = usage_chunk["usage"]
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    # usage 청크 직전 청크는 finish_reason 청크
    fr_chunk = assert_valid_sse_chunk(chunks[-3], expected_model=model_name)
    assert fr_chunk["choices"][0]["finish_reason"] is not None


@pytest.mark.anyio
async def test_include_usage_fallback_when_no_usage_from_upstream(caplog):
    """업스트림이 usage를 제공하지 않는 경우 0으로 채우고 debug 로그를 남김 (REQ-111-033)."""
    provider = make_mock_genai_provider(has_usage=False)
    req = ChatCompletionRequest.model_validate({
        "model": "genai/gpt-oss-120B-medium",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": True,
        "stream_options": {"include_usage": True},
    })

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="ai-proxy"):
        chunks = [c async for c in provider.stream(req)]

    usage_chunk_str = chunks[-2]
    usage_chunk = assert_valid_sse_chunk(usage_chunk_str, expected_model="genai/gpt-oss-120B-medium", is_usage=True)
    assert usage_chunk["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    debug_logs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("no usage data" in msg for msg in debug_logs)


# ── 7. messages[].name 미지원 경고 검증 (REQ-111-035) ──

@pytest.mark.anyio
async def test_messages_name_warning_claude(caplog):
    """Claude는 messages[].name 필드가 있으면 1회 경고를 남겨야 함."""
    provider = make_mock_claude_provider()
    req = ChatCompletionRequest.model_validate({
        "model": "claude/claude-sonnet-4-6",
        "messages": [
            {"role": "user", "content": "hello", "name": "alice"},
            {"role": "assistant", "content": "hi"},
        ],
        "stream": True,
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        _ = [c async for c in provider.stream(req)]

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING and "messages[].name" in r.message]
    assert len(warnings) == 1
    assert "messages[].name" in warnings[0]

    # 동일 요청 객체로 다시 호출해도 중복 경고 없음
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        _ = [c async for c in provider.stream(req)]
    warnings_second = [r.message for r in caplog.records if r.levelno == logging.WARNING and "messages[].name" in r.message]
    assert len(warnings_second) == 0


@pytest.mark.anyio
@pytest.mark.parametrize("name,encoded", [
    ("bob", "bob"), ("a b", "a%20b"),
    ("한글", "%ED%95%9C%EA%B8%80"), ("x]y", "x%5Dy"),
])
@pytest.mark.parametrize("stream", [False, True])
async def test_messages_name_preserved_genai(caplog, name, encoded, stream):
    """REQ-111-035: 실제 업스트림 요청에 name과 본문이 보존되고 유실 경고가 없어야 함."""
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"content": "안녕"})

    provider = GenAIProvider()
    await provider.aclose()
    provider.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "genai/gpt-oss-120B-medium",
        "messages": [{"role": "user", "content": "hello", "name": name}],
        "stream": stream,
    })

    caplog.clear()
    try:
        with caplog.at_level(logging.WARNING, logger="ai-proxy"):
            if stream:
                _ = [c async for c in provider.stream(req)]
            else:
                await provider.chat(req)
    finally:
        await provider.aclose()

    assert len(captured) == 1
    contents = captured[0]["contents"]
    assert len(contents) == 1
    marker = re.fullmatch(r"\[USER#[0-9a-f]+ name=([^\]\s]+)\]\nhello", contents[0])
    assert marker is not None, f"Malformed role marker or lost content: {contents!r}"
    assert marker.group(1) == encoded
    assert unquote(marker.group(1)) == name

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING and "messages[].name" in r.message]
    assert warnings == [], f"Preserved name incorrectly reported as lost: {warnings}"


@pytest.mark.anyio
async def test_messages_name_no_warning_gemini(caplog):
    """Gemini는 messages[].name 필드를 지원하므로 경고가 발생하지 않아야 함."""
    provider = make_mock_gemini_provider()
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "hello", "name": "charlie"}],
        "stream": True,
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        _ = [c async for c in provider.stream(req)]

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING and "messages[].name" in r.message]
    assert len(warnings) == 0


# ── 8. 한글 텍스트 깨짐 없음 검증 (ensure_ascii=False) ──

@pytest.mark.anyio
@pytest.mark.parametrize("provider_factory,model_name", [
    (make_mock_claude_provider, "claude/claude-sonnet-4-6"),
    (make_mock_gemini_provider, "gemini/gemini-3-pro-preview"),
    (make_mock_genai_provider, "genai/gpt-oss-120B-medium"),
])
async def test_korean_text_preserved_in_chunks(provider_factory, model_name):
    """청크 내부의 한글 텍스트가 유니코드 이스케이프 없이 한글 그대로 유지되어야 함."""
    provider = provider_factory()
    req = ChatCompletionRequest.model_validate({
        "model": model_name,
        "messages": [{"role": "user", "content": "안녕"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    full_str = "".join(chunks)

    assert "안녕" in full_str
    assert "\\uc548\\ub155" not in full_str
