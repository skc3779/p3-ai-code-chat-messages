# RELEASE v1.0.123 — `/auto_context -qc` 품질 검사 · `/context -nt` 트리 제외

**릴리스 일자**: 2026-04-27  
**FSD 문서**: [FSD_v1.0.123_auto-context-quality-check-and-context-no-tree.md](../requirements/FSD_v1.0.123_auto-context-quality-check-and-context-no-tree.md)

---

## 1. 변경 요약

| 기능 | 명령어 | 설명 |
|---|---|---|
| **A. 2차 품질 검사** | `/auto_context -qc <패턴> [질문]` | 1차 저장 후 동일 모델에 QC 프롬프트를 주입해 2차 호출, `patch:` 응답을 `AgentPatchApplier`로 적용 |
| **B. 트리 제외 옵션** | `/context -nt <패턴> [질문]` | 프로젝트 트리를 컨텍스트에서 제외하여 토큰 절약 |

---

## 2. 신규 파일

| 파일 | 역할 |
|---|---|
| `src/quality_check_prompt.py` | `QUALITY_CHECK_SYSTEM_PROMPT` 상수 정의 |
| `tests/test_command_parser_options.py` | `parse_command_options()` 단위 테스트 (11건) |
| `tests/test_context_processor_quality_check.py` | QC 로직 단위 테스트 (8건) |
| `tests/test_assistants_include_tree.py` | 어시스턴트 `chat()` 시그니처 테스트 (9건) |

## 3. 수정 파일

| 파일 | 변경 내용 |
|---|---|
| `src/cli_input.py` | `parse_command_options()` 헬퍼 함수 추가 |
| `src/context_processor.py` | `quality_check` 필드, `_run_quality_check`, `_apply_qc_patches`, `_temporarily_override_system_prompt`, `_extract_patch_fences`, `_build_qc_prompt`, QC 통계 출력 |
| `src/claude_assistant.py` | `chat()` 에 `include_tree: bool = True` (keyword-only) 추가 |
| `src/gemini_assistant.py` | 동일 |
| `src/genai_assistant.py` | 동일 |
| `claude-ai-chat-code.py` | `/context` 분기에 `-nt` 파싱, `/auto_context` 분기에 `-qc` 파싱 |
| `gemini-ai-chat-code.py` | 동일 |
| `gen-ai-chat-code.py` | 동일 |

## 4. 테스트 결과

| 테스트 모듈 | 결과 | 건수 |
|---|---|---|
| `tests.test_command_parser_options` | ✅ OK | 11 |
| `tests.test_context_processor_quality_check` | ✅ OK | 8 |
| `tests.test_assistants_include_tree` | ✅ OK | 9 |
| `tests.test_context_processor` (회귀) | ✅ OK | 17 |
| `tests.test_context_builder` (회귀) | ✅ OK | 8 |
| **합계** | **✅ 전체 통과** | **53** |

## 5. 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `AUTO_CONTEXT_QC_MAX_RETRIES` | `1` | 2차 패치 실패 시 재시도 횟수 (0 = 재시도 없음) |
| `AUTO_CONTEXT_MAX_RETRIES` | `3` | 1차 저장 실패 시 재시도 횟수 (기존) |

## 6. 하위 호환성

- `include_tree` 기본값이 `True` 이므로 기존 `/context` 호출은 동작이 변경되지 않음
- `quality_check` 기본값이 `False` 이므로 기존 `/auto_context` 호출에 영향 없음
- 3개 어시스턴트의 `chat()` 시그니처에 keyword-only 매개변수만 추가 — 기존 positional 호출에 영향 없음

## 7. 미완료 항목

- [ ] 3 어시스턴트에서 `/auto_context -qc`, `/context -nt` 수동 검증 (M-123-01 ~ M-123-08)
