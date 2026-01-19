# p3-ai-code-chat-messages

**AI 기반 코딩 어시스턴트 프로젝트**

이 프로젝트는 터미널 환경에서 실행되는 지능형 코딩 어시스턴트입니다. 사용자의 프로젝트 파일을 분석하고, 코드를 생성/수정하며, 즉시 실행해볼 수 있는 대화형 환경을 제공합니다. Claude API와 커스텀 GenAI API를 모두 지원하며, 모듈화된 설계를 통해 확장성을 확보했습니다.

---

## ✨ 주요 기능

- **🤖 멀티 LLM 지원**:
  - **Claude Code Assistant**: Anthropic의 Claude 3.5 Sonnet 모델 활용 (`claude-ai-chat-code01.py`)
  - **GenAI Code Assistant**: 커스텀 GenAI API 활용 (`gen-ai-chat-code01.py`)
  
- **💻 코드 실행 환경 (Code Execution)**:
  - Python, JavaScript (Node.js), Bash 스크립트를 대화 중에 즉시 실행 (`/run`)
  - 실행 결과(Stdout/Stderr)를 실시간으로 확인

- **🖥️ 터미널 통합 (Terminal Integration)**:
  - **안전 모드 (`/shell`)**: 검증된 명령어(ls, pip, git 등)만 실행하여 실수 방지
  - **관리자 모드 (`/shell!`)**: 모든 시스템 명령어 실행 가능 (사용자 확인 절차 포함)

- **📂 스마트 파일 관리**:
  - 프로젝트 구조 트리 보기 (`/tree`)
  - `.gitignore` 패턴 자동 인식 및 파일 필터링
  - AI 응답에서 코드 블록을 감지하여 자동 파일 저장 (`/save`)

- **🧠 컨텍스트 인식**:
  - 특정 파일 패턴(`*.py`, `src/`)을 지정하여 AI에게 프로젝트 컨텍스트 전달 (`/context`)
  - 대용량 컨텍스트 자동 관리

---

## 📦 설치 및 설정

### 1. 요구 사항
- Python 3.8 이상
- Node.js (JavaScript 코드 실행 시 필요)

### 2. 패키지 설치
필요한 Python 패키지를 설치합니다.

```bash
pip install requests sseclient-py python-dotenv
```

### 3. 환경 변수 설정
프로젝트 루트에 `.env` 파일을 생성하고 키를 설정합니다.

```env
# Claude API 사용 시
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL_ID=claude-3-5-sonnet-20240620
CLAUDE_API_ENDPOINT=https://api.anthropic.com

# GenAI API 사용 시
ENDPOINT_URL=https://your-genai-endpoint.com
YOUR_CLIENT_KEY=your-client-id
YOUR_CLIENT_SECRET=your-client-secret
YOUR_MODEL_ID=your-model-id
```

---

## 🚀 사용 방법

### 어시스턴트 실행

**Claude 버전 실행:**
```bash
python claude-ai-chat-code01.py
```

**GenAI 버전 실행:**
```bash
python gen-ai-chat-code01.py
```

### 주요 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `/context <패턴> <질문>` | 파일 컨텍스트와 함께 질문 | `/context src/*.py 리팩토링 제안해줘` |
| `/run [언어]` | AI가 생성한 코드 실행 | `/run python` (기본값: python) |
| `/shell <명령어>` | 쉘 명령어 실행 (안전 모드) | `/shell pip list` |
| `/shell! <명령어>` | 쉘 명령어 실행 (모든 명령 허용) | `/shell! rm temp.txt` |
| `/save` | AI 응답의 코드 블록을 파일로 저장 | `/save` |
| `/files [확장자]` | 파일 목록 확인 | `/files .py` |
| `/tree` | 프로젝트 디렉토리 트리 확인 | `/tree` |
| `/read <패턴>` | 파일 내용 읽기 | `/read requirements.txt` |
| `/history` | 대화 기록 확인 | `/history` |
| `/quit` | 종료 | `/quit` |

---

## 🧪 테스트 및 모듈 구조

### 프로젝트 구조
핵심 로직은 `src/` 패키지에 모듈화되어 있습니다.

```
.
├── claude-ai-chat-code01.py  # Claude 어시스턴트 실행 스크립트
├── gen-ai-chat-code01.py     # GenAI 어시스턴트 실행 스크립트
├── src/
│   ├── __init__.py           # 패키지 노출
│   ├── claude_assistant.py   # Claude API 처리 로직
│   ├── genai_assistant.py    # GenAI API 처리 로직
│   ├── code_executor.py      # 코드 실행 샌드박스
│   ├── terminal_executor.py  # 터미널 명령어 처리기
│   ├── file_manager.py       # 파일 시스템 관리
│   ├── context_builder.py    # 프롬프트 컨텍스트 구성
│   └── tree_builder.py       # 디렉토리 트리 시각화
└── tests/
    └── test_commands.py      # 단위 테스트
```

### 단위 테스트 실행
작성된 기능들의 정상 동작을 검증하려면 단위 테스트를 실행하세요.

```bash
python tests/test_commands.py
```
> **참고**: `tests/test_commands.py`는 `src` 패키지를 import하기 위해 `sys.path` 설정을 포함하고 있습니다.

---

## 📝 코드 사용 예시 (Python)

`src` 패키지를 자신의 다른 프로젝트에서 직접 사용할 수도 있습니다.

```python
from src import FileManager, CodeExecutor

# 1. 파일 관리자 초기화
fm = FileManager("./my_project")

# 로컬 파일 목록 조회 (.gitignore 적용)
files = fm.list_files(extensions=['.py'])
print(files)

# 2. 코드 실행기 사용
executor = CodeExecutor(workspace_dir=fm.workspace_dir)

# Python 코드 실행
code = "print(10 + 20)"
result = executor.execute(code, language='python')

if result['success']:
    print(f"출력 결과: {result['stdout']}")  # 출력 결과: 30
```
