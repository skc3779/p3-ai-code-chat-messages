"""
agent_policy - 에이전트 상호작용 정책 (InteractionPolicy) 정의 (FSD v1.1.062 §3.2, FR-062-01)

정책 값:
    interactive  — 기본. 모든 액션 승인 + 매 iteration 사이 사용자에게 묻는다.
    auto-edit    — 파일 편집은 자동(diff 표시), 셸/위험은 사전 승인 (per-action).
    on-failure   — 자동 진행하되 다음 액션 진입 전 사전 정지. 위험 셸은 항상 승인.
    auto         — 완전 자율 (기존 bypass approvals 와 동치).

P4 범위 (FR-062-22, §3.2):
    - 정책은 iteration 이 아니라 각 액션 실행 직전에 per-action 으로 평가된다.
    - auto-edit / on-failure 의 per-action 강제가 실동작한다 (P1 DEFERRED 해제).
    - 위험 셸은 모든 정책에서 항상 사전 승인.
"""

import os
from typing import Optional

# 정책 상수 (문자열 enum 대용 — 직렬화/CLI 친화)
POLICY_INTERACTIVE = "interactive"
POLICY_AUTO_EDIT   = "auto-edit"
POLICY_ON_FAILURE  = "on-failure"
POLICY_AUTO        = "auto"

VALID_POLICIES = (
    POLICY_INTERACTIVE,
    POLICY_AUTO_EDIT,
    POLICY_ON_FAILURE,
    POLICY_AUTO,
)

DEFAULT_POLICY = POLICY_INTERACTIVE

# auto-edit / on-failure 처럼 per-action 세분 제어를 갖는 정책 집합.
# (P1 에서는 DEFERRED 였으나 P4 에서 per-action 실동작이 부여됨 — FR-062-22.)
#
# 명칭 주의(P5): "DEFERRED" 는 P1 시점의 역사적 명칭이다. P4 에서 per-action
# 제어가 활성화된 이후에도 이 상수는 _confirm_change 의 정책 분기 참조용으로
# 그대로 쓰인다 — 즉 "파일 편집 diff 를 (사용자 프롬프트 없이) 표시 후 자동
# 적용하는 정책 집합" 을 가리킨다. 호환을 위해 명칭은 변경하지 않는다.
DEFERRED_POLICIES = (POLICY_AUTO_EDIT, POLICY_ON_FAILURE)

# ── per-action 결정 상수 (FR-062-22, §3.2) ────────────────────
ACTION_AUTO    = "auto"      # 사용자 개입 없이 자동 실행
ACTION_APPROVE = "approve"   # 실행 직전 사용자 승인 요청
ACTION_STOP    = "stop"      # 실행하지 않고 사용자 턴으로 정지

# 액션 분류 — dispatcher 가 부여하는 의미 범주
ACTKIND_FILE  = "file"       # 파일 편집/생성/패치
ACTKIND_SHELL = "shell"      # 셸 명령 / 스크립트
ACTKIND_CODE  = "code"       # 임시 코드 실행


def normalize_policy(value: Optional[str]) -> str:
    """정책 문자열을 유효성 검사 후 정규화. 잘못된 값/None → DEFAULT_POLICY."""
    if not value:
        return DEFAULT_POLICY
    v = str(value).strip().lower()
    return v if v in VALID_POLICIES else DEFAULT_POLICY


def env_default_policy() -> str:
    """환경변수 AGENT_INTERACTION_POLICY 기반 기본 정책 (잘못된 값 → DEFAULT_POLICY)."""
    return normalize_policy(os.getenv("AGENT_INTERACTION_POLICY", DEFAULT_POLICY))


def per_action_decision(
    policy: str, action_kind: str, *, is_dangerous: bool = False
) -> str:
    """각 액션 실행 직전 정책 평가 (FR-062-22, §3.2).

    Args:
        policy        : 현재 세션 정책 (normalize_policy 로 정규화 권장).
        action_kind   : ACTKIND_FILE | ACTKIND_SHELL | ACTKIND_CODE.
        is_dangerous  : 위험 셸(체이닝 위험 명령 포함 등) 여부.

    Returns:
        ACTION_AUTO    — 자동 실행.
        ACTION_APPROVE — 사용자 승인 요청.
        ACTION_STOP    — 실행 보류, 사용자 턴으로 정지.

    규칙:
      - 위험 셸은 모든 정책에서 항상 사전 승인(ACTION_APPROVE). (auto 제외 —
        auto 는 기존 bypass 안전장치 경로가 별도로 위험 한도를 관리한다.)
      - auto          : 전부 자동.
      - interactive   : 전부 승인.
      - auto-edit     : 파일 편집 자동, 셸/코드는 승인.
      - on-failure    : 다음 액션 진입 전 정지(사전). 위험 셸은 위에서 승인.
    """
    pol = normalize_policy(policy)

    if pol == POLICY_AUTO:
        # auto 는 위험 셸도 bypass 안전장치(누적 한도)가 별도 처리 — 여기선 자동.
        return ACTION_AUTO

    # 위험 셸은 비-auto 모든 정책에서 항상 사전 승인.
    if is_dangerous:
        return ACTION_APPROVE

    if pol == POLICY_INTERACTIVE:
        return ACTION_APPROVE

    if pol == POLICY_AUTO_EDIT:
        if action_kind == ACTKIND_FILE:
            return ACTION_AUTO
        # 셸/코드 등 부수효과 액션은 승인.
        return ACTION_APPROVE

    if pol == POLICY_ON_FAILURE:
        # 자동 진행하되 다음 액션 진입 전 사전 정지 (사후 아님).
        return ACTION_STOP

    # 미지 정책 — 보수적으로 승인.
    return ACTION_APPROVE
