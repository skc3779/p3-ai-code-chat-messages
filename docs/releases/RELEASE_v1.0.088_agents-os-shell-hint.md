# RELEASE v1.0.088 — 에이전트 시스템 프롬프트 OS 쉘 힌트 주입

| 항목 | 내용 |
|---|---|
| 릴리즈 버전 | v1.0.088 |
| 릴리즈 일자 | 2026-04-18 |
| 브랜치 | release_v1.0.090 |
| 요구 문서 | FSD v1.0.088 (`docs/specs/requirements/FSD_v1.0.088_agents-os-shell-hint.md`) |

---

## 변경 요약

`AgentRunner._build_system_prompt()` 에 OS 별 쉘 힌트를 추가하고, 세 어시스턴트 파일에 중복 존재하던 `_get_os_shell_hint()` 를 공유 모듈 `src/os_utils.py` 로 추출했다.

---

## 변경 파일

### 신규

| 파일 | 설명 |
|---|---|
| `src/os_utils.py` | `get_os_shell_hint()` 공유 유틸리티 모듈 |
| `tests/test_os_utils_and_agent_prompt.py` | T-088-01 ~ T-088-10 테스트 (12 케이스) |

### 수정

| 파일 | 변경 내용 |
|---|---|
| `src/agent_runner.py` | `import platform`, `from .os_utils import get_os_shell_hint` 추가; `_build_system_prompt()` 에 `shell_lang` 분기 및 `[실행 환경]` 섹션 추가 |
| `src/claude_assistant.py` | 인라인 `_get_os_shell_hint()` 삭제 → `from .os_utils import get_os_shell_hint as _get_os_shell_hint` |
| `src/gemini_assistant.py` | 동일 |
| `src/genai_assistant.py` | 동일 |

---

## 핵심 변경 내용

### `src/os_utils.py` (신규)

```python
def get_os_shell_hint() -> str:
    if platform.system() == 'Windows':
        return "현재 실행 환경: Windows OS.\n쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 ..."
    return f"현재 실행 환경: {platform.system()} OS.\n쉘 스크립트 작성 시 bash 구문을 사용하고 ..."
```

### `AgentRunner._build_system_prompt()` 변경 사항

1. `[ACT]` 섹션 코드 실행 예시에 `shell_lang` 분기 적용:
   - Windows → `` ```powershell ``
   - Linux/macOS → `` ```bash ``

2. `[주의]` 섹션 끝에 `[실행 환경]` 섹션 추가:
   ```
   [실행 환경]
   현재 실행 환경: Windows OS.
   쉘 스크립트 작성 시 반드시 PowerShell 구문을 사용하고 ...
   ```

---

## 테스트 결과

```
tests/test_os_utils_and_agent_prompt.py  12 passed in 0.49s
```

| 테스트 ID | 시나리오 | 결과 |
|---|---|---|
| T-088-01 | `get_os_shell_hint()` Windows → "powershell" 포함 | ✅ |
| T-088-02 | `get_os_shell_hint()` Linux/macOS → "bash" 포함 | ✅ |
| T-088-03 | `_build_system_prompt()` Windows → `[실행 환경]` 섹션 존재 | ✅ |
| T-088-04 | `_build_system_prompt()` Linux → `[실행 환경]` 섹션 존재 | ✅ |
| T-088-05 | `_build_system_prompt()` Windows → `[ACT]` 에 "powershell" | ✅ |
| T-088-06 | `_build_system_prompt()` Linux → `[ACT]` 에 "bash" | ✅ |
| T-088-07 | `ClaudeCodeAssistant._get_os_shell_hint` → `os_utils` 동일 함수 | ✅ |
| T-088-08 | `GeminiCodeAssistant._get_os_shell_hint` → `os_utils` 동일 함수 | ✅ |
| T-088-09 | `GenAICodeAssistant._get_os_shell_hint` → `os_utils` 동일 함수 | ✅ |
| T-088-10 | `from src.os_utils import get_os_shell_hint` 단독 import | ✅ |

---

## 회귀 영향

- 세 어시스턴트 클래스의 시스템 프롬프트 내 `_get_os_shell_hint()` 호출 코드는 **변경 없음** (별칭 import로 함수명 유지).
- `platform` import 가 각 어시스턴트 파일에서 제거됨 (다른 용도로 사용되지 않았음 확인).
