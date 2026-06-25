# FSD v1.1.061 — `/agents` 기존 구현 전면 삭제

| 항목 | 내용 |
|------|------|
| 문서 번호 | FSD_v1.1.061 |
| 작성일 | 2026-06-24 |
| 상태 | 승인 대기 |
| 목적 | `/agents` 기능 전면 재설계를 위한 기존 구현 완전 삭제 |

---

## 1. 개요

`/agents` 명령은 v1.0.083부터 v1.0.107까지 총 10개의 FSD를 거쳐 점진적으로 구축된 자율 에이전트 루프 기능이다.  
전면 재설계를 앞두고, 기존 구현 코드 · 테스트 · 진입점 연결 코드를 완전히 제거하여 새 설계가 기존 구조에 오염되지 않도록 클린 슬레이트를 확보한다.

> **이 문서는 삭제 작업의 범위와 순서를 정의한다.**  
> 새로운 `/agents` 설계는 별도 FSD(v1.1.062 이후)로 작성된다.

---

## 2. 삭제 대상 — 소스 파일

| 파일 경로 | 규모 | 역할 | 근거 FSD |
|-----------|------|------|----------|
| `src/agent_runner.py` | 1,142줄 | 메인 에이전트 루프 (Reason→Act→Observe→Refine), `AgentRunner`, `AgentSession`, `AgentStopReason`, `ActionResult`, `IterationRecord` 정의 | v1.0.083 |
| `src/agent_action_dispatcher.py` | 370줄 | `ACT` 블록 파싱 및 file_write / code_exec / shell 액션 실행 디스패처 | v1.0.107 |
| `src/agent_input_listener.py` | 196줄 | 에이전트 루프 실행 중 's' 키(중단) 비동기 감지 | v1.0.087 |
| `src/agent_patch_applier.py` | 569줄 | `@@@patch:<path>@@@` 펜스 기반 파일 패치 적용 | v1.0.115 |
| `src/agent_session_store.py` | 136줄 | 에이전트 세션 JSON 직렬화·저장·복원 | v1.0.086 |
| `src/agents_command.py` | 185줄 | `/agents` 명령 공용 처리 진입점 (bypass·steps 플래그 파싱 포함) | v1.0.085 |

**소스 파일 합계: 6개 / 약 2,598줄**

---

## 3. 삭제 대상 — 테스트 파일

| 파일 경로 | 설명 |
|-----------|------|
| `tests/test_agent_runner.py` | AgentRunner 루프 및 종료 조건 테스트 |
| `tests/test_agent_action_dispatcher.py` | 액션 디스패처 파싱·실행 테스트 |
| `tests/test_agent_dispatcher_patch.py` | 디스패처 + 패치 적용기 통합 테스트 |
| `tests/test_agent_input_listener.py` | 키보드 입력 리스너 테스트 |
| `tests/test_agent_patch_applier.py` | 패치 적용 로직 테스트 |
| `tests/test_agent_session_store.py` | 세션 직렬화·복원 테스트 |
| `tests/test_agent_chain_danger.py` | 위험 액션 연속 탐지 테스트 (bypass 안전장치) |
| `tests/test_agent_system_prompt_v111.py` | 시스템 프롬프트 형식 테스트 |
| `tests/test_agents_flags.py` | `-ba` / `-s` 플래그 파싱 테스트 |

**테스트 파일 합계: 9개**

---

## 4. 삭제 대상 — 문서/프롬프트 파일

| 파일 경로 | 설명 |
|-----------|------|
| `docs/prompt/prompt_agents.md` | `/agents` 전용 시스템 프롬프트 (현재 git 수정 상태 M) |

> **참고 FSD 문서는 삭제하지 않는다.**  
> `docs/requirements/` 의 아래 10개 파일은 히스토리 보존 목적으로 유지한다.
> - `FSD_v1.0.083_agents-autonomous-loop.md`
> - `FSD_v1.0.085_agents-multi-provider-replication.md`
> - `FSD_v1.0.086_agents-session-serialization-resume.md`
> - `FSD_v1.0.087_agents-async-stop.md`
> - `FSD_v1.0.088_agents-os-shell-hint.md`
> - `FSD_v1.0.100_agents-bypass-approvals.md`
> - `FSD_v1.0.101_agents-max-iterations-and-resume-index.md`
> - `FSD_v1.0.103_agents-bypass-file-overwrite.md`
> - `FSD_v1.0.106_agents-system-prompt-act-disambiguation.md`
> - `FSD_v1.0.107_agents-act-intelligent-dispatcher.md`

---

## 5. 연관 파일 수정 (삭제가 아닌 코드 제거)

소스 파일 삭제 후 컴파일/임포트 오류가 발생하지 않도록 아래 파일에서 에이전트 관련 코드를 제거한다.

### 5-1. `src/__init__.py`

**제거 대상:**

```python
# 줄 25 — import 제거
from src.agent_runner import AgentRunner, AgentSession, AgentStopReason

# 줄 54–56 — __all__ 항목 제거
'AgentRunner',
'AgentSession',
'AgentStopReason',
```

### 5-2. `src/context_processor.py`

**제거 대상 (줄 314–327):**

```python
from .agent_patch_applier import AgentPatchApplier
applier = AgentPatchApplier(self.file_manager)

# applier를 사용하는 for 블록 전체
applied_total = 0
block_total = 0
failed = False
for fence_path, payload in blocks:
    ...
```

> `context_processor.py`의 해당 메서드(`_apply_patch_fences` 또는 동등한 QC 패치 적용 로직)는  
> `AgentPatchApplier` 없이는 동작하지 않으므로, 메서드 전체를 제거하거나 stub으로 대체한다.  
> 정확한 처리 범위는 구현 시 `context_processor.py` 전체를 재확인하여 결정한다.

### 5-3. `claude-ai-chat-code.py`

**제거 대상 (줄 529–531 일대):**

```python
elif command == '/agents':
    from src.agents_command import handle_agents_command
    handle_agents_command(...)
```

### 5-4. `gemini-ai-chat-code.py`

**제거 대상 (줄 368–370 일대):**

```python
elif command == '/agents':
    from src.agents_command import handle_agents_command
    handle_agents_command(...)
```

### 5-5. `gen-ai-chat-code.py`

**제거 대상 (줄 537–539 일대):**

```python
elif command == '/agents':
    from src.agents_command import handle_agents_command
    handle_agents_command(...)
```

---

## 6. `__pycache__` 정리

아래 `.pyc` 파일들은 소스 삭제 후 자동으로 무효화되지만, 명시적으로 제거하여 혼선을 방지한다.

```
src/__pycache__/agent_action_dispatcher.cpython-312.pyc
src/__pycache__/agent_goal_evaluator.cpython-312.pyc   ← .py 없는 고아 파일
src/__pycache__/agent_input_listener.cpython-312.pyc
src/__pycache__/agent_patch_applier.cpython-312.pyc
src/__pycache__/agent_runner.cpython-312.pyc
src/__pycache__/agents_command.cpython-312.pyc
src/__pycache__/agent_session_store.cpython-312.pyc

tests/__pycache__/test_agent_*.pyc  (9개 + 고아 파일 3개)
  ├── test_agent_eval_gate.cpython-312.pyc        ← .py 없는 고아 파일
  ├── test_agent_patch_similarity.cpython-312.pyc ← .py 없는 고아 파일
  └── test_agent_truncation.cpython-312-pytest-9.1.1.pyc ← .py 없는 고아 파일
```

---

## 7. 삭제 순서 (권장)

```
1. tests/test_agent_*.py          (9개) — 테스트 파일 먼저 삭제
2. src/agents_command.py           — 진입점 연결 모듈 삭제
3. src/agent_session_store.py
4. src/agent_patch_applier.py
5. src/agent_input_listener.py
6. src/agent_action_dispatcher.py
7. src/agent_runner.py             — 핵심 모듈 마지막 삭제
8. docs/prompt/prompt_agents.md
9. __pycache__ 고아 파일 정리
10. src/__init__.py                수정 (import 3줄 제거)
11. src/context_processor.py       수정 (AgentPatchApplier 의존 코드 제거)
12. claude-ai-chat-code.py         수정 (/agents elif 블록 제거)
13. gemini-ai-chat-code.py         수정 (/agents elif 블록 제거)
14. gen-ai-chat-code.py            수정 (/agents elif 블록 제거)
```

---

## 8. 완료 검증 기준

| 항목 | 검증 방법 |
|------|-----------|
| import 오류 없음 | `python -c "from src import *"` 정상 실행 |
| `/agents` 참조 없음 | `grep -rn "agent" src/ tests/` 결과 0건 |
| 기존 테스트 통과 | `python -m unittest discover -s tests -v` 에서 agent 외 테스트 전원 통과 |
| 진입점 정상 기동 | `python claude-ai-chat-code.py --help` (또는 동등) 오류 없음 |

---

## 9. 영향 범위 요약

| 구분 | 파일 수 | 비고 |
|------|---------|------|
| 소스 삭제 | 6개 | src/agent_*.py, src/agents_command.py |
| 테스트 삭제 | 9개 | tests/test_agent_*.py |
| 문서 삭제 | 1개 | docs/prompt/prompt_agents.md |
| 소스 수정 | 2개 | src/__init__.py, src/context_processor.py |
| 진입점 수정 | 3개 | claude/gemini/gen-ai-chat-code.py |
| 참고 FSD 유지 | 10개 | docs/requirements/FSD_v1.0.083~107 |
