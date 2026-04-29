# FSD v1.0.066 - API 응답 대기 UI(스피너) 구현

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.066 |
| 제목 | API 응답 대기 UI(스피너) 구현 |
| 작성일 | 2026-03-03 |
| 상태 | 설계 완료 |
| 대상 소스 | `gemini-ai-chat-code.py`, `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `src/spinner.py` (신규) |

---

## 1. 개요 (Overview)

현재 CLI 기반 챗봇(`gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py`)에서 사용자가 질문을 입력하고 나면, AI 모델의 API 응답이 도착할 때까지 화면이 정지된 것처럼 보여 사용자가 처리가 진행 중인지 알기 어렵습니다. 
이를 해결하기 위해, 질문 입력 후 응답을 대기하는 동안 "답변 진행 중"임을 알리는 동적인 로딩 UI(Spinner)를 구현하여 사용자 경험(UX)을 개선합니다.

### 1.1 개선 목표

| # | 목표 | 설명 |
|---|------|------|
| 1 | 로딩 UI 제공 | API 호출 시작부터 첫 응답 도착 전까지 텍스트 기반 스피너 렌더링 |
| 2 | 스레드 기반 비동기 동작 | 메인 동작(API 호출)을 블록하지 않고 별도 스레드에서 UI 출력 |
| 3 | 공통 유틸리티 적용 | `src/spinner.py` 형태로 클래스를 생성해 3개 챗봇 모두 동일한 UX 제공 |
| 4 | 스트리밍/논스트리밍 지원 | 두 모드 모두에서 응답이 시작되기 직전까지 로딩 UI 표시 |

---

## 2. 설계 (Design)

### 2.1 스피너 유틸리티 (`src/spinner.py`) 설계
파이썬의 내장 `threading` 모듈과 `sys.stdout`을 이용해 콘솔에서 돌아가는 애니메이션(예: `|`, `/`, `-`, `\`)을 구현합니다.
- **클래스명**: `WaitSpinner`
- **구현 방식**: 파이썬 컨텍스트 매니저(`with` 구문)를 지원하여, 블록 내에서 실행되는 작업 동안만 스피너가 돌도록 구현.
- **메시지 커스터마이징**: "🤖 AI가 답변을 고민 중입니다..." 와 같은 문구를 출력.

#### 동작 예시 코드 (컨셉)
```python
import sys
import time
import threading

class WaitSpinner:
    def __init__(self, message="진행 중..."):
        self.message = message
        self.running = False
        self.spinner_thread = None

    def spin(self):
        chars = ['|', '/', '-', '\\']
        idx = 0
        while self.running:
            sys.stdout.write(f"\r{chars[idx]} {self.message}")
            sys.stdout.flush()
            idx = (idx + 1) % len(chars)
            time.sleep(0.1)
        sys.stdout.write('\r' + ' ' * (len(self.message) + 2) + '\r')
        sys.stdout.flush()

    def __enter__(self):
        self.running = True
        self.spinner_thread = threading.Thread(target=self.spin)
        self.spinner_thread.start()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()
```

### 2.2 메인 스크립트 연동
각 `*-chat-code.py` 최상단 커맨드 반복문 내부에서 `assistant.chat()` 메서드를 호출할 때 스피너를 연동할지 검토.
하지만, 스트리밍의 경우 응답 청크(`chunk`)가 떨어지기 시작하면 바로 스피너가 종료되고 답변이 출력되어야 합니다.
따라서 스피너는 `assistant.chat()`이 호출되고 **첫 번째 응답이 오기 전까지** 유지되어야 합니다.
- **방안**: `assistant.chat()` 호출부 밖에서 래핑(`with WaitSpinner(): assistant.chat(...)`)할 경우, 논스트리밍은 문제없으나 스트리밍은 `chat()`이 전부 종료될 때까지 스피너가 돌게 됩니다.
- **해결책**:
  1. 각 `assistant` 클래스(`claude_assistant.py`, `gemini_assistant.py`, `genai_assistant.py`)의 내부 `_chat_streaming` 및 `_chat_non_streaming` 함수에서 **API 요청(requests.post) 직전**에 스피너를 실행(`start()`)하고, **Response가 도착하여 첫 출력을 시작하기 직전**에 스피너를 종료(`stop()`)합니다. 

---

## 3. 요구사항 (Requirements)

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-066-001 | 텍스트 기반 로딩 애니메이션을 렌더링하는 `WaitSpinner` 유틸리티를 `src/spinner.py`에 구현한다. | 필수 |
| REQ-066-002 | 질문을 입력 후 API 호출 시 스피너가 나타나며, 첫 번째 응답이 화면에 출력되기 전에 스피너가 깔끔하게 지워져야 한다. | 필수 |
| REQ-066-003 | `claude_assistant.py`의 스트리밍 및 논스트리밍 호출 로직에 적용한다. | 필수 |
| REQ-066-004 | `gemini_assistant.py`의 스트리밍 및 논스트리밍 호출 로직에 적용한다. | 필수 |
| REQ-066-005 | `genai_assistant.py`의 스트리밍 및 논스트리밍 호출 로직에 적용한다. | 필수 |

### 3.2 비기능/그 외 필요사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| NREQ-066-001 | 화면 깜빡임이 없어야 하며, 텍스트가 깨지지 않고 동일한 라인(`\r` 캐리지 리턴 사용)에서 제자리 애니메이션이 동작해야 한다. | UX 최적화 |
| NREQ-066-002 | 예외(Exception)나 API Error가 발생 시, 스피너 스레드가 멈추지 않고 고아 프레세스가 되는 상황을 방지하기 위해 `finally`나 `Exception` 캐치 구문 내에서 반드시 `stop()` 처리해야 한다. | 안정성 |

---

## 4. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.066 | 2026-03-03 | - | 최초 작성: 질문 입력 후 대기/진행 중 표시 UI(Spinner) 적용 상세 |
