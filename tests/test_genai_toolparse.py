"""REQ-111-040~045: synchronous parser regression tests; no HTTP/client setup."""
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai-proxy"))
from models import ChatCompletionRequest
from providers.genai_provider import GenAIProvider, _scan_balanced_json


@pytest.fixture
def provider():
    return GenAIProvider.__new__(GenAIProvider)


@pytest.fixture
def request_tools():
    schemas = {
        "edit": {"type": "object", "required": ["filePath", "oldString", "newString"],
                 "properties": {k: {"type": "string"} for k in ("filePath", "oldString", "newString")}},
        "read": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
        "write": {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}}},
        "bash": {"type": "object", "required": ["command"], "properties": {"command": {"type": "string"}}},
        "nested": {"type": "object", "required": ["data"], "properties": {
            "data": {"type": "object", "required": ["items"], "properties": {
                "items": {"type": "array", "items": {"type": "object", "required": ["count"],
                                                       "properties": {"count": {"type": "integer"}}}}
            }}}},
    }
    return ChatCompletionRequest(model="genai/test", messages=[], tools=[
        {"type": "function", "function": {"name": name, "parameters": schema}}
        for name, schema in schemas.items()
    ])


def invocation(name="read", arguments=None, key="arguments"):
    return json.dumps({"name": name, key: {"path": "a.py"} if arguments is None else arguments}, ensure_ascii=False)


def fence(raw, label="tool_call"):
    return f"```{label}\n{raw}\n```"


# REQ-111-040: nested literals, quote parity and malformed boundaries.
@pytest.mark.parametrize("args", [
    {"filePath": "a.py", "oldString": "x", "newString": "y"},
    {"data": {"items": [{"count": 3}]}},
    {"code": "if (x) { y(); }"},
    {"oldString": 'say "hi"'},
    {"path": "C:\\dir\\\\"},
    {"code": "한글 {중괄호} 보존"},
])
def test_balanced_scanner(args):
    raw = invocation(arguments=args)
    assert _scan_balanced_json("prefix " + raw + " suffix", 7) == (raw, 7 + len(raw))


@pytest.mark.parametrize("raw", ["", "{", '{"a": {"b": 1}', '{"a": "unfinished}', '{"a":"escape\\'])
def test_unbalanced_scanner(raw):
    assert _scan_balanced_json(raw, 0) is None


# REQ-111-041: all envelopes, alias keys and arrays share scanner boundaries.
@pytest.mark.parametrize("label", ["tool_call", "tool_code", "json", "function_call"])
def test_fences(provider, request_tools, label):
    calls, content = provider._parse_tool_response(fence(invocation(), label), request_tools)
    assert len(calls) == 1 and content is None
    assert json.loads(calls[0].function.arguments) == {"path": "a.py"}


@pytest.mark.parametrize("tag", ["tool_call", "function_call"])
def test_xml(provider, request_tools, tag):
    calls, content = provider._parse_tool_response(f"<{tag}>{invocation()}</{tag}>", request_tools)
    assert calls[0].function.name == "read" and content is None


@pytest.mark.parametrize("key", ["arguments", "parameters", "input"])
def test_bare_aliases(provider, request_tools, key):
    calls, content = provider._parse_tool_response(invocation(key=key), request_tools)
    assert len(calls) == 1 and content is None


@pytest.mark.parametrize("prefix,suffix", [
    ("<|channel|>commentary to=functions.read\n", ""),
    ("<|start|>assistant<|channel|>commentary to=functions.read<|message|>", "<|end|>"),
    ("<|channel|>commentary to=functions.read<|im_sep|>", "<|fim_suffix|>"),
])
def test_harmony(provider, request_tools, prefix, suffix):
    calls, content = provider._parse_tool_response(prefix + '{"path":"a.py"}' + suffix, request_tools)
    assert calls[0].function.name == "read" and content is None


@pytest.mark.parametrize("name,args", [
    ("edit", {"filePath": "a.py", "oldString": "x", "newString": "y"}),
    ("edit", {"filePath": "a.py", "oldString": 'say "hi"', "newString": "안녕하세요"}),
    ("nested", {"data": {"items": [{"count": 4}]}}),
    ("write", {"code": "if (x) { y(); }"}),
    ("read", {"path": "C:\\dir\\\\"}),
    ("read", {"path": "한글/파일.py"}),
])
def test_arguments_preserved(provider, request_tools, name, args):
    calls = provider._parse_tool_calls(fence(invocation(name, args)), request_tools)
    assert json.loads(calls[0].function.arguments) == args


@pytest.mark.parametrize("array", [False, True])
def test_three_parallel_calls(provider, request_tools, array):
    raws = [invocation(), invocation("write", {"code": "hi"}), invocation("bash", {"command": "pwd"})]
    text = fence("[" + ",".join(raws) + "]") if array else "\n".join(fence(raw) for raw in raws)
    calls, content = provider._parse_tool_response(text, request_tools)
    assert [call.function.name for call in calls] == ["read", "write", "bash"]
    assert content is None


def test_mixed_content(provider, request_tools):
    calls, content = provider._parse_tool_response("앞 설명\n" + fence(invocation()) + "\n뒤 설명", request_tools)
    assert len(calls) == 1 and content == "앞 설명\n\n뒤 설명"


# REQ-111-042/043: hallucinations and invalid schemas never execute or leak.
@pytest.mark.parametrize("wrap", [fence, lambda x: x, lambda x: f"<tool_call>{x}</tool_call>"])
def test_unknown_tool_redacted(provider, request_tools, wrap):
    calls, content = provider._parse_tool_response(wrap(invocation("destroy")), request_tools)
    assert calls is None and content is None


@pytest.mark.parametrize("name,args", [
    ("edit", {"filePath": "a.py"}),
    ("read", {"path": 123}),
    ("nested", {"data": {"items": [{"count": True}]}}),
    ("nested", {"data": {"items": [{}]}}),
    ("nested", {"data": {"items": [{"count": "3"}]}}),
    ("read", "not JSON"),
])
def test_schema_rejection(provider, request_tools, name, args):
    calls, content = provider._parse_tool_response(fence(invocation(name, args)), request_tools)
    assert calls is None and content is None


@pytest.mark.parametrize("text", [
    '{"name":"read","description":"example"}',
    '{"name":"read","arguments":42}',
    '```python\nexample = {"name":"read","arguments":{"path":"a.py"}}\n```',
    '`{"name":"read","arguments":{"path":"a.py"}}`',
    '{"example":{"name":"read","arguments":{"path":"a.py"}}}',
    '```json\n{"name":"ordinary data"}\n```',
])
def test_user_json_not_a_call(provider, request_tools, text):
    calls, content = provider._parse_tool_response(text, request_tools)
    assert calls is None and content == text


@pytest.mark.parametrize("text", ["", '{"name":"read","arguments":{', '{"name":"read","arguments":{"path":"unfinished}'])
def test_invalid_response(provider, request_tools, text):
    calls, _ = provider._parse_tool_response(text, request_tools)
    assert calls is None


def test_large_response(provider, request_tools):
    prefix = "설명 " * 35000
    calls, content = provider._parse_tool_response(prefix + fence(invocation()), request_tools)
    assert len(calls) == 1 and content == prefix.strip()


def test_string_arguments(provider, request_tools):
    args = {"path": "a.py"}
    calls = provider._parse_tool_calls(invocation(arguments=json.dumps(args)), request_tools)
    assert json.loads(calls[0].function.arguments) == args


@pytest.mark.parametrize("raw", [
    "{'name':'read','arguments':{'path':'한글.py'}}",
    '{"name":"read","arguments":{"path":"한글.py",},}',
    "{'name':'read','arguments':{'path':'한글.py',},}",
])
def test_recovery_logged(provider, request_tools, caplog, raw):
    calls, content = provider._parse_tool_response(fence(raw), request_tools)
    assert json.loads(calls[0].function.arguments) == {"path": "한글.py"}
    assert content is None and "recovery attempted" in caplog.text


def test_recovery_preserves_code(provider, request_tools):
    raw = '{"name":"write","arguments":{"code":"it\'s a literal ,} and ,]",},}'
    calls = provider._parse_tool_calls(fence(raw), request_tools)
    assert json.loads(calls[0].function.arguments) == {"code": "it's a literal ,} and ,]"}


@pytest.mark.parametrize("raw", [
    "{'name':'read','arguments':{}}",
    "{'name':'read','arguments':{'path':12}}",
    "{'name':'unknown','arguments':{'path':'a.py'}}",
])
def test_recovery_still_validated(provider, request_tools, raw):
    calls, content = provider._parse_tool_response(fence(raw), request_tools)
    assert calls is None and content is None


def test_fallback_priority(provider, request_tools):
    text = invocation("bash", {"command": "pwd"}) + fence(invocation())
    calls, content = provider._parse_tool_response(text, request_tools)
    assert [call.function.name for call in calls] == ["read"] and content is None


def test_fallback_after_invalid_stage(provider, request_tools):
    text = fence(invocation("unknown")) + "<tool_call>" + invocation() + "</tool_call>"
    calls, content = provider._parse_tool_response(text, request_tools)
    assert [call.function.name for call in calls] == ["read"] and content is None


def test_no_tools_no_parsing(provider):
    request = ChatCompletionRequest(model="test", messages=[])
    text = fence(invocation())
    with patch("providers.genai_provider._scan_balanced_json", side_effect=AssertionError("must not scan")):
        assert provider._parse_tool_response(text, request) == (None, text)


# REQ-111-044/045: independent IDs and history lookup preservation.
def test_unique_ids(provider, request_tools):
    ids = [provider._parse_tool_calls(fence(invocation()), request_tools)[0].id for _ in range(100)]
    assert len(set(ids)) == 100
    assert all(re.fullmatch(r"call_[0-9a-f]{24}", value) for value in ids)


def test_tool_result_name_mapping(provider):
    request = ChatCompletionRequest(model="test", messages=[
        {"role": "assistant", "tool_calls": [
            {"id": "first", "function": {"name": "read", "arguments": "{}"}},
            {"id": "second", "function": {"name": "write", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "second", "content": "written"},
        {"role": "tool", "tool_call_id": "first", "content": "read result"},
        {"role": "tool", "tool_call_id": "missing", "content": "unknown"},
    ])
    # REQ-111-045/060/063: compact in call order, pair reordered IDs, retain unknown results.
    contents = provider._transform_request(request)["contents"]
    assert len(contents) == 3
    nonces = set()
    bodies = []
    for item in contents:
        match = re.fullmatch(r"\[TOOL#([0-9a-f]+)\]\n(.*)", item, re.DOTALL)
        assert match is not None, item
        nonces.add(match.group(1))
        bodies.append(match.group(2))
    assert len(nonces) == 1
    assert bodies == [
        "Historical tool: read({}) -> read result",
        "Historical tool: write({}) -> written",
        "Unpaired tool result: unknown",
    ]


# REQ-111-042: fallback envelopes embedded in examples stay inert.
@pytest.mark.parametrize("text", [
    '```python\nexample = \'<tool_call>{"name":"read","arguments":{"path":"a.py"}}</tool_call>\'\n```',
    '`<|channel|>commentary to=functions.read {"path":"a.py"}`',
])
def test_embedded_envelopes_are_code(provider, request_tools, text):
    assert provider._parse_tool_response(text, request_tools) == (None, text)
