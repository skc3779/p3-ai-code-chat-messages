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
import anyio  # REQ-111-044: trio/asyncio 백엔드 중립 지원
import logging
import httpx
from typing import Any, AsyncIterator

from model_registry import get_model_max_output
from providers.base import (
    BaseProvider,
    ProviderError,
    _sanitize_log_input,
    _scrub_secrets,
    truncate_for_log,
    should_log_payload,
)
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
    - messages[role=system] → system 파라미터 분리 (다중 system 누적)
    - max_tokens 필수 추가 (모델별 상한 연동)
    - 인증 헤더 변환
    - ★ tools → Anthropic tools 형식 변환
    - ★ tool role → tool_result content block 변환
    - 멀티모달 content_parts 변환 (data URL / 원격 URL)
    - 메시지 시퀀스 정규화 (빈 content 제거, 동일 role 병합, 선두 user 보장, 후행 공백 제거)
    - Prompt Caching 지원 (CLAUDE_PROMPT_CACHE=1)
    """

    # REQ-111-010, REQ-111-048: Provider 지원 파라미터 집합
    SUPPORTED_PARAMS: set[str] = {
        "model",
        "messages",
        "stream",
        "temperature",
        "max_tokens",
        "tools",
        "tool_choice",
        "stream_options",
    }

    # REQ-111-041: Anthropic stop_reason -> OpenAI finish_reason 매핑 테이블
    STOP_REASON_MAP: dict[str, str] = {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "refusal": "stop",
        "pause_turn": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
    }

    BASE_URL = "https://api.anthropic.com"

    @staticmethod
    def _is_prompt_cache_enabled() -> bool:
        """CLAUDE_PROMPT_CACHE=1 환경변수 활성화 여부 확인 (REQ-111-047)."""
        return os.getenv("CLAUDE_PROMPT_CACHE", "0").strip().lower() in ("1", "true", "yes")

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._validate_api_key(api_key, "ANTHROPIC_API_KEY")  # REQ-111-020
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

    # ── 멀티모달 & 정규화 헬퍼 (REQ-111-040, REQ-111-042) ──

    def _transform_content_parts(self, parts: list) -> list[dict]:
        """
        OpenAI 형식의 content parts 리스트를 Anthropic content blocks 로 변환 (REQ-111-042).
        - text 파트: {"type": "text", "text": "..."}
        - image_url (data URL): {"type": "image", "source": {"type": "base64", "media_type": ..., "data": ...}}
        - image_url (remote URL): {"type": "image", "source": {"type": "url", "url": ...}}
        """
        blocks = []
        for part in parts:
            if isinstance(part, str):
                if part.strip():
                    blocks.append({"type": "text", "text": part})
                continue

            if not isinstance(part, dict):
                part_str = str(part)
                if part_str.strip():
                    blocks.append({"type": "text", "text": part_str})
                continue

            part_type = part.get("type", "text")
            if part_type == "text":
                text = part.get("text", "")
                if text:
                    blocks.append({"type": "text", "text": text})
            elif part_type == "image_url":
                img_info = part.get("image_url", {})
                url = img_info.get("url", "") if isinstance(img_info, dict) else str(img_info or "")
                if not url:
                    continue

                if url.startswith("data:"):
                    # data:image/png;base64,xxxx
                    header, _, b64_data = url.partition(",")
                    media_type = "image/jpeg"
                    if ";" in header:
                        mime_part = header.split(";")[0]
                        if mime_part.startswith("data:"):
                            media_type = mime_part[5:].strip()
                    blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    })
                else:
                    blocks.append({
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": url,
                        },
                    })
            elif part_type == "image" and "source" in part:
                blocks.append(part)
            else:
                if "text" in part and part["text"]:
                    blocks.append({"type": "text", "text": part["text"]})
                else:
                    logger.debug("Ignored unrecognized content part type: %s", part_type)

        return blocks

    def _normalize_anthropic_messages(self, raw_messages: list[dict]) -> list[dict]:
        """
        Anthropic Messages API 제약조건에 맞춰 메시지 시퀀스 정규화 (REQ-111-040).
        (a) content 빈 문자열/빈 블록 메시지 제거 (tool_use / tool_result 보유 시 유지)
        (b) 연속 동일 role 메시지 content 블록 병합 (툴 호출 순서 및 매핑 불변 유지)
        (c) 선두가 assistant면 더미 user 메시지 주입
        (d) 마지막이 assistant면(프리필) 허용하되 후행 공백 제거
        """
        def _has_tool_block(content: Any) -> bool:
            if isinstance(content, list):
                return any(
                    isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result")
                    for b in content
                )
            return False

        def _clean_content(content: Any) -> tuple[Any, bool]:
            if content is None:
                return "", True
            if isinstance(content, str):
                return content, (content.strip() == "")
            if isinstance(content, list):
                cleaned_blocks = []
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "text":
                            txt = b.get("text", "")
                            if txt.strip():
                                cleaned_blocks.append(b)
                        else:
                            cleaned_blocks.append(b)
                    elif isinstance(b, str) and b.strip():
                        cleaned_blocks.append({"type": "text", "text": b})
                return cleaned_blocks, (len(cleaned_blocks) == 0)
            return content, False

        # 1. 빈 content 메시지 제거 (단, tool_use/tool_result 보유 메시지는 필수 유지)
        filtered: list[dict] = []
        for idx, m in enumerate(raw_messages):
            role = m.get("role", "user")
            content = m.get("content")
            has_tools = _has_tool_block(content)

            cleaned_content, is_empty = _clean_content(content)
            if is_empty and not has_tools:
                logger.debug(
                    "Dropped empty %s message at index %d (empty content, no tool blocks)",
                    role, idx,
                )
                continue

            filtered.append({"role": role, "content": cleaned_content})

        # 2. 선두가 assistant 면 더미 user 메시지 주입 (Anthropic 제약: 첫 메시지는 user)
        if not filtered:
            logger.debug("All messages were empty; injecting default user message")
            filtered.append({"role": "user", "content": "Hello"})
        elif filtered[0].get("role") != "user":
            logger.debug("Prepended dummy user message because first message had role '%s'", filtered[0].get("role"))
            filtered.insert(0, {"role": "user", "content": "Hello"})

        # 3. 연속 동일 role 메시지의 content 블록 병합
        def _to_blocks(c: Any) -> list[dict]:
            if isinstance(c, str):
                return [{"type": "text", "text": c}] if c else []
            if isinstance(c, list):
                res = []
                for b in c:
                    if isinstance(b, dict):
                        res.append(b)
                    elif isinstance(b, str) and b:
                        res.append({"type": "text", "text": b})
                return res
            return [{"type": "text", "text": str(c)}] if c else []

        merged: list[dict] = []
        for m in filtered:
            role = m["role"]
            content = m["content"]

            if not merged:
                merged.append(m)
                continue

            prev = merged[-1]
            if prev["role"] == role:
                logger.debug("Merged consecutive %s message into previous turn", role)
                prev_content = prev["content"]

                if isinstance(prev_content, str) and isinstance(content, str):
                    prev["content"] = f"{prev_content}\n\n{content}"
                else:
                    prev_blocks = _to_blocks(prev_content)
                    curr_blocks = _to_blocks(content)
                    combined_blocks = []
                    for b in prev_blocks + curr_blocks:
                        if combined_blocks and combined_blocks[-1].get("type") == "text" and b.get("type") == "text":
                            combined_blocks[-1]["text"] = f"{combined_blocks[-1]['text']}\n\n{b['text']}"
                        else:
                            combined_blocks.append(b)
                    prev["content"] = combined_blocks
            else:
                merged.append(m)

        # 4. 마지막이 assistant 면(프리필) 허용하되 후행 공백 제거
        if merged and merged[-1].get("role") == "assistant":
            last_content = merged[-1]["content"]
            if isinstance(last_content, str):
                stripped = last_content.rstrip()
                if stripped != last_content:
                    logger.debug("Stripped trailing whitespace from assistant prefill")
                    merged[-1]["content"] = stripped
                if not stripped:
                    logger.debug("Removed assistant prefill that became empty after rstrip")
                    merged.pop()
            elif isinstance(last_content, list):
                if last_content:
                    last_block = last_content[-1]
                    if isinstance(last_block, dict) and last_block.get("type") == "text":
                        txt = last_block.get("text", "")
                        stripped_txt = txt.rstrip()
                        if stripped_txt != txt:
                            logger.debug("Stripped trailing whitespace from assistant prefill text block")
                            last_block["text"] = stripped_txt
                        if not stripped_txt:
                            last_content.pop()
                if not last_content:
                    logger.debug("Removed assistant prefill that became empty after rstrip")
                    merged.pop()

        if not merged:
            merged.append({"role": "user", "content": "Hello"})

        return merged

    def _transform_messages(self, request: ChatCompletionRequest) -> tuple[str | None, list[dict]]:
        """
        OpenAI messages → Anthropic messages 변환 (다중 system 누적, 멀티모달, 툴 콜, 정규화)
        """
        system_msg = ""
        messages = []

        i = 0
        while i < len(request.messages):
            m = request.messages[i]

            if m.role == "system":
                # REQ-111-049: 다중 system 메시지 누적 (+=)
                s = m.content_as_str()
                if s:
                    if system_msg:
                        system_msg += "\n\n" + s
                    else:
                        system_msg = s

            elif m.role == "assistant" and m.tool_calls:
                content_blocks = []
                if isinstance(m.content, list):
                    content_blocks.extend(self._transform_content_parts(m.content))
                elif isinstance(m.content, str) and m.content:
                    content_blocks.append({"type": "text", "text": m.content})

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
                # tool role → user + tool_result 블록들로 변환
                tool_results = []
                while i < len(request.messages) and request.messages[i].role == "tool":
                    tm = request.messages[i]
                    if isinstance(tm.content, list):
                        tr_content = self._transform_content_parts(tm.content)
                    else:
                        tr_content = tm.content_as_str()

                    tr_block: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": tm.tool_call_id or "",
                        "content": tr_content,
                    }
                    # REQ-111-049: 명시적 is_error 속성이 True인 경우 전달 (휴리스틱 추측은 유예)
                    if getattr(tm, "is_error", None) is True:
                        tr_block["is_error"] = True

                    tool_results.append(tr_block)
                    i += 1

                messages.append({"role": "user", "content": tool_results})
                continue

            else:
                # 일반 user/assistant 메시지
                if isinstance(m.content, list):
                    # REQ-111-042: 멀티모달 패스스루
                    messages.append({
                        "role": m.role,
                        "content": self._transform_content_parts(m.content),
                    })
                else:
                    messages.append({
                        "role": m.role,
                        "content": m.content if m.content is not None else "",
                    })

            i += 1

        final_system = system_msg if system_msg else None
        # REQ-111-040: 메시지 시퀀스 정규화 후처리
        normalized_messages = self._normalize_anthropic_messages(messages)
        return final_system, normalized_messages

    def _transform_request(self, request: ChatCompletionRequest) -> dict:
        """
        OpenAI 형식 → Anthropic Messages API 형식 변환
        (@ai-sdk/openai-compatible의 transformRequestBody 역할)
        """
        system_msg, messages = self._transform_messages(request)

        # REQ-111-045: max_tokens 미지정 시 router 모델 메타데이터 상한 사용
        model_default_tokens = get_model_max_output(request.model, default=4096)
        max_tokens = request.max_tokens or model_default_tokens

        payload: dict = {
            "model": request.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        # REQ-111-047: Prompt Caching 지원 (CLAUDE_PROMPT_CACHE=1)
        prompt_cache_enabled = self._is_prompt_cache_enabled()

        if system_msg:
            if prompt_cache_enabled:
                payload["system"] = [
                    {
                        "type": "text",
                        "text": system_msg,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
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
            # REQ-111-047: Prompt Caching 활성화 시 마지막 tool에 cache_control 부착
            if prompt_cache_enabled and len(tools) > 0:
                tools[-1]["cache_control"] = {"type": "ephemeral"}
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
                            arguments=json.dumps(block.get("input", {})),
                        ),
                    )
                )

        # REQ-111-041: finish_reason 매핑 테이블 적용
        stop_reason = data.get("stop_reason") or "end_turn"
        finish_reason = self.STOP_REASON_MAP.get(stop_reason, "stop")

        # REQ-111-047: Prompt Caching 캐시 토큰 사용량 합산 반영
        usage_data = data.get("usage", {})
        input_tokens = usage_data.get("input_tokens", 0)
        cache_creation_input_tokens = usage_data.get("cache_creation_input_tokens", 0)
        cache_read_input_tokens = usage_data.get("cache_read_input_tokens", 0)
        prompt_tokens = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
        completion_tokens = usage_data.get("output_tokens", 0)

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
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )


    # ── API 호출 ──

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Claude Messages API 호출 → OpenAI 형식 응답 변환 (429 재시도 포함)"""
        self._warn_unsupported(request, self.SUPPORTED_PARAMS)  # REQ-111-010
        self._warn_name_if_present(request)  # REQ-111-035
        payload = self._transform_request(request)
        logger.info(f"Claude chat request: model={_sanitize_log_input(request.model, max_len=100)}")

        resp = await self._retry_on_429(
            lambda: self.client.post("/v1/messages", json=payload)
        )
        data = resp.json()
        if self.should_log_payload():
            logger.info(f"Claude chat response: {_scrub_secrets(truncate_for_log(data, 500))}")
        return self._parse_response(data, request.model)

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Claude 스트리밍 → OpenAI SSE 형식 변환 (tool_calls 델타, 에러 복구, 재시도 포함) (REQ-111-020, REQ-111-026, REQ-111-030~035, REQ-111-041~048)"""
        self._warn_unsupported(request, self.SUPPORTED_PARAMS)  # REQ-111-010
        self._warn_name_if_present(request)  # REQ-111-035
        include_usage = bool(request.stream_options and request.stream_options.include_usage)  # REQ-111-033, REQ-111-048
        payload = self._transform_request(request)
        payload["stream"] = True

        logger.info(f"Claude stream request: model={_sanitize_log_input(request.model, max_len=100)}")
        if self.should_log_payload():
            logger.info(f"Claude stream request: payload={_scrub_secrets(truncate_for_log(payload))}")

        # REQ-111-044: 첫 바이트 수신 전 429/500/529 지수 백오프 재시도 (최대 3회)
        max_retries = 3
        retry_base_delay = float(os.getenv("RETRY_BASE_DELAY", "0.5"))
        resp: httpx.Response | None = None

        for attempt in range(max_retries + 1):
            req = self.client.build_request("POST", "/v1/messages", json=payload)
            try:
                resp = await self.client.send(req, stream=True)
            except (httpx.ConnectError, httpx.ConnectTimeout) as conn_err:
                if attempt < max_retries:
                    delay = retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "Claude stream connection error (%s) — retry %d/%d in %.1fs",
                        conn_err, attempt + 1, max_retries, delay,
                    )
                    await anyio.sleep(delay)  # REQ-111-044: trio/asyncio 백엔드 중립 슬립
                    continue
                logger.error("Claude stream connection failed after %d retries: %s", max_retries, conn_err)
                yield self._error_chunk("Failed to connect to Claude API", code="proxy_error")
                return

            if resp.status_code in (429, 500, 529):
                err_body = await resp.aread()
                await resp.aclose()
                if attempt < max_retries:
                    retry_after = resp.headers.get("retry-after")
                    delay = retry_base_delay * (2 ** attempt)
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            pass
                    # REQ-111-014, REQ-111-020, REQ-111-044: 로깅 정책 게이팅 및 자격증명 스크러빙
                    if self.should_log_payload():
                        logger.warning(
                            "Claude stream HTTP %d — retry %d/%d in %.1fs (body=%s)",
                            resp.status_code, attempt + 1, max_retries, delay,
                            _scrub_secrets(err_body.decode(errors="replace")[:200]),
                        )
                    else:
                        logger.warning(
                            "Claude stream HTTP %d — retry %d/%d in %.1fs",
                            resp.status_code, attempt + 1, max_retries, delay,
                        )
                    await anyio.sleep(delay)  # REQ-111-044: trio/asyncio 백엔드 중립 슬립
                    continue

                # 재시도 소진
                logger.error(
                    "Claude stream HTTP %d after %d retries: %s",
                    resp.status_code, max_retries, _scrub_secrets(err_body.decode(errors="replace")),
                )
                if resp.status_code == 429:
                    yield self._error_chunk("Rate limit exceeded (429). Please wait and try again.", code="rate_limit_error")
                elif resp.status_code == 529:
                    yield self._error_chunk("Claude API overloaded (529). Please wait and try again.", code="overloaded_error")
                else:
                    yield self._error_chunk(f"Claude API error (HTTP {resp.status_code})", code="proxy_error")
                return

            if resp.status_code != 200:
                # 429/500/529 외 에러는 즉시 실패 처리
                err_body = await resp.aread()
                await resp.aclose()
                logger.error(
                    "Claude stream HTTP %d: %s",
                    resp.status_code, _scrub_secrets(err_body.decode(errors="replace")),
                )
                yield self._error_chunk(f"Claude API error (HTTP {resp.status_code})", code="proxy_error")
                return

            # 200 OK — 스트리밍 시작
            break

        if resp is None:
            yield self._error_chunk("Claude API response missing", code="proxy_error")
            return

        # ── 스트림 청크 수신 및 OpenAI SSE 변환 ──
        try:
            # REQ-111-030: 스트림 생명주기 동안 동일한 chunk_id 유지
            stream_id = self._new_stream_id()
            finish_reason_emitted = False
            prompt_tokens = 0
            completion_tokens = 0

            # 스트리밍 tool_calls 변환 상태
            current_tool_index = -1
            chunk_count = 0
            collected_text = ""

            # REQ-111-031: 스트림 시작 시 delta={"role": "assistant"} 청크 정확히 1회 방출
            chunk_count += 1
            role_chunk = self._chunk(
                chunk_id=stream_id,
                model=request.model,
                delta={"role": "assistant"},
            )
            if self.should_log_chunk():
                logger.info(f"Claude stream chunk[{chunk_count}]: role=assistant")
            yield role_chunk

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue

                try:
                    raw = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                event_type = raw.get("type", "")

                # REQ-111-043: 스트림 도중 error 이벤트 수신 시 에러 청크 방출 후 종료
                if event_type == "error":
                    err_obj = raw.get("error", {})
                    err_msg = err_obj.get("message", "Anthropic stream error")
                    err_type = err_obj.get("type", "upstream_error")
                    logger.error(
                        "Claude stream in-band error event: %s (%s)",
                        _scrub_secrets(err_msg), err_type,
                    )
                    yield self._error_chunk(f"Claude stream error: {err_msg}", code="proxy_error")
                    return

                if event_type == "message_start":
                    msg_obj = raw.get("message", {})
                    usage_obj = msg_obj.get("usage", {})
                    # REQ-111-047: Prompt Caching 캐시 토큰 합산
                    p_tok = usage_obj.get("input_tokens", 0)
                    c_create = usage_obj.get("cache_creation_input_tokens", 0)
                    c_read = usage_obj.get("cache_read_input_tokens", 0)
                    prompt_tokens = p_tok + c_create + c_read

                elif event_type == "content_block_start":
                    block = raw.get("content_block", {})
                    if block.get("type") == "tool_use":
                        # tool_calls 시작 — id, name 전송
                        current_tool_index += 1
                        tool_call_id = block.get("id", "")
                        tool_name = block.get("name", "")

                        chunk_count += 1
                        tool_delta = {
                            "tool_calls": [{
                                "index": current_tool_index,
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": "",
                                },
                            }]
                        }
                        chunk_str = self._chunk(
                            chunk_id=stream_id,
                            model=request.model,
                            delta=tool_delta,
                        )
                        if self.should_log_chunk():
                            logger.info(f"Claude stream chunk[{chunk_count}]: tool_use start id={tool_call_id}, name={tool_name}")
                        yield chunk_str

                elif event_type == "content_block_delta":
                    delta = raw.get("delta", {})

                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            collected_text += text
                            chunk_count += 1
                            chunk_str = self._chunk(
                                chunk_id=stream_id,
                                model=request.model,
                                delta={"content": text},
                            )
                            if self.should_log_chunk():
                                logger.info(f"Claude stream chunk[{chunk_count}]: text_delta len={len(text)}, text={_scrub_secrets(truncate_for_log(text, 100))}")
                            yield chunk_str

                    elif delta.get("type") == "input_json_delta":
                        # tool_calls arguments 델타
                        partial_json = delta.get("partial_json", "")
                        if partial_json:
                            chunk_count += 1
                            tool_delta = {
                                "tool_calls": [{
                                    "index": current_tool_index,
                                    "function": {
                                        "arguments": partial_json,
                                    },
                                }]
                            }
                            chunk_str = self._chunk(
                                chunk_id=stream_id,
                                model=request.model,
                                delta=tool_delta,
                            )
                            if self.should_log_chunk():
                                logger.info(f"Claude stream chunk[{chunk_count}]: input_json_delta len={len(partial_json)}")
                            yield chunk_str

                elif event_type == "content_block_stop":
                    # REQ-111-044: content_block_stop 명시적 수신
                    pass

                elif event_type == "message_delta":
                    # REQ-111-041: finish_reason 매핑 테이블 적용
                    stop_reason = raw.get("delta", {}).get("stop_reason")
                    if stop_reason:
                        finish_reason = self.STOP_REASON_MAP.get(stop_reason, "stop")
                    else:
                        finish_reason = "stop"

                    if "usage" in raw and "output_tokens" in raw["usage"]:
                        completion_tokens = raw["usage"].get("output_tokens", 0)

                    chunk_count += 1
                    chunk_str = self._chunk(
                        chunk_id=stream_id,
                        model=request.model,
                        delta={},
                        finish_reason=finish_reason,
                    )
                    finish_reason_emitted = True
                    if self.should_log_chunk():
                        logger.info(f"Claude stream chunk[{chunk_count}]: finish_reason={finish_reason}")
                    yield chunk_str

                elif event_type == "message_stop":
                    # REQ-111-044: message_stop 수신
                    pass

            # REQ-111-032: 업스트림이 finish_reason 없이 종료된 경우 프록시가 보정 방출
            if not finish_reason_emitted:
                chunk_count += 1
                fr_chunk = self._chunk(
                    chunk_id=stream_id,
                    model=request.model,
                    delta={},
                    finish_reason="stop",
                )
                finish_reason_emitted = True
                if self.should_log_chunk():
                    logger.info(f"Claude stream chunk[{chunk_count}]: compensated finish_reason=stop")
                yield fr_chunk

            # REQ-111-033, REQ-111-048: include_usage=True 일 때 [DONE] 직전 usage 청크 방출
            if include_usage:
                chunk_count += 1
                if prompt_tokens == 0 and completion_tokens == 0:
                    logger.debug("Claude upstream stream provided no usage data; filling 0 for include_usage")
                usage_dict = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                }
                usage_chunk = self._chunk(
                    chunk_id=stream_id,
                    model=request.model,
                    delta={},
                    usage=usage_dict,
                )
                if self.should_log_chunk():
                    logger.info(f"Claude stream chunk[{chunk_count}]: usage={usage_dict}")
                yield usage_chunk

            if self.should_log_payload():
                logger.info(f"Claude stream completed: {chunk_count} chunks, text={_scrub_secrets(truncate_for_log(collected_text, 200))}")
            else:
                logger.info(f"Claude stream completed: {chunk_count} chunks")

        except Exception as e:
            # 이미 바이트를 방출한 후 발생한 예외이므로 재시도하지 않고 에러 청크 방출 (REQ-111-044)
            logger.error("Claude stream runtime error: %s", _scrub_secrets(str(e)))
            yield self._error_chunk("Claude stream processing error", code="proxy_error")
            return
        finally:
            if resp is not None:
                await resp.aclose()

        yield "data: [DONE]\n\n"

