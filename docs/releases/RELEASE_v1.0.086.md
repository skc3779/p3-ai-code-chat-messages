# RELEASE v1.0.086

## 1. 개요

* **버전**: v1.0.086
* **일자**: 2026-04-18
* **목적**: 에이전트 세션 JSON 직렬화/역직렬화 및 `/agents resume` 로 중단된 에이전트 루프 재개 기능 도입
* **관련 FSD**: [FSD v1.0.086](../requirements/FSD_v1.0.086_agents-session-serialization-resume.md)

---

## 2. 주요 변경 사항

### 2.1 [P1] 신규 모듈: `src/agent_session_store.py`

`AgentSessionStore` 클래스를 신규 생성하여 에이전트 세션의 JSON 직렬화/역직렬화 및 파일 관리 기능을 구현하였습니다.

| 기능 | 메서드 | 설명 |
|------|--------|------|
| 직렬화 | `_serialize()` | `dataclasses.asdict()` + 커스텀 `_AgentSessionEncoder`로 `AgentStopReason` Enum 처리 |
| 역직렬화 | `_deserialize()` | `IterationRecord`, `ActionResult` 중첩 dataclass 재구성, Enum/Optional 복원 |
| 저장 | `save()` | 세션 JSON 파일 생성 + `latest.json` 동시 갱신 + FIFO 정리 |
| 로드 | `load(filename)` | 지정 파일명으로 세션 복원 |
| 최근 로드 | `load_latest()` | `latest.json` 에서 최근 세션 복원 |
| 목록 조회 | `list_sessions()` | 저장된 세션 목록 (goal, stop_reason, iterations, mtime) 반환 |
| 정리 | `_cleanup_old()` | `AGENT_MAX_SAVED_SESSIONS` 초과 시 가장 오래된 세션 자동 삭제 (FIFO) |
| 파일 검증 | `validate_matched_files()` | Resume 시 `matched_files` 존재 여부 확인 → 누락 파일 목록 반환 |
| 목록 출력 | `print_session_list()` | `/agents list` 용 터미널 포맷 출력 |

**직렬화 전략 (방안 A 채택):**
- `dataclasses.asdict()` 로 중첩 dataclass → dict 변환
- `AgentStopReason` Enum 은 커스텀 `json.JSONEncoder` 로 `.value` 변환
- `_workspace` 메타 필드 추가 (Resume 시 workspace 경로 비교용)

### 2.2 [P2] `AgentRunner.run()` — `resume_session` 파라미터 지원

`run()` 메서드에 `resume_session: Optional[AgentSession]` 파라미터를 추가하여 중단된 세션에서 루프를 재개합니다.

```python
def run(self, goal="", file_patterns=None, resume_session=None):
    if resume_session is not None:
        session = resume_session
        session.stop_reason = None          # 이전 종료 사유 초기화 (P5)
        session.auto_approve_dangerous_shell = False  # 보안 리셋 (이슈#5)
        session.auto_approve_file_mutation = False
        start_iteration = len(session.iterations) + 1
    else:
        session = AgentSession(goal=goal, ...)
        start_iteration = 1
```

**Resume 시 동작:**
1. PLAN 단계 건너뜀 (이전 `session.plan` 출력만 수행)
2. 이전 iteration 수 + 1 부터 루프 재개
3. `matched_files` 누락 파일 경고 출력 (P4, 방안 A)
4. `auto_approve_*` 플래그 `False` 리셋 (보안 정책, 이슈#5)

### 2.3 [P3] 자동 저장 로직 (`_auto_save()`)

`AgentRunner`에 `_auto_save()` 메서드를 추가하여 다음 시점에 세션을 디스크에 저장합니다:

| 저장 시점 | 구현 |
|-----------|------|
| 루프 정상 종료 | `run()` 반환 직전 `_auto_save()` 호출 |
| `KeyboardInterrupt` (Ctrl+C) | `except KeyboardInterrupt:` 블록 내 `_auto_save()` 호출 |
| 중간 저장 | `AGENT_AUTO_SAVE_INTERVAL` (기본 3) iteration 마다 `_auto_save()` 호출 |

### 2.4 [P4] `/agents resume`, `/agents list` 서브커맨드

`src/agents_command.py` 의 `handle_agents_command()` 에 `resume`, `list` 분기를 추가하였습니다.

| 명령 | 동작 |
|------|------|
| `/agents resume` | 가장 최근 `latest.json` 세션 복원 후 루프 재개 |
| `/agents resume <filename>` | 지정 세션 파일로 복원 |
| `/agents list` | 저장된 세션 목록 (목표, 상태, iteration 수, 날짜) 출력 |

### 2.5 `/agents resume`, `/agents list` 도움말 추가

`src/command_registry.py` 에 `/agents resume`, `/agents list` 명령어 도움말을 추가하였습니다.

### 2.6 환경변수 추가

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `AGENT_MAX_SAVED_SESSIONS` | `5` | 최대 저장 세션 수 (FIFO 방식 정리) |
| `AGENT_AUTO_SAVE_INTERVAL` | `3` | N iteration 마다 중간 저장 (0 = 비활성) |

### 2.7 `.gitignore` / `.env.example` 업데이트

- `.gitignore` 에 `.agent_sessions/` 추가 → 세션 파일이 git 에 포함되지 않음
- `.env.example` 에 `AGENT_MAX_SAVED_SESSIONS`, `AGENT_AUTO_SAVE_INTERVAL` 추가

---

## 3. 영향 범위

| 파일 | 변경 유형 | 주요 내용 |
|------|-----------|-----------|
| `src/agent_session_store.py` | **신규** | 세션 직렬화/역직렬화, 파일 관리, FIFO 정리 |
| `src/agent_runner.py` | 수정 | `resume_session` 파라미터, `_auto_save()` 메서드, 중간 저장 로직 |
| `src/agents_command.py` | 수정 | `resume`, `list` 서브커맨드 분기 추가 |
| `src/command_registry.py` | 수정 | `/agents resume`, `/agents list` 도움말 등록 |
| `.gitignore` | 수정 | `.agent_sessions/` 추가 |
| `.env.example` | 수정 | `AGENT_MAX_SAVED_SESSIONS`, `AGENT_AUTO_SAVE_INTERVAL` 추가 |
| `tests/test_agent_session_store.py` | **신규** | 29개 단위 테스트 (T-086-01 ~ T-086-12 커버) |

---

## 4. 세션 파일 구조

- **저장 위치**: `{workspace}/.agent_sessions/`
- **파일명**: `agent_{YYYYMMDD}_{HHMMSS}_{goal_slug}.json`
- **최근 세션**: `latest.json` (가장 최근 저장 세션의 복사본)
- **보관 한도**: `AGENT_MAX_SAVED_SESSIONS` (기본 5, FIFO 정리)

```
.agent_sessions/
├── agent_20260418_143045_python_테트리스_작성.json
├── agent_20260418_150012_리팩토링.json
└── latest.json
```

---

## 5. 호환성 주의 사항

- **자동 저장**: 에이전트 루프 종료 시 항상 세션이 저장됩니다. 저장 공간이 제한적인 환경에서는 `AGENT_MAX_SAVED_SESSIONS=1` 로 설정하세요.
- **Resume 보안 정책**: Resume 시 `auto_approve_dangerous_shell`, `auto_approve_file_mutation` 플래그는 `False` 로 리셋됩니다. 이전 세션에서 "Always" 승인한 상태가 복원되지 않습니다.
- **Workspace 변경**: 다른 디렉토리에서 Resume 하면 `matched_files` 경로가 무효화될 수 있습니다. 경고 메시지가 출력되지만 루프는 속행됩니다.

---

## 6. 검증 내역

| # | 시나리오 (FSD 테스트 ID) | 테스트 메서드 | 결과 |
|---|-------------------------|--------------|:----:|
| 1 | T-086-01: 세션 파일 생성 확인 | `TestSaveLoad::test_save_creates_file` | ✅ |
| 2 | T-086-01: latest.json 갱신 확인 | `TestSaveLoad::test_save_creates_latest` | ✅ |
| 3 | T-086-03: load_latest() 최근 세션 복원 | `TestSaveLoad::test_load_latest_returns_last_saved` | ✅ |
| 4 | T-086-04: 지정 파일명 세션 복원 | `TestSaveLoad::test_load_by_filename` | ✅ |
| 5 | T-086-05: 세션 목록 표시 | `TestListSessions::test_list_shows_saved_sessions` | ✅ |
| 6 | T-086-05: 목록 필수 필드 확인 | `TestListSessions::test_list_entry_fields` | ✅ |
| 7 | T-086-05: 최신 세션 먼저 정렬 | `TestListSessions::test_list_sorted_by_mtime_desc` | ✅ |
| 8 | T-086-06: 최대 세션 수 초과 정리 | `TestCleanup::test_cleanup_keeps_max_sessions` | ✅ |
| 9 | T-086-06: 가장 오래된 세션 삭제 | `TestCleanup::test_cleanup_removes_oldest` | ✅ |
| 10 | T-086-07: 직렬화 → 역직렬화 왕복 | `TestSerialization::test_roundtrip_basic` | ✅ |
| 11 | T-086-08: IterationRecord/ActionResult 보존 | `TestSerialization::test_iteration_records_preserved` | ✅ |
| 12 | T-086-09: AgentStopReason Enum 왕복 | `TestSerialization::test_enum_roundtrip` | ✅ |
| 13 | T-086-10: matched_files 누락 감지 | `TestValidateMatchedFiles::test_missing_files_detected` | ✅ |
| 14 | T-086-11: stop_reason 보존 확인 | `TestResumeStopReasonReset::test_stop_reason_reset_on_resume` | ✅ |
| 15 | T-086-11: Resume iteration 수 보존 | `TestResumeStopReasonReset::test_resume_iteration_count` | ✅ |
| 16 | T-086-12: AGENT_AUTO_SAVE_INTERVAL 환경변수 | `TestAutoSaveInterval::test_env_var_respected` | ✅ |
| 17 | T-086-12: AGENT_MAX_SAVED_SESSIONS 환경변수 | `TestAutoSaveInterval::test_max_sessions_env_var` | ✅ |
| 18 | 파일명 형식 검증 | `TestFilenaming::test_filename_format` | ✅ |
| 19 | 파일명 슬러그 영숫자 검증 | `TestFilenaming::test_filename_slug_alphanumeric` | ✅ |
| 20 | _workspace 메타 필드 저장 | `TestFilenaming::test_workspace_stored_in_json` | ✅ |
| — | **총 29개 테스트** | | **✅ ALL PASSED** |

---

## 7. 향후 계획

- **FSD v1.0.087**: 비동기 `/agents stop` — 루프 실행 중 사용자 입력 수신
- 세션 파일 암호화 (`AGENT_SESSION_ENCRYPT=true`) — 향후 검토
- `matched_files` 파일 해시 기반 변경 감지 (방안 B) — 향후 고도화
