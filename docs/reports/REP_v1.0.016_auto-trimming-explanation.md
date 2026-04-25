# REF: 대화 히스토리 자동 트리밍 기능 설명

> **문서 버전**: v1.0.016  
> **작성일**: 2026-01-25  
> **관련 문서**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md (P1-02)

---

## 1. 자동 트리밍이란?

### 1.1 정의
**자동 트리밍(Auto Trimming)**은 대화 히스토리가 API 토큰 한도에 근접할 때, **오래된 메시지를 자동으로 제거**하여 토큰 한도 내에서 대화를 유지하는 기능입니다.

### 1.2 왜 필요한가?

Claude API는 **컨텍스트 윈도우 제한**이 있습니다:

| 모델 | 최대 토큰 |
|------|----------|
| Claude 3.5 Sonnet | 200,000 토큰 |
| Claude 3 Opus | 200,000 토큰 |

현재 Claude Code Assistant는 대화가 계속될수록 `conversation_history`에 메시지가 **무한히 누적**됩니다:

```python
# claude_assistant.py - 현재 코드
self.conversation_history.append({"role": "user", "content": message})
self.conversation_history.append({"role": "assistant", "content": response})
# ... 계속 추가됨 (제거 없음)
```

결과적으로:
- 대화가 길어지면 → 토큰 한도 초과 → API 에러 발생
- 특히 `/read` 명령어로 큰 파일을 여러 개 읽으면 급격히 증가

---

## 2. 문제 시나리오

### 2.1 토큰 초과 예시

```
[대화 시작]
├── 사용자: 안녕하세요 (10 토큰)
├── AI: 안녕하세요! (20 토큰)
├── /read main.py (5,000 토큰)
├── 사용자: 분석해줘 (10 토큰)
├── AI: [분석 결과] (3,000 토큰)
├── /read utils.py (4,000 토큰)
├── /read config.py (2,000 토큰)
├── ... (계속 누적)
└── 총 누적: 150,000 토큰 → 다음 요청에서 한도 초과!
```

### 2.2 현재 발생하는 에러

```json
{
  "error": {
    "type": "invalid_request_error",
    "message": "prompt is too long: 205432 tokens > 200000 maximum"
  }
}
```

---

## 3. 자동 트리밍 동작 방식

### 3.1 기본 원리

```
[트리밍 전]                          [트리밍 후]
┌─────────────────────┐             ┌─────────────────────┐
│ 메시지 1 (오래됨)   │ ← 제거      │                     │
│ 메시지 2 (오래됨)   │ ← 제거      │                     │
│ 메시지 3            │ ← 제거      │                     │
│ 메시지 4            │             │ 메시지 4            │
│ 메시지 5            │             │ 메시지 5            │
│ 메시지 6 (최신)     │             │ 메시지 6 (최신)     │
│ [새 메시지 추가]    │             │ [새 메시지 추가]    │
└─────────────────────┘             └─────────────────────┘
     150,000 토큰                        80,000 토큰
```

### 3.2 트리밍 전략

#### 전략 A: FIFO (First-In-First-Out)
가장 오래된 메시지부터 순차적으로 제거

```python
while total_tokens > MAX_TOKENS * 0.8:  # 80% 임계값
    conversation_history.pop(0)  # 가장 오래된 메시지 제거
    total_tokens = calculate_tokens(conversation_history)
```

#### 전략 B: 중요도 기반
- 시스템 프롬프트: 절대 제거 안 함
- 파일 컨텍스트: 우선 제거 (다시 `/read` 가능)
- 최근 N개 대화: 보존

```python
# 우선순위
PRIORITY = {
    "system_prompt": 0,      # 절대 유지
    "recent_messages": 1,    # 유지 (최근 10개)
    "file_context": 2,       # 우선 제거
    "old_messages": 3        # 제거 대상
}
```

#### 전략 C: 슬라이딩 윈도우
최근 N개의 메시지만 유지

```python
MAX_HISTORY_SIZE = 20  # 최근 20개 메시지만 유지
conversation_history = conversation_history[-MAX_HISTORY_SIZE:]
```

---

## 4. 구현 예시

### 4.1 토큰 계산 함수

```python
import tiktoken

def count_tokens(messages: list, model: str = "claude-3-sonnet") -> int:
    """메시지 리스트의 총 토큰 수 계산"""
    # Claude는 tiktoken의 cl100k_base 인코딩과 유사
    encoding = tiktoken.get_encoding("cl100k_base")
    
    total_tokens = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_tokens += len(encoding.encode(content))
        elif isinstance(content, list):  # tool_use 등
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    total_tokens += len(encoding.encode(item["text"]))
    
    return total_tokens
```

### 4.2 자동 트리밍 함수

```python
def auto_trim_history(
    conversation_history: list,
    max_tokens: int = 150000,  # 안전 마진 (200K의 75%)
    keep_recent: int = 6       # 최소 유지할 메시지 수
) -> list:
    """히스토리가 토큰 한도를 초과하면 오래된 메시지 제거"""
    
    current_tokens = count_tokens(conversation_history)
    
    if current_tokens <= max_tokens:
        return conversation_history  # 트리밍 불필요
    
    print(f"⚠️ 토큰 한도 초과 ({current_tokens:,} > {max_tokens:,})")
    print(f"🔄 자동 트리밍 시작...")
    
    # 최소 유지 메시지 수 확보
    while len(conversation_history) > keep_recent:
        # 가장 오래된 메시지 제거
        removed = conversation_history.pop(0)
        current_tokens = count_tokens(conversation_history)
        
        print(f"   - 메시지 제거 (남은 토큰: {current_tokens:,})")
        
        if current_tokens <= max_tokens:
            break
    
    print(f"✅ 트리밍 완료 (최종 토큰: {current_tokens:,})")
    return conversation_history
```

### 4.3 적용 위치

```python
# claude_assistant.py의 chat() 메서드 내
def chat(self, user_message: str, ...):
    # API 호출 전 트리밍 실행
    self.conversation_history = auto_trim_history(
        self.conversation_history,
        max_tokens=150000
    )
    
    # 기존 API 호출 로직
    messages = self.conversation_history.copy()
    messages.append({"role": "user", "content": user_message})
    ...
```

---

## 5. 사용자 알림

### 5.1 트리밍 발생 시 출력

```
⚠️ 대화 히스토리가 토큰 한도에 근접했습니다.
🔄 오래된 메시지 3개를 자동으로 정리했습니다.
📊 현재 토큰: 145,230 / 200,000 (72%)
💡 /clear 명령어로 히스토리를 수동 초기화할 수 있습니다.
```

### 5.2 토큰 상태 표시 명령어 (신규)

```
👤 You: /tokens

📊 토큰 사용량:
   현재:    145,230 토큰
   한도:    200,000 토큰
   사용률:  72.6%
   
   히스토리: 24개 메시지
   시스템:   1,500 토큰
   대화:     143,730 토큰
```

---

## 6. 요약

| 항목 | 설명 |
|------|------|
| **문제** | 대화가 길어지면 토큰 한도 초과로 API 에러 발생 |
| **해결책** | 자동 트리밍 - 오래된 메시지 자동 제거 |
| **트리거** | 토큰 수가 설정 임계값(예: 75%)을 초과할 때 |
| **전략** | FIFO, 중요도 기반, 슬라이딩 윈도우 중 선택 |
| **사용자 경험** | 트리밍 발생 시 알림 + `/tokens` 명령어로 상태 확인 |

---

## 7. 버전 히스토리

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|----------|
| v1.0.016 | 2026-01-25 | AI Assistant | 초기 REF 문서 작성 |
