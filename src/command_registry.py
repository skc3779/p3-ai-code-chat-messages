"""
슬래시 명령어 레지스트리
- 명령어 이름, 설명, 사용법, 예제를 중앙에서 관리
- 접두사 기반 필터링 지원
- print_menu()로 어느 플랫폼에서든 동일한 도움말 출력
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CommandInfo:
    """슬래시 명령어 정보"""
    name: str           # 명령어 이름 (예: '/save')
    description: str    # 명령어 설명 (예: 'AI 응답에서 파일 추출 및 저장')
    usage: str = ""     # 사용법 (예: '/save [name]')
    example: str = ""   # 사용 예제 (예: 'my_session')


class CommandRegistry:
    """슬래시 명령어 레지스트리"""

    def __init__(self):
        self._commands: List[CommandInfo] = []
        self._register_default_commands()

    def _register_default_commands(self):
        """기본 명령어 등록"""
        self._commands = [
            # ── 파일 탐색 ─────────────────────────────────────────────────────
            CommandInfo('/files',         '프로젝트 파일 목록 조회',
                        '/files [ext]',                      '.py .js'),
            CommandInfo('/tree',          '디렉토리 트리 출력',
                        '/tree',                             ''),
            # ── 컨텍스트 읽기 ───────────────────────────────────────────────
            CommandInfo('/read',          '파일 읽기 → 대화 컨텍스트에 추가',
                        '/read <pattern | [p1, p2, ...]>',   '[src/*.py, docs/*.md]'),
            CommandInfo('/context',       '파일 컨텍스트와 함께 AI에게 질문',
                        '/context <pattern> [질문]',         'src/*.py 이 코드 리뷰해줘'),
            CommandInfo('/auto_context',  '패턴별 파일을 순서대로 자동 처리',
                        '/auto_context <pattern> [질문]',    'original/*.md 한글로 번역해줘'),
            CommandInfo('/agents',        "자율 에이전트 루프 실행 (목표 멀티라인, 루프 중 's' 키 또는 Ctrl+C 로 중단)",
                        '/agents [-ba|--bypassApprovals] [pattern | [p1,p2,...] | stop]', '[src/*.py, docs/*.md]'),
            CommandInfo('/agents resume', '마지막(또는 지정) 에이전트 세션 복원 및 재개',
                        '/agents resume [filename]',              'agent_20260418_123045_tetris.json'),
            CommandInfo('/agents list',   '저장된 에이전트 세션 목록 표시',
                        '/agents list',                           ''),
            # ── 응답 처리 ────────────────────────────────────────────────────
            CommandInfo('/save',          'AI 응답의 코드 블록 추출·파일로 저장',
                        '/save',                             ''),
            CommandInfo('/run',           '마지막 AI 응답의 코드 블록 실행',
                        '/run [lang]',                       'run python'),
            CommandInfo('/diff',          '마지막 AI 응답의 코드 변경 차이(Diff) 표시',
                        '/diff',                             ''),
            CommandInfo('/apply',         'Diff 내용을 실제 파일에 적용',
                        '/apply',                            ''),
            # ── 대화 히스토리 ───────────────────────────────────────────────
            CommandInfo('/history',       '대화 히스토리 보기 / 삭제',
                        '/history [--remove|-r <N>] [--delete|-d <index>]', '-r 5'),
            CommandInfo('/clear',         '대화 히스토리 전체 초기화',
                        '/clear',                            ''),
            CommandInfo('/save_history',  '대화 히스토리를 파일로 저장',
                        '/save_history [name]',              'my_session'),
            CommandInfo('/load_history',  '저장된 히스토리 파일 불러오기',
                        '/load_history <name>',              'history_20260306.json'),
            CommandInfo('/list_history',  '저장된 히스토리 파일 목록 보기',
                        '/list_history',                     ''),
            # ── 입력 모드 ────────────────────────────────────────────────────
            CommandInfo('/multiline',     '여러 줄 입력 모드 (종료: /end)',
                        '/multiline',                        ''),
            CommandInfo('/stream',        '스트리밍 출력 켜기',
                        '/stream',                           ''),
            CommandInfo('/nostream',      '스트리밍 출력 끄기',
                        '/nostream',                         ''),
            # ── 시스템 명령 ──────────────────────────────────────────────────
            CommandInfo('/shell',         '시스템 명령어 실행 (안전 모드) · --help로 도움말',
                        '/shell <cmd|--help|-h>',            'shell git status'),
            CommandInfo('/shell!',        '시스템 명령어 실행 (위험 명령 허용)',
                        '/shell! <cmd>',                     'shell! rm -rf tmp/'),
            CommandInfo('/workspace',     '작업 디렉토리 변경',
                        '/workspace [path]',                 '../other-project'),
            CommandInfo('/watch',         '파일 변경 자동 감시 시작',
                        '/watch <pattern>',                  'watch src/*.py'),
            CommandInfo('/unwatch',       '파일 변경 감시 중지',
                        '/unwatch <pattern>',                'unwatch src/*.py'),
            CommandInfo('/watch_list',    '현재 감시 중인 패턴 목록 보기',
                        '/watch_list',                       ''),
            # ── 설정 ─────────────────────────────────────────────────────────
            CommandInfo('/tokens',        '현재 대화의 토큰 사용량 확인',
                        '/tokens',                           ''),
            CommandInfo('/llm_config',    '언어별 LLM 파라미터 설정',
                        '/llm_config <lang>',                'llm_config Java'),
            CommandInfo('/template',      '시스템 프롬프트 템플릿 변경',
                        '/template <name>',                  'template code-review'),
            CommandInfo('/template_list', '사용 가능한 템플릿 목록 보기',
                        '/template_list',                    ''),
            CommandInfo('/template_reset','시스템 프롬프트를 기본값으로 초기화',
                        '/template_reset',                   ''),
            # ── 기타 ─────────────────────────────────────────────────────────
            CommandInfo('/help',          '도움말 출력',
                        '/help',                             ''),
            CommandInfo('/quit',          '프로그램 종료',
                        '/quit',                             ''),
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


def print_menu(title: str = "AI Code Assistant") -> None:
    """
    CommandRegistry 기반으로 도움말 메뉴를 출력합니다.

    Args:
        title: 헤더에 표시할 어시스턴트 이름
    """
    registry = CommandRegistry()
    print("\n" + "=" * 100)
    print(f"🤖 {title}")
    print("=" * 100)
    print("명령어:")
    for cmd in registry.get_commands():
        usage_col = f"  {cmd.usage:<36}"
        example_part = f"   예) {cmd.example}" if cmd.example else ""
        print(f"{usage_col}{cmd.description}{example_part}")
    print("=" * 100)
    print("\n💡 사용 예시:")
    print("  /context src/*.py 이 코드를 리뷰해줘")
    print("  /read [src/*.py, docs/*.md]")
    print("  /history --remove 5")
    print("  /auto_context original/*.md 한글로 번역해줘")
    print("\n✨ AI 자동 기능:")
    print("  - 파일 시스템 조작 (읽기/쓰기/목록)")
    print("  - Git 버전 관리 (상태/diff/커밋)")
    print("  - 패키지 의존성 분석 (pip/npm)")
    print("=" * 100)
