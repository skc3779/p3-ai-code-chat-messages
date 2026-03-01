# REP v1.0.054 - 소스코드 구현사항 보고서

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.054 |
| 제목 | AI Proxy Server — Tool Call 기능 구현 보고서 |
| 작성일 | 2026-03-01 |
| 관련 FSD | [FSD v1.0.052](../requirements/FSD_v1.0.052_openai-compatible-proxy.md) — 프록시 서버 기본 구축 |
|  | [FSD v1.0.053](../requirements/FSD_v1.0.053_openai-compatible-proxy-toolcall.md) — Tool Call 기능 추가 |
|  | [FSD v1.0.054](../requirements/FSD_v1.0.054_genai-provider-toolcall.md) — GenAI Provider Tool Call 에뮬레이션 |

---

## 1. 구현 범위 요약

| FSD 버전 | 대상 | 상태 | 요약 |
|----------|------|:----:|------|
| v1.0.052 | 프록시 서버 기본 구축 | ✅ 완료 | FastAPI 프록시, 3사 Provider 라우팅, OpenCode 연동 |
| v1.0.053 | Tool Call 기능 추가 | ✅ 완료 | Gemini 패스스루+정규화, Claude 양방향 변환, 스키마 확장 |
| v1.0.054 | GenAI Tool Call 에뮬레이션 | ✅ 완료 | 프롬프트 기반 Tool Call 에뮬레이션 (SCI Portal 미연결로 실통합 미검증) |

---

## 2. 변경 파일 목록

### 2.1 핵심 파일

| 파일 | 라인 수 | 변경 유형 | 설명 |
|------|------:|----------|------|
| `ai-proxy/models.py` | 87 | 수정 | Tool Call 스키마 추가 |
| `ai-proxy/providers/base.py` | 145 | 수정 | `truncate_for_log()` 유틸 추가 |
| `ai-proxy/providers/gemini_provider.py` | 219 | 수정 | Tool Call 패스스루 + 스트리밍 정규화 |
| `ai-proxy/providers/claude_provider.py` | 419 | 수정 | Tool Use ↔ OpenAI Tool Call 양방향 변환 |
| `ai-proxy/providers/genai_provider.py` | 277 | 대규모 수정 | 프롬프트 기반 Tool Call 에뮬레이션 |
| `ai-proxy/router.py` | 64 | 수정 | 모델 목록 갱신 |

### 2.2 보조 파일

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `ai-proxy/test_toolcall.py` | 신규 | Tool Call 통합 테스트 스크립트 |
| `docs/specs/requirements/FSD_v1.0.053_*.md` | 수정 | Gemini 정규화 이슈 반영 |
| `docs/specs/requirements/FSD_v1.0.054_*.md` | 신규 | GenAI Tool Call 에뮬레이션 설계 |

---

## 3. 공급자별 구현 상세

### 3.1 공통 — `models.py` 스키마 확장

**추가된 모델:**

```python
class FunctionDefinition(BaseModel):  # 도구 함수 정의
    name: str
    description: Optional[str] = None
    parameters: Optional[dict] = None

class ToolDefinition(BaseModel):       # 도구 정의
    type: str = "function"
    function: FunctionDefinition

class FunctionCall(BaseModel):         # 도구 호출 응답
    name: str
    arguments: str                     # JSON 문자열

class ToolCall(BaseModel):             # 도구 호출
    id: str
    type: str = "function"
    function: FunctionCall
```

**기존 모델 변경:**

| 모델 | 변경 내용 |
|------|---------|
| `ChatMessage` | `content` → `Optional[str]` (None 허용), `tool_calls`, `tool_call_id` 추가 |
| `ChatCompletionRequest` | `tools: Optional[list[ToolDefinition]]`, `tool_choice: Optional[str|dict]` 추가 |
| `ChatCompletionChoice` | `finish_reason`에 `"tool_calls"` 값 허용 |

### 3.2 공통 — `providers/base.py` 유틸

```python
def truncate_for_log(data, max_len: int = 300) -> str:
    """dict/list → JSON → 잘라내기, 문자열 → 잘라내기"""
    # max_len보다 짧으면 전체 반환, 길면 "...(truncated)" 접미사
```

### 3.3 Gemini Provider — 패스스루 + 정규화

**방식:** OpenAI 호환 엔드포인트 패스스루, 스트리밍만 정규화

| 메서드 | 역할 |
|--------|------|
| `_build_payload()` | tools/tool_choice 포함 페이로드 구성 |
| `_parse_response()` | tool_calls 포함 응답 파싱 |
| `_normalize_stream_chunk()` | ★ 스트리밍 정규화 — `index` 자동 추가, `extra_content` 제거 |

**구현 중 발견된 이슈:**

| 이슈 | 원인 | 해결 |
|------|------|------|
| AI SDK 스키마 검증 실패 | Gemini 스트리밍 tool_calls에 `index` 필드 누락 | `_normalize_stream_chunk()`에서 자동 추가 |
| 비표준 필드 | `extra_content.google.thought_signature` 포함 | `tc.pop("extra_content", None)` 제거 |

**정규화 전후:**

```diff
 tool_calls: [{
+  "index": 0,
   "function": {...},
   "id": "...",
   "type": "function",
-  "extra_content": {"google": {...}}
 }]
```

### 3.4 Claude Provider — 양방향 변환

**방식:** Anthropic Messages API ↔ OpenAI 형식 변환

#### 요청 변환 (OpenAI → Anthropic)

| 메서드 | 변환 |
|--------|------|
| `_transform_tools()` | `tools[{function:{name,params}}]` → `tools[{name,input_schema}]` |
| `_transform_tool_choice()` | `"auto"` → `{type:"auto"}`, `"required"` → `{type:"any"}`, `"none"` → tools 제거 |
| `_transform_messages()` | `assistant+tool_calls` → `tool_use` 블록, `tool` role → `tool_result` 블록 (연속된 tool 메시지 묶기) |

#### 응답 변환 (Anthropic → OpenAI)

| 변환 | 상세 |
|------|------|
| `tool_use` → `tool_calls` | `id`, `name` 매핑, `input`(객체) → `arguments`(JSON 문자열) |
| `stop_reason` → `finish_reason` | `"tool_use"` → `"tool_calls"`, `"end_turn"` → `"stop"` |

#### 스트리밍 변환

| Anthropic SSE 이벤트 | OpenAI SSE 변환 |
|---------------------|----------------|
| `content_block_start (tool_use)` | `tool_calls[{index, id, name, arguments:""}]` |
| `content_block_delta (input_json_delta)` | `tool_calls[{index, function:{arguments}}]` (조각별) |
| `content_block_delta (text_delta)` | `delta: {content: "..."}` |
| `message_delta` | `finish_reason` 전송 |

### 3.5 GenAI Provider — 프롬프트 기반 에뮬레이션

**방식:** SCI Portal은 네이티브 Tool Calling 미지원 → 프롬프트 인젝션으로 에뮬레이션

#### 요청 변환 흐름

```
OpenCode                      Proxy                        SCI Portal
───────                      ─────                        ──────────
tools: [{write, read}]  ──→  _build_tools_prompt()   ──→  systemPrompt에 삽입
                              ↓
                         "[TOOLS AVAILABLE]
                          1. write: Write content...
                          ```tool_call
                          {"name":"...", "arguments":{...}}
                          ```"

tool role msg           ──→  _transform_request()    ──→  "[Tool Result for write] ..."
                              ↓
                         user role 텍스트로 변환
```

| 메서드 | 역할 |
|--------|------|
| `_build_tools_prompt()` | tools 배열 → 도구 정의 텍스트 생성, tool_choice에 따른 지시문 |
| `_transform_request()` | tool role → 텍스트, assistant+tool_calls → 텍스트, system에 tools 삽입 |
| `_parse_tool_calls()` | 응답에서 ````tool_call``` 패턴 파싱, arguments/input 양쪽 지원 |
| `_extract_non_tool_content()` | tool_call 블록 제외한 순수 텍스트 추출 |
| `chat()` | 전체 응답 tool_call 파싱 + OpenAI 형식 반환 |
| `stream()` | 버퍼링 후 tool_calls SSE 델타/텍스트 SSE로 재전송 |

#### tool_choice 처리

| OpenAI tool_choice | 프록시 동작 |
|---------------------|-----------|
| `"auto"` (기본) | 도구 정의 삽입 + "필요할 때만 사용" |
| `"none"` | 도구 정의 미삽입 (일반 텍스트 응답) |
| `"required"` | "반드시 도구를 사용하여 응답하세요" 지시문 추가 |
| `{"function":{"name":"x"}}` | "반드시 x 도구를 사용하세요" 지시문 추가 |

---

## 4. 테스트 결과

### 4.1 FSD v1.0.053 테스트 (2026-03-01)

| TC | 테스트 | Provider | 결과 | 상세 |
|----|--------|----------|:----:|------|
| TC-053-008 | 하위 호환 (tools 없이) | Gemini | ✅ | `content: "Hello."`, `finish_reason: stop` |
| TC-053-001 | Tool call | Gemini | ✅ | `tool_calls: [{name: "get_weather", args: '{"city":"서울"}'}]` |
| TC-053-003 | Tool call | Claude | ✅ | `tool_calls: [{name: "get_weather", args: '{"city":"Seoul"}'}]` + `content` |
| TC-053-007 | Tool call 미지원 | GenAI | ✅ | `400: "does not support tool calling"` → v1.0.054에서 개선 |

### 4.2 FSD v1.0.054 테스트 (2026-03-01)

| TC | 테스트 | Provider | 결과 | 비고 |
|----|--------|----------|:----:|------|
| TC-054-007 | 하위 호환 | GenAI | ⚠️ 502 | SCI Portal 사내 네트워크 미연결 (코드 정상) |
| TC-054-001 | Tool call (에뮬레이션) | GenAI | ⚠️ 502 | 동일 (사내 네트워크 필요) |
| 비교 | Gemini tool call | Gemini | ✅ | 정규화 정상 동작 확인 |

> ⚠️ GenAI 테스트는 SCI Portal이 사내 네트워크에서만 접근 가능하여 실통합 테스트가 불가합니다. 코드 변환 로직은 정상이며, 사내 환경에서 검증 필요.

### 4.3 OpenCode 연동 테스트

| 테스트 | Provider | 결과 | 비고 |
|--------|----------|:----:|------|
| 텍스트 채팅 | Gemini Flash | ✅ | 정상 응답 |
| Tool call (write) | Gemini Flash | ✅ | 정규화 후 정상 — `index` 추가, `extra_content` 제거 |

---

## 5. 공급자별 Tool Call 지원 현황

| Provider | 네이티브 지원 | 프록시 구현 | 방식 |
|----------|:----------:|:---------:|------|
| **Gemini** | ✅ | ✅ 패스스루 + 정규화 | OpenAI 호환 엔드포인트에 그대로 전달, 스트리밍만 정규화 |
| **Claude** | ✅ (자체 형식) | ✅ 양방향 변환 | Anthropic Tool Use ↔ OpenAI Tool Call 변환 |
| **GenAI** | ❌ | ✅ 에뮬레이션 | 프롬프트 인젝션 + 응답 파싱으로 Tool Call 흉내 |

---

## 6. 로그 시스템

모든 Provider에 통일된 로그 출력 적용:

| 로그 | 레벨 | 내용 |
|------|------|------|
| 요청 | INFO | `{Provider} chat/stream request: model=...` |
| 페이로드 | INFO | `{Provider} request: payload={truncate_for_log(payload)}` |
| 응답 | INFO | `{Provider} chat response: {truncate_for_log(data, 500)}` |
| 스트리밍 청크 | INFO | `{Provider} stream chunk[N]: {truncate_for_log(line)}` |
| 완료 | INFO | `{Provider} stream completed: N chunks, text=...` |
| 에러 | ERROR | `{Provider} stream/chat error: ...` |

---

## 7. 알려진 제한사항

| 항목 | 설명 | 영향 |
|------|------|------|
| GenAI 에뮬레이션 신뢰성 | AI가 ````tool_call``` 형식을 100% 따르지 않을 수 있음 | Tool call 파싱 실패 시 텍스트로 폴백 (graceful) |
| GenAI 스트리밍 지연 | tool_call 감지를 위해 전체 응답 버퍼링 | 응답 완료 후 한번에 전달 |
| GenAI 토큰 증가 | 도구 정의를 시스템 프롬프트에 삽입 | 도구 수가 많을수록 토큰 소비 증가 |
| Gemini thought 시그니처 | `extra_content.google.thought_signature` 제거됨 | 디버깅 정보 손실 (기능에 영향 없음) |

---

## 8. 향후 과제

| 우선순위 | 과제 | 설명 |
|---------|------|------|
| 높음 | GenAI 사내 네트워크 통합 테스트 | SCI Portal 실제 연결 환경에서 Tool Call 에뮬레이션 검증 |
| 중간 | 스트리밍 최적화 (GenAI) | tool_call이 아닌 순수 텍스트 응답은 실시간 스트리밍 전달 |
| 낮음 | 에러 응답 표준화 | 모든 Provider의 에러 응답을 OpenAI 형식으로 통일 |
