# Release v1.0.161

## 주요 변경 사항

### 기본 시스템 프롬프트의 YAML 외부화 (FSD v1.0.161)

세 어시스턴트(Claude, Gemini, GenAI)의 **기본 시스템 프롬프트**가 더 이상 소스 코드에 하드코딩되지 않습니다. 이제 `.system_prompts/*.yaml` 파일이 단일 진실 원천(SSoT)이며, 어떤 파일을 기본값으로 쓸지는 `.env` 변수로 지정합니다.

#### `.env` 기본 템플릿 설정

```ini
# 값은 .system_prompts/<filename>.yaml 의 파일명 stem(확장자 제외)
DEFAULT_CLAUDE_TEMPLATE=claude-system-prompt
DEFAULT_GEMINI_TEMPLATE=gemini-system-prompt
DEFAULT_GENAI_TEMPLATE=genai-system-prompt
```

- 변수 미설정 시 어시스턴트 타입별 기본 파일명(`<type>-system-prompt`)을 사용합니다.
- `.yaml` 확장자가 포함된 값(`gemini-system-prompt.yaml`)도 정상 처리됩니다.
- 지정된 파일이 없으면 stderr 경고 후 모듈 내 빌트인 fallback 본문을 사용하며, **프로세스는 정상 기동**합니다.

#### `{{변수}}` 자리표시자 치환

YAML 본문 내 `{{os_shell_hint}}` 와 같은 자리표시자가 LLM 호출 직전마다 현재 OS/셸에 맞춰 자동 치환됩니다.

- 신규 모듈 `src/prompt_renderer.py` — `{{key}}` 1패스 비재귀 치환, `on_missing` 정책(`keep`/`empty`/`raise`).
- 누락된 변수는 자리표시자 형태로 보존되어(silently drop 금지) 디버깅이 쉽습니다.
- Jinja2 등 외부 의존성을 추가하지 않았습니다 (의존성 최소화 원칙).

#### 향후 다변수 확장

각 어시스턴트의 `_build_template_context()` 에 키 한 줄을 추가하면 새 변수를 LLM 프롬프트로 흘릴 수 있습니다 (예: `shell_type`, `workspace`). 향후 본격 템플릿 엔진(Jinja2 등)으로 교체해도 `{{var}}` 문법이 동일해 YAML 자산을 그대로 재사용할 수 있습니다.

### 사용자 명령어 호환성 (FSD v1.0.020 회귀 없음)

- `/template <name>` — 다른 템플릿으로 교체 시에도 `{{변수}}` 자동 치환됩니다.
- `/template_list` — 사용 가능한 템플릿 목록 표시 (※ FSD v1.0.161 [ADD] 보강 — 아래 참고).
- `/template_reset` — `.env` 의 `DEFAULT_*_TEMPLATE` 으로 지정된 기본 본문으로 복귀.

### [ADD] `/template_list` 자동 필터링 및 `/template_show` 추가

초기 v1.0.161 구현 이후, 다음 두 개선이 보강되었습니다 (FSD v1.0.161 § 3.7 ~ § 3.8).

#### `/template_list` — `assistant_type` 자동 필터링

YAML 의 `assistant_type` 필드를 기준으로 현재 어시스턴트와 호환되는 템플릿만 노출합니다. `assistant_type` 필드가 없는 공용 템플릿(예: `code-review`)은 모든 타입에서 함께 표시됩니다.

```
> /template_list

📋 사용 가능한 프롬프트 템플릿 (claude):
   - claude-system-prompt [claude]: 전문 개발자 관점의 프로젝트 파일 분석, 코드 생성, 문서 작성
   - code-review [공용]: 시니어 개발자 관점의 코드 리뷰
```

#### `/template_show` — 현재 적용 중인 템플릿 조회

`name`, `description`, `assistant_type` 메타를 즉시 확인할 수 있습니다.

```
> /template_show

📌 현재 적용 중인 템플릿:
   - name           : claude-system-prompt
   - description    : 전문 개발자 관점의 프로젝트 파일 분석, 코드 생성, 문서 작성
   - assistant_type : claude
```

`/template <name>` 으로 변경하거나 `.env` 의 `DEFAULT_*_TEMPLATE` 을 바꾼 직후, 실제 LLM 으로 무엇이 흘러가는지 디버깅·검증할 수 있습니다.

## 변경된 파일

| 파일 | 변경 내용 |
|---|---|
| `src/prompt_renderer.py` (신규) | `PromptRenderer` 클래스 — `{{var}}` 치환 유틸리티 |
| `src/template_manager.py` | `resolve_default_template()` 메서드 추가 (파일명 stem 우선, name 필드 fallback). **[ADD]** `list_templates(assistant_type=...)` 시그니처 변경, `get_template_info(name)` 추가 |
| `src/claude_assistant.py` | 하드코딩 본문 → 빌트인 fallback 상수, `_render_system_prompt`/`_build_template_context` 도입, `chat()` 의 body 구성 직전 재렌더. **[ADD]** `_active_template_name` 추적, `list_templates()` 자동 필터, `get_active_template_info()` 추가 |
| `src/gemini_assistant.py` | 동일 패턴 (`_chat_streaming`/`_chat_non_streaming` 진입부 재렌더). **[ADD]** 동일 보강 |
| `src/genai_assistant.py` | 동일 패턴 (`chat()` body 구성 직전 재렌더). **[ADD]** 동일 보강 |
| **[ADD]** `claude-ai-chat-code.py` / `gemini-ai-chat-code.py` / `gen-ai-chat-code.py` | `/template_show` 핸들러 추가, `/template_list` 출력에 `[assistant_type]` 태그 표시 |
| **[ADD]** `src/command_registry.py` | `/template_show` `CommandInfo` 등록, `/template_list` 설명 갱신 |
| `.env.example` | `DEFAULT_CLAUDE_TEMPLATE`, `DEFAULT_GEMINI_TEMPLATE`, `DEFAULT_GENAI_TEMPLATE` 항목 추가 |
| `tests/test_prompt_renderer.py` (신규) | PromptRenderer 단위 테스트 10건 |
| `tests/test_default_template_loading.py` (신규) | 기본 템플릿 로딩/치환/fallback 테스트 12건 |
| **[ADD]** `tests/test_template_filter_and_show.py` (신규) | assistant_type 필터링 + `get_active_template_info` 테스트 13건 |
| `README.md` | "기본 시스템 프롬프트" 섹션 추가 + **[ADD]** `/template_list`/`/template_show` 보강 가이드 |
| `docs/requirements/FSD_v1.0.020_prompt-templates.md` | v1.0.161 후속 FSD 링크 추가 |
| `docs/requirements/FSD_v1.0.161_default-system-prompt-from-yaml.md` | **[ADD]** § 3.7/§ 3.8/FR-12~17/§ 6.4 보강 섹션 추가 |

## 테스트 결과

- 신규 테스트 35/35 통과 (10 + 12 + 13 = `tests/test_prompt_renderer.py`, `tests/test_default_template_loading.py`, **[ADD]** `tests/test_template_filter_and_show.py`).
- 전체 회귀 테스트 통과 (614 passed, 1 skipped, 51 subtests passed).
- 기존 사전 결함 2건(`tests/test_tokens_command.py` — 한글 정규식 인코딩 불일치)은 본 변경과 무관.

## 마이그레이션 노트

- 기존 `.env` 사용자: 변경 없이 동작합니다 (변수 미설정 → 타입별 기본 파일명 자동 사용).
- 사용자 정의 템플릿을 기본값으로 쓰고 싶다면 `.system_prompts/<my-template>.yaml` 을 추가하고 `.env` 의 `DEFAULT_*_TEMPLATE=<my-template>` 으로 지정하면 됩니다.
- `.system_prompts/*.yaml` 본문 내 `{{os_shell_hint}}` 외에 다른 자리표시자를 쓰려면, 해당 어시스턴트의 `_build_template_context()` 에 키를 추가해야 합니다.
