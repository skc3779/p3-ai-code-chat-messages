"""Goal completion criteria and shell-free evaluator for ``/agents``.

All criterion inputs are treated as untrusted, including records restored from a
session JSON file.  Command criteria are intentionally restricted to supported
Python test runners and are executed without a shell.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple


MAX_CRITERIA = 32
MAX_ID_LENGTH = 32
MAX_DESCRIPTION_LENGTH = 1024
MAX_TARGET_LENGTH = 4096
MAX_EXPECTED_LENGTH = 4096
ALLOWED_CHECK_TYPES = {"file_exists", "file_contains", "cmd_exit_zero", "llm"}
ALLOWED_PROVENANCE = {"extracted", "model"}
ALLOWED_STATUSES = {"pending", "passed", "failed", "unverified"}
_SHELL_META = re.compile(r"[;&|<>`$\r\n]")
_ZERO_TESTS = re.compile(
    r"(?:no tests ran|collected\s+0\s+items|ran\s+0\s+tests?)",
    re.IGNORECASE,
)
_PYTEST_EXECUTED = re.compile(r"\b[1-9]\d*\s+passed\b", re.IGNORECASE)
_UNITTEST_EXECUTED = re.compile(r"\bRan\s+[1-9]\d*\s+tests?\b", re.IGNORECASE)


@dataclass
class AcceptanceCriterion:
    id: str
    description: str
    check_type: str
    target: str = ""
    expected: str = ""
    provenance: str = "extracted"
    status: str = "pending"
    evidence: str = ""


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    if raw == "1":
        return True
    if raw == "0":
        return False
    return default


def bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> Optional[int]:
    """Return a bounded integer.

    Explicit invalid values return ``None`` so security-sensitive callers can
    disable the affected verifier rather than silently widening its authority.
    """

    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if minimum <= value <= maximum else None


class AgentGoalEvaluator:
    """Extract, validate, and evaluate bounded goal criteria."""

    RE_CRITERIA = re.compile(r"@@@criteria\s*(.*?)\s*@@@end", re.DOTALL | re.IGNORECASE)
    RE_EXPLICIT_PATH = re.compile(
        r"(?:작성|생성|create|write)\s+(?:the\s+)?[`'\"]?([\w./\\-]+\.(?:py|md|json|txt))[`'\"]?",
        re.IGNORECASE,
    )

    def __init__(
        self,
        workspace: Path,
        assistant: Any,
        *,
        streaming: bool,
        timeout: Optional[int],
        output_limit: Optional[int],
        report_path: str,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.assistant = assistant
        self.streaming = streaming
        self.timeout = timeout
        self.output_limit = output_limit
        self.report_path = report_path

    # ── criteria construction ──────────────────────────────
    def extract_from_goal(self, goal: str) -> List[AcceptanceCriterion]:
        criteria: List[AcceptanceCriterion] = []
        test_requested = bool(
            re.search(r"테스트.*(?:통과|검증|성공|작성|구현)", goal, re.IGNORECASE | re.DOTALL)
            or re.search(r"(?:write.*tests?|tests?\s+(?:pass|passing|succeed))", goal, re.IGNORECASE | re.DOTALL)
        )
        if test_requested:
            command = self.detect_test_command()
            criteria.append(AcceptanceCriterion(
                id="A1",
                description="요청된 테스트가 실제로 실행되어 모두 통과해야 함",
                check_type="cmd_exit_zero",
                target=command or "",
            ))

        report_target = self._report_path_from_goal(goal)
        report_requested = bool(
            report_target
            or re.search(r"(?:완료\s*)?보고서.*(?:작성|생성)", goal, re.IGNORECASE | re.DOTALL)
            or re.search(
                r"(?:completion|final)?\s*report.*(?:write|create)",
                goal,
                re.IGNORECASE | re.DOTALL,
            )
            or re.search(
                r"(?:write|create)\s+(?:a\s+)?(?:completion|final)?\s*report\b",
                goal,
                re.IGNORECASE,
            )
        )
        if report_requested:
            criteria.append(AcceptanceCriterion(
                id=f"A{len(criteria) + 1}",
                description="요청된 완료 보고서가 워크스페이스에 존재해야 함",
                check_type="file_exists",
                target=report_target or self.report_path,
            ))

        for target in self.RE_EXPLICIT_PATH.findall(goal):
            if report_requested and target == report_target:
                continue
            criteria.append(AcceptanceCriterion(
                id=f"A{len(criteria) + 1}",
                description=f"요청된 파일 {target}이(가) 존재해야 함",
                check_type="file_exists",
                target=target,
            ))

        return self._dedupe(criteria)

    def parse_model_criteria(self, text: str) -> Tuple[List[AcceptanceCriterion], bool]:
        """Return parsed additive criteria and whether a present block was malformed."""

        match = self.RE_CRITERIA.search(text or "")
        if not match:
            return [], False
        parsed: List[AcceptanceCriterion] = []
        malformed = False
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 4:
                malformed = True
                continue
            raw_id, check_type, target, *tail = parts
            if len(tail) == 1:
                expected, description = "", tail[0]
            else:
                expected, description = tail[0], " | ".join(tail[1:])
            criterion = AcceptanceCriterion(
                id=raw_id if raw_id.startswith("M") else f"M{len(parsed) + 1}",
                description=description,
                check_type=check_type,
                target=target,
                expected=expected,
                provenance="model",
            )
            if self.validate_record(criterion, allow_extracted=False) is None:
                malformed = True
                continue
            parsed.append(criterion)
        if not parsed:
            malformed = True
        return self._dedupe(parsed), malformed

    def restore_model_criteria(self, records: Iterable[Any]) -> List[AcceptanceCriterion]:
        restored: List[AcceptanceCriterion] = []
        for raw in list(records)[:MAX_CRITERIA]:
            criterion = self.validate_record(raw, allow_extracted=False)
            if criterion is not None:
                criterion.status = "pending"
                criterion.evidence = ""
                restored.append(criterion)
        return self._dedupe(restored)

    def validate_record(
        self, raw: Any, *, allow_extracted: bool = True
    ) -> Optional[AcceptanceCriterion]:
        if isinstance(raw, AcceptanceCriterion):
            values = vars(raw)
        elif isinstance(raw, dict):
            values = raw
        else:
            return None
        try:
            criterion = AcceptanceCriterion(
                id=str(values.get("id", "")),
                description=str(values.get("description", "")),
                check_type=str(values.get("check_type", "")),
                target=str(values.get("target", "")),
                expected=str(values.get("expected", "")),
                provenance=str(values.get("provenance", "model")),
                status=str(values.get("status", "pending")),
                evidence=str(values.get("evidence", "")),
            )
        except Exception:
            return None
        if not criterion.id or len(criterion.id) > MAX_ID_LENGTH:
            return None
        if not criterion.description or len(criterion.description) > MAX_DESCRIPTION_LENGTH:
            return None
        if criterion.check_type not in ALLOWED_CHECK_TYPES:
            return None
        if criterion.provenance not in ALLOWED_PROVENANCE:
            return None
        if not allow_extracted and criterion.provenance != "model":
            return None
        if criterion.status not in ALLOWED_STATUSES:
            return None
        if len(criterion.target) > MAX_TARGET_LENGTH or len(criterion.expected) > MAX_EXPECTED_LENGTH:
            return None
        if criterion.check_type == "cmd_exit_zero" and self.validate_test_command(criterion.target) is None:
            return None
        if criterion.check_type in {"file_exists", "file_contains"}:
            if not criterion.target or self.resolve_workspace_path(criterion.target) is None:
                return None
        if criterion.check_type == "file_contains" and not criterion.expected:
            return None
        return criterion

    # ── deterministic checks ───────────────────────────────
    def evaluate(self, criteria: Sequence[AcceptanceCriterion]) -> None:
        llm_criteria: List[AcceptanceCriterion] = []
        for criterion in criteria[:MAX_CRITERIA]:
            criterion.status = "pending"
            criterion.evidence = ""
            if criterion.check_type == "llm":
                llm_criteria.append(criterion)
                continue
            if criterion.check_type == "cmd_exit_zero":
                self._evaluate_command(criterion)
            else:
                self._evaluate_file(criterion)
        if llm_criteria:
            self._evaluate_llm(llm_criteria, criteria)

    def resolve_workspace_path(self, target: str) -> Optional[Path]:
        try:
            candidate = Path(target)
            if candidate.is_absolute() or ".." in candidate.parts:
                return None
            resolved = (self.workspace / candidate).resolve(strict=False)
            resolved.relative_to(self.workspace)
            return resolved
        except (OSError, RuntimeError, ValueError):
            return None

    def detect_test_command(self) -> Optional[str]:
        explicit = os.getenv("AGENT_EVAL_TEST_CMD")
        if explicit is not None:
            return explicit if self.validate_test_command(explicit) is not None else None
        pytest_markers = ("pytest.ini", "conftest.py")
        pyproject = self.workspace / "pyproject.toml"
        has_pytest = any((self.workspace / marker).exists() for marker in pytest_markers)
        if pyproject.exists():
            try:
                has_pytest = has_pytest or "pytest" in pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                pass
        if has_pytest and importlib.util.find_spec("pytest") is not None:
            return "python -m pytest"
        tests_dir = self.workspace / "tests"
        if tests_dir.is_dir() or any(self.workspace.glob("test_*.py")):
            return "python -m unittest discover -s tests"
        return None

    @staticmethod
    def validate_test_command(command: str) -> Optional[List[str]]:
        if not command or len(command) > MAX_TARGET_LENGTH or _SHELL_META.search(command):
            return None
        try:
            argv = shlex.split(command, posix=os.name != "nt")
        except ValueError:
            return None
        if len(argv) < 3 or len(argv) > 64:
            return None
        executable = argv[0].lower()
        if Path(executable).is_absolute() or executable not in {"python", "python3", "py"}:
            return None
        if argv[1] != "-m" or argv[2] not in {"pytest", "unittest"}:
            return None
        if "-c" in argv[1:]:
            return None
        if argv[2] == "unittest" and len(argv) > 3 and argv[3] != "discover":
            return None
        if any(_SHELL_META.search(arg) for arg in argv):
            return None
        if argv[2] == "pytest":
            safe_flags = {"-q", "-v", "-x", "--disable-warnings", "--strict-markers", "--strict-config"}
            for arg in argv[3:]:
                # pytest expands @argsfile before normal option/path handling, so
                # treating it as a relative path would bypass this allowlist.
                if arg.startswith("@"):
                    return None
                if arg in safe_flags:
                    continue
                if arg.startswith("--maxfail=") and arg.removeprefix("--maxfail=").isdigit():
                    continue
                if arg.startswith("-"):
                    return None
                path_part = arg.split("::", 1)[0]
                candidate = Path(path_part)
                if candidate.is_absolute() or ".." in candidate.parts:
                    return None
        else:
            args = argv[4:]
            index = 0
            while index < len(args):
                option = args[index]
                if option not in {"-s", "-t", "-p"} or index + 1 >= len(args):
                    return None
                value = args[index + 1]
                if option in {"-s", "-t"}:
                    candidate = Path(value)
                    if candidate.is_absolute() or ".." in candidate.parts:
                        return None
                elif "/" in value or "\\" in value or ".." in value:
                    return None
                index += 2
        return [sys.executable, *argv[1:]]

    def _evaluate_command(self, criterion: AcceptanceCriterion) -> None:
        argv = self.validate_test_command(criterion.target)
        if argv is None:
            criterion.status = "unverified"
            criterion.evidence = "unsupported or unsafe test command"
            return
        if not self._command_paths_are_contained(criterion.target):
            criterion.status = "unverified"
            criterion.evidence = "test path escapes workspace"
            return
        if self.timeout is None or self.output_limit is None:
            criterion.status = "unverified"
            criterion.evidence = "invalid evaluator timeout/output configuration"
            return
        # Do not inherit PYTHONPATH/PYTEST_ADDOPTS or provider credentials into
        # an evaluator process. Only OS process-launch essentials are retained.
        env = {
            key: os.environ[key]
            for key in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
            if key in os.environ
        }
        env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        try:
            returncode, output, exceeded = self._run_bounded_process(argv, env)
        except subprocess.TimeoutExpired:
            criterion.status = "failed"
            criterion.evidence = f"timeout>{self.timeout}s"
            return
        except OSError as exc:
            criterion.status = "failed"
            criterion.evidence = f"execution error: {exc}"
            return
        combined = output.decode("utf-8", errors="replace").strip()
        zero_tests = bool(_ZERO_TESTS.search(combined))
        tests_executed = bool(
            (_PYTEST_EXECUTED if argv[2] == "pytest" else _UNITTEST_EXECUTED).search(combined)
        )
        criterion.status = (
            "passed"
            if returncode == 0 and tests_executed and not zero_tests and not exceeded
            else "failed"
        )
        if exceeded:
            criterion.evidence = self._bounded(
                f"output-limit>{self.output_limit}; exit={returncode}; {combined}"
            )
            return
        suffix = " zero-tests-detected" if zero_tests or not tests_executed else ""
        criterion.evidence = self._bounded(f"exit={returncode}{suffix}; {combined}")

    def _run_bounded_process(
        self, argv: Sequence[str], env: dict
    ) -> Tuple[int, bytes, bool]:
        """Run argv with a hard in-memory/output-pipe cap and no shell.

        A reader thread drains the pipe while retaining at most ``output_limit``
        bytes. The child is killed as soon as it attempts to exceed the cap, so
        output cannot grow in a temporary file or an unbounded Python buffer.
        """

        assert self.timeout is not None and self.output_limit is not None
        execution_argv = list(argv)
        if len(execution_argv) >= 3 and execution_argv[2] == "pytest":
            # Neutralize project/user addopts such as --collect-only. These are
            # trusted internal argv entries, never taken from the goal/session.
            execution_argv.extend(["-o", "addopts="])
        process = subprocess.Popen(
            execution_argv,
            shell=False,
            cwd=str(self.workspace),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        output = bytearray()
        exceeded = threading.Event()

        def drain() -> None:
            stream = process.stdout
            if stream is None:
                return
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                remaining = self.output_limit - len(output)
                if remaining > 0:
                    output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    exceeded.set()
                    process.kill()
                    return

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            returncode = process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            reader.join(timeout=1)
            raise
        reader.join(timeout=1)
        if reader.is_alive():
            process.kill()
            process.wait()
            exceeded.set()
        return returncode, bytes(output), exceeded.is_set()

    def _evaluate_file(self, criterion: AcceptanceCriterion) -> None:
        path = self.resolve_workspace_path(criterion.target)
        if path is None:
            criterion.status = "unverified"
            criterion.evidence = "path escapes workspace or is invalid"
            return
        if criterion.check_type == "file_exists":
            is_file = path.is_file()
            criterion.status = "passed" if is_file else "failed"
            criterion.evidence = f"is_file={is_file} path={criterion.target}"
            return
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            criterion.status = "failed"
            criterion.evidence = f"read failed: {exc}"
            return
        criterion.status = "passed" if criterion.expected in content else "failed"
        criterion.evidence = f"contains={criterion.expected in content} path={criterion.target}"

    def _evaluate_llm(
        self,
        llm_criteria: Sequence[AcceptanceCriterion],
        all_criteria: Sequence[AcceptanceCriterion],
    ) -> None:
        history_snapshot = copy.deepcopy(getattr(self.assistant, "conversation_history", []))
        system_snapshot = copy.deepcopy(getattr(self.assistant, "system_prompt", None))
        evidence = [
            {"id": item.id, "status": item.status, "evidence": self._bounded(item.evidence)}
            for item in all_criteria
            if item.check_type != "llm"
        ]
        prompt = (
            "Evaluate these additive acceptance criteria against the deterministic evidence. "
            "Return only JSON: {\"results\":[{\"id\":\"M1\",\"passed\":true,\"evidence\":\"...\"}]}\n"
            + json.dumps({"criteria": [vars(item) for item in llm_criteria], "evidence": evidence}, ensure_ascii=False)
        )
        try:
            self.assistant.conversation_history = []
            self.assistant.system_prompt = "You are a strict goal evaluator. Never infer missing evidence."
            response = self.assistant.chat(prompt, streaming=False, include_context=False) or ""
            payload = json.loads(response)
            results = payload.get("results") if isinstance(payload, dict) else None
            by_id = {
                str(item.get("id")): item
                for item in results or []
                if isinstance(item, dict) and isinstance(item.get("passed"), bool)
            }
            for criterion in llm_criteria:
                verdict = by_id.get(criterion.id)
                if verdict is None:
                    criterion.status = "unverified"
                    criterion.evidence = "missing or malformed evaluator verdict"
                else:
                    criterion.status = "passed" if verdict["passed"] else "failed"
                    criterion.evidence = self._bounded(str(verdict.get("evidence", "")))
        except Exception:
            for criterion in llm_criteria:
                criterion.status = "unverified"
                criterion.evidence = "evaluator call failed"
        finally:
            self.assistant.conversation_history = history_snapshot
            self.assistant.system_prompt = system_snapshot

    # ── helpers ─────────────────────────────────────────────
    @staticmethod
    def _report_path_from_goal(goal: str) -> Optional[str]:
        path = r"([\w./\\-]+\.md)"
        patterns = (
            rf"(?:완료\s*)?보고서(?:를|는)?\s*[`'\"]?{path}[`'\"]?(?:에|으로)?\s*(?:작성|생성)",
            rf"(?:완료\s*)?보고서\s*(?:작성|생성)\s*(?:경로\s*)?[`'\"]?{path}",
            rf"(?:write|create)\s+(?:a\s+)?(?:completion|final)?\s*report\s+(?:to\s+)?[`'\"]?{path}",
            rf"(?:completion|final)\s+report\s+(?:at\s+)?[`'\"]?{path}",
        )
        for pattern in patterns:
            match = re.search(pattern, goal, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _command_paths_are_contained(self, command: str) -> bool:
        try:
            argv = shlex.split(command, posix=os.name != "nt")
        except ValueError:
            return False
        paths: List[str] = []
        if len(argv) >= 3 and argv[2] == "pytest":
            paths.extend(arg.split("::", 1)[0] for arg in argv[3:] if not arg.startswith("-"))
        elif len(argv) >= 4 and argv[2:4] == ["unittest", "discover"]:
            for index, arg in enumerate(argv[4:-1], start=4):
                if arg in {"-s", "-t"}:
                    paths.append(argv[index + 1])
        return all(self.resolve_workspace_path(path) is not None for path in paths)

    @staticmethod
    def _dedupe(criteria: Sequence[AcceptanceCriterion]) -> List[AcceptanceCriterion]:
        seen = set()
        result: List[AcceptanceCriterion] = []
        for criterion in criteria:
            key = (criterion.check_type, criterion.target.replace("\\", "/"), criterion.expected)
            if key in seen or len(result) >= MAX_CRITERIA:
                continue
            seen.add(key)
            criterion.id = ("A" if criterion.provenance == "extracted" else "M") + str(len(result) + 1)
            result.append(criterion)
        return result

    def _bounded(self, text: str) -> str:
        limit = self.output_limit or 1024
        return text[: min(limit, MAX_TARGET_LENGTH)]
