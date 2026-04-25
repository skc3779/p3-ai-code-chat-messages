# FSD: Claude Code Assistant 인터프리터 최적화 기능 보강

**문서 버전**: v1.0.004  
**작성일자**: 2026-01-19  
**수정일자**: 2026-01-19  
**대상 파일**: `claude-ai-chat-code01.py`

---

## 1. 개요

### 1.1 목적
현재 `claude-ai-chat-code01.py`의 기능을 분석하고, **코드 인터프리터 최적화**를 위한 기능 보강 방안을 제시합니다.

### 1.2 현재 기능 분석

| 기능 영역 | 현재 지원 | 설명 |
|-----------|----------|------|
| **파일 읽기** | ✅ | `FileManager.read_file()` |
| **파일 쓰기** | ✅ | `FileManager.write_file()` |
| **디렉토리 탐색** | ✅ | `FileManager.list_files()`, `TreeBuilder` |
| **AI 채팅** | ✅ | Claude API 스트리밍 |
| **컨텍스트 빌드** | ✅ | `ContextBuilder` |
| **파일 추출/저장** | ✅ | `extract_and_save_files()` |
| **코드 실행** | ✅ | `CodeExecutor` (v1.0.003) |
| **터미널 명령** | ✅ **구현 완료** | `TerminalExecutor` (v1.0.004) |
| **Git 통합** | ❌ | 미지원 |
| **패키지 분석** | ❌ | 미지원 |
| **MCP 통합** | ❌ | 미지원 |

---

## 2. 기능 보강 권장 사항

### 2.1 우선순위 평가

| 순위 | 기능 | 효과 | 구현 난이도 | 권장도 | 상태 |
|------|------|------|-------------|--------|------|
| 1 | **코드 실행 환경** | ⭐⭐⭐⭐⭐ | 중 | 🔴 필수 | ✅ 완료 |
| 2 | **터미널/Shell 통합** | ⭐⭐⭐⭐⭐ | 중 | 🔴 필수 | ✅ 완료 |
| 3 | **Filesystem MCP** | ⭐⭐⭐⭐ | 상 | 🟡 권장 | ⏳ 대기 |
| 4 | **Git 통합** | ⭐⭐⭐⭐ | 중 | 🟡 권장 | ⏳ 대기 |
| 5 | **패키지 의존성 분석** | ⭐⭐⭐ | 하 | 🟢 선택 | ⏳ 대기 |

---

## 3. 구현 완료: 코드 실행 환경 (v1.0.003)

### 3.1 CodeExecutor 클래스
- ✅ Python, JavaScript, Bash 코드 실행
- ✅ 타임아웃 처리 (30초)
- ✅ 코드 블록 자동 추출
- ✅ `/run` 명령어

---

## 4. 구현 완료: 터미널/Shell 통합 (v1.0.004)

### 4.1 TerminalExecutor 클래스

```python
class TerminalExecutor:
    """터미널 명령어 실행 - 안전한 쉘 명령 실행 환경"""
    
    ALLOWED_COMMANDS = [
        'python', 'pip', 'node', 'npm', 'git',
        'ls', 'dir', 'cat', 'mkdir', 'echo', ...
    ]
    
    DANGEROUS_COMMANDS = [
        'rm', 'del', 'mv', 'cp', 'chmod', 'kill', ...
    ]
```

### 4.2 주요 메서드

| 메서드 | 설명 |
|--------|------|
| `execute(command, allow_unsafe)` | 명령어 실행 (안전/위험 모드) |
| `get_allowed_commands()` | 허용 명령어 목록 반환 |

### 4.3 기능 특징

- ✅ **안전 모드** (`/shell`): 허용된 명령어만 실행
- ✅ **위험 모드** (`/shell!`): 모든 명령어 허용 (확인 필요)
- ✅ **허용 명령어**: pip, npm, git, ls, dir, cat, mkdir, echo 등
- ✅ **위험 명령어 차단**: rm, del, mv, cp, chmod, curl 등
- ✅ **타임아웃 처리**: 기본 60초
- ✅ **Cross-platform**: Windows/Linux/Mac 지원

### 4.4 추가된 명령어

```
/shell <command>   - 쉘 명령어 실행 (안전 모드)
/shell! <command>  - 쉘 명령어 실행 (위험 명령 허용)
```

### 4.5 사용 예시

```
👤 You: /shell pip list

💻 명령어 실행: pip list

✅ 실행 성공 (return code: 0)

📤 출력:
Package    Version
---------- -------
requests   2.31.0
sseclient  0.0.27
...

👤 You: /shell rm test.txt

❌ 실행 실패
   ⚠️ 위험 명령어: rm
💡 위험 명령을 실행하려면 /shell! 을 사용하세요.

👤 You: /shell! rm test.txt

⚠️  위험 모드: 모든 명령어가 허용됩니다.
▶️  정말 실행하시겠습니까? (y/N): y

💻 명령어 실행: rm test.txt
✅ 실행 성공 (return code: 0)
```

---

## 5. 구현 로드맵

### Phase 1 (v1.1.0) - 필수 기능 ✅ 완료

| 기능 | 예상 공수 | 우선순위 | 상태 |
|------|----------|----------|------|
| `CodeExecutor` 클래스 구현 | 1일 | 🔴 High | ✅ 완료 |
| `/run` 명령어 추가 | 0.5일 | 🔴 High | ✅ 완료 |
| `TerminalExecutor` 클래스 구현 | 1일 | 🔴 High | ✅ 완료 |
| `/shell` 명령어 추가 | 0.5일 | 🔴 High | ✅ 완료 |

### Phase 2 (v1.2.0) - 권장 기능

| 기능 | 예상 공수 | 우선순위 |
|------|----------|----------|
| Claude Tool Use 연동 | 2일 | 🟡 Medium |
| `GitManager` 클래스 구현 | 1일 | 🟡 Medium |
| `/git` 명령어 추가 | 0.5일 | 🟡 Medium |

### Phase 3 (v1.3.0) - 선택 기능

| 기능 | 예상 공수 | 우선순위 |
|------|----------|----------|
| MCP 서버 구현 | 3일 | 🟢 Low |
| 의존성 분석 | 0.5일 | 🟢 Low |
| 웹 검색 통합 | 1일 | 🟢 Low |

---

## 6. 현재 지원 명령어 (v1.0.004)

| 명령어 | 설명 | 버전 |
|--------|------|------|
| `/files` | 프로젝트 파일 목록 | - |
| `/tree` | 프로젝트 구조 보기 | - |
| `/read` | 파일 읽기 | - |
| `/context` | 컨텍스트 포함 질문 | - |
| `/save` | AI 응답에서 파일 저장 | - |
| `/workspace` | 작업 디렉토리 변경 | - |
| `/stream` | 스트리밍 모드 | - |
| `/history` | 대화 히스토리 | - |
| `/clear` | 히스토리 초기화 | - |
| `/run` | 코드 실행 | v1.0.003 |
| `/shell` | 쉘 명령 (안전) | v1.0.004 |
| `/shell!` | 쉘 명령 (위험) | v1.0.004 |
| `/help` | 도움말 | - |
| `/quit` | 종료 | - |

---

## 7. 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0.001 | 2026-01-19 | 최초 작성 |
| v1.0.002 | 2026-01-19 | 수정 |
| v1.0.003 | 2026-01-19 | CodeExecutor 구현, /run 명령어 추가 |
| v1.0.004 | 2026-01-19 | TerminalExecutor 구현, /shell 명령어 추가 |

---

## 8. 참고 자료

- [Claude Tool Use 문서](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [Model Context Protocol](https://modelcontextprotocol.io/)
