# ORCHESTRATION v1.1.111 — AI 오케스트레이션 요구 명세서

**과제명**: `ai-proxy` OpenAI-Compatible 완전 호환화 및 GenAI Tool Use 재설계
**최종 목표**: `opencode` CLI로 프로젝트 폴더 내 **소스코드 생성 / 편집 / 실행 / 테스트**가 사람 개입 없이 수행될 것
**작성일**: 2026-09-06
**선행 문서**: `CLAUDE_v1.1.111_claude-provider.md`, `GEMINI_v1.1.111_gemini-provider.md`, `GEN_AI_v1.1.111_gen-ai-provider.md`

---

## 1. 오케스트레이션 모델

### 1.1 역할 배정

| 에이전트 | 역할 | 책임 | 부하 배분 |
|---|---|---|:--:|
| **claude** | **오케스트레이터 / 통합자** | 태스크 분해·디스패치, 인터페이스 결정, 충돌 조정, 머지, 최종 아키텍처 정합성 검증 | 15% |
| **agy** (antigravity) | **주 구현자 / 문서 작성자 / 테스트 저자** | 코드 구현, 리팩터링, 단위·통합 테스트 작성, 목 데이터 생성, 코드 헤더·요구명세 문서화, E2E 시나리오 실행 | **60%** |
| **codex** | **비판적 리뷰어 / 보안·엣지케이스 검증자** | 공격적 코드 비평, Python 문법·타입·경계조건 검토, 성능 병목, 보안 결함, 데이터 무결성 위반 탐지 | 25% |

**원칙**
1. **claude는 직접 구현하지 않는다.** 오케스트레이터가 구현까지 하면 자가 승인이 발생한다.
2. **agy에게 최대한 많은 역할을 준다** (토큰 예산 여유). 애매한 작업은 agy에 배정한다.
3. **작성 레인과 검토 레인을 분리한다.** agy가 쓴 코드는 codex가 본다. codex가 지적한 것은 agy가 고친다. 같은 컨텍스트에서 자가 승인 금지.
4. **codex는 승인하지 않는다.** 결함을 찾는 것이 임무다. 통과 판정은 claude가 §6 수용 기준으로 내린다.

### 1.2 디스패치 방법

```bash
# OMC /ask 스킬 경유 (권장 — 아티팩트 자동 캡처)
/oh-my-claudecode:ask antigravity "<프롬프트>"
/oh-my-claudecode:ask codex "<프롬프트>"

# 또는 tri-model 병렬 오케스트레이션
/oh-my-claudecode:ccg "<프롬프트>"
```

에이전트 CLI 실체: `agy` → `~/AppData/Local/agy/bin/agy`, `codex` → Volta 관리 바이너리. **원시 CLI 플래그를 임의로 조립하지 말고 `/ask` 경유를 기본으로 한다.**

### 1.3 산출물 규약

| 항목 | 규약 |
|---|---|
| 브랜치 | 현재 `release_v1.1.110` 기준. 태스크군마다 `feat/proxy-<task-id>` 분기 |
| 작업 산출물 | `.omc/handoffs/<task-id>.md` 에 변경 요약·근거·미해결 사항 기록 |
| 리뷰 산출물 | `.omc/artifacts/review-<task-id>.md` (codex 지적 사항, 심각도 라벨 포함) |
| 검증 명령 | `python -m py_compile claude-ai-chat-code.py gemini-ai-chat-code.py gen-ai-chat-code.py` 및 `pytest` (프로젝트 `CLAUDE.md` 규약) |
| 프록시 전용 검증 | `python -m py_compile ai-proxy/**/*.py` + `pytest tests/ -k provider` |

---

## 2. 태스크 DAG

```text
                        ┌──────────────────────────────┐
                        │ TASK-000  선행 정보 수집      │  (사람 + agy)
                        │  SCI Portal 실샘플/스키마     │
                        └───────────┬──────────────────┘
                                    │
      ┌─────────────────────────────┼─────────────────────────────┐
      │                             │                             │
┌─────▼──────────┐        ┌─────────▼─────────┐        ┌──────────▼────────┐
│ TASK-CORE-1    │        │ TASK-CORE-2       │        │ TASK-CORE-3       │
│ 공통 스키마 확장 │        │ SSE 청크 빌더     │        │ 에러 응답 규격화   │
│ (models.py)    │        │ (base.py)         │        │ (proxy_server.py) │
│  agy → codex   │        │  agy → codex      │        │  agy → codex      │
└─────┬──────────┘        └─────────┬─────────┘        └──────────┬────────┘
      └─────────────────────────────┼─────────────────────────────┘
                                    │  (claude 머지 게이트 G1)
      ┌─────────────────────────────┼─────────────────────────────┐
      │                             │                             │
┌─────▼──────────┐        ┌─────────▼─────────┐        ┌──────────▼────────┐
│ TASK-GENAI-1   │        │ TASK-GENAI-2      │        │ TASK-CLAUDE-1     │
│ ToolCallExtractor│      │ 진짜 스트리밍      │        │ 메시지 정규화      │
│ (P0-N2/N3)     │        │ (P0-N1)           │        │ (P0-C1)           │
│  agy → codex   │        │  agy → codex      │        │  agy → codex      │
└─────┬──────────┘        └─────────┬─────────┘        └──────────┬────────┘
      │                             │                             │
┌─────▼──────────┐        ┌─────────▼─────────┐        ┌──────────▼────────┐
│ TASK-GENAI-3   │        │ TASK-GENAI-4      │        │ TASK-GEMINI-1     │
│ 데이터 무결성   │        │ 대화구조/병렬호출  │        │ tool index 버그    │
│ (P1-N6)        │        │ (P1-N4/N8/N9)     │        │ (P0-G1/G2)        │
│  agy → codex   │        │  agy → codex      │        │  agy → codex      │
└─────┬──────────┘        └─────────┬─────────┘        └──────────┬────────┘
      └─────────────────────────────┼─────────────────────────────┘
                                    │  (claude 머지 게이트 G2)
                        ┌───────────▼──────────────────┐
                        │ TASK-TEST  계약 테스트 스위트 │  agy 작성 / codex 비평
                        └───────────┬──────────────────┘
                                    │  (게이트 G3)
                        ┌───────────▼──────────────────┐
                        │ TASK-E2E   opencode 실사용    │  agy 실행 / claude 판정
                        └───────────┬──────────────────┘
                                    │
                        ┌───────────▼──────────────────┐
                        │ TASK-DOC   문서·레지스트리 정비│  agy
                        └──────────────────────────────┘
```

**병렬 가능**: CORE-1/2/3 동시. G1 통과 후 GENAI-1/2, CLAUDE-1, GEMINI-1 동시. GENAI-3/4는 GENAI-1 이후.

---

## 3. 태스크 명세

각 태스크는 **담당 / 입력 / 산출물 / 완료 조건 / 리뷰 관점** 5요소를 갖는다.

---

### TASK-000 — 선행 정보 수집

- **담당**: agy (조사) + 사람 (자격증명·모델 ID)
- **입력**: `GEN_AI_v1.1.111` §7.3 확인 항목 7건
- **산출물**: `.omc/handoffs/TASK-000-findings.md`
- **완료 조건**:
  - SCI Portal `isStream: true` 응답 실샘플 확보 (최소 3건: 텍스트/툴호출/에러)
  - 에러 응답 스키마 확정 (`resultCode` 등 키 이름)
  - `usage` 필드 제공 여부 확정
  - `glm 5.2 512k`의 실제 `modelIds` 문자열 + context/output 한도
- **차단 시**: 모델 ID 미확정이어도 나머지 태스크는 진행한다. 레지스트리에는 TBD 플레이스홀더를 유지한다.

---

### TASK-CORE-1 — 공통 요청/응답 스키마 확장

- **담당**: 구현 **agy** / 리뷰 **codex**
- **대상**: `ai-proxy/models.py`
- **요구사항**
  1. `ChatCompletionRequest`에 추가: `top_p`, `stop`, `n`, `seed`, `presence_penalty`, `frequency_penalty`, `response_format`, `stream_options`, `parallel_tool_calls`, `user`, `logprobs`, `top_logprobs`
  2. `ChatCompletionResponse`에 `created: int` 추가 (기본값 `int(time.time())`)
  3. `ErrorDetail.code`를 `int` → `str`로 변경
  4. `ChatMessage`에 `name: Optional[str]` 추가
  5. **미지원 파라미터를 조용히 드랍하지 말 것** — Provider가 처리하지 못하는 필드는 `logger.warning`으로 1회 기록
- **완료 조건**: `pytest tests/ -k provider_contract` 통과, 기존 호출부 회귀 없음
- **codex 리뷰 관점**: Pydantic 검증 우회 가능성, `Optional` 남용으로 인한 타입 안전성 저하, 기본값 변경이 기존 직렬화에 미치는 영향

---

### TASK-CORE-2 — SSE 청크 빌더 공통화

- **담당**: 구현 **agy** / 리뷰 **codex**
- **대상**: `ai-proxy/providers/base.py` + 3개 Provider의 `stream()`
- **요구사항**
  1. `BaseProvider._chunk(chunk_id, model, delta, finish_reason=None, usage=None) -> str` 헬퍼 신설
  2. 필수 필드 전량 포함: `id`, `object: "chat.completion.chunk"`, `created`, `model`, `choices[].index`, `choices[].delta`
  3. 모든 Provider가 스트림 시작 시 `delta: {"role": "assistant"}` 청크를 **정확히 1회** 방출
  4. 모든 Provider가 종료 시 `finish_reason` 청크 + `data: [DONE]`을 **반드시** 방출 (업스트림이 주지 않아도 보정)
  5. `stream_options.include_usage=true`면 마지막에 `choices: []` + `usage` 청크
- **완료 조건**: `GEMINI_v1.1.111` §6 "Provider 간 동작 불일치" 표의 SSE 관련 4개 행이 전부 동일해짐
- **codex 리뷰 관점**: 청크 ID 일관성(한 스트림 내 동일 ID 유지), 이중 `[DONE]` 방출, 예외 경로에서의 종결 누락

---

### TASK-CORE-3 — OpenAI 규격 에러 응답

- **담당**: 구현 **agy** / 리뷰 **codex**
- **대상**: `ai-proxy/proxy_server.py`
- **요구사항**
  1. `HTTPException` 전역 핸들러로 최상위 `{"error": {...}}` 형태 `JSONResponse` 반환 (`{"detail": ...}` 래핑 제거)
  2. `code`는 문자열 에러 코드, HTTP 상태는 상태 코드로만 전달
  3. **인증 로깅 제거**: `logger.info(f"... authorization: {authorization}")` 및 `logger.error(f"Expected: Bearer {PROXY_API_KEY}")` 삭제
  4. `hmac.compare_digest()`로 키 비교
  5. FastAPI `lifespan`에서 모든 Provider의 `client.aclose()` 호출
  6. `LOG_PAYLOAD` / `LOG_CHUNK` 환경변수 게이팅, `DEFAULT_LOG_MAX_LEN` 100000 → 2000
- **완료 조건**: 잘못된 모델 ID 요청 시 응답 최상위에 `error` 키 존재. 인증 실패 로그에 키 문자열 부재
- **codex 리뷰 관점**: **보안 최우선.** 다른 로그 경로에 키가 남는지 전수 확인, 타이밍 공격, 에러 메시지의 내부 정보 노출

> **게이트 G1** (claude): CORE-1/2/3 머지. 세 Provider가 동일한 SSE·에러 계약을 따르는지 확인 후 다음 단계 개시.

---

### TASK-GENAI-1 — 계층형 Tool Call 파서 **[최우선]**

- **담당**: 구현 **agy** / 리뷰 **codex**
- **대상**: `ai-proxy/providers/genai_provider.py` — `_parse_tool_calls()` 전면 교체
- **근거**: `GEN_AI_v1.1.111` P0-N2, P0-N3, IMP-N-02
- **요구사항**
  1. `_scan_balanced_json()` 구현 — 문자열 리터럴/이스케이프를 인식하는 중괄호 균형 스캐너. **정규식으로 JSON 경계를 결정하지 말 것**
  2. 5단계 폴백 체인: 펜스 태그 → XML 태그 → Harmony 포맷 → 베어 JSON 스캔 → 느슨한 복구
  3. 파싱된 툴 이름을 `request.tools`와 대조 검증. 미등록 이름은 드랍 + `tool_hallucinated` 계측
  4. `arguments`를 해당 툴의 JSON Schema로 검증 (필수 필드 누락 검출)
  5. tool_call ID를 `f"call_{uuid.uuid4().hex[:24]}"`로 변경
  6. `tool_call_id → tool_name` 매핑을 요청 시작 시 dict로 1회 구축 (O(n²) 제거)
  7. `GENAI_TOOL_TRACE=1`일 때 파싱 단계·결과를 JSONL로 기록
- **완료 조건**: TC-N-01 ~ TC-N-04, TC-N-07, TC-N-13 통과
- **codex 리뷰 관점**:
  - 균형 스캐너의 **엣지케이스 전수 공격**: 이스케이프된 따옴표(`\"`), 백슬래시 연속(`\\`), 유니코드 이스케이프, 중괄호 포함 문자열, 미닫힌 문자열, 빈 입력, 매우 긴 입력(ReDoS)
  - 5단계 폴백의 **오탐(false positive)**: 사용자 코드에 등장한 JSON을 툴 호출로 오인하지 않는가
  - Stage 5 "느슨한 복구"가 **잘못된 arguments를 만들어낼 위험** — 복구보다 실패가 나은 경우 구분
  - 성능: 긴 응답에서의 스캔 복잡도

---

### TASK-GENAI-2 — 진짜 스트리밍 (2모드 전략)

- **담당**: 구현 **agy** / 리뷰 **codex**
- **선행**: TASK-000 (스트리밍 실샘플)
- **대상**: `genai_provider.py` — `_transform_request()`의 `isStream`, `stream()` 전면 재작성
- **근거**: `GEN_AI_v1.1.111` P0-N1, IMP-N-01
- **요구사항**
  1. `isStream: True`로 전환, `event_status: CHUNK / DONE` 파싱
  2. **패스스루 모드** (`tools` 없음): CHUNK 도착 즉시 `delta.content` 방출
  3. **감시 모드** (`tools` 있음): 툴 개시 마커 탐지 전까지 즉시 방출, 탐지 후 버퍼링 → TASK-GENAI-1 파서 적용
  4. 마커 후보: ` ```tool_call `, ` ```json `, `<tool_call>`, `{"name"`, Harmony 채널 토큰
  5. `chat()`(비스트리밍)은 별도 경로로 유지 — `stream()`이 `chat()`을 호출하는 현 구조 제거
  6. 잘림 감지: `finish_reason="length"` 판정 (IMP-N-09)
  7. 첫 바이트 수신 전 429/5xx 지수 백오프 재시도
- **완료 조건**: TC-N-05, TC-N-06, TC-N-11 통과. 첫 청크 지연 3초 이내
- **codex 리뷰 관점**:
  - 마커가 **청크 경계에 걸쳐 분할**되는 경우 (예: `` ``` ``가 청크1 끝, `tool_call`이 청크2 시작) — 슬라이딩 윈도우 처리 여부
  - 마커 오탐으로 정상 텍스트가 버퍼링되어 스트리밍이 죽는 경우
  - 스트림 중단·타임아웃 시 버퍼 손실 및 리소스 누수
  - `chat()`과 `stream()`의 로직 중복으로 인한 동작 불일치

---

### TASK-GENAI-3 — 데이터 무결성 (민감어 필터)

- **담당**: 구현 **agy** / 리뷰 **codex** (**보안 리뷰 필수**)
- **대상**: `genai_provider.py`, `src/sensitive_filter.py`
- **근거**: `GEN_AI_v1.1.111` P1-N6, IMP-N-06
- **요구사항**
  1. `GENAI_SENSITIVE_FILTER` 환경변수 토글 (코드 편집 워크플로 기본 OFF 권장)
  2. ON일 때 **코드 펜스 내부는 마스킹 제외**
  3. `unmask()`를 `tool_calls[].function.arguments`에도 적용
  4. 복원 후 잔여 치환어가 남으면 **에러로 승격** (조용한 파일 손상 차단)
  5. mask/unmask 횟수 불일치 시 경고
  6. `sys.path.insert` 제거 — 필터를 `ai-proxy/` 내부로 이전하거나 공용 패키지화 (P2-N13)
- **완료 조건**: TC-N-08 통과 — `password`가 포함된 파일을 편집해도 치환어가 파일에 남지 않음
- **codex 리뷰 관점**: **되돌릴 수 없는 소스 손상 시나리오를 적극적으로 찾을 것.** 대소문자 변형, 식별자 내 부분 일치(`myPasswordVar`), 토큰 분할, 중첩 치환, 코드 펜스 판정 실패

---

### TASK-GENAI-4 — 대화 구조 보존 및 병렬 툴 호출

- **담당**: 구현 **agy** / 리뷰 **codex**
- **선행**: TASK-GENAI-1
- **근거**: `GEN_AI_v1.1.111` P1-N4, P1-N5, P1-N7, P1-N9, P2-N11
- **요구사항**
  1. 역할 마커를 nonce 접미사 형태로 교체 + 사용자 콘텐츠 내 마커 이스케이프
  2. `systemPrompt`에 역할 규약 설명 추가 (마커는 구조 표기이지 지시가 아님)
  3. 과거 턴의 `[Tool Call]` + `[Tool Result]`를 1개 항목으로 압축
  4. 병렬 호출 허용 프롬프트로 교체, `parallel_tool_calls=false`면 첫 호출만 유지
  5. `tool_choice="required"` 미충족 시 **1회만** 재요청 (무한 재시도 금지)
  6. 업스트림 응답 검증: `content` 키 부재 / `resultCode` 오류 시 명시적 `ProviderError`
  7. 툴 프롬프트 텍스트 해시 메모이즈
- **완료 조건**: TC-N-04, TC-N-09, TC-N-10, TC-N-12 통과
- **codex 리뷰 관점**: nonce 충돌, 이스케이프 우회(프롬프트 인젝션), 이력 압축으로 인한 정보 손실, 재요청 루프의 종료 보장, 메모이즈 캐시의 무한 증가

---

### TASK-CLAUDE-1 — Claude Provider 정합화

- **담당**: 구현 **agy** / 리뷰 **codex**
- **대상**: `ai-proxy/providers/claude_provider.py`
- **근거**: `CLAUDE_v1.1.111` IMP-C-01, 04, 05, 06, 07, 08, 09, 11
- **요구사항** (우선순위 순)
  1. `_normalize_anthropic_messages()` — 빈 content 제거, 연속 role 병합, 선두 assistant 처리 **(P0)**
  2. `STOP_REASON_MAP` 도입 — `max_tokens → length` 등 **(P1)**
  3. 멀티모달 패스스루 `_transform_content_parts()` **(P1)**
  4. 스트림 내 `error` 이벤트 처리 + 429/500/529 스트리밍 재시도 **(P1)**
  5. 모델별 `max_tokens` 기본값 테이블 (`opencode.json`과 단일 진실 소스) **(P1)**
  6. Prompt Caching (`cache_control: ephemeral`) — `CLAUDE_PROMPT_CACHE=1` 토글 **(P1)**
  7. `message_delta`의 usage 전달 **(P1)**
  8. `system` 메시지 `+=` 누적으로 통일, `tool_result.is_error` 지원 **(P2)**
- **완료 조건**: TC-C-01 ~ TC-C-09 통과
- **codex 리뷰 관점**: 메시지 정규화가 **의미를 바꾸는 경우**(툴 호출 순서 뒤바뀜, 프리필 파괴), 캐시 브레이크포인트 위치 오류로 인한 캐시 미스, 병합 시 tool_use/tool_result 짝 붕괴

---

### TASK-GEMINI-1 — Gemini Provider 버그 수정

- **담당**: 구현 **agy** / 리뷰 **codex**
- **대상**: `ai-proxy/providers/gemini_provider.py`
- **근거**: `GEMINI_v1.1.111` IMP-G-01 ~ G-07
- **요구사항**
  1. **스트리밍 tool_call index를 누적 카운터로 교체** — `enumerate` 버그 제거 **(P0)**
  2. `_parse_response()` 방어 — 빈 `choices` 시 명시적 `ProviderError` **(P0)**
  3. 비스트리밍 패스스루 모드 (`GEMINI_PASSTHROUGH=1`) — 필드 손실 제거 **(P1)**
  4. `finish_reason` 화이트리스트 매핑 (`SAFETY → content_filter` 등) **(P1)**
  5. `tools` 직렬화에 `exclude_none=True` **(P1)**
  6. 스트림 종결 보정 + 스트리밍 재시도 **(P1)**
  7. 청크 단위 로그 기본 OFF, 스트림 종료 요약 1줄로 대체 **(P2)**
- **완료 조건**: TC-G-01 ~ TC-G-08 통과
- **codex 리뷰 관점**: 누적 카운터가 업스트림 제공 `index`와 충돌하는 경우, 패스스루 모드에서 `model` 필드 덮어쓰기 누락, 안전 필터 응답의 다양한 형태

> **게이트 G2** (claude): 전 Provider 머지. `GEMINI_v1.1.111` §6 불일치 표 7개 행이 모두 해소되었는지 확인.

---

### TASK-TEST — 계약 테스트 스위트

- **담당**: 작성 **agy** / 비평 **codex**
- **대상**: `tests/test_openai_compat_contract.py` (신규), 기존 `tests/test_large_context_provider_contract.py` 확장
- **요구사항**
  1. 세 Provider 문서의 TC 표 **전 항목**을 자동화한다 (TC-C-01~09, TC-G-01~08, TC-N-01~14)
  2. 업스트림 API를 목(mock)으로 대체해 **자격증명 없이 실행 가능**해야 한다
  3. Tool Call 파서는 **실제 모델이 낼 법한 출력 20종 이상**의 픽스처로 테스트한다 (정상/변형/악성)
  4. SSE 청크 스키마를 검증하는 공통 어서션 헬퍼 제공
  5. `test.skip` / `.only` / 빈 스텁 테스트 **금지** — 미구현은 실패로 남긴다
- **완료 조건**: `pytest tests/` 전체 통과, 신규 테스트 커버리지가 3개 Provider 주요 분기를 포함
- **codex 리뷰 관점**: **테스트가 실제로 무언가를 검증하는지** — 항상 참인 어서션, 목이 실제 API와 다른 계약을 가정하는 경우, 누락된 실패 경로

> **게이트 G3** (claude): `pytest` 및 `python -m py_compile claude-ai-chat-code.py gemini-ai-chat-code.py gen-ai-chat-code.py` 통과 확인.

---

### TASK-E2E — opencode 실사용 검증

- **담당**: 실행 **agy** / 판정 **claude**
- **선행**: G3 통과, 유효한 자격증명
- **시나리오** (각 시나리오는 `genai/gpt-oss-120B-medium`을 기본 모델로 수행)

| # | 시나리오 | 검증 대상 |
|---|---|---|
| E2E-1 | `calculator.py`를 읽고 설명 | 파일 읽기 툴, 스트리밍 |
| E2E-2 | 새 함수를 추가하고 저장 | 편집 툴, 중첩 arguments (TASK-GENAI-1) |
| E2E-3 | `pytest`를 실행하고 결과 요약 | 실행 툴, 멀티턴 |
| E2E-4 | 실패하는 테스트를 스스로 고칠 때까지 반복 | 15턴 루프, 구조 보존 (TASK-GENAI-4) |
| E2E-5 | 파일 3개를 한 턴에 읽기 | 병렬 툴 호출 |
| E2E-6 | `password` 변수를 포함한 파일 편집 | 데이터 무결성 (TASK-GENAI-3) |
| E2E-7 | 동일 시나리오를 `claude/` 및 `gemini/` 모델로 반복 | Provider 간 동작 일치 |

- **완료 조건**: E2E-1 ~ E2E-7 전부 사람 개입 없이 완료. **E2E-4가 최종 수용 기준.**
- **claude 판정 항목**: 성공/실패뿐 아니라 **첫 토큰 지연, 총 턴 수, 총 토큰, 실패 원인 분류**를 기록

---

### TASK-DOC — 문서 및 레지스트리 정비

- **담당**: **agy**
- **요구사항**
  1. `router.SUPPORTED_MODELS` → `MODEL_REGISTRY`로 확장 (name / context / max_output), 중복 키 제거
  2. `glm 5.2 512k` 등록 (TASK-000에서 ID 확보 시) 또는 TBD 주석 유지
  3. `opencode.json`을 레지스트리와 일치시키고, CI에서 불일치를 검출하는 테스트 추가
  4. `genai_provider.py:16` 잘못된 docstring 수정 (`512k 파라미터` → 실제 사양)
  5. 각 Provider 소스 헤더에 변경 이력 추가 (프로젝트 `CLAUDE.md` Gemini 역할 규약 준용)
  6. `docs/requirements/FSD_v1.1.111_openai-compat-hardening.md` 생성 — 본 명세의 REQ 번호 부여판
  7. 세 분석 문서의 "문제점" 표에 **해결 여부 컬럼**을 추가해 갱신
- **완료 조건**: `opencode.json` ↔ 레지스트리 일치 테스트 통과, 문서 갱신 완료

---

## 4. 에이전트 프롬프트 템플릿

### 4.1 agy — 구현 태스크

```text
[역할] 너는 이 태스크의 주 구현자다. 코드를 직접 작성하고 테스트까지 만든다.

[컨텍스트]
- 저장소: p3-ai-code-chat-messages, 브랜치 release_v1.1.110
- 분석 문서: docs/openai-compatible/{CLAUDE|GEMINI|GEN_AI}_v1.1.111_*.md
- 최종 목표: opencode CLI로 코드 생성/편집/실행/테스트가 사람 개입 없이 동작

[태스크] <TASK-ID> — <제목>
[근거] <문서 §번호와 결함 ID>
[요구사항] <번호 목록 그대로 전달>
[완료 조건] <TC ID 목록>

[제약]
- TODO 주석, 미구현 분기, test.skip/.only, 빈 스텁 테스트를 남기지 마라. 전부 블로커다.
- 기존 REQ 주석 규약(REQ-0xx-00x)을 유지하고 새 변경에는 REQ-111-00x를 부여하라.
- 변경 요약·근거·미해결 사항을 .omc/handoffs/<TASK-ID>.md 에 기록하라.
- 검증: python -m py_compile <변경 파일> && pytest tests/ -k <관련 키워드>
- 검증 실패 상태로 완료 보고하지 마라. 실패하면 출력 전문을 그대로 보고하라.
```

### 4.2 codex — 비판 리뷰 태스크

```text
[역할] 너는 공격적인 코드 비평가다. 승인이 임무가 아니라 결함을 찾는 것이 임무다.
      "문제 없음"으로 끝내지 마라. 최소 한 가지 개선 가능 지점은 지적하라.

[대상] <TASK-ID>의 변경분 (git diff)
[구현 근거 문서] <경로>

[집중 검토 관점]
<태스크별 'codex 리뷰 관점' 항목을 그대로 전달>

[공통 검토 항목]
1. Python 문법·타입 오류, None 역참조, 인덱스 오류
2. 경계 조건: 빈 입력, 초장문 입력, 유니코드, 이스케이프, 부분 수신
3. 동시성: 공유 상태 변경, 요청 간 상태 누수
4. 성능: O(n²) 이상 복잡도, ReDoS, 불필요한 재직렬화
5. 보안: 자격증명 로깅, 인젝션, 타이밍 공격
6. 데이터 무결성: 사용자 파일을 손상시킬 수 있는 모든 경로

[출력 형식]
각 지적을 다음으로 분류하라 — BLOCKER / MAJOR / MINOR / NIT
각 항목에 파일:라인, 재현 시나리오(구체적 입력 → 잘못된 출력), 수정 제안을 포함하라.
추측이면 추측이라고 명시하라.
결과를 .omc/artifacts/review-<TASK-ID>.md 에 기록하라.
```

### 4.3 claude — 게이트 판정 (자기 자신)

```text
[게이트 G<n> 체크리스트]
1. codex 리뷰의 BLOCKER/MAJOR가 전부 해소되었는가 (또는 명시적으로 유예 근거가 기록되었는가)
2. 변경 파일에 TODO/스텁/test.skip/미구현 분기가 없는가 (grep으로 실증)
3. pytest 및 py_compile이 실제로 통과했는가 (출력 전문 확인, 보고서 신뢰 금지)
4. 세 Provider의 동작 불일치 표(GEMINI 문서 §6) 해당 행이 해소되었는가
5. .omc/handoffs/ 에 산출물이 기록되었는가
→ 하나라도 미충족이면 해당 태스크를 agy에 반려한다.
```

---

## 5. 반복 규약 (Iteration Protocol)

```text
claude: 태스크 디스패치
   ↓
agy: 구현 + 자체 검증 (py_compile + pytest)
   ↓
agy: .omc/handoffs/<TASK-ID>.md 기록
   ↓
codex: git diff 리뷰 → .omc/artifacts/review-<TASK-ID>.md (BLOCKER/MAJOR/MINOR/NIT)
   ↓
claude: 리뷰 분류 판정
   ├ BLOCKER/MAJOR 있음 → agy에 반려 (리뷰 전문 첨부, 최대 3회 왕복)
   └ 없음 → 게이트 체크리스트 → 머지
   ↓
3회 왕복에도 미해결 → claude가 사람에게 에스컬레이션 (임의 판단으로 통과시키지 않는다)
```

**금지 사항**
- claude가 agy/codex를 거치지 않고 직접 구현하는 것 (자가 승인)
- agy가 자기 코드를 자기가 승인하는 것
- codex의 지적을 claude가 임의로 "해당 없음" 처리하는 것 (반드시 근거를 기록)
- 검증 명령 출력을 확인하지 않고 완료 보고하는 것

---

## 6. 최종 수용 기준

| # | 기준 | 측정 방법 |
|---|---|:--|
| A1 | `python -m py_compile claude-ai-chat-code.py gemini-ai-chat-code.py gen-ai-chat-code.py` 통과 | 명령 실행 |
| A2 | `python -m py_compile ai-proxy/**/*.py` 통과 | 명령 실행 |
| A3 | `pytest` 전체 통과, skip 0건 | 명령 실행 |
| A4 | 세 Provider 문서의 TC 표 전 항목 자동화 및 통과 | `pytest tests/test_openai_compat_contract.py` |
| A5 | E2E-1 ~ E2E-7 사람 개입 없이 완료 | opencode 실행 로그 |
| A6 | **E2E-4** (실패 테스트 자가 수정 15턴 루프) 완료 | opencode 실행 로그 |
| A7 | GenAI 스트리밍 첫 토큰 지연 3초 이내 | 계측 |
| A8 | 중첩 arguments 툴 호출 파싱 성공률 100% (픽스처 20종) | 계측 |
| A9 | 민감어 포함 파일 편집 후 치환어 잔존 0건 | TC-N-08 |
| A10 | 인증 키가 로그에 남지 않음 | `grep -r "$AI_PROXY_API_KEY" logs/` 결과 0건 |
| A11 | `opencode.json` ↔ `MODEL_REGISTRY` 일치 | CI 테스트 |
| A12 | 변경 파일에 TODO/스텁/skip 없음 | grep 실증 |

**A6이 프로젝트 최종 목표의 대리 지표(proxy metric)다.** 나머지가 모두 통과해도 A6이 실패하면 미완료로 간주한다.

---

## 7. 리스크 및 완화

| 리스크 | 영향 | 완화 |
|---|---|---|
| SCI Portal 스트리밍 실샘플 확보 실패 | TASK-GENAI-2 차단 | 비스트리밍 유지 + 나머지 태스크 선행. 스트리밍은 별도 릴리스로 분리 |
| gpt-oss-120B가 어떤 프롬프트에도 툴 형식을 지키지 않음 | Tool Use 근본 불가 | `GENAI_TOOL_TRACE` 데이터로 실제 출력 형식을 확인해 파서를 그 형식에 맞춤. 그래도 불가하면 툴 사용 시 `claude/`로 폴백하는 라우팅 정책 도입 |
| `glm 5.2 512k` 모델 ID 미확정 | 등록 불가 | TBD 유지. 다른 태스크는 무관하게 진행 |
| 민감어 필터 OFF에 대한 조직 정책 반대 | IMP-N-06 제한 | 코드 펜스 제외 + arguments 복원 + 잔여 검사(3단 방어)만으로 진행 |
| agy/codex 왕복 3회 초과 | 진척 정체 | 사람 에스컬레이션. claude가 임의 통과시키지 않음 |
| Prompt Caching 적용 오류로 잘못된 컨텍스트 재사용 | 응답 오염 | 환경변수 기본 OFF, A/B 비교 후 활성화 |

---

## 8. 실행 순서 요약

```text
1. TASK-000              (agy + 사람)        — 선행 정보
2. TASK-CORE-1/2/3       (agy → codex, 병렬)  → 게이트 G1
3. TASK-GENAI-1          (agy → codex)       — 최우선
   TASK-GENAI-2          (agy → codex)
   TASK-CLAUDE-1         (agy → codex)       — 병렬
   TASK-GEMINI-1         (agy → codex)       — 병렬
4. TASK-GENAI-3/4        (agy → codex)       → 게이트 G2
5. TASK-TEST             (agy → codex)       → 게이트 G3
6. TASK-E2E              (agy 실행 / claude 판정)
7. TASK-DOC              (agy)
```

---

## 9. 참조

- `docs/openai-compatible/CLAUDE_v1.1.111_claude-provider.md`
- `docs/openai-compatible/GEMINI_v1.1.111_gemini-provider.md`
- `docs/openai-compatible/GEN_AI_v1.1.111_gen-ai-provider.md`
- `docs/openai-compatible/GUIDE_v1.0.001_openai-compatible-guide.md`
- `CLAUDE.md` (프로젝트 AI 팀 역할 규약)
- `docs/prompt/prompt-proxy.md` (원 요구사항)
