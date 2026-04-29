"""FSD v1.0.054 GenAI Tool Call 에뮬레이션 테스트"""
import httpx
import json

BASE = "http://localhost:8000"
HEADERS = {"Authorization": "Bearer ai-proxy-secret-key", "Content-Type": "application/json"}


def test(name, **kwargs):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    try:
        r = httpx.post(f"{BASE}/v1/chat/completions", headers=HEADERS, json=kwargs, timeout=60)
        print(f"  Status: {r.status_code}")
        d = r.json()
        if "error" in d or "detail" in d:
            print(f"  Error: {json.dumps(d, ensure_ascii=False)[:300]}")
        else:
            msg = d["choices"][0]["message"]
            print(f"  content: {str(msg.get('content', ''))[:200]}")
            print(f"  tool_calls: {msg.get('tool_calls')}")
            print(f"  finish_reason: {d['choices'][0].get('finish_reason')}")
    except Exception as e:
        print(f"  Exception: {e}")


def test_stream(name, **kwargs):
    """스트리밍 테스트 (TC-054-006)"""
    print(f"\n{'='*60}")
    print(f"  {name} [STREAM]")
    print(f"{'='*60}")
    kwargs["stream"] = True
    try:
        with httpx.stream("POST", f"{BASE}/v1/chat/completions", headers=HEADERS, json=kwargs, timeout=60) as r:
            print(f"  Status: {r.status_code}")
            for line in r.iter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        print(f"  [DONE]")
                        break
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    if "tool_calls" in delta:
                        tc = delta["tool_calls"][0]
                        print(f"  SSE tool_call: index={tc.get('index')} name={tc.get('function',{}).get('name','')}")
                    elif "content" in delta:
                        print(f"  SSE content: {str(delta['content'])[:100]}")
                    elif "role" in delta:
                        print(f"  SSE role: {delta['role']}")
                    elif chunk["choices"][0].get("finish_reason"):
                        print(f"  SSE finish_reason: {chunk['choices'][0]['finish_reason']}")
    except Exception as e:
        print(f"  Exception: {e}")


WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    },
}

WRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "write",
        "description": "Write content to a file",
        "parameters": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["filePath", "content"],
        },
    },
}

# TC-054-007: 하위 호환 (tools 없이)
test(
    "TC-054-007: GenAI 하위 호환 (tools 없이)",
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "Say hello"}],
)

# TC-054-001: GenAI tool call (에뮬레이션, tool_choice=auto)
test(
    "TC-054-001: GenAI tool call (tool_choice=auto)",
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "Get weather for Seoul"}],
    tools=[WEATHER_TOOL],
    tool_choice="auto",
)

# TC-054-001b: GenAI write tool call (tool_choice=required)
test(
    "TC-054-001b: GenAI write tool call (tool_choice=required)",
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "Write 'hello world' to hello.md file"}],
    tools=[WRITE_TOOL],
    tool_choice="required",
)

# TC-054-002: tool role 메시지 포함 후속 요청
test(
    "TC-054-002: tool role 후속 요청",
    model="genai/gpt-oss-120B-medium",
    messages=[
        {"role": "user", "content": "Get weather for Seoul"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "genai-tc-001",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"city": "Seoul"}'},
            }],
        },
        {
            "role": "tool",
            "tool_call_id": "genai-tc-001",
            "content": '{"temperature": 15, "condition": "sunny"}',
        },
    ],
    tools=[WEATHER_TOOL],
)

# TC-054-004: tool_choice="none" (도구 미삽입)
test(
    "TC-054-004: tool_choice=none",
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "Get weather for Seoul"}],
    tools=[WEATHER_TOOL],
    tool_choice="none",
)

# TC-054-006: 스트리밍 tool_call 요청
test_stream(
    "TC-054-006: 스트리밍 tool call",
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "Get weather for Seoul"}],
    tools=[WEATHER_TOOL],
    tool_choice="auto",
)

# Gemini 비교 테스트
test(
    "비교: Gemini tool call",
    model="gemini/gemini-3-pro-preview",
    messages=[{"role": "user", "content": "Get weather for Seoul"}],
    tools=[WEATHER_TOOL],
    tool_choice="auto",
)

print("\n" + "="*60)
print("  테스트 완료")
print("="*60)

