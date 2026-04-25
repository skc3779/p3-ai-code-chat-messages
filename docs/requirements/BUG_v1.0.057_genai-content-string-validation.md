# BUG v1.0.057 - GenAI Provider contents 필드 문자열 변환 오류

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.057 |
| 제목 | GenAI Provider — contents 배열에 객체 삽입 시 `Input should be a valid string` 오류 |
| 작성일 | 2026-03-02 |
| 상태 | 수정 완료 |
| 관련 FSD | [FSD v1.0.055](./FSD_v1.0.055_genai-provider-endpoint-fix.md) — Endpoint URL 구조 수정 |
| 수정 대상 | [models.py](../../../ai-proxy/models.py), [genai_provider.py](../../../ai-proxy/providers/genai_provider.py), [claude_provider.py](../../../ai-proxy/providers/claude_provider.py) |

---

## 1. 버그 설명

### 1.1 증상

GenAI 모델로 요청 시 `Input should be a valid string` Pydantic 검증 오류가 발생합니다.

### 1.2 재현 조건

OpenCode/AI SDK가 `content`를 **문자열이 아닌 content parts 배열**로 전송할 때 발생합니다:

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "이 코드를 분석해줘"},
    {"type": "text", "text": "function hello() { return 'world'; }"}
  ]
}
```

OpenAI API 사양에서 `content`는 두 가지 형태가 허용됩니다:

| 형태 | 예시 | 용도 |
|------|------|------|
| **문자열** | `"Hello"` | 일반 텍스트 메시지 |
| **content parts 배열** | `[{"type":"text","text":"Hello"}, ...]` | 멀티모달 입력 (텍스트+이미지 등) |

### 1.3 원인 분석

#### 원인 1: Pydantic 모델 타입 제한 (`models.py`)

```python
# models.py (수정 전) — content가 str만 허용
class ChatMessage(BaseModel):
    content: Optional[str] = None   # ← 배열 수신 시 검증 실패!
```

`content`가 `str` 타입으로만 정의되어 있어, 배열 형태의 content를 수신하면 Pydantic이 **`Input should be a valid string`** 에러를 발생시킵니다.

#### 원인 2: 문자열 가정 사용 (`genai_provider.py`)

```python
# genai_provider.py (수정 전) — content를 문자열로 가정
contents.append(f"[User Context]\n{m.content or ''}")
#                                    ↑ content가 리스트이면 "[User Context]\n[{'type': 'text', ...}]"
```

`_transform_request()`에서 `m.content`를 f-string에 직접 삽입하므로, content가 리스트인 경우 `contents` 배열에 객체가 포함된 문자열이 생성됩니다.

---

## 2. 수정 내역

### 2.1 `models.py` — content 타입 확장 + 변환 헬퍼

```python
# 수정 후
class ChatMessage(BaseModel):
    content: Optional[Union[str, list]] = None  # ★ str 또는 list 허용

    def content_as_str(self) -> str:
        """
        content를 문자열로 변환하여 반환.
        - str → 그대로 반환
        - list → text 부분만 추출하여 결합
        - None → 빈 문자열
        """
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, list):
            parts = []
            for part in self.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    else:
                        parts.append(f"[{part.get('type', 'unknown')}]")
                elif isinstance(part, str):
                    parts.append(part)
                else:
                    parts.append(str(part))
            return "\n".join(parts)
        return str(self.content)
```

### 2.2 `genai_provider.py` — `m.content` → `m.content_as_str()` 전환

| 위치 | 수정 전 | 수정 후 |
|------|---------|---------|
| L170 (system) | `m.content or ""` | `m.content_as_str()` |
| L175-176 (assistant+tool_calls) | `m.content` | `m.content_as_str()` |
| L195 (tool role) | `m.content or ''` | `m.content_as_str()` |
| L201 (user) | `m.content or ''` | `m.content_as_str()` |
| L203 (assistant) | `m.content or ''` | `m.content_as_str()` |

### 2.3 `claude_provider.py` — 동일 수정 적용

| 위치 | 수정 전 | 수정 후 |
|------|---------|---------|
| L122 (system) | `m.content` | `m.content_as_str()` |
| L129-130 (assistant text) | `m.content` | `m.content_as_str()` |
| L157 (tool result) | `tm.content or ""` | `tm.content_as_str()` |
| L165 (일반 메시지) | `m.content or ""` | `m.content_as_str()` |

---

## 3. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `ai-proxy/models.py` | **수정** | `ChatMessage.content` 타입 `Optional[str]` → `Optional[Union[str, list]]`, `content_as_str()` 헬퍼 추가 |
| `ai-proxy/providers/genai_provider.py` | **수정** | `m.content` → `m.content_as_str()` 전환 (5개소) |
| `ai-proxy/providers/claude_provider.py` | **수정** | `m.content` → `m.content_as_str()` 전환 (4개소) |

---

## 4. 검증 시나리오

| # | 입력 content 형태 | 예시 | `content_as_str()` 결과 | 판정 |
|---|-------------------|------|------------------------|:----:|
| 1 | 문자열 | `"Hello"` | `"Hello"` | ✅ |
| 2 | content parts 배열 (text) | `[{"type":"text","text":"Hello"}]` | `"Hello"` | ✅ |
| 3 | content parts 배열 (다중) | `[{"type":"text","text":"A"},{"type":"text","text":"B"}]` | `"A\nB"` | ✅ |
| 4 | content parts 배열 (image) | `[{"type":"text","text":"분석"},{"type":"image_url","url":"..."}]` | `"분석\n[image_url]"` | ✅ |
| 5 | None | `null` | `""` | ✅ |
| 6 | 문자열 배열 | `["Hello", "World"]` | `"Hello\nWorld"` | ✅ |

---

## 5. 변경 이력

| 버전 | 날짜 | 내용 |
|------|------|------|
| v1.0.057 | 2026-03-02 | 최초 작성: GenAI Provider contents 필드 문자열 변환 오류 수정 |
