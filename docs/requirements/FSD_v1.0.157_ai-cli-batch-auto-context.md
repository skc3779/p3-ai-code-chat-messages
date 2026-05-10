# FSD v1.0.157 — `input-cli` 배치 실행: `/auto_context` 명령 파라메터화 및 자동 종료

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.157 |
| 작성일 | 2026-05-10 |
| 구현 예정일 | 2026-05-10 |
| 상태 | ✅ 구현 완료 |
| 선행 문서 | FSD v1.0.049 (context-file-auto-processing), FSD v1.0.123 (auto-context QC), FSD v1.0.156 (`/tokens` 명령어 개선) |
| 대상 파일 | [claude-ai-chat-code.py](../../claude-ai-chat-code.py), [gemini-ai-chat-code.py](../../gemini-ai-chat-code.py), [gen-ai-chat-code.py](../../gen-ai-chat-code.py), [src/cli_input.py](../../src/cli_input.py), [src/context_processor.py](../../src/context_processor.py) |
| 신규 파일 | [ai_cli.py](../../ai_cli.py), (또는 [ai_cli.py](../../ai_cli.py)), [tests/test_ai_cli_batch.py](../../tests/test_ai_cli_batch.py) |

---

## 1. 개요

### 1.1 목적

현재 세 엔트리포인트(`claude-ai-chat-code.py`, `gemini-ai-chat-code.py`, `gen-ai-chat-code.py`) 는 모두 **대화형 REPL** 로만 동작하며, `/auto_context <pattern>` 은 사용자가 프롬프트(질문) 를 키보드로 입력해야 실행된다. CI / 배치 / 자동화 시나리오에서 동일한 작업을 수행하려면 매번 REPL 을 켜고 명령어를 타이핑해야 하는 부담이 있다.

본 FSD 는 **단일 실행 명령** 으로 `/auto_context` 를 즉시 수행하고 결과 처리 완료 시 **자동 종료** 하는 배치 실행 모드를 도입한다:

```
python -m ai_cli -t <claude|gemini|genai> \
                    -wp <workspace path> \
                    -c auto_context <pattern> \
                    -p <prompt file>
```

세 엔트리포인트에 동일한 인자 처리 로직을 적용하여 LLM 종류만 `-t` 옵션으로 분기한다.

### 1.2 다루는 문제

| ID | 현 문제 | 본 FSD 의 대응 |
|---|---|---|
| P-1 | `/auto_context` 는 REPL 안에서만 실행 가능 | 커맨드라인 인자로 직접 실행 |
| P-2 | 작업 디렉토리는 `os.getcwd()` 로 고정 | `-wp` 로 명시적 지정 |
| P-3 | 프롬프트(질문) 를 매번 입력해야 함 | `-p <file>` 로 프롬프트 파일 지정 |
| P-4 | 작업 완료 후에도 REPL 이 유지되어 자동화 불가 | 배치 모드 완료 시 자동 종료 (exit code 반환) |
| P-5 | LLM 종류별로 별도 스크립트 호출 필요 | 통합 `-m input-cli -t <type>` 디스패처 도입 |

### 1.3 비범위

| 항목 | 비고 |
|---|---|
| `/auto_context` 외 명령어의 배치 실행 | 본 FSD 는 `/auto_context` 만 대상. 다른 명령어는 후속 FSD 에서 다룬다 |
| 다중 명령 파이프라인 | `-c` 는 단일 명령만 받는다. 시퀀스 실행은 향후 확장 |
| `-qc` / `--quality-check` 옵션 | 배치 모드에서도 사용 가능하도록 인자 통과만 보장하며, 동작 자체는 FSD v1.0.123 의 정의를 따른다 |
| 대화형 모드 변경 | 인자 없이 실행 시 동작은 기존 REPL 과 동일 (하위 호환) |
| `.env` 자동 생성 | 워크스페이스에 `.env` 가 없으면 기존 동작(경고) 유지 |

---

## 2. 현황 분석

### 2.1 현재 엔트리포인트 구조

세 파일 모두 다음 패턴을 따른다 ([claude-ai-chat-code.py:121](../../claude-ai-chat-code.py#L121), [gemini-ai-chat-code.py:123](../../gemini-ai-chat-code.py#L123), [gen-ai-chat-code.py:122](../../gen-ai-chat-code.py#L122)):

```python
def main():
    load_environment()
    TokenManager.reload_from_env()
    # ... API 키 / 모델 로드
    workspace = os.getcwd()                      # ★ 고정
    assistant = XxxCodeAssistant(...)
    # ... 입력 핸들러 / 워처 초기화
    while True:                                  # ★ REPL 루프
        user_input = input_handler.get_input("> ")
        ...
        elif command == '/auto_context':
            # 패턴 파싱 → 매칭 → 사용자 confirm → ContextProcessor.process_files
```

`sys.argv` 파싱 로직은 어느 파일에도 존재하지 않는다.

### 2.2 `/auto_context` 명령 흐름 ([claude-ai-chat-code.py:459-535](../../claude-ai-chat-code.py#L459-L535))

```
1) -qc 옵션 파싱 (parse_command_options)
2) [pat1, pat2] 또는 단일 pattern 파싱
3) question 추출 (없으면 multiline 입력)
4) FilePatternMatcher.filter_files
5) "▶ 자동 처리를 시작하시겠습니까? (Y/n)" 사용자 확인 ← 배치 모드에서 차단 요인
6) ContextProcessor(streaming, quality_check).process_files(matched, question)
```

배치 모드에서는 **(3) 의 multiline 입력** 과 **(5) 의 사용자 확인** 을 자동으로 우회해야 한다.

### 2.3 `/auto_context` 옵션 등록 ([src/command_registry.py:41-42](../../src/command_registry.py#L41))

```python
CommandInfo('/auto_context',  '패턴별 파일을 순서대로 자동 처리',
            '/auto_context <pattern> [질문]',    'original/*.md 한글로 번역해줘'),
```

→ 배치 실행 옵션은 명령 레지스트리에 영향을 주지 않는다 (REPL 명령어의 시그니처는 변경 없음).

---

## 3. 설계 (Design)

### 3.1 실행 형태

```
python -m input-cli -t <claude|gemini|genai> -wp <workspace> -c auto_context <pattern> -p <prompt file>
```

| 옵션 | 별칭 | 값 | 설명 | 필수 |
|---|---|---|---|---|
| `-t`  | `--type`      | `claude` \| `gemini` \| `genai` | 사용할 LLM 엔트리포인트 선택 | ✅ |
| `-wp` | `--workspace` | `<path>`                        | 작업 디렉토리 절대/상대 경로 | ✅ |
| `-c`  | `--command`   | `auto_context <pattern>`        | 실행할 명령과 인자. 본 FSD 는 `auto_context` 만 지원. `<pattern>` 은 와일드카드 (예: `src/*.py`, `[src/*.py, docs/*.md]`) | ✅ |
| `-p`  | `--prompt`    | `<filename>`                    | 프롬프트(질문) 파일. 파일 내용 전체가 `auto_context` 의 질문으로 사용됨 | ✅ |

#### 3.1.1 인자 누락 시 동작

- 네 옵션 (`-t`, `-wp`, `-c`, `-p`) 중 **하나라도 누락** 되면 `argparse` 가 표준 에러로 사용법을 출력하고 **exit code 2** 로 종료한다.
- 모든 옵션이 없을 경우 (`python -m input-cli`) → 사용법 출력 + exit 2 (대화형 REPL 로 fallback 하지 **않는다**. 기존 REPL 은 `python claude-ai-chat-code.py` 등 직접 호출로만 진입).

### 3.2 모듈 구성

#### 3.2.1 신규 모듈 — `ai_cli`

> `python -m` 은 모듈명에 하이픈을 허용하지 않으므로 **실제 파이썬 모듈명은 `ai_cli`** 로 한다. README / 사용 예시는 사용자 편의상 `python -m input-cli` 와 `python -m ai_cli` 를 모두 허용함을 명시한다 (실제 호출 시에는 `ai_cli` 가 정식). 두 표기는 README 등 문서에서만 동치로 다루며, 패키지 별칭 등록은 하지 않는다.

`ai_cli` 모듈은 다음 책임을 가진다:

1. `argparse` 로 `-t / -wp / -c / -p` 파싱
2. `-t` 값에 따라 세 엔트리포인트의 `main_batch(...)` 함수를 호출
3. 호출 결과(`int` exit code) 를 `sys.exit()` 로 전달

> 본 FSD 는 패키징(`setup.py` / `pyproject.toml`) 추가는 다루지 않는다. 배포 환경(예: PyInstaller) 에서는 `python ai_cli.py` 직접 실행도 가능하도록 `if __name__ == "__main__"` 가드를 둔다.

#### 3.2.2 기존 엔트리포인트 — `main_batch()` 추가

세 파일 (`claude-ai-chat-code.py`, `gemini-ai-chat-code.py`, `gen-ai-chat-code.py`) 에 다음 시그니처의 함수를 추가한다:

```python
def main_batch(workspace: str, command: str, command_args: str, prompt: str) -> int:
    """배치 모드 실행 — REPL 진입 없이 단일 명령을 실행하고 종료한다.

    Args:
        workspace:     작업 디렉토리 절대/상대 경로 (-wp)
        command:       실행할 명령. 본 FSD 에서는 'auto_context' 만 허용
        command_args:  명령 인자 (예: pattern 문자열)
        prompt:        질문/프롬프트 본문 (파일에서 읽어들인 내용)

    Returns:
        0  — 정상 종료
        1  — 매칭 파일 없음 / 프롬프트 빈 문자열 등 사용자 입력 오류
        2  — 명령 미지원 (`auto_context` 외)
        3  — API / 처리 중 예외 발생
    """
```

기존 `main()` 은 변경하지 않는다 (REPL 진입 전용). `main_batch()` 는 `main()` 의 초기화 단계를 함수화하여 공유하되, **`while True` REPL 루프에는 진입하지 않는다**.

#### 3.2.3 공통 초기화 헬퍼 도출

세 엔트리포인트의 `main()` 에서 다음 단계를 별도 함수로 분리하여 `main_batch()` 와 공유한다:

```python
def _initialize(workspace: str | None = None) -> tuple[Assistant, FileWatcher | None]:
    """환경변수 로드, TokenManager reload, API 키 검증, Assistant 생성"""
```

`workspace` 가 `None` 이면 기존 `os.getcwd()` 를 사용한다 (REPL 호환).
`FileWatcher` 는 배치 모드에서는 시작하지 않는다 (NFR-02 참조).

### 3.3 배치 모드 `auto_context` 실행 흐름

```
ai_cli (-m)
  ├─ argparse 로 -t/-wp/-c/-p 파싱
  ├─ -p 파일 존재 / 읽기 권한 검증 → 내용 로드
  ├─ -c 의 첫 토큰이 "auto_context" 인지 검증, 그 외는 exit 2
  ├─ -t 값으로 디스패치
  │     claude → claude_ai_chat_code.main_batch(...)
  │     gemini → gemini_ai_chat_code.main_batch(...)
  │     genai  → gen_ai_chat_code.main_batch(...)
  └─ exit code 전달
```

각 엔트리포인트의 `main_batch()` 는 다음을 수행한다:

```
1) _initialize(workspace) — 환경/Assistant/Pattern 매처 준비
2) command_args 파싱
   - "[pat1, pat2]" 또는 단일 패턴 추출
   - REPL 분기와 동일한 파싱 규칙 (claude-ai-chat-code.py:480-494)
3) FilePatternMatcher.filter_files → matched_files
   - 매칭 결과 0개 → 에러 출력 + return 1
4) 사용자 confirm 단계는 생략 (배치 모드)
   - 매칭 파일 목록은 stdout 으로 출력 (감사용)
5) ContextProcessor(streaming=True, quality_check=<옵션>).process_files(matched_files, prompt)
6) 처리 완료 후 return 0
```

> **자동 confirm:** § 2.2 의 (5) 단계 `input("▶ 자동 처리를 시작하시겠습니까? (Y/n): ")` 를 배치 모드에서는 호출하지 않는다. 대신 매칭 결과 요약을 stdout 으로만 출력한다.
>
> **자동 종료:** `process_files` 반환 후 함수가 종료되며, `ai_cli` 는 그 반환값을 `sys.exit()` 로 전달한다 → 프로세스 종료.

### 3.4 `-c auto_context <pattern>` 인자 파싱 규칙

`argparse` 는 `-c auto_context <pattern>` 형태에서 `<pattern>` 까지 단일 인자로 묶기 어려우므로 다음과 같이 처리한다:

#### 3.4.1 권장 형태 — `nargs='+'` 사용

```python
parser.add_argument("-c", "--command", nargs="+", required=True,
                    metavar=("CMD", "ARG"),
                    help="실행할 명령과 인자. 예: -c auto_context src/*.py")
```

`-c auto_context src/*.py` → `args.command == ["auto_context", "src/*.py"]`

`-c "auto_context [src/*.py, docs/*.md]"` 처럼 따옴표로 감싸도 동일하게 받을 수 있다 (쉘이 토큰화한 결과를 그대로 사용).

#### 3.4.2 검증 로직

```python
if args.command[0] != "auto_context":
    print(f"❌ 지원하지 않는 명령: {args.command[0]} (현재는 'auto_context' 만 지원)")
    sys.exit(2)
if len(args.command) < 2:
    print("❌ 패턴이 누락되었습니다. 예: -c auto_context src/*.py")
    sys.exit(2)
command_name = args.command[0]
command_args = " ".join(args.command[1:])  # 패턴 외 추가 토큰까지 그대로 전달
```

#### 3.4.3 와일드카드 셸 확장 회피

쉘(특히 zsh/bash) 이 와일드카드를 미리 글롭하면 의도와 달라질 수 있다. 사용자에게는 **반드시 따옴표** 로 감쌀 것을 README 에 명시한다:

```
python -m input-cli -t claude -wp ./ -c auto_context "src/*.py" -p prompt.txt
```

### 3.5 `-p <prompt file>` 처리

**경로 규칙**: `-c <pattern>` 과 동일하게, **비절대경로면 `-wp` 워크스페이스 기준**으로 해석한다.

| 입력 예 | 해석 |
|---|---|
| `/abs/path/prompt.txt` | 절대경로 — 그대로 사용 |
| `docs/reqs/prompt.txt` | 상대경로 — `<workspace>/docs/reqs/prompt.txt` 로 해석 |
| `./prompt.txt` | 상대경로 — `<workspace>/prompt.txt` 로 해석 |

```python
prompt_path = Path(args.prompt)
if not prompt_path.is_absolute():
    prompt_path = workspace_path / args.prompt   # workspace 기준 해석
prompt_path = prompt_path.resolve()             # chdir 이후에도 안전하도록 절대경로화
if not prompt_path.is_file():
    print(f"❌ 프롬프트 파일을 찾을 수 없습니다: {prompt_path}")
    sys.exit(1)
```

- 인코딩은 **UTF-8 / UTF-8 BOM** 모두 허용 (`utf-8-sig`). Windows 메모장 호환.
- 파일 끝 개행/공백은 `strip()` 으로 제거.
- `resolve()` 로 절대경로화하여 이후 `os.chdir(workspace)` 에도 영향받지 않는다.

### 3.6 `-wp <workspace>` 처리

```python
workspace_path = Path(args.workspace).resolve()
if not workspace_path.is_dir():
    print(f"❌ 작업 디렉토리가 존재하지 않습니다: {workspace_path}")
    sys.exit(1)
os.chdir(workspace_path)            # 기존 코드의 os.getcwd() 호환을 위해 chdir
```

- 상대 경로는 호출 시점의 cwd 기준으로 resolve.
- `os.chdir()` 후 `_initialize()` 가 `.env` 등을 워크스페이스에서 읽도록 한다.
- `_initialize()` 에는 추가로 `workspace` 명시 인자를 전달하여 `Assistant.workspace_dir` 가 항상 `-wp` 값과 일치하도록 한다.

### 3.7 `-t <type>` 디스패치

```python
TYPE_TO_MODULE = {
    "claude": "claude_ai_chat_code",
    "gemini": "gemini_ai_chat_code",
    "genai":  "gen_ai_chat_code",
}
```

> **모듈명 주의:** 현재 파일명은 하이픈을 포함한다 (`claude-ai-chat-code.py`). `import claude-ai-chat-code` 는 불가하므로, `importlib.util` 로 파일 경로 기반 로드하거나 또는 본 FSD 구현 시점에 **세 파일을 언더스코어 별칭으로 임포트할 수 있는 어댑터** (예: `src/_entrypoints/claude_ai_chat_code.py` 가 원본 파일을 `runpy` 또는 path-based import 로 로드) 를 둔다.
>
> 권장 구현: `importlib.util.spec_from_file_location` 으로 하이픈 파일을 동적 임포트하여 `main_batch` 심볼을 가져온다.

```python
import importlib.util
from pathlib import Path

def _load_entrypoint(module_filename: str):
    repo_root = Path(__file__).resolve().parent.parent  # ai_cli.py 기준
    file_path = repo_root / module_filename
    spec = importlib.util.spec_from_file_location("_entrypoint", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

TYPE_TO_FILE = {
    "claude": "claude-ai-chat-code.py",
    "gemini": "gemini-ai-chat-code.py",
    "genai":  "gen-ai-chat-code.py",
}
```

### 3.8 종료 처리

| 상태 | exit code | stdout/stderr |
|---|---|---|
| 정상 처리 완료 | 0 | 처리 요약 (`✅ N개 파일 처리 완료`) |
| 매칭 파일 0개 | 1 | `❌ 패턴 ... 에 해당하는 파일이 없습니다.` |
| 프롬프트 파일 누락/빈 파일 | 1 | `❌ 프롬프트 파일 ...` |
| 워크스페이스 미존재 | 1 | `❌ 작업 디렉토리가 존재하지 않습니다 ...` |
| 미지원 명령 (auto_context 외) | 2 | argparse 또는 본 FSD § 3.4.2 에러 |
| API/처리 예외 | 3 | 예외 메시지 + traceback (디버깅용) |
| KeyboardInterrupt | 130 | `\n⏭️  사용자 중단` |

### 3.9 REPL 호환성

- 기존 `python claude-ai-chat-code.py` 직접 실행 → `main()` 진입, REPL 동작 변경 없음.
- 본 FSD 는 `main()` 내부 로직에 영향을 주지 않는다 (`_initialize()` 헬퍼 분리만 수행).
- `command_registry.py` 의 `/auto_context` 항목은 변경하지 않는다.

---

## 4. 요구사항

### 4.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-01 | `python -m input-cli -t <type> -wp <ws> -c auto_context <pattern> -p <prompt>` 호출이 가능해야 한다 | 필수 |
| FR-02 | `-t` 는 `claude / gemini / genai` 만 허용하며 그 외 값은 argparse 에러로 거부한다 | 필수 |
| FR-03 | `-wp` 의 경로가 존재하지 않으면 exit 1 과 에러 메시지를 출력한다 | 필수 |
| FR-04 | `-c` 의 첫 토큰이 `auto_context` 가 아니면 exit 2 와 에러 메시지를 출력한다 | 필수 |
| FR-05 | `-p` 의 파일이 없거나 비어있으면 exit 1 과 에러 메시지를 출력한다 | 필수 |
| FR-06 | 배치 모드에서 매칭 파일 목록은 stdout 으로 출력하지만 사용자 확인(`Y/n`) 은 묻지 않는다 | 필수 |
| FR-07 | 매칭 파일이 0개이면 exit 1 로 종료한다 | 필수 |
| FR-08 | `process_files()` 정상 완료 시 exit 0 으로 종료하며 REPL 로 진입하지 않는다 | 필수 |
| FR-09 | 세 엔트리포인트 (`claude-ai-chat-code.py`, `gemini-ai-chat-code.py`, `gen-ai-chat-code.py`) 모두 동일한 `main_batch()` 시그니처를 노출한다 | 필수 |
| FR-10 | 인자 없이 직접 실행 (`python claude-ai-chat-code.py` 등) 시 기존 REPL 동작이 유지되어야 한다 | 필수 |
| FR-11 | `-c auto_context "[src/*.py, docs/*.md]"` 처럼 다중 패턴 형식도 지원한다 (FSD v1.0.068 호환) | 필수 |
| FR-12 | `-p` 파일 인코딩은 UTF-8 / UTF-8 BOM 모두 허용한다 | 필수 |
| FR-13 | `KeyboardInterrupt` 발생 시 exit 130 으로 종료한다 | 권장 |
| FR-14 | 처리 중 예외 발생 시 traceback 을 stderr 로 출력하고 exit 3 으로 종료한다 | 필수 |

### 4.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-01 | 배치 모드의 추가 코드는 기존 REPL 함수의 동작을 변경하지 않는다 (회귀 금지) |
| NFR-02 | 배치 모드에서는 `FileWatcher` 를 시작하지 않는다 (불필요한 백그라운드 스레드 차단) |
| NFR-03 | argparse 사용으로 표준 `--help` 가 자동 제공되어야 한다 |
| NFR-04 | `main_batch()` 는 단일 호출 후 반환 가능해야 하며 모듈 import side-effect 가 없어야 한다 |
| NFR-05 | 본 변경은 PyInstaller 빌드 환경에서도 동작해야 한다 (FSD v1.0.065 호환) |
| NFR-06 | 배치 모드의 stdout 은 처리 결과만 포함하고, ANSI 컬러 코드는 `NO_COLOR` 또는 비-TTY 환경에서 자동 제거된다 |

---

## 5. 변경 파일 요약

| 파일 | 변경 내용 |
|---|---|
| `ai_cli.py` (신규) | `argparse` 기반 디스패처, `-t/-wp/-c/-p` 파싱 후 세 엔트리포인트 `main_batch()` 호출 |
| `src/__main__.py` (신규, 선택) | `python -m src` 호환을 위한 thin wrapper. (또는 `python -m ai_cli` 만 지원하면 생략 가능) |
| `claude-ai-chat-code.py` | `_initialize()` 헬퍼 분리, `main_batch(workspace, command, command_args, prompt)` 함수 추가 |
| `gemini-ai-chat-code.py` | 동일 |
| `gen-ai-chat-code.py` | 동일 |
| `src/context_processor.py` | (필요 시) `process_files()` 가 사용자 확인을 묻지 않는다는 전제 재확인. 기존 동작이 이미 그러하면 변경 없음 |
| `tests/test_ai_cli_batch.py` (신규) | § 6 테스트 케이스 |
| `README.md` | 배치 실행 사용법 섹션 추가 (§ 9 참조) |

---

## 6. 테스트 케이스

### 6.1 단위 테스트 (`tests/test_ai_cli_batch.py`)

| ID | 테스트 | 기대 결과 |
|---|---|---|
| T-01 | `ai_cli.parse_args(["-t","claude","-wp",".","-c","auto_context","src/*.py","-p","p.txt"])` | namespace 에 `type=='claude'`, `command==['auto_context','src/*.py']`, `prompt=='p.txt'` |
| T-02 | `-t foo` | argparse SystemExit (exit code 2) |
| T-03 | `-c read src/*.py` | exit 2, "지원하지 않는 명령" 에러 |
| T-04 | `-c auto_context` (패턴 없음) | exit 2, "패턴이 누락" 에러 |
| T-05 | `-wp /not/exist` | exit 1, "작업 디렉토리가 존재하지 않습니다" |
| T-06 | `-p /not/exist.txt` | exit 1, "프롬프트 파일을 찾을 수 없습니다" |
| T-07 | 빈 프롬프트 파일 | exit 1, "프롬프트 파일이 비어있습니다" |
| T-08 | UTF-8 BOM 프롬프트 파일 | BOM 제거 후 본문이 정확히 로드됨 |
| T-09 | `main_batch()` mock — 매칭 0개 | return 1 |
| T-10 | `main_batch()` mock — 정상 처리 | return 0, REPL 루프 미진입 |
| T-11 | `KeyboardInterrupt` 모킹 | exit 130 |
| T-12 | `_load_entrypoint("claude-ai-chat-code.py")` | 모듈에 `main_batch` 심볼 존재 |

### 6.2 통합 테스트 (수동)

| ID | 테스트 | 기대 결과 |
|---|---|---|
| T-13 | `python -m ai_cli -t claude -wp ./ -c auto_context "src/*.py" -p prompt.txt` | 매칭 파일 처리 후 exit 0 |
| T-14 | T-13 동일하게 `-t gemini` | Gemini API 사용, exit 0 |
| T-15 | T-13 동일하게 `-t genai`  | GenAI API 사용, exit 0 |
| T-16 | `-c auto_context "[src/*.py, docs/*.md]"` (다중 패턴) | 두 패턴 모두 매칭, exit 0 |
| T-17 | `python claude-ai-chat-code.py` (인자 없음) | 기존 REPL 진입 (회귀 검증) |
| T-18 | `python -m ai_cli --help` | argparse 도움말 출력 후 exit 0 |
| T-19 | 배치 실행 중 Ctrl+C | exit 130, 정상 종료 메시지 |

---

## 7. 사용 예시

### 7.1 기본 사용 — Claude 로 `src/*.py` 자동 처리

```bash
# prompt.txt 작성
echo "이 코드를 리뷰하고 개선점을 표 형식으로 알려줘" > prompt.txt

# 배치 실행
python -m ai_cli -t claude -wp ./ -c auto_context "src/*.py" -p prompt.txt
```

> 와일드카드는 **반드시 따옴표** 로 감싼다. 그렇지 않으면 셸이 미리 글롭하여 `argparse` 에 다중 인자가 전달될 수 있다.

### 7.2 Gemini · 다중 패턴

```bash
python -m ai_cli \
    -t gemini \
    -wp /workspace/proj \
    -c auto_context "[src/*.py, docs/*.md]" \
    -p prompts/translate-ko.txt
```

### 7.3 GenAI · 절대 경로 워크스페이스

```bash
python -m ai_cli \
    --type genai \
    --workspace "C:\03_sources\skc3779_srcs\p3-ai-code-chat-messages" \
    --command auto_context "tests/*.py" \
    --prompt prompts/refactor.txt
```

---

## 8. 후속 작업 (Phase 2 이후)

| 항목 | 설명 |
|---|---|
| `-c` 의 명령 확장 | `read`, `context`, `agents` 등 다른 슬래시 명령도 배치 실행 지원 |
| `-c` 시퀀스 실행 | `-c "auto_context src/*.py" -c "save"` 형태로 다중 명령 파이프라인 |
| 결과 출력 파일 | `-o <file>` 옵션으로 LLM 응답을 별도 파일에 저장 |
| `--no-stream` | 배치 모드에서 토큰 청크 출력을 끄고 최종 응답만 출력 |
| `--quality-check` | `auto_context -qc` 동등 옵션을 배치 인자로 노출 (FSD v1.0.123) |

---

## 9. 마이그레이션 체크리스트

- [x] `ai_cli.py` 신규 작성 (argparse + `_load_entrypoint` + 디스패치)
- [x] `claude-ai-chat-code.py` 에 `_parse_auto_context_args()`, `main_batch()` 추가
- [x] `gemini-ai-chat-code.py` 에 `_parse_auto_context_args()`, `main_batch()` 추가
- [x] `gen-ai-chat-code.py` 에 `_parse_auto_context_args()`, `main_batch()` 추가
- [x] `tests/test_ai_cli_batch.py` 작성 및 통과 확인 (18/18 passed)
- [x] 세 엔트리포인트 직접 실행 시 기존 REPL 동작 회귀 검증 (`main()` 무수정)
- [x] `python -m ai_cli --help` 출력 검증
- [x] **FSD 구현 완료 후 `docs/releases` 폴더에 `RELEASE-v1.0.157` 문서 작성**
- [x] **README.md 파일 업데이트** — 배치 실행 사용법 섹션 추가 (§ 7 예시 포함)

---

## 10. 승인

- [x] FSD 문서 검토 완료
- [x] 코드 구현 완료
- [x] 테스트 케이스 전체 통과 (18/18)
- [x] 세 엔트리포인트의 `main_batch()` 시그니처 동일 확인
- [x] 배치 모드 정상 종료 (exit code) 확인
- [x] **FSD 구현 완료 후 `docs/releases` 폴더에 `RELEASE-v1.0.157` 문서 작성**
- [x] **README.md 파일 업데이트**
