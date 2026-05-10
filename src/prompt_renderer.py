"""
PromptRenderer - 시스템 프롬프트 변수 치환 모듈 (FSD v1.0.161)

`{{key}}` 자리표시자를 dict 컨텍스트로 치환하는 경량 렌더러.
- Jinja2 종속을 도입하지 않는다 (현 프로젝트 의존성 최소화 원칙).
- 1패스 비재귀 치환. 값에 또 다른 `{{...}}` 가 있어도 재치환하지 않는다.
- 누락된 변수는 정책에 따라 (a) 빈 문자열로, (b) 자리표시자 보존, (c) 예외 중 선택 가능.
"""

import re
from typing import Mapping, List


class PromptRenderer:
    """`{{key}}` 자리표시자를 dict 로 치환하는 경량 렌더러."""

    _PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

    class MissingVariableError(KeyError):
        """on_missing='raise' 모드에서 누락 변수 발견 시 발생."""
        pass

    @classmethod
    def render(
        cls,
        template: str,
        context: Mapping[str, object],
        *,
        on_missing: str = "keep",
    ) -> str:
        """
        템플릿의 `{{key}}` 자리표시자를 context dict 의 값으로 치환한다.

        Args:
            template: 자리표시자가 포함된 원본 문자열.
            context: 치환에 사용할 키-값 매핑.
            on_missing: 키 누락 시 동작.
                - "keep"  : 자리표시자를 그대로 보존 (기본값, 디버깅 용이)
                - "empty" : 빈 문자열로 치환
                - "raise" : MissingVariableError 발생

        Returns:
            치환된 문자열.
        """
        if template is None:
            return ""
        if on_missing not in ("keep", "empty", "raise"):
            raise ValueError(f"invalid on_missing policy: {on_missing!r}")

        def repl(m: "re.Match[str]") -> str:
            key = m.group(1)
            if key in context:
                return str(context[key])
            if on_missing == "empty":
                return ""
            if on_missing == "raise":
                raise cls.MissingVariableError(key)
            return m.group(0)  # keep

        return cls._PATTERN.sub(repl, template)

    @classmethod
    def find_variables(cls, template: str) -> List[str]:
        """템플릿에 등장한 변수명을 등장 순으로 (중복 제거하여) 반환한다."""
        if not template:
            return []
        seen, out = set(), []
        for m in cls._PATTERN.finditer(template):
            k = m.group(1)
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out
