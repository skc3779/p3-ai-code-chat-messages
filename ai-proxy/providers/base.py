"""
Provider 추상 클래스 + 공통 에러 핸들링 유틸리티
FSD v1.0.052 §4.1 - SRS v2 §4.2 BaseProvider
"""

import anyio  # REQ-111-048: trio/asyncio 백엔드 중립 슬립 (asyncio.sleep 은 trio 루프에서 RuntimeError)
import json
import logging
import os
import re
import time
import unicodedata
import uuid
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

import httpx

from models import ChatCompletionRequest, ChatCompletionResponse

logger = logging.getLogger("ai-proxy")

# 429 재시도 설정
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # 초 (지수 백오프: 2s, 4s, 8s)

# REQ-111-014: 로그 출력 기본 최대 길이 (100000 -> 2000)
DEFAULT_LOG_MAX_LEN = 2000

# REQ-111-020: 마스킹 대상 환경변수 키 목록
ENV_SECRET_NAMES = (
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "YOUR_CLIENT_SECRET",
    "YOUR_CLIENT_KEY",
    "AI_PROXY_API_KEY",
)


def _scrub_secrets(text: object, max_len: int = DEFAULT_LOG_MAX_LEN) -> str:
    """
    내부 진단 로그 및 에러 메시지용 비밀값/자격증명 마스킹 함수 (REQ-111-020).
    - 특정 환경변수 리터럴을 '***REDACTED***'로 치환
    - API 키 및 인증 헤더 공통 패턴 마스킹
    - 최대 길이 상한 적용
    """
    if text is None:
        return ""
    s = str(text)

    # 1. 환경변수 리터럴 치환
    for env_name in ENV_SECRET_NAMES:
        val = os.getenv(env_name)
        if val and len(val.strip()) > 0:
            s = s.replace(val, "***REDACTED***")

    # 2. 흔한 자격증명 패턴 마스킹
    s = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "***REDACTED***", s)
    s = re.sub(r"AIza[A-Za-z0-9_\-]+", "***REDACTED***", s)
    s = re.sub(r"(?i)\bBearer\s+\S+", "Bearer ***REDACTED***", s)
    s = re.sub(r'(?i)x-api-key["\':=\s]+[^\s,;"\'}]+', "x-api-key=***REDACTED***", s)

    # 3. 길이 제한 적용
    if len(s) > max_len:
        s = s[:max_len].rstrip() + "...(truncated)"
    return s


def _validate_api_key(key: str | None, key_name: str) -> None:
    """
    API 키 환경변수 사전 검증 (REQ-111-020).
    개행문자(\\r, \\n) 등 비정상 제어문자가 포함된 경우 에러를 발생시킨다.
    보안: 에러 메시지에 실제 키 값을 절대로 포함하지 않는다.
    """
    if not key:
        return
    for ch in key:
        code = ord(ch)
        if ch in ("\r", "\n") or (code < 32 and ch != "\t") or code == 127:
            raise ValueError(
                f"Invalid API key configuration for '{key_name}': "
                f"contains illegal control or newline characters."
            )


def should_log_payload() -> bool:
    """LOG_PAYLOAD=1 일 때만 요청/응답 페이로드 전문을 기록한다 (기본 off) (REQ-111-014)."""
    return os.getenv("LOG_PAYLOAD", "0").strip().lower() in ("1", "true", "yes")


def should_log_chunk() -> bool:
    """LOG_CHUNK=1 일 때만 SSE 청크 단위 로그를 기록한다 (기본 off) (REQ-111-014)."""
    return os.getenv("LOG_CHUNK", "0").strip().lower() in ("1", "true", "yes")


def truncate_for_log(data, max_len: int = DEFAULT_LOG_MAX_LEN, indent: int = 2) -> str:
    """
    로그 출력용 문자열 변환 + Pretty Printing + 잘라내기 + 비밀값 마스킹 (REQ-111-014, REQ-111-020).

    - dict/list → 들여쓰기가 적용된 JSON 문자열로 변환
    - 문자열이 max_len보다 짧으면 전체 반환
    - 길면 max_len까지만 반환 + '...(truncated)' 접미사
    - 비밀값/자격증명 마스킹 적용
    """
    try:
        if isinstance(data, (dict, list)):
            text = json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=True)
        else:
            text = str(data)
    except Exception as e:
        text = f"[Serialization Error: {e}] {str(data)}"

    # REQ-111-020: 직렬화된 로그 데이터에 비밀값 마스킹 적용
    text = _scrub_secrets(text, max_len=max_len)

    if len(text) <= max_len:
        return text.rstrip() + "\n"
    
    return text[:max_len].rstrip() + "...(truncated)\n"


def _sanitize_log_input(text: object, max_len: int = 100) -> str:
    """
    로그 인젝션 방지를 위한 사용자 입력 정제 함수 (REQ-111-009, REQ-111-017).
    - 개행문자(\\r, \\n), 탭(\\t), ASCII 제어문자 이스케이프
    - 유니코드 줄/문단 구분자(U+2028, U+2029, U+0085) 이스케이프
    - 방향 제어문자(U+202A~U+202E, U+2066~U+2069) 이스케이프
    - 기타 Unicode Cf(Format) 카테고리 문자 이스케이프
    - 최대 길이 제한 (초과 시 ... 포함 총 max_len자 이하)
    """
    if text is None:
        return ""
    s = str(text)
    out = []
    for ch in s:
        code = ord(ch)
        if ch == "\r":
            out.append("\\r")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif code in (0x2028, 0x2029, 0x0085):
            out.append(f"\\u{code:04x}")
        elif (0x202A <= code <= 0x202E) or (0x2066 <= code <= 0x2069):
            out.append(f"\\u{code:04x}")
        elif unicodedata.category(ch) == "Cf":
            out.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        elif code < 0x20 or code == 0x7F:
            out.append(f"\\x{code:02x}")
        else:
            out.append(ch)
    res = "".join(out)
    if len(res) > max_len:
        if max_len >= 3:
            res = res[:max_len - 3] + "..."
        else:
            res = res[:max_len]
    return res


class ProviderError(Exception):
    """Provider에서 발생하는 에러 (상태 코드 + 클라이언트 공개용 메시지 / 내부 진단용 메시지 분리) (REQ-111-020)"""

    def __init__(
        self,
        message: str,
        status_code: int = 502,
        public_message: str | None = None,
        request_id: str | None = None,
    ):
        super().__init__(message)
        self.internal_message = message
        self.status_code = status_code
        self.request_id = request_id

        if public_message is not None:
            self.public_message = public_message
        else:
            req_suffix = f" (request_id={request_id})" if request_id else ""
            if status_code == 429:
                self.public_message = f"Upstream rate limit exceeded{req_suffix}"
            elif status_code in (401, 403):
                self.public_message = f"Upstream authentication error{req_suffix}"
            elif status_code == 400:
                self.public_message = f"Upstream invalid request{req_suffix}"
            elif status_code == 404:
                self.public_message = f"Upstream resource not found{req_suffix}"
            else:
                self.public_message = f"Upstream provider error{req_suffix}"


class BaseProvider(ABC):
    """모든 Provider가 구현해야 하는 인터페이스."""

    _sanitize_log_input = staticmethod(_sanitize_log_input)
    _scrub_secrets = staticmethod(_scrub_secrets)
    _validate_api_key = staticmethod(_validate_api_key)
    should_log_payload = staticmethod(should_log_payload)
    should_log_chunk = staticmethod(should_log_chunk)

    @abstractmethod
    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        pass

    @abstractmethod
    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        pass

    async def aclose(self):
        """Provider 리소스 정리 (AsyncClient 종료 등) (REQ-111-013)."""
        client = getattr(self, "client", None)
        if client is not None and hasattr(client, "aclose") and callable(client.aclose):
            await client.aclose()

    def _extra_param_warnings(self, request: ChatCompletionRequest, is_streaming: bool = False) -> None:
        """
        Provider별 조건부 파라미터 경고 훅 (REQ-111-019).
        기본 구현은 no-op이며, 특정 Provider(예: GenAIProvider)에서 재정의.
        """
        pass

    # ── 공통 유틸리티 ──

    @classmethod
    def _warn_unsupported(
        cls,
        request: ChatCompletionRequest,
        supported: set[str],
        provider_name: str | None = None,
    ) -> list[str]:
        """
        Provider가 처리하지 못하는 필드가 요청에 있으면 logger.warning으로 요청당 1회 기록
        (REQ-111-005, REQ-111-006, REQ-111-009, REQ-111-016, REQ-111-017, REQ-111-018, REQ-111-019).

        - 미지원 필드 계산과 로그 중복 억제를 분리: 반환 목록은 항상 정확히 계산
        - 로그 중복 억제는 (Provider 식별명, 지원 필드 튜플) 단위로 관리
        - stream=False는 비스트리밍 요청 충족이므로 경고 대상 제외
        - stream=True는 Provider 조건부 훅(_extra_param_warnings)에서 전담하므로 일반 경고에서 제외
        - stream_options.include_obfuscation 미지원 옵션 감지
        - 전체 경고 메시지 길이 500자 상한 적용

        Args:
            request: ChatCompletionRequest 요청 객체
            supported: 해당 Provider가 지원하는 필드명 집합 (예: {"model", "messages", "temperature"})
            provider_name: 경고 중복 억제용 Provider 식별명 (미지정 시 cls.__name__)

        Returns:
            list[str]: 감지된 미지원 필드명 목록 (정렬됨)
        """
        unsupported = set()
        for field_name in type(request).model_fields:
            val = getattr(request, field_name, None)
            if val is None:
                continue
            # stream=False는 비스트리밍 요청이 충족되므로 경고 대상 제외 (REQ-111-019)
            # stream=True는 Provider 조건부 훅(_extra_param_warnings)에서 전담하므로 일반 경고에서 제외
            if field_name == "stream":
                continue
            if field_name not in supported:
                unsupported.add(field_name)

        if getattr(request, "model_extra", None):
            for extra_field, extra_val in request.model_extra.items():
                if extra_val is not None and extra_field not in supported:
                    unsupported.add(extra_field)

        # stream_options 내부의 미지원 하위 옵션 검사 (REQ-111-016)
        if request.stream_options is not None:
            if getattr(request.stream_options, "include_obfuscation", None) is not None:
                unsupported.add("stream_options.include_obfuscation")

        unsupported_list = sorted(unsupported)

        # ── 로그 중복 억제 (Provider/지원필드 단위) (REQ-111-018) ──
        provider_key = provider_name or (cls.__name__ if cls is not BaseProvider else "BaseProvider")
        supp_sig = (provider_key, tuple(sorted(supported)))

        warned_keys = getattr(request, "_warned_unsupported_keys", None)
        if warned_keys is None:
            warned_keys = set()
            try:
                request._warned_unsupported_keys = warned_keys
            except Exception:
                pass

        if unsupported_list and supp_sig not in warned_keys:
            warned_keys.add(supp_sig)
            request._warned_unsupported = True

            safe_model = _sanitize_log_input(getattr(request, "model", "unknown"), max_len=100)
            safe_fields = [_sanitize_log_input(f, max_len=100) for f in unsupported_list]
            fields_str = ", ".join(safe_fields)
            warning_msg = (
                f"Unsupported parameters for model '{safe_model}' "
                f"ignored by provider: {fields_str}"
            )
            # REQ-111-017: 경고 메시지 전체 길이 상한 (500자)
            if len(warning_msg) > 500:
                warning_msg = warning_msg[:497] + "..."
            logger.warning(warning_msg)

        return unsupported_list

    @staticmethod
    async def _retry_on_429(coro_factory, max_retries=MAX_RETRIES, request_id: str | None = None):
        """
        429 Too Many Requests 시 지수 백오프로 재시도 (REQ-111-020).

        Args:
            coro_factory: 호출할 코루틴을 반환하는 팩토리 함수 (매번 새 코루틴 생성)
            max_retries: 최대 재시도 횟수
            request_id: 상관 추적용 요청 식별자

        Returns:
            httpx.Response

        Raises:
            ProviderError: 재시도 후에도 실패 시 (클라이언트 공개 메시지와 내부 상세 로그 분리)
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                resp = await coro_factory()
                if resp.status_code == 429 and attempt < max_retries:
                    # Retry-After 헤더 존재 시 해당 시간 사용, 없으면 지수 백오프
                    retry_after = resp.headers.get("retry-after")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = RETRY_BASE_DELAY * (2 ** attempt)
                    else:
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"429 Too Many Requests — retry {attempt + 1}/{max_retries} "
                        f"in {delay:.1f}s"
                    )
                    await anyio.sleep(delay)  # REQ-111-048
                    continue

                resp.raise_for_status()
                return resp

            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code

                if status == 429 and attempt < max_retries:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"429 Too Many Requests — retry {attempt + 1}/{max_retries} "
                        f"in {delay:.1f}s"
                    )
                    await anyio.sleep(delay)  # REQ-111-048
                    continue

                # 429 이외의 에러 또는 재시도 소진
                error_body = ""
                try:
                    error_body = e.response.text
                except Exception:
                    pass
                # REQ-111-020: 내부 진단용 로그에는 비밀값 스크러빙 적용
                scrubbed_body = _scrub_secrets(error_body) if error_body else _scrub_secrets(str(e))
                req_suffix = f" (request_id={request_id})" if request_id else ""
                raise ProviderError(
                    f"HTTP {status}: {scrubbed_body}",
                    status_code=status,
                    public_message=f"Upstream provider error (HTTP {status}){req_suffix}",
                    request_id=request_id,
                ) from e

        # 재시도 모두 소진
        req_suffix = f" (request_id={request_id})" if request_id else ""
        raise ProviderError(
            f"Rate limit exceeded after {max_retries} retries: {_scrub_secrets(str(last_error))}",
            status_code=429,
            public_message=f"Rate limit exceeded after {max_retries} retries{req_suffix}",
            request_id=request_id,
        )

    @staticmethod
    def _error_chunk(message: str, code: str = "proxy_error") -> str:
        """
        스트리밍 도중 에러 발생 시 SSE 에러 청크를 반환 (REQ-111-020).
        클라이언트가 에러를 인식할 수 있도록 OpenAI 형식으로 래핑하며 code 필드를 포함.
        """
        error_data = {
            "error": {
                "message": message,
                "type": "proxy_error",
                "code": code,
            }
        }
        return f"data: {json.dumps(error_data, ensure_ascii=False)}\n\ndata: [DONE]\n\n"

    @staticmethod
    def _new_stream_id() -> str:
        """스트림 단위 고유 chunk_id 생성 (REQ-111-030). 형식: f'chatcmpl-{uuid.uuid4().hex[:24]}'."""
        return f"chatcmpl-{uuid.uuid4().hex[:24]}"

    @staticmethod
    def _chunk(
        chunk_id: str,
        model: str,
        delta: dict,
        finish_reason: str | None = None,
        usage: dict | None = None,
    ) -> str:
        """
        OpenAI 규격 Chat Completion SSE 청크 문자열 생성 (REQ-111-030, REQ-111-033).
        반환 형식: 'data: {json}\\n\\n'
        - ensure_ascii=False 로 직렬화하여 한글 보존
        - usage 가 주어지면 choices 는 빈 배열([])로 설정하고 usage 필드 포함 (REQ-111-033)
        - 일반 청크는 choices[0] 에 index=0, delta, finish_reason 포함
        """
        chunk_dict: dict[str, Any] = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [] if usage is not None else [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        if usage is not None:
            chunk_dict["usage"] = usage

        return f"data: {json.dumps(chunk_dict, ensure_ascii=False)}\n\n"

    @classmethod
    def _warn_name_if_present(cls, request: ChatCompletionRequest) -> None:
        """
        messages[].name 필드 미지원 경고 (REQ-111-035).
        Anthropic API 및 GenAI 등 name 필드를 미지원/유예하는 Provider에서 요청당 1회 경고 기록.
        """
        has_name = any(bool(getattr(m, "name", None)) for m in getattr(request, "messages", []))
        if not has_name:
            return
        sig = (cls.__name__, "messages.name")
        warned_keys = getattr(request, "_warned_unsupported_keys", None)
        if warned_keys is None:
            warned_keys = set()
            try:
                request._warned_unsupported_keys = warned_keys
            except Exception:
                pass
        if sig not in warned_keys:
            warned_keys.add(sig)
            safe_model = _sanitize_log_input(getattr(request, "model", "unknown"), max_len=100)
            if cls.__name__ == "ClaudeProvider":
                logger.warning(
                    f"Model '{safe_model}': 'messages[].name' is not supported by Claude (Anthropic API schema) and will be ignored"
                )
            elif cls.__name__ == "GenAIProvider":
                logger.warning(
                    f"Model '{safe_model}': 'messages[].name' is not yet supported by GenAI (deferred to TASK-GENAI-4) and will be ignored"
                )
            else:
                logger.warning(
                    f"Model '{safe_model}': 'messages[].name' is not supported by {cls.__name__} and will be ignored"
                )
 
 
def __getattr__(name: str):
    """동적 모듈 레벨 속성 지원 (REQ-111-014)."""
    if name == "LOG_PAYLOAD":
        return should_log_payload()
    if name == "LOG_CHUNK":
        return should_log_chunk()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
