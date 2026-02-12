"""
TokenManager - 토큰 관리 및 자동 트리밍 모듈
"""

from typing import List, Dict, Tuple


class TokenManager:
    """대화 히스토리 토큰 관리"""
    
    # 플랫폼별 컨텍스트 윈도우의 75%를 안전 한도로 설정
    MAX_TOKENS_CLAUDE = 150000   # Claude: 200K의 75%
    MAX_TOKENS_GENAI = 96000     # GenAI: 128K의 75%
    MAX_TOKENS_GEMINI = 786000   # Gemini: 1M의 약 75%
    
    # 기본값 (Claude 기준)
    DEFAULT_MAX_TOKENS = 150000
    
    # 최소 유지할 메시지 수 (user + assistant 쌍)
    MIN_MESSAGES_TO_KEEP = 6
    
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
    def auto_trim_history(
        cls,
        conversation_history: List[Dict],
        max_tokens: int = None,
        verbose: bool = True
    ) -> List[Dict]:
        """
        히스토리가 토큰 한도를 초과하면 오래된 메시지를 제거합니다.
        
        Args:
            conversation_history: 대화 히스토리 리스트
            max_tokens: 최대 허용 토큰 수 (기본값: DEFAULT_MAX_TOKENS)
            verbose: 트리밍 발생 시 메시지 출력 여부
            
        Returns:
            트리밍된 대화 히스토리
        """
        if max_tokens is None:
            max_tokens = cls.DEFAULT_MAX_TOKENS
        
        current_tokens = cls.count_tokens(conversation_history)
        
        if current_tokens <= max_tokens:
            return conversation_history
        
        if verbose:
            print(f"\n⚠️ 토큰 한도 초과 ({current_tokens:,} > {max_tokens:,})")
            print("🔄 자동 트리밍 시작...")
        
        removed_count = 0
        
        # 최소 유지 메시지 수 확보하면서 오래된 메시지 제거
        while (len(conversation_history) > cls.MIN_MESSAGES_TO_KEEP and
               cls.count_tokens(conversation_history) > max_tokens):
            conversation_history.pop(0)
            removed_count += 1
        
        if verbose:
            final_tokens = cls.count_tokens(conversation_history)
            print(f"✅ 트리밍 완료: {removed_count}개 메시지 제거")
            print(f"📊 현재 토큰: {final_tokens:,} / {max_tokens:,} ({final_tokens * 100 // max_tokens}%)")
        
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
