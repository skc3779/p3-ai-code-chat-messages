# FSD v1.0.111 — `/agents` ACT 최적화: 파일 수정 Diff/Patch 도입 + 선택지 A/B/C 하이브리드 정합

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.115 |
| 작성일 | 2026-04-26 |
| 구현일 | 2026-04-27 |
| 상태 | ✅ 구현 완료 (수동 확인 대기) |
| 선행 문서 | FSD v1.0.083 (Agents Autonomous Loop), FSD v1.0.100 (Bypass Approvals), FSD v1.0.103 (Bypass File Overwrite), FSD v1.0.106 (System Prompt Disambiguation), FSD v1.0.107 (Action Dispatcher), FSD v1.0.110 (Shell-Aware Executors) |
| 대상 파일 | [src/agent_runner.py](src/agent_runner.py), [src/agent_action_dispatcher.py](src/agent_action_dispatcher.py), [src/response_parser.py](src/response_parser.py) |
| 신규 파일 | [src/agent_patch_applier.py](src/agent_patch_applier.py), [tests/test_agent_patch_applier.py](tests/test_agent_patch_applier.py), [tests/test_agent_dispatcher_patch.py](tests/test_agent_dispatcher_patch.py), [tests/test_agent_system_prompt_v111.py](tests/test_agent_system_prompt_v111.py) |

---

## 1. 개요 (Overview)

`/agents` 의 자율 루프는 매 iteration 마다 [REASON] → [ACT] → [OBSERVE] 를 반복한다. 그중 [ACT] 의 **선택지 A — 파일 생성/수정** 은 현재 **항상 파일 전문(全文)을 다시 작성** 하도록 설계되어 있다(FSD v1.0.083 § 4.1, [src/response_parser.py:51](src/response_parser.py#L51) 의 ` ```filename:<path>` 블록). 이 방식은 다음 문제를 야기한다.

| # | 증상 | 비용 | 위험 |
|---|---|---|---|
| 1 | 한 줄 수정에도 1,000줄 파일 전체를 다시 모델에 출력시켜야 함 | 토큰 사용량 폭증(입력+출력) | 모델 컨텍스트 윈도우 압박 → 압축 빈도 증가 → 정보 손실 |
| 2 | 긴 파일을 재작성하다 모델이 중간 끊김(`...` 생략, 토큰 한도) 발생 | 자기 수정 사이클 추가 비용 | **데이터 손실** — 끊긴 파일이 그대로 저장될 수 있음 |
| 3 | 동시에 다른 도구가 같은 파일을 수정한 경우 모델이 들고 있던 stale 한 전문이 덮어씀 | 사용자 변경분 유실 | git 백업 없으면 복구 불가 |
| 4 | "이 함수만 한 줄 추가" 같은 국소 수정이 시각적으로 노이즈 | 사용자가 diff 를 사람-눈으로 검수해야 함 | 검수 누락 → 잘못된 수정 |

본 FSD 는 **선택지 A 에 Diff/Patch 모드를 도입**해 위 4건을 일괄 해결하며, 모델이 두 모드(전문 vs 패치) 사이에서 적절히 선택할 수 있도록 시스템 프롬프트를 고도화한다. 또한 **선택지 B(코드 실행) · 선택지 C(쉘 명령)** 의 분류·실행 경로에서 같은 결에서 발견된 정합성 이슈도 함께 정리한다.

### 1.1 다루는 문제

| # | 영역 | 현 문제 | 본 FSD 의 대응 |
|---|---|---|---|
| A | **파일 수정 토큰 낭비** | 항상 파일 전문 재작성 — 1줄 수정에도 전체 출력 | `` ```patch:<path> `` SEARCH/REPLACE 블록 도입. 신규/대규모 변경은 기존 ` ```filename:` 유지 |
| B | 코드 실행 vs 쉘 명령 혼동 잔존 | v1.0.107 디스패처가 라우팅하지만 모델이 여전히 ` ```python` 안에 쉘 명령을 적거나, ` ```bash` 안에 ` $ ` 와 함수 정의를 섞음 | 시스템 프롬프트의 선택지 B/C 정의를 **결정 트리 형태**로 재서술. 디스패처에 **혼합 블록 경고** 추가 |
| C | `$ ` 라인 위험 명령 검사 회피 | `cmd1 && cmd2` / `cmd1; cmd2` 형태에서 첫 토큰만 검사. `echo ok && rm -rf /` 통과 가능 | 체이닝 분리 후 **각 세그먼트의 첫 토큰** 을 검사 |
| D | 패치 실패 시 자기 수정 정보 부족 | (신규) 패치 적용 실패는 line-number drift 가 아니라 SEARCH 블록 매치 실패 — 모델에 **현재 파일 단편(snippet)** 을 돌려줘야 한다 | 적용 실패 시 OBSERVE 에 일치 후보 ±5줄 컨텍스트 첨부 |

### 1.2 비범위

| 항목 | 비고 |
|---|---|
| AST 기반 코드 변환 / refactor | 본 FSD 는 **텍스트 Diff** 만 다룸. AST는 별도 FSD |
| 통합(unified) diff 형식 (`@@ -a,b +c,d @@`) | 라인 번호 drift 에 취약 — 본 FSD 는 **SEARCH/REPLACE** 채택 (§ 3.1 참조) |
| 멀티 파일 동시 patch 트랜잭션 (한 파일이 실패하면 모두 롤백) | Phase 2 — 본 FSD 는 **per-block 독립 적용** |
| Choice A 의 신규 파일 생성 형식 변경 | 신규 파일은 ` ```filename:` 그대로. patch 모드는 기존 파일 한정 |
| 모델 자체의 코드 생성 품질 | 본 FSD 는 **출력 형식 채널** 만 정의. 변경 결정은 모델 책임 |
| `/auto_context` 의 동작 변경 | `/agents` 루프 안의 [ACT] 만 영향 |

---

## 2. 현황 분석

### 2.1 선택지 A — 항상 전문 재작성

[src/agent_runner.py:471-476](src/agent_runner.py#L471-L476) 시스템 프롬프트:

```text
== 선택지 A. 파일 생성/수정 ==
  ```filename:<상대경로>
  ... 파일 전문 ...
  ```
  • 한 블록에 한 파일. 워크스페이스 상대경로.
  • 줄바꿈·인코딩 원본 그대로. 언어 태그를 섞지 마세요.
```

[src/response_parser.py:51](src/response_parser.py#L51) 의 라인 기반 파서는 ` ```filename:<path>` 시작 → ` ``` ` 종료까지의 본문을 그대로 디스크에 기록한다. 부분 patch 의 개념이 없다.

#### 2.1.1 토큰 비용 측정 (관찰)

가설적 케이스 — 1,000줄 (~6,000 토큰) Python 파일에 `import os` 한 줄 추가:

| 방식 | 모델 출력 토큰 | 모델 입력 토큰(다음 iter 의 history 압축 전) |
|---|---|---|
| 전문 재작성 | ~6,000 | ~6,000 |
| Diff (SEARCH/REPLACE 1쌍) | ~30 | ~30 |

**~200x 토큰 절감**. 5회 iteration 가정 시 ~30,000 토큰 절약 = $0.10~0.50 (모델별).

### 2.2 선택지 B — 코드 실행 라우팅 잔존 이슈

[src/agent_action_dispatcher.py:43-44](src/agent_action_dispatcher.py#L43-L44) 분류:

```python
SHELL_LANGS = {"bash", "sh", "shell", "powershell", "ps1"}
CODE_LANGS = {"python", "py", "javascript", "js"}
```

v1.0.107 가 **쉘 계열 코드 블록** → `$ ` 라인 추출 → 쉘 단일 명령으로 라우팅하도록 했으나:

| # | 잔존 케이스 | 결과 |
|---|---|---|
| 1 | ` ```python` 안에 `import subprocess; subprocess.run("ls")` 만 적힌 경우 | 코드 실행은 성공하나 쉘 의도였다면 토큰 낭비 — 모델 의도가 모호 |
| 2 | ` ```bash` 안에 `function greet() { ... }` 와 `$ greet` 가 같이 있을 때 | SCRIPT_INDICATORS 가 `function` 매칭 → 전체를 script 로 분류, `$ greet` 도 함수 호출로 묻혀 라인 분해 안 됨 (의도 일치) |
| 3 | ` ```bash` 안에 단순 `ls -la` 한 줄(`$ ` 없음)만 있을 때 | `_strip_dollar` 가 `$ ` 없어도 원본 반환하지만 분류 결과가 'commands' 면 그대로 단일 쉘 명령으로 실행 — 의도 일치 |
| 4 | ` ```python` 코드 안에 `\n$ ls -la\n` 가 docstring으로 포함된 경우 | dispatcher 가 펜스 영역을 마스킹하므로 `$ ` 라인이 추출 안 됨 — 의도 일치 |

→ 잔존 우려는 #1 한 가지. 본 FSD 는 시스템 프롬프트에서 **"코드 안에서 OS 호출하지 말고 선택지 C 사용"** 지침을 강화한다.

### 2.3 선택지 C — 위험 명령 체이닝 회피

[src/agent_runner.py:740-741](src/agent_runner.py#L740-L741):

```python
base = cmd.split()[0].lower() if cmd.split() else ""
dangerous = base in self.terminal_executor.DANGEROUS_COMMANDS
```

[src/agent_runner.py:628-629](src/agent_runner.py#L628-L629) 도 동일 패턴.

문제: `&&`, `||`, `;` 로 체이닝된 경우 **첫 토큰만 검사**.

| 입력 | base | 검사 결과 | 실제 실행 |
|---|---|---|---|
| `rm -rf /` | `rm` | 위험 ✅ | 차단 또는 승인 요청 |
| `echo ok && rm -rf /` | `echo` | 안전 ❌ | **승인 없이 실행** |
| `ls; rm -rf /` | `ls` | 안전 ❌ | **승인 없이 실행** |
| `false || rm -rf /` | `false` | 안전 ❌ | **승인 없이 실행** |

이는 **현재 코드의 보안 취약점** 이다. 본 FSD 에서 함께 수정한다.

### 2.4 시스템 프롬프트 — 결정 트리 부재

현재 프롬프트(v1.0.107, [src/agent_runner.py:447-530](src/agent_runner.py#L447-L530))는 선택지 A/B/C 를 **나열** 한다. 모델이 "어느 선택지를 골라야 하는가" 를 판단하기 위한 **명시적 결정 트리** 가 없다 — 따라서 모델은 자신의 학습 분포(주로 Aider/Cursor 등의 프롬프트 패턴)에 의존해 결정한다. v1.0.111 은 결정 트리를 명시한다.

---

## 3. 설계 (Design)

### 3.1 형식 선정 — SEARCH/REPLACE vs Unified Diff

#### 3.1.1 후보 비교

| 형식 | 장점 | 단점 | 평가 |
|---|---|---|---|
| **Unified diff** (`@@ -a,b +c,d @@`) | 표준 형식 — `git apply` 활용 가능 | 라인 번호 drift 에 취약. 모델이 `a,b,c,d` 계산 빈번하게 틀림. CRLF/LF 혼합 시 깨짐 | ❌ |
| **SEARCH/REPLACE** (Aider/Cline 스타일) | 라인 번호 없음 → drift 면역. 텍스트 매칭이라 CRLF 정규화 가능. AI 학습 분포에서 빈도 높음 | 같은 텍스트가 여러 곳 등장 시 모호. 큰 변경엔 비효율 | ✅ **채택** |
| **앵커 기반** (`<<<OLD>>>...<<<NEW>>>`) | 단순 | 표준화된 구분자 부재. 모델 출력 변동성 큼 | ❌ |
| **OpenAI V4A patch** (`*** Begin Patch`) | 컨텍스트 라인 명시 | 모델 학습 분포에서 빈도 낮음. 우리 fence 파서와 충돌 | ❌ |

**결정**: SEARCH/REPLACE 채택. 라인 번호 drift 가 없는 점이 결정적 — 모델이 patch 를 만든 시점과 적용 시점 사이에 파일이 바뀌어도 SEARCH 블록 매치만 성공하면 적용된다.

#### 3.1.2 형식 정의

**펜스 태그**: ` ```patch:<상대경로>` (` ```filename:` 와 평행).

**본문 문법**:

```
<<<<<<< SEARCH
(원본 파일에서 정확히 매칭될 텍스트 블록)
=======
(교체될 새 텍스트 블록)
>>>>>>> REPLACE
```

- 한 펜스 안에 **하나의 파일**, **N 개의 SEARCH/REPLACE 쌍** 허용
- 빈 SEARCH = 파일 끝 append (편의 규칙 — § 3.1.4)
- 빈 REPLACE = 해당 SEARCH 블록 삭제
- 7개 `<`, 7개 `=`, 7개 `>` 를 정확히 사용 (Git 의 머지 컨플릭트 마커 차용)

**예시 1 — 단순 한 줄 추가**:

````markdown
```patch:src/agent_runner.py
<<<<<<< SEARCH
import os
import platform
import re
=======
import os
import platform
import re
import json
>>>>>>> REPLACE
```
````

**예시 2 — 함수 본문 교체 (다중 블록)**:

````markdown
```patch:src/agent_runner.py
<<<<<<< SEARCH
    def _has_code_failure(actions: List[ActionResult]) -> bool:
        return any(
            (not a.success) and a.kind in ("code", "shell") for a in actions
        )
=======
    def _has_code_failure(actions: List[ActionResult]) -> bool:
        # v1.0.111: file 액션 실패도 자기 수정 트리거에 포함
        return any(
            (not a.success) and a.kind in ("code", "shell", "file")
            for a in actions
        )
>>>>>>> REPLACE
<<<<<<< SEARCH
    SEP = "─" * 60
=======
    SEP = "─" * 60
    PATCH_FUZZY_WHITESPACE = True
>>>>>>> REPLACE
```
````

**예시 3 — 블록 삭제**:

````markdown
```patch:src/legacy.py
<<<<<<< SEARCH
def deprecated_helper():
    """Will be removed in v2."""
    pass

=======
>>>>>>> REPLACE
```
````

**예시 4 — 파일 끝 append (빈 SEARCH)**:

````markdown
```patch:CHANGELOG.md
<<<<<<< SEARCH
=======

## v1.0.111
- ACT 의 선택지 A 에 patch 모드 도입.
>>>>>>> REPLACE
```
````

#### 3.1.3 결정 트리 — 모델이 모드를 고르는 기준

시스템 프롬프트에 **명시적 결정 규칙** 을 박는다(§ 3.4).

```
파일 작업이 필요할 때:
1. 신규 파일 생성       → ```filename:<path>``` 전문
2. 기존 파일 수정인데
   2-a. 변경 라인 < 40% → ```patch:<path>``` SEARCH/REPLACE  ← 권장
   2-b. 대규모 재작성 (전체 구조 개편) → ```filename:<path>``` 전문
3. 파일 삭제            → 선택지 C 의 $ rm <path> (위험 명령 승인)
```

#### 3.1.4 빈 SEARCH 의미

원본 파일이 비어있거나 끝에 추가하는 경우 SEARCH 블록을 비울 수 있다. 빈 SEARCH 가 등장하면 적용기는:

- 파일이 존재하지 않으면 → 새 파일을 만들고 REPLACE 본문을 그대로 기록 (`patch:` 가 신규 파일 생성을 겸함)
- 파일이 존재하면 → 끝에 REPLACE 본문 append (직전에 줄바꿈 보장)

> 단, **신규 파일 생성은 가능하면 ` ```filename:` 을 쓰도록** 시스템 프롬프트에서 권장. patch 의 빈 SEARCH 는 비상용.

### 3.2 패치 적용 알고리즘

#### 3.2.1 단일 SEARCH/REPLACE 쌍 적용

```
apply_one(file_text, search, replace) → (new_text, status, diagnostic)
  │
  ├─ search == "":
  │     return (file_text + "\n" + replace, "appended", None)
  │
  ├─ exact = file_text.count(search)
  │
  ├─ if exact == 1:
  │     return (file_text.replace(search, replace, 1), "exact", None)
  │
  ├─ if exact > 1:
  │     return (file_text, "ambiguous", "multiple_matches=N")
  │
  ├─ # exact == 0 → fuzzy 매칭
  │   normalized_file   = normalize_whitespace(file_text)
  │   normalized_search = normalize_whitespace(search)
  │   if normalized_file.count(normalized_search) == 1:
  │       # 원본 파일에서 해당 위치 찾아 replace
  │       return (apply_fuzzy(file_text, search, replace), "fuzzy", None)
  │
  └─ return (file_text, "no_match",
             diagnostic=nearest_snippet_with_line_numbers(file_text, search))
```

**`normalize_whitespace`**:
- 라인 끝의 공백/탭 제거
- 연속된 공백/탭 1개로 압축
- CRLF → LF
- 라인 시작 들여쓰기는 보존 (Python 인덴트 의존)

**`apply_fuzzy`**:
- 정규화된 텍스트에서 위치를 찾아 원본 텍스트의 해당 라인 범위를 통째로 교체. 들여쓰기 차이는 REPLACE 본문에서 모델이 책임 — 단, 첫 라인의 들여쓰기를 원본에 맞춰 자동 정렬한다 (§ 3.2.4).

#### 3.2.2 적용 결과 코드

| status | 의미 | OBSERVE 표시 |
|---|---|---|
| `exact` | SEARCH 가 정확히 한 번 매칭 — 그대로 교체 | `✅ patched (exact)` |
| `fuzzy` | 공백 정규화 후 한 번 매칭 — 정렬 보정 후 교체 | `✅ patched (fuzzy)` |
| `appended` | 빈 SEARCH — 파일 끝 추가 또는 신규 파일 생성 | `✅ patched (appended)` |
| `ambiguous` | SEARCH 가 N(>1) 회 매칭 — 적용 보류 | `❌ patch ambiguous (N matches) — SEARCH 에 컨텍스트를 더 추가하세요` |
| `no_match` | SEARCH 매칭 실패 | `❌ patch no_match — 최근접 스니펫:\n<L42-L52>` |

#### 3.2.3 다중 블록 적용 — 트랜잭션

한 파일에 N 개의 SEARCH/REPLACE 가 있을 때:

```
apply_all(file_text, blocks) → (new_text, results)
  │
  ├─ working = file_text
  ├─ results = []
  │
  ├─ for block in blocks:
  │     working, status, diag = apply_one(working, block.search, block.replace)
  │     results.append({"status": status, "diagnostic": diag})
  │     # status 가 ambiguous/no_match 라도 다음 블록은 시도 — 모델이 다음 iteration 에 부분 수정 가능
  │
  └─ if all(r.status in ("exact", "fuzzy", "appended")):
         write file
         return (working, results)
     else:
         # **부분 실패 시 디스크에 쓰지 않는다** — 트랜잭셔널 의미 보존
         return (file_text, results)
```

> 부분 실패 시 모두 롤백 — 한 블록이 다른 블록의 컨텍스트에 의존할 수 있어 일관성 보존이 필수.

#### 3.2.4 들여쓰기 자동 정렬 (fuzzy 모드 한정)

Python·YAML 처럼 들여쓰기가 의미를 갖는 언어에서 모델이 SEARCH 의 들여쓰기를 빼먹는 경우가 잦다. fuzzy 모드 적용 시:

```
원본 첫 라인 들여쓰기 = "    " (4 spaces)
SEARCH 첫 라인 들여쓰기 = ""
REPLACE 첫 라인 들여쓰기 = ""

→ delta = 4
→ REPLACE 의 모든 라인 앞에 "    " prefix
```

단, exact 모드에서는 절대 자동 정렬하지 않는다 (정확히 매칭됐으니 모델 의도대로 적용).

#### 3.2.5 신규 파일 자동 생성

` ```patch:<path>` 의 모든 블록이 **빈 SEARCH** 이고 파일이 존재하지 않으면 → 새 파일을 만들고 REPLACE 본문들을 차례로 이어붙여 기록. 다만 모델에는 **신규 파일은 ` ```filename:` 을 쓰라** 고 안내(§ 3.4).

#### 3.2.6 Bypass Approvals 와의 정합

[src/response_parser.py:101](src/response_parser.py#L101) 의 `auto_overwrite=True` 분기와 동일한 정책을 patch 에도 적용:

| 조건 | patch 적용 |
|---|---|
| `session.bypass_approvals == True` | 사용자 프롬프트 없이 적용 |
| 그 외 | 첫 적용 시 사용자 승인 (y/N/A — `auto_approve_file_mutation`) |

> 신규 추가: 비-bypass 모드의 patch 에 대한 **세션-수준 자동 승인 플래그** `auto_approve_file_mutation` 을 도입한다. `A` (Always) 선택 시 같은 세션의 후속 patch 도 자동 적용.

### 3.3 디스패처 통합

#### 3.3.1 새 파싱 진입

[src/agent_action_dispatcher.py:99](src/agent_action_dispatcher.py#L99) `_parse()` 의 펜스 분기 분류:

```python
# 기존:
if tag.lower().startswith("filename:"):
    actions.append(_ParsedAction(kind="file", payload=code, filepath=filepath))
    continue

# 추가:
if tag.lower().startswith("patch:"):
    filepath = tag.split(":", 1)[1].strip()
    actions.append(_ParsedAction(
        kind="patch", payload=code, filepath=filepath,
    ))
    continue
```

#### 3.3.2 새 어댑터 `_exec_patch`

```python
def _exec_patch(self, session, a: _ParsedAction) -> "ActionResult":
    """patch 적용 — AgentPatchApplier 위임."""
    from .agent_patch_applier import AgentPatchApplier
    from .agent_runner import ActionResult

    applier = AgentPatchApplier(self._runner.file_manager)
    result = applier.apply(
        a.filepath,
        a.payload,
        auto_approve=bool(
            session.bypass_approvals
            or session.auto_approve_file_mutation
        ),
        on_first_approval=lambda: self._runner._approve_dangerous(
            session, "auto_approve_file_mutation",
            f"파일 patch '{a.filepath}'",
        ),
    )

    if result.success:
        detail = "\n".join(
            f"  block#{i+1}: {r.status}" for i, r in enumerate(result.block_results)
        )
        return ActionResult(
            kind="file", target=a.filepath, success=True,
            detail=f"patched ({result.applied_count}/{result.total_count}) blocks\n{detail}",
        )
    else:
        # 부분 실패 — diagnostic 첨부
        diag_lines = []
        for i, r in enumerate(result.block_results):
            if r.status not in ("exact", "fuzzy", "appended"):
                diag_lines.append(f"  block#{i+1}: {r.status}\n    {r.diagnostic or ''}")
        return ActionResult(
            kind="file", target=a.filepath, success=False,
            detail="patch 실패 — 적용 안됨 (트랜잭셔널 롤백)\n"
                   + "\n".join(diag_lines),
        )
```

### 3.4 시스템 프롬프트 v1.0.111

[src/agent_runner.py:447](src/agent_runner.py#L447) `_build_system_prompt()` 의 **선택지 A 섹션** 을 다음과 같이 교체. **선택지 B/C** 는 유지하되 결정 트리 헤더를 추가.

```text
[ACT — 의사결정 트리]
무엇을 해야 하는지에 따라 단 하나의 선택지를 고르세요.

  파일을 만들거나 바꿔야 하는가?
    └─ YES
        ├─ 신규 파일?                              → 선택지 A-1 (filename)
        ├─ 기존 파일을 일부만 수정 (변경 < 40%)?  → 선택지 A-2 (patch)  ★ 권장 ★
        └─ 기존 파일을 사실상 다시 쓰기?          → 선택지 A-1 (filename)
    └─ NO
        ├─ 짧은 코드를 한 번 돌려 결과만 보고 싶은가?  → 선택지 B
        └─ OS / Git / 패키지 매니저 명령이 필요한가? → 선택지 C

== 선택지 A-1. 파일 전문 (신규 또는 대규모 재작성) ==
  ```filename:<상대경로>
  ... 파일 전문 ...
  ```
  • 한 블록에 한 파일.
  • 줄바꿈·인코딩 원본 그대로. 언어 태그를 섞지 마세요.

== 선택지 A-2. 파일 패치 (기존 파일의 부분 수정) ==
  ```patch:<상대경로>
  <<<<<<< SEARCH
  (원본에 있는 텍스트 블록 — 한 곳에서만 매칭되도록 충분한 컨텍스트 포함)
  =======
  (바뀐 텍스트 블록)
  >>>>>>> REPLACE
  ```
  • 한 펜스에 같은 파일의 여러 SEARCH/REPLACE 쌍을 넣을 수 있습니다.
  • SEARCH 블록은 원본 파일에 **정확히 한 번** 등장해야 합니다. 모호하면
    위/아래에 한두 줄을 더 포함시켜 유일하게 만드세요.
  • 들여쓰기·공백·줄바꿈을 원본 그대로 복사하세요. 자동 정렬은 시스템이
    하지만 정확한 매칭이 항상 더 안전합니다.
  • 블록 삭제는 REPLACE 를 비우면 됩니다.
  • 신규 파일을 만들 때는 A-2 가 아닌 A-1 을 사용하세요.

  📋 예시 — `import json` 을 imports 끝에 추가:
    ```patch:src/agent_runner.py
    <<<<<<< SEARCH
    import os
    import platform
    import re
    =======
    import os
    import platform
    import re
    import json
    >>>>>>> REPLACE
    ```

  📋 예시 — 함수 본문 교체 + 상수 추가 (한 펜스, 두 블록):
    ```patch:src/agent_runner.py
    <<<<<<< SEARCH
        def _has_code_failure(actions):
            return any(not a.success for a in actions)
    =======
        def _has_code_failure(actions):
            # file 실패도 자기 수정 트리거
            return any((not a.success) and a.kind in ("code","shell","file")
                       for a in actions)
    >>>>>>> REPLACE
    <<<<<<< SEARCH
        SEP = "─" * 60
    =======
        SEP = "─" * 60
        PATCH_FUZZY = True
    >>>>>>> REPLACE
    ```

  ❌ 자주 하는 실수:
    1) SEARCH 블록을 너무 짧게 작성 → 여러 곳 매칭 → ambiguous 실패
    2) SEARCH 의 들여쓰기를 임의로 줄임 → 매칭 실패 가능
    3) 한 파일을 ```filename:``` 과 ```patch:``` 양쪽으로 동시 작성

== 선택지 B. 코드 실행 (임시 실행 — 파일 저장 없음) ==
  ```python
  print("hello")
  ```
  • 언어 태그는 정확히 `python` / `javascript` 두 가지만 사용.
  • 타임아웃 30초 · 워크스페이스 cwd · UTF-8 자동 강제.
  • ⚠️ 코드 안에서 `subprocess.run` / `os.system` 으로 OS 호출하지 마세요 —
     OS 명령은 **선택지 C** 로 분리하세요. (가독성·승인 정책 분리)
  • ⚠️ `bash`/`sh`/`shell`/`powershell`/`ps1` 태그는 자동으로 쉘로 라우팅됩니다.

== 선택지 C. 쉘 명령 실행 ==
  라인 시작에 `$ <명령>` — 코드 블록으로 감싸지 마세요.
    $ git status
    $ python --version
  • 한 줄에 한 명령. 파이프(|)·리다이렉트(>)·`&&`·`;`·`||` 는 한 줄 내 허용.
  • ⚠️ 체이닝(`&&`/`;`/`||`) 안에 위험 명령(rm, del 등) 이 있으면 시스템이
     **각 세그먼트를 검사**해 승인을 요구합니다.
  • 명령은 {shell_type} 구문을 사용하세요.
  • (선택) 명시 라우팅: `[ACTION:shell]` 태그.
```

> 위 텍스트의 `{shell_type}` 은 v1.0.107 그대로 런타임 치환.

### 3.5 위험 명령 체이닝 검사 (보안 패치)

[src/agent_runner.py:628](src/agent_runner.py#L628) / [src/agent_runner.py:740-741](src/agent_runner.py#L740-L741) 의 단일 토큰 검사를 **세그먼트 분해 후 일괄 검사** 로 교체.

```python
def _split_chained_segments(cmd: str) -> List[str]:
    """`&&`, `||`, `;` 로 분할. 큰따옴표/작은따옴표 안의 구분자는 보존."""
    segments: List[str] = []
    buf, i, n = [], 0, len(cmd)
    quote: Optional[str] = None
    while i < n:
        c = cmd[i]
        if quote:
            if c == quote and (i == 0 or cmd[i-1] != "\\"):
                quote = None
            buf.append(c); i += 1; continue
        if c in ("'", '"'):
            quote = c; buf.append(c); i += 1; continue
        # 2글자 분리자 우선
        if c in ("&", "|") and i+1 < n and cmd[i+1] == c:
            segments.append("".join(buf).strip()); buf = []; i += 2; continue
        if c == ";":
            segments.append("".join(buf).strip()); buf = []; i += 1; continue
        buf.append(c); i += 1
    tail = "".join(buf).strip()
    if tail:
        segments.append(tail)
    return [s for s in segments if s]


def _is_chain_dangerous(cmd: str, dangerous_set: Set[str]) -> bool:
    """체이닝된 모든 세그먼트 중 하나라도 위험 명령이면 True."""
    for seg in _split_chained_segments(cmd):
        first = seg.split()[0].lower() if seg.split() else ""
        if first in dangerous_set:
            return True
    return False
```

`_exec_single_shell_command()` 와 `_run_shell_lines()` 의 위험 검사를 `_is_chain_dangerous()` 호출로 교체. 승인 프롬프트의 라벨에는 **위험 세그먼트** 만 표시한다.

### 3.6 자기 수정(Self-Correction) 통합

[src/agent_runner.py:978-981](src/agent_runner.py#L978-L981) 의 `_has_code_failure()` 는 현재 `code`, `shell` 만 자기 수정 대상. **patch 실패도 자기 수정 트리거** 에 포함.

```python
@staticmethod
def _has_code_failure(actions: List[ActionResult]) -> bool:
    return any(
        (not a.success) and a.kind in ("code", "shell", "file")
        for a in actions
    )
```

자기 수정 프롬프트(`_format_failure`) 는 patch 실패 시 `block#N: no_match` 와 nearest snippet 을 그대로 모델에 돌려준다 — 모델은 SEARCH 블록의 컨텍스트를 보강해 재시도.

---

## 4. 파일 변경 예정 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [src/agent_patch_applier.py](src/agent_patch_applier.py) | **신규** | `AgentPatchApplier` 클래스. SEARCH/REPLACE 파싱·exact/fuzzy 매칭·트랜잭셔널 적용·신규 파일 생성. 외부 의존 없음 (stdlib + `FileManager`) |
| [src/agent_action_dispatcher.py](src/agent_action_dispatcher.py) | 수정 | `_parse()` 에 `patch:` 분기 추가. `dispatch()` 의 `kind="patch"` 라우팅. `_exec_patch()` 어댑터 신설 |
| [src/agent_runner.py](src/agent_runner.py) | 수정 | `_build_system_prompt()` 의 선택지 A 섹션 v1.0.111 본문으로 교체. `_has_code_failure()` 에 `"file"` 추가. `_split_chained_segments()` / `_is_chain_dangerous()` 신규. 위험 검사 두 곳을 신 함수로 치환. `auto_approve_file_mutation` 의 patch 흐름 연동 |
| [src/response_parser.py](src/response_parser.py) | 수정(없음 가능) | patch 는 dispatcher 가 직접 처리하므로 변경 없음. 단, 기존 ` ```filename:` 동작은 유지 (패치 모드와 분기) |
| [tests/test_agent_patch_applier.py](tests/test_agent_patch_applier.py) | **신규** | T-111-01 ~ T-111-20 — 적용기 단위 테스트 |
| [tests/test_agent_dispatcher_patch.py](tests/test_agent_dispatcher_patch.py) | **신규** | T-111-30 ~ T-111-39 — 디스패처 통합 |
| [tests/test_agent_system_prompt_v111.py](tests/test_agent_system_prompt_v111.py) | **신규** | T-111-40 ~ T-111-44 — 시스템 프롬프트 회귀 |
| [tests/test_agent_chain_danger.py](tests/test_agent_chain_danger.py) | **신규** | T-111-50 ~ T-111-56 — 체이닝 위험 검사 |
| [tests/test_agent_runner.py](tests/test_agent_runner.py) | 수정(최소) | `_has_code_failure` 에 `"file"` 포함된 회귀 추가 |

---

## 5. 요구사항 (Requirements)

### 5.1 기능 요구사항 (FR)

#### A. Patch 형식 / 적용

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-111-01 | 디스패처는 ` ```patch:<path>` 펜스를 인식해 `kind="patch"` 액션으로 분류한다 | 필수 |
| FR-111-02 | 한 펜스 안의 N 개의 SEARCH/REPLACE 쌍을 모두 파싱한다 (구분자 `<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE`) | 필수 |
| FR-111-03 | 각 SEARCH 가 원본 파일에서 정확히 한 번 매칭되면 exact 모드로 적용한다 | 필수 |
| FR-111-04 | exact 매칭 실패 시 공백 정규화(라인-끝 trim, 연속 공백 1개로 압축, CRLF→LF) 후 재시도. 한 번 매칭되면 fuzzy 모드로 적용 | 필수 |
| FR-111-05 | 같은 SEARCH 가 N(>1) 회 매칭되면 ambiguous 로 표시하고 적용하지 않는다 | 필수 |
| FR-111-06 | 매칭 실패(no_match) 시 원본 파일에서 SEARCH 블록과 가장 유사한 ±5줄 스니펫을 라인 번호와 함께 diagnostic 에 포함한다 | 필수 |
| FR-111-07 | 한 파일의 N 개 블록 중 하나라도 실패하면 디스크에 쓰지 않는다 (트랜잭셔널) | 필수 |
| FR-111-08 | 빈 SEARCH 가 등장하면 파일 끝 append 또는 신규 파일 생성으로 동작한다 | 필수 |
| FR-111-09 | fuzzy 모드 적용 시 REPLACE 본문의 첫 라인 들여쓰기를 원본 첫 라인 들여쓰기에 자동 정렬한다 | 필수 |
| FR-111-10 | exact 모드에서는 자동 정렬을 수행하지 않는다 | 필수 |

#### B. 승인 / 보안

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-111-11 | `session.bypass_approvals == True` 일 때 patch 는 프롬프트 없이 적용된다 | 필수 |
| FR-111-12 | `auto_approve_file_mutation == False` 이고 비-bypass 모드일 때 첫 patch 는 y/N/A 승인을 요구한다 | 필수 |
| FR-111-13 | A(Always) 선택 시 세션 내 후속 patch 는 자동 적용 | 필수 |
| FR-111-14 | 위험 명령 검사는 `&&`/`||`/`;` 로 분리된 모든 세그먼트의 첫 토큰을 검사한다 | 필수 |
| FR-111-15 | 따옴표(`"..."`/`'...'`) 안의 구분자는 분리하지 않는다 | 필수 |
| FR-111-16 | 체이닝 안에 하나라도 위험 명령이 있으면 전체 명령을 위험으로 취급, 승인을 요구한다 | 필수 |

#### C. 시스템 프롬프트 / 모델 가이드

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-111-17 | `_build_system_prompt()` 출력에 결정 트리 헤더가 포함된다 (선택지 A-1/A-2/B/C 분기) | 필수 |
| FR-111-18 | 시스템 프롬프트에 SEARCH/REPLACE 형식 정의와 최소 2 개의 구체 예시(단순 추가, 다중 블록)가 포함된다 | 필수 |
| FR-111-19 | 시스템 프롬프트는 신규 파일에는 ` ```filename:` 을 사용하라고 명시한다 | 필수 |
| FR-111-20 | 시스템 프롬프트는 코드 실행(B) 안에서 OS 호출을 피하고 선택지 C 로 분리하라고 안내한다 | 필수 |
| FR-111-21 | 시스템 프롬프트 길이 증가는 v1.0.107 대비 ≤ 1.6배 (모델 입력 비용 통제) | 권장 |

#### D. 자기 수정 / 결과 표시

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-111-22 | patch 실패가 발생하면 `_has_code_failure()` 가 True 를 반환해 자기 수정 루프를 트리거한다 | 필수 |
| FR-111-23 | 자기 수정 프롬프트(`_format_failure`)에 patch diagnostic 의 nearest snippet 이 포함된다 | 필수 |
| FR-111-24 | OBSERVE 블록의 patch 항목은 `✅ patch <path> — N/M blocks (exact/fuzzy/appended)` 형태로 요약된다 | 필수 |
| FR-111-25 | 같은 iteration 안에서 한 파일을 ` ```filename:` 과 ` ```patch:` 양쪽으로 작성한 경우, dispatcher 는 **filename 을 우선** 적용하고 patch 액션은 `kind="file", success=False, detail="동일 파일에 filename 블록이 우선 적용됨"` 로 보고한다 | 필수 |

### 5.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-111-01 | `AgentPatchApplier` 는 외부 의존 없이 stdlib 만 사용 (PyInstaller 패키징 호환) |
| NFR-111-02 | 1MB 파일에 SEARCH/REPLACE 1쌍 적용 시간 ≤ 100ms (Windows 기준) |
| NFR-111-03 | exact 매칭은 `str.count` / `str.replace(..., 1)` 만 사용 — O(N) 보장 |
| NFR-111-04 | fuzzy 매칭은 정규화 후 `str.find` 단일 호출 — O(N) 보장 (정규식 미사용) |
| NFR-111-05 | 트랜잭셔널 적용은 in-memory copy 1회 — 적용 중간 상태가 디스크에 노출되지 않는다 |
| NFR-111-06 | patch 적용 결과 diagnostic 은 한 항목당 ≤ 500자 (모델 컨텍스트 통제) |
| NFR-111-07 | `_split_chained_segments` 는 따옴표 인식형이지만 정규식 미사용 (이스케이프 처리 일관) |
| NFR-111-08 | 시스템 프롬프트는 Python 일반 문자열로만 구성 — `.format()` 부작용 회피 (중괄호 escape 불필요) |
| NFR-111-09 | 기존 ` ```filename:` 동작과 ` ```patch:` 동작은 **상호 독립** — 한 쪽 변경이 다른 쪽 회귀를 만들지 않는다 |
| NFR-111-10 | patch 실패 시에도 동일 [ACT] 블록 안의 다른 액션(코드/쉘/다른 파일 patch) 실행은 계속된다 (자기 수정 위임) |

---

## 6. 테스트 시나리오

### 6.1 AgentPatchApplier 단위 (`tests/test_agent_patch_applier.py`)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-111-01 | 단일 SEARCH/REPLACE — exact 매칭 | `status="exact"`, 파일에 적용됨 |
| T-111-02 | SEARCH 가 0번 매칭 (`no_match`) — 디스크 미변경 | 파일 unchanged, diagnostic 에 nearest snippet (라인 번호 포함) |
| T-111-03 | SEARCH 가 2번 매칭 (`ambiguous`) | 파일 unchanged, diagnostic="multiple_matches=2" |
| T-111-04 | SEARCH 가 들여쓰기만 다름 (` ` 4-space vs ` ` 2-space) — fuzzy 매칭 | `status="fuzzy"`, 적용됨, REPLACE 첫 라인 들여쓰기가 원본에 정렬됨 |
| T-111-05 | CRLF 원본 + LF SEARCH | fuzzy 모드로 매칭, 원본 EOL 유지 |
| T-111-06 | 한 펜스 안 3 개 블록 — 모두 성공 | 모두 적용, 파일 1회 쓰기 |
| T-111-07 | 한 펜스 안 3 개 블록 — 두 번째 ambiguous | 디스크 미변경, 결과 list 에 3 entries (success/ambiguous/skipped 또는 status only) |
| T-111-08 | 빈 SEARCH + 비어있지 않은 REPLACE — 기존 파일 끝 append | 파일 끝 줄바꿈 1개 보장 + REPLACE 추가 |
| T-111-09 | 빈 SEARCH + 신규 파일 (path 미존재) | 새 파일 생성, REPLACE 본문 그대로 기록 |
| T-111-10 | REPLACE 가 빈 문자열 — SEARCH 블록 삭제 | 해당 블록 사라짐, 주변 라인 보존 |
| T-111-11 | 1MB 파일에 SEARCH/REPLACE 1쌍 (NFR-111-02) | 100ms 이내 완료 |
| T-111-12 | UTF-8 한글 SEARCH | 깨짐 없이 매칭·적용 |
| T-111-13 | SEARCH 블록 중 한 라인이 정규식 메타문자(`(`, `[`, `*`) | 리터럴로 매칭 (정규식 미사용 검증) |
| T-111-14 | path traversal (`../etc/passwd`) | 거부 — `FileManager.workspace_dir` 밖이면 IOError |
| T-111-15 | 잘못된 마커 갯수(`<<<<<<<` 6개) | 파싱 실패, diagnostic="invalid SEARCH marker" |
| T-111-16 | SEARCH/REPLACE 마커가 같은 라인에 끝나지 않음 (개행 누락) | 파싱 실패 처리 |
| T-111-17 | SEARCH 에 trailing newline 차이 (`\n` 끝 vs 없음) | fuzzy 매칭 성공 |
| T-111-18 | 적용 중 IOError (디스크 가득) | 디스크 미변경, success=False |
| T-111-19 | 트랜잭셔널 — 1번 성공·2번 실패 | 파일 unchanged, 1번 결과 보고는 그대로 (모델 가시성) |
| T-111-20 | 같은 파일에 두 번 호출 (한 iter 에 두 펜스) | 두 번째 호출은 첫 번째 결과를 본 상태에서 매칭 |

### 6.2 디스패처 통합 (`tests/test_agent_dispatcher_patch.py`)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-111-30 | ACT 에 ` ```patch:src/x.py` 펜스 한 개 | `_ParsedAction(kind="patch", filepath="src/x.py")` 생성 |
| T-111-31 | ACT 에 ` ```patch:` (path 누락) | 파싱 실패 — `kind="file", success=False, detail="patch path 미지정"` |
| T-111-32 | ACT 에 ` ```filename:src/x.py` + ` ```patch:src/x.py` 동시 | filename 우선 적용. patch 는 보고만 (FR-111-25) |
| T-111-33 | ACT 에 ` ```patch:` 와 ` ```python` 코드 동시 | patch 후 코드 실행 — 둘 다 보고 |
| T-111-34 | bypass_approvals=True 에서 patch | 승인 프롬프트 없이 적용 |
| T-111-35 | bypass_approvals=False, auto_approve_file_mutation=False, 사용자가 'A' 응답 | 첫 patch 적용 + 세션 플래그 True |
| T-111-36 | 자기 수정 — patch 실패 → SELF_CORRECT 프롬프트에 nearest snippet 포함 | `_has_code_failure()` True, `_format_failure()` 에 diagnostic 텍스트 |
| T-111-37 | dispatcher 가 patch 액션을 dedupe 대상에서 제외 (file 과 동일 정책) | 같은 path 두 번 들어와도 두 번 실행 |
| T-111-38 | 보고된 ActionResult.kind | `"file"` (OBSERVE 표시 일관성) |
| T-111-39 | 빈 패치 본문 (마커만 있고 내용 없음) | 파싱 결과 0 블록 — `kind="file", success=False, detail="patch 빈 본문"` |

### 6.3 시스템 프롬프트 회귀 (`tests/test_agent_system_prompt_v111.py`)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-111-40 | `_build_system_prompt()` 에 `"의사결정 트리"` 헤더 포함 | 통과 |
| T-111-41 | 프롬프트에 `"```patch:<상대경로>"` 와 `"<<<<<<< SEARCH"` 포함 | 통과 |
| T-111-42 | 프롬프트에 v1.0.107 의 `[ACTION:shell]` 명시 라우팅 보존 | 통과 (회귀 방지) |
| T-111-43 | 프롬프트 길이 ≤ v1.0.107 길이 × 1.6 | 통과 (FR-111-21) |
| T-111-44 | 프롬프트가 `.format()` 호환 (중괄호 conflict 없음) | `prompt.format()` 호출에 KeyError 없음 |

### 6.4 체이닝 위험 검사 (`tests/test_agent_chain_danger.py`)

| # | 입력 | base_first | `_is_chain_dangerous()` |
|---|---|---|---|
| T-111-50 | `rm -rf /` | rm | True |
| T-111-51 | `echo ok && rm -rf /` | echo | **True** (회귀 방지 — § 2.3) |
| T-111-52 | `ls; rm -rf /` | ls | **True** |
| T-111-53 | `false || rm -rf /` | false | **True** |
| T-111-54 | `echo "rm -rf /"` | echo | **False** (따옴표 안 — NFR-111-07) |
| T-111-55 | `git status && git diff` | git | False |
| T-111-56 | `cmd1 \&\& cmd2` (이스케이프된 `&&`) | cmd1 | False (이스케이프 인식) |

### 6.5 회귀 (변경 없음 확인)

- 기존 `tests/test_agent_runner.py`, `tests/test_agent_dispatcher.py` 전 케이스
- 기존 `tests/test_response_parser.py` — ` ```filename:` 동작 회귀
- 기존 `tests/test_terminal_executor*.py` — 위험 명령 검사 변경(체이닝) 후 단일 명령 케이스 회귀

---

## 7. 실행 흐름 다이어그램

### 7.1 patch 적용 (정상)

```
[ACT] 응답
  │
  ├─ ```patch:src/x.py (3 SEARCH/REPLACE 블록)
  │
  ▼
AgentActionDispatcher._parse()
  └─ _ParsedAction(kind="patch", filepath="src/x.py", payload="...")
  │
  ▼
AgentActionDispatcher._exec_patch()
  │
  ▼
AgentPatchApplier.apply("src/x.py", payload)
  │
  ├─ parse_blocks()  → [Block1, Block2, Block3]
  ├─ original = file_manager.read_file("src/x.py")
  ├─ working = original
  │
  ├─ for block in blocks:
  │     working, status = apply_one(working, block.search, block.replace)
  │     results.append((status, ...))
  │
  ├─ all_ok = all(s in ("exact","fuzzy","appended") for s in results)
  │
  ├─ if all_ok:
  │     승인 검사 (bypass / auto_approve / 첫 호출 y/N/A)
  │     file_manager.write_file("src/x.py", working)
  │     return PatchResult(success=True, applied=3, total=3)
  │
  └─ else:
        # **디스크 미변경**
        return PatchResult(success=False, block_results=results)
  │
  ▼
ActionResult(kind="file", target="src/x.py", success=True/False, detail=...)
  │
  ▼
[OBSERVE]
  ✅ patch src/x.py — 3/3 blocks (exact, exact, fuzzy)
```

### 7.2 patch 실패 → 자기 수정

```
[ACT] iter 3 의 patch 가 block#2 ambiguous → 디스크 미변경
  │
  ▼
ActionResult.success=False
  │
  ▼
_has_code_failure() = True   (FR-111-22)
  │
  ▼
_self_correct_loop() 진입
  │
  ├─ _format_failure() 가 diagnostic 첨부:
  │     [파일 patch 실패: src/x.py]
  │     block#1: exact (보고용)
  │     block#2: ambiguous (multiple_matches=3) — SEARCH 에 컨텍스트 부족
  │     block#3: skipped (전체 트랜잭션 롤백)
  │
  ├─ 모델 호출 → 새 [REASON] / [ACT] (보강된 SEARCH)
  │
  └─ dispatcher 재실행 → 성공
```

### 7.3 결정 트리 (모델 측)

```
모델이 [ACT] 작성 시:
  │
  ├─ 파일 만들기?
  │   ├─ 신규     → ```filename: 전문
  │   └─ 기존
  │       ├─ 변경 < 40%   → ```patch: SEARCH/REPLACE
  │       └─ 대규모 재작성 → ```filename: 전문
  │
  ├─ 코드 한번 돌려보기?  → ```python / ```javascript
  │
  └─ OS / Git / 패키지?  → $ <명령>
```

---

## 8. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | **모델이 SEARCH 컨텍스트를 너무 짧게 잡아 ambiguous 빈발 가능** | 자기 수정 루프가 nearest 매칭 후보 수를 돌려주므로 모델이 컨텍스트를 보강. 시스템 프롬프트의 "❌ 자주 하는 실수" 섹션이 사전 안내 |
| 2 | 이진 파일(.png, .pdf 등)에 patch 시도 — UTF-8 디코드 실패 | `AgentPatchApplier.apply()` 진입 시 `read_file()` 가 latin-1 fallback 으로 읽으므로 매칭은 가능하지만 텍스트 변경 의도 자체가 잘못 — 사용자에게 응답에서 안내 |
| 3 | path traversal — `../../etc/passwd` 같은 경로 | `file_path = file_manager.workspace_dir / current_path` 후 `file_path.resolve().is_relative_to(workspace_dir)` 검사. 위반 시 IOError |
| 4 | git diff 출력을 그대로 복붙한 모델 응답 (`@@ -a,b +c,d @@`) | dispatcher 가 패턴 인식해 "Unified diff 는 미지원, SEARCH/REPLACE 로 변환하세요" diagnostic 반환 (Phase 2) |
| 5 | 같은 파일을 한 iteration 에 ```filename:``` 과 ```patch:``` 양쪽 작성 | filename 우선, patch 는 보고만 (FR-111-25) — 두 번 쓰기로 인한 race 제거 |
| 6 | bypass_approvals 가 patch 도 자동 적용 → 잘못된 patch 가 적용될 위험 | 트랜잭셔널 적용 + 자기 수정 루프 + (선택) git 백업 가정 — v1.0.083 의 "git commit 으로 백업" 가정 보존 |
| 7 | `_is_chain_dangerous` 가 따옴표를 인식하지만 backtick `` ` `` 안의 명령은 미인식 | 현재 `DANGEROUS_COMMANDS` 체크는 첫 토큰만이라 backtick 안의 명령은 그대로 위험. Phase 2 에서 PowerShell `$()` / bash `$(...)` 도 인식 |
| 8 | fuzzy 정렬이 잘못 들어가 코드 들여쓰기를 망칠 수 있음 | 정렬은 **fuzzy 모드 + REPLACE 첫 라인 들여쓰기 = 0** 일 때만 작동. exact 모드에서는 비활성. 단위 테스트 T-111-04 / T-111-09 / T-111-10 으로 보장 |
| 9 | 한 펜스에 1,000 블록 같은 극단 입력 → 메모리 폭증 | `apply_all()` 의 working copy 가 매번 N×1MB 가 되지 않도록 in-place mutation 방지(불변 문자열). N>50 이면 경고 — Phase 2 |
| 10 | 시스템 프롬프트가 길어져 매 iter 모델 비용 증가 | NFR-111-21: ≤ v1.0.107 의 1.6배. 절감되는 출력 토큰(§ 2.1.1) 이 훨씬 큼 — net 이득 |

---

## 9. 후속 작업 (Optional / Phase 2)

| 단계 | 내용 | 비고 |
|---|---|---|
| 1 | Unified diff(`@@ ... @@`) 자동 변환기 | 모델이 `git diff` 를 그대로 붙여넣을 때 SEARCH/REPLACE 로 변환 |
| 2 | 멀티 파일 트랜잭션 (한 iter 의 모든 patch 가 성공해야 디스크 반영) | 일관성 있는 마이그레이션을 위함 |
| 3 | patch dry-run 모드 (`PATCH_DRY_RUN=1`) — 실제 적용 없이 결과만 OBSERVE | 사용자 검수 워크플로 |
| 4 | AST 기반 patch (````patch-py:src/x.py` 의 함수명/클래스명 단위) | Python·JS·Java 한정. 라인 매칭 실패율 추가 감소 |
| 5 | git auto-commit per patch — 적용 직후 자동 커밋 (선택적) | 롤백 용이 |
| 6 | backtick `` `...` `` / `$()` 안의 명령 위험 검사 | 보안 강화 |

---

## 10. 승인

- [x] 설계 검토 (선택지 A 의 patch 모드 도입 + 결정 트리 + 보안 패치)
- [x] [src/agent_patch_applier.py](../../src/agent_patch_applier.py) 신규 — `AgentPatchApplier` 클래스
- [x] [src/agent_action_dispatcher.py](../../src/agent_action_dispatcher.py) `_parse()` 의 `patch:` 분기 + `_exec_patch()` 어댑터
- [x] [src/agent_runner.py](../../src/agent_runner.py) 시스템 프롬프트 v1.0.111 본문 교체
- [x] [src/agent_runner.py](../../src/agent_runner.py) `_split_chained_segments()` / `_is_chain_dangerous()` + 위험 검사 두 곳 치환
- [x] [src/agent_runner.py](../../src/agent_runner.py) `_has_code_failure()` 에 `"file"` 포함
- [x] [src/agent_runner.py](../../src/agent_runner.py) `auto_approve_file_mutation` patch 흐름 연동 (`_exec_patch` 의 auto_approve 게이트)
- [x] [tests/test_agent_patch_applier.py](../../tests/test_agent_patch_applier.py) T-111-01 ~ T-111-20 작성·통과 (+ 승인 흐름 2건)
- [x] [tests/test_agent_dispatcher_patch.py](../../tests/test_agent_dispatcher_patch.py) T-111-30 ~ T-111-39 작성·통과
- [x] [tests/test_agent_system_prompt_v111.py](../../tests/test_agent_system_prompt_v111.py) T-111-40 ~ T-111-44 작성·통과 (+ FR-111-19/20 회귀)
- [x] [tests/test_agent_chain_danger.py](../../tests/test_agent_chain_danger.py) T-111-50 ~ T-111-56 작성·통과 (+ 분리기 단위)
- [x] 기존 테스트 회귀 확인 (NFR-111-09) — `test_agent_runner.py` T-06 갱신, `test_os_utils_and_agent_prompt.py` T-107-02/06 갱신, 직접 영향 242 건 전체 통과
- [ ] Windows PowerShell / Linux 환경에서 `/agents` 자율 루프 patch 모드 수동 검증 — 1줄 추가, 함수 교체, 다중 블록, ambiguous 자기 수정
- [x] [docs/releases/RELEASE_v1.0.115_agents-patch-mode.md](../releases/RELEASE_v1.0.115_agents-patch-mode.md) 작성
