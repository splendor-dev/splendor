"""Source lifecycle, lookup, and freshness command helpers."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, replace
from pathlib import Path

from splendor.commands.ingest import enqueue_ingest_job, is_ingest_current
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import SourceRecord
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import ingest_job_id
from splendor.state.source_compat import (
    canonical_source_ref,
    effective_materialized_path,
    effective_storage_mode,
)
from splendor.state.source_registry import (
    RegisteredSource,
    load_source_record,
    register_source,
    resolve_manifest_storage_path,
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


@dataclass(frozen=True)
class SourceFreshnessItem:
    source: SourceRecord
    manifest_path: Path
    canonical_path: str
    status: str
    manifest_checksum: str
    current_checksum: str | None
    message: str
    next_commands: list[str]


@dataclass(frozen=True)
class SourceFreshnessResult:
    total: int
    unchanged: int
    changed: int
    missing: int
    unsupported: int
    historical: int
    sources: list[SourceFreshnessItem]
    report_path: str | None = None


def list_sources(root: Path) -> list[SourceLookupResult]:
    layout = resolve_layout(root, load_config(root))
    results = [
        SourceLookupResult(source=load_source_record(path), manifest_path=path)
        for path in sorted(layout.source_records_dir.glob("*.json"))
    ]
    return sorted(results, key=_lookup_sort_key)


def scan_source_freshness(root: Path) -> SourceFreshnessResult:
    lookup_results = list_sources(root)
    workspace_groups: dict[str, list[SourceLookupResult]] = {}
    items_by_source_id: dict[str, SourceFreshnessItem] = {}

    for result in lookup_results:
        source = result.source
        if source.source_ref_kind == "workspace_path" and source.source_ref:
            workspace_groups.setdefault(source.source_ref, []).append(result)
            continue
        items_by_source_id[source.source_id] = _freshness_item(root, result)

    for grouped_results in workspace_groups.values():
        for item in _workspace_freshness_items(root, grouped_results):
            items_by_source_id[item.source.source_id] = item

    items = [items_by_source_id[result.source.source_id] for result in lookup_results]
    return SourceFreshnessResult(
        total=len(items),
        unchanged=sum(1 for item in items if item.status == "unchanged"),
        changed=sum(1 for item in items if item.status == "changed"),
        missing=sum(1 for item in items if item.status == "missing"),
        unsupported=sum(1 for item in items if item.status == "unsupported"),
        historical=sum(1 for item in items if item.status == "historical"),
        sources=items,
    )


def lookup_sources(root: Path, query: str | None = None) -> list[SourceLookupResult]:
    results = list_sources(root)
    if query is None or not query.strip():
        return results
    needle = query.strip().casefold()
    return [result for result in results if _matches_source(result.source, needle)]


def resolve_source_query(root: Path, query: str) -> SourceLookupResult:
    return _select_source_query_candidate(root, query)


def resolve_source_query_matches(root: Path, query: str) -> list[SourceLookupResult]:
    matches = lookup_sources(root, query)
    if not matches:
        label = "source ID" if query.startswith("src-") else "source"
        msg = f"Unknown {label}: {query}"
        raise FileNotFoundError(msg)

    exact_id_matches = [match for match in matches if match.source.source_id == query]
    if exact_id_matches:
        return exact_id_matches

    exact_ref_matches = [
        match
        for match in matches
        if canonical_source_ref(match.source) == query
        or (match.source.original_path is not None and match.source.original_path == query)
    ]
    if exact_ref_matches:
        return sorted(exact_ref_matches, key=_latest_source_sort_key, reverse=True)

    exact_matches = [
        match for match in matches if match.source.title.casefold() == query.casefold()
    ]
    if exact_matches:
        refs = {canonical_source_ref(match.source) for match in exact_matches}
        if len(refs) == 1:
            return sorted(exact_matches, key=_latest_source_sort_key, reverse=True)

    return [_select_source_query_candidate(root, query)]


def _select_source_query_candidate(root: Path, query: str) -> SourceLookupResult:
    matches = lookup_sources(root, query)
    exact_matches = [
        match
        for match in matches
        if match.source.source_id == query
        or match.source.title.casefold() == query.casefold()
        or canonical_source_ref(match.source) == query
        or (match.source.original_path is not None and match.source.original_path == query)
    ]
    candidates = exact_matches or matches
    if not candidates:
        label = "source ID" if query.startswith("src-") else "source"
        msg = f"Unknown {label}: {query}"
        raise FileNotFoundError(msg)
    return _select_refresh_candidate(query, candidates)


def source_commit_capture_intent(source: SourceRecord) -> bool | None:
    if source.source_commit_capture is not None:
        return source.source_commit_capture
    if source.source_commit is not None:
        return True
    return None


def refresh_source(root: Path, source_query: str) -> SourceRefreshResult:
    requested_match = resolve_source_query(root, source_query)

    requested = requested_match.source
    current_path = _refreshable_source_path(root, requested)
    current_checksum = sha256_file(current_path)
    changed = current_checksum != requested.checksum

    if changed:
        refreshed = register_source(
            root,
            current_path,
            storage_mode=requested.storage_mode,
            capture_source_commit=source_commit_capture_intent(requested),
            source_class=requested.source_class,
            source_labels=requested.source_labels,
            discovered_by=requested.discovered_by,
        )
    else:
        refreshed = RegisteredSource(
            record=requested,
            manifest_path=requested_match.manifest_path,
            stored_path=_existing_materialized_path(root, requested),
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


def _select_refresh_candidate(
    source_query: str, candidates: list[SourceLookupResult]
) -> SourceLookupResult:
    if len(candidates) == 1:
        return candidates[0]

    candidates_by_ref: dict[str, list[SourceLookupResult]] = {}
    for candidate in candidates:
        candidates_by_ref.setdefault(canonical_source_ref(candidate.source), []).append(candidate)

    if len(candidates_by_ref) == 1:
        return max(candidates, key=_latest_source_sort_key)

    ids = ", ".join(candidate.source.source_id for candidate in candidates[:5])
    suffix = "" if len(candidates) <= 5 else ", ..."
    msg = f"Source lookup is ambiguous for {source_query!r}: {ids}{suffix}"
    raise ValueError(msg)


def _latest_source_sort_key(result: SourceLookupResult) -> tuple[str, str]:
    return (result.source.added_at, result.source.source_id)


def _existing_materialized_path(root: Path, source: SourceRecord) -> Path | None:
    stored_path_value = effective_materialized_path(source)
    if stored_path_value is None:
        return None
    return resolve_manifest_storage_path(root, stored_path_value)


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


def write_source_freshness_report(
    root: Path, result: SourceFreshnessResult, report_path: Path
) -> SourceFreshnessResult:
    expanded_report_path = report_path.expanduser()
    resolved_report_path = (
        expanded_report_path
        if expanded_report_path.is_absolute()
        else Path.cwd() / expanded_report_path
    )
    resolved_report_path.parent.mkdir(parents=True, exist_ok=True)
    result_with_report_path = replace(result, report_path=resolved_report_path.as_posix())
    resolved_report_path.write_text(
        render_source_freshness_json(root, result_with_report_path) + "\n",
        encoding="utf-8",
    )
    return result_with_report_path


def render_source_freshness_json(root: Path, result: SourceFreshnessResult) -> str:
    return json.dumps(
        {
            "total": result.total,
            "unchanged": result.unchanged,
            "changed": result.changed,
            "missing": result.missing,
            "unsupported": result.unsupported,
            "historical": result.historical,
            "report_path": result.report_path,
            "sources": [_freshness_payload(root, item) for item in result.sources],
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
    legacy_path = source.path if source.source_ref is None and source.storage_path is None else ""
    haystacks = [
        source.source_id,
        source.title,
        canonical_source_ref(source),
        legacy_path,
        source.original_path or "",
    ]
    return any(needle in value.casefold() for value in haystacks)


def _refreshable_source_path(root: Path, source: SourceRecord) -> Path:
    if source.source_ref_kind == "workspace_path" and source.source_ref:
        return resolve_workspace_path(root, source.source_ref, context="Workspace source")
    if source.source_ref_kind == "external_path" and source.source_ref:
        return Path(source.source_ref).expanduser().resolve()
    if source.source_ref is None and source.original_path:
        legacy_path = Path(source.original_path).expanduser()
        if legacy_path.is_absolute():
            return legacy_path.resolve()
        return resolve_workspace_path(root, source.original_path, context="Legacy workspace source")
    msg = (
        "Only workspace-backed, external-path, and original_path-backed legacy sources can be "
        f"refreshed by canonical source reference: {source.source_id}. Re-register the source "
        "with `splendor add-source <path>` to create a refreshable source_ref."
    )
    raise ValueError(msg)


def _freshness_item(root: Path, result: SourceLookupResult) -> SourceFreshnessItem:
    source = result.source
    canonical_path = canonical_source_ref(source)
    if source.source_ref_kind != "workspace_path" or not source.source_ref:
        return SourceFreshnessItem(
            source=source,
            manifest_path=result.manifest_path,
            canonical_path=canonical_path,
            status="unsupported",
            manifest_checksum=source.checksum,
            current_checksum=None,
            message=(
                "freshness preview supports only workspace-backed canonical source refs in this "
                "release"
            ),
            next_commands=[],
        )

    return _workspace_freshness_items(root, [result])[0]


def _workspace_freshness_items(
    root: Path, results: list[SourceLookupResult]
) -> list[SourceFreshnessItem]:
    source_ref = results[0].source.source_ref
    if source_ref is None:
        msg = "Workspace freshness group is missing source_ref"
        raise ValueError(msg)

    source_path = resolve_workspace_path(root, source_ref, context="Workspace source")
    if not source_path.exists():
        return [
            SourceFreshnessItem(
                source=result.source,
                manifest_path=result.manifest_path,
                canonical_path=source_ref,
                status="missing",
                manifest_checksum=result.source.checksum,
                current_checksum=None,
                message="canonical workspace source file is missing",
                next_commands=[f"splendor source lookup {result.source.source_id}"],
            )
            for result in results
        ]
    if not source_path.is_file():
        return [
            SourceFreshnessItem(
                source=result.source,
                manifest_path=result.manifest_path,
                canonical_path=source_ref,
                status="unsupported",
                manifest_checksum=result.source.checksum,
                current_checksum=None,
                message="canonical workspace source ref does not resolve to a file",
                next_commands=[],
            )
            for result in results
        ]

    layout = resolve_layout(root, load_config(root))
    current_checksum = sha256_file(source_path)
    latest_result = max(results, key=_latest_source_sort_key)

    items = []
    for result in results:
        source = result.source
        if source.source_id != latest_result.source.source_id:
            items.append(
                SourceFreshnessItem(
                    source=source,
                    manifest_path=result.manifest_path,
                    canonical_path=source_ref,
                    status="historical",
                    manifest_checksum=source.checksum,
                    current_checksum=current_checksum,
                    message=(
                        "older source version for this workspace path; "
                        "latest manifest is freshness target"
                    ),
                    next_commands=[],
                )
            )
            continue

        if source.checksum == current_checksum:
            ingest_current = is_ingest_current(root, layout, source)
            items.append(
                SourceFreshnessItem(
                    source=source,
                    manifest_path=result.manifest_path,
                    canonical_path=source_ref,
                    status="unchanged",
                    manifest_checksum=source.checksum,
                    current_checksum=current_checksum,
                    message=(
                        "canonical workspace source matches manifest checksum"
                        if ingest_current
                        else (
                            "canonical workspace source matches manifest checksum "
                            "but ingest is not current"
                        )
                    ),
                    next_commands=[
                        (
                            f"splendor wiki suggest {source.source_id}"
                            if ingest_current
                            else _source_ingest_command(source.source_id)
                        )
                    ],
                )
            )
            continue

        items.append(
            SourceFreshnessItem(
                source=source,
                manifest_path=result.manifest_path,
                canonical_path=source_ref,
                status="changed",
                manifest_checksum=source.checksum,
                current_checksum=current_checksum,
                message="canonical workspace source differs from latest manifest checksum",
                next_commands=[
                    _source_refresh_command(source_ref),
                    "splendor ingest --pending",
                ],
            )
        )
    return items


def _source_ingest_command(source_id: str) -> str:
    return f"splendor ingest {shlex.quote(source_id)}"


def _source_refresh_command(source_ref: str) -> str:
    return f"splendor source refresh {shlex.quote(source_ref)}"


def _freshness_payload(root: Path, item: SourceFreshnessItem) -> dict[str, object]:
    source = item.source
    return {
        "path": item.canonical_path,
        "status": item.status,
        "source_id": source.source_id,
        "title": source.title,
        "source_ref": canonical_source_ref(source),
        "source_ref_kind": source.source_ref_kind,
        "manifest_checksum": item.manifest_checksum,
        "current_checksum": item.current_checksum,
        "manifest_path": item.manifest_path.relative_to(root).as_posix(),
        "message": item.message,
        "next_commands": item.next_commands,
    }


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
