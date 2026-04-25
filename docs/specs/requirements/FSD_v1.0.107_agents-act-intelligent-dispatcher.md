# FSD v1.0.107 — `/agents` 시스템 프롬프트 재작성 + `[ACT]` 지능형 디스패처 (코드 실행 ↔ 쉘 명령 자동 판별)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.107 |
| 작성일 | 2026-04-25 |
| 상태 | 🟡 설계 확정 (구현 대기) |
| 선행 문서 | FSD v1.0.083 (자율 루프), FSD v1.0.088 (OS Shell Hint), FSD v1.0.100 (Bypass), FSD v1.0.101 (max_iterations override), FSD v1.0.103 (Bypass Overwrite), FSD v1.0.104 (Terminal Executor Shell Hint), RELEASE v1.0.105 (Terminal Executor Shell-Aware), FSD v1.0.106 (System Prompt 재작성 — strict-reject 접근) |
| 대상 파일 | [src/agent_runner.py](src/agent_runner.py), [src/os_utils.py](src/os_utils.py), [src/terminal_executor.py](src/terminal_executor.py), [src/code_executor.py](src/code_executor.py), [tests/test_agent_runner.py](tests/test_agent_runner.py) |
| 신규 파일 | [src/agent_action_dispatcher.py](src/agent_action_dispatcher.py), [tests/test_agent_action_dispatcher.py](tests/test_agent_action_dispatcher.py) |

---

## 1. 개요

### 1.1 문제

`AgentRunner._build_system_prompt()` 의 시스템 명령은 AI 모델에게 `[ACT]` 블록 안에서 **세 가지 액션 타입**을 구분해 사용하라고 지시한다. ([src/agent_runner.py:443-475](src/agent_runner.py#L443-L475))

| 액션 | 현 프롬프트 규정 | 실행 경로 |
|---|---|---|
| 파일 생성/수정 | ```` ```filename:<경로> ... ``` ```` | `_save_file_blocks` → `ResponseParser.parse_and_save()` |
| 코드 실행 (임시) | ```` ```python / ```bash / ```javascript ```` 블록 | `_run_code_blocks` → `CodeExecutor.execute()` |
| 쉘 명령 실행 | 라인 시작에 `$ <명령>` | `_run_shell_lines` → `TerminalExecutor.execute()` |

그러나 실사용에서 AI 모델이 **`코드 실행` 과 `쉘 명령 실행` 두 경로를 자주 혼동**하여, 다음 4가지 잘못된 응답을 반복적으로 생성한다.

#### 1.1.1 실패 패턴 A — 쉘 명령을 코드 블록으로 감싼 응답

````markdown
[ACT]
```powershell
$ git status
$ git log --oneline -5
```
````

**현재 동작:**
- `RE_SHELL = r"^\s*\$\s+(.+)$"` 가 `re.MULTILINE` 으로 동작해 **코드 블록 내부의 `$` 라인도 매칭**한다. → `git status`, `git log ...` 가 `TerminalExecutor` 로 실행됨.
- **동시에** `extract_code_from_response()` 가 `powershell` 태그를 인식해 `CodeExecutor` 로 `.ps1` 임시파일을 만들어 실행한다. → 스크립트 본문이 `$ git status\n$ git log ...` 인 .ps1 이 PowerShell 에 의해 파싱되며 **`$ : ... 용어가 cmdlet 으로 인식되지 않습니다`** 에러로 실패.

**결과:** 동일 명령이 두 번 실행되거나, PowerShell 파싱 에러로 코드 경로가 실패하고 Self-Correction 이 호출된다. 토큰 비용과 응답 시간이 모두 낭비된다.

#### 1.1.2 실패 패턴 B — 코드 실행을 `$` 라인으로 표현한 응답

```markdown
[ACT]
$ python -c "print('hello')"
$ python my_script.py
```

**현재 동작:** AI 가 "Python 코드 실행" 을 의도했지만 `RE_SHELL` 이 매칭해 쉘 경로로 실행된다. 워크스페이스에 `python` 이 PATH 에 없거나, `python` 이 `python3` 인 환경(macOS/Linux) 에서는 `FileNotFoundError`. 또한 `CodeExecutor` 의 UTF-8 환경 주입(`PYTHONIOENCODING`, `PYTHONUTF8=1`, `LC_ALL=C.UTF-8` — [src/code_executor.py:81-95](src/code_executor.py#L81-L95))이 적용되지 않아 한글/이모지 출력이 깨질 수 있다.

#### 1.1.3 실패 패턴 C — 한 iteration 에 두 경로 혼재

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

**현재 동작:** 세 액션이 각각 다른 경로로 실행된다. `bash` 블록은 Windows 에서 `_build_shell_config()` 에 의해 `powershell` 매핑 — `echo step3` 은 PowerShell cmdlet 으로도 동작하므로 **겉보기엔 성공하지만 의도와 실행 환경이 어긋난다**.

**결과:** AI 가 `[OBSERVE]` 단계에서 "어느 출력이 어디서 나왔는지" 추적이 불가능해 Self-Correction 의 정확도가 떨어진다.

#### 1.1.4 실패 패턴 D — 위험 명령을 코드 블록으로 우회 (보안 누수)

````markdown
[ACT]
```powershell
Remove-Item -Recurse -Force .\build
```
````

**현재 동작:**
- `_run_shell_lines()` 는 `DANGEROUS_COMMANDS` 를 검사해 단건 승인 프롬프트를 띄운다. ([src/agent_runner.py:648-674](src/agent_runner.py#L648-L674))
- 그러나 `_run_code_blocks()` 는 **위험 명령 검사를 하지 않는다**. `extract_code_from_response()` 가 `powershell` 태그를 잡으면 .ps1 임시파일에 `Remove-Item ...` 가 그대로 들어가 **승인 절차 없이 실행**된다.

**결과:** 의도하지 않은 Bypass 경로가 존재하며, 이는 FSD v1.0.100 의 위험-액션 한도 검사(`bypass_max_dangerous`) 도 우회한다.

### 1.2 근본 원인 분석

| # | 원인 | 위치 |
|---|---|---|
| R1 | 프롬프트가 추상적 — 한 줄 정의만 있고 **금지/긍정 예시 부재** | [src/agent_runner.py:454-458](src/agent_runner.py#L454-L458) |
| R2 | `RE_SHELL` 이 코드 블록 내부 `$` 도 매칭 (`re.MULTILINE` 만 적용, 펜스 인식 없음) | [src/agent_runner.py:89](src/agent_runner.py#L89) |
| R3 | `CodeExecutor.SUPPORTED_LANGUAGES` 에 쉘 계열(`bash/sh/shell/powershell/ps1`) 5개가 포함되어 두 경로 범위가 겹침 | [src/code_executor.py:38, 70-73](src/code_executor.py#L70-L73) |
| R4 | `_execute_actions()` 가 동일 `act_text` 를 세 함수에 그대로 흘려 **중복 매칭 가능** | [src/agent_runner.py:562-571](src/agent_runner.py#L562-L571) |
| R5 | 위험 명령 검증이 쉘 경로에만 존재 — 코드 경로는 무방비 | [src/agent_runner.py:647-674](src/agent_runner.py#L647-L674) |
| R6 | `get_os_shell_hint()` 가 `platform.system()` 만 보고 PowerShell/CMD 구분 누락. `TerminalExecutor.get_shell_type()` 와 분기 기준 불일치 | [src/os_utils.py:7-20](src/os_utils.py#L7-L20), [src/terminal_executor.py:103-118](src/terminal_executor.py#L103-L118) |
| R7 | 시스템 프롬프트에 `TerminalExecutor.shell_help()` 의 "안전/위험 명령 목록" 이 노출되지 않아 AI 가 실행 가능한 명령을 추정해야 함 | [src/agent_runner.py:474](src/agent_runner.py#L474) |

### 1.3 목표 — 두 갈래 접근

본 문서는 **반응적 차단(v1.0.106 제안)** 대신 **사전 명확화 + 사후 자동 교정** 의 **이중 방어선** 을 채택한다.

```
                          ┌────────────────────────────┐
                          │ AI 모델의 [ACT] 응답         │
                          └────────────┬───────────────┘
                                       │
                       ┌───── 방어선 1: Prompt ─────┐
                       │  (사전 차단)                │
                       │  · 명확한 정의 + 예시      │
                       │  · 금지 패턴 4종 명시      │
                       │  · 쉘 환경 요약 노출       │
                       └────────────┬───────────────┘
                                    │  (실패 시)
                       ┌───── 방어선 2: Dispatcher ─┐
                       │  (사후 자동 교정)          │
                       │  · 의도 분류기            │
                       │  · 단일 경로 매핑          │
                       │  · 통합 위험 명령 검사      │
                       └────────────┬───────────────┘
                                    ▼
                          ┌────────────────────────────┐
                          │ FileWriter / CodeExecutor / │
                          │ TerminalExecutor            │
                          └────────────────────────────┘
```

| 목표 | 구체 내용 |
|---|---|
| G1 | **프롬프트 재작성** — 정의·실행 경로·긍정/부정 예시를 모두 포함. AI 모델이 한 번 읽고 두 경로를 구분 가능하도록 작성. |
| G2 | **쉘 환경 요약 주입** — `TerminalExecutor.agent_shell_brief()` (신규) 가 현 쉘 타입의 안전 명령 9개 + 위험 명령 목록을 반환. 시스템 프롬프트에 상시 포함. |
| G3 | **지능형 디스패처** — AI 가 두 경로를 혼동해도 **결정론적으로 단 한 경로** 로만 실행. 쉘 코드 블록 안의 `$` 라인은 쉘 경로로, 다중라인 스크립트는 그대로 .ps1/.sh 로, 단순 파이썬 -c 는 그대로 쉘로. |
| G4 | **이중 실행 방지** — 같은 텍스트가 두 경로에 매칭되지 않도록 펜스 블록을 사전 추출. |
| G5 | **위험 명령 검사 일원화** — 코드 경로의 쉘 계열 블록도 `DANGEROUS_COMMANDS` 검사를 거친다. Bypass 모드의 누적 한도(`bypass_dangerous_count`) 도 동일 적용. |
| G6 | **명시적 액션 태그(opt-in)** — AI 가 더욱 결정론적으로 의도를 표현할 수 있도록 `[ACTION:file]`, `[ACTION:code]`, `[ACTION:shell]` 태그를 옵션으로 도입. 미사용 시 기존 휴리스틱 동작. |
| G7 | **테스트 확대** — 실패 패턴 A/B/C/D 를 포함한 17 가지 케이스로 단위 테스트. |

### 1.4 범위

| 항목 | 포함 | 위치 |
|---|---|---|
| `_build_system_prompt()` 재작성 (G1) | ✅ | § 3 |
| `TerminalExecutor.agent_shell_brief()` 신규 (G2) | ✅ | § 4.1 |
| `os_utils.get_os_shell_hint()` 4-쉘 분기로 개선 | ✅ | § 4.2 |
| `AgentActionDispatcher` 신규 모듈 (G3, G4) | ✅ | § 5 |
| `_execute_actions()` 가 디스패처 경유로 변경 | ✅ | § 5.4 |
| 코드 경로 위험 명령 검사 (G5) | ✅ | § 5.3 |
| `[ACTION:*]` 태그 opt-in (G6) | ✅ | § 6 |
| 단위 테스트 17건 (G7) | ✅ | § 8 |
| `CodeExecutor.SUPPORTED_LANGUAGES` 변경 | ❌ | `/run` 호환 — 범위 외 |
| `ResponseParser.parse_and_save()` 변경 | ❌ | 범위 외 |
| 에이전트 루프 종료/재개 로직 변경 | ❌ | 범위 외 |

> **v1.0.106 와의 관계:** v1.0.106 은 "쉘 계열 코드 블록을 거부하고 Self-Correction 으로 다음 iteration 에 교정하도록 유도" 하는 **strict-reject** 접근이다. 본 문서(v1.0.107) 는 **거부 대신 자동 분류**를 채택해 (a) iteration 낭비 제거, (b) AI 모델 별 응답 스타일 차이에 더 강건, (c) 동일한 안전 보장(위험 명령 일원 검사) 을 달성한다. v1.0.106 의 프롬프트 설계는 본 문서 § 3 으로 흡수·확장된다.

---

## 2. 현황 분석

### 2.1 현 시스템 프롬프트 — [src/agent_runner.py:443-475](src/agent_runner.py#L443-L475)

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

| # | 문제 | 본 문서 대응 |
|---|---|---|
| P1 | "코드 실행" 의 예시에 `powershell` / `bash` 가 포함되어 있어 AI 가 **"쉘 스크립트 = 코드 실행"** 으로 학습 | § 3.5 — `python` / `javascript` 만 코드 실행으로 명시. 쉘은 § 선택지 C 로 분리 |
| P2 | **금지 예시 0건** — 무엇이 잘못된 패턴인지 학습 불가 | § 3.6 — 4가지 금지 패턴 + 이유 |
| P3 | 현재 OS 만 언급, **쉘 타입(PowerShell vs CMD vs Bash) 미명시** | § 3.4 — `get_shell_type()` 결과 명시 |
| P4 | 안전/위험 명령 목록 미노출 → AI 가 추정으로 명령 작성 | § 3.7 — `agent_shell_brief()` 삽입 |

### 2.2 현 파서 — `RE_SHELL` 의 펜스 미인식

```python
# src/agent_runner.py:89
RE_SHELL = re.compile(r"^\s*\$\s+(.+)$", re.MULTILINE)
```

`re.MULTILINE` 만 사용 → 코드 펜스 안의 `$` 라인을 구분하지 못함.

### 2.3 현 코드 실행기 — 쉘 계열 언어 매핑

```python
# src/code_executor.py
_SHELL_LANG_KEYS = ('bash', 'sh', 'shell', 'powershell', 'ps1')
SUPPORTED_LANGUAGES = {
    **_BASE_LANGUAGES,    # python, py, javascript, js
    **{key: shell_cfg for key in _SHELL_LANG_KEYS},   # ← 5개 모두 매핑
}
```

쉘 계열 5개가 임시 .ps1/.sh 파일로 실행된다. `extract_code_from_response()` 도 이를 그대로 코드 블록으로 추출.

### 2.4 현 실행 흐름 — `_execute_actions()`

```python
# src/agent_runner.py:562-571
def _execute_actions(self, session, act_text):
    if not act_text:
        return []
    results = []
    results += self._save_file_blocks(session, act_text)
    results += self._run_code_blocks(act_text)
    results += self._run_shell_lines(session, act_text)
    return results
```

세 함수가 **동일한 act_text** 를 독립적으로 훑는다.

### 2.5 위험 명령 검사 위치

- `_run_shell_lines()` → `terminal_executor.DANGEROUS_COMMANDS` 검사 + `bypass_dangerous_count` 누적 ([src/agent_runner.py:647-660](src/agent_runner.py#L647-L660))
- `_run_code_blocks()` → 검사 없음

### 2.6 OS 힌트 분기 불일치

| 함수 | 분기 기준 | 결과 종류 |
|---|---|---|
| `os_utils.get_os_shell_hint()` | `platform.system()` | "Windows" / "기타" 2분기 |
| `TerminalExecutor.get_shell_type()` | `platform.system()` + `PSModulePath` | "Windows PowerShell" / "Windows CMD" / "Mac" / "Linux" 4분기 |

→ 같은 환경을 두 함수가 다른 단위로 보고 있다.

---

## 3. 설계 — 새 시스템 프롬프트 (방어선 1)

### 3.1 설계 원칙

| 원칙 | 설명 |
|---|---|
| **결정론** | AI 가 텍스트를 작성하는 순간에 **어떤 파서가 매칭할지 예측 가능** 해야 한다. |
| **단일 경로** | 한 액션 텍스트는 **오직 한 파서**에만 매칭된다. (디스패처가 보장) |
| **구체 예시 우선** | 규칙 나열 대신 ✅/❌ 예시 쌍을 먼저 제시. |
| **쉘 환경 명시** | `get_shell_type()` 결과·안전 명령·위험 명령을 프롬프트에 노출. |
| **관용성** | 프롬프트가 강하게 안내하되, **혼동된 응답도 디스패처가 받아주는** 안전망. AI 의 자기 표현 다양성을 허용. |

### 3.2 프롬프트 전체 스켈레톤

```text
당신은 자율 코딩 에이전트입니다. 주어진 상위 목표를 달성하기 위해
스스로 계획을 세우고 단계별로 실행합니다.

[실행 환경]
{os_hint_block}        ← § 4.2 의 4-쉘 분기 결과

[응답 형식 — 반드시 준수]

첫 번째 응답(계획 수립) 은 번호 매긴 목록으로 전체 PLAN 을 나열하세요.
이후 매 반복(iteration) 응답은 다음 세 블록을 이 순서대로 포함해야 합니다.

[REASON]
3줄 이내. 직전 [OBSERVE] 인용 + 이번 단계 의도.

[ACT]
아래 세 선택지 중 1~3 개를 골라 순서대로 작성하세요.

== 선택지 A. 파일 생성/수정 ==
  ```filename:<상대경로>
  ... 파일 전문 ...
  ```
  • 한 블록에 한 파일. 워크스페이스 상대경로.
  • 줄바꿈·인코딩은 원본 그대로. 주석·언어 태그를 섞지 마세요.

== 선택지 B. 코드 실행 (임시 실행 — 파일 저장 없음) ==
  ```python
  print("hello")
  ```
  ```javascript
  console.log("hi")
  ```
  • 언어 태그는 정확히 `python` / `javascript` 두 가지만 사용하세요.
  • 타임아웃 30초 · 워크스페이스에서 실행 · 입출력 UTF-8 자동 강제.
  • ⚠️ `bash` / `sh` / `shell` / `powershell` / `ps1` 태그는 쉘 명령 실행으로 자동 라우팅됩니다 (선택지 C 동일 처리).

== 선택지 C. 쉘 명령 실행 ==
  라인 시작에 `$ <명령>` — 코드 블록으로 감싸지 마세요.
    $ git status
    $ python --version
  • 한 줄에 한 명령. 파이프(|)·리다이렉트(>)·`&&` 는 한 줄 안에서 허용.
  • 명령은 {shell_type} 구문을 사용하세요.
  • (선택) 명시적 의도 표시: `[ACTION:shell]` 태그 사용 시 해당 블록은 무조건 쉘로 라우팅.

[OBSERVE]
위 ACT 의 기대 결과를 1~3 줄 서술. (실제 결과는 시스템이 다음 프롬프트에 주입)

[완료 판정]
목표 달성 시 응답 맨 끝에 정확히: {done_token}

[Self-Correction]
오류 시 다음 [REASON] 에서 진단 + [ACT] 에서 교정.

[❌ 금지 패턴 — AI 가 자주 저지르는 실수]

1) 쉘 명령을 코드 블록으로 감싸기
   ```powershell
   $ git status              ← `$` 접두사가 펜스 안에 있으면 시스템이
   $ git log --oneline -5    ← "쉘 의도" 로 인식해 쉘 경로로 보냅니다.
   ```
   → 가능하면 코드 블록 없이 다음 형식을 쓰세요:
       $ git status
       $ git log --oneline -5

2) 같은 명령을 두 경로에 중복 작성
   ```powershell
   git status
   ```
   $ git status              ← 디스패처가 중복을 감지해 **하나만 실행** 합니다.
                              그래도 노이즈 발생 — 둘 중 하나만 쓰세요.

3) 여러 줄 파이썬 로직을 $ 한 줄로
   $ python -c "import os; ..."   ← 짧으면 OK. 그러나 여러 줄이면
                                    선택지 B (```python 블록) 로 작성하세요.

4) 위험 명령을 코드 블록으로 숨기기
   ```powershell
   Remove-Item -Recurse -Force .\build
   ```
   → 시스템은 이 경우에도 **단일 경로(쉘) 로 라우팅 + 위험 명령 승인 프롬프트**
      를 띄웁니다. (v1.0.107 부터 일원화)

{shell_brief_block}      ← § 4.1 의 agent_shell_brief() 결과

[주의]
- 코드 블록 밖에서 장황하게 설명하지 마세요.
- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.
- 위험 명령은 반드시 필요한 경우에만 사용하세요. 사용자가 거부할 수 있습니다.
- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.
- 의도가 명확하지 않은 경우 `[ACTION:shell]` / `[ACTION:code]` / `[ACTION:file]`
  태그를 ACT 블록 첫 줄에 추가해 명시할 수 있습니다.
```

### 3.3 프롬프트 핵심 차이점 (vs 현행)

| 섹션 | 현행 | v1.0.107 |
|---|---|---|
| `[실행 환경]` | OS 만 1줄 | 쉘 타입(4분기) + 인코딩 |
| `[ACT]` 정의 | 한 줄씩 3개 | 선택지 A/B/C 로 명시적 분할 + 각 선택지에 정의·예시·주의 |
| 코드 실행 언어 | `python/bash/javascript` | `python/javascript` 만, 쉘 태그는 자동 쉘 라우팅 안내 |
| 금지 패턴 | 없음 | 4종 + 각각의 자동 처리 결과 안내 |
| 쉘 환경 요약 | 없음 | `agent_shell_brief()` 삽입 |
| 명시적 태그 | 없음 | `[ACTION:*]` opt-in 안내 |

### 3.4 `_build_system_prompt()` 재작성

```python
# src/agent_runner.py

def _build_system_prompt(self) -> str:
    from .terminal_executor import TerminalExecutor

    shell_type = TerminalExecutor.get_shell_type()
    shell_brief = TerminalExecutor.agent_shell_brief()
    os_hint = get_os_shell_hint()

    return (
        "당신은 자율 코딩 에이전트입니다. 주어진 상위 목표를 달성하기 위해\n"
        "스스로 계획을 세우고 단계별로 실행합니다.\n\n"

        f"[실행 환경]\n{os_hint}\n\n"

        "[응답 형식 — 반드시 준수]\n"
        "첫 번째 응답(계획 수립)은 번호 매긴 목록으로 전체 PLAN 을 나열하세요.\n"
        "이후 매 반복(iteration) 응답은 다음 세 블록을 순서대로 포함해야 합니다.\n\n"

        "[REASON]\n"
        "3줄 이내. 직전 [OBSERVE] 인용 + 이번 단계 의도.\n\n"

        "[ACT]\n"
        "아래 세 선택지 중 1~3 개를 골라 순서대로 작성하세요.\n\n"

        "== 선택지 A. 파일 생성/수정 ==\n"
        "  ```filename:<상대경로>\n"
        "  ... 파일 전문 ...\n"
        "  ```\n"
        "  • 한 블록에 한 파일. 워크스페이스 상대경로.\n"
        "  • 줄바꿈·인코딩 원본 그대로. 언어 태그를 섞지 마세요.\n\n"

        "== 선택지 B. 코드 실행 (임시 실행 — 파일 저장 없음) ==\n"
        "  ```python\n"
        "  print(\"hello\")\n"
        "  ```\n"
        "  • 언어 태그는 정확히 `python` / `javascript` 두 가지만 사용.\n"
        "  • 타임아웃 30초 · 워크스페이스 cwd · UTF-8 자동 강제.\n"
        "  • ⚠️ `bash`/`sh`/`shell`/`powershell`/`ps1` 태그는 쉘로 자동 라우팅됩니다.\n\n"

        "== 선택지 C. 쉘 명령 실행 ==\n"
        "  라인 시작에 `$ <명령>` — 코드 블록으로 감싸지 마세요.\n"
        "    $ git status\n"
        "    $ python --version\n"
        "  • 한 줄에 한 명령. 파이프(|)·리다이렉트(>)·`&&` 는 한 줄 내 허용.\n"
        f"  • 명령은 {shell_type} 구문을 사용하세요.\n"
        "  • (선택) 명시 라우팅: `[ACTION:shell]` 태그.\n\n"

        "[OBSERVE]\n"
        "기대 결과 1~3줄. (실제 결과는 시스템이 다음 프롬프트에 주입)\n\n"

        "[완료 판정]\n"
        f"목표 달성 시 응답 맨 끝에 정확히: {self.done_token}\n\n"

        "[Self-Correction]\n"
        "오류 시 다음 [REASON] 에서 원인 진단 + [ACT] 에서 교정.\n\n"

        "[❌ 금지 패턴 — AI 가 자주 저지르는 실수]\n\n"

        "1) 쉘 명령을 코드 블록으로 감싸기\n"
        "   ```powershell\n"
        "   $ git status\n"
        "   ```\n"
        "   → 시스템이 \"쉘 의도\" 로 인식해 쉘 경로로 라우팅합니다.\n"
        "      가능하면 코드 블록 없이 `$ git status` 형태로 작성하세요.\n\n"

        "2) 같은 명령 중복 작성\n"
        "   디스패처가 중복을 감지해 1회만 실행하지만 노이즈 발생.\n\n"

        "3) 여러 줄 파이썬 로직을 $ 한 줄로\n"
        "   짧은 -c 는 OK. 여러 줄이면 선택지 B 사용.\n\n"

        "4) 위험 명령을 코드 블록으로 숨기기\n"
        "   v1.0.107 부터 코드 경로의 쉘 블록도 동일한 위험 명령 검사를\n"
        "   거칩니다. 승인 프롬프트가 표시됩니다.\n\n"

        f"{shell_brief}\n\n"

        "[주의]\n"
        "- 코드 블록 밖에서 장황하게 설명하지 마세요.\n"
        "- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.\n"
        "- 의도가 모호하면 `[ACTION:file]` / `[ACTION:code]` / `[ACTION:shell]` "
        "태그를 ACT 첫 줄에 추가해 명시할 수 있습니다.\n"
        "- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.\n"
    )
```

### 3.5 설계 트레이드오프

| 선택 | 채택안 | 기각안 | 이유 |
|---|---|---|---|
| 쉘 코드 블록 처리 | **자동 쉘 라우팅(디스패처)** | strict-reject (v1.0.106) | iteration 낭비 제거, 모델별 다양성 허용 |
| 코드 언어 태그 노출 | `python`/`javascript` 만 | 쉘 5종 포함 | 의도 분리. 단, `CodeExecutor.SUPPORTED_LANGUAGES` 자체는 불변 (`/run` 호환) |
| 위험 명령 검사 | 쉘+코드 일원화 | 쉘만 (현행 유지) | 보안 원칙: 검사 누락 경로 = 우회 경로 |
| 명시적 태그 | opt-in `[ACTION:*]` | mandatory 태그 강제 | 후방 호환성 + 토큰 절감 |
| 프롬프트 길이 | +800 ~ +1200 토큰 | 현행 유지 | Self-Correction 호출 감소로 총 토큰 감소 기대 |

---

## 4. 설계 — 보조 컴포넌트

### 4.1 `TerminalExecutor.agent_shell_brief()` — 신규

`shell_help()` 는 `/shell <cmd>` 형식이라 에이전트 프롬프트에 부적합. 에이전트가 실제로 작성하는 `$ <cmd>` 형식의 압축 요약을 새로 추가한다.

```python
# src/terminal_executor.py

@staticmethod
def agent_shell_brief() -> str:
    """에이전트 시스템 프롬프트 삽입용 현 쉘 환경 요약.

    `shell_help()` 의 `/shell <cmd>` 포맷 대신 에이전트가 실제 생성하는
    `$ <cmd>` 포맷으로 안전 명령 예시 9개와 위험 명령 목록을 제공한다.
    """
    shell_type = TerminalExecutor.get_shell_type()
    dangerous = sorted(TerminalExecutor._get_dangerous_for_shell(shell_type))

    if shell_type == 'Windows PowerShell':
        safe_examples = [
            "$ Get-ChildItem                 # 파일 목록",
            "$ Get-Content <file>            # 파일 내용",
            "$ Get-Location                  # 현재 경로",
            "$ Test-Path <path>              # 경로 존재 여부",
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
            "$ find /i \"text\" <file>        # 텍스트 검색",
            "$ python --version",
            "$ pip list",
            "$ git status",
            "$ git log --oneline -10",
            "$ tasklist",
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
            "$ git log --oneline -10",
            "$ sw_vers",
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
            "$ git log --oneline -10",
            "$ uname -a",
        ]

    lines = [
        f"[쉘 환경 요약 — 현재 쉘: {shell_type}]",
        "",
        "안전 명령 예시 (선택지 C — `$ <cmd>` 형식):",
        *[f"  {ex}" for ex in safe_examples],
        "",
        "위험 명령 (실행 전 승인 프롬프트 표시 · 코드 블록 안에서도 동일 적용):",
        f"  {', '.join(dangerous)}",
    ]
    return "\n".join(lines)
```

### 4.2 `os_utils.get_os_shell_hint()` — 4-쉘 분기로 개선

```python
# src/os_utils.py
"""os_utils - 플랫폼별 유틸리티 함수 (FSD v1.0.088 / v1.0.107)"""


def get_os_shell_hint() -> str:
    """현재 OS/쉘 타입을 기반으로 쉘 구문 힌트를 반환.

    `TerminalExecutor.get_shell_type()` 로 4쉘 분기 (Windows PowerShell /
    Windows CMD / Linux / Mac). 순환 import 방지를 위해 함수 내부 import.
    """
    from .terminal_executor import TerminalExecutor

    shell_type = TerminalExecutor.get_shell_type()
    if shell_type == 'Windows PowerShell':
        return (
            "OS          : Windows\n"
            "쉘 타입     : Windows PowerShell\n"
            "파일 인코딩 : UTF-8\n"
            "쉘 명령은 PowerShell 구문을 사용하세요. "
            "`bash`/`sh` 구문은 이 환경에서 실행되지 않습니다."
        )
    if shell_type == 'Windows CMD':
        return (
            "OS          : Windows\n"
            "쉘 타입     : Windows CMD\n"
            "파일 인코딩 : UTF-8\n"
            "쉘 명령은 CMD 구문을 사용하세요. "
            "`bash`/`sh` 구문은 이 환경에서 실행되지 않습니다."
        )
    if shell_type == 'Mac':
        return (
            "OS          : macOS\n"
            "쉘 타입     : Bash/Zsh\n"
            "파일 인코딩 : UTF-8\n"
            "쉘 명령은 bash/zsh 구문을 사용하세요."
        )
    return (
        "OS          : Linux\n"
        "쉘 타입     : Bash\n"
        "파일 인코딩 : UTF-8\n"
        "쉘 명령은 bash 구문을 사용하세요."
    )
```

> **순환 import 점검:** `terminal_executor.py` 는 `os_utils` 를 import 하지 않는다(grep 으로 확인 가능). 함수 내부 import 로 모듈 로딩 순서에도 안전.

> **호환성:** 시그니처(`get_os_shell_hint() -> str`) 불변. FSD v1.0.088, v1.0.104 의 호출자(`AgentRunner._build_system_prompt`, `TerminalExecutor._execute_command_safely`) 모두 변경 없이 동작.

---

## 5. 설계 — 지능형 디스패처 (방어선 2)

### 5.1 책임 분리

기존 `_save_file_blocks` / `_run_code_blocks` / `_run_shell_lines` 가 각자 `act_text` 를 훑던 구조를 폐기하고, **단일 진입점 `AgentActionDispatcher`** 가 다음 순서로 처리한다.

```
act_text
   │
   ▼
[1] 명시 태그 우선 처리
    [ACTION:file] / [ACTION:code] / [ACTION:shell] 블록 분리
   │
   ▼
[2] 펜스 블록 추출 (```...```)
    · ```filename:...```         → file action
    · ```python|js```             → code action (CodeExecutor)
    · ```bash|sh|shell|powershell|ps1``` → shell-block 분류기로
   │
   ▼
[3] 쉘-블록 분류기 (§ 5.2)
    각 쉘 코드 블록 내용을 분석:
    · 모든 라인이 단일 명령 → shell action 들로 분해 (각 라인별)
    · 다중라인 스크립트(if/for/function) → script action (CodeExecutor 그대로)
   │
   ▼
[4] 펜스 외부 `$` 라인 추출
    펜스를 공백으로 치환한 텍스트에서 RE_SHELL 매칭 → shell actions
   │
   ▼
[5] 정렬 & 중복 제거 (§ 5.3)
    file → code → shell 순. 같은 cmd 가 두 번 나오면 1회로 dedupe
   │
   ▼
[6] 위험 명령 검사 (§ 5.3)
    shell action 의 base_cmd 가 DANGEROUS_COMMANDS ∈ ?
    · approval → execute / skip
   │
   ▼
[7] 실행 (FileWriter / CodeExecutor / TerminalExecutor)
```

### 5.2 쉘-블록 분류기

쉘 코드 블록을 **단일-명령 시퀀스 vs 스크립트** 로 분류하는 휴리스틱. 단일-명령 시퀀스로 판정되면 라인 단위로 `TerminalExecutor` 에 보낸다 (펜스를 한 번에 .ps1/.sh 로 만들지 않음 → "AI 가 모르고 코드 블록으로 감쌌어도 정상 실행").

**휴리스틱 규칙:**

```python
SCRIPT_INDICATORS = (
    # PowerShell 스크립트 키워드 (라인 시작)
    r"^\s*(function|param|if|elseif|else|switch|foreach|for|while|do|try|catch|finally)\b",
    # Bash 스크립트 키워드
    r"^\s*(if|then|elif|else|fi|case|esac|for|while|do|done|until|function|export|local|read)\b",
    # 변수 할당 (PowerShell `$x = ...` / Bash `x=...`)
    r"^\s*\$?\w+\s*=",
    # 함수 정의 (Bash `name() { ... }`)
    r"^\s*\w+\s*\(\)\s*\{",
    # 멀티라인 백슬래시 연결
    r"\\\s*$",
    # 연속된 공백/들여쓰기 (스크립트 블록 본문 시그널)
)


def classify_shell_block(code: str) -> str:
    """쉘 코드 블록을 'commands' (라인별 분해) | 'script' (그대로 실행) 로 분류."""
    lines = [l for l in code.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return 'commands'  # 빈 블록 — 무시
    for line in lines:
        for pat in SCRIPT_INDICATORS:
            if re.search(pat, line):
                return 'script'
    return 'commands'
```

**예시:**

| 입력 코드 블록 | 분류 | 처리 |
|---|---|---|
| ```` ```powershell\n$ git status\n$ git log\n``` ```` | `commands` | 각 라인 → `TerminalExecutor.execute()` (`$` 접두사 strip) |
| ```` ```powershell\nGet-ChildItem\nGet-Location\n``` ```` | `commands` | 각 라인 → `TerminalExecutor.execute()` |
| ```` ```bash\nfor f in *.py; do echo $f; done\n``` ```` | `script` | 그대로 `CodeExecutor.execute(code, 'bash')` |
| ```` ```powershell\nfunction Foo { ... }\nFoo\n``` ```` | `script` | 그대로 `CodeExecutor.execute(code, 'powershell')` |

> **`$` 접두사 처리:** 라인이 `$ git status` 형태이면 첫 `$ ` 토큰을 제거한 뒤 `git status` 만 실행에 사용한다. ($ 가 PowerShell 변수와 충돌하지 않게)

### 5.3 위험 명령 검사 일원화

`AgentActionDispatcher` 가 모든 shell-typed action(쉘-블록의 `commands` 분해 결과 + 펜스 외부 `$` 라인) 에 대해 동일한 검사를 수행한다.

```python
# src/agent_action_dispatcher.py 의 의사 코드

def _check_and_run_shell_action(self, session, cmd):
    base = cmd.split()[0].lower() if cmd.split() else ""
    dangerous = base in self.terminal_executor.DANGEROUS_COMMANDS

    if dangerous:
        if session.bypass_approvals:
            session.bypass_dangerous_count += 1
            if session.bypass_dangerous_count > self.bypass_max_dangerous:
                raise _BypassAbort(f"위험 명령 누적 한도 초과: '{cmd}'")
        if dangerous and not session.auto_approve_dangerous_shell:
            if not self._approve_dangerous(session, ...):
                return ActionResult(kind="shell", target=cmd, success=False,
                                    detail="사용자 거부")

    result = self.terminal_executor.execute(cmd, allow_unsafe=dangerous)
    ...
```

**핵심:** 쉘 코드 블록에서 분해된 `Remove-Item ...` 도 동일한 승인 플로우를 거친다. 실패 패턴 D 의 우회 경로가 폐쇄됨.

### 5.4 `AgentActionDispatcher` 인터페이스

```python
# src/agent_action_dispatcher.py
"""
AgentActionDispatcher (FSD v1.0.107)

[ACT] 블록을 분석해 단일 경로로만 실행되도록 라우팅한다.
- 쉘 계열 코드 블록의 `$ ...` 라인은 쉘로 자동 라우팅
- 다중라인 스크립트는 CodeExecutor 로 라우팅
- 위험 명령 검사는 모든 shell action 에 일원 적용
- `[ACTION:*]` 명시 태그가 있으면 우선 적용
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .agent_runner import ActionResult     # 재사용


@dataclass
class _ParsedAction:
    kind: str         # "file" | "code" | "shell" | "script"
    payload: str      # 원본 텍스트 / 라인
    lang: Optional[str] = None
    filepath: Optional[str] = None
    explicit_tag: bool = False    # [ACTION:*] 로 명시되었는지


class AgentActionDispatcher:

    RE_FENCE = re.compile(r"^[ \t]*```([^\n]*)\n(.*?)\n[ \t]*```", re.MULTILINE | re.DOTALL)
    RE_SHELL_LINE = re.compile(r"^\s*\$\s+(.+)$", re.MULTILINE)
    RE_ACTION_TAG = re.compile(r"^\s*\[ACTION:(file|code|shell)\]\s*$", re.MULTILINE)

    SHELL_LANGS = {"bash", "sh", "shell", "powershell", "ps1"}
    CODE_LANGS  = {"python", "py", "javascript", "js"}

    # 쉘 스크립트(라인 분해 금지) 시그널
    SCRIPT_INDICATORS = [
        re.compile(r"^\s*(function|param|if|elseif|else|switch|foreach|for|while|do|try|catch|finally)\b", re.IGNORECASE),
        re.compile(r"^\s*(then|elif|fi|case|esac|done|until|export|local|read)\b"),
        re.compile(r"^\s*\$?[\w\.]+\s*="),
        re.compile(r"^\s*\w+\s*\(\)\s*\{"),
        re.compile(r"\\\s*$"),
    ]

    def __init__(self, runner):
        # AgentRunner 참조 — 위험 명령 / 승인 플로우 재사용
        self._runner = runner

    # ─── 진입 ──────────────────────────────────────────────────
    def dispatch(self, session, act_text: str) -> List[ActionResult]:
        if not act_text:
            return []

        actions = self._parse(act_text)
        actions = self._dedupe(actions)

        results: List[ActionResult] = []
        for a in actions:
            if a.kind == "file":
                results += self._exec_file(session, a)
            elif a.kind == "code":
                results.append(self._exec_code(a))
            elif a.kind == "script":
                results.append(self._exec_script(a))
            elif a.kind == "shell":
                results.append(self._exec_shell(session, a))
        return results

    # ─── 파싱 ──────────────────────────────────────────────────
    def _parse(self, act_text: str) -> List[_ParsedAction]:
        # (단순화된 로직 — 실제 구현은 펜스를 인덱스 기반으로 추출해 외부 텍스트 분리)
        ...

    def _classify_shell_block(self, code: str) -> str:
        meaningful = [l for l in code.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not meaningful:
            return "commands"
        for line in meaningful:
            for pat in self.SCRIPT_INDICATORS:
                if pat.search(line):
                    return "script"
        return "commands"

    def _strip_dollar(self, line: str) -> str:
        m = self.RE_SHELL_LINE.match(line.rstrip("\r\n"))
        return m.group(1).strip() if m else line.strip()

    # ─── 중복 제거 ─────────────────────────────────────────────
    def _dedupe(self, actions: List[_ParsedAction]) -> List[_ParsedAction]:
        """같은 (kind, payload) 가 연속되면 1회로 축약. file/code 는 유지."""
        seen = set()
        out = []
        for a in actions:
            if a.kind == "shell":
                key = ("shell", a.payload.strip())
                if key in seen:
                    continue
                seen.add(key)
            out.append(a)
        return out

    # ─── 실행 어댑터 (AgentRunner 의 기존 로직 재사용) ────────
    def _exec_file(self, session, a: _ParsedAction) -> List[ActionResult]:
        fake = f"```filename:{a.filepath}\n{a.payload}\n```"
        return self._runner._save_file_blocks(session, fake)

    def _exec_code(self, a: _ParsedAction) -> ActionResult:
        result = self._runner.code_executor.execute(a.payload, a.lang)
        return self._runner._format_code_action_result(a.lang, result)

    def _exec_script(self, a: _ParsedAction) -> ActionResult:
        # 쉘 스크립트(다중라인) — CodeExecutor 의 .ps1/.sh 경로 그대로 사용
        # 단, 첫 라인의 토큰이 위험 명령이면 승인 플로우를 거침
        first_token = a.payload.strip().split()[0].lower() if a.payload.strip() else ""
        if first_token in self._runner.terminal_executor.DANGEROUS_COMMANDS:
            # § 5.3 의 승인 플로우 호출
            ok = self._runner._approve_dangerous(
                session=...,  # 컨텍스트 주입 (run() 에서 dispatcher 인스턴스 전달)
                flag_attr="auto_approve_dangerous_shell",
                label=f"shell script ({a.lang}) — first cmd: '{first_token}'",
            )
            if not ok:
                return ActionResult(kind="code", target=a.lang,
                                    success=False, detail="사용자 거부 (위험 명령 포함)")
        result = self._runner.code_executor.execute(a.payload, a.lang)
        return self._runner._format_code_action_result(a.lang, result)

    def _exec_shell(self, session, a: _ParsedAction) -> ActionResult:
        return self._runner._exec_single_shell_command(session, a.payload)
```

> **구현 노트:** 위는 인터페이스 골격이며 실제 구현 시 `_parse()` 의 인덱스-기반 펜스 분리 로직을 보완해야 한다. 핵심은 (a) 단일 진입점, (b) 쉘 블록의 `commands` 분기, (c) 위험 명령 검사 일원화 세 가지가 결정론적이라는 것.

### 5.5 `AgentRunner` 변경점

```python
# src/agent_runner.py

from .agent_action_dispatcher import AgentActionDispatcher

class AgentRunner:
    def __init__(self, ...):
        ...
        self._dispatcher = AgentActionDispatcher(self)

    def _execute_actions(self, session, act_text):
        # v1.0.107: 디스패처가 단일 경로로 라우팅
        return self._dispatcher.dispatch(session, act_text)

    # 기존 _run_shell_lines / _run_code_blocks 은 디스패처에서
    # 어댑터(_exec_single_shell_command 등) 로 호출되도록 분해.

    def _exec_single_shell_command(self, session, cmd: str) -> ActionResult:
        """디스패처 전용 — 단일 쉘 명령 실행 + 위험 명령 검사."""
        base = cmd.split()[0].lower() if cmd.split() else ""
        dangerous = base in self.terminal_executor.DANGEROUS_COMMANDS

        if dangerous:
            if session.bypass_approvals:
                session.bypass_dangerous_count += 1
                if session.bypass_dangerous_count > self.bypass_max_dangerous:
                    session.stop_reason = AgentStopReason.BYPASS_DANGEROUS_LIMIT
                    raise _BypassAbort(
                        f"위험 명령 누적 한도 초과 "
                        f"({session.bypass_dangerous_count} > "
                        f"{self.bypass_max_dangerous}): '{cmd}'"
                    )
                print(f"\n⚡ BYPASS: 위험 명령 자동 승인 "
                      f"({session.bypass_dangerous_count}/{self.bypass_max_dangerous})")
            if not session.auto_approve_dangerous_shell:
                if not self._approve_dangerous(
                    session, "auto_approve_dangerous_shell", f"shell '{cmd}'"
                ):
                    return ActionResult(kind="shell", target=cmd, success=False,
                                        detail="사용자 거부")

        print(f"\n▶️  $ {cmd}")
        result = self.terminal_executor.execute(cmd, allow_unsafe=dangerous)
        return self._format_shell_action_result(cmd, result)

    @staticmethod
    def _format_code_action_result(lang: str, result: dict) -> ActionResult:
        success = bool(result.get("success"))
        if success:
            stdout = (result.get("stdout") or "").strip()
            detail = f"returncode=0\n{stdout[:500]}" if stdout else "returncode=0"
        else:
            stderr = (result.get("stderr") or result.get("error") or "").strip()
            rc = result.get("returncode", "?")
            detail = f"returncode={rc}\n{stderr[:500]}"
        return ActionResult(kind="code", target=lang, success=success, detail=detail)

    @staticmethod
    def _format_shell_action_result(cmd: str, result: dict) -> ActionResult:
        success = bool(result.get("success"))
        if success:
            stdout = (result.get("stdout") or "").strip()
            detail = f"returncode=0\n{stdout[:500]}" if stdout else "returncode=0"
        else:
            err = (result.get("stderr") or result.get("error") or "").strip()
            rc = result.get("returncode", "?")
            detail = f"returncode={rc}\n{err[:500]}"
        return ActionResult(kind="shell", target=cmd, success=success, detail=detail)
```

> **호환성:** 기존 외부 인터페이스 (`AgentRunner.run()`, `_call_model()`, `_parse_blocks()`, dataclass 시그니처) 는 모두 불변. 디스패처는 `_execute_actions()` 내부 구현 교체일 뿐.

---

## 6. 명시적 액션 태그 (Opt-in)

### 6.1 형식

```text
[ACT]
[ACTION:shell]
$ git status
$ git log --oneline -5

[ACTION:code]
```python
print("hi")
```

[ACTION:file]
```filename:src/foo.py
def foo(): ...
```
```

### 6.2 우선순위

1. `[ACTION:*]` 태그가 있으면 **그 블록의 모든 텍스트는 명시된 종류로 라우팅**.
2. 태그가 없으면 § 5 의 휴리스틱 적용.
3. 태그와 휴리스틱이 충돌(예: `[ACTION:code]` 안에 `$ git status`) 시 **태그 우선** — `code` 로 처리. 단, `code` 안에서도 쉘 블록 휴리스틱은 적용 (````bash` → `script` or `commands`).

### 6.3 옵션 동작 — env 플래그

```python
# src/agent_runner.py
self.action_tags_required = os.getenv("AGENT_ACTION_TAGS_REQUIRED", "0") == "1"
```

- `0` (기본): 태그 없어도 휴리스틱으로 동작 (현행 호환).
- `1`: 태그 누락 시 디스패처가 휴리스틱 0건으로 처리하고 Self-Correction 유도. 강한 결정론 환경 필요 시 사용.

---

## 7. 파일 변경 예정 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [src/agent_runner.py](src/agent_runner.py) | 수정 | `_build_system_prompt()` 재작성 (§ 3.4), `_execute_actions()` 디스패처 위임, `_exec_single_shell_command()` / `_format_*_action_result()` 추가, `action_tags_required` env |
| [src/agent_action_dispatcher.py](src/agent_action_dispatcher.py) | 신규 | 의도 분류 + 단일 경로 라우팅 (§ 5) |
| [src/terminal_executor.py](src/terminal_executor.py) | 수정 | `agent_shell_brief()` 정적 메서드 추가 (§ 4.1) |
| [src/os_utils.py](src/os_utils.py) | 수정 | `get_os_shell_hint()` 4-쉘 분기 (§ 4.2) |
| [src/code_executor.py](src/code_executor.py) | 변경 없음 | `SUPPORTED_LANGUAGES` 그대로 — `/run` 호환 보장 |
| [tests/test_agent_runner.py](tests/test_agent_runner.py) | 수정 | T-107-01 ~ T-107-06 (프롬프트 구성) |
| [tests/test_agent_action_dispatcher.py](tests/test_agent_action_dispatcher.py) | 신규 | T-107-07 ~ T-107-23 (디스패처 단위 테스트) |
| [tests/test_terminal_executor.py](tests/test_terminal_executor.py) | 수정 | T-107-24 ~ T-107-28 (`agent_shell_brief`) |
| [tests/test_os_utils.py](tests/test_os_utils.py) | 수정 | T-107-29 ~ T-107-32 (4-쉘 분기) |
| [docs/specs/releases/RELEASE_v1.0.107_agents-act-intelligent-dispatcher.md](docs/specs/releases/RELEASE_v1.0.107_agents-act-intelligent-dispatcher.md) | 신규 | 구현 완료 후 작성 |

---

## 8. 요구사항

### 8.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-107-01 | `_build_system_prompt()` 는 상단에 `[실행 환경]` 섹션으로 `TerminalExecutor.get_shell_type()` 결과(쉘 타입)를 명시해야 한다. | 필수 |
| FR-107-02 | `[ACT]` 섹션은 "선택지 A/B/C" 로 명확히 3분할되며, 각 선택지는 정의·실행 경로·예시 1건 이상을 포함한다. | 필수 |
| FR-107-03 | 프롬프트의 선택지 B 는 `python` / `javascript` 만 노출하고, 쉘 계열 언어 태그가 자동 쉘 라우팅됨을 명시해야 한다. | 필수 |
| FR-107-04 | 프롬프트는 `[❌ 금지 패턴]` 섹션에 § 1.1.1~1.1.4 의 4 패턴별 안내를 포함한다. | 필수 |
| FR-107-05 | 프롬프트는 `TerminalExecutor.agent_shell_brief()` 의 반환값을 포함해 현 쉘의 안전 9개·위험 명령 목록을 노출한다. | 필수 |
| FR-107-06 | `AgentActionDispatcher.dispatch()` 는 동일 텍스트가 file/code/shell 두 경로에 매칭되지 않도록 보장한다. | 필수 |
| FR-107-07 | 쉘 계열 코드 블록(`bash`/`sh`/`shell`/`powershell`/`ps1`) 은 분류기로 `commands` vs `script` 로 나뉘어, 전자는 라인별 `TerminalExecutor` 로, 후자는 `CodeExecutor` 로 라우팅된다. | 필수 |
| FR-107-08 | 쉘 라인의 `$ ` 접두사는 디스패처가 strip 후 `TerminalExecutor` 에 전달한다. | 필수 |
| FR-107-09 | 모든 shell-typed action(`commands` 분해 결과 + 펜스 외부 `$` 라인 + `script` 첫 토큰) 은 `DANGEROUS_COMMANDS` 검사를 거친다. | 필수 |
| FR-107-10 | Bypass 모드의 `bypass_dangerous_count` 누적은 디스패처의 위험 명령 검사에서도 동일 적용된다. | 필수 |
| FR-107-11 | `[ACTION:file]` / `[ACTION:code]` / `[ACTION:shell]` 태그는 그 블록의 라우팅을 강제한다 (휴리스틱 우선). | 필수 |
| FR-107-12 | `AGENT_ACTION_TAGS_REQUIRED=1` env 시 태그 없는 ACT 는 디스패처가 처리하지 않고 Self-Correction 유도. | 권장 |
| FR-107-13 | `TerminalExecutor.agent_shell_brief()` 는 4 쉘 타입별로 서로 다른 안전 9개 / 위험 목록을 반환한다. | 필수 |
| FR-107-14 | `os_utils.get_os_shell_hint()` 는 Windows PowerShell / Windows CMD / Linux / Mac 4분기 결과를 반환한다. | 필수 |
| FR-107-15 | `os_utils.get_os_shell_hint()` 의 시그니처(`() -> str`) 는 불변. FSD v1.0.088 / v1.0.104 호출자 모두 무수정 호환. | 필수 |
| FR-107-16 | 디스패처는 동일 `(kind=shell, payload=cmd)` 가 두 번 이상 매칭되면 1회로 축약한다. | 필수 |
| FR-107-17 | 프롬프트 재작성은 `done_token`, `self_correct_max`, `compact_after`, `code_timeout` 등 기존 환경변수 인터페이스를 변경하지 않는다. | 필수 |

### 8.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-107-01 | `_build_system_prompt()` 재작성 후에도 `_call_model()` 의 시스템 프롬프트 교체·복원 플로우는 변경되지 않는다. |
| NFR-107-02 | 디스패처의 분류기는 결정론적이며, 동일 입력 → 동일 출력. 외부 시스템 호출 없음. |
| NFR-107-03 | 디스패처 도입으로 `AgentSession` / `IterationRecord` / `ActionResult` 의 직렬화 호환성(FSD v1.0.086) 은 깨지지 않아야 한다. |
| NFR-107-04 | OS/쉘 힌트는 `AgentRunner` 인스턴스 생성 시점이 아니라 `_build_system_prompt()` **호출 시점**에 재계산된다. |
| NFR-107-05 | 테스트는 `unittest.mock.patch("platform.system")` + `patch.dict(os.environ, {"PSModulePath": ...})` 로 4쉘 타입 모두 커버한다. |
| NFR-107-06 | 프롬프트 변경에도 `[REASON]/[ACT]/[OBSERVE]` 정규식은 동일 — Vertex AI / Claude / GenAI 응답 호환성 회귀 없음. |
| NFR-107-07 | 디스패처 도입으로 Bypass Approvals (FSD v1.0.100), Bypass Overwrite (v1.0.103), max_iterations override (v1.0.101), 비동기 stop (v1.0.087) 의 동작 변경 없음. |
| NFR-107-08 | 프롬프트 길이는 한국어 기준 기존 대비 +800 ~ +1200 토큰. (Self-Correction 호출 감소로 총 토큰 감소 기대 — 측정은 후속 작업) |

---

## 9. 테스트 시나리오

### 9.1 `tests/test_agent_runner.py` 추가 — 프롬프트 구성

**클래스:** `TestBuildSystemPrompt107`

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-107-01 | 프롬프트에 `"선택지 A"`, `"선택지 B"`, `"선택지 C"` 세 문자열 모두 포함 | `assertIn` 3회 |
| T-107-02 | 프롬프트에 `"[❌ 금지 패턴]"` 섹션 존재 | `assertIn` |
| T-107-03 | 프롬프트에 `"[쉘 환경 요약 — 현재 쉘:"` 헤더 포함 | `assertIn` |
| T-107-04 | `platform.system()="Windows"` + `PSModulePath` 주입 시 `"Windows PowerShell"` 포함 | `assertIn` |
| T-107-05 | `platform.system()="Linux"` 시 `"Linux"` + `"bash"` 포함 | `assertIn` 2회 |
| T-107-06 | 선택지 B 영역 안에서 `"powershell"` / `"bash"` / `"sh"` 가 **noting code-execution** 으로 표기됨 (자동 쉘 라우팅 안내) | 부분 문자열 검증 |

### 9.2 `tests/test_agent_action_dispatcher.py` 신규 — 디스패처 분기

**공통 셋업:** `_make_dispatcher()` 헬퍼. `code_executor` / `terminal_executor` / `response_parser` Mock.

| # | 시나리오 | 입력 `act_text` (요약) | 기대 |
|---|---|---|---|
| T-107-07 | 단독 `$` 라인 | `"$ git status"` | shell 1건 (`target="git status"`) |
| T-107-08 | 단독 python 블록 | ```` ```python\nprint("hi")\n``` ```` | code 1건 (`target="python"`) |
| T-107-09 | 단독 filename 블록 | ```` ```filename:a.py\ncode\n``` ```` | file 1건 (`target="a.py"`), code 0건 |
| T-107-10 | **실패 패턴 A** — 쉘을 powershell 블록으로 감쌈 | ```` ```powershell\n$ git status\n$ git log\n``` ```` | shell 2건 (`git status` / `git log`), code 0건 |
| T-107-11 | **실패 패턴 B** — `$ python -c "..."` | `"$ python -c \"print('x')\""` | shell 1건 (현 의도대로) |
| T-107-12 | **실패 패턴 C** — 세 경로 혼재 | python + $ 라인 + file 블록 | file 1 + code 1 + shell 1 = 3건 |
| T-107-13 | **실패 패턴 D** — powershell 블록의 `Remove-Item` | ```` ```powershell\nRemove-Item -Recurse .\\build\n``` ```` | shell 1건이되 위험 명령 승인 플로우 트리거 (`approve_dangerous` mock 호출 검증) |
| T-107-14 | 펜스 안팎 `$` 라인 모두 — 중복 cmd | ```` $ ls\n```powershell\n$ ls\n``` ```` | shell 1건 (`ls`) — dedupe |
| T-107-15 | 다중라인 PowerShell 스크립트 | ```` ```powershell\nfunction Foo {...}\nFoo\n``` ```` | code 1건 `target="powershell"` (script 분류) |
| T-107-16 | 다중라인 bash 스크립트 (for 루프) | ```` ```bash\nfor f in *.py; do echo $f; done\n``` ```` | code 1건 `target="bash"` (script 분류) |
| T-107-17 | `[ACTION:shell]` 명시 태그 + python 블록 | `[ACTION:shell]\n```python\nprint('x')\n```` | 디스패처가 태그 기준으로 처리 — 현 스펙: code 0, shell 1건 (블록을 명령처럼 시도)** OR ** 거부(`success=False`). 구현 시 § 6.2 정책 확정 |
| T-107-18 | `AGENT_ACTION_TAGS_REQUIRED=1` + 태그 없는 입력 | `"$ git status"` | actions 0건, Self-Correction 안내 detail 1건 |
| T-107-19 | 빈 act_text | `""` | actions 0건 |
| T-107-20 | 펜스 시작/종료 마커 망가진 경우 | ```` ```python\nprint(1)\n```` (마지막 ``` 누락) | 펜스 미인식 → 펜스 외 텍스트로 처리, code 0건 |
| T-107-21 | 같은 명령 3회 반복 | ```` $ ls\n$ ls\n$ ls ```` | shell 1건 (dedupe) |
| T-107-22 | 위험 명령 + bypass 모드 + 한도 미달 | ```` $ rm tmp ```` (session.bypass_approvals=True, count=2, max=5) | shell 1건, count=3 |
| T-107-23 | 위험 명령 + bypass 모드 + 한도 초과 | count=5, max=5, `$ rm tmp` | `_BypassAbort` raise |

### 9.3 `tests/test_terminal_executor.py` 추가 — `agent_shell_brief()`

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-107-24 | `get_shell_type()` mock = "Windows PowerShell" | `"Get-ChildItem"`, `"Remove-Item"`, `"[쉘 환경 요약 — 현재 쉘: Windows PowerShell]"` 포함 |
| T-107-25 | mock = "Windows CMD" | `"dir"`, `"del"` 포함 |
| T-107-26 | mock = "Mac" | `"ls -la"`, `"diskutil"` 포함 |
| T-107-27 | mock = "Linux" | `"ls -la"`, `"rm"` 포함 |
| T-107-28 | 반환 첫 줄 형식 | `startswith("[쉘 환경 요약 — 현재 쉘: ")` |

### 9.4 `tests/test_os_utils.py` 추가 — 4-쉘 분기

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-107-29 | `get_shell_type` mock = "Windows PowerShell" | `"Windows PowerShell"`, `"PowerShell 구문"` 포함 |
| T-107-30 | mock = "Windows CMD" | `"Windows CMD"`, `"CMD 구문"` 포함 |
| T-107-31 | mock = "Mac" | `"macOS"`, `"bash/zsh"` 포함 |
| T-107-32 | mock = "Linux" | `"Linux"`, `"bash"` 포함 |

### 9.5 통합 회귀 (수동)

`/agents` 모드를 실제 실행해 § 1.1.1 ~ 1.1.4 의 4 패턴을 AI 가 생성하도록 유도(예: "다음 응답에서 `git status` 를 ```powershell``` 블록 안에 `$` 라인으로 작성하세요")한 후, 디스패처가 단일 경로로 라우팅하고 위험 명령 승인 프롬프트가 정상 표시되는지 확인.

---

## 10. 실행 흐름 다이어그램

### 10.1 디스패처 도입 후 `_execute_actions()`

```
act_text (AI 응답의 [ACT] 블록 원문)
   │
   ▼
AgentActionDispatcher.dispatch(session, act_text)
   │
   ├── _parse() ────────────────────────────┐
   │   1. RE_ACTION_TAG 분리 (있으면)         │
   │   2. RE_FENCE 펜스 추출:                 │
   │        ```filename:...```  → file action │
   │        ```python|js|py|... → code action │
   │        ```bash|sh|.../ps1  → 분류기로     │
   │   3. 펜스 영역 마스킹                     │
   │   4. RE_SHELL_LINE → shell action        │
   │                                          │
   │   각 쉘 블록:                             │
   │     classify_shell_block(code)           │
   │       == 'commands' → 라인별 shell action │
   │       == 'script'   → script action       │
   │                       (CodeExecutor)      │
   │                                          │
   ├── _dedupe() ───────────────────────────┘
   │     (kind=shell, payload) 중복 제거
   │
   └── 실행 루프
       file   → _exec_file (response_parser.parse_and_save)
       code   → _exec_code (CodeExecutor)
       script → _exec_script (CodeExecutor + 위험 명령 검사)
       shell  → _exec_shell (TerminalExecutor + 위험 명령 검사)
```

### 10.2 실패 패턴 A 처리 (Before / After)

#### Before (현행)

```
입력: ```powershell\n$ git status\n```

_save_file_blocks  → 0건
_run_code_blocks   → 1건 (.ps1 으로 실행 → '$' 토큰 에러)
_run_shell_lines   → 1건 (git status 정상 실행)

결과: 2건 시도, 1건 실패 → Self-Correction 호출
```

#### After (v1.0.107)

```
입력: ```powershell\n$ git status\n```

dispatch():
  parse: 펜스 [powershell] → 분류기 = 'commands'
         · 라인 "$ git status" → strip $ → "git status"
         · shell action 1건
  dedupe: 1건
  exec: terminal_executor.execute("git status")

결과: 1건 시도, 1건 성공 (Self-Correction 미호출)
```

### 10.3 실패 패턴 D 처리 (Before / After)

#### Before

```
입력: ```powershell\nRemove-Item -Recurse .\build\n```

_run_code_blocks → CodeExecutor.execute(code, "powershell")
                    → .ps1 임시파일에 Remove-Item 그대로 기록 후 실행
                    → 위험 명령 검사 없음 ❌
```

#### After

```
입력: ```powershell\nRemove-Item -Recurse .\build\n```

dispatch():
  parse: 펜스 [powershell] → 분류기 = 'commands' (단일 라인, 스크립트 indicator 없음)
         · 라인 "Remove-Item -Recurse .\build" → shell action
  exec: _exec_single_shell_command():
         · base = "remove-item" ∈ DANGEROUS_COMMANDS
         · session.bypass_approvals 검사 / 승인 프롬프트
         · 승인 시: terminal_executor.execute(..., allow_unsafe=True)
         · 거부 시: ActionResult(success=False, detail="사용자 거부")
```

### 10.4 다중라인 스크립트 (정상 처리)

```
입력: ```powershell
      function Get-Stats {
          Get-ChildItem | Measure-Object
      }
      Get-Stats
      ```

dispatch():
  parse: 펜스 [powershell] → 분류기 = 'script' (function 키워드 감지)
         · script action 1건 (lang=powershell, payload=전체 코드)
  exec: _exec_script():
         · 첫 토큰 "function" ∉ DANGEROUS_COMMANDS → 승인 불요
         · code_executor.execute(payload, "powershell")
         · ActionResult(kind="code", target="powershell", ...)
```

---

## 11. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | 분류기 휴리스틱이 100% 정확하지 않음 (예: `Get-Process | Where-Object { $_.CPU -gt 10 }` 의 중괄호) | `SCRIPT_INDICATORS` 는 라인 시작 키워드 기준이므로 인라인 중괄호는 트리거 안됨. 한 줄짜리 파이프라인은 `commands` 로 정상 분류. 의심스러우면 `[ACTION:code]` 명시. |
| 2 | 프롬프트 길이 +800 ~ +1200 토큰 → iteration 당 입력 토큰 비용 증가 | Self-Correction 감소로 총 iteration 토큰은 감소 기대. 측정 필요. 후속에서 `AGENT_PROMPT_COMPACT=1` 옵션 검토. |
| 3 | 기존 `agent_history` 에 들어 있는 응답은 과거 프롬프트 기준 → Resume 시 첫 iteration 만 혼선 | `_call_model()` 부터 새 system_prompt 가 적용되어 자연 교정. |
| 4 | `[ACTION:*]` 태그가 모델 별 학습 데이터에 익숙하지 않을 수 있음 | opt-in 으로 도입. 기본 미사용. 단계적 도입 가능. |
| 5 | `CodeExecutor.SUPPORTED_LANGUAGES` 의 쉘 5종은 그대로 유지 — `/run` 명령 호환 위함. 에이전트 경로에서만 분류기로 분기 | 책임 분리 명확. 디스패처가 에이전트 경로 전담. |
| 6 | 디스패처의 dedupe 가 사용자 의도(같은 명령을 의도적으로 두 번 실행) 를 막을 수 있음 | 동일 cmd 두 번 실행은 **에이전트 컨텍스트에서 의미 없음** (멱등). 의도적 중복은 거의 없음. |
| 7 | `AGENT_ACTION_TAGS_REQUIRED=1` 일 때 기존 모델 응답이 모두 무효 처리되어 진행이 멈출 수 있음 | 기본값 0 (off). on 은 강한 결정론 환경 전용. |
| 8 | 분류기가 `if` 한 줄짜리 (`if ($x) { ... }`) 를 'script' 로 오분류 | 단일 라인 if 도 문법적으로는 스크립트이므로 `script` 분류가 안전한 기본. 사용자가 `[ACTION:shell]` 로 강제 가능. |
| 9 | Bypass 모드에서 디스패처의 위험 명령 누적이 두 번 카운트될 위험 (구 코드와 신규 코드 동시 호출) | 디스패처 도입 시 기존 `_run_shell_lines()` 는 호출 경로에서 제거 — 단일 경로 보장. |
| 10 | `[ACTION:code]` 와 그 안에 ```bash``` 블록 동시 존재 시 우선순위 | § 6.2 — `[ACTION:code]` 가 외부 컨테이너이지만, 내부 `bash` 블록은 분류기가 다시 'script' or 'commands' 로 처리. 즉, 태그가 코드 경로를 강제하더라도 안에 들어간 쉘은 쉘로 라우팅. 사용자에겐 명확히 안내. |

---

## 12. 후속 작업

| 단계 | 내용 | 비고 |
|---|---|---|
| 1 | 프롬프트 실 사용 데이터에서 § 1.1.1~1.1.4 패턴 발생률 측정 → 디스패처 라우팅 분포 로깅 | 별도 logging 추가 (예: `AGENT_DISPATCHER_TRACE=1`) |
| 2 | Claude / Gemini / GenAI 별 응답 품질 A/B 비교 | RELEASE v1.0.108 후속 |
| 3 | `AGENT_PROMPT_COMPACT=1` — 토큰 절감 압축판 | 별도 FSD |
| 4 | `agent_shell_brief()` 의 안전 명령 동적 생성 (사용자 패턴 기반) | 별도 FSD |
| 5 | 분류기 휴리스틱을 LLM 기반 보조 분류로 보강 (작은 모델 호출) | 비용/지연 트레이드오프 검토 후 |
| 6 | `[ACTION:*]` 태그 사용을 권장하는 점진적 마이그레이션 (`AGENT_ACTION_TAGS_REQUIRED=warn` 모드) | 권장 |

---

## 13. 승인

- [ ] 설계 검토
- [ ] `src/terminal_executor.py` `agent_shell_brief()` 구현 및 T-107-24 ~ T-107-28 통과
- [ ] `src/os_utils.py` 4-쉘 분기 개선 및 T-107-29 ~ T-107-32 통과
- [ ] `src/agent_action_dispatcher.py` 신규 모듈 구현 및 T-107-07 ~ T-107-23 통과
- [ ] `src/agent_runner.py` `_build_system_prompt()` 재작성 및 T-107-01 ~ T-107-06 통과
- [ ] `src/agent_runner.py` `_execute_actions()` 디스패처 위임 + `_exec_single_shell_command()` / `_format_*_action_result()` 유틸 추가
- [ ] 기존 회귀 없음 (`tests/test_agent_runner.py`, `tests/test_terminal_executor.py`, `tests/test_os_utils.py`, `tests/test_agent_session_store.py`)
- [ ] Bypass Approvals (FSD v1.0.100), Bypass Overwrite (v1.0.103), max_iterations override (v1.0.101) 회귀 없음
- [ ] `/agents` 실사용 수동 확인 — § 1.1.1 ~ 1.1.4 4 패턴 재현 시 단일 경로 라우팅 + 위험 명령 승인 정상 동작
- [ ] `docs/specs/releases/RELEASE_v1.0.107_agents-act-intelligent-dispatcher.md` 작성
