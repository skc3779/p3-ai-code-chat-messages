# FSD v1.0.123 — `/auto_context` 2차 품질 검사(`-qc`) 도입 + `/context` 트리 제외(`-nt`) 옵션

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.123 |
| 작성일 | 2026-04-27 |
| 구현 예정일 | 2026-04-27 |
| 상태 | 📝 작성 완료 (구현 대기) |
| 선행 문서 | FSD v1.0.049 (`/auto_context` 파일 단위 자동 처리), FSD v1.0.071 (`/read` ContextBuilder 분리), FSD v1.0.072 (ContextBuilder 토큰 한도), FSD v1.0.076 (`/auto_context` 저장 실패 재시도), FSD v1.0.115 (Agents Patch Mode — SEARCH/REPLACE) |
| 대상 파일 | [src/context_processor.py](src/context_processor.py), [src/claude_assistant.py](src/claude_assistant.py), [src/genai_assistant.py](src/genai_assistant.py), [src/gemini_assistant.py](src/gemini_assistant.py), [claude-ai-chat-code.py](claude-ai-chat-code.py), [gemini-ai-chat-code.py](gemini-ai-chat-code.py), [gen-ai-chat-code.py](gen-ai-chat-code.py) |
| 신규 파일 | [src/quality_check_prompt.py](src/quality_check_prompt.py), [tests/test_context_processor_quality_check.py](tests/test_context_processor_quality_check.py), [tests/test_command_parser_options.py](tests/test_command_parser_options.py) |

---

## 0. 두 기능을 하나의 문서로 묶는 이유

본 FSD 는 **두 개의 독립 기능** 을 다룬다.

| 파트 | 명령어 | 옵션 | 본질 |
|---|---|---|---|
| A | `/auto_context` | `-qc` / `--quality-check` | **출력 품질 향상** — 1차 답변에 2차 AI 점검·patch 수정 |
| B | `/context` | `-nt` / `--no-tree` | **입력 토큰 절감** — 컨텍스트에 프로젝트 트리 미포함 |

두 기능 모두 **대화형 CLI 명령어의 옵션 파싱·라우팅 계층** 을 건드리며, 같은 3개 엔트리 포인트(`*-ai-chat-code.py`)와 같은 어시스턴트 클래스(`*_assistant.py`)에 동일 패턴으로 반영된다. **공통 옵션 파싱 헬퍼** 를 한 번에 도입하기 위해 한 문서로 묶는다(§ 5).

---

## 파트 A — `/auto_context` 2차 품질 검사 (Quality Check)

## A.1 개요

### A.1.1 목적

현재 [src/context_processor.py:46-152](src/context_processor.py#L46-L152) `process_files()` 는 매칭된 파일을 1개씩 AI 에 전달해 **1차 답변** 을 받아 디스크에 저장한다. 그러나 1차 답변에는 다음 류의 결함이 자주 섞인다.

| # | 결함 유형 | 빈도 | 영향 |
|---|---|---|---|
| 1 | 문법 오류 (코드: 누락된 import / 닫히지 않은 괄호 / 들여쓰기 깨짐) | 중 | 후속 빌드 실패 |
| 2 | 마크다운 깨짐 (펜스 누락, 헤더 레벨 점프, 표 정렬 오류) | 중 | 가독성 저하 |
| 3 | 사실/일관성 오류 (변수명 변경 누락, 절반만 번역됨) | 낮음 | 사용자 검수 비용 |
| 4 | 형식 위반 (요청한 스타일·언어·구두점 무시) | 낮음 | 재요청 비용 |

본 파트는 `/auto_context` 에 **`-qc` / `--quality-check` 옵션** 을 추가해, 1차 저장 후 같은 모델에게 **저장된 파일 자체를 입력으로** 다시 보내 점검·수정을 요청한다. 단, **재작성 비용을 최소화** 하기 위해 2차 AI 응답은 **부분 patch 형식 (FSD v1.0.115 의 SEARCH/REPLACE)** 으로만 받는다.

### A.1.2 다루는 문제

| ID | 영역 | 현 문제 | 본 FSD 의 대응 |
|---|---|---|---|
| Q-A | 1차 답변 검수 부재 | `process_files()` 는 모델 1차 출력을 **검증 없이** 디스크에 기록 | `-qc` 옵션 사용 시 같은 모델에게 2차 검사 요청 |
| Q-B | 재작성 비용 폭증 | 모델에게 "수정해줘" 라고만 요청하면 파일 전문을 다시 출력 → 토큰 ~6,000+ | 2차 응답을 **`patch:` 펜스만 허용** 하도록 system prompt 강제. 변경 없으면 빈 응답으로 종료 |
| Q-C | 1차 / 2차 system prompt 혼선 | 같은 어시스턴트 인스턴스를 사용하므로 2차 검사용 지침이 1차 답변에까지 누설되면 1차 출력 형식이 무너짐 | 2차 호출에서만 일시적 system prompt override → 호출 후 즉시 원복(§ A.5.2) |
| Q-D | 2차 응답 적용 불안정 | 모델이 잘못된 patch 를 출력해도 디스크에 기록되면 데이터 손상 | `AgentPatchApplier` (FSD v1.0.115) 의 트랜잭셔널 적용·exact/fuzzy 매칭·실패 시 디스크 미변경 정책 그대로 차용 |

### A.1.3 비범위

| 항목 | 비고 |
|---|---|
| 3차·N차 품질 검사 (chained refinement) | Phase 2. 본 FSD 는 1차 + 2차 한 사이클만 |
| 다른 모델로 교차 검사 (Gemini → Claude) | Phase 2. 멀티 프로바이더 라우팅이 별도 작업 |
| 2차 검사 결과의 자동 git 커밋 | 본 FSD 범위 외 — 사용자가 수동으로 검수·커밋 |
| `/context` 명령어에 동일 옵션 적용 | 비대상 — `/context` 는 파일을 저장하지 않음 |
| AST·정적 분석 통합 | 본 FSD 는 **모델 기반 점검** 만. 정적 분석은 별도 FSD |

---

## A.2 현황 분석

### A.2.1 1차 저장 흐름 (FSD v1.0.076 + v1.0.062 적용 후)

[src/context_processor.py:46-152](src/context_processor.py#L46-L152):

```
for file in matched_files:
    1. read_file()
    2. _build_prompt(question, rel_path, content)    # user 메시지에 파일 내용 포함
    3. assistant.chat(prompt, include_context=False) # ← system_prompt 는 어시스턴트 기본값
    4. _auto_save_files(response)                    # ```filename: ...``` 추출 → 저장
```

→ 시스템 프롬프트는 어시스턴트 객체의 `default_system_prompt` 가 그대로 사용된다 ([src/claude_assistant.py:103-104](src/claude_assistant.py#L103-L104), [src/genai_assistant.py:default_system_prompt](src/genai_assistant.py)). 1차 호출 형식 (` ```filename:` 전문 출력) 은 사용자 질문과 어시스턴트 기본 시스템 프롬프트 만으로 유도된다.

### A.2.2 patch 적용기 (재사용 가능 자산)

FSD v1.0.115 에서 도입된 [src/agent_patch_applier.py](src/agent_patch_applier.py) 는 다음을 제공한다.

| API | 시그니처 | 역할 |
|---|---|---|
| `AgentPatchApplier(file_manager).apply(relative_path, payload, *, auto_approve, on_first_approval)` | `PatchResult` | 펜스 본문 → SEARCH/REPLACE 파싱 → exact/fuzzy 매칭 → 트랜잭셔널 적용 |
| `parse_blocks(payload)` | `List[_Block]` | 펜스 본문 파싱 (`<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE`) |

본 FSD 는 **이 API 를 그대로 재사용** 한다 — 신규 patch 적용기를 만들지 않는다. `/agents` 와 `/auto_context -qc` 가 **동일한 patch 의미론** 을 갖도록 보장하는 것이 데이터 일관성·사용자 학습 비용 면에서 유리하다.

### A.2.3 어시스턴트 chat() 시그니처 차이

세 어시스턴트의 `chat()` 시그니처는 **system prompt override 매개변수가 없다**. 일시적 교체는 다음 중 하나로 풀어야 한다.

| 후보 | 장점 | 단점 |
|---|---|---|
| (1) `chat()` 에 `system_prompt_override` kwarg 추가 | 명시적, 호출자 주도 | 3개 어시스턴트 시그니처 변경 — 회귀 위험 |
| (2) `assistant.system_prompt` 를 호출 직전 swap, finally 에서 복원 | 시그니처 변경 없음 | 동시 호출 시 swap 충돌 가능 (스레드 안전성) |
| (3) 사용자 메시지 머리에 "[System override for this call only]\n..." 주입 | 변경 최소 | 모델이 system 으로 인식하지 않을 수 있음 — 비결정적 |

**결정**: (2) 채택. 본 코드베이스는 단일 스레드 REPL 이며, [src/context_processor.py](src/context_processor.py) 가 동기적으로 chat() 을 한 번에 한 호출씩 한다(스레드 충돌 무관). 단, `try / finally` 로 **예외 발생 시에도 원복** 을 보장한다(§ A.5.2). 향후 멀티 스레드화 시 (1) 로 마이그레이션.

---

## A.3 설계 (Design)

### A.3.1 명령어 옵션 — `-qc` / `--quality-check`

`/auto_context` 의 인자 파싱은 현재 **위치 인자만** 받는다 ([gen-ai-chat-code.py:444-470](gen-ai-chat-code.py#L444-L470) 등). 옵션을 도입하려면 파싱 단계를 **옵션 토큰 분리 → 위치 인자** 순으로 재구성해야 한다.

문법:

```
/auto_context [옵션...] <파일패턴> [질문]

옵션:
  -qc, --quality-check    1차 저장 후 같은 모델에 2차 품질 검사를 요청한다.
                          2차 응답은 patch (SEARCH/REPLACE) 만 허용된다.
```

예시:

```
/auto_context -qc src/*.py 이 모듈에 docstring 을 보강해줘
/auto_context --quality-check [src/*.py, tests/*.py] 한국어 주석을 영어로 번역해줘
/auto_context src/*.py 리팩토링해줘                # ← 옵션 없으면 종전 동작
```

옵션 파싱 우선순위 — **위치 인자보다 먼저** 처리하되, **`[패턴1, 패턴2]` 의 대괄호 토큰은 옵션이 아니다**:

```
tokens = args.split()
options = set()
i = 0
while i < len(tokens) and tokens[i].startswith("-") and not tokens[i].startswith("[") and "/" not in tokens[i]:
    if tokens[i] in ("-qc", "--quality-check"):
        options.add("quality_check")
    else:
        print(f"❌ 알 수 없는 옵션: {tokens[i]}"); break
    i += 1
remaining = " ".join(tokens[i:])  # 남은 부분으로 기존 [pattern] 또는 단일 패턴 파싱
```

> 파싱은 `parse_options(args, allowed={"-qc","--quality-check"})` 헬퍼로 분리한다(§ 5.1) — `/context` 의 `-nt` 도 같은 헬퍼를 쓴다.

### A.3.2 2차 품질 검사 흐름

```
사용자: /auto_context -qc src/*.py "docstring 보강"
   │
   ▼
ContextProcessor.process_files(matched_files, question, quality_check=True)
   │
   ├─ for each file:
   │     1차 호출 (기존 동작 — 어시스턴트 기본 system prompt)
   │       └─ saved_files = _auto_save_files(response_1st)
   │
   │     [if quality_check and saved_files]
   │     for saved_path in saved_files:
   │         2차 호출 (system prompt override = QC 프롬프트)
   │           prompt_2nd = _build_qc_prompt(question, saved_path, saved_content_after_1st)
   │           response_2nd = assistant.chat(prompt_2nd, include_context=False)
   │           # 2차 응답은 ```patch:<path>``` 펜스 만 허용
   │           result = _apply_qc_patches(response_2nd, saved_path)
   │           # result 표시: ✅ patched (N blocks) | ⚠️ no changes | ❌ patch failed
   │
   ▼
요약 (1차 처리 수, 1차 저장 수, 2차 검사 수, 2차 patch 적용 수)
```

### A.3.3 2차 검사용 system prompt (`QualityCheckPrompt`)

[src/quality_check_prompt.py](src/quality_check_prompt.py) 에 **상수 문자열로** 정의한다.

```python
"""quality_check_prompt.py — /auto_context -qc 의 2차 품질 검사 system prompt.

본 프롬프트는 2차 호출에서만 적용되며, 1차 반복 질의에는 사용되지 않는다.
"""

QUALITY_CHECK_SYSTEM_PROMPT = """\
당신은 다른 AI 가 방금 작성한 파일에 대한 **2차 품질 검사관(Quality Reviewer)** 입니다.
입력으로 주어진 파일은 이미 디스크에 저장되어 있습니다. 당신의 임무는 이 파일을
검토해 결함을 식별하고, **결함이 있는 부분만** 부분 패치 형식으로 수정안을 제시하는 것입니다.

[검사 항목]
  1. 문법 오류 — 코드(닫히지 않은 괄호/따옴표, 누락된 import, 잘못된 들여쓰기,
     참조 안 되는 변수)·마크다운(펜스 미닫힘, 표 정렬, 헤더 레벨)·문서 (오탈자, 문장 끊김).
  2. 일관성 — 같은 식별자/번역어가 파일 안에서 일관되게 사용되는가.
  3. 형식 — 사용자가 요청한 출력 형식(언어, 스타일, 구조) 을 준수했는가.
  4. 사실 — 명백한 사실 오류·부정확한 코드 동작·누락된 케이스.

[출력 형식 — 반드시 준수]
  • **수정이 필요한 부분만** 다음 펜스로 출력하세요. 파일 전문을 다시 쓰지 마세요.

    ```patch:<원본 파일과 동일한 상대경로>
    <<<<<<< SEARCH
    (원본 파일에 정확히 한 번만 매칭되는 텍스트 블록)
    =======
    (수정된 텍스트 블록)
    >>>>>>> REPLACE
    ```

  • 한 펜스에 같은 파일의 여러 SEARCH/REPLACE 쌍을 넣을 수 있습니다.
  • SEARCH 블록은 원본 파일에 **정확히 한 번** 등장해야 합니다. 모호하면 위/아래 한두
    줄을 더 포함시켜 유일하게 만드세요.
  • 들여쓰기·공백·줄바꿈을 원본 그대로 복사하세요.
  • 블록 삭제는 REPLACE 를 비우면 됩니다.

[출력 금지]
  • ```filename:``` 펜스 (전문 재작성 금지) — 사용 시 자동 무시됩니다.
  • 일반 산문 설명만 있는 응답 — 변경이 필요 없으면 다음 한 줄만 출력하세요:
        품질 양호 — 수정사항 없음

[자주 하는 실수]
  1) SEARCH 컨텍스트가 너무 짧아 여러 곳 매칭 → 적용 불가
  2) "전체적으로 좋아 보입니다" 같은 모호한 응답 — 무엇을 어떻게 바꿀지 patch 로 명시하세요
  3) 새 import 추가 시 import 줄만 SEARCH 로 잡지 말고 위·아래 import 두세 줄을 함께 포함

지금부터 입력으로 주어진 파일을 검토해 위 형식으로 응답하세요.
"""
```

> 이 프롬프트는 **2차 호출 직전에만** `assistant.system_prompt` 로 주입되고, 호출 후 `try / finally` 에서 즉시 원복된다(§ A.5.2). 따라서 같은 세션의 1차 호출·`/context`·`/agents` 등 다른 명령어 동작에는 영향이 없다.

### A.3.4 2차 user 메시지 형식 (`_build_qc_prompt`)

```
[원래 사용자 요청]
{question}

[1차 답변으로 저장된 파일]
경로: {rel_path}
내용:
--- BEGIN ---
{content_after_1st_save}
--- END ---

위 파일을 system prompt 의 검사 항목에 따라 검토하고,
수정이 필요한 부분만 ```patch:{rel_path}``` 펜스로 출력하세요.
수정사항이 없으면 "품질 양호 — 수정사항 없음" 한 줄만 출력하세요.
```

> **원래 사용자 요청** 을 다시 노출하는 이유: 검사관 모델이 "사용자가 무엇을 원했는가" 를 알아야 형식 위반(Q-3) 을 판정할 수 있다.

### A.3.5 2차 응답 적용 (`_apply_qc_patches`)

```python
def _apply_qc_patches(self, response: str, expected_rel_path: str) -> Tuple[str, int, int]:
    """2차 응답에서 patch 펜스를 추출해 적용.

    Returns:
        (status, applied_blocks, total_blocks)
        status ∈ {"applied", "no_changes", "rejected_filename", "patch_failed"}
    """
    # 1) "수정사항 없음" 단축 응답
    if "품질 양호" in response and "```patch:" not in response:
        return ("no_changes", 0, 0)

    # 2) ```filename:``` 펜스 — 정책 위반: QC 는 patch 만 허용
    has_filename = bool(re.search(r"^`{3,}filename:", response, re.MULTILINE))
    has_patch = bool(re.search(r"^`{3,}patch:", response, re.MULTILINE))
    if has_filename and not has_patch:
        return ("rejected_filename", 0, 0)

    # 3) ```patch:<path>``` 펜스 추출 — expected_rel_path 와 다르면 경고하되 적용은 시도
    blocks = self._extract_patch_fences(response)
    if not blocks:
        return ("no_changes", 0, 0)

    from .agent_patch_applier import AgentPatchApplier
    applier = AgentPatchApplier(self.file_manager)

    applied_total = 0
    block_total = 0
    failed = False
    for fence_path, payload in blocks:
        if fence_path != expected_rel_path:
            print(f"⚠️  QC 응답의 patch 경로가 다릅니다: {fence_path} (기대: {expected_rel_path})")
        result = applier.apply(fence_path, payload, auto_approve=True)
        block_total += result.total_count
        if result.success:
            applied_total += result.applied_count
        else:
            failed = True
            print(f"❌ QC patch 실패 ({fence_path}): {result.error or '블록 매칭 실패'}")

    if failed:
        return ("patch_failed", applied_total, block_total)
    return ("applied", applied_total, block_total)
```

> **`auto_approve=True`** 로 적용하는 이유: 같은 명령어 흐름에서 1차 저장은 이미 무프롬프트로 진행됐다. QC 단계만 별도 승인 프롬프트를 띄우면 UX 가 깨진다. 위험은 **트랜잭셔널 적용** + **expected_rel_path 검증** + **1차에서 이미 저장된 파일 한정** 으로 통제한다(§ A.7).

### A.3.6 보고 / 요약

전체 처리 후 출력에 2차 검사 통계를 추가한다.

```
============================================================
✅ 자동 처리 완료: 3개 파일 처리, 3개 파일 저장
🔍 품질 검사:    3건 검사 — 패치 적용 2건, 변경 없음 1건, 실패 0건
============================================================
```

각 파일의 2차 검사 결과는 시점에 인라인으로 표시한다.

```
━━━ [1/3] src/foo.py ━━━
📖 파일 읽는 중...
🤖 AI 처리 중...
✅ 파일 저장됨: src/foo.py
🔍 품질 검사 (2차) 진행 중...
✅ QC 패치 적용: src/foo.py — 2/2 blocks (exact, exact)

━━━ [2/3] src/bar.py ━━━
...
✅ 파일 저장됨: src/bar.py
🔍 품질 검사 (2차) 진행 중...
✓ QC 결과: 변경 없음
```

### A.3.7 옵션 결정 트리 — 사용자가 언제 `-qc` 를 켜야 하는가

| 상황 | 권장 |
|---|---|
| 짧은 마크다운 (≤ 200줄) 일괄 변환 | `-qc` 권장 — 비용 ≤ 2배, 결과 품질 의미 있는 향상 |
| 대규모 코드 리팩토링 (수백 줄) | `-qc` 권장 — patch 가 부분만 수정하므로 토큰 절약 |
| 외부 API 가 매우 느림 / 무거운 모델 | `-qc` 비권장 — 시간이 2배가 되며, 모델이 자기 출력에 보수적 일 수 있어 효과 미미 |
| 단일 파일에 사용자가 직접 검수 가능 | `-qc` 비권장 — 사용자가 더 빠름 |

> 사용자 가이드는 README 갱신 범위 — 본 FSD 는 옵션 동작을 정의함.

### A.3.8 ★ 추가 제안 (사용자 요청 — "더 좋은 방안")

본 FSD 가 사용자가 명시한 요건을 그대로 충족하면서 함께 도입하면 효과가 큰 보강안:

| ID | 보강안 | 이유 | 본 FSD 채택 |
|---|---|---|---|
| ENH-1 | **2차 응답을 `patch:` 펜스로 강제** (system prompt 에 명시 + 응답 검증 단계에서 `filename:` 거부) | 사용자 요건의 정확한 의도("기존 파일을 일부만 수정") 를 응답 형식 차원에서 강제 | ✅ § A.3.3 / § A.3.5 |
| ENH-2 | **2차 검사 결과를 1차 답변과 함께 디스크에 commit 하지 말고 트랜잭셔널 적용** | 잘못된 patch 가 1차 저장본을 망칠 위험 차단 | ✅ § A.3.5 (FSD v1.0.115 의 트랜잭셔널 정책 재사용) |
| ENH-3 | **"품질 양호 — 수정사항 없음" 단축 응답 규약** | 변경이 없는데 patch 펜스를 억지로 만들면 거짓 양성 발생 → 명시적 단축 응답으로 정직한 종료 경로 제공 | ✅ § A.3.5 |
| ENH-4 | **2차 검사 토큰 사용량을 통계로 기록 (`qc_total_input_tokens`, `qc_total_output_tokens`)** | `-qc` 비용 가시성 — 사용자가 옵션을 켤지 결정하는 근거 | ✅ § A.6 (선택, 가능 시) |
| ENH-5 | **`AUTO_CONTEXT_QC_MAX_RETRIES` 환경변수 (기본 1)** — 2차 응답이 `patch_failed` 상태일 때 1회 재요청 | 첫 patch 가 ambiguous 로 실패해도 모델에 **"SEARCH 에 컨텍스트를 더 붙여 다시 출력하라"** 안내 후 재시도하면 회복률이 의미 있게 오른다 | ✅ § A.6 (선택) — 기본 1 회 (총 2 시도) |
| ENH-6 | **`-qc` 와 `--qc=loose` 두 단계** (loose 는 patch 실패 시 1차 결과 유지하고 경고만, strict 는 patch 실패 시 1차 저장본을 삭제·실패 목록에 추가) | 유스케이스에 따라 정책 분리 | ❌ 본 FSD 는 단일 모드(=loose). 향후 필요 시 추가 |
| ENH-7 | **2차 검사 시점에 .qc.bak 백업 파일 자동 생성** (`src/foo.py.qc.bak`) | 잘못된 patch 적용 시 사용자가 즉시 복구 | ❌ 본 FSD 는 git workflow 가정 (사용자가 1차 저장 후 커밋해두면 충분) — Phase 2 |
| ENH-8 | **2차 system prompt 의 외부 파일 분리** ([src/quality_check_prompt.py](src/quality_check_prompt.py) 단일 모듈) — 향후 사용자 정의 prompt 가능 | 프롬프트 튜닝 비용 분리 | ✅ § A.3.3 |
| ENH-9 | **3개 어시스턴트 별 prompt 호환성** — Claude/Gemini/GenAI 모두 SEARCH/REPLACE 마커 형식 출력 가능. 마커는 git conflict 마커라 모든 모델 학습 분포에 존재 | 프로바이더 무관 동작 보장 | ✅ § A.5.2 (구현 시 3 어시스턴트 통합 테스트) |

채택된 항목(ENH-1, 2, 3, 4, 5, 8, 9) 은 본 FSD 의 요구사항·테스트로 반영했고, 미채택 항목(ENH-6, 7) 은 § 8 후속 작업에 정리한다.

---

## A.4 ContextProcessor 변경 사양

### A.4.1 `__init__` — 필드 추가

```python
def __init__(
    self,
    assistant,
    file_manager,
    streaming: bool = True,
    *,
    quality_check: bool = False,           # ★ NEW
):
    self.assistant = assistant
    self.file_manager = file_manager
    self.streaming = streaming
    self.quality_check = quality_check     # ★ NEW

    self.max_retries = max(1, int(os.getenv("AUTO_CONTEXT_MAX_RETRIES", "3")))
    # ENH-5: 2차 패치 실패 시 재시도 횟수 (기본 1 — 즉, 최대 2회 시도)
    self.qc_max_retries = max(1, int(os.getenv("AUTO_CONTEXT_QC_MAX_RETRIES", "1")))

    # ENH-4: 2차 검사 토큰 사용량 (가능 시 어시스턴트에서 수집)
    self._qc_stats = {"checked": 0, "applied": 0, "no_changes": 0, "failed": 0}
```

### A.4.2 `process_files()` — 2차 검사 호출 추가

기존 1차 저장 성공 분기 이후에 다음을 삽입한다.

```python
if saved:
    saved_count += len(saved)

    # ★ NEW: 2차 품질 검사
    if self.quality_check:
        for saved_rel_path in saved:
            self._run_quality_check(question, saved_rel_path)

    break  # 1차 시도 성공 → 다음 파일로
```

> 1차가 부분 성공(saved 비어있지 않음) 이면 saved 안의 모든 파일에 대해 QC 를 시도한다. 1차가 3회 모두 실패 한 경우 QC 는 건너뛴다(저장된 파일이 없으므로).

### A.4.3 `_run_quality_check()` — 신규 메서드

```python
def _run_quality_check(self, original_question: str, saved_rel_path: str) -> None:
    """2차 품질 검사 — saved_rel_path 에 대해 QC 호출 후 patch 적용."""
    abs_path = self.file_manager.workspace_dir / saved_rel_path
    if not abs_path.exists():
        # 동시에 다른 도구가 지웠을 가능성 — skip
        print(f"⚠️  QC 건너뜀 (파일 없음): {saved_rel_path}")
        self._qc_stats["failed"] += 1
        return

    saved_content = self.file_manager.read_file(abs_path)
    if saved_content is None:
        print(f"⚠️  QC 건너뜀 (읽기 실패): {saved_rel_path}")
        self._qc_stats["failed"] += 1
        return

    qc_prompt = self._build_qc_prompt(original_question, saved_rel_path, saved_content)
    print("🔍 품질 검사 (2차) 진행 중...")

    # ENH-5: patch_failed 시 1회 재시도 (총 qc_max_retries+1 회)
    last_status = None
    for attempt in range(1, self.qc_max_retries + 2):
        with self._temporarily_override_system_prompt(QUALITY_CHECK_SYSTEM_PROMPT):
            response = self.assistant.chat(
                qc_prompt,
                streaming=self.streaming,
                include_context=False,
            )

        if not response:
            last_status = "no_changes"
            break

        status, applied, total = self._apply_qc_patches(
            self.normalize_backtick_blocks(response),
            saved_rel_path,
        )
        last_status = status

        if status == "applied":
            print(f"✅ QC 패치 적용: {saved_rel_path} — {applied}/{total} blocks")
            break
        if status == "no_changes":
            print("✓ QC 결과: 변경 없음")
            break
        if status == "rejected_filename":
            print(f"⚠️  QC 응답에 ```filename:``` 펜스 — 거부 (patch 만 허용)")
            break  # filename 응답은 재시도해도 같은 결과일 가능성 큼
        if status == "patch_failed":
            if attempt <= self.qc_max_retries:
                print(f"🔄 QC 재시도 [{attempt+1}/{self.qc_max_retries+1}] — patch 실패")
                # ENH-5: 재시도 시 user 메시지에 직전 실패 안내 추가
                qc_prompt = qc_prompt + (
                    "\n\n[직전 시도]\n"
                    "patch 적용에 실패했습니다. SEARCH 블록에 위·아래 컨텍스트를 더 포함시켜\n"
                    "원본 파일에 정확히 한 번만 매칭되도록 다시 출력하세요."
                )
                continue
            else:
                print(f"❌ QC patch 적용 실패 (재시도 모두 소진): {saved_rel_path}")
                break

    # 통계 누적
    self._qc_stats["checked"] += 1
    if last_status == "applied":
        self._qc_stats["applied"] += 1
    elif last_status == "no_changes":
        self._qc_stats["no_changes"] += 1
    else:
        self._qc_stats["failed"] += 1
```

### A.4.4 `_temporarily_override_system_prompt()` — 컨텍스트 매니저

```python
from contextlib import contextmanager

@contextmanager
def _temporarily_override_system_prompt(self, override: str):
    """assistant.system_prompt 를 일시적으로 override 후 finally 에서 원복."""
    if not hasattr(self.assistant, "system_prompt"):
        # 호환성 — 어시스턴트가 system_prompt 속성을 안 가진 경우
        yield
        return
    original = self.assistant.system_prompt
    try:
        self.assistant.system_prompt = override
        yield
    finally:
        self.assistant.system_prompt = original
```

> **NFR-A-NFR-04 준수** — 예외 발생 시에도 반드시 원복.

### A.4.5 `_extract_patch_fences()` — `patch:<path>` 펜스 파서

```python
def _extract_patch_fences(self, response: str) -> List[Tuple[str, str]]:
    """
    응답에서 ```patch:<path> ... ``` 펜스를 추출.

    Returns:
        [(rel_path, body), ...]
    """
    pairs: List[Tuple[str, str]] = []
    lines = response.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(`{3,})patch:(.+)$", lines[i].strip())
        if not m:
            i += 1; continue
        fence = m.group(1)
        path = m.group(2).strip()
        body: List[str] = []
        i += 1
        while i < len(lines) and lines[i].strip() != fence:
            body.append(lines[i])
            i += 1
        pairs.append((path, "\n".join(body)))
        i += 1  # 닫는 fence 건너뜀
    return pairs
```

### A.4.6 `_print_summary()` — 2차 통계 출력

기존 요약 끝에 추가:

```python
if self.quality_check:
    s = self._qc_stats
    print(
        f"🔍 품질 검사:    {s['checked']}건 검사 — "
        f"패치 적용 {s['applied']}건, 변경 없음 {s['no_changes']}건, "
        f"실패 {s['failed']}건"
    )
```

---

## 파트 B — `/context` `--no-tree` 옵션

## B.1 개요

### B.1.1 목적

[src/claude_assistant.py:128-132](src/claude_assistant.py#L128-L132), [src/genai_assistant.py:222-227](src/genai_assistant.py#L222-L227), [src/gemini_assistant.py:131-136](src/gemini_assistant.py#L131-L136) 의 `chat()` 은 `include_context=True` 일 때 항상 `build_context(include_tree=True, ...)` 를 호출한다. 프로젝트 루트에 파일이 많으면(예: 100+ 파일) **트리만으로 1,000-3,000 토큰** 이 차지되어 본문 컨텍스트가 잘릴 수 있다.

본 파트는 `/context` 명령어에 **`-nt` / `--no-tree` 옵션** 을 추가해, 사용자가 트리 없이 파일 본문만 컨텍스트로 보내고 싶을 때 선택할 수 있게 한다.

### B.1.2 다루는 문제

| ID | 영역 | 현 문제 | 본 FSD 의 대응 |
|---|---|---|---|
| C-A | 트리 강제 포함 | `chat(include_context=True)` 가 항상 `include_tree=True` 호출 → 사용자 선택권 부재 | `-nt` 옵션 시 `include_tree=False` 로 호출 |
| C-B | 3 어시스턴트 시그니처 비대칭 | 셋 다 `chat()` 에 `include_tree` 매개변수 부재 → 매번 본 FSD 같은 작업이 반복됨 | `chat()` 에 `include_tree: bool = True` kwarg 추가 (기본값 True 유지 — 회귀 없음) |
| C-C | 옵션 파서 부재 | `/context` 도 위치 인자만 파싱. `-qc` 와 같은 옵션 헬퍼가 필요 | § 5.1 의 공통 헬퍼 사용 |

### B.1.3 비범위

| 항목 | 비고 |
|---|---|
| `-nt` 의 기본화 (기본값 변경) | ❌ 본 FSD 는 **기본 동작 변경 없음** (기존 사용자 회귀 0). 옵션 명시 시에만 트리 제외 |
| `/auto_context` 에 `-nt` 적용 | 비대상 — `/auto_context` 는 `include_context=False` 로 호출 (트리 자체가 미포함 흐름) |
| `/read` 에 옵션 적용 | 비대상 — `/read` 는 이미 `include_tree=False` 가 기본 |
| 토큰 예측 표시 | 본 FSD 는 옵션 동작만. 토큰 예측은 별도 FSD |

---

## B.2 현황 분석

### B.2.1 현재 `/context` 흐름

세 엔트리 포인트 모두 동일:

```python
# claude-ai-chat-code.py:425-430, gemini-ai-chat-code.py 유사, gen-ai-chat-code.py 유사
last_response = assistant.chat(
    question,
    streaming=streaming_mode,
    include_context=True,
    file_patterns=file_patterns,
)
```

`include_tree` 를 직접 지정하는 경로는 없다 — 어시스턴트의 `chat()` 안에서 하드코딩된 `include_tree=True` 가 항상 적용된다.

### B.2.2 어시스턴트별 분기

| 어시스턴트 | 위치 | 변경 |
|---|---|---|
| [src/claude_assistant.py:128-132](src/claude_assistant.py#L128-L132) | `chat()` | `include_tree` kwarg 추가, `build_context(include_tree=include_tree, ...)` |
| [src/genai_assistant.py:222-227](src/genai_assistant.py#L222-L227) | `chat()` | 동일 |
| [src/gemini_assistant.py:131-136](src/gemini_assistant.py#L131-L136) | `chat()` | 동일 |

→ 셋의 `chat()` 시그니처는 `include_tree: bool = True` 매개변수를 갖는다. **기본값이 True 이므로 회귀 없음**.

> [src/agent_runner.py:188-193](src/agent_runner.py#L188-L193) 의 `build_context(include_tree=True, ...)` 직접 호출 (assistant.chat 우회) 은 본 FSD 와 무관 — agent 흐름은 자체 컨텍스트 정책을 유지.

---

## B.3 설계

### B.3.1 명령어 옵션

```
/context [옵션...] <파일패턴> [질문]

옵션:
  -nt, --no-tree    프로젝트 트리를 컨텍스트에 포함하지 않는다
                    (파일 본문만 보냄)
```

예시:

```
/context -nt src/*.py 이 모듈에 docstring 보강해줘
/context --no-tree [src/*.py, docs/*.md] README.md 작성해줘
/context src/*.py 리팩토링해줘                # ← 옵션 없으면 종전 동작 (트리 포함)
```

### B.3.2 어시스턴트 `chat()` 시그니처 확장

세 어시스턴트 모두 동일 패턴으로:

```python
def chat(
    self,
    user_message: str,
    streaming: bool = True,
    include_context: bool = False,
    file_patterns: Optional[List[str]] = None,
    *,
    include_tree: bool = True,        # ★ NEW (기본 True — 회귀 없음)
    # claude_assistant 만: disable_tools: bool = False (기존)
) -> str:
    if include_context:
        context = self.context_builder.build_context(
            include_tree=include_tree,        # ← 하드코딩 → 매개변수
            file_patterns=file_patterns,
        )
        ...
```

> Claude 어시스턴트는 기존 `disable_tools: bool = False` 매개변수가 있다 — `include_tree` 도 동일하게 keyword-only 로 추가.

### B.3.3 엔트리 포인트 변경

세 엔트리 포인트의 `/context` 분기에서:

```python
# 현재 (예: claude-ai-chat-code.py:425-430)
last_response = assistant.chat(
    question,
    streaming=streaming_mode,
    include_context=True,
    file_patterns=file_patterns,
)

# 변경 후
last_response = assistant.chat(
    question,
    streaming=streaming_mode,
    include_context=True,
    file_patterns=file_patterns,
    include_tree=not no_tree,           # ★ NEW (옵션 파서가 set 한 bool)
)
```

---

## 5. 공통 — 옵션 파싱 헬퍼

`-qc` 와 `-nt` 모두 같은 패턴(short/long 플래그, 위치 인자 앞단) 이므로 단일 헬퍼로 처리한다.

### 5.1 `parse_options(args, allowed)` — 신규 함수

[src/cli_input.py](src/cli_input.py) 에 추가 (또는 신규 모듈 [src/command_options.py](src/command_options.py) 분리 — 본 FSD 는 `cli_input.py` 추가 채택).

```python
from typing import Dict, Set, Tuple


def parse_command_options(
    args: str,
    aliases: Dict[str, str],   # short/long → canonical name
) -> Tuple[Set[str], str]:
    """
    명령어 인자에서 선두의 옵션 토큰을 분리해 (옵션집합, 나머지) 반환.

    Args:
        args: 명령어 뒤의 전체 문자열 (예: "-qc src/*.py 질문")
        aliases: { "-qc": "quality_check", "--quality-check": "quality_check",
                   "-nt": "no_tree",       "--no-tree":       "no_tree" }

    Returns:
        (set of canonical names, remaining args str)

    Notes:
        - 위치 인자 시작 = 첫 번째 토큰이 옵션이 아닌 시점
        - "[" 로 시작하는 토큰은 패턴 리스트로 간주, 옵션 파싱 종료
        - 알 수 없는 -옵션 은 ValueError
    """
    tokens = args.split()
    options: Set[str] = set()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith("-") or tok.startswith("[") or tok in ("--",):
            break
        if tok not in aliases:
            raise ValueError(f"알 수 없는 옵션: {tok}")
        options.add(aliases[tok])
        i += 1

    # 토큰 재결합 — 단, 원본 args 의 공백을 그대로 보존하기 위해
    # 옵션 토큰까지의 길이만 잘라낸다
    if i == 0:
        return options, args
    consumed_len = sum(len(t) for t in tokens[:i]) + i  # i개의 공백 포함
    return options, args[consumed_len:].lstrip()
```

### 5.2 사용 예 — `/auto_context` / `/context` 분기

```python
# 공통 alias
QC_ALIASES = {"-qc": "quality_check", "--quality-check": "quality_check"}
NT_ALIASES = {"-nt": "no_tree", "--no-tree": "no_tree"}

elif command == '/auto_context':
    if not args:
        print("❌ 형식: /auto_context [-qc] <파일패턴> [질문]")
        ...
        continue
    try:
        options, remaining = parse_command_options(args, QC_ALIASES)
    except ValueError as e:
        print(f"❌ {e}")
        continue
    quality_check = "quality_check" in options
    args = remaining
    # 이후 기존 [패턴] 또는 위치 인자 파싱은 그대로
    ...
    processor = ContextProcessor(
        assistant=assistant,
        file_manager=assistant.file_manager,
        streaming=streaming_mode,
        quality_check=quality_check,           # ★ NEW
    )

elif command == '/context':
    if not args:
        print("❌ 형식: /context [-nt] <파일패턴> [질문]")
        ...
        continue
    try:
        options, remaining = parse_command_options(args, NT_ALIASES)
    except ValueError as e:
        print(f"❌ {e}")
        continue
    no_tree = "no_tree" in options
    args = remaining
    ...
    last_response = assistant.chat(
        question,
        streaming=streaming_mode,
        include_context=True,
        file_patterns=file_patterns,
        include_tree=not no_tree,              # ★ NEW
    )
```

---

## 6. 요구사항

### 6.1 파트 A — `/auto_context -qc` (FR-A)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-A-01 | `/auto_context` 가 `-qc` / `--quality-check` 옵션을 인식한다 | 필수 |
| FR-A-02 | 옵션 부재 시 동작은 v1.0.115 이전과 동일 (1차 저장만, QC 미실행) | 필수 |
| FR-A-03 | `-qc` 활성 시 1차 저장 성공한 각 파일에 대해 2차 AI 호출을 1회 실행한다 | 필수 |
| FR-A-04 | 2차 호출 시 `assistant.system_prompt` 를 `QUALITY_CHECK_SYSTEM_PROMPT` 로 일시 교체하고, 호출 종료 후 (예외 포함) 즉시 원복한다 | 필수 |
| FR-A-05 | 2차 system prompt 는 본 FSD 의 § A.3.3 본문과 일치한다 | 필수 |
| FR-A-06 | 2차 응답에서 ` ```patch:<path>``` ` 펜스를 추출해 `AgentPatchApplier.apply()` 로 적용한다 | 필수 |
| FR-A-07 | 2차 응답에 ` ```filename:``` ` 펜스가 있고 `patch:` 펜스가 없으면 적용을 거부하고 `rejected_filename` 으로 보고한다 | 필수 |
| FR-A-08 | 2차 응답이 빈 문자열이거나 `"품질 양호"` 단축 응답이면 `no_changes` 로 보고하고 적용 건너뜀 | 필수 |
| FR-A-09 | patch 적용은 `auto_approve=True` 로 수행 — 별도 사용자 프롬프트를 띄우지 않는다 | 필수 |
| FR-A-10 | patch 적용이 실패하면 `AUTO_CONTEXT_QC_MAX_RETRIES` 만큼 재시도한다 (기본 1 = 총 2 시도) | 필수 |
| FR-A-11 | patch 재시도 시 user 메시지에 직전 실패 안내(SEARCH 컨텍스트 보강 권고) 를 추가한다 | 필수 |
| FR-A-12 | 처리 종료 후 요약에 QC 통계(검사 수, 적용 수, 변경 없음 수, 실패 수) 를 출력한다 | 필수 |
| FR-A-13 | QC system prompt 는 [src/quality_check_prompt.py](src/quality_check_prompt.py) 단일 모듈에서 import 된다 — 다른 위치에 중복 정의 금지 | 필수 |
| FR-A-14 | 2차 검사 흐름은 1차 저장 결과(`saved` 리스트) 가 비어있으면 건너뛴다 | 필수 |
| FR-A-15 | QC 응답의 patch 펜스 경로가 `expected_rel_path` 와 다른 경우 경고를 출력하되 적용은 시도한다 (모델이 절대경로/상대경로 차이로 약간 다르게 출력하는 케이스 허용) | 권장 |
| FR-A-16 | 환경변수 `AUTO_CONTEXT_QC_MAX_RETRIES` 미설정 시 기본 1 회 (총 2 시도) | 필수 |

### 6.2 파트 B — `/context -nt` (FR-B)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-B-01 | `/context` 가 `-nt` / `--no-tree` 옵션을 인식한다 | 필수 |
| FR-B-02 | 옵션 부재 시 동작은 종전과 동일 (`include_tree=True`) | 필수 |
| FR-B-03 | `-nt` 활성 시 `assistant.chat(include_tree=False, ...)` 를 호출한다 | 필수 |
| FR-B-04 | 3 어시스턴트(`claude_assistant`, `genai_assistant`, `gemini_assistant`) 의 `chat()` 모두 `include_tree: bool = True` keyword-only 매개변수를 가진다 | 필수 |
| FR-B-05 | `chat()` 의 다른 호출자(`/auto_context`, `/agents`, `/read`) 는 `include_tree` 를 명시적으로 전달하지 않으며, 기본값 동작이 종전과 동일하다 | 필수 |
| FR-B-06 | `/read` 명령은 본 FSD 변경의 영향을 받지 않는다 (기존 `build_context(include_tree=False)` 직접 호출 유지) | 필수 |

### 6.3 공통 — 옵션 파서 (FR-C)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-C-01 | `parse_command_options(args, aliases)` 헬퍼는 선두 옵션 토큰을 분리해 `(set, remaining_args)` 를 반환한다 | 필수 |
| FR-C-02 | 알 수 없는 `-옵션` 은 `ValueError` 로 신호하며 호출자가 메시지를 출력한다 | 필수 |
| FR-C-03 | `[패턴]` 으로 시작하는 토큰은 옵션이 아니며 옵션 파싱이 그 시점에 종료된다 | 필수 |
| FR-C-04 | `--` 토큰은 옵션 종료 명시 — 이후 토큰은 위치 인자로 처리 | 권장 |
| FR-C-05 | 옵션 토큰이 0 개이면 입력 args 를 그대로 반환한다 | 필수 |
| FR-C-06 | 동일 옵션이 중복으로 등장해도 한 번 set 에 들어간다 (멱등) | 필수 |

### 6.4 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-01 | `parse_command_options` 는 정규식 미사용 — 토큰 단위 처리 |
| NFR-02 | `_temporarily_override_system_prompt` 는 컨텍스트 매니저로 구현, 예외 발생 시에도 원복 보장 |
| NFR-03 | 2차 호출은 1차 호출과 동일한 어시스턴트 인스턴스를 사용 — 새 인스턴스 생성 금지 (히스토리 일관성) |
| NFR-04 | 2차 호출의 conversation_history 누적은 1차와 분리되지 않는다 — 같은 세션의 자연스러운 흐름으로 history 에 들어간다(현 어시스턴트 동작 그대로) |
| NFR-05 | `chat()` 의 `include_tree` 매개변수 추가는 keyword-only — 기존 위치인자 호출자 회귀 0 |
| NFR-06 | QC system prompt 길이 ≤ 2,500 자 (약 1,500 토큰) — 2차 호출 비용 통제 |
| NFR-07 | `AgentPatchApplier` API 외에 새 patch 구현체를 만들지 않는다 (코드 중복 방지) |
| NFR-08 | QC 통계는 dict 단일 필드 (`self._qc_stats`) — pickle / 직렬화 가능 |
| NFR-09 | `-qc` 와 `-nt` 옵션 처리 코드는 3개 엔트리 포인트에서 동일 — 향후 한 곳만 수정해도 다른 곳에 자동 반영되도록 헬퍼로 분리 |
| NFR-10 | `-qc` 흐름은 1차 저장이 모두 실패한 파일에 대해서는 어떤 호출도 추가하지 않는다 (불필요 토큰 방지) |

---

## 7. 테스트 시나리오

### 7.1 옵션 파서 (`tests/test_command_parser_options.py`)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-123-01 | `parse_command_options("-qc src/*.py 질문", {"-qc":"quality_check"})` | `({"quality_check"}, "src/*.py 질문")` |
| T-123-02 | `parse_command_options("--quality-check [a, b] 질문", QC_ALIASES)` | `({"quality_check"}, "[a, b] 질문")` |
| T-123-03 | `parse_command_options("src/*.py", QC_ALIASES)` | `(set(), "src/*.py")` |
| T-123-04 | `parse_command_options("-qc -qc src/*.py", QC_ALIASES)` | `({"quality_check"}, "src/*.py")` (멱등) |
| T-123-05 | `parse_command_options("-xx src/*.py", QC_ALIASES)` | `ValueError("알 수 없는 옵션: -xx")` |
| T-123-06 | `parse_command_options("-nt src/*.py", NT_ALIASES)` | `({"no_tree"}, "src/*.py")` |
| T-123-07 | `parse_command_options("--no-tree -- -hello", NT_ALIASES)` | `({"no_tree"}, "-hello")` (`--` 종료) |
| T-123-08 | `parse_command_options("[src/*.py] -qc 질문", QC_ALIASES)` | `(set(), "[src/*.py] -qc 질문")` (`[` 만나면 종료) |

### 7.2 ContextProcessor 2차 검사 (`tests/test_context_processor_quality_check.py`)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-123-10 | `quality_check=False` (기본) — 1차 저장만, 2차 호출 0 회 | `assistant.chat` 호출 1회/파일 |
| T-123-11 | `quality_check=True`, 1차 저장 성공, 2차 응답 = "품질 양호 — 수정사항 없음" | `_qc_stats["no_changes"]==1`, 파일 변경 없음 |
| T-123-12 | `quality_check=True`, 2차 응답에 `patch:` 펜스 (1 블록 exact) | `_qc_stats["applied"]==1`, 파일에 패치 반영 |
| T-123-13 | `quality_check=True`, 2차 응답에 `filename:` 펜스만 | `_qc_stats["failed"]==1`, 파일 변경 없음 (rejected_filename) |
| T-123-14 | `quality_check=True`, 2차 응답 patch 가 `no_match` 실패 → 재시도 후 성공 | `_qc_stats["applied"]==1`, chat 호출 2회 |
| T-123-15 | `quality_check=True`, 2차 응답 patch 가 모두 실패 → 재시도 모두 소진 | `_qc_stats["failed"]==1`, 파일 변경 없음 |
| T-123-16 | `quality_check=True`, 1차 저장 0 건 (3회 모두 실패) → 2차 호출 안 함 | `_qc_stats["checked"]==0` (NFR-10) |
| T-123-17 | 2차 호출 도중 예외 발생 → `assistant.system_prompt` 가 원복됨 | 원래 system_prompt 와 동일 (NFR-02) |
| T-123-18 | 2차 호출 후 1차 호출(다음 파일)의 system_prompt 는 어시스턴트 기본값 | 회귀 없음 |
| T-123-19 | 2차 응답 patch 의 path 가 `expected_rel_path` 와 다름 (`src/foo.py` vs `./src/foo.py`) | 경고 출력 후 적용 시도 (FR-A-15) |
| T-123-20 | 환경변수 `AUTO_CONTEXT_QC_MAX_RETRIES=0` | 재시도 0 회 (총 1 시도), patch 실패 시 즉시 종료 |
| T-123-21 | QC system prompt 가 [src/quality_check_prompt.py](src/quality_check_prompt.py) 의 상수와 일치 | `from src.quality_check_prompt import QUALITY_CHECK_SYSTEM_PROMPT` 동일 객체 |
| T-123-22 | 2차 호출 user 메시지에 원래 사용자 질문이 포함됨 | substring 검증 |
| T-123-23 | 2차 호출의 streaming 모드는 1차와 동일 | `assistant.chat` mock 의 `streaming=` kwarg 일치 |
| T-123-24 | 1차 저장 파일이 디스크에서 사라진 경우 (외부 도구가 삭제) | QC 건너뜀 + warning 출력 |

### 7.3 어시스턴트 `include_tree` 매개변수 (`tests/test_assistants_include_tree.py`)

| # | 어시스턴트 | 시나리오 | 기대 결과 |
|---|---|---|---|
| T-123-30 | claude | `chat(include_context=True, include_tree=False)` | `build_context(include_tree=False, ...)` 호출됨 |
| T-123-31 | claude | `chat(include_context=True)` (기본) | `build_context(include_tree=True, ...)` (회귀) |
| T-123-32 | gemini | T-123-30 동일 | 동일 |
| T-123-33 | gemini | T-123-31 동일 | 동일 |
| T-123-34 | genai | T-123-30 동일 | 동일 |
| T-123-35 | genai | T-123-31 동일 | 동일 |
| T-123-36 | claude | `chat(include_context=False, include_tree=False)` | `build_context` 미호출 (`include_context` 가 False 면 무관) |

### 7.4 엔트리 포인트 통합 (수동 검증)

| # | 명령 | 기대 결과 |
|---|---|---|
| M-123-01 | `/context src/*.py 질문` | 트리 포함 컨텍스트 (회귀) |
| M-123-02 | `/context -nt src/*.py 질문` | 트리 미포함 |
| M-123-03 | `/context --no-tree [src/*.py, docs/*.md] 질문` | 트리 미포함, 두 패턴 매칭 |
| M-123-04 | `/auto_context src/*.py 질문` | 1차 저장만 (회귀) |
| M-123-05 | `/auto_context -qc src/*.py 질문` | 1차 저장 + 2차 검사 |
| M-123-06 | `/auto_context -qc [src/*.py] 한국어 주석을 영어로` | 매칭된 모든 파일에 1차 + 2차 적용 |
| M-123-07 | `/auto_context -qc src/*.py` (질문 없음 → 멀티라인 입력) | 멀티라인 질문 받은 후 1차 + 2차 |
| M-123-08 | `/auto_context -unknown src/*.py` | "❌ 알 수 없는 옵션: -unknown" 출력, 처리 중단 |

---

## 8. 파일 변경 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [src/quality_check_prompt.py](src/quality_check_prompt.py) | **신규** | `QUALITY_CHECK_SYSTEM_PROMPT` 상수 (§ A.3.3) |
| [src/cli_input.py](src/cli_input.py) | 수정 | `parse_command_options()` 헬퍼 추가 (§ 5.1) |
| [src/context_processor.py](src/context_processor.py) | 수정 | `__init__` 에 `quality_check`, `qc_max_retries`, `_qc_stats` 추가. `process_files()` 에 2차 검사 진입. `_run_quality_check()`, `_temporarily_override_system_prompt()`, `_extract_patch_fences()`, `_apply_qc_patches()`, `_print_summary()` 신규 |
| [src/claude_assistant.py](src/claude_assistant.py) | 수정 | `chat()` 에 `include_tree: bool = True` keyword-only 추가, 하드코딩된 `include_tree=True` 를 매개변수로 |
| [src/genai_assistant.py](src/genai_assistant.py) | 수정 | 동일 |
| [src/gemini_assistant.py](src/gemini_assistant.py) | 수정 | 동일 |
| [claude-ai-chat-code.py](claude-ai-chat-code.py) | 수정 | `/context` 분기에 옵션 파서 + `include_tree=not no_tree`. `/auto_context` 분기에 옵션 파서 + `quality_check=quality_check` 전달 |
| [gemini-ai-chat-code.py](gemini-ai-chat-code.py) | 수정 | 동일 |
| [gen-ai-chat-code.py](gen-ai-chat-code.py) | 수정 | 동일 |
| [tests/test_command_parser_options.py](tests/test_command_parser_options.py) | **신규** | T-123-01 ~ T-123-08 |
| [tests/test_context_processor_quality_check.py](tests/test_context_processor_quality_check.py) | **신규** | T-123-10 ~ T-123-24 (mock 기반) |
| [tests/test_assistants_include_tree.py](tests/test_assistants_include_tree.py) | **신규** | T-123-30 ~ T-123-36 |
| [tests/test_context_processor.py](tests/test_context_processor.py) | 수정(최소) | 기존 케이스에 `quality_check=False` 명시 (회귀 방지) |
| [docs/requirements/FSD_v1.0.123_auto-context-quality-check-and-context-no-tree.md](docs/requirements/FSD_v1.0.123_auto-context-quality-check-and-context-no-tree.md) | 신규 | 본 문서 |

---

## 9. 실행 흐름 다이어그램

### 9.1 `/auto_context -qc` 정상 시퀀스

```
사용자: /auto_context -qc src/foo.py "docstring 보강"
  │
  ▼
parse_command_options → options={"quality_check"}, remaining="src/foo.py docstring 보강"
  │
  ▼
ContextProcessor(quality_check=True).process_files([foo.py], "docstring 보강")
  │
  ├─ [1/1] src/foo.py
  │     ├─ read_file()
  │     ├─ chat(prompt_1st)            # system = 어시스턴트 기본
  │     │     └─ response_1st (```filename:src/foo.py``` ...)
  │     ├─ _auto_save_files() → saved=["src/foo.py"]
  │     │
  │     └─ _run_quality_check(question, "src/foo.py")
  │           │
  │           ├─ read_file(saved_path)  → content_after_1st
  │           ├─ qc_prompt = _build_qc_prompt(...)
  │           │
  │           ├─ with _temporarily_override_system_prompt(QUALITY_CHECK_SYSTEM_PROMPT):
  │           │     response_2nd = chat(qc_prompt)   # system = QC 프롬프트 (일시)
  │           │     # finally: system_prompt 원복
  │           │
  │           ├─ _apply_qc_patches(response_2nd, "src/foo.py")
  │           │     └─ AgentPatchApplier.apply(... auto_approve=True)
  │           │           → status="exact", applied=2/2
  │           │
  │           └─ print "✅ QC 패치 적용: src/foo.py — 2/2 blocks"
  │
  ▼
요약:
  ✅ 자동 처리 완료: 1개 파일 처리, 1개 파일 저장
  🔍 품질 검사:    1건 검사 — 패치 적용 1건, 변경 없음 0건, 실패 0건
```

### 9.2 `/auto_context -qc` patch 실패 → 재시도 시퀀스

```
... 1차 저장 성공 ...
└─ _run_quality_check
     ├─ attempt=1
     │   chat(qc_prompt) → response (patch 1 블록, no_match)
     │   _apply_qc_patches → status="patch_failed"
     │   print "🔄 QC 재시도 [2/2] — patch 실패"
     │
     ├─ attempt=2 (qc_prompt 에 직전 실패 안내 추가)
     │   chat(qc_prompt') → response (patch 1 블록, exact)
     │   _apply_qc_patches → status="applied"
     │   print "✅ QC 패치 적용: ... — 1/1 blocks"
     │
     └─ break
```

### 9.3 `/context -nt` 호출 경로

```
사용자: /context -nt src/*.py "리팩토링"
  │
  ▼
parse_command_options → no_tree=True, remaining="src/*.py 리팩토링"
  │
  ▼
assistant.chat(
    "리팩토링",
    include_context=True,
    file_patterns=["src/*.py"],
    include_tree=False,                ★
)
  │
  ▼
build_context(include_tree=False, file_patterns=["src/*.py"])
  └─ context_parts 에서 build_file_tree() 스킵 → 파일 본문만 반환
```

---

## 10. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | 2차 검사 모델이 보수적이라 항상 "품질 양호" 만 답할 가능성 | system prompt 의 검사 항목을 **결함 4 분류** 로 명시. ENH-5 (재시도 시 컨텍스트 보강 안내) 가 일부 보완 — 효과 미미 시 Phase 2 에서 cross-model QC (Claude → Gemini) 도입 |
| 2 | 같은 세션의 conversation_history 에 2차 호출의 user/assistant 메시지가 누적 → 다음 1차 호출에 영향 | NFR-04 — 이는 의도된 동작 (사용자가 "방금 본 결과" 를 후속 대화에서 참조 가능). 격리가 필요하면 history 를 별도 세션으로 분리 (Phase 2) |
| 3 | 2차 system prompt swap 의 동시성 — 멀티 스레드 사용 시 race condition | 본 코드베이스는 단일 스레드 REPL — 현 시점 무관. NFR-05 / 향후 멀티 스레드화 시 (1) chat() 시그니처 확장으로 마이그레이션 |
| 4 | 모델이 2차에서 `filename:` 으로 응답하는 경우 (학습 분포 영향) | FR-A-07 — `rejected_filename` 으로 보고하고 스킵. 단순 1차 결과 유지가 최선 (사용자 명시 요건 — "patch 만") |
| 5 | `-qc` 비용 — 모든 파일에 2차 호출 → 토큰 / 시간 ~2 배 | § A.3.7 의 사용자 가이드. ENH-4 (토큰 통계) 로 가시성 제공 |
| 6 | `AgentPatchApplier.apply()` 의 `auto_approve=True` 가 `bypass_approvals` 와 다른 의미 | FR-A-09 — `/auto_context` 자체가 무프롬프트 흐름이므로 일관된 정책. 외부 사용자는 1차 저장이 이미 무프롬프트인 것을 인지하고 명령을 실행 |
| 7 | `-qc` 와 `-nt` 가 같은 명령에 섞이지 않는 이유 — `/auto_context` 는 `include_context=False` 로 호출 | 둘은 직교 옵션 — 한 명령어에서 같이 쓸 일 없음 |
| 8 | `-nt` 기본화 (always-off tree) 요구 가능성 | § B.1.3 비대상 — 회귀 0 정책 유지. 사용자가 자주 켜면 환경변수 `CONTEXT_DEFAULT_NO_TREE=1` 도입 (Phase 2) |
| 9 | `parse_command_options` 가 따옴표로 감싼 옵션-유사 토큰을 처리하지 않음 (예: `'"--no-tree"'` 를 옵션으로 인식) | 위치 인자 시작 판정에 `tok.startswith("'")`/`'"'` 추가 — Phase 2 (현재 사용 패턴 외) |
| 10 | 1차 저장 직후 2차 호출 사이에 사용자가 Ctrl+C 누른 경우 | KeyboardInterrupt 가 `_run_quality_check` 까지 전파되며, `_temporarily_override_system_prompt` 의 finally 가 system_prompt 를 원복. 이미 저장된 1차 파일은 그대로 유지 |

---

## 11. 후속 작업 (Phase 2)

| 단계 | 내용 | 비고 |
|---|---|---|
| 1 | Cross-model QC — `-qc=claude` / `-qc=gemini` 옵션으로 다른 모델에 검사 위임 | ENH-6 |
| 2 | `.qc.bak` 자동 백업 + `/auto_context revert` | ENH-7 |
| 3 | QC 응답에 `filename:` 만 있을 때 자동으로 patch 변환 시도 | 모델 학습 분포 영향 완화 |
| 4 | `CONTEXT_DEFAULT_NO_TREE` 환경변수 — 사용자별 기본값 변경 | § 10 #8 |
| 5 | 토큰 사용량 통계 — 1차/2차 분리 표시 + 비용 추정 | ENH-4 확장 |
| 6 | 3차·N차 chained refinement (`-qc=2` / `-qc=3`) | 본 FSD 비대상 |
| 7 | QC system prompt 사용자 정의 — `~/.config/p3-ai/qc_prompt.txt` 로드 시 우선 | ENH-8 확장 |

---

## 12. 승인

- [ ] 설계 검토 (2차 검사 system prompt swap + patch 적용기 재사용 + `-nt` 옵션 confirm)
- [ ] [src/quality_check_prompt.py](src/quality_check_prompt.py) 신규 — `QUALITY_CHECK_SYSTEM_PROMPT` 정의
- [ ] [src/cli_input.py](src/cli_input.py) 에 `parse_command_options()` 추가
- [ ] [src/context_processor.py](src/context_processor.py) 의 `quality_check` 필드 + `_run_quality_check` / `_apply_qc_patches` / `_temporarily_override_system_prompt` / `_extract_patch_fences` / `_print_summary` 신규
- [ ] [src/claude_assistant.py](src/claude_assistant.py) `chat()` 에 `include_tree` keyword-only 추가
- [ ] [src/genai_assistant.py](src/genai_assistant.py) 동일
- [ ] [src/gemini_assistant.py](src/gemini_assistant.py) 동일
- [ ] [claude-ai-chat-code.py](claude-ai-chat-code.py) `/context` 와 `/auto_context` 분기에 옵션 파서 + 인자 전달
- [ ] [gemini-ai-chat-code.py](gemini-ai-chat-code.py) 동일
- [ ] [gen-ai-chat-code.py](gen-ai-chat-code.py) 동일
- [ ] [tests/test_command_parser_options.py](tests/test_command_parser_options.py) T-123-01 ~ T-123-08 작성·통과
- [ ] [tests/test_context_processor_quality_check.py](tests/test_context_processor_quality_check.py) T-123-10 ~ T-123-24 작성·통과
- [ ] [tests/test_assistants_include_tree.py](tests/test_assistants_include_tree.py) T-123-30 ~ T-123-36 작성·통과
- [ ] 기존 테스트 회귀 확인 — `tests/test_context_processor.py` (FSD v1.0.076 흐름), `tests/test_context_builder.py`
- [ ] 3 어시스턴트(Claude/Gemini/GenAI) 에서 `/auto_context -qc`, `/context -nt` 수동 검증 — M-123-01 ~ M-123-08
- [ ] [docs/releases/RELEASE_v1.0.123_auto-context-qc-and-context-no-tree.md](docs/releases/RELEASE_v1.0.123_auto-context-qc-and-context-no-tree.md) 작성
