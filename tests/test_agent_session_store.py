"""
테스트: AgentSessionStore (FSD v1.0.086)

T-086-01 ~ T-086-12 시나리오를 단위 테스트로 구현한다.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# src 패키지 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent_runner import (
    ActionResult,
    AgentSession,
    AgentStopReason,
    IterationRecord,
)
from src.agent_session_store import AgentSessionStore


# ─── 픽스처 ─────────────────────────────────────────────────────────────────

@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def store(workspace):
    return AgentSessionStore(str(workspace))


def _make_session(
    goal: str = "테스트 목표",
    stop_reason: AgentStopReason = AgentStopReason.DONE,
    n_iters: int = 2,
) -> AgentSession:
    iters = []
    for i in range(1, n_iters + 1):
        iters.append(IterationRecord(
            idx=i,
            reason_text=f"reason {i}",
            act_text=f"act {i}",
            actions=[
                ActionResult(kind="file", target=f"file{i}.py", success=True, detail="저장됨"),
                ActionResult(kind="code", target="python", success=False, detail="SyntaxError"),
            ],
            observe_text=f"observe {i}",
            user_feedback=None,
        ))
    s = AgentSession(
        goal=goal,
        plan="1. step one\n2. step two",
        file_patterns=["src/*.py"],
        matched_files=["src/main.py"],
        iterations=iters,
        agent_history=[{"role": "user", "content": "hi"}, {"role": "model", "content": "hello"}],
        auto_approve_dangerous_shell=False,
        auto_approve_file_mutation=False,
        stop_reason=stop_reason,
    )
    return s


# ─── T-086-07: 직렬화 → 역직렬화 왕복 정합성 ────────────────────────────────

class TestSerialization:
    def test_roundtrip_basic(self, store):
        """T-086-07: session == deserialize(serialize(session))"""
        original = _make_session()
        path = store.save(original)
        restored = store.load(path.name)

        assert restored is not None
        assert restored.goal == original.goal
        assert restored.plan == original.plan
        assert restored.file_patterns == original.file_patterns
        assert restored.matched_files == original.matched_files
        assert len(restored.iterations) == len(original.iterations)
        assert restored.agent_history == original.agent_history
        assert restored.auto_approve_dangerous_shell == original.auto_approve_dangerous_shell
        assert restored.stop_reason == original.stop_reason

    def test_iteration_records_preserved(self, store):
        """T-086-08: IterationRecord 내 ActionResult 직렬화 검증"""
        original = _make_session(n_iters=3)
        path = store.save(original)
        restored = store.load(path.name)

        for orig_it, rest_it in zip(original.iterations, restored.iterations):
            assert orig_it.idx == rest_it.idx
            assert orig_it.reason_text == rest_it.reason_text
            assert orig_it.act_text == rest_it.act_text
            assert orig_it.observe_text == rest_it.observe_text
            assert orig_it.user_feedback == rest_it.user_feedback
            for orig_a, rest_a in zip(orig_it.actions, rest_it.actions):
                assert orig_a.kind == rest_a.kind
                assert orig_a.target == rest_a.target
                assert orig_a.success == rest_a.success
                assert orig_a.detail == rest_a.detail

    def test_enum_roundtrip(self, store):
        """T-086-09: AgentStopReason Enum 직렬화/역직렬화"""
        for reason in AgentStopReason:
            s = _make_session(stop_reason=reason)
            path = store.save(s)
            r = store.load(path.name)
            assert r.stop_reason == reason

    def test_stop_reason_none(self, store):
        """stop_reason=None 일 때 null 으로 저장되고 None 으로 복원"""
        s = _make_session()
        s.stop_reason = None
        path = store.save(s)
        r = store.load(path.name)
        assert r.stop_reason is None

    def test_empty_iterations(self, store):
        """iterations 가 빈 리스트일 때 정상 직렬화"""
        s = _make_session(n_iters=0)
        path = store.save(s)
        r = store.load(path.name)
        assert r.iterations == []

    def test_user_feedback_none_preserved(self, store):
        """user_feedback=None 이 null 로 저장/복원"""
        s = _make_session(n_iters=1)
        s.iterations[0].user_feedback = None
        path = store.save(s)
        r = store.load(path.name)
        assert r.iterations[0].user_feedback is None

    def test_user_feedback_string_preserved(self, store):
        """user_feedback 문자열 보존"""
        s = _make_session(n_iters=1)
        s.iterations[0].user_feedback = "피드백 내용"
        path = store.save(s)
        r = store.load(path.name)
        assert r.iterations[0].user_feedback == "피드백 내용"


# ─── T-086-01: 세션 파일 생성 확인 ──────────────────────────────────────────

class TestSaveLoad:
    def test_save_creates_file(self, store, workspace):
        """T-086-01: 저장 후 .agent_sessions/agent_*.json 생성됨"""
        s = _make_session(stop_reason=AgentStopReason.DONE)
        path = store.save(s)
        assert path.exists()
        assert path.name.startswith("agent_")
        assert path.suffix == ".json"

    def test_save_creates_latest(self, store, workspace):
        """save() 호출 시 latest.json 도 갱신됨"""
        s = _make_session()
        store.save(s)
        assert (workspace / ".agent_sessions" / "latest.json").exists()

    def test_load_returns_none_for_missing(self, store):
        """존재하지 않는 파일 load 시 None 반환"""
        assert store.load("nonexistent.json") is None

    def test_load_latest_returns_none_when_empty(self, store):
        """세션 없을 때 load_latest() 는 None"""
        assert store.load_latest() is None

    def test_load_latest_returns_last_saved(self, store):
        """T-086-03: load_latest() 로 최근 저장 세션 복원"""
        s1 = _make_session(goal="첫 번째 목표")
        s2 = _make_session(goal="두 번째 목표")
        store.save(s1)
        store.save(s2)
        latest = store.load_latest()
        assert latest is not None
        assert latest.goal == "두 번째 목표"

    def test_load_by_filename(self, store):
        """T-086-04: 지정 파일명으로 세션 복원"""
        s = _make_session(goal="지정 세션 테스트")
        path = store.save(s)
        r = store.load(path.name)
        assert r is not None
        assert r.goal == "지정 세션 테스트"


# ─── T-086-05: 세션 목록 ────────────────────────────────────────────────────

class TestListSessions:
    def test_list_empty(self, store):
        """T-086-05: 세션 없을 때 빈 리스트"""
        assert store.list_sessions() == []

    def test_list_shows_saved_sessions(self, store):
        """T-086-05: 저장된 세션이 목록에 나타남"""
        store.save(_make_session(goal="목표 A", stop_reason=AgentStopReason.DONE))
        store.save(_make_session(goal="목표 B", stop_reason=AgentStopReason.USER_STOP))
        sessions = store.list_sessions()
        assert len(sessions) == 2
        goals = [s["goal"] for s in sessions]
        assert "목표 A" in goals
        assert "목표 B" in goals

    def test_list_entry_fields(self, store):
        """목록 항목에 필수 필드가 모두 존재"""
        store.save(_make_session())
        entries = store.list_sessions()
        assert len(entries) == 1
        e = entries[0]
        assert "filename" in e
        assert "goal" in e
        assert "stop_reason" in e
        assert "iterations" in e
        assert "mtime" in e

    def test_list_sorted_by_mtime_desc(self, store):
        """최신 세션이 먼저 나타남"""
        store.save(_make_session(goal="오래된 세션"))
        import time; time.sleep(0.05)
        store.save(_make_session(goal="최신 세션"))
        entries = store.list_sessions()
        assert entries[0]["goal"] == "최신 세션"


# ─── T-086-06: 최대 세션 수 초과 시 정리 ────────────────────────────────────

class TestCleanup:
    def test_cleanup_keeps_max_sessions(self, workspace):
        """T-086-06: AGENT_MAX_SAVED_SESSIONS 초과 시 오래된 세션 삭제"""
        store = AgentSessionStore(str(workspace))
        store.max_sessions = 3
        import time
        for i in range(5):
            store.save(_make_session(goal=f"목표 {i}"))
            time.sleep(0.05)
        files = list((workspace / ".agent_sessions").glob("agent_*.json"))
        assert len(files) <= 3

    def test_cleanup_removes_oldest(self, workspace):
        """가장 오래된 세션이 삭제됨"""
        store = AgentSessionStore(str(workspace))
        store.max_sessions = 2
        import time
        paths = []
        for i in range(3):
            p = store.save(_make_session(goal=f"목표 {i}"))
            paths.append(p)
            time.sleep(0.05)
        # 첫 번째(가장 오래된) 파일이 삭제되어야 함
        assert not paths[0].exists()
        assert paths[1].exists()
        assert paths[2].exists()


# ─── T-086-10: matched_files 누락 경고 ───────────────────────────────────────

class TestValidateMatchedFiles:
    def test_missing_files_detected(self, store, workspace):
        """T-086-10: matched_files 중 존재하지 않는 파일 감지"""
        s = _make_session()
        s.matched_files = ["src/main.py", "src/nonexistent.py"]
        # src/main.py 만 실제로 생성
        (workspace / "src").mkdir()
        (workspace / "src" / "main.py").write_text("# main")
        missing = store.validate_matched_files(s)
        assert "src/nonexistent.py" in missing
        assert "src/main.py" not in missing

    def test_all_files_exist_no_warning(self, store, workspace):
        """모든 matched_files 가 존재하면 빈 리스트 반환"""
        (workspace / "src").mkdir()
        (workspace / "src" / "main.py").write_text("# main")
        s = _make_session()
        s.matched_files = ["src/main.py"]
        missing = store.validate_matched_files(s)
        assert missing == []

    def test_empty_matched_files(self, store):
        """matched_files 가 비어있으면 빈 리스트 반환"""
        s = _make_session()
        s.matched_files = []
        assert store.validate_matched_files(s) == []


# ─── T-086-11: Resume 시 stop_reason 초기화 ─────────────────────────────────

class TestResumeStopReasonReset:
    def test_stop_reason_reset_on_resume(self, store):
        """T-086-11: 역직렬화 후 stop_reason 은 원본 값 유지 (runner에서 None으로 리셋)"""
        s = _make_session(stop_reason=AgentStopReason.USER_STOP)
        path = store.save(s)
        r = store.load(path.name)
        # store.load 는 stop_reason 을 보존; AgentRunner.run() 에서 None 으로 리셋
        assert r.stop_reason == AgentStopReason.USER_STOP

    def test_resume_iteration_count(self, store):
        """resume 세션의 iterations 수가 보존됨"""
        s = _make_session(n_iters=3, stop_reason=AgentStopReason.USER_STOP)
        path = store.save(s)
        r = store.load(path.name)
        assert len(r.iterations) == 3


# ─── T-086-12: 자동 저장 인터벌 환경변수 ────────────────────────────────────

class TestAutoSaveInterval:
    def test_env_var_respected(self, workspace, monkeypatch):
        """T-086-12: AGENT_AUTO_SAVE_INTERVAL 환경변수 반영"""
        monkeypatch.setenv("AGENT_AUTO_SAVE_INTERVAL", "7")
        store = AgentSessionStore(str(workspace))
        assert store.auto_save_interval == 7

    def test_max_sessions_env_var(self, workspace, monkeypatch):
        """AGENT_MAX_SAVED_SESSIONS 환경변수 반영"""
        monkeypatch.setenv("AGENT_MAX_SAVED_SESSIONS", "10")
        store = AgentSessionStore(str(workspace))
        assert store.max_sessions == 10


# ─── 파일명 생성 규칙 ────────────────────────────────────────────────────────

class TestFilenaming:
    def test_filename_format(self, store):
        """파일명이 agent_{timestamp}_{slug}.json 형식"""
        import re
        s = _make_session(goal="python 테트리스 작성")
        path = store.save(s)
        assert re.match(r"agent_\d{8}_\d{6}_.*\.json", path.name)

    def test_filename_slug_alphanumeric(self, store):
        """슬러그에 특수문자 없음"""
        import re
        s = _make_session(goal="hello world! @#$ test")
        path = store.save(s)
        name_no_ext = path.stem
        # agent_YYYYMMDD_HHMMSS_slug
        slug_part = name_no_ext.split("_", 3)[-1]
        assert re.match(r"[\w가-힣]+", slug_part)

    def test_workspace_stored_in_json(self, store, workspace):
        """_workspace 필드가 JSON 에 저장됨"""
        s = _make_session()
        path = store.save(s)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "_workspace" in data
        assert str(workspace) in data["_workspace"]
