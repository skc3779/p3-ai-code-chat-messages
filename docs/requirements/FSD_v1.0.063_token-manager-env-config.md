# FSD v1.0.063 - TokenManager 환경변수 기반 설정 및 메시지 제한 개선

## 문서 정보

| 항목 | 내용 |
|------|------|
| 버전 | v1.0.063 |
| 제목 | TokenManager 환경변수 기반 설정 및 메시지 제한 개선 |
| 작성일 | 2026-03-03 |
| 상태 | 설계 완료 |
| 선행 FSD | [FSD v1.0.017](./FSD_v1.0.017_conversation-history.md) -- 대화 히스토리 관리 |
| 참조 소스 | [token_manager.py](../../../src/token_manager.py), [claude_assistant.py](../../../src/claude_assistant.py), [gemini_assistant.py](../../../src/gemini_assistant.py), [genai_assistant.py](../../../src/genai_assistant.py) |
| 수정 대상 | [token_manager.py](../../../src/token_manager.py), [claude_assistant.py](../../../src/claude_assistant.py), [gemini_assistant.py](../../../src/gemini_assistant.py), [genai_assistant.py](../../../src/genai_assistant.py) |

---

## 1. 개요 (Overview)

`TokenManager`의 토큰 한도 및 메시지 유지 수 설정을 하드코딩된 클래스 상수에서 `.env` 파일 기반의 환경변수로 변경하여 운영 유연성을 확보합니다.

또한 기존 `MIN_MESSAGES_TO_KEEP` (최소 유지 메시지 수) 개념을 `MAX_MESSAGES_TO_KEEP` (최대 유지 메시지 수)으로 변경하여, 메시지 수가 이 값 이상이거나 토큰 사용량이 75%를 초과할 경우 오래된 메시지를 자동으로 제거하는 로직으로 개선합니다.

### 1.1 개선 목표

| # | 목표 | 설명 |
|---|------|------|
| 1 | 상수명 변경 | `MIN_MESSAGES_TO_KEEP` → `MAX_MESSAGES_TO_KEEP` |
| 2 | 환경변수 설정 | `MAX_MESSAGES_TO_KEEP`, `MAX_TOKENS_CLAUDE`, `MAX_TOKENS_GENAI`, `MAX_TOKENS_GEMINI`를 `.env`에서 설정 가능 |
| 3 | 트리밍 조건 개선 | 메시지 수 ≥ `MAX_MESSAGES_TO_KEEP` **또는** 토큰 수 > `MAX_TOKENS_CLAUDE`의 75% 시 트리밍 |
| 4 | 초과 메시지 출력 | 조건 초과 시 관련 정보를 콘솔에 출력 |

---

## 2. 현재 구조 분석

### 2.1 현재 `TokenManager` 클래스 (`src/token_manager.py`)

```python
class TokenManager:
    """대화 히스토리 토큰 관리"""

    # 플랫폼별 컨텍스트 윈도우의 75%를 안전 한도로 설정
    MAX_TOKENS_CLAUDE = 150000   # Claude: 200K의 75%
    MAX_TOKENS_GENAI = 96000     # GenAI: 128K의 75%
    MAX_TOKENS_GEMINI = 786000   # Gemini: 1M의 약 75%

    # 기본값 (Claude 기준)
    DEFAULT_MAX_TOKENS = 150000

    # 최소 유지할 메시지 수 (user + assistant 쌍은 2건으로 계산)
    MIN_MESSAGES_TO_KEEP = 6

    # 토큰 추정 비율 (평균적으로 1토큰 ≈ 4자, 한글은 약 2-3자)
    CHARS_PER_TOKEN = 3.5
```

### 2.2 현재 트리밍 로직 (`auto_trim_history`)

```python
@classmethod
def auto_trim_history(cls, conversation_history, max_tokens=None, verbose=True):
    if max_tokens is None:
        max_tokens = cls.DEFAULT_MAX_TOKENS

    current_tokens = cls.count_tokens(conversation_history)

    if current_tokens <= max_tokens:
        return conversation_history       # ← 토큰 초과일 때만 트리밍

    # 최소 유지 메시지 수 확보하면서 오래된 메시지 제거
    while (len(conversation_history) > cls.MIN_MESSAGES_TO_KEEP and
           cls.count_tokens(conversation_history) > max_tokens):
        conversation_history.pop(0)
```

### 2.3 문제점

| # | 문제점 | 설명 |
|---|--------|------|
| 1 | **하드코딩된 상수** | 토큰 한도, 메시지 수 변경 시 소스 코드 수정 필요 |
| 2 | **MIN 의미 모호** | `MIN_MESSAGES_TO_KEEP = 6`은 "최소 6개는 유지"라는 의미이나, 실제로는 "6개 이상은 트리밍 대상"의 역할 |
| 3 | **트리밍 조건 부족** | 토큰 초과만 확인하고, 메시지 수 자체가 과도하게 쌓이는 경우 대응 불가 |
| 4 | **초과 시 알림 없음** | 메시지 수가 많아져도 토큰 한도 미만이면 사용자에게 별도 알림이 없음 |

### 2.4 호출 위치 분석

| 파일 | 호출 위치 | 사용 상수 |
|------|----------|----------|
| `claude_assistant.py` L131-135 | `chat()` 메서드 내 | `TokenManager.MAX_TOKENS_CLAUDE` |
| `gemini_assistant.py` L131-135 | `chat()` 메서드 내 | `TokenManager.MAX_TOKENS_GEMINI` |
| `genai_assistant.py` L225-230 | `chat()` 메서드 내 | `TokenManager.MAX_TOKENS_GENAI` |

---

## 3. 설계 (Design)

### 3.1 환경변수 정의

| 환경변수 | 설명 | 기본값 | 타입 |
|----------|------|--------|------|
| `MAX_MESSAGES_TO_KEEP` | 최대 유지할 메시지 수 | `30` | int |
| `MAX_TOKENS_CLAUDE` | Claude 토큰 한도 | `150000` | int |
| `MAX_TOKENS_GENAI` | GenAI 토큰 한도 | `96000` | int |
| `MAX_TOKENS_GEMINI` | Gemini 토큰 한도 | `786000` | int |

### 3.2 `.env` 파일 추가 항목

```diff
 # gen-ai-chat-code.py
 ENDPOINT_URL=""
 YOUR_CLIENT_KEY=""
 YOUR_CLIENT_SECRET=""
 YOUR_MODEL_ID=""

 # GenAI API 로깅 (true: 켜기 / false: 끄기)
 GEN_AI_LOG_ENABLED=false

+# TokenManager 설정
+# 최대 유지할 메시지 수 (이 값 이상이면 오래된 메시지 자동 제거)
+MAX_MESSAGES_TO_KEEP=10
+# 플랫폼별 토큰 한도 (컨텍스트 윈도우의 75% 권장)
+MAX_TOKENS_CLAUDE=150000
+MAX_TOKENS_GENAI=96000
+MAX_TOKENS_GEMINI=786000
```

### 3.3 변경된 `TokenManager` 클래스 설계

#### 3.3.1 환경변수 로딩 헬퍼

```python
import os

def _env_int(name: str, default: int) -> int:
    """환경변수에서 정수 값을 읽어 반환. 유효하지 않으면 기본값 사용."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
```

#### 3.3.2 변경된 클래스 상수

```diff
 class TokenManager:
     """대화 히스토리 토큰 관리"""

-    # 플랫폼별 컨텍스트 윈도우의 75%를 안전 한도로 설정
-    MAX_TOKENS_CLAUDE = 150000   # Claude: 200K의 75%
-    MAX_TOKENS_GENAI = 96000     # GenAI: 128K의 75%
-    MAX_TOKENS_GEMINI = 786000   # Gemini: 1M의 약 75%
-
-    # 기본값 (Claude 기준)
-    DEFAULT_MAX_TOKENS = 150000
-
-    # 최소 유지할 메시지 수 (user + assistant 쌍은 2건으로 계산)
-    MIN_MESSAGES_TO_KEEP = 6

+    # 플랫폼별 토큰 한도 (.env에서 설정 가능)
+    MAX_TOKENS_CLAUDE = _env_int("MAX_TOKENS_CLAUDE", 150000)
+    MAX_TOKENS_GENAI  = _env_int("MAX_TOKENS_GENAI",  96000)
+    MAX_TOKENS_GEMINI = _env_int("MAX_TOKENS_GEMINI",  786000)
+
+    # 기본값 (Claude 기준)
+    DEFAULT_MAX_TOKENS = MAX_TOKENS_CLAUDE
+
+    # 최대 유지할 메시지 수 (.env에서 설정 가능, 기본값 30)
+    MAX_MESSAGES_TO_KEEP = _env_int("MAX_MESSAGES_TO_KEEP", 30)

     # 토큰 추정 비율 (평균적으로 1토큰 ≈ 4자, 한글은 약 2-3자)
     CHARS_PER_TOKEN = 3.5
```

#### 3.3.3 변경된 `auto_trim_history` 메서드

```diff
 @classmethod
 def auto_trim_history(
     cls,
     conversation_history: List[Dict],
     max_tokens: int = None,
     verbose: bool = True
 ) -> List[Dict]:
     """
     히스토리가 토큰 한도를 초과하거나 메시지 수가
     MAX_MESSAGES_TO_KEEP 이상이면 오래된 메시지를 제거합니다.

     트리밍 조건 (OR):
       1. 메시지 수 >= MAX_MESSAGES_TO_KEEP
       2. 토큰 수 > max_tokens의 75%
     """
     if max_tokens is None:
         max_tokens = cls.DEFAULT_MAX_TOKENS

     current_tokens = cls.count_tokens(conversation_history)
     message_count = len(conversation_history)
+    token_threshold = int(max_tokens * 0.75)

-    if current_tokens <= max_tokens:
-        return conversation_history
+    # 트리밍 조건 확인: 메시지 수 초과 OR 토큰 75% 초과
+    needs_trim_by_messages = message_count >= cls.MAX_MESSAGES_TO_KEEP
+    needs_trim_by_tokens = current_tokens > token_threshold
+
+    if not needs_trim_by_messages and not needs_trim_by_tokens:
+        return conversation_history

     if verbose:
-        print(f"\n⚠️ 토큰 한도 초과 ({current_tokens:,} > {max_tokens:,})")
-        print("🔄 자동 트리밍 시작...")
+        reasons = []
+        if needs_trim_by_messages:
+            reasons.append(
+                f"메시지 수 초과 ({message_count}개 >= {cls.MAX_MESSAGES_TO_KEEP}개)"
+            )
+        if needs_trim_by_tokens:
+            reasons.append(
+                f"토큰 75% 초과 ({current_tokens:,} > {token_threshold:,})"
+            )
+        print(f"\n⚠️ 히스토리 트리밍 필요: {', '.join(reasons)}")
+        print("🔄 자동 트리밍 시작...")

     removed_count = 0

-    # 최소 유지 메시지 수 확보하면서 오래된 메시지 제거
-    while (len(conversation_history) > cls.MIN_MESSAGES_TO_KEEP and
-           cls.count_tokens(conversation_history) > max_tokens):
-        conversation_history.pop(0)
-        removed_count += 1
+    # 트리밍 루프: 두 조건 모두 해소될 때까지 오래된 메시지 제거
+    # 단, 최소 2개(마지막 user + assistant 쌍)는 유지
+    MIN_KEEP = 2
+    while len(conversation_history) > MIN_KEEP:
+        current_tokens = cls.count_tokens(conversation_history)
+        current_count = len(conversation_history)
+
+        still_over_messages = current_count >= cls.MAX_MESSAGES_TO_KEEP
+        still_over_tokens = current_tokens > token_threshold
+
+        if not still_over_messages and not still_over_tokens:
+            break
+
+        conversation_history.pop(0)
+        removed_count += 1

     if verbose:
         final_tokens = cls.count_tokens(conversation_history)
-        print(f"✅ 트리밍 완료: {removed_count}개 메시지 제거")
-        print(f"📊 현재 토큰: {final_tokens:,} / {max_tokens:,} ({final_tokens * 100 // max_tokens}%)")
+        print(f"✅ 트리밍 완료: {removed_count}개 메시지 제거")
+        print(f"📊 현재 상태: 메시지 {len(conversation_history)}개, "
+              f"토큰 {final_tokens:,} / {max_tokens:,} "
+              f"({final_tokens * 100 // max_tokens}%)")

     return conversation_history
```

### 3.4 전체 변경 후 `token_manager.py` 코드

```python
"""
TokenManager - 토큰 관리 및 자동 트리밍 모듈
"""

import os
from typing import List, Dict, Tuple


def _env_int(name: str, default: int) -> int:
    """환경변수에서 정수 값을 읽어 반환. 유효하지 않으면 기본값 사용."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


class TokenManager:
    """대화 히스토리 토큰 관리"""

    # 플랫폼별 토큰 한도 (.env에서 설정 가능)
    MAX_TOKENS_CLAUDE = _env_int("MAX_TOKENS_CLAUDE", 150000)    # Claude: 200K의 75%
    MAX_TOKENS_GENAI  = _env_int("MAX_TOKENS_GENAI",  96000)     # GenAI: 128K의 75%
    MAX_TOKENS_GEMINI = _env_int("MAX_TOKENS_GEMINI", 786000)    # Gemini: 1M의 약 75%

    # 기본값 (Claude 기준)
    DEFAULT_MAX_TOKENS = MAX_TOKENS_CLAUDE

    # 최대 유지할 메시지 수 (.env에서 설정 가능, 기본값 30)
    MAX_MESSAGES_TO_KEEP = _env_int("MAX_MESSAGES_TO_KEEP", 30)

    # 토큰 추정 비율 (평균적으로 1토큰 ≈ 4자, 한글은 약 2-3자)
    CHARS_PER_TOKEN = 3.5

    @classmethod
    def count_tokens(cls, messages: List[Dict]) -> int:
        """
        메시지 리스트의 총 토큰 수를 추정합니다.

        Args:
            messages: 대화 히스토리 리스트

        Returns:
            추정 토큰 수
        """
        total_chars = 0

        for msg in messages:
            content = msg.get("content", "")

            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # tool_use 등 복합 컨텐츠 처리
                for item in content:
                    if isinstance(item, dict):
                        if "text" in item:
                            total_chars += len(item["text"])
                        elif "content" in item:
                            total_chars += len(str(item["content"]))
                    elif isinstance(item, str):
                        total_chars += len(item)

        return int(total_chars / cls.CHARS_PER_TOKEN)

    @classmethod
    def auto_trim_history(
        cls,
        conversation_history: List[Dict],
        max_tokens: int = None,
        verbose: bool = True
    ) -> List[Dict]:
        """
        히스토리가 토큰 한도의 75%를 초과하거나 메시지 수가
        MAX_MESSAGES_TO_KEEP 이상이면 오래된 메시지를 제거합니다.

        트리밍 조건 (OR):
          1. 메시지 수 >= MAX_MESSAGES_TO_KEEP
          2. 토큰 수 > max_tokens의 75%

        Args:
            conversation_history: 대화 히스토리 리스트
            max_tokens: 최대 허용 토큰 수 (기본값: DEFAULT_MAX_TOKENS)
            verbose: 트리밍 발생 시 메시지 출력 여부

        Returns:
            트리밍된 대화 히스토리
        """
        if max_tokens is None:
            max_tokens = cls.DEFAULT_MAX_TOKENS

        current_tokens = cls.count_tokens(conversation_history)
        message_count = len(conversation_history)
        token_threshold = int(max_tokens * 0.75)

        # 트리밍 조건 확인: 메시지 수 초과 OR 토큰 75% 초과
        needs_trim_by_messages = message_count >= cls.MAX_MESSAGES_TO_KEEP
        needs_trim_by_tokens = current_tokens > token_threshold

        if not needs_trim_by_messages and not needs_trim_by_tokens:
            return conversation_history

        if verbose:
            reasons = []
            if needs_trim_by_messages:
                reasons.append(
                    f"메시지 수 초과 ({message_count}개 >= "
                    f"{cls.MAX_MESSAGES_TO_KEEP}개)"
                )
            if needs_trim_by_tokens:
                reasons.append(
                    f"토큰 75% 초과 ({current_tokens:,} > "
                    f"{token_threshold:,})"
                )
            print(f"\n⚠️ 히스토리 트리밍 필요: {', '.join(reasons)}")
            print("🔄 자동 트리밍 시작...")

        removed_count = 0

        # 트리밍 루프: 두 조건 모두 해소될 때까지 오래된 메시지 제거
        # 단, 최소 2개(마지막 user + assistant 쌍)는 유지
        MIN_KEEP = 2
        while len(conversation_history) > MIN_KEEP:
            current_tokens = cls.count_tokens(conversation_history)
            current_count = len(conversation_history)

            still_over_messages = current_count >= cls.MAX_MESSAGES_TO_KEEP
            still_over_tokens = current_tokens > token_threshold

            if not still_over_messages and not still_over_tokens:
                break

            conversation_history.pop(0)
            removed_count += 1

        if verbose:
            final_tokens = cls.count_tokens(conversation_history)
            print(f"✅ 트리밍 완료: {removed_count}개 메시지 제거")
            print(
                f"📊 현재 상태: 메시지 {len(conversation_history)}개, "
                f"토큰 {final_tokens:,} / {max_tokens:,} "
                f"({final_tokens * 100 // max_tokens}%)"
            )

        return conversation_history

    @classmethod
    def get_token_stats(
        cls,
        conversation_history: List[Dict],
        max_tokens: int = None
    ) -> Dict:
        """
        현재 토큰 사용량 통계를 반환합니다.

        Args:
            conversation_history: 대화 히스토리 리스트
            max_tokens: 최대 허용 토큰 수

        Returns:
            토큰 통계 딕셔너리
        """
        if max_tokens is None:
            max_tokens = cls.DEFAULT_MAX_TOKENS

        current_tokens = cls.count_tokens(conversation_history)

        return {
            "current": current_tokens,
            "max": max_tokens,
            "usage_percent": round(current_tokens * 100 / max_tokens, 1) if max_tokens > 0 else 0,
            "message_count": len(conversation_history),
            "remaining": max_tokens - current_tokens
        }
```

### 3.5 환경변수 로딩 시점

```
프로그램 시작
    │
    ├─[1] load_dotenv() 호출 (main 스크립트)
    │     └─ .env 파일의 환경변수를 os.environ에 로드
    │
    ├─[2] from src import TokenManager
    │     └─ 클래스 정의 시 _env_int() 함수가 호출되어
    │        os.environ에서 값을 읽음
    │
    └─[3] TokenManager 클래스 상수 확정
          ├─ MAX_MESSAGES_TO_KEEP = 30 (또는 .env 값)
          ├─ MAX_TOKENS_CLAUDE = 150000 (또는 .env 값)
          ├─ MAX_TOKENS_GENAI = 96000 (또는 .env 값)
          └─ MAX_TOKENS_GEMINI = 786000 (또는 .env 값)
```

> **중요:** `load_dotenv()`는 각 main 스크립트(`gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py`)의 `load_environment()` 함수에서 호출됩니다. 이 함수는 `from src import TokenManager` **이전**에 실행되므로, `_env_int()`가 호출될 시점에는 `.env` 파일의 값이 이미 `os.environ`에 반영되어 있습니다.

> **참고:** 각 main 스크립트의 import 순서를 확인하면, `load_environment()`는 `main()` 함수 내에서 호출되지만 `from src import ...`는 최상위에서 실행됩니다. 따라서 import 시점에는 `.env`가 로드되지 않은 상태일 수 있습니다. 이를 해결하기 위해 `_env_int()`는 모듈 로드 시점의 `os.environ`을 읽으므로, `.env` 없이 실행할 경우에는 기본값이 사용됩니다. 정확한 `.env` 반영을 위해 **3.6절**의 `reload_from_env()` 클래스 메서드를 추가합니다.

### 3.6 환경변수 재로딩 메서드

import 시점과 `.env` 로드 시점의 차이를 처리하기 위해 `reload_from_env()` 클래스 메서드를 추가합니다.

```python
@classmethod
def reload_from_env(cls):
    """
    .env 파일 로드 후 환경변수 값을 클래스 상수에 반영합니다.
    main 스크립트에서 load_dotenv() 호출 직후 사용합니다.
    """
    cls.MAX_TOKENS_CLAUDE = _env_int("MAX_TOKENS_CLAUDE", 150000)
    cls.MAX_TOKENS_GENAI  = _env_int("MAX_TOKENS_GENAI",  96000)
    cls.MAX_TOKENS_GEMINI = _env_int("MAX_TOKENS_GEMINI", 786000)
    cls.DEFAULT_MAX_TOKENS = cls.MAX_TOKENS_CLAUDE
    cls.MAX_MESSAGES_TO_KEEP = _env_int("MAX_MESSAGES_TO_KEEP", 30)
```

### 3.7 main 스크립트 적용

각 main 스크립트의 `main()` 함수에서 `load_environment()` 직후 `reload_from_env()`를 호출합니다.

#### 3.7.1 `gen-ai-chat-code.py`

```diff
 def main():
     # 환경변수 로드
     load_environment()

+    # REQ-063-002: TokenManager 환경변수 반영
+    TokenManager.reload_from_env()

     # GenAI API 설정값 (환경변수에서 로드)
     ENDPOINT_URL = os.getenv("ENDPOINT_URL")
```

#### 3.7.2 `claude-ai-chat-code.py`

```diff
 def main():
     # 환경변수 로드
     load_environment()

+    # REQ-063-002: TokenManager 환경변수 반영
+    TokenManager.reload_from_env()

     # Claude API 설정값 (환경변수에서 로드)
     ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
```

#### 3.7.3 `gemini-ai-chat-code.py`

```diff
 def main():
     # 환경변수 로드
     load_environment()

+    # REQ-063-002: TokenManager 환경변수 반영
+    TokenManager.reload_from_env()

     # Gemini API 설정값 (환경변수에서 로드)
     GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
```

### 3.8 트리밍 흐름도

```
사용자 입력 → chat() 메서드
    │
    ▼
auto_trim_history(conversation_history, max_tokens)
    │
    ├─[1] token_threshold = max_tokens × 0.75
    │
    ├─[2] 조건 확인
    │     ├─ 메시지 수 >= MAX_MESSAGES_TO_KEEP ?   ── (A)
    │     └─ 토큰 수 > token_threshold ?            ── (B)
    │
    ├─ (A) 또는 (B)가 false이면 → 히스토리 그대로 반환
    │
    ├─ (A) 또는 (B)가 true이면 → 트리밍 시작
    │     │
    │     ├─ verbose=True일 때 초과 사유 출력
    │     │   예: "⚠️ 히스토리 트리밍 필요: 메시지 수 초과 (12개 >= 30개)"
    │     │   예: "⚠️ 히스토리 트리밍 필요: 토큰 75% 초과 (120,000 > 112,500)"
    │     │   예: "⚠️ 히스토리 트리밍 필요: 메시지 수 초과 (...), 토큰 75% 초과 (...)"
    │     │
    │     └─ while 루프: conversation_history.pop(0)
    │           ├─ (A) & (B) 모두 해소될 때까지 반복
    │           └─ 최소 2개 메시지는 유지
    │
    └─ verbose=True일 때 결과 출력
          예: "✅ 트리밍 완료: 4개 메시지 제거"
          예: "📊 현재 상태: 메시지 8개, 토큰 85,000 / 150,000 (56%)"
```

### 3.9 콘솔 출력 예시

#### 메시지 수 초과

```
⚠️ 히스토리 트리밍 필요: 메시지 수 초과 (12개 >= 30개)
🔄 자동 트리밍 시작...
✅ 트리밍 완료: 3개 메시지 제거
📊 현재 상태: 메시지 9개, 토큰 35,000 / 150,000 (23%)
```

#### 토큰 75% 초과

```
⚠️ 히스토리 트리밍 필요: 토큰 75% 초과 (120,000 > 112,500)
🔄 자동 트리밍 시작...
✅ 트리밍 완료: 2개 메시지 제거
📊 현재 상태: 메시지 6개, 토큰 85,000 / 150,000 (56%)
```

#### 복합 조건 (메시지 수 + 토큰 동시 초과)

```
⚠️ 히스토리 트리밍 필요: 메시지 수 초과 (35개 >= 30개), 토큰 75% 초과 (130,000 > 112,500)
🔄 자동 트리밍 시작...
✅ 트리밍 완료: 7개 메시지 제거
📊 현재 상태: 메시지 8개, 토큰 60,000 / 150,000 (40%)
```

---

## 4. 요구사항 (Requirements)

### 4.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|--------:|
| REQ-063-001 | `MIN_MESSAGES_TO_KEEP`를 `MAX_MESSAGES_TO_KEEP`로 변경하고, 기본값을 `10`으로 설정한다 | 필수 |
| REQ-063-002 | `MAX_MESSAGES_TO_KEEP` 값을 `.env` 파일에서 환경변수로 설정할 수 있다 | 필수 |
| REQ-063-003 | `MAX_TOKENS_CLAUDE`, `MAX_TOKENS_GENAI`, `MAX_TOKENS_GEMINI` 값을 `.env` 파일에서 환경변수로 설정할 수 있다 (기본값: 150000, 96000, 786000) | 필수 |
| REQ-063-004 | 메시지 수가 `MAX_MESSAGES_TO_KEEP` 이상이면 오래된 메시지를 자동 제거한다 | 필수 |
| REQ-063-005 | 토큰 수가 `max_tokens`의 75%를 초과하면 오래된 메시지를 자동 제거한다 | 필수 |
| REQ-063-006 | 트리밍 조건 초과 시 초과 사유를 콘솔에 출력한다 (메시지 수 초과, 토큰 초과, 또는 둘 다) | 필수 |
| REQ-063-007 | `reload_from_env()` 클래스 메서드를 추가하여 `load_dotenv()` 호출 후 환경변수를 클래스 상수에 반영한다 | 필수 |
| REQ-063-008 | 각 main 스크립트(`gen-ai-chat-code.py`, `claude-ai-chat-code.py`, `gemini-ai-chat-code.py`)에서 `load_environment()` 직후 `TokenManager.reload_from_env()`를 호출한다 | 필수 |

### 4.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NREQ-063-001 | `.env` 파일에 환경변수가 없으면 기본값을 사용하여 기존 동작과 동일하게 작동한다 |
| NREQ-063-002 | 환경변수 값이 유효하지 않은 정수인 경우 기본값으로 폴백한다 |
| NREQ-063-003 | 트리밍 시 최소 2개의 메시지(마지막 user + assistant 쌍)는 유지한다 |
| NREQ-063-004 | `_env_int()` 헬퍼 함수는 모듈 수준에서 정의하여 클래스 상수 초기화 시 사용한다 |

---

## 5. 변경 파일 목록

| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `src/token_manager.py` | **수정** | `_env_int()` 헬퍼 추가, `MIN_MESSAGES_TO_KEEP` → `MAX_MESSAGES_TO_KEEP` 변경, 환경변수 기반 상수 로딩, `auto_trim_history()` 트리밍 조건 개선, `reload_from_env()` 추가 |
| `gen-ai-chat-code.py` | **수정** | `main()`에 `TokenManager.reload_from_env()` 호출 추가 |
| `claude-ai-chat-code.py` | **수정** | `main()`에 `TokenManager.reload_from_env()` 호출 추가 |
| `gemini-ai-chat-code.py` | **수정** | `main()`에 `TokenManager.reload_from_env()` 호출 추가 |
| `.env` | **수정** | `MAX_MESSAGES_TO_KEEP`, `MAX_TOKENS_CLAUDE`, `MAX_TOKENS_GENAI`, `MAX_TOKENS_GEMINI` 환경변수 추가 |

---

## 6. 테스트 계획 (Test Plan)

### 6.1 단위 테스트

| ID | 테스트 케이스 | 예상 결과 |
|----|--------------|----------|
| TC-063-001 | `.env` 미설정 시 `MAX_MESSAGES_TO_KEEP` 기본값 | `30` |
| TC-063-002 | `.env`에 `MAX_MESSAGES_TO_KEEP=20` 설정 후 `reload_from_env()` | `20` |
| TC-063-003 | `.env` 미설정 시 `MAX_TOKENS_CLAUDE` 기본값 | `150000` |
| TC-063-004 | `.env`에 `MAX_TOKENS_CLAUDE=200000` 설정 후 `reload_from_env()` | `200000` |
| TC-063-005 | `.env`에 유효하지 않은 값 설정 (`MAX_MESSAGES_TO_KEEP=abc`) | 기본값 `30` 사용 |
| TC-063-006 | 메시지 10개인 상태에서 `auto_trim_history()` 호출 | 트리밍 발생, 메시지 감소 |
| TC-063-007 | 메시지 5개, 토큰 미초과 상태에서 `auto_trim_history()` | 트리밍 미발생 |
| TC-063-008 | 메시지 5개, 토큰 75% 초과 상태에서 `auto_trim_history()` | 트리밍 발생 |
| TC-063-009 | 메시지 12개, 토큰 미초과 상태에서 `auto_trim_history()` | 메시지 수 기준 트리밍 발생 |
| TC-063-010 | 메시지 15개, 토큰 75% 초과 시 `auto_trim_history()` | 둘 다 해소될 때까지 트리밍 |
| TC-063-011 | 트리밍 시 verbose=True일 때 초과 사유 출력 | 콘솔에 "⚠️ 히스토리 트리밍 필요: ..." 메시지 출력 |
| TC-063-012 | 트리밍 시 verbose=False일 때 출력 없음 | 콘솔 출력 없음 |
| TC-063-013 | 트리밍 후 최소 2개 메시지 유지 | `len(history) >= 2` |
| TC-063-014 | `MIN_MESSAGES_TO_KEEP` 참조 코드가 없음 | 기존 참조 모두 제거 확인 |

### 6.2 통합 테스트

```bash
# 1. .env에 토큰매니저 설정 추가
# MAX_MESSAGES_TO_KEEP=30
# MAX_TOKENS_CLAUDE=150000

# 2. 어시스턴트 실행
python gen-ai-chat-code.py

# 3. 30개 이상 메시지 교환 후 트리밍 메시지 확인
# ⚠️ 히스토리 트리밍 필요: 메시지 수 초과 (30개 >= 30개)
# 🔄 자동 트리밍 시작...
# ✅ 트리밍 완료: 1개 메시지 제거
# 📊 현재 상태: 메시지 29개, 토큰 ...

# 4. /tokens 명령으로 토큰 사용량 확인
/tokens
```

---

## 7. 주의사항

| 항목 | 설명 |
|------|------|
| **하위 호환성** | `.env`에 새 환경변수가 없더라도 기본값으로 동작하므로 기존 사용자에게 영향 없음 |
| **import 순서** | `from src import TokenManager`는 top-level import이므로 `load_dotenv()` 이전에 실행됨. 반드시 `reload_from_env()` 호출 필요 |
| **최소 유지 메시지** | 트리밍 루프의 안전 장치로 최소 2개 메시지(마지막 대화 쌍)를 유지하여 컨텍스트 완전 손실 방지 |
| **토큰 75% 기준** | `max_tokens`의 75%를 임계값으로 사용하여 버퍼 여유를 확보. `max_tokens` 자체가 이미 컨텍스트 윈도우의 75%이므로, 실제로는 전체 윈도우의 약 56%에서 트리밍 시작 |
| **상수명 변경 영향** | `MIN_MESSAGES_TO_KEEP`는 `token_manager.py` 내부에서만 사용되므로 외부 참조 변경 불필요 |

---

## 8. 변경 이력 (Change History)

| 버전 | 날짜 | 작성자 | 내용 |
|------|------|--------|------|
| v1.0.063 | 2026-03-03 | - | 최초 작성: TokenManager 환경변수 기반 설정 및 메시지 제한 개선 |
