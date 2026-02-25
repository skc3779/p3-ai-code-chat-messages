"""
슬래시 명령어 레지스트리
- 명령어 이름, 설명, 사용법을 중앙에서 관리
- 접두사 기반 필터링 지원
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CommandInfo:
    """슬래시 명령어 정보"""
    name: str           # 명령어 이름 (예: '/save')
    description: str    # 명령어 설명 (예: 'AI 응답에서 파일 추출 및 저장')
    usage: str = ""     # 사용법 (예: '/save')


class CommandRegistry:
    """슬래시 명령어 레지스트리"""
    
    def __init__(self):
        self._commands: List[CommandInfo] = []
        self._register_default_commands()
    
    def _register_default_commands(self):
        """기본 명령어 등록"""
        self._commands = [
            CommandInfo('/files', '프로젝트 파일 목록', '/files [ext]'),
            CommandInfo('/tree', '프로젝트 구조 보기', '/tree'),
            CommandInfo('/read', '파일 읽기', '/read <pattern>'),
            CommandInfo('/context', '컨텍스트 포함하여 질문', '/context <pattern> [질문]'),
            CommandInfo('/save', 'AI 응답에서 파일 추출 및 저장', '/save'),
            CommandInfo('/workspace', '작업 디렉토리 변경', '/workspace [path]'),
            CommandInfo('/stream', '스트리밍 모드 활성화', '/stream'),
            CommandInfo('/nostream', '논스트리밍 모드 활성화', '/nostream'),
            CommandInfo('/history', '대화 히스토리 보기', '/history'),
            CommandInfo('/clear', '대화 히스토리 초기화', '/clear'),
            CommandInfo('/save_history', '대화 히스토리 파일로 저장', '/save_history [name]'),
            CommandInfo('/load_history', '저장된 히스토리 로드', '/load_history <name>'),
            CommandInfo('/list_history', '저장된 히스토리 목록', '/list_history'),
            CommandInfo('/run', '마지막 응답의 코드 실행', '/run [lang]'),
            CommandInfo('/diff', '코드 변경사항 Diff 표시', '/diff'),
            CommandInfo('/apply', 'Diff 내용을 파일에 적용', '/apply'),
            CommandInfo('/multiline', '멀티라인 입력 모드', '/multiline'),
            CommandInfo('/tokens', '토큰 사용량 확인', '/tokens'),
            CommandInfo('/shell', '쉘 명령어 실행 (안전 모드)', '/shell <cmd>'),
            CommandInfo('/shell!', '쉘 명령어 실행 (위험 허용)', '/shell! <cmd>'),
            CommandInfo('/template', '시스템 프롬프트 템플릿 변경', '/template <name>'),
            CommandInfo('/template_list', '사용 가능한 템플릿 목록', '/template_list'),
            CommandInfo('/template_reset', '기본 시스템 프롬프트로 복귀', '/template_reset'),
            CommandInfo('/watch', '파일 변경 감시 시작', '/watch <pattern>'),
            CommandInfo('/unwatch', '파일 변경 감시 중지', '/unwatch <pattern>'),
            CommandInfo('/watch_list', '감시 중인 패턴 목록', '/watch_list'),
            CommandInfo('/llm_config', '언어별 LLM 파라미터 설정', '/llm_config <lang>'),
            CommandInfo('/help', '도움말 보기', '/help'),
            CommandInfo('/quit', '종료', '/quit'),
        ]
    
    def get_commands(self) -> List[CommandInfo]:
        """전체 명령어 목록 반환"""
        return self._commands
    
    def get_command_names(self) -> List[str]:
        """명령어 이름만 반환"""
        return [cmd.name for cmd in self._commands]
    
    def filter_commands(self, prefix: str) -> List[CommandInfo]:
        """
        접두사로 명령어 필터링
        
        Args:
            prefix: 검색 접두사 (예: '/s', '/save')
            
        Returns:
            필터링된 명령어 목록
        """
        return [cmd for cmd in self._commands if cmd.name.startswith(prefix)]
    
    def get_command(self, name: str) -> Optional[CommandInfo]:
        """
        이름으로 명령어 검색
        
        Args:
            name: 명령어 이름 (예: '/save')
            
        Returns:
            CommandInfo 또는 None
        """
        for cmd in self._commands:
            if cmd.name == name:
                return cmd
        return None
