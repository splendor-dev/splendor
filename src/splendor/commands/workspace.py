"""Workspace-level maintenance command helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from splendor.commands.ingest import DrainItemResult, DrainResult, run_ingest_job
from splendor.commands.source import (
    SourceFreshnessItem,
    SourceFreshnessResult,
    SourceRefreshResult,
    refresh_source,
    scan_source_freshness,
)
from splendor.commands.wiki import WikiIndexRebuildResult, rebuild_wiki_index
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import SourceRecord
from splendor.state.source_compat import canonical_source_ref, effective_logical_id
from splendor.state.source_registry import load_source_record, write_source_record
from splendor.utils.fs import write_text_atomic
from splendor.utils.wiki import parse_wiki_markdown, render_frontmatter


@dataclass(frozen=True)
class PrunedSourceSummary:
    path: str
    source_id: str
    superseded_by: str
    manifest_path: str


@dataclass(frozen=True)
class SkippedPruneSourceSummary:
    path: str
    source_id: str
    superseded_by: str | None
    manifest_path: str
    reason: str


@dataclass(frozen=True)
class PruneSupersededResult:
    candidates: int
    pruned: list[PrunedSourceSummary]
    skipped: list[SkippedPruneSourceSummary]


@dataclass(frozen=True)
class TopicRefMigration:
    path: str
    replacements: dict[str, str]


@dataclass(frozen=True)
class TopicRefMigrationResult:
    candidates: int
    updated: list[TopicRefMigration]


@dataclass(frozen=True)
class FailedWorkspaceRefreshSource:
    path: str
    source_id: str
    logical_id: str | None
    title: str
    manifest_path: str
    phase: str
    reason: str


@dataclass(frozen=True)
class WorkspaceRefreshResult:
    initial_freshness: SourceFreshnessResult
    final_freshness: SourceFreshnessResult
    skipped_sources: list[SourceFreshnessItem]
    failed_sources: list[FailedWorkspaceRefreshSource]
    refreshed: list[SourceRefreshResult]
    ingest: DrainResult | None
    index: WikiIndexRebuildResult | None
    pruning: PruneSupersededResult | None
    topic_ref_migration: TopicRefMigrationResult | None


def refresh_workspace(
    root: Path,
    *,
    changed: bool,
    ingest: bool = False,
    rebuild_index: bool = False,
    prune_superseded: bool = False,
    update_topic_refs: bool = False,
) -> WorkspaceRefreshResult:
    if not changed:
        msg = "workspace refresh requires --changed in this release"
        raise ValueError(msg)
    if rebuild_index and not ingest:
        msg = "workspace refresh --rebuild-index requires --ingest"
        raise ValueError(msg)

    initial_freshness = scan_source_freshness(root)
    skipped_sources = _unresolved_active_workspace_sources(initial_freshness)
    changed_items = [item for item in initial_freshness.sources if item.status == "changed"]
    refreshed, failed_sources = _refresh_changed_items(root, changed_items)

    ingest_result = _drain_refreshed_ingest_jobs(root, refreshed) if ingest else None
    index_result = None
    if rebuild_index and (ingest_result is None or ingest_result.failed == 0):
        index_result = rebuild_wiki_index(root)
    topic_ref_migration_result = migrate_superseded_topic_refs(root) if update_topic_refs else None
    pruning_result = prune_superseded_source_summaries(root) if prune_superseded else None
    if rebuild_index and (
        (pruning_result is not None and pruning_result.pruned)
        or (
            topic_ref_migration_result is not None
            and topic_ref_migration_result.updated
            and index_result is None
        )
    ):
        index_result = rebuild_wiki_index(root)
    final_freshness = scan_source_freshness(root)

    return WorkspaceRefreshResult(
        initial_freshness=initial_freshness,
        final_freshness=final_freshness,
        skipped_sources=skipped_sources,
        failed_sources=failed_sources,
        refreshed=refreshed,
        ingest=ingest_result,
        index=index_result,
        pruning=pruning_result,
        topic_ref_migration=topic_ref_migration_result,
    )


def prune_superseded_source_summaries(root: Path) -> PruneSupersededResult:
    layout = resolve_layout(root, load_config(root))
    sources = _load_sources_by_id(layout)
    pruned: list[PrunedSourceSummary] = []
    skipped: list[SkippedPruneSourceSummary] = []
    candidates = 0

    for source_id, source in sorted(sources.items()):
        if source.superseded_by is None or source.source_ref_kind != "workspace_path":
            continue
        page_path = layout.wiki_dir / "sources" / f"{source_id}.md"
        if not page_path.is_file():
            continue
        candidates += 1
        manifest_path = layout.source_records_dir / f"{source_id}.json"
        page_relpath = page_path.relative_to(root).as_posix()

        successor = sources.get(source.superseded_by)
        if successor is None:
            skipped.append(
                _skipped_prune_summary(
                    root,
                    manifest_path=manifest_path,
                    path=page_relpath,
                    source=source,
                    reason=f"superseded_by source is missing: {source.superseded_by}",
                )
            )
            continue
        successor_page = layout.wiki_dir / "sources" / f"{successor.source_id}.md"
        if not successor_page.is_file():
            successor_page_ref = successor_page.relative_to(root).as_posix()
            skipped.append(
                _skipped_prune_summary(
                    root,
                    manifest_path=manifest_path,
                    path=page_relpath,
                    source=source,
                    reason=f"successor source-summary page is missing: {successor_page_ref}",
                )
            )
            continue

        try:
            parsed = parse_wiki_markdown(page_path)
        except ValueError as exc:
            skipped.append(
                _skipped_prune_summary(
                    root,
                    manifest_path=manifest_path,
                    path=page_relpath,
                    source=source,
                    reason=str(exc),
                )
            )
            continue
        if parsed.frontmatter.kind != "source-summary" or parsed.frontmatter.page_id != source_id:
            skipped.append(
                _skipped_prune_summary(
                    root,
                    manifest_path=manifest_path,
                    path=page_relpath,
                    source=source,
                    reason=(f"wiki page is not the expected source-summary for {source_id}"),
                )
            )
            continue

        blocking_reason = _prune_blocking_reference_reason(
            root,
            layout,
            page_id=source_id,
            page_ref=page_relpath,
            candidate_path=page_path,
        )
        if blocking_reason is not None:
            skipped.append(
                _skipped_prune_summary(
                    root,
                    manifest_path=manifest_path,
                    path=page_relpath,
                    source=source,
                    reason=blocking_reason,
                )
            )
            continue

        _remove_pruned_page_links(manifest_path, source, page_relpath)
        page_path.unlink()
        pruned.append(
            PrunedSourceSummary(
                path=page_relpath,
                source_id=source_id,
                superseded_by=successor.source_id,
                manifest_path=manifest_path.relative_to(root).as_posix(),
            )
        )

    return PruneSupersededResult(candidates=candidates, pruned=pruned, skipped=skipped)


def migrate_superseded_topic_refs(root: Path) -> TopicRefMigrationResult:
    layout = resolve_layout(root, load_config(root))
    sources = _load_sources_by_id(layout)
    replacements = _superseded_source_replacements(sources)
    updated: list[TopicRefMigration] = []
    candidates = 0
    if not replacements:
        return TopicRefMigrationResult(candidates=0, updated=[])

    for page_path in sorted(layout.wiki_dir.rglob("*.md")):
        if page_path.name == ".gitkeep" or page_path in {layout.index_file, layout.log_file}:
            continue
        try:
            parsed = parse_wiki_markdown(page_path)
        except ValueError:
            continue
        if parsed.frontmatter.kind == "source-summary":
            continue
        page_replacements = {
            source_id: replacements[source_id]
            for source_id in parsed.frontmatter.source_refs
            if source_id in replacements
        }
        body = parsed.body
        for old_id, new_id in replacements.items():
            migrated_body = _migrate_source_ref_body_lines(body, old_id=old_id, new_id=new_id)
            if migrated_body == body:
                continue
            page_replacements.setdefault(old_id, new_id)
            body = migrated_body
        if not page_replacements:
            continue

        candidates += 1
        migrated_refs = [
            page_replacements.get(source_ref, source_ref)
            for source_ref in parsed.frontmatter.source_refs
        ]
        frontmatter = parsed.frontmatter.model_copy(
            update={"source_refs": _dedupe_preserve_order(migrated_refs)}
        )
        content = f"---\n{render_frontmatter(frontmatter)}\n---\n{body}"
        write_text_atomic(page_path, content)
        updated.append(
            TopicRefMigration(
                path=page_path.relative_to(root).as_posix(),
                replacements=dict(sorted(page_replacements.items())),
            )
        )

    return TopicRefMigrationResult(candidates=candidates, updated=updated)


def render_workspace_refresh_json(root: Path, result: WorkspaceRefreshResult) -> str:
    return json.dumps(
        {
            "initial_freshness": _freshness_counts(result.initial_freshness),
            "final_freshness": _freshness_counts(result.final_freshness),
            "skipped_sources": [
                _skipped_source_payload(root, item) for item in result.skipped_sources
            ],
            "failed_sources": [asdict(item) for item in result.failed_sources],
            "refreshed": [_refresh_payload(root, item) for item in result.refreshed],
            "ingest": None if result.ingest is None else _ingest_payload(root, result.ingest),
            "index": None if result.index is None else asdict(result.index),
            "pruning": None if result.pruning is None else asdict(result.pruning),
            "topic_ref_migration": (
                None if result.topic_ref_migration is None else asdict(result.topic_ref_migration)
            ),
        },
        indent=2,
    )


def _load_sources_by_id(layout) -> dict[str, SourceRecord]:
    return {
        path.stem: load_source_record(path)
        for path in sorted(layout.source_records_dir.glob("*.json"))
        if path.is_file()
    }


def _skipped_prune_summary(
    root: Path,
    *,
    manifest_path: Path,
    path: str,
    source: SourceRecord,
    reason: str,
) -> SkippedPruneSourceSummary:
    return SkippedPruneSourceSummary(
        path=path,
        source_id=source.source_id,
        superseded_by=source.superseded_by,
        manifest_path=manifest_path.relative_to(root).as_posix(),
        reason=reason,
    )


def _remove_pruned_page_links(manifest_path: Path, source: SourceRecord, page_ref: str) -> None:
    linked_pages = [value for value in source.linked_pages if value != page_ref]
    provenance_links = [
        link
        for link in source.provenance_links
        if not (
            link.page_id == source.source_id
            and link.role == "generated-page"
            and link.path_ref == page_ref
        )
    ]
    if linked_pages == source.linked_pages and provenance_links == source.provenance_links:
        return
    updated = source.model_copy(
        update={"linked_pages": linked_pages, "provenance_links": provenance_links}
    )
    write_source_record(manifest_path, updated)


def _prune_blocking_reference_reason(
    root: Path,
    layout,
    *,
    page_id: str,
    page_ref: str,
    candidate_path: Path,
) -> str | None:
    for wiki_path in sorted(layout.wiki_dir.rglob("*.md")):
        if wiki_path in {candidate_path, layout.index_file, layout.log_file}:
            continue
        if wiki_path.name == ".gitkeep":
            continue
        wiki_ref = wiki_path.relative_to(root).as_posix()
        text = wiki_path.read_text(encoding="utf-8")
        if page_ref in text:
            return f"referenced by wiki page body: {wiki_ref}"
        try:
            parsed = parse_wiki_markdown(wiki_path)
        except ValueError:
            continue
        frontmatter = parsed.frontmatter
        if page_id in frontmatter.related_pages:
            return f"referenced by wiki page related_pages: {wiki_ref}"
        for link in frontmatter.provenance_links:
            if link.page_id == page_id or link.path_ref == page_ref:
                return f"referenced by wiki page provenance: {wiki_ref}"
        for contradiction in frontmatter.contradictions:
            if page_id in contradiction.related_page_ids:
                return f"referenced by wiki page contradiction: {wiki_ref}"
            for evidence in contradiction.evidence:
                if evidence.page_id == page_id:
                    return f"referenced by wiki page contradiction evidence: {wiki_ref}"

    for planning_path in sorted(layout.planning_dir.rglob("*.md")):
        if planning_path.name == ".gitkeep" or not planning_path.is_file():
            continue
        text = planning_path.read_text(encoding="utf-8")
        if page_ref in text:
            planning_ref = planning_path.relative_to(root).as_posix()
            return f"referenced by planning record: {planning_ref}"

    return None


def _migrate_source_ref_body_lines(body: str, *, old_id: str, new_id: str) -> str:
    lines = body.splitlines(keepends=True)
    migrated: list[str] = []
    in_source_references = False
    for line in lines:
        newline = ""
        content = line
        if line.endswith("\r\n"):
            content = line[:-2]
            newline = "\r\n"
        elif line.endswith("\n"):
            content = line[:-1]
            newline = "\n"
        stripped = content.strip()
        if stripped.startswith("## "):
            in_source_references = stripped == "## Source References"
        if in_source_references and stripped == f"- `{old_id}`":
            leading = content[: len(content) - len(content.lstrip())]
            migrated.append(f"{leading}- `{new_id}`{newline}")
            continue
        migrated.append(line)
    return "".join(migrated)


def _superseded_source_replacements(sources: dict[str, SourceRecord]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for source_id, source in sources.items():
        current_id = _current_source_id(source, sources)
        if current_id != source_id:
            replacements[source_id] = current_id
    return replacements


def _current_source_id(source: SourceRecord, sources: dict[str, SourceRecord]) -> str:
    seen = {source.source_id}
    current = source
    while current.superseded_by is not None and current.superseded_by not in seen:
        successor = sources.get(current.superseded_by)
        if successor is None:
            break
        seen.add(successor.source_id)
        current = successor
    return current.source_id


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _refresh_changed_item(root: Path, item: SourceFreshnessItem) -> SourceRefreshResult:
    return refresh_source(root, item.canonical_path)


def _refresh_changed_items(
    root: Path, items: list[SourceFreshnessItem]
) -> tuple[list[SourceRefreshResult], list[FailedWorkspaceRefreshSource]]:
    refreshed: list[SourceRefreshResult] = []
    failed: list[FailedWorkspaceRefreshSource] = []
    for item in items:
        try:
            refreshed.append(_refresh_changed_item(root, item))
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            failed.append(_failed_refresh_source(root, item=item, reason=str(exc)))
    return refreshed, failed


def _unresolved_active_workspace_sources(
    result: SourceFreshnessResult,
) -> list[SourceFreshnessItem]:
    return [
        item
        for item in result.sources
        if item.status in {"missing", "unsupported"} and item.source.superseded_by is None
    ]


def _failed_refresh_source(
    root: Path, *, item: SourceFreshnessItem, reason: str
) -> FailedWorkspaceRefreshSource:
    source = item.source
    return FailedWorkspaceRefreshSource(
        path=item.canonical_path,
        source_id=source.source_id,
        logical_id=effective_logical_id(source),
        title=source.title,
        manifest_path=item.manifest_path.relative_to(root).as_posix(),
        phase="refresh",
        reason=reason,
    )


def _drain_refreshed_ingest_jobs(root: Path, refreshed: list[SourceRefreshResult]) -> DrainResult:
    queue_paths = [
        result.queue_path for result in refreshed if result.queued and result.queue_path is not None
    ]
    item_results: list[DrainItemResult] = []
    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for queue_path in queue_paths:
        source_id = queue_path.stem.removeprefix("ingest-")
        try:
            result = run_ingest_job(root, queue_path)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            processed += 1
            failed += 1
            item_results.append(
                DrainItemResult(
                    source_id=source_id,
                    queue_path=queue_path,
                    outcome="failed",
                    message=str(exc),
                )
            )
            continue

        if result.no_op:
            skipped += 1
            item_results.append(
                DrainItemResult(
                    source_id=result.source_id,
                    queue_path=queue_path,
                    outcome="skipped",
                    message="already ingested for the current pipeline version",
                )
            )
            continue

        processed += 1
        succeeded += 1
        item_results.append(
            DrainItemResult(
                source_id=result.source_id,
                queue_path=queue_path,
                outcome="succeeded",
                message=f"run {result.run_id}",
            )
        )

    return DrainResult(
        total=len(queue_paths),
        processed=processed,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        items=item_results,
    )


def _freshness_counts(result: SourceFreshnessResult) -> dict[str, int]:
    return {
        "total": result.total,
        "unchanged": result.unchanged,
        "changed": result.changed,
        "missing": result.missing,
        "unsupported": result.unsupported,
        "historical": result.historical,
    }


def _refresh_payload(root: Path, result: SourceRefreshResult) -> dict[str, object]:
    queue_path = None
    if result.queue_path is not None:
        queue_path = result.queue_path.relative_to(root).as_posix()
    return {
        "path": canonical_source_ref(result.refreshed.record),
        "requested_source_id": result.requested.source_id,
        "requested_logical_id": effective_logical_id(result.requested),
        "source_id": result.refreshed.record.source_id,
        "logical_id": effective_logical_id(result.refreshed.record),
        "supersedes": result.refreshed.record.supersedes,
        "superseded_by": result.refreshed.record.superseded_by,
        "changed": result.changed,
        "queued": result.queued,
        "queue_path": queue_path,
        "message": result.message,
    }


def _skipped_source_payload(root: Path, item: SourceFreshnessItem) -> dict[str, object]:
    source = item.source
    return {
        "path": item.canonical_path,
        "status": item.status,
        "source_id": source.source_id,
        "logical_id": effective_logical_id(source),
        "title": source.title,
        "source_ref": canonical_source_ref(source),
        "source_ref_kind": source.source_ref_kind,
        "manifest_path": item.manifest_path.relative_to(root).as_posix(),
        "message": item.message,
        "next_commands": item.next_commands,
    }


def _ingest_payload(root: Path, result: DrainResult) -> dict[str, object]:
    return {
        "total": result.total,
        "processed": result.processed,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "skipped": result.skipped,
        "items": [
            {
                "source_id": item.source_id,
                "queue_path": item.queue_path.relative_to(root).as_posix(),
                "outcome": item.outcome,
                "message": item.message,
            }
            for item in result.items
        ],
    }
