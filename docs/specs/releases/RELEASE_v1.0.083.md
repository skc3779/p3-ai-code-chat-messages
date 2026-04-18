# RELEASE v1.0.083

## 1. 개요

* **버전**: v1.0.083
* **일자**: 2026-04-18
* **목적**: `/agents` 자율 에이전트 루프 (Vertex AI Gemini) 도입 — CoT / ReAct / Self-Correction 기반 Reason → Act → Observe → Refine 사이클
* **관련 FSD**: [FSD v1.0.083](../requirements/FSD_v1.0.083_agents-autonomous-loop.md)
* **적용 범위 (1단계)**: `gemini-ai-chat-code.py` 전용. Claude / GenAI 확장은 후속 FSD(v1.0.085)에서 처리.

---

## 2. 주요 변경 사항

### 2.1 신규 모듈 — `src/agent_runner.py`

자율 에이전트 루프 실행기. Provider 독립적으로 설계되어 `assistant.chat()` / `conversation_history` / `system_prompt` 인터페이스만 있으면 재사용 가능하다.

| 구성 요소 | 설명 |
|---|---|
| `AgentStopReason` (Enum) | `DONE` / `MAX_ITERATIONS` / `USER_STOP` / `USER_ABORT_ON_ERROR` / `FATAL_ERROR` |
| `ActionResult` (dataclass) | 액션 1건의 실행 결과 (`kind`, `target`, `success`, `detail`) |
| `IterationRecord` (dataclass) | 한 iteration 의 Reason/Act/Observe + 액션 결과 + user_feedback |
| `AgentSession` (dataclass) | 목표·계획·반복 기록·격리 히스토리·세션 자동승인 플래그 집계 |
| `AgentRunner` (class) | 루프 실행기 — PLAN → Iterate → Self-Correct → DONE 관리 |

**핵심 플로우**

1. `<pattern>` 지정 시 `FilePatternMatcher` 로 파일 필터링 → 0개 매칭이면 즉시 중단
2. `ContextBuilder.build_context(file_patterns, include_tree=True)` 로 `[FILE_CONTEXT]` 구성 (PLAN 호출 1회에만 전체 본문, 이후 iteration 은 `[FILE_CONTEXT_REF]` 요약)
3. **Step 0**: PLAN (CoT) 수립 — AI 에게 번호 매긴 목록 요구
4. **Step 1..N**: `[REASON] / [ACT] / [OBSERVE]` 블록 파싱 → 액션 실행 → 실제 Observe 합성 → `[AGENT_DONE]` 감지
5. 실패 시 **Self-Correction** 최대 3회 재시도 (`AGENT_SELF_CORRECT_MAX`)
6. iteration 종료 시 **턴 사이 프롬프트** `[c]ontinue / [f]eedback / [s]top`
7. `agent_history` 길이가 `AGENT_COMPACT_AFTER` 초과 시 AI 압축 요약
8. 루프 종료 시 메인 `conversation_history` 에 요약 1쌍(user+model) 만 append (격리성 보장)

**액션 디스패치**
- ` ```filename:<경로>` 블록 → `ResponseParser.parse_and_save()` 로 자동 저장
- ` ```python` / ` ```bash` / ` ```javascript` 블록 → 전용 `CodeExecutor` (AGENT_CODE_TIMEOUT 반영)로 실행
- `$ <cmd>` 라인 → `TerminalExecutor` 로 실행. `DANGEROUS_COMMANDS` 포함 시 `[y/N/A]` 단건 승인 + 세션 자동 승인

### 2.2 엔트리 포인트 추가 — `gemini-ai-chat-code.py`

`/auto_context` 분기 뒤에 `/agents [pattern | [p1, p2, ...] | stop]` 분기 신규 추가 (`/context` 와 동일한 패턴 파서 재사용, 항상 멀티라인 목표 수집).

**사용 예시**

| 입력 | 동작 |
|---|---|
| `/agents` | 패턴 없음 → 멀티라인 목표 수집 → 순수 목표 기반 루프 |
| `/agents src/*.py` | 단일 패턴 → `[FILE_CONTEXT]` 주입 |
| `/agents src/*.py tests/*.py` | 공백 구분 다중 패턴 |
| `/agents [src/*.py, docs/*.md]` | 리스트 형식 다중 패턴 |
| `/agents stop` | 안내 메시지만 출력 (실행 중 중단은 Ctrl+C) |

### 2.3 명령 레지스트리 등록 — `src/command_registry.py`

`CommandInfo('/agents', ...)` 를 `/auto_context` 뒤에 추가하여 `/help` 와 자동완성에 노출.

### 2.4 환경변수 5종 추가 — `.env.example`

```env
# === 자율 에이전트 (/agents) — FSD v1.0.083 ===
AGENT_MAX_ITERATIONS=10
AGENT_SELF_CORRECT_MAX=3
AGENT_COMPACT_AFTER=5
AGENT_CODE_TIMEOUT=30
AGENT_DONE_TOKEN=[AGENT_DONE]
```

### 2.5 패키지 re-export — `src/__init__.py`

`AgentRunner`, `AgentSession`, `AgentStopReason` 을 `from src import …` 형태로 노출.

---

## 3. 영향 범위

| 파일 | 변경 유형 | 주요 내용 |
|---|---|---|
| `src/agent_runner.py` | **신규** | `AgentRunner` + 4개 데이터 구조체 |
| `gemini-ai-chat-code.py` | 수정 | `/agents` 분기 추가 (약 45줄, `/auto_context` 뒤) |
| `src/command_registry.py` | 수정 | `CommandInfo('/agents', ...)` 1건 추가 |
| `.env.example` | 수정 | `AGENT_*` 5개 환경변수 추가 |
| `src/__init__.py` | 수정 | `AgentRunner`/`AgentSession`/`AgentStopReason` re-export |
| `claude-ai-chat-code.py` | 변경 없음 | 2단계(FSD v1.0.085)에서 추가 |
| `gen-ai-chat-code.py` | 변경 없음 | 2단계(FSD v1.0.085)에서 추가 |

---

## 4. 호환성 / 설계 주의 사항

- **히스토리 격리**: 에이전트 루프는 `assistant.conversation_history` 와 `system_prompt` 를 임시 교체했다가 루프 종료 시 원복한다. CLI 특성상 재진입은 발생하지 않지만 동시 호출에는 안전하지 않다.
- **메인 히스토리 오염 방지**: 루프 내 Reason/Act/Observe 세부는 메인 `conversation_history` 에 남지 않고, 요약 1쌍(user+model) 만 append 된다.
- **`CodeExecutor` 분리**: `assistant.code_executor` (기본 30초) 는 건드리지 않고, `AGENT_CODE_TIMEOUT` 값을 반영한 **에이전트 전용 인스턴스** 를 `AgentRunner.__init__` 에서 생성한다.
- **`/agents stop` 의 의미**: 루프 실행 중 메인 `while True` 가 블로킹이므로 실제 중단은 `Ctrl+C` 로 처리된다. `/agents stop` 은 루프가 끝난 뒤 잘못 입력된 경우의 안내 메시지 전용이다.
- **위험 명령 승인 세션화**: `$ rm ...` 등 `TerminalExecutor.DANGEROUS_COMMANDS` 에 해당하는 명령은 매 실행마다 `[y/N/A]` 프롬프트. `A` 선택 시 현재 에이전트 세션 내에 한정해 자동 승인.
- **토큰 관리**: `AGENT_COMPACT_AFTER=5` 기준으로 `agent_history` 를 AI 압축 요약. 압축 자체도 토큰을 쓰므로 값은 보수적.
- **파일 저장 자동 덮어쓰기**: ` ```filename:` 블록은 확인 없이 저장된다 (기존 `/auto_context` 와 동일). 중요 파일은 실행 전 `git commit` 권장.

---

## 5. 검증 내역

| # | 시나리오 | 결과 |
|---|---|:----:|
| 1 | `src/agent_runner.py` Python AST 파싱 | ✅ |
| 2 | `gemini-ai-chat-code.py` Python AST 파싱 | ✅ |
| 3 | `src/command_registry.py` Python AST 파싱 | ✅ |
| 4 | `src/__init__.py` Python AST 파싱 | ✅ |
| 5 | `from src.agent_runner import AgentRunner, AgentSession, AgentStopReason, IterationRecord, ActionResult` 임포트 | ✅ |
| 6 | `/agents stop` — 루프 외부 안내 메시지 | ✅ (엔트리 포인트 코드 확인) |
| 7 | `/agents [src/*.py` 등 닫히지 않은 대괄호 → 오류 안내 | ✅ (패턴 파서 확인) |
| 8 | `CommandRegistry` 에 `/agents` 노출 (`/help` · 자동완성) | ✅ |

실제 AI 호출이 수반되는 T-02~T-14/T-16~T-22 시나리오(자율 루프 동작, Self-Correction, 피드백 주입, `<pattern>` 컨텍스트 주입 등)는 런타임 검증 대상이다.

---

## 6. 후속 작업

- **FSD v1.0.085 (확장)**: `claude-ai-chat-code.py` / `gen-ai-chat-code.py` 에 동일 `/agents` 분기 복제 및 공용 핸들러 추출
- **테스트 파일**: `tests/test_agent_runner.py` — FSD §8 T-01~T-22 중 순수 로직 테스트(파싱, Self-Correct 판정, 히스토리 격리, 요약 append 등)
- **후속 FSD 후보**: 세션 상태 JSON 직렬화 + `/agents resume`, 비동기 `/agents stop` (루프 중 입력 수신), Gemini `functionDeclarations` 기반 구조화 Tool Calling
