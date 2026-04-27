"""
Context 파일 자동 처리기

/auto_context 명령어에서 매칭된 파일을 1개씩 순차적으로
AI에 전달하고, 응답에 포함된 파일을 자동 저장하는 프로세서.
"""

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import List, Tuple

from .quality_check_prompt import QUALITY_CHECK_SYSTEM_PROMPT


class ContextProcessor:
    """파일 단위 자동 반복 처리기"""
    
    def normalize_backtick_blocks(self, text: str) -> str:
        """
        AI 응답의 ``` 블록을 정렬한다.

        1. ``` 블록이 줄 시작에 오도록 정규화:
           ``` 앞에 \\n이 없는 경우(문자열 시작 제외) \\n을 삽입
        2. 언밸런스 ``` 보정:
           ``` 개수가 홀수면 닫히지 않은 블록이므로 \\n``` 를 말미에 추가
        """
        text = re.sub(r'(?<=[^\n])(```)', r'\n\1', text)
        if text.count("```") % 2 != 0:
            if not text.endswith("\n"):
                text += "\n"
            text += "```"
        return text

    def __init__(self, assistant, file_manager, streaming: bool = True,
                 *, quality_check: bool = False):
        """
        Args:
            assistant: AI 어시스턴트 인스턴스 (chat 메서드 필요)
            file_manager: FileManager 인스턴스
            streaming: 스트리밍 모드 여부
            quality_check: 2차 품질 검사 활성화 여부 (FSD v1.0.123)
        """
        self.assistant = assistant
        self.file_manager = file_manager
        self.streaming = streaming
        self.quality_check = quality_check
        # FR-076-005: 환경변수로 최대 재시도 횟수 설정 (기본값: 3)
        self.max_retries = max(1, int(os.getenv("AUTO_CONTEXT_MAX_RETRIES", "3")))
        # ENH-5: 2차 패치 실패 시 재시도 횟수 (기본 1 — 즉, 최대 2회 시도)
        self.qc_max_retries = max(0, int(os.getenv("AUTO_CONTEXT_QC_MAX_RETRIES", "1")))
        # ENH-4: 2차 검사 통계
        self._qc_stats = {"checked": 0, "applied": 0, "no_changes": 0, "failed": 0}

    def process_files(
        self,
        matched_files: List[Path],
        question: str,
    ) -> Tuple[int, int]:
        """
        매칭된 파일을 1개씩 순차 처리 (저장 실패 시 최대 max_retries회 재시도)

        Args:
            matched_files: 처리할 파일 목록
            question: 사용자가 입력한 작업 지시문

        Returns:
            (처리 파일 수, 저장 파일 수) 튜플
        """
        total = len(matched_files)
        processed_count = 0
        saved_count = 0
        failed_files: List[str] = []  # FR-076-003: 실패 파일 목록

        for idx, filepath in enumerate(matched_files, 1):
            try:
                rel_path = filepath.relative_to(self.file_manager.workspace_dir)
                print(f"\n━━━ [{idx}/{total}] {rel_path} ━━━")

                # 1. 파일 읽기
                print("📖 파일 읽는 중...")
                content = self.file_manager.read_file(filepath)
                if content is None:
                    print(f"❌ 파일 읽기 실패: {rel_path}")
                    failed_files.append(str(rel_path))
                    continue

                # 2. 프롬프트 조합
                prompt = self._build_prompt(question, rel_path, content)

                # 3~4. AI 전송 + 응답 저장 (재시도 포함)
                saved = []
                for attempt in range(1, self.max_retries + 1):
                    # 3. AI에 전송
                    if attempt == 1:
                        print("🤖 AI 처리 중...")
                    else:
                        print(f"🔄 재시도 [{attempt}/{self.max_retries}] AI 재전송 중...")

                    response = self.assistant.chat(
                        prompt,
                        streaming=self.streaming,
                        include_context=False
                    )

                    # FR-076-007: 응답이 비어있는 경우
                    if not response:
                        print(f"⚠️  AI 응답이 비어있습니다. (시도 {attempt}/{self.max_retries})")
                        if attempt < self.max_retries:
                            continue
                        else:
                            break

                    # 4. 응답에서 파일 추출 및 자동 저장
                    saved = self._auto_save_files(
                        self.normalize_backtick_blocks(response)
                    )

                    # FR-076-006: 저장 성공 판정
                    if saved:
                        saved_count += len(saved)

                        # ★ FSD v1.0.123: 2차 품질 검사 (FR-A-03)
                        if self.quality_check:
                            for saved_rel_path in saved:
                                self._run_quality_check(question, saved_rel_path)

                        break  # 성공 → 다음 파일로
                    else:
                        print(f"⚠️  응답에 저장할 파일 블록이 없습니다. (시도 {attempt}/{self.max_retries})")
                        if attempt < self.max_retries:
                            continue  # 재시도
                        # 마지막 시도도 실패

                # 재시도 모두 실패한 경우
                if not saved:
                    print(f"❌ {self.max_retries}회 시도 후에도 저장 실패: {rel_path}")
                    failed_files.append(str(rel_path))

                processed_count += 1

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

        # FSD v1.0.123 § A.4.6: 2차 검사 통계 출력
        if self.quality_check:
            s = self._qc_stats
            print(
                f"🔍 품질 검사:    {s['checked']}건 검사 — "
                f"패치 적용 {s['applied']}건, 변경 없음 {s['no_changes']}건, "
                f"실패 {s['failed']}건"
            )

        # FR-076-004: 실패 파일 요약
        if failed_files:
            print(f"\n❌ 저장 실패 파일 ({len(failed_files)}개):")
            for ff in failed_files:
                print(f"   - {ff}")

        print(f"{'='*60}")

        return processed_count, saved_count

    # ─── FSD v1.0.123: 2차 품질 검사 메서드 ─────────────────────

    def _run_quality_check(self, original_question: str, saved_rel_path: str) -> None:
        """2차 품질 검사 — saved_rel_path 에 대해 QC 호출 후 patch 적용.

        FSD v1.0.123 § A.4.3
        """
        abs_path = self.file_manager.workspace_dir / saved_rel_path
        if not abs_path.exists():
            # 동시에 다른 도구가 지웠을 가능성 — skip
            print(f"⚠️  QC 건너뜀 (파일 없음): {saved_rel_path}")
            self._qc_stats["failed"] += 1
            return

        saved_content = self.file_manager.read_file(abs_path)
        if saved_content is None:
            print(f"⚠️  QC 건너뜀 (읽기 실패): {saved_rel_path}")
            self._qc_stats["failed"] += 1
            return

        qc_prompt = self._build_qc_prompt(original_question, saved_rel_path, saved_content)
        print("🔍 품질 검사 (2차) 진행 중...")

        # ENH-5: patch_failed 시 재시도 (총 qc_max_retries+1 회)
        last_status = None
        for attempt in range(1, self.qc_max_retries + 2):
            with self._temporarily_override_system_prompt(QUALITY_CHECK_SYSTEM_PROMPT):
                response = self.assistant.chat(
                    qc_prompt,
                    streaming=self.streaming,
                    include_context=False,
                )

            if not response:
                last_status = "no_changes"
                break

            status, applied, total = self._apply_qc_patches(
                self.normalize_backtick_blocks(response),
                saved_rel_path,
            )
            last_status = status

            if status == "applied":
                print(f"✅ QC 패치 적용: {saved_rel_path} — {applied}/{total} blocks")
                break
            if status == "no_changes":
                print("✓ QC 결과: 변경 없음")
                break
            if status == "rejected_filename":
                print("⚠️  QC 응답에 ```filename:``` 펜스 — 거부 (patch 만 허용)")
                break  # filename 응답은 재시도해도 같은 결과일 가능성 큼
            if status == "patch_failed":
                if attempt <= self.qc_max_retries:
                    print(f"🔄 QC 재시도 [{attempt+1}/{self.qc_max_retries+1}] — patch 실패")
                    # ENH-5: 재시도 시 user 메시지에 직전 실패 안내 추가
                    qc_prompt = qc_prompt + (
                        "\n\n[직전 시도]\n"
                        "patch 적용에 실패했습니다. SEARCH 블록에 위·아래 컨텍스트를 더 포함시켜\n"
                        "원본 파일에 정확히 한 번만 매칭되도록 다시 출력하세요."
                    )
                    continue
                else:
                    print(f"❌ QC patch 적용 실패 (재시도 모두 소진): {saved_rel_path}")
                    break

        # 통계 누적
        self._qc_stats["checked"] += 1
        if last_status == "applied":
            self._qc_stats["applied"] += 1
        elif last_status == "no_changes":
            self._qc_stats["no_changes"] += 1
        else:
            self._qc_stats["failed"] += 1

    @contextmanager
    def _temporarily_override_system_prompt(self, override: str):
        """assistant.system_prompt 를 일시적으로 override 후 finally 에서 원복.

        FSD v1.0.123 § A.4.4 — NFR-02 준수 (예외 발생 시에도 반드시 원복)
        """
        if not hasattr(self.assistant, "system_prompt"):
            # 호환성 — 어시스턴트가 system_prompt 속성을 안 가진 경우
            yield
            return
        original = self.assistant.system_prompt
        try:
            self.assistant.system_prompt = override
            yield
        finally:
            self.assistant.system_prompt = original

    def _build_qc_prompt(self, question: str, rel_path: str, content: str) -> str:
        """2차 검사용 user 메시지 구성.

        FSD v1.0.123 § A.3.4
        """
        return (
            f"[원래 사용자 요청]\n"
            f"{question}\n\n"
            f"[1차 답변으로 저장된 파일]\n"
            f"경로: {rel_path}\n"
            f"내용:\n"
            f"--- BEGIN ---\n"
            f"{content}\n"
            f"--- END ---\n\n"
            f"위 파일을 system prompt 의 검사 항목에 따라 검토하고,\n"
            f"수정이 필요한 부분만 ```patch:{rel_path}``` 펜스로 출력하세요.\n"
            f"수정사항이 없으면 \"품질 양호 — 수정사항 없음\" 한 줄만 출력하세요."
        )

    def _apply_qc_patches(self, response: str, expected_rel_path: str) -> Tuple[str, int, int]:
        """2차 응답에서 patch 펜스를 추출해 적용.

        FSD v1.0.123 § A.3.5

        Returns:
            (status, applied_blocks, total_blocks)
            status ∈ {"applied", "no_changes", "rejected_filename", "patch_failed"}
        """
        # 1) "수정사항 없음" 단축 응답
        if "품질 양호" in response and "```patch:" not in response:
            return ("no_changes", 0, 0)

        # 2) ```filename:``` 펜스 — 정책 위반: QC 는 patch 만 허용
        has_filename = bool(re.search(r"^`{3,}filename:", response, re.MULTILINE))
        has_patch = bool(re.search(r"^`{3,}patch:", response, re.MULTILINE))
        if has_filename and not has_patch:
            return ("rejected_filename", 0, 0)

        # 3) ```patch:<path>``` 펜스 추출
        blocks = self._extract_patch_fences(response)
        if not blocks:
            return ("no_changes", 0, 0)

        from .agent_patch_applier import AgentPatchApplier
        applier = AgentPatchApplier(self.file_manager)

        applied_total = 0
        block_total = 0
        failed = False
        for fence_path, payload in blocks:
            if fence_path != expected_rel_path:
                print(f"⚠️  QC 응답의 patch 경로가 다릅니다: {fence_path} (기대: {expected_rel_path})")
            result = applier.apply(fence_path, payload, auto_approve=True)
            block_total += result.total_count
            if result.success:
                applied_total += result.applied_count
            else:
                failed = True
                print(f"❌ QC patch 실패 ({fence_path}): {result.error or '블록 매칭 실패'}")

        if failed:
            return ("patch_failed", applied_total, block_total)
        return ("applied", applied_total, block_total)

    def _extract_patch_fences(self, response: str) -> List[Tuple[str, str]]:
        """
        응답에서 ```patch:<path> ... ``` 펜스를 추출.

        FSD v1.0.123 § A.4.5

        Returns:
            [(rel_path, body), ...]
        """
        pairs: List[Tuple[str, str]] = []
        lines = response.splitlines()
        i = 0
        while i < len(lines):
            m = re.match(r"^(`{3,})patch:(.+)$", lines[i].strip())
            if not m:
                i += 1
                continue
            fence = m.group(1)
            path = m.group(2).strip()
            body: List[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != fence:
                body.append(lines[i])
                i += 1
            pairs.append((path, "\n".join(body)))
            i += 1  # 닫는 fence 건너뜀
        return pairs

    # ─── 기존 메서드 ─────────────────────────────────────────────

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

        전처리:
        - ``` 앞에 \\n이 없으면(문자열 시작 제외) 자동으로 \\n을 삽입
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
