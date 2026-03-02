"""
Context 파일 자동 처리기

/auto_context 명령어에서 매칭된 파일을 1개씩 순차적으로
AI에 전달하고, 응답에 포함된 파일을 자동 저장하는 프로세서.
"""

import re
from pathlib import Path
from typing import List, Tuple


class ContextProcessor:
    """파일 단위 자동 반복 처리기"""
    
    def fix_unbalance_backticks(self, text: str) -> str:
        """
        텍스트에서 닫히지 않은 백틱을 수정
        
        Args:
            text: 수정할 텍스트
            
        Returns:
            수정된 텍스트
        """
        
        backtick_count = text.count("```")
        if backtick_count % 2 != 0:
            if not text.endswith("\n"):
                text += "\n"
            text += "```"
        return text

    def __init__(self, assistant, file_manager, streaming: bool = True):
        """
        Args:
            assistant: AI 어시스턴트 인스턴스 (chat 메서드 필요)
            file_manager: FileManager 인스턴스
            streaming: 스트리밍 모드 여부
        """
        self.assistant = assistant
        self.file_manager = file_manager
        self.streaming = streaming

    def process_files(
        self,
        matched_files: List[Path],
        question: str,
    ) -> Tuple[int, int]:
        """
        매칭된 파일을 1개씩 순차 처리

        Args:
            matched_files: 처리할 파일 목록
            question: 사용자가 입력한 작업 지시문

        Returns:
            (처리 파일 수, 저장 파일 수) 튜플
        """
        total = len(matched_files)
        processed_count = 0
        saved_count = 0

        for idx, filepath in enumerate(matched_files, 1):
            try:
                rel_path = filepath.relative_to(self.file_manager.workspace_dir)
                print(f"\n━━━ [{idx}/{total}] {rel_path} ━━━")

                # 1. 파일 읽기
                print("📖 파일 읽는 중...")
                content = self.file_manager.read_file(filepath)
                if content is None:
                    print(f"❌ 파일 읽기 실패: {rel_path}")
                    continue

                # 2. 프롬프트 조합
                prompt = self._build_prompt(question, rel_path, content)

                # 3. AI에 전송
                print("🤖 AI 처리 중...")
                response = self.assistant.chat(
                    prompt,
                    streaming=self.streaming,
                    include_context=False
                )
                processed_count += 1

                # 4. 응답에서 파일 추출 및 자동 저장
                if response:
                    saved = self._auto_save_files(self.fix_unbalance_backticks(response))
                    saved_count += len(saved)

                    if not saved:
                        print("⚠️  응답에 저장할 파일 블록이 없습니다.")

            except KeyboardInterrupt:
                print(f"\n\n⚠️  사용자 중단 (Ctrl+C)")
                print(f"   처리 완료: {processed_count}/{total}개")
                break
            except Exception as e:
                print(f"❌ 처리 실패: {e}")
                try:
                    cont = input("▶ 다음 파일로 계속하시겠습니까? (Y/n): ").strip().lower()
                    if cont == 'n':
                        break
                except (EOFError, KeyboardInterrupt):
                    break

        # 5. 전체 요약
        print(f"\n{'='*60}")
        print(f"✅ 자동 처리 완료: {processed_count}개 파일 처리, {saved_count}개 파일 저장")
        print(f"{'='*60}")

        return processed_count, saved_count

    def _build_prompt(self, question: str, rel_path, content: str) -> str:
        """파일 내용을 포함한 프롬프트 생성"""
        return (
            f"{question}\n\n"
            f"--- 파일: {rel_path} ---\n"
            f"{content}\n"
            f"--- 파일 끝 ---"
        )

    def _auto_save_files(self, response: str) -> List[str]:
        """
        AI 응답에서 ```filename: 블록을 추출하여 자동 저장
        (확인 프롬프트 없이 자동 덮어쓰기)

        중첩 코드 블록 처리:
        - 언어 태그가 있는 ```lang → 내부 코드 블록 시작
        - 언어 태그가 없는 ``` → 내부 블록이 열려있으면 종료,
          아닌 경우 다음 줄 존재 여부로 내부 블록 시작 vs 파일 블록 종료 판별
        """
        saved_files: List[str] = []
        lines = response.splitlines()

        collecting = False
        current_path = ""
        current_content: List[str] = []
        delimiter = "```"
        in_nested_block = False

        for idx, line in enumerate(lines):
            stripped = line.strip()

            if not collecting:
                match = re.match(r"^(`{3,})filename:(.+)$", stripped)
                if match:
                    delimiter = match.group(1)
                    current_path = match.group(2).strip()
                    collecting = True
                    current_content = []
                    in_nested_block = False
                    continue

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

                    # 2-b) 내부 블록이 닫혀있는 상태에서 ``` 발견
                    #      → 다음 줄을 확인하여 내부 코드 블록 시작인지 판별
                    next_idx = idx + 1
                    if next_idx < len(lines):
                        next_stripped = lines[next_idx].strip()
                        # 다음 줄이 비어있지 않고, ``` 또는 ```filename:이 아니면
                        # 이것은 언어 태그 없는 내부 코드 블록 시작
                        is_next_delimiter = next_stripped == delimiter
                        is_next_filename = re.match(
                            r"^`{3,}filename:.+$", next_stripped
                        )
                        if (
                            next_stripped
                            and not is_next_delimiter
                            and not is_next_filename
                        ):
                            in_nested_block = True
                            current_content.append(line)
                            continue

                    # 2-c) 파일 블록 종료 → 저장
                    file_path = self.file_manager.workspace_dir / current_path
                    file_content = "\n".join(current_content).strip()

                    # 상위 디렉토리 자동 생성
                    file_path.parent.mkdir(parents=True, exist_ok=True)

                    if self.file_manager.write_file(file_path, file_content):
                        saved_files.append(current_path)
                        print(f"✅ 파일 저장됨: {current_path}")
                    else:
                        print(f"❌ 파일 저장 실패: {current_path}")

                    collecting = False
                    current_path = ""
                    current_content = []
                    continue

                current_content.append(line)

        if collecting:
            print(f"⚠️  닫히지 않은 파일 블록 발견: {current_path}")

        return saved_files
