"""
OpenAI Chat Completions API 호환 Pydantic 스키마
FSD v1.0.052 §4.3 요청/응답/에러 형식 정의
"""

from pydantic import BaseModel, Field
from typing import Optional


# ── 요청 스키마 ──

class ChatMessage(BaseModel):
    """채팅 메시지 (role + content)"""
    role: str       # "system" | "user" | "assistant"
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions 요청 형식"""
    model: str                                      # "gemini/gemini-3-pro-preview"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


# ── 응답 스키마 ──

class ChatCompletionChoice(BaseModel):
    """응답 선택지"""
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


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
