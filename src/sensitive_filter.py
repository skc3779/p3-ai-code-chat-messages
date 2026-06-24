"""
SensitiveWordFilter - GenAI 입력 컨텍스트 민감 단어 치환 모듈

FSD v1.0.058 / REQ-058-001~006
FSD v1.1.030

GenAI는 입력 context에 password, secret 등의 민감 단어가 포함되면
"The content was blocked by the filter" 오류가 발생한다.
이를 방지하기 위해 입력 전 민감 단어를 안전한 대체 문자열로 치환하고,
응답 수신 후 원래 단어로 복원한다.

흐름:
1. 입력 context에서 민감 단어 검사 (대소문자 구분 없음)
2. 민감 단어가 있으면 대소문자를 유지하면서 치환
3. 치환된 context를 GenAI에 전달
4. 응답 수신
5. 응답 내의 치환된 단어를 원래 단어로 복원
6. 복원된 응답을 반환
"""

import re
from typing import Dict, List, Tuple


class SensitiveWordFilter:
    """
    GenAI API 호출 시 민감 단어를 치환/복원하는 필터.

    민감 사전:
        password   -> p1assw1ord
        secret     -> s1ecr1et
        api_key    -> a1pi_k1ey
        apikey     -> a1pike1y
        token      -> t1oken
        credential -> c1red1ent1al

    대소문자 유지 치환 규칙:
        - 원문이 모두 대문자이면 치환어도 모두 대문자: PASSWORD -> P1ASSW1ORD
        - 원문이 Title Case이면 치환어도 Title Case: Password -> P1assw1ord
        - 그 외에는 치환어를 그대로 사용: password -> p1assw1ord
    """

    # 민감 단어 사전 (소문자 원본 -> 소문자 치환어)
    # 순서: 긴 단어부터 먼저 매칭 (api_key > apikey 등)
    SENSITIVE_DICT: List[Tuple[str, str]] = [
        ("credential", "c1red1ent1al"),
        ("password", "p1assw1ord"),
        ("Password", "P1assw1ord"),
        ("PASSWORD", "P1ASSW1ORD"),
        ("secret", "s1ecr1et")
    ]

    def __init__(self):
        """민감 단어 패턴을 컴파일하여 초기화한다."""
        # 대소문자 무시 정규식 패턴 생성 (긴 단어 우선)
        escaped_words = [re.escape(word) for word, _ in self.SENSITIVE_DICT]
        pattern_str = "|".join(escaped_words)
        self._pattern = re.compile(f"({pattern_str})", re.IGNORECASE)

        # 빠른 조회를 위한 소문자 매핑 딕셔너리
        self._forward_map: Dict[str, str] = {
            word: replacement for word, replacement in self.SENSITIVE_DICT
        }
        # 복원용 역방향 매핑 (소문자 치환어 -> 소문자 원본)
        self._reverse_map: Dict[str, str] = {
            replacement: word for word, replacement in self.SENSITIVE_DICT
        }

        # 복원용 정규식 패턴
        escaped_replacements = [re.escape(repl) for _, repl in self.SENSITIVE_DICT]
        reverse_pattern_str = "|".join(escaped_replacements)
        self._reverse_pattern = re.compile(f"({reverse_pattern_str})", re.IGNORECASE)

    @staticmethod
    def _apply_case(original: str, replacement: str) -> str:
        """
        원본 단어의 대소문자 패턴을 치환 단어에 적용한다.

        Rules:
            - 모두 대문자 → 치환어도 모두 대문자
            - Title Case (첫 글자 대문자) → 치환어도 Title Case
            - 그 외 → 치환어를 그대로 사용 (소문자)
        """
        if original.isupper():
            return replacement.upper()
        elif original[0].isupper():
            return replacement[0].upper() + replacement[1:]
        else:
            return replacement

    def has_sensitive_words(self, text: str) -> bool:
        """텍스트에 민감 단어가 포함되어 있는지 검사한다."""
        return bool(self._pattern.search(text))

    def get_detected_words(self, text: str) -> List[str]:
        """텍스트에서 감지된 민감 단어 목록을 반환한다."""
        return self._pattern.findall(text)

    def mask(self, text: str) -> str:
        """
        입력 텍스트의 민감 단어를 치환한다 (GenAI 전송 전).

        대소문자를 유지하면서 치환한다.
        예: Password -> P1assw1ord, PASSWORD -> P1ASSW1ORD
        """
        def _replace_match(match: re.Match) -> str:
            matched_word = match.group(0)
            lower_word = matched_word.lower()
            replacement = self._forward_map.get(lower_word, matched_word)
            return self._apply_case(matched_word, replacement)

        return self._pattern.sub(_replace_match, text)

    def unmask(self, text: str) -> str:
        """
        응답 텍스트의 치환된 단어를 원래 단어로 복원한다 (GenAI 응답 후).

        대소문자를 유지하면서 복원한다.
        예: P1assw1ord -> Password, P1ASSW1ORD -> PASSWORD
        """
        def _restore_match(match: re.Match) -> str:
            matched_word = match.group(0)
            lower_word = matched_word.lower()
            original = self._reverse_map.get(lower_word, matched_word)
            return self._apply_case(matched_word, original)

        return self._reverse_pattern.sub(_restore_match, text)

    def mask_contents(self, contents: list) -> list:
        """
        contents 배열(문자열 리스트)의 각 항목에서 민감 단어를 치환한다.
        GenAI API의 contents 필드는 문자열 배열이므로 각 문자열을 처리한다.
        """
        return [self.mask(item) if isinstance(item, str) else item for item in contents]

    def mask_system_prompt(self, prompt: str) -> str:
        """시스템 프롬프트에서 민감 단어를 치환한다."""
        return self.mask(prompt) if prompt else prompt