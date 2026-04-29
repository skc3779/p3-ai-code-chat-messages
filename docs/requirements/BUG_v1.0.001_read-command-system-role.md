# BUG Report: `/read` 명령어 System Role 사용 오류

> **문서 버전**: v1.0.001  
> **작성일**: 2026-01-25  
> **상태**: Open  
> **심각도**: Critical  
> **영향 범위**: `/read` 명령어 사용 후 모든 후속 API 호출 실패

---

## 1. 개요

### 1.1 버그 요약
`/read <filename>` 명령어 실행 후 후속 질문을 하면 Claude Messages API에서 `400 Bad Request` 오류가 발생합니다.

### 1.2 오류 메시지
```
API Error: 400 - {
  "type": "error",
  "error": {
    "type": "invalid_request_error",
    "message": "messages: Unexpected role \"system\". The Messages API accepts a top-level `system` parameter, not \"system\" as an input message role."
  },
  "request_id": "req_011CXSyUgR4EhfV8dKsJ6Gzt"
}
```

---

## 2. 재현 단계

### 2.1 Reproduction Steps
1. `python3 claude-ai-chat-code01.py` 실행
2. `/read calculator.py` 명령어 입력 (정상 출력)
3. `calculator.py 소스코드 기능 분석해줘` 질문 입력
4. **오류 발생**: API 400 에러

### 2.2 예상 동작
- `/read` 명령어로 읽은 파일 컨텍스트가 히스토리에 저장됨
- 후속 질문 시 해당 컨텍스트를 참조하여 AI가 응답

### 2.3 실제 동작
- `/read` 명령어로 파일 컨텍스트가 `"role": "system"`으로 히스토리에 추가됨
- 후속 API 호출 시 `messages` 배열에 `system` role이 포함되어 API 오류 발생

---

## 3. 근본 원인 분석

### 3.1 문제 코드 위치
**파일**: `claude-ai-chat-code01.py`  
**라인**: 180-183

```python
if matched_files:
    context = assistant.context_builder.build_files_context(matched_files)
    history_entry = {"role": "system", "content": context }  # ❌ 문제 발생 지점
    assistant.conversation_history.append(history_entry)
    print(context)
```

### 3.2 Claude Messages API 구조

Claude Messages API는 다음과 같은 구조를 요구합니다:

```python
body = {
    "model": "claude-sonnet-4-5",
    "messages": [
        {"role": "user", "content": "..."},      # ✅ 허용
        {"role": "assistant", "content": "..."}  # ✅ 허용
        # {"role": "system", ...}                # ❌ 불허용
    ],
    "system": "시스템 프롬프트 내용",              # ✅ system은 top-level 파라미터
    "max_tokens": 8192
}
```

**참고**: `claude_assistant.py` (107-114줄)에서 올바르게 `system` 파라미터를 사용하고 있음:

```python
body = {
    "model": self.model_id,
    "messages": messages,
    "max_tokens": 8192,
    "system": self.system_prompt,  # ← 올바른 사용
    "tools": FILESYSTEM_TOOLS,
    "stream": streaming
}
```

### 3.3 문제 발생 흐름

```
[/read calculator.py]
         ↓
history_entry = {"role": "system", "content": context}
         ↓
conversation_history = [{"role": "system", "content": "..."}]
         ↓
[후속 질문 입력]
         ↓
messages = conversation_history.copy()  ← system role 포함
messages.append({"role": "user", "content": "..."})
         ↓
API 호출 → 400 Error (system role in messages)
```

---

## 4. 해결 방안

### 4.1 Option A: User Role로 변경 (권장)

파일 컨텍스트를 `user` role로 추가하여 "사용자가 파일 내용을 제공한 것"으로 처리:

```python
if matched_files:
    context = assistant.context_builder.build_files_context(matched_files)
    # ✅ 수정: user role로 변경
    history_entry = {"role": "user", "content": f"[파일 컨텍스트]\n{context}"}
    assistant.conversation_history.append(history_entry)
    
    # AI의 확인 응답도 추가 (선택적)
    assistant.conversation_history.append({
        "role": "assistant", 
        "content": "파일 내용을 확인했습니다. 질문해 주세요."
    })
    print(context)
```

**장점**:
- Messages API 규격 준수
- 대화 흐름 유지
- AI가 컨텍스트를 참조할 수 있음

### 4.2 Option B: System Prompt에 동적 추가

`system` 파라미터에 파일 컨텍스트를 동적으로 포함:

```python
# claude_assistant.py 수정
def chat(self, user_message: str, ..., additional_context: str = None):
    system = self.system_prompt
    if additional_context:
        system = f"{self.system_prompt}\n\n[추가 컨텍스트]\n{additional_context}"
    
    body = {
        "model": self.model_id,
        "messages": messages,
        "system": system,  # ← 동적 system 프롬프트
        ...
    }
```

**장점**:
- API 규격 준수
- 컨텍스트가 system level에서 처리됨

**단점**:
- `chat` 메서드 수정 필요
- 컨텍스트가 히스토리에 영구 저장되지 않음

### 4.3 Option C: 세션 컨텍스트 별도 관리

별도의 `session_context` 속성을 두어 관리:

```python
class ClaudeCodeAssistant:
    def __init__(self, ...):
        self.session_context = []  # 파일 컨텍스트 저장용
        
    def add_file_context(self, context: str):
        self.session_context.append(context)
        
    def chat(self, ...):
        combined_system = self.system_prompt
        if self.session_context:
            combined_system += "\n\n[세션 컨텍스트]\n" + "\n".join(self.session_context)
        ...
```

---

## 5. 권장 수정 사항

### 5.1 즉시 수정 (Quick Fix)

**파일**: `claude-ai-chat-code01.py`  
**라인**: 182

```diff
- history_entry = {"role": "system", "content": context }
+ history_entry = {"role": "user", "content": f"[파일 컨텍스트 로드됨]\n{context}"}
```

### 5.2 추가 권장 사항

1. `/read` 명령어 실행 후 AI의 확인 응답을 히스토리에 추가하여 user/assistant 쌍 유지
2. `/clear` 명령어가 올바르게 히스토리를 초기화하는지 확인
3. `/context` 명령어도 동일한 패턴을 사용하는지 검토

---

## 6. 영향 분석

### 6.1 영향 받는 기능
| 기능 | 영향도 | 설명 |
|------|--------|------|
| `/read` | Critical | 사용 후 모든 후속 채팅 불가 |
| `/context` | 확인 필요 | 동일 패턴 사용 시 동일 문제 발생 가능 |
| 일반 채팅 | 정상 | `/read` 미사용 시 정상 동작 |

### 6.2 회귀 테스트 항목
- [ ] `/read <file>` 후 일반 질문 정상 동작
- [ ] `/read` 다회 사용 후 질문 정상 동작
- [ ] `/read` 후 `/clear` 후 질문 정상 동작
- [ ] `/context` 명령어 정상 동작

---

## 7. 참조

### 7.1 관련 파일
- `claude-ai-chat-code01.py` (182줄)
- `src/claude_assistant.py` (107-114줄)

### 7.2 API 문서
- [Claude Messages API](https://docs.anthropic.com/en/api/messages)
- Messages API는 `messages` 배열에서 `user`와 `assistant` role만 허용
- `system` 컨텐츠는 top-level `system` 파라미터로 전달 필수

---

## 8. 버전 히스토리

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|----------|
| v1.0.001 | 2026-01-25 | AI Assistant | 초기 BUG 문서 작성 |
