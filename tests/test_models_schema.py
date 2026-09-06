"""
TASK-CORE-1 단위 테스트 — 공통 요청/응답 스키마 확장 및 미지원 파라미터 경고 검증.
REQ-111-001: ChatCompletionRequest 신규 필드 (top_p, stop, n, seed, stream_options 등)
REQ-111-002: ChatCompletionResponse created 자동 생성 (int timestamp)
REQ-111-003: ErrorDetail.code 타입 int -> str 변경
REQ-111-004: ChatMessage.name 지원
REQ-111-005: BaseProvider._warn_unsupported 미지원 필드 경고 (요청당 1회)
"""

import logging
import ast
from collections import Counter
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

# ai-proxy 디렉토리를 sys.path에 추가하여 내부 모듈 import 보장
PROXY_DIR = Path(__file__).resolve().parent.parent / "ai-proxy"
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))

from models import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ErrorDetail,
    ErrorResponse,
    StreamOptions,
    Usage,
)
from providers.base import BaseProvider


# REQ-111-047: 별도 인터프리터에서 import 순서와 기존 모듈 캐시 영향을 제거한다.
def test_model_registry_import_does_not_load_providers():
    script = """
import sys
sys.path.insert(0, sys.argv[1])
import model_registry
loaded = sorted(name for name in sys.modules
                if name == 'providers' or name.startswith('providers.'))
assert not loaded, f'model_registry imported providers: {loaded}'
assert 'router' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(PROXY_DIR)],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# REQ-111-045: 접두사 양쪽 형식 및 알려지지 않은 모델의 기본값 계약.
@pytest.mark.parametrize("model,expected", [
    ("claude/claude-sonnet-4-6", 65536),
    ("gemini/gemini-3-pro-preview", 65536),
    ("genai/glm5.2", 4096),
])
def test_registry_max_output_prefixed_and_bare(model, expected):
    from model_registry import get_model_max_output

    assert get_model_max_output(model) == expected
    assert get_model_max_output(model.split("/", 1)[1]) == expected
    assert get_model_max_output("unknown-model") == 4096
    assert get_model_max_output("unknown-model", default=123) == 123


# REQ-111-046, REQ-111-047: 등록 정합성 및 하위 호환 re-export 객체 동일성.
def test_registry_metadata_and_router_identity():
    import model_registry
    import router

    assert "genai/glm5.2" in model_registry.SUPPORTED_MODELS
    assert router.SUPPORTED_MODELS is model_registry.SUPPORTED_MODELS
    missing = set(model_registry.MODEL_METADATA) - set(model_registry.SUPPORTED_MODELS)
    assert not missing, f"Metadata models absent from SUPPORTED_MODELS: {sorted(missing)}"


# REQ-111-046: dict 평가로 사라지는 중복 키를 원본 AST에서 검출한다.
def test_supported_models_source_has_no_duplicate_keys():
    tree = ast.parse((PROXY_DIR / "model_registry.py").read_text(encoding="utf-8"))
    declarations = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "SUPPORTED_MODELS"
                   for target in targets):
                declarations.append(node.value)
    assert len(declarations) == 1, "Expected one SUPPORTED_MODELS source declaration"
    literal = declarations[0]
    assert isinstance(literal, ast.Dict), "SUPPORTED_MODELS must be an inspectable dict literal"
    assert all(isinstance(key, ast.Constant) and isinstance(key.value, str)
               for key in literal.keys), "Model keys must be explicit strings"
    duplicates = sorted(key for key, count in Counter(
        key.value for key in literal.keys).items() if count > 1)
    assert not duplicates, f"Duplicate SUPPORTED_MODELS source keys: {duplicates}"


# REQ-111-045, REQ-111-046: TASK-DOC 소유 설정의 누락/초과 모델을 숨기지 않는다.
def test_opencode_models_match_registry():
    from model_registry import SUPPORTED_MODELS

    config = json.loads((PROXY_DIR.parent / "opencode.json").read_text(encoding="utf-8"))
    configured = set(config["provider"]["ai-proxy"]["models"])
    supported = set(SUPPORTED_MODELS)
    assert configured == supported, (
        "opencode.json update required (TASK-DOC): "
        f"missing in opencode.json={sorted(supported - configured)}; "
        f"extra in opencode.json={sorted(configured - supported)}"
    )


# ── REQ-111-001: ChatCompletionRequest 신규 필드 기본값 및 보존 검증 ──

def test_new_fields_default_none():
    """신규 추가된 모든 필드가 기본값 None으로 존재하는지 검증 (REQ-111-001)."""
    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hello")],
    )

    assert req.top_p is None
    assert req.stop is None
    assert req.n is None
    assert req.seed is None
    assert req.presence_penalty is None
    assert req.frequency_penalty is None
    assert req.response_format is None
    assert req.stream_options is None
    assert req.parallel_tool_calls is None
    assert req.user is None
    assert req.logprobs is None
    assert req.top_logprobs is None


def test_new_fields_preserved_when_provided():
    """신규 추가된 필드에 값을 전달했을 때 온전히 보존되는지 검증 (REQ-111-001)."""
    req = ChatCompletionRequest(
        model="gemini/gemini-3-pro-preview",
        messages=[ChatMessage(role="user", content="test message")],
        top_p=0.95,
        stop=["END", "STOP"],
        n=2,
        seed=12345,
        presence_penalty=0.5,
        frequency_penalty=-0.5,
        response_format={"type": "json_object"},
        stream_options=StreamOptions(include_usage=True),
        parallel_tool_calls=False,
        user="user-42",
        logprobs=True,
        top_logprobs=3,
    )

    assert req.top_p == 0.95
    assert req.stop == ["END", "STOP"]
    assert req.n == 2
    assert req.seed == 12345
    assert req.presence_penalty == 0.5
    assert req.frequency_penalty == -0.5
    assert req.response_format == {"type": "json_object"}
    assert req.stream_options is not None
    assert req.stream_options.include_usage is True
    assert req.parallel_tool_calls is False
    assert req.user == "user-42"
    assert req.logprobs is True
    assert req.top_logprobs == 3

    # model_dump 직렬화 보존 확인
    dumped = req.model_dump()
    assert dumped["top_p"] == 0.95
    assert dumped["stop"] == ["END", "STOP"]
    assert dumped["n"] == 2
    assert dumped["seed"] == 12345
    assert dumped["presence_penalty"] == 0.5
    assert dumped["frequency_penalty"] == -0.5
    assert dumped["response_format"] == {"type": "json_object"}
    assert dumped["stream_options"] == {"include_usage": True, "include_obfuscation": None}
    assert dumped["parallel_tool_calls"] is False
    assert dumped["user"] == "user-42"
    assert dumped["logprobs"] is True
    assert dumped["top_logprobs"] == 3


def test_stop_string_and_list_parsing():
    """stop 파라미터가 str과 list[str] 양쪽 모두로 정상 파싱되는지 검증 (REQ-111-001)."""
    # 1. 단일 문자열
    req_str = ChatCompletionRequest(
        model="genai/gpt-oss-120B-medium",
        messages=[ChatMessage(role="user", content="hi")],
        stop="STOP_NOW",
    )
    assert req_str.stop == "STOP_NOW"

    # 2. 문자열 리스트
    req_list = ChatCompletionRequest(
        model="genai/gpt-oss-120B-medium",
        messages=[ChatMessage(role="user", content="hi")],
        stop=["STOP_1", "STOP_2"],
    )
    assert req_list.stop == ["STOP_1", "STOP_2"]

    # 3. dict 역직렬화(model_validate) 검증
    validated_str = ChatCompletionRequest.model_validate({
        "model": "test-model",
        "messages": [{"role": "user", "content": "hi"}],
        "stop": "HALT",
    })
    assert validated_str.stop == "HALT"

    validated_list = ChatCompletionRequest.model_validate({
        "model": "test-model",
        "messages": [{"role": "user", "content": "hi"}],
        "stop": ["HALT", "QUIT"],
    })
    assert validated_list.stop == ["HALT", "QUIT"]


def test_stream_options_parsing():
    """StreamOptions 모델 및 include_usage 파싱 검증 (REQ-111-001)."""
    # 1. StreamOptions 기본값
    so_default = StreamOptions()
    assert so_default.include_usage is False

    # 2. StreamOptions 명시적 설정
    so_true = StreamOptions(include_usage=True)
    assert so_true.include_usage is True

    # 3. ChatCompletionRequest에 dict로 전달 시 StreamOptions로 자동 파싱
    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="stream with usage")],
        stream=True,
        stream_options={"include_usage": True},
    )
    assert isinstance(req.stream_options, StreamOptions)
    assert req.stream_options.include_usage is True

    # 4. extra 필드가 포함되면 거부(extra="forbid")하여 422/ValidationError 발생하는지 검증 (REQ-111-007, MINOR-5)
    with pytest.raises(ValidationError):
        StreamOptions.model_validate({"include_usage": True, "extra_flag": "test"})

    # 오타(include_usgae, include_obfuscaton) 전달 시 ValidationError 발생 확인
    with pytest.raises(ValidationError):
        StreamOptions.model_validate({"include_usgae": True})
    with pytest.raises(ValidationError):
        StreamOptions.model_validate({"include_obfuscaton": False})

    # 5. REQ-111-016 (MAJOR-2): include_obfuscation 공식 옵션 정상 수용 검증
    so_obf_false = StreamOptions(include_obfuscation=False)
    assert so_obf_false.include_obfuscation is False

    so_obf_true = StreamOptions(include_obfuscation=True)
    assert so_obf_true.include_obfuscation is True

    # codex 2차 리뷰 재현 케이스: {"stream": True, "stream_options": {"include_obfuscation": False}}
    req_obf = ChatCompletionRequest.model_validate({
        "model": "claude/claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "stream_options": {"include_obfuscation": False},
    })
    assert req_obf.stream_options is not None
    assert req_obf.stream_options.include_obfuscation is False

    # 프록시 미지원 옵션이므로 _warn_unsupported 대상에 포함됨을 검증
    unsupported = BaseProvider._warn_unsupported(req_obf, {"model", "messages", "stream"})
    assert "stream_options.include_obfuscation" in unsupported


# ── REQ-111-002: ChatCompletionResponse created 자동 생성 검증 ──

def test_created_auto_generation():
    """ChatCompletionResponse.created 필드가 int 타임스탬프로 자동 생성되는지 검증 (REQ-111-002)."""
    before = int(time.time())
    resp = ChatCompletionResponse(
        id="chatcmpl-test-123",
        model="claude/claude-sonnet-4-6",
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content="hello"),
                finish_reason="stop",
            )
        ],
    )
    after = int(time.time())

    assert isinstance(resp.created, int)
    assert before <= resp.created <= after

    # 명시적 값 전달 시 해당 값 보존
    custom_created = 1700000000
    resp_custom = ChatCompletionResponse(
        id="chatcmpl-test-custom",
        created=custom_created,
        model="claude/claude-sonnet-4-6",
        choices=[],
    )
    assert resp_custom.created == custom_created


# ── REQ-111-003: ErrorDetail.code str 타입 검증 ──

def test_error_detail_code_is_string():
    """ErrorDetail.code 타입이 str이며 문자열 코드로 반환되는지 검증 (REQ-111-003)."""
    # 1. 기본값 검증
    err_default = ErrorDetail(message="Bad request")
    assert isinstance(err_default.code, str)
    assert err_default.code == "invalid_request_error"

    # 2. 커스텀 문자열 에러 코드 전달
    err_proxy = ErrorDetail(
        message="Upstream gateway error",
        type="proxy_error",
        code="proxy_error",
    )
    assert isinstance(err_proxy.code, str)
    assert err_proxy.code == "proxy_error"

    err_auth = ErrorDetail(
        message="Invalid token",
        type="authentication_error",
        code="authentication_error",
    )
    assert isinstance(err_auth.code, str)
    assert err_auth.code == "authentication_error"

    # 3. ErrorResponse 직렬화 후 code 타입 확인
    resp = ErrorResponse(error=err_proxy)
    dumped = resp.model_dump()
    assert isinstance(dumped["error"]["code"], str)
    assert dumped["error"]["code"] == "proxy_error"


# ── REQ-111-004: ChatMessage.name 필드 및 content_as_str 검증 ──

def test_chat_message_name_field():
    """ChatMessage에 name 필드가 기본 None으로 존재하고, 값 설정 시 보존되는지 검증 (REQ-111-004)."""
    # 기본값 None
    msg_def = ChatMessage(role="user", content="hi")
    assert msg_def.name is None

    # 명시적 설정
    msg_named = ChatMessage(role="user", content="hi", name="tester_alice")
    assert msg_named.name == "tester_alice"

    # 직렬화 검증
    dumped = msg_named.model_dump()
    assert dumped["name"] == "tester_alice"


def test_chat_message_content_as_str_preserved():
    """기존 content_as_str() 동작이 깨지지 않고 보존되는지 검증 (REQ-111-004 / BUG-057 회귀 방지)."""
    # 1. 문자열 content
    msg_str = ChatMessage(role="user", content="Plain text")
    assert msg_str.content_as_str() == "Plain text"

    # 2. content parts list (text + image_url)
    msg_list = ChatMessage(
        role="user",
        content=[
            {"type": "text", "text": "Part 1"},
            {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
            {"type": "text", "text": "Part 2"},
        ],
    )
    expected = "Part 1\n[image_url]\nPart 2"
    assert msg_list.content_as_str() == expected

    # 3. None content
    msg_none = ChatMessage(role="assistant", content=None)
    assert msg_none.content_as_str() == ""


# ── REQ-111-005: BaseProvider._warn_unsupported 미지원 필드 경고 검증 ──

def test_warn_unsupported_with_unsupported_fields(caplog):
    """Provider가 처리하지 못하는 필드가 요청에 있으면 logger.warning으로 1회 기록되는지 검증 (REQ-111-005)."""
    supported = {"model", "messages", "temperature", "max_tokens"}

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hello")],
        top_p=0.9,
        seed=42,
        presence_penalty=0.8,
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        unsupported = BaseProvider._warn_unsupported(req, supported)

    assert "top_p" in unsupported
    assert "seed" in unsupported
    assert "presence_penalty" in unsupported
    assert len(unsupported) == 3

    # 요청당 정확히 1회의 warning 로그 기록
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) == 1
    log_msg = warning_records[0].message
    assert "Unsupported parameters" in log_msg
    assert "top_p" in log_msg
    assert "seed" in log_msg
    assert "presence_penalty" in log_msg
    assert "claude/claude-sonnet-4-6" in log_msg


def test_warn_unsupported_no_warning_when_all_supported(caplog):
    """모든 요청 파라미터가 지원될 때 경고가 발생하지 않는지 검증 (REQ-111-005)."""
    supported = {"model", "messages", "temperature", "max_tokens"}

    req = ChatCompletionRequest(
        model="claude/claude-sonnet-4-6",
        messages=[ChatMessage(role="user", content="hello")],
        temperature=0.7,
        max_tokens=2048,
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        unsupported = BaseProvider._warn_unsupported(req, supported)

    assert unsupported == []
    assert len(caplog.records) == 0


def test_warn_unsupported_none_fields_not_flagged(caplog):
    """신규 필드가 기본값(None)인 경우 미지원 집합에 없더라도 경고하지 않는지 검증 (REQ-111-005)."""
    supported = {"model", "messages"}

    # 모든 추가 필드가 None인 기본 요청
    req = ChatCompletionRequest(
        model="gemini/gemini-3-pro-preview",
        messages=[ChatMessage(role="user", content="test")],
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        unsupported = BaseProvider._warn_unsupported(req, supported)

    assert unsupported == []
    assert len(caplog.records) == 0


def test_warn_unsupported_stream_default_false_not_flagged(caplog):
    """stream=False가 기본값이고 명시적으로 지정되지 않은 경우 경고 대상에서 제외되는지 검증 (REQ-111-005)."""
    supported = {"model", "messages"}

    req = ChatCompletionRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="test")],
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        unsupported = BaseProvider._warn_unsupported(req, supported)

    assert "stream" not in unsupported
    assert len(caplog.records) == 0


# ── MAJOR-1 / REQ-111-006: 미지정 최상위 필드 보존 및 _warn_unsupported 검증 ──

def test_chat_completion_request_extra_fields_preserved():
    """스키마에 정의되지 않은 필드(reasoning_effort 등)가 model_extra에 온전히 보존되는지 검증 (REQ-111-006, MAJOR-1)."""
    data = {
        "model": "claude/claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hello"}],
        "reasoning_effort": "high",
        "custom_metadata": {"trace_id": "abc-123"},
    }
    req = ChatCompletionRequest.model_validate(data)

    assert req.model_extra is not None
    assert req.model_extra.get("reasoning_effort") == "high"
    assert req.model_extra.get("custom_metadata") == {"trace_id": "abc-123"}


def test_warn_unsupported_flags_model_extra(caplog):
    """model_extra에 존재하는 미지원 필드가 _warn_unsupported에서 감지되고 경고가 남는지 검증 (REQ-111-006, MAJOR-1)."""
    supported = {"model", "messages", "temperature"}
    data = {
        "model": "claude/claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.7,
        "reasoning_effort": "high",
    }
    req = ChatCompletionRequest.model_validate(data)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        unsupported = BaseProvider._warn_unsupported(req, supported)

    assert "reasoning_effort" in unsupported
    assert len(caplog.records) == 1
    assert "reasoning_effort" in caplog.records[0].message


# ── MAJOR-3 / REQ-111-008: 숫자 및 파라미터 유효성/범위 검증 ──

def test_field_range_validation_temperature():
    """temperature 범위 검증 (0.0 ~ 2.0) (REQ-111-008, MAJOR-3)."""
    # 유효 경계값
    req_0 = ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], temperature=0.0)
    assert req_0.temperature == 0.0
    req_2 = ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], temperature=2.0)
    assert req_2.temperature == 2.0

    # 범위 초과
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], temperature=-0.1)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], temperature=2.1)


def test_field_range_validation_top_p():
    """top_p 범위 검증 (0.0 ~ 1.0) (REQ-111-008, MAJOR-3)."""
    req_0 = ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], top_p=0.0)
    assert req_0.top_p == 0.0
    req_1 = ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], top_p=1.0)
    assert req_1.top_p == 1.0

    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], top_p=-0.01)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], top_p=1.01)


def test_field_range_validation_n():
    """n 범위 검증 (ge=1) (REQ-111-008, MAJOR-3)."""
    req = ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], n=1)
    assert req.n == 1

    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], n=0)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], n=-1)


def test_field_range_validation_max_tokens():
    """max_tokens 범위 검증 (ge=1) (REQ-111-008, MAJOR-3)."""
    req = ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], max_tokens=1)
    assert req.max_tokens == 1

    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], max_tokens=0)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], max_tokens=-5)


def test_field_range_validation_penalties():
    """presence_penalty 및 frequency_penalty 범위 검증 (-2.0 ~ 2.0) (REQ-111-008, MAJOR-3)."""
    req = ChatCompletionRequest(
        model="m",
        messages=[ChatMessage(role="user", content="h")],
        presence_penalty=-2.0,
        frequency_penalty=2.0,
    )
    assert req.presence_penalty == -2.0
    assert req.frequency_penalty == 2.0

    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], presence_penalty=-2.1)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], presence_penalty=2.1)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], frequency_penalty=-2.1)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], frequency_penalty=2.1)


def test_field_range_validation_top_logprobs_and_logprobs():
    """top_logprobs 범위 (0~20) 및 logprobs=True 의존성 검증 (REQ-111-008, MAJOR-3)."""
    # logprobs=True 이고 top_logprobs가 0~20 사이인 경우 성공
    req = ChatCompletionRequest(
        model="m",
        messages=[ChatMessage(role="user", content="h")],
        logprobs=True,
        top_logprobs=5,
    )
    assert req.logprobs is True
    assert req.top_logprobs == 5

    # top_logprobs 범위 초과 (-1, 21)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], logprobs=True, top_logprobs=-1)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], logprobs=True, top_logprobs=21)

    # top_logprobs가 지정되었으나 logprobs가 True가 아닌 경우 (None 또는 False) -> 실패
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], top_logprobs=5)
    with pytest.raises(ValidationError):
        ChatCompletionRequest(model="m", messages=[ChatMessage(role="user", content="h")], logprobs=False, top_logprobs=5)

    # logprobs=True 이고 top_logprobs는 None인 경우 -> 성공
    req_only_logprobs = ChatCompletionRequest(
        model="m",
        messages=[ChatMessage(role="user", content="h")],
        logprobs=True,
    )
    assert req_only_logprobs.logprobs is True


def test_stop_list_max_length_validation():
    """stop 파라미터가 리스트일 때 최대 4개 제한 검증 (문자열은 길이 제한 없음) (REQ-111-008, MAJOR-3)."""
    # 문자열은 길이 제한 없음
    req_str = ChatCompletionRequest(
        model="m",
        messages=[ChatMessage(role="user", content="h")],
        stop="very_long_stop_sequence_longer_than_four_characters",
    )
    assert req_str.stop == "very_long_stop_sequence_longer_than_four_characters"

    # 4개 이하 리스트 성공
    req_4 = ChatCompletionRequest(
        model="m",
        messages=[ChatMessage(role="user", content="h")],
        stop=["s1", "s2", "s3", "s4"],
    )
    assert len(req_4.stop) == 4

    # 5개 리스트 실패
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            model="m",
            messages=[ChatMessage(role="user", content="h")],
            stop=["s1", "s2", "s3", "s4", "s5"],
        )


# ── MINOR-8 / REQ-111-009: 경고 메시지 로그 인젝션 방지 검증 ──

# ── MINOR-8 / REQ-111-009, REQ-111-017: 경고 메시지 로그 인젝션 방지 검증 ──

def test_warn_unsupported_log_injection_sanitization(caplog):
    """제어문자 이스케이프 및 100자 길이 제한으로 로그 인젝션이 방지되는지 검증 (REQ-111-009, MINOR-8)."""
    supported = {"model", "messages"}

    # 개행 문자 및 가짜 로그 주입 시도
    evil_model = "gemini/test\n[ERROR] forged error message\r\n[CRITICAL] hacked"
    req = ChatCompletionRequest.model_validate({
        "model": evil_model,
        "messages": [{"role": "user", "content": "hi"}],
        "evil\nparam": "value",
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        BaseProvider._warn_unsupported(req, supported)

    proxy_records = [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]
    assert len(proxy_records) == 1
    log_msg = proxy_records[0].message

    # 실제 개행 문자가 없어야 함 (한 줄 로그 유지)
    assert "\n" not in log_msg
    assert "\r" not in log_msg
    # 이스케이프된 문자열로 존재
    assert "\\n" in log_msg

    # 100자 초과 모델명 잘림 검증
    super_long_model = "a" * 150
    req_long = ChatCompletionRequest.model_validate({
        "model": super_long_model,
        "messages": [{"role": "user", "content": "hi"}],
        "extra_field": 1,
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        BaseProvider._warn_unsupported(req_long, supported)

    proxy_records = [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]
    assert len(proxy_records) == 1
    long_log = proxy_records[0].message
    assert "..." in long_log
    # 150개 연속 a가 로그에 그대로 나오지 않음
    assert ("a" * 150) not in long_log


def test_warn_unsupported_unicode_control_characters_escaped(caplog):
    """
    유니코드 줄/문단 구분자(U+2028, U+2029, U+0085), 방향제어문자(U+202A~202E, U+2066~2069),
    Cf 포맷 문자 이스케이프 및 전체 메시지 500자 상한 검증 (REQ-111-017, MINOR-4).
    """
    supported = {"model", "messages"}

    # codex 2차 리뷰 재현 문자: "x\u2028[ERROR] forged\u202E", U+0085, U+2029, U+2066
    unicode_evil_key = "x\u2028[ERROR] forged\u202E"
    unicode_model = "model\u2029test\u0085dir\u2066bidi\u2069"

    req = ChatCompletionRequest.model_validate({
        "model": unicode_model,
        "messages": [{"role": "user", "content": "hi"}],
        unicode_evil_key: "value",
        "format\u200bzero_width": "cf_char",
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        BaseProvider._warn_unsupported(req, supported)

    proxy_records = [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]
    assert len(proxy_records) == 1
    log_msg = proxy_records[0].message

    # 원시 유니코드 제어문자가 남아있지 않아야 함
    assert "\u2028" not in log_msg
    assert "\u2029" not in log_msg
    assert "\u0085" not in log_msg
    assert "\u202e" not in log_msg
    assert "\u2066" not in log_msg
    assert "\u2069" not in log_msg
    assert "\u200b" not in log_msg

    # 올바르게 이스케이프 문자열로 존재
    assert "\\u2028" in log_msg
    assert "\\u202e" in log_msg
    assert "\\u2029" in log_msg
    assert "\\u0085" in log_msg

    # 전체 경고 메시지 길이 500자 이하 상한 보장
    assert len(log_msg) <= 500

    # 초대형 필드 목록으로 500자 초과 시 잘림 검증
    huge_extra = {f"extra_key_{i:03d}_{'k'*15}": i for i in range(50)}
    req_huge = ChatCompletionRequest.model_validate({
        "model": "test-huge-fields",
        "messages": [{"role": "user", "content": "hi"}],
        **huge_extra,
    })

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        BaseProvider._warn_unsupported(req_huge, supported)

    proxy_records_huge = [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]
    assert len(proxy_records_huge) == 1
    huge_log = proxy_records_huge[0].message
    assert len(huge_log) <= 500
    assert huge_log.endswith("...")


# ── MAJOR-2 / REQ-111-010, REQ-111-018: 미지원 필드 계산과 로그 중복 억제 분리 검증 ──

def test_warn_unsupported_deduplication(caplog):
    """
    동일 요청 객체에 대해:
    1) 반환 목록은 호출될 때마다 항상 정확히 계산 (REQ-111-018, MINOR-5)
    2) 로그 중복 억제는 1회만 발생
    """
    supported = {"model", "messages"}
    req = ChatCompletionRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="hi")],
        temperature=0.7,  # 미지원
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        first_call = BaseProvider._warn_unsupported(req, supported)
        second_call = BaseProvider._warn_unsupported(req, supported)

    # 반환 목록은 매번 정확하게 계산됨
    assert first_call == ["temperature"]
    assert second_call == ["temperature"]
    # 로그는 정확히 1회만 기록
    proxy_records = [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]
    assert len(proxy_records) == 1


def test_warn_unsupported_calculation_separate_from_log_suppression(caplog):
    """
    codex 2차 리뷰 재현 케이스:
    미지원 필드 없이 검사 -> []. 같은 객체에 seed=42 추가 후 다시 검사 -> ["seed"] 반환 및 경고 발생 (REQ-111-018, MINOR-5).
    """
    supported = {"model", "messages"}
    req = ChatCompletionRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="hi")],
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        first_call = BaseProvider._warn_unsupported(req, supported)

    assert first_call == []
    proxy_records = [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]
    assert len(proxy_records) == 0

    # 동일 객체에 seed=42 추가 후 재검사
    req.seed = 42
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        second_call = BaseProvider._warn_unsupported(req, supported)

    # 미지원 필드가 정확히 계산되어 반환되고, 경고 로그도 정상 발생
    assert second_call == ["seed"]
    proxy_records_after = [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]
    assert len(proxy_records_after) == 1
    assert "seed" in proxy_records_after[0].message


def test_warn_unsupported_provider_isolated_suppression(caplog):
    """
    폴백 라우팅 대비: 동일 요청에 대해 다른 Provider가 검사 시 각각 1회씩 경고 발생 (REQ-111-018).
    """
    req = ChatCompletionRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="hi")],
        temperature=0.7,
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="ai-proxy"):
        # ProviderA 검사
        res_a1 = BaseProvider._warn_unsupported(req, {"model", "messages"}, provider_name="ProviderA")
        res_a2 = BaseProvider._warn_unsupported(req, {"model", "messages"}, provider_name="ProviderA")
        # ProviderB 검사 (폴백 상황)
        res_b1 = BaseProvider._warn_unsupported(req, {"model", "messages"}, provider_name="ProviderB")

    assert res_a1 == ["temperature"]
    assert res_a2 == ["temperature"]
    assert res_b1 == ["temperature"]

    # ProviderA 1회 + ProviderB 1회 = 총 2회 기록
    proxy_records = [r for r in caplog.records if r.name == "ai-proxy" and r.levelno == logging.WARNING]
    assert len(proxy_records) == 2


# ── NIT-9 / REQ-111-003: 상태 코드 -> OpenAI 에러 코드 매핑 테이블 검증 ──

def test_proxy_server_status_code_mapping():
    """proxy_server의 상태 코드 매핑 딕셔너리 상수 및 기본값 검증 (REQ-111-003, NIT-9)."""
    from proxy_server import DEFAULT_ERROR_CODE, STATUS_CODE_TO_ERROR_CODE

    assert STATUS_CODE_TO_ERROR_CODE[400] == "invalid_request_error"
    assert STATUS_CODE_TO_ERROR_CODE[401] == "authentication_error"
    assert STATUS_CODE_TO_ERROR_CODE[404] == "not_found_error"
    assert STATUS_CODE_TO_ERROR_CODE[429] == "rate_limit_error"
    assert DEFAULT_ERROR_CODE == "proxy_error"
    assert STATUS_CODE_TO_ERROR_CODE.get(500, DEFAULT_ERROR_CODE) == "proxy_error"


# ── MINOR-3 해소 증명: 422 RequestValidationError -> OpenAI 에러 계약 검증 (REQ-111-020) ──

def test_validation_error_openai_error_format():
    """
    TASK-CORE-3에서 추가된 RequestValidationError 핸들러에 의해,
    top_p=-1 등 유효성 검증 실패 시 422 상태 코드 및 OpenAI 형식 최상위 error 객체가 반환됨을 증명.
    """
    from starlette.testclient import TestClient
    from proxy_server import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/v1/chat/completions", json={
        "model": "gemini/gemini-3-pro-preview",
        "messages": [{"role": "user", "content": "hi"}],
        "top_p": -1.0,  # 0.0 ~ 1.0 범위 위반
    })

    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    err = data["error"]
    assert "message" in err
    assert err["type"] == "invalid_request_error"
    assert err["code"] == "invalid_request_error"
