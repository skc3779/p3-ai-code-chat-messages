# FSD v1.0.106 — `/agents` 시스템 프롬프트 재작성 · `[ACT]` 블록의 "코드 실행" vs "쉘 명령 실행" 명확화

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.106 |
| 작성일 | 2026-04-25 |
| 상태 | 🟡 설계 확정 (구현 대기) |
| 선행 문서 | FSD v1.0.083 (자율 루프), FSD v1.0.088 (OS Shell Hint), FSD v1.0.100 (Bypass), FSD v1.0.103 (Bypass Overwrite), FSD v1.0.104 (Terminal Executor Shell Hint), RELEASE v1.0.105 (Terminal Executor Shell-Aware) |
| 대상 파일 | [src/agent_runner.py](src/agent_runner.py), [src/os_utils.py](src/os_utils.py), [src/terminal_executor.py](src/terminal_executor.py), [src/code_executor.py](src/code_executor.py), [tests/test_agent_runner.py](tests/test_agent_runner.py) |
| 신규 파일 | [tests/test_agent_runner_act_parsing.py](tests/test_agent_runner_act_parsing.py) |

---

## 1. 개요

### 1.1 문제

`AgentRunner._build_system_prompt()` 가 AI 모델에게 `[ACT]` 블록 안에서 **세 가지 액션 타입**을 구분해 사용하라고 지시한다.

| 액션 | 현 프롬프트 규정 | 실행 경로 |
|---|---|---|
| 파일 생성/수정 | ```` ```filename:<경로> ... ``` ```` | `ResponseParser.parse_and_save()` |
| 코드 실행 (임시) | ```` ```python / ```bash / ```javascript ```` 블록 | `CodeExecutor.execute()` |
| 쉘 명령 실행 | 라인 시작에 `$ <명령>` | `TerminalExecutor.execute()` |

그러나 실사용에서 AI 모델이 **두 가지 실행 경로를 혼동**하여, 다음과 같은 잘못된 응답을 생성하는 사례가 반복 관측됐다.

#### 1.1.1 실패 패턴 A — "쉘 명령을 코드 블록으로 감싼" 응답

````markdown
[ACT]
```powershell
$ git status
$ git log --oneline -5
```
````

- 이 응답은 `RE_SHELL = r"^\s*\$\s+(.+)$"` 에 의해 `git status`, `git log ...` 가 `TerminalExecutor` 로 실행된다.
- **동시에** `extract_code_from_response()` 가 ```` ```powershell ```` 태그를 인식해 **`CodeExecutor` 로 .ps1 임시파일까지 만들어 실행**한다.
- 결과: **동일 명령이 두 번 실행**되거나, `$` 프리픽스를 포함한 스크립트가 PowerShell 에서 `$ : ... 용어가 <cmdlet, 함수, 스크립트 파일...> 로 인식되지 않습니다` 에러로 실패한다.

#### 1.1.2 실패 패턴 B — "코드 실행을 `$` 라인으로 표현한" 응답

```markdown
[ACT]
$ python -c "print('hello')"
$ python my_script.py
```

- AI 가 **Python 코드 실행 의도**로 작성했지만, `RE_SHELL` 에 의해 쉘로 실행된다.
- 쉘 환경에 `python` 이 없으면 `FileNotFoundError` 로 실패.
- `CodeExecutor` 로 실행할 때 기대되는 **UTF-8 환경 주입, 타임아웃, 자식 프로세스 격리** 가 적용되지 않는다.

#### 1.1.3 실패 패턴 C — "같은 iteration 에 두 경로 혼재"

````markdown
[ACT]
```python
print("step1")
```

$ python -c "print('step2')"

```bash
echo step3
```
````

- 세 액션이 각각 다른 경로로 실행되며, AI 가 결과 관찰(`[OBSERVE]`) 시 어느 출력이 어디 경로로 나왔는지 추적 불가.
- `bash` 블록은 Windows 에선 `CodeExecutor` 가 `powershell` 로 매핑하지만, `echo step3` 은 PowerShell cmdlet 으로도 동작하므로 겉보기엔 성공해 보이지만 **의도와 실행 환경이 어긋난다**.

#### 1.1.4 실패 패턴 D — "위험 명령을 코드 블록으로 우회"

````markdown
[ACT]
```powershell
Remove-Item -Recurse -Force .\build
```
````

- 현 구현에서 `TerminalExecutor.execute()` 는 `DANGEROUS_COMMANDS` 집합을 확인해 단건 승인 프롬프트를 띄운다. [src/agent_runner.py:648-674](src/agent_runner.py#L648-L674)
- 반면 `CodeExecutor` 경로는 **위험 명령 검사를 하지 않는다**. `extract_code_from_response()` 가 `powershell` 태그를 잡으면 **위험 명령이 승인 절차 없이 바로 실행**된다.
- 보안 관점에서 **의도하지 않은 Bypass** 경로가 존재한다.

### 1.2 근본 원인

1. **프롬프트의 추상성** — 현 프롬프트는 세 액션을 한 줄씩으로만 정의하고, 혼동 시의 **부정 예시**가 없다.
2. **파서 중복** — `RE_SHELL` 은 **코드 블록 내부의 `$` 라인도 포함**해 매칭한다. `extract_code_from_response()` 는 `powershell`/`bash`/`sh`/`ps1`/`shell` 태그를 모두 코드 실행 대상으로 간주한다. 두 범위가 겹친다.
3. **OS 힌트 노출 부족** — `_build_system_prompt()` 는 `get_os_shell_hint()` 의 1문단만 포함한다. 그러나 `TerminalExecutor.shell_help()` 는 현 쉘 환경의 **안전/위험 명령 목록**을 문서화하고 있는데, 이 내용은 에이전트 시스템 프롬프트에 포함되지 않아 AI 가 **실제 실행 가능한 명령을 추정**해야 한다.
4. **위험 명령 검증 누수** — 쉘 경로(`_run_shell_lines`) 만 `DANGEROUS_COMMANDS` 를 검사하고, 코드 경로(`_run_code_blocks`) 는 검사하지 않는다.

### 1.3 목표

1. **프롬프트 재작성** — AI 모델이 두 실행 경로를 오인하지 않도록, (a) 정의·(b) 실행되는 구체 경로·(c) 긍정 예시·(d) 부정 예시 를 모두 포함한 시스템 프롬프트를 구성한다.
2. **"터미널 명령어 실행 - 안전한 쉘 명령 실행 환경" 명시적 포함** — `TerminalExecutor.shell_help()` 의 요약본(또는 그 신규 압축 API) 을 에이전트 시스템 프롬프트에 포함해, AI 가 **실제 쉘 환경에서 동작하는 명령**을 선택하도록 유도.
3. **파서 결정론화** — `_run_shell_lines()` 는 **코드 블록 바깥의 `$` 라인만** 추출한다. `_run_code_blocks()` 와 경로가 절대 겹치지 않도록 한다.
4. **위험 명령 검증의 일관성** — 코드 경로에서도 쉘 계열(`bash`/`sh`/`powershell`/`ps1`/`shell`) 블록의 **첫 명령 토큰이 `DANGEROUS_COMMANDS` 에 포함되면** 동일한 승인 플로우를 태운다.
5. **`agent_runner.py` 단위 테스트 확대** — `[ACT]` 블록의 11가지 대표 케이스(§ 7) 에 대해 액션 분리/실행 경로가 결정론적으로 동작함을 검증.

### 1.4 범위

| 항목 | 포함 | 비고 |
|---|---|---|
| `_build_system_prompt()` 재작성 — CoT 단계별 힌트·긍정/부정 예시 | ✅ | § 3 |
| 에이전트 시스템 프롬프트에 `TerminalExecutor` 쉘 환경 요약 삽입 | ✅ | § 3.3 |
| `_run_shell_lines()` 가 코드 블록 내부 `$` 를 스킵 | ✅ | § 4.1 |
| `_run_code_blocks()` 에 위험 명령 검증 추가 | ✅ | § 4.2 |
| `_execute_actions()` 에서 중복 실행 방지 (동일 텍스트가 두 경로에 매칭되지 않도록) | ✅ | § 4.3 |
| `TerminalExecutor` 에 `agent_shell_brief()` 추가 (프롬프트용 요약) | ✅ | § 4.4 |
| `os_utils.get_os_shell_hint()` 문구 개선 (현 쉘 타입 명시) | ✅ | § 4.5 |
| 단위 테스트 `tests/test_agent_runner_act_parsing.py` 신규 | ✅ | § 7 |
| 기존 `tests/test_agent_runner.py` 확장 (T-106-01 ~ T-106-14) | ✅ | § 7 |
| `ResponseParser.parse_and_save()` 의 ```` ```filename: ```` 파싱 규칙 변경 | ❌ | 범위 외 |
| `CodeExecutor` 가 지원하는 언어 집합 축소/확장 | ❌ | 범위 외 |
| 에이전트 루프의 종료/재개 로직 변경 | ❌ | 범위 외 |

---

## 2. 현황 분석

### 2.1 현 프롬프트 원문 — [src/agent_runner.py:443-475](src/agent_runner.py#L443-L475)

```text
[ACT]
이번 단계에서 수행할 구체적 행동:
- 파일 생성/수정:  ```filename:<경로>
   ...
   ```
   블록
- 코드 실행:       ```python
 ...
 ```
 ```powershell  (← OS 에 따라 bash 또는 powershell)
 ...
 ```
 ```javascript
 ...
 ```
 블록 (파일명 없음 → 임시 실행)
- 쉘 명령 실행:    라인 시작에 `$ <명령>` (한 줄에 한 명령)
```

**평가:**

- 어느 쉘 언어 태그가 "코드 실행" 인지 "쉘 명령 실행" 인지 **모호**. (예: `powershell` 태그 블록 + `$` 라인 조합 시 중복 실행)
- **부정 예시 없음** — 금지 패턴을 AI 가 학습할 수 없다.
- **현재 OS/쉘 명시 누락** — `get_os_shell_hint()` 하단 한 줄만 포함. `TerminalExecutor.get_shell_type()` 의 값("Windows PowerShell" / "Windows CMD" / "Linux" / "Mac") 이 프롬프트에 들어가지 않는다.

### 2.2 현 파서 — [src/agent_runner.py:89](src/agent_runner.py#L89), [src/code_executor.py:173-201](src/code_executor.py#L173-L201)

```python
# AgentRunner
RE_SHELL = re.compile(r"^\s*\$\s+(.+)$", re.MULTILINE)
```

- `re.MULTILINE` 이라 **코드 블록 내부의 `$` 라인도 매칭**한다.

```python
# CodeExecutor
pattern2 = r'```(\w+)\n(.*?)```'
...
if lang.lower() in self.SUPPORTED_LANGUAGES:    # bash/sh/shell/powershell/ps1 포함
    code_blocks.append({...})
```

- `SUPPORTED_LANGUAGES` 에 쉘 계열 태그(`bash`, `sh`, `shell`, `powershell`, `ps1`) 가 포함되어 있어, **쉘 스크립트도 코드 실행 경로**로 처리된다.

### 2.3 현 실행 흐름 — [src/agent_runner.py:562-572](src/agent_runner.py#L562-L572)

```python
def _execute_actions(self, session, act_text):
    results = []
    results += self._save_file_blocks(session, act_text)    # filename: 블록
    results += self._run_code_blocks(act_text)              # ```lang 블록
    results += self._run_shell_lines(session, act_text)     # $ 라인
    return results
```

- 세 함수가 **동일한 `act_text`** 를 독립적으로 훑는다. 겹치는 텍스트는 두 번 실행된다.

### 2.4 `TerminalExecutor.shell_help()` — [src/terminal_executor.py:197-355](src/terminal_executor.py#L197-L355)

- 4가지 쉘 타입별로 상세한 안전/위험 명령 목록과 예시를 제공한다.
- 다만 `"/shell <cmd>"` 형식으로 **사용자 대화형 도움말**용이다. 에이전트 시스템 프롬프트에는 `$ <cmd>` 형식이어야 하므로 **그대로 주입할 수 없다**. 요약 API 가 필요하다.

### 2.5 `os_utils.get_os_shell_hint()` — [src/os_utils.py:7-20](src/os_utils.py#L7-L20)

```python
def get_os_shell_hint() -> str:
    if platform.system() == 'Windows':
        return (
            "현재 실행 환경: Windows OS.\n"
            "쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 ..."
        )
    ...
```

- `"Windows OS"` 만 알리고, PowerShell/CMD 구분은 안 한다.
- `TerminalExecutor.get_shell_type()` 와 분기 기준이 다르다(`platform.system()` 만). PSModulePath 기반 구분이 누락.

---

## 3. 설계 — 새 시스템 프롬프트

### 3.1 설계 원칙

| 원칙 | 설명 |
|---|---|
| **결정론** | AI 가 텍스트를 읽는 순서대로 어떤 파서가 매칭할지 예측 가능해야 한다. |
| **단일 경로** | 한 액션 텍스트는 **오직 한 파서**에만 매칭된다. |
| **구체 예시 우선** | 규칙 나열 대신 "✅ 이렇게 / ❌ 이렇게 하지 마세요" 쌍을 먼저 제시. |
| **쉘 환경 명시** | `get_shell_type()` 결과를 프롬프트 상단에 명시. |
| **안전/위험 구분** | Safe 명령 예시와 Dangerous 명령 목록을 별도로 노출. |

### 3.2 새 프롬프트 스켈레톤

```text
당신은 자율 코딩 에이전트입니다. 주어진 상위 목표를 달성하기 위해
스스로 계획을 세우고 단계별로 실행합니다.

[실행 환경]
OS          : Windows   (platform.system() 기준)
쉘 타입     : Windows PowerShell    ← 쉘 명령은 이 환경에서 실행됩니다
파일 인코딩 : UTF-8

[응답 형식 — 반드시 준수]

첫 번째 응답(계획 수립) 은 번호 매긴 목록으로 전체 PLAN 을 나열하세요.
이후 매 반복(iteration) 응답은 다음 세 블록을 **이 순서대로** 포함해야 합니다.

[REASON]
현재 상태를 분석하고, 바로 직전 [OBSERVE] 결과를 인용하며,
이번 단계에서 무엇을 할지 3줄 이내로 논리 기술.

[ACT]
== 선택지 A. 파일 생성/수정 ==
  ```filename:<상대경로>
  ... 파일 전문 ...
  ```
  • 파일 경로는 워크스페이스 상대경로, 한 블록에 **한 파일만**.
  • 줄바꿈·인코딩은 원본 그대로. 주석·언어 태그를 섞지 마세요.

== 선택지 B. 코드 실행 (임시 실행, 파일 저장 없음) ==
  ```python
  print("hello")
  ```
  • 언어 태그는 **정확히 `python` / `javascript`** 둘만 사용하세요.
  • 이 경로는 stdin 없음 · 타임아웃 30초 · 워크스페이스에서 실행.
  • 입출력 인코딩은 UTF-8 로 자동 강제됩니다.
  • ⚠️ **쉘/bash/sh/powershell/ps1 태그는 절대 사용하지 마세요.** (§ 선택지 C 참조)

== 선택지 C. 쉘 명령 실행 (현 쉘 환경에서 한 줄씩) ==
  라인 시작에 `$ <명령>` — **코드 블록으로 감싸지 마세요**.
    $ git status
    $ python --version
  • 한 줄에 한 명령, 여러 명령은 각각 별도 `$` 라인.
  • 파이프(|), 리다이렉트(>), `&&` 는 한 줄 안에서 허용.
  • 명령은 Windows PowerShell 구문을 사용하세요.

[OBSERVE]
위 ACT 를 실행했을 때 기대되는 결과를 1~3줄 서술.
(실제 실행 결과는 시스템이 다음 프롬프트에 주입합니다.)

[완료 판정]
목표를 완전히 달성했다고 판단되면 응답 맨 끝에 정확히 다음 한 줄:
  [AGENT_DONE]

[Self-Correction]
[OBSERVE] 또는 시스템 주입 결과에 오류가 있으면,
다음 [REASON] 에서 원인을 진단하고 [ACT] 를 교정하세요.

[금지 패턴 — 아래는 AI 가 자주 저지르는 실수입니다. 절대 하지 마세요]

❌ 쉘 명령을 코드 블록으로 감싸기
   ```powershell
   $ git status        ← $ 접두사가 파서에 의해 쉘 명령으로도 매칭되어 이중 실행됩니다
   ```

❌ 파이썬 코드를 `$` 라인으로 실행 시도
   $ python -c "print('hello')"
   → 단순한 문자열 출력은 OK 지만, 여러 줄 파이썬 로직은 선택지 B (```python 블록) 을 쓰세요.

❌ 같은 iteration 에 같은 명령을 두 경로로 중복 작성
   ```powershell
   git status
   ```
   $ git status           ← 두 번 실행됩니다

❌ 위험 명령을 코드 블록으로 숨기기
   ```powershell
   Remove-Item -Recurse -Force .\build
   ```
   → 시스템은 이 경우에도 승인 프롬프트를 띄웁니다 (v1.0.106 부터).

[쉘 환경 요약 — 현재 쉘: Windows PowerShell]

안전 명령 예시
   $ Get-ChildItem                 # 파일 목록
   $ Get-Content <file>            # 파일 내용 출력
   $ Get-Location                  # 현재 경로
   $ Test-Path <path>              # 경로 존재 여부
   $ Select-String <pat> <file>    # 텍스트 검색
   $ python --version
   $ pip list
   $ git status
   $ git log --oneline -10

위험 명령 (실행 전 승인 프롬프트 표시)
   Remove-Item, Move-Item, Rename-Item, Copy-Item,
   Set-Content, Add-Content, Clear-Content, New-Item,
   Set-Acl, Stop-Process, Restart-Computer, Stop-Computer,
   Invoke-WebRequest, Invoke-RestMethod,
   Set-ItemProperty, Remove-ItemProperty,
   Set-ExecutionPolicy, Invoke-Expression, iex

[주의]
- 코드 블록 밖에서 장황하게 설명하지 마세요.
- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.
- 위험 명령은 반드시 필요한 경우에만 사용하세요. 사용자가 거부할 수 있습니다.
- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.
```

> **주의:** 위 예시는 Windows PowerShell 환경을 가정한 것이며, 런타임에서 `TerminalExecutor.get_shell_type()` 반환값에 따라 **쉘 예시/위험 명령 목록/구문 힌트가 4분기**(Windows PowerShell / Windows CMD / Linux / Mac) 된다.

### 3.3 `TerminalExecutor.agent_shell_brief()` — 신규 API

`shell_help()` 는 `/shell <cmd>` 형식이라 에이전트에 부적합하다. 에이전트 프롬프트 전용 요약 메서드를 추가한다.

```python
# src/terminal_executor.py

@staticmethod
def agent_shell_brief() -> str:
    """에이전트 시스템 프롬프트에 삽입할 현 쉘 환경 요약.

    `shell_help()` 의 `/shell <cmd>` 포맷 대신 에이전트가 실제 생성하는
    `$ <cmd>` 포맷으로 안전 명령 예시와 위험 명령 목록을 제공한다.
    """
    shell_type = TerminalExecutor.get_shell_type()
    dangerous = sorted(
        TerminalExecutor._get_dangerous_for_shell(shell_type)
    )

    if shell_type == 'Windows PowerShell':
        safe_examples = [
            "$ Get-ChildItem                 # 파일 목록",
            "$ Get-Content <file>            # 파일 내용",
            "$ Get-Location                  # 현재 경로",
            "$ Test-Path <path>              # 경로 존재",
            "$ Select-String <pat> <file>    # 텍스트 검색",
            "$ python --version",
            "$ pip list",
            "$ git status",
            "$ git log --oneline -10",
        ]
    elif shell_type == 'Windows CMD':
        safe_examples = [
            "$ dir                           # 파일 목록",
            "$ type <file>                   # 파일 내용",
            "$ where <cmd>                   # 명령어 경로",
            "$ find /i \"text\" <file>       # 텍스트 검색",
            "$ python --version",
            "$ pip list",
            "$ git status",
        ]
    elif shell_type == 'Mac':
        safe_examples = [
            "$ ls -la",
            "$ cat <file>",
            "$ grep -r 'pat' src/",
            "$ find . -name '*.py'",
            "$ python3 --version",
            "$ pip3 list",
            "$ git status",
        ]
    else:  # Linux
        safe_examples = [
            "$ ls -la",
            "$ cat <file>",
            "$ grep -r 'pat' src/",
            "$ find . -name '*.py'",
            "$ python3 --version",
            "$ pip3 list",
            "$ git status",
        ]

    lines = [
        f"[쉘 환경 요약 — 현재 쉘: {shell_type}]",
        "",
        "안전 명령 예시",
        *[f"  {ex}" for ex in safe_examples],
        "",
        "위험 명령 (실행 전 승인 프롬프트 표시)",
        f"  {', '.join(dangerous)}",
    ]
    return "\n".join(lines)
```

### 3.4 `os_utils.get_os_shell_hint()` 개선

`platform.system()` 에만 의존하던 것을 `TerminalExecutor.get_shell_type()` 로 일원화한다.

```python
# src/os_utils.py
from .terminal_executor import TerminalExecutor


def get_os_shell_hint() -> str:
    """현재 OS/쉘 타입을 기반으로 쉘 구문 힌트를 반환한다."""
    shell_type = TerminalExecutor.get_shell_type()
    if shell_type == 'Windows PowerShell':
        return (
            "현재 실행 환경: Windows PowerShell.\n"
            "쉘 명령은 PowerShell 구문을 사용하세요. "
            "`bash`/`sh` 구문은 이 환경에서 실행되지 않습니다."
        )
    if shell_type == 'Windows CMD':
        return (
            "현재 실행 환경: Windows CMD.\n"
            "쉘 명령은 CMD 구문을 사용하세요. "
            "`bash`/`sh` 구문은 이 환경에서 실행되지 않습니다."
        )
    if shell_type == 'Mac':
        return (
            "현재 실행 환경: macOS (Bash/Zsh).\n"
            "쉘 명령은 bash/zsh 구문을 사용하세요."
        )
    return (
        "현재 실행 환경: Linux (Bash).\n"
        "쉘 명령은 bash 구문을 사용하세요."
    )
```

> **순환 import 주의:** `terminal_executor` 가 `os_utils` 를 import 하지 않으므로 단방향 의존으로 안전하다. (확인: `terminal_executor.py` 내 `from .os_utils ...` 구문 없음)

### 3.5 `_build_system_prompt()` 재작성

```python
# src/agent_runner.py

def _build_system_prompt(self) -> str:
    from .terminal_executor import TerminalExecutor
    shell_type = TerminalExecutor.get_shell_type()
    shell_brief = TerminalExecutor.agent_shell_brief()
    os_hint = get_os_shell_hint()

    # 쉘 타입별 "언어 태그 안내" 3가지 패턴
    if shell_type.startswith('Windows'):
        code_lang_note = (
            "  ```python / ```javascript 만 코드 실행 대상입니다.\n"
            "  쉘 스크립트가 필요하면 선택지 C (`$ ...`) 를 사용하세요."
        )
    else:
        code_lang_note = (
            "  ```python / ```javascript 만 코드 실행 대상입니다.\n"
            "  쉘 스크립트가 필요하면 선택지 C (`$ ...`) 를 사용하세요."
        )

    return (
        "당신은 자율 코딩 에이전트입니다. 주어진 상위 목표를 달성하기 위해\n"
        "스스로 계획을 세우고 단계별로 실행합니다.\n\n"

        f"[실행 환경]\n{os_hint}\n\n"

        "[응답 형식 — 반드시 준수]\n"
        "첫 번째 응답(계획 수립)은 번호 매긴 목록으로 전체 PLAN 을 나열하세요.\n"
        "이후 매 반복(iteration) 응답은 다음 세 블록을 이 순서대로 포함해야 합니다.\n\n"

        "[REASON]\n"
        "현재 상태 분석 + 직전 [OBSERVE] 참조 + 이번 단계 의도 (3줄 이내)\n\n"

        "[ACT]\n"
        "아래 세 선택지 중 **1~3 개를 골라** 순서대로 작성하세요.\n\n"

        "== 선택지 A. 파일 생성/수정 ==\n"
        "  ```filename:<상대경로>\n"
        "  ... 파일 전문 ...\n"
        "  ```\n"
        "  • 한 블록에 한 파일. 경로는 워크스페이스 상대경로.\n\n"

        "== 선택지 B. 코드 실행 (임시 실행, 파일 저장 없음) ==\n"
        "  ```python\n"
        "  print(\"hello\")\n"
        "  ```\n"
        f"{code_lang_note}\n"
        "  • 타임아웃 30초, 워크스페이스에서 실행, 입출력 UTF-8.\n\n"

        "== 선택지 C. 쉘 명령 실행 ==\n"
        "  라인 시작에 `$ <명령>` — 코드 블록으로 감싸지 마세요.\n"
        "    $ git status\n"
        "    $ python --version\n"
        "  • 한 줄에 한 명령. 파이프(|)·리다이렉트(>)·`&&` 는 한 줄 내 허용.\n"
        f"  • 명령은 {shell_type} 구문을 사용하세요.\n\n"

        "[OBSERVE]\n"
        "위 ACT 실행 시 기대 결과를 1~3줄 서술.\n"
        "(실제 실행 결과는 시스템이 다음 프롬프트에 주입합니다.)\n\n"

        "[완료 판정]\n"
        f"목표 달성 시 응답 맨 끝에 정확히: {self.done_token}\n\n"

        "[Self-Correction]\n"
        "[OBSERVE] 또는 시스템 제공 결과에 오류 시, 다음 [REASON] 에서\n"
        "원인 진단 후 [ACT] 를 교정하세요.\n\n"

        "[❌ 금지 패턴 — 자주 발생하는 실수입니다]\n\n"

        "1) 쉘 명령을 코드 블록으로 감싸기\n"
        "   ```powershell\n"
        "   $ git status\n"
        "   ```\n"
        "   → `$` 라인이 쉘 파서와 코드 파서 양쪽에 매칭되어 이중 실행.\n\n"

        "2) 같은 명령을 두 경로에 중복 작성\n"
        "   ```powershell\n"
        "   git status\n"
        "   ```\n"
        "   $ git status          ← 두 번 실행됨\n\n"

        "3) 여러 줄 파이썬 로직을 $ 로 실행\n"
        "   → 선택지 B (```python 블록) 을 쓰세요.\n\n"

        "4) 위험 명령을 코드 블록으로 숨기기\n"
        "   (v1.0.106 부터 이 경로에도 승인 프롬프트가 적용됩니다.)\n\n"

        f"{shell_brief}\n\n"

        "[주의]\n"
        "- 코드 블록 밖에서 장황하게 설명하지 마세요.\n"
        "- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.\n"
        "- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.\n"
    )
```

### 3.6 설계 트레이드오프

| 선택 | 채택안 | 기각안 | 사유 |
|---|---|---|---|
| "쉘 스크립트" 표현 | 선택지 C (`$` 라인) 단일 경로 | `bash`/`powershell` 언어 태그 블록도 허용 | 중복 매칭 금지 원칙. 단일 경로가 AI 학습에 유리. |
| 코드 언어 태그 범위 | `python`/`javascript` 두 가지만 프롬프트에 노출 | 기존 5개(`bash`/`sh`/`shell`/`powershell`/`ps1` 포함) | `CodeExecutor` 는 이들을 지원하지만, 에이전트 프롬프트에서는 **C 경로만 쉘 담당**. CodeExecutor 지원 언어 자체는 변경하지 않음(하위 호환) |
| 쉘 브리프 길이 | 안전 9개 · 위험 목록 1줄 | 전체 `shell_help()` 복사 | 토큰 비용. 에이전트는 "환경이 있다는 것" 만 알면 충분. |
| OS 힌트 출처 | `os_utils.get_os_shell_hint()` 개선 | `TerminalExecutor` 로 이전 | 기존 공개 함수 유지(FSD v1.0.088 호환) |

---

## 4. 파서/실행 경로 개선

### 4.1 `_run_shell_lines()` — 코드 블록 내부 `$` 스킵

```python
# src/agent_runner.py

RE_FENCED_BLOCK = re.compile(r"```.*?\n.*?```", re.DOTALL)

def _strip_fenced_blocks(self, text: str) -> str:
    """펜스(```) 코드 블록을 공백으로 치환해 길이·라인을 보존.

    RE_SHELL 이 코드 블록 안쪽의 `$` 라인을 잘못 매칭하지 않도록,
    블록 내용을 동일 길이의 공백으로 교체한다. 라인 번호 보존이 중요.
    """
    def _blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return self.RE_FENCED_BLOCK.sub(_blank, text)

def _run_shell_lines(self, session, act_text):
    cleaned = self._strip_fenced_blocks(act_text)
    lines = self.RE_SHELL.findall(cleaned)
    ...
```

**효과:**
- `[ACT]` 에 ```` ```powershell\n$ git status\n``` ```` 가 있어도 `_run_shell_lines` 은 **빈 매칭**을 반환.
- 중복 실행 제거.

### 4.2 `_run_code_blocks()` — 쉘 계열 언어 차단 + 위험 명령 검사

두 가지 변경:

**(a) 쉘 계열 언어 블록을 에이전트 경로에서 거부**

```python
_SHELL_LANG_KEYS_SET = {'bash', 'sh', 'shell', 'powershell', 'ps1'}

def _run_code_blocks(self, act_text):
    results = []
    try:
        blocks = self.code_executor.extract_code_from_response(act_text) or []
    except Exception as e:
        return [ActionResult(kind="code", target="?", success=False,
                             detail=f"코드 블록 추출 오류: {e}")]

    for block in blocks:
        if block.get("filepath"):
            continue
        lang = (block.get("language") or "").lower()
        code = block.get("code", "")
        if not code:
            continue

        # v1.0.106: 쉘 계열 언어 태그는 에이전트에서 거부 (선택지 C 로 유도)
        if lang in _SHELL_LANG_KEYS_SET:
            results.append(ActionResult(
                kind="code", target=lang, success=False,
                detail=(
                    f"쉘 언어 태그(`{lang}`) 블록은 에이전트에서 실행되지 않습니다. "
                    f"`$ <명령>` 라인을 사용하세요."
                ),
            ))
            continue

        print(f"\n⚙️  코드 실행 ({lang})...")
        result = self.code_executor.execute(code, lang)
        ...
```

> 이 거부는 **에이전트 루프 내부**에만 적용된다. `/run` 등 대화형 경로는 `CodeExecutor.execute()` 를 직접 쓰므로 영향 없음.

**(b) (옵션) 실행 전 위험 명령 검사** — 쉘 계열을 차단했으므로 § 4.2(a) 만으로 충분. 추가 검사는 생략.

### 4.3 `_execute_actions()` — 처리 순서 명시

```python
def _execute_actions(self, session, act_text):
    if not act_text:
        return []
    results = []
    # 순서: (1) 파일 (2) 코드 (3) 쉘 — 명시적 문서화
    results += self._save_file_blocks(session, act_text)
    results += self._run_code_blocks(act_text)         # filename: 블록 건너뛰기 내부 처리
    results += self._run_shell_lines(session, act_text)  # 코드 블록 내부 $ 는 § 4.1 로 제거
    return results
```

- 세 경로가 각각 **상호 배타적 텍스트 영역**을 처리하도록 보장됨:
  - `_save_file_blocks` → ```` ```filename:... ``` ```` 전용
  - `_run_code_blocks` → ```` ```python/javascript ```` 전용 (filename 블록 skip, 쉘 계열 거부)
  - `_run_shell_lines` → 펜스 바깥의 `$` 라인 전용

### 4.4 `TerminalExecutor.agent_shell_brief()` — § 3.3 참조

### 4.5 `os_utils.get_os_shell_hint()` — § 3.4 참조

---

## 5. 파일 변경 예정 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [src/agent_runner.py](src/agent_runner.py) | 수정 | `_build_system_prompt()` 재작성, `_run_shell_lines()` 에 `_strip_fenced_blocks()` 도입, `_run_code_blocks()` 에 쉘 계열 거부 추가, `RE_FENCED_BLOCK` 상수 추가 |
| [src/terminal_executor.py](src/terminal_executor.py) | 수정 | `agent_shell_brief()` 정적 메서드 추가 |
| [src/os_utils.py](src/os_utils.py) | 수정 | `get_shell_type()` 기반으로 4분기, import 추가 |
| [src/code_executor.py](src/code_executor.py) | 변경 없음 | `SUPPORTED_LANGUAGES`, `extract_code_from_response()` 는 그대로 — `/run` 호환 |
| [tests/test_agent_runner.py](tests/test_agent_runner.py) | 수정 | T-106-01 ~ T-106-06 추가 (프롬프트 구성) |
| [tests/test_agent_runner_act_parsing.py](tests/test_agent_runner_act_parsing.py) | 신규 | T-106-07 ~ T-106-14 (ACT 파싱/실행 경로 분리) |
| [docs/specs/releases/RELEASE_v1.0.106_agents-system-prompt-act-disambiguation.md](docs/specs/releases/RELEASE_v1.0.106_agents-system-prompt-act-disambiguation.md) | 신규 | 구현 완료 후 작성 |

---

## 6. 요구사항

### 6.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-106-01 | `_build_system_prompt()` 는 상단에 `[실행 환경]` 섹션으로 `TerminalExecutor.get_shell_type()` 결과를 포함해야 한다. | 필수 |
| FR-106-02 | `[ACT]` 섹션은 "선택지 A/B/C" 로 명확히 3분할되어야 하며, 각 선택지는 정의·실행 경로·예시 1건 이상을 포함한다. | 필수 |
| FR-106-03 | 프롬프트의 선택지 B 는 `python` / `javascript` 만 노출하고, 쉘 계열 언어 태그 사용을 **명시적으로 금지**해야 한다. | 필수 |
| FR-106-04 | 프롬프트는 `[❌ 금지 패턴]` 섹션을 포함하고, 1.1.1~1.1.4 의 4가지 실패 패턴 각각에 대해 "잘못된 예 + 이유" 를 담아야 한다. | 필수 |
| FR-106-05 | 프롬프트는 `TerminalExecutor.agent_shell_brief()` 의 반환값을 포함해 현 쉘의 안전/위험 명령을 노출한다. | 필수 |
| FR-106-06 | `_run_shell_lines()` 는 ```` ``` ```` 으로 감싼 펜스 블록 내부의 `$` 라인을 **매칭하지 않아야** 한다. | 필수 |
| FR-106-07 | `_run_code_blocks()` 는 언어 태그가 `bash`/`sh`/`shell`/`powershell`/`ps1` 인 블록을 실행하지 않고, `ActionResult(kind="code", success=False)` 로 거부 사유를 반환해야 한다. | 필수 |
| FR-106-08 | `_execute_actions()` 는 (1) 파일 (2) 코드 (3) 쉘 순으로 호출되며, 동일 텍스트가 두 경로에 매칭되지 않아야 한다. | 필수 |
| FR-106-09 | `TerminalExecutor.agent_shell_brief()` 는 쉘 타입(4종) 별로 서로 다른 안전 예시 목록을 반환해야 한다. | 필수 |
| FR-106-10 | `os_utils.get_os_shell_hint()` 는 Windows PowerShell / Windows CMD / Linux / Mac 4분기를 반환한다. | 필수 |
| FR-106-11 | 기존 `get_os_shell_hint()` 를 호출하던 모든 경로(`AgentRunner._build_system_prompt`, `TerminalExecutor._execute_command_safely` 등) 는 재작성 후에도 동일 시그니처로 호출 가능해야 한다. | 필수 |
| FR-106-12 | Bypass Approvals 모드(v1.0.100) 에서도 `_run_code_blocks()` 의 쉘 거부는 동일하게 적용된다 (바이패스 대상 아님). | 필수 |
| FR-106-13 | 프롬프트 재작성은 `done_token`, `self_correct_max` 등 기존 환경변수 인터페이스를 변경하지 않아야 한다. | 필수 |
| FR-106-14 | 프롬프트 예상 토큰 길이는 한국어 기준 약 1200~1800 토큰 이내 (기존 대비 +700 ~ +1300). | 권장 |

### 6.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-106-01 | `_build_system_prompt()` 재작성 후에도 `_call_model()` 의 시스템 프롬프트 교체 플로우는 변경되지 않는다. |
| NFR-106-02 | `_strip_fenced_blocks()` 는 라인 번호를 보존(펜스 내부를 공백으로 치환) 하여, 향후 에러 리포트에서 위치 매핑이 깨지지 않게 한다. |
| NFR-106-03 | 쉘 계열 언어 블록 거부는 `ActionResult(success=False)` 로 표기되며, Self-Correction 루프가 **정상 작동**해 AI 가 다음 iteration 에서 `$` 라인으로 교정할 수 있어야 한다. |
| NFR-106-04 | 프롬프트 내 OS/쉘 힌트는 `AgentRunner` 인스턴스 생성 시점이 아니라 `_build_system_prompt()` **호출 시점**에 재계산된다. (env 변경 대응) |
| NFR-106-05 | 테스트는 `unittest.mock.patch("platform.system")` 및 `patch.dict(os.environ, {"PSModulePath": ...})` 로 4쉘 타입 모두 커버한다. |
| NFR-106-06 | 프롬프트 변경으로 인한 Vertex AI / Claude / GenAI 호출 응답 호환성 회귀는 발생하지 않는다(기존 `[REASON]/[ACT]/[OBSERVE]` 정규식 동일). |

---

## 7. 테스트 시나리오

### 7.1 기존 `tests/test_agent_runner.py` 추가 테스트

**클래스:** `TestBuildSystemPrompt106` (신규)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-106-01 | `_build_system_prompt()` 이 "선택지 A", "선택지 B", "선택지 C" 세 문자열을 모두 포함 | `assertIn` 3회 |
| T-106-02 | 프롬프트에 `[❌ 금지 패턴]` 섹션 존재 | `assertIn("[❌ 금지 패턴]", p)` |
| T-106-03 | 프롬프트에 `TerminalExecutor.agent_shell_brief()` 결과 포함 (`[쉘 환경 요약`) | `assertIn("[쉘 환경 요약", p)` |
| T-106-04 | `platform.system()` mock 을 `"Windows"` + `PSModulePath` env 주입 시 프롬프트에 `"Windows PowerShell"` 문자열 포함 | `assertIn("Windows PowerShell", p)` |
| T-106-05 | `platform.system()="Linux"` mock 시 프롬프트에 `"Linux"` 및 `"bash"` 포함 | `assertIn("Linux", p)`, `assertIn("bash", p)` |
| T-106-06 | 프롬프트에 선택지 B 의 언어 태그는 정확히 `python` / `javascript` 만 노출, `powershell` / `bash` / `sh` 는 **선택지 B 블록 범위 안에서** 미노출 | 문자열 범위 검증 (`[ACT]` 섹션 안에서 `[❌ 금지 패턴]` 전까지의 부분문자열을 잘라 검사) |

### 7.2 신규 `tests/test_agent_runner_act_parsing.py`

**목적:** `[ACT]` 블록의 다양한 형식에 대해 실행 경로 분리가 결정론적임을 검증.

**공통 셋업:** `_make_runner()` 헬퍼를 재사용. `CodeExecutor` / `TerminalExecutor` / `ResponseParser` 는 모두 Mock.

| # | 시나리오 | 입력 `act_text` | 기대 `ActionResult` |
|---|---|---|---|
| T-106-07 | 단독 쉘 라인 | `"$ git status"` | shell 1건 (`target="git status"`), code 0건, file 0건 |
| T-106-08 | 단독 파이썬 블록 | ```` ```python\nprint("hi")\n``` ```` | code 1건 (`target="python"`), shell 0건 |
| T-106-09 | 단독 파일 블록 | ```` ```filename:a.py\ncode\n``` ```` | file 1건 (`target="a.py"`), code 0건 (filepath skip), shell 0건 |
| T-106-10 | **실패 패턴 A** — 쉘 라인을 powershell 블록으로 감싼 경우 | ```` ```powershell\n$ git status\n``` ```` | shell 0건 (펜스 스킵), code 1건이되 `success=False` 이고 detail 에 "쉘 언어 태그" 문구 포함 |
| T-106-11 | **실패 패턴 B** — `$` 라인에 `python -c "..."` | `"$ python -c \"print('x')\""` | shell 1건 — 현 스펙상 허용(단일 명령). code 0건 |
| T-106-12 | **실패 패턴 C** — 세 경로 혼재 | 파이썬 블록 + $ 라인 + 파일 블록 | file 1 + code 1 + shell 1 총 3건, 각각 중복 없음 |
| T-106-13 | **실패 패턴 D** — powershell 블록 내부의 위험 명령(`Remove-Item`) | ```` ```powershell\nRemove-Item .\build\n``` ```` | code 1건 `success=False`, detail 에 "쉘 언어 태그" 포함 (실행되지 않음) |
| T-106-14 | 여러 펜스 블록 사이 `$` 라인 | ```` ```python\nprint(1)\n```\n$ echo hi\n```javascript\nconsole.log(2)\n``` ```` | code 2건 (python / javascript), shell 1건 (`echo hi`), 순서 무관 |
| T-106-15 | `$` 라인이 펜스 바깥과 안쪽에 둘 다 있을 때 | ```` $ outside\n```powershell\n$ inside\n``` ```` | shell 1건 `"outside"` 만, `"inside"` 미포함 |
| T-106-16 | bash 코드 블록(Windows 환경에서도) | ```` ```bash\nls -la\n``` ```` | code 1건 `success=False`, detail 에 "쉘 언어 태그(`bash`)" 포함 |
| T-106-17 | `$` 접두사 없는 단순 쉘 라인 (예: `git status`) | `"git status"` | shell 0건, code 0건, file 0건 (아무것도 실행 안 됨) |

### 7.3 `TerminalExecutor.agent_shell_brief()` 단위 테스트 (tests/test_terminal_executor.py 확장)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-106-18 | `get_shell_type()` mock 이 `"Windows PowerShell"` 반환 시 `agent_shell_brief()` 에 `"Get-ChildItem"`, `"Remove-Item"` 포함 | `assertIn` 2회 |
| T-106-19 | `"Windows CMD"` mock 시 `"dir"`, `"del"` 포함 | `assertIn` 2회 |
| T-106-20 | `"Linux"` mock 시 `"ls -la"`, `"rm"` 포함 | `assertIn` 2회 |
| T-106-21 | `"Mac"` mock 시 `"ls -la"`, `"diskutil"` 포함 | `assertIn` 2회 |
| T-106-22 | 반환 문자열 맨 윗줄이 `"[쉘 환경 요약 — 현재 쉘: <type>]"` 형식 | `startswith` 검증 |

### 7.4 `os_utils.get_os_shell_hint()` 테스트 (tests/test_os_utils.py 확장)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-106-23 | shell_type mock = Windows PowerShell → `"Windows PowerShell"` 포함 | `assertIn` |
| T-106-24 | shell_type mock = Windows CMD → `"Windows CMD"` 포함 | `assertIn` |
| T-106-25 | shell_type mock = Mac → `"macOS"` 포함 | `assertIn` |
| T-106-26 | shell_type mock = Linux → `"Linux"` 포함 | `assertIn` |

---

## 8. 실행 흐름 다이어그램

### 8.1 수정 후 `_execute_actions()` 플로우

```
act_text (AI 응답의 [ACT] 블록 원문)
  │
  ├─ _save_file_blocks(session, act_text)
  │    └─ RE_FILENAME_BLOCK 매칭 → response_parser.parse_and_save(...)
  │         └─ ActionResult(kind="file", ...)
  │
  ├─ _run_code_blocks(act_text)
  │    └─ code_executor.extract_code_from_response(act_text)
  │         ├─ filepath 있음 → skip (파일 경로에서 이미 처리)
  │         ├─ lang ∈ {bash, sh, shell, powershell, ps1}
  │         │    └─ ActionResult(kind="code", success=False,
  │         │                    detail="쉘 언어 태그(`...`) 블록은 ...")
  │         │       ※ 실행 안 함
  │         └─ lang ∈ {python, py, javascript, js}
  │              └─ code_executor.execute(code, lang)
  │                   └─ ActionResult(kind="code", ...)
  │
  └─ _run_shell_lines(session, act_text)
       ├─ _strip_fenced_blocks(act_text)   ← 펜스 내부를 공백으로
       └─ RE_SHELL.findall(cleaned)
             └─ 각 cmd → terminal_executor.execute(...)
                  └─ ActionResult(kind="shell", ...)
```

### 8.2 금지 패턴 A(쉘을 블록으로 감쌈) 의 처리

```markdown
입력:
  ```powershell
  $ git status
  ```

_save_file_blocks      → 파일 블록 없음 (RE_FILENAME_BLOCK 미매칭)
_run_code_blocks       → lang="powershell" → success=False 거부
                         ActionResult(kind="code", target="powershell",
                                      success=False,
                                      detail="쉘 언어 태그(`powershell`) 블록은 ...")
_run_shell_lines       → _strip_fenced_blocks 로 내부 $ git status 제거
                         → 매칭 0건

⇒ 실제 실행 없음, Self-Correction 이 다음 iteration 에서
   AI 에게 "선택지 C ($ 라인) 사용" 을 유도.
```

---

## 9. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | 프롬프트 길이 증가로 iteration 당 입력 토큰 +700 ~ +1300 예상 | 과금 영향 있으나, Self-Correction 감소로 총 iteration 수 감소 기대 |
| 2 | 기존 AgentSession 이력(`agent_history`) 에 들어 있는 AI 응답은 "과거 프롬프트 기준" 으로 생성됨 → Resume 시 혼선 가능 | Resume 은 기존 세션을 그대로 로드하지만, 다음 `_call_model()` 부터는 새 system_prompt 가 적용되어 자연 교정됨 |
| 3 | `CodeExecutor.SUPPORTED_LANGUAGES` 에는 쉘 태그가 여전히 존재 (`/run` 명령 호환) → 에이전트 경로에서만 거부 | `_run_code_blocks()` 에서 분기, CodeExecutor 자체는 불변 |
| 4 | 프롬프트의 긍정/부정 예시가 모델별로 다르게 해석될 수 있음 (Claude/Gemini/GenAI) | 기본은 영어권 모델에서도 명확한 `❌` / `✅` 기호 사용. 응답 품질 모니터링 후 추가 보정. |
| 5 | Windows CMD 환경에서 `PSModulePath` 가 설정되지 않은 상태 판별 | `TerminalExecutor.get_shell_type()` 이 이미 이 분기를 처리(PSModulePath 유무). 테스트에서 `os.environ` 조작 필요. |
| 6 | `_strip_fenced_blocks()` 는 언어 태그 없는 ```` ``` ``` ```` 블록(일반 코드 인용) 도 제거 → 사용자 의도와 다를 수 있음 | 에이전트 경로에서 쉘 명령은 오직 `$` 라인만 허용되므로 "쉘 외의 인용 블록 내 $ 라인" 은 실행 대상 아님 — 올바른 동작 |
| 7 | `agent_shell_brief()` 의 안전 명령 예시는 하드코딩 | 쉘 타입별로 대표 9개 내외. 실제 사용 패턴을 보며 조정. |
| 8 | Bypass 모드에서도 쉘 계열 코드 블록은 거부됨(자동 실행 안 됨) | Bypass 는 "승인 프롬프트 스킵" 이지 "파서 우회" 가 아님. AI 는 선택지 C 로 재작성해야 한다. 이는 의도된 설계. |

---

## 10. 후속 작업

| 단계 | 내용 | 비고 |
|---|---|---|
| 1 | 프롬프트 실 사용 데이터에서 Self-Correction 호출 횟수 측정 → 1.1.1~1.1.4 패턴 재발률 추적 | 별도 로깅 필요 |
| 2 | Claude / Gemini / GenAI 별 응답 품질 A/B 비교 후 프롬프트 미세 조정 | RELEASE v1.0.107 예정 |
| 3 | `agent_shell_brief()` 의 예시 확장 (git 서브커맨드·패키지 매니저별 분기) | 별도 FSD |
| 4 | `_strip_fenced_blocks()` 을 `ResponseParser` 에도 공유(중복 shell line 매칭 방지) | 범위 외 |
| 5 | 프롬프트 축약판(`AGENT_PROMPT_COMPACT=1`) 옵션 도입 — 토큰 절감 | 필요시 별도 FSD |

---

## 11. 승인

- [ ] 설계 검토
- [ ] `src/terminal_executor.py` `agent_shell_brief()` 추가 및 T-106-18 ~ T-106-22 통과
- [ ] `src/os_utils.py` 4분기 개선 및 T-106-23 ~ T-106-26 통과
- [ ] `src/agent_runner.py` `_build_system_prompt()` 재작성 및 T-106-01 ~ T-106-06 통과
- [ ] `src/agent_runner.py` `_strip_fenced_blocks()` / `_run_code_blocks()` 쉘 거부 구현 및 T-106-07 ~ T-106-17 통과
- [ ] 기존 테스트 회귀 없음(`tests/test_agent_runner.py`, `tests/test_terminal_executor.py`, `tests/test_os_utils.py`)
- [ ] `/agents` 실사용 수동 확인 — 1.1.1 ~ 1.1.4 실패 패턴 재현 시도 후 새 프롬프트가 안내하는 형식으로 AI 응답이 교정되는지 관찰
- [ ] `docs/specs/releases/RELEASE_v1.0.106_agents-system-prompt-act-disambiguation.md` 작성
