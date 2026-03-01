"""
Provider 추상 클래스 + 공통 에러 핸들링 유틸리티
FSD v1.0.052 §4.1 - SRS v2 §4.2 BaseProvider
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx

from models import ChatCompletionRequest, ChatCompletionResponse

logger = logging.getLogger("ai-proxy")

# 429 재시도 설정
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # 초 (지수 백오프: 2s, 4s, 8s)

# 로그 출력 기본 최대 길이
DEFAULT_LOG_MAX_LEN = 300


def truncate_for_log(data, max_len: int = DEFAULT_LOG_MAX_LEN) -> str:
    """
    로그 출력용 문자열 변환 + 잘라내기.

    - dict/list → JSON 문자열로 변환
    - 문자열이 max_len보다 짧으면 전체 반환
    - 길면 max_len까지만 반환 + '...(truncated)' 접미사
    """
    if isinstance(data, (dict, list)):
        text = json.dumps(data, ensure_ascii=False)
    else:
        text = str(data)

    if len(text) <= max_len:
        return text
    return text[:max_len] + "...(truncated)"


class ProviderError(Exception):
    """Provider에서 발생하는 에러 (상태 코드 포함)"""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class BaseProvider(ABC):
    """모든 Provider가 구현해야 하는 인터페이스."""

    @abstractmethod
    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        pass

    @abstractmethod
    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        pass

    # ── 공통 유틸리티 ──

    @staticmethod
    async def _retry_on_429(coro_factory, max_retries=MAX_RETRIES):
        """
        429 Too Many Requests 시 지수 백오프로 재시도.

        Args:
            coro_factory: 호출할 코루틴을 반환하는 팩토리 함수 (매번 새 코루틴 생성)
            max_retries: 최대 재시도 횟수

        Returns:
            httpx.Response

        Raises:
            ProviderError: 재시도 후에도 실패 시
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                resp = await coro_factory()
                if resp.status_code == 429 and attempt < max_retries:
                    # Retry-After 헤더 존재 시 해당 시간 사용, 없으면 지수 백오프
                    retry_after = resp.headers.get("retry-after")
                    if retry_after:
                        delay = float(retry_after)
                    else:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"429 Too Many Requests — retry {attempt + 1}/{max_retries} "
                        f"in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    continue

                resp.raise_for_status()
                return resp

            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code

                if status == 429 and attempt < max_retries:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"429 Too Many Requests — retry {attempt + 1}/{max_retries} "
                        f"in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    continue

                # 429 이외의 에러 또는 재시도 소진
                error_body = ""
                try:
                    error_body = e.response.text
                except Exception:
                    pass
                raise ProviderError(
                    f"HTTP {status}: {error_body or str(e)}",
                    status_code=status,
                ) from e

        # 재시도 모두 소진
        raise ProviderError(
            f"Rate limit exceeded after {max_retries} retries: {last_error}",
            status_code=429,
        )

    @staticmethod
    def _error_chunk(message: str) -> str:
        """
        스트리밍 도중 에러 발생 시 SSE 에러 청크를 반환.
        클라이언트가 에러를 인식할 수 있도록 OpenAI 형식으로 래핑.
        """
        error_data = {
            "error": {
                "message": message,
                "type": "proxy_error",
            }
        }
        return f"data: {json.dumps(error_data)}\n\ndata: [DONE]\n\n"
