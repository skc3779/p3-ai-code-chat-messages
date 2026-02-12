# FSD: Claude Code Assistant 인터프리터 최적화 기능 보강

**문서 버전**: v1.0.003  
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
| **코드 실행** | ✅ **구현 완료** | `CodeExecutor` (v1.0.003) |
| **터미널 명령** | ❌ | 미지원 |
| **Git 통합** | ❌ | 미지원 |
| **패키지 분석** | ❌ | 미지원 |
| **MCP 통합** | ❌ | 미지원 |

---

## 2. 기능 보강 권장 사항

### 2.1 우선순위 평가

| 순위 | 기능 | 효과 | 구현 난이도 | 권장도 | 상태 |
|------|------|------|-------------|--------|------|
| 1 | **코드 실행 환경** | ⭐⭐⭐⭐⭐ | 중 | 🔴 필수 | ✅ 완료 |
| 2 | **터미널/Shell 통합** | ⭐⭐⭐⭐⭐ | 중 | 🔴 필수 | ⏳ 대기 |
| 3 | **Filesystem MCP** | ⭐⭐⭐⭐ | 상 | 🟡 권장 | ⏳ 대기 |
| 4 | **Git 통합** | ⭐⭐⭐⭐ | 중 | 🟡 권장 | ⏳ 대기 |
| 5 | **패키지 의존성 분석** | ⭐⭐⭐ | 하 | 🟢 선택 | ⏳ 대기 |

---

## 3. 구현 완료: 코드 실행 환경 (CodeExecutor)

### 3.1 구현 내용

#### 3.1.1 CodeExecutor 클래스

```python
class CodeExecutor:
    """코드 실행 환경 - 다양한 언어의 코드를 실행하고 결과를 반환"""
    
    SUPPORTED_LANGUAGES = {
        'python': {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
        'py': {'cmd': 'python', 'ext': '.py', 'icon': '🐍'},
        'javascript': {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
        'js': {'cmd': 'node', 'ext': '.js', 'icon': '📜'},
        'bash': {'cmd': 'bash', 'ext': '.sh', 'icon': '🖥️'},
        'sh': {'cmd': 'bash', 'ext': '.sh', 'icon': '🖥️'},
    }
```

#### 3.1.2 주요 메서드

| 메서드 | 설명 |
|--------|------|
| `execute(code, language)` | 코드 실행 및 결과 반환 (stdout, stderr, returncode) |
| `extract_code_from_response(response)` | AI 응답에서 코드 블록 추출 |
| `_ext_to_language(ext)` | 파일 확장자 → 언어 변환 |

#### 3.1.3 기능 특징

- ✅ **다중 언어 지원**: Python, JavaScript, Bash
- ✅ **타임아웃 처리**: 기본 30초 (설정 가능)
- ✅ **코드 블록 자동 추출**: `filename:` 및 언어 식별자 형식 모두 지원
- ✅ **실행 전 확인**: 사용자 확인 후 실행
- ✅ **결과 출력**: stdout/stderr 분리 표시
- ✅ **에러 핸들링**: 타임아웃, 실행 환경 없음 등

### 3.2 추가된 명령어

```
/run [lang]    - 마지막 응답의 코드 실행 (python/js/bash)
```

### 3.3 사용 예시

```
👤 You: Python으로 1부터 10까지 합을 구하는 코드 작성해줘

🤖 AI: 
```filename:sum_example.py
total = sum(range(1, 11))
print(f"1부터 10까지의 합: {total}")
```

👤 You: /run

🔍 1개의 코드 블록을 발견했습니다.

============================================================
📌 [1] sum_example.py (python)
============================================================
   total = sum(range(1, 11))
   print(f"1부터 10까지의 합: {total}")

▶️  이 코드를 실행하시겠습니까? (y/N): y

🚀 python 코드 실행 중...

🐍 ✅ 실행 성공!

📤 출력:
1부터 10까지의 합: 55
```

---

## 4. 다음 구현 예정: 터미널/Shell 통합 (우선순위 2)

### 4.1 설계

```python
class TerminalExecutor:
    """터미널 명령어 실행"""
    
    ALLOWED_COMMANDS = [
        'pip', 'python', 'node', 'npm', 'git', 'ls', 'dir', 'cat', 
        'type', 'echo', 'pwd', 'mkdir', 'touch', 'rm', 'cp', 'mv'
    ]
```

### 4.2 명령어

```
/shell <command>   - 쉘 명령어 실행 (안전 모드)
/shell! <command>  - 쉘 명령어 실행 (위험 명령 허용)
```

---

## 5. 구현 로드맵

### Phase 1 (v1.1.0) - 필수 기능

| 기능 | 예상 공수 | 우선순위 | 상태 |
|------|----------|----------|------|
| `CodeExecutor` 클래스 구현 | 1일 | 🔴 High | ✅ 완료 |
| `/run` 명령어 추가 | 0.5일 | 🔴 High | ✅ 완료 |
| `TerminalExecutor` 클래스 구현 | 1일 | 🔴 High | ⏳ 대기 |
| `/shell` 명령어 추가 | 0.5일 | 🔴 High | ⏳ 대기 |

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

## 6. 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0.001 | 2026-01-19 | 최초 작성 |
| v1.0.002 | 2026-01-19 | 삭제됨 |
| v1.0.003 | 2026-01-19 | CodeExecutor 구현 완료, /run 명령어 추가 |

---

## 7. 참고 자료

- [Claude Tool Use 문서](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [MCP Filesystem Server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
