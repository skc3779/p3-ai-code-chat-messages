"""
OpenAI Chat Completions API 호환 Pydantic 스키마
FSD v1.0.052 §4.3 + FSD v1.0.053 §4.3 Tool Call 지원
"""

from pydantic import BaseModel, Field
from typing import Optional, Union


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


# ── 요청 스키마 ──

class ChatMessage(BaseModel):
    """채팅 메시지 (tool call 지원)"""
    role: str                                       # "system"|"user"|"assistant"|"tool"
    content: Optional[str] = None                   # ★ None 허용 (tool_calls 시)
    tool_calls: Optional[list[ToolCall]] = None     # assistant의 도구 호출
    tool_call_id: Optional[str] = None              # tool role 메시지의 호출 ID


class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions 요청 형식 (tool call 지원)"""
    model: str                                      # "gemini/gemini-3-pro-preview"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list[ToolDefinition]] = None    # ★ 추가 (REQ-053-001)
    tool_choice: Optional[Union[str, dict]] = None  # ★ 추가 (REQ-053-002)


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
    """OpenAI Chat Completions 응답 형식"""
    id: str
    object: str = "chat.completion"
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage = Field(default_factory=Usage)


# ── 에러 스키마 (REQ-052-004) ──

class ErrorDetail(BaseModel):
    """OpenAI 형식 에러 상세"""
    message: str
    type: str = "invalid_request_error"
    code: int = 400


class ErrorResponse(BaseModel):
    """OpenAI 형식 에러 응답"""
    error: ErrorDetail
