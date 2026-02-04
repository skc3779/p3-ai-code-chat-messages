"""
ResponseParser - AI 응답 파싱 유틸리티
"""

from typing import List
import re
from .file_manager import FileManager

class ResponseParser:
    """AI 응답에서 파일 블록을 추출하고 저장하는 파서"""
    
    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager

    def parse_and_save(self, response: str) -> List[str]:
        """
        AI 응답에서 ````filename:```` 로 시작하는 파일 블록을 추출하여 저장합니다.
        파일 내용에 내부 코드 블록(```python, ``` 등)이 포함되어 있어도
        올바르게 전체 내용을 캡처하도록 라인 기반 파서를 사용합니다.
        """
        saved_files: List[str] = []

        # 라인 단위로 파싱하기 위해 문자열을 분리
        lines = response.splitlines()

        collecting: bool = False               # 현재 파일 블록을 수집 중인지 여부
        current_path: str = ""                 # 현재 파일의 상대 경로
        current_content: List[str] = []        # 현재 파일에 쓸 내용 라인들
        
        delimiter: str = "```"                 # 현재 파일 블록의 닫는 구분자 (동적 감지)
        nested_block_depth: int = 0            # 중첩된 코드 블록 깊이

        for line in lines:
            stripped = line.strip()

            # ── 파일 블록 시작 ──
            # (수집 중이 아닐 때)
            if not collecting:
                # ```filename: 또는 ````filename: 등 감지
                match = re.match(r"^(`{3,})filename:(.+)$", stripped)
                if match:
                    delimiter = match.group(1)
                    current_path = match.group(2).strip()
                    collecting = True
                    current_content = []
                    nested_block_depth = 0
                    continue

            # ── 파일 블록 종료 및 내용 수집 ──
            if collecting:
                # 1. 중첩된 코드 블록 시작 감지 (예: ```python)
                #    구분자로 시작하되, 길이가 더 길면(태그 등) 중첩 시작으로 간주
                if stripped.startswith(delimiter) and len(stripped) > len(delimiter):
                    nested_block_depth += 1
                
                # 2. 코드 블록 종료 후보 감지
                elif stripped == delimiter:
                    if nested_block_depth > 0:
                        # 중첩된 내부 블록의 종료
                        nested_block_depth -= 1
                    else:
                        # 최상위 파일 블록의 종료 -> 파일 저장 프로세스
                        file_path = self.file_manager.workspace_dir / current_path

                        # 파일이 이미 존재하면 덮어쓰기 여부 확인
                        if file_path.exists():
                            print(f"\n⚠️  파일이 이미 존재합니다: {current_path}")
                            try:
                                confirm = input("덮어쓰시겠습니까? (y/N): ").strip().lower()
                                if confirm != 'y':
                                    print(f"⏭️  건너뛰기: {current_path}")
                                    collecting = False
                                    continue
                            except EOFError:
                                print(f"⏭️  입력 불가로 건너뛰기: {current_path}")
                                collecting = False
                                continue

                        # 파일에 내용 기록
                        file_content = "\n".join(current_content).strip()
                        if self.file_manager.write_file(file_path, file_content):
                            saved_files.append(current_path)
                            print(f"✅ 파일 저장됨: {current_path}")
                        else:
                            print(f"❌ 파일 저장 실패: {current_path}")

                        # 상태 초기화
                        collecting = False
                        current_path = ""
                        current_content = []
                        continue

                # 내용 추가
                current_content.append(line)

        # 닫히지 않은 파일 블록이 남아있는 경우 경고
        if collecting:
            print(f"⚠️  닫히지 않은 파일 블록 발견: {current_path}")

        return saved_files
