"""
Gemini Provider - Google OpenAI 호환 엔드포인트 패스스루
FSD v1.0.052 §4.4.1 / REQ-052-003
FSD v1.0.053 §4.4.1 / REQ-053-006 — tools/tool_calls 패스스루

★ Gemini는 공식 OpenAI 호환 엔드포인트를 제공하므로 변환 없이 패스스루.
★ tools, tool_calls도 OpenAI 호환이므로 그대로 전달.
★ 단, 스트리밍 tool_calls에 index 누락/비표준 필드 → 정규화 처리
"""

import os
import json
import time
import logging
import httpx
from typing import AsyncIterator

from providers.base import BaseProvider, ProviderError, truncate_for_log
from models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatMessage,
    ToolCall,
    FunctionCall,
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
    Tool Call: 패스스루 + 스트리밍 정규화 (REQ-053-006)
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

    def _build_payload(self, request: ChatCompletionRequest, stream: bool = False) -> dict:
        """요청 페이로드 구성 (tools/tool_choice 포함)"""
        messages = []
        for m in request.messages:
            msg = m.model_dump(exclude_none=True)
            messages.append(msg)

        payload = {
            "model": request.model,
            "messages": messages,
            "stream": stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        # ★ Tool Call 패스스루 (REQ-053-006)
        if request.tools:
            payload["tools"] = [t.model_dump() for t in request.tools]
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice

        return payload

    def _parse_response(self, data: dict, model: str) -> ChatCompletionResponse:
        """Gemini 응답 파싱 (tool_calls 포함)"""
        choice_data = data["choices"][0]
        msg_data = choice_data["message"]

        # tool_calls 파싱
        tool_calls = None
        if msg_data.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    type=tc.get("type", "function"),
                    function=FunctionCall(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ),
                )
                for tc in msg_data["tool_calls"]
            ]

        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{int(time.time())}"),
            model=model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(
                        role="assistant",
                        content=msg_data.get("content"),
                        tool_calls=tool_calls,
                    ),
                    finish_reason=choice_data.get("finish_reason", "stop"),
                )
            ],
            usage=Usage(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0),
                total_tokens=data.get("usage", {}).get("total_tokens", 0),
            ),
        )

    def _normalize_stream_chunk(self, chunk_data: dict) -> dict:
        """
        Gemini SSE 청크를 OpenAI 호환 형식으로 정규화.

        AI SDK(OpenCode)는 스트리밍 tool_calls에 다음을 요구:
        - tool_calls[].index (필수, 숫자)
        - extra_content 등 비표준 필드 제거
        """
        for choice in chunk_data.get("choices", []):
            delta = choice.get("delta", {})
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                normalized = []
                for i, tc in enumerate(tool_calls):
                    # ★ index 필드가 없으면 자동 추가
                    if "index" not in tc:
                        tc["index"] = i
                    # ★ 비표준 필드 제거 (extra_content 등)
                    tc.pop("extra_content", None)
                    normalized.append(tc)
                delta["tool_calls"] = normalized
        return chunk_data

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """OpenAI 형식 그대로 Gemini에 전달 (패스스루, 429 재시도 포함)"""
        payload = self._build_payload(request, stream=False)
        logger.info(f"Gemini chat request: model={request.model}")

        resp = await self._retry_on_429(
            lambda: self.client.post("/chat/completions", json=payload)
        )
        data = resp.json()
        logger.info(f"Gemini chat response: {truncate_for_log(data)}")
        return self._parse_response(data, request.model)

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Gemini SSE 스트리밍 (tool_calls 정규화 포함)"""
        payload = self._build_payload(request, stream=True)

        try:
            logger.info(f"Gemini stream request: model={request.model}")
            logger.info(f"Gemini stream request: payload={truncate_for_log(payload)}")

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

                # ★ SSE 청크 정규화 — tool_calls index 추가 + 비표준 필드 제거
                chunk_count = 0
                collected_text = ""
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_count += 1

                        if line.strip() == "data: [DONE]":
                            logger.info(f"Gemini stream chunk[{chunk_count}]: [DONE]")
                            yield line + "\n\n"
                            continue

                        try:
                            chunk_data = json.loads(line[6:])

                            # 텍스트 수집 (요약 로그용)
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            if delta.get("content"):
                                collected_text += delta["content"]

                            # ★ tool_calls 정규화
                            chunk_data = self._normalize_stream_chunk(chunk_data)

                            normalized_line = f"data: {json.dumps(chunk_data)}"
                            logger.info(f"Gemini stream chunk[{chunk_count}]: {truncate_for_log(normalized_line)}")
                            yield normalized_line + "\n\n"

                        except (json.JSONDecodeError, IndexError) as e:
                            # 파싱 실패 시 원본 그대로 전달
                            logger.warning(f"Gemini stream chunk[{chunk_count}] parse error: {e}, passing raw")
                            yield line + "\n\n"

                logger.info(f"Gemini stream completed: {chunk_count} chunks, text={truncate_for_log(collected_text, 200)}")

        except Exception as e:
            logger.error(f"Gemini stream error: {e}")
            yield self._error_chunk(f"Gemini stream error: {str(e)}")
