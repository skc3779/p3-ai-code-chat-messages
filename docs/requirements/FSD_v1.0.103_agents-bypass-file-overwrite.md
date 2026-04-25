# FSD v1.0.103 — 에이전트 Bypass Approvals 모드 파일 Overwrite 자동 승인

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.103 |
| 작성일 | 2026-04-23 |
| 상태 | ✅ 구현 완료 (2026-04-23) |
| 선행 문서 | FSD v1.0.083 (`/agents` 자율 에이전트 루프), FSD v1.0.100 (Bypass Approvals 모드), FSD v1.0.101 (최대 반복 횟수 제어·Resume Index) |
| 대상 파일 | [src/response_parser.py](src/response_parser.py), [src/agent_runner.py](src/agent_runner.py), [src/claude_assistant.py](src/claude_assistant.py), [src/gemini_assistant.py](src/gemini_assistant.py), [src/genai_assistant.py](src/genai_assistant.py) |
| 신규 파일 | [tests/test_response_parser_overwrite.py](tests/test_response_parser_overwrite.py) (테스트 전용) |

---

## 1. 개요

### 1.1 목적

FSD v1.0.100 에서 도입된 **Bypass Approvals 모드**(이하 *Bypass 모드*)는 `_ask_continue()` 의 턴 사이 프롬프트, 위험 shell 단건 확인, 파일 변경 단건 확인(`auto_approve_file_mutation`) 등 **대부분의 대화형 프롬프트**를 스킵한다.

그러나 현재 구현에서는 **AI 응답에 포함된 파일 블록(```filename:...```) 을 저장할 때, 동일 경로 파일이 이미 존재하면 여전히 `input("덮어쓰시겠습니까? (y/N): ")` 프롬프트가 출력**된다. [src/response_parser.py:93-105](src/response_parser.py#L93-L105)

```python
# 파일이 이미 존재하면 덮어쓰기 여부 확인
if file_path.exists():
    print(f"\n⚠️  파일이 이미 존재합니다: {current_path}")
    try:
        confirm = input("덮어쓰시겠습니까? (y/N): ").strip().lower()
        if confirm != 'y':
            print(f"⏭️  건너뛰기: {current_path}")
            ...
```

이 프롬프트는 다음 상황에서 Bypass 모드의 **"사용자 개입 없는 자율 실행"** 설계 목표와 정면으로 충돌한다.

- 야간/백그라운드 실행: 사용자 부재 중 `input()` 에서 루프가 정지됨 → `EOFError` 후 건너뛰기로 대량 파일 변경 실패
- 리팩토링 목표: 기존 파일 수정이 주 작업인데, 매 파일마다 승인 프롬프트로 중단
- CI/파이프라인 환경: stdin 비활성 상태에서 `EOFError` 로 저장 실패 → `BYPASS_STAGNATION` 오탐 가능

본 FSD 는 **Bypass 모드가 활성화된 경우에 한해 기존 파일의 덮어쓰기 확인 프롬프트를 스킵하고 즉시 덮어쓰기**를 수행하도록 한다.

### 1.2 범위

| 항목 | 포함 여부 |
|---|---|
| Bypass 모드에서 `parse_and_save()` 의 overwrite 프롬프트 스킵 | ✅ |
| 대화형(L0) 모드는 기존 동작 100% 유지 | ✅ |
| `ResponseParser.parse_and_save()` 시그니처에 Bypass 신호 전달 | ✅ |
| `AgentRunner._save_file_blocks()` 에서 `session.bypass_approvals` 전달 | ✅ |
| Bypass 덮어쓰기 발생 시 사용자에게 명시적 안내 메시지 | ✅ |
| 덮어쓰기 전 자동 백업(.bak) 파일 생성 | ❌ 범위 외 (별도 FSD) |
| 파일 저장 횟수 한도(위험 shell `AGENT_BYPASS_MAX_DANGEROUS` 와 유사) | ❌ 범위 외 (4.2 에서 제안) |
| `/run` 명령(대화형)에서의 `parse_and_save()` 동작 변경 | ❌ 범위 외 — 에이전트 루프 전용 |

---

## 2. 현황 분석

### 2.1 파일 저장 경로

현재 `AgentRunner` 는 AI 응답의 파일 블록을 두 경로로 저장한다.

1. 에이전트 루프: [src/agent_runner.py:565](src/agent_runner.py#L565) — `self.response_parser.parse_and_save(act_text)`
2. 대화형 `/run`, 스트리밍 후처리: 각 Assistant 의 `_extract_and_save_files()` — [src/claude_assistant.py:510](src/claude_assistant.py#L510), [src/gemini_assistant.py:349](src/gemini_assistant.py#L349), [src/genai_assistant.py:429](src/genai_assistant.py#L429)

양쪽 모두 `ResponseParser.parse_and_save()` 를 사용하지만, **Bypass 모드는 오직 에이전트 루프 내부에서만 유효**하므로 동작 분기는 에이전트 경로에서만 일어나야 한다.

### 2.2 `ResponseParser.parse_and_save()` 현재 시그니처

[src/response_parser.py:15](src/response_parser.py#L15)

```python
def parse_and_save(self, response: str) -> List[str]:
```

Bypass 신호를 받을 인자가 없다. 세 Assistant 에서 모두 동일 인터페이스로 호출된다.

### 2.3 `AgentSession.bypass_approvals` (FSD v1.0.100)

[src/agent_runner.py:52-62](src/agent_runner.py#L52-L62) — 세션 플래그로 이미 존재.

- Bypass 진입 시 `_enter_bypass_mode()` 가 `bypass_approvals=True` 및 `auto_approve_file_mutation=True` 로 설정
- Resume 시 `bypass_approvals=False` 로 초기화 (FR-100-11)

본 FSD 는 **이 기존 플래그를 그대로 신호로 재사용**한다. 새 플래그를 추가하지 않는다.

### 2.4 `auto_approve_file_mutation` 플래그의 현재 쓰임

현재 이 플래그는 **세션 필드로만 존재**하고, `ResponseParser.parse_and_save()` 내부에서는 참조되지 않는다. (위험 shell 승인 경로에서만 사용됨) 따라서 본 FSD 의 구현은 이 플래그를 `ResponseParser` 까지 **처음으로 연결**하는 작업이기도 하다.

---

## 3. 설계

### 3.1 적용 원칙

> **Bypass 모드일 때만(`session.bypass_approvals is True`) overwrite 프롬프트를 스킵한다.** 그 외 모든 경로(`/run`, 대화형 `/agents` L0, 세 Assistant 의 `_extract_and_save_files`) 는 기존 프롬프트 동작을 유지한다.

이를 위해 Bypass 신호를 `ResponseParser` 까지 전달해야 한다. 3가지 설계안 중 **A안(명시적 인자 전달)** 을 채택한다.

| 안 | 방식 | 장점 | 단점 | 채택 |
|---|---|---|---|---|
| A | `parse_and_save(response, *, auto_overwrite: bool=False)` — 인자 추가 | 명시적·무상태·테스트 용이 | 세 Assistant 호출부 각각 시그니처 무변경(기본값 False), 에이전트 루프만 True 전달 | ✅ |
| B | `ResponseParser` 인스턴스에 세션 참조 주입 (생성자) | 코드 변경 최소 | 세션 수명과 파서 수명 불일치(파서는 Assistant 수명), 전역 가변 상태 | ❌ |
| C | 환경 변수/전역 플래그 | 파라미터 전파 불필요 | 테스트 격리성 파괴, 재진입 시 누수 | ❌ |

### 3.2 `ResponseParser.parse_and_save()` 수정

[src/response_parser.py](src/response_parser.py)

```python
def parse_and_save(
    self,
    response: str,
    *,
    auto_overwrite: bool = False,
) -> List[str]:
    """
    ...
    Args:
        response: AI 응답 원문
        auto_overwrite: True 면 기존 파일 존재 시에도 프롬프트 없이 덮어쓴다.
                        에이전트 루프의 Bypass Approvals 모드에서만 True 로 호출된다.
                        기본값 False — 대화형 경로는 기존 동작 유지.
    """
```

덮어쓰기 분기 수정:

```python
# 2-c) 최상위 파일 블록의 종료 -> 파일 저장 프로세스
file_path = self.file_manager.workspace_dir / current_path

if file_path.exists():
    if auto_overwrite:
        # Bypass Approvals — 사용자 프롬프트 없이 즉시 덮어쓰기
        print(f"\n⚡ BYPASS: 기존 파일 자동 덮어쓰기: {current_path}")
    else:
        # 기존 동작(대화형) — 사용자 확인
        print(f"\n⚠️  파일이 이미 존재합니다: {current_path}")
        try:
            confirm = input("덮어쓰시겠습니까? (y/N): ").strip().lower()
            if confirm != 'y':
                print(f"⏭️  건너뛰기: {current_path}")
                collecting = False
                continue
        except EOFError:
            print(f"⏭️  입력 불가로 건너뛰기: {current_path}")
            collecting = False
            continue

# 파일에 내용 기록
file_content = "\n".join(current_content).strip()
if self.file_manager.write_file(file_path, file_content):
    saved_files.append(current_path)
    print(f"✅ 파일 저장됨: {current_path}")
```

> **Keyword-only 인자**(`*`)로 받는 이유: 기존 위치 인자 호출부(세 Assistant) 와의 호환성을 보장하고, 실수로 `True` 를 흘려 넣는 것을 방지한다.

### 3.3 `AgentRunner._save_file_blocks()` 수정

[src/agent_runner.py:557-585](src/agent_runner.py#L557-L585)

세션 플래그를 `ResponseParser` 에 전달하도록 시그니처 확장.

```python
def _execute_actions(
    self, session: AgentSession, act_text: str
) -> List[ActionResult]:
    if not act_text:
        return []
    results: List[ActionResult] = []
    results += self._save_file_blocks(session, act_text)   # ← session 전달
    results += self._run_code_blocks(act_text)
    results += self._run_shell_lines(session, act_text)
    return results

def _save_file_blocks(
    self, session: AgentSession, act_text: str
) -> List[ActionResult]:
    results: List[ActionResult] = []
    declared = [m.strip() for m in self.RE_FILENAME_BLOCK.findall(act_text)]
    if not declared:
        return results

    try:
        saved = self.response_parser.parse_and_save(
            act_text,
            auto_overwrite=bool(session.bypass_approvals),   # ← 신규
        ) or []
    except Exception as e:
        ...
```

호출측(`_execute_actions`) 한 줄만 `session` 인자를 전달하도록 변경한다.

### 3.4 대화형 경로 — 변경 없음

[src/claude_assistant.py:510](src/claude_assistant.py#L510), [src/gemini_assistant.py:349](src/gemini_assistant.py#L349), [src/genai_assistant.py:429](src/genai_assistant.py#L429)

세 Assistant 의 `_extract_and_save_files()` 는 `auto_overwrite` 인자 없이 호출한다. 기본값 False 로 기존 프롬프트 동작이 그대로 유지된다.

```python
# 변경 없음 — 기본값 False 로 동작
def _extract_and_save_files(self, response: str) -> List[str]:
    return self.response_parser.parse_and_save(response)
```

### 3.5 안내 메시지 정책

Bypass 덮어쓰기는 **사용자 부재 중 수행될 가능성이 높으므로**, 감사(audit) 및 사후 검토를 위해 각 파일마다 한 줄의 명시적 로그를 남긴다.

| 시점 | 출력 |
|---|---|
| 덮어쓰기 전 | `⚡ BYPASS: 기존 파일 자동 덮어쓰기: <path>` |
| 덮어쓰기 성공 | `✅ 파일 저장됨: <path>` (기존) |
| 덮어쓰기 실패 | `❌ 파일 저장 실패: <path>` (기존) |
| 신규 파일 | `✅ 파일 저장됨: <path>` (기존, 차이 없음) |

`⚡` 이모지는 FSD v1.0.100 의 위험 shell 자동 승인 메시지(`⚡ BYPASS: 위험 명령 자동 승인`)와 시각적 일관성을 유지한다.

### 3.6 예외 흐름

| 상황 | Bypass 모드 동작 | 근거 |
|---|---|---|
| 덮어쓰기 대상이 읽기 전용 파일 | `file_manager.write_file()` 가 False 반환 → `❌ 파일 저장 실패` 로그 | 기존 동작 그대로 — Bypass 는 "프롬프트 스킵"이지 "권한 우회"가 아님 |
| 경로 상위 디렉터리 없음 | `file_manager.write_file()` 이 디렉터리 생성 처리 (기존 동작) | FR v1.0.103 에서 신규로 강제하지 않음 |
| 디스크 꽉참 등 I/O 오류 | 상위 `try/except` 에서 "저장 오류" 로 ActionResult 생성 → S3 정체 탐지에 기여 | FSD v1.0.100 안전장치로 처리 |
| `parse_and_save()` 이 blanket `except Exception` 에 흡수됨 | 에이전트 루프의 `_save_file_blocks` 는 이미 `try/except` 로 감싸고 있음 ([agent_runner.py:565-572](src/agent_runner.py#L565-L572)) — 변경 없음 | - |

### 3.7 동작 요약표

| 모드 | 파일 신규 | 파일 기존 |
|---|---|---|
| 대화형 `/run`, `/agents` L0 | 즉시 저장 | `덮어쓰시겠습니까? (y/N):` 프롬프트 — **기존 동작** |
| `/agents` — `_ask_continue` 에서 `[b]` 선택 후 | 즉시 저장 | **즉시 덮어쓰기** (본 FSD) |
| `/agents -ba <goal>` (시작 시점 Bypass) | 즉시 저장 | **즉시 덮어쓰기** (본 FSD) |
| `/agents resume` (Bypass 초기화 후) | 즉시 저장 | `덮어쓰시겠습니까? (y/N):` 프롬프트 — FR-100-11 에 의해 기본 복귀 |

---

## 4. 추가 제안 (Optional Enhancements)

### 4.1 덮어쓰기 전 자동 백업(.bak) — 별도 FSD 권장

Bypass 중 덮어쓰기는 **복구 불가능한 손실**로 이어질 수 있다. 간단한 완화책은 덮어쓰기 직전 `<path>.bak` 을 만들어 두는 것이다.

- 장점: 사용자가 결과 불만족 시 즉시 복구 가능
- 단점: 대용량 파일 다수 수정 시 디스크 I/O 2배, 세션 종료 후 `.bak` 정리 정책 필요
- 현실적 대안: **git commit 이 이미 백업 역할을 한다** (기존 FSD v1.0.083 "실행 전 중요한 파일은 git commit 으로 백업되어 있다고 가정" 원칙과 일치)

본 FSD 에서는 **구현하지 않음**. 도입 필요성 체감 시 별도 FSD 로 분리.

### 4.2 Bypass 중 파일 변경 누적 한도 — 별도 FSD 권장

FSD v1.0.100 의 S5 (위험 shell 누적 한도) 와 유사하게, Bypass 중 덮어쓴 파일 수가 일정치를 넘으면 종료.

```
AGENT_BYPASS_MAX_FILE_OVERWRITE=30  # 기본 30개, 초과 시 BYPASS_FILE_LIMIT
```

- 장점: 모델이 폭주해서 수백 파일을 덮어쓰는 사고 방지
- 단점: 대규모 리팩토링이 본래 목적일 때 False Positive
- 권장: 1차 구현은 생략 → 실사용 후 도입 여부 판단

### 4.3 Git Dirty 상태 사전 체크 (권장 ★)

Bypass 진입 시 `git status` 가 깨끗하지 않으면 경고 후 확인 프롬프트 표시.

- 사용자가 커밋하지 않은 작업이 있는 상태에서 Bypass 덮어쓰기로 인해 작업이 섞이는 사고 방지
- FSD v1.0.100 `4.3 Bypass 시작 시 사전 확인` 과 결합 가능 (PLAN 출력 + dirty 경고)
- 본 FSD 범위 외 — v1.0.100 확장으로 제안

---

## 5. 파일 변경 예정 목록

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| [src/response_parser.py](src/response_parser.py) | 수정 | `parse_and_save()` 에 `auto_overwrite: bool=False` keyword-only 인자 추가, 덮어쓰기 분기 이원화, 안내 메시지 추가 |
| [src/agent_runner.py](src/agent_runner.py) | 수정 | `_save_file_blocks(session, act_text)` 시그니처 확장, `_execute_actions()` 에서 session 전달, `parse_and_save(act_text, auto_overwrite=session.bypass_approvals)` 호출 |
| [src/claude_assistant.py](src/claude_assistant.py) | 변경 없음 | `_extract_and_save_files()` 는 기본값 False 로 기존 동작 유지 |
| [src/gemini_assistant.py](src/gemini_assistant.py) | 변경 없음 | 동일 |
| [src/genai_assistant.py](src/genai_assistant.py) | 변경 없음 | 동일 |
| [tests/test_response_parser_overwrite.py](tests/test_response_parser_overwrite.py) | 신규 | T-103-01 ~ T-103-06 테스트 케이스 (단위 테스트) |
| [tests/test_agent_runner.py](tests/test_agent_runner.py) | 수정 | T-103-07 ~ T-103-08 (AgentRunner 통합 테스트) |
| [docs/specs/releases/](docs/specs/releases/) | 신규 | 구현 완료 후 `RELEASE_v1.0.103_agents-bypass-file-overwrite.md` 작성 |

---

## 6. 요구사항 (Functional / Non-Functional)

### 6.1 기능 요구사항 (FR)

| ID | 내용 | 우선순위 |
|---|---|---|
| FR-103-01 | `ResponseParser.parse_and_save(response, *, auto_overwrite=False)` 시그니처를 제공한다 (keyword-only) | 필수 |
| FR-103-02 | `auto_overwrite=False` (기본값) 인 경우, 기존 파일 발견 시 `덮어쓰시겠습니까? (y/N):` 프롬프트를 출력한다 (기존 동작 100% 유지) | 필수 |
| FR-103-03 | `auto_overwrite=True` 인 경우, 기존 파일 발견 시 프롬프트 없이 즉시 덮어쓴다 | 필수 |
| FR-103-04 | `auto_overwrite=True` 인 경우, 덮어쓰기 전 `⚡ BYPASS: 기존 파일 자동 덮어쓰기: <path>` 로그를 출력한다 | 필수 |
| FR-103-05 | `AgentRunner._save_file_blocks()` 는 `session.bypass_approvals` 값을 `auto_overwrite` 인자로 전달한다 | 필수 |
| FR-103-06 | 세 Assistant 의 `_extract_and_save_files()` 경로는 `auto_overwrite` 를 전달하지 않는다 (기본값 False) | 필수 |
| FR-103-07 | Bypass 모드에서 파일 저장 실패(쓰기 오류) 는 기존과 동일하게 `ActionResult(success=False)` 로 집계되어 S3 정체 탐지에 반영된다 | 필수 |
| FR-103-08 | Resume 세션(`bypass_approvals=False` 로 초기화됨) 에서는 overwrite 프롬프트가 다시 출력된다 | 필수 |
| FR-103-09 | Bypass 중 누적 덮어쓰기 수에 대한 한도 제약은 본 FSD 에서 구현하지 않는다 | 선택 (4.2) |

### 6.2 비기능 요구사항 (NFR)

| ID | 내용 |
|---|---|
| NFR-103-01 | `ResponseParser` API 변경은 하위호환이어야 한다. 기본값 False 로 기존 호출부를 수정하지 않는다. |
| NFR-103-02 | Bypass 덮어쓰기 안내 메시지는 FSD v1.0.100 의 `⚡ BYPASS:` 프리픽스 컨벤션과 시각적으로 일관되어야 한다. |
| NFR-103-03 | 파일별 분기 오버헤드는 `if auto_overwrite` 단건 체크 수준이며, I/O 나 네트워크 호출을 추가하지 않는다. |
| NFR-103-04 | 본 FSD 의 구현은 **프롬프트 스킵**이지 **권한 우회**가 아니다. OS 레벨 권한 오류는 기존 경로로 ActionResult 실패로 집계된다. |
| NFR-103-05 | 대화형 경로(`/run`, `/agents` L0) 의 UX 는 한 줄도 변경되지 않는다. |

---

## 7. 테스트 시나리오

### 7.1 단위 테스트 (`tests/test_response_parser_overwrite.py`)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-103-01 | 존재하지 않는 경로에 파일 블록 저장 (`auto_overwrite=False`) | 파일 생성됨, `saved_files` 에 포함 |
| T-103-02 | 기존 파일에 `auto_overwrite=False` + `input` mock 이 `"y"` 반환 | 덮어쓰기 성공, 기존 메시지 출력 |
| T-103-03 | 기존 파일에 `auto_overwrite=False` + `input` mock 이 `"n"` 반환 | 건너뛰기 로그 출력, `saved_files` 에 미포함 |
| T-103-04 | 기존 파일에 `auto_overwrite=False` + stdin 비활성(`EOFError`) | `⏭️  입력 불가로 건너뛰기` 로그, `saved_files` 에 미포함 |
| T-103-05 | 기존 파일에 `auto_overwrite=True` | `input()` 호출 없음(mock 검증), `⚡ BYPASS` 로그 출력, 덮어쓰기 성공 |
| T-103-06 | 존재하지 않는 경로에 `auto_overwrite=True` | `⚡ BYPASS` 로그는 출력되지 않음 (신규 파일), 일반 저장 메시지만 출력 |

### 7.2 통합 테스트 (`tests/test_agent_runner.py`)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-103-07 | `session.bypass_approvals=False` 에서 `_save_file_blocks()` 실행, 기존 파일 + stdin 에 `"n"` 주입 | 파일 덮어쓰기되지 않음, ActionResult `success=False` |
| T-103-08 | `session.bypass_approvals=True` 에서 `_save_file_blocks()` 실행, 기존 파일 | `input()` 호출 없음 (mock 검증), 파일 덮어쓰기 성공, ActionResult `success=True` |
| T-103-09 | `/agents -ba "기존 파일 X 를 수정해"` 시나리오 (E2E) — 모델 응답이 기존 파일 블록 포함 | Bypass 모드로 진입 → 파일이 즉시 덮어쓰여짐, 루프 중단 없음 |
| T-103-10 | `/agents resume <file>` 로 Bypass 였던 세션을 재개 | `bypass_approvals=False` 로 초기화되므로 기존 파일 덮어쓰기 시도 시 다시 프롬프트 출력 |

---

## 8. 실행 흐름 다이어그램

### 8.1 Bypass 모드 파일 저장 플로우

```
AgentRunner.run(... bypass_approvals=True)
  │
  ▼
_enter_bypass_mode(session)
  └─ session.bypass_approvals = True
  │
  ▼
[루프] 각 iteration:
  ├─ model.chat() → [ACT] 블록에 ```filename:src/foo.py ... ```
  ├─ _execute_actions(session, act_text)
  │    └─ _save_file_blocks(session, act_text)
  │         └─ response_parser.parse_and_save(
  │              act_text,
  │              auto_overwrite=session.bypass_approvals  ← True
  │            )
  │              └─ file_path.exists() == True
  │                   └─ auto_overwrite=True
  │                       ├─ print("⚡ BYPASS: 기존 파일 자동 덮어쓰기: src/foo.py")
  │                       └─ file_manager.write_file(...) (프롬프트 없음)
  │                          → saved_files.append("src/foo.py")
  └─ ActionResult(kind="file", target="src/foo.py", success=True)
```

### 8.2 대화형(L0) 파일 저장 플로우 — 변경 없음

```
AgentRunner.run(...)            # bypass_approvals=False 기본
  │
  ▼
[루프] 각 iteration:
  ├─ model.chat() → [ACT]
  ├─ _save_file_blocks(session, act_text)
  │    └─ response_parser.parse_and_save(
  │         act_text,
  │         auto_overwrite=False       ← 그대로 False
  │       )
  │         └─ file_path.exists() == True
  │              └─ auto_overwrite=False
  │                  ├─ print("⚠️  파일이 이미 존재합니다: src/foo.py")
  │                  └─ input("덮어쓰시겠습니까? (y/N): ")
```

---

## 9. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | 사용자가 Bypass 모드에서 덮어쓴 파일을 복구하려면 외부 VCS(git) 에 의존 | 구현 범위 외 — FSD v1.0.083 의 "실행 전 git commit 백업" 원칙 준수 |
| 2 | 세 Assistant 의 `_extract_and_save_files()` 는 에이전트 루프 외에서도 `response_parser.parse_and_save()` 를 호출한다 — 키워드 인자 기본값 False 로만 호환 확보 | keyword-only 인자로 정의 → 위치 인자 호출부 시그니처 무변경 |
| 3 | `parse_and_save()` 의 덮어쓰기 분기 내부에 `input()` 호출이 있어 단위 테스트가 stdin mocking 필요 | `unittest.mock.patch("builtins.input")` 로 커버 (T-103-02/03/07) |
| 4 | `auto_overwrite=True` 상태에서 `file_manager.write_file()` 이 실패하면 "덮어쓰기 시도했으나 실패" 라는 상태가 되지만, Bypass 모드 특성상 사용자가 즉시 개입할 수 없음 | ActionResult(success=False) 로 집계되고, 연속되면 FSD v1.0.100 의 S3 정체 탐지가 종료 처리 |
| 5 | 현재 `ResponseParser` 는 파서 내부에서 직접 `print()` / `input()` 을 호출한다 (UI 계층 분리 부재). 본 FSD 는 이 구조를 바꾸지 않음 | 차후 리팩토링(UI 콜백 주입) 은 별도 FSD 로 검토 |
| 6 | `AGENT_BYPASS_MAX_FILE_OVERWRITE` 와 같은 한도는 도입하지 않음 | 4.2 에서 제안 — 실사용 데이터 후 재검토 |

---

## 10. 후속 작업

| 단계 | 내용 | 비고 |
|---|---|---|
| 1 | Bypass 중 파일 덮어쓰기 한도(`AGENT_BYPASS_MAX_FILE_OVERWRITE`) | 4.2 — 별도 FSD |
| 2 | Bypass 진입 시 Git Dirty 상태 사전 경고 | 4.3 — FSD v1.0.100 확장으로 통합 검토 |
| 3 | 자동 `.bak` 백업 옵션 (`AGENT_BYPASS_AUTO_BACKUP`) | 4.1 — 별도 FSD |
| 4 | `ResponseParser` UI 콜백 분리 리팩토링 (`print`/`input` 의존 제거) | 이슈#5 — 별도 FSD |

---

## 11. 승인

- [x] 설계 검토 (2026-04-23)
- [x] [src/response_parser.py](src/response_parser.py) 수정 및 단위 테스트 통과 (T-103-01 ~ T-103-06) — 6/6 PASSED
- [x] [src/agent_runner.py](src/agent_runner.py) `_save_file_blocks` / `_execute_actions` 수정 및 통합 테스트 통과 (T-103-07 ~ T-103-10) — 4/4 PASSED
- [x] 세 Assistant(`claude` / `gemini` / `genai`) 의 `_extract_and_save_files()` 대화형 동작 무변경 확인 — keyword-only 기본값 False 유지, 기존 81개 테스트 전체 통과
- [ ] `/agents -ba` 시나리오 E2E 수동 확인 (기존 파일 수정 목표)
- [ ] Resume 세션에서 overwrite 프롬프트 재출력 확인
- [ ] [docs/specs/releases/RELEASE_v1.0.103_agents-bypass-file-overwrite.md](docs/specs/releases/RELEASE_v1.0.103_agents-bypass-file-overwrite.md) 작성
