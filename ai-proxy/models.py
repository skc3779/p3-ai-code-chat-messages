"""
OpenAI Chat Completions API 호환 Pydantic 스키마
FSD v1.0.052 §4.3 + FSD v1.0.053 §4.3 Tool Call 지원
BUG v1.0.057 — content 필드 타입 확장 (str | list 지원)
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
    role: str                                                    # "system"|"user"|"assistant"|"tool"
    content: Optional[Union[str, list]] = None                   # ★ str 또는 content parts 배열 허용 (BUG-057)
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
