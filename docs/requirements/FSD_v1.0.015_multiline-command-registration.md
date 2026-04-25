# FSD: Multiline Command Registration

> **문서 버전**: v1.0.015  
> **작성일**: 2026-01-25  
> **상태**: Draft

---

## 1. 개요

### 1.1 목적
`/multiline` 명령어를 통해 여러 줄의 텍스트를 한 번에 입력하여 AI에 전송할 수 있도록 지원합니다.

### 1.2 배경
현재 `input()` 함수는 단일 라인만 입력받습니다. 긴 프롬프트나 코드 스니펫을 전송할 때 멀티라인 입력이 필요합니다.

---

## 2. 기능 요구사항

### 2.1 명령어 정의

| 명령어 | 설명 |
|--------|------|
| `/multiline` | 멀티라인 입력 모드 시작 |
| `/end` | 멀티라인 입력 종료 및 전송 |

### 2.2 사용 흐름

```
👤 You: /multiline
📝 멀티라인 모드 (종료: /end 또는 빈 줄 2회)
... 다음 코드를 분석해줘:
... def hello():
...     print("world")
... /end

🤖 AI: [응답]
```

---

## 3. 구현 명세

### 3.1 수정 대상
**파일**: `claude-ai-chat-code01.py`

### 3.2 구현 코드

```python
elif command == '/multiline':
    print("📝 멀티라인 모드 (종료: /end 또는 빈 줄 2회)")
    lines = []
    empty_count = 0
    
    while True:
        line = input("... ")
        
        if line.strip() == '/end':
            break
        
        if line == "":
            empty_count += 1
            if empty_count >= 2:
                break
            lines.append(line)
        else:
            empty_count = 0
            lines.append(line)
    
    multiline_input = "\n".join(lines).strip()
    
    if multiline_input:
        last_response = assistant.chat(multiline_input, streaming=streaming_mode)
    else:
        print("⚠️ 입력이 비어있습니다.")
```

### 3.3 삽입 위치
`claude-ai-chat-code01.py`의 명령어 처리 블록 (`elif command == '/shell'` 이전)에 추가합니다.

---

## 4. 테스트 케이스

| TC | 입력 | 예상 결과 |
|----|------|----------|
| TC-01 | `/multiline` → 텍스트 → `/end` | 정상 전송 |
| TC-03 | `/multiline` → `/end` (바로 종료) | 경고 메시지 출력 |

---

## 5. 버전 히스토리

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0.015 | 2026-01-25 | 초기 문서 작성 |
