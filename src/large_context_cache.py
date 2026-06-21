"""Atomic, integrity-checked disk cache for large-context processing."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional


class LargeContextCache:
    def __init__(self, workspace: Path, job_id: str):
        self.root = workspace / ".large_context_cache" / job_id
        self.maps = self.root / "maps"
        self.reduces = self.root / "reduces"
        for path in (self.root, self.maps, self.reduces):
            path.mkdir(parents=True, exist_ok=True)
            self._chmod(path, 0o700)

    @staticmethod
    def digest(text: str) -> str:
        return sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _chmod(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except OSError:
            pass

    def _atomic_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with open(temp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        self._chmod(temp, 0o600)
        os.replace(temp, path)
        self._chmod(path, 0o600)

    def write_json(self, path: Path, value: Any) -> None:
        self._atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def load_manifest(self) -> Optional[dict]:
        try:
            return json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None

    def save_manifest(self, manifest: dict) -> None:
        manifest["updated_at"] = self.now()
        self.write_json(self.root / "manifest.json", manifest)

    def save_artifact(self, kind: str, key: str, content: str, metadata: dict) -> None:
        directory = self.maps if kind == "map" else self.reduces
        markdown = directory / f"{key}.md"
        meta = directory / f"{key}.json"
        self._atomic_text(markdown, content)
        value = dict(metadata, status="complete", content_sha256=self.digest(content))
        self.write_json(meta, value)

    def load_artifact(self, kind: str, key: str) -> Optional[str]:
        directory = self.maps if kind == "map" else self.reduces
        try:
            content = (directory / f"{key}.md").read_text(encoding="utf-8")
            metadata = json.loads((directory / f"{key}.json").read_text(encoding="utf-8"))
            if metadata.get("status") != "complete" or metadata.get("content_sha256") != self.digest(content):
                return None
            return content
        except (OSError, ValueError, TypeError):
            return None

    def save_final(self, content: str, fingerprint: str) -> None:
        self._atomic_text(self.root / "final.md", content)
        self.write_json(self.root / "final.json", {"fingerprint": fingerprint, "content_sha256": self.digest(content)})

    def load_final(self, fingerprint: str) -> Optional[str]:
        try:
            content = (self.root / "final.md").read_text(encoding="utf-8")
            meta = json.loads((self.root / "final.json").read_text(encoding="utf-8"))
            if meta.get("fingerprint") == fingerprint and meta.get("content_sha256") == self.digest(content):
                return content
        except (OSError, ValueError, TypeError):
            pass
        return None
