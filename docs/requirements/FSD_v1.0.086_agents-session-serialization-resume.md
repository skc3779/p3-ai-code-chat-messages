# FSD v1.0.086 — 세션 상태 JSON 직렬화 + `/agents resume`

| 항목 | 내용 |
|---|---|
| 문서 버전 | v1.0.086 |
| 작성일 | 2026-04-18 |
| 상태 | 📝 사전 분석 (구현 대기) |
| 선행 문서 | FSD v1.0.083 (`/agents` 자율 에이전트 루프), FSD v1.0.085 (멀티 Provider 복제) |
| 대상 파일 | `src/agent_runner.py`, `src/agent_session_store.py` (**신규**), 각 엔트리 포인트 |
| 관련 모듈 | `src/agent_runner.py` (기존 `AgentSession` 데이터클래스) |

---

## 1. 개요

### 1.1 목적

현재 `/agents` 루프가 중단되면 (`/agents stop`, `Ctrl+C`, `MAX_ITERATIONS` 도달) 세션 상태는 **메모리에서 폐기**된다. 본 FSD 는 에이전트 세션 전체를 JSON 으로 직렬화하여 디스크에 저장하고, `/agents resume` 명령으로 마지막 세션을 복원하여 중단된 지점부터 루프를 재개하는 기능을 도입한다.

### 1.2 범위

| 항목 | 포함 여부 |
|---|---|
| `AgentSession` JSON 직렬화/역직렬화 | ✅ |
| 자동 저장 (루프 종료 시 / 매 iteration 종료 시) | ✅ |
| `/agents resume` 명령어 | ✅ |
| `/agents list` (저장된 세션 목록) | ✅ (선택) |
| 다중 세션 관리 (세션 ID 지정 재개) | ✅ (선택) |
| 비동기 `/agents stop` | ❌ (FSD v1.0.087) |

---

## 2. 현황 분석

### 2.1 현재 `AgentSession` 구조 (agent_runner.py)

```python
@dataclass
class AgentSession:
    goal: str
    plan: str = ""
    file_patterns: List[str] = field(default_factory=list)
    matched_files: List[str] = field(default_factory=list)
    iterations: List[IterationRecord] = field(default_factory=list)
    agent_history: List[Dict[str, str]] = field(default_factory=list)
    auto_approve_dangerous_shell: bool = False
    auto_approve_file_mutation: bool = False
    stop_reason: Optional[AgentStopReason] = None
```

### 2.2 직렬화 대상 분석

| 필드 | 타입 | JSON 변환 가능 여부 | 비고 |
|---|---|---|---|
| `goal` | `str` | ✅ | |
| `plan` | `str` | ✅ | |
| `file_patterns` | `List[str]` | ✅ | |
| `matched_files` | `List[str]` | ✅ | |
| `iterations` | `List[IterationRecord]` | ⚠️ 중첩 dataclass | `IterationRecord` 내부의 `ActionResult` 까지 재귀 변환 필요 |
| `agent_history` | `List[Dict]` | ✅ | |
| `auto_approve_*` | `bool` | ✅ | |
| `stop_reason` | `AgentStopReason` (Enum) | ⚠️ Enum | `.value` 로 직렬화, 역직렬화 시 `AgentStopReason(value)` |

---

## 3. 문제점 사전 분석

### 3.1 🔴 [P1] 중첩 dataclass 직렬화

**문제:**
`AgentSession.iterations` 는 `List[IterationRecord]` 이며, `IterationRecord.actions` 는 `List[ActionResult]` 이다. Python `json.dumps()` 는 dataclass 를 자동으로 직렬화하지 못한다.

```python
@dataclass
class ActionResult:
    kind: str         # "file" | "code" | "shell"
    target: str
    success: bool
    detail: str = ""

@dataclass
class IterationRecord:
    idx: int
    reason_text: str
    act_text: str
    actions: List[ActionResult] = field(default_factory=list)
    observe_text: str = ""
    user_feedback: Optional[str] = None
```

**해결 방안:**

| 방안 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. `dataclasses.asdict()` 사용** | `asdict(session)` 으로 전체 세션을 중첩 dict 로 변환 후 Enum 만 수동 처리 | 표준 라이브러리, 코드 최소화 | Enum 처리를 위한 custom encoder 필요 |
| **B. Pydantic 모델 전환** | 모든 dataclass 를 Pydantic `BaseModel` 로 변경 | `.model_dump_json()` / `.model_validate_json()` 제공 | 새 의존성 추가 (pydantic), 기존 코드 대규모 변경 |
| **C. 수동 `to_dict()` / `from_dict()` 메서드** | 각 dataclass 에 `to_dict()`, `@classmethod from_dict()` 추가 | 의존성 없음, 세밀한 제어 | 보일러플레이트 코드 증가 |

**권장: 방안 A** — 표준 `dataclasses.asdict()` + 커스텀 JSON encoder 로 Enum 처리.

```python
import dataclasses
import json

class AgentSessionEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, AgentStopReason):
            return o.value
        return super().default(o)

def serialize_session(session: AgentSession) -> str:
    data = dataclasses.asdict(session)
    return json.dumps(data, cls=AgentSessionEncoder, ensure_ascii=False, indent=2)
```

---

### 3.2 🔴 [P2] 역직렬화 — Enum / Optional 복원

**문제:**
`json.loads()` 로 읽은 dict 를 `AgentSession` 으로 복원할 때:
- `stop_reason` 이 `"done"` (문자열) → `AgentStopReason("done")` 으로 변환 필요
- `iterations` 내부의 각 항목을 `IterationRecord` 로, `actions` 를 `ActionResult` 로 재구성 필요
- `user_feedback` 이 `None` 인 경우 JSON 에서는 `null` 로 저장됨 — 자동 복원됨

**해결 방안:**

```python
@staticmethod
def deserialize_session(json_str: str) -> AgentSession:
    data = json.loads(json_str)
    # stop_reason 복원
    sr = data.get("stop_reason")
    data["stop_reason"] = AgentStopReason(sr) if sr else None
    # iterations 복원
    iters = []
    for it_data in data.get("iterations", []):
        actions = [ActionResult(**a) for a in it_data.pop("actions", [])]
        iters.append(IterationRecord(**it_data, actions=actions))
    data["iterations"] = iters
    return AgentSession(**data)
```

---

### 3.3 🟡 [P3] `agent_history` 의 콘텐츠 크기

**문제:**
`agent_history` 는 매 iteration 마다 user + model 메시지가 누적된다. 10 iteration 이면 20 개 메시지, 각각 수 KB ~ 수십 KB. 직렬화 시 JSON 파일 크기가 수백 KB ~ 수 MB 에 달할 수 있다.

또한 `AGENT_COMPACT_AFTER` 에 의해 압축된 히스토리는 원본이 사라진 상태이므로, **resume 시 이전 맥락이 요약본만으로 구성**된다.

**영향:**
- 디스크 사용량 → 관리 가능 (`.agent_sessions/` 폴더에 최대 N 개 유지)
- 압축 후 resume → AI 가 요약만으로도 맥락을 이해할 수 있어야 함

**해결 방안:**
1. 최대 세션 보관 수 제한 (env `AGENT_MAX_SAVED_SESSIONS=5`)
2. 세션 파일명에 타임스탬프 포함하여 FIFO 관리
3. 큰 agent_history 는 직렬화 시 최근 N 개만 저장하고 나머지는 요약으로 대체

---

### 3.4 🟡 [P4] Resume 시 `assistant` 상태 동기화

**문제:**
`AgentRunner.run()` 진입 시 `assistant` 의 현재 상태(메인 `conversation_history`, `system_prompt`)가 있다. Resume 은 **이전 세션의 agent_history 를 복원**하고 이전 iteration 지점부터 다시 시작해야 한다.

그러나:
1. `assistant.conversation_history` 는 **Resume 시점의 별개 메인 히스토리** 일 수 있음 (이전 세션 이후에 다른 대화를 했을 수 있음)
2. 에이전트가 저장한 파일들이 Resume 시점에 이미 수정/삭제되었을 수 있음 — 에이전트는 이를 인지하지 못함
3. `matched_files` 가 가리키는 파일이 Resume 시에는 존재하지 않을 수 있음

**해결 방안:**

| 방안 | 설명 |
|---|---|
| **A. 컨텍스트 무결성 경고만 표시** | Resume 시 matched_files 의 존재 여부를 확인하고 변경/삭제된 파일은 경고만 출력. 에이전트 루프는 그대로 속행. |
| **B. 파일 해시 검증** | 저장 시 matched_files 의 해시를 기록하고, Resume 시 비교하여 변경된 파일을 AI 에게 알림 |

**권장: 방안 A** — 1단계에서는 단순 경고. 향후 방안 B 로 고도화.

---

### 3.5 🟡 [P5] Resume 진입점 — 루프 재개 위치

**문제:**
현재 `run()` 메서드는 항상 Step 0 (PLAN) 부터 시작한다. Resume 시에는:
1. PLAN 은 이미 수립됨 (`session.plan` 에 저장)
2. N 번째 iteration 까지 완료됨 (`session.iterations` 에 기록)
3. N+1 번째부터 재개해야 함

**해결 방안:**

```python
def run(self, goal=None, file_patterns=None, resume_session=None):
    if resume_session:
        session = resume_session
        start_iteration = len(session.iterations) + 1
        # PLAN 단계 건너뜀
    else:
        session = AgentSession(goal=goal, ...)
        # PLAN 수립
        start_iteration = 1

    for i in range(start_iteration, self.max_iterations + 1):
        ...
```

**주의:** `resume_session` 을 사용할 때 `session.stop_reason` 을 초기화 (`None`) 해야 루프가 정상 진행됨.

---

### 3.6 🟢 [P6] 세션 파일 저장 위치 및 네이밍

**문제:**
세션 파일을 어디에 저장할 것인가?

**해결 방안:**
- 저장 위치: `{workspace}/.agent_sessions/` (`.gitignore` 에 추가)
- 파일명: `agent_{timestamp}_{goal_slug}.json`
    - `timestamp`: `%Y%m%d_%H%M%S`
    - `goal_slug`: 목표의 앞 30자를 slug 화 (영숫자 + 밑줄만)
- 최근 세션 심볼: `latest.json` → 가장 최근 세션에 대한 복사본 또는 심볼릭 링크

---

### 3.7 🟢 [P7] `/agents resume` 명령 UX

**사용 형식:**

| 입력 | 동작 |
|---|---|
| `/agents resume` | 가장 최근 저장된 세션 복원 |
| `/agents resume <filename>` | 지정 세션 파일 복원 |
| `/agents list` | 저장된 세션 목록 표시 (목표, 상태, iteration 수, 날짜) |

**Resume 시 출력 예시:**

```
> /agents resume
📂 세션 복원: agent_20260418_123045_python_테트리스.json
  목표: python으로 테트리스 작성해줘
  상태: user_stop (3/10 iterations 완료)
  저장된 파일: tetris/main.py, tetris/piece.py

🤖 에이전트 재개 — iteration 4 부터 계속합니다.

━━━ Iteration 4/10 ━━━
...
```

---

### 3.8 🟡 [P8] 자동 저장 시점 결정

**문제:**
세션을 언제 자동으로 디스크에 저장할 것인가?

| 시점 | 장점 | 단점 |
|---|---|---|
| **매 iteration 종료 시** | 최소 데이터 손실 | I/O 빈번, 큰 세션은 매번 수십~수백 KB 쓰기 |
| **루프 종료 시에만** | I/O 최소화 | `Ctrl+C` / 예외 시 저장 안 됨 |
| **루프 종료 + Ctrl+C 핸들러** | 강제 종료에도 저장 | `KeyboardInterrupt` catch 위치가 중요 |

**권장:** `루프 종료 + KeyboardInterrupt catch 시` — 현재 구현에서 이미 `except KeyboardInterrupt:` 에서 세션을 안전하게 종료하므로 여기에 저장 로직 추가.

추가로 `AGENT_AUTO_SAVE_INTERVAL` (기본 3) — N iteration 마다 중간 저장.

---

### 3.9 🟢 [P9] 저장 시 보안/개인정보

**문제:**
`agent_history` 에는 사용자의 코드, 파일 내용, 쉘 명령 결과가 포함될 수 있다. JSON 으로 평문 저장 시 민감 정보 노출 우려.

**해결 방안:**
1. `.agent_sessions/` 를 `.gitignore` 에 추가 (필수)
2. 선택적 암호화 (`AGENT_SESSION_ENCRYPT=true`) — 향후 검토
3. GenAI 의 `SensitiveWordFilter` 를 직렬화 시에도 적용 — 과도, 비권장

**1단계:** `.gitignore` 추가만 수행. 보안 경고 메시지를 `/agents list` 출력에 포함.

---

## 4. 구현 사양 (초안)

### 4.1 신규 모듈: `src/agent_session_store.py`

```python
"""
AgentSessionStore — 에이전트 세션 JSON 직렬화/역직렬화 및 파일 관리
"""

import json
import dataclasses
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .agent_runner import (
    AgentSession, AgentStopReason,
    IterationRecord, ActionResult
)


class AgentSessionStore:
    SESSIONS_DIR = ".agent_sessions"
    MAX_SESSIONS = 5  # 기본값, env AGENT_MAX_SAVED_SESSIONS 로 오버라이드

    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.sessions_dir = self.workspace_dir / self.SESSIONS_DIR
        self.max_sessions = int(os.getenv("AGENT_MAX_SAVED_SESSIONS", "5"))

    def save(self, session: AgentSession) -> Path: ...
    def load(self, filename: str) -> Optional[AgentSession]: ...
    def load_latest(self) -> Optional[AgentSession]: ...
    def list_sessions(self) -> List[Dict]: ...
    def _cleanup_old(self) -> None: ...
    def _serialize(self, session: AgentSession) -> str: ...
    def _deserialize(self, json_str: str) -> AgentSession: ...
    def _make_filename(self, session: AgentSession) -> str: ...
```

### 4.2 환경변수

| 변수명 | 기본값 | 설명 |
|---|---|---|
| `AGENT_MAX_SAVED_SESSIONS` | `5` | 최대 저장 세션 수 (FIFO) |
| `AGENT_AUTO_SAVE_INTERVAL` | `3` | N iteration 마다 중간 저장 (0=비활성) |

### 4.3 `.env.example` 추가

```env
# === 에이전트 세션 저장 ===
AGENT_MAX_SAVED_SESSIONS=5
AGENT_AUTO_SAVE_INTERVAL=3
```

### 4.4 `.gitignore` 추가

```
.agent_sessions/
```

---

## 5. 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| T-086-01 | 에이전트 정상 완료 (`AGENT_DONE`) 후 세션 파일 존재 확인 | `.agent_sessions/agent_*.json` 생성됨 |
| T-086-02 | `Ctrl+C` 중단 후 세션 파일 존재 확인 | 중단 시점까지의 세션 저장됨 |
| T-086-03 | `/agents resume` 로 최근 세션 복원 | 이전 PLAN 출력, 다음 iteration 부터 재개 |
| T-086-04 | `/agents resume <filename>` 로 지정 세션 복원 | 해당 세션 복원 |
| T-086-05 | `/agents list` 로 세션 목록 표시 | 목표, 상태, iteration 수, 날짜 출력 |
| T-086-06 | 저장 세션 수가 `AGENT_MAX_SAVED_SESSIONS` 초과 시 | 가장 오래된 세션 자동 삭제 |
| T-086-07 | 직렬화 → 역직렬화 왕복 정합성 | `session == deserialize(serialize(session))` |
| T-086-08 | `IterationRecord` 내 `ActionResult` 직렬화 검증 | `kind`, `target`, `success`, `detail` 모두 보존 |
| T-086-09 | `AgentStopReason` Enum 직렬화/역직렬화 | `"done"` ↔ `AgentStopReason.DONE` 왕복 |
| T-086-10 | Resume 시 `matched_files` 가 삭제된 경우 | 경고 출력, 루프 속행 |
| T-086-11 | Resume 시 `stop_reason` 초기화 확인 | `None` 으로 리셋되어 루프 정상 진행 |
| T-086-12 | `AGENT_AUTO_SAVE_INTERVAL=3` 일 때 3번째 iteration 후 중간 저장 확인 | 세션 파일 갱신됨 |

---

## 6. 파일 변경 예정 목록

| 파일 | 변경 유형 | 설명 |
|---|---|---|
| `src/agent_session_store.py` | **신규** | 세션 직렬화/역직렬화, 파일 관리 |
| `src/agent_runner.py` | 수정 | `run()` 에 `resume_session` 파라미터 추가, 자동 저장 로직 |
| 각 엔트리 포인트 (`gemini-`, `claude-`, `gen-ai-`) | 수정 | `/agents resume`, `/agents list` 분기 추가 |
| `src/agents_command.py` | 수정 (FSD v1.0.085 에서 생성 시) | `resume` / `list` 서브커맨드 추가 |
| `src/command_registry.py` | 수정 | `/agents resume`, `/agents list` 도움말 추가 |
| `.gitignore` | 수정 | `.agent_sessions/` 추가 |
| `.env.example` | 수정 | `AGENT_MAX_SAVED_SESSIONS`, `AGENT_AUTO_SAVE_INTERVAL` 추가 |

---

## 7. 이슈 및 제약

| # | 내용 | 대응 |
|---|---|---|
| 1 | `agent_history` 에 포함된 AI 응답이 매우 클 수 있다 (코드 전문 등). 직렬화 시 파일 크기가 수 MB 에 달할 수 있음 | `AGENT_MAX_SAVED_SESSIONS` 로 수량 제한 + 정기 정리 |
| 2 | Resume 시 workspace 가 변경되었으면 `matched_files` 경로가 무효화됨 | Resume 시 workspace 경로를 세션에 저장하고, 현재 workspace 와 비교. 다르면 경고 출력 |
| 3 | `dataclasses.asdict()` 는 `Optional` 필드가 `None` 이면 `null` 로 변환되어 역직렬화 시 자동 복원됨. 하지만 `default_factory=list` 필드가 빈 리스트일 때 JSON 에서 `[]` → `list()` 로 정상 복원됨 | 문제 없음, 별도 조치 불필요 |
| 4 | 동시에 여러 에이전트가 같은 workspace 에서 실행되면 세션 파일 충돌 가능 | CLI 특성상 동시 실행 없음. 파일명에 타임스탬프 포함으로 충돌 방지 |
| 5 | `auto_approve_dangerous_shell` / `auto_approve_file_mutation` 플래그를 Resume 시 직렬화/복원하면, 이전 세션의 자동 승인이 그대로 유지됨 | 보안 관점에서 Resume 시 이 플래그들은 `False` 로 리셋하는 것이 안전. 사양에 명시 |

---

## 8. 승인

- [ ] 사전 분석 검토 (2026-04-18)
- [ ] 직렬화 방안 확정 (방안 A/B/C)
- [ ] 구현
- [ ] 테스트
- [ ] 문서 반영
