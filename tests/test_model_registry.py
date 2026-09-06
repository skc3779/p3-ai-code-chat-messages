"""
TASK-CORE-1 / TASK-PROXY 계약 테스트 — 모델 레지스트리 독립 검증.
REQ-111-045: 모델별 최대 출력 토큰 메타데이터 및 get_model_max_output
REQ-111-046: 지원 모델 목록 등록 및 정합성, 중복 키 방지
REQ-111-047: model_registry 분리 및 순환 import 방지, router re-export 동일성
"""

import ast
from collections import Counter
from pathlib import Path
import subprocess
import sys

import pytest

# ai-proxy 디렉토리를 sys.path에 추가 (기존 테스트 방식 준수)
PROXY_DIR = Path(__file__).resolve().parent.parent / "ai-proxy"
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))

import model_registry
import router


# REQ-111-047: model_registry 단독 import 시 providers 패키지 및 router를 로드하지 않는다.
def test_model_registry_isolated_import_does_not_load_providers():
    script = """
import sys
sys.path.insert(0, sys.argv[1])
import model_registry
loaded_providers = [name for name in sys.modules if name == 'providers' or name.startswith('providers.')]
assert not loaded_providers, f"model_registry imported providers: {loaded_providers}"
assert 'router' not in sys.modules, "model_registry imported router"
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(PROXY_DIR)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"


# REQ-111-045: get_model_max_output 이 접두사 포함 ID와 미포함 ID 양쪽을 처리한다.
@pytest.mark.parametrize(
    "prefixed_id,bare_id,expected_limit",
    [
        ("claude/claude-sonnet-4-6", "claude-sonnet-4-6", 65536),
        ("claude/claude-haiku-4-5", "claude-haiku-4-5", 65536),
        ("gemini/gemini-3-pro-preview", "gemini-3-pro-preview", 65536),
        ("gemini/gemini-3-flash-preview", "gemini-3-flash-preview", 65536),
        ("genai/gpt-oss-120B-medium", "gpt-oss-120B-medium", 4096),
        ("genai/glm5.2", "glm5.2", 4096),
    ],
)
def test_get_model_max_output_prefixed_and_unprefixed(prefixed_id, bare_id, expected_limit):
    assert model_registry.get_model_max_output(prefixed_id) == expected_limit
    assert model_registry.get_model_max_output(bare_id) == expected_limit


# REQ-111-045: 알 수 없는 모델 ID 는 default 값을 반환한다.
def test_get_model_max_output_unknown_model_fallback():
    # 기본 default 파라미터는 4096
    assert model_registry.get_model_max_output("nonexistent/unknown-model") == 4096
    assert model_registry.get_model_max_output("completely-unknown") == 4096

    # 명시적 default 파라미터 지정 시 해당 값 반환
    assert model_registry.get_model_max_output("nonexistent/unknown-model", default=8192) == 8192
    assert model_registry.get_model_max_output("bare-unknown", default=1024) == 1024


# REQ-111-046: genai/glm5.2 가 MODEL_METADATA 와 SUPPORTED_MODELS 양쪽에 등록되어 있다.
def test_genai_glm52_registered_in_metadata_and_supported():
    assert "genai/glm5.2" in model_registry.MODEL_METADATA
    assert "genai/glm5.2" in model_registry.SUPPORTED_MODELS

    meta = model_registry.MODEL_METADATA["genai/glm5.2"]
    assert meta["limit"]["output"] == 4096
    assert meta["limit"]["context"] == 128000
    assert model_registry.SUPPORTED_MODELS["genai/glm5.2"] == "Samsung SCI Portal GLM 5.2"


# REQ-111-046: MODEL_METADATA 의 모든 키가 SUPPORTED_MODELS 에도 있다 (정합성).
def test_model_metadata_keys_consistent_with_supported_models():
    missing = set(model_registry.MODEL_METADATA.keys()) - set(model_registry.SUPPORTED_MODELS.keys())
    assert not missing, f"MODEL_METADATA keys missing from SUPPORTED_MODELS: {sorted(missing)}"
    # 양방향 동등성 보장
    assert set(model_registry.MODEL_METADATA.keys()) == set(model_registry.SUPPORTED_MODELS.keys())


# REQ-111-047: router.SUPPORTED_MODELS is model_registry.SUPPORTED_MODELS (동일 객체 re-export)
def test_router_reexports_supported_models_identity():
    assert router.SUPPORTED_MODELS is model_registry.SUPPORTED_MODELS
    assert router.MODEL_METADATA is model_registry.MODEL_METADATA


# REQ-111-047: router.get_model_max_output is model_registry.get_model_max_output
def test_router_reexports_get_model_max_output_identity():
    assert router.get_model_max_output is model_registry.get_model_max_output


# REQ-111-046: ai-proxy/model_registry.py 소스에 중복 딕셔너리 키가 없다 (ast 로 파싱해 키 중복 검사).
def test_model_registry_source_has_no_duplicate_dict_keys():
    source_file = PROXY_DIR / "model_registry.py"
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    found_dicts = 0
    duplicate_errors = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            found_dicts += 1
            key_names = []
            for k in node.keys:
                if k is None:
                    continue  # **kwargs unpacking syntax
                assert isinstance(k, ast.Constant), f"Dict key must be constant literal, got: {ast.dump(k)}"
                key_names.append(k.value)

            counts = Counter(key_names)
            duplicates = [k for k, count in counts.items() if count > 1]
            if duplicates:
                duplicate_errors.append(f"Line {getattr(node, 'lineno', '?')}: duplicate keys {duplicates}")

    assert found_dicts >= 2, f"Expected at least MODEL_METADATA and SUPPORTED_MODELS dicts, found {found_dicts}"
    assert not duplicate_errors, f"Duplicate dictionary keys detected in model_registry.py:\n" + "\n".join(duplicate_errors)
