"""
AgentRunner - 자율 에이전트 루프 실행기 (FSD v1.0.083)

CoT / ReAct / Self-Correction 을 적용해 사용자가 제시한 상위 목표를
Reason → Act → Observe → Refine 사이클로 반복 수행한다.

Provider 에 독립적으로 설계되었으며, `assistant.chat(prompt, streaming, include_context)`
및 `assistant.conversation_history`, `assistant.system_prompt` 인터페이스만 요구한다.
"""

import os
import platform
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .agent_action_dispatcher import AgentActionDispatcher
from .agent_input_listener import AgentInputListener
from .code_executor import CodeExecutor
from .os_utils import get_os_shell_hint


class AgentStopReason(Enum):
    DONE = "done"                        # [AGENT_DONE]
    MAX_ITERATIONS = "max_iterations"    # AGENT_MAX_ITERATIONS 초과
    USER_STOP = "user_stop"              # /agents stop 또는 Ctrl+C
    USER_ABORT_ON_ERROR = "user_abort"   # 에러 프롬프트에서 사용자가 s 선택
    FATAL_ERROR = "fatal_error"          # 복구 불가 예외
    # FSD v1.0.100
    BYPASS_TIMEOUT = "bypass_timeout"           # 시간 예산 초과
    BYPASS_STAGNATION = "bypass_stagnation"     # 진행 정체 탐지
    BYPASS_LOOP_DETECTED = "bypass_loop"        # 반복 루프 탐지
    BYPASS_DANGEROUS_LIMIT = "bypass_danger_limit"  # 위험 액션 한도 초과


class _BypassAbort(Exception):
    """bypass 안전장치(S5) 내부 전용 예외 — 스택 트레이스 미노출."""


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
    file_patterns: List[str] = field(default_factory=list)
    matched_files: List[str] = field(default_factory=list)
    iterations: List[IterationRecord] = field(default_factory=list)
    agent_history: List[Dict[str, str]] = field(default_factory=list)
    auto_approve_dangerous_shell: bool = False
    auto_approve_file_mutation: bool = False
    # FSD v1.0.100
    bypass_approvals: bool = False
    bypass_started_at: Optional[float] = None   # time.monotonic() — 직렬화 시 None 처리
    bypass_dangerous_count: int = 0
    stop_reason: Optional[AgentStopReason] = None
    # FSD v1.0.101 — 런타임 캐시 (JSON 직렬화에서 제외)
    effective_max_iterations: Optional[int] = None


class AgentRunner:
    """에이전트 루프 실행기 (Provider 독립)

    주의: `assistant.conversation_history` / `system_prompt` 를 임시 교체/원복하는
    방식이므로 동시 호출(재진입)에 안전하지 않다. CLI 특성상 재진입은 발생하지 않는다.
    """

    RE_REASON  = re.compile(r"\[REASON\](.*?)(?=\[ACT\]|\[OBSERVE\]|\[AGENT_DONE\]|\Z)", re.DOTALL)
    RE_ACT     = re.compile(r"\[ACT\](.*?)(?=\[OBSERVE\]|\[AGENT_DONE\]|\Z)", re.DOTALL)
    RE_OBSERVE = re.compile(r"\[OBSERVE\](.*?)(?=\[AGENT_DONE\]|\Z)", re.DOTALL)
    RE_SHELL   = re.compile(r"^\s*\$\s+(.+)$", re.MULTILINE)
    RE_FILENAME_BLOCK = re.compile(r"`{3,}filename:([^\n]+)", re.MULTILINE)

    SEP = "─" * 60

    def __init__(
        self,
        assistant,
        file_manager,
        code_executor,
        terminal_executor,
        response_parser,
        cli_handler,
        context_builder=None,
        streaming: bool = True,
        assistant_role: str = "model",
    ):
        self.assistant = assistant
        self.file_manager = file_manager
        self.terminal_executor = terminal_executor
        self.response_parser = response_parser
        self.cli_handler = cli_handler
        self.context_builder = context_builder
        self.streaming = streaming
        self.assistant_role = assistant_role

        self.max_iterations   = int(os.getenv("AGENT_MAX_ITERATIONS", "10"))
        self.self_correct_max = int(os.getenv("AGENT_SELF_CORRECT_MAX", "3"))
        self.compact_after    = int(os.getenv("AGENT_COMPACT_AFTER", "5"))
        self.code_timeout     = int(os.getenv("AGENT_CODE_TIMEOUT", "60"))
        self.done_token       = os.getenv("AGENT_DONE_TOKEN", "[AGENT_DONE]")
        # FSD v1.0.100 bypass 안전장치
        self.bypass_timeout_sec       = int(os.getenv("AGENT_BYPASS_TIMEOUT", "1800"))
        self.bypass_stagnation_window = int(os.getenv("AGENT_BYPASS_STAGNATION_N", "3"))
        self.bypass_loop_window       = int(os.getenv("AGENT_BYPASS_LOOP_N", "3"))
        self.bypass_max_dangerous     = int(os.getenv("AGENT_BYPASS_MAX_DANGEROUS", "5"))

        # 에이전트 전용 CodeExecutor (AGENT_CODE_TIMEOUT 반영)
        self.code_executor = CodeExecutor(
            self.file_manager.workspace_dir, timeout=self.code_timeout
        )

        # FSD v1.0.107: 지능형 디스패처
        self._dispatcher = AgentActionDispatcher(self)

        # 비동기 stop 리스너 (FSD v1.0.087)
        self._input_listener = AgentInputListener()

    # ─── 진입점 ──────────────────────────────────────────────
    def run(
        self,
        goal: str = "",
        file_patterns: Optional[List[str]] = None,
        resume_session: Optional["AgentSession"] = None,
        bypass_approvals: bool = False,
        max_iterations_override: Optional[int] = None,   # FSD v1.0.101
    ) -> "AgentSession":
        auto_save_interval = int(os.getenv("AGENT_AUTO_SAVE_INTERVAL", "3"))

        # ── Resume 분기 ──────────────────────────────────────
        if resume_session is not None:
            session = resume_session
            session.stop_reason = None  # 이전 종료 사유 초기화 (P5, 이슈#5)
            session.auto_approve_dangerous_shell = False  # 보안 리셋 (이슈#5)
            session.auto_approve_file_mutation = False
            # FR-100-11: bypass 는 resume 시 항상 초기화 — 명시적 -ba 재지정 필요
            session.bypass_approvals = False
            session.bypass_started_at = None
            session.bypass_dangerous_count = 0
            # FR-101-13: 이전 오버라이드 재활성 방지
            session.effective_max_iterations = None
            start_iteration = len(session.iterations) + 1
            file_context = ""
            print(f"\n🤖 에이전트 재개 — iteration {start_iteration} 부터 계속합니다.")
            print(f"  목표: {session.goal}")
            print(f"  이전 PLAN:\n{session.plan}\n")
        else:
            # ── 신규 세션 ─────────────────────────────────────
            file_context = ""
            matched_rel_paths: List[str] = []

            if file_patterns:
                if self.context_builder is None:
                    print("⚠️  ContextBuilder 미주입 — <pattern> 모드 비활성화")
                else:
                    try:
                        from .file_pattern_matcher import FilePatternMatcher
                        matcher = FilePatternMatcher(self.file_manager.workspace_dir)
                        all_files = self.file_manager.list_files()
                        matched = matcher.filter_files(all_files, file_patterns)
                        if not matched:
                            print(f"❌ 패턴 {file_patterns} 에 해당하는 파일이 없습니다.")
                            session = AgentSession(goal=goal, file_patterns=file_patterns)
                            session.stop_reason = AgentStopReason.FATAL_ERROR
                            return session
                        matched_rel_paths = [
                            str(p.relative_to(self.file_manager.workspace_dir)).replace("\\", "/")
                            for p in matched
                        ]
                        file_context = self.context_builder.build_context(
                            include_tree=True, file_patterns=file_patterns
                        ) or ""
                    except Exception as e:
                        print(f"⚠️  파일 컨텍스트 구성 실패: {e}")

            session = AgentSession(
                goal=goal,
                file_patterns=file_patterns or [],
                matched_files=matched_rel_paths,
            )
            start_iteration = 1

            print(f"\n🤖 에이전트 시작 — 목표:\n  {goal}\n")
            if matched_rel_paths:
                print(f"📂 컨텍스트에 포함된 파일 {len(matched_rel_paths)}개:")
                for p in matched_rel_paths:
                    print(f"  - {p}")
                print()

        # Resume 시 matched_files 존재 여부 경고 (P4)
        if resume_session is not None and session.matched_files:
            try:
                from .agent_session_store import AgentSessionStore
                store = AgentSessionStore(str(self.file_manager.workspace_dir))
                missing = store.validate_matched_files(session)
                if missing:
                    print(f"⚠️  다음 파일이 현재 워크스페이스에 없습니다:")
                    for f in missing:
                        print(f"  - {f}")
                    print("  에이전트는 이 파일들이 존재하지 않음을 인지하지 못할 수 있습니다.\n")
            except Exception:
                pass

        # FSD v1.0.101: 오버라이드 적용 (지역 변수로만 — 인스턴스 상태 불변)
        effective_max = (
            max_iterations_override
            if (max_iterations_override and max_iterations_override >= 1)
            else self.max_iterations
        )
        if max_iterations_override and max_iterations_override >= 1:
            print(f"🔧 max_iterations 오버라이드: {effective_max} (기본 {self.max_iterations})")
        session.effective_max_iterations = effective_max

        # bypass_approvals 인자로 시작 시점 진입 (신규/resume 공통)
        if bypass_approvals:
            self._enter_bypass_mode(session)

        # 비동기 stop 리스너 시작 (TTY 가 아니면 자동 비활성)
        self._input_listener.clear_stop()
        self._input_listener.start()
        if self._input_listener.enabled:
            print("💡 루프 중 's' 키로 안전하게 중단할 수 있습니다 (Ctrl+C 도 여전히 유효).")

        try:
            # ── Step 0. PLAN (신규 세션만) ──────────────────
            if resume_session is None:
                plan_prompt = self._build_initial_prompt(goal, file_context)
                plan_response = self._call_model(session, plan_prompt)
                session.plan = plan_response
                self._print_block("📋", " PLAN", plan_response)

            # ── Step 1..N. 반복 ──────────────────────────────
            feedback: Optional[str] = None
            completed = False

            for i in range(start_iteration, effective_max + 1):
                # ── 체크포인트 1: iteration 시작 전 ──
                if self._check_async_stop(session):
                    completed = True
                    break

                self._print_header(session, i)

                prompt = self._build_iteration_prompt(session, feedback)
                feedback_used = feedback
                feedback = None

                response = self._call_model(session, prompt)

                # ── 체크포인트 2: 모델 호출 후 ──
                if self._check_async_stop(session):
                    completed = True
                    break

                reason, act, observe_hint = self._parse_blocks(response)
                self._print_block("🧠", f" Reason #{i}", reason or "(없음)")
                self._print_block("🔨", f" Act #{i}", act or "(없음)")

                actions = self._execute_actions(session, act)

                # Self-Correction: 실패한 액션이 있으면 최대 N회 재시도
                if self._has_code_failure(actions):
                    corrected_actions = self._self_correct_loop(session, actions)
                    if corrected_actions:
                        actions = actions + corrected_actions

                observe_text = self._format_observe(observe_hint, actions)
                self._print_block("👁", f" Observe #{i}", observe_text)

                session.iterations.append(IterationRecord(
                    idx=i,
                    reason_text=reason,
                    act_text=act,
                    actions=actions,
                    observe_text=observe_text,
                    user_feedback=feedback_used,
                ))

                # 중간 자동 저장 (P8)
                if auto_save_interval > 0 and i % auto_save_interval == 0:
                    self._auto_save(session)

                # [AGENT_DONE] 체크
                if self.done_token in response:
                    session.stop_reason = AgentStopReason.DONE
                    print(f"\n✅ 에이전트가 목표 달성을 선언했습니다 ({self.done_token}).")
                    completed = True
                    break

                # ── 체크포인트 3: 액션 실행 후 ──
                if self._check_async_stop(session):
                    completed = True
                    break

                self._compact_history_if_needed(session)

                # ── bypass 모드: 안전장치 검사 후 자동 진행 ──
                if session.bypass_approvals:
                    brk = self._check_bypass_safety(session)
                    if brk is not None:
                        session.stop_reason = brk
                        completed = True
                        break
                    continue

                # 사용자 턴 사이 프롬프트 (동기 input — 리스너 일시 정지)
                with self._input_listener.paused():
                    choice, fb = self._ask_continue()
                if choice == 's':
                    session.stop_reason = AgentStopReason.USER_STOP
                    completed = True
                    break
                if choice == 'f':
                    feedback = fb
                if choice == 'b':
                    self._enter_bypass_mode(session)

            if not completed and session.stop_reason is None:
                session.stop_reason = AgentStopReason.MAX_ITERATIONS
                print(f"\n⚠️  최대 iteration ({effective_max}) 초과 — 한도 도달.")

        except KeyboardInterrupt:
            session.stop_reason = AgentStopReason.USER_STOP
            print("\n\n⚠️  사용자 중단 (Ctrl+C)")
            if self._input_listener.enabled:
                print("💡 다음부터는 's' 키로도 안전하게 중단할 수 있습니다.")
            self._auto_save(session)
        except _BypassAbort as e:
            # stop_reason 은 _run_shell_lines 에서 이미 설정됨 — 덮어쓰지 않음
            print(f"\n🛑 Bypass 안전장치 발동: {e}")
        except Exception as e:
            session.stop_reason = AgentStopReason.FATAL_ERROR
            print(f"\n❌ 에이전트 오류: {e}")
        finally:
            self._input_listener.stop()

        self._auto_save(session)
        self._append_summary_to_main_history(session)
        self._print_final_summary(session)
        return session

    def _check_async_stop(self, session: AgentSession) -> bool:
        """비동기 stop 이 요청되었는지 확인하고, 요청이면 세션에 표시한다."""
        if not self._input_listener.is_stop_requested():
            return False
        session.stop_reason = AgentStopReason.USER_STOP
        print("\n\n⚠️  사용자 중단 (비동기 stop — 's' 키).")
        return True

    # ─── Bypass Approvals (FSD v1.0.100) ────────────────────
    def _enter_bypass_mode(self, session: AgentSession) -> None:
        """bypass 플래그 세팅 + auto-approve 통합 + 시작 시각 기록."""
        import time as _time
        session.bypass_approvals = True
        session.auto_approve_dangerous_shell = True
        session.auto_approve_file_mutation = True
        session.bypass_started_at = _time.monotonic()
        mx = session.effective_max_iterations or self.max_iterations
        remaining = mx - len(session.iterations)
        print("\n" + "━" * 60)
        print("🚀 BYPASS APPROVALS 활성화")
        print(f"  남은 iteration: 최대 {remaining} 회")
        print(f"  시간 예산      : {self.bypass_timeout_sec}초 "
              f"(env AGENT_BYPASS_TIMEOUT)")
        print(f"  위험 액션 한도 : {self.bypass_max_dangerous} 회 "
              f"(env AGENT_BYPASS_MAX_DANGEROUS)")
        print("  중단 방법      : 's' 키 또는 Ctrl+C")
        print("━" * 60)

    def _check_bypass_safety(self, session: AgentSession) -> Optional[AgentStopReason]:
        """S2/S3/S4 안전장치 검사. 위반 시 해당 AgentStopReason 반환, 정상 시 None."""
        import time as _time

        # S2: 시간 예산
        if session.bypass_started_at is not None:
            elapsed = _time.monotonic() - session.bypass_started_at
            if elapsed > self.bypass_timeout_sec:
                print(f"\n⏱️  Bypass 시간 예산 초과 "
                      f"({elapsed:.0f}s > {self.bypass_timeout_sec}s) — 루프 종료.")
                return AgentStopReason.BYPASS_TIMEOUT

        # S3: 진행 정체 탐지
        if self._check_stagnation(session):
            print(f"\n⚠️  Bypass 정체 탐지 "
                  f"({self.bypass_stagnation_window}회 연속 성공 액션 없음) — 루프 종료.")
            return AgentStopReason.BYPASS_STAGNATION

        # S4: 반복 루프 탐지
        if self._check_loop(session):
            print(f"\n⚠️  Bypass 루프 탐지 "
                  f"({self.bypass_loop_window}회 동일 ACT) — 루프 종료.")
            return AgentStopReason.BYPASS_LOOP_DETECTED

        return None

    def _check_stagnation(self, session: AgentSession) -> bool:
        """최근 N iteration 에 성공 액션이 하나도 없으면 True."""
        if len(session.iterations) < self.bypass_stagnation_window:
            return False
        recent = session.iterations[-self.bypass_stagnation_window:]
        for rec in recent:
            if any(a.success for a in rec.actions):
                return False
        return True

    def _check_loop(self, session: AgentSession) -> bool:
        """최근 K iteration 의 ACT 텍스트 해시가 모두 동일하면 True."""
        if len(session.iterations) < self.bypass_loop_window:
            return False
        import hashlib
        recent = session.iterations[-self.bypass_loop_window:]
        hashes = {
            hashlib.md5(rec.act_text.encode("utf-8")).hexdigest()
            for rec in recent
        }
        return len(hashes) == 1

    def _auto_save(self, session: "AgentSession") -> None:
        try:
            from .agent_session_store import AgentSessionStore
            store = AgentSessionStore(str(self.file_manager.workspace_dir))
            path = store.save(session)
            print(f"\n💾 세션 저장: {path.name}")
        except Exception as e:
            print(f"\n⚠️  세션 저장 실패: {e}")

    # ─── 프롬프트 구성 ───────────────────────────────────────
    def _build_system_prompt(self) -> str:
        """FSD v1.0.115: 시스템 프롬프트 — 의사결정 트리 + 선택지 A-1/A-2/B/C."""
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
            "5줄 이내. 직전 [OBSERVE] 인용 + 이번 단계 의도.\n\n"

            "[ACT — 의사결정 트리]\n"
            "- 무엇을 해야 하는지에 따라 1~3개의 선택지를 고르세요.\n\n"
            "  파일을 만들거나 바꿔야 하는가?\n"
            "    └─ YES\n"
            "        ├─ 신규 파일?                          → 선택지 A-1 (filename)\n"
            "        ├─ 기존 파일을 일부만 수정 (변경 < 40%)?  → 선택지 A-2 (patch) **권장**\n"
            "        └─ 기존 파일을 사실상 다시 쓰기?          → 선택지 A-1 (filename)\n"
            "    └─ NO\n"
            "        ├─ 짧은 코드를 한 번 돌려 결과만 보고 싶은가?  → 선택지 B\n"
            "        └─ OS / Git / 패키지 매니저 명령이 필요한가? → 선택지 C\n\n"

            "- == 선택지 A-1. 파일 전문 (신규 또는 대규모 재작성) ==\n"
            "  ```filename:<경로/파일명.확장자>\n... 파일 전문 ...\n```\n"
            "  - 예시 :\n"
            "  ```filename:src/utils.py\ndef add(a, b):\n    return a + b\n```\n\n"

            "  - 한 블록에 한 파일. 워크스페이스 상대경로.\n"
            "  - 줄바꿈·인코딩 원본 그대로. 언어 태그를 섞지 마세요.\n\n"

            "- == 선택지 A-2. 파일 패치 (기존 파일의 부분 수정) ==\n"
            "  ```patch:<경로/파일명.확장자>\n"
            "  <<<<<<< SEARCH\n"
            "  (원본에 있는 텍스트 블록 — 한 곳에서만 매칭되도록 충분한 컨텍스트 포함)\n"
            "  =======\n"
            "  (바뀐 텍스트 블록)\n"
            "  >>>>>>> REPLACE\n"
            "  ```\n"
            "  - 한 펜스에 같은 파일의 여러 SEARCH/REPLACE 쌍을 넣을 수 있습니다.\n"
            "  - SEARCH 블록은 원본 파일에 정확히 한 번 등장해야 합니다.\n"
            "    모호하면 위/아래에 한두 줄을 더 포함시켜 유일하게 만드세요.\n"
            "  - 들여쓰기·공백·줄바꿈을 원본 그대로 복사하세요.\n"
            "  - 블록 삭제는 REPLACE 를 비우면 됩니다.\n"
            "  - 신규 파일을 만들 때는 A-2 가 아닌 A-1 을 사용하세요.\n\n"

            "  예시 — `import json` 을 imports 끝에 추가:\n"
            "    ```patch:src/agent_runner.py\n"
            "    <<<<<<< SEARCH\n"
            "    import os\n"
            "    import platform\n"
            "    import re\n"
            "    =======\n"
            "    import os\n"
            "    import platform\n"
            "    import re\n"
            "    import json\n"
            "    >>>>>>> REPLACE\n"
            "    ```\n\n"

            "  예시 — 함수 본문 교체 + 상수 추가 (한 펜스, 두 블록):\n"
            "    ```patch:src/agent_runner.py\n"
            "    <<<<<<< SEARCH\n"
            "        def _has_code_failure(actions):\n"
            "            return any(not a.success for a in actions)\n"
            "    =======\n"
            "        def _has_code_failure(actions):\n"
            "            return any((not a.success) and a.kind in ('code','shell','file')\n"
            "                       for a in actions)\n"
            "    >>>>>>> REPLACE\n"
            "    <<<<<<< SEARCH\n"
            "        SEP = '─' * 60\n"
            "    =======\n"
            "        SEP = '─' * 60\n"
            "        PATCH_FUZZY = True\n"
            "    >>>>>>> REPLACE\n"
            "    ```\n\n"

            "  자주 하는 실수:\n"
            "    1) SEARCH 블록을 너무 짧게 작성 → 여러 곳 매칭 → ambiguous 실패\n"
            "    2) SEARCH 의 들여쓰기를 임의로 줄임 → 매칭 실패 가능\n"
            "    3) 한 파일을 ```filename:``` 과 ```patch:``` 양쪽으로 동시 작성\n\n"

            "== 선택지 B. 코드 실행 (임시 실행 — 파일 저장 없음) ==\n"
            "  ```python\n"
            "  print(\"hello\")\n"
            "  ```\n"
            "  - 언어 태그는 정확히 `python` / `javascript` 두 가지만 사용.\n"
            "  - 타임아웃 120초 · 워크스페이스 cwd · UTF-8 자동 강제.\n"
            "  - 경고: 코드 안에서 `subprocess.run` / `os.system` 으로 OS 호출하지 마세요 —\n"
            "     OS 명령은 선택지 C 로 분리하세요. (가독성·승인 정책 분리)\n"
            "  - 경고: `bash`/`sh`/`shell`/`powershell`/`ps1` 태그는 자동으로 쉘로 라우팅됩니다.\n\n"

            "== 선택지 C. 쉘 명령 실행 ==\n"
            "  라인 시작에 `$ <명령>` — 코드 블록으로 감싸지 마세요.\n"
            "    $ git status\n"
            "    $ python --version\n"
            "  - 한 줄에 한 명령. 파이프(|)·리다이렉트(>)·`&&`·`;`·`||` 는 한 줄 내 허용.\n"
            "  - 경고: 체이닝(`&&`/`;`/`||`) 안에 위험 명령(rm, del 등) 이 있으면 시스템이\n"
            "     각 세그먼트를 검사해 승인을 요구합니다.\n"
           f"  - 명령은 {shell_type} 구문을 사용하세요.\n"
            "  - (선택) 명시 라우팅: `[ACTION:shell]` 태그.\n\n"

            "[OBSERVE]\n"
            "기대 결과 1~5줄. (실제 결과는 시스템이 다음 프롬프트에 주입)\n\n"

            "[완료 판정]\n"
           f"목표 달성 시 응답 맨 끝에 정확히: {self.done_token}\n\n"

            "[Self-Correction]\n"
            "오류 시 다음 [REASON] 에서 원인 진단 + [ACT] 에서 교정.\n\n"

            f"{shell_brief}\n\n"

            "[주의]\n"
            "- 코드 블록 밖에서 장황하게 설명하지 마세요.\n"
            "- 한 iteration 에서 너무 많은 파일/명령을 시도하지 말고 1~3 개로 쪼개세요.\n"
            "- 의도가 모호하면 `[ACTION:file]` / `[ACTION:code]` / `[ACTION:shell]` "
            "태그를 ACT 첫 줄에 추가해 명시할 수 있습니다.\n"
            "- 실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정하세요.\n"
        )

    def _build_initial_prompt(self, goal: str, file_context: str = "") -> str:
        parts = [f"[GOAL]\n{goal}"]
        if file_context:
            parts.append(f"[FILE_CONTEXT]\n{file_context}")
        parts.append(
            "이 목표를 달성하기 위한 전체 PLAN 을 번호 매긴 목록으로 제시하세요.\n"
            "PLAN 은 간결하게, 실행 가능한 단위로 쪼개세요."
        )
        return "\n\n".join(parts)

    def _build_iteration_prompt(
        self, session: AgentSession, feedback: Optional[str]
    ) -> str:
        parts: List[str] = [f"[GOAL]\n{session.goal}"]

        if session.plan:
            parts.append(f"[PLAN]\n{session.plan}")

        if session.matched_files:
            files_ref = "\n".join(f"  - {p}" for p in session.matched_files)
            parts.append(
                "[FILE_CONTEXT_REF]\n"
                "본 에이전트는 다음 파일들을 컨텍스트로 가지고 있습니다 "
                "(전문은 이전 메시지 참조):\n" + files_ref
            )

        # HISTORY SUMMARY: 압축 요약은 agent_history 에 이미 반영되어 있으므로
        # RECENT OBSERVATIONS 만 별도로 주입한다.
        recent = session.iterations[-2:] if session.iterations else []
        if recent:
            obs_lines = []
            for rec in recent:
                obs_lines.append(
                    f"— Iteration {rec.idx} —\n{rec.observe_text.strip()}"
                )
            parts.append("[RECENT OBSERVATIONS]\n" + "\n\n".join(obs_lines))

        if feedback:
            parts.append(f"[USER_FEEDBACK]\n{feedback.strip()}")

        parts.append(
            "이제 다음 iteration 의 [REASON] / [ACT] / [OBSERVE] 를 작성하세요.\n"
            f"목표를 달성했다면 {self.done_token} 으로 마무리하세요."
        )
        return "\n\n".join(parts)

    # ─── 모델 호출 (히스토리 격리) ───────────────────────────
    def _call_model(self, session: AgentSession, user_prompt: str) -> str:
        saved_main = self.assistant.conversation_history
        saved_sys = getattr(self.assistant, "system_prompt", None)

        self.assistant.conversation_history = list(session.agent_history)
        self.assistant.system_prompt = self._build_system_prompt()

        try:
            response = self.assistant.chat(
                user_prompt,
                streaming=self.streaming,
                include_context=False,
            )
        finally:
            session.agent_history = self.assistant.conversation_history
            self.assistant.conversation_history = saved_main
            if saved_sys is not None:
                self.assistant.system_prompt = saved_sys

        return response or ""

    # ─── 블록 파싱 ───────────────────────────────────────────
    def _parse_blocks(self, response: str) -> Tuple[str, str, str]:
        m_reason = self.RE_REASON.search(response)
        m_act    = self.RE_ACT.search(response)
        m_obs    = self.RE_OBSERVE.search(response)

        reason = m_reason.group(1).strip() if m_reason else ""
        act    = m_act.group(1).strip()    if m_act    else ""
        obs    = m_obs.group(1).strip()    if m_obs    else ""

        # 관대한 폴백: 블록 태그가 없으면 전체 응답을 ACT 로 간주
        if not (reason or act or obs):
            act = response.strip()

        return reason, act, obs

    # ─── 액션 실행 ───────────────────────────────────────────
    def _execute_actions(
        self, session: AgentSession, act_text: str
    ) -> List[ActionResult]:
        """v1.0.107: 디스패처가 단일 경로로 라우팅."""
        return self._dispatcher.dispatch(session, act_text)

    # ─── 위험 명령 체이닝 검사 (FSD v1.0.115 §3.5) ────────────
    @staticmethod
    def _split_chained_segments(cmd: str) -> List[str]:
        """`&&`, `||`, `;` 로 분할. 큰따옴표/작은따옴표 안 또는 백슬래시
        이스케이프된 구분자는 분리하지 않는다."""
        segments: List[str] = []
        buf: List[str] = []
        i, n = 0, len(cmd)
        quote: Optional[str] = None
        while i < n:
            c = cmd[i]
            if quote:
                if c == quote and (i == 0 or cmd[i - 1] != "\\"):
                    quote = None
                buf.append(c)
                i += 1
                continue
            if c in ("'", '"'):
                quote = c
                buf.append(c)
                i += 1
                continue
            # 백슬래시로 이스케이프된 구분자 (`\&\&`, `\;`, `\|\|`)
            if c == "\\" and i + 1 < n and cmd[i + 1] in ("&", "|", ";"):
                buf.append(c)
                buf.append(cmd[i + 1])
                i += 2
                continue
            # 2글자 분리자 (`&&`, `||`)
            if c in ("&", "|") and i + 1 < n and cmd[i + 1] == c:
                segments.append("".join(buf).strip())
                buf = []
                i += 2
                continue
            if c == ";":
                segments.append("".join(buf).strip())
                buf = []
                i += 1
                continue
            buf.append(c)
            i += 1
        tail = "".join(buf).strip()
        if tail:
            segments.append(tail)
        return [s for s in segments if s]

    def _is_chain_dangerous(self, cmd: str) -> Tuple[bool, List[str]]:
        """체이닝된 모든 세그먼트의 첫 토큰 중 위험 명령 여부.

        Returns:
            (is_dangerous, dangerous_segments)
        """
        dangerous_set = self.terminal_executor.DANGEROUS_COMMANDS
        bad: List[str] = []
        for seg in self._split_chained_segments(cmd):
            tokens = seg.split()
            first = tokens[0].lower() if tokens else ""
            if first in dangerous_set:
                bad.append(seg)
        return (bool(bad), bad)

    # ─── 디스패처 전용 — 단일 쉘 명령 실행 ────────────────────
    def _exec_single_shell_command(
        self, session: AgentSession, cmd: str
    ) -> ActionResult:
        """디스패처 전용 — 단일 쉘 명령 실행 + 위험 명령 검사 (체이닝 분해)."""
        dangerous, bad_segments = self._is_chain_dangerous(cmd)

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
                label = (
                    f"shell '{cmd}' — 위험 세그먼트: {bad_segments}"
                    if bad_segments and bad_segments != [cmd]
                    else f"shell '{cmd}'"
                )
                if not self._approve_dangerous(
                    session, "auto_approve_dangerous_shell", label,
                ):
                    return ActionResult(
                        kind="shell", target=cmd, success=False,
                        detail="사용자 거부",
                    )

        print(f"\n▶️  $ {cmd}")
        result = self.terminal_executor.execute(cmd, allow_unsafe=dangerous)
        success = bool(result.get("success"))
        if success:
            stdout = (result.get("stdout") or "").strip()
            detail = f"returncode=0\n{stdout[:500]}" if stdout else "returncode=0"
        else:
            err = (result.get("stderr") or result.get("error") or "").strip()
            rc = result.get("returncode", "?")
            detail = f"returncode={rc}\n{err[:500]}"
        return ActionResult(
            kind="shell", target=cmd, success=success, detail=detail,
        )

    def _save_file_blocks(self, session: AgentSession, act_text: str) -> List[ActionResult]:
        results: List[ActionResult] = []
        # 파일명 목록을 사전 추출 (저장 전/후 비교)
        declared = [m.strip() for m in self.RE_FILENAME_BLOCK.findall(act_text)]
        if not declared:
            return results

        try:
            saved = self.response_parser.parse_and_save(
                act_text,
                auto_overwrite=bool(session.bypass_approvals),
            ) or []
        except Exception as e:
            for path in declared:
                results.append(ActionResult(
                    kind="file", target=path, success=False,
                    detail=f"저장 오류: {e}",
                ))
            return results

        saved_set = set(saved)
        for path in declared:
            if path in saved_set:
                results.append(ActionResult(
                    kind="file", target=path, success=True, detail="저장됨",
                ))
            else:
                results.append(ActionResult(
                    kind="file", target=path, success=False,
                    detail="저장 실패 또는 사용자 거부",
                ))
        return results

    def _run_code_blocks(self, act_text: str) -> List[ActionResult]:
        results: List[ActionResult] = []
        try:
            blocks = self.code_executor.extract_code_from_response(act_text) or []
        except Exception as e:
            return [ActionResult(
                kind="code", target="?", success=False,
                detail=f"코드 블록 추출 오류: {e}",
            )]

        for block in blocks:
            if block.get("filepath"):
                continue  # 파일 블록은 _save_file_blocks 에서 처리
            lang = block.get("language", "python")
            code = block.get("code", "")
            if not code:
                continue
            print(f"\n⚙️  코드 실행 ({lang})...")
            result = self.code_executor.execute(code, lang)
            success = bool(result.get("success"))
            if success:
                stdout = (result.get("stdout") or "").strip()
                detail = f"returncode=0\n{stdout[:500]}" if stdout else "returncode=0"
            else:
                stderr = (result.get("stderr") or result.get("error") or "").strip()
                rc = result.get("returncode", "?")
                detail = f"returncode={rc}\n{stderr[:500]}"
            results.append(ActionResult(
                kind="code", target=lang, success=success, detail=detail,
            ))
        return results

    def _run_shell_lines(
        self, session: AgentSession, act_text: str
    ) -> List[ActionResult]:
        results: List[ActionResult] = []
        lines = self.RE_SHELL.findall(act_text)
        for cmd in lines:
            cmd = cmd.strip()
            if not cmd:
                continue
            dangerous, bad_segments = self._is_chain_dangerous(cmd)

            if dangerous:
                if session.bypass_approvals:
                    # S5: 위험 액션 한도 검사 (실행 전)
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

            if dangerous and not session.auto_approve_dangerous_shell:
                label = (
                    f"shell '{cmd}' — 위험 세그먼트: {bad_segments}"
                    if bad_segments and bad_segments != [cmd]
                    else f"shell '{cmd}'"
                )
                approved = self._approve_dangerous(
                    session, "auto_approve_dangerous_shell", label,
                )
                if not approved:
                    results.append(ActionResult(
                        kind="shell", target=cmd, success=False,
                        detail="사용자 거부",
                    ))
                    continue

            print(f"\n▶️  $ {cmd}")
            result = self.terminal_executor.execute(cmd, allow_unsafe=dangerous)
            success = bool(result.get("success"))
            if success:
                stdout = (result.get("stdout") or "").strip()
                detail = f"returncode=0\n{stdout[:500]}" if stdout else "returncode=0"
            else:
                err = (result.get("stderr") or result.get("error") or "").strip()
                rc = result.get("returncode", "?")
                detail = f"returncode={rc}\n{err[:500]}"
            results.append(ActionResult(
                kind="shell", target=cmd, success=success, detail=detail,
            ))
        return results

    # ─── 승인 ────────────────────────────────────────────────
    def _approve_dangerous(
        self, session: AgentSession, flag_attr: str, label: str
    ) -> bool:
        prompt = (
            f"\n⚠️  위험 액션 감지: {label}\n"
            "▶ 실행하시겠습니까? [y]es / [N]o / [A]lways (세션 내 자동 승인) : "
        )
        try:
            with self._input_listener.paused():
                ans = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if ans == 'a':
            setattr(session, flag_attr, True)
            return True
        return ans == 'y'

    # ─── Self-Correction ─────────────────────────────────────
    def _self_correct_loop(
        self, session: AgentSession, last_actions: List[ActionResult]
    ) -> List[ActionResult]:
        corrected_total: List[ActionResult] = []
        current_failures = last_actions

        for attempt in range(1, self.self_correct_max + 1):
            fail_summary = self._format_failure(current_failures)
            correct_prompt = (
                f"[SELF_CORRECT attempt={attempt}/{self.self_correct_max}]\n"
                "직전 [ACT] 실행 결과 다음 오류가 발생했습니다.\n"
                "원인을 진단하고 수정된 [REASON] / [ACT] / [OBSERVE] 를 제시하세요.\n\n"
                f"{fail_summary}"
            )
            print(f"\n🔄 Self-Correction [{attempt}/{self.self_correct_max}]")
            response = self._call_model(session, correct_prompt)
            reason, act, _ = self._parse_blocks(response)
            self._print_block("🧠", f" Reason (correct {attempt})", reason or "(없음)")
            self._print_block("🔨", f" Act (correct {attempt})", act or "(없음)")

            new_actions = self._execute_actions(session, act)
            corrected_total.extend(new_actions)

            if not self._has_code_failure(new_actions):
                return corrected_total
            current_failures = new_actions

        print(
            f"⚠️  Self-Correction {self.self_correct_max}회 실패 — 다음 iteration 으로 진행"
        )
        return corrected_total

    # ─── 사용자 개입 ─────────────────────────────────────────
    def _ask_continue(self) -> Tuple[str, Optional[str]]:
        try:
            ans = input(
                "\n▶ [c]ontinue / [f]eedback / [b]ypass approvals / [s]top ? (c): "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return ('s', None)
        if not ans:
            ans = 'c'
        if ans == 'f':
            print("💬 피드백 입력 (멀티라인, 종료: /end 또는 Esc+Enter):")
            try:
                feedback = self.cli_handler.get_multiline()
            except Exception:
                feedback = ""
            return ('f', feedback or None)
        if ans == 's':
            return ('s', None)
        if ans == 'b':
            return ('b', None)
        return ('c', None)

    # ─── 히스토리 압축 / 요약 ───────────────────────────────
    def _compact_history_if_needed(self, session: AgentSession) -> None:
        if len(session.agent_history) <= self.compact_after * 2:
            return
        # 최근 2쌍(user+model)은 보존, 그 외는 요약 요청
        keep = session.agent_history[-4:]
        to_summarize = session.agent_history[:-4]
        if not to_summarize:
            return

        dump = []
        for msg in to_summarize:
            role = msg.get("role", "?")
            content = (msg.get("content", "") or "")[:1500]
            dump.append(f"[{role}]\n{content}")
        summarize_prompt = (
            "[COMPACT_HISTORY]\n"
            "아래 에이전트 대화 이력을 5~10줄로 핵심만 요약하세요. "
            "산출물(저장된 파일, 성공한 단계, 실패/보류된 단계)을 빠짐없이 포함하세요.\n\n"
            + "\n\n".join(dump)
        )

        # 요약 호출은 현 세션에 추가 메시지를 남기지 않기 위해 임시 히스토리로 수행
        saved_main = self.assistant.conversation_history
        saved_sys = getattr(self.assistant, "system_prompt", None)
        self.assistant.conversation_history = []
        self.assistant.system_prompt = self._build_system_prompt()
        try:
            summary = self.assistant.chat(
                summarize_prompt, streaming=False, include_context=False,
            ) or ""
        except Exception as e:
            summary = f"(요약 실패: {e})"
        finally:
            self.assistant.conversation_history = saved_main
            if saved_sys is not None:
                self.assistant.system_prompt = saved_sys

        session.agent_history = [
            {"role": "user", "content": "[HISTORY_SUMMARY]"},
            {"role": self.assistant_role, "content": summary},
        ] + keep
        print(f"\n🗜  히스토리 압축 완료 ({len(to_summarize)} → 요약 1쌍)")

    def _append_summary_to_main_history(self, session: AgentSession) -> None:
        user_msg = f"[/agents] 목표: {session.goal}"
        saved_files: List[str] = []
        for it in session.iterations:
            for a in it.actions:
                if a.kind == "file" and a.success and a.target not in saved_files:
                    saved_files.append(a.target)
        reason_txt = session.stop_reason.value if session.stop_reason else "unknown"
        bot_msg = (
            f"에이전트 실행 완료 ({reason_txt}, "
            f"{len(session.iterations)} iterations)\n"
            f"저장된 파일: {saved_files or '없음'}"
        )
        self.assistant.conversation_history.append(
            {"role": "user", "content": user_msg}
        )
        self.assistant.conversation_history.append(
            {"role": self.assistant_role, "content": bot_msg}
        )

    # ─── 출력 유틸 ───────────────────────────────────────────
    def _print_header(self, session: AgentSession, iteration_idx: int) -> None:
        mx = session.effective_max_iterations or self.max_iterations
        if session.bypass_approvals and session.bypass_started_at is not None:
            import time as _time
            elapsed = int(_time.monotonic() - session.bypass_started_at)
            mm, ss = divmod(elapsed, 60)
            print(f"\n━━━ Iteration {iteration_idx}/{mx} "
                  f"[BYPASS · elapsed {mm:02d}:{ss:02d}] ━━━")
        else:
            print(f"\n━━━ Iteration {iteration_idx}/{mx} ━━━")

    def _print_block(self, emoji: str, title: str, body: str) -> None:
        print(f"\n{emoji} {title}")
        print(self.SEP)
        print((body or "").rstrip())

    def _print_final_summary(self, session: AgentSession) -> None:
        print("\n" + "=" * 60)
        reason = session.stop_reason.value if session.stop_reason else "unknown"
        print(f"✅ 에이전트 종료 (stop_reason={reason}, "
              f"{len(session.iterations)} iterations)")

        saved: List[str] = []
        shells: List[str] = []
        code_runs = 0
        code_fails = 0
        for it in session.iterations:
            for a in it.actions:
                if a.kind == "file" and a.success and a.target not in saved:
                    saved.append(a.target)
                elif a.kind == "shell":
                    shells.append(f"{'✅' if a.success else '❌'} {a.target}")
                elif a.kind == "code":
                    code_runs += 1
                    if not a.success:
                        code_fails += 1

        if saved:
            print(f"📁 생성/수정 파일 ({len(saved)}):")
            for p in saved:
                print(f"  - {p}")
        else:
            print("📁 생성/수정 파일: 없음")

        if code_runs:
            print(f"⚙️  코드 실행: {code_runs}회 (실패 {code_fails}회)")
        if shells:
            print(f"🖥  쉘 명령: {len(shells)}건")
            for s in shells[:10]:
                print(f"  {s}")

        print("=" * 60)

    # ─── 보조 판정 / 포맷 ───────────────────────────────────
    @staticmethod
    def _has_code_failure(actions: List[ActionResult]) -> bool:
        # FSD v1.0.115 FR-111-22: patch 실패도 자기 수정 트리거에 포함
        return any(
            (not a.success) and a.kind in ("code", "shell", "file")
            for a in actions
        )

    @staticmethod
    def _format_observe(hint: str, actions: List[ActionResult]) -> str:
        lines: List[str] = []
        for a in actions:
            icon = "✅" if a.success else "❌"
            if a.kind == "file":
                lines.append(f"{icon} 파일 {a.target} — {a.detail}")
            elif a.kind == "code":
                lines.append(f"{icon} 코드 실행 ({a.target})\n{a.detail}")
            elif a.kind == "shell":
                lines.append(f"{icon} $ {a.target}\n{a.detail}")
        if hint:
            lines.append(f"(예상: {hint})")
        if not lines:
            lines.append("(실행된 액션 없음)")
        return "\n".join(lines)

    @staticmethod
    def _format_failure(actions: List[ActionResult]) -> str:
        parts = []
        for a in actions:
            if a.success:
                continue
            if a.kind == "code":
                parts.append(f"[코드 실행 실패: {a.target}]\n{a.detail}")
            elif a.kind == "shell":
                parts.append(f"[쉘 실패: {a.target}]\n{a.detail}")
            elif a.kind == "file":
                # patch 실패는 detail 에 nearest snippet 이 포함됨 (FR-111-23)
                parts.append(f"[파일 작업 실패: {a.target}]\n{a.detail}")
        return "\n\n".join(parts) if parts else "(실패 액션 없음 — 참고)"
