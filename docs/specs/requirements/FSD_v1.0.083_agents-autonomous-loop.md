# FSD v1.0.083 — `/agents` 자율 에이전트 루프 (Vertex AI 기반)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.083 |
| 작성일 | 2026-04-18 |
| 상태 | 📝 설계 완료 (구현 대기) |
| 선행 문서 | FSD v1.0.030 (Gemini API 통합), FSD v1.0.076 (`/auto_context` 재시도) |
| 대상 파일 (1단계) | `src/agent_runner.py` (**신규**), `gemini-ai-chat-code.py`, `src/command_registry.py` |
| 대상 파일 (2단계, 별도 FSD 예정) | `claude-ai-chat-code.py`, `gen-ai-chat-code.py` |
| 테스트 파일 | `tests/test_agent_runner.py` (**신규**) |

---

## 1. 개요

### 1.1 목적

기존 `/context`, `/auto_context` 는 **한 번의 질문 → 한 번의 응답 (Zero-shot)** 패턴으로, "python으로 테트리스 작성해줘" 같은 **막연한 상위 목표(High-level goal)** 를 단일 호출만으로 달성하기 어렵다.

본 FSD는 **Vertex AI Gemini API** 를 이용해 AI가 **스스로 계획을 세우고(Plan) → 실행(Act) → 관찰(Observe) → 반성/수정(Reflect/Refine)** 의 사이클을 반복하며 목표를 달성하는 **자율 에이전트(Autonomous Agent)** 기능 `/agents` 를 도입한다. 1단계로 `gemini-ai-chat-code.py` 에만 반영하며, 검증 후 Claude/GenAI 계열로 확장한다.

### 1.2 배경 · 핵심 전략

| 전략 | 본 기능에 적용되는 방식 |
|---|---|
| **CoT (Chain of Thought)** | 첫 iteration 에서 AI 가 목표를 세분화한 **계획(PLAN)** 을 단계별로 나열 |
| **ReAct (Reason + Act)** | 매 iteration 을 `Reason → Act → Observe` 3-단계 블록으로 구조화하여 JSON 또는 태그 포맷으로 응답 |
| **Self-Correction** | 코드 실행 결과 stderr / returncode != 0 를 다음 iteration 의 입력 컨텍스트로 피드백하여 AI 가 스스로 수정 |
| **Self-Reflection** | 각 iteration 끝에서 AI 가 "산출물이 목표를 만족하는가?" 스스로 판정하고, 만족 시 `[AGENT_DONE]` 출력 |
| **Iterative Refinement** | 위 사이클을 `AGENT_MAX_ITERATIONS` 한도 내에서 반복 |
| **Human-in-the-Loop** | 매 iteration 끝에 사용자가 `계속 / 피드백 / 중단` 을 선택 (턴 사이 프롬프트 모델) |

### 1.3 범위

| 항목 | 1단계 (본 FSD) | 2단계 (예정) |
|---|---|---|
| 대상 엔트리 포인트 | `gemini-ai-chat-code.py` | `claude-ai-chat-code.py`, `gen-ai-chat-code.py` |
| Provider | Vertex AI Gemini (`GeminiCodeAssistant.chat()` 재사용) | Claude / GenAI |
| 공용 모듈 | `src/agent_runner.py` (신규) — Provider 독립적 설계 | 동일 모듈 재사용 |
| 상태 저장/재개 | ❌ (stop = 폐기) | 별도 FSD 에서 검토 |

### 1.4 비-목표 (Non-Goals)

- 에이전트 상태의 디스크 직렬화/재개 (`/agents resume`)
- 외부 MCP 서버 / 외부 도구(tool) 호출 (shell/code-executor 외)
- 다중 에이전트 협업 (multi-agent)
- 병렬 iteration 실행

---

## 2. 현황 분석

### 2.1 기존 명령어와의 차이

| 명령어 | 루프 | 자가 수정 | 계획 수립 | 실행 | 사용자 개입 |
|---|---|---|---|---|---|
| `/context` | ❌ 1회 | ❌ | ❌ | ❌ | — |
| `/auto_context` | 파일 단위 for-loop | 저장 실패 시 3회 재시도 (동일 프롬프트) | ❌ | ❌ | 시작 전 Y/N |
| **`/agents`** (신규) | ✅ Reason→Act→Observe 사이클 | ✅ 에러 → 프롬프트에 주입 | ✅ CoT 기반 초기 PLAN | ✅ 코드/쉘/파일 쓰기 | ✅ 매 iteration 턴 사이 |

#### 2.1.1 `/agents` 호출 형식 (2가지)

| 형식 | 의미 | 파일 컨텍스트 |
|---|---|---|
| `/agents` | 목표만 멀티라인으로 입력 | ❌ 파일 없이 순수 목표만 |
| `/agents <pattern>` | 패턴을 먼저 지정 → **이어서 멀티라인 모드로 목표 입력** | ✅ 매칭 파일을 초기 프롬프트의 `[FILE_CONTEXT]` 블록으로 주입 |

- **두 형식 모두 멀티라인 모드**로 진입해 goal 을 수집한다. (`/context` 처럼 한 줄 뒤에 질문을 이어 쓰는 형태는 지원하지 않음 — 에이전트 목표는 보통 장문이므로 멀티라인으로 통일)
- `<pattern>` 이 지정되면 기존 `/context` 와 **동일한 파서**(단일 패턴, 공백 구분 다중, `[p1, p2, …]` 리스트)를 사용하며, `/context` 의 컨텍스트 구성 로직(`ContextBuilder.build_context(file_patterns=…, include_tree=True)`)을 재사용한다.
- 매칭 파일이 0 개이면 에이전트를 시작하지 않고 안내만 출력한다 (기존 `/context` / `/auto_context` 와 동일한 UX).
- `<pattern>` 모드의 동작 철학은 `/context` (전체 매칭 파일을 **합쳐** 한 세션에 주입) 에 가깝고, `/auto_context` 처럼 파일별로 1-by-1 루프를 돌지는 **않는다**. 에이전트는 모든 파일을 한 컨텍스트로 보고 스스로 계획을 세운다.

### 2.2 재사용 가능한 기존 자산

| 자산 | 본 기능에서의 역할 |
|---|---|
| `GeminiCodeAssistant.chat()` | Vertex AI Gemini API 호출 (streaming/non-streaming) |
| `GeminiCodeAssistant.conversation_history` | 메인 대화 히스토리 (루프 종료 후 요약본만 append) |
| `CodeExecutor.execute(code, language)` | Python/JS/Bash 코드 실행 (30초 timeout) |
| `TerminalExecutor.execute(cmd, allow_unsafe)` | 쉘 명령 실행 (안전/위험 모드) |
| `FileManager.write_file(path, content)` | 파일 저장 |
| `ResponseParser.parse_and_save(response)` | ` ```filename:` 블록 → 파일 저장 |
| `CLIInputHandler.get_multiline()` | `/agents` 입력 수집 |
| `ContextBuilder.build_context(file_patterns=…, include_tree=True)` | `<pattern>` 지정 시 파일 컨텍스트 생성 (`/context` 와 동일 경로) |
| `FilePatternMatcher` | 다중 패턴 구문 파싱 (`[p1, p2]`) — `/context` 와 공용 |
| `ContextProcessor.normalize_backtick_blocks()` | 코드 블록 정규화 (참고) |

### 2.3 엔트리 포인트 현황 (`gemini-ai-chat-code.py:176-615`)

`while True:` 루프 안에서 `user_input.startswith('/')` 로 슬래시 명령을 분기한다. `/agents` 는 기존 `/multiline`, `/auto_context` 핸들러와 유사한 위치에 추가한다.

---

## 3. 요구사항

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-083-001 | `/agents` 입력 시 멀티라인 입력 모드로 전환하여 목표를 수집 | 필수 |
| FR-083-002 | 목표가 비어있으면 에이전트를 시작하지 않고 경고 출력 | 필수 |
| FR-083-003 | `/agents stop` 입력 시 실행 중인 루프를 중단하고 상태를 폐기. 루프 미실행 중 입력 시 "실행 중인 에이전트 없음" 안내 | 필수 |
| FR-083-004 | 루프 진입 즉시 AI 에게 **PLAN(CoT)** 을 먼저 수립시키고 번호 매긴 단계 리스트로 출력 | 필수 |
| FR-083-005 | 매 iteration 에서 AI 는 `[REASON] … [ACT] … [OBSERVE 예상] …` 3-블록 포맷으로 응답 | 필수 |
| FR-083-006 | `[ACT]` 블록 안의 ` ```filename:` 은 자동 저장, ` ```python/js/bash` (파일명 없음) 은 `CodeExecutor` 로 자동 실행, `$ <shell-cmd>` 라인은 `TerminalExecutor` 로 실행 요청 | 필수 |
| FR-083-007 | 코드 실행 결과(stdout/stderr/returncode)를 **OBSERVE** 로 사용자에게 출력하고 다음 iteration 프롬프트에 주입 | 필수 |
| FR-083-008 | 코드 실행이 실패(returncode != 0 또는 예외)하면 동일 목표에 대해 **최대 3회** 자동 Self-Correction 시도 후 포기 (env `AGENT_SELF_CORRECT_MAX=3`) | 필수 |
| FR-083-009 | 매 iteration 종료 시 사용자에게 `▶ [c]ontinue / [f]eedback / [s]top ?` 프롬프트를 표시. `f` 선택 시 멀티라인 입력을 받아 다음 iteration 프롬프트에 **`[USER_FEEDBACK]`** 블록으로 주입 | 필수 |
| FR-083-010 | 최대 iteration 횟수 도달 시(env `AGENT_MAX_ITERATIONS=10`) 강제 종료하고 "한도 초과" 메시지 출력 | 필수 |
| FR-083-011 | AI 응답 어딘가에 `[AGENT_DONE]` 태그가 포함되면 "목표 달성" 메시지 출력 후 루프 정상 종료 | 필수 |
| FR-083-012 | 루프 도중 `Ctrl+C` 입력 시 즉시 중단. 현재까지의 반복 횟수와 저장된 산출물 요약 출력 | 필수 |
| FR-083-013 | 쉘 명령 실행 요청(`$ <cmd>`)이 `TerminalExecutor.DANGEROUS_COMMANDS` 에 해당하면, 매 실행 시 **단건 승인 프롬프트** `▶ 이 명령을 실행할까요? [y/N/A(항상허용)]` 표시. `A` 선택 시 현재 에이전트 세션 한정 자동 승인 | 필수 |
| FR-083-014 | 파일 삭제/이동(`rm`, `mv`, `del`, `move` 등) 액션 요청 시 동일한 단건 승인 + 세션 자동승인 UI 적용 | 필수 |
| FR-083-015 | 에이전트 대화는 별도 `agent_history` 리스트에 누적 (메인 `conversation_history` 와 분리). 루프 종료 시 **에이전트 요약 메시지 1개** 만 메인 히스토리에 append | 필수 |
| FR-083-016 | `Reason / Act / Observe` 블록은 **제목 + 코드/결과** 만 표시 (세부 사고 과정은 원문 그대로 스트리밍). 중간 단계 축약 없음 | 필수 |
| FR-083-017 | `print_menu()` 도움말에 `/agents`, `/agents stop` 을 추가 | 필수 |
| FR-083-018 | `/agents` 는 `<pattern>` **선택 인자** 를 지원한다. 지원 형식은 `/context` 와 동일: 단일 패턴, 공백 구분 다중 패턴, `[p1, p2, …]` 리스트 | 필수 |
| FR-083-019 | 패턴 유무와 무관하게 명령 실행 직후 **항상 멀티라인 입력 모드**로 전환하여 goal 을 수집한다. 멀티라인 입력이 비어있으면 에이전트 미시작 | 필수 |
| FR-083-020 | `<pattern>` 지정 시 `ContextBuilder.build_context(file_patterns=…, include_tree=True)` 로 컨텍스트를 생성하여, 초기 PLAN 프롬프트의 `[FILE_CONTEXT]` 블록과 매 iteration 프롬프트의 `[FILE_CONTEXT_REF]` 요약 힌트에 반영한다 (전체 본문은 PLAN 호출 1회만 주입하여 토큰 절약) | 필수 |
| FR-083-021 | `<pattern>` 에 매칭되는 파일이 0 개이면 `❌ 패턴 '…' 에 해당하는 파일이 없습니다.` 를 출력하고 에이전트를 시작하지 않음 | 필수 |
| FR-083-022 | 매칭 파일이 1개 이상일 때 시작 직후 매칭 파일 목록(상대 경로)을 출력하여 사용자가 현재 컨텍스트 범위를 확인할 수 있도록 함 | 필수 |
| FR-083-023 | `[USER_FEEDBACK]` / `<pattern>` / 단순 `/agents` 세 경로 모두 **동일한 에이전트 루프** 를 사용한다 (분기 없음). 차이는 초기 프롬프트 구성에만 있다 | 필수 |

### 3.2 비기능 요구사항

| ID | 요구사항 |
|---|---|
| NFR-083-001 | `AgentRunner` 는 Provider 에 독립적이어야 함. `assistant.chat(prompt, streaming, include_context=False)` 인터페이스만 요구 |
| NFR-083-002 | 에이전트 실행 중 `GeminiCodeAssistant.conversation_history` 는 수정하지 않음 (격리성) |
| NFR-083-003 | 토큰 폭증 방지: `agent_history` 는 각 iteration 끝에 요약본으로 압축 (env `AGENT_COMPACT_AFTER=5`, 기본 5 iteration 이상 시 압축) |
| NFR-083-004 | 모든 액션 실행(파일 쓰기/코드 실행/쉘)은 **로깅**하여 루프 종료 시 요약에 포함 |
| NFR-083-005 | `Ctrl+C` 처리는 `KeyboardInterrupt` 를 catch 하여 정상 종료 경로로 수렴 (프로세스 전체는 죽지 않음) |
| NFR-083-006 | 환경변수 기본값은 코드에 하드코딩하되, `.env` 에서 오버라이드 가능 |

### 3.3 환경변수

| 변수명 | 기본값 | 설명 |
|---|---|---|
| `AGENT_MAX_ITERATIONS` | `10` | 루프 최대 반복 횟수 |
| `AGENT_SELF_CORRECT_MAX` | `3` | 코드 실행 실패 시 동일 목표에 대한 자가 수정 최대 횟수 |
| `AGENT_COMPACT_AFTER` | `5` | `agent_history` 길이가 이 값을 넘으면 AI 에게 압축 요약을 요청 |
| `AGENT_CODE_TIMEOUT` | `30` | `CodeExecutor` 코드 실행 timeout (초) — 기본값은 `CodeExecutor` 기본과 동일 |
| `AGENT_DONE_TOKEN` | `[AGENT_DONE]` | 종료 신호 토큰 (커스터마이즈 가능) |

---

## 4. 구현 사양

### 4.1 신규 모듈: `src/agent_runner.py`

#### 4.1.1 클래스 구조

```python
"""
AgentRunner - 자율 에이전트 루프 실행기

CoT / ReAct / Self-Correction 을 적용해 사용자가 제시한 상위 목표를
Reason → Act → Observe → Refine 사이클로 반복 수행한다.
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class AgentStopReason(Enum):
    DONE = "done"                        # [AGENT_DONE]
    MAX_ITERATIONS = "max_iterations"    # AGENT_MAX_ITERATIONS 초과
    USER_STOP = "user_stop"              # /agents stop 또는 Ctrl+C
    USER_ABORT_ON_ERROR = "user_abort"   # 에러 프롬프트에서 사용자가 s 선택
    FATAL_ERROR = "fatal_error"          # 복구 불가 예외


@dataclass
class ActionResult:
    """한 iteration 내 액션(file_write / code_exec / shell) 실행 결과"""
    kind: str                            # "file" | "code" | "shell"
    target: str                          # 파일 경로 / 언어 / 명령
    success: bool
    detail: str = ""                     # stdout / stderr / error 요약


@dataclass
class IterationRecord:
    idx: int
    reason_text: str
    act_text: str
    actions: List[ActionResult] = field(default_factory=list)
    observe_text: str = ""
    user_feedback: Optional[str] = None


@dataclass
class AgentSession:
    goal: str
    plan: str = ""
    file_patterns: List[str] = field(default_factory=list)   # FR-083-018
    matched_files: List[str] = field(default_factory=list)   # 초기 매칭 파일 상대경로
    iterations: List[IterationRecord] = field(default_factory=list)
    agent_history: List[Dict[str, str]] = field(default_factory=list)
    # 세션 한정 자동 승인 플래그
    auto_approve_dangerous_shell: bool = False
    auto_approve_file_mutation: bool = False
    stop_reason: Optional[AgentStopReason] = None


class AgentRunner:
    """에이전트 루프 실행기 (Provider 독립)"""

    # ─── 태그 정의 ────────────────────────────────────────────
    RE_REASON  = re.compile(r"\[REASON\](.*?)(?=\[ACT\]|\[OBSERVE\]|\[AGENT_DONE\]|\Z)", re.DOTALL)
    RE_ACT     = re.compile(r"\[ACT\](.*?)(?=\[OBSERVE\]|\[AGENT_DONE\]|\Z)", re.DOTALL)
    RE_OBSERVE = re.compile(r"\[OBSERVE\](.*?)(?=\[AGENT_DONE\]|\Z)", re.DOTALL)
    RE_SHELL   = re.compile(r"^\s*\$\s+(.+)$", re.MULTILINE)
    # ```filename:path\n ... ``` (ResponseParser 재사용)
    # ```lang\n ... ``` (CodeExecutor.extract_code_from_response 재사용)

    def __init__(
        self,
        assistant,                       # GeminiCodeAssistant 등 chat() 보유 객체
        file_manager,                    # FileManager
        code_executor,                   # CodeExecutor
        terminal_executor,               # TerminalExecutor
        response_parser,                 # ResponseParser (```filename: 저장)
        cli_handler,                     # CLIInputHandler (피드백 멀티라인 입력)
        context_builder=None,            # ContextBuilder (<pattern> 컨텍스트 생성)
        streaming: bool = True,
    ):
        self.assistant = assistant
        self.file_manager = file_manager
        self.code_executor = code_executor
        self.terminal_executor = terminal_executor
        self.response_parser = response_parser
        self.cli_handler = cli_handler
        self.context_builder = context_builder   # None 이면 <pattern> 미지원
        self.streaming = streaming

        self.max_iterations       = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))
        self.self_correct_max     = int(os.getenv("AGENT_SELF_CORRECT_MAX", "3"))
        self.compact_after        = int(os.getenv("AGENT_COMPACT_AFTER", "5"))
        self.done_token           = os.getenv("AGENT_DONE_TOKEN", "[AGENT_DONE]")

    # ─── 진입점 ──────────────────────────────────────────────
    def run(
        self,
        goal: str,
        file_patterns: Optional[List[str]] = None,   # FR-083-018
    ) -> AgentSession: ...

    # ─── 내부 ────────────────────────────────────────────────
    def _build_system_prompt(self) -> str: ...
    def _build_initial_prompt(self, goal: str, file_context: str = "") -> str: ...
    def _build_iteration_prompt(self, session: AgentSession, feedback: Optional[str]) -> str: ...

    def _call_model(self, session: AgentSession, user_prompt: str) -> str: ...
    def _parse_blocks(self, response: str) -> Tuple[str, str, str]: ...  # reason, act, observe

    def _execute_actions(self, session: AgentSession, act_text: str) -> List[ActionResult]: ...
    def _save_file_blocks(self, act_text: str) -> List[ActionResult]: ...
    def _run_code_blocks(self, act_text: str) -> List[ActionResult]: ...
    def _run_shell_lines(self, session: AgentSession, act_text: str) -> List[ActionResult]: ...

    def _ask_continue(self) -> Tuple[str, Optional[str]]: ...   # ('c'|'f'|'s', feedback?)
    def _approve_dangerous(self, session: AgentSession, flag_attr: str, label: str) -> bool: ...

    def _compact_history_if_needed(self, session: AgentSession) -> None: ...
    def _append_summary_to_main_history(self, session: AgentSession) -> None: ...

    def _print_header(self, session, iteration_idx: int) -> None: ...
    def _print_block(self, emoji: str, title: str, body: str) -> None: ...
    def _print_final_summary(self, session: AgentSession) -> None: ...
```

#### 4.1.2 `run()` 메인 루프 의사 코드

```python
def run(self, goal: str, file_patterns: Optional[List[str]] = None) -> AgentSession:
    # <pattern> 지정 시 파일 컨텍스트 생성 (FR-083-020)
    file_context = ""
    matched_rel_paths: List[str] = []
    if file_patterns:
        if self.context_builder is None:
            print("⚠️  ContextBuilder 미주입 — <pattern> 모드 비활성화")
        else:
            file_context = self.context_builder.build_context(
                include_tree=True, file_patterns=file_patterns
            ) or ""
            # 매칭 파일 목록 사전 검사 (FR-083-021, FR-083-022)
            from src.file_pattern_matcher import FilePatternMatcher
            matcher = FilePatternMatcher(self.file_manager.workspace_dir)
            all_files = self.file_manager.list_files()
            matched = matcher.filter_files(all_files, file_patterns)
            if not matched:
                print(f"❌ 패턴 {file_patterns} 에 해당하는 파일이 없습니다.")
                session = AgentSession(goal=goal)
                session.stop_reason = AgentStopReason.FATAL_ERROR
                return session
            matched_rel_paths = [
                str(p.relative_to(self.file_manager.workspace_dir)) for p in matched
            ]

    session = AgentSession(
        goal=goal, file_patterns=file_patterns or [],
        matched_files=matched_rel_paths,
    )
    print(f"\n🤖 에이전트 시작 — 목표:\n  {goal}\n")
    if matched_rel_paths:
        print(f"📂 컨텍스트에 포함된 파일 {len(matched_rel_paths)}개:")
        for p in matched_rel_paths:
            print(f"  - {p}")

    try:
        # ── Step 0. PLAN (CoT) ───────────────────────────
        plan_prompt = self._build_initial_prompt(goal, file_context)
        plan_response = self._call_model(session, plan_prompt)
        session.plan = plan_response
        self._print_block("📋", "PLAN", plan_response)

        # [AGENT_DONE] 이 plan 단계에서 나오는 건 비정상이므로 무시

        # ── Step 1..N. 반복 ──────────────────────────────
        feedback: Optional[str] = None
        for i in range(1, self.max_iterations + 1):
            self._print_header(session, i)

            prompt = self._build_iteration_prompt(session, feedback)
            feedback = None

            # Self-Correction 을 포함한 내부 재시도
            response = self._call_model(session, prompt)

            reason, act, observe_hint = self._parse_blocks(response)
            self._print_block("🧠", f"Reason #{i}", reason)
            self._print_block("🔨", f"Act #{i}",    act)

            # 액션 실행 + Observe 합성
            actions = self._execute_actions(session, act)
            observe_text = self._format_observe(observe_hint, actions)
            self._print_block("👁 ", f"Observe #{i}", observe_text)

            session.iterations.append(IterationRecord(
                idx=i, reason_text=reason, act_text=act,
                actions=actions, observe_text=observe_text,
            ))

            # Self-Correction: 액션 중 하나라도 실패 시 프롬프트에 에러 주입
            if self._has_code_failure(actions):
                corrected = self._self_correct_loop(session, actions)
                if corrected:  # 수정 성공 시 다음 iteration 으로
                    pass
                # 실패해도 다음 iteration 으로 진행 (observe 에 실패 기록됨)

            # [AGENT_DONE] 체크
            if self.done_token in response:
                session.stop_reason = AgentStopReason.DONE
                break

            # 토큰 압축
            self._compact_history_if_needed(session)

            # 사용자 개입 (턴 사이 프롬프트)
            choice, feedback = self._ask_continue()
            if choice == 's':
                session.stop_reason = AgentStopReason.USER_STOP
                break
            # 'c' → feedback = None 그대로
            # 'f' → feedback 에 주입됨

        else:
            # for-else: break 없이 끝까지 돌면 실행됨
            session.stop_reason = AgentStopReason.MAX_ITERATIONS

    except KeyboardInterrupt:
        session.stop_reason = AgentStopReason.USER_STOP
        print("\n\n⚠️  사용자 중단 (Ctrl+C)")
    except Exception as e:
        session.stop_reason = AgentStopReason.FATAL_ERROR
        print(f"\n❌ 에이전트 오류: {e}")

    # 요약을 메인 히스토리에 누적
    self._append_summary_to_main_history(session)
    self._print_final_summary(session)
    return session
```

#### 4.1.3 에이전트 시스템 프롬프트 (`_build_system_prompt()`)

AI 가 CoT / ReAct / `[AGENT_DONE]` 규약을 지키도록 강하게 지시한다.

```
당신은 자율 코딩 에이전트입니다. 주어진 상위 목표를 달성하기 위해
스스로 계획을 세우고 단계별로 실행합니다.

[응답 형식 — 반드시 준수]
첫 번째 응답(계획 수립)은 번호 매긴 목록으로 전체 PLAN 을 나열하세요.
이후 매 반복(iteration) 응답은 다음 세 블록을 순서대로 포함해야 합니다.

[REASON]
현재 상태를 분석하고 이번 단계에서 무엇을 할지 논리적으로 서술
(바로 직전 [OBSERVE] 결과를 반드시 참조)

[ACT]
이번 단계에서 수행할 구체적 행동:
- 파일 생성/수정:  ```filename:<경로>   ...   ```   블록
- 코드 실행:       ```python / ```bash / ```javascript 블록 (파일명 없음 → 임시 실행)
- 쉘 명령 실행:    라인 시작에 `$ <명령>` (한 줄에 한 명령)

[OBSERVE]
위 ACT 를 실행했을 때 기대되는 결과를 간단히 서술
(실제 실행 결과는 시스템이 다음 프롬프트에 주입합니다)

[완료 판정]
목표를 완전히 달성했다고 판단되면 응답 맨 끝에 정확히 다음 한 줄을 추가:
  [AGENT_DONE]

[Self-Correction]
[OBSERVE] 또는 시스템이 제공한 실행 결과에 오류가 포함된 경우,
다음 [REASON] 에서 원인을 진단하고 [ACT] 에서 수정 버전을 제시하세요.

[주의]
- 코드 블록 밖에서 장황하게 설명하지 마세요.
- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.
- 위험 명령(rm, mv, del, move 등)은 반드시 필요한 경우에만 사용하세요. 사용자가 거부할 수 있습니다.
```

#### 4.1.4 `_build_initial_prompt()` 구성 (Step 0 · PLAN 수립용)

```
[GOAL]
<원본 목표>

[FILE_CONTEXT]   ← <pattern> 지정 시에만
<ContextBuilder.build_context(file_patterns, include_tree=True) 결과 전문>

이 목표를 달성하기 위한 전체 PLAN 을 번호 매긴 목록으로 제시하세요.
PLAN 은 간결하게, 실행 가능한 단위로 쪼개세요.
```

> `[FILE_CONTEXT]` 블록은 **PLAN 호출 1회** 에만 전체 본문을 포함하며, 이후 iteration 프롬프트에는 매칭 파일 목록 요약만 재주입한다 (토큰 절약). `agent_history` 에는 이 블록이 누적되므로 이후 AI 가 계속 참조할 수 있다.

#### 4.1.4.1 `_build_iteration_prompt()` 구성 (Step 1..N)

```
[GOAL]
<원본 목표>

[PLAN]
<Step 0에서 수립된 계획>

[FILE_CONTEXT_REF]   ← <pattern> 지정 시에만
본 에이전트는 다음 파일들을 컨텍스트로 가지고 있습니다(전문은 이전 메시지 참조):
  - src/foo.py
  - src/bar.py

[HISTORY SUMMARY]
<agent_history 요약 — AGENT_COMPACT_AFTER 초과 시 AI로 압축한 텍스트>

[RECENT OBSERVATIONS]
<최근 2 iteration 의 Observe 결과 원문>

[USER_FEEDBACK]   ← 선택 시에만
<사용자 입력 원문>

이제 다음 iteration 의 [REASON] / [ACT] / [OBSERVE] 를 작성하세요.
목표를 달성했다면 [AGENT_DONE] 으로 마무리하세요.
```

#### 4.1.5 액션 실행 (`_execute_actions()`) 상세

```python
def _execute_actions(self, session, act_text):
    results: List[ActionResult] = []
    results += self._save_file_blocks(act_text)        # ```filename:path
    results += self._run_code_blocks(act_text)         # ```python / ```bash / ```javascript
    results += self._run_shell_lines(session, act_text) # $ <cmd>
    return results
```

**`_save_file_blocks`** — `ResponseParser.parse_and_save(act_text)` 를 호출. `rm`/`mv`/`del`/`move` 를 의미하는 특수 메타 블록(예: ` ```remove:path`)이 있다면 `_approve_dangerous()` 로 승인 후 `FileManager.delete_file()` 실행. *(1단계: 본 FSD 에서는 파일 삭제 전용 구문은 쉘 라인 `$ rm ...` 으로 통일 — 별도 구문 도입 안 함.)*

**`_run_code_blocks`** — `CodeExecutor.extract_code_from_response(act_text)` 로 `filepath is None` 인 블록만 실행. `self.code_executor.timeout` 은 `AGENT_CODE_TIMEOUT` 값으로 초기화된 `code_executor` 사용.

**`_run_shell_lines`** —
1. 정규식 `^\s*\$\s+(.+)$` 로 ACT 본문에서 쉘 라인 추출.
2. 각 명령의 `base_cmd` 가 `TerminalExecutor.DANGEROUS_COMMANDS` 에 포함되면:
   - `session.auto_approve_dangerous_shell == True` 이면 자동 승인
   - 아니면 `_approve_dangerous(session, 'auto_approve_dangerous_shell', label)` 호출
3. 승인 후 `terminal_executor.execute(cmd, allow_unsafe=<위험명령 여부>)` 실행.

#### 4.1.6 단건 승인 + 세션 자동 승인 (`_approve_dangerous()`)

```python
def _approve_dangerous(self, session, flag_attr: str, label: str) -> bool:
    """
    Returns True if approved (either y or A), False if rejected.
    'A' 선택 시 session 의 해당 flag 를 True 로 설정하여 이후 자동 승인.
    """
    prompt = f"\n⚠️  위험 액션 감지: {label}\n" \
             f"▶ 실행하시겠습니까? [y]es / [N]o / [A]lways (세션 내 자동 승인) : "
    try:
        ans = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if ans == 'a':
        setattr(session, flag_attr, True)
        return True
    return ans == 'y'
```

#### 4.1.7 Self-Correction 루프

```python
def _self_correct_loop(self, session, last_actions):
    """코드 실행 실패 시 동일 목표에 대해 최대 self_correct_max 회 재시도"""
    for attempt in range(1, self.self_correct_max + 1):
        fail_summary = self._format_failure(last_actions)
        correct_prompt = (
            f"[SELF_CORRECT attempt={attempt}/{self.self_correct_max}]\n"
            f"직전 [ACT] 실행 결과 다음 오류가 발생했습니다.\n"
            f"원인을 진단하고 수정된 [REASON] / [ACT] / [OBSERVE] 를 제시하세요.\n\n"
            f"{fail_summary}"
        )
        response = self._call_model(session, correct_prompt)
        _, act, _ = self._parse_blocks(response)
        last_actions = self._execute_actions(session, act)
        if not self._has_code_failure(last_actions):
            return True
    print(f"⚠️  Self-Correction {self.self_correct_max}회 실패 — 다음 iteration 으로 진행")
    return False
```

#### 4.1.8 `_ask_continue()` 턴 사이 프롬프트

```python
def _ask_continue(self) -> Tuple[str, Optional[str]]:
    try:
        ans = input("\n▶ [c]ontinue / [f]eedback / [s]top ? (c): ").strip().lower() or 'c'
    except (EOFError, KeyboardInterrupt):
        return ('s', None)
    if ans == 'f':
        print("💬 피드백 입력 (멀티라인, 종료: /end 또는 Esc+Enter):")
        feedback = self.cli_handler.get_multiline()
        return ('f', feedback or None)
    if ans == 's':
        return ('s', None)
    return ('c', None)
```

#### 4.1.9 히스토리 격리 & 요약 append

```python
def _call_model(self, session, user_prompt):
    """
    assistant.chat() 을 그대로 사용하되, 호출 전후로 메인 conversation_history 를
    격리한다. 에이전트 메시지는 session.agent_history 에만 누적.
    """
    saved_main = self.assistant.conversation_history
    saved_sys  = getattr(self.assistant, 'system_prompt', None)

    # 에이전트 전용 컨텍스트 주입
    self.assistant.conversation_history = list(session.agent_history)
    self.assistant.system_prompt = self._build_system_prompt()

    try:
        response = self.assistant.chat(
            user_prompt, streaming=self.streaming, include_context=False
        )
    finally:
        # assistant.chat() 이 agent_history 에 이미 추가했음 → 그대로 동기화
        session.agent_history = self.assistant.conversation_history
        self.assistant.conversation_history = saved_main
        if saved_sys is not None:
            self.assistant.system_prompt = saved_sys

    return response


def _append_summary_to_main_history(self, session):
    """루프 종료 시 메인 히스토리에 요약 1쌍 append"""
    user_msg = f"[/agents] 목표: {session.goal}"
    saved_files = [a.target for it in session.iterations for a in it.actions
                   if a.kind == "file" and a.success]
    bot_msg = (
        f"에이전트 실행 완료 ({session.stop_reason.value}, "
        f"{len(session.iterations)} iterations)\n"
        f"저장된 파일: {saved_files or '없음'}"
    )
    self.assistant.conversation_history.append({"role": "user",  "content": user_msg})
    self.assistant.conversation_history.append({"role": "model", "content": bot_msg})
```

### 4.2 `gemini-ai-chat-code.py` 변경

엔트리 포인트 `while True:` 루프의 명령 분기에 **하나의 elif** 추가.

```python
# 기존 /multiline 분기 근처에 추가 (대략 line 170 이후)
elif command == '/agents':
    # /agents stop : 실행 중이 아니면 안내, 실행 중이면 session.stop 요청
    if args.strip().lower() == 'stop':
        print("💡 에이전트는 현재 실행 중이 아닙니다. 루프 도중 Ctrl+C 로 중단하세요.")
        continue

    # FR-083-018 / FR-083-019: <pattern> 파싱 (/context 와 동일 규칙)
    file_patterns: list[str] = []
    if args.strip():
        if args.strip().startswith('['):
            try:
                end_idx = args.index(']')
                file_patterns = [p.strip() for p in args[1:end_idx].split(',') if p.strip()]
            except ValueError:
                print("❌ 닫는 대괄호 ']'가 없습니다.")
                continue
        else:
            file_patterns = args.split()

    # 목표 수집 (패턴 유무와 관계없이 항상 멀티라인)
    if file_patterns:
        print(f"🎯 목표를 입력하세요 — 컨텍스트 패턴: {file_patterns}")
    else:
        print("🎯 목표를 입력하세요 (멀티라인, 종료: /end 또는 Esc+Enter)")
    goal = cli_handler.get_multiline()
    if not goal or not goal.strip():
        print("❌ 목표가 비어있습니다.")
        continue

    from src.agent_runner import AgentRunner
    runner = AgentRunner(
        assistant=assistant,
        file_manager=assistant.file_manager,
        code_executor=assistant.code_executor,
        terminal_executor=assistant.terminal_executor,
        response_parser=assistant.response_parser,
        cli_handler=cli_handler,
        context_builder=assistant.context_builder,   # <pattern> 지원
        streaming=streaming,
    )
    session = runner.run(goal, file_patterns=file_patterns or None)
    last_response = ""  # 에이전트 산출물은 파일로 저장되었으므로 /save 대상 아님
```

**사용 예시**

| 입력 | 동작 |
|---|---|
| `/agents` | 패턴 없음 → 멀티라인 목표 수집 → 순수 목표 기반 에이전트 루프 |
| `/agents src/*.py` | 단일 패턴 → 멀티라인 목표 수집 → 매칭 .py 파일을 `[FILE_CONTEXT]` 로 주입 |
| `/agents src/*.py tests/*.py` | 공백 구분 다중 패턴 |
| `/agents [src/*.py, docs/*.md]` | 리스트 형식 다중 패턴 |
| `/agents stop` | 안내 메시지만 출력 (실행 중 중단은 Ctrl+C) |

> **`/agents stop` 의 의미**
> 루프 실행 중에는 메인 `while True` 가 입력을 받지 않으므로, 실제 중단은 `Ctrl+C` 로 처리된다. `/agents stop` 명령은 루프가 끝난 **이후에** 잘못 입력된 경우 친절한 안내 메시지를 표시하는 용도이다. 비동기 키 리스너는 1단계 범위 외이다.

### 4.3 `src/command_registry.py` 변경

```python
# _register_default_commands() 내 추가 위치 (파일 탐색 섹션 아래, /context 근처)
CommandInfo('/agents',      '자율 에이전트 루프 실행 (목표 멀티라인 입력, 선택적 파일 컨텍스트)',
            '/agents [pattern | [p1, p2, ...] | stop]',
            '[src/*.py, docs/*.md]'),
```

### 4.4 `.env.example` 추가

```env
# === 자율 에이전트 (/agents) ===
AGENT_MAX_ITERATIONS=10
AGENT_SELF_CORRECT_MAX=3
AGENT_COMPACT_AFTER=5
AGENT_CODE_TIMEOUT=30
AGENT_DONE_TOKEN=[AGENT_DONE]
```

---

## 5. 프로세스 흐름

### 5.1 전체 플로우

```
사용자: /agents [pattern?]
  │
  ├─ pattern 있음 → FilePatternMatcher 로 파일 목록 확정
  │                 ContextBuilder.build_context(file_patterns) → file_context
  │                 (0개 매칭 시 여기서 중단)
  │
  ▼
① 목표 멀티라인 입력 수집 (항상)
  │
  ▼
② AgentRunner.run(goal, file_patterns)
  │
  ├─► Step 0. PLAN 수립
  │     initial_prompt = [GOAL] + [FILE_CONTEXT if pattern] → PLAN 출력
  │
  ├─► Step 1..N. 반복 루프
  │     ┌──────────────────────────────────────────┐
  │     │ (a) iteration 프롬프트 생성                │
  │     │     (goal + plan + recent observations +   │
  │     │      optional user feedback)              │
  │     │ (b) assistant.chat() 호출                  │
  │     │ (c) [REASON] / [ACT] / [OBSERVE] 파싱     │
  │     │ (d) ACT 실행:                              │
  │     │     - ```filename:  → write_file          │
  │     │     - ```python/js/bash → code_executor   │
  │     │     - $ <cmd>       → terminal_executor   │
  │     │       (위험 명령은 y/N/A 승인 프롬프트)    │
  │     │ (e) 실제 Observe 합성 + 출력              │
  │     │ (f) 실패 시 Self-Correction (최대 3회)    │
  │     │ (g) [AGENT_DONE] 검사 → break             │
  │     │ (h) agent_history 압축 (>5)               │
  │     │ (i) 사용자 턴 사이 프롬프트 [c/f/s]       │
  │     └──────────────────────────────────────────┘
  │
  ▼
③ 루프 종료 (DONE / MAX_ITERATIONS / USER_STOP)
  │
  ▼
④ 최종 요약 출력 + 메인 history 에 요약 1쌍 append
```

### 5.2 시퀀스 다이어그램

```mermaid
sequenceDiagram
    participant U as User
    participant E as gemini-ai-chat-code.py
    participant R as AgentRunner
    participant A as GeminiCodeAssistant
    participant X as CodeExecutor / TerminalExecutor / FileManager

    U->>E: /agents [pattern?]
    alt pattern 지정됨
        E->>E: FilePatternMatcher.filter_files
        alt 0개 매칭
            E->>U: ❌ 매칭 파일 없음
            Note over E: 에이전트 미시작, 메인 루프 복귀
        else 1개 이상 매칭
            E->>E: ContextBuilder.build_context(file_patterns)
        end
    end
    E->>U: 🎯 멀티라인 목표 입력 요청
    U-->>E: goal (멀티라인)
    E->>R: run(goal, file_patterns)

    opt pattern 지정됨
        R->>U: 📂 매칭 파일 목록 표시
    end

    R->>A: chat(initial_prompt + [FILE_CONTEXT])      # PLAN
    A-->>R: PLAN (CoT)
    R->>U: 📋 PLAN 출력

    loop i = 1..MAX_ITERATIONS
        R->>A: chat(iteration_prompt)
        A-->>R: [REASON][ACT][OBSERVE]
        R->>U: 🧠 Reason / 🔨 Act 출력

        par 액션 실행
            R->>X: write_file / code.exec / shell.exec
            X-->>R: ActionResult
        end

        alt 실패 발생
            loop self-correct ≤ 3
                R->>A: chat(correct_prompt + error)
                A-->>R: 수정된 [ACT]
                R->>X: 재실행
            end
        end

        R->>U: 👁 Observe (실제 결과)

        alt [AGENT_DONE] 포함
            R->>U: ✅ 목표 달성
            break
        end

        R->>U: ▶ [c]/[f]/[s] ?
        U-->>R: 선택 + (피드백)
        alt stop
            break
        end
    end

    R->>A: conversation_history.append(요약)
    R->>U: 최종 요약
```

### 5.3 Self-Correction 세부

```
ACT 실행 → stderr 포함 실패
   │
   ▼
[SELF_CORRECT attempt=1/3] 프롬프트 조립
   ├─ 원본 목표 + 실패한 ACT + 에러 메시지
   │
   ▼
chat() → 수정된 [ACT]
   │
   ▼
재실행 → 성공? ─── yes ─→ 다음 iteration 으로
   │
   no
   ▼
attempt += 1, 3회까지 반복
   │
   ▼
3회 모두 실패 → ⚠️ 경고 출력 후 다음 iteration (Observe 에 실패 기록)
```

---

## 6. 에이전트 시스템 프롬프트 (전문)

`AgentRunner._build_system_prompt()` 가 반환하는 문자열은 4.1.3 절의 내용을 그대로 사용한다. 기존 `GeminiCodeAssistant.default_system_prompt` 는 격리된 `agent_history` 호출 시 에이전트 전용 프롬프트로 **교체**되며, 호출 후 원복된다(4.1.9 참조).

---

## 7. 사용자 출력 예시

### 7.1 정상 시나리오 (간단 목표, 2 iteration 만에 완료)

```
> /agents
🎯 목표를 입력하세요 (멀티라인, 종료: /end 또는 Esc+Enter)
python으로 1~100 소수 리스트 출력하는 코드를 만들고 실행해서 결과 확인해줘.
/end

🤖 에이전트 시작 — 목표:
  python으로 1~100 소수 리스트 출력하는 코드를 만들고 실행해서 결과 확인해줘.

📋 PLAN
─────────────────────────────────────────────
1. primes.py 에 1~100 범위 소수 판별 함수 작성
2. 결과를 stdout 으로 출력
3. 실행 결과 검증 후 완료

━━━ Iteration 1/10 ━━━
🧠 Reason #1
─────────────────────────────────────────────
primes.py 파일을 생성하고 단순한 시브(sieve) 로직을 사용한다.

🔨 Act #1
─────────────────────────────────────────────
```filename:primes.py
def primes(n):
    sieve = [True]*(n+1)
    sieve[0]=sieve[1]=False
    for i in range(2, int(n**0.5)+1):
        if sieve[i]:
            for j in range(i*i, n+1, i): sieve[j]=False
    return [i for i,v in enumerate(sieve) if v]

print(primes(100))
```

```python
exec(open('primes.py').read())
```

👁  Observe #1
─────────────────────────────────────────────
✅ 파일 저장됨: primes.py
✅ 코드 실행 성공 (returncode=0)
stdout: [2, 3, 5, 7, 11, ..., 97]

▶ [c]ontinue / [f]eedback / [s]top ? (c): c

━━━ Iteration 2/10 ━━━
🧠 Reason #2
─────────────────────────────────────────────
primes.py 가 정상 출력됨. 목표 달성.

🔨 Act #2
─────────────────────────────────────────────
(추가 액션 없음)

👁  Observe #2
─────────────────────────────────────────────
목표 달성 확인. [AGENT_DONE]

✅ 에이전트 완료 (stop_reason=done, 2 iterations)
📁 생성된 파일: primes.py
============================================================
```

### 7.2 Self-Correction 발동 예시

```
━━━ Iteration 3/10 ━━━
🧠 Reason #3
─────────────────────────────────────────────
블록 회전 로직을 추가한다.

🔨 Act #3
─────────────────────────────────────────────
```filename:tetris/piece.py
... (회전 함수에 오타: ratate → rotate)
```
```python
import tetris.piece; tetris.piece.Piece().ratate()
```

👁  Observe #3
─────────────────────────────────────────────
❌ 코드 실행 실패 (returncode=1)
stderr: AttributeError: 'Piece' object has no attribute 'ratate'

🔄 Self-Correction [1/3]
🧠 Reason (correct)
─────────────────────────────────────────────
메서드 이름 오타(ratate → rotate) 수정.

🔨 Act (correct)
─────────────────────────────────────────────
```filename:tetris/piece.py
... def rotate(self): ...
```

👁  Observe (correct)
─────────────────────────────────────────────
✅ 코드 실행 성공 (returncode=0)

▶ [c]ontinue / [f]eedback / [s]top ? (c):
```

### 7.3 위험 명령 승인 프롬프트

```
🔨 Act #5
─────────────────────────────────────────────
$ rm -rf build/

⚠️  위험 액션 감지: shell 'rm -rf build/'
▶ 실행하시겠습니까? [y]es / [N]o / [A]lways (세션 내 자동 승인) : A

✅ 명령 실행 성공 (returncode=0)
(이후 세션 동안 rm/mv 등 위험 명령 자동 승인)
```

### 7.4 사용자 피드백 주입

```
▶ [c]ontinue / [f]eedback / [s]top ? (c): f
💬 피드백 입력 (멀티라인, 종료: /end 또는 Esc+Enter):
블록이 좌우로 안 움직여. 키보드 입력 핸들러 추가해줘.
/end

━━━ Iteration 4/10 ━━━
🧠 Reason #4
─────────────────────────────────────────────
사용자 피드백 반영: pygame.KEYDOWN 핸들러를 추가한다.
...
```

### 7.5 `/agents stop` (실행 중 아님)

```
> /agents stop
💡 에이전트는 현재 실행 중이 아닙니다. 루프 도중 Ctrl+C 로 중단하세요.
```

### 7.6 `<pattern>` 모드 — 기존 코드 리팩토링 에이전트

```
> /agents [src/*.py, tests/test_*.py]
🎯 목표를 입력하세요 — 컨텍스트 패턴: ['src/*.py', 'tests/test_*.py']
src 의 모든 파일을 읽고 타입 힌트가 빠진 함수에 타입 힌트를 추가해줘.
테스트가 모두 통과하는지 확인하고 완료해줘.
/end

🤖 에이전트 시작 — 목표:
  src 의 모든 파일을 읽고 타입 힌트가 빠진 함수에 타입 힌트를 추가해줘.
  테스트가 모두 통과하는지 확인하고 완료해줘.

📂 컨텍스트에 포함된 파일 7개:
  - src/file_manager.py
  - src/context_builder.py
  - ...
  - tests/test_file_manager.py

📋 PLAN
─────────────────────────────────────────────
1. 각 파일에서 타입 힌트 누락 함수 목록화
2. file_manager.py 부터 타입 힌트 추가
3. pytest 실행하여 회귀 없는지 검증
4. 전체 파일 동일 절차 반복

━━━ Iteration 1/10 ━━━
🧠 Reason #1
─────────────────────────────────────────────
file_manager.py 의 read_file / write_file / list_files 에 반환 타입이 없음.
먼저 이 3개 함수부터 수정한다.

🔨 Act #1
─────────────────────────────────────────────
```filename:src/file_manager.py
... (타입 힌트 추가된 전체 파일 내용) ...
```
```bash
pytest tests/test_file_manager.py -q
```

👁  Observe #1
─────────────────────────────────────────────
✅ 파일 저장됨: src/file_manager.py
✅ 코드 실행 성공 (returncode=0)
stdout: 14 passed in 0.21s

▶ [c]ontinue / [f]eedback / [s]top ? (c): c
...
```

### 7.7 `<pattern>` 매칭 0개

```
> /agents src/nonexistent*.py
🎯 목표를 입력하세요 — 컨텍스트 패턴: ['src/nonexistent*.py']
리팩토링해줘
/end
❌ 패턴 ['src/nonexistent*.py'] 에 해당하는 파일이 없습니다.
> _
```

---

## 8. 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-01 | `/agents` 입력 후 빈 목표 제출 | "목표가 비어있습니다" 경고, 에이전트 미시작 |
| T-02 | 단순 목표(소수 출력) | 2~3 iteration 내 `[AGENT_DONE]` 로 종료 |
| T-03 | AI 응답에 `[REASON]/[ACT]/[OBSERVE]` 중 하나 누락 | 관대하게 파싱(빈 블록 허용), Reason/Act 만 있어도 실행 |
| T-04 | 코드 실행 실패 1회 → 2회차 성공 | Self-Correction `[1/3]` 메시지 후 성공 |
| T-05 | 코드 실행 실패 3회 연속 | Self-Correction 종료 후 `⚠️` 경고, 다음 iteration 으로 진행 |
| T-06 | `AGENT_MAX_ITERATIONS=3` 설정 후 `[AGENT_DONE]` 안 나는 목표 | 3 iteration 후 `max_iterations` 사유로 종료 |
| T-07 | iteration 도중 Ctrl+C | `user_stop` 사유로 즉시 종료, 현재까지 요약 출력 |
| T-08 | 위험 명령 `rm -rf` 액션 → `N` 응답 | 명령 미실행, Observe 에 "거부됨" 기록, 다음 iteration 진행 |
| T-09 | 위험 명령 첫 요청 `A` 응답 → 이후 동일 세션에서 두 번째 위험 명령 | 두 번째는 프롬프트 없이 자동 승인 |
| T-10 | iteration 종료 후 `f` 입력 → 피드백 제출 | 다음 프롬프트에 `[USER_FEEDBACK]` 블록 포함, AI 응답에 반영 |
| T-11 | `agent_history` 길이가 `AGENT_COMPACT_AFTER` 초과 | 압축 요약 실행, 다음 iteration 프롬프트에 요약본 사용 |
| T-12 | 루프 종료 후 메인 `conversation_history` 확인 | 에이전트 내부 Reason/Act 세부는 없고, 요약 1쌍(user + model)만 추가됨 |
| T-13 | 루프 중 `assistant.system_prompt` 가 에이전트 전용으로 교체되었다가 종료 후 원복되는지 확인 | 원복 완료 |
| T-14 | `/agents stop` 을 루프 외부에서 입력 | "실행 중인 에이전트 없음" 안내 |
| T-15 | `/help` 에 `/agents` 가 노출 | CommandRegistry 에 등록 확인 |
| T-16 | `/agents src/*.py` 단일 패턴 + 멀티라인 목표 | 매칭 파일 목록 출력, `[FILE_CONTEXT]` 가 초기 프롬프트에 포함 |
| T-17 | `/agents [src/*.py, docs/*.md]` 리스트 구문 | 두 패턴 모두 매칭되어 파일 목록에 포함 |
| T-18 | `/agents src/*.py tests/*.py` 공백 구분 다중 패턴 | 두 패턴 모두 매칭 |
| T-19 | `/agents nonexistent*.py` (매칭 0개) | ❌ 안내 메시지 후 에이전트 미시작, 메인 루프로 복귀 |
| T-20 | `/agents [src/*.py` (닫히지 않은 대괄호) | ❌ "닫는 대괄호 ']'가 없습니다." 안내, 에이전트 미시작 |
| T-21 | `/agents <pattern>` 후 멀티라인 입력 비어있음 | ❌ "목표가 비어있습니다." 안내, 에이전트 미시작 |
| T-22 | `<pattern>` 모드에서 PLAN 프롬프트 1회 호출 시에만 `[FILE_CONTEXT]` 전문이 포함, 이후 iteration 프롬프트에는 `[FILE_CONTEXT_REF]` 요약만 포함 | 토큰 절약 확인 |

---

## 9. 파일 변경 목록

| 파일 | 변경 유형 | 설명 |
|---|---|---|
| `src/agent_runner.py` | **신규** | `AgentRunner`, `AgentSession`(file_patterns/matched_files 포함), `IterationRecord`, `ActionResult`, `AgentStopReason` |
| `src/__init__.py` | 수정 | `AgentRunner` 재export (선택) |
| `gemini-ai-chat-code.py` | 수정 | `/agents [pattern]` 분기 추가 (패턴 파싱 포함, 약 35줄) |
| `src/command_registry.py` | 수정 | `CommandInfo('/agents', ...)` 추가 — `[pattern]` 사용법 명시 |
| `.env.example` | 수정 | `AGENT_*` 환경변수 5개 추가 |
| `tests/test_agent_runner.py` | **신규** | T-01~T-15 중 순수 로직 테스트(파싱, self-correct 판정, 히스토리 격리, 요약 append 등) |
| `claude-ai-chat-code.py` | **변경 없음** (2단계에서 추가) | — |
| `gen-ai-chat-code.py` | **변경 없음** (2단계에서 추가) | — |

---

## 10. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | `AGENT_DONE` 은 AI 의 자발적 출력에 의존한다. 모델이 규약을 무시하면 `MAX_ITERATIONS` 에 의해서만 종료된다. | 시스템 프롬프트에 **정확한 토큰 문자열** 과 **마지막 줄** 위치를 명시. `AGENT_MAX_ITERATIONS` 를 안전장치로 유지. |
| 2 | 루프 실행 중 메인 `while True` 가 블로킹이므로 `/agents stop` 의 비동기 중단은 `Ctrl+C` 에 의존한다. | 1단계에선 `Ctrl+C` 로 한정. 비동기 키 리스너 도입은 별도 FSD. |
| 3 | `assistant.conversation_history` 를 임시 교체/원복하는 방식은 동시 호출(재진입)에 안전하지 않다. | CLI 특성상 재진입 불가능. 경고 주석 추가. 추후 `GeminiCodeAssistant.chat()` 에 `history` / `system_prompt` 파라미터를 추가하는 리팩토링 고려. |
| 4 | 토큰 누적으로 비용 증가 가능 (`AGENT_MAX_ITERATIONS=10` × 긴 히스토리). | `AGENT_COMPACT_AFTER` 로 압축. 압축 자체도 토큰을 사용하므로 값은 보수적으로 `5` 로 설정. |
| 5 | `CodeExecutor.execute()` 는 30초 timeout 으로 고정이나 환경변수 `AGENT_CODE_TIMEOUT` 를 반영하려면 `CodeExecutor(timeout=…)` 생성 시점에 재생성하거나 별도 인스턴스를 준비해야 함. | `AgentRunner.__init__` 에서 `CodeExecutor(workspace, timeout=AGENT_CODE_TIMEOUT)` 로 **에이전트 전용 인스턴스** 를 생성. 기존 `assistant.code_executor` 는 건드리지 않음. |
| 6 | 쉘 명령 `$ <cmd>` 파싱이 여러 줄 명령(heredoc 등)을 지원하지 않는다. | 1단계: 단일 라인 명령만 지원. 복잡한 쉘 스크립트는 `bash` 코드 블록으로 유도. |
| 7 | Self-Correction 은 **직전 iteration 실패** 에만 발동하며, 여러 iteration 에 걸친 논리 오류는 해결하지 못할 수 있다. | 사용자 피드백(`f`) 으로 보강. 향후 Reflexion 스타일의 장기 기억 메커니즘 검토. |
| 8 | ` ```filename:` 블록 저장은 확인 없이 자동 덮어쓰기 한다 (FR-083 기준 "자동 저장"). | 기존 `/auto_context` 와 동일 동작. 중요 파일 손실 우려 시 `/agents` 실행 전 git commit 권장 — 시스템 프롬프트 안내문에 포함. |
| 9 | `<pattern>` 모드에서 매칭 파일의 총 크기가 `TokenManager.MAX_TOKENS_GEMINI` 를 초과하면 `ContextBuilder` 내부에서 일부 파일이 **잘려 들어갈 수 있다** (기존 `/context` 와 동일). | 에이전트 출력에서 "일부 파일 생략됨" 메시지가 `ContextBuilder` 로부터 전달되면 그대로 사용자에게 노출. 향후 패턴 모드 전용 chunking 전략 검토. |
| 10 | `<pattern>` 모드는 `/auto_context` 처럼 파일 단위 1-by-1 루프가 **아니다**. 대량의 파일을 개별 처리하려면 여전히 `/auto_context` 를 사용해야 한다. | 도움말 메시지와 본 FSD 에 명시. 향후 `/agents --per-file <pattern>` 같은 옵션 도입 검토. |

---

## 11. 후속 작업 (2단계 이상)

| 단계 | 내용 | 별도 FSD |
|---|---|---|
| 2 | `claude-ai-chat-code.py`, `gen-ai-chat-code.py` 에 동일 `/agents` 분기 복제 | FSD v1.0.084 예정 |
| 3 | 세션 상태 JSON 직렬화 + `/agents resume` | FSD v1.0.085 예정 |
| 4 | 비동기 `/agents stop` (루프 중 입력 수신) | FSD v1.0.086 예정 |
| 5 | Tool Calling 도입 (Gemini `functionDeclarations`) 으로 ReAct 의 ACT 를 구조화 JSON 으로 전환 | 별도 검토 |

---

## 12. 승인

- [ ] 요구사항 검토 (2026-04-18)
- [ ] 구현 (예정)
- [ ] 테스트 (`tests/test_agent_runner.py`)
- [ ] 문서 반영 (`RELEASE_v1.0.083.md`)
