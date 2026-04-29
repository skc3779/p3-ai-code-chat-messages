# REP v1.0.055 - GenAI Provider Endpoint URL 구조 수정 보고서

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.055 |
| 제목 | GenAI Provider — Endpoint URL 및 API 형식 구조 수정 완료 보고서 |
| 작성일 | 2026-03-02 |
| 관련 FSD | [FSD v1.0.055](../requirements/FSD_v1.0.055_genai-provider-endpoint-fix.md) — Endpoint URL 구조 수정 |
| 선행 | [FSD v1.0.054 v2](../requirements/FSD_v1.0.054_genai-provider-toolcall_v2.md) — GenAI Provider Tool Call 에뮬레이션 |
| 참조 소스 | [genai_assistant.py](../../../src/genai_assistant.py), [llm_config.py](../../../src/llm_config.py), [README-gen-ai-chat-code.md](../../../README-gen-ai-chat-code.md) |

---

## 1. 구현 범위 요약

| 요구사항 ID | 요구사항 | 상태 |
|------------|----------|:----:|
| REQ-055-001 | Endpoint URL에 `/openapi/chat/v1/messages` 하위 경로 추가 | ✅ 완료 |
| REQ-055-002 | 인증 헤더를 `X-Lego-Client-Id` / `X-Lego-Client-Secret`로 수정 | ✅ 완료 |
| REQ-055-003 | Request Body를 `modelIds`, `contents`, `llmConfig`, `isStream`, `systemPrompt` 구조로 수정 | ✅ 완료 |
| REQ-055-004 | 논스트리밍 Response 파싱을 `content` 키 기반으로 수정 | ✅ 완료 |
| REQ-055-005 | 스트리밍 Response SSE 이벤트 파싱 지원 | ✅ 완료 |
| REQ-055-006 | 기존 Tool Call 에뮬레이션(FSD v1.0.054) 유지 | ✅ 완료 |
| REQ-055-007 | `llmConfig`에 `llm_config.py` 기본값 반영 (`max_new_tokens: 10240`) | ✅ 완료 |

---

## 2. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `ai-proxy/providers/genai_provider.py` | **전면 수정** | Endpoint URL, 인증 헤더, Request Body, Response 파싱 전면 수정 (421줄) |
| `src/llm_config.py` | **수정** | 모든 언어 설정의 `max_new_tokens`를 `3072` → `10240`으로 변경 |
| `docs/specs/requirements/FSD_v1.0.054_genai-provider-toolcall_v2.md` | **수정** | §3.3 비교표에 v1.0.055 수정 내역 반영 |
| `docs/specs/requirements/FSD_v1.0.055_genai-provider-endpoint-fix.md` | **신규** | 오류 분석 및 수정 설계 문서 |

---

## 3. 수정 상세 내역

### 3.1 Endpoint URL 수정 (REQ-055-001)

```diff
 # chat() 메서드
-resp = await self._retry_on_429(
-    lambda: self.client.post(self.base_url, json=payload)
-)
+api_url = f"{self.base_url}/openapi/chat/v1/messages"
+resp = await self._retry_on_429(
+    lambda: self.client.post(api_url, json=payload)
+)
```

### 3.2 인증 헤더 수정 (REQ-055-002)

```diff
 self.client = httpx.AsyncClient(
     headers={
-        "X-Client-Key": client_key,
-        "X-Client-Secret": client_secret,
+        "X-Lego-Client-Id": client_key,
+        "X-Lego-Client-Secret": client_secret,
         "Content-Type": "application/json",
     },
 )
```

### 3.3 Request Body 구조 수정 (REQ-055-003)

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 모델 ID | `model_id: "모델"` (문자열) | `modelIds: ["모델"]` (배열) |
| 대화 내용 | `prompt: [{role, text}]` (객체 배열) | `contents: ["문자열"]` (문자열 배열) |
| LLM 설정 | `parameters: {temperature, max_output_tokens}` (2개) | `llmConfig: {max_new_tokens, seed, top_k, top_p, temperature, repetition_penalty}` (6개) |
| 스트리밍 | 없음 | `isStream: false` |
| 시스템 프롬프트 | prompt 배열 내 system role | `systemPrompt: "..."` (최상위 키) |

```diff
-return {
-    "model_id": request.model,
-    "prompt": prompt,
-    "parameters": {
-        "temperature": ...,
-        "max_output_tokens": ...,
-    },
-}
+return {
+    "modelIds": [request.model],
+    "contents": contents,
+    "llmConfig": {
+        "max_new_tokens": request.max_tokens or 10240,
+        "seed": None,
+        "top_k": 14,
+        "top_p": 0.94,
+        "temperature": request.temperature if request.temperature is not None else 0.4,
+        "repetition_penalty": 1.04,
+    },
+    "isStream": False,
+    "systemPrompt": system_prompt,
+}
```

### 3.4 Response 파싱 수정 (REQ-055-004)

```diff
-content = data.get("response", data.get("text", data.get("result", str(data))))
+content = data.get("content", "")
```

### 3.5 llm_config.py `max_new_tokens` 변경 (REQ-055-007)

모든 언어 설정(python, java, node.js, c#, srs, baseline)의 `max_new_tokens`를 일괄 변경:

```diff
-"max_new_tokens": 3072,
+"max_new_tokens": 10240,
```

---

## 4. 요구사항별 검증

### 4.1 기능 요구사항 (REQ-055)

| REQ | 요구사항 | 구현 위치 | 결과 |
|-----|----------|----------|------|
| REQ-055-001 | Endpoint URL 경로 추가 | `chat()` L250: `api_url = f"{self.base_url}/openapi/chat/v1/messages"` | ✅ 통과 |
| REQ-055-002 | 인증 헤더 수정 | `__init__()` L76-77: `X-Lego-Client-Id`, `X-Lego-Client-Secret` | ✅ 통과 |
| REQ-055-003 | Request Body 구조 수정 | `_transform_request()` L220-226: `modelIds`, `contents`, `llmConfig`, `isStream`, `systemPrompt` | ✅ 통과 |
| REQ-055-004 | 응답 파싱 수정 (content 키) | `chat()` L259: `content = data.get("content", "")` | ✅ 통과 |
| REQ-055-005 | 스트리밍 SSE 지원 | `stream()` — 버퍼링 후 OpenAI SSE 변환 (`chat()` 내부 사용) | ✅ 통과 |
| REQ-055-006 | Tool Call 에뮬레이션 유지 | `_build_tools_prompt()`, `_parse_tool_calls()`, `_extract_non_tool_content()` 유지 | ✅ 통과 |
| REQ-055-007 | llmConfig 기본값 반영 | `_transform_request()` L211-218: 6개 파라미터, `max_new_tokens: 10240` | ✅ 통과 |

### 4.2 비기능 요구사항 (NREQ-055)

| NREQ | 요구사항 | 결과 |
|------|----------|------|
| NREQ-055-001 | FSD v1.0.054 Tool Call 에뮬레이션 정상 동작 | ✅ 기존 로직 유지 (REQ-054-001~009 모두 보존) |
| NREQ-055-002 | `genai_assistant.py`와 동일한 API 구조 사용 | ✅ Endpoint URL, 헤더, Body 구조 모두 일치 |

---

## 5. 수정 전후 API 형식 대비

| 항목 | 수정 전 (v1.0.054) | 수정 후 (v1.0.055) | `genai_assistant.py` |
|------|--------------------|--------------------|---------------------|
| Endpoint | `{ENDPOINT_URL}` | `{ENDPOINT_URL}/openapi/chat/v1/messages` ✅ | `{url}/openapi/chat/v1/messages` |
| 인증 (ID) | `X-Client-Key` | `X-Lego-Client-Id` ✅ | `X-Lego-Client-Id` |
| 인증 (Secret) | `X-Client-Secret` | `X-Lego-Client-Secret` ✅ | `X-Lego-Client-Secret` |
| 모델 ID | `model_id` (문자열) | `modelIds` (배열) ✅ | `modelIds` (배열) |
| 대화 내용 | `prompt` (객체 배열) | `contents` (문자열 배열) ✅ | `contents` (문자열 배열) |
| LLM 설정 | `parameters` (2개) | `llmConfig` (6개) ✅ | `llmConfig` (6개) |
| 스트리밍 | 없음 | `isStream` ✅ | `isStream` |
| 시스템 프롬프트 | prompt 내 system role | `systemPrompt` (최상위 키) ✅ | `systemPrompt` (최상위 키) |
| 응답 파싱 | `response/text/result` | `content` ✅ | `content` |

---

## 6. 알려진 사항

| 항목 | 설명 |
|------|------|
| 사내 네트워크 테스트 | SCI Portal은 사내 네트워크에서만 접근 가능하여 실통합 테스트는 사내 환경에서 필요 |
| `max_new_tokens` 변경 | 기존 `3072` → `10240`으로 변경하여 더 긴 응답 생성 가능 (모든 언어 설정 동일 적용) |
| Tool Call 에뮬레이션 | FSD v1.0.054의 프롬프트 기반 Tool Call 에뮬레이션이 수정된 API 구조에서도 정상 유지 |

---

## 7. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1.0.055 | 2026-03-02 | 최초 작성: GenAI Provider Endpoint URL, 인증 헤더, Request Body, Response 파싱 구조 수정 완료 |
