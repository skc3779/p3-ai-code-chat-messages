"""
GenAI Provider - Samsung SCI Portal (gpt-oss-120B-medium) 형식 변환
FSD v1.0.052 §4.4.3 / REQ-052-005

★ SCI Portal 커스텀 REST API 형식으로 변환
★ 인증: X-Client-Key / X-Client-Secret 헤더
★ 모델: gpt-oss-120B-medium (120B 파라미터, Medium 등급)
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


class GenAIProvider(BaseProvider):
    """
    Samsung SCI Portal - 커스텀 REST API 형식 변환

    변환 로직 (transformRequestBody 역할):
    - model → model_id
    - messages[{role, content}] → prompt[{role, text}]
    - temperature/max_tokens → parameters 객체
    - 인증: X-Client-Key / X-Client-Secret 헤더
    """

    def __init__(self):
        self.base_url = os.getenv(
            "ENDPOINT_URL",
            "https://scisportaldev.samsungif.net/rest/genAi",
        )
        client_key = os.getenv("YOUR_CLIENT_KEY", "API_CLIENT_APP")
        client_secret = os.getenv("YOUR_CLIENT_SECRET", "")

        self.client = httpx.AsyncClient(
            headers={
                "X-Client-Key": client_key,
                "X-Client-Secret": client_secret,
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    def _transform_request(self, request: ChatCompletionRequest) -> dict:
        """
        OpenAI 형식 → SCI Portal 형식 변환
        (@ai-sdk/openai-compatible의 transformRequestBody 역할)
        """
        return {
            "model_id": request.model,  # "gpt-oss-120B-medium"
            "prompt": [
                {"role": m.role, "text": m.content} for m in request.messages
            ],
            "parameters": {
                "temperature": request.temperature if request.temperature is not None else 0.7,
                "max_output_tokens": request.max_tokens or 2048,
            },
        }

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """SCI Portal API 호출 → OpenAI 형식 응답 변환 (429 재시도 포함)"""
        payload = self._transform_request(request)

        resp = await self._retry_on_429(
            lambda: self.client.post(self.base_url, json=payload)
        )
        data = resp.json()

        # SCI Portal 응답 → OpenAI 형식 변환
        content = data.get("response", data.get("text", data.get("result", str(data))))

        usage_data = data.get("usage", {})

        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content=content),
                )
            ],
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """
        SCI Portal 스트리밍 (폴백: 논스트리밍 결과를 SSE로 반환)
        에러 핸들링 포함.
        """
        try:
            result = await self.chat(request)
            content = result.choices[0].message.content

            chunk = {"choices": [{"delta": {"content": content}, "index": 0}]}
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"GenAI stream error: {e}")
            yield self._error_chunk(f"GenAI API error: {str(e)}")
