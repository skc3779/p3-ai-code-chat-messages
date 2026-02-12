"""
CLI 입력 핸들러
- Tab 자동완성 (readline)
- 히스토리 관리
"""

import os
import readline
from typing import Optional


class CLIInputHandler:
    """CLI 입력 처리 클래스"""
    
    def __init__(self, history_file: str = ".cli_history"):
        """
        초기화
        
        Args:
            history_file: 히스토리 파일 경로
        """
        self.history_file = history_file
        self.commands = [
            '/help', '/quit', '/files', '/tree', '/read', '/context',
            '/save', '/workspace', '/stream', '/nostream', 
            '/history', '/clear', '/save_history', '/load_history', '/list_history',
            '/run', '/multiline', '/tokens', '/shell', '/shell!',
            '/template', '/template_list', '/template_reset',
            '/watch', '/unwatch', '/watch_list',
            '/llm_config',  # GenAI 전용
            '/diff', '/apply'
        ]
        
        # readline 설정
        self._setup_readline()
        
        # 히스토리 로드
        self._load_history()
    
    def _setup_readline(self):
        """readline 설정"""
        try:
            # Tab 자동완성 활성화
            readline.parse_and_bind('tab: complete')
            readline.set_completer(self._completer)
            
            # 자동완성 구분자 설정
            readline.set_completer_delims(' \t\n')
        except Exception as e:
            # readline이 없는 환경에서는 무시
            pass
    
    def _completer(self, text: str, state: int) -> Optional[str]:
        """
        Tab 자동완성 함수
        
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
    
    def _load_history(self):
        """히스토리 파일 로드"""
        try:
            if os.path.exists(self.history_file):
                readline.read_history_file(self.history_file)
        except Exception:
            # readline이 없거나 히스토리 로드 실패 시 무시
            pass
    
    def _save_history(self):
        """히스토리 파일 저장"""
        try:
            readline.write_history_file(self.history_file)
        except Exception:
            # readline이 없거나 히스토리 저장 실패 시 무시
            pass
    
    def get_input(self, prompt: str = "👤 You: ") -> str:
        """
        사용자 입력 받기
        
        Args:
            prompt: 프롬프트 메시지
            
        Returns:
            사용자 입력 문자열
        """
        try:
            user_input = input(prompt).strip()
            if user_input:
                self._save_history()
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
