# FSD v1.0.085 — `/agents` 멀티 Provider 분기 복제 (Claude / GenAI)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.085 |
| 작성일 | 2026-04-18 |
| 상태 | 📝 사전 분석 (구현 대기) |
| 선행 문서 | FSD v1.0.083 (`/agents` 자율 에이전트 루프) |
| 대상 파일 | `claude-ai-chat-code.py`, `gen-ai-chat-code.py` |
| 관련 모듈 | `src/agent_runner.py` (기존), `src/claude_assistant.py`, `src/genai_assistant.py` |

---

## 1. 개요

### 1.1 목적

FSD v1.0.083 에서 `gemini-ai-chat-code.py` 에만 구현된 `/agents` 자율 에이전트 루프를 `claude-ai-chat-code.py` 와 `gen-ai-chat-code.py` 엔트리 포인트에 동일하게 복제한다. `AgentRunner` 는 Provider 독립적으로 설계되었으므로 기본적으로 재사용 가능하나, **각 Provider 의 API 인터페이스 차이**로 인해 사전에 식별·해결해야 할 문제들이 존재한다.

### 1.2 범위

| 항목 | 포함 여부 |
|---|---|
| `claude-ai-chat-code.py` 에 `/agents` 분기 추가 | ✅ |
| `gen-ai-chat-code.py` 에 `/agents` 분기 추가 | ✅ |
| `src/agent_runner.py` 수정 (호환성 개선) | ✅ 필요 시 |
| `src/claude_assistant.py` 수정 | ✅ 필요 시 |
| `src/genai_assistant.py` 수정 | ✅ 필요 시 |
| 세션 상태 저장/재개 | ❌ (FSD v1.0.086) |
| 비동기 `/agents stop` | ❌ (FSD v1.0.087) |

---

## 2. 현황 분석

### 2.1 AgentRunner 의 Provider 인터페이스 요구사항

`AgentRunner` 는 아래 인터페이스를 **assistant** 객체에 요구한다:

| 인터페이스 | 용도 | 현재 상태 |
|---|---|---|
| `assistant.chat(prompt, streaming, include_context)` | 모델 호출 | Gemini ✅ / Claude ✅ / GenAI ✅ |
| `assistant.conversation_history` (읽기/쓰기) | 히스토리 격리 | Gemini `List[Dict]` ✅ / Claude `List[Dict]` ⚠️ / GenAI `List[str]` ❌ |
| `assistant.system_prompt` (읽기/쓰기) | 에이전트 전용 프롬프트 교체 | Gemini ✅ / Claude ✅ / GenAI ✅ |
| `assistant.file_manager` | 파일 관리 | 모두 ✅ |
| `assistant.code_executor` | 코드 실행 | 모두 ✅ |
| `assistant.terminal_executor` | 쉘 명령 실행 | 모두 ✅ |
| `assistant.response_parser` | 파일 블록 저장 | 모두 ✅ |
| `assistant.context_builder` | 패턴 컨텍스트 | 모두 ✅ |

### 2.2 Provider 별 `chat()` 시그니처 비교

```python
# GeminiCodeAssistant (gemini_assistant.py:137)
def chat(self, user_message, streaming=True, include_context=False, file_patterns=None) -> str

# ClaudeCodeAssistant (claude_assistant.py:134)
def chat(self, user_message, streaming=True, include_context=False, file_patterns=None) -> str

# GenAICodeAssistant (genai_assistant.py:228)
def chat(self, user_message, streaming=True, include_context=False, file_patterns=None) -> str
```

> 시그니처는 모두 동일. 반환값도 모두 `str`. **호출 자체는 호환된다.**

### 2.3 Provider 별 `conversation_history` 구조 비교

| Provider | 타입 | 구조 | 역할 키 |
|---|---|---|---|
| Gemini | `List[Dict]` | `{"role": "user"/"model", "content": str}` | `user`, `model` |
| Claude | `List[Dict]` | `{"role": "user"/"assistant", "content": str\|List}` | `user`, `assistant` |
| GenAI | `List[str]` | 단순 문자열 리스트 | 없음 (홀/짝으로 구분) |

---

## 3. 문제점 사전 분석

### 3.1 🔴 [P1] GenAI `conversation_history: List[str]` 비호환

**문제:**
`AgentRunner._call_model()` 은 `assistant.conversation_history` 를 `List[Dict[str, str]]` 형식 (`{"role": "...", "content": "..."}`) 으로 다루며, 세션 격리 시 `session.agent_history` (역시 `List[Dict]`) 를 대입한다.

```python
# agent_runner.py:312-313 — 현재 코드
self.assistant.conversation_history = list(session.agent_history)
# → GenAI 에서 List[Dict] 를 List[str] 자리에 대입 → 타입 불일치
```

`GenAICodeAssistant.chat()` 내부에서 `conversation_history` 를 직접 `contents` 리스트에 추가할 때 문자열을 기대하기 때문에, `Dict` 가 들어가면 **직렬화 오류**가 발생한다.

**영향:** GenAI 에서 `/agents` 전혀 동작 불가.

**해결 방안:**

| 방안 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. GenAI 히스토리 Dict 로 통일** | `genai_assistant.py` 의 `conversation_history` 를 `List[Dict]` 로 변경. `chat()` 내부 API 호출 시 `List[str]` 로 변환. | Provider 간 통일, AgentRunner 수정 불요 | GenAI 쪽 변경 범위 큼, 기존 `/history` 등 명령 영향 |
| **B. AgentRunner 어댑터 패턴** | AgentRunner 에 `_serialize_history()` / `_deserialize_history()` 어댑터를 두어 Provider 별 형식 변환 | AgentRunner 내부에서 캡슐화 | AgentRunner 가 Provider 의존적이 됨 |
| **C. agent_history 전용 인자로 chat() 호출** | `chat()` 호출 시 `history` 파라미터를 별도로 전달하고, `conversation_history` 교체를 완전 회피 | 가장 깔끔. 재진입 안전성도 확보 | **모든 Provider 의 `chat()` 시그니처** 변경 필요 |

**권장: 방안 A 또는 C**. 방안 A 가 단기적으로 가장 리스크가 낮다. 방안 C 는 향후 확장에 유리하나 변경 범위가 넓다.

**사용자 피드백** : 방안 A로 처리해줘

---

### 3.2 🟡 [P2] Claude `conversation_history` — `content` 가 `List` 일 수 있음

**문제:**
Claude 의 `_chat_streaming()` 은 `assistant` 역할 메시지의 `content` 를 `List[Dict]` (tool_use + text 블록 혼합) 로 저장한다:

```python
# claude_assistant.py:368
self.conversation_history.append({"role": "assistant", "content": assistant_content})
# assistant_content 가 List[Dict] 일 수 있음
```

`AgentRunner._append_summary_to_main_history()` 는 요약 메시지를 `{"role": "model", "content": str}` 형태로 추가하는데, Claude 의 role 명은 `assistant` 이다.

**영향:**
1. `_call_model()` 에서 `session.agent_history` 를 `conversation_history` 에 대입 후 Claude `chat()` 호출 시, agent_history 의 `"role": "model"` 을 Claude API 가 인식하지 못할 수 있음 → **API 에러 가능**
2. 에이전트 요약 append 시 role 이 `model` 로 들어가 Claude `conversation_history` 와 혼재

**해결 방안:**

| 방안 | 설명 |
|---|---|
| **A. AgentRunner 에 role 매핑 로직 추가** | `__init__()` 에 `assistant_role_name` 파라미터 도입. Gemini = `"model"`, Claude = `"assistant"`. Agent 내부에서 role 구성 시 이 값을 사용. |
| **B. Provider Assistant 에 `ROLE_ASSISTANT` 상수 추가** | 각 Assistant 클래스에 `ROLE_ASSISTANT = "model"` 또는 `"assistant"` 를 정의하고, AgentRunner 가 `self.assistant.ROLE_ASSISTANT` 를 참조 |

**권장: 방안 A** — AgentRunner 생성자에 간단히 파라미터 하나만 추가.

**사용자 피드백** : 방안 A로 처리해줘

---

### 3.3 🟡 [P3] Claude Tool Use 와 에이전트 루프 충돌 가능성

**문제:**
Claude `chat()` 은 응답에 `tool_use` 블록이 포함되면 자동으로 도구를 실행하고 **재귀 호출** 로 후속 응답을 받는다 (claude_assistant.py:370-402). 에이전트 루프에서 `_call_model()` 이 `chat()` 을 호출하면:

1. 에이전트 전용 시스템 프롬프트에는 tool_use 규약이 없음
2. 그러나 Claude 모델이 자발적으로 tool_use 블록을 포함하면 `_chat_streaming` 이 도구를 실행하고 재귀 호출
3. 재귀 호출 시점에 `conversation_history` 는 에이전트 전용이므로 도구 결과가 agent_history 에 편입
4. `finally` 블록에서 `session.agent_history = self.assistant.conversation_history` 로 동기화되므로 **도구 호출이 agent_history 에 부수적으로 누적** — 의도하지 않은 히스토리 오염

**해결 방안:**

| 방안 | 설명 |
|---|---|
| **A. 에이전트 호출 시 tools 제거** | `chat()` 호출 전 `body["tools"]` 를 비우거나, `chat()` 에 `disable_tools=True` 파라미터 추가 |
| **B. 에이전트 시스템 프롬프트에서 tool_use 금지 명시** | "tool_use를 사용하지 마세요" 라고 지시 — 보장 안 됨 |
| **C. 무시 (허용)** | 도구 호출이 발생하면 에이전트 맥락에서 자연스럽게 활용 |

**권장: 방안 A** — Claude `chat()` 에 `tools=None` 을 전달할 수 있는 인터페이스 확장 권장. 또는 에이전트 전용 호출 시 `body` 에서 `tools` 키를 제거.

**사용자 피드백** : 방안 A로 처리해줘


---

### 3.4 🟢 [P4] 엔트리 포인트 코드 중복

**문제:**
현재 `gemini-ai-chat-code.py` 의 `/agents` 분기 (라인 343-386, 약 44줄) 를 `claude-ai-chat-code.py` 와 `gen-ai-chat-code.py` 에 **거의 동일하게 복사**해야 한다. 이는 향후 유지보수 부담을 증가시킨다.

세 엔트리 포인트 간 차이점:
- 변수명: `cli_handler` vs `input_handler`
- 스트리밍 변수명: `streaming` vs `streaming_mode`
- Assistant 클래스 타입 (속성 동일하므로 duck-typing 으로 무관)

**해결 방안:**

| 방안 | 설명 |
|---|---|
| **A. 단순 복사 + 변수명 조정** | 빠르고 확실. 변경 시 세 곳 수정 필요. |
| **B. `src/agents_command.py` 공용 함수 추출** | 패턴 파싱 + 목표 수집 + AgentRunner 생성 + 실행을 하나의 함수 `handle_agents_command(assistant, cli_handler, streaming, args)` 로 추출 |

**권장: 방안 B** — 향후 Agent 관련 명령이 늘어나면 (resume, status 등) 공용화의 이점이 커진다.

**사용자 피드백** : 방안 B로 처리해줘

---

### 3.5 🟡 [P5] GenAI `chat()` 의 히스토리 추가 방식 차이

**문제:**
GenAI `chat()` 은 히스토리에 문자열을 다음과 같이 추가한다:

```python
# genai_assistant.py:363-365
self.conversation_history.append(f"[User Context]\n{user_message}")
self.conversation_history.append(f"[Assistant Context]\n{result_message}")
```

`_call_model()` 이 `chat()` 을 호출한 후 `session.agent_history = self.assistant.conversation_history` 로 동기화하는데, GenAI 에서는 이 값이 `List[str]` 이므로 `agent_history` (원래 `List[Dict]`) 와 타입 불일치가 발생한다.

또한 GenAI `chat()` 은 `full_message` (context 포함 메시지) 를 히스토리에 추가하므로, 에이전트의 `include_context=False` 를 사용해도 GenAI 내부에서 context 를 붙이지 않지만 히스토리 추가 방식 자체가 다르다.

**해결:** P1 과 동일한 방안으로 해결 (GenAI 히스토리 Dict 통일 또는 어댑터 패턴).

---

### 3.6 🟢 [P6] Claude 의 `system_prompt` 반영 방식

**문제:**
`AgentRunner._call_model()` 은 `self.assistant.system_prompt` 를 직접 교체하여 에이전트 전용 프롬프트를 주입한다. Claude `chat()` 에서는 이 값을 `body["system"]` 에 사용하므로 정상 동작한다.

그러나 교체 후 `chat()` 내부에서 **Tool Use 재귀 호출** 이 발생하면, 재귀 호출 시에도 에이전트 전용 프롬프트가 유지되는지 검증이 필요하다.

**결론:** 현재 구현에서는 `finally` 블록이 재귀 완료 후 실행되므로, 재귀 중에는 에이전트 프롬프트가 유지된다. **문제 없음** (P3 해결 시 도구 호출 자체를 비활성화하면 이 우려도 해소).

---

### 3.7 🟢 [P7] `command_registry.py` 변경 불요

`/agents` 명령은 이미 FSD v1.0.083 에서 `command_registry.py` 에 등록되어 있다. Claude/GenAI 엔트리 포인트도 동일한 `print_menu()` 를 공유하므로 추가 변경 불필요.

---

## 4. 구현 사양 (초안)

### 4.1 공용 함수 추출 (방안 B 채택 시)

```python
# src/agents_command.py (신규)

from typing import List, Optional

def handle_agents_command(
    assistant,           # GeminiCodeAssistant / ClaudeCodeAssistant / GenAICodeAssistant
    cli_handler,         # CLIInputHandler
    streaming: bool,
    args: str,           # /agents 뒤의 인자 문자열
    assistant_role: str = "model",  # "model" (Gemini) / "assistant" (Claude)
) -> None:
    """
    /agents 명령의 공통 처리 로직.
    패턴 파싱 → 멀티라인 목표 수집 → AgentRunner 생성 → 실행.
    """
    from src.agent_runner import AgentRunner

    # /agents stop
    if args.strip().lower() == 'stop':
        print("💡 에이전트는 현재 실행 중이 아닙니다. 루프 도중 Ctrl+C 로 중단하세요.")
        return

    # <pattern> 파싱
    file_patterns: List[str] = []
    stripped = args.strip()
    if stripped:
        if stripped.startswith('['):
            try:
                end_idx = args.index(']')
                file_patterns = [p.strip() for p in args[1:end_idx].split(',') if p.strip()]
            except ValueError:
                print("❌ 닫는 대괄호 ']'가 없습니다.")
                return
        else:
            file_patterns = stripped.split()

    # 목표 수집
    if file_patterns:
        print(f"🎯 목표를 입력하세요 — 컨텍스트 패턴: {file_patterns}")
    else:
        print("🎯 목표를 입력하세요 (멀티라인, 종료: /end 또는 Esc+Enter)")
    goal = cli_handler.get_multiline()
    if not goal or not goal.strip():
        print("❌ 목표가 비어있습니다.")
        return

    runner = AgentRunner(
        assistant=assistant,
        file_manager=assistant.file_manager,
        code_executor=assistant.code_executor,
        terminal_executor=assistant.terminal_executor,
        response_parser=assistant.response_parser,
        cli_handler=cli_handler,
        context_builder=assistant.context_builder,
        streaming=streaming,
        assistant_role=assistant_role,   # P2 해결
    )
    runner.run(goal, file_patterns=file_patterns or None)
```

### 4.2 AgentRunner 수정 (P2 해결)

```python
class AgentRunner:
    def __init__(self, ..., assistant_role: str = "model"):
        ...
        self.assistant_role = assistant_role  # "model" or "assistant"

    def _append_summary_to_main_history(self, session):
        ...
        self.assistant.conversation_history.append(
            {"role": "user", "content": user_msg}
        )
        self.assistant.conversation_history.append(
            {"role": self.assistant_role, "content": bot_msg}  # ← 변경
        )
```

### 4.3 Claude 엔트리 포인트

```python
# claude-ai-chat-code.py — /auto_context 분기 아래에 추가
elif command == '/agents':
    from src.agents_command import handle_agents_command
    handle_agents_command(
        assistant=assistant,
        cli_handler=input_handler,
        streaming=streaming_mode,
        args=args,
        assistant_role="assistant",
    )
    last_response = ""
```

### 4.4 GenAI 엔트리 포인트

```python
# gen-ai-chat-code.py — /auto_context 분기 아래에 추가
elif command == '/agents':
    from src.agents_command import handle_agents_command
    handle_agents_command(
        assistant=assistant,
        cli_handler=input_handler,
        streaming=streaming_mode,
        args=args,
        assistant_role="model",  # GenAI 는 role 키 없으므로 기본값 사용
    )
    last_response = ""
```

> ⚠️ **GenAI 는 P1 해결 전에는 동작하지 않는다.** P1 해결이 선행 조건.

---

## 5. 작업 순서 (권장)

```
Step 1. [P1 해결] genai_assistant.py 히스토리 구조 Dict 통일
        └─ conversation_history: List[str] → List[Dict[str, str]]
        └─ chat() 내부에서 API 호출 시 List[str] 로 변환
        └─ gen-ai-chat-code.py 의 /history, /tokens 등 관련 코드 수정

Step 2. [P2 해결] AgentRunner 에 assistant_role 파라미터 추가
        └─ _append_summary_to_main_history(), _call_model() 내 role 참조 변경

Step 3. [P3 해결] Claude 에이전트 호출 시 Tool Use 비활성화 방안 결정/구현
        └─ chat() 에 disable_tools 인자 추가 또는 _call_model() 에서 처리

Step 4. [P4 해결] src/agents_command.py 공용 함수 추출

Step 5. claude-ai-chat-code.py 에 /agents 분기 추가 (약 5줄)

Step 6. gen-ai-chat-code.py 에 /agents 분기 추가 (약 5줄)

Step 7. 통합 테스트
        └─ 각 Provider 별 /agents 기본 시나리오 (PLAN + 1 iteration + AGENT_DONE)
        └─ /agents stop 안내 메시지
        └─ /agents <pattern> 모드
```

---

## 6. 테스트 시나리오

| # | 시나리오 | Provider | 기대 결과 |
|---|---|---|---|
| T-085-01 | Claude `/agents` 기본 (멀티라인 목표) | Claude | PLAN 출력 → Iteration → [AGENT_DONE] 정상 종료 |
| T-085-02 | GenAI `/agents` 기본 (멀티라인 목표) | GenAI | 동일 |
| T-085-03 | Claude `/agents stop` | Claude | "실행 중이 아닙니다" 안내 |
| T-085-04 | GenAI `/agents stop` | GenAI | 동일 |
| T-085-05 | Claude `/agents src/*.py` (패턴 모드) | Claude | 파일 목록 출력 + PLAN 에 FILE_CONTEXT 포함 |
| T-085-06 | Claude 에이전트 루프 종료 후 `conversation_history` 확인 | Claude | role="assistant" 로 요약 1쌍 추가, 에이전트 내부 상세 없음 |
| T-085-07 | GenAI 에이전트 루프 종료 후 `conversation_history` 확인 | GenAI | Dict 형태로 요약 1쌍 추가 |
| T-085-08 | Claude 에이전트 중 Tool Use 발동 시 | Claude | P3 방안에 따라 도구 비활성화 또는 정상 처리 |
| T-085-09 | Ctrl+C 로 중단 | 모두 | user_stop 사유로 종료, 요약 출력 |
| T-085-10 | `handle_agents_command()` 공용 함수가 세 엔트리에서 동일 동작 | 모두 | Gemini/Claude/GenAI 모두 동일 UX |

---

## 7. 파일 변경 예정 목록

| 파일 | 변경 유형 | 설명 |
|---|---|---|
| `src/agents_command.py` | **신규** | `/agents` 공용 처리 함수 |
| `src/agent_runner.py` | 수정 | `assistant_role` 파라미터 추가, role 매핑 적용 |
| `src/genai_assistant.py` | 수정 | `conversation_history` 를 `List[Dict]` 로 변경 |
| `gen-ai-chat-code.py` | 수정 | (1) `/agents` 분기 추가 (2) 히스토리 참조 코드 수정 |
| `claude-ai-chat-code.py` | 수정 | `/agents` 분기 추가 |
| `src/claude_assistant.py` | 수정 (선택) | `chat()` 에 `disable_tools` 파라미터 추가 |
| `gemini-ai-chat-code.py` | 수정 (선택) | 기존 인라인 코드 → `handle_agents_command()` 호출로 대체 |

---

## 8. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | GenAI 히스토리 구조 변경은 기존 저장된 히스토리 파일과의 하위 호환성 문제를 야기할 수 있다 | `load_history()` 에서 마이그레이션 로직 추가 (구 `List[str]` → 신 `List[Dict]`) |
| 2 | Claude 의 `content: List` 형식은 `AgentRunner._compact_history_if_needed()` 에서 `msg.get("content", "")[:1500]` 로 접근 시 리스트에 대해 슬라이싱이 적용돼 문자열이 아닌 리스트 슬라이스가 됨 | 에이전트 `agent_history` 는 무조건 `{"role": str, "content": str}` 형태로 관리. Claude `chat()` 이 tool_result 를 포함한 비문자열 content 를 추가하더라도 `_call_model()` 의 finally 에서 동기화 시점에 이를 정규화 |
| 3 | GenAI API 의 `SensitiveWordFilter` 가 에이전트 메시지에도 적용되어야 한다 | GenAI `chat()` 내부에서 이미 적용되므로 추가 조치 불필요 |
| 4 | 각 Provider 의 토큰 한도가 다르다 (`MAX_TOKENS_GEMINI`, `MAX_TOKENS_CLAUDE`, `MAX_TOKENS_GENAI`) | `AgentRunner` 는 토큰 관리를 `chat()` 에 위임하므로 영향 없음. 단, `AGENT_COMPACT_AFTER` 의 적절성은 Provider 별 토큰 한도에 따라 조정 필요 |

---

## 9. 승인

- [ ] 사전 분석 검토 (2026-04-18)
- [ ] P1~P3 해결 방안 확정
- [ ] 구현
- [ ] 테스트
- [ ] 문서 반영
