# BUG: File Watcher Deadlock Issue

> **문서 버전**: v1.0.021  
> **작성일**: 2026-01-25  
> **상태**: ✅ Implemented  
> **관련 파일**: src/file_watcher.py

---

## 1. 개요 (Overview)

### 1.1 현상
사용자가 `/watch` 명령어를 실행하여 파일 감시를 시작하려고 하면, 프로그램이 응답하지 않고 멈추는(Hang) 현상이 발생합니다.

### 1.2 재현 방법
1. 애플리케이션 실행
2. 프롬프트에서 `/watch *.py` 입력
3. 명령어 입력 직후 시스템 먹통 발생

---

## 2. 원인 분석 (Root Cause Analysis)

### 2.1 코드 분석
`src/file_watcher.py`의 `FileWatcher` 클래스는 스레드 안전성을 위해 `self._lock` (`threading.Lock`)을 사용합니다.

```python
# src/file_watcher.py

def add_watch(self, pattern: str) -> bool:
    with self._lock:  # (1) Lock 획득
        self.patterns.add(pattern)
        # ...
        if not self._running:
            self.start()  # (2) start() 호출 (Lock 보유 상태)

def start(self) -> bool:
    # ...
    with self._lock:  # (3) Lock 재획득 시도 -> Deadlock 발생!
        if self._running:
            return True
```

### 2.2 기술적 원인
*   **교착 상태 (Deadlock)**: `add_watch` 메서드가 `_lock`을 획득한 상태에서 `start` 메서드를 호출합니다. `start` 메서드는 내부적으로 다시 `_lock` 획득을 시도합니다.
*   **Non-Reentrant Lock**: Python의 기본 `threading.Lock`은 재진입(Reentrant)을 지원하지 않습니다. 즉, **동일한 스레드**라도 이미 획득한 Lock을 다시 획득하려고 하면 무한 대기 상태에 빠집니다.

---

## 3. 해결 방안 (Solution)

### 3.1 권장 수정 방안
`threading.Lock` 대신 `threading.RLock` (Reentrant Lock)을 사용해야 합니다. `RLock`은 동일한 스레드가 Lock을 여러 번 획득하는 것을 허용하며, 획득한 횟수만큼 해제해야 락이 풀리는 구조입니다.

### 3.2 코드 수정 예시

**변경 전:**
```python
self._lock = threading.Lock()
```

**변경 후:**
```python
self._lock = threading.RLock()
```

---

## 4. 검증 계획
1. `src/file_watcher.py` 수정 후 `/watch *.py` 명령 실행.
2. 프로그램이 멈추지 않고 "파일 감시 시작" 메시지가 정상 출력되는지 확인.

---

## 5. 추가 분석 (안전성 검증)

### 5.1 중복 감시 패턴 안전성
Q: `/watch` 명령을 중복 수행하거나 (예: `/watch *.py` 후 다시 `/watch *.py`), 겹치는 패턴을 등록할 경우 (예: `/watch *.py` 후 `/watch calculator.py`) 문제가 발생하는가?

A: **문제 없습니다.** `RLock` 적용 후에도 안정적으로 동작합니다.

### 5.2 이유
1. **자료구조 특성 (Set)**: 감시 패턴을 저장하는 `self.patterns`는 `Set` 자료구조입니다. 중복된 패턴(예: `*.py` 재입력)은 자동으로 병합되어 하나만 유지됩니다.
2. **매칭 로직 (OR 조건)**: `FileChangeHandler`는 등록된 패턴 중 **하나라도 일치하면** 이벤트를 발생시킵니다. `*.py`와 `calculator.py`가 모두 등록되어 있어도, `calculator.py` 수정 시 이벤트는 1회만 발생합니다.
3. **RLock 특성**: `RLock`은 동일 스레드의 중복 락 획득을 허용하므로, 사용자가 명령어를 연속으로 입력해도 데드락 없이 안전하게 처리됩니다.
