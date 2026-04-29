"""
APIRetry - API 호출 재시도 모듈 (지수 백오프)
"""

import time
import random
from typing import Callable, Any, Set
from functools import wraps


class APIRetry:
    """API 호출 재시도 로직 (지수 백오프)"""
    
    # 기본 설정
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # 초
    MAX_DELAY = 30.0  # 최대 대기 시간
    
    # 재시도 가능한 HTTP 상태 코드
    RETRYABLE_STATUS_CODES: Set[int] = {
        408,  # Request Timeout
        429,  # Too Many Requests (Rate Limit)
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504,  # Gateway Timeout
    }
    
    @classmethod
    def is_retryable_error(cls, status_code: int) -> bool:
        """
        재시도 가능한 오류인지 확인합니다.
        
        Args:
            status_code: HTTP 상태 코드
            
        Returns:
            재시도 가능 여부
        """
        return status_code in cls.RETRYABLE_STATUS_CODES
    
    @classmethod
    def calculate_delay(cls, attempt: int) -> float:
        """
        지수 백오프 + 지터를 적용한 대기 시간을 계산합니다.
        
        Args:
            attempt: 현재 시도 횟수 (0부터 시작)
            
        Returns:
            대기 시간 (초)
        """
        # 지수 백오프: 2^attempt * base_delay
        delay = cls.BASE_DELAY * (2 ** attempt)
        
        # 지터 추가 (0.5 ~ 1.5 배)
        jitter = 0.5 + random.random()
        delay *= jitter
        
        # 최대 대기 시간 제한
        return min(delay, cls.MAX_DELAY)
    
    @classmethod
    def retry_request(
        cls,
        request_func: Callable,
        *args,
        max_retries: int = None,
        verbose: bool = True,
        **kwargs
    ) -> Any:
        """
        HTTP 요청을 재시도 로직과 함께 실행합니다.
        
        Args:
            request_func: requests.get 또는 requests.post 등
            *args: 요청 함수에 전달할 위치 인자
            max_retries: 최대 재시도 횟수 (기본값: MAX_RETRIES)
            verbose: 재시도 메시지 출력 여부
            **kwargs: 요청 함수에 전달할 키워드 인자
            
        Returns:
            응답 객체
            
        Raises:
            마지막 시도에서 발생한 예외
        """
        if max_retries is None:
            max_retries = cls.MAX_RETRIES
        
        last_exception = None
        
        for attempt in range(max_retries + 1):  # 최초 시도 + 재시도
            try:
                response = request_func(*args, **kwargs)
                
                # 성공 또는 재시도 불가능한 오류
                if response.status_code < 400 or not cls.is_retryable_error(response.status_code):
                    return response
                
                # 재시도 가능한 오류
                if attempt < max_retries:
                    delay = cls.calculate_delay(attempt)
                    if verbose:
                        print(f"\n⚠️ API 오류 ({response.status_code}). {delay:.1f}초 후 재시도... ({attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    return response  # 마지막 시도 - 오류 응답 그대로 반환
                    
            except Exception as e:
                last_exception = e
                
                if attempt < max_retries:
                    delay = cls.calculate_delay(attempt)
                    if verbose:
                        print(f"\n⚠️ 네트워크 오류: {str(e)[:50]}. {delay:.1f}초 후 재시도... ({attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    raise  # 마지막 시도 - 예외 다시 발생
        
        # 모든 재시도 실패 시 마지막 예외 발생
        if last_exception:
            raise last_exception


def with_retry(max_retries: int = 3, verbose: bool = True):
    """
    함수에 재시도 로직을 적용하는 데코레이터
    
    Usage:
        @with_retry(max_retries=3)
        def my_api_call():
            return requests.post(...)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return APIRetry.retry_request(
                func, *args,
                max_retries=max_retries,
                verbose=verbose,
                **kwargs
            )
        return wrapper
    return decorator
