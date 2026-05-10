"""ai_cli 배치 모드 테스트 (FSD v1.0.157)."""

# pyrefly: ignore [missing-import]
import pytest
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

# 프로젝트 루트 sys.path 추가 (`ai_cli.py` 가 루트에 위치)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ai_cli  # noqa: E402


# ───────────────── argparse 검증 ─────────────────

def test_parse_args_basic():
    """T-01: 기본 인자 조합이 namespace 에 올바르게 반영된다."""
    ns = ai_cli.parse_args([
        "-t", "claude",
        "-wp", ".",
        "-c", "auto_context", "src/*.py",
        "-p", "p.txt",
    ])
    assert ns.type == "claude"
    assert ns.workspace == "."
    assert ns.command == ["auto_context", "src/*.py"]
    assert ns.prompt == "p.txt"


def test_parse_args_invalid_type():
    """T-02: -t 의 값이 허용 범위 밖이면 SystemExit (argparse exit code 2)."""
    with pytest.raises(SystemExit) as ei:
        ai_cli.parse_args([
            "-t", "foo",
            "-wp", ".",
            "-c", "auto_context", "src/*.py",
            "-p", "p.txt",
        ])
    assert ei.value.code == 2


def test_parse_args_missing_required():
    """필수 옵션 누락 시 SystemExit."""
    with pytest.raises(SystemExit):
        ai_cli.parse_args(["-t", "claude"])


# ───────────────── main() 디스패처 검증 ─────────────────

def _make_prompt_file(tmp_path: Path, body: str = "리뷰해줘", suffix: str = "") -> Path:
    p = tmp_path / f"prompt{suffix}.txt"
    p.write_text(body, encoding="utf-8")
    return p


def test_main_unsupported_command(tmp_path):
    """T-03: -c 의 첫 토큰이 auto_context 가 아니면 exit 2."""
    prompt = _make_prompt_file(tmp_path)
    rc = ai_cli.main([
        "-t", "claude",
        "-wp", str(tmp_path),
        "-c", "read", "src/*.py",
        "-p", str(prompt),
    ])
    assert rc == 2


def test_main_pattern_missing(tmp_path):
    """T-04: -c auto_context 만 있고 패턴 토큰이 없으면 exit 2."""
    prompt = _make_prompt_file(tmp_path)
    rc = ai_cli.main([
        "-t", "claude",
        "-wp", str(tmp_path),
        "-c", "auto_context",
        "-p", str(prompt),
    ])
    assert rc == 2


def test_main_workspace_missing(tmp_path):
    """T-05: -wp 가 존재하지 않으면 exit 1."""
    prompt = _make_prompt_file(tmp_path)
    missing = tmp_path / "nope"
    rc = ai_cli.main([
        "-t", "claude",
        "-wp", str(missing),
        "-c", "auto_context", "src/*.py",
        "-p", str(prompt),
    ])
    assert rc == 1


def test_main_prompt_missing(tmp_path):
    """T-06: -p 의 파일이 없으면 exit 1 (절대경로)."""
    rc = ai_cli.main([
        "-t", "claude",
        "-wp", str(tmp_path),
        "-c", "auto_context", "src/*.py",
        "-p", str(tmp_path / "no_such_prompt.txt"),
    ])
    assert rc == 1


def test_main_prompt_missing_relative(tmp_path):
    """T-06b: 비절대경로 -p 가 워크스페이스 내에도 없으면 exit 1."""
    rc = ai_cli.main([
        "-t", "claude",
        "-wp", str(tmp_path),
        "-c", "auto_context", "src/*.py",
        "-p", "no_such_prompt.txt",          # 상대경로 → workspace 기준 탐색
    ])
    assert rc == 1


def test_main_prompt_workspace_relative(tmp_path):
    """T-06c: 비절대경로 -p 는 워크스페이스 기준으로 해석되어 정상 로드된다."""
    # workspace 안에 하위 경로로 프롬프트 파일 생성
    sub = tmp_path / "docs" / "reqs"
    sub.mkdir(parents=True)
    prompt_file = sub / "prompt.txt"
    prompt_file.write_text("리뷰해줘", encoding="utf-8")

    captured = {}

    def fake_main_batch(workspace, command, command_args, prompt):
        captured["prompt"] = prompt
        return 0

    fake_module = type("M", (), {"main_batch": staticmethod(fake_main_batch)})
    with patch.object(ai_cli, "_load_entrypoint", return_value=fake_module):
        rc = ai_cli.main([
            "-t", "claude",
            "-wp", str(tmp_path),
            "-c", "auto_context", "src/*.py",
            "-p", "docs/reqs/prompt.txt",    # 비절대경로 → workspace 기준
        ])
    assert rc == 0
    assert captured["prompt"] == "리뷰해줘"


def test_main_prompt_empty(tmp_path):
    """T-07: 빈 프롬프트 파일은 exit 1."""
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    rc = ai_cli.main([
        "-t", "claude",
        "-wp", str(tmp_path),
        "-c", "auto_context", "src/*.py",
        "-p", str(empty),
    ])
    assert rc == 1


def test_main_prompt_utf8_bom(tmp_path):
    """T-08: UTF-8 BOM 프롬프트도 정상 로드되어야 한다."""
    bom_file = tmp_path / "bom.txt"
    body = "리뷰해줘"
    bom_file.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8") + b"\n")
    loaded = ai_cli._read_prompt(bom_file)
    assert loaded == body
    # BOM (U+FEFF) 이 제거되어야 한다
    assert "﻿" not in loaded


def test_main_dispatch_calls_main_batch(tmp_path):
    """T-10: main_batch 가 호출되며 반환값이 그대로 exit code 로 전달된다."""
    prompt = _make_prompt_file(tmp_path, body="패턴 적용해줘")

    captured = {}

    def fake_main_batch(workspace, command, command_args, prompt):
        captured["workspace"] = workspace
        captured["command"] = command
        captured["command_args"] = command_args
        captured["prompt"] = prompt
        return 0

    fake_module = type("M", (), {"main_batch": staticmethod(fake_main_batch)})
    with patch.object(ai_cli, "_load_entrypoint", return_value=fake_module):
        rc = ai_cli.main([
            "-t", "claude",
            "-wp", str(tmp_path),
            "-c", "auto_context", "src/*.py",
            "-p", str(prompt),
        ])
    assert rc == 0
    assert captured["command"] == "auto_context"
    assert captured["command_args"] == "src/*.py"
    assert captured["prompt"] == "패턴 적용해줘"
    assert Path(captured["workspace"]).resolve() == tmp_path.resolve()


def test_main_dispatch_returns_main_batch_failure(tmp_path):
    """T-09 변형: main_batch 가 1 을 반환하면 exit 1."""
    prompt = _make_prompt_file(tmp_path)
    fake_module = type("M", (), {"main_batch": staticmethod(lambda **kw: 1)})
    with patch.object(ai_cli, "_load_entrypoint", return_value=fake_module):
        rc = ai_cli.main([
            "-t", "claude",
            "-wp", str(tmp_path),
            "-c", "auto_context", "src/*.py",
            "-p", str(prompt),
        ])
    assert rc == 1


def test_main_keyboard_interrupt_exit_130(tmp_path):
    """T-11: KeyboardInterrupt 발생 시 exit 130."""
    prompt = _make_prompt_file(tmp_path)

    def boom(**kw):
        raise KeyboardInterrupt()

    fake_module = type("M", (), {"main_batch": staticmethod(boom)})
    with patch.object(ai_cli, "_load_entrypoint", return_value=fake_module):
        rc = ai_cli.main([
            "-t", "claude",
            "-wp", str(tmp_path),
            "-c", "auto_context", "src/*.py",
            "-p", str(prompt),
        ])
    assert rc == 130


def test_main_unhandled_exception_exit_3(tmp_path):
    """T-14: 일반 예외는 exit 3."""
    prompt = _make_prompt_file(tmp_path)

    def boom(**kw):
        raise RuntimeError("boom")

    fake_module = type("M", (), {"main_batch": staticmethod(boom)})
    with patch.object(ai_cli, "_load_entrypoint", return_value=fake_module):
        rc = ai_cli.main([
            "-t", "claude",
            "-wp", str(tmp_path),
            "-c", "auto_context", "src/*.py",
            "-p", str(prompt),
        ])
    assert rc == 3


# ───────────────── _load_entrypoint 검증 ─────────────────

def test_load_entrypoint_exposes_main_batch():
    """T-12: 세 엔트리포인트 모두 main_batch 심볼을 노출한다."""
    for filename in ai_cli.TYPE_TO_FILE.values():
        module = ai_cli._load_entrypoint(filename)
        assert hasattr(module, "main_batch"), f"{filename} 에 main_batch 가 없음"
        assert callable(module.main_batch)


# ───────────────── _parse_auto_context_args 검증 (엔트리포인트 헬퍼) ─────────────────

def test_parse_auto_context_single_pattern():
    module = ai_cli._load_entrypoint("claude-ai-chat-code.py")
    qc, patterns, q = module._parse_auto_context_args("src/*.py")
    assert qc is False
    assert patterns == ["src/*.py"]
    assert q == ""


def test_parse_auto_context_bracket_patterns():
    module = ai_cli._load_entrypoint("claude-ai-chat-code.py")
    qc, patterns, q = module._parse_auto_context_args("[src/*.py, docs/*.md]")
    assert patterns == ["src/*.py", "docs/*.md"]


def test_parse_auto_context_qc_flag():
    module = ai_cli._load_entrypoint("claude-ai-chat-code.py")
    qc, patterns, q = module._parse_auto_context_args("-qc src/*.py")
    assert qc is True
    assert patterns == ["src/*.py"]


def test_parse_auto_context_unclosed_bracket():
    module = ai_cli._load_entrypoint("claude-ai-chat-code.py")
    with pytest.raises(ValueError, match="닫는 대괄호"):
        module._parse_auto_context_args("[src/*.py")

if __name__ == "__main__":
    unittest.main()