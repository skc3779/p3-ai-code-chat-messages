"""
CLI 입력 핸들러 - Gemini CLI 스타일 전체 화면 TUI

입력 아래에 전체 터미널 너비의 플랫 인라인 목록으로 명령어 제안:
- 명령어 이름은 / 없이 볼드, 설명은 dim
- ▼ 스크롤 인디케이터
- (현재위치/전체수) 페이지네이션 (좌측 하단)
- 하단 상태 바 3영역 (경로 / streaming / model)
- 프롬프트: >
- ↑↓ 네비게이션, Tab/Enter 확정, ESC 닫기
- prompt_toolkit 미설치 시 readline 폴백
"""

import os
import shutil
from typing import Optional, List

try:
    from prompt_toolkit import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window, ConditionalContainer
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.processors import BeforeInput
    from prompt_toolkit.layout.margins import PromptMargin
    from prompt_toolkit.styles import Style
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False

from src.command_registry import CommandRegistry


# ═══════════════════════════════════════════════════════════════
# Gemini CLI 스타일 커스텀 Application
# ═══════════════════════════════════════════════════════════════

if PROMPT_TOOLKIT_AVAILABLE:

    # 스타일 정의 (Gemini CLI 테마)
    GEMINI_STYLE = Style.from_dict({
        'prompt':           'bold',
        'cmd-name':         'bold #e0e0e0',
        'cmd-name-selected':'bold bg:#3a3a3a #ffffff',
        'cmd-desc':         '#707070',
        'cmd-desc-selected':'bg:#3a3a3a #909090',
        'scroll-indicator':  '#505050',
        'pagination':        '#606060',
        'toolbar':           'bg:#1a1a2e #a0a0a0',
        'toolbar-path':      'bold',
        'toolbar-center':    'italic',
        'toolbar-model':     'bold',
    })


class CLIInputHandler:
    """Gemini CLI 스타일 입력 처리 클래스

    prompt_toolkit의 커스텀 Application+Layout을 사용하여
    전체 화면 너비의 플랫 인라인 명령어 제안 목록을 구현합니다.
    """

    def __init__(self, history_file: str = ".cli_history",
                 workspace: str = "", model_name: str = "",
                 streaming_mode: bool = True):
        self.history_file = history_file
        self.workspace = workspace
        self.model_name = model_name
        self.streaming_mode = streaming_mode
        self.registry = CommandRegistry()

        if PROMPT_TOOLKIT_AVAILABLE:
            self._init_prompt_toolkit()
        else:
            self._init_readline()

    # ───────────────────────────────────────────────────────
    # prompt_toolkit 커스텀 Application
    # ───────────────────────────────────────────────────────

    def _init_prompt_toolkit(self):
        """prompt_toolkit 커스텀 Application 초기화"""
        try:
            # 상태 변수
            self._filtered: List = []
            self._selected_idx: int = 0
            self._scroll_offset: int = 0
            self._show_suggestions: bool = False
            self._result: Optional[str] = None

            # 히스토리
            self._history = FileHistory(self.history_file)

            self._use_prompt_toolkit = True
        except Exception:
            self._init_readline()

    def _get_max_visible(self) -> int:
        """터미널 높이에 따른 최대 표시 항목 수"""
        term_height = shutil.get_terminal_size((80, 24)).lines
        # 입력 1줄 + 상태바 1줄 + 여유 2줄 = 빼고 나머지 사용
        return max(5, term_height - 4)

    def _build_app(self, prompt_text: str) -> 'Application':
        """매 get_input 호출마다 새 Application 생성"""
        handler = self  # 클로저 참조

        # ── Buffer ──
        input_buffer = Buffer(
            history=self._history,
            on_text_changed=lambda buf: handler._on_text_changed(buf),
        )
        self._buffer = input_buffer

        # ── 키 바인딩 ──
        kb = KeyBindings()

        @kb.add('enter')
        def _enter(event):
            if handler._show_suggestions and handler._filtered:
                # 제안이 열려있고 항목이 있을 때 → 선택된 명령어로 교체
                cmd = handler._filtered[handler._selected_idx]
                event.app.current_buffer.text = cmd.name + ' '
                event.app.current_buffer.cursor_position = len(cmd.name) + 1
                handler._show_suggestions = False
                handler._filtered = []
            else:
                # 일반 Enter → 입력 확정
                handler._result = event.app.current_buffer.text
                event.app.exit()

        @kb.add('tab')
        def _tab(event):
            if handler._show_suggestions and handler._filtered:
                cmd = handler._filtered[handler._selected_idx]
                event.app.current_buffer.text = cmd.name + ' '
                event.app.current_buffer.cursor_position = len(cmd.name) + 1
                handler._show_suggestions = False
                handler._filtered = []

        @kb.add('escape')
        def _escape(event):
            if handler._show_suggestions:
                handler._show_suggestions = False
                handler._filtered = []
            else:
                # ESC로 빈 입력 반환
                handler._result = ""
                event.app.exit()

        @kb.add('up')
        def _up(event):
            if handler._show_suggestions and handler._filtered:
                handler._selected_idx = max(0, handler._selected_idx - 1)
                # 스크롤 조정
                if handler._selected_idx < handler._scroll_offset:
                    handler._scroll_offset = handler._selected_idx

        @kb.add('down')
        def _down(event):
            if handler._show_suggestions and handler._filtered:
                total = len(handler._filtered)
                handler._selected_idx = min(total - 1, handler._selected_idx + 1)
                max_vis = handler._get_max_visible()
                if handler._selected_idx >= handler._scroll_offset + max_vis:
                    handler._scroll_offset = handler._selected_idx - max_vis + 1

        @kb.add('c-c')
        def _ctrl_c(event):
            handler._result = ""
            event.app.exit()

        @kb.add('c-d')
        def _ctrl_d(event):
            handler._result = "/quit"
            event.app.exit()

        # ── 레이아웃 ──
        # 1) 입력 영역
        input_window = Window(
            BufferControl(
                buffer=input_buffer,
                input_processors=[BeforeInput(prompt_text)],
            ),
            height=1,
        )

        # 2) 명령어 제안 영역 (조건부)
        suggestion_window = ConditionalContainer(
            Window(
                FormattedTextControl(lambda: handler._render_suggestions()),
                dont_extend_height=True,
            ),
            filter=Condition(lambda: handler._show_suggestions and len(handler._filtered) > 0),
        )

        # 3) 하단 상태 바
        toolbar_window = Window(
            FormattedTextControl(lambda: handler._render_toolbar()),
            height=1,
            style='class:toolbar',
        )

        layout = Layout(
            HSplit([
                input_window,
                suggestion_window,
                toolbar_window,
            ])
        )

        return Application(
            layout=layout,
            key_bindings=kb,
            style=GEMINI_STYLE,
            full_screen=False,
            erase_when_done=True,
        )

    def _on_text_changed(self, buf):
        """입력 텍스트 변경 시 명령어 필터링"""
        text = buf.text.strip()

        if text.startswith('/') and ' ' not in text:
            self._filtered = self.registry.filter_commands(text)
            self._show_suggestions = True
            self._selected_idx = 0
            self._scroll_offset = 0
        else:
            self._show_suggestions = False
            self._filtered = []

    def _render_suggestions(self) -> FormattedText:
        """명령어 제안 목록 렌더링 (전체 화면 너비, 플랫)"""
        result = []
        max_vis = self._get_max_visible()
        total = len(self._filtered)

        visible = self._filtered[self._scroll_offset:self._scroll_offset + max_vis]

        # 터미널 너비 가져오기
        term_width = shutil.get_terminal_size((80, 24)).columns

        # 명령어 이름 최대 너비 계산
        name_width = 18
        if visible:
            max_name_len = max(len(cmd.name.lstrip('/')) for cmd in visible)
            name_width = max(max_name_len + 2, 18)

        for i, cmd in enumerate(visible):
            actual_idx = self._scroll_offset + i
            display_name = cmd.name.lstrip('/')

            # 스타일 결정
            if actual_idx == self._selected_idx:
                name_style = 'class:cmd-name-selected'
                desc_style = 'class:cmd-desc-selected'
            else:
                name_style = 'class:cmd-name'
                desc_style = 'class:cmd-desc'

            # 전체 너비로 배치
            name_part = f"{display_name:<{name_width}}"
            desc_part = cmd.description
            # 줄의 나머지를 패딩
            line_content = name_part + desc_part
            padding = max(0, term_width - len(line_content) - 1)

            result.append((name_style, name_part))
            result.append((desc_style, desc_part + ' ' * padding))
            result.append(('', '\n'))

        # 스크롤 인디케이터
        if self._scroll_offset + max_vis < total:
            result.append(('class:scroll-indicator', '▼\n'))
        elif self._scroll_offset > 0:
            result.append(('class:scroll-indicator', '▲\n'))

        # 페이지네이션 (좌측 하단)
        current_pos = self._selected_idx + 1
        result.append(('class:pagination', f'({current_pos}/{total})\n'))

        return FormattedText(result)

    def _render_toolbar(self) -> FormattedText:
        """하단 상태 바 렌더링 - Gemini CLI 스타일 3영역"""
        # 경로 축약
        path = self.workspace
        if len(path) > 45:
            path = path[:12] + "\\..." + path[-28:]

        mode_info = "streaming" if self.streaming_mode else "nostream"
        model_info = f"/model {self.model_name}" if self.model_name else ""

        # 터미널 너비에 맞춰 배치
        term_width = shutil.get_terminal_size((80, 24)).columns
        left = path
        center = mode_info
        right = model_info

        # 여백 계산
        used = len(left) + len(center) + len(right) + 4
        gap1 = max(2, (term_width - used) // 2)
        gap2 = max(2, term_width - used - gap1)

        return FormattedText([
            ('class:toolbar-path', f' {left}'),
            ('class:toolbar', ' ' * gap1),
            ('class:toolbar-center', center),
            ('class:toolbar', ' ' * gap2),
            ('class:toolbar-model', right),
        ])

    # ───────────────────────────────────────────────────────
    # readline 폴백
    # ───────────────────────────────────────────────────────

    def _init_readline(self):
        """readline 폴백 초기화"""
        self._use_prompt_toolkit = False
        self.commands = self.registry.get_command_names()

        try:
            import readline
            self._readline = readline
            readline.parse_and_bind('tab: complete')
            readline.set_completer(self._completer)
            readline.set_completer_delims(' \t\n')

            if os.path.exists(self.history_file):
                readline.read_history_file(self.history_file)
        except (ImportError, Exception):
            self._readline = None

    def _completer(self, text: str, state: int) -> Optional[str]:
        """Tab 자동완성 (readline 폴백용)"""
        if text.startswith('/'):
            options = [cmd for cmd in self.commands if cmd.startswith(text)]
        else:
            options = []
        if state < len(options):
            return options[state]
        return None

    # ───────────────────────────────────────────────────────
    # 공통 인터페이스
    # ───────────────────────────────────────────────────────

    def get_input(self, prompt: str = "> ") -> str:
        """
        사용자 입력 받기 - Gemini CLI 스타일

        Args:
            prompt: 프롬프트 메시지

        Returns:
            사용자 입력 문자열
        """
        try:
            if self._use_prompt_toolkit:
                self.reset_runtime_state()

                app = self._build_app(prompt)
                app.run()

                final_text = (self._result or "").strip()
                # erase_when_done=True로 인해 프롬프트 입력줄도 지워지므로 명시적으로 터미널에 다시 복원
                print(f"{prompt}{final_text}")

                return final_text
            else:
                user_input = input(prompt).strip()
                if user_input and hasattr(self, '_readline') and self._readline:
                    try:
                        self._readline.write_history_file(self.history_file)
                    except Exception:
                        pass
                return user_input
        except EOFError:
            return "/quit"
        except KeyboardInterrupt:
            print()
            return ""

    def reset_runtime_state(self) -> None:
        """다음 prompt_toolkit 입력을 위해 일회성 TUI 상태를 초기화한다.

        /agents 처럼 외부 루프가 stdin 을 장시간 점유한 뒤 복귀할 때,
        이전 세션의 suggestion/buffer 잔재가 다음 입력에 영향을 주지 않도록
        명시적으로 리셋한다. B-071-03 수정.
        """
        if not getattr(self, "_use_prompt_toolkit", False):
            return
        self._result = None
        self._filtered = []
        self._show_suggestions = False
        self._selected_idx = 0
        self._scroll_offset = 0
        buffer = getattr(self, "_buffer", None)
        if buffer is not None:
            try:
                # 빈 Document 로 교체해 텍스트·커서 위치·히스토리 포인터를 초기화
                buffer.reset(Document(""))
            except Exception:
                pass

    def get_multiline(self) -> str:
        """
        멀티라인 텍스트 편집 입력 (prompt_toolkit 사용)

        - ↑↓←→ 키로 전체 텍스트 탐색 및 수정
        - Enter: 줄바꿈 (마지막 줄이 /end이면 입력 확정)
        - Esc / Ctrl+C: 입력 취소
        - prompt_toolkit 미설치 시 get_multiline_legacy() 폴백
        """
        if not PROMPT_TOOLKIT_AVAILABLE or not getattr(self, '_use_prompt_toolkit', False):
            return self.get_multiline_legacy()

        print("📝 멀티라인 모드 (/end로 종료, Esc 취소)")

        try:
            multiline_result = [None]  # 클로저용 리스트

            # ── 멀티라인 Buffer ──
            ml_buffer = Buffer(multiline=True)

            # ── 키 바인딩 ──
            kb = KeyBindings()

            @kb.add('enter')
            def _enter(event):
                buf = event.app.current_buffer
                text = buf.text
                lines = text.split('\n')

                # 현재 줄(마지막 줄)이 /end이면 종료
                # 커서가 마지막 줄에 있고 그 줄이 /end인지 확인
                doc = buf.document
                current_line = doc.current_line_before_cursor + doc.current_line_after_cursor
                if current_line.strip() == '/end':
                    # /end 줄을 제거한 결과 생성
                    result_lines = []
                    for line in lines:
                        if line.strip() != '/end':
                            result_lines.append(line)
                    multiline_result[0] = '\n'.join(result_lines)
                    event.app.exit()
                else:
                    # 일반 줄바꿈
                    buf.insert_text('\n')

            @kb.add('escape')
            def _escape(event):
                multiline_result[0] = ""
                event.app.exit()

            @kb.add('c-c')
            def _ctrl_c(event):
                multiline_result[0] = ""
                event.app.exit()

            @kb.add('c-d')
            def _ctrl_d(event):
                # Ctrl+D: 현재 내용으로 확정
                multiline_result[0] = event.app.current_buffer.text
                event.app.exit()

            # ── 레이아웃 ──
            # PromptMargin: 모든 줄에 '... ' 프롬프트 표시
            multiline_margin = PromptMargin(
                get_prompt=lambda: [('', '... ')],
                get_continuation=lambda width, line_number, is_soft_wrap: [('', '... ')],
            )

            input_window = Window(
                BufferControl(
                    buffer=ml_buffer,
                ),
                left_margins=[multiline_margin],
                wrap_lines=True,
            )

            # 안내 바
            help_bar = Window(
                FormattedTextControl(
                    FormattedText([
                        ('class:toolbar', ' /end: 전송 | Esc: 취소 '),
                    ])
                ),
                height=1,
                style='class:toolbar',
            )

            layout = Layout(
                HSplit([
                    input_window,
                    help_bar,
                ])
            )

            app = Application(
                layout=layout,
                key_bindings=kb,
                style=GEMINI_STYLE if PROMPT_TOOLKIT_AVAILABLE else None,
                full_screen=False,
                erase_when_done=True,
            )

            # 실행
            app.run()

            result = multiline_result[0]
            if result is None:
                result = ml_buffer.text

            # erase_when_done으로 지워진 내용 복원 표시
            if result and result.strip():
                preview_lines = result.split('\n')
                for line in preview_lines:
                    print(f"... {line}")

            return result.strip() if result else ""

        except Exception as e:
            print(f"⚠️  멀티라인 입력 오류, 레거시 모드로 전환: {e}")
            return self.get_multiline_legacy()

    def get_multiline_legacy(self) -> str:
        """레거시 멀티라인 입력 (/multiline 명령어용)"""
        print("📝 멀티라인 모드 (종료: /end)")
        lines = []
        while True:
            try:
                line = input("... ")
                if line.strip() == '/end':
                    break
                lines.append(line)
            except EOFError:
                break
            except KeyboardInterrupt:
                print()
                return ""
        return "\n".join(lines)

    def update_workspace(self, workspace: str):
        """작업 경로 업데이트 (하단 상태 바 갱신용)"""
        self.workspace = workspace

    def update_model(self, model_name: str):
        """모델 이름 업데이트 (하단 상태 바 갱신용)"""
        self.model_name = model_name

    def update_streaming_mode(self, streaming: bool):
        """스트리밍 모드 업데이트 (하단 상태 바 갱신용)"""
        self.streaming_mode = streaming


# ═══════════════════════════════════════════════════════════════
# FSD v1.0.123 § 5.1 — 공통 옵션 파싱 헬퍼
# ═══════════════════════════════════════════════════════════════

from dataclasses import dataclass
from typing import Dict, Set, Tuple


def parse_command_options(
    args: str,
    aliases: Dict[str, str],
) -> Tuple[Set[str], str]:
    """
    명령어 인자에서 선두의 옵션 토큰을 분리해 (옵션집합, 나머지) 반환.

    Args:
        args: 명령어 뒤의 전체 문자열 (예: "-qc src/*.py 질문")
        aliases: { "-qc": "quality_check", "--quality-check": "quality_check",
                   "-nt": "no_tree",       "--no-tree":       "no_tree" }

    Returns:
        (set of canonical names, remaining args str)

    Notes:
        - 위치 인자 시작 = 첫 번째 토큰이 옵션이 아닌 시점
        - "[" 로 시작하는 토큰은 패턴 리스트로 간주, 옵션 파싱 종료
        - 알 수 없는 -옵션 은 ValueError
        - "--" 토큰은 옵션 종료 명시 (FR-C-04)

    Raises:
        ValueError: 알 수 없는 옵션 토큰이 발견된 경우
    """
    tokens = args.split()
    options: Set[str] = set()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # "--" 는 옵션 종료 명시자 (FR-C-04)
        if tok == "--":
            i += 1
            break
        if not tok.startswith("-") or tok.startswith("["):
            break
        if tok not in aliases:
            raise ValueError(f"알 수 없는 옵션: {tok}")
        options.add(aliases[tok])
        i += 1

    # 원문 길이 계산은 선행/중복 공백에서 잘못된 위치를 자를 수 있다.
    # 이미 토큰화한 결과로 위치 인자를 안정적으로 재구성한다.
    if i == 0:
        return options, args
    return options, " ".join(tokens[i:])


@dataclass(frozen=True)
class ContextCommandArgs:
    file_patterns: list[str]
    question: str
    large: bool
    no_tree: bool


def parse_context_command_args(args: str) -> ContextCommandArgs:
    """Parse the shared `/context` option, pattern, and question contract."""
    aliases = {
        "--large": "large",
        "-l": "large",
        "-nt": "no_tree",
        "--no-tree": "no_tree",
    }
    options, remaining = parse_command_options(args, aliases)
    if not remaining:
        raise ValueError("파일 패턴을 입력하세요.")
    if remaining.startswith("["):
        try:
            end = remaining.index("]")
        except ValueError as exc:
            raise ValueError("닫는 대괄호 ']'가 없습니다.") from exc
        patterns = [item.strip() for item in remaining[1:end].split(",") if item.strip()]
        question = remaining[end + 1:].strip()
    else:
        parts = remaining.split(maxsplit=1)
        patterns = [parts[0]]
        question = parts[1] if len(parts) == 2 else ""
    if not patterns:
        raise ValueError("파일 패턴을 입력하세요.")
    return ContextCommandArgs(patterns, question, "large" in options, "no_tree" in options)
