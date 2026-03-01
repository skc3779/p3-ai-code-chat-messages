"""
Claude Provider - Anthropic Messages API ↔ OpenAI 형식 변환
FSD v1.0.052 §4.4.2 / REQ-052-004

★ Claude는 OpenAI 호환 엔드포인트를 제공하지 않음
★ 핵심 변환:
  - system 메시지 → 별도 파라미터
  - max_tokens 필수 (미지정 시 기본값 4096 추가)
  - 인증: x-api-key + anthropic-version
  - 응답: content[0].text → choices[0].message.content
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


class ClaudeProvider(BaseProvider):
    """
    Anthropic Claude - /v1/messages 형식을 OpenAI 형식으로 변환

    변환 로직 (transformRequestBody 역할):
    - messages[role=system] → system 파라미터 분리
    - max_tokens 필수 추가
    - 인증 헤더 변환
    """

    BASE_URL = "https://api.anthropic.com"

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    def _transform_request(self, request: ChatCompletionRequest) -> dict:
        """
        OpenAI 형식 → Anthropic Messages API 형식 변환
        (@ai-sdk/openai-compatible의 transformRequestBody 역할)
        """
        system_msg = None
        messages = []

        for m in request.messages:
            if m.role == "system":
                system_msg = m.content
            else:
                messages.append({"role": m.role, "content": m.content})

        payload: dict = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,  # ★ Claude 필수!
        }

        if system_msg:
            payload["system"] = system_msg
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        return payload

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Claude Messages API 호출 → OpenAI 형식 응답 변환 (429 재시도 포함)"""
        payload = self._transform_request(request)

        # 429 재시도 로직 적용
        resp = await self._retry_on_429(
            lambda: self.client.post("/v1/messages", json=payload)
        )
        data = resp.json()

        # Anthropic 응답 → OpenAI 응답 변환
        content = ""
        if data.get("content"):
            content = data["content"][0].get("text", "")

        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{int(time.time())}"),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content=content),
                )
            ],
            usage=Usage(
                prompt_tokens=data.get("usage", {}).get("input_tokens", 0),
                completion_tokens=data.get("usage", {}).get("output_tokens", 0),
                total_tokens=(
                    data.get("usage", {}).get("input_tokens", 0)
                    + data.get("usage", {}).get("output_tokens", 0)
                ),
            ),
        )

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Claude 스트리밍 → OpenAI SSE 형식 변환 (에러 핸들링 포함)"""
        payload = self._transform_request(request)
        payload["stream"] = True

        try:
            logger.info(f"Claude stream request: {payload}")    
            
            async with self.client.stream(
                "POST", "/v1/messages", json=payload
            ) as resp:
                # ★ 스트리밍 응답 시작 전에 상태 코드 확인
                if resp.status_code == 429:
                    error_body = await resp.aread()
                    logger.error(f"Claude 429 Too Many Requests: {error_body.decode()}")
                    yield self._error_chunk(
                        "Rate limit exceeded (429). Please wait and try again."
                    )
                    return

                if resp.status_code != 200:
                    error_body = await resp.aread()
                    logger.error(f"Claude HTTP {resp.status_code}: {error_body.decode()}")
                    yield self._error_chunk(
                        f"Claude API error (HTTP {resp.status_code})"
                    )
                    return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    try:
                        raw = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    # content_block_delta 이벤트에서 텍스트 추출
                    if raw.get("type") == "content_block_delta":
                        text = raw.get("delta", {}).get("text", "")
                        if text:
                            chunk = {
                                "choices": [
                                    {"delta": {"content": text}, "index": 0}
                                ]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"

        except httpx.HTTPStatusError as e:
            logger.error(f"Claude stream HTTP error: {e}")
            yield self._error_chunk(f"Claude API error: {e.response.status_code}")
            return
        except Exception as e:
            logger.error(f"Claude stream error: {e}")
            yield self._error_chunk(f"Claude stream error: {str(e)}")
            return

        yield "data: [DONE]\n\n"
