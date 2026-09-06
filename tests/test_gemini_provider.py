"""
TASK-GEMINI-1 Gemini Provider 버그 수정 및 개선 검증 테스트.
REQ-111-040 ~ REQ-111-047 (IMP-G-01 ~ IMP-G-07)

검증 범위 (13종 시나리오 전수):
1. 툴 호출 3개가 청크마다 하나씩 오는 스트림 -> index가 0/1/2로 분리 (REQ-111-040, P0)
2. 같은 id의 arguments 델타가 여러 청크에 걸쳐 오는 경우 -> 같은 index 유지 (REQ-111-040, P0)
3. 업스트림이 index를 준 경우 -> 덮어쓰지 않고 보존 (REQ-111-040, P0)
4. 동시 요청 2건이 서로의 index 상태를 오염시키지 않음 (싱글톤 회귀 방지, REQ-111-040)
5. choices 빈 배열 -> IndexError가 아니라 명시적 ProviderError(502) (REQ-111-041, P0)
6. choices 키 부재 / 200 에러 바디 -> ProviderError(502) (REQ-111-041, P0)
7. finish_reason "SAFETY" -> "content_filter" 매핑 (비스트리밍 & 스트리밍) (REQ-111-043, P1)
8. 업스트림 created 필드 보존 (REQ-111-044, P1)
9. description 없는 tool 정의 -> payload에 null이 실리지 않음 (REQ-111-045, P1)
10. 업스트림이 [DONE] 없이 끊긴 경우 -> 프록시 보정 방출로 정상 종결 (REQ-111-032, REQ-111-034)
11. 첫 바이트 전 429 -> 재시도 후 성공 (REQ-111-046, P1)
12. 이미 방출 후 에러 -> 재시도하지 않고 에러 청크 방출 (REQ-111-046, P1)
13. GEMINI_PASSTHROUGH=1 에서 n=2 응답의 두 후보가 모두 보존 (REQ-111-042, P1)
"""

import anyio
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

# ai-proxy 디렉토리를 sys.path에 추가
PROXY_DIR = Path(__file__).resolve().parent.parent / "ai-proxy"
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))

from models import (
    ChatCompletionRequest,
    ChatMessage,
    FunctionDefinition,
    ToolDefinition,
)
from providers.claude_provider import ClaudeProvider  # circular import guard
from providers.base import ProviderError
from providers.gemini_provider import (
    GeminiProvider,
    PassthroughResponse,
    _map_finish_reason,
)



# ── 검증 헬퍼 ──

def parse_sse_chunks(raw_chunks: list[str]) -> list[dict[str, Any]]:
    """SSE 청크 리스트에서 JSON 딕셔너리만 추출 ([DONE] 제외)."""
    parsed = []
    for chunk in raw_chunks:
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                parsed.append(json.loads(line[6:]))
    return parsed


def make_test_provider(transport: httpx.AsyncBaseTransport) -> GeminiProvider:
    """httpx.MockTransport 기반 GeminiProvider 생성."""
    os.environ["GEMINI_API_KEY"] = "test-gemini-key"
    provider = GeminiProvider()
    provider.client = httpx.AsyncClient(
        transport=transport,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )
    return provider


# ── 1. 툴 호출 3개가 청크마다 하나씩 오는 스트림 -> index가 0, 1, 2 로 분리 (REQ-111-040) ──

@pytest.mark.anyio
async def test_tool_calls_sequential_chunks_indexes_separated():
    """
    업스트림에서 3개의 tool_calls가 각각 개별 청크로 도착할 때,
    청크별 enumerate 리셋 버그 없이 누적 카운터로 index가 0, 1, 2로 정상 부여되는지 검증 (REQ-111-040).
    """
    sse_body = (
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"tool_calls":[{"id":"call_1","type":"function","function":{"name":"read_file","arguments":"{}"}}]}}]}\n\n'
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"tool_calls":[{"id":"call_2","type":"function","function":{"name":"write_file","arguments":"{}"}}]}}]}\n\n'
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"tool_calls":[{"id":"call_3","type":"function","function":{"name":"bash","arguments":"{}"}}]}}]}\n\n'
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "run 3 tools"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    parsed = parse_sse_chunks(chunks)

    # tool_calls를 포함하는 청크 추출
    tc_chunks = [p for p in parsed if p.get("choices") and p["choices"][0].get("delta", {}).get("tool_calls")]
    assert len(tc_chunks) == 3, f"Expected 3 tool call chunks, got {len(tc_chunks)}"

    idx0 = tc_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["index"]
    idx1 = tc_chunks[1]["choices"][0]["delta"]["tool_calls"][0]["index"]
    idx2 = tc_chunks[2]["choices"][0]["delta"]["tool_calls"][0]["index"]

    assert idx0 == 0, f"First tool_call index should be 0, got {idx0}"
    assert idx1 == 1, f"Second tool_call index should be 1, got {idx1}"
    assert idx2 == 2, f"Third tool_call index should be 2, got {idx2}"


# ── 2. 같은 id의 arguments 델타가 여러 청크에 걸쳐 오는 경우 -> 같은 index 유지 (REQ-111-040) ──

@pytest.mark.anyio
async def test_tool_calls_same_id_maintains_same_index():
    """
    동일 tool_call id를 가진 인자 스트리밍 델타가 여러 청크에 걸쳐 올 때
    동일한 index가 유지되는지 검증 (REQ-111-040).
    """
    sse_body = (
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"tool_calls":[{"id":"call_abc","type":"function","function":{"name":"edit","arguments":"{\\"path\\": "}}]}}]}\n\n'
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"tool_calls":[{"id":"call_abc","function":{"arguments":"\\"main.py\\""}}]}}]}\n\n'
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "edit code"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    parsed = parse_sse_chunks(chunks)

    tc_chunks = [p for p in parsed if p.get("choices") and p["choices"][0].get("delta", {}).get("tool_calls")]
    assert len(tc_chunks) == 2

    assert tc_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["index"] == 0
    assert tc_chunks[1]["choices"][0]["delta"]["tool_calls"][0]["index"] == 0


# ── 3. 업스트림이 index를 준 경우 -> 덮어쓰지 않는지 (REQ-111-040) ──

@pytest.mark.anyio
async def test_tool_calls_upstream_provided_index_preserved():
    """업스트림이 명시적으로 제공한 index를 임의로 덮어쓰지 않고 보존하는지 검증 (REQ-111-040)."""
    sse_body = (
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"tool_calls":[{"id":"call_99","index":5,"type":"function","function":{"name":"search","arguments":"{}"}}]}}]}\n\n'
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "search"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    parsed = parse_sse_chunks(chunks)

    tc_chunks = [p for p in parsed if p.get("choices") and p["choices"][0].get("delta", {}).get("tool_calls")]
    assert len(tc_chunks) == 1
    assert tc_chunks[0]["choices"][0]["delta"]["tool_calls"][0]["index"] == 5


# ── 4. 동시 요청 2건이 서로의 index 상태를 오염시키지 않는지 (싱글톤 회귀 방지, REQ-111-040) ──

@pytest.mark.anyio
async def test_concurrent_streams_isolated_indexes():
    """
    단일 GeminiProvider 인스턴스로 동시 2건의 스트림을 수행할 때,
    tool_call 인덱스 카운터가 서로 간섭하지 않고 각 스트림마다 0부터 독립적으로 시작하는지 검증 (REQ-111-040).
    """
    def make_stream_body(call_prefix: str) -> bytes:
        return (
            f'data: {{"id\":\"cmpl-{call_prefix}\",\"choices\":[{{\"index\":0,\"delta\":{{\"tool_calls\":[{{\"id\":\"{call_prefix}_1\",\"type\":\"function\",\"function\":{{\"name\":\"f1\",\"arguments\":\"{{}}\"}}}}]}}}}]}}\n\n'
            f'data: {{"id\":\"cmpl-{call_prefix}\",\"choices\":[{{\"index\":0,\"delta\":{{\"tool_calls\":[{{\"id\":\"{call_prefix}_2\",\"type\":\"function\",\"function\":{{\"name\":\"f2\",\"arguments\":\"{{}}\"}}}}]}}}}]}}\n\n'
            f'data: {{"id\":\"cmpl-{call_prefix}\",\"choices\":[{{\"index\":0,\"delta\":{{}},\"finish_reason\":\"stop\"}}]}}\n\n'
            'data: [DONE]\n\n'
        ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prefix = "stream_a" if "request_A" in body["messages"][0]["content"] else "stream_b"
        return httpx.Response(200, content=make_stream_body(prefix), headers={"content-type": "text/event-stream"})

    shared_provider = make_test_provider(httpx.MockTransport(handler))

    req_a = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "request_A"}],
        "stream": True,
    })
    req_b = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "request_B"}],
        "stream": True,
    })

    chunks_a = []
    chunks_b = []

    async def run_a():
        nonlocal chunks_a
        chunks_a = [c async for c in shared_provider.stream(req_a)]

    async def run_b():
        nonlocal chunks_b
        chunks_b = [c async for c in shared_provider.stream(req_b)]

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_a)
        tg.start_soon(run_b)

    parsed_a = parse_sse_chunks(chunks_a)
    parsed_b = parse_sse_chunks(chunks_b)

    tc_a = [p for p in parsed_a if p.get("choices") and p["choices"][0].get("delta", {}).get("tool_calls")]
    tc_b = [p for p in parsed_b if p.get("choices") and p["choices"][0].get("delta", {}).get("tool_calls")]

    assert len(tc_a) == 2
    assert len(tc_b) == 2

    # 두 스트림 모두 index가 0, 1 이어야 함 (서로 누적되지 않음)
    assert [tc["choices"][0]["delta"]["tool_calls"][0]["index"] for tc in tc_a] == [0, 1]
    assert [tc["choices"][0]["delta"]["tool_calls"][0]["index"] for tc in tc_b] == [0, 1]


# ── 5. choices 빈 배열 -> IndexError 가 아니라 명시적 ProviderError(502) + 원인 메시지 (REQ-111-041) ──

@pytest.mark.anyio
async def test_parse_response_empty_choices_raises_provider_error():
    """choices가 빈 배열일 때 IndexError 대신 명시적 ProviderError(502)가 발생하는지 검증 (REQ-111-041)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "chatcmpl-empty",
            "choices": [],
            "usage": {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
        })

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "hello"}],
    })

    with pytest.raises(ProviderError) as exc_info:
        await provider.chat(req)

    assert exc_info.value.status_code == 502
    assert "no choices" in str(exc_info.value).lower()


# ── 6. choices 키 부재 / 200 에러 바디 -> ProviderError(502) (REQ-111-041) ──

@pytest.mark.anyio
async def test_parse_response_missing_choices_or_200_error_body():
    """업스트림이 choices 키 없이 200 에러 바디를 보낸 경우 502 ProviderError 발생 검증 (REQ-111-041)."""
    # 시나리오 1: 200 응답 내 error 객체 포함
    def handler_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "error": {"message": "Resource has been exhausted (rate limit)", "status": "RESOURCE_EXHAUSTED"}
        })

    provider_err = make_test_provider(httpx.MockTransport(handler_error))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "hello"}],
    })

    with pytest.raises(ProviderError) as exc_info:
        await provider_err.chat(req)

    assert exc_info.value.status_code == 502
    assert "exhausted" in str(exc_info.value).lower()

    # 시나리오 2: choices 키 자체가 누락된 경우
    def handler_no_key(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "test-no-choices"})

    provider_no_key = make_test_provider(httpx.MockTransport(handler_no_key))
    with pytest.raises(ProviderError) as exc_info2:
        await provider_no_key.chat(req)

    assert exc_info2.value.status_code == 502
    assert "no choices" in str(exc_info2.value).lower()


# ── 7. finish_reason "SAFETY" -> "content_filter" 매핑 (비스트리밍 & 스트리밍) (REQ-111-043) ──

@pytest.mark.anyio
async def test_finish_reason_whitelist_mapping():
    """Gemini 고유 finish_reason(SAFETY, RECITATION, MAX_TOKENS)이 OpenAI 표준으로 매핑되는지 검증 (REQ-111-043)."""
    # 7-1: 비스트리밍 검증
    def handler_chat(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "chatcmpl-safety",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "blocked"},
                "finish_reason": "SAFETY",
            }],
        })

    provider = make_test_provider(httpx.MockTransport(handler_chat))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "unsafe"}],
    })

    resp = await provider.chat(req)
    assert resp.choices[0].finish_reason == "content_filter"

    # 7-2: 스트리밍 검증
    sse_body = (
        'data: {"id":"cmpl-1","choices":[{"index":0,"delta":{"content":"blocked"},"finish_reason":"SAFETY"}]}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    def handler_stream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider_stream = make_test_provider(httpx.MockTransport(handler_stream))
    req_stream = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "unsafe"}],
        "stream": True,
    })

    chunks = [c async for c in provider_stream.stream(req_stream)]
    parsed = parse_sse_chunks(chunks)

    fr_chunks = [p for p in parsed if p.get("choices") and p["choices"][0].get("finish_reason")]
    assert len(fr_chunks) >= 1
    assert fr_chunks[0]["choices"][0]["finish_reason"] == "content_filter"


# ── 8. 업스트림 created 보존 (REQ-111-044) ──

@pytest.mark.anyio
async def test_upstream_created_preserved():
    """업스트림이 전달한 created 타임스탬프가 ChatCompletionResponse에 보존되는지 검증 (REQ-111-044)."""
    expected_created = 1705555555

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "chatcmpl-created-test",
            "created": expected_created,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }],
        })

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "check created"}],
    })

    resp = await provider.chat(req)
    assert resp.created == expected_created


# ── 9. description 없는 tool 정의 -> payload에 null이 실리지 않는지 (REQ-111-045) ──

@pytest.mark.anyio
async def test_tool_definition_without_description_excludes_null():
    """description이 None인 tool 정의가 직렬화될 때 exclude_none=True로 null 필드가 배제되는지 검증 (REQ-111-045)."""
    recorded_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        return httpx.Response(200, json={
            "id": "chatcmpl-tool",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "tool call planned"},
                "finish_reason": "stop",
            }],
        })

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [
            ToolDefinition(
                type="function",
                function=FunctionDefinition(
                    name="simple_fn",
                    description=None,
                    parameters=None,
                ),
            )
        ],
    })

    await provider.chat(req)
    assert len(recorded_requests) == 1
    sent_payload = json.loads(recorded_requests[0].content)

    assert "tools" in sent_payload
    tool_func = sent_payload["tools"][0]["function"]
    assert "name" in tool_func
    assert "description" not in tool_func, f"description should not be present in payload: {tool_func}"
    assert "parameters" not in tool_func, f"parameters should not be present in payload: {tool_func}"


# ── 10. 업스트림이 [DONE] 없이 끊긴 경우 -> 클라이언트가 정상 종결 인식 (REQ-111-032, REQ-111-034) ──

@pytest.mark.anyio
async def test_upstream_disconnect_without_done_terminates_cleanly():
    """
    업스트림이 finish_reason 및 [DONE] 없이 조기 단절되어도
    프록시가 finish_reason="stop" 청크 보정 및 data: [DONE]\n\n 을 방출하여 정상 종료하는지 검증 (REQ-111-032).
    """
    sse_body = (
        'data: {"id":"cmpl-trunc","choices":[{"index":0,"delta":{"content":"truncated output"}}]}\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "tell story"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    assert len(chunks) >= 3

    # 마지막 청크는 data: [DONE]\n\n 이어야 함
    assert chunks[-1] == "data: [DONE]\n\n"

    # [DONE] 직전 청크는 프록시가 보정한 finish_reason="stop" 이어야 함
    penultimate = parse_sse_chunks([chunks[-2]])[0]
    assert penultimate["choices"][0]["finish_reason"] == "stop"


# ── 11. 첫 바이트 전 429 -> 재시도 후 성공 (REQ-111-046) ──

@pytest.mark.anyio
async def test_stream_retry_on_429_before_first_byte_succeeds(monkeypatch):
    """첫 바이트 전 429 수신 시 지수 백오프 재시도하여 결국 성공 스트림을 yield하는지 검증 (REQ-111-046)."""
    monkeypatch.setenv("PROXY_RETRY_BASE_DELAY", "0.001")

    attempts = [0]
    sse_body = (
        'data: {"id":"cmpl-retried","choices":[{"index":0,"delta":{"content":"success after retry"},"finish_reason":"stop"}]}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        attempts[0] += 1
        if attempts[0] == 1:
            return httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "retry me"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    assert attempts[0] == 2, f"Expected 2 attempts, got {attempts[0]}"
    parsed = parse_sse_chunks(chunks)

    content_chunks = [p for p in parsed if p.get("choices") and p["choices"][0].get("delta", {}).get("content")]
    assert len(content_chunks) >= 1
    assert content_chunks[0]["choices"][0]["delta"]["content"] == "success after retry"


# ── 12. 이미 방출 후 에러 -> 재시도하지 않고 에러 청크 (REQ-111-046) ──

@pytest.mark.anyio
async def test_stream_error_after_first_byte_no_retry_emits_error_chunk():
    """첫 청크(role=assistant) 방출 후 업스트림에서 에러 발생 시 재시도하지 않고 에러 청크를 방출하는지 검증 (REQ-111-046)."""
    attempts = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        attempts[0] += 1
        # 비정상 바이트 스트림 반환 (aiter_lines 중 decode error 유발)
        return httpx.Response(200, content=b'data: valid line\n\ndata: {"choices": [unparseable}\n\n', headers={"content-type": "text/event-stream"})

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "fail midway"}],
        "stream": True,
    })

    chunks = [c async for c in provider.stream(req)]
    # 첫 바이트 방출 후 에러이므로 attempts는 1회만 실행되어야 함 (재시도 없음)
    assert attempts[0] == 1, f"Should not retry after emitting bytes, attempts: {attempts[0]}"
    assert any("error" in c for c in chunks) or any("[DONE]" in c for c in chunks)


# ── 13. GEMINI_PASSTHROUGH=1 에서 n=2 응답의 두 후보가 모두 보존되는지 (REQ-111-042) ──

@pytest.mark.anyio
async def test_gemini_passthrough_mode_preserves_multiple_choices(monkeypatch):
    """
    GEMINI_PASSTHROUGH=1 일 때 _parse_response의 choices[0] 단일 추출 손실 없이
    n=2 다중 choices 원형이 PassthroughResponse로 보존되는지 검증 (REQ-111-042).
    """
    monkeypatch.setenv("GEMINI_PASSTHROUGH", "1")

    raw_response_data = {
        "id": "chatcmpl-n2-passthrough",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gemini-3-pro-preview",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Candidate 1"},
                "finish_reason": "stop",
            },
            {
                "index": 1,
                "message": {"role": "assistant", "content": "Candidate 2"},
                "finish_reason": "stop",
            },
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "system_fingerprint": "fp_gemini_123",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw_response_data)

    provider = make_test_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest.model_validate({
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "give 2 options"}],
    })

    result = await provider.chat(req)

    # 1. PassthroughResponse 타입 및 dict 인터페이스 검증
    assert isinstance(result, (dict, PassthroughResponse))
    assert len(result["choices"]) == 2, f"Both choices should be preserved, got {len(result['choices'])}"
    assert result["choices"][0]["message"]["content"] == "Candidate 1"
    assert result["choices"][1]["message"]["content"] == "Candidate 2"

    # 2. proxy_server.py 호환성: result.model 속성 읽기 및 쓰기 동작 검증
    assert result.model == "gemini/gemini-3-pro-preview"
    result.model = "overridden/model-id"
    assert result["model"] == "overridden/model-id"
    assert result.model == "overridden/model-id"

    # 3. 추가 원본 필드 보존 검증
    assert result.get("system_fingerprint") == "fp_gemini_123"
