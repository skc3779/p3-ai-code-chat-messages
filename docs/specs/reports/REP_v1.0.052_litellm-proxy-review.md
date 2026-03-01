# REP v1.0.052 - LiteLLM Proxy 적용 검토 보고서

## 문서 정보

| 항목 | 내용 |
|------|------|
| **버전** | v1.0.052 |
| **작성일** | 2026-03-01 |
| **종류** | 기술 검토 보고서 (Review & Evaluation Report) |
| **참조 SRS** | SRS_v1.0.052_openai-compatible-provider_v2.md |
| **참조 FSD** | FSD_v1.0.052_openai-compatible-proxy.md |
| **검토 대상** | [LiteLLM](https://github.com/BerriAI/litellm) Proxy Server (AI Gateway) |

---

## 1. 검토 요약

| 구분 | 결과 |
|------|------|
| LiteLLM Proxy 도입 필요성 | ❌ **불필요** |
| 결론 | FSD v1.0.052의 **FastAPI 직접 구현** 방식 유지 |
| 사유 | 커스텀 API(SCI Portal) 미지원, 과도한 의존성, 학습 비용 |

---

## 2. 검토 배경

### 2.1 LiteLLM이란?

LiteLLM은 **100개 이상의 LLM 공급자**를 OpenAI 호환 형식(`/v1/chat/completions`)으로 통합하는 오픈소스 Python 기반 프록시 서버(AI Gateway)입니다.

- **GitHub**: https://github.com/BerriAI/litellm
- **라이선스**: MIT
- **언어**: Python
- **주요 지원**: Anthropic, Google Vertex, Azure, Bedrock, OpenAI 등 100+ 공급자

### 2.2 검토 목적

FSD v1.0.052에서 설계한 **FastAPI 직접 구현 방식** 대신, LiteLLM Proxy를 사용하면 개발 공수를 줄일 수 있는지 평가합니다.

---

## 3. 비교 분석

### 3.1 기능 비교

| 항목 | FastAPI 직접 구현 | LiteLLM Proxy |
|------|-----------------|---------------|
| OpenAI 호환 `/v1/chat/completions` | ✅ 직접 구현 | ✅ 기본 제공 |
| Gemini 지원 | ✅ 패스스루 구현 | ✅ `gemini/` 접두사 지원 |
| Claude 지원 | ✅ 형식 변환 구현 | ✅ `anthropic/` 접두사 지원 |
| **SCI Portal (GenAI) 지원** | ✅ 커스텀 Provider 구현 | ❌ **기본 미지원** |
| 스트리밍 (SSE) | ✅ 구현 필요 | ✅ 기본 제공 |
| Token 사용량 추적 | ⚠️ 별도 구현 | ✅ 내장 |
| 로드밸런싱 | ❌ 미구현 | ✅ 내장 |
| 레이트 리밋 | ❌ 미구현 | ✅ 내장 |

### 3.2 인프라/의존성 비교

| 항목 | FastAPI 직접 구현 | LiteLLM Proxy |
|------|-----------------|---------------|
| **설치 크기** | ~10MB | **~200MB+** |
| **핵심 의존성** | fastapi, uvicorn, httpx (4개) | litellm + 수십 개 종속 패키지 |
| **데이터베이스** | 불필요 | PostgreSQL 권장 (사용량/로깅) |
| **Docker** | 선택 | 사실상 필수 (안정 배포) |
| **설정 파일** | `.env` (단순) | `litellm_config.yaml` (별도 학습) |

### 3.3 운영/유지보수 비교

| 항목 | FastAPI 직접 구현 | LiteLLM Proxy |
|------|-----------------|---------------|
| **코드 제어** | ✅ 100% 제어 가능 | ❌ 블랙박스 (내부 동작 불투명) |
| **디버깅** | ✅ 직접 디버깅 가능 | ⚠️ LiteLLM 내부 추적 필요 |
| **팀 학습 비용** | 🟢 Python/FastAPI (기존 역량) | 🟠 LiteLLM 설정/운영 학습 필요 |
| **업데이트 리스크** | 🟢 자체 제어 | 🟠 LiteLLM 버전 업데이트 영향 |

---

## 4. SCI Portal (GenAI) 호환성 분석

### 4.1 LiteLLM의 커스텀 API 지원 방식

LiteLLM은 [`custom_llm_server`](https://docs.litellm.ai/docs/providers/custom_llm_server) 기능으로 커스텀 API를 등록할 수 있습니다. 그러나 이를 위해 다음 작업이 필요합니다:

```python
# LiteLLM 커스텀 핸들러 (별도 구현 필요)
class SCIPortalHandler(litellm.CustomLLM):
    def completion(self, model, messages, **kwargs):
        # ① OpenAI 형식 → SCI Portal 형식 변환 (직접 구현)
        payload = {
            "model_id": model,
            "prompt": [{"role": m["role"], "text": m["content"]} for m in messages],
            "parameters": {...},
        }
        # ② 커스텀 인증 헤더 (직접 구현)
        headers = {
            "X-Client-Key": "API_CLIENT_APP",
            "X-Client-Secret": "",
        }
        # ③ HTTP 요청 + 응답 파싱 (직접 구현)
        response = httpx.post(ENDPOINT_URL, json=payload, headers=headers)
        # ④ SCI Portal 응답 → OpenAI 형식 변환 (직접 구현)
        ...
```

### 4.2 결론

| 작업 | FastAPI로 직접 | LiteLLM 사용 시 |
|------|--------------|----------------|
| 요청 형식 변환 | `_transform_request()` | `CustomLLM.completion()` |
| 인증 헤더 처리 | `httpx.AsyncClient(headers={})` | `CustomLLM` 내부 |
| 응답 파싱 | `Provider.chat()` | `CustomLLM.completion()` |

**→ SCI Portal 변환 코드는 어느 방식이든 직접 작성해야 하므로, LiteLLM을 도입해도 핵심 개발 공수가 줄지 않습니다.**

---

## 5. 종합 평가

### 5.1 LiteLLM이 적합한 경우

| 조건 | 설명 |
|------|------|
| 공급자 10개 이상 | 다양한 상용 LLM을 동시 운영 |
| 커스텀 API 없음 | 모든 공급자가 LiteLLM 기본 지원 |
| 운영 인프라 확보 | Docker/PostgreSQL/Redis 운영 가능 |
| 엔터프라이즈 기능 필요 | 로드밸런싱, 레이트 리밋, 비용 추적 등 |

### 5.2 현 프로젝트 상황

| 조건 | 현 프로젝트 | 적합 여부 |
|------|-----------|----------|
| 공급자 수 | **3개** (GenAI, Claude, Gemini) | ❌ 과잉 |
| 커스텀 API | **있음** (SCI Portal) | ❌ 추가 구현 필요 |
| 인프라 | 로컬 개발 환경 | ❌ Docker/DB 부담 |
| 엔터프라이즈 기능 | 불필요 | ❌ 과잉 |
| 팀 구성 | 소규모, Python 중심 | ❌ 학습 비용 |

### 5.3 최종 판정

| 판정 | 내용 |
|------|------|
| **결과** | ❌ LiteLLM Proxy 도입 **불필요** |
| **사유 1** | SCI Portal 커스텀 API 미지원 → 핵심 코드는 어차피 직접 구현 |
| **사유 2** | 3개 공급자 연동에 100+ 공급자용 범용 게이트웨이는 과잉 설계 |
| **사유 3** | 200MB+ 의존성 + Docker/DB 인프라는 프로젝트 규모에 부적합 |
| **사유 4** | LiteLLM 블랙박스 리스크 vs FastAPI 100% 코드 제어 |
| **권장** | FSD v1.0.052의 **Python FastAPI 직접 구현** 방식 유지 |

---

## 6. 참고 사항

향후 프로젝트가 확장되어 다음 조건을 충족하면 LiteLLM 재검토를 권장합니다:

| 트리거 조건 | 재검토 시점 |
|------------|-----------|
| 공급자 5개 이상 추가 | 직접 구현 대비 LiteLLM 효율성 재평가 |
| 로드밸런싱/폴백 필요 | LiteLLM 내장 기능 활용 검토 |
| 엔터프라이즈 비용 추적 필요 | LiteLLM 내장 비용 추적 활용 검토 |
| SCI Portal이 OpenAI 호환 엔드포인트 지원 시 | 커스텀 변환 불필요 → LiteLLM 즉시 도입 가능 |

---

## 7. 승인

- [x] LiteLLM Proxy 기능 및 지원 공급자 분석 완료
- [x] SCI Portal (GenAI) 커스텀 API 호환성 분석 완료
- [x] FastAPI 직접 구현 vs LiteLLM 비교 분석 완료
- [x] 최종 판정: LiteLLM 도입 불필요, FastAPI 직접 구현 유지
