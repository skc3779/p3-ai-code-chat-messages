"""Provider-independent execution for the non-interactive ``/context`` command."""

from __future__ import annotations

import datetime
import sys
from dataclasses import dataclass
from pathlib import Path

from .cli_input import parse_context_command_args
from .file_pattern_matcher import FilePatternMatcher
from .large_context_processor import LargeContextProcessor


@dataclass(frozen=True)
class ContextBatchRequest:
    """Validated input for one context batch execution."""

    file_patterns: list[str]
    prompt: str
    large: bool
    no_tree: bool


class ContextBatchInputError(ValueError):
    """Expected batch input failure with a stable process exit code."""

    def __init__(self, message: str, *, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def prepare_context_batch(command_args: str, prompt: str) -> ContextBatchRequest:
    """Parse and validate context input before provider auth/initialization."""
    try:
        parsed = parse_context_command_args(command_args)
    except ValueError as exc:
        raise ContextBatchInputError(str(exc)) from exc

    if parsed.question:
        raise ContextBatchInputError(
            "context 배치 모드의 질문은 -p 파일로만 지정하세요.",
            exit_code=2,
        )

    question = (prompt or "").strip()
    if not question:
        raise ContextBatchInputError("프롬프트가 비어있습니다.")

    return ContextBatchRequest(
        file_patterns=parsed.file_patterns,
        prompt=question,
        large=parsed.large,
        no_tree=parsed.no_tree,
    )


def _save_response(
    response: str,
    output_dir: Path,
    provider: str,
    patterns: list[str],
) -> Path:
    """응답 텍스트를 타임스탬프 파일로 저장하고 경로를 반환한다."""
    now = datetime.datetime.now()
    filename = f"context_{now.strftime('%Y%m%d_%H%M%S')}.md"
    output_path = output_dir / filename
    header = (
        f"# AI 응답\n\n"
        f"- 날짜: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- Provider: {provider}\n"
        f"- 파일 패턴: {', '.join(patterns)}\n\n"
        f"---\n\n"
    )
    output_path.write_text(header + response, encoding="utf-8")
    return output_path


def run_context_batch(
    *,
    assistant,
    provider: str,
    request: ContextBatchRequest,
    streaming: bool,
    output_dir: Path | None = None,
) -> int:
    """Execute a prepared request once, print its owned output, and return."""
    try:
        matcher = FilePatternMatcher(assistant.file_manager.workspace_dir)
        matched_files = matcher.filter_files(
            assistant.file_manager.list_files(), request.file_patterns
        )
        if not matched_files:
            print(
                f"❌ 패턴 {request.file_patterns}에 해당하는 파일이 없습니다.",
                file=sys.stderr,
            )
            return 1

        if request.large:
            response = LargeContextProcessor(
                assistant,
                assistant.file_manager,
                provider=provider,
            ).process(
                request.file_patterns,
                request.prompt,
                include_tree=not request.no_tree,
            )
            # Large-context internal calls are non-streaming, so this layer owns
            # the final synthesized response output.
            if response:
                print(f"🤖 AI: {response}")
        else:
            response = assistant.chat(
                request.prompt,
                streaming=streaming,
                include_context=True,
                file_patterns=request.file_patterns,
                include_tree=not request.no_tree,
                raise_on_error=True,
            )
            # Streaming assistants already print chunks. Non-streaming calls do
            # not, so print their result exactly once here.
            if not streaming and response:
                print(f"🤖 AI: {response}")

        if output_dir is not None:
            # -o 지정: 응답 전체를 단일 타임스탬프 파일로 저장
            if response:
                try:
                    saved_path = _save_response(response, output_dir, provider, request.file_patterns)
                    print(f"💾 응답 저장: {saved_path}")
                except OSError as exc:
                    print(f"❌ 응답 저장 실패: {exc}", file=sys.stderr)
                    return 1
        else:
            # -o 미지정: @@@filename:... 블록을 /save 와 동일하게 자동 추출/저장
            # 배치 모드는 input() 불가이므로 auto_overwrite=True 로 기존 파일 덮어씀
            if response:
                saved_files = assistant.response_parser.parse_and_save(
                    response, auto_overwrite=True
                )
                if saved_files:
                    print(f"✅ 총 {len(saved_files)}개 파일이 저장되었습니다.")
    except KeyboardInterrupt:
        print("\n⏭️  사용자 중단", file=sys.stderr)
        return 130
    except Exception:
        print(f"❌ context 배치 처리 실패 ({provider})", file=sys.stderr)
        return 3
    return 0
