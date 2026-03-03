"""
GenAIApiLogger 단위 테스트

FSD v1.0.062 테스트 케이스:
- TC-062-001: GEN_AI_LOG_ENABLED=true일 때 Request 로그 생성
- TC-062-002: GEN_AI_LOG_ENABLED=true일 때 Response 로그 생성
- TC-062-003: GEN_AI_LOG_ENABLED=false일 때 로그 미생성
- TC-062-004: 환경변수 미설정 시 기본값 false
- TC-062-005: Request-Response 쌍 UUID 동일
- TC-062-006: Secret 헤더 마스킹
- TC-062-007: logs/gen-ai/ 폴더 자동 생성
- TC-062-008: 스트리밍 응답 chunk_count 기록
- TC-062-009: elapsed_ms 기록
- TC-062-010: JSON 형식 검증
- TC-062-011: 파일명 패턴 검증 (gen-ai-{UUID}-request/response-{TS}.json)
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.api_logger import ApiLogger


class TestGenAIApiLogger(unittest.TestCase):
    """GenAIApiLogger 단위 테스트"""

    def setUp(self):
        """테스트용 임시 디렉토리 생성"""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """테스트용 임시 디렉토리 삭제"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _make_logger(self, enabled: str = "true"):
        """테스트용 로거 생성 (환경변수 mock)"""
        with patch.dict(os.environ, {"GEN_AI_LOG_ENABLED": enabled}):
            return ApiLogger(provider="gen-ai", workspace_dir=self.test_dir)

    def _sample_headers(self):
        return {
            "X-Lego-Client-Id": "TEST_CLIENT",
            "X-Lego-Client-Secret": "super_secret_value",
            "Content-Type": "application/json"
        }

    def _sample_body(self):
        return {
            "modelIds": ["gpt-oss-120B-medium"],
            "contents": ["[User Context]\nhello"],
            "llmConfig": {"temperature": 0.4},
            "isStream": True,
            "systemPrompt": "You are a helpful assistant."
        }

    # ── TC-062-001: Request 로그 생성 ──

    def test_log_request_creates_file(self):
        """GEN_AI_LOG_ENABLED=true일 때 Request 로그 파일 생성"""
        logger = self._make_logger("true")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body=self._sample_body(),
            streaming=True,
            model_id="gpt-oss-120B-medium"
        )

        # 파일이 생성되었는지 확인
        log_files = list(logger.log_dir.glob("gen-ai-*-request-*.json"))
        self.assertEqual(len(log_files), 1)
        self.assertIn(log_id, log_files[0].name)

    # ── TC-062-002: Response 로그 생성 ──

    def test_log_response_creates_file(self):
        """GEN_AI_LOG_ENABLED=true일 때 Response 로그 파일 생성"""
        logger = self._make_logger("true")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body=self._sample_body(),
            streaming=False,
            model_id="gpt-oss-120B-medium"
        )
        logger.log_response(
            log_id=log_id,
            status_code=200,
            streaming=False,
            response_body={"content": "Hello!"},
            elapsed_ms=1000
        )

        log_files = list(logger.log_dir.glob("gen-ai-*-response-*.json"))
        self.assertEqual(len(log_files), 1)
        self.assertIn(log_id, log_files[0].name)

    # ── TC-062-003: GEN_AI_LOG_ENABLED=false ──

    def test_disabled_no_files(self):
        """GEN_AI_LOG_ENABLED=false일 때 파일 미생성"""
        logger = self._make_logger("false")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body=self._sample_body(),
            streaming=True,
            model_id="test-model"
        )
        logger.log_response(
            log_id=log_id,
            status_code=200,
            streaming=True,
            assembled_content="test",
            chunk_count=5,
            elapsed_ms=500
        )

        # log_dir이 생성되지 않았거나 파일이 없어야 함
        log_dir = logger.log_dir
        if log_dir.exists():
            files = list(log_dir.glob("*.json"))
            self.assertEqual(len(files), 0)

    # ── TC-062-004: 환경변수 미설정 시 기본값 false ──

    def test_default_disabled(self):
        """환경변수 미설정 시 disabled"""
        with patch.dict(os.environ, {}, clear=True):
            # GEN_AI_LOG_ENABLED가 없으므로 기본값 false
            if "GEN_AI_LOG_ENABLED" in os.environ:
                del os.environ["GEN_AI_LOG_ENABLED"]
            logger = ApiLogger(provider="gen-ai", workspace_dir=self.test_dir)
            self.assertFalse(logger.enabled)

    # ── TC-062-005: Request-Response UUID 동일 ──

    def test_same_log_id(self):
        """Request-Response 쌍이 같은 log_id 공유"""
        logger = self._make_logger("true")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body=self._sample_body(),
            streaming=True,
            model_id="test-model"
        )
        logger.log_response(
            log_id=log_id,
            status_code=200,
            streaming=True,
            assembled_content="response",
            chunk_count=1,
            elapsed_ms=100
        )

        req_files = list(logger.log_dir.glob(f"gen-ai-{log_id}-request-*.json"))
        resp_files = list(logger.log_dir.glob(f"gen-ai-{log_id}-response-*.json"))
        self.assertEqual(len(req_files), 1)
        self.assertEqual(len(resp_files), 1)

    # ── TC-062-006: Secret 헤더 마스킹 ──

    def test_secret_masked(self):
        """Secret 헤더 값이 마스킹됨"""
        logger = self._make_logger("true")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body=self._sample_body(),
            streaming=True,
            model_id="test-model"
        )

        req_files = list(logger.log_dir.glob(f"gen-ai-{log_id}-request-*.json"))
        with open(req_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["headers"]["X-Lego-Client-Secret"], "***MASKED***")
        self.assertEqual(data["headers"]["X-Lego-Client-Id"], "TEST_CLIENT")

    # ── TC-062-007: 폴더 자동 생성 ──

    def test_log_dir_auto_created(self):
        """logs/gen-ai/ 폴더 자동 생성"""
        logger = self._make_logger("true")
        self.assertTrue(logger.log_dir.exists())
        self.assertTrue(logger.log_dir.is_dir())

    # ── TC-062-008: 스트리밍 chunk_count ──

    def test_streaming_chunk_count(self):
        """스트리밍 응답 chunk_count 기록"""
        logger = self._make_logger("true")
        log_id = logger._generate_log_id()
        logger.log_response(
            log_id=log_id,
            status_code=200,
            streaming=True,
            assembled_content="test content",
            chunk_count=42,
            elapsed_ms=5000
        )

        resp_files = list(logger.log_dir.glob(f"gen-ai-{log_id}-response-*.json"))
        with open(resp_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["chunk_count"], 42)
        self.assertEqual(data["streaming"], True)
        self.assertIn("assembled_content", data)

    # ── TC-062-009: elapsed_ms 기록 ──

    def test_elapsed_ms(self):
        """elapsed_ms 기록 확인"""
        logger = self._make_logger("true")
        log_id = logger._generate_log_id()
        logger.log_response(
            log_id=log_id,
            status_code=200,
            streaming=False,
            response_body={"content": "test"},
            elapsed_ms=3250
        )

        resp_files = list(logger.log_dir.glob(f"gen-ai-{log_id}-response-*.json"))
        with open(resp_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["elapsed_ms"], 3250)

    # ── TC-062-010: JSON 형식 검증 ──

    def test_valid_json_format(self):
        """유효한 JSON, UTF-8, indent=2 형식"""
        logger = self._make_logger("true")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body={"contents": ["한글 테스트"]},
            streaming=True,
            model_id="test-model"
        )

        req_files = list(logger.log_dir.glob(f"gen-ai-{log_id}-request-*.json"))
        content = req_files[0].read_text(encoding="utf-8")

        # indent=2 확인 (들여쓰기 존재)
        self.assertIn("  ", content)

        # ensure_ascii=False 확인 (한글이 유니코드 이스케이프 없이 존재)
        self.assertIn("한글 테스트", content)

        # 유효한 JSON
        data = json.loads(content)
        self.assertIsInstance(data, dict)

    # ── TC-062-011: 파일명 패턴 검증 ──

    def test_filename_pattern(self):
        """파일명이 gen-ai-{UUID}-request/response-{TS}.json 패턴"""
        logger = self._make_logger("true")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body=self._sample_body(),
            streaming=True,
            model_id="test-model"
        )
        logger.log_response(
            log_id=log_id,
            status_code=200,
            streaming=True,
            assembled_content="test",
            chunk_count=1,
            elapsed_ms=100
        )

        req_files = list(logger.log_dir.glob("gen-ai-*-request-*.json"))
        resp_files = list(logger.log_dir.glob("gen-ai-*-response-*.json"))

        # 파일명에 UUID가 request/response 앞에 위치
        req_name = req_files[0].name
        self.assertTrue(req_name.startswith(f"gen-ai-{log_id}-request-"))
        self.assertTrue(req_name.endswith(".json"))

        resp_name = resp_files[0].name
        self.assertTrue(resp_name.startswith(f"gen-ai-{log_id}-response-"))
        self.assertTrue(resp_name.endswith(".json"))

    # ── TC-062-012: Request 로그 내용 검증 ──

    def test_request_log_contents(self):
        """Request 로그 내용 검증 (필수 필드 존재)"""
        logger = self._make_logger("true")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body=self._sample_body(),
            streaming=True,
            model_id="gpt-oss-120B-medium"
        )

        req_files = list(logger.log_dir.glob(f"gen-ai-{log_id}-request-*.json"))
        with open(req_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["log_type"], "request")
        self.assertEqual(data["log_id"], log_id)
        self.assertEqual(data["method"], "POST")
        self.assertEqual(data["api_url"], "https://example.com/api")
        self.assertEqual(data["streaming"], True)
        self.assertEqual(data["model_id"], "gpt-oss-120B-medium")
        self.assertIn("timestamp", data)
        self.assertIn("headers", data)
        self.assertIn("body", data)

    # ── TC-062-013: 논스트리밍 Response 로그 내용 검증 ──

    def test_non_streaming_response_log(self):
        """논스트리밍 Response 로그 내용 검증"""
        logger = self._make_logger("true")
        log_id = logger._generate_log_id()
        logger.log_response(
            log_id=log_id,
            status_code=200,
            streaming=False,
            response_body={"content": "Hello!", "modelId": "gpt-oss-120B-medium"},
            elapsed_ms=2000
        )

        resp_files = list(logger.log_dir.glob(f"gen-ai-{log_id}-response-*.json"))
        with open(resp_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["log_type"], "response")
        self.assertEqual(data["status_code"], 200)
        self.assertEqual(data["streaming"], False)
        self.assertIn("response_body", data)
        self.assertNotIn("assembled_content", data)
        self.assertNotIn("chunk_count", data)

    # ── TC-062-014: _mask_headers 직접 테스트 ──

    def test_mask_headers_direct(self):
        """_mask_headers 헬퍼 직접 테스트"""
        headers = {
            "X-Lego-Client-Id": "APP",
            "X-Lego-Client-Secret": "my_secret_123",
            "Content-Type": "application/json",
            "Authorization-Secret": "another_secret"
        }
        masked = ApiLogger._mask_headers(headers)

        self.assertEqual(masked["X-Lego-Client-Id"], "APP")
        self.assertEqual(masked["X-Lego-Client-Secret"], "***MASKED***")
        self.assertEqual(masked["Content-Type"], "application/json")
        self.assertEqual(masked["Authorization-Secret"], "***MASKED***")

    # ── TC-062-015: 비활성화 시 log_id 반환 ──

    def test_disabled_returns_log_id(self):
        """비활성화 시에도 log_id는 반환 (빈 문자열 아님)"""
        logger = self._make_logger("false")
        log_id = logger.log_request(
            api_url="https://example.com/api",
            headers=self._sample_headers(),
            body=self._sample_body(),
            streaming=True,
            model_id="test-model",
            log_id="custom_id"
        )
        self.assertEqual(log_id, "custom_id")


if __name__ == "__main__":
    unittest.main()
