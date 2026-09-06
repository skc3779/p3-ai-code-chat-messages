# REL v1.1.111 — ai-proxy OpenAI-Compatible 호환성 강화 및 GenAI Tool Use 재설계

- **릴리즈 대상**: `ai-proxy` (OpenAI 호환 로컬 프록시 서버)
- **브랜치**: `feat/proxy-v1.1.111`
- **기준 커밋**: `05a7ca9`
- **작성일**: 2026-09-07
- **요구 명세서**: `docs/openai-compatible/ORCHESTRATION_v1.1.111_tooluse-opencode.md`
- **최종 목표**: `opencode` CLI로 프로젝트 폴더 내 소스코드 생성 / 편집 / 실행 / 테스트가 원활히 수행되는 것

---

## 1. 요약

세 Provider(Claude / Gemini / GenAI)의 OpenAI 호환성을 분석해 결함 40여 건을 도출하고, AI 오케스트레이션 방식으로 수정했다. **BLOCKER 1건, MAJOR 14건, MINOR 13건**을 해소했으며 신규 테스트 **368건**을 추가했다.

가장 중요한 성과는 두 가지다.

1. **주력 GenAI Provider의 Tool Use 파서 재설계.** 기존 단일 정규식이 중첩 JSON에서 확정적으로 깨져 `edit` / `write` / `bash` 툴 호출이 조용히 버려지고 있었다. 중괄호 균형 스캐너와 5단계 폴백 체인으로 대체했다.
2. **업스트림 자격증명 유출 차단.** 업스트림 에러 본문이 클라이언트 응답과 로그에 그대로 노출되던 경로를 제거했다.

### 테스트 결과

| 시점 | 통과 | 실패 |
|---|---:|---:|
| 기준선 (`05a7ca9`) | 994 | 22 |
| 릴리즈 (`feat/proxy-v1.1.111`) | **1362** | 22 |

- **회귀 0건.** 실패 22건은 이 브랜치 이전부터 존재하던 결함으로 `ai-proxy`와 무관하다 (§6).
- 실패 테스트의 파일별 구성이 기준선과 정확히 일치함을 매 단계 확인했다.

### 변경 규모

```text
 ai-proxy/models.py                    |  72 +-
 ai-proxy/providers/base.py            | 370 +++++-
 ai-proxy/providers/claude_provider.py | 781 ++++++++++++-----
 ai-proxy/providers/gemini_provider.py | 484 +++++++---
 ai-proxy/providers/genai_provider.py  | 813 +++++++++++++-----
 ai-proxy/proxy_server.py              | 321 +++++--
 ai-proxy/router.py                    |  26 +-
 opencode.json                         |  17 +-
 9 files changed, 2346 insertions(+), 542 deletions(-)

신규 파일:
 ai-proxy/model_registry.py
 tests/ 11개 파일 (test_base_retry, test_claude_provider, test_error_contract,
   test_gemini_provider, test_genai_conversation, test_genai_integrity,
   test_genai_toolparse, test_model_registry, test_models_schema,
   test_request_param_contract, test_sse_contract)
 docs/openai-compatible/ 분석·명세 문서 4종
```

REQ 번호 `REQ-111-001` ~ `REQ-111-069` (57개) 부여.

---

## 2. 주요 변경 사항

### 2.1 BLOCKER — 업스트림 자격증명 유출 차단

`_retry_on_429()`가 업스트림 응답 본문을 `ProviderError` 메시지에 그대로 담고, `proxy_server`가 이를 `error.message`로 클라이언트에 반환하고 있었다. GenAI 스트리밍은 SSE `error.message`로도 내보냈다.

**조치**
- `ProviderError`에 `public_message`(클라이언트용)와 내부 상세를 분리. 요청별 `request_id`로 운영자가 로그와 응답을 상관 가능
- `_scrub_secrets()` 신설 — 환경변수 실제 값 리터럴 + `sk-ant-*` / `AIza*` / `Bearer *` / `x-api-key` 패턴 마스킹
- SSE 에러 경로에도 동일 적용, `_error_chunk`에 누락돼 있던 `code` 필드 추가

**검증** — 업스트림이 HTTP 500과 함께 `x-api-key=sk-ant-SECRET123; host=db.private`를 반환해도 클라이언트에는 `Upstream provider error (HTTP 500)`만 도달. `LOG_PAYLOAD=0`에서 사용자 메시지와 키가 로그에 남지 않음. (`tests/test_base_retry.py`)

### 2.2 GenAI — Tool Use 파서 재설계 (최우선 P0)

기존 파서:

```python
TOOL_CALL_PATTERN = re.compile(r'```tool_call\s*(\{.*?\})\s*```', re.DOTALL)
```

**결함 1 — 중첩 JSON 절단.** non-greedy `\{.*?\}`가 처음 만나는 `}`에서 멈춘다. opencode의 실제 툴 스키마는 거의 전부 중첩 객체다.

```json
{"name":"edit","arguments":{"filePath":"a.py","oldString":"x","newString":"y"}}
```

안쪽 첫 `}`에서 잘려 중괄호 불균형 → `JSONDecodeError` → 툴 호출을 조용히 드랍. `read` 같은 평면 스키마는 우연히 동작하고 `edit` / `write` / `bash`는 실패하므로 **"가끔 되는 것처럼 보이는" 형태**로 나타났다.

**결함 2 — 단일 형식만 인식.** 모델이 ` ```json `, 베어 JSON, `<tool_call>` 태그, Harmony 포맷 중 하나로 이탈하면 툴 호출이 전부 무시되고 마크다운 원문이 사용자에게 노출됐다.

**조치**
- `_scan_balanced_json()` — 문자열 리터럴과 백슬래시 이스케이프를 인식하는 중괄호 균형 스캐너. 정규식으로 JSON 경계를 결정하지 않는다
- 5단계 폴백 체인: 펜스 태그 → XML 태그 → Harmony 포맷 → 베어 JSON 스캔 → 느슨한 복구
- 툴 이름을 `request.tools`와 대조 검증(환각 드랍), arguments를 JSON Schema로 검증
- 복구 결과가 스키마 검증을 통과하지 못하면 폐기 — 잘못된 arguments로 파일을 손상시키는 것보다 실패가 낫다
- tool_call ID를 `call_{uuid4}`로 변경 (기존 초 단위 타임스탬프는 동시 요청 시 충돌)
- `tool_call_id → tool_name` 매핑을 dict로 1회 구축 (O(n²) 제거)

**검증** (실측)

| 케이스 | 결과 |
|---|---|
| 중첩 객체 arguments | 3개 키 온전히 파싱 |
| 문자열 안의 중괄호 `if (x) { y(); }` | 정상 |
| 이스케이프된 따옴표 | 정상 |
| ` ```json ` / 베어 JSON / `<tool_call>` | 전부 인식 |
| 병렬 툴 호출 2개 | 2건 분리 |
| 환각 툴 이름 | 드랍, 원문 미노출 |
| 미닫힌 중괄호 | 크래시 없이 거부 |

### 2.3 GenAI — 데이터 무결성 및 대화 구조

**민감어 필터로 인한 소스 손상 차단.** `password` 같은 단어가 마스킹된 채 모델에 전달되고, `unmask()`가 정확히 일치하는 토큰만 되돌리므로 치환어가 남은 코드가 파일에 기록될 수 있었다.

- `GENAI_SENSITIVE_FILTER` 토글 도입
- 코드 펜스 내부는 마스킹 제외
- `tool_calls[].function.arguments`에도 `unmask` 적용
- 복원 후 잔여 치환어가 남으면 `ProviderError`로 승격 — 조용한 파일 손상보다 명시적 실패

**대화 구조 보존.** `contents`가 role 없는 평문 배열이라 긴 에이전트 루프에서 모델이 과거 툴 호출 텍스트를 새 지시로 오인해 무한 루프에 빠졌다.

- 요청별 nonce 마커(`[USER#<nonce> name=...]`), 사용자 콘텐츠 마커 이스케이프
- 툴 호출과 결과를 1개 항목으로 압축, 짝 없는 결과는 `Unpaired tool result:`로 보존
- `systemPrompt`에 "완료된 이력이지 재호출 요청이 아니다" 규약 명시
- 병렬 툴 호출 허용, `tool_choice="required"` 미충족 시 1회만 재요청 (무한 재시도 금지)
- 업스트림 200 + 에러 바디를 조용한 빈 응답으로 흘리지 않고 `ProviderError(502)`

### 2.4 Claude Provider

- **메시지 시퀀스 정규화** — 빈 content 제거, 연속 동일 role 병합, 선두 assistant 처리. Anthropic의 role 교대·비어있지 않은 text 블록 요구를 위반해 400으로 에이전트 루프가 중단되던 문제 해소. tool_use↔tool_result 짝과 호출 순서는 불변식으로 보존
- `finish_reason` 매핑 테이블 (`max_tokens → length` 등). 기존에는 미지의 값이 통과해 opencode가 **잘린 코드를 완성본으로 오인**했다
- 멀티모달 패스스루 (base64 / URL 이미지)
- 스트림 내 `error` 이벤트 처리, 첫 바이트 전 429/500/529 재시도
- `max_tokens` 모델별 기본값 (`opencode.json`과 단일 진실 소스)
- 스트리밍 usage 전달, 다중 system 메시지 누적

### 2.5 Gemini Provider

- **스트리밍 tool_call 인덱스 버그 수정** — `enumerate`가 청크 내 위치를 세어 청크마다 하나씩 오는 툴 호출이 전부 `index=0`이 되고 서로 덮어써졌다. 스트림 전체 누적 카운터로 교체. Provider가 싱글톤이므로 상태는 스트림 지역에 유지
- 빈 `choices` / 200 에러 바디 방어 (기존 `IndexError` → 원인 불명 502)
- `finish_reason` 화이트리스트 매핑 (`SAFETY` → `content_filter` 등)
- `GEMINI_PASSTHROUGH=1` 무손실 모드, 업스트림 `created` 보존
- `tools` 직렬화 `exclude_none=True`, 스트림 종결 보정, 스트리밍 재시도

### 2.6 공통 인프라

- **요청 스키마 확장** — `top_p`, `stop`, `n`, `seed`, `presence_penalty`, `frequency_penalty`, `response_format`, `stream_options`, `parallel_tool_calls`, `user`, `logprobs`, `top_logprobs`. OpenAI 스펙 기준 범위 검증 포함
- **미지원 파라미터 경고** — 조용한 드랍을 제거. Provider별 `SUPPORTED_PARAMS` 선언 후 요청당 1회 경고
- **SSE 청크 통일** — `_chunk()` 공통 빌더. 세 Provider 모두 `id`/`object`/`created`/`model` 필수 필드, 초기 `role` 청크, 종료 시 `finish_reason` + `[DONE]` 정확히 1회. 업스트림이 `[DONE]`을 주지 않아도 프록시가 보정
- **OpenAI 규격 에러 응답** — `{"detail": {...}}` 래핑 제거, 최상위 `error` 키. Starlette 404/405와 미처리 500도 포함
- **보안** — 인증 헤더·서버 키 로깅 제거, `hmac.compare_digest` (bytes 비교로 비-ASCII 헤더가 500이 아닌 401), `LOG_PAYLOAD`/`LOG_CHUNK` 게이팅, 로그 인젝션 방어(ASCII 제어문자 + U+2028/2029/0085/202A-E/2066-9 + Cf 카테고리)
- **리소스** — FastAPI `lifespan`에서 `AsyncClient.aclose()`, 이미 생성된 인스턴스만 정리, `try/finally` 보장
- **`model_registry.py` 신설** — `claude_provider` ↔ `router` 순환 import 해소. `router`는 하위 호환 re-export 유지
- **`anyio.sleep` 전환** — `asyncio.sleep`은 trio 이벤트 루프에서 `RuntimeError: no running event loop`를 일으킨다

---

## 3. 미완료 항목

### 3.1 TASK-GENAI-2 — 진짜 스트리밍 (보류)

**현황**: GenAI Provider의 `stream()`은 여전히 `chat()`을 전량 버퍼링한 뒤 SSE 청크로 분해한다. `isStream: False`가 하드코딩되어 있다.

**영향**: opencode TUI가 첫 토큰까지 무응답. 120B 모델의 장문 생성이 `timeout=120.0`을 넘기면 부분 결과조차 받지 못한다.

**보류 사유**: SCI Portal의 `isStream: true` 응답 실샘플을 확보하지 못했다. 자격증명(`YOUR_CLIENT_SECRET`)이 없어 `event_status: CHUNK/DONE`의 정확한 필드 구성을 검증할 수 없다. 검증 불가능한 추측 구현보다 보류가 낫다고 판단했다. 요구 명세서 §7 리스크 완화책에 사전 합의된 처리다.

**재개에 필요한 선행 정보**
1. SCI Portal 스트리밍 실샘플 3종 (텍스트 / 툴 호출 / 에러)
2. 에러 응답 스키마 (`resultCode` 등 키 이름)
3. `usage` 필드 제공 여부
4. 프롬프트 캐싱 지원 여부

### 3.2 TASK-E2E — opencode 실사용 검증 (범위 제외)

사용자 결정으로 이번 릴리즈 범위에서 제외됐다(G3까지). SCI Portal 자격증명이 있어야 무인 완주가 가능하다. 요구 명세서의 최종 수용 기준 **A6**(실패 테스트 자가 수정 15턴 루프)는 **미검증** 상태다.

즉 이번 릴리즈는 **계약 수준의 정합성은 확보했으나, opencode를 통한 실제 코드 생성/편집/실행 루프는 아직 실증되지 않았다.**

### 3.3 Claude Prompt Caching (보류)

`cache_control` 주입 로직은 비용 최적화 후속 마일스톤으로 분리했다. 현재 opencode 에이전트는 매 턴 전체 대화와 툴 정의를 재전송한다.

---

## 4. 사용자 직접 변경 사항

이 브랜치에는 에이전트 작업과 별개로 사용자가 직접 편집한 내용이 포함된다.

| 파일 | 변경 | 영향 |
|---|---|---|
| `ai-proxy/providers/genai_provider.py` | 기본 `ENDPOINT_URL`을 `scisportaldev.samsungif.net` → `scisportal.samsungif.net` | **`ENDPOINT_URL` 환경변수를 설정하지 않은 설치는 이 커밋 이후 운영 호스트로 요청이 나간다** |
| `ai-proxy/providers/genai_provider.py` | `glm5.2` 모델 명시 | 모델 ID 확정 (`genai/glm5.2`) |

코드 리뷰에서 첫 항목이 MAJOR로 지적됐으나, 의도된 개발→운영 전환으로 판단해 되돌리지 않았다.

---

## 5. 설정 변경

### 5.1 `opencode.json`

`genai/glm5.2` 추가, 모델 표시명을 `model_registry.MODEL_METADATA`와 일치시킴.

```json
"genai/glm5.2": {
  "name": "Samsung SCI Portal GLM 5.2",
  "limit": { "context": 128000, "output": 4096 }
}
```

`tests/test_models_schema.py::test_opencode_models_match_registry`가 `opencode.json` ↔ 레지스트리 정합성을 강제한다.

### 5.2 신규 환경변수

| 변수 | 기본값 | 용도 |
|---|---|---|
| `LOG_PAYLOAD` | `0` | 요청/응답 페이로드 전문 로깅 |
| `LOG_CHUNK` | `0` | SSE 청크 단위 로깅 |
| `GENAI_SENSITIVE_FILTER` | `1` | 민감어 필터 토글. **코드 편집 워크플로에서는 `0` 권장** |
| `GENAI_TOOL_TRACE` | 미설정 | tool call 파싱 단계 JSONL 추적 |
| `GEMINI_PASSTHROUGH` | 미설정 | Gemini 비스트리밍 무손실 패스스루 |
| `CLAUDE_PROMPT_CACHE` | 미설정 | (예약) prompt caching |

`DEFAULT_LOG_MAX_LEN`이 100,000 → 2,000으로 축소됐다.

---

## 6. 기존 실패 테스트 22건 (이번 릴리즈 범위 밖)

기준선(`05a7ca9`)부터 실패하던 결함으로 `ai-proxy`와 무관하다. 이번 작업에서 손대지 않았다.

| 파일 | 건수 |
|---|---:|
| `tests/test_sensitive_filter.py` | 11 |
| `tests/test_template_filter_and_show.py` | 5 |
| `tests/test_agent_input_listener.py` | 2 |
| `tests/test_ai_cli_batch_auto_context.py` | 2 |
| `tests/test_ai_cli_batch_context.py` | 1 |
| `tests/test_cli_input_runtime_reset.py` | 1 |

다수가 `assert 'skc' in '***'` 형태로, `SensitiveWordFilter` 마스킹과 테스트 기대값 불일치가 공통 원인으로 보인다. 별도 과제로 분리 권장.

---

## 7. AI 오케스트레이션 실행 기록

요구 명세서의 역할 배정: **claude**(오케스트레이터) / **agy**(구현·문서) / **codex**(비판 리뷰).

### 실행 통계

| 항목 | 값 |
|---|---|
| 구현 라운드 | 13 |
| 리뷰 라운드 | 4 |
| 게이트 | G1, G3 통과 (G2는 G1/G3에 흡수) |
| 핸드오프 문서 | 10건 (`.omc/handoffs/`) |
| 리뷰 아티팩트 | 3건 (`.omc/artifacts/`) |

### 계획 대비 변경

1. **CORE-1/2/3 병렬 → 순차.** 세 태스크가 `base.py`를 공유해 동시 편집 시 서로를 덮어썼다. 게이트 시점은 동일하게 유지.
2. **GENAI-1 담당을 agy → codex로 교체.** agy가 동일 태스크에서 3회 연속 실패했다 (백그라운드 pytest 대기 중 세션 종료 2회, 즉시 오류 종료 1회). 리뷰 지적이 아니라 툴링 실패였으므로 담당 교체가 적절하다고 판단.
3. **오케스트레이터 직접 수정 2건.** `model_registry.py` 분리(순환 import)와 `base.py`의 `anyio.sleep` 교체는 에이전트 담당 범위 사이에 낀 구조적 결함이라 직접 처리했다. 자가 승인을 피하기 위해 `tests/test_model_registry.py`와 `tests/test_base_retry.py`로 **독립 검증을 별도 레인에 맡겼다**.
4. **codex 사용량 한도.** TASK-TEST 중간에 한도에 도달해 잔여 작업을 agy로 이관했다.

### 리뷰에서 검출된 주요 결함

codex 리뷰가 잡아낸 것 중 실측으로 확인된 항목:

- 업스트림 자격증명 유출 (BLOCKER) — h11 예외 문자열에 키가 포함되는 것을 격리 실행으로 재현
- `LOG_PAYLOAD=0`인데 Provider 호출부 12곳이 무조건 로깅
- 비-ASCII `Authorization` 헤더 → `hmac.compare_digest` `TypeError` → 401이 아닌 500
- `stream_options.include_obfuscation`(정식 OpenAI 옵션)이 `extra: forbid`로 422 거절
- 종료 테스트가 전역 Provider에 `AsyncMock`을 심고 복원하지 않아 다른 테스트를 오염

codex가 자기 주장의 한계를 명시한 점(추측 표기, 미확인 사항 구분)은 판정에 유용했다.

### 도구 문제

- **agy print 모드의 백그라운드 대기 문제** — 전체 스위트(4~5분)를 백그라운드로 돌리고 대기하면 세션이 종료되어 산출물이 유실된다. 이후 태스크에는 "전체 스위트를 실행하지 마라, 오케스트레이터가 검증한다"를 명시해 해소.
- **codex 리뷰의 이전 결과 재출력** — 리뷰 프롬프트에 이전 리뷰 전문을 첨부하자 그것을 자기 판정으로 되돌려주는 현상이 1회 발생. 해당 라운드는 오케스트레이터의 실행 검증으로 대체.

---

## 8. 검증 명령

```bash
# 프로젝트 규약 (CLAUDE.md)
python -m py_compile claude-ai-chat-code.py gemini-ai-chat-code.py gen-ai-chat-code.py
pytest

# ai-proxy 전용
python -m py_compile ai-proxy/models.py ai-proxy/providers/*.py ai-proxy/proxy_server.py \
                     ai-proxy/router.py ai-proxy/model_registry.py
pytest tests/test_sse_contract.py tests/test_genai_toolparse.py tests/test_genai_integrity.py \
       tests/test_genai_conversation.py tests/test_gemini_provider.py tests/test_claude_provider.py \
       tests/test_error_contract.py tests/test_models_schema.py tests/test_request_param_contract.py \
       tests/test_model_registry.py tests/test_base_retry.py -q
```

---

## 9. 참조

- `docs/openai-compatible/ORCHESTRATION_v1.1.111_tooluse-opencode.md` — 요구 명세서
- `docs/openai-compatible/CLAUDE_v1.1.111_claude-provider.md`
- `docs/openai-compatible/GEMINI_v1.1.111_gemini-provider.md`
- `docs/openai-compatible/GEN_AI_v1.1.111_gen-ai-provider.md`
- `.omc/handoffs/` — 태스크별 구현 핸드오프 10건
- `.omc/artifacts/` — codex 리뷰 아티팩트 3건
