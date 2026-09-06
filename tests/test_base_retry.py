"""
TASK-CORE-2 / TASK-PROXY 계약 테스트 — BaseProvider 429 재시도 및 anyio 백엔드 중립 슬립 검증.
REQ-111-020: 429 재시도, ProviderError, 비밀값 마스킹, 공용 메시지 분리
REQ-111-048: anyio.sleep 기반 trio/asyncio 백엔드 중립 429 재시도
"""

import ast
from pathlib import Path
import sys

import anyio
import httpx
import pytest

# ai-proxy 디렉토리를 sys.path에 추가 (기존 테스트 방식 준수)
PROXY_DIR = Path(__file__).resolve().parent.parent / "ai-proxy"
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))

from providers.base import BaseProvider, ProviderError


# REQ-111-048: anyio 기반 asyncio 및 trio 양쪽 백엔드 파라미터화 fixture
@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request):
    """asyncio 및 trio 양쪽 비동기 루프 백엔드에서 테스트 실행을 보장."""
    return request.param


@pytest.fixture
def mock_anyio_sleep(monkeypatch):
    """실제 대기 시간을 제거하고 호출된 지연(delay) 값들을 기록하는 fixture."""
    recorded_delays: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        recorded_delays.append(delay)

    monkeypatch.setattr(anyio, "sleep", _fake_sleep)
    return recorded_delays


# REQ-111-048, REQ-111-020: asyncio와 trio 양쪽 백엔드에서 429 재시도 정상 동작 (trio 루프 크래시 방지).
@pytest.mark.anyio
async def test_base_retry_on_429_success_both_backends(mock_anyio_sleep):
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"error": "Too Many Requests"})
        return httpx.Response(200, json={"result": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test") as client:
        resp = await BaseProvider._retry_on_429(lambda: client.post("/chat", json={"prompt": "hi"}))

    assert resp.status_code == 200
    assert resp.json() == {"result": "ok"}
    assert call_count == 2
    assert mock_anyio_sleep == [2.0]


# REQ-111-020, REQ-111-048: Retry-After 헤더가 있으면 그 값을 delay로 사용한다.
@pytest.mark.anyio
@pytest.mark.parametrize("retry_after_header,expected_delay", [
    ("3", 3.0),
    ("7.5", 7.5),
    ("1", 1.0),
])
async def test_base_retry_respects_retry_after_header(mock_anyio_sleep, retry_after_header, expected_delay):
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": retry_after_header},
                json={"error": "rate limit"},
            )
        return httpx.Response(200, json={"status": "recovered"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test") as client:
        resp = await BaseProvider._retry_on_429(lambda: client.post("/chat", json={"msg": "test"}))

    assert resp.status_code == 200
    assert call_count == 2
    assert mock_anyio_sleep == [expected_delay]


# REQ-111-020, REQ-111-048: Retry-After 가 없으면 지수 백오프(2s, 4s, 8s)를 쓴다.
@pytest.mark.anyio
async def test_base_retry_exponential_backoff_without_retry_after(mock_anyio_sleep):
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return httpx.Response(429, json={"error": f"rate limit attempt {call_count}"})
        return httpx.Response(200, json={"status": "final success"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test") as client:
        resp = await BaseProvider._retry_on_429(
            lambda: client.post("/chat", json={"msg": "test"}),
            max_retries=3,
        )

    assert resp.status_code == 200
    assert call_count == 4
    # RETRY_BASE_DELAY = 2.0: 2.0 * (2^0) = 2.0, 2.0 * (2^1) = 4.0, 2.0 * (2^2) = 8.0
    assert mock_anyio_sleep == [2.0, 4.0, 8.0]


# REQ-111-020, REQ-111-048: Retry-After 가 숫자가 아니면 지수 백오프로 폴백한다.
@pytest.mark.anyio
@pytest.mark.parametrize("invalid_header", [
    "invalid-non-numeric",
    "Wed, 21 Oct 2026 07:28:00 GMT",
    "",
])
async def test_base_retry_fallback_exponential_when_retry_after_invalid(mock_anyio_sleep, invalid_header):
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": invalid_header},
                json={"error": "rate limit"},
            )
        return httpx.Response(200, json={"status": "recovered"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test") as client:
        resp = await BaseProvider._retry_on_429(lambda: client.post("/chat", json={"msg": "test"}))

    assert resp.status_code == 200
    assert call_count == 2
    # 숫자가 아닌 헤더는 ValueError 발생 후 지수 백오프 기본값(2.0)으로 폴백
    assert mock_anyio_sleep == [2.0]


# REQ-111-020: 재시도 소진 시 ProviderError 가 나고 status_code 가 429 다.
@pytest.mark.anyio
async def test_base_retry_exhausted_raises_provider_error_status_429(mock_anyio_sleep):
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, json={"error": f"persistent rate limit {call_count}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test") as client:
        with pytest.raises(ProviderError) as exc_info:
            await BaseProvider._retry_on_429(
                lambda: client.post("/chat", json={"msg": "test"}),
                max_retries=3,
            )

    err = exc_info.value
    assert err.status_code == 429
    # max_retries=3일 때 최초 1회 + 재시도 3회 = 총 4회 시도, sleep은 3회 발생
    assert call_count == 4
    assert mock_anyio_sleep == [2.0, 4.0, 8.0]


# REQ-111-020: ProviderError 의 public_message 에 업스트림 응답 본문이 들어 있지 않다 (자격증명 유출 방지).
@pytest.mark.anyio
async def test_base_retry_provider_error_public_message_does_not_leak_body(mock_anyio_sleep):
    secret_payload = "leak-test-upstream-detail: x-api-key=SECRET123 sensitive data"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            content=secret_payload.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test") as client:
        with pytest.raises(ProviderError) as exc_info:
            await BaseProvider._retry_on_429(
                lambda: client.post("/chat", json={"msg": "test"}),
                max_retries=2,
            )

    err = exc_info.value
    assert err.status_code == 429
    # public_message 에 민감한 업스트림 본문 및 키가 유출되지 않아야 함
    assert "x-api-key=SECRET123" not in err.public_message
    assert "SECRET123" not in err.public_message
    assert "leak-test-upstream-detail" not in err.public_message


# REQ-111-020: 429 가 아닌 4xx/5xx 는 재시도하지 않고 즉시 ProviderError 가 된다.
@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 500, 502, 503])
async def test_base_retry_non_429_fails_immediately_no_retry(mock_anyio_sleep, status_code):
    call_count = 0
    sensitive_content = f"Error details containing x-api-key=SECRET123 on HTTP {status_code}"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            status_code,
            content=sensitive_content.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test") as client:
        with pytest.raises(ProviderError) as exc_info:
            await BaseProvider._retry_on_429(
                lambda: client.post("/chat", json={"msg": "test"}),
                max_retries=3,
            )

    err = exc_info.value
    # 1. 429가 아니므로 재시도 없이 1회 호출 후 즉시 에러 발생
    assert call_count == 1
    # 2. anyio.sleep 은 단 한 번도 호출되지 않음
    assert len(mock_anyio_sleep) == 0
    # 3. status_code 일치
    assert err.status_code == status_code
    # 4. public_message 에 비밀값이 노출되지 않음
    assert "x-api-key=SECRET123" not in err.public_message
    assert "SECRET123" not in err.public_message


# REQ-111-048: base.py 소스에 asyncio 직접 의존이 남아 있지 않다 (소스 문자열 및 AST 검사).
def test_base_source_has_no_asyncio_dependency():
    base_source_path = PROXY_DIR / "providers" / "base.py"
    source_content = base_source_path.read_text(encoding="utf-8")

    # 1. import 구문 검사
    assert "import asyncio" not in source_content, "base.py must not import asyncio"
    assert "from asyncio" not in source_content, "base.py must not import from asyncio"

    # 2. AST 검사: 모듈 임포트 및 실제 식별자 참조에 asyncio가 없어야 함 (주석 외 실제 의존성 검증)
    tree = ast.parse(source_content, filename=str(base_source_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "asyncio", "Found import asyncio in base.py"
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "asyncio" and not (node.module and node.module.startswith("asyncio.")), "Found from asyncio in base.py"
        elif isinstance(node, ast.Name):
            assert node.id != "asyncio", f"Found direct asyncio identifier reference at line {getattr(node, 'lineno', '?')}"

    # 3. anyio 기반 슬립 사용 확인
    assert "import anyio" in source_content, "base.py must import anyio"
    assert "anyio.sleep" in source_content, "base.py must use anyio.sleep"
