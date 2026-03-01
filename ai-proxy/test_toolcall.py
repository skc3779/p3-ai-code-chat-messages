"""FSD v1.0.053 Tool Call 테스트"""
import httpx
import json

BASE = "http://localhost:8000"
HEADERS = {"Authorization": "Bearer ai-proxy-secret-key", "Content-Type": "application/json"}


def test(name, **kwargs):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    try:
        r = httpx.post(f"{BASE}/v1/chat/completions", headers=HEADERS, json=kwargs, timeout=30)
        print(f"  Status: {r.status_code}")
        d = r.json()
        if "error" in d or "detail" in d:
            print(f"  Error: {json.dumps(d, ensure_ascii=False)[:200]}")
        else:
            msg = d["choices"][0]["message"]
            print(f"  content: {str(msg.get('content', ''))[:100]}")
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

# TC-053-008: 하위 호환 (tools 없는 기존 요청)
test(
    "TC-053-008: 하위 호환 (tools 없이)",
    model="gemini/gemini-3-pro-preview",
    messages=[{"role": "user", "content": "Say hello in one word"}],
)

# TC-053-001: Gemini tool call
test(
    "TC-053-001: Gemini tool call",
    model="gemini/gemini-3-pro-preview",
    messages=[{"role": "user", "content": "서울의 현재 날씨를 알려줘"}],
    tools=[WEATHER_TOOL],
    tool_choice="auto",
)

# TC-053-003: Claude tool call
test(
    "TC-053-003: Claude tool call",
    model="claude/claude-haiku-4-5",
    messages=[{"role": "user", "content": "서울의 현재 날씨를 알려줘"}],
    tools=[WEATHER_TOOL],
    tool_choice="auto",
)

# TC-053-007: GenAI tool call (미지원 → 에러)
test(
    "TC-053-007: GenAI tool call (미지원)",
    model="genai/gpt-oss-120B-medium",
    messages=[{"role": "user", "content": "서울의 현재 날씨"}],
    tools=[WEATHER_TOOL],
)

print("\n✅ 테스트 완료")
