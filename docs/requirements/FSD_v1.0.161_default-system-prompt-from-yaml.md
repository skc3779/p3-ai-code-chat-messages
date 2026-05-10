# FSD v1.0.161 — 기본 시스템 프롬프트의 YAML 외부화 및 `{{변수}}` 치환

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.161 |
| 작성일 | 2026-05-10 |
| 구현 예정일 | 2026-05-10 |
| 상태 | ✅ 구현 완료 (보강분 [ADD] 포함) |
| 선행 문서 | [FSD v1.0.020 — 프롬프트 템플릿 시스템](FSD_v1.0.020_prompt-templates.md), FSD v1.0.115 (agent_runner 시스템 프롬프트) |
| 대상 파일 | [src/claude_assistant.py](../../src/claude_assistant.py), [src/gemini_assistant.py](../../src/gemini_assistant.py), [src/genai_assistant.py](../../src/genai_assistant.py), [src/template_manager.py](../../src/template_manager.py), [.env.example](../../.env.example) |
| 신규 파일 | [src/prompt_renderer.py](../../src/prompt_renderer.py), [tests/test_prompt_renderer.py](../../tests/test_prompt_renderer.py), [tests/test_default_template_loading.py](../../tests/test_default_template_loading.py) |
| 관련 자산 | [.system_prompts/claude-system-prompt.yaml](../../.system_prompts/claude-system-prompt.yaml), [.system_prompts/gemini-system-prompt.yaml](../../.system_prompts/gemini-system-prompt.yaml), [.system_prompts/genai-system-prompt.yaml](../../.system_prompts/genai-system-prompt.yaml) |

---

## 1. 개요

### 1.1 배경

[FSD v1.0.020](FSD_v1.0.020_prompt-templates.md) 에서 `.system_prompts/*.yaml` 기반의 **선택적** 템플릿 교체 (`/template <name>`, `/template_list`, `/template_reset`) 를 도입했다. 그러나 **기본 시스템 프롬프트** 는 여전히 세 어시스턴트 소스에 하드코딩된 상태다:

- [src/claude_assistant.py:58-104](../../src/claude_assistant.py#L58-L104) — `self.default_system_prompt = """..."""`
- [src/gemini_assistant.py:63-104](../../src/gemini_assistant.py#L63-L104) — 동일 패턴
- [src/genai_assistant.py:66-122](../../src/genai_assistant.py#L66-L122) — 동일 패턴

세 위치 모두 본문 내부에 `_get_os_shell_hint()` 의 반환값을 문자열 연결로 끼워 넣고 있다 (예: `... + _get_os_shell_hint() + ...`). 결과적으로:

- 동일/유사 프롬프트가 세 파일에 분산되어 **유지보수 비용**이 크다.
- 프롬프트 본문 수정 시 코드 변경 → 재빌드/재배포가 필요해 **운영 효율**이 낮다.
- `.system_prompts/*.yaml` 파일과 **하드코딩 본문**이 이중으로 존재해 진실의 원천(SSoT) 이 모호하다.

### 1.2 목적

1. 세 어시스턴트의 기본 시스템 프롬프트를 **`.system_prompts/*.yaml` 파일에서 로드**하도록 변경한다.
2. `.env` 파일에 **타입별 기본 템플릿 파일명**을 명시한다:
   - `DEFAULT_CLAUDE_TEMPLATE`, `DEFAULT_GEMINI_TEMPLATE`, `DEFAULT_GENAI_TEMPLATE`
3. 사용자가 `/template <name>` 으로 명시 변경하지 않는 한 위 기본 템플릿을 사용한다 (FSD v1.0.020 의 사용자 명령어 동작은 그대로 유지).
4. 템플릿 본문 내 **`{{os_shell_hint}}`** 와 같은 `{{변수}}` 치환을 지원한다. 향후 다변수 확장을 위해 **`PromptRenderer`** 유틸리티를 도입한다.
5. 치환은 `_build_request_body()` 호출 **직전** 단계에서 수행하여, 컨텍스트(예: OS·셸) 가 변할 수 있는 시나리오에서도 항상 최신 값으로 LLM 에 전달되도록 한다.
6. **[ADD]** YAML 의 `assistant_type` 필드 기반 **`/template_list` 자동 필터링** — 어시스턴트가 자기 타입에 해당하지 않는 템플릿은 목록에서 숨긴다 (`assistant_type` 미지정 템플릿은 공용으로 모두 노출).
7. **[ADD]** **`/template_show`** 명령어 추가 — 현재 적용 중인 템플릿의 `name`, `description`, `assistant_type` 메타정보를 즉시 확인할 수 있다.

### 1.3 비범위

| 항목 | 비고 |
|---|---|
| `/template`, `/template_list`, `/template_reset` 동작 변경 | FSD v1.0.020 정의를 그대로 따른다 |
| `agent_runner.py._build_system_prompt()` 의 외부화 | 본 FSD 에서는 어시스턴트 3종만 다룬다. 에이전트 프롬프트 외부화는 후속 FSD 에서 검토 |
| YAML 스키마 v2 도입 | 기존 `name / description / assistant_type / system_prompt` 구조를 유지 (확장 필드만 추가 가능) |
| 다국어/지역화 | 본 FSD 범위 외 |

---

## 2. 현황 분석

### 2.1 하드코딩 위치 요약

| 파일 | 하드코딩 라인 | 변수 치환 패턴 |
|---|---|---|
| `src/claude_assistant.py` | 58~104 | `""" ... [실행 환경]\n""" + _get_os_shell_hint() + """\n..."""` |
| `src/gemini_assistant.py` | 63~104 | 동일 |
| `src/genai_assistant.py` | 66~122 | 동일 |

세 파일 모두 `__init__` 에서:
```python
self.default_system_prompt = """...[실행 환경]\n""" + _get_os_shell_hint() + """\n..."""
self.system_prompt = self.default_system_prompt
```
로 단 한 번 평가된다. 즉, 인스턴스 생성 시점의 OS·셸 힌트가 라이프사이클 동안 고정된다 (워크스페이스 전환 후에도 재계산되지 않음).

### 2.2 `.system_prompts/` 자산

이미 다음 파일이 존재하며 `{{os_shell_hint}}` 자리표시자도 포함되어 있다:

| 파일 | `name` | `assistant_type` | `{{os_shell_hint}}` 포함 여부 |
|---|---|---|---|
| `.system_prompts/claude-system-prompt.yaml` | `claude-system-prompt` | `claude` | ✅ ([L46-47](../../.system_prompts/claude-system-prompt.yaml#L46-L47)) |
| `.system_prompts/gemini-system-prompt.yaml` | `gemini-system-prompt` | `gemini` | ✅ ([L42-43](../../.system_prompts/gemini-system-prompt.yaml#L42-L43)) |
| `.system_prompts/genai-system-prompt.yaml` | `genai-system-prompt` | `genai` | ✅ ([L56-57](../../.system_prompts/genai-system-prompt.yaml#L56-L57)) |
| `.system_prompts/code-review.yaml` | `code-review` | (없음) | ❌ |

→ **구조 변경 없음**. 다만 본 FSD 는 자리표시자 처리 책임을 명시하고, 누락된 변수에 대한 정책을 정한다 (§ 3.5).

### 2.3 `TemplateManager` 현 상태 ([src/template_manager.py](../../src/template_manager.py))

- `get_template(name)` / `list_templates()` / `get_system_prompt(name, assistant_type)` 제공.
- 변수 치환은 **수행하지 않는다**. 즉, 호출자가 `{{os_shell_hint}}` 가 그대로 남은 문자열을 받게 된다 (회귀 위험).

### 2.4 `agent_runner.py._build_system_prompt()` 비교

[src/agent_runner.py:448-635](../../src/agent_runner.py#L448-L635) 는 한 함수 안에서 7+ 개의 변수 (`shell_type`, `shell_brief`, `os_hint`, `done_token`, 각 단계 매개변수) 를 f-string 문자열 연결로 합친다. 향후 어시스턴트 프롬프트가 동일한 다변수 합성 단계까지 진화할 가능성이 크므로, 본 FSD 는 **변수 치환 인터페이스** 를 일찍 추상화하여 추후 `_build_system_prompt()` 도 같은 유틸리티로 통합 이주할 수 있는 길을 연다 (§ 7).

---

## 3. 설계 (Design)

### 3.1 큰 그림

```
.env  ──(DEFAULT_*_TEMPLATE)──►  Assistant.__init__
                                    │
                                    ▼
                          TemplateManager.get_system_prompt
                          (raw YAML body, {{...}} 미치환)
                                    │
                                    ▼              ┌─ os_shell_hint = _get_os_shell_hint()
                          PromptRenderer.render ◄──┤
                                    │              └─ (확장 시) shell_type, shell_brief, ...
                                    ▼
                              system_prompt
                                    │
                                    ▼
                            _build_request_body()
                                    │
                                    ▼
                                LLM 호출
```

핵심 결정 두 가지:
1. **로딩**: `__init__` 시점에 `.env` 의 `DEFAULT_*_TEMPLATE` 으로 **원본(raw)** 프롬프트 본문만 캐시한다. 치환은 하지 않는다.
2. **치환**: `_build_request_body()` 호출 **직전** 마다 `PromptRenderer.render(raw, context)` 로 최종 프롬프트를 만든다. → OS/셸 변화·런타임 컨텍스트 반영 가능.

### 3.2 `.env` 변수

`.env.example` 에 다음 항목을 추가한다 (값은 **파일명 stem**, `.yaml` 확장자 제외):

```ini
# ─── 기본 시스템 프롬프트 템플릿 (FSD v1.0.161) ───────────────
# 값은 .system_prompts/<filename>.yaml 의 파일명 stem(확장자 제외)
DEFAULT_CLAUDE_TEMPLATE=claude-system-prompt
DEFAULT_GEMINI_TEMPLATE=gemini-system-prompt
DEFAULT_GENAI_TEMPLATE=genai-system-prompt
```

**해석 규칙**

| 케이스 | 동작 |
|---|---|
| 변수 미설정 | 어시스턴트 타입별 하드코딩 fallback 이름 (`claude-system-prompt` 등) 사용 |
| 변수 값이 빈 문자열 | 미설정과 동일하게 처리 |
| `.yaml` 확장자가 포함된 값 (`gemini-system-prompt.yaml`) | 확장자를 제거하여 이름으로 사용 (관용 처리) |
| 해당 이름의 YAML 미존재 | **오류 메시지 stderr 출력 후 `assistant_type` 별 fallback 본문** 사용 (§ 3.6) |

**TemplateManager 의 키 매칭**: `TemplateManager` 는 YAML 의 `name:` 필드를 키로 사용한다. 본 FSD 의 `.env` 변수 값은 **파일명 stem** 이며, 관례상 `name:` 과 일치하지만 다를 수 있다. 따라서 다음 두 단계로 조회한다:

```python
def _resolve_default_template(tm: TemplateManager, env_value: str | None,
                              assistant_type: str) -> str | None:
    """파일명 stem 우선 → name 필드 fallback. raw system_prompt 본문을 반환."""
    if not env_value:
        env_value = f"{assistant_type}-system-prompt"  # 기본 fallback 파일명
    stem = env_value.removesuffix(".yaml")

    # 1) 파일명으로 직접 로드
    file_path = tm.prompts_path / f"{stem}.yaml"
    if file_path.is_file():
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get(f"{assistant_type}_system_prompt") or data.get("system_prompt")

    # 2) name: 필드로 조회
    return tm.get_system_prompt(stem, assistant_type)
```

→ 사용자가 파일명을 그대로 `.env` 에 적든, `name:` 값을 적든 모두 동작한다. 권장은 **파일명 stem** (요구사항 명세).

### 3.3 신규 모듈 — `src/prompt_renderer.py`

#### 3.3.1 책임

- `{{변수명}}` 형식의 자리표시자를 `dict` 컨텍스트로 치환한다.
- 누락된 변수 / 잉여 변수 / 중첩 / 재귀를 일관된 정책으로 처리한다.
- `string.Template` (`$var` 문법) 이 아닌 **`{{var}}`** 문법을 채택 — `.system_prompts/*.yaml` 의 기존 자리표시자 표기 및 다른 LLM 도구 생태계 (Jinja, Langchain) 와 일관성 유지.

#### 3.3.2 인터페이스

```python
# src/prompt_renderer.py
import re
from typing import Mapping

class PromptRenderer:
    """`{{key}}` 자리표시자를 dict 로 치환하는 경량 렌더러.

    - Jinja2 종속을 도입하지 않는다 (현 프로젝트 의존성 최소화 원칙).
    - 1패스 비재귀 치환. 값에 또 다른 `{{...}}` 가 있어도 재치환하지 않는다.
    - 누락된 변수는 정책에 따라 (a) 빈 문자열로, (b) 자리표시자 보존, (c) 예외 중 선택 가능.
    """

    _PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

    class MissingVariableError(KeyError):
        pass

    @classmethod
    def render(
        cls,
        template: str,
        context: Mapping[str, object],
        *,
        on_missing: str = "keep",   # "keep" | "empty" | "raise"
    ) -> str:
        def repl(m: re.Match) -> str:
            key = m.group(1)
            if key in context:
                return str(context[key])
            if on_missing == "empty":
                return ""
            if on_missing == "raise":
                raise cls.MissingVariableError(key)
            return m.group(0)  # keep
        return cls._PATTERN.sub(repl, template)

    @classmethod
    def find_variables(cls, template: str) -> list[str]:
        """템플릿에 등장한 변수명을 등장 순으로 (중복 제거하여) 반환한다."""
        seen, out = set(), []
        for m in cls._PATTERN.finditer(template):
            k = m.group(1)
            if k not in seen:
                seen.add(k); out.append(k)
        return out
```

#### 3.3.3 왜 Jinja2/`string.Template` 가 아닌가

| 후보 | 채택 안 함 이유 |
|---|---|
| `string.Template` ([stdlib](https://docs.python.org/3/library/string.html#template-strings)) | `$var` 문법. 기존 YAML 의 `{{var}}` 와 불일치 — YAML 본문 수정 부담 |
| `str.format_map` | `{name}` 문법, YAML 의 `{` 가 모두 충돌. 이스케이프 불편 |
| **Jinja2** | 강력하지만 의존성/렌더 비용/보안 (loader, autoescape) 부담. 본 프로젝트는 단순 1패스 변수 치환만 필요 |
| **자체 정규식 렌더러 (채택)** | 30 LoC, 무의존, 향후 필요 시 Jinja2 로 무손실 이식 가능 (`{{var}}` 문법 호환) |

**확장 여지**: 향후 분기/반복이 필요해지는 시점에 `PromptRenderer` 를 Jinja2 어댑터로 교체해도, **`{{var}}` 자리표시자 문법이 동일**하므로 YAML 자산 수정 없이 이주 가능하다.

### 3.4 어시스턴트 3종 변경

#### 3.4.1 공통 변경 패턴

`__init__` 의 하드코딩 본문 블록 (예: `claude_assistant.py:58-104`) 을 다음으로 대체한다:

```python
import os
# ...
self.template_manager = TemplateManager(self.file_manager.workspace_dir)

# (1) 기본 템플릿 이름 결정 — .env 우선, 없으면 어시스턴트 타입별 fallback
default_name = os.getenv("DEFAULT_CLAUDE_TEMPLATE") or "claude-system-prompt"   # claude
# default_name = os.getenv("DEFAULT_GEMINI_TEMPLATE") or "gemini-system-prompt"  # gemini
# default_name = os.getenv("DEFAULT_GENAI_TEMPLATE")  or "genai-system-prompt"   # genai

# (2) 원본(raw) 프롬프트 본문 로드 — 변수 치환 전 상태
self._default_template_name = default_name
raw = _resolve_default_template(self.template_manager, default_name, "claude")
if raw is None:
    print(f"⚠️ 기본 템플릿 '{default_name}' 을 찾지 못해 내장 fallback 을 사용합니다.")
    raw = _BUILTIN_FALLBACK_CLAUDE  # § 3.6
self._raw_system_prompt = raw

# (3) 호환을 위한 default_system_prompt — 치환 후 1회 평가본
self.default_system_prompt = self._render_system_prompt(raw)
self.system_prompt = self.default_system_prompt
```

**`_render_system_prompt()`** 는 다음과 같이 인스턴스 메서드로 추가한다:

```python
def _render_system_prompt(self, raw: str | None = None) -> str:
    """현재 컨텍스트로 raw 프롬프트의 {{변수}} 를 치환한 최종 본문을 반환."""
    raw = raw if raw is not None else self._raw_system_prompt
    ctx = self._build_template_context()
    return PromptRenderer.render(raw, ctx, on_missing="keep")

def _build_template_context(self) -> dict[str, str]:
    """렌더 컨텍스트 — 현재는 os_shell_hint 만 제공.
    향후 변수 추가는 이 메서드에 한 줄씩 추가하면 된다."""
    return {
        "os_shell_hint": _get_os_shell_hint(),
    }
```

#### 3.4.2 `_build_request_body()` 호출 직전 치환

세 어시스턴트 모두 `chat()` → `_chat_streaming()` / `_chat_non_streaming()` → `_build_request_body()` 의 흐름을 가진다. 본 FSD 는 **`_build_request_body()` 호출 직전**에 `self.system_prompt` 를 재렌더한다:

```python
# 예: src/gemini_assistant.py:_chat_streaming
def _chat_streaming(self, user_message: str) -> str:
    # FSD v1.0.161: 매 호출 직전 변수 재치환
    self.system_prompt = self._render_system_prompt(self._raw_system_prompt_active())
    body = self._build_request_body(user_message)
    ...
```

여기서 `_raw_system_prompt_active()` 는:
- 사용자가 `/template <name>` 으로 변경한 경우: 해당 템플릿의 raw 본문
- 변경하지 않은 경우: `self._raw_system_prompt` (기본)
- `/template_reset` 이후: `self._raw_system_prompt`

```python
def _raw_system_prompt_active(self) -> str:
    return getattr(self, "_active_raw_system_prompt", self._raw_system_prompt)
```

#### 3.4.3 `set_system_prompt_from_template()` / `reset_system_prompt()` 변경

현재 ([gemini_assistant.py:108-118](../../src/gemini_assistant.py#L108-L118)) 는 `TemplateManager.get_system_prompt()` 의 결과를 **그대로** `self.system_prompt` 에 저장한다 (변수 미치환 → 회귀). 본 FSD 변경:

```python
def set_system_prompt_from_template(self, template_name: str) -> bool:
    raw = self.template_manager.get_system_prompt(template_name, "gemini")
    if raw is None:
        return False
    self._active_raw_system_prompt = raw
    self.system_prompt = self._render_system_prompt(raw)
    return True

def reset_system_prompt(self) -> None:
    self._active_raw_system_prompt = self._raw_system_prompt
    self.system_prompt = self.default_system_prompt
```

> 결과적으로 `_build_request_body()` 직전 재렌더와 결합하여, 어떤 경로로 프롬프트가 바뀌어도 항상 변수가 치환된 상태로 LLM 에 전달된다.

### 3.5 `{{os_shell_hint}}` 미치환 정책

| 케이스 | 처리 |
|---|---|
| 컨텍스트에 `os_shell_hint` 키 존재 | `_get_os_shell_hint()` 반환값으로 치환 |
| 키 누락 (개발자 실수) | `on_missing="keep"` → 자리표시자가 그대로 남아 **로그/리뷰에서 즉시 발견** 가능 |
| 잉여 변수 (`{{some_unknown}}`) | 동일하게 keep — silently drop 하지 않는다 (디버깅 용이) |

`on_missing="raise"` 모드는 본 FSD 의 단위 테스트 (T-04) 와 향후 strict 검증 시점에 사용한다. 운영 경로는 `keep` 으로 유지해 회귀 시에도 LLM 에 빈 문자열이 흘러가지 않도록 한다.

### 3.6 빌트인 Fallback

`.system_prompts/` 디렉토리 자체가 없거나 (`pyinstaller` onefile 배포 등), `.env` 가 잘못된 이름을 가리키는 경우를 대비해 **각 어시스턴트 모듈 내부에 기존 본문을 fallback 상수**로 보존한다:

```python
# src/claude_assistant.py 모듈 상단
_BUILTIN_FALLBACK_CLAUDE = """당신은 Anthropic의 ... [실행 환경]\n{{os_shell_hint}}\n..."""
```

→ 본문은 기존 `default_system_prompt` 와 동일하되, `_get_os_shell_hint()` 직접 연결 대신 **`{{os_shell_hint}}`** 로 변경하여 동일 렌더 경로를 통과한다.

> **유지보수 부담 절감 원칙**: fallback 은 "빌드물에 자산이 동봉되지 않은 비상 시" 안전망일 뿐이며, **정상 경로는 YAML** 이라는 점을 코드 주석에 명시한다.

### 3.7 [ADD] `/template_list` 의 `assistant_type` 자동 필터링

#### 3.7.1 배경

기존 `TemplateManager.list_templates()` 는 `.system_prompts/` 의 모든 YAML 을 어시스턴트 타입과 무관하게 반환했다. 결과적으로 Claude REPL 에서 `/template_list` 를 실행하면 `gemini-system-prompt`, `genai-system-prompt` 까지 함께 노출되어 **사용자가 잘못된 타입의 템플릿을 선택**할 위험이 있었다.

#### 3.7.2 설계

`TemplateManager.list_templates(assistant_type: Optional[str] = None)` 에 옵션 인자를 추가한다. 동작 정책:

| 케이스 | 동작 |
|---|---|
| `assistant_type=None` (기본) | 모든 템플릿 반환 — 호환성 유지 |
| `assistant_type="claude"` | YAML 의 `assistant_type` 가 `"claude"` 이거나 **필드 자체가 없는** 항목만 반환 |
| `gemini` / `genai` | 동일 정책 |

`assistant_type` 필드가 없는 템플릿(예: `code-review.yaml`)은 **공용** 으로 간주하여 모든 타입에서 노출된다. 반환 dict 에 `assistant_type` 키도 포함되어, REPL 출력에서 `[claude]` / `[공용]` 등으로 표시할 수 있다.

각 어시스턴트의 `list_templates()` 는 자기 타입을 자동으로 전달한다:

```python
# claude_assistant.py
def list_templates(self) -> List[Dict[str, str]]:
    return self.template_manager.list_templates(assistant_type="claude")
```

→ REPL 진입점은 변경 없이 동작이 자동 필터링된다.

### 3.8 [ADD] `/template_show` — 현재 적용 중인 템플릿 조회

#### 3.8.1 배경

`/template <name>` 으로 변경하거나 `.env` 의 `DEFAULT_*_TEMPLATE` 으로 기본값을 바꾼 뒤, 현재 어떤 템플릿이 LLM 에 전달되는지 **확인할 방법이 없었다**. 디버깅·운영 측면에서 자주 필요한 동작이다.

#### 3.8.2 설계

각 어시스턴트가 `_active_template_name` 을 추적한다:

| 시점 | 갱신 |
|---|---|
| `__init__` | `.env` 의 `DEFAULT_*_TEMPLATE` 값 (또는 타입별 기본 파일명) 으로 초기화 |
| `set_system_prompt_from_template(name)` 성공 | `name` 으로 갱신 |
| `reset_system_prompt()` | `_default_template_name` 으로 복귀 |

`get_active_template_info()` 메서드가 `_active_template_name` 을 키로 `TemplateManager.get_template_info()` 를 호출해 다음 dict 를 반환한다:

```python
{
    "name":           "claude-system-prompt",
    "description":    "전문 개발자 관점의 프로젝트 파일 분석, 코드 생성, 문서 작성",
    "assistant_type": "claude",
}
```

빌트인 fallback 사용 중이거나 메타가 없으면 `description` 자리에 안내 문구를 채우고 `name` 은 `_active_template_name` 그대로 반환한다 (정보 손실 없음).

#### 3.8.3 REPL 출력 예시

```
> /template_show

📌 현재 적용 중인 템플릿:
   - name           : claude-system-prompt
   - description    : 전문 개발자 관점의 프로젝트 파일 분석, 코드 생성, 문서 작성
   - assistant_type : claude
```

`assistant_type` 가 빈 문자열인 공용 템플릿(`code-review`)은 `(공용)` 으로 표시한다.

#### 3.8.4 명령 등록

`src/command_registry.py` 의 `_register_default_commands()` 에 `/template_show` 항목을 추가하여 `/help`, 자동 완성, 슬래시 명령 추천(FSD v1.0.046) 시스템에서 일관되게 노출되도록 한다.

### 3.9 PyInstaller 배포 호환

`.system_prompts/` 는 패키지 내부가 아닌 **워크스페이스(`workspace_dir`)** 기준으로 탐색되므로 ([template_manager.py:19-21](../../src/template_manager.py#L19-L21)), PyInstaller 단일 실행 파일 빌드에서도 **사용자 워크스페이스에 `.system_prompts/` 가 있으면** 정상 동작한다. 워크스페이스에 없으면 § 3.6 의 fallback 으로 진입한다.

> **권장 배포**: 빌드 산출물과 함께 `.system_prompts/` 디렉토리를 **샘플 자산** 으로 동봉한다 (FSD v1.0.065 의 PyInstaller spec 에 추가). 본 FSD 의 spec 변경 항목은 § 5 참조.

---

## 4. 요구사항

### 4.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-01 | `.env` 의 `DEFAULT_CLAUDE_TEMPLATE` / `DEFAULT_GEMINI_TEMPLATE` / `DEFAULT_GENAI_TEMPLATE` 값을 파일명 stem 으로 해석해 `.system_prompts/<stem>.yaml` 을 로드한다 | 필수 |
| FR-02 | `.env` 미설정 시 어시스턴트 타입별 기본 파일명 (`claude-system-prompt`, `gemini-system-prompt`, `genai-system-prompt`) 을 사용한다 | 필수 |
| FR-03 | 값에 `.yaml` 확장자가 포함되어도 정상 처리한다 | 필수 |
| FR-04 | 지정된 템플릿이 없으면 stderr 경고 후 빌트인 fallback 본문을 사용하며, **프로세스는 정상 기동한다** | 필수 |
| FR-05 | 템플릿 본문의 `{{os_shell_hint}}` 는 `_get_os_shell_hint()` 결과로 치환된다 | 필수 |
| FR-06 | 정의되지 않은 `{{변수}}` 는 자리표시자 형태로 보존된다 (silently drop 금지) | 필수 |
| FR-07 | `_build_request_body()` 호출 직전 시점에 변수 재치환이 수행된다 | 필수 |
| FR-08 | `/template <name>` 으로 변경 시에도 변수 치환이 적용된다 (set_system_prompt_from_template) | 필수 |
| FR-09 | `/template_reset` 후 기본 템플릿(.env 지정) 의 본문으로 복귀한다 | 필수 |
| FR-10 | `PromptRenderer` 는 `{{var}}` 문법, 1패스 비재귀, `on_missing` 정책 (`keep`/`empty`/`raise`) 을 지원한다 | 필수 |
| FR-11 | 사용자가 `/template` 명령을 실행하지 않은 경우 기본 템플릿이 그대로 유지된다 | 필수 |
| FR-12 | **[ADD]** `TemplateManager.list_templates(assistant_type=...)` 는 해당 타입과 일치하거나 `assistant_type` 필드가 없는 템플릿만 반환한다 | 필수 |
| FR-13 | **[ADD]** 각 어시스턴트의 `list_templates()` 는 내부적으로 자기 타입(`claude`/`gemini`/`genai`)을 자동 전달한다 | 필수 |
| FR-14 | **[ADD]** `list_templates()` 반환 dict 에 `assistant_type` 키가 포함된다 | 필수 |
| FR-15 | **[ADD]** `/template_show` 명령은 `name`, `description`, `assistant_type` 을 포함한 현재 활성 템플릿 메타를 출력한다 | 필수 |
| FR-16 | **[ADD]** `set_system_prompt_from_template()` 성공 시 `_active_template_name` 이 갱신되고, `reset_system_prompt()` 시 `_default_template_name` 으로 복귀한다 | 필수 |
| FR-17 | **[ADD]** 빌트인 fallback 본문 사용 중에도 `/template_show` 는 안전하게 정보(또는 안내 문구)를 반환한다 | 필수 |

### 4.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-01 | 외부 의존성 추가 없음 (Jinja2 등 비도입) |
| NFR-02 | `_build_request_body()` 직전 재렌더로 인한 추가 비용은 무시 가능해야 한다 (1KB 본문, < 0.1ms) |
| NFR-03 | 기존 `/template`, `/template_list`, `/template_reset` 동작과 회귀 없음 (FSD v1.0.020) |
| NFR-04 | 세 어시스턴트의 시스템 프롬프트 정의는 **단일 진실 원천 = `.system_prompts/*.yaml`** 로 수렴한다 (fallback 은 비상용) |
| NFR-05 | PyInstaller 빌드 환경에서도 동작해야 한다 (FSD v1.0.065 호환) |

---

## 5. 변경 파일 요약

| 파일 | 변경 내용 |
|---|---|
| `.env.example` | `DEFAULT_CLAUDE_TEMPLATE`, `DEFAULT_GEMINI_TEMPLATE`, `DEFAULT_GENAI_TEMPLATE` 항목 추가 (주석 포함) |
| `src/prompt_renderer.py` (신규) | `PromptRenderer` 클래스 — `{{var}}` 1패스 치환, `on_missing` 정책 |
| `src/template_manager.py` | `_resolve_default_template()` 헬퍼 함수 추가 (또는 `TemplateManager` 메서드로 흡수). 기존 동작 유지 |
| `src/claude_assistant.py` | (1) 하드코딩 `default_system_prompt` 삭제, (2) `_BUILTIN_FALLBACK_CLAUDE` 상수로 대체 (`{{os_shell_hint}}` 사용), (3) `_raw_system_prompt`, `_active_raw_system_prompt`, `_render_system_prompt`, `_build_template_context`, `_raw_system_prompt_active` 추가, (4) `set_system_prompt_from_template`/`reset_system_prompt` 변수 치환 적용, (5) `_chat_streaming`/`_chat_non_streaming` 진입부에서 `_build_request_body` 직전 재렌더 |
| `src/gemini_assistant.py` | 동일 패턴 |
| `src/genai_assistant.py` | 동일 패턴 |
| `tests/test_prompt_renderer.py` (신규) | § 6.1 테스트 |
| `tests/test_default_template_loading.py` (신규) | § 6.2 테스트 |
| **[ADD]** `src/template_manager.py` | `list_templates(assistant_type=None)` 시그니처 변경, `get_template_info(name)` 메서드 추가 |
| **[ADD]** `src/claude_assistant.py` / `src/gemini_assistant.py` / `src/genai_assistant.py` | `_active_template_name` 추적, `list_templates()` 자동 필터, `get_active_template_info()` 추가 |
| **[ADD]** `claude-ai-chat-code.py` / `gemini-ai-chat-code.py` / `gen-ai-chat-code.py` | `/template_show` 핸들러 추가, `/template_list` 출력에 `[assistant_type]` 표기 |
| **[ADD]** `src/command_registry.py` | `/template_show` `CommandInfo` 등록, `/template_list` 설명 갱신 |
| **[ADD]** `tests/test_template_filter_and_show.py` (신규) | § 6.4 보강 테스트 |
| `README.md` | "기본 시스템 프롬프트 변경" 섹션 추가 (§ 9) |

> PyInstaller spec 파일이 별도 존재한다면 `.system_prompts/` 자산 동봉 룰을 추가한다 (작업 산출물에 포함되어 있지 않다면 본 FSD 범위 외).

---

## 6. 테스트 케이스

### 6.1 단위 테스트 — `tests/test_prompt_renderer.py`

| ID | 테스트 | 기대 결과 |
|---|---|---|
| T-01 | `PromptRenderer.render("hi {{name}}", {"name":"Bob"})` | `"hi Bob"` |
| T-02 | 공백 허용 — `"{{ name }}"` 치환 | `"Bob"` |
| T-03 | 누락 변수 keep | `"hi {{age}}"` 그대로 유지 |
| T-04 | 누락 변수 raise | `MissingVariableError` 발생 |
| T-05 | 1패스 비재귀 — 값이 `"{{x}}"` 인 경우 재치환되지 않음 | `"{{x}}"` 그대로 |
| T-06 | `find_variables("{{a}}{{b}}{{a}}")` | `["a","b"]` (중복 제거, 등장순) |
| T-07 | 잘못된 식별자 (`{{1abc}}`) 무시 | 자리표시자 보존 |

### 6.2 단위 테스트 — `tests/test_default_template_loading.py`

| ID | 테스트 | 기대 결과 |
|---|---|---|
| T-10 | `.env` 에 `DEFAULT_CLAUDE_TEMPLATE=claude-system-prompt` → `ClaudeCodeAssistant.system_prompt` 에 `{{os_shell_hint}}` 가 치환된 본문 포함 | `"Windows" / "PowerShell" / "bash"` 등 OS 힌트 키워드 포함 |
| T-11 | `DEFAULT_GEMINI_TEMPLATE` 미설정 → fallback 으로 `gemini-system-prompt` 사용 | 정상 로드 |
| T-12 | 존재하지 않는 이름 (`DEFAULT_CLAUDE_TEMPLATE=ghost`) | stderr 경고 + 빌트인 fallback 사용, 인스턴스 생성 성공 |
| T-13 | `.yaml` 확장자 포함된 값 (`gemini-system-prompt.yaml`) | 정상 로드 |
| T-14 | `/template <name>` 호출 후 `_build_request_body()` 직전 → 재렌더 호출 발생 (mock) | `_render_system_prompt` 1회 호출 |
| T-15 | `/template_reset` 후 기본 본문 복귀 | `system_prompt` == `default_system_prompt` |
| T-16 | YAML 본문에 `{{os_shell_hint}}` 누락 — `claude-system-prompt` 의 본문을 임시 수정한 fixture | 누락 변수 정책에 따라 본문 그대로 LLM 전달 (회귀 없음) |

### 6.3 회귀 테스트 (FSD v1.0.020)

| ID | 테스트 | 기대 결과 |
|---|---|---|
| T-20 | `/template_list` 출력 | 자기 타입 + 공용(`assistant_type` 미지정) 템플릿만 표시 (FSD v1.0.161 [ADD] 반영) |
| T-21 | `/template code-review` 적용 후 첫 메시지 | 시스템 프롬프트가 `code-review` 본문으로 교체됨 |
| T-22 | `/template_reset` | 기본 템플릿 (`.env` 의 `DEFAULT_*_TEMPLATE`) 으로 복귀 |

### 6.4 [ADD] 단위 테스트 — `tests/test_template_filter_and_show.py`

| ID | 테스트 | 기대 결과 |
|---|---|---|
| T-30 | `TemplateManager.list_templates(assistant_type="claude")` | `claude-system-prompt`, `code-review`(공용) 포함 / `gemini-*`, `genai-*` 제외 |
| T-31 | `assistant_type="gemini"` | `gemini-system-prompt`, `code-review` 포함 / 그 외 제외 |
| T-32 | `assistant_type="genai"` | `genai-system-prompt`, `code-review` 포함 / 그 외 제외 |
| T-33 | `assistant_type=None` (호환) | 모든 템플릿 반환 |
| T-34 | 반환 dict 에 `assistant_type` 키 존재 | 모든 항목에 키 포함 |
| T-35 | `get_template_info(name)` — 캐시 / 파일명 stem / `.yaml` 확장자 / 미존재 4 케이스 | 정상 동작 / 미존재는 `None` |
| T-36 | 어시스턴트의 `list_templates()` 자동 필터 (3종) | 자기 타입만 노출 |
| T-37 | `get_active_template_info()` 라이프사이클 — 초기 / `set_system_prompt_from_template` / `reset_system_prompt` | `name` 이 각 시점에 맞게 갱신됨 |
| T-37b | 빌트인 fallback (`DEFAULT_*=ghost-xyz`) 사용 시 `get_active_template_info()` | `name="ghost-xyz"`, `assistant_type` 어시스턴트 타입, 안내 문구 포함 |

---

## 7. 다변수 치환 — 권장 진화 경로 (Suggestion)

> 사용자 요청: *"`agent_runner.py` 의 `_build_system_prompt()` 처럼 여러 변수가 필요해질 수 있어 더 좋은 방법이 있으면 제안해줘."*

### 7.1 권장: `PromptRenderer` + **컨텍스트 빌더 함수**

```python
def _build_template_context(self) -> dict[str, str]:
    return {
        "os_shell_hint":  _get_os_shell_hint(),
        # 향후 추가:
        # "shell_type":   TerminalExecutor.get_shell_type(),
        # "shell_brief":  TerminalExecutor.agent_shell_brief(),
        # "done_token":   self.done_token,
        # "workspace":    str(self.file_manager.workspace_dir),
    }
```

**이유:**

1. **변경 비용 최소** — 변수 한 개를 추가할 때 (a) YAML 본문에 `{{key}}` 추가, (b) 컨텍스트 빌더에 키 한 줄 추가, 끝.
2. **테스트 용이** — `_build_template_context()` 를 monkeypatch 해 결정적 fixture 로 만들 수 있음.
3. **이주 호환** — 향후 Jinja2/Liquid 등 본격 템플릿 엔진으로 교체 시 `{{var}}` 문법이 동일해 YAML 자산 무수정.
4. **agent_runner 통합 길** — `agent_runner._build_system_prompt()` 도 `.system_prompts/agent-runner.yaml` 로 외부화하고 동일 `PromptRenderer` 로 렌더하면, 본 FSD 가 닦은 인프라를 재사용 가능 (후속 FSD 에서 다룬다).

### 7.2 비추천 대안

| 대안 | 비추천 이유 |
|---|---|
| **f-string 문자열 연결** (현재 `agent_runner` 방식) | 본문이 코드에 묶임 → 외부화 불가 |
| **`str.format_map`** | `{` 가 자연어 본문에 흔함 → 충돌·이스케이프 부담 |
| **Jinja2 즉시 도입** | 현재 시점엔 분기/반복 미사용. 의존성 추가만 부담. **필요 시점에 어댑터 교체** 가 더 합리적 |
| **YAML 내 `!substitute` 커스텀 태그** | YAML 처리 복잡도 ↑. 다른 도구와의 호환성 ↓ |

### 7.3 (옵션) 명시 검증 단계

`PromptRenderer.find_variables(raw)` 를 활용해 **로딩 시점**에 누락된 변수를 경고할 수 있다:

```python
declared = set(self._build_template_context().keys())
required = set(PromptRenderer.find_variables(raw))
missing = required - declared
if missing:
    print(f"⚠️ 템플릿이 요구하는 변수가 컨텍스트에 없습니다: {missing}")
```

조기 발견 ↔ 운영 안정성의 트레이드오프이므로, 본 FSD 는 **경고만** (raise 없음) 권장한다.

---

## 8. 마이그레이션 체크리스트

- [x] `src/prompt_renderer.py` 신규 작성 + 단위 테스트 7건 통과
- [x] `src/template_manager.py` 에 `_resolve_default_template()` 헬퍼 추가 (또는 모듈 함수로 분리)
- [x] `src/claude_assistant.py` — 하드코딩 본문 → fallback 상수, `_render_system_prompt` 도입, `_build_request_body` 직전 재렌더
- [x] `src/gemini_assistant.py` 동일 변경
- [x] `src/genai_assistant.py` 동일 변경
- [x] `.env.example` 에 `DEFAULT_*_TEMPLATE` 3종 추가
- [x] 테스트 16건 (T-01 ~ T-16) + 회귀 3건 (T-20 ~ T-22) 통과
- [x] **[ADD]** `TemplateManager.list_templates(assistant_type=...)` / `get_template_info()` 추가
- [x] **[ADD]** 3 어시스턴트의 `_active_template_name` 추적 + `get_active_template_info()` + 자동 필터 적용
- [x] **[ADD]** 3 엔트리포인트에 `/template_show` 핸들러 추가, `/template_list` 출력에 `[assistant_type]` 표시
- [x] **[ADD]** `src/command_registry.py` 에 `/template_show` 등록
- [x] **[ADD]** 보강 테스트 13건 (T-30 ~ T-37b) 통과
- [ ] **FSD 구현 완료 후 `docs/releases` 폴더에 `RELEASE-v1.0.161` 문서 업데이트**
- [ ] **README.md 파일 업데이트** — § 9 가이드 반영 ([ADD] 항목 포함)

---

## 9. README 업데이트 가이드 (참고)

README 에 다음 섹션을 추가/갱신한다 (정확한 헤딩 위치는 README 의 기존 구조에 따른다):

````markdown
### 기본 시스템 프롬프트 (FSD v1.0.161)

세 어시스턴트의 기본 시스템 프롬프트는 `.system_prompts/*.yaml` 에서 로드된다.
어떤 파일을 기본값으로 쓸지는 `.env` 의 다음 변수로 지정한다 (값은 파일명 stem):

```ini
DEFAULT_CLAUDE_TEMPLATE=claude-system-prompt
DEFAULT_GEMINI_TEMPLATE=gemini-system-prompt
DEFAULT_GENAI_TEMPLATE=genai-system-prompt
```

런타임에 `/template <name>` 으로 다른 템플릿으로 교체할 수 있고, `/template_reset`
으로 위 기본값으로 복귀한다 (FSD v1.0.020).

템플릿 본문에는 `{{os_shell_hint}}` 와 같은 변수를 쓸 수 있으며, LLM 호출
직전마다 현재 OS / 셸에 맞춰 자동 치환된다.

**[ADD] 슬래시 명령어 보강 (v1.0.161)**

- `/template_list` — 현재 어시스턴트 타입과 호환되는 템플릿만 표시
  (`assistant_type` 필드가 없는 공용 템플릿은 모든 타입에서 노출).
  각 항목 옆에 `[claude]` / `[gemini]` / `[genai]` / `[공용]` 태그가 표시된다.
- `/template_show` — 현재 적용 중인 템플릿의 `name`, `description`,
  `assistant_type` 메타정보를 조회한다.
````

---

## 10. 승인 체크리스트

- [x] FSD 문서 검토 완료
- [x] 코드 구현 완료 (3 어시스턴트 + PromptRenderer)
- [x] 테스트 16건 + 회귀 3건 전체 통과 (1차 구현)
- [x] 세 어시스턴트의 LLM 호출 시 `{{os_shell_hint}}` 가 모두 실제 값으로 치환되어 전달되는지 수동 확인
- [x] **[ADD]** `/template_list` 자동 필터링 + `/template_show` 보강 구현 완료
- [x] **[ADD]** 보강 테스트 13건(T-30~T-37b) 통과 (전체 누적 35건 + 회귀 614 passed)
- [ ] **FSD 구현 완료 후 `docs/releases` 폴더에 `RELEASE-v1.0.161` 문서 업데이트**
- [ ] **README.md 파일 업데이트**
