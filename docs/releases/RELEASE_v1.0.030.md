# 릴리즈 노트 v1.0.030

> **버전**: v1.0.030  
> **릴리즈 일자**: 2026-02-06  
> **FSD 문서**: FSD_Gemini_API_Integration_v1.0.030.md

---

## 개요

Google Gemini API 지원이 추가되었습니다. 이제 사용자는 Claude, GenAI, Gemini 중 원하는 LLM을 선택하여 사용할 수 있습니다.

---

## 신규 기능

### 1. Gemini Code Assistant

새로운 `gemini-ai-chat-code01.py` Entry Point가 추가되어 Google Gemini API를 통한 코딩 어시스턴트 기능을 제공합니다.

**주요 특징**:
- REST API 직접 호출 (SDK 의존성 없음)
- 스트리밍/논스트리밍 모드 지원
- Server-Sent Events (SSE) 기반 실시간 응답
- 기존 Claude/GenAI 어시스턴트와 동일한 명령어 체계

### 2. GeminiCodeAssistant 클래스

`src/gemini_assistant.py`에 새로운 어시스턴트 클래스가 추가되었습니다.

**구현 내용**:
- `requests` + `sseclient-py`를 사용한 HTTP 직접 호출
- Gemini API 응답 구조 파싱 (`candidates[].content.parts[].text`)
- 대화 히스토리 관리 (`role: user/model`)
- 토큰 자동 트리밍 (MAX_TOKENS_GEMINI: 786,000)
- 템플릿 시스템 연동
- 히스토리 저장/로드 기능

---

## 파일 변경 내역

### 신규 파일

| 파일 | 설명 |
|------|------|
| `gemini-ai-chat-code01.py` | Gemini 어시스턴트 Entry Point |
| `src/gemini_assistant.py` | GeminiCodeAssistant 클래스 |
| `tests/test_gemini_tool_use.py` | Gemini Tool Use 단위 테스트 |

### 수정 파일

| 파일 | 변경 사항 |
|------|-----------|
| `src/__init__.py` | GeminiCodeAssistant import 추가 |
| `src/token_manager.py` | MAX_TOKENS_GEMINI 상수 추가 (786,000) |
| `src/history_manager.py` | save_gemini_history() 메서드 추가 |

---

## 설정 방법

### 환경변수 (.env)

```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL_ID=gemini-3.0-flash
GEMINI_API_ENDPOINT=https://generativelanguage.googleapis.com/v1beta
```

### 실행 방법

```bash
python gemini-ai-chat-code01.py
```

---

## API 엔드포인트

| 기능 | 엔드포인트 |
|------|-----------|
| 논스트리밍 | `{endpoint}/models/{model}:generateContent?key={api_key}` |
| 스트리밍 | `{endpoint}/models/{model}:streamGenerateContent?alt=sse&key={api_key}` |

---

## 대화 히스토리 형식 비교

| 항목 | Claude | GenAI | Gemini |
|------|--------|-------|--------|
| 사용자 역할 | `role: "user"` | `role: "user"` | `role: "user"` |
| AI 역할 | `role: "assistant"` | `role: "assistant"` | `role: "model"` |
| 인증 방식 | `x-api-key` 헤더 | 커스텀 헤더 | `?key=` 쿼리 파라미터 |

---

## 테스트

```bash
python -m pytest tests/test_gemini_tool_use.py -v
```

---

## 알려진 이슈

- Gemini API의 Function Calling은 이번 버전에서 미구현 (향후 버전에서 추가 예정)
- Vertex AI 엔드포인트는 별도 인증이 필요함

---

## 다음 버전 계획

- [ ] Gemini Function Calling (Tool Use) 구현
- [ ] Vertex AI 지원
- [ ] 멀티모달 입력 (이미지) 지원
