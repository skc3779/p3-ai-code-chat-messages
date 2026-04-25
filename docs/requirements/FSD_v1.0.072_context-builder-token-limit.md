# FSD v1.0.072 — ContextBuilder 크기 제한을 TokenManager 토큰 한도로 통합

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.072 |
| 작성일 | 2026-03-06 |
| 상태 | 초안 |
| 대상 파일 | `src/context_builder.py`, `src/claude_assistant.py`, `src/genai_assistant.py`, `src/gemini_assistant.py`, `tests/test_context_builder.py` |
| 연관 모듈 | `src/token_manager.py` |

---

## 1. 개요

현재 `ContextBuilder`는 파일 컨텍스트 크기를 **문자 수(chars)** 기준의 `max_context_size`로 독립적으로 관리한다.  
`TokenManager`는 이미 플랫폼별 **토큰 수** 한도(`MAX_TOKENS_CLAUDE`, `MAX_TOKENS_GENAI`, `MAX_TOKENS_GEMINI`)를  
환경변수 기반으로 중앙 관리하고 있다.

두 모듈이 서로 다른 단위(chars vs tokens)로 크기를 제한하는 구조는  
플랫폼별 실제 컨텍스트 윈도우를 일관되게 반영하지 못하는 문제를 야기한다.

이 문서는 `ContextBuilder`의 `max_context_size`를 제거하고, `TokenManager`의 플랫폼별  
토큰 한도로 대체하는 방법을 정의한다.

---

## 2. 현황 분석

### 2.1 ContextBuilder (현재 — `src/context_builder.py`)

```python
_DEFAULT_MAX_CONTEXT_SIZE = 1000000  # 문자 수 기본값

class ContextBuilder:
    def __init__(self, file_manager: FileManager):
        self.max_context_size = _env_int("MAX_CONTEXT_SIZE", _DEFAULT_MAX_CONTEXT_SIZE)

    def build_files_context(self, filepaths):
        ...
        if total_size + len(file_context) > self.max_context_size:  # 문자 수 비교
            context_parts.append("⚠️ 컨텍스트 크기 제한으로 일부 파일이 생략되었습니다.")
            ...
```

**문제점:**
- `MAX_CONTEXT_SIZE` 환경변수가 `MAX_TOKENS_*` 환경변수와 별도로 존재 — 설정 이중화
- 문자 수 단위 제한은 플랫폼별 토큰 윈도우와 직접 대응되지 않음
- 모든 플랫폼이 동일한 `1,000,000`자 한도를 사용 — Claude(525,000자 허용)와 Gemini(2,751,000자 허용)가 동일 취급
- `ContextBuilder`가 `TokenManager`와 무관하게 독립적인 `_env_int` 로직 중복 보유

### 2.2 TokenManager (현재 — `src/token_manager.py`)

```python
class TokenManager:
    MAX_TOKENS_CLAUDE = _env_int("MAX_TOKENS_CLAUDE", 150000)   # 200K의 75%
    MAX_TOKENS_GENAI  = _env_int("MAX_TOKENS_GENAI",  96000)    # 128K의 75%
    MAX_TOKENS_GEMINI = _env_int("MAX_TOKENS_GEMINI", 786000)   # 1M의 75%

    CHARS_PER_TOKEN = 3.5  # 1토큰 ≈ 3.5자 (한글 포함 평균)
```

토큰 → 문자 수 환산:

| 플랫폼 | MAX_TOKENS | 문자 수 환산 (× 3.5) | 현재 max_context_size |
|---|---|---|---|
| Claude  | 150,000 | 525,000자 | 1,000,000자 (초과 허용) |
| GenAI   | 96,000  | 336,000자 | 1,000,000자 (초과 허용) |
| Gemini  | 786,000 | 2,751,000자 | 1,000,000자 (과소 제한) |

→ Claude·GenAI는 실제 허용 범위보다 넓게, Gemini는 실제보다 좁게 제한되고 있음.

### 2.3 어시스턴트별 ContextBuilder 생성 (현재)

세 어시스턴트 모두 플랫폼 구분 없이 동일하게 생성:

```python
# claude_assistant.py, gemini_assistant.py, genai_assistant.py 공통
self.context_builder = ContextBuilder(self.file_manager)  # 플랫폼 정보 없음
```

### 2.4 기타 컨텍스트 크기 제한 관련 코드 검토

| 파일 | 크기 제한 로직 | 비고 |
|---|---|---|
| `src/context_builder.py` | `max_context_size` (chars) | **본 FSD 대상** |
| `src/token_manager.py` | `MAX_TOKENS_*` (tokens) | 히스토리 트리밍 기준 |
| `src/context_processor.py` | 없음 | `/auto_context` 처리기, 크기 제한 없음 |
| `src/claude_assistant.py` | 없음 | ContextBuilder 위임 |
| `src/gemini_assistant.py` | 없음 | ContextBuilder 위임 |
| `src/genai_assistant.py` | 없음 | ContextBuilder 위임 |
| `claude-ai-chat-code.py` | 없음 | ContextBuilder 위임 |
| `gen-ai-chat-code.py` | 없음 | ContextBuilder 위임 |
| `gemini-ai-chat-code.py` | 없음 | ContextBuilder 위임 |

→ `max_context_size` 관련 크기 제한은 `src/context_builder.py` 단 한 곳에만 존재하며,  
나머지 파일에는 별도의 컨텍스트 크기 제한 로직이 없음.

---

## 3. 개선 요구사항

### 3.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-01 | `ContextBuilder.__init__`에 `max_tokens` 파라미터 추가 | 필수 |
| FR-02 | `max_context_size` 인스턴스 변수 및 `_DEFAULT_MAX_CONTEXT_SIZE`, `MAX_CONTEXT_SIZE` 환경변수 지원 제거 | 필수 |
| FR-03 | `build_files_context` 내 크기 비교를 `max_tokens * TokenManager.CHARS_PER_TOKEN` (chars)으로 수행 | 필수 |
| FR-04 | `context_builder.py`의 중복 `_env_int` 함수 및 `import os` 제거 | 필수 |
| FR-05 | 각 어시스턴트가 `ContextBuilder` 생성 시 플랫폼별 토큰 한도를 전달 | 필수 |
| FR-06 | 기존 테스트를 새 인터페이스(`max_tokens`)에 맞게 갱신 | 필수 |

### 3.2 비기능 요구사항

| ID | 요구사항 |
|---|---|
| NFR-01 | `MAX_CONTEXT_SIZE` 환경변수는 폐기 — `.env` 예시 파일에서 제거 대상으로 표시 |
| NFR-02 | 플랫폼별 토큰 한도는 `TokenManager.reload_from_env()` 호출로만 갱신 (기존 방식 유지) |
| NFR-03 | `ContextBuilder` 생성자의 `max_tokens` 기본값은 `None` — 미전달 시 `TokenManager.DEFAULT_MAX_TOKENS` 사용 |

---

## 4. 설계

### 4.1 ContextBuilder 변경 설계 (`src/context_builder.py`)

#### 변경 전

```python
import fnmatch
import os
from pathlib import Path
from typing import List, Optional

from .file_manager import FileManager
from .tree_builder import TreeBuilder

_DEFAULT_MAX_CONTEXT_SIZE = 1000000

def _env_int(name: str, default: int) -> int:
    ...

class ContextBuilder:
    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager
        self.max_context_size = _env_int("MAX_CONTEXT_SIZE", _DEFAULT_MAX_CONTEXT_SIZE)

    def build_files_context(self, filepaths):
        ...
        if total_size + len(file_context) > self.max_context_size:
            context_parts.append("⚠️ 컨텍스트 크기 제한으로 일부 파일이 생략되었습니다.")
            context_parts.append(f"=> total:{total_size} + context:{len(file_context)} > max_context_size:{self.max_context_size}\n")
```

#### 변경 후

```python
import fnmatch
from pathlib import Path
from typing import List, Optional

from .file_manager import FileManager
from .token_manager import TokenManager
from .tree_builder import TreeBuilder


class ContextBuilder:
    def __init__(self, file_manager: FileManager, max_tokens: int = None):
        self.file_manager = file_manager
        self.max_tokens = max_tokens if max_tokens is not None else TokenManager.DEFAULT_MAX_TOKENS

    def build_files_context(self, filepaths: List[Path]) -> str:
        context_parts = []
        total_size = 0
        max_chars = int(self.max_tokens * TokenManager.CHARS_PER_TOKEN)

        for filepath in filepaths:
            content = self.file_manager.read_file(filepath)
            if content is None:
                continue

            rel_path = filepath.relative_to(self.file_manager.workspace_dir)
            file_context = f"\n{'=' * 80}\n"
            file_context += f"📄 파일: {rel_path}\n"
            file_context += f"{'=' * 80}\n"
            file_context += f"```{filepath.suffix[1:] if filepath.suffix else ''}\n"
            file_context += content
            file_context += f"\n```\n"

            if total_size + len(file_context) > max_chars:
                context_parts.append("\n⚠️ 컨텍스트 크기 제한으로 일부 파일이 생략되었습니다.")
                context_parts.append(
                    f"=> total:{total_size} + context:{len(file_context)} "
                    f"> max_chars:{max_chars} ({self.max_tokens:,} tokens)\n"
                )
                break

            context_parts.append(file_context)
            total_size += len(file_context)

        return "\n".join(context_parts)
```

### 4.2 어시스턴트별 ContextBuilder 생성 변경

| 파일 | 변경 전 | 변경 후 |
|---|---|---|
| `src/claude_assistant.py` | `ContextBuilder(self.file_manager)` | `ContextBuilder(self.file_manager, max_tokens=TokenManager.MAX_TOKENS_CLAUDE)` |
| `src/genai_assistant.py` | `ContextBuilder(self.file_manager)` | `ContextBuilder(self.file_manager, max_tokens=TokenManager.MAX_TOKENS_GENAI)` |
| `src/gemini_assistant.py` | `ContextBuilder(self.file_manager)` | `ContextBuilder(self.file_manager, max_tokens=TokenManager.MAX_TOKENS_GEMINI)` |

> import 주의: `TokenManager`가 아직 import되지 않은 어시스턴트 파일이 있을 경우 추가 필요

### 4.3 플랫폼별 실제 문자 수 한도 (변경 후)

| 플랫폼 | max_tokens | max_chars (×3.5) |
|---|---|---|
| Claude  | 150,000 | 525,000자 |
| GenAI   | 96,000  | 336,000자 |
| Gemini  | 786,000 | 2,751,000자 |

> `.env`에서 `MAX_TOKENS_*` 값 변경 시 `TokenManager.reload_from_env()` 호출 후  
> ContextBuilder가 참조하는 `max_tokens`도 자동 반영됨

### 4.4 테스트 갱신 (`tests/test_context_builder.py`)

교체 대상 테스트:

| 기존 테스트 | 변경 사항 |
|---|---|
| `test_max_context_size_default` | `max_tokens` 기본값 = `TokenManager.DEFAULT_MAX_TOKENS` 확인으로 변경 |
| `test_max_context_size_from_env` | `MAX_CONTEXT_SIZE` env → `max_tokens` 직접 생성자 파라미터 전달로 변경 |
| `test_max_context_size_invalid_env_falls_back_to_default` | `MAX_CONTEXT_SIZE` env 테스트 제거 (환경변수 폐기) |
| `test_context_truncated_when_exceeds_max_context_size` | `context_builder.max_context_size = 100` → `context_builder.max_tokens` 직접 설정으로 변경 |

---

## 5. 변경 대상 파일 요약

| 파일 | 변경 유형 | 주요 변경 내용 |
|---|---|---|
| `src/context_builder.py` | 수정 | `max_context_size` 제거, `max_tokens` 도입, `_env_int`·`import os`·`_DEFAULT_MAX_CONTEXT_SIZE` 제거, `TokenManager` import 추가 |
| `src/claude_assistant.py` | 수정 | `ContextBuilder(file_manager, max_tokens=TokenManager.MAX_TOKENS_CLAUDE)` |
| `src/genai_assistant.py` | 수정 | `ContextBuilder(file_manager, max_tokens=TokenManager.MAX_TOKENS_GENAI)` |
| `src/gemini_assistant.py` | 수정 | `ContextBuilder(file_manager, max_tokens=TokenManager.MAX_TOKENS_GEMINI)` |
| `tests/test_context_builder.py` | 수정 | `max_context_size` 관련 테스트 4개 → `max_tokens` 기반으로 교체 |

**변경 없는 파일:**
- `src/token_manager.py` — 변경 불필요
- `src/context_processor.py` — 크기 제한 로직 없음
- `claude-ai-chat-code.py`, `gen-ai-chat-code.py`, `gemini-ai-chat-code.py` — 어시스턴트 파일에서 ContextBuilder를 직접 생성하지 않음

---

## 6. 폐기 항목

| 항목 | 위치 | 처리 |
|---|---|---|
| `_DEFAULT_MAX_CONTEXT_SIZE = 1000000` | `src/context_builder.py` | 삭제 |
| `_env_int()` 함수 | `src/context_builder.py` | 삭제 (TokenManager에 동일 함수 존재) |
| `self.max_context_size` 인스턴스 변수 | `src/context_builder.py` | `self.max_tokens`로 교체 |
| `MAX_CONTEXT_SIZE` 환경변수 | `.env`, 문서 | 폐기 — 대신 `MAX_TOKENS_CLAUDE` / `MAX_TOKENS_GENAI` / `MAX_TOKENS_GEMINI` 사용 |
| `import os` | `src/context_builder.py` | 삭제 |

---

## 7. 테스트 계획

| TC ID | 설명 | 기대 결과 |
|---|---|---|
| TC-01 | `max_tokens` 미전달 시 `TokenManager.DEFAULT_MAX_TOKENS` 사용 | `cb.max_tokens == TokenManager.DEFAULT_MAX_TOKENS` |
| TC-02 | `max_tokens=50000` 직접 전달 | `cb.max_tokens == 50000` |
| TC-03 | `max_tokens` 기반 max_chars 초과 시 생략 경고 포함 | 경고 메시지에 `tokens` 표기 포함 |
| TC-04 | Claude 어시스턴트 생성 시 `MAX_TOKENS_CLAUDE` 전달 확인 | `cb.max_tokens == TokenManager.MAX_TOKENS_CLAUDE` |
| TC-05 | GenAI 어시스턴트 생성 시 `MAX_TOKENS_GENAI` 전달 확인 | `cb.max_tokens == TokenManager.MAX_TOKENS_GENAI` |
| TC-06 | Gemini 어시스턴트 생성 시 `MAX_TOKENS_GEMINI` 전달 확인 | `cb.max_tokens == TokenManager.MAX_TOKENS_GEMINI` |

---

## 8. 참고

- `TokenManager.CHARS_PER_TOKEN = 3.5` — 문자 수 ↔ 토큰 수 환산 기준
- `TokenManager.reload_from_env()` — `.env` 변경 후 토큰 한도 갱신 (main 진입점에서 호출)
- 히스토리 트리밍 기준(`auto_trim_history`)과 컨텍스트 파일 읽기 제한이 동일한 `MAX_TOKENS_*` 값을 공유하므로 정책 일관성 확보
- 관련 FSD: `FSD_v1.0.063_token-manager-env-config.md`, `FSD_v1.0.070` (MAX_CONTEXT_SIZE 도입)
