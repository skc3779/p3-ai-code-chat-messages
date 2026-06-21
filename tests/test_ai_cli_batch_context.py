"""Batch ``/context`` parsing, execution, and provider delegation tests."""

from __future__ import annotations

import builtins
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import ai_cli
from src.batch_context import (
    ContextBatchInputError,
    ContextBatchRequest,
    prepare_context_batch,
    run_context_batch,
)


def test_context_local_flags_are_preserved_without_quoting():
    args = ai_cli.parse_args([
        "-t", "gemini", "-wp", "C:/work",
        "-c", "context", "-l", "-nt", "[a/**/*.*,b/**/*.*]",
        "-p", "prompt.md",
    ])
    assert args.command == ["context", "-l", "-nt", "[a/**/*.*,b/**/*.*]"]


def test_long_context_flags_and_reordered_top_level_options_are_preserved():
    args = ai_cli.parse_args([
        "-p", "prompt.md",
        "--command", "context", "--large", "--no-tree", "[a/*.py,b/*.md]",
        "--workspace", ".", "--type", "claude",
    ])
    assert args.command == ["context", "--large", "--no-tree", "[a/*.py,b/*.md]"]


@pytest.mark.parametrize("duplicate", [
    ["-t", "claude", "--type", "gemini"],
    ["-wp", ".", "--workspace", "."],
    ["-p", "a", "--prompt", "b"],
    ["-c", "context", "x", "--command", "context", "y"],
])
def test_logical_top_level_duplicates_are_rejected(duplicate):
    defaults = ["-t", "claude", "-wp", ".", "-c", "context", "x", "-p", "p"]
    logical = {
        "-t": "type", "--type": "type",
        "-wp": "workspace", "--workspace": "workspace",
        "-c": "command", "--command": "command",
        "-p": "prompt", "--prompt": "prompt",
    }
    target = logical[duplicate[0]]
    argv, index = [], 0
    while index < len(defaults):
        token = defaults[index]
        if logical.get(token) == target:
            index += 2
            continue
        argv.extend(defaults[index:index + 2])
        index += 2
    with pytest.raises(SystemExit) as exc:
        ai_cli.parse_args(argv + duplicate)
    assert exc.value.code == 2


def test_main_dispatches_context_tokens_and_prompt(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("질문", encoding="utf-8")
    captured = {}

    def main_batch(**kwargs):
        captured.update(kwargs)
        return 0

    module = SimpleNamespace(main_batch=main_batch)
    with patch.object(ai_cli, "_load_entrypoint", return_value=module):
        result = ai_cli.main([
            "-t", "gemini", "-wp", str(tmp_path),
            "-c", "context", "-l", "-nt", "[a/*.py,b/*.md]",
            "-p", str(prompt),
        ])
    assert result == 0
    assert captured["command"] == "context"
    assert captured["command_args"] == "-l -nt [a/*.py,b/*.md]"
    assert captured["prompt"] == "질문"


def test_invalid_utf8_prompt_returns_one_without_loading_provider(tmp_path):
    prompt = tmp_path / "invalid.md"
    prompt.write_bytes(b"\xff\xfe")
    with patch.object(ai_cli, "_load_entrypoint") as load_entrypoint:
        result = ai_cli.main([
            "-t", "gemini", "-wp", str(tmp_path),
            "-c", "context", "src/*.py", "-p", str(prompt),
        ])
    assert result == 1
    load_entrypoint.assert_not_called()


def test_prepare_context_batch_parses_shared_contract():
    request = prepare_context_batch("-l -nt [a/*.py,b/*.md]", " 질문 \n")
    assert request == ContextBatchRequest(
        file_patterns=["a/*.py", "b/*.md"],
        prompt="질문",
        large=True,
        no_tree=True,
    )


@pytest.mark.parametrize("args", ["-x a/*.py", "[a/*.py,b/*.md"])
def test_prepare_context_batch_reports_parser_input_errors(args):
    with pytest.raises(ContextBatchInputError) as exc:
        prepare_context_batch(args, "질문")
    assert exc.value.exit_code == 1


def test_prepare_context_batch_rejects_inline_question():
    with pytest.raises(ContextBatchInputError, match="-p 파일로만") as exc:
        prepare_context_batch("a/*.py 인라인 질문", "파일 질문")
    assert exc.value.exit_code == 2


def _assistant(tmp_path: Path, response: str = "응답"):
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir(exist_ok=True)
    source.write_text("x = 1", encoding="utf-8")
    file_manager = SimpleNamespace(
        workspace_dir=tmp_path,
        list_files=Mock(return_value=[source]),
    )
    response_parser = SimpleNamespace(parse_and_save=Mock(return_value=[]))
    return SimpleNamespace(
        file_manager=file_manager,
        chat=Mock(return_value=response),
        response_parser=response_parser,
    )


def test_normal_context_calls_chat_once_with_error_propagation(tmp_path, capsys):
    assistant = _assistant(tmp_path)
    request = ContextBatchRequest(["src/*.py"], "질문", False, True)
    result = run_context_batch(
        assistant=assistant, provider="claude", request=request, streaming=False
    )
    assert result == 0
    assistant.chat.assert_called_once_with(
        "질문",
        streaming=False,
        include_context=True,
        file_patterns=["src/*.py"],
        include_tree=False,
        raise_on_error=True,
    )
    assert capsys.readouterr().out.count("🤖 AI: 응답") == 1


def test_streaming_context_does_not_duplicate_assistant_output(tmp_path, capsys):
    assistant = _assistant(tmp_path)
    request = ContextBatchRequest(["src/*.py"], "질문", False, False)
    assert run_context_batch(
        assistant=assistant, provider="gemini", request=request, streaming=True
    ) == 0
    assert "🤖 AI:" not in capsys.readouterr().out


def test_context_batch_never_reads_stdin(tmp_path):
    assistant = _assistant(tmp_path)
    request = ContextBatchRequest(["src/*.py"], "질문", False, False)
    with patch.object(builtins, "input", side_effect=AssertionError("stdin read")):
        assert run_context_batch(
            assistant=assistant, provider="gemini", request=request, streaming=True
        ) == 0


def test_no_match_returns_one_without_chat(tmp_path, capsys):
    assistant = _assistant(tmp_path)
    request = ContextBatchRequest(["missing/*.py"], "질문", False, False)
    assert run_context_batch(
        assistant=assistant, provider="genai", request=request, streaming=True
    ) == 1
    assistant.chat.assert_not_called()
    assert "해당하는 파일이 없습니다" in capsys.readouterr().err


def test_large_context_uses_processor_and_prints_final_once(tmp_path, capsys):
    assistant = _assistant(tmp_path)
    request = ContextBatchRequest(["src/*.py"], "질문", True, True)
    processor = Mock()
    processor.process.return_value = "통합 응답"
    with patch("src.batch_context.LargeContextProcessor", return_value=processor) as cls:
        result = run_context_batch(
            assistant=assistant, provider="claude", request=request, streaming=True
        )
    assert result == 0
    cls.assert_called_once_with(assistant, assistant.file_manager, provider="claude")
    processor.process.assert_called_once_with(["src/*.py"], "질문", include_tree=False)
    assistant.chat.assert_not_called()
    assert capsys.readouterr().out.count("🤖 AI: 통합 응답") == 1


@pytest.mark.parametrize("error,code", [(RuntimeError("api"), 3), (KeyboardInterrupt(), 130)])
def test_context_runtime_errors_have_stable_exit_codes(tmp_path, error, code):
    assistant = _assistant(tmp_path)
    assistant.chat.side_effect = error
    request = ContextBatchRequest(["src/*.py"], "질문", False, False)
    assert run_context_batch(
        assistant=assistant, provider="claude", request=request, streaming=True
    ) == code


def test_context_runtime_error_does_not_expose_exception_details(tmp_path, capsys):
    assistant = _assistant(tmp_path)
    assistant.chat.side_effect = RuntimeError("TOP-SECRET PRIVATE-PROMPT")
    request = ContextBatchRequest(["src/*.py"], "PRIVATE-PROMPT", False, False)
    assert run_context_batch(
        assistant=assistant, provider="gemini", request=request, streaming=True
    ) == 3
    error = capsys.readouterr().err
    assert "context 배치 처리 실패 (gemini)" in error
    assert "TOP-SECRET" not in error
    assert "PRIVATE-PROMPT" not in error


@pytest.mark.parametrize("filename", ai_cli.TYPE_TO_FILE.values())
def test_provider_validates_context_before_environment_and_auth(filename):
    module = ai_cli._load_entrypoint(filename)
    with patch.object(module, "load_environment") as load_environment:
        result = module.main_batch(".", "context", "src/*.py inline", "prompt")
    assert result == 2
    load_environment.assert_not_called()


@pytest.mark.parametrize("filename", ai_cli.TYPE_TO_FILE.values())
def test_provider_context_delegation_is_shared(filename):
    module = ai_cli._load_entrypoint(filename)
    prepared = ContextBatchRequest(["src/*.py"], "질문", False, False)
    assistant = object()
    constructor_name = {
        "claude-ai-chat-code.py": "ClaudeCodeAssistant",
        "gemini-ai-chat-code.py": "GeminiCodeAssistant",
        "gen-ai-chat-code.py": "GenAICodeAssistant",
    }[filename]
    env = {
        "claude-ai-chat-code.py": {"ANTHROPIC_API_KEY": "key"},
        "gemini-ai-chat-code.py": {"GEMINI_API_KEY": "key"},
        "gen-ai-chat-code.py": {
            "ENDPOINT_URL": "url", "YOUR_CLIENT_KEY": "key", "YOUR_CLIENT_SECRET": "secret"
        },
    }[filename]
    with (
        patch.object(module, "prepare_context_batch", return_value=prepared),
        patch.object(module, "load_environment"),
        patch.object(module.TokenManager, "reload_from_env"),
        patch.dict(module.os.environ, env, clear=True),
        patch.object(module, constructor_name, return_value=assistant),
        patch.object(module, "run_context_batch", return_value=0) as run,
    ):
        assert module.main_batch("/work", "context", "src/*.py", "질문") == 0
    assert run.call_args.kwargs["assistant"] is assistant
    assert run.call_args.kwargs["request"] == prepared
    assert run.call_args.kwargs["streaming"] is True


@pytest.mark.parametrize("filename", ai_cli.TYPE_TO_FILE.values())
def test_provider_context_keyboard_interrupt_returns_130(filename):
    module = ai_cli._load_entrypoint(filename)
    prepared = ContextBatchRequest(["src/*.py"], "질문", False, False)
    constructor_name = {
        "claude-ai-chat-code.py": "ClaudeCodeAssistant",
        "gemini-ai-chat-code.py": "GeminiCodeAssistant",
        "gen-ai-chat-code.py": "GenAICodeAssistant",
    }[filename]
    env = {
        "claude-ai-chat-code.py": {"ANTHROPIC_API_KEY": "key"},
        "gemini-ai-chat-code.py": {"GEMINI_API_KEY": "key"},
        "gen-ai-chat-code.py": {
            "ENDPOINT_URL": "url", "YOUR_CLIENT_KEY": "key", "YOUR_CLIENT_SECRET": "secret"
        },
    }[filename]
    with (
        patch.object(module, "prepare_context_batch", return_value=prepared),
        patch.object(module, "load_environment"),
        patch.object(module.TokenManager, "reload_from_env"),
        patch.dict(module.os.environ, env, clear=True),
        patch.object(module, constructor_name, return_value=object()),
        patch.object(module, "run_context_batch", side_effect=KeyboardInterrupt),
    ):
        assert module.main_batch("/work", "context", "src/*.py", "질문") == 130


@pytest.mark.parametrize("filename", ai_cli.TYPE_TO_FILE.values())
@pytest.mark.parametrize("error,code", [(KeyboardInterrupt(), 130), (RuntimeError("SECRET"), 3)])
def test_provider_context_initialization_errors_are_sanitized(filename, error, code, capsys):
    module = ai_cli._load_entrypoint(filename)
    with (
        patch.object(module, "load_environment", side_effect=error),
        patch.object(module.TokenManager, "reload_from_env"),
    ):
        assert module.main_batch("/work", "context", "src/*.py", "질문") == code
    assert "SECRET" not in capsys.readouterr().err

# ---------------------------------------------------------------------------
# TC-S: 응답 자동 저장 (-o / --output)
# ---------------------------------------------------------------------------

def test_output_option_is_parsed_into_args(tmp_path):
    prompt = tmp_path / "p.md"
    prompt.write_text("q", encoding="utf-8")
    args = ai_cli.parse_args([
        "-t", "claude", "-wp", str(tmp_path),
        "-c", "context", "src/*.py",
        "-p", str(prompt),
        "-o", str(tmp_path / "out"),
    ])
    assert args.output == str(tmp_path / "out")


def test_output_option_is_not_consumed_as_context_token(tmp_path):
    prompt = tmp_path / "p.md"
    prompt.write_text("q", encoding="utf-8")
    args = ai_cli.parse_args([
        "-t", "claude", "-wp", str(tmp_path),
        "-c", "context", "src/*.py",
        "-o", str(tmp_path / "out"),
        "-p", str(prompt),
    ])
    assert args.command == ["context", "src/*.py"]


def test_main_passes_output_dir_to_main_batch(tmp_path):
    prompt = tmp_path / "p.md"
    prompt.write_text("질문", encoding="utf-8")
    out_dir = tmp_path / "responses"
    captured = {}

    def main_batch(**kwargs):
        captured.update(kwargs)
        return 0

    module = SimpleNamespace(main_batch=main_batch)
    with patch.object(ai_cli, "_load_entrypoint", return_value=module):
        result = ai_cli.main([
            "-t", "gemini", "-wp", str(tmp_path),
            "-c", "context", "src/*.py",
            "-p", str(prompt),
            "-o", str(out_dir),
        ])
    assert result == 0
    assert captured["output_dir"] == str(out_dir.resolve())


def test_main_creates_output_dir_if_missing(tmp_path):
    prompt = tmp_path / "p.md"
    prompt.write_text("q", encoding="utf-8")
    out_dir = tmp_path / "new" / "nested"
    module = SimpleNamespace(main_batch=lambda **kw: 0)
    with patch.object(ai_cli, "_load_entrypoint", return_value=module):
        result = ai_cli.main([
            "-t", "claude", "-wp", str(tmp_path),
            "-c", "context", "src/*.py",
            "-p", str(prompt),
            "-o", str(out_dir),
        ])
    assert result == 0
    assert out_dir.is_dir()


def test_main_returns_one_if_output_path_is_file(tmp_path):
    prompt = tmp_path / "p.md"
    prompt.write_text("q", encoding="utf-8")
    conflict = tmp_path / "conflict"
    conflict.write_text("data")
    with patch.object(ai_cli, "_load_entrypoint") as load_ep:
        result = ai_cli.main([
            "-t", "claude", "-wp", str(tmp_path),
            "-c", "context", "src/*.py",
            "-p", str(prompt),
            "-o", str(conflict),
        ])
    assert result == 1
    load_ep.assert_not_called()


def test_run_context_batch_saves_response_when_output_dir_given(tmp_path, capsys):
    assistant = _assistant(tmp_path)
    request = ContextBatchRequest(["src/*.py"], "질문", False, False)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = run_context_batch(
        assistant=assistant, provider="claude", request=request,
        streaming=False, output_dir=out_dir,
    )
    assert result == 0
    files = list(out_dir.glob("context_*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "응답" in content
    assert "Provider: claude" in content
    assert "💾 응답 저장:" in capsys.readouterr().out


def test_no_output_dir_calls_parse_and_save_with_auto_overwrite(tmp_path):
    assistant = _assistant(tmp_path, response="응답")
    request = ContextBatchRequest(["src/*.py"], "질문", False, False)
    result = run_context_batch(
        assistant=assistant, provider="claude", request=request,
        streaming=False, output_dir=None,
    )
    assert result == 0
    assistant.response_parser.parse_and_save.assert_called_once_with(
        "응답", auto_overwrite=True
    )


def test_no_output_dir_prints_count_when_blocks_found(tmp_path, capsys):
    assistant = _assistant(tmp_path, response="응답")
    assistant.response_parser.parse_and_save.return_value = ["a.py", "b.py"]
    request = ContextBatchRequest(["src/*.py"], "질문", False, False)
    run_context_batch(
        assistant=assistant, provider="claude", request=request,
        streaming=False, output_dir=None,
    )
    assert "총 2개 파일이 저장되었습니다" in capsys.readouterr().out


def test_no_output_dir_no_blocks_exits_zero_silently(tmp_path, capsys):
    assistant = _assistant(tmp_path, response="블록 없는 응답")
    assistant.response_parser.parse_and_save.return_value = []
    request = ContextBatchRequest(["src/*.py"], "질문", False, False)
    result = run_context_batch(
        assistant=assistant, provider="claude", request=request,
        streaming=False, output_dir=None,
    )
    assert result == 0
    assert "저장" not in capsys.readouterr().out


def test_save_response_file_contains_metadata_and_body(tmp_path):
    from src.batch_context import _save_response
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    path = _save_response("AI 응답 내용", out_dir, "gemini", ["src/*.py", "docs/*.md"])
    text = path.read_text(encoding="utf-8")
    assert "Provider: gemini" in text
    assert "src/*.py" in text
    assert "docs/*.md" in text
    assert "AI 응답 내용" in text


def test_save_response_filename_matches_timestamp_pattern(tmp_path):
    from src.batch_context import _save_response
    import re
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    path = _save_response("x", out_dir, "claude", ["p"])
    assert re.match(r"context_\d{8}_\d{6}\.md$", path.name)


def test_run_context_batch_save_failure_returns_one(tmp_path, capsys):
    assistant = _assistant(tmp_path)
    request = ContextBatchRequest(["src/*.py"], "질문", False, False)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with patch("src.batch_context._save_response", side_effect=OSError("disk full")):
        result = run_context_batch(
            assistant=assistant, provider="claude", request=request,
            streaming=False, output_dir=out_dir,
        )
    assert result == 1
    assert "응답 저장 실패" in capsys.readouterr().err


def test_large_context_batch_saves_response_when_output_dir_given(tmp_path, capsys):
    assistant = _assistant(tmp_path)
    request = ContextBatchRequest(["src/*.py"], "질문", True, True)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    processor = Mock()
    processor.process.return_value = "통합 응답"
    with patch("src.batch_context.LargeContextProcessor", return_value=processor):
        result = run_context_batch(
            assistant=assistant, provider="claude", request=request,
            streaming=True, output_dir=out_dir,
        )
    assert result == 0
    files = list(out_dir.glob("context_*.md"))
    assert len(files) == 1
    assert "통합 응답" in files[0].read_text(encoding="utf-8")


@pytest.mark.parametrize("filename", ai_cli.TYPE_TO_FILE.values())
def test_provider_main_batch_passes_output_dir_to_run(filename, tmp_path):
    module = ai_cli._load_entrypoint(filename)
    prepared = ContextBatchRequest(["src/*.py"], "질문", False, False)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    constructor_name = {
        "claude-ai-chat-code.py": "ClaudeCodeAssistant",
        "gemini-ai-chat-code.py": "GeminiCodeAssistant",
        "gen-ai-chat-code.py": "GenAICodeAssistant",
    }[filename]
    env = {
        "claude-ai-chat-code.py": {"ANTHROPIC_API_KEY": "key"},
        "gemini-ai-chat-code.py": {"GEMINI_API_KEY": "key"},
        "gen-ai-chat-code.py": {
            "ENDPOINT_URL": "url", "YOUR_CLIENT_KEY": "key", "YOUR_CLIENT_SECRET": "secret"
        },
    }[filename]
    with (
        patch.object(module, "prepare_context_batch", return_value=prepared),
        patch.object(module, "load_environment"),
        patch.object(module.TokenManager, "reload_from_env"),
        patch.dict(module.os.environ, env, clear=True),
        patch.object(module, constructor_name, return_value=object()),
        patch.object(module, "run_context_batch", return_value=0) as run,
    ):
        assert module.main_batch("/work", "context", "src/*.py", "질문",
                                 output_dir=str(out_dir)) == 0
    assert run.call_args.kwargs["output_dir"] == out_dir


if __name__ == "__main__":
    import unittest
    unittest.main()
