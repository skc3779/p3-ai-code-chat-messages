"""REQ-111-050~054: integrity checks using credential-free MockTransport."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai-proxy"))
from models import ChatCompletionRequest
from providers.base import ProviderError
from providers.genai_provider import GenAIProvider
from src.sensitive_filter import SensitiveWordFilter


def run_chat(body, messages=None, tools=None):
    captured = []
    async def run():
        provider = GenAIProvider.__new__(GenAIProvider)
        provider.base_url = "https://portal.test"
        provider.sensitive_filter = SensitiveWordFilter()
        def handle(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=body)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            provider.client = client
            result = await provider.chat(ChatCompletionRequest(
                model="genai/test", messages=messages or [{"role": "user", "content": "password"}], tools=tools))
        return result
    return asyncio.run(run()), captured


@pytest.fixture(autouse=True)
def filtering(monkeypatch):
    monkeypatch.delenv("GENAI_SENSITIVE_FILTER", raising=False)


# REQ-111-051: ordinary, nested, longer and unfinished code fences.
@pytest.mark.parametrize("code", [
    "```python\npassword = 1\n```",
    "```python\npassword = 1",
    "```markdown\n```python\npassword = 1\n```\n```",
    "````markdown\n```python\npassword = 1\n```\n````",
])
def test_code_fences_preserved(code):
    _, payloads = run_chat({"content": "ok"}, [
        {"role": "system", "content": "password\n" + code},
        {"role": "user", "content": "password\n" + code},
    ])
    for text in [payloads[0]["contents"][0], payloads[0]["systemPrompt"]]:
        assert code in text
        assert "p1assw1ord" in text


# REQ-111-052: embedded identifiers, case changes and JSON escapes restore.
@pytest.mark.parametrize("code,expected", [
    ("myP1assw1ordVar = S1ECR1ET", "myPasswordVar = SECRET"),
    (r"p1assw1ord", "password"),
])
def test_arguments_unmask(code, expected):
    raw = "```tool_call\n" + json.dumps({"name": "write", "arguments": {"code": code}}) + "\n```"
    result, _ = run_chat({"content": raw}, tools=[
        {"function": {"name": "write", "parameters": {"type": "object"}}}])
    assert json.loads(result.choices[0].message.tool_calls[0].function.arguments)["code"] == expected


def test_json_escaped_arguments_unmask():
    raw = r'{"name":"write","arguments":{"code":"p1assw1\u006frd"}}'
    result, _ = run_chat({"content": raw}, tools=[{"function": {"name": "write"}}])
    assert json.loads(result.choices[0].message.tool_calls[0].function.arguments)["code"] == "password"


# REQ-111-053: fail closed without leaking original/code to public errors.
@pytest.mark.parametrize("broken", ["p1assw1 ord", "P1ASSW1ORD"])
def test_residual_error_is_private(broken):
    with patch.object(SensitiveWordFilter, "unmask", side_effect=lambda text: text):
        with pytest.raises(ProviderError) as caught:
            run_chat({"content": "private-source " + broken})
    error = caught.value
    assert error.status_code == 502 and error.request_id
    assert "private-source" not in error.public_message
    assert broken not in error.public_message
    assert "password" not in error.public_message


def test_filter_disabled(monkeypatch):
    monkeypatch.setenv("GENAI_SENSITIVE_FILTER", "0")
    with patch.object(SensitiveWordFilter, "mask", side_effect=AssertionError("mask called")):
        with patch.object(SensitiveWordFilter, "unmask", side_effect=AssertionError("unmask called")):
            result, payloads = run_chat({"content": "p1assw1ord"})
    assert payloads[0]["contents"][0].endswith("password")
    assert result.choices[0].message.content == "p1assw1ord"


# REQ-111-054: logs carry counts, never source.
def test_count_mismatch_warns(caplog):
    run_chat({"content": "ok"})
    assert "count mismatch: mask=1 unmask=0" in caplog.text


def test_equal_counts_do_not_warn(caplog):
    result, _ = run_chat({"content": "p1assw1ord"})
    assert result.choices[0].message.content == "password"
    assert "count mismatch" not in caplog.text


# REQ-111-053: residuals encoded as JSON escapes must fail after decoding.
def test_split_escaped_argument_is_rejected():
    raw = json.dumps({"name": "write", "arguments": {"code": "p1assw1\nord"}})
    with pytest.raises(ProviderError, match="residual"):
        run_chat({"content": raw}, tools=[{"function": {"name": "write"}}])


def test_inline_fence_only_protects_inside():
    from providers.genai_provider import _mask_prose
    text, count = _mask_prose("password ```password``` password", SensitiveWordFilter())
    assert text == "p1assw1ord ```password``` p1assw1ord"
    assert count == 2
