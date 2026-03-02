# REP v1.0.056 - Response 파싱 × Tool Call 에뮬레이션 검증 보고서

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.056 |
| 제목 | FSD v1.0.055 오류 9-10 (Response 파싱 불일치) × Tool Call 에뮬레이션 적용 검증 |
| 작성일 | 2026-03-02 |
| 관련 FSD | [FSD v1.0.055](../requirements/FSD_v1.0.055_genai-provider-endpoint-fix.md) — Endpoint URL 구조 수정 |
| 선행 REP | [REP v1.0.055](./REP_v1.0.055_genai-provider-endpoint-fix.md) — Endpoint URL 구조 수정 완료 보고서 |
| 검증 대상 | [genai_provider.py](../../../ai-proxy/providers/genai_provider.py) — Response 파싱 + Tool Call 에뮬레이션 |
| 참조 소스 | [genai_assistant.py](../../../src/genai_assistant.py) — 올바른 Response 파싱 원본 |

---

## 1. 검증 목적

FSD v1.0.055에서 식별된 **오류 9-10 (Response 파싱 불일치)**이 Tool Call 에뮬레이션(FSD v1.0.054) 코드 경로에서도 올바르게 적용되었는지 검증합니다.

### 1.1 오류 요약

| # | 오류 | 수정 전 | 수정 후 |
|---|------|---------|---------|
| 9 | 스트리밍 Response 파싱 | `{response, text, result}` 필드 검색 | SSE `event_status: CHUNK/DONE`, `content` 키 |
| 10 | 논스트리밍 Response 파싱 | `data.get("response", ...)` 체인 | `data.get("content", "")` |

### 1.2 검증 포인트

Tool Call 에뮬레이션은 **SCI Portal 응답 텍스트에서 `tool_call` 패턴을 파싱**하므로, 응답 텍스트가 올바르게 추출되지 않으면 Tool Call 파싱 자체가 실패합니다.

```
SCI Portal 응답 → [Response 파싱] → content 추출 → [Tool Call 파싱] → tool_calls 변환
                   ↑ 오류 9-10                        ↑ REQ-054-002
                   이 단계가 잘못되면              이 단계도 실패
```

---

## 2. 데이터 흐름 추적

Tool Call이 포함된 요청의 **전체 응답 파싱 흐름**을 `genai_provider.py` 라인 단위로 추적합니다.

### 2.1 논스트리밍 경로 (`chat()`)

```
① _transform_request() — L281
   OpenAI 형식 → GenAI API 형식 변환 (isStream: False)

② self.client.post(api_url, json=payload) — L288
   SCI Portal에 논스트리밍 요청 전송

③ data = resp.json() — L290
   SCI Portal JSON 응답 수신

④ content = data.get("content", "") — L294  ★ 오류 10 수정
   올바른 키("content")로 응답 텍스트 추출

⑤ tool_calls = self._parse_tool_calls(content) — L301
   content에서 ```tool_call``` 패턴 파싱 (REQ-054-002)

⑥ content = self._extract_non_tool_content(content) — L305
   tool_call 블록 제거한 순수 텍스트 분리 (REQ-054-009)

⑦ ChatCompletionResponse 반환 — L308-326
   content + tool_calls를 OpenAI 형식으로 반환
```

### 2.2 스트리밍 경로 (`stream()`)

```
① result = await self.chat(request) — L337
   내부적으로 chat() 호출 (버퍼링 방식)
   → 논스트리밍 경로(§2.1)와 동일한 파싱 수행

② msg = result.choices[0].message — L338
   이미 올바르게 파싱된 결과 사용

③ msg.tool_calls 확인 — L350
   tool_calls가 있으면 SSE 델타로 변환 (L352-370)

④ msg.content 확인 — L373, L392
   텍스트가 있으면 SSE content 청크로 변환
```

---

## 3. 항목별 검증

### 3.1 오류 10: 논스트리밍 Response 파싱 — ✅ 정상 적용

**`genai_provider.py` L294 vs `genai_assistant.py` L319:**

```python
# genai_provider.py (수정 후) — L294
content = data.get("content", "")      # ← 올바른 키 ✅

# genai_assistant.py (원본) — L319
content = result.get('content', '')    # ← 일치 ✅
```

이전의 잘못된 코드 `data.get("response", data.get("text", data.get("result", str(data))))` 는 **완전히 제거**되었습니다.

### 3.2 오류 9: 스트리밍 Response 파싱 — ✅ 정상 적용 (간접)

현재 `stream()`은 내부에서 `chat()`을 호출하여 **버퍼링 방식**으로 동작합니다:

- `stream()` L337: `result = await self.chat(request)`
- `chat()` L224: `"isStream": False` — 논스트리밍으로 SCI Portal에 요청
- 따라서 SSE 이벤트 파싱(`event_status: CHUNK/DONE`)은 현재 불필요
- `chat()` 내부에서 `data.get("content", "")`로 올바르게 파싱 후, `stream()`이 SSE 청크로 재변환

### 3.3 Tool Call 파싱 흐름의 `content` 키 사용 일관성 — ✅

```python
# L294: SCI Portal 응답에서 content 추출 (오류 10 수정)
content = data.get("content", "")         # ← 올바른 키 사용

# L301: 이 content를 tool_call 파싱에 전달
tool_calls = self._parse_tool_calls(content)     # ← content가 올바르므로 정상

# L305: tool_call 블록 제외한 텍스트 분리
content = self._extract_non_tool_content(content) # ← content가 올바르므로 정상
```

만약 이전의 잘못된 파싱(`data.get("response", ...)`)이 남아 있었다면, SCI Portal이 `content` 키로 응답을 보내므로 **빈 문자열이 반환**되어 Tool Call 파싱이 실패했을 것입니다.

---

## 4. 시나리오별 검증

| # | 시나리오 | SCI Portal `content` 값 | `_parse_tool_calls` | `_extract_non_tool_content` | 최종 OpenAI 응답 | 판정 |
|---|---------|------------------------|---------------------|-----------------------------|-----------------|:----:|
| 1 | 일반 텍스트 | `"안녕하세요"` | `None` | (호출 안 됨) | `content="안녕하세요", tool_calls=null, finish_reason="stop"` | ✅ |
| 2 | Tool Call만 | `` ```tool_call\n{"name":"write","arguments":{...}}\n``` `` | `[ToolCall(...)]` | `None` | `content=null, tool_calls=[{...}], finish_reason="tool_calls"` | ✅ |
| 3 | 혼합 응답 | `"파일을 작성합니다.\n```tool_call\n{...}\n```"` | `[ToolCall(...)]` | `"파일을 작성합니다."` | `content="파일을 작성합니다.", tool_calls=[{...}], finish_reason="tool_calls"` | ✅ |
| 4 | JSON 파싱 실패 | `` ```tool_call\n잘못된JSON\n``` `` | `None` (JSONDecodeError) | (호출 안 됨) | `content="```tool_call\n...\n```", tool_calls=null, finish_reason="stop"` | ✅ |
| 5 | 스트리밍 + Tool Call | (chat()으로 버퍼링) | `[ToolCall(...)]` | `None` | SSE 델타: `tool_calls[{index, id, function}]`, `finish_reason="tool_calls"` | ✅ |
| 6 | 스트리밍 + 일반 텍스트 | (chat()으로 버퍼링) | `None` | (호출 안 됨) | SSE 델타: `{content: "..."}`, `finish_reason="stop"` | ✅ |
| 7 | tools 없는 요청 | `"일반 응답"` | (request.tools 없으므로 호출 안 됨) | (호출 안 됨) | `content="일반 응답", tool_calls=null, finish_reason="stop"` | ✅ |

---

## 5. 핵심 코드 대비 (genai_assistant.py vs genai_provider.py)

### 5.1 논스트리밍 Response 파싱

| 항목 | `genai_assistant.py` | `genai_provider.py` | 일치 |
|------|---------------------|---------------------|:----:|
| 응답 키 | L319: `result.get('content', '')` | L294: `data.get("content", "")` | ✅ |
| usage 키 | — | L295: `data.get("usage", {})` | ✅ (추가) |

### 5.2 스트리밍 Response 파싱

| 항목 | `genai_assistant.py` | `genai_provider.py` | 일치 |
|------|---------------------|---------------------|:----:|
| SSE 파싱 | L285-293: `event_status` + `content` | L337: `chat()` 호출 (버퍼링) | ⚠️ 간접 적용 |
| 접근 방식 | `isStream: true` → SSE 직접 파싱 | `isStream: false` → 논스트리밍 수신 후 SSE 변환 | 동일 결과 |

> **참고:** `genai_provider.py`는 `isStream: False`로 논스트리밍 수신 후 OpenAI SSE로 재변환하므로, SSE 파싱 로직(`event_status: CHUNK/DONE`)은 현재 사용되지 않습니다. 향후 `isStream: True`로 전환 시 FSD §3.1 REQ-055-005의 `_collect_streaming_response()` 구현이 필요합니다.

### 5.3 Tool Call 파싱 패턴

| 항목 | `genai_assistant.py` | `genai_provider.py` | 비고 |
|------|---------------------|---------------------|------|
| 파싱 패턴 | `` ```tool_code``` `` | `` ```tool_call``` `` | 의도적 차이 (FSD v1.0.054 §2.2) |
| 키 이름 | `input` | `arguments` (폴백: `input`) | 호환성 유지 |
| 파싱 메서드 | `process_tool_calls()` L179-200 | `_parse_tool_calls()` L230-265 | 동일 패턴, 용어 차이 |

---

## 6. 최종 판정

| 오류 | 검증 대상 | 판정 | 근거 |
|------|----------|:----:|------|
| **오류 10** (논스트리밍 파싱) | `chat()` → Tool Call 파싱 흐름 | ✅ **통과** | L294: `data.get("content", "")` → L301: `_parse_tool_calls(content)` 정상 전달 |
| **오류 9** (스트리밍 파싱) | `stream()` → Tool Call 파싱 흐름 | ✅ **통과** | L337: `chat()` 내부 호출로 동일 파싱 경로 사용 |
| Tool Call 파싱 | `_parse_tool_calls()` | ✅ **통과** | 올바르게 추출된 `content`에서 `` ```tool_call``` `` 패턴 검색 |
| 혼합 응답 분리 | `_extract_non_tool_content()` | ✅ **통과** | tool_call 블록 제외 후 순수 텍스트 반환 |
| Graceful degradation | JSON 파싱 실패 시 | ✅ **통과** | JSONDecodeError 시 원본 텍스트 그대로 content 반환 |
| 하위 호환 | tools 없는 요청 | ✅ **통과** | `request.tools` 조건 분기로 기존 동작 유지 |

### 결론

> **✅ FSD v1.0.055 오류 9-10 (Response 파싱 불일치)이 Tool Call 에뮬레이션 코드 경로에 올바르게 적용되었습니다.**
>
> - 논스트리밍: `data.get("content", "")` → `_parse_tool_calls()` → 정상 동작
> - 스트리밍: `chat()` 버퍼링 방식으로 동일 경로 사용 → 정상 동작
> - 이전의 잘못된 `data.get("response", ...)` 코드는 완전히 제거됨

---

## 7. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1.0.056 | 2026-03-02 | 최초 작성: FSD v1.0.055 오류 9-10 × Tool Call 에뮬레이션 적용 검증 |
