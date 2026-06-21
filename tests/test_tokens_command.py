# pyrefly: ignore [missing-import]
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


# ── T-A系: auto_trim_history 이중 75% 방지 테스트 ────────────────────────────


def _history_with_chars(num_chars: int) -> list:
    """num_chars 길이의 단일 user 메시지 히스토리 반환"""
    return [{"role": "user", "content": "x" * num_chars}]


def test_trim_threshold_is_max_tokens_not_075_times_max():
    """T-A01: threshold = max_tokens (이중 75% 없음)

    구버그: token_threshold = int(max_tokens * 0.75) = 7,500
    현재:   token_threshold = max_tokens = 10,000
    7,500 < tokens < 10,000 구간은 트리밍 없어야 한다.
    """
    max_tokens = 10_000
    old_threshold = int(max_tokens * 0.75)        # 7,500 (구버그 기준)
    tokens_in_zone = old_threshold + 500           # 8,000 (구버그면 트리밍됐을 값)
    history = _history_with_chars(int(tokens_in_zone * TokenManager.CHARS_PER_TOKEN))

    result = TokenManager.auto_trim_history(history, max_tokens=max_tokens, verbose=False)
    assert len(result) == 1, "이중 75% 적용 시 이 구간에서 트리밍됨 — 버그 재현"


def test_trim_triggers_when_exceeds_max_tokens():
    """T-A02: 토큰이 max_tokens를 초과하면 트리밍 발동

    MIN_KEEP=2 제약으로 인해 메시지 3개 이상이어야 트리밍 루프가 실행된다.
    """
    max_tokens = 1_000
    # 각 400토큰 × 3개 = 1,200토큰 > 1,000
    msg_chars = int(400 * TokenManager.CHARS_PER_TOKEN)
    history = [
        {"role": "user",      "content": "x" * msg_chars},
        {"role": "assistant", "content": "x" * msg_chars},
        {"role": "user",      "content": "x" * msg_chars},
    ]
    assert TokenManager.count_tokens(history) > max_tokens
    result = TokenManager.auto_trim_history(history, max_tokens=max_tokens, verbose=False)
    assert TokenManager.count_tokens(result) <= max_tokens


def test_no_trim_below_max_tokens():
    """T-A03: 토큰이 max_tokens 이하면 트리밍 없음"""
    max_tokens = 10_000
    # 메시지 1개 → 메시지 수 트리밍 조건(MAX_MESSAGES_TO_KEEP) 미해당
    safe_chars = int(max_tokens * TokenManager.CHARS_PER_TOKEN * 0.90)
    history = _history_with_chars(safe_chars)
    result = TokenManager.auto_trim_history(history, max_tokens=max_tokens, verbose=False)
    assert len(result) == 1


def test_each_provider_default_no_double_75pct():
    """T-A04: 플랫폼별 기본 한도에서 0.75×max_tokens 수준은 트리밍 없음

    이중 75% 적용 시 각 플랫폼의 old_threshold에서 트리밍이 발생했다.
    수정 후에는 max_tokens에 도달할 때까지 트리밍 없어야 한다.

      Claude  구버그 임계: 112,500 (=150,000 × 0.75)  실제 윈도우 대비 56.25%
      GenAI   구버그 임계:  72,000 (= 96,000 × 0.75)  실제 윈도우 대비 56.25%
      Gemini  구버그 임계: 589,500 (=786,000 × 0.75)  실제 윈도우 대비 56.22%
    """
    TokenManager.MAX_MESSAGES_TO_KEEP = 10_000  # 메시지 수 트리밍 무력화

    cases = [
        ("Claude",  TokenManager.MAX_TOKENS_CLAUDE),   # 150,000
        ("GenAI",   TokenManager.MAX_TOKENS_GENAI),    # 96,000
        ("Gemini",  TokenManager.MAX_TOKENS_GEMINI),   # 786,000
    ]
    for name, max_tokens in cases:
        old_threshold = int(max_tokens * 0.75)         # 구버그 임계값
        tokens_just_above_old = old_threshold + 1
        chars = int(tokens_just_above_old * TokenManager.CHARS_PER_TOKEN)
        history = _history_with_chars(chars)
        result = TokenManager.auto_trim_history(history, max_tokens=max_tokens, verbose=False)
        assert len(result) == 1, (
            f"{name}: {tokens_just_above_old:,} 토큰에서 트리밍 발생 "
            f"(이중 75% 버그 — old_threshold={old_threshold:,}, max={max_tokens:,})"
        )


def test_trim_verbose_message_no_75pct_mention(capsys):
    """T-A05: 트리밍 출력 메시지에 '75%' 표현 없음 (수정 후 '한도 초과'로 변경)"""
    max_tokens = 1_000
    half_chars = int((max_tokens + 100) * TokenManager.CHARS_PER_TOKEN // 2)
    history = [
        {"role": "user",      "content": "x" * half_chars},
        {"role": "assistant", "content": "x" * half_chars},
    ]
    TokenManager.auto_trim_history(history, max_tokens=max_tokens, verbose=True)
    captured = capsys.readouterr()
    assert "75%" not in captured.out
    assert "한도 초과" in captured.out
