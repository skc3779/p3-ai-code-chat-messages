"""REP v1.1.032 evaluator-gated termination tests."""

from __future__ import annotations

import json
import io
import os
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agent_goal_evaluator import AcceptanceCriterion, AgentGoalEvaluator
from src.agent_runner import AgentRunner, AgentSession, AgentStopReason
from src.agent_session_store import AgentSessionStore


class SequenceAssistant:
    def __init__(self, responses, hook=None):
        self.responses = list(responses)
        self.hook = hook
        self.calls = 0
        self.conversation_history = []
        self.system_prompt = "main-system"

    def chat(self, *_args, **_kwargs):
        self.calls += 1
        if self.hook:
            self.hook(self.calls)
        return self.responses.pop(0) if self.responses else ""


class FakeProcess:
    def __init__(self, output=b"1 passed\n", returncode=0, timeout=False):
        self.stdout = io.BytesIO(output)
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False

    def wait(self, timeout=None):
        if self.timeout and not self.killed:
            from subprocess import TimeoutExpired
            raise TimeoutExpired("pytest", timeout)
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def make_runner(tmp_path: Path, responses, *, env=None, hook=None) -> AgentRunner:
    assistant = SequenceAssistant(responses, hook=hook)
    file_manager = MagicMock()
    file_manager.workspace_dir = tmp_path
    terminal = MagicMock()
    terminal.DANGEROUS_COMMANDS = {"rm", "del"}
    values = {
        "AGENT_EVAL_GATE": "1",
        "AGENT_EVAL_MAX_REJECTS": "3",
        "AGENT_EVAL_TEST_TIMEOUT": "10",
        "AGENT_EVAL_OUTPUT_MAX_BYTES": "4096",
        "AGENT_MAX_ITERATIONS": "3",
        "AGENT_AUTO_SAVE_INTERVAL": "0",
    }
    values.update(env or {})
    with patch.dict(os.environ, values, clear=False), patch("src.agent_runner.CodeExecutor"):
        runner = AgentRunner(
            assistant=assistant,
            file_manager=file_manager,
            code_executor=MagicMock(),
            terminal_executor=terminal,
            response_parser=MagicMock(),
            cli_handler=MagicMock(),
            context_builder=None,
            streaming=False,
        )
    runner._dispatcher.dispatch = MagicMock(return_value=[])
    runner._ask_continue = MagicMock(return_value=("c", None))
    runner._input_listener = MagicMock()
    runner._input_listener.enabled = False
    runner._input_listener.is_stop_requested.return_value = False
    runner._input_listener.paused.return_value = nullcontext()
    return runner


def evaluator(tmp_path: Path, assistant=None, **kwargs) -> AgentGoalEvaluator:
    assistant = assistant or SequenceAssistant([])
    return AgentGoalEvaluator(
        tmp_path,
        assistant,
        streaming=False,
        timeout=kwargs.get("timeout", 10),
        output_limit=kwargs.get("output_limit", 4096),
        report_path="docs/완료보고서.md",
    )


class TestCriteriaExtraction:
    def test_korean_tests_report_and_explicit_file_are_extracted(self, tmp_path):
        ev = evaluator(tmp_path)
        criteria = ev.extract_from_goal(
            "모든 테스트 통과를 검증하고 완료 보고서를 docs/final.md에 작성하고 create result.json"
        )
        assert {item.check_type for item in criteria} == {"cmd_exit_zero", "file_exists"}
        assert any(item.target == "docs/final.md" for item in criteria)
        assert all(item.provenance == "extracted" for item in criteria)

    def test_english_test_goal_is_extracted_and_deduplicated(self, tmp_path):
        (tmp_path / "tests").mkdir()
        ev = evaluator(tmp_path)
        criteria = ev.extract_from_goal("write tests and make all tests pass")
        assert len(criteria) == 1
        assert criteria[0].target == "python -m unittest discover -s tests"

    def test_unmatched_goal_has_no_silent_criterion(self, tmp_path):
        assert evaluator(tmp_path).extract_from_goal("improve the implementation") == []

    def test_report_path_is_associated_with_report_not_earlier_markdown(self, tmp_path):
        criteria = evaluator(tmp_path).extract_from_goal(
            "docs/spec.md를 참고하고 완료 보고서를 docs/final.md에 작성"
        )
        report = [item for item in criteria if "보고서" in item.description]
        assert len(report) == 1
        assert report[0].target == "docs/final.md"

    @pytest.mark.parametrize(
        "goal",
        ["write final report to docs/final.md", "create completion report docs/final.md"],
    )
    def test_english_verb_first_report_path_is_authoritative(self, tmp_path, goal):
        criteria = evaluator(tmp_path).extract_from_goal(goal)
        assert len(criteria) == 1
        assert criteria[0].target == "docs/final.md"

    def test_english_pathless_report_uses_configured_default(self, tmp_path):
        criteria = evaluator(tmp_path).extract_from_goal("write a final report")
        assert len(criteria) == 1
        assert criteria[0].target == "docs/완료보고서.md"

    def test_model_criteria_are_additive_and_strict(self, tmp_path):
        ev = evaluator(tmp_path)
        parsed, malformed = ev.parse_model_criteria(
            "@@@criteria\nA1 | file_exists | result.txt | | result exists\n@@@end"
        )
        assert not malformed
        assert parsed[0].id == "M1"
        assert parsed[0].provenance == "model"

    @pytest.mark.parametrize(
        "body",
        [
            "M1 | unknown | x | | bad",
            "M1 | cmd_exit_zero | rm -rf . | | unsafe",
            "M1 | file_exists | ../escape.txt | | escape",
            "broken line",
        ],
    )
    def test_malformed_or_unsafe_model_criteria_are_rejected(self, tmp_path, body):
        parsed, malformed = evaluator(tmp_path).parse_model_criteria(
            f"@@@criteria\n{body}\n@@@end"
        )
        assert parsed == []
        assert malformed


class TestSafeDeterministicEvaluation:
    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf .",
            "python -c 'print(1)'",
            "python -m pytest; rm -rf .",
            "python -m pytest | tee out",
            "/usr/bin/python -m pytest",
            "python -m unknown",
            "python -m pytest --version",
            "python -m pytest --junitxml=../outside.xml",
            "python -m pytest --collect-only",
            "python -m pytest @args.txt",
        ],
    )
    def test_command_allowlist_rejects_shell_and_unknown_forms(self, command):
        assert AgentGoalEvaluator.validate_test_command(command) is None

    def test_command_uses_argv_without_shell_parser(self, tmp_path):
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", "python -m pytest")

        def fake_popen(argv, **kwargs):
            assert argv[0] != "/bin/bash"
            assert kwargs["shell"] is False
            assert kwargs["cwd"] == str(tmp_path.resolve())
            return FakeProcess()

        with patch("src.agent_goal_evaluator.subprocess.Popen", side_effect=fake_popen):
            evaluator(tmp_path).evaluate([criterion])
        assert criterion.status == "passed"

    @pytest.mark.parametrize("output", [b"no tests ran\n", b"collected 0 items\n", b"Ran 0 tests\nOK\n"])
    def test_zero_tests_never_passes(self, tmp_path, output):
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", "python -m pytest")

        with patch("src.agent_goal_evaluator.subprocess.Popen", return_value=FakeProcess(output)):
            evaluator(tmp_path).evaluate([criterion])
        assert criterion.status == "failed"
        assert "zero-tests-detected" in criterion.evidence

    def test_collect_only_output_never_passes(self, tmp_path):
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", "python -m pytest")
        process = FakeProcess(b"collected 2 items\n<Module test_sample.py>\n", returncode=0)
        with patch("src.agent_goal_evaluator.subprocess.Popen", return_value=process) as popen:
            evaluator(tmp_path).evaluate([criterion])
        assert criterion.status == "failed"
        assert "zero-tests-detected" in criterion.evidence
        assert popen.call_args.args[0][-2:] == ["-o", "addopts="]

    def test_real_pytest_config_collect_only_is_neutralized(self, tmp_path):
        (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --collect-only\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_real.py").write_text("def test_real():\n    assert True\n", encoding="utf-8")
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", "python -m pytest")
        evaluator(tmp_path, timeout=30, output_limit=8192).evaluate([criterion])
        assert criterion.status == "passed", criterion.evidence
        assert "passed" in criterion.evidence

    def test_real_pytest_argsfile_cannot_escape_workspace(self, tmp_path):
        outside = tmp_path.parent / "outside-argsfile"
        outside.mkdir(exist_ok=True)
        marker = outside / "executed.txt"
        test_file = outside / "test_outside.py"
        test_file.write_text(
            "from pathlib import Path\n"
            f"def test_outside():\n    Path({str(marker)!r}).write_text('ran')\n",
            encoding="utf-8",
        )
        (tmp_path / "args.txt").write_text(str(test_file), encoding="utf-8")
        criterion = AcceptanceCriterion(
            "A1", "tests", "cmd_exit_zero", "python -m pytest @args.txt"
        )
        evaluator(tmp_path, timeout=30, output_limit=8192).evaluate([criterion])
        assert criterion.status == "unverified"
        assert not marker.exists()

    def test_timeout_is_failed(self, tmp_path):
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", "python -m pytest")
        with patch(
            "src.agent_goal_evaluator.subprocess.Popen",
            return_value=FakeProcess(timeout=True),
        ):
            evaluator(tmp_path).evaluate([criterion])
        assert criterion.status == "failed"
        assert "timeout" in criterion.evidence

    def test_invalid_security_bounds_make_command_unverified(self, tmp_path):
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", "python -m pytest")
        evaluator(tmp_path, timeout=None, output_limit=None).evaluate([criterion])
        assert criterion.status == "unverified"

    def test_output_cap_kills_child_without_unbounded_capture(self, tmp_path):
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", "python -m pytest")
        process = FakeProcess(b"x" * 100)
        with patch("src.agent_goal_evaluator.subprocess.Popen", return_value=process):
            evaluator(tmp_path, output_limit=16).evaluate([criterion])
        assert process.killed
        assert criterion.status == "failed"
        assert "output-limit>16" in criterion.evidence

    def test_real_child_output_is_killed_at_cap(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_loud.py").write_text(
            "def test_loud():\n"
            "    value = 'x' * 200000\n"
            "    assert value == 'short'\n",
            encoding="utf-8",
        )
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", "python -m pytest")
        evaluator(tmp_path, timeout=30, output_limit=512).evaluate([criterion])
        assert criterion.status == "failed"
        assert "output-limit>512" in criterion.evidence

    def test_relative_file_passes_but_traversal_and_symlink_escape_do_not(self, tmp_path):
        (tmp_path / "ok.txt").write_text("ok", encoding="utf-8")
        ev = evaluator(tmp_path)
        good = AcceptanceCriterion("A1", "good", "file_exists", "ok.txt")
        bad = AcceptanceCriterion("A2", "bad", "file_exists", "../outside.txt")
        ev.evaluate([good, bad])
        assert good.status == "passed"
        assert bad.status == "unverified"

        outside = tmp_path.parent / "outside-eval"
        outside.mkdir(exist_ok=True)
        link = tmp_path / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation unavailable")
        escaped = AcceptanceCriterion("A3", "escaped", "file_exists", "link/result.txt")
        ev.evaluate([escaped])
        assert escaped.status == "unverified"

    @pytest.mark.parametrize(
        "command",
        ["python -m pytest link/test_outside.py", "python -m unittest discover -s link"],
    )
    def test_test_runner_symlink_paths_never_execute(self, tmp_path, command):
        outside = tmp_path.parent / "outside-tests"
        outside.mkdir(exist_ok=True)
        (outside / "test_outside.py").write_text("raise RuntimeError('must not run')", encoding="utf-8")
        try:
            (tmp_path / "link").symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation unavailable")
        criterion = AcceptanceCriterion("A1", "tests", "cmd_exit_zero", command)
        with patch("src.agent_goal_evaluator.subprocess.Popen") as popen:
            evaluator(tmp_path).evaluate([criterion])
        popen.assert_not_called()
        assert criterion.status == "unverified"

    def test_file_exists_requires_a_regular_file(self, tmp_path):
        (tmp_path / "result.txt").mkdir()
        criterion = AcceptanceCriterion("A1", "file", "file_exists", "result.txt")
        evaluator(tmp_path).evaluate([criterion])
        assert criterion.status == "failed"

    def test_non_utf8_file_contains_is_bounded_failure(self, tmp_path):
        (tmp_path / "binary.txt").write_bytes(b"\xff")
        criterion = AcceptanceCriterion(
            "A1", "contains", "file_contains", "binary.txt", expected="needle"
        )
        evaluator(tmp_path).evaluate([criterion])
        assert criterion.status == "failed"
        assert "read failed" in criterion.evidence

    def test_llm_evaluation_restores_nested_history_and_system_prompt(self, tmp_path):
        assistant = SequenceAssistant([])
        assistant.conversation_history = [{"role": "user", "content": {"nested": [1]}}]
        assistant.system_prompt = {"name": "main"}
        expected_history = json.loads(json.dumps(assistant.conversation_history))
        expected_system = dict(assistant.system_prompt)

        def chat(*_args, **_kwargs):
            assistant.conversation_history.append({"role": "model", "content": "mutated"})
            assistant.system_prompt = "mutated"
            return '{"results":[{"id":"M1","passed":true,"evidence":"ok"}]}'

        assistant.chat = chat
        criterion = AcceptanceCriterion("M1", "manual", "llm", provenance="model")
        evaluator(tmp_path, assistant).evaluate([criterion])
        assert criterion.status == "passed"
        assert assistant.conversation_history == expected_history
        assert assistant.system_prompt == expected_system

    def test_malformed_llm_verdict_fails_closed_and_restores_state(self, tmp_path):
        assistant = SequenceAssistant(["not-json"])
        before = [{"role": "user", "content": ["deep"]}]
        assistant.conversation_history = json.loads(json.dumps(before))
        criterion = AcceptanceCriterion("M1", "manual", "llm", provenance="model")
        evaluator(tmp_path, assistant).evaluate([criterion])
        assert criterion.status == "unverified"
        assert assistant.conversation_history == before

    def test_provider_exception_text_is_not_exposed(self, tmp_path):
        assistant = SequenceAssistant([])

        def fail(*_args, **_kwargs):
            raise RuntimeError("SECRET-TOKEN-123")

        assistant.chat = fail
        criterion = AcceptanceCriterion("M1", "manual", "llm", provenance="model")
        evaluator(tmp_path, assistant).evaluate([criterion])
        assert criterion.status == "unverified"
        assert "SECRET" not in criterion.evidence


class TestRunnerGateLifecycle:
    def test_done_claim_passes_only_after_file_evidence(self, tmp_path):
        (tmp_path / "result.txt").write_text("done", encoding="utf-8")
        runner = make_runner(tmp_path, ["plan", "[ACTION]\nnothing\n[AGENT_DONE]"])
        session = runner.run(goal="create result.txt", max_iterations_override=1)
        assert session.stop_reason == AgentStopReason.DONE
        assert session.acceptance_criteria[0].status == "passed"

    def test_premature_done_is_rejected_then_cap_reports_not_met(self, tmp_path):
        runner = make_runner(tmp_path, ["plan", "[ACTION]\nnothing\n[AGENT_DONE]"], env={"AGENT_EVAL_MAX_REJECTS": "3"})
        session = runner.run(goal="create result.txt", max_iterations_override=1)
        assert session.stop_reason == AgentStopReason.GOAL_NOT_MET
        assert session.eval_reject_count == 1

    def test_rejected_claim_can_continue_and_pass(self, tmp_path):
        def create_on_third_call(call_number):
            if call_number == 3:
                (tmp_path / "result.txt").write_text("done", encoding="utf-8")

        runner = make_runner(
            tmp_path,
            ["plan", "[ACTION]\nnothing\n[AGENT_DONE]", "[ACTION]\nnothing\n[AGENT_DONE]"],
            hook=create_on_third_call,
        )
        session = runner.run(goal="create result.txt", max_iterations_override=2)
        assert session.stop_reason == AgentStopReason.DONE
        assert session.eval_reject_count == 1

    def test_cap_can_classify_satisfied_goal_done_without_token(self, tmp_path):
        (tmp_path / "result.txt").write_text("done", encoding="utf-8")
        runner = make_runner(tmp_path, ["plan", "[ACTION]\nnothing"])
        session = runner.run(goal="create result.txt", max_iterations_override=1)
        assert session.stop_reason == AgentStopReason.DONE

    def test_gate_off_preserves_legacy_cap_reason(self, tmp_path):
        runner = make_runner(
            tmp_path,
            ["plan", "[ACTION]\nnothing"],
            env={"AGENT_EVAL_GATE": "0"},
        )
        session = runner.run(goal="unmatched goal", max_iterations_override=1)
        assert session.stop_reason == AgentStopReason.MAX_ITERATIONS

    def test_gate_off_preserves_immediate_done(self, tmp_path):
        runner = make_runner(
            tmp_path,
            ["plan", "[AGENT_DONE]"],
            env={"AGENT_EVAL_GATE": "0"},
        )
        session = runner.run(goal="unmatched goal", max_iterations_override=1)
        assert session.stop_reason == AgentStopReason.DONE

    def test_no_criteria_and_failed_single_reprompt_is_unverified(self, tmp_path):
        runner = make_runner(tmp_path, ["plan", "still no criteria"])
        session = runner.run(goal="improve quality", max_iterations_override=1)
        assert session.stop_reason == AgentStopReason.GOAL_UNVERIFIED
        assert session.criteria_reprompted is True
        assert len(session.iterations) == 0

    def test_malformed_plan_and_malformed_reprompt_fail_closed_with_authoritative_criterion(self, tmp_path):
        (tmp_path / "required.txt").write_text("ok", encoding="utf-8")
        runner = make_runner(
            tmp_path,
            ["@@@criteria\nbroken\n@@@end", "@@@criteria\nstill broken\n@@@end"],
        )
        session = runner.run(goal="create required.txt", max_iterations_override=1)
        assert session.stop_reason == AgentStopReason.GOAL_UNVERIFIED
        assert len(session.iterations) == 0

    def test_llm_only_criterion_cannot_self_certify_done(self, tmp_path):
        runner = make_runner(
            tmp_path,
            [
                "@@@criteria\nM1 | llm | | | quality is good\n@@@end",
                "[AGENT_DONE]",
            ],
        )
        session = runner.run(goal="improve quality", max_iterations_override=1)
        assert session.stop_reason == AgentStopReason.GOAL_UNVERIFIED

    def test_resume_discards_forged_extracted_and_does_not_stop_early(self, tmp_path):
        forged = AcceptanceCriterion(
            "A1", "forged", "file_exists", "already.txt", provenance="extracted", status="passed"
        )
        session = AgentSession(
            goal="create required.txt",
            plan="plan",
            acceptance_criteria=[forged],
        )
        runner = make_runner(tmp_path, ["[ACTION]\nnothing"])
        resumed = runner.run(resume_session=session, max_iterations_override=1)
        assert resumed.acceptance_criteria[0].target == "required.txt"
        assert len(resumed.iterations) == 1
        assert resumed.stop_reason == AgentStopReason.GOAL_NOT_MET

    def test_legacy_resume_extracts_from_goal(self, tmp_path):
        (tmp_path / "required.txt").write_text("ok", encoding="utf-8")
        session = AgentSession(goal="create required.txt", plan="plan")
        runner = make_runner(tmp_path, ["[AGENT_DONE]"])
        resumed = runner.run(resume_session=session, max_iterations_override=1)
        assert resumed.stop_reason == AgentStopReason.DONE
        assert resumed.acceptance_criteria[0].target == "required.txt"


class TestPersistenceHardening:
    def test_roundtrip_reconstructs_typed_criteria(self, tmp_path):
        store = AgentSessionStore(str(tmp_path))
        session = AgentSession(
            goal="create result.txt",
            acceptance_criteria=[AcceptanceCriterion("A1", "result", "file_exists", "result.txt")],
        )
        restored = store._deserialize(store._serialize(session))
        assert isinstance(restored.acceptance_criteria[0], AcceptanceCriterion)

    def test_malformed_unknown_and_oversized_records_are_dropped(self, tmp_path):
        store = AgentSessionStore(str(tmp_path))
        payload = {
            "goal": "goal",
            "acceptance_criteria": [
                {"id": "M1", "description": "bad", "check_type": "shell", "provenance": "model"},
                {"id": "M2", "description": "x" * 2000, "check_type": "llm", "provenance": "model"},
            ],
        }
        restored = store._deserialize(json.dumps(payload))
        assert restored.acceptance_criteria == []

    def test_store_does_not_execute_or_evaluate(self, tmp_path):
        store = AgentSessionStore(str(tmp_path))
        payload = {
            "goal": "tests pass",
            "acceptance_criteria": [
                {
                    "id": "M1",
                    "description": "unsafe",
                    "check_type": "cmd_exit_zero",
                    "target": "rm -rf .",
                    "provenance": "model",
                }
            ],
        }
        with patch("src.agent_goal_evaluator.subprocess.Popen") as run:
            restored = store._deserialize(json.dumps(payload))
        run.assert_not_called()
        assert restored.acceptance_criteria[0].target == "rm -rf ."


@pytest.mark.parametrize(
    "name,value,expected",
    [
        ("AGENT_EVAL_MAX_REJECTS", "-1", 0),
        ("AGENT_EVAL_MAX_REJECTS", "999", 0),
        ("AGENT_EVAL_MAX_REJECTS", "NaN", 0),
    ],
)
def test_invalid_reject_env_is_conservative(tmp_path, name, value, expected):
    runner = make_runner(tmp_path, [], env={name: value})
    assert runner.eval_max_rejects == expected


@pytest.mark.parametrize("value", ["0", "-1", "601", "NaN", "inf"])
def test_invalid_timeout_disables_command_verification(tmp_path, value):
    runner = make_runner(tmp_path, [], env={"AGENT_EVAL_TEST_TIMEOUT": value})
    assert runner.eval_test_timeout is None


def test_unittest_only_workspace_does_not_require_pytest(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text("import unittest\n", encoding="utf-8")
    assert evaluator(tmp_path).detect_test_command() == "python -m unittest discover -s tests"
