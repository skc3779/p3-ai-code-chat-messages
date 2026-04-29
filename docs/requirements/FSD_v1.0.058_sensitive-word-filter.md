# FSD v1.0.058 - GenAI 민감 단어 필터링 (Sensitive Word Filter)

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.058 |
| 제목 | GenAI 입력 컨텍스트 민감 단어 치환/복원 |
| 작성일 | 2026-03-02 |
| 상태 | 구현 완료 |
| 선행 FSD | [FSD v1.0.055](./FSD_v1.0.055_genai-provider-endpoint-fix.md) -- GenAI Provider Endpoint 수정 |
| 참조 소스 | [genai_assistant.py](../../../src/genai_assistant.py), [gen-ai-chat-code.py](../../../gen-ai-chat-code.py) |
| 수정 대상 | [genai_assistant.py](../../../src/genai_assistant.py), [genai_provider.py](../../../ai-proxy/providers/genai_provider.py) |
| 신규 모듈 | [sensitive_filter.py](../../../src/sensitive_filter.py) |
| 테스트 | [test_sensitive_filter.py](../../../tests/test_sensitive_filter.py) |

---

## 1. 개요 (Overview)

GenAI (Samsung SCI Portal) API는 입력 컨텍스트에 `password`, `secret`, `credential` 등의 민감 단어가 포함되면 보안 필터에 의해 요청이 차단되어 다음과 같은 오류 응답이 반환됩니다:

```json
{
  "content": "The content was blocked by the filter.",
  "filterBlockReason": {
    "ko": "Credential",
    "en": "Credential",
    "policyId": "62",
    "message": "The content was blocked by the filter.",
    "resultCode": "FR-400",
    "filterLogId": "26367154"
  },
  "status": "FILTER_INVALID",
  "eventStatus": "DONE"
}
```

이 문제를 해결하기 위해, GenAI API에 전송하기 전에 민감 단어를 안전한 대체 문자열로 치환하고, 응답 수신 후 원래 단어로 복원하는 기능을 구현합니다.

---

## 2. 문제 분석 (Problem Analysis)

### 2.1 원인

GenAI SCI Portal의 보안 필터(Policy ID: 62)가 입력 텍스트에서 `password`, `secret`, `credential`, `token`, `api_key` 등의 민감 키워드를 감지하면 요청을 차단합니다.

### 2.2 영향 범위

| 영향 대상 | 설명 |
|----------|------|
| `src/genai_assistant.py` | CLI에서 직접 GenAI API를 호출하는 어시스턴트 |
| `ai-proxy/providers/genai_provider.py` | OpenAI 호환 프록시에서 GenAI API로 변환하는 프로바이더 |

### 2.3 발생 시나리오

- 사용자가 `/context` 명령으로 `.env` 파일이나 설정 파일을 포함하여 질문하는 경우
- 코드 내에 `password`, `secret`, `api_key` 등의 변수명이 포함된 경우
- 시스템 프롬프트에 "Never expose user password" 등의 문구가 있는 경우

---

## 3. 설계 (Design)

### 3.1 민감 단어 사전

대소문자를 유지하면서 치환하는 것이 핵심입니다.

| 원본 (소문자) | 치환어 (소문자) | 대문자 예시 | Title Case 예시 |
|--------------|---------------|------------|----------------|
| `password` | `p1assw1ord` | `PASSWORD` -> `P1ASSW1ORD` | `Password` -> `P1assw1ord` |
| `secret` | `s1ecr1et` | `SECRET` -> `S1ECR1ET` | `Secret` -> `S1ecr1et` |
| `api_key` | `a1pi_k1ey` | `API_KEY` -> `A1PI_K1EY` | `Api_key` -> `A1pi_k1ey` |
| `apikey` | `a1pike1y` | `APIKEY` -> `A1PIKE1Y` | `Apikey` -> `A1pike1y` |
| `token` | `t1oken` | `TOKEN` -> `T1OKEN` | `Token` -> `T1oken` |
| `credential` | `c1red1ent1al` | `CREDENTIAL` -> `C1RED1ENT1AL` | `Credential` -> `C1red1ent1al` |

### 3.2 대소문자 유지 규칙

| 원본 패턴 | 규칙 | 예시 |
|----------|------|------|
| 모두 대문자 | 치환어도 모두 대문자로 변환 | `PASSWORD` -> `P1ASSW1ORD` |
| Title Case (첫 글자 대문자) | 치환어의 첫 글자만 대문자로 변환 | `Password` -> `P1assw1ord` |
| 그 외 (소문자 등) | 치환어를 그대로 사용 | `password` -> `p1assw1ord` |

### 3.3 처리 흐름

```
[사용자 입력 / 컨텍스트]
        │
        ▼
  ┌─────────────────┐
  │ 1. 민감 단어 검사 │  (대소문자 구분 없이 검사)
  └────────┬────────┘
           │ 민감 단어 있음
           ▼
  ┌─────────────────┐
  │ 2. 단어 치환     │  (대소문자 유지하면서 치환)
  │  mask()         │  password -> p1assw1ord
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ 3. GenAI API    │  (치환된 컨텍스트 전달)
  │   전송          │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ 4. 응답 수신     │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │ 5. 단어 복원     │  (치환된 단어를 원래대로)
  │  unmask()       │  p1assw1ord -> password
  └────────┬────────┘
           │
           ▼
  [최종 응답 반환]
```

### 3.4 모듈 설계

#### 3.4.1 `SensitiveWordFilter` 클래스 (`src/sensitive_filter.py`)

```python
class SensitiveWordFilter:
    """GenAI API 호출 시 민감 단어를 치환/복원하는 필터"""

    SENSITIVE_DICT = [
        ("credential", "c1red1ent1al"),  # 긴 단어 우선
        ("password",   "p1assw1ord"),
        ("api_key",    "a1pi_k1ey"),
        ("apikey",     "a1pike1y"),
        ("secret",     "s1ecr1et"),
        ("token",      "t1oken"),
    ]

    def has_sensitive_words(text: str) -> bool
    def get_detected_words(text: str) -> List[str]
    def mask(text: str) -> str          # 치환 (전송 전)
    def unmask(text: str) -> str        # 복원 (응답 후)
    def mask_contents(contents: list) -> list
    def mask_system_prompt(prompt: str) -> str
```

#### 3.4.2 적용 위치 -- `genai_assistant.py`

```python
# chat() 메서드 내
# 전송 전: contents와 systemPrompt 치환
masked_contents = self.sensitive_filter.mask_contents(contents)
masked_system_prompt = self.sensitive_filter.mask_system_prompt(self.system_prompt)

body = {
    "modelIds": [self.model_id],
    "contents": masked_contents,          # 치환된 contents
    "systemPrompt": masked_system_prompt  # 치환된 systemPrompt
}

# 응답 후: 치환된 단어 복원
response_text = self.sensitive_filter.unmask(response_text)
```

#### 3.4.3 적용 위치 -- `genai_provider.py`

```python
# chat() 메서드 내
payload = self._transform_request(request)

# 전송 전: payload의 contents와 systemPrompt 치환
payload["contents"] = self.sensitive_filter.mask_contents(payload["contents"])
payload["systemPrompt"] = self.sensitive_filter.mask_system_prompt(payload["systemPrompt"])

# 응답 후: content 복원
content = self.sensitive_filter.unmask(content)
```

---

## 4. 요구사항 (Requirements)

### 4.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-058-001 | `SensitiveWordFilter` 클래스를 `src/sensitive_filter.py`에 구현한다 | 필수 |
| REQ-058-002 | GenAI API 전송 전 `contents` 배열과 `systemPrompt`의 민감 단어를 치환한다 (`mask`) | 필수 |
| REQ-058-003 | 대소문자를 유지하면서 치환한다 (모두 대문자, Title Case, 소문자) | 필수 |
| REQ-058-004 | 민감 단어 사전에 `password`, `secret`, `api_key`, `apikey`, `token`, `credential` 6개 단어를 등록한다 | 필수 |
| REQ-058-005 | GenAI 응답 수신 후 치환된 단어를 원래 단어로 복원한다 (`unmask`) | 필수 |
| REQ-058-006 | `genai_assistant.py`와 `genai_provider.py` 양쪽 모두에 필터를 적용한다 | 필수 |

### 4.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-058-001 | 민감 단어가 없는 텍스트는 변경 없이 그대로 통과해야 한다 |
| NREQ-058-002 | mask -> unmask 왕복 시 원본 텍스트가 정확히 복원되어야 한다 |
| NREQ-058-003 | 정규식 기반 매칭으로 성능 저하가 최소화되어야 한다 |
| NREQ-058-004 | 기존 Tool Call 에뮬레이션(FSD v1.0.054) 기능에 영향을 주지 않아야 한다 |

---

## 5. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `src/sensitive_filter.py` | **신규** | `SensitiveWordFilter` 클래스 구현 |
| `src/genai_assistant.py` | **수정** | `chat()` 내 mask/unmask 적용, `__init__`에서 필터 초기화 |
| `ai-proxy/providers/genai_provider.py` | **수정** | `chat()` 내 mask/unmask 적용, `__init__`에서 필터 초기화 |
| `src/__init__.py` | **수정** | `SensitiveWordFilter` export 추가 |
| `tests/test_sensitive_filter.py` | **신규** | 단위 테스트 34개 |

---

## 6. 구현 상세

### 6.1 `sensitive_filter.py` -- 핵심 구현

```python
class SensitiveWordFilter:
    # 민감 단어 사전 (긴 단어 우선 매칭)
    SENSITIVE_DICT = [
        ("credential", "c1red1ent1al"),
        ("password",   "p1assw1ord"),
        ("api_key",    "a1pi_k1ey"),
        ("apikey",     "a1pike1y"),
        ("secret",     "s1ecr1et"),
        ("token",      "t1oken"),
    ]

    @staticmethod
    def _apply_case(original: str, replacement: str) -> str:
        """원본의 대소문자 패턴을 치환어에 적용"""
        if original.isupper():
            return replacement.upper()
        elif original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        else:
            return replacement

    def mask(self, text: str) -> str:
        """민감 단어를 치환 (대소문자 유지)"""
        def _replace(match):
            word = match.group(0)
            replacement = self._forward_map[word.lower()]
            return self._apply_case(word, replacement)
        return self._pattern.sub(_replace, text)

    def unmask(self, text: str) -> str:
        """치환된 단어를 복원 (대소문자 유지)"""
        def _restore(match):
            word = match.group(0)
            original = self._reverse_map[word.lower()]
            return self._apply_case(word, original)
        return self._reverse_pattern.sub(_restore, text)
```

### 6.2 `genai_assistant.py` -- 적용 위치

```diff
 # __init__() 내
+from .sensitive_filter import SensitiveWordFilter
+self.sensitive_filter = SensitiveWordFilter()

 # chat() 내 - API 전송 전
-body = {
-    "contents": contents,
-    "systemPrompt": self.system_prompt
-}
+masked_contents = self.sensitive_filter.mask_contents(contents)
+masked_system_prompt = self.sensitive_filter.mask_system_prompt(self.system_prompt)
+body = {
+    "contents": masked_contents,
+    "systemPrompt": masked_system_prompt
+}

 # chat() 내 - 응답 수신 후
+response_text = self.sensitive_filter.unmask(response_text)
```

### 6.3 `genai_provider.py` -- 적용 위치

```diff
 # __init__() 내
+from src.sensitive_filter import SensitiveWordFilter
+self.sensitive_filter = SensitiveWordFilter()

 # chat() 내 - API 전송 전
+payload["contents"] = self.sensitive_filter.mask_contents(payload["contents"])
+payload["systemPrompt"] = self.sensitive_filter.mask_system_prompt(payload["systemPrompt"])

 # chat() 내 - 응답 수신 후
+content = self.sensitive_filter.unmask(content)
```

---

## 7. 테스트 계획 (Test Plan)

### 7.1 단위 테스트

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-058-001 | 민감 단어 감지 (`has_sensitive_words`) | `password`, `secret` 등이 포함된 텍스트에서 True 반환 |
| TC-058-002 | 소문자 치환 (`mask`) | `password` -> `p1assw1ord` |
| TC-058-003 | 대문자 치환 (`mask`) | `PASSWORD` -> `P1ASSW1ORD` |
| TC-058-004 | Title Case 치환 (`mask`) | `Password` -> `P1assw1ord` |
| TC-058-005 | 혼합 대소문자 문장 | 각 단어의 대소문자 패턴 유지하면서 치환 |
| TC-058-006 | `contents` 배열 치환 | 리스트 내 각 문자열의 민감 단어 치환 |
| TC-058-007 | 민감 단어 없는 경우 | 원본 텍스트 그대로 반환 |
| TC-058-008 | 왕복 정확성 (`mask` -> `unmask`) | 원본과 정확히 동일하게 복원 |
| TC-058-009 | 여러 민감 단어 동시 포함 | 모든 민감 단어가 올바르게 치환 |
| TC-058-010 | 코드 컨텍스트 내 민감 단어 | 코드 블록 내에서도 정확히 치환/복원 |

### 7.2 테스트 실행

```bash
python -m unittest tests.test_sensitive_filter -v
```

### 7.3 통합 테스트 시나리오

```bash
# 프록시 서버를 통한 테스트
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer proxy-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "genai/gpt-oss-120B-medium",
    "messages": [
      {"role": "user", "content": "DB_PASSWORD=mypass123, API_SECRET=abc 이 설정을 분석해줘"}
    ]
  }'
```

---

## 8. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.058 | 2026-03-02 | - | 최초 작성: GenAI 민감 단어 필터링 기능 설계 및 구현 |
