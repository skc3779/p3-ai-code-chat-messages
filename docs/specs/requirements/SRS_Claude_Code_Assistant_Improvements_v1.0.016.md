# SRS: Claude Code Assistant 기능 개선 요구사항

> **문서 버전**: v1.0.016  
> **작성일**: 2026-01-25  
> **상태**: Draft  
> **대상 파일**: claude-ai-chat-code01.py, src/claude_assistant.py

---

## 1. 개요

### 1.1 목적
Claude Code Assistant의 현재 소스코드를 분석하여 기능 개선이 필요한 사항을 우선순위별로 정리합니다.

### 1.2 현재 아키텍처
```
claude-ai-chat-code01.py (Entry Point)
├── src/claude_assistant.py (ClaudeCodeAssistant)
│   ├── src/file_manager.py (FileManager)
│   ├── src/context_builder.py (ContextBuilder)
│   ├── src/code_executor.py (CodeExecutor)
│   ├── src/terminal_executor.py (TerminalExecutor)
│   ├── src/git_manager.py (GitManager)
│   ├── src/package_manager.py (PackageManager)
│   └── src/tool_definitions.py (FILESYSTEM_TOOLS)
```

---

## 2. 우선순위별 개선 사항

### 2.1 P1 - Critical (즉시 수정 필요)

| ID | 개선 사항 | 현재 문제 | 개선 방안 | 처리 |
|----|-----------|----------|----------|---|
| P1-01 | `/read` 명령어 System Role 수정 | `role: "system"` 사용으로 API 오류 발생 | `role: "user"` 또는 세션 컨텍스트 방식으로 변경 | 구현완료 |
| P1-02 | 대화 히스토리 토큰 관리 | 히스토리 무제한 누적으로 토큰 초과 가능 | 토큰 수 계산 및 자동 트리밍 기능 추가 | 구현완료 |
| P1-03 | API 오류 재시도 로직 | 네트워크 오류 시 즉시 실패 | 지수 백오프 재시도 로직 구현 | 구현완료 |

**세부 내용:**

**P1-01: `/read` 명령어 System Role 수정**
```python
# 현재 (문제)
history_entry = {"role": "system", "content": context}

# 개선안
history_entry = {"role": "user", "content": f"[파일 컨텍스트]\n{context}"}
```

---

### 2.2 P2 - High (2주 내 개선)

| ID | 개선 사항 | 현재 문제 | 개선 방안 |
|----|-----------|----------|----------|
| P2-01 | 대화 히스토리 저장/로드 | 세션 종료 시 히스토리 손실 | JSON 파일로 히스토리 영속화 |
| P2-02 | 설정 파일 지원 | 하드코딩된 설정값 | `.claude-config.yaml` 설정 파일 지원 |
| P2-03 | 파일 변경 감지 | 수동 `/read` 필요 | watchdog 기반 자동 컨텍스트 갱신 |
| P2-04 | 스트리밍 에러 핸들링 | SSE 스트림 중단 시 복구 불가 | 스트림 재연결 및 부분 응답 복구 |

**세부 내용:**

**P2-01: 대화 히스토리 저장/로드**
```python
# 새 명령어 추가
/save_session <name>  # 현재 세션 저장
/load_session <name>  # 세션 복원
/list_sessions        # 저장된 세션 목록
```

---

### 2.3 P3 - Medium (1개월 내 개선)

| ID | 개선 사항 | 현재 문제 | 개선 방안 |
|----|-----------|----------|----------|
| P3-01 | 프롬프트 템플릿 | 시스템 프롬프트 고정 | 사용자 정의 템플릿 시스템 |
| P3-02 | 플러그인 시스템 | 기능 확장 어려움 | 플러그인 아키텍처 도입 |
| P3-03 | 코드 diff 표시 | AI 수정 코드 전체 출력 | 기존 코드와 diff 비교 출력 |
| P3-04 | 비용 추적 | API 사용량 미추적 | 토큰/비용 계산 및 표시 |
| P3-05 | 자동 완성 | 명령어 수동 입력 | Tab 자동 완성 지원 |

**세부 내용:**

**P3-01: 프롬프트 템플릿**
```yaml
# .claude-prompts/code-review.yaml
name: code-review
description: 코드 리뷰 프롬프트
system_prompt: |
  당신은 시니어 개발자입니다.
  코드 리뷰 시 다음을 확인하세요:
  - 버그 가능성
  - 성능 이슈
  - 코드 스타일
```

---

### 2.4 P4 - Low (분기 내 개선)

| ID | 개선 사항 | 현재 문제 | 개선 방안 |
|----|-----------|----------|----------|
| P4-01 | 테마/컬러 설정 | 고정된 출력 스타일 | 사용자 정의 테마 지원 |
| P4-02 | 로깅 시스템 | 디버깅 어려움 | 구조화된 로깅 추가 |
| P4-03 | 국제화 (i18n) | 한국어만 지원 | 다국어 메시지 지원 |
| P4-04 | Web UI | CLI만 지원 | Flask/FastAPI 기반 Web UI |
| P4-05 | 단축키 지원 | 키보드 단축키 없음 | readline 기반 단축키 |

---

## 3. 신규 기능 제안

### 3.1 대화형 코드 편집
```
/edit <file> <line-range>
AI가 특정 파일의 지정된 라인 범위만 편집
```

### 3.2 코드 검색
```
/search <query>
프로젝트 내 코드 검색 (ripgrep 활용)
```

### 3.3 테스트 자동 생성
```
/test <file>
AI가 해당 파일의 유닛 테스트 자동 생성
```

### 3.4 문서 자동 생성
```
/docs <pattern>
AI가 docstring/JSDoc 자동 생성
```

### 3.5 코드 설명
```
/explain <file> [line-range]
AI가 코드 동작 설명
```

---

## 4. 기술 부채 정리

### 4.1 리팩토링 필요 사항

| 항목 | 현재 상태 | 개선 방향 |
|------|----------|----------|
| 명령어 핸들러 | main() 함수 내 if-elif 체인 | Command 패턴으로 분리 |
| 에러 처리 | try-except 범용 처리 | 커스텀 예외 클래스 도입 |
| 상수 관리 | 코드 내 하드코딩 | constants.py로 분리 |
| 의존성 주입 | 직접 인스턴스 생성 | DI 컨테이너 도입 |

### 4.2 테스트 커버리지

| 모듈 | 현재 상태 | 목표 |
|------|----------|------|
| claude_assistant.py | 테스트 없음 | 70% 이상 |
| code_executor.py | 테스트 없음 | 80% 이상 |
| terminal_executor.py | 테스트 없음 | 80% 이상 |
| file_manager.py | 테스트 없음 | 90% 이상 |

---

## 5. 보안 개선

| ID | 항목 | 현재 위험 | 개선 방안 |
|----|------|----------|----------|
| S-01 | API 키 관리 | .env 평문 저장 | keyring 라이브러리 활용 |
| S-02 | 코드 실행 샌드박싱 | 직접 실행 | Docker 컨테이너 격리 |
| S-03 | 파일 접근 제한 | 모든 파일 읽기 가능 | 화이트리스트 기반 제한 |
| S-04 | 입력 검증 | 미검증 | 경로 traversal 방지 |

---

## 6. 구현 로드맵

```
Phase 1 (1-2주): P1 Critical 수정
├── P1-01: /read 명령어 수정
├── P1-02: 토큰 관리 추가
└── P1-03: 재시도 로직 구현

Phase 2 (3-4주): P2 High 개선
├── P2-01: 세션 저장/로드
├── P2-02: 설정 파일 지원
└── P2-04: 스트리밍 에러 핸들링

Phase 3 (1-2개월): P3 Medium 개선
├── P3-01: 프롬프트 템플릿
├── P3-03: 코드 diff 표시
└── P3-04: 비용 추적

Phase 4 (분기): P4 + 신규 기능
├── 플러그인 시스템
├── Web UI
└── 고급 기능 추가
```

---

## 7. 버전 히스토리

| 버전 | 날짜 | 작성자 | 변경 내용 |
|------|------|--------|----------|
| v1.0.016 | 2026-01-25 | AI Assistant | 초기 SRS 문서 작성 |
