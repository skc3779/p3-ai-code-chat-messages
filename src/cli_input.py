"""
CLI Input Handler - 자동 완성 및 히스토리 기능을 제공하는 사용자 입력 모듈
"""

from typing import List
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, PathCompleter, NestedCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

class CLIInputHandler:
    """CLI 입력 처리기"""
    
    def __init__(self, history_file: str = ".cli_history"):
        self.history_file = history_file
        
        # 기본 명령어 목록
        self.commands = [
            '/help', '/quit', '/files', '/tree', '/read', '/context',
            '/save', '/workspace', '/stream', '/nostream', 
            '/history', '/clear', '/save_history', '/load_history', '/list_history',
            '/run', '/multiline', '/tokens', '/shell', '/shell!',
            '/template', '/template_list', '/template_reset',
            '/watch', '/unwatch', '/watch_list',
            '/llm_config'  # GenAI 전용
        ]
        
        # 자동 완성 설정
        self.completer = NestedCompleter.from_nested_dict({
            '/files': PathCompleter(),
            '/read': PathCompleter(),
            '/context': PathCompleter(),
            '/workspace': PathCompleter(only_directories=True),
            '/save_history': None,
            '/load_history': None,
            '/run': WordCompleter(['python', 'javascript', 'bash', 'shell']),
            '/shell': None,
            '/shell!': None,
            '/watch': None,
            '/unwatch': None,
            '/template': None, # 추후 동적 로드 가능하도록 개선 가능
            '/llm_config': WordCompleter(['python', 'javascript', 'java', 'cpp', 'go']),
            **{cmd: None for cmd in self.commands if cmd not in [
                '/files', '/read', '/context', '/workspace', 
                '/save_history', '/load_history', '/run', 
                '/shell', '/shell!', '/watch', '/unwatch', '/template', '/llm_config'
            ]}
        })
        
        # 스타일 설정
        self.style = Style.from_dict({
            'prompt': '#ansigreen bold',
        })
        
        # 세션 초기화
        self.session = PromptSession(
            history=FileHistory(self.history_file),
            completer=self.completer,
            style=self.style
        )

    def get_input(self, prompt_text: str = "👤 You: ") -> str:
        """사용자 입력 받기"""
        try:
            return self.session.prompt(prompt_text).strip()
        except EOFError:
            return "/quit"
        except KeyboardInterrupt:
            return ""
