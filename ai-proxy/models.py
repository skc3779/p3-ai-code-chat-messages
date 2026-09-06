"""
OpenAI Chat Completions API 호환 Pydantic 스키마
FSD v1.0.052 §4.3 + FSD v1.0.053 §4.3 Tool Call 지원
BUG v1.0.057 — content 필드 타입 확장 (str | list 지원)
"""

import time
from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
from typing import Any, Optional, Union


# ── Tool 관련 스키마 (REQ-053-001~003) ──

class FunctionDefinition(BaseModel):
    """도구 함수 정의"""
    name: str
    description: Optional[str] = None
    parameters: Optional[dict] = None       # JSON Schema


class ToolDefinition(BaseModel):
    """도구 정의"""
    type: str = "function"
    function: FunctionDefinition


class FunctionCall(BaseModel):
    """도구 호출 응답 — function name + arguments"""
    name: str
    arguments: str                          # JSON 문자열


class ToolCall(BaseModel):
    """도구 호출"""
    id: str
    type: str = "function"
    function: FunctionCall


# ── 스트리밍 옵션 스키마 (REQ-111-001, REQ-111-007, REQ-111-016) ──

class StreamOptions(BaseModel):
    """스트리밍 옵션 (REQ-111-001, REQ-111-007: extra forbid 유지, REQ-111-016: include_obfuscation 선언)"""
    include_usage: bool = False
    include_obfuscation: Optional[bool] = None

    model_config = {"extra": "forbid"}


# ── 요청 스키마 ──

class ChatMessage(BaseModel):
    """채팅 메시지 (tool call 지원) (REQ-111-004)"""
    role: str                                                    # "system"|"user"|"assistant"|"tool"
    content: Optional[Union[str, list]] = None                   # ★ str 또는 content parts 배열 허용 (BUG-057)
    name: Optional[str] = None                                   # 참여자 이름 (REQ-111-004)
    tool_calls: Optional[list[ToolCall]] = None                  # assistant의 도구 호출
    tool_call_id: Optional[str] = None                           # tool role 메시지의 호출 ID

    def content_as_str(self) -> str:
        """
        content를 문자열로 변환하여 반환 (BUG-057).

        OpenAI API에서 content는 두 가지 형태가 가능:
          1. 문자열: "Hello" → 그대로 반환
          2. content parts 배열: [{"type":"text","text":"Hello"}, ...] → text 부분 결합

        Returns:
            str: 변환된 텍스트 문자열 (None이면 빈 문자열)
        """
        if self.content is None:
            return ""
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, list):
            # content parts 배열: [{"type": "text", "text": "..."}] 형태
            parts = []
            for part in self.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        parts.append(part.get("text", ""))
                    else:
                        # image_url 등 텍스트가 아닌 타입은 설명으로 변환
                        parts.append(f"[{part.get('type', 'unknown')}]")
                elif isinstance(part, str):
                    parts.append(part)
                else:
                    parts.append(str(part))
            return "\n".join(parts)
        # 기타 타입은 문자열로 변환
        return str(self.content)


class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions 요청 형식 (tool call 지원) (REQ-111-001, REQ-111-006, REQ-111-008)"""
    model_config = {"extra": "allow"}

    # 내부 중복 경고 방지용 비공개 속성 (직렬화/스키마 미노출) (REQ-111-018)
    _warned_unsupported: bool = PrivateAttr(default=False)
    _warned_unsupported_keys: set[Any] = PrivateAttr(default_factory=set)

    model: str                                                    # "gemini/gemini-3-pro-preview"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    tools: Optional[list[ToolDefinition]] = None                  # ★ 추가 (REQ-053-001)
    tool_choice: Optional[Union[str, dict]] = None                # ★ 추가 (REQ-053-002)

    # ── 확장 요청 파라미터 (REQ-111-001, REQ-111-008) ──
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stop: Optional[Union[str, list[str]]] = None
    n: Optional[int] = Field(default=None, ge=1)
    seed: Optional[int] = None
    presence_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    response_format: Optional[dict[str, Any]] = None
    stream_options: Optional[StreamOptions] = None
    parallel_tool_calls: Optional[bool] = None
    user: Optional[str] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = Field(default=None, ge=0, le=20)

    @field_validator("stop")
    @classmethod
    def validate_stop(cls, v: Optional[Union[str, list[str]]]) -> Optional[Union[str, list[str]]]:
        if isinstance(v, list) and len(v) > 4:
            raise ValueError("stop array can contain at most 4 items")
        return v

    @model_validator(mode="after")
    def validate_logprobs_consistency(self) -> "ChatCompletionRequest":
        if self.top_logprobs is not None and not self.logprobs:
            raise ValueError("top_logprobs requires logprobs to be True")
        return self


# ── 응답 스키마 ──

class ChatCompletionChoice(BaseModel):
    """응답 선택지 (tool call 지원)"""
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"       # ★ "tool_calls" 가능


class Usage(BaseModel):
    """토큰 사용량"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI Chat Completions 응답 형식 (REQ-111-002)"""
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage = Field(default_factory=Usage)


# ── 에러 스키마 (REQ-052-004, REQ-111-003) ──

class ErrorDetail(BaseModel):
    """OpenAI 형식 에러 상세 (REQ-111-003: code int -> str 변경)"""
    message: str
    type: str = "invalid_request_error"
    code: str = "invalid_request_error"


class ErrorResponse(BaseModel):
    """OpenAI 형식 에러 응답"""
    error: ErrorDetail
