# FSD v1.0.156 — `/tokens` 명령어 개선: 메시지 한도 런타임 수정 및 출력 통일

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.156 |
| 작성일 | 2026-05-10 |
| 구현 예정일 | 2026-05-10 |
| 상태 | ✅ 구현 완료 |
| 선행 문서 | FSD v1.0.063 (TokenManager .env 설정) |
| 대상 파일 | [src/token_manager.py](../../src/token_manager.py), [claude-ai-chat-code.py](../../claude-ai-chat-code.py), [gemini-ai-chat-code.py](../../gemini-ai-chat-code.py), [gen-ai-chat-code.py](../../gen-ai-chat-code.py), [src/command_registry.py](../../src/command_registry.py) |
| 신규 파일 | [tests/test_tokens_command.py](../../tests/test_tokens_command.py) |

---

## 1. 개요

### 1.1 목적

현재 `/tokens` 명령어는 **토큰 사용량 조회** 만 제공하며, `MAX_MESSAGES_TO_KEEP` 설정은 `.env` 파일을 직접 수정한 뒤 애플리케이션을 재시작해야 반영된다. 또한 세 엔트리포인트(`claude-ai-chat-code.py`, `gemini-ai-chat-code.py`, `gen-ai-chat-code.py`) 의 `/tokens` 출력 형식이 서로 다르다.

본 FSD 는 다음 세 가지를 개선한다:

| # | 개선 사항 | 효과 |
|---|---|---|
| 1 | `/tokens -k <number>` / `/tokens -k default` 옵션으로 `MAX_MESSAGES_TO_KEEP` 런타임 수정 | 재시작 없이 메시지 보관 수 제어 |
| 2 | 세 엔트리포인트의 `/tokens` 출력을 **동일한 형식** 으로 통일 — `메시지 수: N / MAX` 포함 | UX 일관성 |
| 3 | `token_manager.py` 에 정의된 **토큰 한계 수치** (Claude/GenAI/Gemini) 를 함께 표시 | 설정 가시성 |

### 1.2 다루는 문제

| ID | 현 문제 | 본 FSD 의 대응 |
|---|---|---|
| P-1 | `MAX_MESSAGES_TO_KEEP` 변경 시 `.env` 수정 + 재시작 필요 | `/tokens -k <N>` 으로 런타임 변경, 즉시 반영 |
| P-2 | 세 파일의 `/tokens` 출력 형식이 상이 (줄 수, 항목명, 단위 표기 등) | 공통 출력 함수(`TokenManager.format_token_report`) 도입 |
| P-3 | `MAX_MESSAGES_TO_KEEP` 값이 출력에 표시되지 않음 | `메시지 수: N / MAX` 형식으로 표시 |
| P-4 | 플랫폼별 토큰 한계 설정값을 확인하려면 `.env` 또는 소스를 열어야 함 | `/tokens` 출력에 한계 설정값 섹션 추가 |

### 1.3 비범위

| 항목 | 비고 |
|---|---|
| `.env` 파일 자동 쓰기 | 런타임 변경은 현재 세션에만 유효. `.env` 에 자동 기록하지 않음 |
| 토큰 한계 수치의 런타임 변경 | 본 FSD 는 `MAX_MESSAGES_TO_KEEP` 만 대상. 토큰 한계는 표시만 |
| `/tokens` 이외 명령어 변경 | `/history`, `/clear` 등은 변경하지 않음 |

---

## 2. 현황 분석

### 2.1 현재 `/tokens` 출력 비교

**claude-ai-chat-code.py** (L316-325):
```
📊 토큰 사용량:
   현재:    1,234 토큰
   한도:    150,000 토큰 (Claude)
   사용률:  0.8%
   메시지: 5개
```

**gen-ai-chat-code.py** (L324-333):
```
📊 토큰 사용량:
   현재:    1,234 토큰
   한도:    96,000 토큰 (GenAI)
   사용률:  1.3%
   메시지: 5개
```

**gemini-ai-chat-code.py** (L549-557):
```
📊 토큰 사용량:
  - 현재: 1,234 / 786,000 (0.2%)
  - 메시지 수: 5
  - 남은 토큰: 784,766
```

→ 형식이 모두 다르며, `MAX_MESSAGES_TO_KEEP` 정보가 없고, 토큰 한계 설정값도 표시되지 않는다.

### 2.2 `TokenManager` 클래스 상수 (token_manager.py)

```python
MAX_TOKENS_CLAUDE = _env_int("MAX_TOKENS_CLAUDE", 150000)   # Claude: 200K의 75%
MAX_TOKENS_GENAI  = _env_int("MAX_TOKENS_GENAI",  96000)    # GenAI: 128K의 75%
MAX_TOKENS_GEMINI = _env_int("MAX_TOKENS_GEMINI", 786000)   # Gemini: 1M의 약 75%
MAX_MESSAGES_TO_KEEP = _env_int("MAX_MESSAGES_TO_KEEP", 30)
CHARS_PER_TOKEN = 3.5
```

### 2.3 `command_registry.py` 의 `/tokens` 등록 (L90-91)

```python
CommandInfo('/tokens', '현재 대화의 토큰 사용량 확인',
            '/tokens',                           ''),
```

→ `-k` 옵션에 대한 usage/example 정보가 없다.

---

## 3. 설계 (Design)

### 3.1 명령어 문법 확장

```
/tokens                  기존 동작: 토큰 사용량 + 메시지 한도 + 토큰 한계 설정값 출력
/tokens -k <number>      MAX_MESSAGES_TO_KEEP 을 <number> 로 변경 (런타임)
/tokens -k default       MAX_MESSAGES_TO_KEEP 을 .env 기본값으로 복원
```

**`-k` 옵션 동작 상세:**

| 입력 | 동작 | 유효성 |
|---|---|---|
| `/tokens -k 50` | `TokenManager.MAX_MESSAGES_TO_KEEP = 50` | `<number>` 는 1 이상 정수 |
| `/tokens -k 0` | 거부 — 최소 1 | 에러 메시지 출력 |
| `/tokens -k default` | `.env` 에서 `MAX_MESSAGES_TO_KEEP` 다시 읽기, 없으면 30 | 항상 유효 |
| `/tokens -k` | 에러 — 값 누락 | 사용법 안내 출력 |
| `/tokens -k abc` | 에러 — 숫자가 아님 | 에러 메시지 출력 |

### 3.2 통일된 출력 형식

세 엔트리포인트 모두 아래 형식으로 동일하게 출력한다:

```
📊 토큰 사용량:
   현재 토큰:  1,234 / 150,000 (0.8%)
   메시지 수:  5 / 30
   남은 토큰:  148,766

⚙️ 토큰 한계 설정:
   Claude:  150,000
   GenAI:   96,000
   Gemini:  786,000
```

- **`메시지 수: 5 / 30`** → 현재 메시지 수 / `MAX_MESSAGES_TO_KEEP`
- **토큰 한계 설정** 섹션은 세 플랫폼의 한계값을 모두 표시한다 (현재 플랫폼에 `(현재)` 마커 추가).

> 예시 — Claude 에서 실행 시:
> ```
> ⚙️ 토큰 한계 설정:
>    Claude:  150,000 (현재)
>    GenAI:   96,000
>    Gemini:  786,000
> ```

### 3.3 `TokenManager` 변경

#### 3.3.1 `DEFAULT_MAX_MESSAGES_TO_KEEP` 상수 추가

```python
# 기본값 (복원 시 사용)
DEFAULT_MAX_MESSAGES_TO_KEEP = _env_int("MAX_MESSAGES_TO_KEEP", 30)
```

`reload_from_env()` 호출 시 이 값도 갱신한다. `/tokens -k default` 는 이 상수에서 값을 복원한다.

#### 3.3.2 `set_max_messages(cls, value: int)` 클래스메서드 추가

```python
@classmethod
def set_max_messages(cls, value: int) -> None:
    """MAX_MESSAGES_TO_KEEP 을 런타임에 변경한다.

    Args:
        value: 1 이상의 정수
    Raises:
        ValueError: value < 1
    """
    if value < 1:
        raise ValueError("MAX_MESSAGES_TO_KEEP 은 1 이상이어야 합니다.")
    cls.MAX_MESSAGES_TO_KEEP = value
```

#### 3.3.3 `reset_max_messages(cls)` 클래스메서드 추가

```python
@classmethod
def reset_max_messages(cls) -> None:
    """MAX_MESSAGES_TO_KEEP 을 .env 기본값으로 복원한다."""
    cls.MAX_MESSAGES_TO_KEEP = cls.DEFAULT_MAX_MESSAGES_TO_KEEP
```

#### 3.3.4 `format_token_report(cls, ...) -> str` 클래스메서드 추가

세 엔트리포인트에서 중복 코드 없이 동일 출력을 생성하기 위한 포매터:

```python
@classmethod
def format_token_report(
    cls,
    conversation_history: List[Dict],
    max_tokens: int = None,
    platform: str = "Claude",
) -> str:
    """통일된 /tokens 출력 문자열을 생성한다.

    Args:
        conversation_history: 대화 히스토리 리스트
        max_tokens: 현재 플랫폼의 최대 토큰 수
        platform: 플랫폼 이름 ("Claude", "GenAI", "Gemini")

    Returns:
        출력용 포맷팅된 문자열
    """
    if max_tokens is None:
        max_tokens = cls.DEFAULT_MAX_TOKENS

    stats = cls.get_token_stats(conversation_history, max_tokens)

    lines = [
        "\n📊 토큰 사용량:",
        f"   현재 토큰:  {stats['current']:,} / {stats['max']:,} ({stats['usage_percent']}%)",
        f"   메시지 수:  {stats['message_count']} / {cls.MAX_MESSAGES_TO_KEEP}",
        f"   남은 토큰:  {stats['remaining']:,}",
        "",
        "⚙️ 토큰 한계 설정:",
    ]

    platforms = [
        ("Claude", cls.MAX_TOKENS_CLAUDE),
        ("GenAI",  cls.MAX_TOKENS_GENAI),
        ("Gemini", cls.MAX_TOKENS_GEMINI),
    ]
    for name, limit in platforms:
        marker = " (현재)" if name == platform else ""
        lines.append(f"   {name + ':':9s}{limit:,}{marker}")

    return "\n".join(lines)
```

#### 3.3.5 `reload_from_env()` 수정

`DEFAULT_MAX_MESSAGES_TO_KEEP` 도 갱신:

```python
@classmethod
def reload_from_env(cls):
    cls.MAX_TOKENS_CLAUDE = _env_int("MAX_TOKENS_CLAUDE", 150000)
    cls.MAX_TOKENS_GENAI  = _env_int("MAX_TOKENS_GENAI",  96000)
    cls.MAX_TOKENS_GEMINI = _env_int("MAX_TOKENS_GEMINI", 786000)
    cls.DEFAULT_MAX_TOKENS = cls.MAX_TOKENS_CLAUDE
    cls.MAX_MESSAGES_TO_KEEP = _env_int("MAX_MESSAGES_TO_KEEP", 30)
    cls.DEFAULT_MAX_MESSAGES_TO_KEEP = cls.MAX_MESSAGES_TO_KEEP  # ★ NEW
```

### 3.4 엔트리포인트 변경 — `/tokens` 분기

세 파일 모두 동일한 패턴으로 변경한다:

```python
elif command == '/tokens':
    if args.strip().startswith('-k'):
        # -k 옵션 처리
        parts = args.strip().split()
        if len(parts) < 2:
            print("❌ 사용법: /tokens -k <number> 또는 /tokens -k default")
            continue
        value_str = parts[1]
        if value_str == 'default':
            TokenManager.reset_max_messages()
            print(f"✅ MAX_MESSAGES_TO_KEEP 이 기본값({TokenManager.MAX_MESSAGES_TO_KEEP})으로 복원되었습니다.")
        else:
            try:
                value = int(value_str)
                TokenManager.set_max_messages(value)
                print(f"✅ MAX_MESSAGES_TO_KEEP 이 {value} 로 변경되었습니다.")
            except ValueError:
                print(f"❌ 유효하지 않은 값: {value_str} (1 이상의 정수 또는 'default')")
                continue
    # 항상 토큰 리포트 출력
    report = TokenManager.format_token_report(
        assistant.conversation_history,
        max_tokens=TokenManager.MAX_TOKENS_XXXXX,  # 플랫폼별 상수
        platform="XXXXX",                           # 플랫폼명
    )
    print(report)
```

> `MAX_TOKENS_XXXXX` / `platform` 은 엔트리포인트별로:
> - **claude**: `MAX_TOKENS_CLAUDE`, `"Claude"`
> - **gemini**: `MAX_TOKENS_GEMINI`, `"Gemini"`
> - **gen-ai**: `MAX_TOKENS_GENAI`, `"GenAI"`

### 3.5 `command_registry.py` 변경

```python
CommandInfo('/tokens',        '토큰 사용량 확인 · 메시지 한도 변경',
            '/tokens [-k <number|default>]',     '-k 50'),
```

---

## 4. 요구사항

### 4.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-01 | `/tokens` (인자 없음) 실행 시 토큰 사용량, 메시지 수/한도, 토큰 한계 설정값을 출력한다 | 필수 |
| FR-02 | 출력 형식은 § 3.2 의 통일 형식과 일치해야 한다 | 필수 |
| FR-03 | `메시지 수:` 행에 `현재 수 / MAX_MESSAGES_TO_KEEP` 형식으로 표시한다 | 필수 |
| FR-04 | `⚙️ 토큰 한계 설정:` 섹션에 Claude/GenAI/Gemini 세 값을 모두 표시한다 | 필수 |
| FR-05 | 현재 실행 중인 플랫폼의 한계값 옆에 `(현재)` 마커를 표시한다 | 필수 |
| FR-06 | `/tokens -k <number>` 실행 시 `TokenManager.MAX_MESSAGES_TO_KEEP` 을 `<number>` 로 변경한다 | 필수 |
| FR-07 | `<number>` 는 1 이상 정수여야 한다. 0 이하, 비정수 입력 시 에러 메시지를 출력한다 | 필수 |
| FR-08 | `/tokens -k default` 실행 시 `.env` 기본값으로 복원한다 | 필수 |
| FR-09 | `-k` 옵션 처리 후에도 토큰 리포트를 출력한다 (변경 확인 겸용) | 필수 |
| FR-10 | 세 엔트리포인트(`claude-ai-chat-code.py`, `gemini-ai-chat-code.py`, `gen-ai-chat-code.py`) 모두 동일한 출력 형식을 사용한다 | 필수 |
| FR-11 | 출력은 `TokenManager.format_token_report()` 단일 메서드에서 생성한다 (중복 코드 금지) | 필수 |
| FR-12 | `command_registry.py` 의 `/tokens` usage/example 을 갱신한다 | 필수 |
| FR-13 | `-k` 런타임 변경은 현재 세션에만 유효하다 (`.env` 파일을 수정하지 않는다) | 필수 |

### 4.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-01 | `format_token_report()` 는 외부 의존 없이 순수 문자열 포맷팅만 수행한다 |
| NFR-02 | `set_max_messages()` / `reset_max_messages()` 는 스레드 안전을 고려하지 않는다 (단일 스레드 REPL) |
| NFR-03 | 기존 `get_token_stats()` 의 시그니처와 반환값은 변경하지 않는다 |

---

## 5. 변경 파일 요약

| 파일 | 변경 내용 |
|---|---|
| `src/token_manager.py` | `DEFAULT_MAX_MESSAGES_TO_KEEP` 상수, `set_max_messages()`, `reset_max_messages()`, `format_token_report()` 추가, `reload_from_env()` 수정 |
| `claude-ai-chat-code.py` | `/tokens` 분기를 § 3.4 패턴으로 교체 (platform=`"Claude"`, max_tokens=`MAX_TOKENS_CLAUDE`) |
| `gemini-ai-chat-code.py` | `/tokens` 분기를 § 3.4 패턴으로 교체 (platform=`"Gemini"`, max_tokens=`MAX_TOKENS_GEMINI`) |
| `gen-ai-chat-code.py` | `/tokens` 분기를 § 3.4 패턴으로 교체 (platform=`"GenAI"`, max_tokens=`MAX_TOKENS_GENAI`) |
| `src/command_registry.py` | `/tokens` 의 usage/example 갱신 |
| `tests/test_tokens_command.py` | 신규 — § 6 테스트 케이스 |

---

## 6. 테스트 케이스

### 6.1 `TokenManager` 단위 테스트

| ID | 테스트 | 기대 결과 |
|---|---|---|
| T-01 | `set_max_messages(50)` 호출 | `MAX_MESSAGES_TO_KEEP == 50` |
| T-02 | `set_max_messages(0)` 호출 | `ValueError` 발생 |
| T-03 | `set_max_messages(-1)` 호출 | `ValueError` 발생 |
| T-04 | `set_max_messages(50)` → `reset_max_messages()` | `MAX_MESSAGES_TO_KEEP == DEFAULT_MAX_MESSAGES_TO_KEEP` |
| T-05 | `format_token_report([], platform="Claude")` | 출력 문자열에 `메시지 수:  0 / 30` 포함 |
| T-06 | `format_token_report([], platform="Gemini")` | `Gemini:` 행에 `(현재)` 포함, `Claude:` 행에 미포함 |
| T-07 | `set_max_messages(10)` → `format_token_report(...)` | `메시지 수:  N / 10` 형식 |
| T-08 | `format_token_report(...)` 출력에 `⚙️ 토큰 한계 설정:` 포함 | Claude/GenAI/Gemini 세 행 존재 |

### 6.2 통합 테스트 (수동)

| ID | 테스트 | 기대 결과 |
|---|---|---|
| T-09 | `/tokens` 실행 (인자 없음) | 통일 형식으로 출력, `메시지 수: N / 30` |
| T-10 | `/tokens -k 10` 실행 | `✅ MAX_MESSAGES_TO_KEEP 이 10 로 변경되었습니다.` + 리포트 |
| T-11 | `/tokens -k default` 실행 | `✅ MAX_MESSAGES_TO_KEEP 이 기본값(30)으로 복원되었습니다.` + 리포트 |
| T-12 | `/tokens -k abc` 실행 | `❌ 유효하지 않은 값: abc` |
| T-13 | `/tokens -k` (값 없음) 실행 | `❌ 사용법: /tokens -k <number> 또는 /tokens -k default` |
| T-14 | `/tokens -k 0` 실행 | `❌ 유효하지 않은 값` |
| T-15 | claude/gemini/gen-ai 세 파일에서 `/tokens` 출력 비교 | platform 마커만 다르고 형식 동일 |

---

## 7. 출력 예시 (최종)

### 7.1 `/tokens` (인자 없음, Claude 실행)

```
📊 토큰 사용량:
   현재 토큰:  1,234 / 150,000 (0.8%)
   메시지 수:  5 / 30
   남은 토큰:  148,766

⚙️ 토큰 한계 설정:
   Claude:  150,000 (현재)
   GenAI:   96,000
   Gemini:  786,000
```

### 7.2 `/tokens -k 50` (변경 + 리포트)

```
✅ MAX_MESSAGES_TO_KEEP 이 50 로 변경되었습니다.

📊 토큰 사용량:
   현재 토큰:  1,234 / 150,000 (0.8%)
   메시지 수:  5 / 50
   남은 토큰:  148,766

⚙️ 토큰 한계 설정:
   Claude:  150,000 (현재)
   GenAI:   96,000
   Gemini:  786,000
```

### 7.3 `/tokens -k default` (복원)

```
✅ MAX_MESSAGES_TO_KEEP 이 기본값(30)으로 복원되었습니다.

📊 토큰 사용량:
   현재 토큰:  1,234 / 150,000 (0.8%)
   메시지 수:  5 / 30
   남은 토큰:  148,766

⚙️ 토큰 한계 설정:
   Claude:  150,000 (현재)
   GenAI:   96,000
   Gemini:  786,000
```

---

## 8. 후속 작업

| 항목 | 설명 |
|---|---|
| `.env` 자동 저장 | `/tokens -k <N> --save` 옵션으로 `.env` 에 영구 기록하는 기능 (Phase 2) |
| 토큰 한계값 런타임 변경 | `/tokens --max-tokens <platform> <value>` (Phase 2) |

---

## 9. 마이그레이션 체크리스트

- [ ] `src/token_manager.py` 에 `DEFAULT_MAX_MESSAGES_TO_KEEP`, `set_max_messages()`, `reset_max_messages()`, `format_token_report()` 추가
- [ ] `src/token_manager.py` 의 `reload_from_env()` 에 `DEFAULT_MAX_MESSAGES_TO_KEEP` 갱신 로직 추가
- [ ] `claude-ai-chat-code.py` `/tokens` 분기 교체
- [ ] `gemini-ai-chat-code.py` `/tokens` 분기 교체
- [ ] `gen-ai-chat-code.py` `/tokens` 분기 교체
- [ ] `src/command_registry.py` `/tokens` usage/example 갱신
- [ ] `tests/test_tokens_command.py` 작성 및 통과 확인

---

## 10. 승인

- [x] FSD 문서 검토 완료
- [x] 코드 구현 완료
- [x] 테스트 케이스 전체 통과
- [x] 세 엔트리포인트 출력 형식 동일 확인
- [x] FSD 구현 완료 후 `docs/releases` 폴더에 `RELEASE-v1.0.156` 문서 작성
- [x] README.md 파일 업데이트
