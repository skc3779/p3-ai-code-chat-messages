# REP v1.0.058 - GenAI Provider Tool Call 프록시 레벨 에뮬레이션 분석 보고서

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.058 |
| 제목 | GenAI Provider Tool Call 프록시 레벨 에뮬레이션 상세 분석 |
| 작성일 | 2026-03-02 |
| 분석 대상 | [genai_provider.py](../../../ai-proxy/providers/genai_provider.py) (449 Lines) |
| 관련 FSD | [FSD v1.0.054 v2](../requirements/FSD_v1.0.054_genai-provider-toolcall_v2.md) -- GenAI Provider Tool Call 에뮬레이션 |
| 관련 모델 | [models.py](../../../ai-proxy/models.py) -- Pydantic 스키마 |
| 관련 베이스 | [base.py](../../../ai-proxy/providers/base.py) -- BaseProvider 인터페이스 |

---

## 1. Tool Call 에뮬레이션이란?

### 1.1 배경: 왜 "에뮬레이션"이 필요한가?

OpenAI, Gemini, Claude 등 주요 AI API는 **네이티브 Tool Calling**을 지원합니다. 
이는 AI가 "이 도구를 호출하겠습니다"라고 구조화된 JSON 형태로 응답하는 기능입니다.

```
[ 네이티브 Tool Calling 지원 예시 ]

클라이언트 → API: "서울 날씨 알려줘" + tools: [get_weather]
API → 클라이언트: tool_calls: [{name: "get_weather", arguments: {"city": "서울"}}]
                   ↑ API가 자체적으로 구조화된 JSON으로 응답
```

그러나 **GenAI (Samsung SCI Portal)는 네이티브 Tool Calling을 지원하지 않습니다**.
SCI Portal은 순수 텍스트만 입력받고 순수 텍스트만 출력합니다.

```
[ GenAI (SCI Portal) - 네이티브 Tool Calling 미지원 ]

클라이언트 → SCI Portal: "서울 날씨 알려줘" + tools: [get_weather]
SCI Portal → 에러! (tools 해석 불가)
```

이 문제를 해결하기 위해 **프록시 서버가 중간에서 변환**을 수행합니다.
이것이 "Tool Call 프록시 레벨 에뮬레이션"입니다.

### 1.2 에뮬레이션의 핵심 아이디어

```
"도구 정의를 텍스트(자연어)로 변환하여 프롬프트에 삽입하고,
 AI의 텍스트 응답에서 패턴을 파싱하여 구조화된 tool_calls로 변환한다."
```

즉, AI에게 **"이런 도구가 있으니, 사용하고 싶으면 이런 형식으로 응답해"**라고 가르치는 방식입니다.

---

## 2. 전체 흐름 (Big Picture)

```
 ┌─────────────┐     ┌──────────────────────────┐     ┌─────────────┐
 │  클라이언트   │     │     AI Proxy Server       │     │  SCI Portal │
 │  (OpenCode)  │     │  (genai_provider.py)      │     │  (GenAI)    │
 └──────┬───────┘     └───────────┬────────────────┘     └──────┬──────┘
        │                        │                              │
   [1]  │  OpenAI 형식 요청       │                              │
        │  tools: [{write, read}] │                              │
        │ ──────────────────────>│                              │
        │                        │                              │
        │                   [2]  │  도구 정의를 텍스트로 변환      │
        │                        │  _build_tools_prompt()        │
        │                        │                              │
        │                   [3]  │  요청 형식 변환               │
        │                        │  _transform_request()        │
        │                        │                              │
        │                        │  SCI Portal 형식으로 전송     │
        │                        │ ───────────────────────────>│
        │                        │                              │
        │                        │  텍스트 응답 수신             │
        │                        │ <───────────────────────────│
        │                   [4]  │                              │
        │                        │  응답에서 tool_call 패턴 파싱  │
        │                        │  _parse_tool_calls()          │
        │                        │                              │
   [5]  │  OpenAI 형식 응답       │                              │
        │  tool_calls: [{...}]   │                              │
        │ <──────────────────────│                              │
        │                        │                              │
   [6]  │  도구 실행 후           │                              │
        │  tool role 결과 전송    │                              │
        │ ──────────────────────>│                              │
        │                   [7]  │  tool 결과를 텍스트로 변환     │
        │                        │  _transform_request()        │
        │                        │ ───────────────────────────>│
        │                        │                              │
        │                   [8]  │  최종 텍스트 응답              │
        │ <──────────────────────│ <───────────────────────────│
```

### 2.1 흐름 단계별 요약

| 단계 | 주체 | 동작 | 핵심 메서드 |
|:----:|------|------|-----------|
| 1 | 클라이언트 | OpenAI 형식으로 도구 정의 + 질문 전송 | -- |
| 2 | 프록시 | `tools` 배열 -> 텍스트 도구 정의 생성 | `_build_tools_prompt()` |
| 3 | 프록시 | OpenAI 형식 -> SCI Portal 형식 변환 | `_transform_request()` |
| 4 | 프록시 | 응답 텍스트에서 tool_call 패턴 파싱 | `_parse_tool_calls()` |
| 5 | 프록시 | OpenAI tool_calls 형식으로 클라이언트에 반환 | `chat()` |
| 6 | 클라이언트 | 도구 실행 후 결과를 `tool` role로 전송 | -- |
| 7 | 프록시 | tool role -> `[Tool Result]` 텍스트로 변환 | `_transform_request()` |
| 8 | 프록시 | 최종 AI 응답을 클라이언트에 반환 | `chat()` |

---

## 3. 메서드별 상세 분석

### 3.1 `_build_tools_prompt()` -- 도구 정의를 텍스트로 변환

**목적:** OpenAI의 구조화된 `tools` 배열을 AI가 이해할 수 있는 **자연어 텍스트**로 변환합니다.

**위치:** [genai_provider.py L104-165](../../../ai-proxy/providers/genai_provider.py)

#### 입력 (OpenAI tools 형식)

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "write",
        "description": "Write content to a file",
        "parameters": {
          "type": "object",
          "properties": {
            "filePath": {"type": "string", "description": "File path to write"},
            "content":  {"type": "string", "description": "File content"}
          },
          "required": ["filePath", "content"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "read",
        "description": "Read a file",
        "parameters": {
          "type": "object",
          "properties": {
            "filePath": {"type": "string", "description": "File path to read"}
          },
          "required": ["filePath"]
        }
      }
    }
  ]
}
```

#### 출력 (시스템 프롬프트에 삽입되는 텍스트)

```
[TOOLS AVAILABLE]
When you need to use a tool, respond with ONLY a tool call block in this EXACT format:

```tool_call
{"name": "tool_name", "arguments": {"key": "value"}}
```

Available tools:
1. write: Write content to a file
   Parameters: filePath (string, required) - File path to write, content (string, required) - File content
2. read: Read a file
   Parameters: filePath (string, required) - File path to read

IMPORTANT RULES:
- When calling a tool, output ONLY the ```tool_call``` block, nothing else.
- The arguments value must be a valid JSON object.
- Do NOT wrap tool calls in any other format.
```

#### 변환 과정 코드 분석

```python
def _build_tools_prompt(self, request: ChatCompletionRequest) -> str:
    # --- Guard 1: tools가 없으면 빈 문자열 반환 ---
    if not request.tools:          # tools=None 또는 []
        return ""

    # --- Guard 2: tool_choice="none"이면 도구를 사용하지 않겠다는 의미 ---
    if request.tool_choice == "none":
        return ""                  # 도구 정의를 프롬프트에 넣지 않음

    # --- 도구 형식 예시를 포함한 헤더 ---
    lines = [
        "",
        "[TOOLS AVAILABLE]",
        "When you need to use a tool, respond with ONLY a tool call block "
        "in this EXACT format:",
        "",
        "```tool_call",
        '{"name": "tool_name", "arguments": {"key": "value"}}',
        "```",
        "",
        "Available tools:",
    ]

    # --- 각 도구를 번호 매기며 나열 ---
    for i, tool in enumerate(request.tools, 1):
        func = tool.function
        desc = func.description or ""
        lines.append(f"{i}. {func.name}: {desc}")

        # 파라미터가 있으면 Properties를 순회하며 설명 생성
        if func.parameters and func.parameters.get("properties"):
            props = func.parameters["properties"]
            required = func.parameters.get("required", [])
            param_parts = []
            for pname, pinfo in props.items():
                ptype = pinfo.get("type", "any")      # string, number 등
                pdesc = pinfo.get("description", "")
                req_marker = ", required" if pname in required else ""
                part = f"{pname} ({ptype}{req_marker})"
                if pdesc:
                    part += f" - {pdesc}"
                param_parts.append(part)
            if param_parts:
                lines.append(f"   Parameters: {', '.join(param_parts)}")

    # --- tool_choice에 따른 추가 지시문 ---
    if request.tool_choice == "required":
        lines.append("")
        lines.append("You MUST use one of the tools above to respond.")
    elif isinstance(request.tool_choice, dict):
        fn = request.tool_choice.get("function", {}).get("name", "")
        if fn:
            lines.append("")
            lines.append(f"You MUST use the '{fn}' tool to respond.")

    # --- 필수 규칙 ---
    lines.append("")
    lines.append("IMPORTANT RULES:")
    lines.append("- When calling a tool, output ONLY the ```tool_call``` "
                  "block, nothing else.")
    lines.append("- The arguments value must be a valid JSON object.")
    lines.append("- Do NOT wrap tool calls in any other format.")

    return "\n".join(lines)
```

#### tool_choice 처리 상세

| `tool_choice` 값 | 프록시 동작 | AI에게 전달되는 지시 |
|------------------|-----------|-------------------|
| `"auto"` (기본) | 도구 정의 삽입 | "필요할 때 도구를 사용해라" (기본 지시) |
| `"none"` | **빈 문자열 반환** (도구 정의 미삽입) | AI는 도구의 존재를 모름 -> 순수 텍스트 응답 |
| `"required"` | 도구 정의 + 강제 지시 | "You MUST use one of the tools above to respond." |
| `{"function":{"name":"write"}}` | 도구 정의 + 특정 도구 강제 | "You MUST use the 'write' tool to respond." |

---

### 3.2 `_transform_request()` -- 요청 형식 전체 변환

**목적:** OpenAI 형식의 요청 전체를 SCI Portal이 이해하는 형식으로 변환합니다.

**위치:** [genai_provider.py L169-242](../../../ai-proxy/providers/genai_provider.py)

#### 변환 규칙 전체표

| OpenAI 입력 | SCI Portal 출력 | 변환 설명 |
|------------|----------------|----------|
| `messages[role="system"]` | `systemPrompt` (최상위 키) | system 메시지는 별도 최상위 키로 분리 |
| `messages[role="user"]` | `contents[]` 문자열 | `[User Context]\n내용` 형식 |
| `messages[role="assistant"]` | `contents[]` 문자열 | `[Assistant Context]\n내용` 형식 |
| `messages[role="assistant" + tool_calls]` | `contents[]` 문자열 | `[Assistant Context]\n[Tool Call] name(args)` 형식 |
| `messages[role="tool"]` | `contents[]` 문자열 | `[Tool Result for name]\n결과` 형식 |
| `model` | `modelIds` (배열) | 문자열 -> 단일 요소 배열 |
| `temperature` | `llmConfig.temperature` | LLM 설정 객체 내부 |
| `max_tokens` | `llmConfig.max_new_tokens` | 키 이름 변경 |
| `tools` | `systemPrompt`에 삽입 | `_build_tools_prompt()` 결과를 추가 |

#### 메시지 role별 변환 상세

##### (1) system 메시지 -> `systemPrompt`

```
OpenAI 입력:
  {"role": "system", "content": "당신은 개발 어시스턴트입니다."}

SCI Portal 출력:
  systemPrompt: "당신은 개발 어시스턴트입니다." + (도구 정의 텍스트)
```

system 메시지는 SCI Portal의 최상위 `systemPrompt` 키로 분리됩니다.
여기에 `_build_tools_prompt()`가 생성한 도구 정의 텍스트가 **추가 연결**됩니다.

##### (2) user 메시지 -> `contents[]` 문자열

```
OpenAI 입력:
  {"role": "user", "content": "hello.md 파일을 만들어줘"}

SCI Portal 출력 (contents 배열 요소):
  "[User Context]\nhello.md 파일을 만들어줘"
```

##### (3) assistant + tool_calls 메시지 -> `contents[]` 텍스트 변환 (REQ-054-008)

클라이언트가 다중 턴 대화에서 이전 AI의 tool_calls 응답을 다시 보내면, 
SCI Portal은 이를 이해할 수 없으므로 텍스트로 변환합니다.

```
OpenAI 입력:
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [{
      "id": "tc-1",
      "function": {
        "name": "write",
        "arguments": "{\"filePath\":\"hello.md\",\"content\":\"Hello World\"}"
      }
    }]
  }

SCI Portal 출력 (contents 배열 요소):
  "[Assistant Context]\n[Tool Call] write({\"filePath\":\"hello.md\",\"content\":\"Hello World\"})"
```

**변환 코드:**

```python
elif m.role == "assistant" and m.tool_calls:
    tool_text_parts = []
    if m.content_as_str():                    # content가 있으면 먼저 추가
        tool_text_parts.append(m.content_as_str())
    for tc in m.tool_calls:                   # 각 tool_call을 텍스트로 변환
        tool_text_parts.append(
            f"[Tool Call] {tc.function.name}({tc.function.arguments})"
        )
    contents.append(f"[Assistant Context]\n{chr(10).join(tool_text_parts)}")
```

##### (4) tool role 메시지 -> `contents[]` 텍스트 변환 (REQ-054-003)

클라이언트가 도구 실행 결과를 `tool` role로 보내면, 
이를 SCI Portal이 이해할 수 있는 텍스트로 변환합니다.

```
OpenAI 입력:
  {
    "role": "tool",
    "tool_call_id": "tc-1",
    "content": "File written successfully: hello.md"
  }

SCI Portal 출력 (contents 배열 요소):
  "[Tool Result for write]\nFile written successfully: hello.md"
```

**tool_call_id로 도구명 역추적:**

```python
elif m.role == "tool":
    tool_name = ""
    if m.tool_call_id:
        # 이전 메시지들을 순회하여 tool_call_id에 해당하는 도구명 찾기
        for prev in request.messages:
            if prev.role == "assistant" and prev.tool_calls:
                for tc in prev.tool_calls:
                    if tc.id == m.tool_call_id:
                        tool_name = tc.function.name  # "write"
                        break
    contents.append(
        f"[Tool Result{' for ' + tool_name if tool_name else ''}]\n{m.content_as_str()}"
    )
```

#### 최종 출력 형식

```python
return {
    "modelIds": ["gpt-oss-120B-medium"],   # 배열 형식
    "contents": [                           # 문자열 배열
        "[User Context]\nhello.md를 만들어줘",
        "[Assistant Context]\n[Tool Call] write({...})",
        "[Tool Result for write]\nFile written successfully",
    ],
    "llmConfig": {                          # LLM 설정 객체
        "max_new_tokens": 10240,
        "seed": None,
        "top_k": 14,
        "top_p": 0.94,
        "temperature": 0.4,
        "repetition_penalty": 1.04,
    },
    "isStream": False,
    "systemPrompt": "당신은 개발 어시스턴트입니다.\n[TOOLS AVAILABLE]\n..."
}
```

---

### 3.3 `_parse_tool_calls()` -- 응답에서 tool_call 패턴 파싱

**목적:** AI 응답 텍스트에서 `` ```tool_call``` `` 패턴을 찾아 OpenAI `tool_calls` 형식으로 변환합니다.

**위치:** [genai_provider.py L246-281](../../../ai-proxy/providers/genai_provider.py)

#### 정규식 패턴

```python
TOOL_CALL_PATTERN = re.compile(
    r'```tool_call\s*(\{.*?\})\s*```',
    re.DOTALL     # . 이 줄바꿈도 매칭하도록
)
```

이 패턴은 다음 구조를 감지합니다:

```
```tool_call
{"name": "write", "arguments": {"filePath": "hello.md", "content": "Hello"}}
```
```

#### 변환 과정

```
AI 텍스트 응답                    OpenAI tool_calls 형식
──────────────                   ─────────────────────

```tool_call                     {
{"name": "write",          →       "id": "genai-tc-1709312345-0",
 "arguments": {                    "type": "function",
   "filePath": "hello.md",        "function": {
   "content": "Hello"               "name": "write",
 }}                                  "arguments": "{\"filePath\":\"hello.md\",...}"
```                                }
                                 }
```

#### 상세 코드 분석

```python
def _parse_tool_calls(self, text: str) -> list[ToolCall] | None:
    # 1. 정규식으로 모든 ```tool_call``` 블록 찾기
    matches = TOOL_CALL_PATTERN.findall(text)
    if not matches:
        return None                  # ☆ 패턴이 없으면 None -> 일반 텍스트 응답

    tool_calls = []
    for i, match in enumerate(matches):
        try:
            # 2. JSON 파싱
            data = json.loads(match)
            name = data.get("name", "")

            # 3. arguments 추출 (호환성: "arguments" 또는 "input" 키 모두 지원)
            args = data.get("arguments", data.get("input", {}))
            #                ↑ OpenAI 표준      ↑ genai_assistant.py 방식

            # 4. arguments를 JSON 문자열로 변환 (OpenAI 표준)
            if isinstance(args, str):
                args_str = args            # 이미 문자열이면 그대로
            else:
                args_str = json.dumps(args, ensure_ascii=False)  # 객체 -> JSON 문자열

            # 5. OpenAI ToolCall 객체 생성
            tool_calls.append(ToolCall(
                id=f"genai-tc-{int(time.time())}-{i}",  # 고유 ID 생성
                type="function",
                function=FunctionCall(
                    name=name,
                    arguments=args_str,                   # JSON 문자열
                ),
            ))
        except json.JSONDecodeError:
            # 6. JSON 파싱 실패 -> 로그만 남기고 건너뜀 (graceful degradation)
            logger.warning(f"GenAI tool_call JSON 파싱 실패: {match[:100]}")
            continue

    return tool_calls if tool_calls else None
```

#### 핵심 포인트: `arguments` vs `input`

| 키 | 사용처 | 설명 |
|----|--------|------|
| `arguments` | OpenAI 표준, 프록시에서 도구 정의 시 사용 | 클라이언트가 기대하는 표준 형식 |
| `input` | `genai_assistant.py`의 기존 구현 | CLI 어시스턴트에서 사용하던 형식 |

프록시는 도구 정의에 `arguments` 키를 사용하지만, AI가 `input` 키로 응답할 수도 있으므로
**양쪽 모두 지원**합니다: `data.get("arguments", data.get("input", {}))`

#### 핵심 포인트: arguments 직렬화

OpenAI 표준에서 `arguments`는 **JSON 문자열**입니다 (객체가 아님).

```json
// OpenAI 표준 (JSON 문자열)
"arguments": "{\"filePath\":\"hello.md\",\"content\":\"Hello\"}"

// AI가 응답할 수 있는 형태 (JSON 객체)
"arguments": {"filePath": "hello.md", "content": "Hello"}
```

AI가 JSON 객체로 응답하면 `json.dumps()`로 문자열로 변환합니다.

---

### 3.4 `_extract_non_tool_content()` -- 혼합 응답 분리

**목적:** AI가 텍스트와 tool_call을 함께 응답한 경우, tool_call 블록을 제거한 순수 텍스트만 추출합니다.

**위치:** [genai_provider.py L283-286](../../../ai-proxy/providers/genai_provider.py)

```python
def _extract_non_tool_content(self, text: str) -> str | None:
    cleaned = TOOL_CALL_PATTERN.sub("", text).strip()   # tool_call 블록 제거
    return cleaned if cleaned else None                  # 빈 문자열이면 None
```

#### 예시

```
AI 응답 (혼합):
  "파일을 생성하겠습니다.
   ```tool_call
   {"name": "write", "arguments": {"filePath": "hello.md", "content": "Hello"}}
   ```
   위 파일이 생성됩니다."

분리 결과:
  content = "파일을 생성하겠습니다.\n   \n   위 파일이 생성됩니다."
  tool_calls = [{name: "write", arguments: {...}}]
```

---

### 3.5 `chat()` -- 모든 것을 조합하는 핵심 메서드

**목적:** 요청 변환 -> API 호출 -> 응답 파싱 -> OpenAI 형식 반환의 전 과정을 수행합니다.

**위치:** [genai_provider.py L290-354](../../../ai-proxy/providers/genai_provider.py)

#### 실행 흐름 다이어그램

```
chat(request)
│
├─[1] _transform_request(request)
│     └─ OpenAI messages → SCI Portal {modelIds, contents, systemPrompt, ...}
│        └─ assistant+tool_calls → "[Tool Call] name(args)" 텍스트
│        └─ tool role → "[Tool Result for name]\n결과" 텍스트
│        └─ tools → systemPrompt에 도구 정의 삽입
│
├─[2] sensitive_filter.mask_contents(payload["contents"])
│     └─ password, secret 등 민감 단어 치환
│
├─[3] sensitive_filter.mask_system_prompt(payload["systemPrompt"])
│     └─ systemPrompt 내 민감 단어 치환
│
├─[4] _retry_on_429(client.post(api_url, json=payload))
│     └─ SCI Portal API 호출 (429 재시도 포함, 최대 3회)
│
├─[5] data = resp.json()
│     └─ content = data.get("content", "")
│
├─[6] sensitive_filter.unmask(content)
│     └─ 민감 단어 복원
│
├─[7] tools가 있으면 → _parse_tool_calls(content)
│     ├─ tool_calls 감지됨:
│     │   ├─ finish_reason = "tool_calls"
│     │   └─ content = _extract_non_tool_content(content)  (혼합 응답 분리)
│     └─ tool_calls 없음:
│         └─ finish_reason = "stop"  (일반 텍스트 응답)
│
└─[8] ChatCompletionResponse 생성 및 반환
      └─ {id, model, choices: [{message: {role, content, tool_calls}, finish_reason}], usage}
```

#### 응답 형식 비교

| 상황 | `content` | `tool_calls` | `finish_reason` |
|------|-----------|--------------|-----------------|
| 일반 텍스트 응답 | "응답 텍스트" | `null` | `"stop"` |
| tool_call만 있는 응답 | `null` | `[{id, function}]` | `"tool_calls"` |
| 텍스트 + tool_call 혼합 | "텍스트 부분" | `[{id, function}]` | `"tool_calls"` |
| tools 없는 요청 | "응답 텍스트" | `null` | `"stop"` |

---

### 3.6 `stream()` -- 스트리밍 변환 (버퍼링 방식)

**목적:** 클라이언트가 스트리밍(`stream: true`)을 요청한 경우, OpenAI SSE 형식으로 응답합니다.

**위치:** [genai_provider.py L358-448](../../../ai-proxy/providers/genai_provider.py)

#### 핵심 전략: 버퍼링

```
일반적인 스트리밍:
  API 응답 청크 --즉시전달--> 클라이언트

GenAI 에뮬레이션 스트리밍 (버퍼링):
  SCI Portal 응답 --전체수신--> tool_call 파싱 --SSE 청크로 변환--> 클라이언트
```

tool_call 패턴이 여러 청크에 걸쳐 분산될 수 있으므로, 
**전체 응답을 `chat()`으로 수신한 후** SSE 청크로 재변환합니다.

#### SSE 출력 구조

```
[1] role 청크 (항상 첫 번째):
    data: {"choices": [{"delta": {"role": "assistant"}, "index": 0}]}

[2-A] tool_calls가 있는 경우:
    data: {"choices": [{"delta": {"tool_calls": [{
      "index": 0,
      "id": "genai-tc-...",
      "type": "function",
      "function": {"name": "write", "arguments": "{...}"}
    }]}, "index": 0}]}
    
    (혼합 응답이면 content 청크도 추가)
    data: {"choices": [{"delta": {"content": "텍스트 부분"}, "index": 0}]}
    
    data: {"choices": [{"delta": {}, "finish_reason": "tool_calls", "index": 0}]}

[2-B] 일반 텍스트 응답인 경우:
    data: {"choices": [{"delta": {"content": "전체 응답 텍스트"}, "index": 0}]}
    data: {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]}

[3] 종료 (항상 마지막):
    data: [DONE]
```

---

## 4. 다중 턴 대화 시나리오 (End-to-End)

실제 OpenCode에서 GenAI Provider로 파일 쓰기를 수행하는 시나리오를 단계별로 따라갑니다.

### 턴 1: 사용자 요청 + AI가 도구 호출

```
[클라이언트 → 프록시]
{
  "model": "genai/gpt-oss-120B-medium",
  "messages": [
    {"role": "system", "content": "You are a coding assistant."},
    {"role": "user", "content": "hello.md 파일을 만들어줘. 내용은 'Hello World!'"}
  ],
  "tools": [{
    "type": "function",
    "function": {
      "name": "write",
      "description": "Write content to a file",
      "parameters": {
        "properties": {
          "filePath": {"type": "string"},
          "content": {"type": "string"}
        },
        "required": ["filePath", "content"]
      }
    }
  }]
}

[프록시 → SCI Portal] (_transform_request 결과)
{
  "modelIds": ["gpt-oss-120B-medium"],
  "contents": [
    "[User Context]\nhello.md 파일을 만들어줘. 내용은 'Hello World!'"
  ],
  "systemPrompt": "You are a coding assistant.\n[TOOLS AVAILABLE]\n...(도구 정의)...",
  "llmConfig": {...},
  "isStream": false
}

[SCI Portal → 프록시] (텍스트 응답)
{
  "content": "```tool_call\n{\"name\": \"write\", \"arguments\": {\"filePath\": \"hello.md\", \"content\": \"Hello World!\"}}\n```"
}

[프록시 → 클라이언트] (_parse_tool_calls 결과)
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "genai-tc-1709312345-0",
        "type": "function",
        "function": {
          "name": "write",
          "arguments": "{\"filePath\":\"hello.md\",\"content\":\"Hello World!\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

### 턴 2: 클라이언트가 도구 실행 후 결과 전송 -> AI가 최종 응답

```
[클라이언트 → 프록시]
{
  "messages": [
    {"role": "system", "content": "You are a coding assistant."},
    {"role": "user", "content": "hello.md 파일을 만들어줘."},
    {"role": "assistant", "content": null, "tool_calls": [{
      "id": "genai-tc-1709312345-0",
      "function": {"name": "write", "arguments": "{...}"}
    }]},
    {"role": "tool", "tool_call_id": "genai-tc-1709312345-0",
     "content": "Successfully wrote 12 bytes to hello.md"}
  ],
  "tools": [...]
}

[프록시 → SCI Portal] (_transform_request 결과)
{
  "contents": [
    "[User Context]\nhello.md 파일을 만들어줘.",
    "[Assistant Context]\n[Tool Call] write({...})",
    "[Tool Result for write]\nSuccessfully wrote 12 bytes to hello.md"
  ],
  "systemPrompt": "You are a coding assistant.\n[TOOLS AVAILABLE]\n...",
  ...
}

[SCI Portal → 프록시]
{
  "content": "hello.md 파일이 성공적으로 생성되었습니다."
}

[프록시 → 클라이언트] (tool_call 패턴 없음 → 일반 텍스트)
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "hello.md 파일이 성공적으로 생성되었습니다.",
      "tool_calls": null
    },
    "finish_reason": "stop"
  }]
}
```

---

## 5. 데이터 모델 (Pydantic 스키마)

에뮬레이션에서 사용하는 핵심 데이터 모델들입니다.

```
ChatCompletionRequest (요청)
├── model: str                          "genai/gpt-oss-120B-medium"
├── messages: list[ChatMessage]
│   ├── role: str                       "system" | "user" | "assistant" | "tool"
│   ├── content: Optional[str|list]     메시지 내용 (tool_calls 시 null 가능)
│   ├── tool_calls: Optional[list]      assistant의 도구 호출 목록
│   └── tool_call_id: Optional[str]     tool role의 호출 ID
├── tools: Optional[list[ToolDefinition]]
│   └── function: FunctionDefinition
│       ├── name: str                   "write"
│       ├── description: Optional[str]  "Write content to a file"
│       └── parameters: Optional[dict]  JSON Schema
├── tool_choice: Optional[str|dict]     "auto" | "none" | "required" | {"function":{}}
└── stream: bool

ChatCompletionResponse (응답)
├── choices: list[ChatCompletionChoice]
│   ├── message: ChatMessage
│   │   ├── role: "assistant"
│   │   ├── content: Optional[str]      텍스트 응답 (tool_calls만이면 null)
│   │   └── tool_calls: Optional[list[ToolCall]]
│   │       ├── id: str                 "genai-tc-1709312345-0"
│   │       ├── type: "function"
│   │       └── function: FunctionCall
│   │           ├── name: str           "write"
│   │           └── arguments: str      JSON 문자열
│   └── finish_reason: str              "stop" | "tool_calls"
└── usage: Usage
```

---

## 6. 에뮬레이션 vs 네이티브 비교

### 6.1 3사 Provider 비교

| 항목 | Gemini | Claude | GenAI (에뮬레이션) |
|------|--------|--------|--------------------|
| Tool Call 지원 | 네이티브 | 네이티브 (자체 형식) | 에뮬레이션 |
| 프록시 변환 방식 | 패스스루 + 정규화 | 양방향 변환 | 프롬프트 인젝션 + 파싱 |
| tools 처리 | API에 그대로 전달 | `input_schema` 형식으로 변환 | 텍스트로 변환 -> systemPrompt에 삽입 |
| tool role 처리 | API에 그대로 전달 | `tool_result` content 블록으로 변환 | `[Tool Result]` 텍스트로 변환 |
| 응답 파싱 | API 응답 그대로 사용 | `tool_use` -> `tool_calls` 변환 | 텍스트에서 패턴 파싱 |
| 신뢰성 | 100% | 100% | AI 응답 형식에 의존 (비보장) |
| 스트리밍 | 실시간 | 실시간 | 버퍼링 후 일괄 전달 |

### 6.2 에뮬레이션의 장단점

| 장점 | 단점 |
|------|------|
| SCI Portal API 변경 없이 Tool Call 사용 가능 | AI가 형식을 100% 따르지 않을 수 있음 |
| 기존 genai_assistant.py에서 검증된 방식 | 도구 정의 삽입으로 토큰 소비 증가 |
| OpenCode 등 클라이언트와 완전 호환 | 스트리밍 지연 (버퍼링 필요) |
| 파싱 실패 시 텍스트로 폴백 (graceful) | 복잡한 도구 파라미터 설명이 제한적 |

---

## 7. 에러 처리 메커니즘

### 7.1 에러 처리 흐름

| 에러 유형 | 처리 방식 | 결과 |
|----------|---------|------|
| tool_call JSON 파싱 실패 | `logger.warning()` + `continue` | 해당 tool_call만 건너뜀 (다른 것은 정상 파싱) |
| 모든 tool_call 파싱 실패 | `_parse_tool_calls()` -> `None` | 원본 텍스트를 content로 반환 (일반 응답처럼 동작) |
| API 호출 에러 (5xx) | `ProviderError` 발생 | 클라이언트에 에러 전달 |
| 429 Too Many Requests | `_retry_on_429()` 지수 백오프 | 최대 3회 재시도 (2s, 4s, 8s) |
| 스트리밍 에러 | `_error_chunk()` SSE 에러 청크 | 클라이언트에 에러 + [DONE] 전달 |

### 7.2 Graceful Degradation (REQ-054-007)

```
AI 응답: "파일을 만들겠습니다. tool_call으로 실행합니다."
         (```tool_call``` 블록이 아닌 일반 텍스트에 "tool_call" 언급)

→ _parse_tool_calls() 결과: None (패턴 미매칭)
→ 일반 텍스트 응답으로 처리: content = "파일을 만들겠습니다. tool_call으로 실행합니다."
→ finish_reason = "stop"
```

도구 호출이 실패해도 사용자는 AI의 텍스트 응답을 여전히 받을 수 있습니다.

---

## 8. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1.0.058 | 2026-03-02 | 최초 작성: genai_provider.py Tool Call 에뮬레이션 상세 분석 |
