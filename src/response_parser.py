"""
ResponseParser - AI 응답 파싱 유틸리티
"""

import re
from typing import List

from .file_manager import FileManager


class ResponseParser:
    """AI 응답에서 파일 블록을 추출하고 저장하는 파서"""
    
    def __init__(self, file_manager: FileManager):
        self.file_block_validator = None
        self.file_manager = file_manager


    def _ensure_single_file_block_closed(self, text: str) -> str:
        """
        [개선 기능] 응답에 @@@filename: 블록이 단 '하나'만 존재할 때,
        닫는 구분자(예: @@@)가 누락되어 있다면 문자열 끝에 자동으로 추가합니다.
        """
        filename_pattern = r"^(@{3,})filename:(.+)$"
        lines = text.splitlines()

        # 1. 파일 블록 시작 패턴을 가진 라인들을 탐색
        valid_matches = []
        for line in lines:
            m = re.match(filename_pattern, line.strip())
            if m:
                valid_matches.append(m)

        # 2. 반드시 단 하나의 파일 블록만 존재할 때만 보정 로직 실행
        if len(valid_matches) != 1:
            return text

        delimiter = valid_matches[0].group(1)  # 매칭된 구분자 추출 (예: '@@@')

        # 3. 파서 상태를 가상으로 시뮬레이션하여 닫혔는지 판단
        collecting = False
        in_nested_block = False

        for idx, line in enumerate(lines):
            stripped = line.strip()

            if not collecting:
                match = re.match(filename_pattern, stripped)
                if match:
                    collecting = True
                    in_nested_block = False
                    continue

            if collecting:
                # 언어 태그가 있는 내부 중첩 코드 블록의 시작
                if stripped.startswith(delimiter) and len(stripped) > len(delimiter):
                    in_nested_block = True
                    continue

                # 정확히 구분자만 적혀있는 줄인 경우
                if stripped == delimiter:
                    # 이미 내부 중첩 블록 안이라면 -> 내부 블록만 종료
                    if in_nested_block:
                        in_nested_block = False
                        continue

                    # 내부 중첩 블록 밖이라면 -> 다음 줄을 확인하여 무명 중첩 블록인지 체크
                    next_idx = idx + 1
                    if next_idx < len(lines):
                        next_stripped = lines[next_idx].strip()
                        is_next_delimiter = next_stripped == delimiter
                        is_next_filename = bool(re.match(r"^@{3,}filename:.+$", next_stripped))

                        if (
                            next_stripped
                            and not is_next_delimiter
                            and not is_next_filename
                        ):
                            in_nested_block = True
                            continue

                    # 정상적으로 파일 블록이 종료됨
                    collecting = False

        # 4. 시뮬레이션 종료 시점에 블록이 닫히지 않았다면(collecting == True) 구분자 추가
        if collecting:
            if not text.endswith("\n"):
                text += "\n"
            text += delimiter

        return text

    def parse_and_save(self, response: str, *, auto_overwrite: bool = False) -> List[str]:
        """
        AI 응답에서 `@@@filename:` 로 시작하는 파일 블록을 추출하여 저장합니다.
        파일 내용에 내부 코드 블록(```python, ``` 등)이 포함되어 있어도
        올바르게 전체 내용을 캡처하도록 라인 기반 파서를 사용합니다.

        중첩 코드 블록 처리:
        - 언어 태그가 있는 ```lang → 내부 코드 블록 시작
        - 언어 태그가 없는 ``` → 내부 블록이 열려있으면 종료,
          아닌 경우 다음 줄 존재 여부로 내부 블록 시작 vs 파일 블록 종료 판별

        Args:
            response: AI 응답 원문
            auto_overwrite: True 면 기존 파일 존재 시에도 프롬프트 없이 덮어쓴다.
                            에이전트 루프의 Bypass Approvals 모드에서만 True 로 호출된다.
                            기본값 False — 대화형 경로는 기존 동작 유지.
        """

        # 동일 레벨의 보정 메서드 호출 (단일 파일 블록 누락 보정)
        response = self._ensure_single_file_block_closed(response)

        # 라인 단위로 파싱하기 위해 문자열을 분리
        saved_files: List[str] = []
        lines = response.splitlines()

        collecting: bool = False               # 현재 파일 블록을 수집 중인지 여부
        current_path: str = ""                 # 현재 파일의 상대 경로
        current_content: List[str] = []        # 현재 파일에 쓸 내용 라인들
        
        delimiter: str = "@@@"                 # 현재 파일 블록의 닫는 구분자 (동적 감지)
        in_nested_block: bool = False          # 내부 코드 블록이 열려있는지 여부

        for idx, line in enumerate(lines):
            stripped = line.strip()

            # ── 파일 블록 시작 ──
            # (수집 중이 아닐 때)
            if not collecting:
                # @@@filename: 또는 @@@@filename: 등 감지
                match = re.match(r"^(@{3,})filename:(.+)$", stripped)
                if match:
                    delimiter = match.group(1)
                    current_path = match.group(2).strip()
                    collecting = True
                    current_content = []
                    in_nested_block = False
                    continue

            # ── 파일 블록 종료 및 내용 수집 ──
            if collecting:
                # 1) 언어 태그가 있는 코드 블록 시작 (```python, ```sql 등)
                if stripped.startswith(delimiter) and len(stripped) > len(delimiter):
                    in_nested_block = True
                    current_content.append(line)
                    continue

                # 2) 정확히 delimiter만 있는 줄
                if stripped == delimiter:
                    # 2-a) 내부 블록이 열려있으면 → 내부 블록 종료
                    if in_nested_block:
                        in_nested_block = False
                        current_content.append(line)
                        continue

                    # 2-b) 내부 블록이 닫혀있는 상태에서 @@@ 발견
                    #      → 다음 줄을 확인하여 내부 코드 블록 시작인지 판별
                    next_idx = idx + 1
                    if next_idx < len(lines):
                        next_stripped = lines[next_idx].strip()
                        # 다음 줄이 비어있지 않고, @@@ 또는 @@@filename:이 아니면
                        # 이것은 언어 태그 없는 내부 코드 블록 시작
                        is_next_delimiter = next_stripped == delimiter
                        is_next_filename = re.match(
                            r"^@{3,}filename:.+$", next_stripped
                        )
                        if (
                            next_stripped
                            and not is_next_delimiter
                            and not is_next_filename
                        ):
                            in_nested_block = True
                            current_content.append(line)
                            continue

                    # 2-c) 최상위 파일 블록의 종료 -> 파일 저장 프로세스
                    file_path = self.file_manager.workspace_dir / current_path

                    # 파일이 이미 존재하면 덮어쓰기 여부 확인
                    if file_path.exists():
                        if auto_overwrite:
                            # Bypass Approvals — 사용자 프롬프트 없이 즉시 덮어쓰기
                            print(f"\n⚡ BYPASS: 기존 파일 자동 덮어쓰기: {current_path}")
                        else:
                            # 기존 동작(대화형) — 사용자 확인
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