"""
Gemini Provider - Google OpenAI 호환 엔드포인트 패스스루
FSD v1.0.052 §4.4.1 / REQ-052-003
FSD v1.0.053 §4.4.1 / REQ-053-006 — tools/tool_calls 패스스루
TASK-GEMINI-1 (v1.1.111) — REQ-111-040 ~ REQ-111-047

★ Gemini는 공식 OpenAI 호환 엔드포인트를 제공하므로 원칙적으로 패스스루.
★ 스트리밍 tool_calls의 index 누적 카운터 부여 및 동시성 격리 (REQ-111-040).
★ 비스트리밍 빈 choices 및 200 에러 바디 방어 (REQ-111-041).
★ 진짜 패스스루 모드 GEMINI_PASSTHROUGH=1 지원 (REQ-111-042).
★ finish_reason 화이트리스트 매핑 (REQ-111-043).
★ 업스트림 created 타임스탬프 보존 (REQ-111-044).
★ tools 직렬화 exclude_none=True 정합화 (REQ-111-045).
★ 스트리밍 첫 바이트 전 429/500/503 지수 백오프 재시도 (REQ-111-046).
★ LOG_CHUNK 게이팅 및 스트림 종료 요약 로그 (REQ-111-047).
"""

import json
import logging
import os
import time
from typing import Any, AsyncIterator

import anyio
import httpx

from models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    FunctionCall,
    ToolCall,
    Usage,
)
from providers.base import (
    BaseProvider,
    ProviderError,
    _sanitize_log_input,
    _scrub_secrets,
    truncate_for_log,
)

logger = logging.getLogger("ai-proxy")

# Gemini OpenAI 호환 Base URL (끝에 /openai 필수)
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

# REQ-111-043: OpenAI 규격 finish_reason 화이트리스트 및 Gemini 고유 상태 매핑 테이블
ALLOWED_FINISH_REASONS: set[str] = {
    "stop",
    "length",
    "tool_calls",
    "content_filter",
    "function_call",
}

GEMINI_FINISH_REASON_MAP: dict[str, str] = {
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "MAX_TOKENS": "length",
    "STOP": "stop",
    "OTHER": "stop",
}


def _map_finish_reason(fr: str | None) -> str | None:
    """Gemini finish_reason을 OpenAI 규격 화이트리스트 값으로 정규화 (REQ-111-043)."""
    if fr is None:
        return None
    if fr in ALLOWED_FINISH_REASONS:
        return fr
    upper = fr.upper()
    if upper in GEMINI_FINISH_REASON_MAP:
        return GEMINI_FINISH_REASON_MAP[upper]
    lower = fr.lower()
    if lower in ALLOWED_FINISH_REASONS:
        return lower
    return "stop"


class PassthroughResponse(dict):
    """
    GEMINI_PASSTHROUGH=1 일 때 반환되는 무손실 응답 딕셔너리 객체 (REQ-111-042).

    - 업스트림 원본 dict의 모든 필드(choices[1..n], logprobs, refusal, annotations 등)를 보존
    - .model 속성 접근(getter/setter)을 지원하여 proxy_server의 모델 ID 덮어쓰기 및 FastAPI 직렬화 호환성 보장
    """

    @property
    def model(self) -> str:
        return self.get("model", "")

    @model.setter
    def model(self, value: str) -> None:
        self["model"] = value


class GeminiProvider(BaseProvider):
    """
    Google Gemini - 공식 OpenAI 호환 엔드포인트 패스스루

    변환 로직: 없음 (패스스루)
    인증: Authorization: Bearer <GEMINI_API_KEY>
    Tool Call: 패스스루 + 스트리밍 정규화 (REQ-053-006)
    """

    # REQ-111-010: Provider 지원 파라미터 집합 (GEMINI_v1.1.111 §2.1 기준)
    SUPPORTED_PARAMS: set[str] = {
        "model",
        "messages",
        "stream",
        "temperature",
        "max_tokens",
        "tools",
        "tool_choice",
    }

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY", "")
        self._validate_api_key(api_key, "GEMINI_API_KEY")  # REQ-111-020
        self.client = httpx.AsyncClient(
            base_url=GEMINI_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    def _build_payload(self, request: ChatCompletionRequest, stream: bool = False) -> dict:
        """요청 페이로드 구성 (tools/tool_choice 포함) (REQ-111-045: tools exclude_none=True)"""
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

        # ★ Tool Call 패스스루 (REQ-053-006, REQ-111-045: exclude_none=True 적용)
        if request.tools:
            payload["tools"] = [t.model_dump(exclude_none=True) for t in request.tools]
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice

        return payload

    def _parse_response(self, data: dict, model: str) -> ChatCompletionResponse:
        """Gemini 응답 파싱 (REQ-111-041: 빈 choices/200 에러 바디 방어, REQ-111-043: finish_reason 매핑, REQ-111-044: created 보존)"""
        # REQ-111-041: 업스트림이 200 상태코드에 error 키를 담아 응답한 경우 검출
        error_info = data.get("error")
        if error_info:
            err_msg = error_info.get("message") if isinstance(error_info, dict) else str(error_info)
            raise ProviderError(
                f"Gemini returned error in response body: {_scrub_secrets(err_msg)}",
                status_code=502,
                public_message="Gemini returned error in response body",
            )

        # REQ-111-041: choices 빈 배열 또는 키 부재 방어
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(
                f"Gemini returned no choices: {_scrub_secrets(json.dumps(data))[:500]}",
                status_code=502,
                public_message="Gemini returned no choices (possibly blocked by safety filter)",
            )

        choice_data = choices[0]
        msg_data = choice_data.get("message") or {}

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

        # REQ-111-043: finish_reason 화이트리스트 정규화
        raw_finish_reason = choice_data.get("finish_reason") or "stop"
        finish_reason = _map_finish_reason(raw_finish_reason) or "stop"

        response_kwargs: dict[str, Any] = {
            "id": data.get("id", f"chatcmpl-{int(time.time())}"),
            "model": model,
            "choices": [
                ChatCompletionChoice(
                    message=ChatMessage(
                        role="assistant",
                        content=msg_data.get("content"),
                        tool_calls=tool_calls,
                    ),
                    finish_reason=finish_reason,
                )
            ],
            "usage": Usage(
                prompt_tokens=data.get("usage", {}).get("prompt_tokens", 0) or 0,
                completion_tokens=data.get("usage", {}).get("completion_tokens", 0) or 0,
                total_tokens=data.get("usage", {}).get("total_tokens", 0) or 0,
            ),
        }

        # REQ-111-044: 업스트림 created 보존 (없을 때만 모델 기본 factory 사용)
        if "created" in data and data["created"] is not None:
            response_kwargs["created"] = data["created"]

        return ChatCompletionResponse(**response_kwargs)

    def _normalize_stream_chunk(
        self,
        chunk_data: dict,
        seen_tool_ids: dict[str, int] | None = None,
        next_index_ref: list[int] | None = None,
    ) -> dict:
        """
        Gemini SSE 청크를 OpenAI 호환 형식으로 정규화 (REQ-111-040).

        - tool_calls[].index 를 스트림 전체 누적 카운터로 부여
        - 업스트림이 이미 제공한 index 는 신뢰하고 보존
        - 동일 tool_call id 에 대해 여러 청크에 걸친 arguments 델타가 오더라도 동일 index 유지
        - id 가 없으면 도착 순서대로 새 index 부여
        - extra_content 등 비표준 필드 제거
        """
        if seen_tool_ids is None:
            seen_tool_ids = {}
        if next_index_ref is None:
            next_index_ref = [0]

        for choice in chunk_data.get("choices", []):
            delta = choice.get("delta", {})
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                normalized = []
                for tc in tool_calls:
                    if "index" in tc:
                        # 업스트림이 명시한 index 보존 및 상태 추적
                        tc_id = tc.get("id")
                        if tc_id:
                            seen_tool_ids[tc_id] = tc["index"]
                        if next_index_ref[0] <= tc["index"]:
                            next_index_ref[0] = tc["index"] + 1
                    else:
                        tc_id = tc.get("id")
                        if tc_id and tc_id in seen_tool_ids:
                            # 이미 관측된 동일 tool_call ID -> 기존 index 재사용
                            tc["index"] = seen_tool_ids[tc_id]
                        else:
                            # 새 tool_call -> 누적 카운터 기반 index 부여
                            tc["index"] = next_index_ref[0]
                            if tc_id:
                                seen_tool_ids[tc_id] = next_index_ref[0]
                            next_index_ref[0] += 1

                    # 비표준 필드 제거
                    tc.pop("extra_content", None)
                    normalized.append(tc)
                delta["tool_calls"] = normalized
        return chunk_data

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse | PassthroughResponse:
        """OpenAI 형식 그대로 Gemini에 전달 (REQ-111-041, REQ-111-042: GEMINI_PASSTHROUGH 지원)"""
        self._warn_unsupported(request, self.SUPPORTED_PARAMS)  # REQ-111-010
        payload = self._build_payload(request, stream=False)
        logger.info(f"Gemini chat request: model={_sanitize_log_input(request.model, max_len=100)}")

        resp = await self._retry_on_429(
            lambda: self.client.post("/chat/completions", json=payload)
        )
        data = resp.json()
        if self.should_log_payload():
            logger.info(f"Gemini chat response: {_scrub_secrets(truncate_for_log(data))}")

        # REQ-111-042: GEMINI_PASSTHROUGH=1 일 때 비스트리밍 응답 업스트림 원본 무손실 반환
        is_passthrough = os.getenv("GEMINI_PASSTHROUGH", "0").strip().lower() in ("1", "true", "yes")
        if is_passthrough:
            # 200 에러 및 choices 방어 검증 (REQ-111-041)
            error_info = data.get("error")
            if error_info:
                err_msg = error_info.get("message") if isinstance(error_info, dict) else str(error_info)
                raise ProviderError(
                    f"Gemini returned error in response body: {_scrub_secrets(err_msg)}",
                    status_code=502,
                    public_message="Gemini returned error in response body",
                )
            choices = data.get("choices") or []
            if not choices:
                raise ProviderError(
                    f"Gemini returned no choices: {_scrub_secrets(json.dumps(data))[:500]}",
                    status_code=502,
                    public_message="Gemini returned no choices (possibly blocked by safety filter)",
                )

            passthrough = PassthroughResponse(data)
            # model 필드만 접두사 포함 원본 ID 로 덮어쓴다
            passthrough.model = request.model
            # finish_reason 화이트리스트 매핑 적용 (REQ-111-043)
            for c in passthrough.get("choices", []):
                if "finish_reason" in c:
                    c["finish_reason"] = _map_finish_reason(c.get("finish_reason")) or "stop"
            return passthrough

        return self._parse_response(data, request.model)

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """Gemini SSE 스트리밍 (REQ-111-040, REQ-111-043, REQ-111-046, REQ-111-047)"""
        self._warn_unsupported(request, self.SUPPORTED_PARAMS)  # REQ-111-010
        include_usage = bool(request.stream_options and request.stream_options.include_usage)  # REQ-111-033
        payload = self._build_payload(request, stream=True)

        logger.info(f"Gemini stream request: model={_sanitize_log_input(request.model, max_len=100)}")
        if self.should_log_payload():
            logger.info(f"Gemini stream request: payload={_scrub_secrets(truncate_for_log(payload))}")

        # REQ-111-040: 스트림 제너레이터 단위 지역 상태 (싱글톤 Provider 인스턴스 동시 요청 간 격리 보장)
        seen_tool_ids: dict[str, int] = {}
        next_tool_index_ref: list[int] = [0]

        # REQ-111-047: 요약 로깅용 집계 변수
        chunk_count = 0
        collected_text = ""
        final_finish_reason: str | None = None
        unique_tool_call_ids: set[str] = set()

        # REQ-111-046: 첫 바이트 전 429/500/503 지수 백오프 재시도
        max_stream_retries = 3
        retry_base_delay = float(os.getenv("PROXY_RETRY_BASE_DELAY", "1.0"))
        stream_cm = None
        resp = None

        try:
            for attempt in range(max_stream_retries + 1):
                stream_cm = self.client.stream("POST", "/chat/completions", json=payload)
                resp = await stream_cm.__aenter__()

                # 첫 바이트 수신 전 429 / 500 / 503 재시도 판정
                if resp.status_code in (429, 500, 503) and attempt < max_stream_retries:
                    error_bytes = await resp.aread()
                    await stream_cm.__aexit__(None, None, None)
                    stream_cm = None

                    retry_after = resp.headers.get("retry-after")
                    delay = retry_base_delay * (2 ** attempt)
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            pass

                    logger.warning(
                        f"Gemini stream HTTP {resp.status_code} — retry {attempt + 1}/{max_stream_retries} "
                        f"in {delay:.2f}s: {_scrub_secrets(error_bytes.decode(errors='replace'))}"
                    )
                    # REQ-111-046: anyio.sleep()을 사용하여 asyncio 및 trio 양쪽 이벤트 루프 호환 보장
                    await anyio.sleep(delay)
                    continue

                if resp.status_code == 429:
                    error_bytes = await resp.aread()
                    await stream_cm.__aexit__(None, None, None)
                    stream_cm = None
                    logger.error(f"Gemini stream 429: {_scrub_secrets(error_bytes.decode(errors='replace'))}")
                    yield self._error_chunk(
                        "Rate limit exceeded (429). Please wait and try again.",
                        code="rate_limit_error",
                    )
                    return

                if resp.status_code != 200:
                    error_bytes = await resp.aread()
                    await stream_cm.__aexit__(None, None, None)
                    stream_cm = None
                    logger.error(f"Gemini stream HTTP {resp.status_code}: {_scrub_secrets(error_bytes.decode(errors='replace'))}")
                    yield self._error_chunk(
                        f"Gemini API error (HTTP {resp.status_code})",
                        code="proxy_error",
                    )
                    return

                # 정상 연결 수립 -> 재시도 루프 탈출
                break

            # ── 스트림 본체 처리 (첫 바이트 방출 이후는 절대 재시도하지 않음) ──
            try:
                stream_id = self._new_stream_id()
                finish_reason_emitted = False
                stream_usage = None

                # REQ-111-031: 스트림 시작 시 role 청크 방출 (첫 바이트)
                chunk_count += 1
                role_chunk = self._chunk(
                    chunk_id=stream_id,
                    model=request.model,
                    delta={"role": "assistant"},
                )
                if self.should_log_chunk():
                    logger.info(f"Gemini stream chunk[{chunk_count}]: role=assistant")
                yield role_chunk

                # SSE 라인 반복 처리
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    raw_line = line[6:].strip()
                    # REQ-111-034: Gemini 업스트림 [DONE] 수신 시 루프 종료
                    if raw_line == "[DONE]":
                        if self.should_log_chunk():
                            logger.info("Gemini stream: upstream [DONE] received (terminating proxy stream)")
                        break

                    try:
                        chunk_data = json.loads(raw_line)
                    except (json.JSONDecodeError, IndexError) as e:
                        if self.should_log_chunk():
                            logger.warning(f"Gemini stream chunk parse error: {e}, passing raw")
                        continue

                    # usage 캡처
                    if "usage" in chunk_data and chunk_data["usage"]:
                        stream_usage = chunk_data["usage"]

                    # REQ-111-040: 스트림 지역 상태를 통한 tool_calls 정규화
                    chunk_data = self._normalize_stream_chunk(
                        chunk_data,
                        seen_tool_ids=seen_tool_ids,
                        next_index_ref=next_tool_index_ref,
                    )
                    choices = chunk_data.get("choices") or []
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})

                    # tool_call ID 집계 (REQ-111-047 요약 로그용)
                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            tc_id = tc.get("id")
                            if tc_id:
                                unique_tool_call_ids.add(tc_id)
                            else:
                                unique_tool_call_ids.add(f"idx_{tc.get('index', len(unique_tool_call_ids))}")

                    # REQ-111-043: finish_reason 화이트리스트 매핑 적용
                    raw_fr = choice.get("finish_reason")
                    finish_reason = _map_finish_reason(raw_fr)

                    # 초기 role 중복 방지
                    if delta.get("role") == "assistant":
                        delta = {k: v for k, v in delta.items() if k != "role"}
                        if not delta and finish_reason is None:
                            continue

                    if delta.get("content"):
                        collected_text += delta["content"]

                    if finish_reason is not None:
                        finish_reason_emitted = True
                        final_finish_reason = finish_reason

                    chunk_count += 1
                    chunk_str = self._chunk(
                        chunk_id=stream_id,
                        model=request.model,
                        delta=delta,
                        finish_reason=finish_reason,
                    )
                    if self.should_log_chunk():
                        logger.info(f"Gemini stream chunk[{chunk_count}]: {_scrub_secrets(truncate_for_log(chunk_str))}")
                    yield chunk_str

                # REQ-111-032: 업스트림이 finish_reason 없이 종료된 경우 프록시가 보정 방출
                if not finish_reason_emitted:
                    chunk_count += 1
                    final_finish_reason = "stop"
                    fr_chunk = self._chunk(
                        chunk_id=stream_id,
                        model=request.model,
                        delta={},
                        finish_reason="stop",
                    )
                    finish_reason_emitted = True
                    if self.should_log_chunk():
                        logger.info(f"Gemini stream chunk[{chunk_count}]: compensated finish_reason=stop")
                    yield fr_chunk

                # REQ-111-033: include_usage=True 일 때 [DONE] 직전 usage 청크 방출
                if include_usage:
                    chunk_count += 1
                    if not stream_usage:
                        stream_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                    else:
                        p_tok = stream_usage.get("prompt_tokens", 0) or 0
                        c_tok = stream_usage.get("completion_tokens", 0) or 0
                        t_tok = stream_usage.get("total_tokens", 0) or (p_tok + c_tok)
                        stream_usage = {
                            "prompt_tokens": p_tok,
                            "completion_tokens": c_tok,
                            "total_tokens": t_tok,
                        }
                    usage_chunk = self._chunk(
                        chunk_id=stream_id,
                        model=request.model,
                        delta={},
                        usage=stream_usage,
                    )
                    if self.should_log_chunk():
                        logger.info(f"Gemini stream chunk[{chunk_count}]: usage={stream_usage}")
                    yield usage_chunk

                # REQ-111-047: 스트림 종료 시 1줄 요약 로그 (청크 수, 총 길이, finish_reason, tool_call 수)
                logger.info(
                    f"Gemini stream completed: chunks={chunk_count}, text_len={len(collected_text)}, "
                    f"finish_reason={final_finish_reason or 'stop'}, tool_calls={len(unique_tool_call_ids)}"
                )

            finally:
                if stream_cm is not None:
                    await stream_cm.__aexit__(None, None, None)

        except Exception as e:
            logger.error(f"Gemini stream error: {_scrub_secrets(str(e))}")
            yield self._error_chunk("Gemini stream processing error", code="proxy_error")
            return

        yield "data: [DONE]\n\n"
