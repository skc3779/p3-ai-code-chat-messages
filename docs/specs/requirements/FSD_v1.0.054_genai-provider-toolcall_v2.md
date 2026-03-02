# FSD v1.0.054 - GenAI Provider Tool Call 지원

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.054 |
| 제목 | GenAI Provider (SCI Portal) — Tool Call 프록시 레벨 에뮬레이션 |
| 작성일 | 2026-03-01 |
| 상태 | 구현 완료 |
| 선행 FSD | [FSD v1.0.053](./FSD_v1.0.053_openai-compatible-proxy-toolcall.md) — Tool Call 기능 추가 |
| 참조 SRS | [SRS v1.0.052 v2](../api-specs/SRS_v1.0.052_openai-compatible-provider_v2.md) |
| 참조 소스 | [genai_assistant.py](../../../src/genai_assistant.py) — 기존 프롬프트 기반 Tool Call 구현 |
| 구현 소스 | [genai_provider.py](../../../ai-proxy/providers/genai_provider.py) — 프록시 에뮬레이션 구현 |
| 테스트 | [test_toolcall.py](../../../ai-proxy/test_toolcall.py) — 통합 테스트 스크립트 |
| 참조 스펙 | [AI SDK OpenAI Compatible](https://sdk.vercel.ai/providers/openai-compatible-providers) |

---

## 1. 개요 (Overview)

FSD v1.0.053에서 GenAI Provider는 Tool Call 미지원으로 분류되었습니다 (REQ-053-008).
그러나 기존 `genai_assistant.py`에서는 **프롬프트 기반 Tool Call 에뮬레이션**을 이미 구현하고 있습니다.

본 문서는 이 접근법을 프록시 레벨에서 구현하여, OpenCode 등 클라이언트에서
GenAI Provider로도 Tool Call을 사용할 수 있도록 `genai_provider.py`를 개선하는 방안을 정의합니다.

### 1.1 핵심 과제

```
SCI Portal API는 네이티브 Tool Calling을 지원하지 않음
→ 프록시가 OpenAI tools 형식을 프롬프트 인젝션으로 변환하여 에뮬레이션
→ AI 응답에서 tool call 패턴을 파싱하여 OpenAI tool_calls 형식으로 반환
```

---

## 2. 배경 (Background)

### 2.1 현재 상태 (FSD v1.0.053)

FSD v1.0.053에서는 GenAI Provider에 tools 요청 시 에러를 반환하도록 구현되었습니다:

```python
# genai_provider.py — v1.0.053: tools 요청 시 에러 반환
# REQ-053-008
if request.tools:
    raise ProviderError("GenAI (SCI Portal) does not support tool calling.", status_code=400)
```

### 2.2 기존 구현 분석 (`genai_assistant.py`)

기존 프로젝트에서는 **프롬프트 기반 Tool Call**을 이미 성공적으로 사용 중입니다:

#### 방식 A: 시스템 프롬프트에 도구 정의 삽입

```python
# genai_assistant.py 시스템 프롬프트 (발췌)
"""
[필수] 파일 시스템 조작이 필요한 경우 제공된 도구(Tools)를 사용하세요.

```tool_code
{"name": "도구이름", "input": {"키": "값"}}
```

사용 가능한 도구:
1. 파일 시스템: read_file(path), write_file(path, content), ...
2. Git: git_status(), git_diff(), ...
"""
```

#### 방식 B: 응답에서 Tool Call 패턴 파싱

```python
# genai_assistant.py — 응답 파싱
def process_tool_calls(self, response: str) -> str:
    pattern = r'```tool_code\s*({.*?})\s*```'
    matches = re.findall(pattern, response, re.DOTALL)
    for match in matches:
        tool_call = json.loads(match)
        name = tool_call.get("name")
        input_data = tool_call.get("input", {})
        result = self._execute_tool(name, input_data)
```

#### 핵심 관찰

| 항목 | 기존 genai_assistant.py | 프록시 genai_provider.py |
|------|------------------------|------------------------|
| 도구 정의 | 시스템 프롬프트에 하드코딩 | ★ OpenAI `tools` → 프롬프트 자동 생성 |
| 파싱 패턴 | `` ```tool_code``` `` (input 키 사용) | ★ `` ```tool_call``` `` (arguments 키 사용) |
| 도구 호출 | AI가 `` ```tool_code``` `` 블록으로 응답 | ★ 동일 패턴을 파싱 → OpenAI `tool_calls` 변환 |
| 도구 실행 | 클라이언트(genai_assistant)에서 직접 실행 | ★ 클라이언트(OpenCode)에서 실행 |
| 결과 전달 | `[System Tool Results]`로 히스토리 추가 | ★ `tool` role 메시지 → 프롬프트에 삽입 |

---

## 3. 설계 (Design)

### 3.1 방안 검토

#### 방안 1: 프록시 레벨 프롬프트 에뮬레이션 (★ 선정)

```
OpenCode                    Proxy                     SCI Portal
───────                    ─────                     ──────────
tools: [{name,params}] ──→ 시스템 프롬프트에 삽입 ──→ API 호출
                           (도구 정의 텍스트 생성)
                      ←── ```tool_call``` 파싱 ←── 텍스트 응답
tool_calls: [{id,      ←   → OpenAI tool_calls 변환
  name, arguments}]
tool role msg       ────→ 프롬프트에 결과 삽입  ──→ API 호출
                           "[Tool Result] ..."
```

**장점:**
- SCI Portal API 변경 불필요
- 기존 genai_assistant.py에서 검증된 방식
- OpenCode 호환 (AI SDK tool_calls 형식)

**단점:**
- 100% 정확한 tool call 파싱이 보장되지 않음 (AI 응답 형식 의존)
- 프롬프트 토큰 추가 소비

#### 방안 2: Tool Call 미지원 유지 + 에러 반환

현재 FSD v1.0.053의 방식으로, tools 요청 시 에러를 반환.

**장점:** 단순함, 문제 없음
**단점:** GenAI Provider에서 OpenCode의 핵심 기능(파일 쓰기 등) 사용 불가

#### 결론

**방안 1** 채택. 기존 `genai_assistant.py`에서 검증된 프롬프트 기반 Tool Call을 프록시 레벨로 이식합니다.

### 3.2 상세 설계

#### 3.2.1 요청 변환: tools → 시스템 프롬프트 삽입

OpenAI `tools` 배열을 텍스트 형태의 도구 정의로 변환하여 시스템 프롬프트에 삽입합니다.

```
입력 (OpenAI tools):
───────────────────
tools: [{
  "type": "function",
  "function": {
    "name": "write",
    "description": "Write content to a file",
    "parameters": {
      "properties": {
        "filePath": {"type": "string", "description": "File path"},
        "content": {"type": "string", "description": "File content"}
      },
      "required": ["filePath", "content"]
    }
  }
}]

변환 후 (시스템 프롬프트에 추가):
──────────────────────────────────
[TOOLS AVAILABLE]
When you need to use a tool, respond with ONLY a tool call block in this EXACT format:

```tool_call
{"name": "tool_name", "arguments": {"key": "value"}}
```

Available tools:
1. write: Write content to a file
   Parameters: filePath (string, required) - File path, content (string, required) - File content

IMPORTANT RULES:
- When calling a tool, output ONLY the ```tool_call``` block, nothing else.
- The arguments value must be a valid JSON object.
- Do NOT wrap tool calls in any other format.
```

#### 3.2.2 응답 변환: 텍스트 → tool_calls

AI 응답에서 `` ```tool_call``` `` 패턴을 파싱하여 OpenAI `tool_calls` 형식으로 변환합니다.

```python
# 파싱 패턴 (genai_provider.py 실제 구현)
TOOL_CALL_PATTERN = re.compile(r'```tool_call\s*(\{.*?\})\s*```', re.DOTALL)

# 예시 AI 응답:
"""
```tool_call
{"name": "write", "arguments": {"filePath": "hello.md", "content": "hello world"}}
```
"""

# 변환 결과 (OpenAI tool_calls):
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,          # ★ tool_call 블록 이외 텍스트 없으면 null
      "tool_calls": [{
        "id": "genai-tc-1709312345-0",
        "type": "function",
        "function": {
          "name": "write",
          "arguments": "{\"filePath\":\"hello.md\",\"content\":\"hello world\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

> **구현 참고:** `_extract_non_tool_content()` 메서드가 tool_call 블록을 제거한 나머지 텍스트를 추출합니다. 텍스트와 tool_call이 혼합된 경우 `content`에 텍스트가, `tool_calls`에 도구 호출이 모두 포함됩니다.

#### 3.2.3 도구 결과 처리: tool role → 프롬프트 삽입

OpenCode가 도구 실행 결과를 `tool` role 메시지로 전송하면,
SCI Portal이 이해할 수 있는 텍스트 형태로 변환합니다.

```
입력 (OpenAI messages):
─────────────────────
{
  "role": "assistant",
  "content": null,
  "tool_calls": [{"id": "tc-1", "function": {"name": "write", "arguments": "..."}}]
},
{
  "role": "tool",
  "tool_call_id": "tc-1",
  "content": "File written successfully"
}

변환 후 (SCI Portal prompt 배열):
──────────────────────────────────
{
  "role": "assistant",
  "text": "[Tool Call] write({\"filePath\":\"hello.md\",\"content\":\"hello world\"})"
},
{
  "role": "user",
  "text": "[Tool Result for write]\nFile written successfully"
}
```

> **구현 참고:** tool_call_id를 기반으로 이전 assistant 메시지의 tool_calls에서 tool name을 자동 매칭합니다.

#### 3.2.4 tool_choice 처리

| OpenAI tool_choice | 프록시 동작 |
|---------------------|-----------|
| `"auto"` (기본) | 시스템 프롬프트에 도구 정의 삽입 + "필요할 때만 사용" |
| `"none"` | 도구 정의를 프롬프트에 삽입하지 않음 (빈 문자열 반환) |
| `"required"` | "You MUST use one of the tools above to respond." 추가 |
| `{"function":{"name":"x"}}` | "You MUST use the 'x' tool to respond." 추가 |

#### 3.2.5 스트리밍 처리

SCI Portal의 스트리밍 응답은 tool_call 패턴이 여러 청크에 걸쳐 분산될 수 있습니다.
따라서 **전체 응답을 `chat()`으로 수집한 후 SSE 청크로 재변환**하는 버퍼링 전략을 사용합니다.

```
스트리밍 흐름 (실제 구현):
───────────────────────────
클라이언트 stream 요청
  → genai_provider.stream()
    → chat() 호출 (SCI Portal에 논스트리밍으로 전체 응답 수신)
    → tool_call 파싱
    → tool_call 있음: OpenAI SSE tool_calls 델타 청크로 변환하여 전송
    → tool_call 없음: OpenAI SSE content 청크로 변환하여 전송
    → "data: [DONE]" 전송
```

> ⚠️ 이 방식은 스트리밍 응답이 즉시 전달되지 않고 전체 응답 수신 후 일괄 전달됩니다.
> 향후 SCI Portal이 네이티브 스트리밍 tool_call을 지원하면 실시간 전달로 개선 가능합니다.

### 3.3 SCI Portal API 형식 (실제 구현 기준)

| 항목 | 값 |
|------|-----|
| 엔드포인트 | `{ENDPOINT_URL}` (환경변수, 기본값: `https://scisportaldev.samsungif.net/rest/genAi`) |
| 인증 헤더 | `X-Client-Key` / `X-Client-Secret` |
| 요청 형식 | `{"model_id", "prompt": [{"role","text"}], "parameters": {"temperature","max_output_tokens"}}` |
| 응답 형식 | `{"response": "텍스트...", "usage": {...}}` |

> **참고:** `genai_assistant.py`(직접 호출)와 `genai_provider.py`(프록시)의 SCI Portal API 호출 형식에 차이가 있습니다:
>
> | 항목 | genai_assistant.py | genai_provider.py |
> |------|-------------------|-------------------|
> | 엔드포인트 | `{url}/openapi/chat/v1/messages` | `{ENDPOINT_URL}` (직접 POST) |
> | 인증 헤더 | `X-Lego-Client-Id` / `X-Lego-Client-Secret` | `X-Client-Key` / `X-Client-Secret` |
> | 요청 키 | `modelIds`, `contents`, `llmConfig`, `systemPrompt` | `model_id`, `prompt`, `parameters` |

### 3.4 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|---------|
| `ai-proxy/providers/genai_provider.py` | **대규모 수정** | Tool Call 에뮬레이션 로직 추가 (REQ-054-001~007) |
| `ai-proxy/test_toolcall.py` | **신규** | GenAI Tool Call 통합 테스트 스크립트 |
| `docs/specs/requirements/FSD_v1.0.053_*.md` | **참조 업데이트** | GenAI 상태를 "에뮬레이션 지원 (FSD v1.0.054)"으로 변경 |

---

## 4. 요구사항 (Requirements)

### 4.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-054-001 | OpenAI `tools` 배열을 시스템 프롬프트 텍스트로 변환하여 SCI Portal에 전달 | 필수 |
| REQ-054-002 | AI 응답에서 `` ```tool_call``` `` 패턴을 파싱하여 OpenAI `tool_calls` 형식으로 변환 | 필수 |
| REQ-054-003 | `tool` role 메시지를 텍스트 형태로 변환하여 SCI Portal 메시지에 삽입 | 필수 |
| REQ-054-004 | `tool_choice` 파라미터에 따라 프롬프트 지시문 조정 (`auto`/`none`/`required`/`{function}`) | 필수 |
| REQ-054-005 | 스트리밍 응답에서 tool_call 감지 시 OpenAI SSE tool_calls 델타로 변환 (버퍼링 방식) | 필수 |
| REQ-054-006 | `tools` 없는 기존 요청은 현재와 동일하게 동작 (하위 호환) | 필수 |
| REQ-054-007 | tool_call 파싱 실패 시 원본 텍스트를 그대로 `content`로 반환 (graceful degradation) | 권장 |
| REQ-054-008 | `assistant` 메시지에 `tool_calls`가 포함된 경우 `[Tool Call]` 텍스트로 변환 | 필수 |
| REQ-054-009 | tool_call 블록과 일반 텍스트가 혼합된 응답을 올바르게 분리 | 권장 |

### 4.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-054-001 | 프롬프트 에뮬레이션이므로 100% 신뢰성은 보장되지 않음을 인지 |
| NREQ-054-002 | 도구 정의 프롬프트 추가로 인한 토큰 증가를 최소화 (간결한 포맷) |
| NREQ-054-003 | 429 Too Many Requests 시 `BaseProvider._retry_on_429()` 지수 백오프 재시도 적용 |

---

## 5. 구현 계획 (Implementation Plan)

### 5.1 단계별 구현

| 단계 | 작업 | 구현 메서드 | 산출물 |
|------|------|-----------|--------|
| **Step 1** | tools → 시스템 프롬프트 텍스트 변환 | `_build_tools_prompt()` | `genai_provider.py` |
| **Step 2** | 요청 변환 — tools 프롬프트 삽입 + tool role 변환 | `_transform_request()` | `genai_provider.py` |
| **Step 3** | 응답에서 tool_call 패턴 파싱 | `_parse_tool_calls()` | `genai_provider.py` |
| **Step 4** | 텍스트/tool_call 혼합 응답 분리 | `_extract_non_tool_content()` | `genai_provider.py` |
| **Step 5** | chat() 개선 — tool_calls 응답 생성 | `chat()` | `genai_provider.py` |
| **Step 6** | stream() 개선 — 버퍼링 후 SSE 변환 | `stream()` | `genai_provider.py` |
| **Step 7** | 통합 테스트 | — | `test_toolcall.py` |

### 5.2 구현 우선순위

```
Step 1 (프롬프트) → Step 2 (요청변환) → Step 3 (파싱) → Step 4 (분리)
       ↓               ↓                ↓              ↓
   tools→텍스트      tool role→텍스트  ```tool_call```  content 분리
                                        패턴 파싱

→ Step 5 (chat) → Step 6 (stream) → Step 7 (테스트)
       ↓              ↓
   응답 변환      SSE 변환(버퍼링)
```

---

## 6. 핵심 구현 코드 (Implementation Reference)

### 6.1 tools → 시스템 프롬프트 변환

```python
def _build_tools_prompt(self, request: ChatCompletionRequest) -> str:
    """OpenAI tools 배열 → 시스템 프롬프트에 삽입할 도구 정의 텍스트 생성."""
    if not request.tools:
        return ""

    # tool_choice="none" 이면 도구 정의를 삽입하지 않음 (REQ-054-004)
    if request.tool_choice == "none":
        return ""

    lines = [
        "",
        "[TOOLS AVAILABLE]",
        "When you need to use a tool, respond with ONLY a tool call block in this EXACT format:",
        "",
        "```tool_call",
        '{"name": "tool_name", "arguments": {"key": "value"}}',
        "```",
        "",
        "Available tools:",
    ]

    for i, tool in enumerate(request.tools, 1):
        func = tool.function
        desc = func.description or ""
        lines.append(f"{i}. {func.name}: {desc}")

        # 파라미터 설명 생성 (description 포함)
        if func.parameters and func.parameters.get("properties"):
            props = func.parameters["properties"]
            required = func.parameters.get("required", [])
            param_parts = []
            for pname, pinfo in props.items():
                ptype = pinfo.get("type", "any")
                pdesc = pinfo.get("description", "")
                req_marker = ", required" if pname in required else ""
                part = f"{pname} ({ptype}{req_marker})"
                if pdesc:
                    part += f" - {pdesc}"
                param_parts.append(part)
            if param_parts:
                lines.append(f"   Parameters: {', '.join(param_parts)}")

    # tool_choice에 따른 지시문 (REQ-054-004)
    if request.tool_choice == "required":
        lines.append("")
        lines.append("You MUST use one of the tools above to respond.")
    elif isinstance(request.tool_choice, dict):
        fn = request.tool_choice.get("function", {}).get("name", "")
        if fn:
            lines.append("")
            lines.append(f"You MUST use the '{fn}' tool to respond.")

    lines.append("")
    lines.append("IMPORTANT RULES:")
    lines.append("- When calling a tool, output ONLY the ```tool_call``` block, nothing else.")
    lines.append("- The arguments value must be a valid JSON object.")
    lines.append("- Do NOT wrap tool calls in any other format.")

    return "\n".join(lines)
```

### 6.2 요청 변환 (tool role 처리 포함)

```python
def _transform_request(self, request: ChatCompletionRequest) -> dict:
    """OpenAI 형식 → SCI Portal 형식 변환. tools는 시스템 프롬프트에, tool role은 텍스트로."""
    prompt = []

    for m in request.messages:
        if m.role == "system":
            prompt.append({"role": "system", "text": m.content or ""})

        elif m.role == "assistant" and m.tool_calls:
            # ★ assistant + tool_calls → 텍스트 변환 (REQ-054-008)
            tool_text_parts = []
            if m.content:
                tool_text_parts.append(m.content)
            for tc in m.tool_calls:
                tool_text_parts.append(
                    f"[Tool Call] {tc.function.name}({tc.function.arguments})"
                )
            prompt.append({"role": "assistant", "text": "\n".join(tool_text_parts)})

        elif m.role == "tool":
            # ★ tool role → user 텍스트 변환 (REQ-054-003)
            tool_name = ""
            if m.tool_call_id:
                # 이전 assistant 메시지에서 해당 tool_call_id의 name을 역추적
                for prev in request.messages:
                    if prev.role == "assistant" and prev.tool_calls:
                        for tc in prev.tool_calls:
                            if tc.id == m.tool_call_id:
                                tool_name = tc.function.name
                                break
            prompt.append({
                "role": "user",
                "text": f"[Tool Result{' for ' + tool_name if tool_name else ''}]\n{m.content or ''}",
            })

        else:
            prompt.append({"role": m.role, "text": m.content or ""})

    # ★ tools → 시스템 프롬프트에 도구 정의 삽입 (REQ-054-001)
    tools_prompt = self._build_tools_prompt(request)
    if tools_prompt:
        system_found = False
        for p in prompt:
            if p["role"] == "system":
                p["text"] += tools_prompt
                system_found = True
                break
        if not system_found:
            prompt.insert(0, {"role": "system", "text": tools_prompt.strip()})

    return {
        "model_id": request.model,
        "prompt": prompt,
        "parameters": {
            "temperature": request.temperature if request.temperature is not None else 0.7,
            "max_output_tokens": request.max_tokens or 4096,
        },
    }
```

### 6.3 응답 파싱

```python
TOOL_CALL_PATTERN = re.compile(r'```tool_call\s*(\{.*?\})\s*```', re.DOTALL)

def _parse_tool_calls(self, text: str) -> list[ToolCall] | None:
    """응답 텍스트에서 ```tool_call``` 패턴을 파싱"""
    matches = TOOL_CALL_PATTERN.findall(text)
    if not matches:
        return None

    tool_calls = []
    for i, match in enumerate(matches):
        try:
            data = json.loads(match)
            name = data.get("name", "")
            # ★ arguments와 input 양쪽 모두 지원 (genai_assistant.py 호환)
            args = data.get("arguments", data.get("input", {}))

            # arguments가 이미 문자열이면 그대로, 아니면 JSON 직렬화
            if isinstance(args, str):
                args_str = args
            else:
                args_str = json.dumps(args, ensure_ascii=False)

            tool_calls.append(ToolCall(
                id=f"genai-tc-{int(time.time())}-{i}",
                type="function",
                function=FunctionCall(
                    name=name,
                    arguments=args_str,
                ),
            ))
        except json.JSONDecodeError:
            logger.warning(f"GenAI tool_call JSON 파싱 실패: {match[:100]}")
            continue

    return tool_calls if tool_calls else None

def _extract_non_tool_content(self, text: str) -> str | None:
    """tool_call 블록을 제거한 나머지 텍스트를 반환 (REQ-054-009)"""
    cleaned = TOOL_CALL_PATTERN.sub("", text).strip()
    return cleaned if cleaned else None
```

---

## 7. 테스트 계획 (Test Plan)

### 7.1 테스트 케이스

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-054-001 | tools 포함 요청 (GenAI, tool_choice=auto) | 시스템 프롬프트에 도구 정의 삽입, tool_calls 응답 반환 |
| TC-054-001b | tools 포함 요청 (GenAI, tool_choice=required) | "You MUST use" 지시문 포함, tool_calls 응답 반환 |
| TC-054-002 | tool role 메시지 포함 후속 요청 | `[Tool Result]` 텍스트로 변환되어 SCI Portal에 전달 |
| TC-054-003 | tool_call 패턴 없는 일반 텍스트 응답 | 기존과 동일 (content 반환, tool_calls=null) |
| TC-054-004 | tool_choice="none" | 도구 정의 미삽입, 일반 텍스트 응답 |
| TC-054-005 | tool_choice="required" | "반드시 도구 사용" 지시문 포함 |
| TC-054-006 | 스트리밍 tool_call 요청 | 버퍼링 후 SSE tool_calls 델타로 변환 + `[DONE]` |
| TC-054-007 | tools 없는 기존 요청 (하위 호환) | 기존과 동일 동작 (REQ-054-006) |
| TC-054-008 | 잘못된 tool_call JSON 패턴 (파싱 실패) | 원본 텍스트 그대로 content로 반환 (REQ-054-007) |
| TC-054-009 | 텍스트 + tool_call 혼합 응답 | content에 텍스트, tool_calls에 호출 정보 모두 포함 |

### 7.2 테스트 실행

```bash
# 프록시 서버 실행
cd ai-proxy
python proxy_server.py

# 별도 터미널에서 테스트 실행
python test_toolcall.py
```

### 7.3 Gemini 비교 테스트

GenAI 에뮬레이션 결과를 Gemini 네이티브 tool_call과 비교하여 호환성을 검증합니다.

---

## 8. 주의사항

| 항목 | 설명 |
|------|------|
| **에뮬레이션 한계** | SCI Portal API는 네이티브 Tool Calling을 지원하지 않으므로, AI가 프롬프트 지시를 따르지 않으면 tool_call이 실패할 수 있습니다. |
| **토큰 증가** | 도구 정의를 시스템 프롬프트에 삽입하므로 입력 토큰이 증가합니다. OpenCode의 도구 수가 많을 경우(10개+) 토큰 한도 초과에 주의해야 합니다. |
| **파싱 패턴 (tool_call vs tool_code)** | 기존 `genai_assistant.py`는 `` ```tool_code``` `` 패턴과 `input` 키를 사용합니다. 프록시에서는 `` ```tool_call``` `` 패턴과 `arguments` 키를 사용하되, 파싱 시 `input` 키도 폴백으로 지원합니다. |
| **arguments vs input** | OpenAI는 `arguments` 키를, `genai_assistant.py`는 `input` 키를 사용합니다. `_parse_tool_calls()`에서 `data.get("arguments", data.get("input", {}))` 로 양쪽 모두 지원합니다. |
| **arguments 직렬화** | OpenAI 표준은 `arguments`를 JSON **문자열**로 전달합니다. AI가 JSON **객체**로 응답한 경우 `json.dumps()`로 자동 변환합니다. |
| **스트리밍 지연** | 현재 구현은 `stream()` 내부에서 `chat()`을 호출하여 전체 응답을 받은 후 SSE 청크로 재변환합니다. 따라서 스트리밍 응답 시에도 첫 응답까지 지연이 발생합니다. |
| **429 재시도** | `BaseProvider._retry_on_429()` 지수 백오프가 `chat()` 내부에 적용되어 있습니다 (최대 3회, 2s/4s/8s). |
| **다중 tool_call** | 하나의 응답에 여러 `` ```tool_call``` `` 블록이 있을 수 있습니다. 모두 파싱하여 `tool_calls` 배열로 반환합니다. |
| **SCI Portal API 형식 차이** | `genai_assistant.py`와 `genai_provider.py`는 서로 다른 SCI Portal API 엔드포인트/인증 형식을 사용합니다 (§3.3 참고). |

---

## 9. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.054 v1 | 2026-03-01 | - | 최초 작성 |
| v1.0.054 v2 | 2026-03-02 | - | 문서 검토 및 개선: 실제 구현과 일치하도록 수정, SCI Portal API 형식 비교표 추가, 누락된 요구사항(REQ-054-008, REQ-054-009, NREQ-054-003) 보충, 테스트 케이스 보완, 인증 헤더/요청 형식 정정, 스트리밍 구현 방식(버퍼링) 명시 |
