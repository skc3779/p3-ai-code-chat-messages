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

- **� AI 자동 도구 (Auto Tool Use) (NEW)**:
  - **파일 시스템 도구**: AI가 직접 파일을 읽고, 쓰고, 생성 (`read/write/list_file`)
  - **Git 버전 관리**: 변경 사항 확인(`status`, `diff`) 및 커밋(`commit`)을 AI가 수행
  - **패키지 분석**: 설치된 환경(`pip`, `npm`)을 분석하여 의존성 문제 해결

- **�📂 스마트 파일 관리**:
  - 프로젝트 구조 트리 보기 (`/tree`)
  - `.gitignore` 패턴 자동 인식 및 파일 필터링
  - AI 응답에서 코드 블록을 감지하여 자동 파일 저장 (`/save`)

- **🧠 컨텍스트 인식**:
  - 특정 파일 패턴(`*.py`, `src/`)을 지정하여 AI에게 프로젝트 컨텍스트 전달 (`/context`)
  - 대용량 컨텍스트 자동 관리

---

## 📦 설치 및 설정

### 1. 요구 사항
- **Python 3.8 이상** (권장: 3.10+)
- **Node.js** (JavaScript 코드 실행 시 필요, 선택)
- **Git** (버전 관리 기능 사용 시 필요, 선택)

### 2. 설치 방법

#### 방법 1: requirements.txt 사용 (권장)
```bash
# 프로젝트 클론 또는 다운로드 후 디렉토리 이동
cd p3-ai-code-chat-messages

# 가상환경 생성 (권장)
python -m venv venv

# 가상환경 활성화
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt
```

#### 방법 2: 개별 패키지 설치
```bash
pip install requests sseclient-py python-dotenv PyYAML prompt_toolkit watchdog
```

### 3. 환경 변수 설정
프로젝트 루트에 `.env` 파일을 생성하고 API 키를 설정합니다.

```env
# Claude API 사용 시 (Anthropic)
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL_ID=claude-sonnet-4-5
CLAUDE_API_ENDPOINT=https://api.anthropic.com

# GenAI API 사용 시 (커스텀 API)
ENDPOINT_URL=https://your-genai-endpoint.com
YOUR_CLIENT_KEY=your-client-id
YOUR_CLIENT_SECRET=your-client-secret
YOUR_MODEL_ID=your-model-id
```

---

## 🚀 실행 방법

### 빠른 시작
```bash
# 가상환경 활성화 (설정한 경우)
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Claude 어시스턴트 실행
python claude-ai-chat-code01.py

# 또는 GenAI 어시스턴트 실행
python gen-ai-chat-code01.py
```

### 다른 프로젝트에서 실행
특정 프로젝트 디렉토리에서 어시스턴트를 사용하려면:
```bash
# 해당 프로젝트 디렉토리로 이동
cd /path/to/your/project

# 어시스턴트 실행 (절대 경로 또는 PATH 설정 필요)
python /path/to/p3-ai-code-chat-messages/claude-ai-chat-code01.py
```

### 배치 실행 (자동 종료) — `python -m ai_cli`

REPL 진입 없이 `/auto_context` 를 한 번 실행하고 완료 시 종료하는 배치 모드입니다 (FSD v1.0.157).

```bash
python -m ai_cli -t <claude|gemini|genai> \
                 -wp <workspace path> \
                 -c auto_context <pattern> \
                 -p <prompt file>
```

| 옵션 | 별칭 | 설명 |
|---|---|---|
| `-t`  | `--type`      | 사용할 LLM (`claude` / `gemini` / `genai`) |
| `-wp` | `--workspace` | 작업 디렉토리 경로 |
| `-c`  | `--command`   | 실행 명령. 현재 `auto_context <pattern>` 만 지원. `<pattern>` 은 와일드카드 |
| `-p`  | `--prompt`    | 프롬프트(질문) 파일 경로 (UTF-8 / UTF-8 BOM 허용) |

종료 코드: `0` 정상, `1` 입력 오류, `2` 미지원 명령, `3` 처리 예외, `130` 사용자 중단.

```bash
# Claude · 단일 패턴
python -m ai_cli -t claude -wp ./ -c auto_context "src/*.py" -p prompt.txt

# Gemini · 다중 패턴 (대괄호 형식)
python -m ai_cli -t gemini -wp /work \
    -c auto_context "[src/*.py, docs/*.md]" -p prompts/translate.txt

# GenAI · 절대 경로 워크스페이스
python -m ai_cli --type genai \
    --workspace "C:\proj" \
    --command auto_context "tests/*.py" \
    --prompt prompts/refactor.txt
```

> 셸 글롭을 막기 위해 와일드카드는 **반드시 따옴표** 로 감쌉니다.

### 주요 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `/context <패턴> <질문>` | 파일 컨텍스트와 함께 질문 | `/context src/*.py 리팩토링 제안해줘` |
| `/diff` | AI 응답의 코드 변경사항 Diff 표시 | `/diff` |
| `/apply` | Diff 내용을 실제 파일에 적용 | `/apply` |
| `/run [언어]` | AI가 생성한 코드 실행 | `/run python` (기본값: python) |
| `/shell <명령어>` | 쉘 명령어 실행 (안전 모드) | `/shell pip list` |
| `/shell! <명령어>` | 쉘 명령어 실행 (모든 명령 허용) | `/shell! rm temp.txt` |
| `/save` | AI 응답의 코드 블록을 파일로 저장 | `/save` |
| `/files [확장자]` | 파일 목록 확인 | `/files .py` |
| `/tree` | 프로젝트 디렉토리 트리 확인 | `/tree` |
| `/read <패턴>` | 파일 내용 읽기 | `/read requirements.txt` |
| `/watch <패턴>` | 파일 변경 감시 시작 | `/watch *.py` |
| `/history` | 대화 기록 확인 | `/history` |
| `/tokens` | 토큰 사용량 확인 · 메시지 보관 한도 수정 | `/tokens [-k <number\|default>]` |
| `/help` | 전체 명령어 도움말 | `/help` |
| `/quit` | 종료 | `/quit` |

---

## 🧪 테스트 및 모듈 구조

### 프로젝트 구조
핵심 로직은 `src/` 패키지에 모듈화되어 있습니다.

```
.
├── claude-ai-chat-code01.py  # Claude 어시스턴트 실행 스크립트
├── gen-ai-chat-code01.py     # GenAI 어시스턴트 실행 스크립트
├── requirements.txt          # Python 패키지 의존성
├── src/
│   ├── __init__.py           # 패키지 노출
│   ├── claude_assistant.py   # Claude API 처리 로직 (Tool Use 포함)
│   ├── genai_assistant.py    # GenAI API 처리 로직 (Tool Use 포함)
│   ├── diff_viewer.py        # 코드 Diff 표시 및 적용 (NEW)
│   ├── cli_input.py          # CLI 자동완성 및 히스토리
│   ├── code_executor.py      # 코드 실행 샌드박스
│   ├── terminal_executor.py  # 터미널 명령어 처리기
│   ├── file_watcher.py       # 파일 변경 감시
│   ├── git_manager.py        # Git 명령 통합 관리
│   ├── package_manager.py    # 패키지 의존성 분석
│   ├── file_manager.py       # 파일 시스템 관리
│   ├── context_builder.py    # 프롬프트 컨텍스트 구성
│   ├── tool_definitions.py   # AI 도구(Tool) 스키마 정의
│   ├── token_manager.py      # 토큰 사용량 관리
│   ├── api_retry.py          # API 재시도 로직 (지수 백오프)
│   ├── history_manager.py    # 대화 히스토리 저장/로드
│   ├── template_manager.py   # 시스템 프롬프트 템플릿
│   └── tree_builder.py       # 디렉토리 트리 시각화
├── tests/
│   ├── __init__.py           # 테스트 패키지 초기화
│   ├── test_diff_viewer.py   # DiffViewer 테스트 (NEW)
│   ├── test_claude_tool_use.py # Claude Tool Use 테스트
│   ├── test_genai_tool_use.py  # GenAI Tool Use 테스트
│   ├── test_file_manager.py  # FileManager 테스트
│   ├── test_code_executor.py # CodeExecutor 테스트
│   └── ...                   # 기타 단위 테스트 파일들
```

### 단위 테스트 실행
작성된 기능들의 정상 동작을 검증하려면 단위 테스트를 실행하세요.

```bash
# 모든 테스트 실행 (권장)
python -m unittest discover tests

# 개별 테스트 파일 실행
python tests/test_file_manager.py
python tests/test_code_executor.py
# ... 기타 개별 파일들

# 모듈 방식 실행
python -m unittest tests.test_response_parser -v

# 특정 클래스의 특정 메서드(단일 기능)만 실행
python -m unittest tests.test_response_parser.TestResponseParser.test_parse_untagged_code_block -v
```
> **참고**: `tests/` 폴더 내의 테스트 파일들은 `src` 패키지를 import하기 위해 `sys.path` 설정을 포함하고 있습니다. 모듈 방식으로 실행하려면 `tests/` 디렉토리에 `__init__.py`가 존재해야 합니다.


```bash
# FSD_v1.0.157_ai-cli-batch-auto-context.md 단위테스트
python -m pytest tests/test_ai_cli_batch.py
```

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
