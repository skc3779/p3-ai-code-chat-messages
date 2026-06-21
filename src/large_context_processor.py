"""Sequential Map/Reduce orchestration for `/context --large`."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Iterable, List

from .context_chunker import CHUNK_SCHEMA_VERSION, ContextBudget, ContextChunk, ContextChunker, FileRecord
from .file_pattern_matcher import FilePatternMatcher
from .large_context_cache import LargeContextCache
from .large_context_prompts import PROMPT_SCHEMA_VERSION, build_map_prompt, build_reduce_prompt


MAX_REDUCE_LEVELS = 8


class LargeContextError(RuntimeError):
    pass


@dataclass(frozen=True)
class InternalCallResult:
    success: bool
    content: str = ""
    error: str = ""


class LargeContextProcessor:
    def __init__(self, assistant, file_manager, *, provider: str):
        self.assistant = assistant
        self.file_manager = file_manager
        self.provider = provider
        self.calls = {"map": 0, "reduce": 0}
        self.reused = {"map": 0, "reduce": 0}

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()

    def _invoke(self, prompt: str, budget: ContextBudget) -> str:
        saved_history = self.assistant.conversation_history
        saved_suppress = getattr(self.assistant, "_suppress_chat_output", False)
        self.assistant.conversation_history = []
        self.assistant._suppress_chat_output = True
        try:
            prepared = self._prepare_request(prompt, history_already_isolated=True)
            system_prompt = prepared["system_prompt"]
            rendered_chars = prepared["request_chars"]
            if rendered_chars > budget.reduce_payload_chars:
                raise LargeContextError(
                    f"렌더링된 내부 요청이 예산을 초과했습니다: {rendered_chars:,} > {budget.reduce_payload_chars:,} chars"
                )
            try:
                response = self.assistant.chat(
                    prompt, streaming=False, include_context=False,
                    disable_tools=True, raise_on_error=True,
                    internal_system_prompt=system_prompt,
                )
                result = InternalCallResult(True, response)
            except LargeContextError:
                raise
            except Exception as exc:
                result = InternalCallResult(False, error=str(exc))
        finally:
            self.assistant.conversation_history = saved_history
            self.assistant._suppress_chat_output = saved_suppress
        if not result.success:
            raise LargeContextError(f"내부 LLM 호출 실패: {result.error}")
        if not result.content:
            raise LargeContextError("내부 LLM 호출은 성공했지만 필수 응답 본문이 비어 있습니다.")
        return result.content

    def _prepare_request(self, prompt: str, *, history_already_isolated: bool = False) -> dict:
        saved_history = self.assistant.conversation_history
        if not history_already_isolated:
            self.assistant.conversation_history = []
        try:
            prepare = getattr(self.assistant, "prepare_internal_request", None)
            if prepare is not None:
                return prepare(prompt)
            system_prompt = str(getattr(self.assistant, "system_prompt", ""))
            return {"system_prompt": system_prompt, "request_chars": len(prompt) + len(system_prompt)}
        finally:
            if not history_already_isolated:
                self.assistant.conversation_history = saved_history

    def process(self, file_patterns: List[str], question: str, *, include_tree: bool = True,
                _file_change_retry: bool = False) -> str:
        workspace = self.file_manager.workspace_dir.resolve()
        request_budget = self.assistant.context_builder.max_tokens
        try:
            budget = ContextBudget.from_request_budget(request_budget)
        except ValueError as exc:
            raise LargeContextError(str(exc)) from exc
        model_id = str(getattr(self.assistant, "model_id", "unknown"))
        prepared_empty = self._prepare_request("")
        config = {
            "budget": budget.to_dict(),
            "provider": self.provider,
            "model_id": model_id,
            "prompt_schema": PROMPT_SCHEMA_VERSION,
            "chunk_schema": CHUNK_SCHEMA_VERSION,
            "system_prompt_sha256": sha256(prepared_empty["system_prompt"].encode("utf-8")).hexdigest(),
        }
        job_material = {
            "workspace": str(workspace),
            "provider": self.provider,
            "model_id": model_id,
            "patterns": sorted(file_patterns),
            "question": question,
            "include_tree": include_tree,
            "config": config,
        }
        job_id = self._digest(job_material)[:12]
        cache = LargeContextCache(workspace, job_id)

        records, read_errors = self._read_records(workspace, file_patterns, budget)
        if not records:
            error = "패턴에 해당하는 읽을 수 있는 파일이 없습니다."
            manifest = self._new_manifest(
                job_id, question, file_patterns, include_tree, config,
                records, read_errors, [],
            )
            manifest["status"] = "failed"
            manifest["last_error"] = error
            cache.save_manifest(manifest)
            raise LargeContextError(error)
        map_probe = build_map_prompt(question, "", "")
        map_overhead = self._prepare_request(map_probe)["request_chars"]
        available = min(budget.map_payload_chars, budget.reduce_payload_chars - map_overhead - 512)
        if available <= 0:
            raise LargeContextError("질문과 Map 프롬프트만으로 요청 예산을 초과합니다.")
        chunk_budget = replace(budget, map_payload_chars=available)
        chunker = ContextChunker(chunk_budget)
        chunks = chunker.chunk(records, identity=self._digest({"question": question, **config}))
        inventory = self._render_inventory(records, read_errors, chunks)
        tree = self.assistant.context_builder.build_file_tree() if include_tree else ""
        tree_limit = min(8192, max(0, budget.reduce_payload_chars // 10))
        if len(tree) > tree_limit:
            tree = tree[:tree_limit] + "\n... [tree truncated for request budget]"
        inventory_fingerprint = self._inventory_fingerprint(records, read_errors, config, tree)
        cached_final = cache.load_final(inventory_fingerprint)
        if cached_final is not None:
            print(f"♻️ 완료 캐시 재사용 (작업 ID: {job_id})")
            self._commit_history(question, cached_final)
            return cached_final
        manifest = self._new_manifest(job_id, question, file_patterns, include_tree, config, records, read_errors, chunks)
        cache.save_manifest(manifest)

        try:
            summaries = self._map(cache, manifest, chunks, question, budget)
            self._mark_mapped(manifest)
            self._validate_completeness(manifest)
            current_records, current_errors = self._read_records(workspace, file_patterns, budget)
            if self._inventory_signature(records, read_errors) != self._inventory_signature(current_records, current_errors):
                manifest["status"] = "interrupted"
                manifest["last_error"] = "입력 파일이 실행 중 변경되어 영향 청크를 다시 처리합니다."
                cache.save_manifest(manifest)
                if _file_change_retry:
                    raise LargeContextError("입력 파일이 재처리 중 다시 변경되어 중단했습니다.")
                return self.process(
                    file_patterns, question, include_tree=include_tree,
                    _file_change_retry=True,
                )
            manifest["status"] = "reducing"
            cache.save_manifest(manifest)
            final = self._reduce(cache, manifest, summaries, question, inventory, tree, budget)
            cache.save_final(final, inventory_fingerprint)
            manifest["status"] = "complete"
            manifest["last_error"] = None
            cache.save_manifest(manifest)
        except KeyboardInterrupt:
            manifest["status"] = "interrupted"
            manifest["last_error"] = "KeyboardInterrupt"
            cache.save_manifest(manifest)
            raise
        except Exception as exc:
            if manifest.get("status") != "interrupted":
                manifest["status"] = "failed"
                manifest["last_error"] = str(exc)
                cache.save_manifest(manifest)
            raise

        self._commit_history(question, final)
        print("✅ 대규모 컨텍스트 처리 완료")
        print(f"   파일: {len(records) + len(read_errors)}개 (읽기 실패 {len(read_errors)})")
        print(f"   LLM 호출: {self.calls['map'] + self.calls['reduce']}회 (Map {self.calls['map']}, Reduce {self.calls['reduce']})")
        print(f"   캐시 재사용: Map {self.reused['map']}, Reduce {self.reused['reduce']}")
        print(f"   작업 ID: {job_id}")
        return final

    def _read_records(self, workspace: Path, patterns: List[str], budget: ContextBudget) -> tuple[List[FileRecord], List[dict]]:
        matcher = FilePatternMatcher(workspace)
        matched = matcher.filter_files(self.file_manager.list_files(), patterns)
        chunker = ContextChunker(budget)
        records, errors = [], []
        seen_targets: set[Path] = set()
        for path in sorted(matched, key=lambda value: value.relative_to(workspace).as_posix()):
            resolved = path.resolve()
            try:
                resolved.relative_to(workspace)
            except ValueError:
                errors.append({
                    "path": path.relative_to(workspace).as_posix(),
                    "status": "read_error",
                    "error_type": "outside_workspace",
                })
                continue
            target_chain = (resolved, *resolved.parents)
            if any(
                candidate != workspace and self.file_manager.should_ignore(candidate)
                for candidate in target_chain
                if candidate == workspace or workspace in candidate.parents
            ):
                errors.append({
                    "path": path.relative_to(workspace).as_posix(),
                    "status": "read_error",
                    "error_type": "ignored_target",
                })
                continue
            if resolved in seen_targets:
                continue
            seen_targets.add(resolved)
            content = self.file_manager.read_file(resolved)
            if content is None:
                errors.append({"path": path.relative_to(workspace).as_posix(), "status": "read_error", "error_type": "unreadable"})
            else:
                records.append(chunker.make_record(workspace, resolved, content))
        return records, errors

    def _map(self, cache, manifest, chunks: List[ContextChunk], question: str, budget: ContextBudget) -> List[tuple[str, str]]:
        summaries = []
        manifest["status"] = "mapping"
        for chunk in chunks:
            summary = cache.load_artifact("map", chunk.fingerprint)
            label = ", ".join(dict.fromkeys(part.path for part in chunk.parts))
            if summary is not None:
                self.reused["map"] += 1
                manifest["chunks"][chunk.index - 1]["status"] = "complete"
                print(f"[Map {chunk.index}/{len(chunks)}] {label} ... ♻️ 캐시 재사용")
            else:
                inventory = "\n".join(
                    f"- {part.path}:L{part.start_line}-L{part.end_line} part {part.part_index}/{part.part_count}"
                    for part in chunk.parts
                )
                prompt = build_map_prompt(question, inventory, chunk.payload)
                try:
                    summary = self._invoke(prompt, budget)
                except BaseException:
                    manifest["chunks"][chunk.index - 1]["status"] = "failed"
                    cache.save_manifest(manifest)
                    raise
                self.calls["map"] += 1
                cache.save_artifact("map", chunk.fingerprint, summary, {"chunk_index": chunk.index})
                manifest["chunks"][chunk.index - 1]["status"] = "complete"
                cache.save_manifest(manifest)
                print(f"[Map {chunk.index}/{len(chunks)}] {label} ... ✅ 저장")
            summaries.append((chunk.fingerprint, summary))
        return summaries

    def _reduce(self, cache, manifest, summaries, question, inventory, tree, budget):
        level = 0
        current = summaries
        while True:
            final_prompt = build_reduce_prompt(
                question,
                self._render_summaries(current),
                inventory,
                level=level + 1,
                final=True,
                tree=tree,
            )
            if len(final_prompt) <= budget.reduce_payload_chars:
                key = self._digest({
                    "level": level + 1, "final": True,
                    "inputs": self._summary_identities(current),
                    "question": question, "inventory": inventory, "tree": tree,
                    "prompt_schema": PROMPT_SCHEMA_VERSION,
                })
                cached = cache.load_artifact("reduce", f"L{level + 1:02d}-{key}")
                if cached is not None:
                    self.reused["reduce"] += 1
                    return cached
                result = self._invoke(final_prompt, budget)
                self.calls["reduce"] += 1
                cache.save_artifact("reduce", f"L{level + 1:02d}-{key}", result, {"level": level + 1, "final": True})
                return result
            level += 1
            if level > MAX_REDUCE_LEVELS:
                raise LargeContextError(f"Reduce가 {MAX_REDUCE_LEVELS}단계 안에 수렴하지 않았습니다.")
            groups = self._group_summaries(current, question, inventory, budget)
            if len(groups) >= len(current):
                raise LargeContextError("Reduce 입력이 더 작은 그룹으로 수렴하지 않습니다.")
            next_level = []
            for index, group in enumerate(groups, 1):
                if len(group) == 1:
                    next_level.append(group[0])
                    continue
                prompt = build_reduce_prompt(question, self._render_summaries(group), inventory, level=level, final=False)
                key = self._digest({
                    "level": level, "inputs": self._summary_identities(group),
                    "question": question, "inventory": inventory,
                    "prompt_schema": PROMPT_SCHEMA_VERSION,
                })
                artifact_key = f"L{level:02d}-{key}"
                result = cache.load_artifact("reduce", artifact_key)
                if result is None:
                    result = self._invoke(prompt, budget)
                    self.calls["reduce"] += 1
                    cache.save_artifact("reduce", artifact_key, result, {"level": level, "group": index})
                    cache.save_manifest(manifest)
                    print(f"[Reduce L{level} {index}/{len(groups)}] ... ✅ 저장")
                else:
                    self.reused["reduce"] += 1
                    print(f"[Reduce L{level} {index}/{len(groups)}] ... ♻️ 캐시 재사용")
                next_level.append((key, result))
            if sum(len(text) for _, text in next_level) >= sum(len(text) for _, text in current):
                raise LargeContextError("Reduce 결과가 입력보다 작아지지 않아 중단했습니다.")
            current = next_level

    def _group_summaries(self, summaries, question, inventory, budget):
        groups, current = [], []
        for item in summaries:
            candidate = current + [item]
            prompt = build_reduce_prompt(question, self._render_summaries(candidate), inventory, level=1, final=False)
            if current and len(prompt) > budget.reduce_payload_chars:
                groups.append(current)
                current = [item]
            else:
                current = candidate
        if current:
            groups.append(current)
        if len(groups) == 1 and len(summaries) > 1:
            midpoint = max(1, len(summaries) // 2)
            groups = [summaries[:midpoint], summaries[midpoint:]]
        return groups

    @staticmethod
    def _render_summaries(summaries) -> str:
        return "\n\n".join(f"### Summary {key}\n{text}" for key, text in summaries)

    @staticmethod
    def _summary_identities(summaries) -> list[tuple[str, str]]:
        return [(key, sha256(text.encode("utf-8")).hexdigest()) for key, text in summaries]

    @staticmethod
    def _inventory_signature(records: Iterable[FileRecord], errors: list[dict]) -> tuple:
        files = tuple(sorted((record.path, record.sha256) for record in records))
        failed = tuple(sorted((item.get("path"), item.get("status"), item.get("error_type")) for item in errors))
        return files, failed

    def _inventory_fingerprint(self, records, errors, config, tree):
        return self._digest({
            "files": [(r.path, r.sha256) for r in records],
            "errors": errors, "config": config, "tree_sha256": sha256(tree.encode("utf-8")).hexdigest(),
        })

    @staticmethod
    def _render_inventory(records, errors, chunks):
        part_counts = {}
        for chunk in chunks:
            for part in chunk.parts:
                part_counts[part.path] = max(part_counts.get(part.path, 0), part.part_count)
        lines = [f"- {record.path} ({record.size} bytes, {part_counts.get(record.path, 1)} part(s))" for record in records]
        lines.extend(f"- {item['path']} (read_error)" for item in errors)
        return "\n".join(lines)

    def _new_manifest(self, job_id, question, patterns, include_tree, config, records, errors, chunks):
        now = LargeContextCache.now()
        return {
            "schema_version": 1, "job_id": job_id, "status": "planned", "provider": self.provider,
            "model_id": config["model_id"], "question_sha256": sha256(question.encode()).hexdigest(),
            "patterns": sorted(patterns), "include_tree": include_tree, "budget": config["budget"],
            "config_fingerprint": self._digest(config),
            "files": [{"path": r.path, "sha256": r.sha256, "size": r.size, "status": "pending"} for r in records] + errors,
            "chunks": [{"index": c.index, "fingerprint": c.fingerprint, "status": "pending"} for c in chunks],
            "reduce_levels": [], "created_at": now, "updated_at": now, "last_error": None,
        }

    @staticmethod
    def _mark_mapped(manifest: dict) -> None:
        for item in manifest["files"]:
            if item["status"] == "pending":
                item["status"] = "mapped"
        for item in manifest["chunks"]:
            item["status"] = "complete"

    @staticmethod
    def _validate_completeness(manifest: dict) -> None:
        allowed = {"mapped", "read_error"}
        invalid = [item["path"] for item in manifest["files"] if item.get("status") not in allowed]
        if invalid:
            manifest["status"] = "incomplete"
            raise LargeContextError(f"파일 완전성 검증 실패: {', '.join(invalid)}")

    def _commit_history(self, question: str, result: str) -> None:
        role = "assistant" if self.provider == "claude" else "model"
        self.assistant.conversation_history.append({"role": "user", "content": question})
        self.assistant.conversation_history.append({"role": role, "content": result})
