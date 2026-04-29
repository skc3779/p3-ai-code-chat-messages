"""
GenAI Provider - Samsung SCI Portal (gpt-oss-120B-medium) 형식 변환
FSD v1.0.052 §4.4.3 / REQ-052-005
FSD v1.0.053 §4.4.3 / REQ-053-008
FSD v1.0.054 / REQ-054-001~009 — Tool Call 프록시 레벨 에뮬레이션
FSD v1.0.055 / REQ-055-001~007 — Endpoint URL 구조 수정
BUG v1.0.057 — content 필드 문자열 변환 (str | list 안전 처리)
FSD v1.0.058 / REQ-058-001~006 — 민감 단어 필터링 (password, secret 등 치환/복원)

★ SCI Portal 커스텀 REST API 형식으로 변환
★ 인증: X-Lego-Client-Id / X-Lego-Client-Secret 헤더 (REQ-055-002)
★ Endpoint: {ENDPOINT_URL}/openapi/chat/v1/messages (REQ-055-001)
★ Request Body: modelIds, contents, llmConfig, isStream, systemPrompt (REQ-055-003)
★ Response: event_status(CHUNK/DONE), content (REQ-055-004, REQ-055-005)
★ 모델: gpt-oss-120B-medium (120B 파라미터, Medium 등급)
★ Tool Call: 프롬프트 기반 에뮬레이션 (기존 genai_assistant.py 방식 이식)
  - tools → 시스템 프롬프트에 도구 정의 텍스트 삽입 (REQ-054-001)
  - 응답에서 ```tool_call``` 패턴 파싱 → OpenAI tool_calls 변환 (REQ-054-002)
  - tool role 메시지 → 텍스트로 변환하여 프롬프트에 삽입 (REQ-054-003)
  - tool_choice 처리 (REQ-054-004)
  - assistant tool_calls → 텍스트 변환 (REQ-054-008)
  - 혼합 응답 분리 (REQ-054-009)
★ 민감 단어 필터링 (REQ-058-001~006): password, secret 등 치환/복원
"""

import os
import re
import json
import time
import logging
import httpx
import sys
from pathlib import Path
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

# src/ 패키지 경로 추가 (SensitiveWordFilter 사용을 위해)
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.sensitive_filter import SensitiveWordFilter

# tool_call 파싱 패턴 (genai_assistant.py의 tool_code 패턴과 유사)
TOOL_CALL_PATTERN = re.compile(
    r'```tool_call\s*(\{.*?\})\s*```', re.DOTALL
)


class GenAIProvider(BaseProvider):
    """
    Samsung SCI Portal - 커스텀 REST API 형식 변환 + Tool Call 에뮬레이션

    변환 로직 (FSD v1.0.055 수정):
    - model → modelIds (배열)
    - messages[{role, content}] → contents (문자열 배열) + systemPrompt (최상위 키)
    - temperature/max_tokens → llmConfig 객체 (max_new_tokens, seed, top_k, top_p, temperature, repetition_penalty)
    - 인증: X-Lego-Client-Id / X-Lego-Client-Secret 헤더
    - Endpoint: {ENDPOINT_URL}/openapi/chat/v1/messages
    - ★ tools → 시스템 프롬프트 삽입 (REQ-054-001)
    - ★ 응답 → tool_call 패턴 파싱 (REQ-054-002)
    - ★ tool role → 텍스트 변환 (REQ-054-003)
    - ★ tool_choice 처리 (REQ-054-004)
    - ★ assistant tool_calls → 텍스트 변환 (REQ-054-008)
    - ★ 혼합 응답(텍스트+tool_call) 분리 (REQ-054-009)
    - ★ 민감 단어 필터링 (REQ-058-001~006)
    """

    def __init__(self):
        self.base_url = os.getenv(
            "ENDPOINT_URL",
            "https://scisportaldev.samsungif.net/rest/genAi",
        )
        # REQ-055-002: 올바른 인증 헤더 키 사용
        client_key = os.getenv("YOUR_CLIENT_KEY", "API_CLIENT_APP")
        client_secret = os.getenv("YOUR_CLIENT_SECRET", "")

        self.client = httpx.AsyncClient(
            headers={
                "X-Lego-Client-Id": client_key,        # REQ-055-002
                "X-Lego-Client-Secret": client_secret,  # REQ-055-002
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

        # REQ-058-001: 민감 단어 필터 초기화
        self.sensitive_filter = SensitiveWordFilter()

    # ── Step 1: tools → 시스템 프롬프트 텍스트 (REQ-054-001) ──

    def _build_tools_prompt(self, request: ChatCompletionRequest) -> str:
        """
        OpenAI tools 배열 → 시스템 프롬프트에 삽입할 도구 정의 텍스트 생성.
        genai_assistant.py의 시스템 프롬프트 방식을 자동화.
        """
        if not request.tools:
            return ""

        # tool_choice="none" 이면 도구 정의를 삽입하지 않음
        if request.tool_choice == "none":
            return ""

        lines = [
            "",
            "[TOOLS AVAILABLE]",
            "When you need to use a tool, respond with ONLY a tool call block in this EXACT format:",
            "",
            "```tool_call",
            '{"name": "tool_name", "arguments": {"key": "value"}}',
            "```",
            "",
            "Available tools:",
        ]

        for i, tool in enumerate(request.tools, 1):
            func = tool.function
            desc = func.description or ""
            lines.append(f"{i}. {func.name}: {desc}")

            # 파라미터 설명 생성
            if func.parameters and func.parameters.get("properties"):
                props = func.parameters["properties"]
                required = func.parameters.get("required", [])
                param_parts = []
                for pname, pinfo in props.items():
                    ptype = pinfo.get("type", "any")
                    pdesc = pinfo.get("description", "")
                    req_marker = ", required" if pname in required else ""
                    part = f"{pname} ({ptype}{req_marker})"
                    if pdesc:
                        part += f" - {pdesc}"
                    param_parts.append(part)
                if param_parts:
                    lines.append(f"   Parameters: {', '.join(param_parts)}")

        # tool_choice에 따른 지시문 (REQ-054-004)
        if request.tool_choice == "required":
            lines.append("")
            lines.append("You MUST use one of the tools above to respond.")
        elif isinstance(request.tool_choice, dict):
            fn = request.tool_choice.get("function", {}).get("name", "")
            if fn:
                lines.append("")
                lines.append(f"You MUST use the '{fn}' tool to respond.")

        lines.append("")
        lines.append("IMPORTANT RULES:")
        lines.append("- When calling a tool, output ONLY the ```tool_call``` block, nothing else.")
        lines.append("- The arguments value must be a valid JSON object.")
        lines.append("- Do NOT wrap tool calls in any other format.")

        return "\n".join(lines)

    # ── Step 2: 요청 변환 (REQ-055-003, REQ-054-001, REQ-054-003) ──

    def _transform_request(self, request: ChatCompletionRequest) -> dict:
        """
        OpenAI 형식 → GenAI API (SCI Portal) 형식 변환.
        FSD v1.0.055: genai_assistant.py와 동일한 API 형식 사용.

        변환 규칙:
        - messages → contents (문자열 배열) + systemPrompt (최상위 키)
        - model → modelIds (배열)
        - temperature/max_tokens → llmConfig 객체
        - tools → systemPrompt에 도구 정의 삽입
        """
        contents = []
        system_prompt = ""

        for m in request.messages:
            if m.role == "system":
                # system 메시지는 systemPrompt 최상위 키로 분리 (REQ-055-003)
                system_prompt += m.content_as_str()  # BUG-057: content_as_str() 사용

            elif m.role == "assistant" and m.tool_calls:
                # ★ assistant + tool_calls → 텍스트 변환 (REQ-054-008)
                tool_text_parts = []
                if m.content_as_str():
                    tool_text_parts.append(m.content_as_str())  # BUG-057
                for tc in m.tool_calls:
                    tool_text_parts.append(
                        f"[Tool Call] {tc.function.name}({tc.function.arguments})"
                    )
                contents.append(f"[Assistant Context]\n{chr(10).join(tool_text_parts)}")

            elif m.role == "tool":
                # ★ tool role → 텍스트 변환 (REQ-054-003)
                tool_name = ""
                # tool_call_id로부터 tool name 추적
                if m.tool_call_id:
                    for prev in request.messages:
                        if prev.role == "assistant" and prev.tool_calls:
                            for tc in prev.tool_calls:
                                if tc.id == m.tool_call_id:
                                    tool_name = tc.function.name
                                    break
                contents.append(
                    f"[Tool Result{' for ' + tool_name if tool_name else ''}]\n{m.content_as_str()}"  # BUG-057
                )

            else:
                # user/assistant → 문자열로 변환 (genai_assistant.py 방식)
                if m.role == "user":
                    contents.append(f"[User Context]\n{m.content_as_str()}")  # BUG-057
                else:
                    contents.append(f"[Assistant Context]\n{m.content_as_str()}")  # BUG-057

        # ★ tools → 시스템 프롬프트에 도구 정의 삽입 (REQ-054-001)
        tools_prompt = self._build_tools_prompt(request)
        if tools_prompt:
            system_prompt += tools_prompt

        # REQ-055-003, REQ-055-007: llmConfig 구성 (llm_config.py 기본값 기반)
        llm_config = {
            "max_new_tokens": request.max_tokens or 10240,
            "seed": None,
            "top_k": 14,
            "top_p": 0.94,
            "temperature": request.temperature if request.temperature is not None else 0.4,
            "repetition_penalty": 1.04,
        }

        return {
            "modelIds": [request.model],       # REQ-055-003: 배열 형식
            "contents": contents,               # REQ-055-003: 문자열 배열
            "llmConfig": llm_config,            # REQ-055-003: LLM 설정 객체
            "isStream": False,                  # 프록시에서는 논스트리밍으로 수신 후 변환
            "systemPrompt": system_prompt,      # REQ-055-003: 최상위 키
        }

    # ── Step 3: 응답 파싱 (REQ-054-002) ──

    def _parse_tool_calls(self, text: str) -> list[ToolCall] | None:
        """
        응답 텍스트에서 ```tool_call``` 패턴을 파싱하여 OpenAI tool_calls로 변환.
        genai_assistant.py의 process_tool_calls() 방식을 이식.
        """
        matches = TOOL_CALL_PATTERN.findall(text)
        if not matches:
            return None

        tool_calls = []
        for i, match in enumerate(matches):
            try:
                data = json.loads(match)
                name = data.get("name", "")
                # arguments와 input 양쪽 모두 지원 (호환성)
                args = data.get("arguments", data.get("input", {}))

                # arguments가 이미 문자열이면 그대로, 아니면 JSON 직렬화
                if isinstance(args, str):
                    args_str = args
                else:
                    args_str = json.dumps(args, ensure_ascii=False)

                tool_calls.append(ToolCall(
                    id=f"genai-tc-{int(time.time())}-{i}",
                    type="function",
                    function=FunctionCall(
                        name=name,
                        arguments=args_str,
                    ),
                ))
            except json.JSONDecodeError:
                logger.warning(f"GenAI tool_call JSON 파싱 실패: {match[:100]}")
                continue

        return tool_calls if tool_calls else None

    def _extract_non_tool_content(self, text: str) -> str | None:
        """tool_call 블록을 제거한 나머지 텍스트를 반환 (REQ-054-009: 혼합 응답 분리)"""
        cleaned = TOOL_CALL_PATTERN.sub("", text).strip()
        return cleaned if cleaned else None

    # ── Step 5: chat() (REQ-055-004, REQ-054-002, REQ-054-006, REQ-054-007, REQ-054-009) ──

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """
        SCI Portal API 호출 → OpenAI 형식 응답 변환.
        REQ-055-001: 올바른 endpoint URL 사용
        REQ-055-004: 올바른 response 파싱
        tool_call 패턴 파싱 포함 (429 재시도 포함).
        """
        payload = self._transform_request(request)

        # REQ-058-002: 민감 단어 치환 (GenAI 전송 전)
        if "contents" in payload:
            payload["contents"] = self.sensitive_filter.mask_contents(payload["contents"])
        if "systemPrompt" in payload and payload["systemPrompt"]:
            payload["systemPrompt"] = self.sensitive_filter.mask_system_prompt(payload["systemPrompt"])

        # REQ-055-001: 올바른 endpoint URL 구성
        api_url = f"{self.base_url}/openapi/chat/v1/messages"
        logger.info(f"GenAI chat request: model={request.model}, url={api_url}")
        logger.info(f"GenAI chat payload: {truncate_for_log(payload, 500)}")

        resp = await self._retry_on_429(
            lambda: self.client.post(api_url, json=payload)  # REQ-055-001
        )
        data = resp.json()
        logger.info(f"GenAI chat response: {truncate_for_log(data, 500)}")

        # REQ-055-004: SCI Portal 응답 → 텍스트 추출 (논스트리밍: content 키 사용)
        content = data.get("content", "")

        # REQ-058-005: 응답에서 치환된 단어 복원
        if content:
            content = self.sensitive_filter.unmask(content)

        usage_data = data.get("usage", {})

        # ★ tool_call 패턴 파싱 (REQ-054-002)
        tool_calls = None
        finish_reason = "stop"
        if request.tools:
            tool_calls = self._parse_tool_calls(content)
            if tool_calls:
                finish_reason = "tool_calls"
                # tool_call 블록 외의 텍스트 추출
                content = self._extract_non_tool_content(content)
                logger.info(f"GenAI tool_calls parsed: {len(tool_calls)} calls")

        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(
                        role="assistant",
                        content=content,
                        tool_calls=tool_calls,
                    ),
                    finish_reason=finish_reason,
                )
            ],
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
        )

    # ── Step 6: stream() (REQ-055-005, REQ-054-005, REQ-054-009) ──

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """
        SCI Portal 스트리밍 → OpenAI SSE.
        tool_call 감지를 위해 전체 응답 버퍼링 후 파싱.
        """
        try:
            # 버퍼링 방식: 전체 응답을 chat()으로 받아서 SSE 청크로 변환
            result = await self.chat(request)
            msg = result.choices[0].message
            finish_reason = result.choices[0].finish_reason

            # ★ 첫 번째 청크: role 전송 (OpenAI SSE 표준)
            role_chunk = {
                "choices": [{
                    "delta": {"role": "assistant"},
                    "index": 0
                }]
            }
            yield f"data: {json.dumps(role_chunk)}\n\n"

            if msg.tool_calls:
                # ★ tool_calls → OpenAI SSE 델타 형식으로 변환
                for i, tc in enumerate(msg.tool_calls):
                    chunk = {
                        "choices": [{
                            "delta": {
                                "tool_calls": [{
                                    "index": i,
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    }
                                }]
                            },
                            "index": 0
                        }]
                    }
                    logger.info(f"GenAI stream: tool_call[{i}] name={tc.function.name}")
                    yield f"data: {json.dumps(chunk)}\n\n"

                # ★ REQ-054-009: tool_calls와 content가 동시에 있는 혼합 응답 처리
                if msg.content:
                    content_chunk = {
                        "choices": [{
                            "delta": {"content": msg.content},
                            "index": 0
                        }]
                    }
                    yield f"data: {json.dumps(content_chunk, ensure_ascii=False)}\n\n"

                # finish_reason 청크
                done_chunk = {
                    "choices": [{
                        "delta": {},
                        "finish_reason": "tool_calls",
                        "index": 0
                    }]
                }
                yield f"data: {json.dumps(done_chunk)}\n\n"

            elif msg.content:
                # 일반 텍스트 응답 → SSE text 청크
                chunk = {
                    "choices": [{
                        "delta": {"content": msg.content},
                        "index": 0
                    }]
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                # finish_reason 청크
                done_chunk = {
                    "choices": [{
                        "delta": {},
                        "finish_reason": "stop",
                        "index": 0
                    }]
                }
                yield f"data: {json.dumps(done_chunk)}\n\n"

            yield "data: [DONE]\n\n"
            logger.info(f"GenAI stream completed: finish_reason={finish_reason}")

        except ProviderError as e:
            logger.error(f"GenAI tool error: {e}")
            yield self._error_chunk(str(e))
        except Exception as e:
            logger.error(f"GenAI stream error: {e}")
            yield self._error_chunk(f"GenAI API error: {str(e)}")
