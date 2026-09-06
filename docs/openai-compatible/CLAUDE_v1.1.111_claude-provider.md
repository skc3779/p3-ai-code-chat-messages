# CLAUDE v1.1.111 — `claude_provider.py` OpenAI-Compatible 적합성 분석

- **대상 소스**: `ai-proxy/providers/claude_provider.py` (416 lines)
- **연관 소스**: `ai-proxy/proxy_server.py`, `ai-proxy/models.py`, `ai-proxy/router.py`, `ai-proxy/providers/base.py`
- **기준 스펙**: OpenAI Chat Completions API + Anthropic Messages API (`anthropic-version: 2023-06-01`)
- **소비자(Consumer)**: `opencode` (Vercel AI SDK `@ai-sdk/openai-compatible`) — `opencode.json` 참조
- **작성일**: 2026-09-06
- **결론 요약**: **부분 호환 (Partially Compatible)**. Tool Use 왕복 변환은 구조적으로 올바르나, **메시지 시퀀스 정규화 부재 · SSE 스키마 결손 · prompt caching 미지원** 3가지가 opencode 에이전트 루프에서 실패를 유발한다.

---

## 1. 아키텍처 개요

Claude(Anthropic)는 OpenAI 호환 엔드포인트를 제공하지 않으므로, 본 Provider는 **전량 변환(full transformation)** 방식이다.

```text
opencode (OpenAI 형식)
   │  POST /v1/chat/completions  { model: "claude/claude-sonnet-4-6", messages, tools, stream }
   ↓
proxy_server.py  ── router.route_model() ──▶ ClaudeProvider + "claude-sonnet-4-6"
   ↓
ClaudeProvider._transform_request()
   ├─ _transform_messages()    : system 분리 / assistant.tool_calls → tool_use / tool → user+tool_result
   ├─ _transform_tools()       : function.parameters → input_schema
   └─ _transform_tool_choice() : auto|none|required|{function} → {type: auto|any|tool}
   ↓
POST https://api.anthropic.com/v1/messages   (x-api-key + anthropic-version)
   ↓
_parse_response() / stream()
   ├─ content[].text     → choices[0].message.content
   ├─ content[].tool_use → choices[0].message.tool_calls
   └─ stop_reason        → finish_reason
   ↓
opencode
```

---

## 2. 지원 스펙 (Support Matrix)

### 2.1 요청 파라미터

| OpenAI 필드 | 지원 | 변환 대상 | 구현 위치 | 비고 |
|---|:--:|---|---|---|
| `model` | O | `model` | `_transform_request` | 접두사 `claude/` 제거 후 전달 |
| `messages[].role=system` | △ | `system` (최상위) | `_transform_messages` | **다중 system 메시지 시 마지막 것만 생존** (§3.12) |
| `messages[].role=user` | O | `messages[]` | `_transform_messages` | |
| `messages[].role=assistant` | O | `messages[]` | `_transform_messages` | |
| `messages[].role=tool` | O | `user` + `tool_result` 블록 | `_transform_messages` | 연속 tool 메시지 1개로 병합 — **정확한 구현** |
| `messages[].content` (문자열) | O | `content` | `content_as_str()` | |
| `messages[].content` (parts 배열) | △ | 텍스트만 추출 | `models.ChatMessage.content_as_str` | **`image_url` → `[image_url]` 문자열로 소실** (§3.5) |
| `messages[].name` | X | — | — | 스키마 미정의, 조용히 드랍 |
| `stream` | O | `stream` | `stream()` | |
| `temperature` | O | `temperature` | `_transform_request` | |
| `max_tokens` | △ | `max_tokens` (Anthropic 필수) | `_transform_request` | 미지정 시 **4096 하드코딩** (§3.7) |
| `tools` | O | `tools[{name, description, input_schema}]` | `_transform_tools` | |
| `tool_choice` | O | `{type: auto\|any\|tool}` | `_transform_tool_choice` | `none` → tools 자체 미전송 (올바름) |
| `top_p` / `stop` / `n` / `seed` | X | — | — | `models.py` 스키마에 없어 **조용히 유실** |
| `response_format` (Structured Output) | X | — | — | |
| `stream_options.include_usage` | X | — | — | §3.9 |
| `parallel_tool_calls` | X | `disable_parallel_tool_use` | — | 미매핑 |
| `presence_penalty` / `frequency_penalty` | X | — | — | Anthropic 미지원 (정상) |

### 2.2 응답 필드 (비스트리밍)

| OpenAI 필드 | 지원 | 소스 | 비고 |
|---|:--:|---|---|
| `id` | O | `data.id` | Anthropic `msg_xxx` 형식 그대로 반환 |
| `object` | O | `"chat.completion"` (기본값) | |
| `created` | X | — | **`models.ChatCompletionResponse`에 필드 자체가 없음** |
| `model` | O | — | `proxy_server`에서 접두사 포함 원본 ID로 복원 |
| `choices[].message.content` | O | `content[].text` 연결 | |
| `choices[].message.tool_calls` | O | `content[].tool_use` | `arguments`를 JSON 문자열로 직렬화 — 올바름 |
| `choices[].finish_reason` | △ | `stop_reason` | `tool_use→tool_calls`, `end_turn→stop`만 매핑 (§3.4) |
| `usage.*` | O | `input_tokens` / `output_tokens` | 비스트리밍 전용 |

### 2.3 스트리밍 (SSE) 이벤트

| Anthropic 이벤트 | 처리 | OpenAI 델타 | 비고 |
|---|:--:|---|---|
| `message_start` | X | — | **`delta.role="assistant"` 초기 청크 미전송** (§3.3) |
| `content_block_start` (text) | X | — | 무시 (무해) |
| `content_block_start` (tool_use) | O | `tool_calls[{index,id,type,function.name}]` | |
| `content_block_delta` (text_delta) | O | `delta.content` | |
| `content_block_delta` (input_json_delta) | O | `tool_calls[{index, function.arguments}]` | |
| `content_block_stop` | X | — | 무시 (무해) |
| `message_delta` | △ | `finish_reason` | **동봉된 `usage.output_tokens` 폐기** (§3.9) |
| `message_stop` | X | — | |
| `error` (스트림 내 이벤트) | X | — | **스트림 중간 에러가 조용히 무시됨** (§3.6) |
| `ping` | X | — | 무시 (무해) |

**스트리밍 청크 공통 결손** — 모든 청크가 `{"choices":[{"delta":{...},"index":0}]}` 형태뿐이며 `id`, `object: "chat.completion.chunk"`, `created`, `model` 필드가 전부 없다.

---

## 3. 문제점 분석

심각도: **P0** = opencode 기능 파손 · **P1** = 신뢰성/비용 문제 · **P2** = 스펙 이탈/개선

### 3.0 문제점별 해결 현황 요약 (v1.1.111 검증 기준)

| 항목 ID | 심각도 | 문제점 요약 | 해결 여부 | 조치 근거 및 상태 요약 |
|---|:---:|---|:---:|---|
| **P0-C1** | P0 | 메시지 시퀀스 정규화 부재 (400 오류) | **해결됨** | `_normalize_anthropic_messages()` (빈 블록 제거, 동일 role 병합, 선두 user 주입) (REQ-111-040) |
| **P0-C2** | P0 | 에러 응답 비표준 래핑 (`detail` 객체) | **해결됨** | OpenAI 최상위 `error` 객체 및 문자열 에러 코드 통일 핸들러 도입 (REQ-111-011) |
| **P0-C3** | P0 | SSE 청크 스키마 결손 (`object` 부재 등) | **해결됨** | `BaseProvider._chunk()` 공통 헬퍼로 `object: "chat.completion.chunk"` 및 초기 role 방출 보장 (REQ-111-030, 031) |
| **P1-C4** | P1 | `finish_reason` 매핑 누락 (`max_tokens`) | **해결됨** | `STOP_REASON_MAP` 정규화 적용 (`max_tokens` → `length`, `end_turn` → `stop`) (REQ-111-041) |
| **P1-C5** | P1 | Vision(멀티모달) 완전 소실 | **해결됨** | `_transform_content_parts()`로 base64 data URL 및 image URL Anthropic 변환 지원 (REQ-111-042) |
| **P1-C6** | P1 | 스트림 오류 무시 및 스트리밍 재시도 부재 | **해결됨** | 인밴드 `error` 감지 및 첫 바이트 전 `anyio.sleep()` 지수 백오프 재시도 (429/500/529) (REQ-111-043, 044) |
| **P1-C7** | P1 | `max_tokens` 기본값 4096 하드코딩 불일치 | **해결됨** | `model_registry.py`의 `get_model_max_output()` 연동 (Claude 65536 적용) (REQ-111-045) |
| **P1-C8** | P1 | Prompt Caching 미지원 | **미해결 (보류)** | Anthropic `cache_control` 블록 주입 및 브레이크포인트 로직은 비용 최적화 후속 마일스톤 분리 |
| **P1-C9** | P1 | 스트리밍 usage 폐기 | **해결됨** | `stream_options.include_usage` 지원 및 스트림 종결 시 usage 청크 방출 (REQ-111-033, 048) |
| **P2-C10** | P2 | API 키 평문 로깅 (보안) | **해결됨** | `authorization` 및 정답 키 평문 로깅 완전 삭제, `hmac.compare_digest`, `_scrub_secrets` 적용 (REQ-111-012, 020) |
| **P2-C11** | P2 | 전체 페이로드 로깅 과적 | **해결됨** | `DEFAULT_LOG_MAX_LEN=2000` 축소, `LOG_PAYLOAD=1` 환경변수 게이팅, `_scrub_secrets` 적용 (REQ-111-014) |
| **P2-C12** | P2 | 기타 (AsyncClient 미종료, models created 부재 등) | **해결됨** | lifespan `aclose()` 클라이언트 정리, `created` 타임스탬프 추가, `SUPPORTED_MODELS` 중복 제거 완료 |

---

### P0-C1. 메시지 시퀀스 정규화 부재 → Anthropic 400 오류
- **해결 여부**: **해결됨**
- **조치 내용**: `_normalize_anthropic_messages()` 정규화 함수 도입 (REQ-111-040, TASK-CLAUDE-1). (a) 빈 문자열/빈 블록 메시지 제거(단, tool_use/tool_result 메시지는 보존), (b) 연속 동일 role 메시지 content 블록 병합, (c) 선두가 assistant면 더미 user 주입, (d) 마지막 assistant 프리필 허용 및 후행 공백 정제 완료.

`_transform_messages()` (`claude_provider.py:110-176`)는 OpenAI 메시지를 **1:1로 그대로 옮긴다**. 그러나 Anthropic Messages API는 다음을 강제한다.

1. 첫 메시지는 `user` 여야 한다.
2. `user`/`assistant`가 **교대**해야 한다 (연속 동일 role 금지).
3. `text` 블록은 **비어 있을 수 없다** (`text content blocks must be non-empty`).

opencode는 (a) 툴 실행 후 assistant 메시지를 연속으로 쌓고, (b) `tool_calls`만 있고 `content`가 `""`인 assistant 메시지를 흔히 생성한다. 이 경우 프록시는 다음을 그대로 전송한다.

```json
{"role": "assistant", "content": ""}
```

Anthropic이 `400 invalid_request_error`를 반환하면 `_retry_on_429`는 429가 아니므로 즉시 `ProviderError(400)`로 종결된다. **에이전트 루프가 중단된다.**

### P0-C2. 에러 응답이 OpenAI 스펙과 다른 형태로 래핑됨
- **해결 여부**: **해결됨**
- **조치 내용**: `proxy_server.py`에 `RequestValidationError` 및 `HTTPException` 전역 핸들러 구현 (REQ-111-011, TASK-CORE-3). 최상위 `error` 객체(`message`, `type`, `code`)로 통일하고 `STATUS_CODE_TO_ERROR_CODE`를 통해 `code`를 표준 문자열로 정규화.

`proxy_server.py:129-140`은 `HTTPException(detail=ErrorResponse(...).model_dump())`를 사용한다. FastAPI는 이를 다음으로 직렬화한다.

```json
{ "detail": { "error": { "message": "...", "type": "proxy_error", "code": 400 } } }
```

OpenAI 스펙은 **최상위 `error` 키**를 요구한다.

```json
{ "error": { "message": "...", "type": "...", "code": "..." } }
```

`@ai-sdk/openai-compatible`의 에러 파서는 최상위 `error`를 찾으므로, opencode 화면에는 원인 메시지 대신 무의미한 일반 오류만 표시된다. 또한 `code`가 OpenAI에서는 **문자열**인데 여기서는 정수다.

### P0-C3. SSE 청크 스키마 결손
- **해결 여부**: **해결됨**
- **조치 내용**: `BaseProvider._chunk()` 공통 헬퍼 도입으로 모든 청크에 `id`, `object: "chat.completion.chunk"`, `created`, `model` 필드 보장 (REQ-111-030). 스트림 시작 시 `delta={"role": "assistant"}` 초기 청크 1회 방출 보장 (REQ-111-031).

`stream()`이 만드는 모든 청크에 `object: "chat.completion.chunk"`가 없다. 관대한 파서에서는 통과하지만, `chunk.id`로 메시지를 상관(correlate)하는 클라이언트나 엄격한 검증 계층에서는 스트림이 통째로 버려진다. 또한 `delta.role="assistant"` 초기 청크가 없어 일부 클라이언트가 assistant 메시지를 시작하지 못한다.

> 동일 프로젝트의 `genai_provider.stream()`은 role 청크를 보낸다 → **Provider 간 SSE 동작 불일치**.

### P1-C4. `finish_reason` 매핑 누락 — `max_tokens` 그대로 통과
- **해결 여부**: **해결됨**
- **조치 내용**: `STOP_REASON_MAP` 정규화 도입 (REQ-111-041). `max_tokens` → `length`, `end_turn`/`stop_sequence`/`refusal` → `stop`, `tool_use` → `tool_calls`로 OpenAI 규격 매핑.

`_parse_response()` (`claude_provider.py:216-222`) 및 `stream()` (`claude_provider.py:374-380`)은 `tool_use` / `end_turn`만 변환하고 나머지는 원본을 통과시킨다.

| Anthropic `stop_reason` | 현재 출력 | OpenAI 정답 |
|---|---|---|
| `end_turn` | `stop` | `stop` (정상) |
| `tool_use` | `tool_calls` | `tool_calls` (정상) |
| `max_tokens` | **`max_tokens`** | `length` |
| `stop_sequence` | **`stop_sequence`** | `stop` |
| `refusal` / `pause_turn` | 원본 통과 | `stop` |

opencode는 `length`를 보고 "출력이 잘렸으니 이어쓰기"를 판단한다. `max_tokens`라는 미지의 값을 받으면 **잘린 코드를 완성된 것으로 오인**해 파일에 그대로 쓴다.

### P1-C5. Vision(멀티모달) 완전 소실
- **해결 여부**: **해결됨**
- **조치 내용**: `_transform_content_parts()` 구현 (REQ-111-042). OpenAI `image_url` data URL(base64) 및 remote URL을 Anthropic `image` 블록(`source.type="base64"` / `"url"`)으로 변환 처리.

`content_as_str()` (`models.py:56-83`)은 `image_url` 파트를 문자열 `"[image_url]"`로 치환한다. Claude는 이미지 입력을 지원하지만 프록시가 원천 차단한다. opencode의 스크린샷 첨부 기능이 무의미해진다.

### P1-C6. 스트림 중 오류 무시 / 스트리밍 재시도 부재
- **해결 여부**: **해결됨**
- **조치 내용**: 스트림 인밴드 `event_type == "error"` 감지 시 `_error_chunk` 방출 (REQ-111-043). 첫 바이트 수신 전 HTTP 429/500/529 및 ConnectError에 대해 `anyio.sleep()` 기반 최대 3회 지수 백오프 재시도 구현 (REQ-111-044, TASK-CLAUDE-1).

Anthropic은 스트림 도중 `{"type":"error","error":{...}}` 이벤트를 보낼 수 있다(overloaded 등). 현재 `stream()`의 `event_type` 분기에 `error`가 없어 **조용히 무시**되고, 클라이언트는 잘린 응답을 정상으로 받는다. HTTP **529 (Overloaded)** 역시 `_retry_on_429`의 대상이 아니며, 스트리밍 경로에는 재시도 자체가 없다.

### P1-C7. `max_tokens` 기본값 4096 하드코딩 ↔ `opencode.json` 선언 불일치
- **해결 여부**: **해결됨**
- **조치 내용**: `model_registry.py`의 `get_model_max_output()` 연동으로 단일 진실 소스 메타데이터 상한(Claude 65536)을 참조 적용 (REQ-111-045).

`opencode.json`은 `claude/claude-sonnet-4-6`의 `limit.output`을 **65536**으로 선언한다. 그러나 프록시는 클라이언트가 `max_tokens`를 생략하면 무조건 4096을 넣는다. 대형 파일 생성 시 출력이 조용히 잘리고, P1-C4와 결합되어 **잘림이 감지조차 되지 않는다**.

### P1-C8. Prompt Caching 미지원 → 에이전트 루프 비용 폭증
- **해결 여부**: **미해결 (보류)**
- **사유**: Anthropic `cache_control: {"type": "ephemeral"}` 블록 주입 및 캐시 브레이크포인트 로직은 비용 최적화 후속 마일스톤으로 분리.

Anthropic `cache_control: {"type": "ephemeral"}` 블록을 전혀 사용하지 않는다. opencode 에이전트는 매 턴 **전체 대화 + 전체 툴 정의**를 재전송하므로, 20턴 루프에서 동일 시스템 프롬프트를 20번 과금한다. `usage`의 `cache_creation_input_tokens` / `cache_read_input_tokens`도 집계되지 않는다.

### P1-C9. 스트리밍 usage 폐기
- **해결 여부**: **해결됨**
- **조치 내용**: `stream_options.include_usage` 지원 (REQ-111-001). `message_delta` 수신 시 usage를 집계하고 스트림 마지막에 OpenAI 규격 usage 청크 방출 구현 (REQ-111-033, REQ-111-048).

`message_delta` 이벤트에는 `usage.output_tokens`가 들어 있으나 `stream()`은 `stop_reason`만 읽고 버린다. `stream_options.include_usage`도 스키마에 없다. **스트리밍 모드에서 토큰/비용 계측이 전면 불가**하다.

### P2-C10. API 키 평문 로깅 (보안)
- **해결 여부**: **해결됨**
- **조치 내용**: `proxy_server.py`에서 `authorization` 및 `Expected: Bearer` 평문 로그 완전 삭제, `hmac.compare_digest` 도입, `_scrub_secrets` 및 `public_message` 도입으로 민감정보 유출 차단 (REQ-111-012, REQ-111-020, TASK-CORE-3).

```python
# proxy_server.py
logger.info(f"/v1/chat/completions authorization: {authorization}")   # 매 요청 클라이언트 토큰 기록
logger.error(f"Expected: Bearer {PROXY_API_KEY}")                     # 서버 정답 키 자체를 기록
```

인증 실패 시 **서버의 정답 키를 로그에 남긴다**. 저장소에 `logs/` 디렉터리가 실재하므로 유출 경로가 존재한다. 또한 `authorization != f"Bearer {PROXY_API_KEY}"`는 타이밍 세이프 비교가 아니다.

### P2-C11. 전체 페이로드 로깅
- **해결 여부**: **해결됨**
- **조치 내용**: `DEFAULT_LOG_MAX_LEN=2000` 축소, `LOG_PAYLOAD=1` 환경변수 게이팅(`should_log_payload()`), `_scrub_secrets` 마스킹 적용 (REQ-111-014, TASK-CORE-3, TASK-CLAUDE-1).

`stream()`은 `truncate_for_log(payload)`를 기본 한도(`DEFAULT_LOG_MAX_LEN = 100000`)로 호출한다. 매 요청 대화 전문 최대 100KB가 `sort_keys=True`로 재직렬화되어 기록된다. CPU·디스크·기밀성 모두에 부담이다.

### P2-C12. 기타
- **해결 여부**: **해결됨 (일부 후속 마일스톤 보류)**
- **조치 내용**:
  - **`AsyncClient` 미종료 [해결됨]**: FastAPI lifespan 컨텍스트 매니저 도입 및 `BaseProvider.aclose()`로 클라이언트 정상 종료 보장 (REQ-111-013).
  - **`/v1/models` 응답 `created` 부재 [해결됨]**: 정수 epoch 타임스탬프 추가 완료 (REQ-111-015).
  - **`router.SUPPORTED_MODELS` 키 중복 [해결됨]**: `model_registry.py` 분리 및 중복 제거 완료 (REQ-111-046, REQ-111-047).
  - **`system` 다중 메시지 [해결됨]**: `_normalize_anthropic_messages` 및 정규화로 병합/단일화 처리.
  - **`tool_result.is_error` [해결됨]**: Anthropic tool_result 블록 생성 시 error 플래그 반영.
  - **Extended Thinking [미해결 (보류)]**: thinking 파라미터 및 델타는 후속 릴리스로 분리.

- **`AsyncClient` 미종료**: `__init__`에서 생성한 httpx 클라이언트를 FastAPI lifespan에서 닫지 않는다.
- **`system` 다중 메시지 덮어쓰기**: `system_msg = m.content_as_str()`(단순 대입). 동일 프로젝트 `genai_provider`는 `+=`(누적) → 동작 불일치.
- **`tool_result.is_error` 미지원**: 툴 실행 실패를 모델에 구조적으로 알릴 수 없다.
- **Extended Thinking 미지원**: `thinking` 파라미터 / `thinking_delta` 이벤트 미처리.
- **`/v1/models` 응답에 `created` 없음**, 비표준 `name` 키 포함.
- **`router.SUPPORTED_MODELS`에 `genai/gpt-oss-120B-medium` 키 중복** (dict이므로 1개 무시).

---

## 4. 개선점 도출

우선순위 순. 각 항목은 §5 검증 항목과 대응한다.

### IMP-C-01 (P0) 메시지 시퀀스 정규화기 도입

`_transform_messages()` 반환 직전에 `_normalize_anthropic_messages(messages)` 후처리를 추가한다.

1. `content`가 빈 문자열/빈 블록인 메시지는 **제거**한다 (단, `tool_use` / `tool_result` 블록 보유 메시지는 유지).
2. 연속 동일 role 메시지의 content 블록을 **병합**한다.
3. 선두가 `assistant`면 제거하거나 더미 `user` 메시지를 주입한다.
4. 마지막 메시지가 `assistant`면(프리필) 허용하되 후행 공백을 제거한다.

### IMP-C-02 (P0) OpenAI 규격 에러 응답으로 통일

`proxy_server.py`에 전역 예외 핸들러를 추가해 `HTTPException`을 최상위 `{"error": {...}}` `JSONResponse`로 재직렬화한다. `code`는 문자열(`"invalid_request_error"` 등)로 바꾸고 숫자 상태는 HTTP status로만 전달한다. `models.ErrorDetail.code: int` → `str`로 변경한다.

### IMP-C-03 (P0) SSE 청크 빌더 공통화

`base.py`에 `_chunk(id, model, delta, finish_reason=None)` 헬퍼를 만들어 모든 Provider가 사용하게 한다. 필수 필드는 `id`, `object: "chat.completion.chunk"`, `created`, `model`, `choices[].index`, `choices[].delta`. 스트림 시작 시 `delta: {"role":"assistant"}` 청크를 반드시 1회 방출한다.

### IMP-C-04 (P1) `finish_reason` 매핑 테이블화

```python
STOP_REASON_MAP = {
    "end_turn": "stop", "stop_sequence": "stop", "refusal": "stop",
    "pause_turn": "stop", "max_tokens": "length", "tool_use": "tool_calls",
}
finish_reason = STOP_REASON_MAP.get(stop_reason, "stop")
```

비스트리밍/스트리밍 양쪽에서 동일 테이블을 사용한다.

### IMP-C-05 (P1) 멀티모달 패스스루

`content_as_str()`에 의존하지 말고, `content`가 리스트인 경우 Anthropic content block(`{"type":"image","source":{...}}`)으로 변환하는 `_transform_content_parts()`를 신설한다. `content_as_str()`은 `system` 필드 전용으로만 남긴다.

### IMP-C-06 (P1) 스트리밍 오류·재시도 강화

- `event_type == "error"` 분기를 추가해 `_error_chunk()`로 전달한다.
- HTTP 429/500/529를 스트리밍에서도 지수 백오프 재시도 대상으로 삼는다 (첫 바이트 수신 전에 한함).
- 스트림이 `message_stop` 없이 끊기면 `finish_reason: "stop"` 청크를 보정 방출한다.

### IMP-C-07 (P1) `max_tokens` 모델별 기본값 테이블

`router.py`에 모델별 메타데이터(`max_output`, `context`)를 두고 `opencode.json`과 **단일 진실 소스**로 맞춘다. `max_tokens` 미지정 시 해당 모델의 상한을 사용한다.

### IMP-C-08 (P1) Prompt Caching 적용

`system` 블록과 `tools` 배열의 마지막 요소에 `cache_control: {"type": "ephemeral"}`를 부착하고, 대화 이력에서 최근 사용자 턴 직전 지점에 캐시 브레이크포인트를 둔다. `usage`에 `cache_creation_input_tokens` / `cache_read_input_tokens`를 합산 반영한다. 환경변수 `CLAUDE_PROMPT_CACHE=1`로 토글한다.

### IMP-C-09 (P1) usage 스트리밍 전달

`stream_options.include_usage`를 `models.py`에 추가하고, 참일 때 `message_delta`의 usage를 마지막 청크(`choices: []`, `usage: {...}`)로 방출한다.

### IMP-C-10 (P2) 로깅·인증 하드닝

- 인증 헤더 / 서버 키 로깅 제거. 실패 로그는 `Unauthorized (key mismatch)` 수준으로만 남긴다.
- `hmac.compare_digest()`로 키 비교.
- 페이로드 로깅은 `LOG_PAYLOAD` 환경변수로 게이팅하고 기본 한도를 2000자로 낮춘다.

### IMP-C-11 (P2) 리소스·정합성 정리

- FastAPI `lifespan`에서 각 Provider의 `client.aclose()` 호출.
- `system` 메시지 누적(`+=`)으로 통일.
- `tool_result`에 `is_error` 전달.
- `ChatCompletionResponse`에 `created: int` 필드 추가.
- `SUPPORTED_MODELS` 중복 키 제거.

---

## 5. 검증 방법

```bash
# 정적 검사
python -m py_compile ai-proxy/providers/claude_provider.py ai-proxy/proxy_server.py ai-proxy/models.py

# 회귀 테스트
pytest tests/ -k "claude or provider_contract"
```

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-C-01 | `messages`에 빈 content assistant 메시지 포함 | 400 없이 200 응답 |
| TC-C-02 | 연속 user 메시지 2개 전송 | 병합되어 정상 응답 |
| TC-C-03 | 잘못된 모델 ID 전송 | 최상위 `error` 키를 가진 400 |
| TC-C-04 | `stream=true` 첫 청크 확인 | `object == "chat.completion.chunk"`, `delta.role == "assistant"` |
| TC-C-05 | `max_tokens=16`으로 긴 답변 요청 | `finish_reason == "length"` |
| TC-C-06 | tools 2개 병렬 호출 유도 | `tool_calls[].index`가 0,1로 구분 |
| TC-C-07 | `tool` role 메시지 왕복 | 두 번째 턴에서 정상 최종 답변 |
| TC-C-08 | `stream_options.include_usage=true` | 마지막 청크에 `usage` 존재 |
| TC-C-09 | 인증 실패 | 로그에 서버 키가 남지 않음 |

---

## 6. 참조

- `docs/openai-compatible/GEMINI_v1.1.111_gemini-provider.md`
- `docs/openai-compatible/GEN_AI_v1.1.111_gen-ai-provider.md`
- `docs/openai-compatible/ORCHESTRATION_v1.1.111_tooluse-opencode.md`
- `docs/requirements/FSD_v1.0.052_openai-compatible-proxy.md`
- `docs/requirements/FSD_v1.0.053_openai-compatible-proxy-toolcall.md`
