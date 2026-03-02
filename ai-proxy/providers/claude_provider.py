"""
Claude Provider - Anthropic Messages API ↔ OpenAI 형식 변환
FSD v1.0.052 §4.4.2 / REQ-052-004
FSD v1.0.053 §4.4.2 / REQ-053-007 — Tool Use ↔ OpenAI Tool Call 변환

★ Claude는 OpenAI 호환 엔드포인트를 제공하지 않음
★ 핵심 변환:
  - system 메시지 → 별도 파라미터
  - max_tokens 필수 (미지정 시 기본값 4096 추가)
  - 인증: x-api-key + anthropic-version
  - 응답: content[0].text → choices[0].message.content
  - ★ tools: OpenAI function → Anthropic tools 변환
  - ★ tool_calls: Anthropic tool_use → OpenAI tool_calls 변환
  - ★ tool results: OpenAI tool role → Anthropic tool_result 변환
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


class ClaudeProvider(BaseProvider):
    """
    Anthropic Claude - /v1/messages 형식을 OpenAI 형식으로 변환

    변환 로직 (transformRequestBody 역할):
    - messages[role=system] → system 파라미터 분리
    - max_tokens 필수 추가
    - 인증 헤더 변환
    - ★ tools → Anthropic tools 형식 변환
    - ★ tool role → tool_result content block 변환
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

    # ── 요청 변환 ──

    def _transform_tools(self, request: ChatCompletionRequest) -> list[dict] | None:
        """
        OpenAI tools → Anthropic tools 변환
        OpenAI:     [{type:"function", function:{name, description, parameters}}]
        Anthropic:  [{name, description, input_schema}]
        """
        if not request.tools:
            return None

        anthropic_tools = []
        for tool in request.tools:
            anthropic_tools.append({
                "name": tool.function.name,
                "description": tool.function.description or "",
                "input_schema": tool.function.parameters or {"type": "object", "properties": {}},
            })
        return anthropic_tools

    def _transform_tool_choice(self, tool_choice) -> dict | None:
        """
        OpenAI tool_choice → Anthropic tool_choice 변환
        "auto"                      → {"type": "auto"}
        "none"                      → None (tools를 제거)
        "required"                  → {"type": "any"}
        {"function":{"name":"x"}}   → {"type": "tool", "name": "x"}
        """
        if tool_choice is None:
            return None
        if tool_choice == "auto":
            return {"type": "auto"}
        if tool_choice == "none":
            return None  # 호출자에서 tools도 제거
        if tool_choice == "required":
            return {"type": "any"}
        if isinstance(tool_choice, dict):
            func = tool_choice.get("function", {})
            return {"type": "tool", "name": func.get("name", "")}
        return None

    def _transform_messages(self, request: ChatCompletionRequest) -> tuple[str | None, list[dict]]:
        """
        OpenAI messages → Anthropic messages 변환 (tool role 포함)
        
        변환 규칙:
        - role=system → system 파라미터로 분리
        - role=assistant + tool_calls → content에 tool_use 블록 추가
        - role=tool → role=user + content[{type:tool_result}]로 변환
        """
        system_msg = None
        messages = []

        i = 0
        while i < len(request.messages):
            m = request.messages[i]

            if m.role == "system":
                system_msg = m.content_as_str()  # BUG-057: content_as_str() 사용

            elif m.role == "assistant" and m.tool_calls:
                # assistant + tool_calls → Anthropic content blocks
                content_blocks = []

                # 텍스트가 있으면 text 블록 추가
                if m.content_as_str():  # BUG-057
                    content_blocks.append({"type": "text", "text": m.content_as_str()})

                # tool_calls → tool_use 블록 변환
                for tc in m.tool_calls:
                    try:
                        input_data = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        input_data = {}

                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": input_data,
                    })

                messages.append({"role": "assistant", "content": content_blocks})

            elif m.role == "tool":
                # tool role → user + tool_result 블록
                # 연속된 tool 메시지들을 하나의 user 메시지로 묶기
                tool_results = []
                while i < len(request.messages) and request.messages[i].role == "tool":
                    tm = request.messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tm.tool_call_id or "",
                        "content": tm.content_as_str(),  # BUG-057
                    })
                    i += 1
                messages.append({"role": "user", "content": tool_results})
                continue  # i는 이미 증가됨

            else:
                # 일반 user/assistant 메시지
                messages.append({"role": m.role, "content": m.content_as_str()})  # BUG-057

            i += 1

        return system_msg, messages

    def _transform_request(self, request: ChatCompletionRequest) -> dict:
        """
        OpenAI 형식 → Anthropic Messages API 형식 변환
        (@ai-sdk/openai-compatible의 transformRequestBody 역할)
        """
        system_msg, messages = self._transform_messages(request)

        payload: dict = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,  # ★ Claude 필수!
        }

        if system_msg:
            payload["system"] = system_msg
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        # ★ Tool Call 변환 (REQ-053-007)
        tools = self._transform_tools(request)
        tool_choice = self._transform_tool_choice(
            request.tool_choice
        ) if request.tools else None

        # tool_choice="none" 이면 tools 자체를 보내지 않음
        if request.tool_choice != "none" and tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        return payload

    # ── 응답 변환 ──

    def _parse_response(self, data: dict, model: str) -> ChatCompletionResponse:
        """
        Anthropic 응답 → OpenAI 응답 변환 (tool_use → tool_calls 포함)
        """
        content_text = ""
        tool_calls = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                content_text += block.get("text", "")
            elif block.get("type") == "tool_use":
                # ★ Anthropic tool_use → OpenAI tool_calls
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        type="function",
                        function=FunctionCall(
                            name=block["name"],
                            # ★ arguments는 JSON 문자열로 변환
                            arguments=json.dumps(block.get("input", {})),
                        ),
                    )
                )

        # finish_reason 변환: tool_use → tool_calls
        stop_reason = data.get("stop_reason", "end_turn")
        if stop_reason == "tool_use":
            finish_reason = "tool_calls"
        elif stop_reason == "end_turn":
            finish_reason = "stop"
        else:
            finish_reason = stop_reason

        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{int(time.time())}"),
            model=model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(
                        role="assistant",
                        content=content_text or None,
                        tool_calls=tool_calls if tool_calls else None,
                    ),
                    finish_reason=finish_reason,
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

    # ── API 호출 ──

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Claude Messages API 호출 → OpenAI 형식 응답 변환 (429 재시도 포함)"""
        payload = self._transform_request(request)
        logger.info(f"Claude chat request: model={request.model}")

        resp = await self._retry_on_429(
            lambda: self.client.post("/v1/messages", json=payload)
        )
        data = resp.json()
        logger.info(f"Claude chat response: {truncate_for_log(data, 500)}")
        return self._parse_response(data, request.model)

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Claude 스트리밍 → OpenAI SSE 형식 변환 (tool_calls 델타 포함)"""
        payload = self._transform_request(request)
        payload["stream"] = True

        try:
            logger.info(f"Claude stream request: model={request.model}")
            logger.info(f"Claude stream request: payload={truncate_for_log(payload)}")

            async with self.client.stream(
                "POST", "/v1/messages", json=payload
            ) as resp:
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

                # ★ 스트리밍 tool_calls 변환 상태
                current_tool_index = -1
                tool_call_id = None
                tool_name = None
                chunk_count = 0
                collected_text = ""

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    try:
                        raw = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    event_type = raw.get("type", "")

                    # 텍스트 델타
                    if event_type == "content_block_delta":
                        delta = raw.get("delta", {})

                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                collected_text += text
                                chunk_count += 1
                                chunk = {
                                    "choices": [
                                        {"delta": {"content": text}, "index": 0}
                                    ]
                                }
                                logger.info(f"Claude stream chunk[{chunk_count}]: text_delta len={len(text)}, text={truncate_for_log(text, 100)}")
                                yield f"data: {json.dumps(chunk)}\n\n"

                        elif delta.get("type") == "input_json_delta":
                            # ★ tool_calls arguments 델타
                            partial_json = delta.get("partial_json", "")
                            if partial_json:
                                chunk = {
                                    "choices": [{
                                        "delta": {
                                            "tool_calls": [{
                                                "index": current_tool_index,
                                                "function": {
                                                    "arguments": partial_json
                                                }
                                            }]
                                        },
                                        "index": 0
                                    }]
                                }
                                logger.info(f"Claude stream chunk: input_json_delta len={len(partial_json)}")
                                yield f"data: {json.dumps(chunk)}\n\n"

                    elif event_type == "content_block_start":
                        block = raw.get("content_block", {})
                        if block.get("type") == "tool_use":
                            # ★ tool_calls 시작 — id, name 전송
                            current_tool_index += 1
                            tool_call_id = block.get("id", "")
                            tool_name = block.get("name", "")

                            chunk = {
                                "choices": [{
                                    "delta": {
                                        "tool_calls": [{
                                            "index": current_tool_index,
                                            "id": tool_call_id,
                                            "type": "function",
                                            "function": {
                                                "name": tool_name,
                                                "arguments": ""
                                            }
                                        }]
                                    },
                                    "index": 0
                                }]
                            }
                            logger.info(f"Claude stream: tool_use start id={tool_call_id}, name={tool_name}")
                            yield f"data: {json.dumps(chunk)}\n\n"

                    elif event_type == "message_delta":
                        # ★ finish_reason 전송
                        stop_reason = raw.get("delta", {}).get("stop_reason", "")
                        if stop_reason == "tool_use":
                            finish_reason = "tool_calls"
                        elif stop_reason == "end_turn":
                            finish_reason = "stop"
                        else:
                            finish_reason = stop_reason or "stop"

                        chunk = {
                            "choices": [{
                                "delta": {},
                                "finish_reason": finish_reason,
                                "index": 0
                            }]
                        }
                        logger.info(f"Claude stream: finish_reason={finish_reason}")
                        yield f"data: {json.dumps(chunk)}\n\n"

                logger.info(f"Claude stream completed: {chunk_count} chunks, text={truncate_for_log(collected_text, 200)}")

        except httpx.HTTPStatusError as e:
            logger.error(f"Claude stream HTTP error: {e}")
            yield self._error_chunk(f"Claude API error: {e.response.status_code}")
            return
        except Exception as e:
            logger.error(f"Claude stream error: {e}")
            yield self._error_chunk(f"Claude stream error: {str(e)}")
            return

        yield "data: [DONE]\n\n"
