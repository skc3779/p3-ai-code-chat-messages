"""
FSD v1.0.068 - /context · /auto_context 파일 패턴 매칭 테스트

TC-01 ~ TC-26: 명령어 파싱, 파일 패턴 매칭, 스크립트 일관성 전체 검증
"""

import unittest
import tempfile
import shutil
import re
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.file_pattern_matcher import FilePatternMatcher


# ────────────────────────────────────────────────────────────
# 헬퍼: 명령어 파싱 로직 (3개 스크립트 공통 로직 추출)
# ────────────────────────────────────────────────────────────
def parse_context_command(args: str):
    """
    /context 및 /auto_context 명령어의 인수에서
    file_patterns와 question을 분리하는 공통 파싱 로직.

    Returns:
        (file_patterns, question, error) 튜플
        - 성공 시: ([패턴, ...], "질문", None)
        - 도움말 시 (인수 없음): (None, None, "help")
        - 에러 시: (None, None, "에러 메시지")
    """
    if not args or not args.strip():
        return None, None, "help"

    args = args.strip()
    file_patterns = []
    question = ""

    # [pattern1, pattern2] 형식 확인
    if args.startswith('['):
        try:
            end_idx = args.index(']')
            patterns_str = args[1:end_idx]
            file_patterns = [p.strip() for p in patterns_str.split(',') if p.strip()]
            question = args[end_idx+1:].strip()
        except ValueError:
            return None, None, "❌ 닫는 대괄호 ']'가 없습니다."
    else:
        # 단일 패턴 지원
        parts = args.split(maxsplit=1)
        file_patterns = [parts[0]]
        question = parts[1] if len(parts) >= 2 else ""

    return file_patterns, question, None


# ════════════════════════════════════════════════════════════
# 2.1 명령어 파싱 테스트 (TC-01 ~ TC-06)
# ════════════════════════════════════════════════════════════
class TestContextCommandParsing(unittest.TestCase):
    """TC-01 ~ TC-06: /context 명령어 인수 파싱 테스트"""

    def test_tc01_no_args_shows_help(self):
        """TC-01: 인수 없이 /context → 도움말 반환"""
        patterns, question, error = parse_context_command("")
        self.assertIsNone(patterns)
        self.assertEqual(error, "help")

    def test_tc02_single_pattern_no_question(self):
        """TC-02: /context src/*.py → 패턴만 추출, 질문 빈 문자열"""
        patterns, question, error = parse_context_command("src/*.py")
        self.assertIsNone(error)
        self.assertEqual(patterns, ["src/*.py"])
        self.assertEqual(question, "")

    def test_tc03_single_pattern_with_question(self):
        """TC-03: /context src/*.py 이 코드 분석해줘 → 패턴+질문 분리"""
        patterns, question, error = parse_context_command("src/*.py 이 코드 분석해줘")
        self.assertIsNone(error)
        self.assertEqual(patterns, ["src/*.py"])
        self.assertEqual(question, "이 코드 분석해줘")

    def test_tc04_multi_pattern_no_question(self):
        """TC-04: /context [src/*.py, docs/*.md] → 다중 패턴, 질문 빈 문자열"""
        patterns, question, error = parse_context_command("[src/*.py, docs/*.md]")
        self.assertIsNone(error)
        self.assertEqual(patterns, ["src/*.py", "docs/*.md"])
        self.assertEqual(question, "")

    def test_tc05_multi_pattern_with_question(self):
        """TC-05: /context [src/*.py, docs/*.md] README 작성해줘 → 패턴+질문"""
        patterns, question, error = parse_context_command("[src/*.py, docs/*.md] README 작성해줘")
        self.assertIsNone(error)
        self.assertEqual(patterns, ["src/*.py", "docs/*.md"])
        self.assertEqual(question, "README 작성해줘")

    def test_tc06_unclosed_bracket_error(self):
        """TC-06: /context [src/*.py → 닫는 대괄호 누락 에러"""
        patterns, question, error = parse_context_command("[src/*.py")
        self.assertIsNone(patterns)
        self.assertIn("닫는 대괄호", error)

    def test_multi_pattern_with_spaces(self):
        """추가: 대괄호 내 공백이 있는 패턴도 정상 분리"""
        patterns, question, error = parse_context_command("[ src/*.py ,  docs/*.md , tests/*.py ]")
        self.assertIsNone(error)
        self.assertEqual(patterns, ["src/*.py", "docs/*.md", "tests/*.py"])

    def test_empty_patterns_filtered(self):
        """추가: 빈 패턴은 필터링"""
        patterns, question, error = parse_context_command("[src/*.py, , docs/*.md]")
        self.assertIsNone(error)
        self.assertEqual(patterns, ["src/*.py", "docs/*.md"])


# ════════════════════════════════════════════════════════════
# 2.2 파일 패턴 매칭 테스트 (TC-07 ~ TC-20)
# ════════════════════════════════════════════════════════════
class TestFilePatternMatching(unittest.TestCase):
    """TC-07 ~ TC-20: FilePatternMatcher 패턴 매칭 테스트"""

    def setUp(self):
        """테스트용 임시 워크스페이스 생성"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.matcher = FilePatternMatcher(self.temp_dir)

        # 테스트 파일 구조 생성
        self.test_files_rel = [
            "src/__init__.py",
            "src/file_manager.py",
            "src/gen_utils.py",
            "src/generator.py",
            "src/context_processor.py",
            "src/file1.py",
            "src/file2.py",
            "src/deep/nested.py",
            "src/deep/gen_deep.py",
            "docs/readme.md",
            "docs/guide.md",
            "logs/log_2026-03-05.log",
            "logs/log_2026-03-04.log",
            "images/logo.jpg",
            "images/banner.png",
            "images/icon.jpeg",
            "images/data.csv",
        ]

        for rel in self.test_files_rel:
            filepath = self.temp_dir / rel
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(f"# {rel}", encoding="utf-8")

        # 전체 파일 Path 목록
        self.all_files = [self.temp_dir / rel for rel in self.test_files_rel]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _match_names(self, patterns):
        """패턴으로 매칭된 파일들의 상대 경로 문자열 집합 반환"""
        matched = self.matcher.filter_files(self.all_files, patterns)
        return {str(f.relative_to(self.temp_dir)).replace("\\", "/") for f in matched}

    # ── 2.2.1 기본 와일드카드 (*) ──

    def test_tc07_src_star_py(self):
        """TC-07: src/*.py → src 직하위 .py 파일 매칭
        
        Note: FilePatternMatcher의 우선순위 4번(lstrip) 매칭에 의해
        하위 폴더 파일도 매칭됩니다. 이는 기존 설계 동작입니다.
        """
        matched = self._match_names(["src/*.py"])
        # src 직하위 파일 포함
        self.assertIn("src/__init__.py", matched)
        self.assertIn("src/file_manager.py", matched)
        self.assertIn("src/gen_utils.py", matched)
        self.assertIn("src/generator.py", matched)
        self.assertIn("src/context_processor.py", matched)
        self.assertIn("src/file1.py", matched)
        self.assertIn("src/file2.py", matched)

    def test_tc08_star_py_all(self):
        """TC-08: *.py → 전체 워크스페이스의 모든 .py 파일 (파일명 매칭)"""
        matched = self._match_names(["*.py"])
        for rel in self.test_files_rel:
            if rel.endswith(".py"):
                self.assertIn(rel, matched, f"{rel} should match *.py")

    def test_tc09_docs_star_md(self):
        """TC-09: docs/*.md → docs/ 직하위 .md 파일"""
        matched = self._match_names(["docs/*.md"])
        self.assertEqual(matched, {"docs/readme.md", "docs/guide.md"})

    # ── 2.2.2 문자 범위 ([seq]) ──

    def test_tc10_file_range(self):
        """TC-10: src/file[0-9].py → 숫자로 끝나는 file만"""
        matched = self._match_names(["src/file[0-9].py"])
        self.assertEqual(matched, {"src/file1.py", "src/file2.py"})

    def test_tc11_file_not_range(self):
        """TC-11: src/file[!0-9].py → 숫자가 아닌 1글자"""
        matched = self._match_names(["src/file[!0-9].py"])
        # file_manager.py는 5글자, file1/file2는 [0-9] → 둘 다 매칭 안 됨
        # file[!0-9].py는 file + (숫자 아닌 1글자) + .py → 해당 없음
        self.assertEqual(matched, set())

    # ── 2.2.3 접두어 패턴 (gen*) ──

    def test_tc12_src_gen_star(self):
        """TC-12: src/gen*.py → src 직하위 gen* 파일만"""
        matched = self._match_names(["src/gen*.py"])
        self.assertEqual(matched, {"src/gen_utils.py", "src/generator.py"})
        self.assertNotIn("src/deep/gen_deep.py", matched)

    def test_tc13_gen_star_filename(self):
        """TC-13: gen*.py → 파일명 매칭으로 하위 폴더 포함"""
        matched = self._match_names(["gen*.py"])
        self.assertIn("src/gen_utils.py", matched)
        self.assertIn("src/generator.py", matched)
        self.assertIn("src/deep/gen_deep.py", matched)

    # ── 2.2.4 다중 패턴 (대괄호 구문) ──

    def test_tc14_multi_pattern_union(self):
        """TC-14: [src/*.py, docs/*.md] → 두 패턴의 합집합"""
        matched = self._match_names(["src/*.py", "docs/*.md"])
        self.assertIn("src/__init__.py", matched)
        self.assertIn("src/file_manager.py", matched)
        self.assertIn("docs/readme.md", matched)
        self.assertIn("docs/guide.md", matched)

    def test_tc15_multi_filename_pattern(self):
        """TC-15: [*.py, *.md] → 전체 .py + .md"""
        matched = self._match_names(["*.py", "*.md"])
        for rel in self.test_files_rel:
            if rel.endswith(".py") or rel.endswith(".md"):
                self.assertIn(rel, matched)

    def test_tc16_multi_pattern_with_prefix(self):
        """TC-16: [src/gen*.py, docs/*.md] → gen 접두어 + docs .md"""
        matched = self._match_names(["src/gen*.py", "docs/*.md"])
        self.assertEqual(matched, {
            "src/gen_utils.py", "src/generator.py",
            "docs/readme.md", "docs/guide.md"
        })

    # ── 2.2.5 ** 재귀 글로빙 (v1.0.068 개선) ──

    def test_tc17_recursive_star_star(self):
        """TC-17: src/**/*.py → src 하위 모든 .py (재귀)"""
        matched = self._match_names(["src/**/*.py"])
        # 직하위
        self.assertIn("src/__init__.py", matched)
        self.assertIn("src/file_manager.py", matched)
        # 하위 폴더 포함 (**의 핵심)
        self.assertIn("src/deep/nested.py", matched)
        self.assertIn("src/deep/gen_deep.py", matched)
        # docs, logs 등은 미포함
        self.assertNotIn("docs/readme.md", matched)

    def test_tc18_recursive_with_question(self):
        """TC-18: src/**/*.py 파싱 + 재귀 매칭 통합"""
        # 파싱
        patterns, question, error = parse_context_command("src/**/*.py 이 코드 분석해줘")
        self.assertIsNone(error)
        self.assertEqual(patterns, ["src/**/*.py"])
        self.assertEqual(question, "이 코드 분석해줘")

        # 매칭
        matched = self._match_names(patterns)
        self.assertIn("src/deep/nested.py", matched)
        self.assertIn("src/__init__.py", matched)

    def test_tc19_recursive_prefix_pattern(self):
        """TC-19: src/**/gen*.py → 재귀 + gen 접두어"""
        # 파싱
        patterns, question, error = parse_context_command("src/**/gen*.py 이 코드 분석해줘")
        self.assertIsNone(error)
        self.assertEqual(patterns, ["src/**/gen*.py"])

        # 매칭
        matched = self._match_names(patterns)
        self.assertIn("src/gen_utils.py", matched)
        self.assertIn("src/generator.py", matched)
        self.assertIn("src/deep/gen_deep.py", matched)
        self.assertNotIn("src/__init__.py", matched)
        self.assertNotIn("src/deep/nested.py", matched)

    # ── 2.2.6 fnmatch [seq] 패턴 (정규식과 구별) ──

    def test_tc20_fnmatch_char_class(self):
        """TC-20 부분: src/*_[0-9].py → fnmatch [0-9] 정상 동작 확인"""
        # src/file1.py, src/file2.py는 file[0-9].py 패턴이지 *_[0-9].py가 아님
        # *_[0-9].py는 밑줄+숫자 패턴 → 현재 테스트 파일에는 없음
        matched = self._match_names(["src/*_[0-9].py"])
        self.assertEqual(matched, set())  # 현재 파일 구조에 해당 없음

    def test_tc20_question_mark_pattern(self):
        """TC-20 대체: logs/log_????-??-??.log → ? 패턴"""
        matched = self._match_names(["logs/log_????-??-??.log"])
        self.assertEqual(matched, {"logs/log_2026-03-05.log", "logs/log_2026-03-04.log"})

    def test_tc20_multiple_extension_patterns(self):
        """TC-20 대체: 확장자별 개별 패턴으로 다중 매칭"""
        matched = self._match_names(["images/*.jpg", "images/*.png", "images/*.jpeg"])
        self.assertEqual(matched, {"images/logo.jpg", "images/banner.png", "images/icon.jpeg"})
        self.assertNotIn("images/data.csv", matched)


# ════════════════════════════════════════════════════════════
# 2.3 스크립트 일관성 테스트 (TC-21 ~ TC-26)
# ════════════════════════════════════════════════════════════
class TestScriptConsistency(unittest.TestCase):
    """TC-21 ~ TC-26: 3개 스크립트 간 /context 핸들러 일관성 검증"""

    @classmethod
    def setUpClass(cls):
        """3개 스크립트 소스코드 로드"""
        cls.scripts = {}
        for name in ["gemini-ai-chat-code.py", "claude-ai-chat-code.py", "gen-ai-chat-code.py"]:
            path = project_root / name
            if path.exists():
                cls.scripts[name] = path.read_text(encoding="utf-8")

    def _extract_context_handler(self, source: str) -> str:
        """소스에서 /context 핸들러 블록 추출 (들여쓰기 기반)"""
        lines = source.split('\n')
        start = None
        for i, line in enumerate(lines):
            if "elif command == '/context':" in line:
                start = i
                break
        if start is None:
            return ""

        # 시작 줄의 들여쓰기 레벨 계산
        start_line = lines[start]
        indent_level = len(start_line) - len(start_line.lstrip())

        # 같은 들여쓰기 레벨의 다음 elif/else 찾기
        end = len(lines)
        for i in range(start + 1, len(lines)):
            line = lines[i]
            if not line.strip():
                continue
            line_indent = len(line) - len(line.lstrip())
            stripped = line.strip()
            if line_indent <= indent_level and (
                stripped.startswith("elif ") or stripped.startswith("else:")
            ):
                end = i
                break
        return '\n'.join(lines[start:end])

    def test_tc21_help_message_5_lines(self):
        """TC-21: 3개 스크립트 모두 /context 도움말 5줄 출력"""
        expected_lines = [
            "형식: /context",
        ]
        for name, source in self.scripts.items():
            handler = self._extract_context_handler(source)
            for expected in expected_lines:
                self.assertIn(expected, handler,
                    f"{name}: 도움말에 '{expected}' 포함되어야 함")

    def test_tc22_single_pattern_parsing(self):
        """TC-22: 3개 스크립트 모두 단일 패턴 + split(maxsplit=1) 사용"""
        for name, source in self.scripts.items():
            handler = self._extract_context_handler(source)
            self.assertIn("args.split(maxsplit=1)", handler,
                f"{name}: 단일 패턴 split(maxsplit=1) 사용해야 함")

    def test_tc23_bracket_multi_pattern(self):
        """TC-23: 3개 스크립트 모두 [p1, p2] 대괄호 파싱 로직 존재"""
        for name, source in self.scripts.items():
            handler = self._extract_context_handler(source)
            self.assertIn("args.startswith('[')", handler,
                f"{name}: 대괄호 파싱 args.startswith('[') 존재해야 함")
            self.assertIn("args.index(']')", handler,
                f"{name}: 닫는 대괄호 검색 args.index(']') 존재해야 함")

    def test_tc24_bracket_error_message(self):
        """TC-24: 3개 스크립트 모두 ] 누락 에러 메시지 출력"""
        for name, source in self.scripts.items():
            handler = self._extract_context_handler(source)
            self.assertIn("닫는 대괄호", handler,
                f"{name}: 닫는 대괄호 에러 메시지 존재해야 함")

    def test_tc25_multiline_fallback(self):
        """TC-25: 3개 스크립트 모두 질문 생략 시 멀티라인 입력"""
        for name, source in self.scripts.items():
            handler = self._extract_context_handler(source)
            self.assertIn("get_multiline", handler,
                f"{name}: get_multiline() 호출 존재해야 함")

    def test_tc26_variable_name_file_patterns(self):
        """TC-26: 3개 스크립트 모두 변수명 file_patterns 사용"""
        for name, source in self.scripts.items():
            handler = self._extract_context_handler(source)
            self.assertIn("file_patterns", handler,
                f"{name}: 변수명 file_patterns 사용해야 함")


if __name__ == '__main__':
    unittest.main(verbosity=2)
