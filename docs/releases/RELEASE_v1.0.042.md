# 릴리즈 노트 v1.0.042

> **버전**: v1.0.042  
> **릴리즈 일자**: 2026-02-25  
> **관련 문서**: BUG_v1.0.042_save-workspace-path.md

---

## 개요

`/workspace` 명령어 환경에서 `/save` 작동 시, 변경된 작업 경로가 정상적으로 반영되지 않고 메인 스크립트 실행 위치에 저장되던 심각한 버그를 완벽하게 수정했습니다. 이제 `/save` 명령어는 사용자가 지정한 `/workspace` 위치를 정확히 추적하여 프로젝트 파일시스템에 안전하게 기록합니다.

---

## 버그 픽스 내역

### 1. `/save` 명령어 경로 참조 오류 해결

기존 구현에서는 프로그램이 최초 구동된 현재 위치(`os.getcwd()`)를 기반으로 고정된 `FileManager` 객체를 파서(response_parser)가 계속 참조하는 문제가 있었습니다. `/workspace`로 경로를 옮기더라도 실제 저장 로직에서는 과거 위치를 바라봐 소스 디렉토리가 오염될 수 있었습니다.

**적용된 조치 사항**:
- Assistant 인스턴스에 `change_workspace()` 메서드 추가로 의존성 관리 로직 캡슐화
- `/workspace` 명령 실행 시 `file_manager` 객체를 재생성하고 내부 파서의 참조까지 강력하게 일괄 동기화
- `gemini-ai-chat-code01.py` 및 `claude-ai-chat-code01.py`에 공통 적용 완료

### 2. Claude 어시스턴트 감시 객체 누락 해결

`claude-ai-chat-code01.py`에서 작업 공간 변경 시 파일의 실시간 변경을 감지하는 `file_watcher` 데몬이 재초기화되지 않고 이전 경로를 계속 주시하던 문제를 동반 수정했습니다.

---

## 파일 변경 내역

### 수정 파일

| 파일 | 변경 사항 |
|------|-----------|
| `gemini-ai-chat-code01.py` | `/workspace` 명령 내부 참조 동기화 및 FileWatcher 업데이트 로직 보완 |
| `claude-ai-chat-code01.py` | `/workspace` 명령 내부 참조 동기화 및 FileWatcher 재생성 누락 수복 |
| `tests/test_change_workspace.py` (신규) | 신규 테스트 17건(작업 디렉토리 동적 변경 추적 검증 등) |

---

## 테스트

신규 반영된 구조적 안정성을 보장하기 위해 저장 경로 무결성 테스트가 17개 추가 통과되었습니다.

```bash
python -m unittest tests.test_change_workspace -v
```
