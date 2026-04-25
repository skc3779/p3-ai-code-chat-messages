# Release Notes: Claude Code Assistant v1.0.004

**버전**: v1.0.005  
**릴리즈 날짜**: 2026-01-19  
**타입**: Feature Release + Code Refactoring

---

## 🎯 릴리즈 개요

Claude Code Assistant v1.0.004는 **코드 인터프리터 최적화**를 위한 주요 기능 추가와 **코드 구조 리팩토링**을 포함합니다.

---

## ✨ 새로운 기능

### 1. 코드 실행 환경 (CodeExecutor)

AI가 생성한 코드를 즉시 실행할 수 있는 기능 추가

| 지원 언어 | 명령어 | 아이콘 |
|-----------|--------|--------|
| Python | `python` | 🐍 |
| JavaScript | `node` | 📜 |
| Bash | `bash` | 🖥️ |

**새 명령어**: `/run [lang]`

```bash
# 사용 예시
👤 You: Python으로 1+1 계산하는 코드 작성해줘
🤖 AI: (코드 생성)
👤 You: /run
🐍 ✅ 실행 성공!
📤 출력: 2
```

### 2. 터미널/Shell 통합 (TerminalExecutor)

시스템 명령어를 안전하게 실행할 수 있는 기능 추가

**새 명령어**:
- `/shell <cmd>` - 안전 모드 (허용된 명령어만)
- `/shell! <cmd>` - 위험 모드 (모든 명령어, 확인 필요)

**허용된 명령어 (안전 모드)**:
```
pip, npm, git, ls, dir, cat, mkdir, echo, pwd, which, make, gradle, mvn...
```

**차단된 명령어 (위험)**:
```
rm, del, mv, cp, chmod, kill, curl, wget, ssh...
```

```bash
# 사용 예시
👤 You: /shell pip list
✅ 실행 성공!

👤 You: /shell rm file.txt
❌ 위험 명령어: rm
💡 위험 명령을 실행하려면 /shell! 을 사용하세요.
```

---

## 🔧 코드 구조 리팩토링

### Before (단일 파일)
```
claude-ai-chat-code01.py  # 1,031줄 모놀리식 파일
```

### After (모듈화)
```
claude-ai-chat-code01.py    # 메인 진입점 (~300줄)
src/
├── __init__.py             # 패키지 초기화
├── file_manager.py         # FileManager 클래스
├── code_executor.py        # CodeExecutor 클래스
├── terminal_executor.py    # TerminalExecutor 클래스
├── tree_builder.py         # TreeBuilder 클래스
├── context_builder.py      # ContextBuilder 클래스
└── claude_assistant.py     # ClaudeCodeAssistant 클래스
```

### 모듈별 책임

| 모듈 | 크기 | 책임 |
|------|------|------|
| `file_manager.py` | 3.8KB | 파일 읽기/쓰기, gitignore 처리 |
| `code_executor.py` | 4.9KB | Python/JS/Bash 코드 실행 |
| `terminal_executor.py` | 4.2KB | 쉘 명령어 실행, 안전 검증 |
| `tree_builder.py` | 2.4KB | 프로젝트 구조 트리 생성 |
| `context_builder.py` | 4.1KB | AI 컨텍스트 구성 |
| `claude_assistant.py` | 6.8KB | Claude API 연동, 채팅 처리 |

---

## 📋 전체 명령어 목록 (v1.0.004)

| 명령어 | 설명 | 버전 |
|--------|------|------|
| `/files [ext]` | 프로젝트 파일 목록 | v1.0.0 |
| `/tree` | 프로젝트 구조 보기 | v1.0.0 |
| `/read <pattern>` | 파일 읽기 | v1.0.0 |
| `/context <pattern>` | 컨텍스트 포함 질문 | v1.0.0 |
| `/save` | AI 응답에서 파일 저장 | v1.0.0 |
| `/workspace [path]` | 작업 디렉토리 변경 | v1.0.0 |
| `/stream` | 스트리밍 모드 | v1.0.0 |
| `/nostream` | 논스트리밍 모드 | v1.0.0 |
| `/history` | 대화 히스토리 | v1.0.0 |
| `/clear` | 히스토리 초기화 | v1.0.0 |
| `/run [lang]` | 코드 실행 | **v1.0.003** |
| `/shell <cmd>` | 쉘 명령 (안전) | **v1.0.004** |
| `/shell! <cmd>` | 쉘 명령 (위험) | **v1.0.004** |
| `/help` | 도움말 | v1.0.0 |
| `/quit` | 종료 | v1.0.0 |

---

## 🐛 버그 수정

### /save 명령어 파일 저장 실패 (v1.0.003)

- **문제**: AI가 `````python` 형식으로 응답 시 `/save`로 파일 저장 불가
- **원인**: 정규식 패턴이 `````filename:` 형식만 인식
- **해결**: 시스템 프롬프트 강화로 AI가 올바른 형식 사용하도록 유도

---

## 📦 의존성

```
requests>=2.28.0
sseclient-py>=1.7.2
python-dotenv>=1.0.0
```

---

## 🔄 업그레이드 방법

```bash
# 기존 파일 백업 권장
cp claude-ai-chat-code01.py claude-ai-chat-code01.py.bak

# 새 버전 적용
# src/ 폴더와 claude-ai-chat-code01.py 교체

# 테스트
python claude-ai-chat-code01.py
```

---

## 📚 관련 문서

- [FSD_Interpreter_Optimization_v1.0.004.md](../requrements/FSD_Interpreter_Optimization_v1.0.004.md)
- [BUG_Save_Command_Fix_v1.0.001.md](../requrements/BUG_Save_Command_Fix_v1.0.001.md)
- [FSD_Claude_API_Migration_v1.0.001.md](../requrements/FSD_Claude_API_Migration_v1.0.001.md)

---

## 📝 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0.001 | 2026-01-19 | Claude API 마이그레이션 |
| v1.0.002 | 2026-01-19 | 시스템 프롬프트 개선 |
| v1.0.003 | 2026-01-19 | CodeExecutor 추가, /run 명령어 |
| v1.0.004 | 2026-01-19 | TerminalExecutor 추가, /shell 명령어, 코드 리팩토링 |
