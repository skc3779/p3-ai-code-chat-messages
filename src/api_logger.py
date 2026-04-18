"""
ApiLogger - API 요청/응답 JSON 파일 로깅 공통 모듈

FSD v1.0.064 / REQ-064-001~006

각 모델(Claude, Gemini, GenAI) API 호출 시 Request Header, Body와 Response를
JSON 파일로 저장하여 디버깅 및 장애 분석에 활용한다.

- logs/{provider}/ 폴더에 JSON 파일 생성
- 파일명: {provider}-{YYYYMMDDHHMMSS}-{UUID}-request.json
          {provider}-{YYYYMMDDHHMMSS}-{UUID}-response.json
- .env의 {PROVIDER}_AI_LOG_ENABLED 플래그로 켜기/끄기 제어 (단, GenAI는 GEN_AI_LOG_ENABLED)
"""

import os
import json
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class ApiLogger:
    """
    API 요청/응답을 JSON 파일로 로깅하는 공통 모듈.

    사용법:
        logger = ApiLogger("claude", workspace_dir=".")
        log_id = logger.log_request(api_url, headers, body, streaming, model_id)
        logger.log_response(log_id, status_code, streaming, ...)
    """

    def __init__(self, provider: str, workspace_dir: str = "."):
        """
        REQ-064-001: API 로거 초기화.

        Args:
            provider: 제공자 이름 ("claude", "gemini", "gen-ai")
            workspace_dir: 프로젝트 루트 디렉토리 (logs 폴더의 기준 경로)
        """
        self.provider = provider
        self.workspace_dir = Path(workspace_dir)
        self.enabled = self._check_enabled()
        self.log_dir = self.workspace_dir / f"logs/{self.provider}"

        # REQ-062-002, NREQ-062-003: 로그 폴더 자동 생성
        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def _check_enabled(self) -> bool:
        """
        REQ-064-002: 환경변수를 확인하여 로깅 활성화 여부 반환.

        - gen-ai -> GEN_AI_LOG_ENABLED
        - claude -> CLAUDE_AI_LOG_ENABLED
        - gemini -> GEMINI_AI_LOG_ENABLED
        
        지원 값: true, 1, yes (대소문자 무관)
        기본값: false (미설정 시)
        """
        if self.provider == "gen-ai":
            env_key = "GEN_AI_LOG_ENABLED"
        else:
            env_key = f"{self.provider.replace('-', '_').upper()}_AI_LOG_ENABLED"
            
        value = os.getenv(env_key, "false")
        return value.lower() in ("true", "1", "yes")

    @staticmethod
    def _generate_log_id() -> str:
        """REQ-062-005: 고유 로그 ID 생성 (YYYYMMDDHHMMSS-UUID 8자리)."""
        ts = ApiLogger._get_file_timestamp()
        uid = uuid.uuid4().hex[:8]
        return f"{ts}-{uid}"

    @staticmethod
    def _get_timestamp() -> str:
        """현재 시각을 ISO 형식 문자열로 반환."""
        return datetime.now().astimezone().isoformat()

    @staticmethod
    def _get_file_timestamp() -> str:
        """파일명용 타임스탬프 (YYYYMMDDHHMMSS)."""
        return datetime.now().strftime("%Y%m%d%H%M%S")

    @staticmethod
    def _mask_headers(headers: Dict) -> Dict:
        """
        REQ-062-007: 보안 - Secret 헤더 값을 마스킹.

        키 이름에 'secret'이 포함된 헤더의 값을 ***MASKED***로 치환한다.
        """
        masked = dict(headers)
        for key in masked:
            if "secret" in key.lower():
                masked[key] = "***MASKED***"
        return masked

    def _save_log(self, filename: str, data: dict) -> Optional[str]:
        """
        NREQ-062-004: JSON 로그 파일 저장.
        NREQ-062-002: 저장 실패 시 API 호출을 방해하지 않음.

        Returns:
            저장된 파일 경로 (비활성화 또는 실패 시 None)
        """
        if not self.enabled:
            return None

        try:
            filepath = self.log_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            return str(filepath)
        except Exception:
            # NREQ-062-002: 로그 저장 실패가 API 호출을 방해하지 않도록 함
            return None

    def log_request(self, api_url: str, headers: Dict, body: Dict,
                    streaming: bool, model_id: str,
                    log_id: str = None) -> str:
        """
        REQ-062-003 / REQ-064-005,006: Request 로그를 JSON 파일로 저장.

        파일명: {provider}-{YYYYMMDDHHMMSS}-{UUID}-request.json

        Args:
            api_url: API 엔드포인트 URL
            headers: 요청 헤더 (Secret은 마스킹됨)
            body: 요청 본문
            streaming: 스트리밍 모드 여부
            model_id: 모델 ID
            log_id: 기존 로그 ID (없으면 신규 생성)

        Returns:
            log_id: 동일 요청-응답 쌍을 연결하는 고유 ID
        """
        if not log_id:
            log_id = self._generate_log_id()

        if not self.enabled:
            return log_id

        # log_id 형식은 {YYYYMMDDHHMMSS}-{UUID}
        filename = f"{self.provider}-{log_id}-request.json"

        data = {
            "log_type": "request",
            "log_id": log_id,
            "timestamp": self._get_timestamp(),
            "api_url": api_url,
            "method": "POST",
            "headers": self._mask_headers(headers),
            "body": body,
            "streaming": streaming,
            "model_id": model_id,
        }

        self._save_log(filename, data)
        return log_id

    def log_response(self, log_id: str, status_code: int,
                     streaming: bool, response_body: dict = None,
                     assembled_content: str = None,
                     chunk_count: int = 0,
                     elapsed_ms: int = 0) -> Optional[str]:
        """
        REQ-062-004 / REQ-064-005,006: Response 로그를 JSON 파일로 저장.

        파일명: {provider}-{YYYYMMDDHHMMSS}-{UUID}-response.json

        Args:
            log_id: 요청과 동일한 고유 ID
            status_code: HTTP 상태 코드
            streaming: 스트리밍 모드 여부
            response_body: 논스트리밍 응답 본문 (dict)
            assembled_content: 스트리밍 조립된 응답 텍스트
            chunk_count: 스트리밍 청크 수
            elapsed_ms: API 호출 소요 시간 (밀리초)

        Returns:
            저장된 파일 경로 (비활성화 시 None)
        """
        if not self.enabled:
            return None

        filename = f"{self.provider}-{log_id}-response.json"

        data = {
            "log_type": "response",
            "log_id": log_id,
            "timestamp": self._get_timestamp(),
            "status_code": status_code,
            "streaming": streaming,
            "elapsed_ms": elapsed_ms,
        }

        if streaming:
            data["assembled_content"] = assembled_content
            data["chunk_count"] = chunk_count
        else:
            data["response_body"] = response_body

        return self._save_log(filename, data)
