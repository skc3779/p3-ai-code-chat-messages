"""
TokenManager - 토큰 관리 및 자동 트리밍 모듈
"""

import os
from typing import List, Dict, Tuple


def _env_int(name: str, default: int) -> int:
    """환경변수에서 정수 값을 읽어 반환. 유효하지 않으면 기본값 사용."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _env_int_range(name: str, default: int, minimum: int, maximum: int) -> int:
    """환경변수 정수를 범위 검증해 반환. 범위 밖/오류는 기본값."""
    value = _env_int(name, default)
    if minimum <= value <= maximum:
        return value
    return default


class TokenManager:
    """대화 히스토리 토큰 관리"""
    
    # 플랫폼별 컨텍스트 윈도우의 75%를 안전 한도로 설정
    MAX_TOKENS_CLAUDE = _env_int("MAX_TOKENS_CLAUDE", 150000)   # Claude: 200K의 75%
    MAX_TOKENS_GENAI = _env_int("MAX_TOKENS_GENAI",  96000)     # GenAI: 128K의 75%
    MAX_TOKENS_GEMINI = _env_int("MAX_TOKENS_GEMINI",  786000)  # Gemini: 1M의 약 75%
    
    # 기본값 (Claude 기준)
    DEFAULT_MAX_TOKENS = MAX_TOKENS_CLAUDE
    
    # 최대 유지할 메시지 수 (.env에서 설정 가능, 기본값 30, 최솟값 1)
    MAX_MESSAGES_TO_KEEP = max(1, _env_int("MAX_MESSAGES_TO_KEEP", 30))

    # /agents 전용 히스토리 보존 수 (FSD v1.1.073): 일반 채팅 설정과 분리
    MAX_AGENT_MESSAGES_TO_KEEP = _env_int_range(
        "MAX_AGENT_MESSAGES_TO_KEEP", 30, 2, 200
    )

    # 기본값 (복원 시 사용)
    DEFAULT_MAX_MESSAGES_TO_KEEP = max(1, _env_int("MAX_MESSAGES_TO_KEEP", 30))
    DEFAULT_MAX_AGENT_MESSAGES_TO_KEEP = MAX_AGENT_MESSAGES_TO_KEEP
    
    # 토큰 추정 비율 (평균적으로 1토큰 ≈ 4자, 한글은 약 2-3자)
    CHARS_PER_TOKEN = 3.5
    
    @classmethod
    def count_tokens(cls, messages: List[Dict]) -> int:
        """
        메시지 리스트의 총 토큰 수를 추정합니다.
        
        Args:
            messages: 대화 히스토리 리스트
            
        Returns:
            추정 토큰 수
        """
        total_chars = 0
        
        for msg in messages:
            content = msg.get("content", "")
            
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # tool_use 등 복합 컨텐츠 처리
                for item in content:
                    if isinstance(item, dict):
                        if "text" in item:
                            total_chars += len(item["text"])
                        elif "content" in item:
                            total_chars += len(str(item["content"]))
                    elif isinstance(item, str):
                        total_chars += len(item)
        
        return int(total_chars / cls.CHARS_PER_TOKEN)
    
    @classmethod
    def reload_from_env(cls):
        """
        .env 파일 로드 후 환경변수 값을 클래스 상수에 반영합니다.
        main 스크립트에서 load_dotenv() 호출 직후 사용합니다.
        """
        cls.MAX_TOKENS_CLAUDE = _env_int("MAX_TOKENS_CLAUDE", 150000)
        cls.MAX_TOKENS_GENAI  = _env_int("MAX_TOKENS_GENAI",  96000)
        cls.MAX_TOKENS_GEMINI = _env_int("MAX_TOKENS_GEMINI", 786000)
        cls.DEFAULT_MAX_TOKENS = cls.MAX_TOKENS_CLAUDE
        cls.MAX_MESSAGES_TO_KEEP = max(1, _env_int("MAX_MESSAGES_TO_KEEP", 30))
        cls.MAX_AGENT_MESSAGES_TO_KEEP = _env_int_range(
            "MAX_AGENT_MESSAGES_TO_KEEP", 30, 2, 200
        )
        cls.DEFAULT_MAX_MESSAGES_TO_KEEP = cls.MAX_MESSAGES_TO_KEEP
        cls.DEFAULT_MAX_AGENT_MESSAGES_TO_KEEP = cls.MAX_AGENT_MESSAGES_TO_KEEP

    @classmethod
    def set_max_messages(cls, value: int) -> None:
        """MAX_MESSAGES_TO_KEEP 을 런타임에 변경한다.

        Args:
            value: 0 이상의 정수
        Raises:
            ValueError: value < 0
        """
        if value < 1:
            raise ValueError("MAX_MESSAGES_TO_KEEP 은 1 이상이어야 합니다.")
        cls.MAX_MESSAGES_TO_KEEP = value

    @classmethod
    def reset_max_messages(cls) -> None:
        """MAX_MESSAGES_TO_KEEP 을 .env 기본값으로 복원한다."""
        cls.MAX_MESSAGES_TO_KEEP = cls.DEFAULT_MAX_MESSAGES_TO_KEEP

    @classmethod
    def format_token_report(
        cls,
        conversation_history: List[Dict],
        max_tokens: int = None,
        platform: str = "Claude",
    ) -> str:
        """통일된 /tokens 출력 문자열을 생성한다.

        Args:
            conversation_history: 대화 히스토리 리스트
            max_tokens: 현재 플랫폼의 최대 토큰 수
            platform: 플랫폼 이름 ("Claude", "GenAI", "Gemini")

        Returns:
            출력용 포맷팅된 문자열
        """
        if max_tokens is None:
            max_tokens = cls.DEFAULT_MAX_TOKENS

        stats = cls.get_token_stats(conversation_history, max_tokens)

        lines = [
            "\n📊 토큰 사용량:",
            f"   현재 토큰:  {stats['current']:,} / {stats['max']:,} ({stats['usage_percent']}%)",
            f"   메시지 수:  {stats['message_count']} / {cls.MAX_MESSAGES_TO_KEEP}",
            f"   남은 토큰:  {stats['remaining']:,}",
            "",
            "⚙️ 토큰 한계 설정:",
        ]

        platforms = [
            ("Claude", cls.MAX_TOKENS_CLAUDE),
            ("GenAI",  cls.MAX_TOKENS_GENAI),
            ("Gemini", cls.MAX_TOKENS_GEMINI),
        ]
        for name, limit in platforms:
            marker = " (현재)" if name == platform else ""
            lines.append(f"   {name + ':':9s}{limit:,}{marker}")

        return "\n".join(lines)

    @classmethod
    def auto_trim_history(
        cls,
        conversation_history: List[Dict],
        max_tokens: int = None,
        verbose: bool = True,
        max_messages: int = None,
    ) -> List[Dict]:
        """
        히스토리가 토큰 한도를 초과하거나 메시지 수가
        MAX_MESSAGES_TO_KEEP 이상이면 오래된 메시지를 제거합니다.

        MAX_TOKENS_* 환경변수는 이미 플랫폼 컨텍스트 윈도우의 75% 안전 상한이므로
        이 함수에서 0.75를 재적용하지 않는다. token_threshold = max_tokens.

        트리밍 조건 (OR):
          1. 메시지 수 >= MAX_MESSAGES_TO_KEEP
          2. 토큰 수 > max_tokens

        Args:
            conversation_history: 대화 히스토리 리스트
            max_tokens: 최대 허용 토큰 수 (기본값: DEFAULT_MAX_TOKENS)
            verbose: 트리밍 발생 시 메시지 출력 여부
            max_messages: 메시지 수 한도. None 이면 MAX_MESSAGES_TO_KEEP 사용

        Returns:
            트리밍된 대화 히스토리
        """
        if max_tokens is None:
            max_tokens = cls.DEFAULT_MAX_TOKENS

        if max_messages is None:
            max_messages = cls.MAX_MESSAGES_TO_KEEP
        else:
            max_messages = max(1, int(max_messages))

        current_tokens = cls.count_tokens(conversation_history)
        message_count = len(conversation_history)
        token_threshold = max_tokens

        # 트리밍 조건 확인: 메시지 수 >= max_messages OR 토큰 한도 초과
        needs_trim_by_messages = message_count >= max_messages
        needs_trim_by_tokens = current_tokens > token_threshold
        
        if not needs_trim_by_messages and not needs_trim_by_tokens:
            return conversation_history
        
        if verbose:
            reasons = []
            if needs_trim_by_messages:
                reasons.append(
                    f"메시지 수 초과 ({message_count}개 >= "
                    f"{max_messages}개)"
                )
            if needs_trim_by_tokens:
                reasons.append(
                    f"토큰 한도 초과 ({current_tokens:,} > "
                    f"{token_threshold:,})"
                )
            print(f"\n⚠️ 히스토리 트리밍 필요: {', '.join(reasons)}")
            print("🔄 자동 트리밍 시작...")
        
        removed_count = 0
        
        # 트리밍 루프: 두 조건 모두 해소될 때까지 오래된 메시지 제거
        # 단, 최소 2개(마지막 user + assistant 쌍)는 유지
        MIN_KEEP = 2
        while len(conversation_history) > MIN_KEEP:
            current_tokens = cls.count_tokens(conversation_history)
            current_count = len(conversation_history)

            still_over_messages = current_count >= max_messages
            still_over_tokens = current_tokens > token_threshold

            if not still_over_messages and not still_over_tokens:
                break

            conversation_history.pop(0)
            removed_count += 1
        
        if verbose:
            final_tokens = cls.count_tokens(conversation_history)
            print(f"✅ 트리밍 완료: {removed_count}개 메시지 제거")
            print(
                f"📊 현재 상태: 메시지 {len(conversation_history)}개, "
                f"토큰 {final_tokens:,} / {max_tokens:,} "
                f"({final_tokens * 100 // max_tokens}%)"
            )
        
        return conversation_history
    
    @classmethod
    def get_token_stats(
        cls,
        conversation_history: List[Dict],
        max_tokens: int = None
    ) -> Dict:
        """
        현재 토큰 사용량 통계를 반환합니다.
        
        Args:
            conversation_history: 대화 히스토리 리스트
            max_tokens: 최대 허용 토큰 수
            
        Returns:
            토큰 통계 딕셔너리
        """
        if max_tokens is None:
            max_tokens = cls.DEFAULT_MAX_TOKENS
        
        current_tokens = cls.count_tokens(conversation_history)
        
        return {
            "current": current_tokens,
            "max": max_tokens,
            "usage_percent": round(current_tokens * 100 / max_tokens, 1) if max_tokens > 0 else 0,
            "message_count": len(conversation_history),
            "remaining": max_tokens - current_tokens
        }
