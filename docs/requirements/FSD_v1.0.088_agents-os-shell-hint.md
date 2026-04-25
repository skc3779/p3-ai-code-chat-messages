# FSD v1.0.088 — 에이전트 시스템 프롬프트 OS 쉘 힌트 주입

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.088 |
| 작성일 | 2026-04-18 |
| 상태 | 📝 사전 분석 (구현 대기) |
| 선행 문서 | FSD v1.0.083 (`/agents` 자율 에이전트 루프) |
| 대상 파일 | `src/agent_runner.py`, `src/claude_assistant.py`, `src/gemini_assistant.py`, `src/genai_assistant.py` |
| 신규 파일 | `src/os_utils.py` |

---

## 1. 개요

### 1.1 목적

현재 `AgentRunner._build_system_prompt()` 는 쉘 명령 실행 예시를 아래와 같이 고정 문자열로 제공한다:

```
[ACT]
이번 단계에서 수행할 구체적 행동:
- 쉘 명령 실행:    라인 시작에 `$ <명령>` (한 줄에 한 명령)
- 코드 실행:       ```python / ```bash / ```javascript 블록
```

이 설명에는 **현재 OS 에 맞는 쉘 구문 정보가 없다.** Windows 환경에서 에이전트가 `bash` 스크립트를 생성하거나 Unix 계열 쉘 명령을 그대로 제안하는 문제가 발생할 수 있다.

반면 세 개의 어시스턴트 클래스(`ClaudeCodeAssistant`, `GeminiCodeAssistant`, `GenAICodeAssistant`)는 이미 `_get_os_shell_hint()` 함수를 통해 OS 별 쉘 힌트를 시스템 프롬프트에 주입하고 있다.

본 FSD 는 **에이전트 시스템 프롬프트에도 동일한 OS 쉘 힌트를 주입**하고, 세 파일에 중복된 `_get_os_shell_hint()` 함수를 `src/os_utils.py` 공유 모듈로 추출하는 방법을 명세한다.

### 1.2 범위

| 항목 | 포함 여부 |
|---|---|
| `_get_os_shell_hint()` 공유 모듈(`os_utils.py`) 추출 | ✅ |
| `AgentRunner._build_system_prompt()` 에 OS 힌트 추가 | ✅ |
| 세 어시스턴트 파일의 인라인 함수 → import 전환 | ✅ |
| 힌트 내용 자체의 변경 (Windows/Unix 문구 수정) | ❌ (현행 유지) |
| macOS 별도 분기 추가 | ❌ (현행 유지, macOS 는 Unix 경로) |

---

## 2. 현황 분석

### 2.1 `_get_os_shell_hint()` 현재 구현 (세 파일 동일)

`src/claude_assistant.py`, `src/gemini_assistant.py`, `src/genai_assistant.py` 에 각각 다음 함수가 **완전 동일**한 형태로 존재한다:

```python
def _get_os_shell_hint() -> str:
    if platform.system() == 'Windows':
        return (
            "현재 실행 환경: Windows OS.\n"
            "쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 "
            "코드 블록 언어 태그를 `powershell` 또는 `ps1`로 지정하세요. "
            "`bash`, `sh` 코드 블록은 이 환경에서 실행되지 않습니다."
        )
    return (
        f"현재 실행 환경: {platform.system()} OS.\n"
        "쉘 스크립트 작성 시 bash 구문을 사용하고 "
        "코드 블록 언어 태그를 `bash` 또는 `sh`로 지정하세요."
    )
```

각 파일 상단에서 `import platform` 을 선언하고, 클래스 생성자의 `default_system_prompt` 문자열 끝 `[실행 환경]` 섹션에 주입된다:

```python
[실행 환경]
""" + _get_os_shell_hint() + """
```

### 2.2 `AgentRunner._build_system_prompt()` 현재 상태

`src/agent_runner.py` 의 `_build_system_prompt()` 는 `[ACT]` 블록 안에 아래와 같이 bash 를 언급하나 OS 분기가 없다:

```python
"- 코드 실행:       ```python / ```bash / ```javascript 블록 (파일명 없음 → 임시 실행)\n"
"- 쉘 명령 실행:    라인 시작에 `$ <명령>` (한 줄에 한 명령)\n\n"
```

`[실행 환경]` 섹션이 아예 없다.

### 2.3 문제 예시 (Windows)

Windows 에서 에이전트가 다음과 같은 코드 블록을 생성하면 실행 실패한다:

```bash
$ pip install requests
$ python main.py
```

에이전트가 bash 를 가정하고 있기 때문이다. 올바른 Windows 출력은:

```powershell
$ pip install requests
$ python main.py
```

또는

````powershell
```powershell
pip install requests
python main.py
```
````

---

## 3. 설계

### 3.1 공유 모듈 `src/os_utils.py` 추출

세 어시스턴트 파일의 `_get_os_shell_hint()` 를 `src/os_utils.py` 로 이동하고, 세 파일에서 import 한다.

#### 신규 파일: `src/os_utils.py`

```python
"""
os_utils - 플랫폼별 유틸리티 함수 (FSD v1.0.088)

현재는 OS 쉘 힌트 텍스트 생성만 포함한다.
"""

import platform


def get_os_shell_hint() -> str:
    """현재 OS 에 맞는 쉘 구문 힌트 문자열을 반환한다.

    반환값은 어시스턴트/에이전트 시스템 프롬프트의 '[실행 환경]' 섹션에 삽입된다.

    Returns:
        Windows: PowerShell 사용 권고 문자열
        기타(Linux, macOS): bash/sh 사용 권고 문자열
    """
    if platform.system() == 'Windows':
        return (
            "현재 실행 환경: Windows OS.\n"
            "쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 "
            "코드 블록 언어 태그를 `powershell` 또는 `ps1`로 지정하세요. "
            "`bash`, `sh` 코드 블록은 이 환경에서 실행되지 않습니다."
        )
    return (
        f"현재 실행 환경: {platform.system()} OS.\n"
        "쉘 스크립트 작성 시 bash 구문을 사용하고 "
        "코드 블록 언어 태그를 `bash` 또는 `sh`로 지정하세요."
    )
```

> **함수명**: 기존 `_get_os_shell_hint` (모듈 내 private) → `get_os_shell_hint` (공개 API)
>
> 세 어시스턴트 파일에서는 하위 호환을 위해 기존 이름(`_get_os_shell_hint`)을 별칭으로 유지할 수 있으나, 신규 코드는 `get_os_shell_hint` 를 사용한다.

### 3.2 세 어시스턴트 파일 수정

각 파일의 인라인 `_get_os_shell_hint()` 정의를 삭제하고 import 로 교체한다.

**변경 전 (`claude_assistant.py` 등):**

```python
import platform
...
def _get_os_shell_hint() -> str:
    if platform.system() == 'Windows':
        ...
```

**변경 후:**

```python
from .os_utils import get_os_shell_hint as _get_os_shell_hint
```

`platform` 모듈 직접 import 는 `os_utils.py` 로 이동하므로 해당 어시스턴트 파일에서 제거 가능하다 (단, 다른 용도로 사용 중이면 유지).

### 3.3 `AgentRunner._build_system_prompt()` 수정

`[주의]` 섹션 뒤에 `[실행 환경]` 섹션을 추가한다.

**변경 전:**

```python
def _build_system_prompt(self) -> str:
    return (
        "당신은 자율 코딩 에이전트입니다. ...\n"
        ...
        "[주의]\n"
        "- 코드 블록 밖에서 장황하게 설명하지 마세요.\n"
        "- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.\n"
        "- 위험 명령(rm, mv, del, move 등)은 반드시 필요한 경우에만 사용하세요. ...\n"
        "- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.\n"
    )
```

**변경 후:**

```python
from .os_utils import get_os_shell_hint

class AgentRunner:
    ...
    def _build_system_prompt(self) -> str:
        return (
            "당신은 자율 코딩 에이전트입니다. ...\n"
            ...
            "[주의]\n"
            "- 코드 블록 밖에서 장황하게 설명하지 마세요.\n"
            "- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.\n"
            "- 위험 명령(rm, mv, del, move 등)은 반드시 필요한 경우에만 사용하세요. ...\n"
            "- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.\n\n"
            "[실행 환경]\n"
            + get_os_shell_hint()
        )
```

또한 `[ACT]` 섹션의 코드 블록 언어 힌트도 OS 분기를 반영하도록 개선한다:

**변경 전 (`[ACT]` 섹션 일부):**

```
"- 코드 실행:       ```python / ```bash / ```javascript 블록 (파일명 없음 → 임시 실행)\n"
"- 쉘 명령 실행:    라인 시작에 `$ <명령>` (한 줄에 한 명령)\n\n"
```

**변경 후:**

```python
"- 코드 실행:       ```python / ```{shell_lang} / ```javascript 블록 (파일명 없음 → 임시 실행)\n"
"- 쉘 명령 실행:    라인 시작에 `$ <명령>` (한 줄에 한 명령)\n\n"
```

여기서 `shell_lang` 은 `_build_system_prompt()` 내부에서:

```python
import platform
shell_lang = "powershell" if platform.system() == "Windows" else "bash"
```

으로 결정한다.

---

## 4. 구현 사양 (초안)

### 4.1 `src/os_utils.py` 전체

```python
"""
os_utils - 플랫폼별 유틸리티 함수 (FSD v1.0.088)
"""
import platform


def get_os_shell_hint() -> str:
    """현재 OS 에 맞는 쉘 구문 힌트 문자열을 반환한다."""
    if platform.system() == 'Windows':
        return (
            "현재 실행 환경: Windows OS.\n"
            "쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 "
            "코드 블록 언어 태그를 `powershell` 또는 `ps1`로 지정하세요. "
            "`bash`, `sh` 코드 블록은 이 환경에서 실행되지 않습니다."
        )
    return (
        f"현재 실행 환경: {platform.system()} OS.\n"
        "쉘 스크립트 작성 시 bash 구문을 사용하고 "
        "코드 블록 언어 태그를 `bash` 또는 `sh`로 지정하세요."
    )
```

### 4.2 `src/agent_runner.py` 상단 import 추가

```python
import platform
from .os_utils import get_os_shell_hint
```

### 4.3 `_build_system_prompt()` 전체 변경 사양

```python
def _build_system_prompt(self) -> str:
    shell_lang = "powershell" if platform.system() == "Windows" else "bash"
    return (
        "당신은 자율 코딩 에이전트입니다. 주어진 상위 목표를 달성하기 위해\n"
        "스스로 계획을 세우고 단계별로 실행합니다.\n\n"
        "[응답 형식 — 반드시 준수]\n"
        "첫 번째 응답(계획 수립)은 번호 매긴 목록으로 전체 PLAN 을 나열하세요.\n"
        "이후 매 반복(iteration) 응답은 다음 세 블록을 순서대로 포함해야 합니다.\n\n"
        "[REASON]\n"
        "현재 상태를 분석하고 이번 단계에서 무엇을 할지 논리적으로 서술\n"
        "(바로 직전 [OBSERVE] 결과를 반드시 참조)\n\n"
        "[ACT]\n"
        "이번 단계에서 수행할 구체적 행동:\n"
        "- 파일 생성/수정:  ```filename:<경로>   ...   ```   블록\n"
        f"- 코드 실행:       ```python / ```{shell_lang} / ```javascript 블록 (파일명 없음 → 임시 실행)\n"
        "- 쉘 명령 실행:    라인 시작에 `$ <명령>` (한 줄에 한 명령)\n\n"
        "[OBSERVE]\n"
        "위 ACT 를 실행했을 때 기대되는 결과를 간단히 서술\n"
        "(실제 실행 결과는 시스템이 다음 프롬프트에 주입합니다)\n\n"
        "[완료 판정]\n"
        f"목표를 완전히 달성했다고 판단되면 응답 맨 끝에 정확히 다음 한 줄을 추가:\n"
        f"  {self.done_token}\n\n"
        "[Self-Correction]\n"
        "[OBSERVE] 또는 시스템이 제공한 실행 결과에 오류가 포함된 경우,\n"
        "다음 [REASON] 에서 원인을 진단하고 [ACT] 에서 수정 버전을 제시하세요.\n\n"
        "[주의]\n"
        "- 코드 블록 밖에서 장황하게 설명하지 마세요.\n"
        "- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.\n"
        "- 위험 명령(rm, mv, del, move 등)은 반드시 필요한 경우에만 사용하세요. 사용자가 거부할 수 있습니다.\n"
        "- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.\n\n"
        "[실행 환경]\n"
        + get_os_shell_hint()
    )
```

### 4.4 세 어시스턴트 파일 변경 요약

각 파일에서 아래 블록 **삭제**:

```python
def _get_os_shell_hint() -> str:
    if platform.system() == 'Windows':
        ...
    return ...
```

아래 **추가** (상단 import 영역):

```python
from .os_utils import get_os_shell_hint as _get_os_shell_hint
```

기존 시스템 프롬프트 내 `_get_os_shell_hint()` 호출 위치는 **변경 없음** (함수 이름 별칭이 동일하므로).

---

## 5. 파일 변경 예정 목록

| 파일 | 변경 유형 | 설명 |
|---|---|---|
| `src/os_utils.py` | **신규** | `get_os_shell_hint()` 공유 유틸리티 |
| `src/agent_runner.py` | 수정 | import 추가, `_build_system_prompt()` 에 `[실행 환경]` 섹션 및 `shell_lang` 분기 추가 |
| `src/claude_assistant.py` | 수정 | 인라인 `_get_os_shell_hint()` 삭제 → `from .os_utils import` 교체 |
| `src/gemini_assistant.py` | 수정 | 동일 |
| `src/genai_assistant.py` | 수정 | 동일 |
| `src/__init__.py` | 수정 (선택) | `os_utils` 를 패키지 공개 API 에 추가 여부 결정 |

---

## 6. 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-088-01 | `get_os_shell_hint()` Windows 환경 반환값 | "Windows OS" + "powershell" 키워드 포함 |
| T-088-02 | `get_os_shell_hint()` Linux 환경 반환값 | "Linux OS" + "bash" 키워드 포함 |
| T-088-03 | `AgentRunner._build_system_prompt()` Windows | `[실행 환경]` 섹션에 "powershell" 포함 |
| T-088-04 | `AgentRunner._build_system_prompt()` Linux | `[실행 환경]` 섹션에 "bash" 포함 |
| T-088-05 | `AgentRunner._build_system_prompt()` Windows | `[ACT]` 섹션 코드 실행 예시에 "powershell" 포함 |
| T-088-06 | `AgentRunner._build_system_prompt()` Linux | `[ACT]` 섹션 코드 실행 예시에 "bash" 포함 |
| T-088-07 | `ClaudeCodeAssistant` 시스템 프롬프트 | `_get_os_shell_hint()` 결과가 기존과 동일 (회귀 없음) |
| T-088-08 | `GeminiCodeAssistant` 시스템 프롬프트 | 동일 |
| T-088-09 | `GenAICodeAssistant` 시스템 프롬프트 | 동일 |
| T-088-10 | `os_utils` 독립 import (의존성 없음) | `from src.os_utils import get_os_shell_hint` 단독 import 성공 |

---

## 7. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | `platform.system()` 은 런타임에 평가되므로 `_build_system_prompt()` 호출 시점마다 일관됨 | 문제 없음 — 프로세스 실행 중 OS 는 바뀌지 않음 |
| 2 | WSL(Windows Subsystem for Linux) 에서는 `platform.system()` 이 `"Linux"` 를 반환하므로 bash 경로로 처리됨 | 의도된 동작 — WSL 은 bash 사용 |
| 3 | 세 어시스턴트 파일의 `import platform` 이 다른 목적으로 사용 중일 수 있음 | 각 파일에서 `platform` 사용 여부 확인 후 불필요하면 제거, 아니면 유지 |
| 4 | `_get_os_shell_hint` 는 모듈-private 이름 관례(`_` 접두사)이므로, 공개 API `get_os_shell_hint` 와 구분됨 | 어시스턴트 파일 내부에서는 별칭(`as _get_os_shell_hint`)으로 사용하여 기존 호출 코드 변경 최소화 |

---

## 8. 승인

- [ ] 설계 검토 (2026-04-18)
- [ ] `src/os_utils.py` 신규 생성
- [ ] `src/agent_runner.py` 수정
- [ ] 세 어시스턴트 파일 수정 (중복 코드 제거)
- [ ] 테스트 작성 및 통과
- [ ] 문서 반영
