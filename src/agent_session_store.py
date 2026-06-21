"""
AgentSessionStore — 에이전트 세션 JSON 직렬화/역직렬화 및 파일 관리 (FSD v1.0.086)
"""

import dataclasses
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .agent_goal_evaluator import (
    ALLOWED_CHECK_TYPES,
    ALLOWED_PROVENANCE,
    ALLOWED_STATUSES,
    MAX_CRITERIA,
    MAX_DESCRIPTION_LENGTH,
    MAX_EXPECTED_LENGTH,
    MAX_ID_LENGTH,
    MAX_TARGET_LENGTH,
    AcceptanceCriterion,
)
from .agent_runner import ActionResult, AgentSession, AgentStopReason, IterationRecord


class _AgentSessionEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, AgentStopReason):
            return o.value
        return super().default(o)


class AgentSessionStore:
    SESSIONS_DIR = ".agent_sessions"

    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.sessions_dir = self.workspace_dir / self.SESSIONS_DIR
        self.max_sessions = int(os.getenv("AGENT_MAX_SAVED_SESSIONS", "5"))
        self.auto_save_interval = int(os.getenv("AGENT_AUTO_SAVE_INTERVAL", "3"))

    def _ensure_dir(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _make_filename(self, session: AgentSession) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^\w가-힣]", "_", session.goal[:30]).strip("_")
        slug = re.sub(r"_+", "_", slug)
        return f"agent_{ts}_{slug}.json"

    def _serialize(self, session: AgentSession) -> str:
        data = dataclasses.asdict(session)
        # stop_reason Enum → value (asdict 이 Enum 을 그대로 넣으므로 수동 변환)
        if isinstance(data.get("stop_reason"), AgentStopReason):
            data["stop_reason"] = data["stop_reason"].value
        # FSD v1.0.101 — 런타임 캐시는 직렬화 제외
        data.pop("effective_max_iterations", None)
        # workspace 경로 저장 (resume 시 경로 검증용)
        data["_workspace"] = str(self.workspace_dir)
        return json.dumps(data, cls=_AgentSessionEncoder, ensure_ascii=False, indent=2)

    def _deserialize(self, json_str: str) -> AgentSession:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            raise ValueError("agent session JSON must be an object")
        data.pop("_workspace", None)
        # stop_reason 복원
        sr = data.get("stop_reason")
        data["stop_reason"] = AgentStopReason(sr) if sr else None
        # iterations 복원
        iters = []
        for it_data in data.get("iterations", []):
            actions = [ActionResult(**a) for a in it_data.pop("actions", [])]
            iters.append(IterationRecord(**it_data, actions=actions))
        data["iterations"] = iters
        data["acceptance_criteria"] = self._deserialize_criteria(
            data.get("acceptance_criteria", [])
        )
        # Ignore unknown future/tampered keys instead of forwarding them to the
        # dataclass constructor. Runtime validation remains AgentRunner-owned.
        allowed = {item.name for item in dataclasses.fields(AgentSession)}
        data = {key: value for key, value in data.items() if key in allowed}
        return AgentSession(**data)

    @staticmethod
    def _deserialize_criteria(raw_records) -> List[AcceptanceCriterion]:
        if not isinstance(raw_records, list):
            return []
        restored: List[AcceptanceCriterion] = []
        for raw in raw_records[:MAX_CRITERIA]:
            if not isinstance(raw, dict):
                continue
            values = {
                "id": str(raw.get("id", "")),
                "description": str(raw.get("description", "")),
                "check_type": str(raw.get("check_type", "")),
                "target": str(raw.get("target", "")),
                "expected": str(raw.get("expected", "")),
                "provenance": str(raw.get("provenance", "model")),
                "status": str(raw.get("status", "pending")),
                "evidence": str(raw.get("evidence", ""))[:MAX_TARGET_LENGTH],
            }
            if not values["id"] or len(values["id"]) > MAX_ID_LENGTH:
                continue
            if not values["description"] or len(values["description"]) > MAX_DESCRIPTION_LENGTH:
                continue
            if values["check_type"] not in ALLOWED_CHECK_TYPES:
                continue
            if values["provenance"] not in ALLOWED_PROVENANCE:
                continue
            if values["status"] not in ALLOWED_STATUSES:
                continue
            if len(values["target"]) > MAX_TARGET_LENGTH:
                continue
            if len(values["expected"]) > MAX_EXPECTED_LENGTH:
                continue
            restored.append(AcceptanceCriterion(**values))
        return restored

    def save(self, session: AgentSession, filename: Optional[str] = None) -> Path:
        self._ensure_dir()
        fname = filename or self._make_filename(session)
        path = self.sessions_dir / fname
        path.write_text(self._serialize(session), encoding="utf-8")
        # latest.json 갱신
        latest = self.sessions_dir / "latest.json"
        latest.write_text(self._serialize(session), encoding="utf-8")
        self._cleanup_old()
        return path

    def load(self, filename: str) -> Optional[AgentSession]:
        path = self.sessions_dir / filename
        if not path.exists():
            return None
        return self._deserialize(path.read_text(encoding="utf-8"))

    def load_latest(self) -> Optional[AgentSession]:
        latest = self.sessions_dir / "latest.json"
        if not latest.exists():
            return None
        return self._deserialize(latest.read_text(encoding="utf-8"))

    def list_sessions(self) -> List[Dict]:
        if not self.sessions_dir.exists():
            return []
        entries = []
        for p in sorted(self.sessions_dir.glob("agent_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                entries.append({
                    "filename": p.name,
                    "goal": data.get("goal", "")[:60],
                    "stop_reason": data.get("stop_reason") or "unknown",
                    "iterations": len(data.get("iterations", [])),
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
            except Exception:
                continue
        return entries

    def _cleanup_old(self) -> None:
        files = sorted(
            self.sessions_dir.glob("agent_*.json"),
            key=lambda x: x.stat().st_mtime,
        )
        while len(files) > self.max_sessions:
            files.pop(0).unlink(missing_ok=True)

    # ── 공개 유틸 ──────────────────────────────────────────────────────────
    def print_session_list(self) -> None:
        sessions = self.list_sessions()
        if not sessions:
            print("📭 저장된 에이전트 세션이 없습니다.")
            return
        print(f"\n{'─'*80}")
        print(f"{'#':<3} {'파일명':<40} {'상태':<14} {'iter':<5} {'날짜'}")
        print(f"{'─'*80}")
        for i, s in enumerate(sessions, 1):
            print(f"{i:<3} {s['filename']:<40} {s['stop_reason']:<14} {s['iterations']:<5} {s['mtime']}")
            print(f"    목표: {s['goal']}")
        print(f"{'─'*80}")
        print("⚠️  세션 파일에 대화 내용이 평문으로 저장됩니다. git 에는 포함되지 않습니다.")
        print("💡 /agents resume <번호> 또는 /agents resume <파일명>\n")

    def validate_matched_files(self, session: AgentSession) -> List[str]:
        missing = []
        for rel in session.matched_files:
            if not (self.workspace_dir / rel).exists():
                missing.append(rel)
        return missing
