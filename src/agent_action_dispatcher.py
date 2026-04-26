"""
AgentActionDispatcher (FSD v1.0.107)

[ACT] 블록을 분석해 단일 경로로만 실행되도록 라우팅한다.
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
    """[ACT] 블록 → 단일 경로 라우팅 디스패처.

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

    SHELL_LANGS = {"bash", "sh", "shell", "powershell", "ps1"}
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
        for a in actions:
            if a.kind == "file":
                results += self._exec_file(session, a)
            elif a.kind == "code":
                results.append(self._exec_code(a))
            elif a.kind == "script":
                results.append(self._exec_script(session, a))
            elif a.kind == "shell":
                results.append(self._exec_shell(session, a))
            elif a.kind == "patch":
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

    # ─── 파싱 ──────────────────────────────────────────────────
    def _parse(self, act_text: str) -> List[_ParsedAction]:
        """act_text 를 파싱하여 _ParsedAction 리스트를 반환.

        1. 펜스 블록을 추출하면서 각 블록의 (start, end) 인덱스를 기록.
        2. 펜스 영역을 공백으로 마스킹한 텍스트에서 `$ ...` 쉘 라인 추출.
        3. 중복 shell 명령 제거는 _dedupe() 에서 처리.
        """
        actions: List[_ParsedAction] = []
        fence_spans: list = []  # (start_idx, end_idx) — 마스킹용

        # [1] 펜스 블록 추출
        for m in self.RE_FENCE.finditer(act_text):
            fence_spans.append((m.start(), m.end()))
            tag = m.group(2).strip()
            code = m.group(3)

            # filename:path → file action
            if tag.lower().startswith("filename:"):
                filepath = tag.split(":", 1)[1].strip()
                actions.append(_ParsedAction(
                    kind="file", payload=code, filepath=filepath,
                ))
                continue

            # patch:path → patch action (FSD v1.0.115)
            if tag.lower().startswith("patch:"):
                filepath = tag.split(":", 1)[1].strip()
                actions.append(_ParsedAction(
                    kind="patch", payload=code, filepath=filepath,
                ))
                continue

            lang = tag.lower()

            # 코드 언어 (python, javascript)
            if lang in self.CODE_LANGS:
                actions.append(_ParsedAction(
                    kind="code", payload=code, lang=lang,
                ))
                continue

            # 쉘 계열 언어 → 분류기
            if lang in self.SHELL_LANGS:
                classification = self._classify_shell_block(code)
                if classification == "script":
                    actions.append(_ParsedAction(
                        kind="script", payload=code, lang=lang,
                    ))
                else:
                    # commands — 라인별로 분해
                    for line in code.splitlines():
                        stripped = line.strip()
                        if not stripped or stripped.startswith("#"):
                            continue
                        cmd = self._strip_dollar(stripped)
                        if cmd:
                            actions.append(_ParsedAction(
                                kind="shell", payload=cmd,
                            ))
                continue

            # 알 수 없는 태그(text, json 등) → 무시
            # 단, 코드 블록 자체는 fence_spans 에 기록됨

        # [2] 펜스 영역 마스킹 → 외부 텍스트에서 $ 라인 추출
        masked = list(act_text)
        for start, end in fence_spans:
            for i in range(start, min(end, len(masked))):
                masked[i] = ' '
        masked_text = ''.join(masked)

        for m in self.RE_SHELL_LINE.finditer(masked_text):
            cmd = m.group(1).strip()
            if cmd:
                actions.append(_ParsedAction(kind="shell", payload=cmd))

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
        """파일 저장 — AgentRunner._save_file_blocks() 위임."""
        fake = f"```filename:{a.filepath}\n{a.payload}\n```"
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
        """patch 적용 — AgentPatchApplier 위임 (FSD v1.0.115)."""
        from .agent_patch_applier import AgentPatchApplier
        from .agent_runner import ActionResult

        if not a.filepath:
            return ActionResult(
                kind="file", target="?", success=False,
                detail="patch path 미지정",
            )

        applier = AgentPatchApplier(self._runner.file_manager)
        auto_approve = bool(
            getattr(session, "bypass_approvals", False)
            or getattr(session, "auto_approve_file_mutation", False)
        )
        on_first_approval = lambda: self._runner._approve_dangerous(
            session, "auto_approve_file_mutation",
            f"파일 patch '{a.filepath}'",
        )

        print(f"\n📝 patch 적용: {a.filepath}")
        result = applier.apply(
            a.filepath,
            a.payload,
            auto_approve=auto_approve,
            on_first_approval=on_first_approval,
        )

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
