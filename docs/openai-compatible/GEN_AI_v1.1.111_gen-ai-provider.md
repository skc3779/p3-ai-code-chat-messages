# GEN AI v1.1.111 — `genai_provider.py` OpenAI-Compatible 적합성 분석 및 Tool Use 재설계

- **대상 소스**: `ai-proxy/providers/genai_provider.py` (448 lines)
- **연관 소스**: `ai-proxy/models.py`, `ai-proxy/router.py`, `ai-proxy/proxy_server.py`, `src/sensitive_filter.py`
- **업스트림**: Samsung SCI Portal — `{ENDPOINT_URL}/openapi/chat/v1/messages` (커스텀 REST, OpenAI 비호환)
- **대상 모델**: `genai/gpt-oss-120B-medium`, `genai/<glm-5.2-512k-model-id>` **(TBD — §2.0)**
- **작성일**: 2026-09-06
- **위상**: **주력(primary) Provider**. opencode를 통한 코드 생성/편집/실행/테스트의 기본 백엔드.

---

## 0. 핵심 정정 — "Tool Use 미지원"은 사실이 아니다

착수 프롬프트에는 *"현재는 Conversational(chat/completions)만 지원되고 Tool Use는 지원되지 않는다"* 고 되어 있으나, **소스 확인 결과 프롬프트 기반 Tool Use 에뮬레이션이 이미 구현되어 있다.**

| 요구 기능 | 구현 여부 | 구현 위치 |
|---|:--:|---|
| `tools` → 프롬프트 주입 | **구현됨** | `_build_tools_prompt()` (REQ-054-001) |
| 응답 → `tool_calls` 파싱 | **구현됨** | `_parse_tool_calls()` + `TOOL_CALL_PATTERN` (REQ-054-002) |
| `tool` role → 텍스트 변환 | **구현됨** | `_transform_request()` (REQ-054-003) |
| `tool_choice` 처리 | **구현됨** | `_build_tools_prompt()` (REQ-054-004) |
| assistant `tool_calls` → 텍스트 | **구현됨** | `_transform_request()` (REQ-054-008) |
| 혼합 응답 분리 | **구현됨** | `_extract_non_tool_content()` (REQ-054-009) |
| SSE `tool_calls` 델타 방출 | **구현됨** | `stream()` (REQ-054-005) |

따라서 본 문서의 과제는 **"없는 기능을 새로 만드는 것"이 아니라, 있는 기능이 opencode 실사용에서 왜 실패하는지를 규명하고 재설계하는 것**이다. 아래 §4에서 실패 원인을 6개 계층으로 분해한다.

---

## 0.1 glm 5.2

착수 프롬프트의 `glm5.2 512k`는 **코드·설정 어디에도 등록되어 있지 않다.**

`glm5.2 512k` -> `glm5.2` 로 수정하고 아래와 같이 modelIds 배열의 요소로 전달해야 한다.

```python
    ... 생략
    return {
        "modelIds": [request.model],       # REQ-055-003: 배열 형식
        "contents": contents,               # REQ-055-003: 문자열 배열
        "llmConfig": llm_config,            # REQ-055-003: LLM 설정 객체
        "isStream": False,                  # 프록시에서는 논스트리밍으로 수신 후 변환
        "systemPrompt": system_prompt,      # REQ-055-003: 최상위 키
    }

```

---

## 1. 아키텍처 개요

SCI Portal은 OpenAI 스펙과 **구조적으로 다른** 커스텀 REST API다.

```text
opencode (OpenAI 형식)
   │  { model: "genai/gpt-oss-120B-medium", messages[], tools[], tool_choice, stream: true }
   ↓
proxy_server.py ── router.route_model() ──▶ GenAIProvider
   ↓
_transform_request()
   ├─ messages[]  → contents[]  (역할 표시가 문자열 태그로만 남는 평문 배열)
   │                 "[User Context]\n...", "[Assistant Context]\n...", "[Tool Result for X]\n..."
   ├─ system      → systemPrompt (최상위 문자열, += 누적)
   ├─ tools       → systemPrompt 말미에 도구 정의 텍스트 주입  ← Tool Use 에뮬레이션의 핵심
   ├─ temperature / max_tokens → llmConfig{max_new_tokens, seed, top_k, top_p, temperature, repetition_penalty}
   └─ isStream: False  (하드코딩)
   ↓
SensitiveWordFilter.mask_contents() / mask_system_prompt()      ← 민감어 치환
   ↓
POST {ENDPOINT_URL}/openapi/chat/v1/messages
     헤더: X-Lego-Client-Id / X-Lego-Client-Secret
   ↓
응답 { "content": "..." }
   ↓
SensitiveWordFilter.unmask(content)                             ← content에만 적용
   ↓
_parse_tool_calls()  : ```tool_call {json} ``` 정규식 매칭 → OpenAI tool_calls
_extract_non_tool_content() : tool_call 블록 제거 후 잔여 텍스트
   ↓
chat()  → ChatCompletionResponse
stream() → chat() 결과를 SSE 청크로 사후 분해 (진짜 스트리밍 아님)
   ↓
opencode
```

---

## 2. 지원 스펙 (Support Matrix)

### 2.1 요청 파라미터

| OpenAI 필드 | 지원 | 매핑 | 비고 |
|---|:--:|---|---|
| `model` | O | `modelIds: [model]` | 배열 형식 |
| `messages[].role=system` | O | `systemPrompt` (`+=` 누적) | 3사 중 유일하게 누적 처리 |
| `messages[].role=user` | △ | `contents[] "[User Context]\n..."` | **역할이 구조가 아닌 텍스트 관례로 표현** (§4.4) |
| `messages[].role=assistant` | △ | `contents[] "[Assistant Context]\n..."` | 동일 |
| `messages[].role=tool` | △ | `contents[] "[Tool Result for X]\n..."` | 이름 역추적이 O(n²) (§4.6) |
| `messages[].content` (parts 배열) | △ | 텍스트만 추출 | 멀티모달 소실 |
| `stream` | **X** | — | **`isStream: False` 하드코딩** (§4.1) |
| `temperature` | O | `llmConfig.temperature` (기본 0.4) | |
| `max_tokens` | O | `llmConfig.max_new_tokens` (기본 10240) | |
| `tools` | O | `systemPrompt` 텍스트 주입 | 에뮬레이션 |
| `tool_choice` | △ | 프롬프트 지시문 | **강제력 없음** (§4.5) |
| `top_p` / `top_k` / `repetition_penalty` | X (하드코딩) | `llmConfig`에 고정값 | 0.94 / 14 / 1.04 — 클라이언트 제어 불가 |
| `response_format` / `stream_options` / `n` / `stop` | X | — | 스키마 부재 |

### 2.2 응답 필드

| OpenAI 필드 | 지원 | 소스 | 비고 |
|---|:--:|---|---|
| `id` | △ | `f"chatcmpl-{int(time.time())}"` | **초 단위 해상도 — 충돌 가능** |
| `object` / `model` | O | | |
| `created` | X | — | 스키마 필드 자체가 없음 |
| `message.content` | △ | `data["content"]` | 에러 응답 시 조용히 `""` (§4.7) |
| `message.tool_calls` | △ | 정규식 파싱 | **파싱 실패 시 원문 노출** (§4.2, §4.3) |
| `finish_reason` | △ | `stop` / `tool_calls` | `length` 판정 불가 — 잘림을 알 수 없음 |
| `usage.*` | △ | `data["usage"]` | SCI Portal 응답에 해당 키가 없으면 **항상 0** |

### 2.3 스트리밍

| 항목 | 상태 |
|---|---|
| 실시간 토큰 전송 | **없음.** `stream()`이 `chat()`을 await 하여 전체 응답을 받은 뒤 SSE 청크로 쪼갬 |
| `delta.role="assistant"` 초기 청크 | 전송 (3사 중 유일) |
| `tool_calls` 델타 | 전송 (완성된 arguments를 한 번에) |
| 혼합 응답(content + tool_calls) | 처리됨 (REQ-054-009) |
| SSE 청크 `id`/`object`/`created`/`model` | **전부 없음** |
| SCI Portal `event_status: CHUNK/DONE` 파싱 | docstring에만 존재. **`isStream: False`이므로 사문(死文)** |

---

## 3. 아키텍처 등급 판정

| 계층 | 판정 | 근거 |
|---|:--:|---|
| 요청 변환 | **C** | 역할 정보가 구조에서 문자열 관례로 격하됨 |
| 응답 변환 | **D** | 단일 정규식 의존, 폴백 없음, 에러 미검증 |
| Tool Use 에뮬레이션 | **C-** | 개념 설계는 타당, 파서 견고성이 실사용 수준 미달 |
| 스트리밍 | **F** | 스트리밍이 아님 |
| 보안/데이터 무결성 | **D** | 민감어 마스킹이 tool arguments를 복원하지 않음 |
| 관측성 | **C** | 로그는 많으나 실패 원인 분류 불가 |

---

## 4. 문제점 분석 — Tool Use가 opencode에서 실패하는 6개 계층

### 4.0 문제점별 해결 현황 요약 (v1.1.111 검증 기준)

| 항목 ID | 심각도 | 문제점 요약 | 해결 여부 | 조치 근거 및 상태 요약 |
|---|:---:|---|:---:|---|
| **P0-N1** | P0 | 가짜 스트리밍 (`isStream: False` 하드코딩) | **미해결 — 보류** | SCI Portal `isStream=true` 실샘플 및 자격증명 부재로 추측 구현 위험. 별도 릴리스 분리 |
| **P0-N2** | P0 | 정규식 단일 형식 의존 | **해결됨** | 5단계 폴백 체인 (fence → XML → Harmony → bare JSON → 복구) 도입 (REQ-111-041) |
| **P0-N3** | P0 | Non-greedy 중괄호 매칭 (중첩 JSON 절단) | **해결됨** | `_scan_balanced_json` 중괄호 균형 스캐너 도입 (REQ-111-040) |
| **P1-N4** | P1 | 대화 구조 소실 (멀티턴 붕괴) | **해결됨** | uuid4 nonce 경계 분리, 마커 이스케이프, 시스템 프롬프트 규약 주입 (REQ-111-060~062) |
| **P1-N5** | P1 | `tool_choice="required"` 강제력 부재 | **해결됨** | 미호출 시 직전 응답 JSON 인용 1회 재요청 강제 루프 도입 (REQ-111-064) |
| **P1-N6** | P1 | 민감어 마스킹의 tool arguments 비복원 | **해결됨** | 펜스 스캐너 보호, arguments 재귀 unmask, 치환어 잔여 502 차단 (REQ-111-050~054) |
| **P1-N7** | P1 | 업스트림 에러 미검증 (조용한 빈 응답) | **해결됨** | code/resultCode 성공 allowlist 검증, 오류 시 502 ProviderError 발생 (REQ-111-069) |
| **P1-N8** | P1 | tool_call ID 충돌 및 O(n²) 역추적 | **해결됨** | `call_{uuid}` 독립 고유 ID 생성, tool_call_id 사전 1회 구축(O(1)) (REQ-111-044, 045) |
| **P1-N9** | P1 | 병렬 툴 호출 불가 | **해결됨** | 복수 펜스 파싱 지원, `parallel_tool_calls=False` 제어 지원 (REQ-111-063) |
| **P1-N10** | P1 | 잘림(truncation) 감지 불가 | **미해결 (보류)** | SCI Portal 응답에 finish_reason/길이 초과 메타데이터 부재 (미확인) |
| **P2-N11** | P2 | 시스템 프롬프트 비대화 | **해결됨** | tools SHA-256 키 기반 64개 LRU 프롬프트 메모이제이션 적용 (REQ-111-068) |
| **P2-N12** | P2 | 모델 레지스트리 결함 | **해결됨** | `model_registry.py` 분리, `glm5.2` 등록, `opencode.json` 메타데이터/limit 동기화 완료 |
| **P2-N13** | P2 | 패키지 경계 위반 (`src/` 경로 임포트) | **미해결 (보류)** | PyInstaller 독립 패키징 개편 시까지 현행 유지 |
| **P2-N14** | P2 | 공통 인프라 결함 | **해결됨** | OpenAI 규격 에러, `_scrub_secrets`, `public_message`, lifespan aclose, created 필드 완료 |

---

### P0-N1. 스트리밍이 가짜다 — `isStream: False` 하드코딩
- **해결 여부**: **미해결 — 보류**
- **사유**: SCI Portal 의 `isStream=true` 응답 실샘플을 확보하지 못했다. 자격증명이 없어 실제 형식(`event_status` CHUNK/DONE 의 정확한 필드 구성)을 검증할 수 없다. 검증 불가능한 추측 구현보다 보류가 낫다는 판단. 별도 릴리스로 분리한다.
- **필요한 선행 정보**: 스트리밍 실샘플 3종(텍스트/툴호출/에러), 에러 응답 스키마, usage 필드 제공 여부.

`stream()` (`genai_provider.py:377-380`):

```python
result = await self.chat(request)     # 전체 응답을 다 받을 때까지 블록
```

그리고 `_transform_request()`는 `"isStream": False`를 **무조건** 넣는다.

**영향**

1. opencode TUI가 첫 토큰까지 수십 초간 완전 무응답 → 사용자는 멈춘 것으로 판단.
2. 120B 모델이 긴 코드를 생성하면 `timeout=120.0`을 넘겨 요청 자체가 실패한다. 부분 결과조차 받지 못한다.
3. 리버스 프록시/로드밸런서의 idle timeout에 걸릴 수 있다.
4. `event_status: CHUNK/DONE` 파싱 로직(REQ-055-005)이 코드 주석에만 존재하고 실행되지 않는다.

이것이 **주력 Provider의 체감 품질을 가장 크게 떨어뜨리는 단일 결함**이다.

### P0-N2. 정규식이 단일 형식만 인식 — 실패 시 폴백 없음
- **해결 여부**: **해결됨**
- **조치 내용**: `_scan_balanced_json` 중괄호 균형 스캐너와 연계된 5단계 폴백 체인(fence → XML → Harmony → bare JSON → 제한적 복구)으로 대체됨 (REQ-111-041, TASK-GENAI-1). 처음 검증을 통과한 단계에서 툴 호출을 수집하고, 여러 펜스 및 JSON 배열 객체를 분실 없이 처리함.

```python
TOOL_CALL_PATTERN = re.compile(r'```tool_call\s*(\{.*?\})\s*```', re.DOTALL)
```

모델이 다음 중 **어느 하나로만 벗어나도 툴 호출이 전부 무시**되고, 사용자에게는 마크다운 원문이 그대로 노출된다.

| 실제로 흔한 모델 출력 | 현재 파서 |
|---|:--:|
| ` ```tool_call {...} ``` ` | 인식 |
| ` ```json {...} ``` ` | **실패** |
| ` ```tool_code {...} ``` ` | **실패** |
| 펜스 없이 `{"name": ..., "arguments": ...}` | **실패** |
| `<tool_call>{...}</tool_call>` | **실패** |
| ` ```tool_call ` 다음 줄에 설명문이 섞임 | **실패** |
| 여러 툴을 한 펜스 안에 JSON 배열로 출력 | **실패** |

gpt-oss 계열은 Harmony 포맷(`<|channel|>commentary to=functions.x`)으로 툴을 표현하는 경향이 있어, `tool_call` 펜스를 지시해도 이탈률이 낮지 않다.

### P0-N3. Non-greedy 중괄호 매칭 — 중첩 JSON에서 확정적으로 깨짐
- **해결 여부**: **해결됨**
- **조치 내용**: 문자열 및 백슬래시 홀짝을 인식하는 `_scan_balanced_json` 중괄호 균형 스캐너로 대체됨 (REQ-111-040, TASK-GENAI-1). JSON 경계를 정규식으로 추출하지 않고 괄호 균형과 문자열 리터럴을 추적하여 중첩 객체 arguments를 온전히 파싱함.

`\{.*?\}`는 **처음 만나는 `}` 에서 멈춘다.** opencode의 실제 툴 스키마는 거의 전부 중첩 객체를 갖는다.

```json
{"name": "edit", "arguments": {"filePath": "a.py", "oldString": "x", "newString": "y"}}
```

정규식이 잡아내는 부분:

```text
{"name": "edit", "arguments": {"filePath": "a.py", "oldString": "x", "newString": "y"}
                                                                                     ↑ 여기서 종료
```

→ 중괄호 불균형 → `json.JSONDecodeError` → `logger.warning` 후 **해당 툴 호출을 조용히 버린다**. `read` 같은 단순 스키마는 우연히 동작하고 `edit`/`write`/`bash`는 실패하므로, **"가끔 되는 것처럼 보이는" 가장 나쁜 형태의 버그**다.

> `\{.*\}`(greedy)로 바꾸는 것도 정답이 아니다 — 여러 툴 호출이 하나로 합쳐진다. **중괄호 균형 스캐너**가 필요하다 (IMP-N-02).

### P1-N4. 대화 구조 소실 — 멀티턴 에이전트 루프 붕괴
- **해결 여부**: **해결됨**
- **조치 내용**: 요청당 uuid4 nonce 역할 경계 분리, literal `\u005b` 패턴 마커 이스케이프, URL 인코딩 name 주입, systemPrompt 말미에 역할 규약 및 과거 도구 기록 재실행 금지 설명 주입, assistant call과 tool result ID 기반 병합 구현 (REQ-111-060~062, TASK-GENAI-3-4).

`contents`는 role 필드가 없는 **평문 문자열 배열**이다. 역할은 `[User Context]` / `[Assistant Context]` / `[Tool Result for X]` 라는 텍스트 관례로만 표현된다.

opencode 에이전트는 10~30턴을 돈다. 턴이 쌓일수록 모델은 (a) 자신의 과거 출력과 사용자 입력을 혼동하고, (b) 과거 턴의 `[Tool Call] read(...)` 텍스트를 **새로운 지시로 오인해 같은 툴을 재호출**한다. 무한 루프의 직접 원인이다.

또한 `[Tool Call]`, `[User Context]` 같은 마커가 **사용자 코드에 그대로 등장하면 구분이 불가능**하다 — 이스케이프나 구분자 처리가 전혀 없다.

### P1-N5. `tool_choice="required"`에 강제력이 없음
- **해결 여부**: **해결됨**
- **조치 내용**: `tool_choice="required"` 지정 시 모델 응답에 도구 호출이 없으면 직전 응답을 JSON 인용하여 1회 재요청하는 강제 루프 도입, 2회차 미호출 시 경고 후 stop 처리. `tool_choice="none"` 시 도구 실행 억제 (REQ-111-064, TASK-GENAI-3-4).

프롬프트에 `"You MUST use one of the tools above to respond."` 문장을 넣는 것이 전부다. 모델이 산문으로 답하면 `_parse_tool_calls()`가 `None`을 반환하고 `finish_reason="stop"`이 되어, opencode는 **툴이 필요한 상황에서 툴 없는 응답**을 받는다. 재시도/강제 파싱 루프가 없다.

### P1-N6. 민감어 마스킹이 tool arguments를 복원하지 않음 — 데이터 손상
- **해결 여부**: **해결됨**
- **조치 내용**: GENAI 내부 펜스 스캐너로 코드 블록을 보호하고, 응답 원문 복원 후 파싱된 arguments의 JSON 키/문자열/중첩 객체까지 재귀 unmask 복원 적용. 치환어 잔여 감지 시 ProviderError(502) 차단. `GENAI_SENSITIVE_FILTER=0` 설정 권장 및 환경변수 토글 지원 (REQ-111-050~054, TASK-GENAI-3-4).

```python
# 전송 전
payload["contents"] = self.sensitive_filter.mask_contents(payload["contents"])
payload["systemPrompt"] = self.sensitive_filter.mask_system_prompt(payload["systemPrompt"])

# 수신 후
content = self.sensitive_filter.unmask(content)     # ← content 에만 적용
```

`content`는 복원되지만, 그 뒤 `_parse_tool_calls()`가 만드는 `tool_calls[].function.arguments`는 **복원 이후의 텍스트에서 추출되므로 일견 안전해 보인다.** 그러나 실제 위험은 **역방향**이다.

1. 사용자 코드에 `password`, `secret` 같은 단어가 있으면 마스킹되어 모델에게 전달된다.
2. 모델은 마스킹된 식별자를 그대로 유지해 코드를 재작성한다.
3. `unmask()`는 **정확히 치환어와 일치하는 토큰만** 되돌린다. 모델이 대소문자를 바꾸거나(`_apply_case` 범위 밖), 식별자에 붙여 쓰거나(`myPasswordVar`), 분할하면 **복원되지 않는다.**
4. 그 결과 `write`/`edit` 툴의 arguments에 **치환어가 그대로 남은 코드가 파일에 기록된다.**

되돌릴 수 없는 소스 손상이며, 최종 목표(코드 편집)와 정면으로 충돌한다.

### P1-N7. 업스트림 에러 미검증 — 조용한 실패
- **해결 여부**: **해결됨**
- **조치 내용**: 응답 본문 파싱 시 JSON 객체/문자열 content 요구 및 code/resultCode 성공 allowlist(0, 200, "0", "200", "ok", "success") 엄격 적용. 알 수 없거나 에러 코드는 조용한 빈 응답 대신 ProviderError(502) 및 public_message 반환 (REQ-111-069, TASK-GENAI-3-4).

```python
content = data.get("content", "")
```

SCI Portal이 HTTP 200과 함께 `{"resultCode": "E001", "message": "..."}` 같은 에러 바디를 반환하면 `content`는 `""`가 되고, 프록시는 **정상 응답으로 위장한 빈 답변**을 돌려준다. opencode는 빈 assistant 메시지를 받고 루프를 계속 돈다. `resultCode` / `message` / `error` 키를 전혀 확인하지 않는다.

### P1-N8. tool_call ID 충돌 및 O(n²) 역추적
- **해결 여부**: **해결됨**
- **조치 내용**: `call_{uuid.uuid4().hex[:24]}` 독립 고유 ID 생성으로 타임스탬프 기반 충돌 원천 차단 (REQ-111-044). 요청 시작 시 `tool_call_id → tool_name` 매핑 사전 1회 구축으로 O(1) 처리 (REQ-111-045, TASK-GENAI-1).

```python
id=f"genai-tc-{int(time.time())}-{i}"
```

초 단위 타임스탬프 + 응답 내 인덱스. 같은 초에 두 번의 응답이 오면 **ID가 충돌**하고, opencode가 tool_call과 tool_result를 잘못 짝지을 수 있다.

역방향으로, `tool` 메시지의 이름을 찾는 코드는 매 tool 메시지마다 **전체 메시지 배열을 재순회**한다 (`genai_provider.py:236-244`). 30턴 대화에서 불필요한 O(n²)다.

### P1-N9. 병렬 툴 호출 불가
- **해결 여부**: **해결됨**
- **조치 내용**: 복수 독립 툴 호출 펜스 파싱 지원, `parallel_tool_calls=False` 시 파서에서 첫 유효 호출만 남기는 제어 지원 (REQ-111-063, TASK-GENAI-3-4).

프롬프트에 `"When calling a tool, output ONLY the tool_call block, nothing else."` 라고 지시하므로, 파서는 다중 매칭을 지원하지만 **모델은 한 번에 하나만 출력**한다. opencode가 "파일 3개를 읽어라"를 한 턴에 처리하지 못하고 3턴을 소모한다. 지연·비용·컨텍스트 낭비가 3배다.

### P1-N10. 잘림(truncation) 감지 불가
- **해결 여부**: **미해결 (보류)**
- **사유**: SCI Portal 업스트림 응답에서 `max_new_tokens` 초과 여부를 알리는 메타데이터(finish_reason 규격 등)가 확인되지 않았다. 공식 스키마 확인 전까지 finish_reason="length" 판정 불가.

`finish_reason`은 `stop` 또는 `tool_calls` 두 값만 나온다. `max_new_tokens`(기본 10240)에 걸려 응답이 잘려도 `stop`이 반환된다. opencode는 **잘린 코드를 완성본으로 간주해 파일에 쓴다.**

### P2-N11. 시스템 프롬프트 비대화
- **해결 여부**: **해결됨**
- **조치 내용**: tools 배열 canonical JSON SHA-256 키 기반 프로세스 단위 64개 LRU 프롬프트 메모이제이션 적용 (REQ-111-068, TASK-GENAI-3-4).

opencode는 통상 10개 이상의 툴을 등록한다. `_build_tools_prompt()`는 매 요청 **모든 툴의 이름·설명·전체 파라미터 목록**을 systemPrompt에 재생성해 붙인다. 수천 토큰이 매 턴 반복 전송되며, SCI Portal에 프롬프트 캐싱이 있는지도 확인되지 않았다.

### P2-N12. 모델 레지스트리 결함
- **해결 여부**: **해결됨**
- **조치 내용**: `model_registry.py` 분리, `MODEL_METADATA` 단일 진실 소스화, `SUPPORTED_MODELS` 중복 제거, `genai/glm5.2` 등록 및 `opencode.json` 동기화 완료 (TASK-DOC, REQ-111-045~047).

- `glm 5.2 512k` 미등록 (§0.1)
- `SUPPORTED_MODELS`에 `genai/gpt-oss-120B-medium` **중복 키**
- `opencode.json`의 `genai/gpt-oss-120B-medium` `limit.output`이 **4096**인데 프록시 기본값은 **10240** → 불일치
- `router.py`가 알 수 없는 하위 모델명을 검증하지 않음 (`genai/anything`이 그대로 업스트림 전송됨)

### P2-N13. 패키지 경계 위반
- **해결 여부**: **미해결 (보류)**
- **사유**: PyInstaller 독립 패키징 개편 시까지 `src.sensitive_filter` 경로 임포트 현행 유지.

```python
_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))
from src.sensitive_filter import SensitiveWordFilter
```

`ai-proxy`가 상위 프로젝트의 `src/`를 런타임에 경로 주입해 임포트한다. `ai-proxy`를 독립 배포하거나 PyInstaller로 빌드하면 깨진다 (`docs/requirements/FSD_v1.0.065_pyinstaller_build.md` 참조).

### P2-N14. 공통 인프라 결함
- **해결 여부**: **해결됨**
- **조치 내용**:
  1. **자격증명 평문 로깅 완전 제거**: `proxy_server.py`의 `authorization` 및 `Expected: Bearer` 평문 로그 삭제, `hmac.compare_digest` 적용, `_scrub_secrets` 및 `public_message` 도입으로 민감정보 유출 차단 (REQ-111-012, REQ-111-020).
  2. **OpenAI 규격 에러 응답 통일**: 최상위 `error` 객체(`message`, `type`, `code`) 및 문자열 에러 코드 정규화 (REQ-111-011).
  3. **리소스 안전 종료**: FastAPI lifespan 도입 및 `BaseProvider.aclose()`로 클라이언트 종료 보장 (REQ-111-013).
  4. **표준 타임스탬프 필드**: `/v1/models` 및 `/health`에 `created` 정수 epoch 추가 (REQ-111-015).
  5. **SSE 표준 청크 규격**: `BaseProvider._chunk` 공통 헬퍼로 `object: "chat.completion.chunk"` 및 표준 스키마 준수 (REQ-111-030).

Claude/Gemini 문서와 동일: 에러 응답 `{"detail": {...}}` 래핑, SSE 청크 필수 필드 누락, `AsyncClient` 미종료, API 키 평문 로깅, `created` 필드 부재, 스트리밍 재시도 부재.

---

## 5. 개선점 도출 — Conversational 기반 Tool Use 재설계

### 5.1 설계 원칙

1. **파싱은 관대하게, 프롬프트는 엄격하게** (Postel의 법칙). 모델을 신뢰하지 않는다.
2. **구조 우선**. 역할·경계를 텍스트 관례가 아닌 명시적 구분자와 검증으로 표현한다.
3. **실패를 관측 가능하게**. 조용한 드랍을 전부 제거하고 실패 사유를 분류·계측한다.
4. **점진 적용**. 모든 개선은 환경변수 토글로 A/B 비교가 가능해야 한다.

### 5.2 개선 항목

#### IMP-N-01 (P0) 진짜 스트리밍 도입

`isStream: True`로 SCI Portal 스트리밍을 사용하고 `event_status: CHUNK/DONE`을 파싱한다. Tool Use와 양립시키기 위해 **2모드 전략**을 쓴다.

| 조건 | 모드 | 동작 |
|---|---|---|
| `request.tools` 없음 | **패스스루 스트리밍** | CHUNK 도착 즉시 `delta.content`로 방출. 첫 토큰 지연 최소 |
| `request.tools` 있음 | **감시 스트리밍** | CHUNK를 버퍼에 누적하면서, 툴 호출 개시 마커(` ```tool_call `, `{"name"`, `<tool_call>`)가 나타나기 전까지는 텍스트를 즉시 방출. 마커 등장 시 방출을 중단하고 끝까지 버퍼링 후 파싱 |

감시 스트리밍은 "툴을 안 부르는 응답"에서 스트리밍 이점을 온전히 얻으면서, 툴 호출 시에만 버퍼링 비용을 낸다. `timeout`도 스트리밍 전환으로 read timeout 기반으로 바뀌어 장문 생성 실패가 해소된다.

#### IMP-N-02 (P0) 계층형 Tool Call 파서 (`ToolCallExtractor`)

단일 정규식을 **폴백 체인**으로 교체한다. 앞 단계가 실패하면 다음 단계로 내려간다.

```text
Stage 1  펜스 태그 매칭      ```tool_call / ```tool_code / ```json / ```function_call
Stage 2  XML 태그 매칭        <tool_call>...</tool_call>, <function_call>...</function_call>
Stage 3  Harmony 포맷         <|channel|>commentary to=functions.<name> ... (gpt-oss 계열)
Stage 4  베어 JSON 스캔       텍스트 내 {"name": ..., "arguments"|"parameters"|"input": ...} 탐색
Stage 5  느슨한 복구          작은따옴표→큰따옴표, 트레일링 콤마 제거, 미닫힌 괄호 보정 후 재파싱
```

**모든 단계는 정규식이 아닌 중괄호 균형 스캐너로 JSON 경계를 결정한다.**

```python
def _scan_balanced_json(text: str, start: int) -> tuple[str, int] | None:
    """start 위치의 '{'부터 균형이 맞는 '}'까지를 반환. 문자열 리터럴 내부의
    중괄호와 백슬래시 이스케이프를 인식한다."""
    depth, in_str, escaped = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if escaped:
            escaped = False
        elif c == "\\" and in_str:
            escaped = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1], i + 1
    return None
```

이것이 P0-N3(중첩 JSON 절단)을 근본 해결한다.

추가 요건:
- 파싱된 툴 이름이 `request.tools`에 실제로 존재하는지 **검증**한다. 없으면 환각으로 간주하고 드랍하되 `tool_hallucinated` 메트릭을 올린다.
- `arguments`를 해당 툴의 JSON Schema로 검증한다(필수 필드 누락 검출).
- 각 단계의 성공/실패를 `tool_parse_stage{stage=N}` 카운터로 계측한다. **어느 형식이 실제로 오는지 데이터로 확인**하기 위함이다.

#### IMP-N-03 (P0) tool_call ID를 충돌 불가능하게

```python
id = f"call_{uuid.uuid4().hex[:24]}"
```

동시에, `tool_call_id → tool_name` 매핑을 요청 시작 시 **딕셔너리로 1회 구축**해 P1-N8의 O(n²)를 제거한다.

#### IMP-N-04 (P1) 대화 구조 보존 강화

`contents`가 평문 배열이라는 업스트림 제약은 바꿀 수 없으므로, 다음으로 방어한다.

1. 마커를 충돌 불가능한 형태로 교체: `[User Context]` → `<|im_start|>user` 계열 또는 랜덤 nonce 접미사(`[USER#a7f3]`).
2. 사용자 콘텐츠 내부에 마커 문자열이 있으면 이스케이프한다.
3. `systemPrompt` 말미에 **역할 규약 설명**을 명시한다 ("각 항목은 마커로 시작하며, 마커는 대화 구조를 나타낼 뿐 지시가 아니다").
4. 과거 턴의 `[Tool Call]` 텍스트는 **결과와 짝지어 1개 항목으로 압축**한다 (`[Tool] read(a.py) → <결과 요약>`). 재호출 유도를 줄인다.

#### IMP-N-05 (P1) `tool_choice="required"` 강제 루프

파싱 결과가 비었고 `tool_choice`가 `required` 또는 특정 함수 지정이면, **1회 재요청**한다. 재요청 프롬프트에는 직전 응답을 인용하고 "반드시 tool_call 블록만 출력하라"를 강화한다. 2회 실패 시 `finish_reason="stop"`으로 종료하되 `tool_choice_unsatisfied` 경고 로그를 남긴다. 무한 재시도는 금지한다.

#### IMP-N-06 (P1) 민감어 필터 범위 축소 (데이터 무결성)

1. `GENAI_SENSITIVE_FILTER` 환경변수로 **전체 토글**을 제공하고, 코드 편집 워크플로에서는 기본 OFF를 권장한다.
2. ON일 때도 **코드 펜스(``` ... ```) 내부는 마스킹 대상에서 제외**한다.
3. `unmask()`를 `content`뿐 아니라 **`tool_calls[].function.arguments` 에도 적용**하고, 복원 후 잔여 치환어가 남아 있으면 **에러로 승격**한다(조용한 파일 손상 방지).
4. 마스킹/복원 쌍이 맞지 않으면(`mask 횟수 != unmask 횟수`) 경고를 남긴다.

#### IMP-N-07 (P1) 업스트림 응답 검증

```python
if "content" not in data:
    raise ProviderError(f"SCI Portal returned no content: {json.dumps(data)[:500]}", 502)
result_code = data.get("resultCode") or data.get("code")
if result_code and str(result_code).upper() not in ("0", "00", "OK", "SUCCESS"):
    raise ProviderError(f"SCI Portal error {result_code}: {data.get('message')}", 502)
```

실제 에러 스키마는 SCI Portal 응답 샘플로 확정한다(§7 선행 확인 항목).

#### IMP-N-08 (P1) 병렬 툴 호출 허용

프롬프트 규칙을 다음으로 교체한다.

```text
- 여러 도구를 동시에 호출해야 하면, tool_call 블록을 연달아 여러 개 출력하라.
- 각 블록은 독립된 ```tool_call 펜스를 사용한다.
- 도구 호출 블록 외의 설명 문장은 출력하지 않는다.
```

파서는 이미 다중 매칭을 지원하므로 프롬프트 변경만으로 활성화된다. `parallel_tool_calls=false` 요청 시에는 첫 호출만 남긴다.

#### IMP-N-09 (P1) 잘림 감지

`llmConfig.max_new_tokens` 대비 응답 토큰 수, 또는 SCI Portal이 제공하는 종료 사유 필드를 확인해 `finish_reason="length"`를 반환한다. 필드가 없으면 **휴리스틱**(응답이 `max_new_tokens` 근처이고 코드 펜스가 닫히지 않음)으로라도 판정한다.

#### IMP-N-10 (P2) 툴 프롬프트 캐싱

동일한 `tools` 배열에 대해 생성한 프롬프트 텍스트를 **해시 키로 메모이즈**한다. 생성 비용은 줄지만 전송량은 그대로이므로, SCI Portal의 프롬프트 캐싱 지원 여부를 확인해 지원 시 캐시 지시자를 함께 전달한다.

#### IMP-N-11 (P2) 패키지 경계 정리

`sensitive_filter.py`를 `ai-proxy/` 내부로 복사하거나 공용 패키지로 승격해 `sys.path` 주입을 제거한다.

#### IMP-N-12 (P2) 모델 레지스트리 정비

```python
MODEL_REGISTRY = {
    "genai/gpt-oss-120B-medium": {
        "name": "Samsung SCI Portal GPT-OSS 120B Medium",
        "context": 200000, "max_output": 10240,
    },
    # TODO: 실제 modelIds 확정 후 등록
    "genai/<glm-5.2-512k-model-id>": {
        "name": "GLM 5.2 (512k context)",
        "context": 524288, "max_output": None,   # TBD
    },
}
```

- 중복 키 제거.
- `opencode.json`을 이 레지스트리에서 **생성**하거나, 최소한 CI에서 일치를 검증한다.
- 등록되지 않은 하위 모델명은 400으로 거절한다.

#### IMP-N-13 (P2) 관측성

`GENAI_TOOL_TRACE=1`일 때 요청별로 다음을 `.omc/logs/` 또는 `logs/`에 JSONL로 남긴다.

```json
{"ts": "...", "request_id": "...", "tools_count": 12, "raw_response_len": 3401,
 "parse_stage": 4, "tool_calls_found": 2, "hallucinated": 0,
 "schema_errors": [], "finish_reason": "tool_calls", "latency_ms": 8120}
```

이 로그가 있어야 "어떤 형식으로 모델이 툴을 부르는가"를 데이터로 판단해 파서를 좁힐 수 있다.

---

## 6. 목표 상태 (재설계 후 흐름)

```text
opencode ──▶ /v1/chat/completions (stream=true, tools=[...])
                   │
                   ▼
        _transform_request()
          ├ contents: nonce 마커 + 이스케이프 + 툴 이력 압축
          ├ systemPrompt: 병렬 호출 허용 규약 + 툴 정의(메모이즈)
          └ isStream: TRUE
                   │
                   ▼
        SCI Portal SSE (event_status: CHUNK ... DONE)
                   │
        ┌──────────┴───────────┐
        │ tools 없음            │ tools 있음
        ▼                       ▼
  즉시 delta.content 방출   툴 마커 탐지 전까지 즉시 방출
                            마커 탐지 후 버퍼링
                                    │
                                    ▼
                        ToolCallExtractor (5단계 폴백 + 균형 스캐너)
                                    │
                        ├ 툴 이름 검증 (환각 차단)
                        ├ JSON Schema 검증
                        ├ unmask(arguments) + 잔여 검사
                        └ uuid4 기반 call_id 부여
                                    │
                                    ▼
              OpenAI SSE 청크 (id/object/created/model 완비)
                                    │
                                    ▼
                                opencode
```

---

## 7. 검증 방법 및 선행 확인 항목

### 7.1 명령

```bash
python -m py_compile ai-proxy/providers/genai_provider.py ai-proxy/models.py ai-proxy/router.py
pytest tests/ -k "genai or toolcall or provider_contract"
python ai-proxy/test_toolcall.py          # 프록시 기동 상태에서 수동 실행
```

### 7.2 수용 기준 (Acceptance Criteria)

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-N-01 | 중첩 객체 arguments를 갖는 `edit` 툴 호출 | arguments가 절단 없이 완전 파싱 |
| TC-N-02 | 모델이 ` ```json ` 펜스로 툴 출력 | Stage 1 폴백으로 정상 인식 |
| TC-N-03 | 펜스 없이 베어 JSON 출력 | Stage 4로 정상 인식 |
| TC-N-04 | 한 턴에 툴 3개 호출 | `tool_calls` 3개, index 0/1/2 |
| TC-N-05 | `stream=true`, tools 없음 | 첫 청크가 3초 이내 도착 |
| TC-N-06 | `stream=true`, tools 있고 산문 응답 | 텍스트가 실시간 스트리밍됨 |
| TC-N-07 | 존재하지 않는 툴 이름 출력 | 드랍 + `tool_hallucinated` 계측, 원문 미노출 |
| TC-N-08 | 코드에 `password` 포함한 파일 편집 | 파일에 치환어가 남지 않음 |
| TC-N-09 | SCI Portal이 200 + 에러 바디 반환 | 빈 응답이 아닌 명시적 502 + 원인 메시지 |
| TC-N-10 | `tool_choice="required"`인데 산문 응답 | 1회 재요청 후 툴 호출 또는 명시적 경고 |
| TC-N-11 | `max_tokens=64`로 긴 코드 요청 | `finish_reason == "length"` |
| TC-N-12 | 15턴 에이전트 루프 (읽기→편집→테스트) | 동일 툴 재호출 루프 없이 완료 |
| TC-N-13 | 동시 요청 2건 | tool_call ID 충돌 없음 |
| TC-N-14 | opencode E2E: "calculator.py에 함수 추가하고 pytest 실행" | 사람 개입 없이 완료 |

**TC-N-14가 최종 수용 기준이다.**

### 7.3 착수 전 확인 필요 (사람/환경 의존)

| # | 항목 | 필요 이유 |
|---|---|---|
| 1 | `glm 5.2 512k`의 실제 `modelIds` 문자열 | 레지스트리 등록 (§0.1) |
| 2 | 해당 모델의 context / max_output 한도 | `opencode.json` 및 `llmConfig` 정합 |
| 3 | SCI Portal 스트리밍 응답 실샘플 (`isStream: true`) | IMP-N-01 파서 구현 |
| 4 | SCI Portal 에러 응답 스키마 (`resultCode` 등) | IMP-N-07 |
| 5 | SCI Portal `usage` 필드 제공 여부 | 토큰 계측 가능성 판단 |
| 6 | SCI Portal 프롬프트 캐싱 지원 여부 | IMP-N-10 |
| 7 | 개발용 자격증명 (`YOUR_CLIENT_SECRET`) | E2E 테스트 실행 |

---

## 8. 참조

- `docs/openai-compatible/CLAUDE_v1.1.111_claude-provider.md`
- `docs/openai-compatible/GEMINI_v1.1.111_gemini-provider.md`
- `docs/openai-compatible/ORCHESTRATION_v1.1.111_tooluse-opencode.md`
- `docs/openai-compatible/GUIDE_v1.0.001_openai-compatible-guide.md`
- `docs/requirements/FSD_v1.0.054_genai-provider-toolcall_v2.md`
- `docs/requirements/FSD_v1.0.055_genai-provider-endpoint-fix.md`
- `docs/requirements/FSD_v1.0.058_sensitive-word-filter.md`
- `docs/requirements/BUG_v1.0.057_genai-content-string-validation.md`
