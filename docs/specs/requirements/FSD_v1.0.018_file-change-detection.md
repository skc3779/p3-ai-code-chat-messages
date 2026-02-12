# FSD: 파일 변경 감지 기능 (P2-03)

> **문서 버전**: v1.0.018  
> **작성일**: 2026-01-25  
> **상태**: ✅ Implemented  
> **관련 SRS**: SRS_Claude_Code_Assistant_Improvements_v1.0.016.md

---

## 1. 개요

### 1.1 목적
현재 `/read` 명령으로 수동 파일 로딩이 필요한 구조를 개선하여, watchdog 라이브러리 기반의 파일 변경 자동 감지 기능을 구현합니다.

### 1.2 현재 문제
| 항목 | 설명 |
|-----|------|
| 수동 갱신 필요 | 파일 수정 시 `/read` 명령 재실행 필요 |
| 컨텍스트 불일치 | AI가 outdated 파일 내용으로 응답 가능 |
| 사용자 경험 저하 | 반복적인 수동 작업으로 생산성 감소 |

---

## 2. 기능 요구사항

### 2.1 핵심 기능
- 읽어들인 파일의 변경 사항 실시간 감지
- 변경 감지 시 자동으로 컨텍스트 갱신
- 변경 알림 메시지 표시

### 2.2 사용자 명령어
```
/watch <pattern>    # 파일 감시 시작 (예: /watch *.py)
/unwatch <pattern>  # 파일 감시 중지
/watch_list         # 현재 감시 중인 파일 목록
```

---

## 3. 기술 설계

### 3.1 의존성
```
watchdog>=3.0.0
```

### 3.2 구현 구조
```
src/
└── file_watcher.py  # FileWatcher 클래스 (신규)
```

### 3.3 핵심 클래스
```python
class FileWatcher:
    def __init__(self, callback: Callable):
        """callback: 파일 변경 시 호출될 함수"""
        
    def add_watch(self, pattern: str) -> None:
        """감시 대상 추가"""
        
    def remove_watch(self, pattern: str) -> None:
        """감시 대상 제거"""
        
    def get_watched_files(self) -> List[str]:
        """감시 중인 파일 목록 반환"""
        
    def start(self) -> None:
        """백그라운드 감시 시작"""
        
    def stop(self) -> None:
        """감시 중지"""
```

---

## 4. 통합 포인트

### 4.1 ClaudeCodeAssistant 수정
- `FileWatcher` 인스턴스 초기화
- `/watch`, `/unwatch`, `/watch_list` 명령어 핸들러 추가
- 파일 변경 콜백에서 `ContextBuilder` 자동 갱신 호출

---

## 5. 검증 계획

| 항목 | 검증 방법 |
|-----|----------|
| 변경 감지 | 파일 수정 후 콘솔 알림 확인 |
| 컨텍스트 갱신 | 변경 후 AI 응답에 최신 내용 반영 확인 |
| 다중 파일 | 여러 파일 동시 감시 동작 확인 |

---

## 6. 버전 히스토리

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0.018 | 2026-01-25 | 초기 FSD 문서 작성 |
