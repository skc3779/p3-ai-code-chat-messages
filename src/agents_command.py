"""
agents_command - /agents 명령 공용 처리 모듈 (FSD v1.0.085, FSD v1.0.100)

gemini / claude / gen-ai 세 엔트리 포인트에서 공통으로 호출한다.
"""

import os
from typing import List, Tuple

BYPASS_FLAGS = {"-ba", "--bypassapprovals", "--bypass-approvals"}


def _extract_bypass_flag(args: str) -> Tuple[bool, str]:
    """args 에서 bypass 플래그를 분리해 (bypass, 남은_args) 를 반환.

    대괄호 블록([...]) 내부 토큰은 건드리지 않는다.
    AGENT_BYPASS_DEFAULT=true 환경변수가 설정된 경우에도 bypass=True.
    """
    stripped = args.strip()
    env_default = os.getenv("AGENT_BYPASS_DEFAULT", "false").lower() == "true"

    if not stripped:
        return env_default, ""

    # 대괄호 블록은 패턴 파싱에 넘기므로 플래그 추출 없음
    if stripped.startswith("["):
        return env_default, args

    tokens = stripped.split()
    bypass = env_default
    remaining: List[str] = []
    for tok in tokens:
        if tok.lower() in BYPASS_FLAGS:
            bypass = True
        else:
            remaining.append(tok)
    return bypass, " ".join(remaining)


def handle_agents_command(
    assistant,
    cli_handler,
    streaming: bool,
    args: str,
    assistant_role: str = "model",
) -> None:
    """/agents 명령 공통 처리.

    패턴 파싱 → 멀티라인 목표 수집 → AgentRunner 생성 → 실행.

    assistant_role:
        "model"     — Gemini, GenAI
        "assistant" — Claude
    """
    from .agent_runner import AgentRunner
    from .agent_session_store import AgentSessionStore

    # bypass 플래그 선추출
    bypass, args = _extract_bypass_flag(args)
    stripped = args.strip()
    sub = stripped.lower().split()[0] if stripped else ""

    # ── /agents stop ────────────────────────────────────────
    if sub == "stop":
        if bypass:
            print("⚠️  /agents stop 에는 -ba 플래그가 적용되지 않습니다.")
        print(
            "💡 에이전트는 현재 실행 중이 아닙니다. "
            "루프 도중에는 's' 키(또는 Ctrl+C)로 안전하게 중단할 수 있습니다."
        )
        return

    # ── /agents list ────────────────────────────────────────
    if sub == "list":
        if bypass:
            print("⚠️  /agents list 에는 -ba 플래그가 적용되지 않습니다.")
        store = AgentSessionStore(str(assistant.file_manager.workspace_dir))
        store.print_session_list()
        return

    # ── /agents resume [filename] ───────────────────────────
    if sub == "resume":
        store = AgentSessionStore(str(assistant.file_manager.workspace_dir))
        parts = stripped.split(maxsplit=1)
        filename = parts[1] if len(parts) > 1 else None
        if filename:
            session = store.load(filename)
            if session is None:
                print(f"❌ 세션 파일을 찾을 수 없습니다: {filename}")
                return
        else:
            session = store.load_latest()
            if session is None:
                print("❌ 저장된 세션이 없습니다. /agents list 로 확인하세요.")
                return

        stop = session.stop_reason.value if session.stop_reason else "unknown"
        iters_done = len(session.iterations)
        print(f"\n📂 세션 복원: {filename or 'latest.json'}")
        print(f"  목표: {session.goal}")
        print(f"  상태: {stop} ({iters_done} iterations 완료)")
        if session.matched_files:
            print(f"  저장된 파일 참조: {', '.join(session.matched_files[:5])}")

        runner = AgentRunner(
            assistant=assistant,
            file_manager=assistant.file_manager,
            code_executor=assistant.code_executor,
            terminal_executor=assistant.terminal_executor,
            response_parser=assistant.response_parser,
            cli_handler=cli_handler,
            context_builder=assistant.context_builder,
            streaming=streaming,
            assistant_role=assistant_role,
        )
        runner.run(resume_session=session, bypass_approvals=bypass)
        return

    # ── /agents [pattern] — 신규 실행 ──────────────────────
    file_patterns: List[str] = []
    if stripped:
        if stripped.startswith("["):
            try:
                end_idx = args.index("]")
                file_patterns = [p.strip() for p in args[1:end_idx].split(",") if p.strip()]
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
        assistant_role=assistant_role,
    )
    runner.run(goal, file_patterns=file_patterns or None, bypass_approvals=bypass)
