"""
AgentGoalEvaluator — 완료 기준 게이트 (FSD v1.1.062 §2.2 / FR-062-08)

종료(성공) 판정의 **단독 권위**. 자기보고(`[AGENT_DONE]`)는 신뢰하지 않고,
목표에서 결정론적으로 추출한 기준 + 모델이 추가한 기준을 **증거로 검증**한다.

3-tier provenance:
  extracted (목표에서 결정론적 추출, 권위·불변)
    → model (PLAN 의 @@@criteria 블록, add-only 병합)
      → 없으면 GOAL_UNVERIFIED (검증할 기준이 0개)

검증 타입: file_exists / file_contains / cmd_exit_zero / llm.

shell-free verifier (보안 핵심):
  cmd_exit_zero 는 `subprocess.Popen(argv, shell=False)` 전용 실행기로만 실행한다.
  - pytest/unittest/python allowlist
  - workspace 봉쇄 (cwd 고정, `..` traversal 거부)
  - zero-test 위장(테스트 0개 통과 위장) 차단
"""

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


# ─── 데이터 ────────────────────────────────────────────────────
@dataclass
class Criterion:
    """단일 완료 기준.

    kind       : "file_exists" | "file_contains" | "cmd_exit_zero" | "llm"
    provenance : "extracted" (권위·불변) | "model" (add-only)
    target     : 경로 / 명령 / 설명
    expect     : file_contains 기대 문자열 등 (선택)
    passed     : 평가 결과 (None=미검증)
    evidence   : 평가 근거 텍스트
    """
    id: str
    kind: str
    provenance: str
    target: str
    expect: Optional[str] = None
    passed: Optional[bool] = None
    evidence: str = ""


@dataclass
class CriteriaSnapshot:
    """evaluate() 결과 요약."""
    criteria: List[Criterion] = field(default_factory=list)
    all_passed: bool = False
    unmet: List[Criterion] = field(default_factory=list)
    unverified: bool = False


# zero-test 위장 차단용 패턴 (pytest / unittest 공통)
_ZERO_TEST_MARKERS = (
    "collected 0 items",
    "no tests ran",
    "ran 0 tests",
    "no tests were run",
)

# cmd_exit_zero allowlist — argv[0] basename (확장자 제거 후)
_ALLOWED_BIN = {"python", "python3", "pytest", "py.test"}
# `python -m <mod>` 로 허용되는 모듈
_ALLOWED_PY_MODULES = {"pytest", "unittest"}


class AgentGoalEvaluator:
    """완료 기준 추출 · 병합 · 증거 기반 검증.

    의존성: file_manager (workspace_dir / read_file 인터페이스).
    """

    MAX_TOTAL = 32

    # @@@criteria ... @@@ 블록 (PLAN 응답)
    RE_CRITERIA_BLOCK = re.compile(
        r"@{3,}\s*criteria\s*\n(.*?)(?:\n\s*@{3,}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )

    # 추출 휴리스틱: 파일 경로 언급 ("xxx.py 생성/만들/작성")
    RE_FILE_MENTION = re.compile(
        r"([\w./\-]+\.[A-Za-z0-9]{1,8})"  # 경로처럼 보이는 토큰
        r"\s*(?:파일\s*)?(?:을|를|이|가)?\s*"
        r"(?:생성|만들|작성|추가|구현|create|add|write|implement)",
    )
    # "테스트 통과" / pytest / unittest 신호
    RE_TEST_SIGNAL = re.compile(
        r"(pytest|unittest|테스트\s*(?:가|를|는)?\s*통과|tests?\s+pass|모든\s*테스트)",
        re.IGNORECASE,
    )

    def __init__(self, file_manager):
        self.file_manager = file_manager
        self.cmd_timeout = self._env_int("AGENT_EVAL_CMD_TIMEOUT", 60, minimum=1)

    # ─── 추출 (provenance=extracted) ─────────────────────────
    def extract_from_goal(self, goal: str) -> List[Criterion]:
        """목표 텍스트에서 결정론적으로 권위 기준을 추출한다.

        과도추출 금지 — 명확한 신호만. 추출 0개여도 정상(빈 리스트).
        """
        criteria: List[Criterion] = []
        seen_targets: set = set()
        text = goal or ""

        # 1) 파일 생성/작성 언급 → file_exists
        for m in self.RE_FILE_MENTION.finditer(text):
            path = m.group(1).strip().strip("`\"'")
            if not path or path in seen_targets:
                continue
            # 너무 일반적인 토큰(확장자만 등) 방어
            if path.startswith(".") and "/" not in path:
                continue
            seen_targets.add(path)
            criteria.append(Criterion(
                id=f"extracted:file_exists:{path}",
                kind="file_exists",
                provenance="extracted",
                target=path,
            ))

        # 2) "테스트 통과" / pytest / unittest → cmd_exit_zero
        if self.RE_TEST_SIGNAL.search(text):
            # 명시적 명령이 없으면 보수적 기본: pytest
            cmd = self._guess_test_command(text)
            tgt_id = f"extracted:cmd_exit_zero:{cmd}"
            if cmd not in seen_targets:
                seen_targets.add(cmd)
                criteria.append(Criterion(
                    id=tgt_id,
                    kind="cmd_exit_zero",
                    provenance="extracted",
                    target=cmd,
                ))

        return criteria[: self.MAX_TOTAL]

    @staticmethod
    def _guess_test_command(text: str) -> str:
        """목표 텍스트에서 테스트 명령을 추정. 명시 pytest 인용이 있으면 그대로,
        없으면 보수적 기본 'pytest -q'."""
        # 명시적 pytest 호출 인용(경로/플래그 포함, ASCII 토큰만)을 우선.
        # \w 는 유니코드 한글까지 매칭하므로 ASCII 한정 클래스를 직접 명시.
        m = re.search(
            r"(?:python\s+-m\s+)?pytest(?:\s+[A-Za-z0-9_./\-]+)*", text
        )
        if m:
            return m.group(0).strip()
        if re.search(r"unittest", text, re.IGNORECASE):
            return "python -m unittest"
        return "pytest -q"

    # ─── 파싱 (provenance=model) ─────────────────────────────
    def parse_model_criteria(self, plan: str) -> List[Criterion]:
        """PLAN 응답의 `@@@criteria ... @@@` 블록에서 모델 기준을 파싱한다.

        각 줄 형식:
          file_exists:path
          file_contains:path::expected
          cmd_exit_zero:command
          llm:description
        블록 없으면 빈 리스트.
        """
        if not plan:
            return []
        m = self.RE_CRITERIA_BLOCK.search(plan)
        if not m:
            return []

        criteria: List[Criterion] = []
        for raw in m.group(1).splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            kind, _, rest = line.partition(":")
            kind = kind.strip().lower()
            rest = rest.strip()
            if not rest:
                continue

            if kind == "file_exists":
                criteria.append(Criterion(
                    id=f"model:file_exists:{rest}",
                    kind="file_exists", provenance="model", target=rest,
                ))
            elif kind == "file_contains":
                path, _, expect = rest.partition("::")
                path = path.strip()
                expect = expect.strip()
                if not path or not expect:
                    continue
                criteria.append(Criterion(
                    id=f"model:file_contains:{path}::{expect}",
                    kind="file_contains", provenance="model",
                    target=path, expect=expect,
                ))
            elif kind == "cmd_exit_zero":
                # FR-062-08 (Major-1): self-grant 게이트 우회 차단.
                # 모델 provenance 의 cmd_exit_zero 는 **테스트 러너 형태**(pytest/
                # unittest 등)만 게이트 자격을 인정한다. `python -c "sys.exit(0)"`
                # 같은 임의 명령 주입으로 자기부여 DONE 을 막는다.
                # (extracted provenance 는 목표에서 결정론 추출이므로 제한 없음.)
                if not self._is_test_runner_cmd(rest):
                    print(
                        "⚠️  모델 기준 무시(게이트 자격 없음 — 테스트러너 아님): "
                        f"{rest}"
                    )
                    continue
                criteria.append(Criterion(
                    id=f"model:cmd_exit_zero:{rest}",
                    kind="cmd_exit_zero", provenance="model", target=rest,
                ))
            elif kind == "llm":
                criteria.append(Criterion(
                    id=f"model:llm:{rest}",
                    kind="llm", provenance="model", target=rest,
                ))
            # 알 수 없는 kind 는 무시

        return criteria

    @staticmethod
    def _is_test_runner_cmd(command: str) -> bool:
        """명령이 테스트 러너 형태인지 판정 (Major-1 게이트 자격).

        허용 형태: `pytest ...`, `py.test ...`, `python -m pytest ...`,
        `python -m unittest ...`, `unittest ...`. 그 외(예: `python -c ...`,
        `python script.py`)는 게이트 자격 없음.
        """
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        if not argv:
            return False
        bin0 = os.path.basename(argv[0]).lower()
        bin0 = re.sub(r"\.(exe|bat|cmd)$", "", bin0)
        if bin0 in {"pytest", "py.test", "unittest"}:
            return True
        if bin0 in {"python", "python3"}:
            # `python -m pytest|unittest` 형태만 테스트 러너로 인정
            if len(argv) >= 3 and argv[1] == "-m":
                mod = argv[2].split(".")[0]
                return mod in _ALLOWED_PY_MODULES
            return False
        return False

    # ─── 병합 ────────────────────────────────────────────────
    def merge_criteria(
        self,
        extracted: List[Criterion],
        model: List[Criterion],
        max_total: int = MAX_TOTAL,
    ) -> List[Criterion]:
        """extracted 우선·불변, model 은 add-only(중복 id 제외), 상한 적용."""
        merged: List[Criterion] = []
        seen: set = set()
        for c in extracted:
            if c.id in seen:
                continue
            seen.add(c.id)
            merged.append(c)
            if len(merged) >= max_total:
                return merged
        for c in model:
            if c.id in seen:
                continue
            seen.add(c.id)
            merged.append(c)
            if len(merged) >= max_total:
                break
        return merged

    # ─── 평가 ────────────────────────────────────────────────
    def evaluate(
        self, criteria: List[Criterion], *, run_commands: bool = True
    ) -> CriteriaSnapshot:
        """각 기준을 검증하고 요약을 반환한다.

        - file_exists   : workspace 기준 경로 존재
        - file_contains : 파일 읽어 expect 포함 여부
        - cmd_exit_zero : shell-free verifier 로 실행, exit 0 → passed
        - llm           : 검증 불가 → passed=None (미검증 기여)

        all_passed : non-llm 기준이 모두 True 이고 llm 기준이 없을 때만 True.
        unverified : 기준 0개 또는 llm 기준 존재로 확정 불가.
        """
        if not criteria:
            return CriteriaSnapshot(
                criteria=[], all_passed=False, unmet=[], unverified=True,
            )

        has_llm = False
        for c in criteria:
            if c.kind == "file_exists":
                self._eval_file_exists(c)
            elif c.kind == "file_contains":
                self._eval_file_contains(c)
            elif c.kind == "cmd_exit_zero":
                if run_commands:
                    self._eval_cmd_exit_zero(c)
                else:
                    c.passed = None
                    c.evidence = "명령 미실행 (run_commands=False)"
            elif c.kind == "llm":
                has_llm = True
                c.passed = None
                c.evidence = "LLM 기준 — 자동 검증 불가 (미검증)"
            else:
                c.passed = None
                c.evidence = f"알 수 없는 기준 종류: {c.kind}"

        unmet = [c for c in criteria if c.passed is False]
        non_llm = [c for c in criteria if c.kind != "llm"]
        non_llm_all_passed = bool(non_llm) and all(
            c.passed is True for c in non_llm
        )

        # all_passed: non-llm 전부 통과 AND llm 없음
        all_passed = non_llm_all_passed and not has_llm
        # unverified: 확정 불가 — 평가 가능한 기준이 전부 미검증(None)이거나
        # llm 기준이 섞여 있어 성공을 단정할 수 없을 때.
        evaluable_results = [c.passed for c in non_llm]
        no_concrete = len(non_llm) == 0 or all(
            r is None for r in evaluable_results
        )
        unverified = no_concrete or (has_llm and not unmet)

        return CriteriaSnapshot(
            criteria=list(criteria),
            all_passed=all_passed,
            unmet=unmet,
            unverified=unverified,
        )

    # ─── 개별 검증기 ─────────────────────────────────────────
    def _resolve_in_workspace(self, rel: str) -> Optional[Path]:
        """workspace 기준 경로 해석 + `..` traversal 봉쇄. 위반 시 None."""
        ws = Path(self.file_manager.workspace_dir).resolve()
        candidate = (ws / rel).resolve()
        try:
            candidate.relative_to(ws)
        except ValueError:
            return None
        return candidate

    def _eval_file_exists(self, c: Criterion) -> None:
        path = self._resolve_in_workspace(c.target)
        if path is None:
            c.passed = False
            c.evidence = "workspace 밖 경로 거부 (.. traversal)"
            return
        if path.exists():
            c.passed = True
            c.evidence = f"존재함: {c.target}"
        else:
            c.passed = False
            c.evidence = f"파일 없음: {c.target}"

    def _eval_file_contains(self, c: Criterion) -> None:
        path = self._resolve_in_workspace(c.target)
        if path is None:
            c.passed = False
            c.evidence = "workspace 밖 경로 거부 (.. traversal)"
            return
        if not path.exists():
            c.passed = False
            c.evidence = f"파일 없음: {c.target}"
            return
        try:
            body = self.file_manager.read_file(path)
        except Exception as e:
            c.passed = False
            c.evidence = f"읽기 실패: {e}"
            return
        if body is None:
            c.passed = False
            c.evidence = "읽기 실패 (None)"
            return
        if c.expect and c.expect in body:
            c.passed = True
            c.evidence = f"기대 문자열 포함: {c.expect!r}"
        else:
            c.passed = False
            c.evidence = f"기대 문자열 미포함: {c.expect!r}"

    def _eval_cmd_exit_zero(self, c: Criterion) -> None:
        rc, out = self._run_command_shellfree(c.target)
        tail = (out or "").strip()[-400:]
        if rc != 0:
            c.passed = False
            c.evidence = f"exit={rc}\n{tail}"
            return
        # zero-test 위장 차단: exit 0 이어도 테스트가 0개면 실패 처리
        low = (out or "").lower()
        if any(mark in low for mark in _ZERO_TEST_MARKERS):
            c.passed = False
            c.evidence = f"테스트 0개 (zero-test 위장 차단)\n{tail}"
            return
        c.passed = True
        c.evidence = f"exit=0\n{tail}"

    # ─── shell-free verifier (보안 핵심) ─────────────────────
    def _run_command_shellfree(self, command: str) -> Tuple[int, str]:
        """allowlist 검증 후 shell=False 로 명령 실행.

        Returns (exit_code, combined_output). 차단/오류 시 exit=-1.
        """
        try:
            argv = shlex.split(command)
        except ValueError as e:
            return -1, f"명령 파싱 실패: {e}"
        if not argv:
            return -1, "빈 명령"

        ok, reason = self._is_allowed(argv)
        if not ok:
            return -1, f"차단된 명령: {reason}"

        ws = Path(self.file_manager.workspace_dir).resolve()
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(ws),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,                # 보안: 절대 shell 경유 금지
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return -1, f"실행 파일 없음: {argv[0]}"
        except Exception as e:
            return -1, f"실행 오류: {e}"

        try:
            out, _ = proc.communicate(timeout=self.cmd_timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
            return -1, f"타임아웃 ({self.cmd_timeout}s 초과)"
        return int(proc.returncode), out or ""

    def _is_allowed(self, argv: List[str]) -> Tuple[bool, str]:
        """allowlist + workspace 봉쇄 검사.

        허용: python/python3/pytest/py.test, 또는 `python -m pytest|unittest`.
        경로 인자에 `..` traversal 이 있으면 거부.
        """
        bin0 = os.path.basename(argv[0]).lower()
        # .exe 등 확장자 제거 (windows 호환)
        bin0 = re.sub(r"\.(exe|bat|cmd)$", "", bin0)

        if bin0 in {"python", "python3"}:
            # python -m <mod> 패턴이면 모듈 allowlist 강제
            if len(argv) >= 3 and argv[1] == "-m":
                mod = argv[2].split(".")[0]
                if mod not in _ALLOWED_PY_MODULES:
                    return False, f"허용되지 않은 python 모듈: {argv[2]}"
            # python <script.py> / python -m pytest 등은 허용
        elif bin0 in {"pytest", "py.test"}:
            pass
        else:
            return False, f"allowlist 외 명령: {argv[0]}"

        # 경로 인자 traversal 검사 (모든 인자 토큰)
        for tok in argv[1:]:
            if ".." in tok.replace("\\", "/").split("/"):
                return False, f".. traversal 인자 거부: {tok}"
            if os.path.isabs(tok):
                # 절대경로 인자는 workspace 밖일 수 있어 거부
                # (단, -m 옵션값 등 비-경로 토큰은 isabs 가 False)
                ws = Path(self.file_manager.workspace_dir).resolve()
                try:
                    Path(tok).resolve().relative_to(ws)
                except ValueError:
                    return False, f"workspace 밖 절대경로 인자 거부: {tok}"

        return True, ""

    # ─── 유틸 ────────────────────────────────────────────────
    @staticmethod
    def _env_int(name: str, default: int, minimum: Optional[int] = None) -> int:
        try:
            val = int(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default
        if minimum is not None and val < minimum:
            return default
        return val
