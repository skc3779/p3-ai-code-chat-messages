# FSD: 스트리밍 에러 핸들링 및 복구 (P2-04)

> **문서 버전**: v1.0.019  
> **작성일**: 2026-01-25  
> **상태**: ✅ Implemented  
> **관련 SRS**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md

---

## 1. 개요

### 1.1 목적
SSE(Server-Sent Events) 스트리밍 도중 네트워크 불안정이나 서버 측 문제로 연결이 끊길 경우, 애플리케이션이 비정상 종료되거나 생성 중이던 응답이 모두 소실되는 문제를 방지합니다.

### 1.2 현재 문제
* `_chat_streaming` 메서드 내 `client.events()` 반복문이 예외 처리 없이 실행됨.
* 스트림 중단 시 `ChunkedEncodingError` 등으로 인한 크래시 발생 가능.
* 중단 시점까지 생성된 데이터가 사용자에게 전달되지 않거나 히스토리에 저장되지 않음.

---

## 2. 기능 요구사항

### 2.1 스트림 예외 처리
* 스트림 소비(consumption) 루프에 대한 예외 처리(Try-Catch) 적용.
* 주요 감지 대상 예외:
    * `requests.exceptions.ChunkedEncodingError`
    * `requests.exceptions.ConnectionError`
    * `requests.exceptions.ReadTimeout`
    * `StopIteration` (비정상 조기 종료)

### 2.2 부분 응답 복구 (Partial Recovery)
* 에러 발생 시점까지 수신한 텍스트 및 도구 호출 데이터는 보존되어야 함.
* 사용자에게 스트림 중단 사실을 명확히 알림 (예: `[⚠️ 네트워크 오류로 응답이 중단되었습니다]`).
* 히스토리에는 중단된 시점까지의 내용이 저장되어야 함.

### 2.3 파일 추출 및 저장 호환성
* 파일 생성 블록(` ```filename:... `)이 완전히 수신된 상태에서 스트림이 끊긴 경우, 해당 파일은 정상적으로 추출/저장 가능해야 함.
* 파일 블록 중간에 끊긴 경우, 불완전한 파일로 저장되지 않도록(또는 경고와 함께 저장되도록) 처리.

---

## 3. 기술 설계

### 3.1 `src/claude_assistant.py` 수정

**`_chat_streaming` 메서드 흐름 개선:**

```python
try:
    for event in client.events():
        # ... 이벤트 처리 ...
except (ChunkedEncodingError, ConnectionError, ReadTimeout) as e:
    # 1. 에러 로그 출력
    print(f"\n[⚠️ 스트리밍 중단: {str(e)}]")
    
    # 2. 사용자 응답에 에러 메시지 추가
    error_msg = "\n\n[⚠️ 네트워크 오류로 인해 응답이 중단되었습니다.]"
    print(error_msg)
    current_message_content.append({"type": "text", "text": error_msg})
    
    # 3. 루프 탈출 후 정상 종료 처리 (finally 블록 불필요, 함수 하단 로직 진행)
```

### 3.2 의존성 확인
* `requests.exceptions` 모듈 import 필요.

---

## 4. 검증 계획

| 항목 | 검증 방법 |
|-----|----------|
| 예외 포착 | 소스 코드 내에서 강제로 `raise ChunkedEncodingError`를 주입하여 테스트 |
| 부분 응답 | 긴 응답 생성 중 강제 중단 시, 앞부분 내용이 히스토리에 남는지 확인 |
| 시스템 안정성 | 에러 후 다음 명령어가 정상적으로 입력 가능한지 확인 |

---

## 5. 버전 히스토리

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0.019 | 2026-01-25 | 초기 FSD 문서 작성 |
