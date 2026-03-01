"""
Gemini Provider - Google OpenAI 호환 엔드포인트 패스스루
FSD v1.0.052 §4.4.1 / REQ-052-003

★ Gemini는 공식 OpenAI 호환 엔드포인트를 제공하므로 변환 없이 패스스루.
★ baseURL 끝에 /openai/ 필수!
"""

import os
import json
import time
import logging
import httpx
from typing import AsyncIterator

from providers.base import BaseProvider, ProviderError
from models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatMessage,
    Usage,
)

logger = logging.getLogger("ai-proxy")

# Gemini OpenAI 호환 Base URL (끝에 /openai 필수)
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class GeminiProvider(BaseProvider):
    """
    Google Gemini - 공식 OpenAI 호환 엔드포인트 패스스루

    변환 로직: 없음 (패스스루)
    인증: Authorization: Bearer <GEMINI_API_KEY>
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "")
        self.client = httpx.AsyncClient(
            base_url=GEMINI_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """OpenAI 형식 그대로 Gemini에 전달 (패스스루, 429 재시도 포함)"""
        payload = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        resp = await self._retry_on_429(
            lambda: self.client.post("/chat/completions", json=payload)
        )
        data = resp.json()

        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{int(time.time())}"),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(
                        role="assistant",
                        content=data["choices"][0]["message"]["content"],
                    ),
                )
            ],
            usage=Usage(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                total_tokens=data.get("usage", {}).get("total_tokens", 0),
            ),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Gemini SSE 스트리밍 패스스루 (에러 핸들링 포함)"""
        payload = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": True,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        try:
            async with self.client.stream(
                "POST", "/chat/completions", json=payload
            ) as resp:
                if resp.status_code == 429:
                    error_body = await resp.aread()
                    logger.error(f"Gemini 429: {error_body.decode()}")
                    yield self._error_chunk(
                        "Rate limit exceeded (429). Please wait and try again."
                    )
                    return

                if resp.status_code != 200:
                    error_body = await resp.aread()
                    logger.error(f"Gemini HTTP {resp.status_code}: {error_body.decode()}")
                    yield self._error_chunk(
                        f"Gemini API error (HTTP {resp.status_code})"
                    )
                    return

                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line + "\n\n"

        except Exception as e:
            logger.error(f"Gemini stream error: {e}")
            yield self._error_chunk(f"Gemini stream error: {str(e)}")
