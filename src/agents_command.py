"""
agents_command - /agents 명령 공용 처리 모듈 (FSD v1.0.085, FSD v1.0.100, FSD v1.0.101)

gemini / claude / gen-ai 세 엔트리 포인트에서 공통으로 호출한다.
"""

import os
from typing import List, Optional, Tuple

from .agent_policy import (
    POLICY_AUTO,
    env_default_policy,
    normalize_policy,
)

BYPASS_FLAGS = {"-ba", "--bypassapprovals", "--bypass-approvals"}
STEPS_FLAGS  = {"-s", "--steps"}  # FSD v1.0.101
POLICY_FLAGS = {"--policy"}       # FSD v1.1.062 FR-062-01


def _extract_steps_flag(args: str) -> Tuple[Optional[int], str]:
    """args 에서 `-s N` / `--steps N` 을 분리해 (override, 남은_args) 를 반환.

    - 값이 양의 정수로 파싱되지 않으면 override=None, 경고 출력
    - 대괄호 블록으로 시작하면 즉시 (None, args) 반환
    """
    stripped = args.strip()
    if not stripped or stripped.startswith("["):
        return None, args

    tokens = stripped.split()
    override: Optional[int] = None
    remaining: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.lower() in STEPS_FLAGS:
            if i + 1 >= len(tokens):
                print(f"⚠️  {tok} 플래그의 값이 누락되어 무시됩니다.")
                i += 1
                continue
            raw = tokens[i + 1]
            try:
                val = int(raw)
                if val < 1:
                    raise ValueError
                override = val
            except ValueError:
                print(f"⚠️  {tok} 값은 양의 정수여야 합니다: {raw!r} → 무시됩니다.")
            i += 2
            continue
        remaining.append(tok)
        i += 1
    return override, " ".join(remaining)


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


def _has_policy_flag(args: str) -> bool:
    """대괄호 블록 밖에서 `--policy` 가 명시되었는지 여부."""
    stripped = args.strip()
    if not stripped or stripped.startswith("["):
        return False
    return any(tok.lower() in POLICY_FLAGS for tok in stripped.split())


def _extract_policy_flag(args: str) -> Tuple[str, str]:
    """args 에서 `--policy <val>` 을 분리해 (policy, 남은_args) 를 반환.

    - 플래그 명시값 > env(AGENT_INTERACTION_POLICY) > 기본(interactive)
    - 잘못된 값은 normalize_policy 로 interactive 폴백
    - 대괄호 블록([...])으로 시작하면 즉시 (env_default, args) 반환
    """
    env_default = env_default_policy()

    stripped = args.strip()
    if not stripped or stripped.startswith("["):
        return env_default, args

    tokens = stripped.split()
    policy: Optional[str] = None
    remaining: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.lower() in POLICY_FLAGS:
            if i + 1 >= len(tokens):
                print(f"⚠️  {tok} 플래그의 값이 누락되어 무시됩니다.")
                i += 1
                continue
            raw = tokens[i + 1]
            normalized = normalize_policy(raw)
            if normalized != raw.strip().lower():
                print(f"⚠️  {tok} 값이 유효하지 않아 '{normalized}' 로 처리됩니다: {raw!r}")
            policy = normalized
            i += 2
            continue
        remaining.append(tok)
        i += 1

    final = policy if policy is not None else env_default
    return final, " ".join(remaining)


def _resolve_resume_target(arg: str, store) -> Optional[object]:
    """resume 인자를 해석해 AgentSession 을 반환.

    - arg 가 전부 숫자 → 1-based 인덱스로 해석
    - 그 외 → 파일명으로 해석
    실패 시 None 반환 (호출측이 에러 메시지 출력)
    """
    if arg.isdigit():
        idx = int(arg)
        sessions = store.list_sessions()
        if idx < 1 or idx > len(sessions):
            print(f"❌ 세션 인덱스 범위 초과: {idx} (현재 {len(sessions)} 개)")
            return None
        return store.load(sessions[idx - 1]["filename"])
    return store.load(arg)


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

    # --policy 가 명시되었는지 추출 전에 판정 (대괄호 블록 밖에서만)
    policy_explicit = _has_policy_flag(args)

    # 플래그 선추출: bypass → steps → policy 순
    bypass, args = _extract_bypass_flag(args)
    steps_override, args = _extract_steps_flag(args)
    policy_flag, args = _extract_policy_flag(args)

    # 최종 정책 결정 (FR-062-01):
    #   --policy 명시값 > (-ba 있으면 auto) > env > interactive
    # _extract_policy_flag 는 플래그 부재 시 env_default 를 돌려주므로,
    # 명시 여부(policy_explicit)로 -ba 와의 우선순위를 가린다.
    if policy_explicit:
        policy = policy_flag                     # 명시 --policy 가 최우선
    elif bypass:
        policy = POLICY_AUTO                      # -ba 후방호환 → auto
    else:
        policy = policy_flag                      # env > interactive

    # bypass_approvals 는 policy=="auto" 와 동치로 정리 (기존 _enter_bypass_mode 재사용)
    bypass = (policy == POLICY_AUTO)

    stripped = args.strip()
    sub = stripped.lower().split()[0] if stripped else ""

    # ── /agents stop ────────────────────────────────────────
    if sub == "stop":
        if bypass:
            print("⚠️  /agents stop 에는 -ba 플래그가 적용되지 않습니다.")
        if steps_override is not None:
            print("⚠️  /agents stop 에는 -s 플래그가 적용되지 않습니다.")
        print(
            "💡 에이전트는 현재 실행 중이 아닙니다. "
            "루프 도중에는 's' 키(또는 Ctrl+C)로 안전하게 중단할 수 있습니다."
        )
        return

    # ── /agents list ────────────────────────────────────────
    if sub == "list":
        if bypass:
            print("⚠️  /agents list 에는 -ba 플래그가 적용되지 않습니다.")
        if steps_override is not None:
            print("⚠️  /agents list 에는 -s 플래그가 적용되지 않습니다.")
        store = AgentSessionStore(str(assistant.file_manager.workspace_dir))
        store.print_session_list()
        return

    # ── /agents resume [N | filename] ──────────────────────
    if sub == "resume":
        store = AgentSessionStore(str(assistant.file_manager.workspace_dir))
        parts = stripped.split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else None

        if arg is None:
            session = store.load_latest()
            if session is None:
                print("❌ 저장된 세션이 없습니다. /agents list 로 확인하세요.")
                return
        else:
            session = _resolve_resume_target(arg, store)
            if session is None:
                if not arg.isdigit():
                    print(f"❌ 세션 파일을 찾을 수 없습니다: {arg}")
                return

        stop = session.stop_reason.value if session.stop_reason else "unknown"
        iters_done = len(session.iterations)
        display_name = arg or "latest.json"
        print(f"\n📂 세션 복원: {display_name}")
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
        runner.run(
            resume_session=session,
            bypass_approvals=bypass,
            max_iterations_override=steps_override,
            interaction_policy=policy,
        )
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
    runner.run(
        goal,
        file_patterns=file_patterns or None,
        bypass_approvals=bypass,
        max_iterations_override=steps_override,
        interaction_policy=policy,
    )
