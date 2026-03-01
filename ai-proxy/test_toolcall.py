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

# TC-054-001: GenAI tool call (에뮬레이션)
test(
    "TC-054-001: GenAI tool call (에뮬레이션)",
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "Get weather for Seoul"}],
    tools=[WEATHER_TOOL],
    tool_choice="auto",
)

# TC-054-001b: GenAI write tool call
test(
    "TC-054-001b: GenAI write tool call",
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "Write 'hello world' to hello.md file"}],
    tools=[WRITE_TOOL],
    tool_choice="required",
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
