# Release Notes: Claude Code Assistant v1.0.007

**버전**: v1.0.007  
**릴리즈 날짜**: 2026-01-19  
**타입**: Feature Release

---

## 🎯 릴리즈 개요

Claude Code Assistant v1.0.007에는 **Git 통합 (Git Integration)** 기능이 추가되었습니다. 이제 AI가 코드를 작성하는 것뿐만 아니라, 변경 사항을 Git으로 관리하고 커밋까지 수행할 수 있어 개발 생산성이 크게 향상됩니다.

---

## ✨ 새로운 기능

### 1. Git Tools (Tool Use)

Claude API의 Function Calling을 통해 다음 Git 명령어를 자동으로 수행할 수 있습니다.

| 도구 | 설명 | 예시 시나리오 |
|------|------|---------------|
| `git_status` | 현재 변경된 파일 상태 확인 | "어떤 파일이 수정됐어?" |
| `git_diff` | 상세 변경 내용(Diff) 확인 | "변경 내용 보여줘" |
| `git_add` | 파일 스테이징 | (수정 후 커밋 전 자동 호출) |
| `git_commit` | 커밋 생성 | "수정 사항 커밋해줘" |
| `git_log` | 최근 커밋 내역 조회 | "최근 작업 내역 알려줘" |

**사용 예시**:
> **User**: "방금 만든 테스트 코드 커밋해줘. 메시지는 'Add unit tests'로 해."
> 
> **AI**: 
> 1. `git_status` 호출 -> 변경 파일 확인
> 2. `git_add` 호출 -> 파일 스테이징
> 3. `git_commit(message='Add unit tests')` 호출
> 4. "커밋이 완료되었습니다!" 응답

---

## 🔧 주요 변경 사항

- **`src/git_manager.py`**: Git 명령어를 `subprocess`로 실행하는 관리 클래스 추가. Windows 환경의 인코딩 문제를 해결했습니다.
- **`src/tool_definitions.py`**: Git 관련 5가지 도구 스키마 추가.
- **`src/claude_assistant.py`**: `GitManager` 통합 및 도구 핸들러 추가.

---

## 📋 관련 문서

- [FSD_Interpreter_Optimization_v1.0.007.md](../requrements/FSD_Interpreter_Optimization_v1.0.007.md)

---

## 📝 업데이트 방법

```bash
# 별도의 패키지 설치 필요 없음 (기본 subprocess, pathlib 사용)
# Git이 시스템 경로(PATH)에 설치되어 있어야 합니다.
```
