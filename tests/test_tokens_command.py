import pytest
from src.token_manager import TokenManager
import os


@pytest.fixture(autouse=True)
def reset_token_manager():
    """매 테스트 전/후 TokenManager 초기화"""
    # 저장
    original_max = TokenManager.MAX_MESSAGES_TO_KEEP
    original_default = TokenManager.DEFAULT_MAX_MESSAGES_TO_KEEP
    
    yield
    
    # 복원
    TokenManager.MAX_MESSAGES_TO_KEEP = original_max
    TokenManager.DEFAULT_MAX_MESSAGES_TO_KEEP = original_default


def test_set_max_messages():
    """T-01: set_max_messages(50) 호출 시 값 변경 검증"""
    TokenManager.set_max_messages(50)
    assert TokenManager.MAX_MESSAGES_TO_KEEP == 50

def test_set_max_messages_invalid_zero():
    """T-02: set_max_messages(0) 호출 시 ValueError"""
    with pytest.raises(ValueError, match="1 이상이어야 합니다"):
        TokenManager.set_max_messages(0)

def test_set_max_messages_invalid_negative():
    """T-03: set_max_messages(-1) 호출 시 ValueError"""
    with pytest.raises(ValueError, match="1 이상이어야 합니다"):
        TokenManager.set_max_messages(-1)

def test_reset_max_messages():
    """T-04: reset_max_messages() 호출 시 기본값으로 복원 검증"""
    TokenManager.DEFAULT_MAX_MESSAGES_TO_KEEP = 30
    TokenManager.set_max_messages(50)
    assert TokenManager.MAX_MESSAGES_TO_KEEP == 50
    
    TokenManager.reset_max_messages()
    assert TokenManager.MAX_MESSAGES_TO_KEEP == 30

def test_format_token_report_claude():
    """T-05, T-08: format_token_report() (Claude) 출력 형식 검증"""
    TokenManager.MAX_MESSAGES_TO_KEEP = 30
    report = TokenManager.format_token_report([], max_tokens=150000, platform="Claude")
    
    assert "메시지 수:  0 / 30" in report
    assert "⚙️ 토큰 한계 설정:" in report
    assert "Claude:  150,000 (현재)" in report
    assert "GenAI:   96,000" in report
    assert "Gemini:  786,000" in report

def test_format_token_report_gemini():
    """T-06: format_token_report() (Gemini) 출력 형식 검증"""
    report = TokenManager.format_token_report([], max_tokens=786000, platform="Gemini")
    
    assert "Gemini:  786,000 (현재)" in report
    assert "Claude:  150,000\n" in report

def test_format_token_report_after_set():
    """T-07: set_max_messages() 후 format_token_report() 반영 검증"""
    TokenManager.set_max_messages(10)
    report = TokenManager.format_token_report([], platform="Claude")
    assert "메시지 수:  0 / 10" in report
