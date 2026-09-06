"""
TASK-CLAUDE-1 Claude Provider 정합화 검증 테스트 스위트.
REQ-111-040 ~ REQ-111-049 (IMP-C-01 ~ IMP-C-11)

검증 범위 (15종 시나리오 전수):
1. 메시지 정규화 — 선두 assistant 메시지 앞에 user 삽입 (REQ-111-040)
2. 메시지 정규화 — 연속 user 메시지 병합 (텍스트) (REQ-111-040)
3. 메시지 정규화 — 연속 assistant 메시지 병합 (REQ-111-040)
4. 메시지 정규화 — 빈 content 메시지 제거 (텍스트) (REQ-111-040)
5. 메시지 정규화 — 빈 content 이지만 tool_use 포함 시 보존 (REQ-111-040)
6. 메시지 정규화 — 빈 content 이지만 tool_result 포함 시 보존 (REQ-111-040)
7. 메시지 정규화 — 마지막 assistant 프리필 후행 공백 rstrip (REQ-111-040)
8. finish_reason 매핑 — max_tokens -> length, end_turn -> stop, tool_use -> tool_calls (논스트리밍) (REQ-111-041)
9. finish_reason 매핑 — max_tokens -> length, end_turn -> stop, tool_use -> tool_calls (스트리밍) (REQ-111-041)
10. 멀티모달 — data URL base64 image_url 변환 (REQ-111-042)
11. 멀티모달 — 원격 URL image_url 변환 (REQ-111-042)
12. 스트리밍 인밴드 에러 이벤트 — {"type": "error", "error": {...}} -> _error_chunk (REQ-111-043)
13. 스트리밍 pre-flight 재시도 — 529 수신 후 1회 재시도 성공 (REQ-111-044)
14. max_tokens 기본값 — router 메타데이터 상한 반영 (미지정 시 65536) (REQ-111-045)
15. 프롬프트 캐싱 — CLAUDE_PROMPT_CACHE=1 일 때 system/tools 에 cache_control 부착 + usage 합산 (REQ-111-047, REQ-111-048)
+ 보너스: 다중 system 누적 및 tool_result is_error 전달 검증 (REQ-111-049)
"""

import os
import sys
import json
from pathlib import Path
from typing import Any
import pytest
import httpx

# ai-proxy 디렉토리를 sys.path에 추가
PROXY_DIR = Path(__file__).resolve().parent.parent / "ai-proxy"
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))

from models import (
    ChatCompletionRequest,
    ChatMessage,
    ToolCall,
    FunctionCall,
    ToolDefinition,
    FunctionDefinition,
    StreamOptions,
)
from providers.claude_provider import ClaudeProvider
from router import get_model_max_output


# ── 테스트 픽스처 및 헬퍼 ──

@pytest.fixture
def anyio_backend():
    """ai-proxy는 asyncio 기반 비동기 프레임워크이므로 asyncio 백엔드만 활성화."""
    return "asyncio"


def make_claude_provider(transport: httpx.AsyncBaseTransport) -> ClaudeProvider:
    """httpx.MockTransport 기반 ClaudeProvider 생성."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-key-12345"
    provider = ClaudeProvider()
    provider.client = httpx.AsyncClient(
        transport=transport,
        base_url="https://api.anthropic.com",
    )
    return provider


def parse_sse_chunks(raw_chunks: list[str]) -> list[dict[str, Any]]:
    """SSE 청크 목록에서 JSON 딕셔너리만 추출 ([DONE] 제외)."""
    parsed = []
    for chunk in raw_chunks:
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                parsed.append(json.loads(line[6:]))
    return parsed


# ── 1. 메시지 정규화 — 선두 assistant 메시지 앞에 user 삽입 (REQ-111-040) ──

def test_normalize_leading_assistant_prepends_user():
    """선두 메시지가 assistant일 때 Anthropic 제약(첫 메시지는 user)을 준수하도록 더미 user 메시지 주입."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="assistant", content="I am an AI assistant."),
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert system_msg is None
    assert len(normalized) == 2
    assert normalized[0]["role"] == "user"
    assert normalized[0]["content"] == "Hello"
    assert normalized[1]["role"] == "assistant"
    assert normalized[1]["content"] == "I am an AI assistant."


# ── 2. 메시지 정규화 — 연속 user 메시지 병합 (텍스트) (REQ-111-040) ──

def test_normalize_consecutive_user_messages_merged():
    """연속된 user 메시지들이 \\n\\n 으로 올바르게 병합되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="user", content="Hello world"),
            ChatMessage(role="user", content="How are you?"),
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert len(normalized) == 1
    assert normalized[0]["role"] == "user"
    assert normalized[0]["content"] == "Hello world\n\nHow are you?"


# ── 3. 메시지 정규화 — 연속 assistant 메시지 병합 (REQ-111-040) ──

def test_normalize_consecutive_assistant_messages_merged():
    """연속된 assistant 메시지들이 순서를 유지하며 병합되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="user", content="Do tasks"),
            ChatMessage(role="assistant", content="Step 1 complete."),
            ChatMessage(role="assistant", content="Step 2 complete."),
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert len(normalized) == 2
    assert normalized[0]["role"] == "user"
    assert normalized[0]["content"] == "Do tasks"
    assert normalized[1]["role"] == "assistant"
    assert normalized[1]["content"] == "Step 1 complete.\n\nStep 2 complete."


# ── 4. 메시지 정규화 — 빈 content 메시지 제거 (텍스트) (REQ-111-040) ──

def test_normalize_empty_content_message_removed():
    """툴 호출이 없는 빈 문자열/공백 메시지는 필터링되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="user", content="Question"),
            ChatMessage(role="assistant", content=""),
            ChatMessage(role="assistant", content="   \n\t  "),
            ChatMessage(role="user", content="Additional detail"),
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert len(normalized) == 1
    assert normalized[0]["role"] == "user"
    assert normalized[0]["content"] == "Question\n\nAdditional detail"


# ── 5. 메시지 정규화 — 빈 content 이지만 tool_use 포함 시 보존 (REQ-111-040) ──

def test_normalize_empty_content_with_tool_use_preserved():
    """content가 빈 문자열이어도 tool_calls가 있으면 assistant 메시지가 보존되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="user", content="Run command"),
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_bash_01",
                        type="function",
                        function=FunctionCall(name="bash", arguments='{"cmd":"pwd"}'),
                    )
                ],
            ),
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert len(normalized) == 2
    assert normalized[1]["role"] == "assistant"
    blocks = normalized[1]["content"]
    assert isinstance(blocks, list)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "tool_use"
    assert blocks[0]["id"] == "call_bash_01"
    assert blocks[0]["name"] == "bash"
    assert blocks[0]["input"] == {"cmd": "pwd"}


# ── 6. 메시지 정규화 — 빈 content 이지만 tool_result 포함 시 보존 (REQ-111-040) ──

def test_normalize_empty_content_with_tool_result_preserved():
    """tool role의 content가 빈 문자열이어도 tool_result 블록과 짝이 보존되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="user", content="Run command"),
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_bash_01",
                        type="function",
                        function=FunctionCall(name="bash", arguments='{"cmd":"true"}'),
                    )
                ],
            ),
            ChatMessage(role="tool", content="", tool_call_id="call_bash_01"),
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert len(normalized) == 3
    assert normalized[2]["role"] == "user"
    results = normalized[2]["content"]
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["type"] == "tool_result"
    assert results[0]["tool_use_id"] == "call_bash_01"
    assert results[0]["content"] == ""


# ── 7. 메시지 정규화 — 마지막 assistant 프리필 후행 공백 rstrip (REQ-111-040) ──

def test_normalize_trailing_assistant_prefill_rstrip():
    """대화 마지막의 assistant prefill 메시지에 후행 공백이 있으면 Anthropic 400 방지를 위해 rstrip 처리되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="user", content="Output json"),
            ChatMessage(role="assistant", content='{\n  "status": "ok"   \n\t '),
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert len(normalized) == 2
    assert normalized[1]["role"] == "assistant"
    assert normalized[1]["content"] == '{\n  "status": "ok"'


# ── 8. finish_reason 매핑 — max_tokens -> length, end_turn -> stop, tool_use -> tool_calls (논스트리밍) (REQ-111-041) ──

def test_finish_reason_mapping_non_streaming():
    """논스트리밍 응답에서 Anthropic stop_reason이 OpenAI finish_reason으로 정확히 매핑되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    cases = [
        ("max_tokens", "length"),
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("refusal", "stop"),
        ("pause_turn", "stop"),
        ("tool_use", "tool_calls"),
    ]

    for anthropic_reason, expected_openai in cases:
        data = {
            "id": "msg_test",
            "content": [{"type": "text", "text": "result"}],
            "stop_reason": anthropic_reason,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        resp = provider._parse_response(data, "claude-sonnet-4-6")
        assert resp.choices[0].finish_reason == expected_openai, (
            f"Expected {expected_openai} for Anthropic stop_reason {anthropic_reason}, got {resp.choices[0].finish_reason}"
        )


# ── 9. finish_reason 매핑 — max_tokens -> length, end_turn -> stop, tool_use -> tool_calls (스트리밍) (REQ-111-041) ──

@pytest.mark.anyio
async def test_finish_reason_mapping_streaming():
    """스트리밍 응답에서 message_delta의 stop_reason이 OpenAI finish_reason으로 정확히 변환되는지 검증."""
    cases = [
        ("max_tokens", "length"),
        ("end_turn", "stop"),
        ("tool_use", "tool_calls"),
    ]

    for anthropic_reason, expected_openai in cases:
        sse_body = (
            'data: {"type":"message_start","message":{"id":"msg_1","usage":{"input_tokens":5}}}\n\n'
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hi"}}\n\n'
            f'data: {{"type":"message_delta","delta":{{"stop_reason":"{anthropic_reason}"}},"usage":{{"output_tokens":2}}}}\n\n'
            'data: {"type":"message_stop"}\n\n'
        ).encode("utf-8")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

        provider = make_claude_provider(httpx.MockTransport(handler))
        req = ChatCompletionRequest(
            model="claude/claude-sonnet-4-6",
            messages=[ChatMessage(role="user", content="hi")],
            stream=True,
        )

        chunks = [c async for c in provider.stream(req)]
        parsed = parse_sse_chunks(chunks)

        fr_chunks = [p for p in parsed if p.get("choices") and p["choices"][0].get("finish_reason") is not None]
        assert len(fr_chunks) >= 1
        assert fr_chunks[0]["choices"][0]["finish_reason"] == expected_openai


# ── 10. 멀티모달 — data URL base64 image_url 변환 (REQ-111-042) ──

def test_multimodal_data_url_base64_conversion():
    """data URL 형태의 이미지 파트가 Anthropic base64 source 블록으로 변환되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Describe image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA"},
                    },
                ],
            )
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert len(normalized) == 1
    blocks = normalized[0]["content"]
    assert isinstance(blocks, list)
    assert len(blocks) == 2
    assert blocks[0] == {"type": "text", "text": "Describe image"}
    assert blocks[1]["type"] == "image"
    assert blocks[1]["source"]["type"] == "base64"
    assert blocks[1]["source"]["media_type"] == "image/png"
    assert blocks[1]["source"]["data"] == "iVBORw0KGgoAAAANSUhEUgAA"


# ── 11. 멀티모달 — 원격 URL image_url 변환 (REQ-111-042) ──

def test_multimodal_remote_url_conversion():
    """원격 HTTP/HTTPS URL 이미지가 Anthropic url source 블록으로 변환되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Describe remote image"},
                    {
                        "type": "image_url",
                        "image_url": "https://example.com/images/cat.jpg",
                    },
                ],
            )
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert len(normalized) == 1
    blocks = normalized[0]["content"]
    assert isinstance(blocks, list)
    assert len(blocks) == 2
    assert blocks[0] == {"type": "text", "text": "Describe remote image"}
    assert blocks[1]["type"] == "image"
    assert blocks[1]["source"]["type"] == "url"
    assert blocks[1]["source"]["url"] == "https://example.com/images/cat.jpg"


# ── 12. 스트리밍 인밴드 에러 이벤트 — {"type": "error", "error": {...}} -> _error_chunk (REQ-111-043) ──

@pytest.mark.anyio
async def test_streaming_inband_error_event():
    """SSE 스트림 중간에 Anthropic error 이벤트가 발생했을 때 에러 청크를 방출하고 정상 종결되는지 검증."""
    sse_body = (
        'data: {"type":"message_start","message":{"id":"msg_err","usage":{"input_tokens":5}}}\n\n'
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
        'data: {"type":"error","error":{"type":"overloaded_error","message":"Anthropic system is overloaded"}}\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = make_claude_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hi")],
        stream=True,
    )

    chunks = [c async for c in provider.stream(req)]
    parsed = parse_sse_chunks(chunks)

    # role chunk 다음에 error 청크가 와야 함
    err_chunks = [p for p in parsed if "error" in p]
    assert len(err_chunks) == 1
    assert "Anthropic system is overloaded" in err_chunks[0]["error"]["message"]
    assert err_chunks[0]["error"]["code"] == "proxy_error"


# ── 13. 스트리밍 pre-flight 재시도 — 529 수신 후 1회 재시도 성공 (REQ-111-044) ──

@pytest.mark.anyio
async def test_streaming_preflight_retry_529_then_success(monkeypatch):
    """첫 바이트 전 529 Overloaded 발생 시 지수 백오프로 재시도하여 2번째 시도에서 성공하는지 검증."""
    monkeypatch.setenv("RETRY_BASE_DELAY", "0.01")
    request_count = 0

    sse_body = (
        'data: {"type":"message_start","message":{"id":"msg_ok","usage":{"input_tokens":12}}}\n\n'
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Recovered"}}\n\n'
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":4}}\n\n'
        'data: {"type":"message_stop"}\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(529, text='{"error":{"message":"Overloaded"}}')
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = make_claude_provider(httpx.MockTransport(handler))
    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hello")],
        stream=True,
    )

    chunks = [c async for c in provider.stream(req)]
    assert request_count == 2, f"Expected 2 attempts (1 retry), got {request_count}"

    parsed = parse_sse_chunks(chunks)
    text_chunks = [p for p in parsed if p.get("choices") and p["choices"][0].get("delta", {}).get("content")]
    assert len(text_chunks) == 1
    assert text_chunks[0]["choices"][0]["delta"]["content"] == "Recovered"


# ── 14. max_tokens 기본값 — router 메타데이터 상한 반영 (미지정 시 65536) (REQ-111-045) ──

def test_max_tokens_default_from_router_metadata():
    """max_tokens 미지정 시 router.py의 메타데이터(Claude 모델 65536)를 상한으로 자동 적용하는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    # 1. Claude Sonnet (미지정 -> 65536)
    req1 = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="Hi")],
    )
    p1 = provider._transform_request(req1)
    assert p1["max_tokens"] == 65536

    # 2. Claude Haiku (미지정 -> 65536)
    req2 = ChatCompletionRequest(
        model="claude-haiku-4-5",
        messages=[ChatMessage(role="user", content="Hi")],
    )
    p2 = provider._transform_request(req2)
    assert p2["max_tokens"] == 65536

    # 3. 명시적 max_tokens 지정 시 사용자 값 존중
    req3 = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        max_tokens=2048,
        messages=[ChatMessage(role="user", content="Hi")],
    )
    p3 = provider._transform_request(req3)
    assert p3["max_tokens"] == 2048


# ── 15. 프롬프트 캐싱 — CLAUDE_PROMPT_CACHE=1 일 때 system/tools 에 cache_control 부착 + usage 합산 (REQ-111-047, REQ-111-048) ──

@pytest.mark.anyio
async def test_prompt_caching_and_usage_accounting(monkeypatch):
    """CLAUDE_PROMPT_CACHE=1 일 때 system 및 tools[-1]에 cache_control이 부착되고 usage에 캐시 토큰이 합산되는지 검증."""
    monkeypatch.setenv("CLAUDE_PROMPT_CACHE", "1")
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    # 1. 요청 변환 시 system 블록 및 tools 마지막 요소에 cache_control 부착 검증
    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="system", content="System instruction"),
            ChatMessage(role="user", content="Do search"),
        ],
        tools=[
            ToolDefinition(
                type="function",
                function=FunctionDefinition(name="search", description="Search web"),
            ),
            ToolDefinition(
                type="function",
                function=FunctionDefinition(name="calc", description="Calculate"),
            ),
        ],
    )
    payload = provider._transform_request(req)

    # system이 리스트 형태로 감싸지고 cache_control 부착
    assert isinstance(payload["system"], list)
    assert payload["system"][0]["type"] == "text"
    assert payload["system"][0]["text"] == "System instruction"
    assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}

    # tools 마지막 요소에만 cache_control 부착
    assert len(payload["tools"]) == 2
    assert "cache_control" not in payload["tools"][0]
    assert payload["tools"][1]["cache_control"] == {"type": "ephemeral"}

    # 2. 논스트리밍 usage 합산 검증: prompt_tokens = input + cache_creation + cache_read
    data = {
        "id": "msg_cached",
        "content": [{"type": "text", "text": "cached response"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 100,
            "cache_creation_input_tokens": 50,
            "cache_read_input_tokens": 200,
            "output_tokens": 30,
        },
    }
    resp = provider._parse_response(data, "claude-sonnet-4-6")
    assert resp.usage.prompt_tokens == 350  # 100 + 50 + 200
    assert resp.usage.completion_tokens == 30
    assert resp.usage.total_tokens == 380

    # 3. 스트리밍 usage 청크 전달 검증 (include_usage=True)
    sse_body = (
        'data: {"type":"message_start","message":{"id":"msg_stream_c","usage":{"input_tokens":80,"cache_creation_input_tokens":40,"cache_read_input_tokens":120}}}\n\n'
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}\n\n'
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":15}}\n\n'
        'data: {"type":"message_stop"}\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    stream_provider = make_claude_provider(httpx.MockTransport(handler))
    stream_req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="Hi")],
        stream=True,
        stream_options=StreamOptions(include_usage=True),
    )

    chunks = [c async for c in stream_provider.stream(stream_req)]
    parsed = parse_sse_chunks(chunks)

    usage_chunks = [p for p in parsed if p.get("usage") is not None]
    assert len(usage_chunks) == 1
    u = usage_chunks[0]["usage"]
    assert u["prompt_tokens"] == 240  # 80 + 40 + 120
    assert u["completion_tokens"] == 15
    assert u["total_tokens"] == 255


# ── 보너스: 다중 system 누적 및 tool_result is_error 지원 (REQ-111-049) ──

def test_multi_system_accumulation_and_tool_result_is_error():
    """여러 system 메시지가 += "\\n\\n" 으로 누적되고, tool 메시지의 is_error 속성이 전달되는지 검증."""
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
    provider = ClaudeProvider()

    tool_msg = ChatMessage(role="tool", content="command failed: 127", tool_call_id="call_err")
    object.__setattr__(tool_msg, "is_error", True)  # 동적 is_error 속성 주입

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[
            ChatMessage(role="system", content="System 1"),
            ChatMessage(role="system", content="System 2"),
            ChatMessage(role="user", content="Run command"),
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_err",
                        type="function",
                        function=FunctionCall(name="bash", arguments="{}"),
                    )
                ],
            ),
            tool_msg,
        ],
    )
    system_msg, normalized = provider._transform_messages(req)

    assert system_msg == "System 1\n\nSystem 2"
    assert len(normalized) == 3
    tool_results = normalized[2]["content"]
    assert tool_results[0]["is_error"] is True
