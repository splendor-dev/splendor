"""Source lifecycle and lookup command helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from splendor.commands.ingest import enqueue_ingest_job, is_ingest_current
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import SourceRecord
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import ingest_job_id
from splendor.state.source_compat import canonical_source_ref, effective_storage_mode
from splendor.state.source_registry import (
    RegisteredSource,
    load_source_record,
    register_source,
)
from splendor.utils.hashing import sha256_file


@dataclass(frozen=True)
class SourceLookupResult:
    source: SourceRecord
    manifest_path: Path


@dataclass(frozen=True)
class SourceRefreshResult:
    requested: SourceRecord
    refreshed: RegisteredSource
    changed: bool
    queued: bool
    queue_path: Path | None
    message: str


def list_sources(root: Path) -> list[SourceLookupResult]:
    layout = resolve_layout(root, load_config(root))
    results = [
        SourceLookupResult(source=load_source_record(path), manifest_path=path)
        for path in sorted(layout.source_records_dir.glob("*.json"))
    ]
    return sorted(results, key=_lookup_sort_key)


def lookup_sources(root: Path, query: str | None = None) -> list[SourceLookupResult]:
    results = list_sources(root)
    if query is None or not query.strip():
        return results
    needle = query.strip().casefold()
    return [result for result in results if _matches_source(result.source, needle)]


def refresh_source(root: Path, source_query: str) -> SourceRefreshResult:
    matches = lookup_sources(root, source_query)
    exact_matches = [
        match
        for match in matches
        if match.source.source_id == source_query
        or match.source.title.casefold() == source_query.casefold()
        or canonical_source_ref(match.source) == source_query
        or (match.source.original_path is not None and match.source.original_path == source_query)
    ]
    candidates = exact_matches or matches
    if not candidates:
        msg = f"Unknown source: {source_query}"
        raise FileNotFoundError(msg)
    if len(candidates) > 1:
        ids = ", ".join(candidate.source.source_id for candidate in candidates[:5])
        suffix = "" if len(candidates) <= 5 else ", ..."
        msg = f"Source lookup is ambiguous for {source_query!r}: {ids}{suffix}"
        raise ValueError(msg)

    requested = candidates[0].source
    current_path = _refreshable_source_path(root, requested)
    current_checksum = sha256_file(current_path)
    changed = current_checksum != requested.checksum

    if changed:
        refreshed = register_source(
            root,
            current_path,
            storage_mode=requested.storage_mode,
            source_class=requested.source_class,
            source_labels=requested.source_labels,
            discovered_by=requested.discovered_by,
        )
    else:
        refreshed = RegisteredSource(
            record=requested,
            manifest_path=candidates[0].manifest_path,
            stored_path=None,
            storage_mode=effective_storage_mode(requested),
            source_ref=canonical_source_ref(requested),
            copied=False,
            already_registered=True,
        )

    layout = resolve_layout(root, load_config(root))
    if is_ingest_current(root, layout, refreshed.record):
        return SourceRefreshResult(
            requested=requested,
            refreshed=refreshed,
            changed=changed,
            queued=False,
            queue_path=None,
            message="source is already ingested for the current pipeline version",
        )

    queue_path = enqueue_ingest_job(root, refreshed.record.source_id)
    return SourceRefreshResult(
        requested=requested,
        refreshed=refreshed,
        changed=changed,
        queued=True,
        queue_path=queue_path,
        message="queued ingest",
    )


def render_source_lookup_json(root: Path, results: list[SourceLookupResult]) -> str:
    return json.dumps(
        {"sources": [_source_payload(root, result) for result in results]},
        indent=2,
    )


def render_source_refresh_json(root: Path, result: SourceRefreshResult) -> str:
    return json.dumps(
        {
            "requested_source_id": result.requested.source_id,
            "source_id": result.refreshed.record.source_id,
            "changed": result.changed,
            "queued": result.queued,
            "queue_path": (
                None
                if result.queue_path is None
                else result.queue_path.relative_to(root).as_posix()
            ),
            "message": result.message,
        },
        indent=2,
    )


def _lookup_sort_key(result: SourceLookupResult) -> tuple[str, str, str]:
    return (
        result.source.title.casefold(),
        canonical_source_ref(result.source).casefold(),
        result.source.source_id,
    )


def _matches_source(source: SourceRecord, needle: str) -> bool:
    haystacks = [
        source.source_id,
        source.title,
        canonical_source_ref(source),
        source.path,
        source.original_path or "",
    ]
    return any(needle in value.casefold() for value in haystacks)


def _refreshable_source_path(root: Path, source: SourceRecord) -> Path:
    if source.source_ref_kind == "workspace_path" and source.source_ref:
        return resolve_workspace_path(root, source.source_ref, context="Workspace source")
    if source.source_ref_kind == "external_path" and source.source_ref:
        return Path(source.source_ref).expanduser().resolve()
    msg = (
        "Only workspace-backed and external-path sources can be refreshed by canonical source "
        f"reference: {source.source_id}"
    )
    raise ValueError(msg)


def _source_payload(root: Path, result: SourceLookupResult) -> dict[str, object]:
    source = result.source
    return {
        "source_id": source.source_id,
        "title": source.title,
        "source_type": source.source_type,
        "status": source.status,
        "source_ref": canonical_source_ref(source),
        "source_ref_kind": source.source_ref_kind,
        "original_path": source.original_path,
        "checksum": source.checksum,
        "manifest_path": result.manifest_path.relative_to(root).as_posix(),
        "queue_job_id": ingest_job_id(source.source_id),
        "linked_pages": source.linked_pages,
    }
