# RELEASE v1.0.085

## 1. 개요

* **버전**: v1.0.085
* **일자**: 2026-04-18
* **목적**: `/agents` 자율 에이전트 루프를 Claude / GenAI Provider로 확장하고, 공용 핸들러 추출로 코드 중복 제거
* **관련 FSD**: [FSD v1.0.085](../requirements/FSD_v1.0.085_agents-multi-provider-replication.md)

---

## 2. 주요 변경 사항

### 2.1 [P1] GenAI `conversation_history` 구조 통일 (`src/genai_assistant.py`)

`AgentRunner`와의 호환성 확보를 위해 GenAI의 대화 히스토리 형식을 `List[str]`에서 `List[Dict]`로 변경하였습니다.

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| `conversation_history` 타입 | `List[str]` | `List[Dict[str, str]]` |
| 항목 구조 | `"[User Context]\n..."` | `{"role": "user", "content": "..."}` |
| 토큰 트리밍 | `history_dicts` 임시 변환 후 트리밍 | `conversation_history` 직접 트리밍 |
| 기존 히스토리 파일 로드 | — | `load_history()` 에서 `List[str]` → `List[Dict]` 자동 마이그레이션 |

- `_chat_streaming()`, `_chat_non_streaming()` 내 히스토리 append 형식 변경
- `src/history_manager.py` `save_genai_history()` 시그니처를 `List[Dict]`로 업데이트
- `gen-ai-chat-code.py` `/history` 디스플레이, `/tokens` 명령 업데이트

### 2.2 [P2] `AgentRunner` — `assistant_role` 파라미터 추가 (`src/agent_runner.py`)

에이전트 히스토리 요약 시 사용하는 AI role 이름을 Provider별로 구분합니다.

```python
AgentRunner(..., assistant_role="model")     # Gemini, GenAI
AgentRunner(..., assistant_role="assistant") # Claude
```

`_append_summary_to_main_history()` 및 `_compact_history_if_needed()` 내 하드코딩된 `"model"` role을 `self.assistant_role`로 교체하였습니다.

### 2.3 [P3] Claude `chat()` — `disable_tools` 파라미터 추가 (`src/claude_assistant.py`)

에이전트 루프 호출 시 Claude의 Tool Use 자동 발동을 억제합니다.

```python
assistant.chat(prompt, disable_tools=True)
```

`disable_tools=True`이면 API 요청 body에서 `"tools"` 키를 제거합니다. 기본값은 `False`로 기존 동작을 유지합니다.

### 2.4 [P4] `/agents` 공용 핸들러 추출 (`src/agents_command.py` — 신규)

세 엔트리 포인트의 `/agents` 처리 로직을 `handle_agents_command()` 함수로 통합하였습니다.

```python
from src.agents_command import handle_agents_command

handle_agents_command(
    assistant=assistant,
    cli_handler=input_handler,
    streaming=streaming_mode,
    args=args,
    assistant_role="assistant",   # Claude
)
```

### 2.5 각 CLI에 `/agents` 분기 추가

| 파일 | 변경 내용 |
|------|---------|
| `gemini-ai-chat-code.py` | 기존 44줄 인라인 코드 → `handle_agents_command()` 9줄로 교체 |
| `claude-ai-chat-code.py` | `/agents` 분기 신규 추가 (`assistant_role="assistant"`) |
| `gen-ai-chat-code.py` | `/agents` 분기 신규 추가 (`assistant_role="model"`) |

---

## 3. 영향 범위

| 파일 | 변경 유형 | 주요 내용 |
|------|---------|---------|
| `src/agents_command.py` | **신규** | `/agents` 공용 처리 함수 |
| `src/agent_runner.py` | 수정 | `assistant_role` 파라미터 추가 |
| `src/genai_assistant.py` | 수정 | `conversation_history` 구조 변경, OS 쉘 힌트 주입 |
| `src/claude_assistant.py` | 수정 | `chat()` `disable_tools` 파라미터, OS 쉘 힌트 주입 |
| `src/history_manager.py` | 수정 | `save_genai_history()` 시그니처 업데이트 |
| `gemini-ai-chat-code.py` | 수정 | `/agents` 인라인 → 공용 함수 호출로 리팩터 |
| `claude-ai-chat-code.py` | 수정 | `/agents` 분기 신규 추가 |
| `gen-ai-chat-code.py` | 수정 | `/agents` 분기 신규 추가, `/history`·`/tokens` 업데이트 |

---

## 4. 호환성 주의 사항

- **GenAI 기존 히스토리 파일**: `.chat_history/*.json` 중 `type: genai`인 파일의 `messages` 필드가 `List[str]`인 경우, `load_history()` 호출 시 자동으로 `List[Dict]`로 마이그레이션됩니다. 별도 수동 작업 불필요.
- **AgentRunner 직접 생성 코드**: `assistant_role` 파라미터가 추가되었지만 기본값이 `"model"`이므로 기존 Gemini 호출 코드는 변경 불필요.

---

## 5. 검증 내역

| # | 시나리오 | 결과 |
|---|---------|:----:|
| 1 | `gemini-ai-chat-code.py` — `/agents` 실행 (기존 동작 유지 확인) | ✅ |
| 2 | `claude-ai-chat-code.py` — `/agents` 신규 실행 | ✅ |
| 3 | `gen-ai-chat-code.py` — `/agents` 신규 실행 | ✅ |
| 4 | GenAI 기존 `List[str]` 히스토리 파일 로드 마이그레이션 | ✅ |
| 5 | `/agents stop` — 세 Provider 모두 안내 메시지 출력 | ✅ |
