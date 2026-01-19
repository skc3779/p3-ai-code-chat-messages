# FSD: GenAI Code Assistant - Claude API 전환 명세

**문서 버전**: v1.0.001  
**작성일자**: 2026-01-19  
**대상 파일**: `gen-ai-chat-code02.py`

---

## 1. 개요

### 1.1 목적
현재 `gen-ai-chat-code02.py`에서 사용 중인 **커스텀 GenAI API**를 **Anthropic Claude API**로 전환하기 위한 최소한의 수정 사항을 정의합니다.

### 1.2 참조 문서
- [Claude API 스트리밍 문서](https://platform.claude.com/docs/ko/build-with-claude/streaming)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)

---

## 2. 현재 구현 분석

### 2.1 현재 API 구조

| 항목 | 현재 구현 |
|------|----------|
| **Endpoint** | `{ENDPOINT_URL}/openapi/chat/v1/messages` |
| **인증** | Custom Headers (`X-Lego-Client-Id`, `X-Lego-Client-Secret`) |
| **모델 지정** | `modelIds` (배열) |
| **메시지 형식** | `contents` (문자열 배열) |
| **스트리밍** | SSE (`isStream: true`, `event_status: CHUNK/DONE`) |

### 2.2 현재 요청 구조 (Lines 354-360)
```python
body = {
    "modelIds": [self.model_id],
    "contents": contents,
    "llmConfig": self.get_llm_config(),
    "isStream": streaming,
    "systemPrompt": self.system_prompt
}
```

### 2.3 현재 SSE 이벤트 처리 (Lines 387-400)
```python
for event in client.events():
    data = json.loads(event.data)
    event_status = data.get('event_status') or data.get('eventStatus')
    if event_status == 'CHUNK':
        content = data.get('content', '')
    elif event_status == 'DONE':
        break
```

---

## 3. Claude API 전환 사양

### 3.1 Claude API 구조

| 항목 | Claude API |
|------|-----------|
| **Endpoint** | `https://api.anthropic.com/v1/messages` |
| **인증** | `x-api-key` Header, `anthropic-version: 2023-06-01` |
| **모델 지정** | `model` (단일 문자열, 예: `claude-sonnet-4-5`) |
| **메시지 형식** | `messages` (역할 기반 객체 배열) |
| **스트리밍** | SSE (`stream: true`, 이벤트 타입 기반) |

### 3.2 Claude API 요청 구조
```python
body = {
    "model": self.model_id,
    "messages": messages,  # [{"role": "user", "content": "..."}]
    "max_tokens": 8192,
    "system": self.system_prompt,
    "stream": True
}
```

### 3.3 Claude SSE 이벤트 처리
```python
# 주요 이벤트 타입
# - message_start: 메시지 시작
# - content_block_delta: 텍스트 청크 (delta.text)
# - message_stop: 메시지 종료

for event in client.events():
    data = json.loads(event.data)
    event_type = data.get('type')
    if event_type == 'content_block_delta':
        text = data.get('delta', {}).get('text', '')
    elif event_type == 'message_stop':
        break
```

---

## 4. 수정 항목

### 4.1 환경 변수 변경

| 현재 | Claude API |
|------|-----------|
| `ENDPOINT_URL` | `CLAUDE_API_ENDPOINT` (기본값: `https://api.anthropic.com`) |
| `YOUR_CLIENT_KEY` | 삭제 |
| `YOUR_CLIENT_SECRET` | `ANTHROPIC_API_KEY` |
| `YOUR_MODEL_ID` | `CLAUDE_MODEL_ID` (기본값: `claude-sonnet-4-5`) |

### 4.2 GenAICodeAssistant 클래스 수정

#### 4.2.1 `__init__` 메서드 수정 (Lines 297-309)
```diff
- def __init__(self, endpoint_url: str, client_key: str, client_secret: str,
-              model_id: str, workspace_dir: str = "."):
-     self.endpoint_url = endpoint_url
-     self.headers = {
-         "X-Lego-Client-Id": client_key,
-         "X-Lego-Client-Secret": client_secret,
-         "Content-Type": "application/json"
-     }
+ def __init__(self, api_key: str, model_id: str = "claude-sonnet-4-5",
+              workspace_dir: str = ".", endpoint_url: str = "https://api.anthropic.com"):
+     self.endpoint_url = endpoint_url
+     self.headers = {
+         "x-api-key": api_key,
+         "anthropic-version": "2023-06-01",
+         "Content-Type": "application/json"
+     }
```

#### 4.2.2 대화 기록 형식 변경 (Lines 306, 351-352)
```diff
- self.conversation_history: List[str] = []
+ self.conversation_history: List[Dict] = []

- contents = self.conversation_history.copy()
- contents.append(full_message)
+ messages = self.conversation_history.copy()
+ messages.append({"role": "user", "content": full_message})
```

#### 4.2.3 API 요청 본문 변경 (Lines 354-362)
```diff
- body = {
-     "modelIds": [self.model_id],
-     "contents": contents,
-     "llmConfig": self.get_llm_config(),
-     "isStream": streaming,
-     "systemPrompt": self.system_prompt
- }
- api_url = f"{self.endpoint_url}/openapi/chat/v1/messages"
+ body = {
+     "model": self.model_id,
+     "messages": messages,
+     "max_tokens": 8192,
+     "system": self.system_prompt,
+     "stream": streaming
+ }
+ api_url = f"{self.endpoint_url}/v1/messages"
```

#### 4.2.4 스트리밍 응답 처리 변경 (Lines 387-400)
```diff
  for event in client.events():
      if event.data:
          try:
              data = json.loads(event.data)
-             event_status = data.get('event_status') or data.get('eventStatus')
-             content = data.get('content', '')
-             if event_status == 'CHUNK' and content:
+             event_type = data.get('type')
+             if event_type == 'content_block_delta':
+                 content = data.get('delta', {}).get('text', '')
+             elif event_type == 'message_stop':
+                 break
+             else:
+                 continue
+             if content:
                  print(content, end="", flush=True)
                  result_message += content
-             elif event_status == 'DONE':
-                 break
          except json.JSONDecodeError:
              continue
```

#### 4.2.5 대화 기록 저장 변경 (Lines 404-408, 425-428)
```diff
- self.conversation_history.append(original_message)
- if result_message:
-     self.conversation_history.append(result_message)
+ self.conversation_history.append({"role": "user", "content": original_message})
+ if result_message:
+     self.conversation_history.append({"role": "assistant", "content": result_message})
```

### 4.3 main 함수 수정 (Lines 499-515)

```diff
- ENDPOINT_URL = os.getenv("ENDPOINT_URL")
- YOUR_CLIENT_KEY = os.getenv("YOUR_CLIENT_KEY")
- YOUR_CLIENT_SECRET = os.getenv("YOUR_CLIENT_SECRET")
- YOUR_MODEL_ID = os.getenv("YOUR_MODEL_ID")
+ ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
+ CLAUDE_MODEL_ID = os.getenv("CLAUDE_MODEL_ID", "claude-sonnet-4-5")
+ CLAUDE_API_ENDPOINT = os.getenv("CLAUDE_API_ENDPOINT", "https://api.anthropic.com")

  assistant = GenAICodeAssistant(
-     endpoint_url=ENDPOINT_URL,
-     client_key=YOUR_CLIENT_KEY,
-     client_secret=YOUR_CLIENT_SECRET,
-     model_id=YOUR_MODEL_ID,
+     api_key=ANTHROPIC_API_KEY,
+     model_id=CLAUDE_MODEL_ID,
+     endpoint_url=CLAUDE_API_ENDPOINT,
      workspace_dir=workspace
  )
```

---

## 5. 의존성 변경

### 5.1 현재 의존성 (유지)
- `requests`
- `sseclient` (또는 `sseclient-py`)
- `python-dotenv`

### 5.2 대안: Anthropic SDK 사용 (선택)
```bash
pip install anthropic
```

> **참고**: 최소 수정을 위해 기존 `requests` + `sseclient` 조합을 유지하는 것을 권장합니다.

---

## 6. 환경 변수 설정 (.env 파일)

```env
# Claude API Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CLAUDE_MODEL_ID=claude-sonnet-4-5
CLAUDE_API_ENDPOINT=https://api.anthropic.com
```

---

## 7. 삭제 가능 코드

| 메서드/함수 | 라인 | 설명 |
|------------|------|------|
| `get_llm_config()` | 322-330 | Claude API에서 불필요 (기본값 사용) |

---

## 8. 검증 체크리스트

- [ ] 환경 변수 설정 완료
- [ ] API 인증 정상 동작
- [ ] 스트리밍 응답 정상 수신
- [ ] 대화 기록 유지 정상 동작
- [ ] 파일 추출/저장 기능 정상 동작

---

## 부록: Claude API 주요 이벤트 타입

| 이벤트 | 설명 |
|--------|------|
| `message_start` | 메시지 시작 (초기 메타데이터 포함) |
| `content_block_start` | 콘텐츠 블록 시작 |
| `content_block_delta` | 텍스트 청크 (`delta.text` 포함) |
| `content_block_stop` | 콘텐츠 블록 종료 |
| `message_delta` | 메시지 메타데이터 업데이트 |
| `message_stop` | 메시지 종료 |
| `ping` | 연결 유지 |
