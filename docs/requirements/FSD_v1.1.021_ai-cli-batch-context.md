# FSD v1.1.021 — `ai_cli` `/context` 배치 실행 및 자동 종료

## 문서 정보

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.1.021 |
| 작성일 | 2026-06-21 |
| 상태 | 구현 완료 |
| 대상 명령 | `python -m ai_cli ... -c context ...` |
| 선행 문서 | `FSD_v1.0.157_ai-cli-batch-auto-context.md`, `FSD_v1.0.123_auto-context-quality-check-and-context-no-tree.md`, `FSD_v1.1.011_context-large-file-handling.md` |
| 주요 대상 파일 | [ai_cli.py](../../ai_cli.py), [src/cli_input.py](../../src/cli_input.py), [claude-ai-chat-code.py](../../claude-ai-chat-code.py), [gemini-ai-chat-code.py](../../gemini-ai-chat-code.py), [gen-ai-chat-code.py](../../gen-ai-chat-code.py) |
| 테스트 대상 파일 | [tests/test_ai_cli_batch.py](../../tests/test_ai_cli_batch.py), [tests/test_large_context_command.py](../../tests/test_large_context_command.py), 신규 `tests/test_ai_cli_batch_context.py` |

---

## 1. 목적

기존 `ai_cli` 배치 모드는 `/auto_context`만 명령줄에서 즉시 실행하고 처리 완료 후 종료한다. 본 FSD는 기존 동작을 유지하면서 REPL 전용인 `/context`를 동일한 단일 실행 방식으로 추가한다.

```powershell
python -m ai_cli -t <claude|gemini|genai> `
    -wp <workspace-path> `
    -c context <options> <pattern> `
    -p <prompt-file>
```

대표 실행 예시는 다음과 같다.

```powershell
python -m ai_cli -t gemini `
    -wp C:\03_sources\github_others_srcs\baeldung-tutorials `
    -c context -l -nt [apache-kafka-2/**/*.*,apache-kafka-3/**/*.*,apache-kafka-4/sa/**/*.*] `
    -p docs\prompts\prompt_module_guide.md
```

성공 조건은 다음과 같다.

1. `context`와 `auto_context`를 같은 `ai_cli` 진입점에서 선택할 수 있다.
2. `context`는 REPL, 멀티라인 입력, 사용자 확인을 거치지 않는다.
3. `-l`/`--large`, `-nt`/`--no-tree`, 단일·다중 패턴의 의미가 REPL `/context`와 같다.
4. `-p` 파일 본문이 질문으로 사용되고, 응답 처리가 끝나면 프로세스가 종료된다.
5. 성공·입력 오류·처리 오류·사용자 중단이 안정적인 종료 코드로 구분된다.
6. 기존 `/auto_context` 배치 및 REPL `/context` 동작에 회귀가 없다.

---

## 2. 범위

### 2.1 포함 범위

- `-c context <options> <pattern>` 명령 인식
- `/context` 공통 옵션과 패턴 파서 재사용
- 일반 컨텍스트 단일 호출과 `--large` Map/Reduce 호출
- `-p` 프롬프트 파일 기반 비대화형 질문 전달
- 응답 출력, 종료 코드, 오류 메시지 표준화
- 세 provider(`claude`, `gemini`, `genai`)의 동일한 동작
- 단위·통합·회귀 테스트

### 2.2 제외 범위

- 한 프로세스에서 여러 명령을 순차 실행하는 파이프라인
- `-p` 없이 stdin 또는 명령줄 인라인 질문을 받는 기능
- `/read`, `/tokens`, `/agents` 등 다른 REPL 명령의 배치 지원
- `/context` 및 `--large` 자체 알고리즘 변경
- provider API, 모델 선택, 인증 환경변수 규칙 변경
- 신규 외부 패키지 도입

---

## 3. 현행 구현 분석

### 3.1 `ai_cli`의 제한

[ai_cli.py](../../ai_cli.py)는 `-c`의 첫 토큰을 `auto_context`로만 허용한다.

```python
if args.command[0] != "auto_context":
    return 2
```

세 엔트리포인트의 `main_batch()`도 같은 제한을 중복 구현한다. 따라서 디스패처와 provider별 배치 함수 모두 확장해야 한다.

### 3.2 `/context`의 재사용 가능한 계약

[src/cli_input.py](../../src/cli_input.py)의 `parse_context_command_args()`는 다음 항목을 이미 공통 파싱한다.

- `-l`, `--large`
- `-nt`, `--no-tree`
- 단일 패턴
- `[pattern1,pattern2]` 다중 패턴
- 패턴 뒤 인라인 질문
- 알 수 없는 옵션 및 닫히지 않은 대괄호 오류

배치 모드에서 별도의 `/context` 파서를 만들지 않고 이 함수를 단일 파싱 기준으로 사용해야 한다.

### 3.3 `-c` 내부 옵션과 `argparse` 충돌

현재 `-c/--command`는 `nargs='+'`이다. 이 방식에서 아래의 `-l`, `-nt`는 명령 인자가 아니라 `ai_cli` 최상위 옵션으로 해석될 수 있다.

```text
-c context -l -nt [src/**/*.*] -p prompt.md
```

따라서 따옴표 사용을 강제하거나 `nargs='+'`만 유지하는 구현은 요구 예시를 충족하지 못한다. CLI 파싱 전에 `-c` 뒤부터 다음 **등록된 최상위 옵션** 전까지의 토큰을 원문 순서대로 추출해야 한다.

### 3.4 REPL 전용 상호작용

현재 REPL `/context`는 패턴 뒤 질문이 없으면 멀티라인 입력을 호출한다. 배치 모드에서는 질문을 `-p`에서 이미 읽으므로 다음 동작을 금지한다.

- `get_multiline()` 호출
- `input()` 호출
- 처리 후 REPL 루프 진입
- 파일 저장 여부를 사용자에게 묻는 후속 상호작용 (배치 모드는 `auto_overwrite=True` 로 대체)

---

## 4. 기능 요구사항

### FR-01. 지원 명령 확장

`ai_cli`는 다음 두 명령을 허용한다.

| 명령 | 실행 의미 |
|---|---|
| `auto_context` | 기존 파일별 순차 자동 처리 |
| `context` | 파일 컨텍스트를 포함한 단일 질문 처리 |

명령명 앞의 `/`는 받지 않는다. `-c /context ...`는 미지원 명령으로 종료 코드 `2`를 반환한다.

### FR-02. 명령 토큰 추출

`ai_cli`는 원시 `argv`에서 `-c` 또는 `--command`의 값을 추출한다.

1. 시작 토큰은 `-c` 또는 `--command`이다.
2. 종료 지점은 다음에 나타나는 등록된 최상위 옵션 `-t`, `--type`, `-wp`, `--workspace`, `-p`, `--prompt`, `-c`, `--command`, `-o`, `--output`이다.
3. `-l`, `--large`, `-nt`, `--no-tree`는 최상위 옵션이 아니며 명령 토큰에 보존한다.
4. 명령 구간이 비었거나 `-c`가 두 번 이상이면 사용법 오류로 종료한다.
5. 최상위 옵션 순서는 고정하지 않되 각 옵션은 한 번만 허용한다.

예상 결과:

```python
argv = [
    "-t", "gemini", "-wp", "C:\\work",
    "-c", "context", "-l", "-nt", "[a/**/*.*,b/**/*.*]",
    "-p", "prompt.md",
]

command_tokens == ["context", "-l", "-nt", "[a/**/*.*,b/**/*.*]"]
```

추출 후 나머지 최상위 인자는 기존 `argparse`로 검증한다. 이 로직은 `auto_context`의 기존 토큰 순서와 패턴 문자열도 그대로 보존해야 한다.

### FR-03. `/context` 인자 파싱

명령 이름을 제외한 토큰을 공백으로 결합해 `parse_context_command_args()`에 전달한다.

```python
parsed = parse_context_command_args(" ".join(command_tokens[1:]))
```

| 입력 | 파싱 결과 |
|---|---|
| `context src/*.py` | `patterns=['src/*.py']`, `large=False`, `no_tree=False` |
| `context -nt src/*.py` | `patterns=['src/*.py']`, `large=False`, `no_tree=True` |
| `context -l [src/*.py,docs/*.md]` | 다중 패턴, `large=True` |
| `context --large --no-tree [...]` | 다중 패턴, `large=True`, `no_tree=True` |

### FR-04. 질문 소스

- 질문은 `-p` 파일의 UTF-8/UTF-8 BOM 본문만 사용한다.
- 상대 프롬프트 경로는 기존과 같이 `-wp` 기준으로 해석한다.
- 파일이 없거나 읽을 수 없거나 `strip()` 후 비어 있으면 종료 코드 `1`이다.
- `-c context <pattern> 인라인 질문`처럼 파서가 인라인 질문을 검출하면 모호성을 피하기 위해 종료 코드 `2`와 함께 거부한다.
- 오류 문구는 `context 배치 모드의 질문은 -p 파일로만 지정하세요.`를 포함한다.

### FR-05. 일반 `/context` 실행

`parsed.large is False`이면 provider assistant를 초기화한 후 아래 호출을 정확히 한 번 수행한다.

```python
response = assistant.chat(
    prompt,
    streaming=<provider의 기존 배치 기본값>,
    include_context=True,
    file_patterns=parsed.file_patterns,
    include_tree=not parsed.no_tree,
)
```

- REPL과 동일한 `assistant.chat()` 경로를 사용한다.
- 배치 실행에서는 대화 히스토리를 다음 명령으로 이어가지 않는다.
- 반환값이 문자열이고 provider가 응답을 직접 출력하지 않은 경우 `🤖 AI: <response>` 형식으로 한 번 출력한다.
- 스트리밍 provider의 중복 출력을 막기 위해 출력 책임은 공통 배치 실행 헬퍼에서 명시적으로 한 곳에 둔다.

### FR-06. 대규모 `/context` 실행

`parsed.large is True`이면 FSD v1.1.011의 처리기를 사용한다.

```python
response = LargeContextProcessor(
    assistant,
    assistant.file_manager,
    provider=provider,
).process(
    parsed.file_patterns,
    prompt,
    include_tree=not parsed.no_tree,
)
```

- `-nt`는 `include_tree=False`로 전달한다.
- 캐시, 재개, 예산 계산, Map/Reduce 오류 규칙은 FSD v1.1.011을 변경하지 않는다.
- 성공 시 최종 통합 응답을 한 번 출력하고 종료한다.

### FR-07. 파일 매칭 실패

API 호출 전에 `FilePatternMatcher` 또는 기존 처리기의 동일한 매칭 계약으로 대상 파일 존재 여부를 검증한다.

- 매칭 파일이 없으면 API를 호출하지 않는다.
- stderr에 패턴과 `해당하는 파일이 없습니다`를 출력한다.
- 종료 코드 `1`을 반환한다.
- 일반 모드와 대규모 모드의 패턴 해석 결과가 같아야 한다.

### FR-08. 자동 종료

응답 출력 및 자동 저장(FR-11) 또는 오류 처리가 끝나면 `main_batch()`가 정수 코드를 반환하고 `ai_cli`의 `sys.exit()`가 프로세스를 종료한다. 파일 감시자, 백그라운드 스레드, REPL 루프를 시작하지 않는다. `/save` 와 같은 후속 상호작용도 시작하지 않는다.

### FR-09. 종료 코드

| 코드 | 조건 |
|---:|---|
| `0` | 응답 처리 및 출력 완료 (저장 포함) |
| `1` | 워크스페이스·프롬프트·패턴·매칭 파일·저장 디렉토리 등 사용자 입력 데이터 오류 |
| `2` | argparse 사용법 오류, 미지원 명령, 인라인 질문 충돌 |
| `3` | 엔트리포인트 로드, 인증, provider API, 컨텍스트 처리 예외 |
| `130` | `KeyboardInterrupt` |

세 provider는 같은 오류 분류를 사용해야 한다.

### FR-10. 하위 호환성

- 기존 `python -m ai_cli ... -c auto_context ...` 구문과 종료 코드를 유지한다.
- 기존 provider 스크립트를 직접 실행했을 때의 REPL `/context` 동작을 유지한다.
- `/context`의 옵션 별칭, 패턴 파싱, `--large` 캐시 형식은 변경하지 않는다.
- `-o` 옵션을 지정하지 않으면 자동 저장을 수행하지 않는다. 기존 동작과 동일하다.

### FR-11. 응답 자동 저장

배치 모드에서는 REPL의 `/save` 같은 후속 상호작용이 불가능하다. 따라서 응답 출력 직후 `-o`/`--output` 옵션 유무에 따라 두 가지 방식으로 자동 저장한다.

| 조건 | 동작 |
|---|---|
| `-o <dir>` **지정** | 응답 전체를 `<dir>/context_YYYYMMDD_HHMMSS.md` 단일 파일로 저장 |
| `-o` **미지정** | 응답에서 `@@@filename:경로/파일명.확장자` 블록을 추출해 각 파일 경로에 자동 저장 (`/save` 와 동일 로직) |

#### FR-11.1 CLI 옵션

```powershell
# -o 지정: 응답 전체를 단일 파일로 저장
python -m ai_cli -t <type> -wp <workspace> -c context <options> <pattern> -p <prompt> -o <output-dir>

# -o 미지정: @@@filename:... 블록 자동 추출·저장
python -m ai_cli -t <type> -wp <workspace> -c context <options> <pattern> -p <prompt>
```

| 옵션 | 별칭 | 의미 |
|---|---|---|
| `-o` | `--output` | 응답 전체를 저장할 디렉토리 경로 (선택) |

- 비절대경로는 `-wp` 워크스페이스 기준으로 해석한다.
- 지정 경로가 존재하지 않으면 `mkdir -p` 방식으로 자동 생성한다.
- 경로가 존재하지만 파일인 경우 종료 코드 `1`을 반환하고 엔트리포인트를 로드하지 않는다.
- `-o` 옵션은 최상위 옵션이며 명령 토큰(`-l`, `-nt` 등)과 구분된다.

#### FR-11.2 `-o` 지정 시: 응답 단일 파일 저장

- 파일 이름: `context_YYYYMMDD_HHMMSS.md`
- 인코딩: UTF-8 (BOM 없음)
- 헤더(날짜·Provider·패턴)와 응답 본문을 포함한다.

```markdown
# AI 응답

- 날짜: YYYY-MM-DD HH:MM:SS
- Provider: <provider>
- 파일 패턴: <pattern1>, <pattern2>, ...

---

<응답 텍스트>
```

- 저장 성공 시: `💾 응답 저장: <절대경로>` stdout 출력
- `OSError` 등 저장 실패 시: stderr 오류 출력 후 종료 코드 `1`
- 응답이 비어 있으면 파일을 생성하지 않는다.

#### FR-11.3 `-o` 미지정 시: `@@@filename:` 블록 자동 추출·저장

응답에 포함된 아래 형식의 모든 파일 블록을 추출하여 해당 경로에 저장한다.

```
@@@filename:경로/파일명.확장자
파일 내용...
@@@
```

- REPL `/save` 명령의 `ResponseParser.parse_and_save()` 를 재사용한다.
- 배치 모드는 `input()` 호출 불가이므로 `auto_overwrite=True` 로 기존 파일을 확인 없이 덮어쓴다.
- 블록이 있고 저장 성공 시: `✅ 총 N개 파일이 저장되었습니다.` stdout 출력
- 블록이 없으면 출력 없이 정상 종료(exit `0`)
- 개별 파일 저장 성공/실패는 `ResponseParser` 내부에서 `✅`/`❌` 출력한다.
- 일반 모드와 대규모(`--large`) 모드 모두에 적용된다.

#### FR-11.4 모듈 계약

`run_context_batch()` 에 `output_dir: Path | None = None` 파라미터를 사용한다. `ai_cli`는 `output_dir` 을 `main_batch()` 키워드 인자로 전달한다.

```python
def run_context_batch(
    *,
    assistant,
    provider: str,
    request: ContextBatchRequest,
    streaming: bool,
    output_dir: Path | None = None,
) -> int: ...

def main_batch(
    workspace: str,
    command: str,
    command_args: str,
    prompt: str,
    *,
    output_dir: str | None = None,
) -> int: ...
```

저장 분기 의사코드:

```python
if output_dir is not None:
    # -o 지정: 응답 전체를 단일 파일로 저장
    if response:
        saved_path = _save_response(response, output_dir, provider, patterns)
        print(f"💾 응답 저장: {saved_path}")
else:
    # -o 미지정: @@@filename:... 블록 자동 추출/저장
    if response:
        saved_files = assistant.response_parser.parse_and_save(
            response, auto_overwrite=True
        )
        if saved_files:
            print(f"✅ 총 {len(saved_files)}개 파일이 저장되었습니다.")
```

---

## 5. 설계 가이드

### 5.1 권장 모듈 경계

provider별 `main_batch()`에 `/context` 분기를 세 번 복사하지 않는다. 다음과 같이 provider 독립 실행 함수를 [src/cli_input.py](../../src/cli_input.py) 또는 신규 `src/batch_context.py`에 둔다.

```python
def run_context_batch(
    *,
    assistant,
    provider: str,
    command_args: str,
    prompt: str,
    streaming: bool,
) -> int:
    ...
```

각 엔트리포인트는 인증·assistant 생성까지만 담당하고 공통 함수에 위임한다. 이 구조는 파싱, 매칭, 일반/large 분기, 출력, 오류 코드를 한 계약으로 유지한다.

### 5.2 `main_batch()` 분기

```python
if command not in {"auto_context", "context"}:
    return 2

assistant = initialize_provider_assistant(workspace)

if command == "auto_context":
    return run_auto_context_batch(...)

return run_context_batch(
    assistant=assistant,
    provider="gemini",
    command_args=command_args,
    prompt=prompt,
    streaming=True,
)
```

초기화 이전에 명령명과 구문을 검증해 잘못된 CLI 입력이 API 키 오류로 가려지지 않게 한다.

### 5.3 처리 흐름

```text
raw argv
  → -c 명령 토큰 추출
  → 최상위 argparse 검증
  → workspace/prompt 검증 및 prompt 로드
  → provider 엔트리포인트 로드
  → main_batch(command="context")
  → parse_context_command_args(command_args)
  → 인라인 질문 없음 검증
  → 패턴 매칭 및 0건 차단
  ├─ large=False → assistant.chat(include_context=True)
  └─ large=True  → LargeContextProcessor.process()
  → 최종 응답 출력
  → exit 0
```

### 5.4 오류 처리 경계

- 파싱 및 입력 파일 오류는 traceback을 출력하지 않는다.
- 예상하지 못한 예외만 provider 정보와 함께 stderr에 출력하고 종료 코드 `3`을 반환한다.
- API 키, secret, prompt 본문, 컨텍스트 원문은 오류 로그에 출력하지 않는다.
- `KeyboardInterrupt`는 traceback 없이 `130`으로 변환한다.

---

## 6. 비기능 요구사항

| ID | 요구사항 |
|---|---|
| NFR-01 | Python 3.12.10에서 동작해야 한다. |
| NFR-02 | 신규 외부 의존성을 추가하지 않는다. |
| NFR-03 | Windows PowerShell과 bash/zsh에서 동일한 명령 의미를 제공한다. |
| NFR-04 | 경로는 `pathlib.Path`로 처리하고 Windows 절대경로 및 workspace 상대경로를 지원한다. |
| NFR-05 | 프롬프트 파일은 `utf-8-sig`로 읽어 BOM을 제거한다. |
| NFR-06 | 배치 실행 중 stdin을 읽지 않는다. CI에서 닫힌 stdin으로 실행 가능해야 한다. |
| NFR-07 | command 파서와 context 파서는 순수 함수로 분리해 API 호출 없이 단위 테스트할 수 있어야 한다. |
| NFR-08 | 세 provider의 분기 로직은 공통 헬퍼로 검증해 동작 편차를 방지한다. |

---

## 7. 테스트 케이스

### 7.1 CLI 파싱 및 검증

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-C01 | `-c context src/*.py` | 명령=`context`, 패턴 토큰 보존 |
| TC-C02 | `-c context -l -nt [a/**/*.*,b/**/*.*] -p p.md` | `-l`, `-nt`가 최상위 옵션 오류 없이 명령 토큰에 포함 |
| TC-C03 | `--command context --large --no-tree [...]` | 긴 별칭 정상 파싱 |
| TC-C04 | 최상위 옵션 순서를 `-p`, `-c`, `-wp`, `-t`로 변경 | 동일한 Namespace와 명령 토큰 생성 |
| TC-C05 | `-c` 값 누락 | exit `2` |
| TC-C06 | `-c` 중복 | exit `2` |
| TC-C07 | `-c /context src/*.py` | 미지원 명령, exit `2` |
| TC-C08 | `-c read src/*.py` | 미지원 명령, exit `2` |
| TC-C09 | `context -x src/*.py` | 알 수 없는 context 옵션, exit `1` |
| TC-C10 | `context [a/*.py,b/*.md` | 닫는 대괄호 오류, exit `1` |
| TC-C11 | `context src/*.py 인라인 질문`과 `-p` 동시 사용 | 충돌 오류, exit `2`, API 미호출 |

### 7.2 일반 컨텍스트 실행

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-N01 | 단일 패턴 | `assistant.chat()` 1회, `include_context=True` |
| TC-N02 | 다중 패턴 | 패턴 순서와 값이 그대로 전달 |
| TC-N03 | `-nt` | `include_tree=False` |
| TC-N04 | 옵션 없음 | `include_tree=True` |
| TC-N05 | 매칭 파일 0건 | chat 미호출, exit `1` |
| TC-N06 | 정상 문자열 응답 | 응답 1회 출력, exit `0` |
| TC-N07 | provider 예외 | stderr 오류, exit `3` |
| TC-N08 | stdin을 읽으면 실패하도록 mock | stdin 미사용, 정상 종료 |

### 7.3 대규모 컨텍스트 실행

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-L01 | `-l` | `LargeContextProcessor.process()` 1회, chat 직접 호출 없음 |
| TC-L02 | `--large -nt` | `include_tree=False` 전달 |
| TC-L03 | 다중 패턴 | 모든 패턴이 동일 순서로 processor에 전달 |
| TC-L04 | 처리기 최종 응답 | 응답 1회 출력, exit `0` |
| TC-L05 | `LargeContextError` | exit `3`, REPL 진입 없음 |
| TC-L06 | 재실행 캐시 적중 | 완료 청크 재호출 없이 최종 처리 완료 |

### 7.4 provider 계약

아래 테스트는 `claude`, `gemini`, `genai`에 대해 매개변수화한다.

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-P01 | `main_batch(..., command='context')` | 공통 context 실행 헬퍼 호출 |
| TC-P02 | 일반 모드 | 올바른 assistant와 provider별 streaming 값 전달 |
| TC-P03 | large 모드 | processor에 정확한 provider 이름 전달 |
| TC-P04 | 인증 정보 누락 | exit `3`, secret 미출력 |
| TC-P05 | `KeyboardInterrupt` | exit `130` |

### 7.5 프롬프트 및 경로

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-F01 | workspace 상대 `-p` | `-wp` 기준 파일 로드 |
| TC-F02 | 절대 `-p` | 지정 파일 로드 |
| TC-F03 | UTF-8 BOM 파일 | BOM 제거 후 질문 전달 |
| TC-F04 | 빈 파일 | exit `1` |
| TC-F05 | 존재하지 않는 파일 | exit `1` |
| TC-F06 | 존재하지 않는 workspace | exit `1` |
| TC-F07 | 공백·한글이 포함된 Windows 경로 | 따옴표로 전달 시 정상 resolve |

### 7.6 회귀 테스트

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-R01 | 기존 `auto_context` 단일 패턴 | 기존 `main_batch()` 호출 인자 및 exit 유지 |
| TC-R02 | 기존 `auto_context -qc` | 품질 검사 옵션 유지 |
| TC-R03 | REPL `/context src/*.py 질문` | 기존 일반 context 동작 유지 |
| TC-R04 | REPL `/context -l -nt [...] 질문` | 기존 large/no-tree 동작 유지 |
| TC-R05 | 기존 `tests/test_ai_cli_batch.py` 전체 | 모두 통과 |
| TC-R06 | 기존 context/large-context 테스트 전체 | 모두 통과 |

### 7.7 응답 자동 저장 (FR-11)

#### 7.7.1 CLI 파싱 (`-o` 옵션)

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-S01 | `-o <dir>` 옵션 | `args.output == <dir>`, 명령 토큰에 포함되지 않음 |
| TC-S02 | `--output <dir>` 긴 별칭 | 동일 |
| TC-S03 | `-o` 옵션을 `-c` 앞에 배치 | 명령 토큰 오염 없이 정상 파싱 |
| TC-S04 | `-o` 미지정 | `args.output is None` |
| TC-S05 | `-o` 경로가 존재하지 않는 디렉토리 | 자동 생성 후 정상 진행 |
| TC-S06 | `-o` 경로가 파일인 경우 | exit `1`, 엔트리포인트 미로드 |

#### 7.7.2 `-o` 지정: 응답 단일 파일 저장

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-S07 | 일반 모드, `-o` 지정 | `context_YYYYMMDD_HHMMSS.md` 생성, Provider·패턴·응답 포함 |
| TC-S08 | 대규모 모드, `-o` 지정 | 동일한 저장 동작 |
| TC-S09 | 저장 성공 | stdout에 `💾 응답 저장: <절대경로>` 출력 |
| TC-S10 | `OSError` 발생 시 | exit `1`, stderr에 `응답 저장 실패` 포함 |
| TC-S11 | 파일명이 `context_YYYYMMDD_HHMMSS.md` 패턴 | 정규식 `context_\d{8}_\d{6}\.md` 일치 |

#### 7.7.3 `-o` 미지정: `@@@filename:` 블록 자동 추출·저장

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-S12 | 응답에 블록 있음 | `parse_and_save(response, auto_overwrite=True)` 호출, `✅ 총 N개` 출력 |
| TC-S13 | 응답에 블록 없음 | `parse_and_save` 호출, 저장 관련 메시지 없이 exit `0` |
| TC-S14 | `💾` 미출력 확인 | stdout에 `💾` 없음 (단일 파일 저장 아님) |

#### 7.7.4 provider 위임 계약

| ID | 시나리오 | 기대 결과 |
|---|---|---|
| TC-S15 | `claude`, `gemini`, `genai` 각각 `-o` 지정 | `run_context_batch(output_dir=Path(...))` 호출 확인 |

---

## 8. 검증 절차

### 8.1 정적 및 자동 테스트

구현 후 아래 순서로 실행한다.

```powershell
python -m pytest tests/test_ai_cli_batch.py tests/test_ai_cli_batch_context.py -q
python -m pytest tests/test_large_context_command.py tests/test_large_context_processor.py -q
python -m pytest tests/test_context_pattern.py -q
python -m pytest -q
```

프로젝트에 설정된 lint/typecheck 명령이 존재하면 변경 파일에 대해 추가 실행한다. 새 도구나 패키지는 설치하지 않는다.

### 8.2 API 미호출 통합 검증

provider와 assistant를 mock하여 다음을 증명한다.

1. 예시 명령의 토큰이 손실 없이 파싱된다.
2. 프롬프트 파일 본문이 `prompt` 인자로 전달된다.
3. `-l -nt`가 `LargeContextProcessor.process(..., include_tree=False)`로 전달된다.
4. 반환 후 REPL 입력 함수와 파일 감시자가 호출되지 않는다.
5. `main()` 반환값이 프로세스 종료 코드로 전달된다.
6. `-o <dir>` 지정 시 `run_context_batch(output_dir=Path(<dir>))`로 전달되고, 응답 전체가 단일 파일로 저장된다.
7. `-o` 미지정 시 `assistant.response_parser.parse_and_save(response, auto_overwrite=True)`가 호출된다.

### 8.3 실제 provider 스모크 테스트

유효한 개발용 인증 환경에서 provider별 최소 1회 수행한다. 외부 API 호출이므로 자동 단위 테스트에는 포함하지 않는다.

```powershell
# 저장 없이 실행
python -m ai_cli -t claude -wp . -c context -nt "[src/cli_input.py]" -p docs\prompts\smoke.md
python -m ai_cli -t gemini -wp . -c context -l -nt "[src/cli_input.py]" -p docs\prompts\smoke.md
python -m ai_cli -t genai  -wp . -c context "[src/cli_input.py]" -p docs\prompts\smoke.md

# 자동 저장 포함 실행
python -m ai_cli -t claude -wp . -c context -nt "[src/cli_input.py]" -p docs\prompts\smoke.md -o docs\responses
python -m ai_cli -t gemini -wp . -c context -l -nt "[src/cli_input.py]" -p docs\prompts\smoke.md -o docs\responses
```

각 실행에서 다음을 확인한다.

- 응답이 한 번 출력된다.
- 추가 입력 프롬프트가 나타나지 않는다.
- 정상 완료 시 `$LASTEXITCODE`가 `0`이다.
- 실패 시 오류 유형에 맞는 종료 코드가 반환된다.
- 로그에 인증 정보와 프롬프트 전문이 노출되지 않는다.
- `-o` 지정 시 `docs\responses\context_YYYYMMDD_HHMMSS.md` 가 생성되고 stdout에 `💾 응답 저장:` 경로가 출력된다.

---

## 9. 구현 완료 체크리스트

- [x] `ai_cli`가 `context`와 `auto_context`를 모두 허용한다.
- [x] `-c context -l -nt ...`가 따옴표 없이도 파싱된다.
- [x] `parse_context_command_args()`를 재사용한다.
- [x] `-p`만 질문 소스로 사용하며 인라인 질문 충돌을 거부한다.
- [x] 일반 모드가 `assistant.chat(include_context=True)`를 호출한다.
- [x] large 모드가 `LargeContextProcessor`를 호출한다.
- [x] `-nt`가 두 모드 모두에서 트리를 제외한다.
- [x] 매칭 파일이 없으면 외부 API를 호출하지 않는다.
- [x] 세 provider가 공통 실행 경로와 종료 코드를 사용한다.
- [x] 처리 완료 후 stdin 대기 또는 REPL 진입 없이 종료한다.
- [x] 신규 테스트와 기존 회귀 테스트가 통과한다.
- [x] 변경 파일 `compileall`과 `git diff --check`가 통과했다.
- [x] `-o`/`--output` 옵션이 최상위 옵션으로 등록되어 명령 토큰 오염 없이 파싱된다.
- [x] 비절대 `-o` 경로는 `-wp` 기준으로 resolve 된다.
- [x] 지정 디렉토리가 없으면 자동 생성, 파일이면 exit `1`로 조기 거부한다.
- [x] `-o` 지정 시: 응답 전체를 `context_YYYYMMDD_HHMMSS.md` 단일 파일로 저장, 헤더(날짜·Provider·패턴) 포함, `💾 응답 저장:` 출력.
- [x] `-o` 미지정 시: `assistant.response_parser.parse_and_save(response, auto_overwrite=True)` 호출로 `@@@filename:` 블록 자동 추출·저장.
- [x] 블록 있음 → `✅ 총 N개 파일이 저장되었습니다.` 출력 / 블록 없음 → 출력 없이 exit `0`.
- [x] 저장 `OSError` 시 exit `1`.
- [x] 세 provider의 `main_batch(output_dir=)` 위임 계약이 단위 테스트로 검증된다.

검증 기록(2026-06-21, FR-11 수정): FR-11 재정의 후 신규 테스트 포함 총 51개 `test_ai_cli_batch_context.py` 테스트 통과. 회귀 테스트(`test_large_context_command.py`, `test_context_pattern.py`, `test_context_builder.py`, `test_command_parser_options.py`) 54개 통과. 실제 provider API 스모크 테스트는 인증 정보가 없어 수행하지 않았다.

---

## 10. 완료 기준

본 기능은 다음 조건을 모두 만족할 때 완료로 판정한다.

1. 요구 예시 명령이 그대로 실행 가능하다.
2. 세 provider에서 일반 및 `--large` context 배치 분기가 검증된다.
3. 정상 완료 시 자동 종료 및 exit `0`이 확인된다.
4. 입력 오류, 처리 오류, 사용자 중단의 종료 코드 테스트가 통과한다.
5. 기존 `auto_context` 배치와 REPL context 회귀 테스트가 통과한다.
6. `-o` 지정 시 응답 전체가 단일 파일로 저장되고, `-o` 미지정 시 응답 내 `@@@filename:` 블록이 `/save` 와 동일하게 자동 저장되며, 두 경우 모두 추가 상호작용 없이 프로세스가 종료된다.
7. 실제 API 검증을 수행하지 못한 경우 그 사유와 미검증 위험이 릴리스 기록에 명시된다.
