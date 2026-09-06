# GEMINI v1.1.111 — `gemini_provider.py` OpenAI-Compatible 적합성 분석

- **대상 소스**: `ai-proxy/providers/gemini_provider.py` (218 lines)
- **연관 소스**: `ai-proxy/proxy_server.py`, `ai-proxy/models.py`, `ai-proxy/providers/base.py`
- **업스트림**: `https://generativelanguage.googleapis.com/v1beta/openai` (Google 공식 OpenAI 호환 엔드포인트)
- **대상 모델**: `gemini/gemini-3-pro-preview`, `gemini/gemini-3-flash-preview`
- **작성일**: 2026-09-06
- **결론 요약**: **세 Provider 중 호환성이 가장 높음**. 다만 "패스스루"라고 선언해 놓고 실제로는 **응답을 재구성(re-serialize)** 하기 때문에, 패스스루의 장점(무손실)을 스스로 무너뜨리는 구조적 모순이 있다. 스트리밍 `tool_calls` 인덱스 부여 로직에 **실동작 버그**가 있다.

---

## 1. 아키텍처 개요

Gemini는 Google이 제공하는 **공식 OpenAI 호환 엔드포인트**를 갖고 있어, 원칙적으로 변환이 불필요하다.

```text
opencode
   │  POST /v1/chat/completions  { model: "gemini/gemini-3-pro-preview", ... }
   ↓
proxy_server.py ── router.route_model() ──▶ GeminiProvider + "gemini-3-pro-preview"
   ↓
GeminiProvider._build_payload()      ← 요청: 사실상 패스스루 (필드 선별 재조립)
   ↓
POST {GEMINI_BASE_URL}/chat/completions   (Authorization: Bearer <GEMINI_API_KEY>)
   ↓
비스트리밍 → _parse_response()          ← 응답: 재구성 (패스스루 아님!)
스트리밍   → _normalize_stream_chunk()  ← tool_calls index 보정 + extra_content 제거
   ↓
opencode
```

**설계 의도와 구현의 괴리**: 파일 상단 docstring은 "변환 없이 패스스루"라고 명시하지만, 요청은 `_build_payload()`에서 화이트리스트 방식으로 재조립되고 응답은 `_parse_response()`에서 필드 단위로 재구성된다. 실제로는 **손실 있는 프록시(lossy proxy)** 다.

---

## 2. 지원 스펙 (Support Matrix)

### 2.1 요청 파라미터

| OpenAI 필드 | 지원 | 처리 | 비고 |
|---|:--:|---|---|
| `model` | O | 접두사 제거 후 전달 | |
| `messages[]` | O | `model_dump(exclude_none=True)` | `role`, `content`, `tool_calls`, `tool_call_id`만 통과 |
| `messages[].content` (parts 배열) | O | 원형 유지 | `_build_payload`는 `content_as_str()`를 쓰지 않아 **멀티모달이 살아남음** (3사 중 유일) |
| `messages[].name` | X | — | `models.ChatMessage` 스키마에 없어 유실 |
| `stream` | O | | |
| `temperature` / `max_tokens` | O | 조건부 포함 | |
| `tools` | O | `t.model_dump()` | **`exclude_none` 미적용** → `description: null` 등이 그대로 전송됨 (§3.6) |
| `tool_choice` | O | 원형 전달 | |
| `top_p` / `stop` / `n` / `seed` / `presence_penalty` | X | — | `models.py` 스키마 부재로 **조용히 유실** |
| `response_format` (Structured Output) | X | — | Gemini는 지원하나 프록시가 차단 (§3.5) |
| `stream_options` | X | — | |
| `reasoning_effort` / `thinking` | X | — | Gemini 3 사고 예산 제어 불가 |

### 2.2 응답 필드 (비스트리밍)

| OpenAI 필드 | 지원 | 소스 | 비고 |
|---|:--:|---|---|
| `id` | O | `data.id` | |
| `object` | O | 기본값 | |
| `created` | X | — | 스키마에 필드 없음 |
| `choices[0].message.content` | O | | |
| `choices[0].message.tool_calls` | O | | |
| `choices[0].finish_reason` | △ | 원본 통과 | 매핑 검증 없음 (§3.4) |
| `choices[1..n]` (n>1) | X | **폐기** | `_parse_response`가 `choices[0]`만 취함 (§3.3) |
| `logprobs` / `refusal` / `annotations` | X | **폐기** | 동일 원인 |
| `usage.*` | O | | `completion_tokens_details` 등 세부는 유실 |

### 2.3 스트리밍

| 항목 | 지원 | 비고 |
|---|:--:|---|
| SSE 텍스트 델타 | O | 원본 청크를 재직렬화하여 전달 |
| `tool_calls` 델타 | △ | `index` 자동 부여 로직에 버그 (§3.1) |
| 비표준 필드 제거 | O | `extra_content` 제거 |
| `[DONE]` 종결 | △ | 업스트림이 보낼 때만 전달 (§3.7) |
| 429 재시도 | X | 스트리밍 경로에 재시도 없음 |
| 파싱 실패 시 | O | 원본 라인 그대로 통과 (안전한 폴백) |

### 2.4 기타 엔드포인트

| OpenAI 엔드포인트 | 지원 | 비고 |
|---|:--:|---|
| `POST /v1/chat/completions` | O | |
| `GET /v1/models` | △ | 정적 하드코딩 목록. 업스트림 조회 아님 |
| `POST /v1/embeddings` | X | Gemini 호환 엔드포인트에 존재하나 프록시 미구현 |
| `POST /v1/completions` (legacy) | X | |
| `POST /v1/images/generations` | X | |

---

## 3. 문제점 분석

### 3.0 문제점별 해결 현황 요약 (v1.1.111 검증 기준)

| 항목 ID | 심각도 | 문제점 요약 | 해결 여부 | 조치 근거 및 상태 요약 |
|---|:---:|---|:---:|---|
| **P0-G1** | P0 | 스트리밍 `tool_calls` 인덱스 버그 (청크 내 enumerate) | **해결됨** | 스트림 스코프 누적 카운터 `next_index_ref` + `seen_tool_ids` 딕셔너리 도입 (REQ-111-040) |
| **P0-G2** | P0 | `_parse_response()` 무방비 인덱싱 → IndexError | **해결됨** | choices 빈 배열 검사 및 200 에러 바디 검출 시 `ProviderError(502)` 명시적 발생 (REQ-111-041) |
| **P1-G3** | P1 | "패스스루" 선언 위반 — 응답 필드 손실 | **해결됨** | `GEMINI_PASSTHROUGH=1` 및 `PassthroughResponse` 도입으로 n>1, logprobs 등 무손실 보존 (REQ-111-042) |
| **P1-G4** | P1 | `finish_reason` 무검증 통과 | **해결됨** | `ALLOWED_FINISH_REASONS` 및 `GEMINI_FINISH_REASON_MAP` 정규화 매핑 적용 (REQ-111-043) |
| **P1-G5** | P1 | Structured Output(`response_format`) 차단 | **해결됨** | `ChatCompletionRequest`에 `response_format` 필드 추가 및 Gemini 페이로드 전달 통과 (REQ-111-001, 045) |
| **P1-G6** | P1 | `tools` 직렬화 시 `exclude_none` 누락 | **해결됨** | `[t.model_dump(exclude_none=True) for t in request.tools]` 적용 (REQ-111-045) |
| **P1-G7** | P1 | 스트림 종결 보장 없음 | **해결됨** | 업스트림 단절 또는 [DONE] 누락 시 `finish_reason="stop"` 청크 보정 및 `[DONE]` 방출 보장 (REQ-111-032) |
| **P1-G8** | P1 | 스트리밍 429/5xx 재시도 부재 | **해결됨** | 첫 바이트 전 HTTP 429/500/503 수신 시 `anyio.sleep()` 지수 백오프 최대 3회 재시도 (REQ-111-046) |
| **P2-G9** | P2 | 로깅 과적 (청크 단위 출력) | **해결됨** | `LOG_CHUNK=1` 환경변수 게이팅, 스트림 완료 1줄 요약 출력, `DEFAULT_LOG_MAX_LEN=2000` (REQ-111-014, 047) |
| **P2-G10** | P2 | 공통 인프라 결함 (에러 래핑, API 키 평문 등) | **해결됨** | OpenAI 규격 에러 통일, lifespan aclose, created 타임스탬프 추가, API 키 평문 로깅 제거 (REQ-111-011~015) |

---

### P0-G1. 스트리밍 `tool_calls` 인덱스 부여 버그 — 병렬 툴 호출 파손
- **해결 여부**: **해결됨**
- **조치 내용**: 스트림 제너레이터 단위의 지역 상태(`seen_tool_ids: dict[str, int]`, `next_index_ref: list[int]`)를 도입하여 스트림 전체 누적 카운터로 인덱스를 부여함. 업스트림 인덱스는 보존하며 동일 tool_call ID의 청크 분할 델타에 대해 동일 index 유지 보장 (REQ-111-040, TASK-GEMINI-1).

`_normalize_stream_chunk()` (`gemini_provider.py:130-152`):

```python
for i, tc in enumerate(tool_calls):
    if "index" not in tc:
        tc["index"] = i
```

`enumerate`는 **해당 청크 내부의 위치**를 센다. 그런데 Gemini는 여러 개의 tool_call을 **청크마다 하나씩** 나눠 보내는 경우가 있다. 이때 각 청크의 첫 요소는 항상 `i == 0`이므로,

```text
chunk 1: tool_calls[{index:0, name:"read"}]
chunk 2: tool_calls[{index:0, name:"write"}]   ← 잘못된 index
chunk 3: tool_calls[{index:0, name:"bash"}]    ← 잘못된 index
```

AI SDK는 `index`를 키로 툴 호출을 누적 병합하므로, **세 개의 툴 호출이 하나로 덮어써지거나 arguments가 뒤섞인다.** 파일 편집 + 테스트 실행을 한 턴에 하려는 opencode 워크플로가 정확히 여기서 깨진다.

> 인덱스는 **스트림 전체에 걸친 누적 카운터**여야 한다 (Claude Provider의 `current_tool_index` 방식이 옳다).

### P0-G2. `_parse_response()` 무방비 인덱싱 → IndexError
- **해결 여부**: **해결됨**
- **조치 내용**: 업스트림 200 응답 바디 내 `error` 객체 존재 검사 및 `choices` 빈 배열/키 부재 방어 로직 추가. 안전 필터 차단 등을 인지하여 명시적 `ProviderError(502)` 및 `public_message` 발생 (REQ-111-041, TASK-GEMINI-1).

```python
choice_data = data["choices"][0]      # gemini_provider.py:83
```

Gemini는 안전 필터 차단, 프롬프트 거부, 빈 후보(candidate) 상황에서 `choices`를 빈 배열로 반환할 수 있다. 이 경우 `IndexError`가 발생하고, `proxy_server.py`의 포괄 `except Exception`에 걸려 **원인 불명의 502**로 변환된다. 사용자는 "왜 막혔는지" 알 수 없다. `data["choices"]` 키 자체가 없는 에러 응답(200 상태의 error body)도 동일하다.

### P1-G3. "패스스루" 선언 위반 — 응답 필드 손실
- **해결 여부**: **해결됨**
- **조치 내용**: `GEMINI_PASSTHROUGH=1` 모드 및 `PassthroughResponse` 도입으로 n>1 다중 선택지, logprobs, annotations 등 업스트림 응답 필드를 무손실 보존 (REQ-111-042, TASK-GEMINI-1).

`_parse_response()`는 `id`, `content`, `tool_calls`, `finish_reason`, `usage`만 골라 새 객체를 만든다. 결과적으로 다음이 전부 사라진다.

- `choices[1..n]` — `n > 1` 요청 시 나머지 후보 전부
- `logprobs`, `refusal`, `annotations`(그라운딩/인용 메타데이터)
- `system_fingerprint`, `service_tier`
- `usage.completion_tokens_details.reasoning_tokens` — Gemini 3의 사고 토큰 계측

패스스루가 목적이라면 **비스트리밍 응답도 업스트림 JSON을 그대로 반환**하는 것이 맞다.

### P1-G4. `finish_reason` 무검증 통과
- **해결 여부**: **해결됨**
- **조치 내용**: `ALLOWED_FINISH_REASONS` 화이트리스트 및 `GEMINI_FINISH_REASON_MAP` 정규화 매핑(`_map_finish_reason`) 적용. SAFETY/RECITATION → content_filter, MAX_TOKENS → length, STOP/OTHER → stop (REQ-111-043, TASK-GEMINI-1).

`choice_data.get("finish_reason", "stop")`을 그대로 반환한다. Google 호환 계층은 대체로 OpenAI 값을 쓰지만, 안전 필터 차단 시 `SAFETY`, `RECITATION` 같은 **Gemini 고유 값**이 새어 나올 수 있다. opencode는 이를 해석하지 못해 턴을 정상 종료로 오인한다.

### P1-G5. Structured Output(`response_format`) 차단
- **해결 여부**: **해결됨**
- **조치 내용**: `models.ChatCompletionRequest`에 `response_format` 필드 추가 및 Gemini 페이로드 전달 통과 (REQ-111-001, REQ-111-045).

`models.ChatCompletionRequest`에 `response_format`이 없어 Pydantic이 무시한다. Gemini는 JSON 스키마 강제 출력을 지원하는데, 프록시가 이를 전달하지 못한다. opencode의 구조화 응답 기능이 무력화된다.

### P1-G6. `tools` 직렬화 시 `exclude_none` 누락
- **해결 여부**: **해결됨**
- **조치 내용**: `_build_payload()`에서 `[t.model_dump(exclude_none=True) for t in request.tools]` 적용으로 불필요한 null 필드 배제 (REQ-111-045, TASK-GEMINI-1).

```python
payload["tools"] = [t.model_dump() for t in request.tools]
```

`FunctionDefinition.description`/`parameters`가 `None`이면 `{"description": null, "parameters": null}`이 그대로 전송된다. Google 검증 계층이 `null` 스키마를 거부하면 400이 난다. `messages`는 `exclude_none=True`를 쓰는데 `tools`만 빠져 있다 — **일관성 결함**.

### P1-G7. 스트림 종결 보장 없음
- **해결 여부**: **해결됨**
- **조치 내용**: 업스트림 단절 또는 `[DONE]` 누락 시 `finish_reason: "stop"` 청크 보정 및 `[DONE]` 방출 보장 (REQ-111-032, TASK-GEMINI-1).

정상 경로에서 `[DONE]`은 업스트림이 보낸 라인을 중계할 때만 전달된다. 업스트림이 커넥션을 그냥 닫으면 `async for`가 조용히 끝나고 **`[DONE]`도 `finish_reason`도 없이** 스트림이 종료된다. `_error_chunk()`에는 `[DONE]`이 포함되어 있어 에러 경로만 안전하다.

### P1-G8. 스트리밍 429/5xx 재시도 부재
- **해결 여부**: **해결됨**
- **조치 내용**: 첫 바이트 방출 전 HTTP 429/500/503 수신 시 `await anyio.sleep()` 기반 최대 3회 지수 백오프 재시도 구현 (REQ-111-046, TASK-GEMINI-1).

`chat()`은 `_retry_on_429`로 보호되지만 `stream()`은 상태 코드를 확인 후 즉시 에러 청크를 방출한다. opencode는 기본적으로 스트리밍을 쓰므로 **실사용 경로에 재시도가 없다**. Gemini 무료 티어의 분당 요청 제한을 감안하면 체감 실패율이 높다.

### P2-G9. 로깅
- **해결 여부**: **해결됨**
- **조치 내용**: `LOG_CHUNK=1` 환경변수 게이팅(`should_log_chunk()`), 스트림 완료 시 1줄 단일 요약 로그 출력, `DEFAULT_LOG_MAX_LEN=2000` 축소 및 `_scrub_secrets` 적용 (REQ-111-014, REQ-111-047, TASK-CORE-3, TASK-GEMINI-1).

- `logger.info(f"Gemini chat response: {truncate_for_log(data)}")` — 기본 한도 100,000자. **응답 전문을 매번 기록**한다.
- `logger.info(f"Gemini stream chunk[{n}]: ...")` — **청크마다 한 줄**. 긴 응답 하나에 수천 줄의 로그가 쌓인다. 스트리밍 처리량 자체를 떨어뜨린다.
- 요청 페이로드 전문도 동일하게 기록된다.

### P2-G10. 공통 인프라 결함 (Claude 문서와 동일)
- **해결 여부**: **해결됨**
- **조치 내용**:
  1. **자격증명 평문 로깅 완전 제거**: `proxy_server.py`의 `authorization` 및 `Expected: Bearer` 평문 로그 삭제, `hmac.compare_digest` 적용, `_scrub_secrets` 및 `public_message` 도입으로 민감정보 유출 차단 (REQ-111-012, REQ-111-020).
  2. **OpenAI 규격 에러 응답 통일**: 최상위 `error` 객체(`message`, `type`, `code`) 및 문자열 에러 코드 정규화 (REQ-111-011).
  3. **리소스 안전 종료**: FastAPI lifespan 도입 및 `BaseProvider.aclose()`로 클라이언트 종료 보장 (REQ-111-013).
  4. **표준 타임스탬프 필드**: `/v1/models` 및 `/health`에 `created` 정수 epoch 추가 (REQ-111-015).
  5. **SSE 표준 청크 규격**: `BaseProvider._chunk` 공통 헬퍼로 `object: "chat.completion.chunk"` 및 표준 스키마 준수 (REQ-111-030).

- 에러 응답이 `{"detail": {"error": ...}}` 형태 (OpenAI 스펙 위반)
- `AsyncClient` 미종료
- `/v1/models`가 정적 목록이며 `created` 필드 없음
- `AI_PROXY_API_KEY` 평문 로깅
- `ChatCompletionResponse`에 `created` 필드 부재

---

## 4. 개선점 도출

### IMP-G-01 (P0) 스트리밍 tool_call 인덱스를 누적 카운터로 교체

`_normalize_stream_chunk()`를 스트림 단위 상태를 갖는 형태로 바꾼다.

```python
# stream() 지역 상태
seen_tool_ids: dict[str, int] = {}
next_index = 0

# 정규화 시
for tc in tool_calls:
    if "index" in tc:
        continue                       # 업스트림이 준 index를 신뢰
    tc_id = tc.get("id")
    if tc_id and tc_id in seen_tool_ids:
        tc["index"] = seen_tool_ids[tc_id]
    else:
        tc["index"] = next_index
        if tc_id:
            seen_tool_ids[tc_id] = next_index
        next_index += 1
```

`id`가 있으면 그것으로 동일 툴 호출을 상관시키고, 없으면 도착 순서대로 새 인덱스를 부여한다.

### IMP-G-02 (P0) 응답 파싱 방어 + 진짜 패스스루

```python
choices = data.get("choices") or []
if not choices:
    raise ProviderError(
        f"Gemini returned no choices: {json.dumps(data)[:500]}",
        status_code=502,
    )
```

나아가 **비스트리밍 응답을 업스트림 JSON 그대로 반환**하는 경로를 도입한다 (`GEMINI_PASSTHROUGH=1`). `model` 필드만 접두사 포함 원본 ID로 덮어쓰면 되며, `_parse_response()`는 검증/폴백 용도로만 남긴다. 이렇게 하면 P1-G3이 근본 해소된다.

### IMP-G-03 (P1) `finish_reason` 화이트리스트 매핑

```python
ALLOWED = {"stop", "length", "tool_calls", "content_filter", "function_call"}
GEMINI_MAP = {"SAFETY": "content_filter", "RECITATION": "content_filter",
              "MAX_TOKENS": "length", "STOP": "stop"}
fr = choice.get("finish_reason", "stop")
fr = fr if fr in ALLOWED else GEMINI_MAP.get(fr, "stop")
```

### IMP-G-04 (P1) 요청 스키마 확장 (전 Provider 공통)

`models.ChatCompletionRequest`에 다음을 추가하고, Gemini는 이를 그대로 통과시킨다.

`top_p`, `stop`, `n`, `seed`, `presence_penalty`, `frequency_penalty`, `response_format`, `stream_options`, `parallel_tool_calls`, `user`, `logprobs`, `top_logprobs`

미지원 Provider(Claude/GenAI)는 명시적으로 드랍하되 **경고 로그를 남긴다** — 현재처럼 조용히 사라지면 안 된다.

### IMP-G-05 (P1) `tools` 직렬화 정합화

```python
payload["tools"] = [t.model_dump(exclude_none=True) for t in request.tools]
```

### IMP-G-06 (P1) 스트림 종결·재시도 보강

- 업스트림 종료 후 `[DONE]`을 받지 못했으면 `finish_reason: "stop"` 청크 + `[DONE]`을 보정 방출한다.
- 첫 바이트 수신 전 429/500/503에 한해 스트리밍도 지수 백오프 재시도한다.

### IMP-G-07 (P2) 로깅 정책 통일

- `LOG_LEVEL` / `LOG_PAYLOAD` / `LOG_CHUNK` 3개 환경변수로 분리 제어.
- 청크 단위 로그는 기본 OFF. 대신 스트림 종료 시 요약 1줄(청크 수, 총 길이, finish_reason, tool_call 수).
- `truncate_for_log` 기본 한도 100000 → 2000.

### IMP-G-08 (P2) 엔드포인트 확장 (선택)

`/v1/embeddings` 프록시를 추가하면 opencode의 코드 인덱싱/검색 기능을 Gemini로 처리할 수 있다. 우선순위는 낮으나 최종 목표(코드베이스 탐색)와 부합한다.

---

## 5. 검증 방법

```bash
python -m py_compile ai-proxy/providers/gemini_provider.py
pytest tests/ -k "gemini or provider_contract"
```

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-G-01 | 한 턴에 툴 3개 병렬 호출 유도 (스트리밍) | 델타의 `index`가 0,1,2로 구분되고 3개 모두 실행 |
| TC-G-02 | 안전 필터에 걸리는 프롬프트 | 502가 아닌 명시적 `content_filter` 또는 원인이 담긴 에러 |
| TC-G-03 | `n=2` 요청 | 두 후보 모두 반환 (패스스루 모드) |
| TC-G-04 | `description` 없는 tool 정의 전송 | 400 없이 정상 처리 |
| TC-G-05 | `response_format` JSON 스키마 지정 | 스키마를 따르는 응답 |
| TC-G-06 | 업스트림이 `[DONE]` 없이 종료 | 클라이언트가 정상 종결 인식 |
| TC-G-07 | 이미지 파트 포함 메시지 | Vision 응답 정상 (Claude와 대조) |
| TC-G-08 | 429 유발 후 스트리밍 요청 | 재시도 후 성공 또는 명확한 429 에러 |

---

## 6. Provider 간 동작 불일치 요약 (v1.1.111 현황)

세 Provider가 같은 인터페이스를 구현하면서 서로 다르게 동작했던 지점. v1.1.111 리팩토링을 통해 공통 계층(TASK-CORE) 및 Provider별 구현(TASK-GEMINI/CLAUDE/GENAI)으로 불일치를 점검·정비하였다.

### 6.1 Provider 동작 비교 및 해소 상태 표

| 항목 | Claude | Gemini | GenAI | 현재 상태 및 해소 여부 |
|---|---|---|---|:---:|
| **SSE `delta.role` 초기 청크** | 전송 (`_chunk` 사용) | 전송 (`_chunk` 사용) | 전송 (`_chunk` 사용) | **해소됨** (3사 모두 스트림 시작 시 `delta={"role": "assistant"}` 청크 1회 방출 통일, REQ-111-031) |
| **SSE `object` 필드** | 있음 (`chat.completion.chunk`) | 있음 (`chat.completion.chunk`) | 있음 (`chat.completion.chunk`) | **해소됨** (`BaseProvider._chunk` 공통 도입으로 3사 모두 표준 필드 `object`, `id`, `created`, `model` 보장, REQ-111-030) |
| **tool_call index** | 누적 카운터 (정상) | **누적 카운터 + seen_tool_ids (정상)** | `call_{uuid}` 독립 식별 + 누적 관리 | **해소됨** (Gemini의 청크 내 enumerate 버그 해결되어 스트림 전체 누적 카운터 및 seen_tool_ids 적용, REQ-111-040) |
| **다중 system 메시지** | 병합/정규화 (`_normalize_anthropic_messages`) | 그대로 전달 (OpenAI 호환 배열 유지) | 누적 (`+=` 및 프롬프트 규약 주입) | **부분 해소 (허용된 차이)** (각 업스트림 모델 API 제약에 맞춰 안전하게 정규화/전달됨) |
| **멀티모달** | `_transform_content_parts` (base64/URL 지원) | 유지 (parts 배열 그대로 전달) | 문자열 변환 (`[User Context]` 텍스트화) | **부분 해소** (Claude 멀티모달 이미지 블록 지원 구현 REQ-111-042; GenAI는 SCI Portal API 텍스트 사양 유지) |
| **스트리밍 재시도** | 첫 바이트 전 지수 백오프 (429/500/529) | 첫 바이트 전 지수 백오프 (429/500/503) | 미지원 (스트리밍 자체가 버퍼링) | **부분 해소** (Claude, Gemini는 `anyio.sleep` 기반 첫 바이트 전 지수 백오프 재시도 구현 완료; GenAI는 버퍼링) |
| **실시간 스트리밍** | 진짜 스트리밍 (SSE) | 진짜 스트리밍 (SSE) | **가짜 (버퍼링 후 일괄 SSE 방출)** | **미해소 (보류)** (GenAI Provider는 SCI Portal 실샘플 부재로 `isStream=False` 버퍼링 방식 유지 — P0-N1 별도 릴리스 분리) |

### 6.2 해소 결과 구분 요약
- **해소된 행 (3개)**:
  1. **SSE `delta.role` 초기 청크**: 3개 Provider 모두 스트림 시작 즉시 `role: "assistant"`를 방출하도록 정규화 완료.
  2. **SSE `object` 필드**: `BaseProvider._chunk()` 공통 헬퍼를 통해 `chat.completion.chunk` 표준 필드 규격 통일.
  3. **tool_call index**: Gemini Provider의 청크 단위 enumerate 버그가 스트림 단위 누적 카운터(`next_index_ref`, `seen_tool_ids`)로 완벽히 교체되어 병렬 툴 호출 인덱스 충돌 해소.
- **부분 해소된 행 (3개)**:
  4. **다중 system 메시지**: Anthropic API 제약(단일 system)에 맞춘 Claude Provider 정규화, GenAI의 누적 프롬프트, Gemini의 네이티브 메시지 통과로 각 업스트림 특성에 최적화.
  5. **멀티모달**: Gemini(네이티브 전달)에 이어 Claude도 base64/URL 변환 지원(`_transform_content_parts`) 완료. GenAI는 포털 텍스트 전용 특성상 문자열 처리.
  6. **스트리밍 재시도**: Gemini와 Claude 모두 첫 바이트 전 429/5xx 수신 시 `anyio.sleep()` 지수 백오프 재시도 구현 완료.
- **남은 행 (미해소, 1개)**:
  7. **실시간 스트리밍**: Claude와 Gemini는 실제 업스트림 SSE 스트리밍을 수행하나, GenAI Provider는 SCI Portal의 `isStream=true` 실샘플 및 자격증명 부재로 인해 `isStream=False` 버퍼링 방식 유지 (P0-N1 사유로 별도 릴리스 보류).

→ 이 표의 각 행을 통일하는 것이 `ORCHESTRATION_v1.1.111` 문서의 공통 작업(TASK-CORE)이다.

---

## 7. 참조

- `docs/openai-compatible/CLAUDE_v1.1.111_claude-provider.md`
- `docs/openai-compatible/GEN_AI_v1.1.111_gen-ai-provider.md`
- `docs/openai-compatible/ORCHESTRATION_v1.1.111_tooluse-opencode.md`
- `docs/requirements/BUG_v1.0.081_gemini-streaming-response-parsing.md`
- `docs/requirements/BUG_v1.0.031_gemini-rate-limit.md`
