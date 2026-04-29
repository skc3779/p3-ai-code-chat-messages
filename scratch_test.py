import os
import tempfile
from unittest.mock import patch
from src.api_logger import ApiLogger

def _make_logger(test_dir, enabled: str = "true"):
    with patch.dict(os.environ, {"GEN_AI_LOG_ENABLED": enabled}):
        return ApiLogger(provider="gen-ai", workspace_dir=test_dir)

def _test():
    with tempfile.TemporaryDirectory() as test_dir:
        logger = _make_logger(test_dir, "true")
        res = logger.log_request('http://api', {}, {}, True, 'test-model')
        print('enabled=', logger.enabled)
        print('log_dir=', logger.log_dir)
        files = list(logger.log_dir.glob('*.json'))
        print('files=', files)

_test()
