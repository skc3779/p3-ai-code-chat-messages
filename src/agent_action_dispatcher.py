"""
AgentActionDispatcher (FSD v1.0.107)

[ACTION] 블록을 분석해 단일 경로로만 실행되도록 라우팅한다.
- 쉘 계열 코드 블록의 `$ ...` 라인은 쉘로 자동 라우팅
- 다중라인 스크립트는 CodeExecutor 로 라우팅
- 위험 명령 검사는 모든 shell action 에 일원 적용
- `[ACTION:*]` 명시 태그가 있으면 우선 적용
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class _ParsedAction:
    kind: str           # "file" | "code" | "shell" | "script" | "patch"
    payload: str        # 원본 텍스트 / 라인
    lang: Optional[str] = None
    filepath: Optional[str] = None
    explicit_tag: bool = False    # [ACTION:*] 로 명시되었는지


class AgentActionDispatcher:
    """[ACTION] 블록 → 단일 경로 라우팅 디스패처.

    기존 AgentRunner._execute_actions() 가 세 파서를 독립 호출하던 방식을
    단일 진입점(dispatch)으로 교체한다. 쉘 블록 분류기, 중복 제거,
    위험 명령 검사 일원화를 담당.
    """

    RE_FENCE = re.compile(
        r"^[ \t]*(`{3,})(\w*(?::[\S]*)?)[ \t]*\n(.*?)\n[ \t]*\1[ \t]*$",
        re.MULTILINE | re.DOTALL,
    )
    RE_SHELL_LINE = re.compile(r"^\s*\$\s+(.+)$", re.MULTILINE)
    RE_ACTION_TAG = re.compile(
        r"^\s*\[ACTION:(file|code|shell)\]\s*$", re.MULTILINE | re.IGNORECASE,
    )

    SHELL_LANGS = {"powershell", "ps1", "bash", "sh", "shell"}
    CODE_LANGS = {"python", "py", "javascript", "js"}

    # 쉘 스크립트(라인 분해 금지) 시그널
    SCRIPT_INDICATORS = [
        re.compile(
            r"^\s*(function|param|if|elseif|else|switch|foreach|for|while|do|try|catch|finally)\b",
            re.IGNORECASE,
        ),
        re.compile(r"^\s*(then|elif|fi|case|esac|done|until|export|local|read)\b"),
        re.compile(r"^\s*\$?[\w\.]+\s*="),
        re.compile(r"^\s*\w+\s*\(\)\s*\{"),
        re.compile(r"\\\s*$"),
    ]

    def __init__(self, runner):
        """AgentRunner 참조 — 위험 명령 / 승인 플로우 재사용."""
        self._runner = runner
        self.action_tags_required = (
            os.getenv("AGENT_ACTION_TAGS_REQUIRED", "0") == "1"
        )

    # ─── 진입 ──────────────────────────────────────────────────
    def dispatch(self, session, act_text: str) -> list:
        """act_text 를 파싱해 단일 경로 실행 결과 리스트를 반환."""
        from .agent_runner import ActionResult

        if not act_text:
            return []

        actions = self._parse(act_text)

        # AGENT_ACTION_TAGS_REQUIRED=1: 태그 없으면 Self-Correction 유도
        if self.action_tags_required and actions and not any(a.explicit_tag for a in actions):
            return [ActionResult(
                kind="code", target="dispatcher",
                success=False,
                detail="[ACTION:*] 태그가 필요합니다. ACT 첫 줄에 "
                       "[ACTION:file] / [ACTION:code] / [ACTION:shell] 태그를 추가하세요.",
            )]

        actions = self._dedupe(actions)

        # FR-111-25: 같은 iteration 안에서 같은 파일을 filename 과 patch 양쪽으로
        # 작성한 경우, filename 을 우선 적용하고 patch 는 보고만 한다.
        file_paths = {
            (a.filepath or "").strip().replace("\\", "/")
            for a in actions
            if a.kind == "file" and a.filepath
        }

        results: list = []
        for idx, a in enumerate(actions):
            # ── per-action 정책 게이트 (FR-062-22, §3.2) ──
            # 각 액션 실행 직전에 정책을 평가해 승인/정지/자동을 결정한다.
            gate = self._per_action_gate(session, a)
            if gate == "stop":
                # 정지 — 이 액션 및 나머지 액션을 실행하지 않고 보존(사용자 턴으로).
                results.append(self._make_hold_result(actions[idx:]))
                break
            if gate == "reject":
                # 이 액션만 거부(실패 처리), 나머지는 계속.
                results.append(ActionResult(
                    kind=self._observe_kind(a),
                    target=self._action_target(a),
                    success=False,
                    detail="사용자 거부 (per-action 승인 거부)",
                ))
                continue
            # gate == "approve" 로 셸/스크립트가 승인된 경우, 실행기 내부의 위험
            # 셸 2차 프롬프트와 중복되지 않도록 해당 액션 한정 자동승인을 임시 부여
            # (실행 후 원복). interactive/auto 경로는 gate 가 AUTO 라 영향 없음.
            transient_danger_ok = (
                gate == "approve" and a.kind in ("shell", "script")
            )
            prev_danger_flag = getattr(
                session, "auto_approve_dangerous_shell", False
            )
            if transient_danger_ok:
                session.auto_approve_dangerous_shell = True
            try:
                # gate in ("auto", "approve") → 실행 진행
                if a.kind == "file":
                    results += self._exec_file(session, a)
                elif a.kind == "code":
                    results.append(self._exec_code(a))
                elif a.kind == "script":
                    results.append(self._exec_script(session, a))
                elif a.kind == "shell":
                    results.append(self._exec_shell(session, a))
                elif a.kind == "patch":
                    pass  # 아래 patch 분기에서 처리 (try 밖)
            finally:
                if transient_danger_ok:
                    session.auto_approve_dangerous_shell = prev_danger_flag
            if a.kind == "patch":
                key = (a.filepath or "").strip().replace("\\", "/")
                if key and key in file_paths:
                    results.append(ActionResult(
                        kind="file",
                        target=a.filepath or "?",
                        success=False,
                        detail="동일 파일에 filename 블록이 우선 적용됨",
                    ))
                    continue
                results.append(self._exec_patch(session, a))
        return results

    # ─── per-action 정책 게이트 (FR-062-22, §3.2) ──────────────
    @staticmethod
    def _observe_kind(a: _ParsedAction) -> str:
        """ActionResult.kind 매핑 (file/patch→file, script→code 보고 형식 유지)."""
        if a.kind in ("file", "patch"):
            return "file"
        if a.kind == "script":
            return "code"
        return a.kind

    @staticmethod
    def _action_target(a: _ParsedAction) -> str:
        """보고용 타겟 — 파일/패치는 경로, 셸은 명령, 코드는 언어."""
        if a.kind in ("file", "patch"):
            return a.filepath or "?"
        if a.kind == "shell":
            return a.payload
        return a.lang or a.kind

    def _policy_action_kind(self, a: _ParsedAction) -> str:
        """_ParsedAction → 정책 액션 범주 (file | shell | code)."""
        from .agent_policy import ACTKIND_CODE, ACTKIND_FILE, ACTKIND_SHELL

        if a.kind in ("file", "patch"):
            return ACTKIND_FILE
        if a.kind in ("shell", "script"):
            return ACTKIND_SHELL
        return ACTKIND_CODE

    def _action_is_dangerous(self, a: _ParsedAction) -> bool:
        """셸/스크립트의 위험 명령 여부 — 정책 무관 항상 사전 승인 대상."""
        if a.kind == "shell":
            dangerous, _ = self._runner._is_chain_dangerous(a.payload)
            return dangerous
        if a.kind == "script":
            # 스크립트 첫 실행 라인의 base command 검사 (_exec_script 와 동일 기준).
            for line in a.payload.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    tok = stripped.split()
                    first = tok[0].lower() if tok else ""
                    return first in self._runner.terminal_executor.DANGEROUS_COMMANDS
        return False

    def _per_action_gate(self, session, a: _ParsedAction) -> str:
        """액션 실행 직전 정책 평가를 runner.per_action_gate 에 위임.

        Returns: "auto" | "approve" | "stop" | "reject".
        """
        action_kind = self._policy_action_kind(a)
        is_dangerous = self._action_is_dangerous(a)
        label = self._action_target(a)
        return self._runner.per_action_gate(
            session, action_kind, is_dangerous=is_dangerous, label=label,
        )

    def _make_hold_result(self, remaining: List[_ParsedAction]):
        """정지 시 나머지 액션 보존 — OBSERVE 에 보류를 기록하는 ActionResult.

        잔여 액션을 다음 프롬프트에 재제시하지 않고 모델이 OBSERVE 로 인지하도록
        한다(§3.2). 보류된 액션 요약을 detail 에 담아 보고한다.
        """
        from .agent_runner import ActionResult

        summary = []
        for a in remaining:
            summary.append(f"{a.kind}:{self._action_target(a)}")
        detail = (
            "사용자 승인 대기로 나머지 액션 보류 — "
            f"{len(remaining)}개 미실행: " + ", ".join(summary)
        )
        # kind="hold" — 정책 보류는 실패가 아니므로 Self-Correction 을 트리거하지
        # 않는다 (_has_code_failure 가 file/code/shell 만 본다).
        return ActionResult(
            kind="hold", target="per-action-hold",
            success=True, detail=detail,
        )

    # ─── 파싱 ──────────────────────────────────────────────────
    # v1.0.141 — `@@@` 도 펜스 마커로 인식 (filename:/patch: 전용 신규 패턴)
    _RE_FENCE_LINE = re.compile(r'^[ \t]*(`{3,}|@{3,})(\S*)[ \t]*$')

    def _parse(self, act_text: str) -> List[_ParsedAction]:
        """act_text 를 파싱하여 _ParsedAction 리스트를 반환.

        라인 단위 depth-counting 방식으로 펜스 블록을 파싱한다.
        filename:/patch: 블록 내부에 중첩된 코드 펜스가 있어도 올바르게
        바깥 블록의 닫힘 위치를 탐색한다 (BUG v1.0.121).

        v1.0.141: 펜스 마커로 백틱(```) 외에 `@@@` 도 허용. 두 종류의
        마커는 길이 비교만 수행하므로 상호 호환된다.
        """
        actions: List[_ParsedAction] = []
        lines = act_text.split('\n')
        covered = [False] * len(lines)

        i = 0
        while i < len(lines):
            m = self._RE_FENCE_LINE.match(lines[i])
            if not m:
                i += 1
                continue

            fence_len = len(m.group(1))
            tag = m.group(2).strip()

            # depth-counting 으로 matching closing fence 탐색
            depth = 1
            j = i + 1
            while j < len(lines):
                inner = self._RE_FENCE_LINE.match(lines[j])
                if inner:
                    inner_len = len(inner.group(1))
                    inner_tag = inner.group(2).strip()
                    if inner_len >= fence_len and not inner_tag:
                        depth -= 1
                        if depth == 0:
                            break
                    elif inner_tag:
                        depth += 1
                j += 1

            if depth != 0:
                # 닫히지 않은 펜스 — 무시
                i += 1
                continue

            # j: closing fence 라인
            content = '\n'.join(lines[i + 1: j])
            for k in range(i, j + 1):
                covered[k] = True

            tag_lower = tag.lower()

            if tag_lower.startswith("filename:"):
                filepath = tag.split(":", 1)[1].strip()
                actions.append(_ParsedAction(kind="file", payload=content, filepath=filepath))

            elif tag_lower.startswith("patch:"):
                filepath = tag.split(":", 1)[1].strip()
                actions.append(_ParsedAction(kind="patch", payload=content, filepath=filepath))

            elif tag_lower in self.CODE_LANGS:
                actions.append(_ParsedAction(kind="code", payload=content, lang=tag_lower))

            elif tag_lower in self.SHELL_LANGS:
                classification = self._classify_shell_block(content)
                if classification == "script":
                    actions.append(_ParsedAction(kind="script", payload=content, lang=tag_lower))
                else:
                    for line in content.splitlines():
                        stripped = line.strip()
                        if not stripped or stripped.startswith("#"):
                            continue
                        cmd = self._strip_dollar(stripped)
                        if cmd:
                            actions.append(_ParsedAction(kind="shell", payload=cmd))

            # 알 수 없는 태그(text, json, sql, tree 등) → 무시

            i = j + 1

        # 펜스 바깥의 $ 쉘 라인 추출
        for k, line in enumerate(lines):
            if not covered[k]:
                m = self.RE_SHELL_LINE.match(line)
                if m:
                    cmd = m.group(1).strip()
                    if cmd:
                        actions.append(_ParsedAction(kind="shell", payload=cmd))

        # [ACTION:*] 태그 감지 → explicit_tag 설정 (AGENT_ACTION_TAGS_REQUIRED 모드 통과용)
        if self.RE_ACTION_TAG.search(act_text):
            for a in actions:
                a.explicit_tag = True

        return actions

    def _classify_shell_block(self, code: str) -> str:
        """쉘 코드 블록을 'commands' | 'script' 로 분류."""
        meaningful = [
            ln for ln in code.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if not meaningful:
            return "commands"  # 빈 블록 — 무시
        for line in meaningful:
            for pat in self.SCRIPT_INDICATORS:
                if pat.search(line):
                    return "script"
        return "commands"

    def _strip_dollar(self, line: str) -> str:
        """'$ git status' → 'git status'. $ 없으면 원본 그대로."""
        m = re.match(r"^\s*\$\s+(.+)$", line)
        return m.group(1).strip() if m else line.strip()

    # ─── 중복 제거 ─────────────────────────────────────────────
    def _dedupe(self, actions: List[_ParsedAction]) -> List[_ParsedAction]:
        """같은 (kind=shell, payload) 가 중복이면 1회로 축약. file/code 는 유지."""
        seen: set = set()
        out: List[_ParsedAction] = []
        for a in actions:
            if a.kind == "shell":
                key = ("shell", a.payload.strip())
                if key in seen:
                    continue
                seen.add(key)
            out.append(a)
        return out

    # ─── 실행 어댑터 ──────────────────────────────────────────
    def _exec_file(self, session, a: _ParsedAction) -> list:
        """파일 저장 — AgentRunner._save_file_blocks() 위임.

        FSD v1.1.062 §3.4: 디스크 반영 전 before(현재 디스크) vs after(신규)
        diff 를 미리보기로 출력(로그). 저장 자체의 승인은 기존 _save_file_blocks /
        response_parser 경로(auto_overwrite)가 담당 — 이중 프롬프트 회피.
        """
        if a.filepath and self._runner.diff_preview_enabled:
            try:
                from .patch_applier import PatchApplier
                applier = PatchApplier(self._runner.file_manager)
                plan = applier.compute_full_file(a.filepath, a.payload)
                if plan.success and plan.diff:
                    label = "신규" if not plan.existed else "수정"
                    print(f"\n📝 파일 변경 미리보기 ({label}): {a.filepath}")
                    diff = self._runner._preview_file_change(
                        a.filepath, plan.before_text, a.payload,
                    )
                    print(diff)
            except Exception:
                pass  # 미리보기는 표시용 — 실패해도 저장 흐름에 영향 없음
        fake = f"@@@filename:{a.filepath}\n{a.payload}\n@@@"
        return self._runner._save_file_blocks(session, fake)

    def _exec_code(self, a: _ParsedAction):
        """코드 실행 — CodeExecutor 위임."""
        from .agent_runner import ActionResult

        lang = a.lang or "python"
        print(f"\n⚙️  코드 실행 ({lang})...")
        result = self._runner.code_executor.execute(a.payload, lang)
        return _format_code_result(lang, result)

    def _exec_script(self, session, a: _ParsedAction):
        """쉘 스크립트(다중라인) — CodeExecutor 경로 + 위험 명령 1차 검사."""
        from .agent_runner import ActionResult

        lang = a.lang or "powershell"
        # 스크립트 내 첫 실행 가능 라인의 base command 를 검사
        first_token = ""
        for line in a.payload.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                first_token = stripped.split()[0].lower() if stripped.split() else ""
                break

        if first_token and first_token in self._runner.terminal_executor.DANGEROUS_COMMANDS:
            approved = self._runner._approve_dangerous(
                session, "auto_approve_dangerous_shell",
                f"shell script ({lang}) — first cmd: '{first_token}'",
            )
            if not approved:
                return ActionResult(
                    kind="code", target=lang, success=False,
                    detail="사용자 거부 (위험 명령 포함)",
                )

        print(f"\n⚙️  쉘 스크립트 실행 ({lang})...")
        result = self._runner.code_executor.execute(a.payload, lang)
        return _format_code_result(lang, result)

    def _exec_shell(self, session, a: _ParsedAction):
        """단일 쉘 명령 — AgentRunner._exec_single_shell_command() 위임."""
        return self._runner._exec_single_shell_command(session, a.payload)

    def _exec_patch(self, session, a: _ParsedAction):
        """patch 적용 — PatchApplier 위임 (FSD v1.0.115, FSD v1.1.061 중립 모듈).

        FSD v1.1.062 §3.4: compute(dry-run) → diff 미리보기 → 정책 승인 →
        승인 시 commit, 거부 시 폐기(무변경). 세션 자동승인 시 미리보기 생략 가능.
        """
        from .patch_applier import PatchApplier
        from .agent_runner import ActionResult, AgentStopReason

        if not a.filepath:
            return ActionResult(
                kind="file", target="?", success=False,
                detail="patch path 미지정",
            )

        applier = PatchApplier(self._runner.file_manager)
        auto_approve = bool(
            getattr(session, "bypass_approvals", False)
            or getattr(session, "auto_approve_file_mutation", False)
        )

        print(f"\n📝 patch 적용: {a.filepath}")

        # ── compute: 매칭·diff 산출 (디스크 미변경) ──
        plan = applier.compute(a.filepath, a.payload)

        if not plan.success:
            # 매칭/파싱 실패 — commit 없이 실패 PatchResult 형태로 보고
            from .patch_applier import PatchResult
            result = PatchResult(
                success=False, applied_count=0,
                total_count=len(plan.block_results),
                block_results=plan.block_results, error=plan.error,
            )
            return self._report_patch(a, result)

        # ── diff 미리보기 + 정책 승인 ──
        if auto_approve:
            # 세션 자동승인: diff 로그만(있으면), 바로 commit.
            # FR-062-10: 자동승인 경로도 AGENT_DIFF_MAX_LINES 요약을 거친다.
            if self._runner.diff_preview_enabled and plan.diff:
                summarized = self._runner._summarize_diff(plan.diff)
                print(f"\n📝 변경 미리보기 (자동 적용): {a.filepath}\n{summarized}")
        else:
            decision = self._runner._confirm_change(
                session.interaction_policy, a.filepath, plan.diff,
            )
            if decision == "all":
                session.auto_approve_file_mutation = True
            elif decision == "stop":
                session.stop_reason = (
                    getattr(session, "stop_reason", None)
                    or AgentStopReason.USER_STOP
                )
                return ActionResult(
                    kind="file", target=a.filepath, success=False,
                    detail="사용자 중단 (diff 승인에서 stop)",
                )
            elif decision == "no":
                return ActionResult(
                    kind="file", target=a.filepath, success=False,
                    detail="사용자 거부 (diff 미승인 — 무변경)",
                )
            # "yes" / "all" → commit 진행

        result = applier.commit(plan)
        return self._report_patch(a, result)

    def _report_patch(self, a: _ParsedAction, result):
        """PatchResult → ActionResult 보고 (FR-111-24 형식 보존)."""
        from .agent_runner import ActionResult

        # 보고 형식 (FR-111-24): N/M blocks (statuses)
        statuses = [r.status for r in result.block_results]
        status_summary = ", ".join(statuses) if statuses else "-"

        if result.success:
            detail = (
                f"patched {result.applied_count}/{result.total_count} blocks "
                f"({status_summary})"
            )
            print(f"✅ patch {a.filepath} — {detail}")
            return ActionResult(
                kind="file", target=a.filepath, success=True, detail=detail,
            )

        # 실패 — diagnostic 첨부
        diag_lines: List[str] = []
        for i, r in enumerate(result.block_results):
            tag = r.status
            if r.diagnostic:
                diag_lines.append(f"  block#{i + 1}: {tag}\n    {r.diagnostic}")
            else:
                diag_lines.append(f"  block#{i + 1}: {tag}")
        head = result.error or f"patch 실패 — {result.total_count} 블록 중 적용 안됨"
        detail = head + ("\n" + "\n".join(diag_lines) if diag_lines else "")
        print(f"❌ patch {a.filepath} — {head}")
        return ActionResult(
            kind="file", target=a.filepath, success=False, detail=detail,
        )


# ─── 헬퍼 함수 ───────────────────────────────────────────────

def _format_code_result(lang: str, result: dict):
    """CodeExecutor 결과 → ActionResult 변환."""
    from .agent_runner import ActionResult

    success = bool(result.get("success"))
    if success:
        stdout = (result.get("stdout") or "").strip()
        detail = f"returncode=0\n{stdout[:500]}" if stdout else "returncode=0"
    else:
        stderr = (result.get("stderr") or result.get("error") or "").strip()
        rc = result.get("returncode", "?")
        detail = f"returncode={rc}\n{stderr[:500]}"
    return ActionResult(kind="code", target=lang, success=success, detail=detail)
