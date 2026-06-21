#!/usr/bin/env python3
"""ai_cli — `/auto_context`, `/context` 배치 실행 디스패처.

경로 규칙:
    -c <pattern>  : 비절대경로면 -wp 워크스페이스 기준 (FilePatternMatcher 가 자동 적용)
    -p <file>     : 비절대경로면 -wp 워크스페이스 기준으로 해석

사용 예:
    # prompt.txt 가 워크스페이스 내 docs/reqs/ 에 있는 경우
    python -m ai_cli -t claude -wp /work -c auto_context "src/*.py" -p docs/reqs/prompt.txt

    # 절대경로 사용
    python -m ai_cli -t gemini -wp /work -c auto_context "[src/*.py, docs/*.md]" -p /abs/prompt.txt
"""

import argparse
import importlib.util
import os
import sys
import traceback
from pathlib import Path


TYPE_TO_FILE = {
    "claude": "claude-ai-chat-code.py",
    "gemini": "gemini-ai-chat-code.py",
    "genai":  "gen-ai-chat-code.py",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai_cli",
        description="Batch executor for /auto_context and /context.",
    )
    parser.add_argument(
        "-t", "--type", required=True, choices=list(TYPE_TO_FILE),
        help="LLM 엔트리포인트 선택 (claude / gemini / genai)",
    )
    parser.add_argument(
        "-wp", "--workspace", required=True,
        help="작업 디렉토리 절대/상대 경로",
    )
    parser.add_argument(
        "-c", "--command", nargs="+", required=True,
        metavar=("CMD", "ARG"),
        help="실행할 명령과 인자. 예: -c auto_context src/*.py",
    )
    parser.add_argument(
        "-p", "--prompt", required=True,
        help="프롬프트(질문) 파일 경로 (UTF-8 / UTF-8 BOM 허용)",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="DIR",
        default=None,
        help="응답을 저장할 디렉토리 (지정 시 context_YYYYMMDD_HHMMSS.md 자동 생성)",
    )
    return parser


def parse_args(argv=None) -> argparse.Namespace:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    command_tokens, parser_argv = _extract_command_tokens(raw_argv)
    args = build_parser().parse_args(parser_argv)
    args.command = command_tokens
    return args


_TOP_LEVEL_OPTIONS = {
    "-t": "type",
    "--type": "type",
    "-wp": "workspace",
    "--workspace": "workspace",
    "-c": "command",
    "--command": "command",
    "-p": "prompt",
    "--prompt": "prompt",
    "-o": "output",
    "--output": "output",
}


def _option_name(token: str) -> str | None:
    option = token.split("=", 1)[0]
    return _TOP_LEVEL_OPTIONS.get(option)


def _extract_command_tokens(argv: list[str]) -> tuple[list[str], list[str]]:
    """Extract the raw command slice while preserving command-local flags."""
    occurrences: dict[str, int] = {}
    command_index = None
    for index, token in enumerate(argv):
        logical_name = _option_name(token)
        if logical_name is None:
            continue
        occurrences[logical_name] = occurrences.get(logical_name, 0) + 1
        if logical_name == "command" and command_index is None:
            command_index = index

    duplicates = sorted(name for name, count in occurrences.items() if count > 1)
    if duplicates:
        build_parser().error(f"최상위 옵션을 중복 지정할 수 없습니다: {', '.join(duplicates)}")
    if command_index is None:
        # Let argparse produce its standard missing-required-argument error.
        return [], argv
    if "=" in argv[command_index]:
        build_parser().error("--command=<value> 형식은 지원하지 않습니다. --command 뒤에 값을 지정하세요.")

    end = command_index + 1
    while end < len(argv) and _option_name(argv[end]) is None:
        end += 1
    command_tokens = argv[command_index + 1:end]
    if not command_tokens:
        build_parser().error("-c/--command 뒤에 명령을 지정하세요.")

    # A harmless placeholder lets argparse validate all remaining top-level
    # options without interpreting context-local -l/-nt tokens.
    parser_argv = argv[:command_index] + [argv[command_index], "__command__"] + argv[end:]
    return command_tokens, parser_argv


def _load_entrypoint(filename: str):
    """루트 디렉토리의 하이픈 포함 엔트리포인트를 동적 임포트한다."""
    repo_root = Path(__file__).resolve().parent
    # 엔트리포인트가 `from src import ...` 를 수행하므로 repo_root 가 sys.path 에 있어야 한다.
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    file_path = repo_root / filename
    if not file_path.is_file():
        raise FileNotFoundError(f"엔트리포인트 파일을 찾을 수 없습니다: {file_path}")
    spec = importlib.util.spec_from_file_location("_ai_cli_entrypoint", file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"spec 생성 실패: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_prompt(prompt_path: Path) -> str:
    """UTF-8 / UTF-8 BOM 모두 허용. 끝 개행/공백 제거."""
    return prompt_path.read_text(encoding="utf-8-sig").strip()


def main(argv=None) -> int:
    args = parse_args(argv)

    # -c 검증
    if args.command[0] not in {"auto_context", "context"}:
        print(
            f"❌ 지원하지 않는 명령: {args.command[0]} ('auto_context', 'context' 지원)",
            file=sys.stderr,
        )
        return 2
    if len(args.command) < 2:
        print("❌ 패턴이 누락되었습니다. 예: -c auto_context src/*.py", file=sys.stderr)
        return 2
    command_name = args.command[0]
    command_args = " ".join(args.command[1:])

    # -wp 검증
    workspace_path = Path(args.workspace).resolve()
    if not workspace_path.is_dir():
        print(
            f"❌ 작업 디렉토리가 존재하지 않습니다: {workspace_path}",
            file=sys.stderr,
        )
        return 1

    # -p 검증/로드
    # 절대경로 → 그대로 사용
    # 비절대경로 → 워크스페이스(-wp) 기준으로 해석
    prompt_path = Path(args.prompt)
    if not prompt_path.is_absolute():
        prompt_path = workspace_path / args.prompt
    prompt_path = prompt_path.resolve()  # 이후 chdir 에 영향받지 않도록 절대경로화
    if not prompt_path.is_file():
        print(f"❌ 프롬프트 파일을 찾을 수 없습니다: {prompt_path}", file=sys.stderr)
        return 1
    try:
        prompt = _read_prompt(prompt_path)
    except (OSError, UnicodeError) as exc:
        print(f"❌ 프롬프트 파일 읽기 실패: {exc}", file=sys.stderr)
        return 1
    if not prompt:
        print(f"❌ 프롬프트 파일이 비어있습니다: {prompt_path}", file=sys.stderr)
        return 1

    # -o 검증/생성 (context 명령에서만 의미 있으나 파싱은 항상 수행)
    output_dir: Path | None = None
    if args.output is not None:
        raw_output = Path(args.output)
        if not raw_output.is_absolute():
            raw_output = workspace_path / args.output
        output_dir = raw_output.resolve()
        if output_dir.exists() and not output_dir.is_dir():
            print(f"❌ 출력 경로가 디렉토리가 아닙니다: {output_dir}", file=sys.stderr)
            return 1
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                print(f"❌ 출력 디렉토리 생성 실패: {exc}", file=sys.stderr)
                return 1

    # 작업 디렉토리 변경 (엔트리포인트의 .env / os.getcwd() 호환)
    os.chdir(workspace_path)

    # 엔트리포인트 로드 → main_batch 호출
    try:
        module = _load_entrypoint(TYPE_TO_FILE[args.type])
    except Exception as exc:
        print(f"❌ 엔트리포인트 로드 실패: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 3

    if not hasattr(module, "main_batch"):
        print(
            f"❌ {TYPE_TO_FILE[args.type]} 에 main_batch() 가 없습니다.",
            file=sys.stderr,
        )
        return 3

    try:
        return int(module.main_batch(
            workspace=str(workspace_path),
            command=command_name,
            command_args=command_args,
            prompt=prompt,
            output_dir=str(output_dir) if output_dir is not None else None,
        ))
    except KeyboardInterrupt:
        print("\n⏭️  사용자 중단", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"❌ 처리 중 예외 발생: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
