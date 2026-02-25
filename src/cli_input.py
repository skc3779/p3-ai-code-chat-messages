"""
CLI 입력 핸들러
- prompt_toolkit 기반 슬래시 명령어 인라인 제안 (타이핑 중 자동 표시)
- 하단 상태 바 (작업 경로 + 모델 정보)
- prompt_toolkit 미설치 시 readline 폴백
- 히스토리 관리
"""

import os
from typing import Optional

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.history import FileHistory
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False

from src.command_registry import CommandRegistry


class SlashCommandCompleter(Completer):
    """슬래시 명령어 자동완성 + 인라인 제안"""
    
    def __init__(self, registry: CommandRegistry):
        self.registry = registry
    
    def get_completions(self, document, complete_event):
        """
        입력 텍스트 기반으로 명령어 제안 생성
        
        - '/' 로 시작하는 입력에 대해서만 동작
        - 첫 번째 단어(명령어 부분)에서만 동작
        - 명령어 이후 인자 입력 중이면 제안하지 않음
        """
        text = document.text_before_cursor
        
        # 명령어 부분만 추출 (첫 번째 공백 이전)
        if ' ' in text:
            return  # 명령어 이후 인자 입력 중이면 제안하지 않음
        
        if not text.startswith('/'):
            return
        
        # 접두사 필터링
        matched = self.registry.filter_commands(text)
        
        for cmd in matched:
            yield Completion(
                cmd.name,
                start_position=-len(text),
                display=cmd.name,
                display_meta=cmd.description,
            )


class CLIInputHandler:
    """CLI 입력 처리 클래스 (prompt_toolkit 우선, readline 폴백)"""
    
    def __init__(self, history_file: str = ".cli_history",
                 workspace: str = "", model_name: str = ""):
        """
        초기화
        
        Args:
            history_file: 히스토리 파일 경로
            workspace: 작업 디렉토리 경로 (하단 상태 바 표시용)
            model_name: AI 모델 이름 (하단 상태 바 표시용)
        """
        self.history_file = history_file
        self.workspace = workspace
        self.model_name = model_name
        self.registry = CommandRegistry()
        
        if PROMPT_TOOLKIT_AVAILABLE:
            self._init_prompt_toolkit()
        else:
            self._init_readline()
    
    def _init_prompt_toolkit(self):
        """prompt_toolkit 초기화"""
        try:
            # 히스토리 파일 설정
            history = FileHistory(self.history_file)
            
            # prompt_toolkit 세션 생성
            self.session = PromptSession(
                completer=SlashCommandCompleter(self.registry),
                complete_while_typing=True,   # 타이핑 중 자동 제안
                bottom_toolbar=self._get_toolbar,  # 하단 상태 바
                history=history,
            )
            self._use_prompt_toolkit = True
        except Exception:
            # 비대화형 환경(파이프, 리디렉션 등)에서 실패 시 readline 폴백
            self._init_readline()
    
    def _get_toolbar(self):
        """하단 상태 바 생성 (좌측: 경로, 우측: 모델)"""
        # 경로가 길면 축약
        path = self.workspace
        if len(path) > 50:
            path = path[:15] + "\\..." + path[-32:]
        
        model_info = f"/model {self.model_name}" if self.model_name else ""
        
        return HTML(
            f' <b>{path}</b>'
            f'<right><b>{model_info}</b></right>'
        )
    
    def update_workspace(self, workspace: str):
        """작업 경로 업데이트 (하단 상태 바 갱신용)"""
        self.workspace = workspace
    
    def update_model(self, model_name: str):
        """모델 이름 업데이트 (하단 상태 바 갱신용)"""
        self.model_name = model_name
    
    def _init_readline(self):
        """readline 폴백 초기화"""
        self._use_prompt_toolkit = False
        self.commands = self.registry.get_command_names()
        
        try:
            import readline
            self._readline = readline
            
            # Tab 자동완성 활성화
            readline.parse_and_bind('tab: complete')
            readline.set_completer(self._completer)
            
            # 자동완성 구분자 설정
            readline.set_completer_delims(' \t\n')
            
            # 히스토리 로드
            if os.path.exists(self.history_file):
                readline.read_history_file(self.history_file)
        except (ImportError, Exception):
            # readline이 없는 환경에서는 무시
            self._readline = None
    
    def _completer(self, text: str, state: int) -> Optional[str]:
        """
        Tab 자동완성 함수 (readline 폴백용)
        
        Args:
            text: 현재 입력된 텍스트
            state: 자동완성 상태 인덱스
            
        Returns:
            자동완성 옵션 또는 None
        """
        # 명령어로 시작하는 경우
        if text.startswith('/'):
            options = [cmd for cmd in self.commands if cmd.startswith(text)]
        else:
            options = []
        
        if state < len(options):
            return options[state]
        return None
    
    def get_input(self, prompt: str = "👤 You: ") -> str:
        """
        사용자 입력 받기
        
        Args:
            prompt: 프롬프트 메시지
            
        Returns:
            사용자 입력 문자열
        """
        try:
            if self._use_prompt_toolkit:
                user_input = self.session.prompt(prompt).strip()
            else:
                user_input = input(prompt).strip()
                if user_input and self._readline:
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
    
    def get_multiline_legacy(self) -> str:
        """
        레거시 멀티라인 입력 (/multiline 명령어용)
        
        Returns:
            여러 줄 입력
        """
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
