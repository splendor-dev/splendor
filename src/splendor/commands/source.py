"""Source lifecycle, lookup, and freshness command helpers."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, replace
from pathlib import Path

from splendor import __version__
from splendor.commands.ingest import (
    enqueue_ingest_job,
    is_ingest_current,
    preflight_enqueue_ingest_job,
    run_ingest_job,
)
from splendor.commands.mutation import mutation_contract, mutation_record
from splendor.config import load_config
from splendor.ingest_dispatch import SUPPORTED_SOURCE_TYPES
from splendor.layout import resolve_layout
from splendor.schemas import SourceRecord
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import ingest_job_id
from splendor.state.source_compat import (
    canonical_source_ref,
    effective_aliases,
    effective_logical_id,
    effective_materialized_path,
    effective_storage_mode,
    logical_source_id_for_ref,
)
from splendor.state.source_pointer import pointer_artifact_path
from splendor.state.source_registry import (
    RegisteredSource,
    load_source_record,
    manifest_original_path,
    register_source,
    resolve_manifest_storage_path,
    write_source_record,
)
from splendor.utils.hashing import sha256_file
from splendor.utils.ids import stable_source_id
from splendor.utils.time import utc_now_iso


@dataclass(frozen=True)
class SourceLookupResult:
    source: SourceRecord
    manifest_path: Path


@dataclass(frozen=True)
class SourceRefreshResult:
    requested: SourceRecord
    requested_manifest_path: Path
    refreshed: RegisteredSource
    changed: bool
    queued: bool
    queue_path: Path | None
    message: str
    applied: bool = True


@dataclass(frozen=True)
class SourcePathUpdateResult:
    source: SourceRecord
    manifest_path: Path
    old_path: str
    new_path: str
    status: str
    manifest_checksum: str
    current_checksum: str
    checksum_matches: bool
    updated: bool
    queue_path: Path | None
    next_commands: list[str]
    applied: bool = True
    selector: str | None = None


@dataclass(frozen=True)
class SourceReconcileUpdate:
    source: SourceRecord
    manifest_path: Path
    before_supersedes: list[str]
    after_supersedes: list[str]
    before_superseded_by: str | None
    after_superseded_by: str | None


@dataclass(frozen=True)
class SourceReconcileResult:
    applied: bool
    selector: str
    current_selector: str | None
    canonical_ref: str
    current: SourceRecord
    current_manifest_path: Path
    active_before: list[SourceRecord]
    updates: list[SourceReconcileUpdate]


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


@dataclass(frozen=True)
class StaleIngestRefresh:
    requested_source_id: str
    refreshed_source_id: str | None
    source_ref: str
    changed: bool | None
    queued: bool
    queue_path: Path | None
    status: str
    message: str


@dataclass(frozen=True)
class StaleIngestRun:
    source_id: str
    outcome: str
    message: str
    queue_path: Path | None = None
    run_id: str | None = None
    page_path: Path | None = None


@dataclass(frozen=True)
class StaleIngestResult:
    status: str
    initial_freshness: SourceFreshnessResult
    final_freshness: SourceFreshnessResult
    missing: list[SourceFreshnessItem]
    refreshed: list[StaleIngestRefresh]
    ingest: list[StaleIngestRun]
    processed: int
    succeeded: int
    failed: int
    skipped: int


def _dedupe_aliases(aliases: list[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias and alias not in seen:
            seen.add(alias)
            deduped.append(alias)
    return deduped


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


def resolve_source_query_exact(root: Path, query: str) -> SourceLookupResult:
    matches = list_sources(root)
    exact_id_matches = [match for match in matches if match.source.source_id == query]
    if exact_id_matches:
        return exact_id_matches[0]

    exact_identity_matches = [
        match
        for match in matches
        if canonical_source_ref(match.source) == query
        or (match.source.original_path is not None and match.source.original_path == query)
        or effective_logical_id(match.source) == query
        or query in effective_aliases(match.source)
    ]
    if exact_identity_matches:
        return _select_refresh_candidate(query, exact_identity_matches)

    exact_title_matches = [
        match for match in matches if match.source.title.casefold() == query.casefold()
    ]
    if exact_title_matches:
        return _select_refresh_candidate(query, exact_title_matches)

    label = "source ID" if query.startswith("src-") else "source"
    msg = f"Unknown {label}: {query}"
    raise FileNotFoundError(msg)


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
        or effective_logical_id(match.source) == query
        or query in effective_aliases(match.source)
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
        or effective_logical_id(match.source) == query
        or query in effective_aliases(match.source)
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


def refresh_source(root: Path, source_query: str, *, apply: bool = True) -> SourceRefreshResult:
    requested_match = resolve_source_query(root, source_query)

    requested = requested_match.source
    current_path = _refreshable_source_path(root, requested)
    current_checksum = sha256_file(current_path)
    changed = current_checksum != requested.checksum
    layout = resolve_layout(root, load_config(root))

    if not apply:
        refreshed = _preview_refreshed_registration(
            root,
            layout=layout,
            requested_match=requested_match,
            current_path=current_path,
            current_checksum=current_checksum,
            changed=changed,
        )
        queued = not is_ingest_current(root, layout, refreshed.record)
        queue_path = (
            preflight_enqueue_ingest_job(
                root,
                refreshed.record.source_id,
                require_manifest=refreshed.manifest_path.exists(),
            )
            if queued
            else None
        )
        message = (
            "would queue ingest with --apply"
            if queued
            else "source is already ingested for the current pipeline version"
        )
        return SourceRefreshResult(
            requested=requested,
            requested_manifest_path=requested_match.manifest_path,
            refreshed=refreshed,
            changed=changed,
            queued=queued,
            queue_path=queue_path,
            message=message,
            applied=False,
        )

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
        refreshed = _record_source_supersession(
            requested_match=requested_match,
            refreshed=refreshed,
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

    if is_ingest_current(root, layout, refreshed.record):
        return SourceRefreshResult(
            requested=requested,
            requested_manifest_path=requested_match.manifest_path,
            refreshed=refreshed,
            changed=changed,
            queued=False,
            queue_path=None,
            message="source is already ingested for the current pipeline version",
            applied=True,
        )

    queue_path = enqueue_ingest_job(root, refreshed.record.source_id)
    return SourceRefreshResult(
        requested=requested,
        requested_manifest_path=requested_match.manifest_path,
        refreshed=refreshed,
        changed=changed,
        queued=True,
        queue_path=queue_path,
        message="queued ingest",
        applied=True,
    )


def _preview_refreshed_registration(
    root: Path,
    *,
    layout,
    requested_match: SourceLookupResult,
    current_path: Path,
    current_checksum: str,
    changed: bool,
) -> RegisteredSource:
    requested = requested_match.source
    if not changed:
        return RegisteredSource(
            record=requested,
            manifest_path=requested_match.manifest_path,
            stored_path=_existing_materialized_path(root, requested),
            storage_mode=effective_storage_mode(requested),
            source_ref=canonical_source_ref(requested),
            copied=False,
            already_registered=True,
        )

    source_id = stable_source_id(current_checksum)
    manifest_path = layout.source_records_dir / f"{source_id}.json"
    if manifest_path.exists():
        existing = load_source_record(manifest_path)
        record = existing
        if existing.source_id != requested.source_id:
            supersedes = _dedupe_aliases([*existing.supersedes, requested.source_id])
            update_fields: dict[str, object] = {"supersedes": supersedes}
            if existing.superseded_by is not None:
                update_fields["superseded_by"] = None
            record = SourceRecord.model_validate(existing.model_dump(mode="json") | update_fields)
        return RegisteredSource(
            record=record,
            manifest_path=manifest_path,
            stored_path=_existing_materialized_path(root, record),
            storage_mode=effective_storage_mode(record),
            source_ref=canonical_source_ref(record),
            copied=False,
            already_registered=True,
        )

    try:
        source_ref = current_path.relative_to(root.resolve()).as_posix()
        source_ref_kind = "workspace_path"
    except ValueError:
        source_ref = str(current_path)
        source_ref_kind = "external_path"
    storage_mode = effective_storage_mode(requested)
    stored_path = None
    if storage_mode in {"copy", "symlink"}:
        stored_path = layout.raw_sources_dir / source_id / current_path.name
    elif storage_mode == "pointer":
        stored_path = pointer_artifact_path(layout, source_id)

    stored_ref = None if stored_path is None else stored_path.relative_to(root).as_posix()
    record = SourceRecord(
        source_id=source_id,
        title=current_path.stem.replace("_", " ").replace("-", " ").strip() or current_path.name,
        source_type=current_path.suffix.lstrip(".") or "file",
        path=stored_ref or source_ref,
        checksum=current_checksum,
        added_at=utc_now_iso(),
        pipeline_version=__version__,
        original_path=manifest_original_path(root, current_path),
        source_ref=source_ref,
        source_ref_kind=source_ref_kind,
        storage_mode=storage_mode,
        storage_path=stored_ref,
        materialized_at=utc_now_iso() if stored_ref is not None else None,
        logical_id=effective_logical_id(requested),
        aliases=_dedupe_aliases([*requested.aliases, source_ref]),
        supersedes=[requested.source_id] if requested.source_id != source_id else [],
        source_commit_capture=source_commit_capture_intent(requested),
        source_class=requested.source_class,
        source_labels=list(requested.source_labels),
        discovered_by=requested.discovered_by,
    )
    return RegisteredSource(
        record=record,
        manifest_path=manifest_path,
        stored_path=stored_path,
        storage_mode=storage_mode,
        source_ref=source_ref,
        copied=storage_mode == "copy",
        already_registered=False,
    )


def update_source_path(
    root: Path,
    source_query: str,
    new_path: Path,
    *,
    force: bool = False,
    apply: bool = True,
) -> SourcePathUpdateResult:
    source_match = resolve_source_query_exact(root, source_query)
    source = source_match.source
    old_path = canonical_source_ref(source)

    if source.superseded_by is not None:
        msg = (
            "Cannot update the path for a superseded source version: "
            f"{source.source_id}. Select the active source version instead."
        )
        raise ValueError(msg)
    if source.source_ref_kind != "workspace_path" or source.source_ref is None:
        msg = (
            "source update-path supports only workspace-backed curated sources in this release: "
            f"{source.source_id}"
        )
        raise ValueError(msg)
    storage_mode = effective_storage_mode(source)
    if storage_mode not in {"none", "copy"}:
        msg = (
            "source update-path supports only none/copy storage for workspace-backed sources in "
            f"this release; got {storage_mode!r}"
        )
        raise ValueError(msg)

    old_target = resolve_workspace_path(root, source.source_ref, context="Current workspace source")
    if old_target.exists() and not force:
        msg = (
            "Current workspace source path still exists; refusing to reparent a healthy source "
            f"without --force: {source.source_ref}"
        )
        raise ValueError(msg)

    target = _source_path_update_target(root, new_path)
    source_type = target.suffix.lstrip(".") or "file"
    if source_type not in SUPPORTED_SOURCE_TYPES:
        msg = f"Target source type is not supported for ingestion: {source_type}"
        raise ValueError(msg)
    if source_type != source.source_type:
        msg = (
            "Target source type must match the existing source manifest: "
            f"expected {source.source_type}, got {source_type}"
        )
        raise ValueError(msg)

    new_ref = target.relative_to(root.resolve()).as_posix()
    _ensure_update_path_target_is_unambiguous(
        root,
        source_id=source.source_id,
        new_ref=new_ref,
    )

    current_checksum = sha256_file(target)
    stable_identity_ref = source.original_path or old_path
    logical_id = source.logical_id or logical_source_id_for_ref(
        stable_identity_ref, "workspace_path"
    )
    aliases = _dedupe_aliases([*source.aliases, old_path, new_ref])
    updated_fields: dict[str, object] = {
        "source_ref": new_ref,
        "source_ref_kind": "workspace_path",
        "logical_id": logical_id,
        "aliases": aliases,
    }
    if storage_mode == "none":
        updated_fields["path"] = new_ref

    checksum_matches = current_checksum == source.checksum
    if checksum_matches and source.status == "ingested":
        updated_fields["status"] = "registered"

    updated_source = SourceRecord.model_validate(source.model_dump(mode="json") | updated_fields)
    updated = updated_source != source
    if updated and apply:
        write_source_record(source_match.manifest_path, updated_source)

    queue_path = None
    if checksum_matches:
        queue_path = (
            enqueue_ingest_job(root, updated_source.source_id)
            if apply
            else preflight_enqueue_ingest_job(root, updated_source.source_id)
        )
    status = "repaired" if checksum_matches else "partial"
    if not apply:
        command = (
            "splendor source update-path "
            f"{shlex.quote(source_query)} {shlex.quote(new_ref)} --apply"
        )
        if force:
            command += " --force"
        next_commands = [command]
    elif not checksum_matches:
        next_commands = [
            f"splendor source refresh {shlex.quote(new_ref)}",
            "splendor ingest --pending --apply",
            "splendor source freshness",
        ]
    else:
        next_commands = [
            "splendor ingest --pending --apply",
            "splendor source freshness",
        ]
    return SourcePathUpdateResult(
        source=updated_source,
        manifest_path=source_match.manifest_path,
        old_path=old_path,
        new_path=new_ref,
        status=status,
        manifest_checksum=updated_source.checksum,
        current_checksum=current_checksum,
        checksum_matches=checksum_matches,
        updated=updated,
        queue_path=queue_path,
        next_commands=next_commands,
        applied=apply,
        selector=source_query,
    )


def reconcile_sources(
    root: Path,
    selector: str,
    *,
    current_selector: str | None = None,
    apply: bool = False,
) -> SourceReconcileResult:
    group = _reconcile_group(root, selector)
    canonical_ref = canonical_source_ref(group[0].source)
    active_group = [result for result in group if result.source.superseded_by is None]
    if not active_group:
        msg = f"No active source versions found for canonical source ref: {canonical_ref}"
        raise ValueError(msg)

    current_match = (
        _current_reconcile_match(root, current_selector, canonical_ref)
        if current_selector is not None
        else _default_reconcile_current(selector, group, active_group)
    )
    current = current_match.source
    if current.superseded_by is not None:
        msg = f"Current source version is already superseded: {current.source_id}"
        raise ValueError(msg)

    superseded_ids = _reconcile_superseded_ids(group, current)
    updates: list[SourceReconcileUpdate] = []
    for result in sorted(group, key=lambda item: item.source.source_id):
        source = result.source
        if source.source_id not in superseded_ids or source.superseded_by == current.source_id:
            continue
        updates.append(
            SourceReconcileUpdate(
                source=source,
                manifest_path=result.manifest_path,
                before_supersedes=list(source.supersedes),
                after_supersedes=list(source.supersedes),
                before_superseded_by=source.superseded_by,
                after_superseded_by=current.source_id,
            )
        )

    current_supersedes = _dedupe_aliases([*current.supersedes, *superseded_ids])
    if current_supersedes != current.supersedes:
        updates.append(
            SourceReconcileUpdate(
                source=current,
                manifest_path=current_match.manifest_path,
                before_supersedes=list(current.supersedes),
                after_supersedes=current_supersedes,
                before_superseded_by=current.superseded_by,
                after_superseded_by=None,
            )
        )

    validated_updates = [
        (
            update.manifest_path,
            SourceRecord.model_validate(
                update.source.model_dump(mode="json")
                | {
                    "supersedes": update.after_supersedes,
                    "superseded_by": update.after_superseded_by,
                }
            ),
        )
        for update in updates
    ]
    if apply:
        for manifest_path, updated in validated_updates:
            write_source_record(manifest_path, updated)

    return SourceReconcileResult(
        applied=apply,
        selector=selector,
        current_selector=current_selector,
        canonical_ref=canonical_ref,
        current=current,
        current_manifest_path=current_match.manifest_path,
        active_before=[
            result.source for result in sorted(active_group, key=_latest_source_sort_key)
        ],
        updates=updates,
    )


def ingest_changed_sources(root: Path) -> StaleIngestResult:
    initial_freshness = scan_source_freshness(root)
    missing_items = [item for item in initial_freshness.sources if item.status == "missing"]
    changed_items = [item for item in initial_freshness.sources if item.status == "changed"]

    refreshed_items: list[StaleIngestRefresh] = []
    ingest_items: list[StaleIngestRun] = []
    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for item in changed_items:
        try:
            refresh = refresh_source(root, item.source.source_id)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            failed += 1
            refreshed_items.append(
                StaleIngestRefresh(
                    requested_source_id=item.source.source_id,
                    refreshed_source_id=None,
                    source_ref=item.canonical_path,
                    changed=None,
                    queued=False,
                    queue_path=None,
                    status="failed",
                    message=str(exc),
                )
            )
            continue

        refreshed_items.append(
            StaleIngestRefresh(
                requested_source_id=refresh.requested.source_id,
                refreshed_source_id=refresh.refreshed.record.source_id,
                source_ref=canonical_source_ref(refresh.refreshed.record),
                changed=refresh.changed,
                queued=refresh.queued,
                queue_path=refresh.queue_path,
                status="queued" if refresh.queued else "skipped",
                message=refresh.message,
            )
        )

        if refresh.queue_path is None:
            skipped += 1
            ingest_items.append(
                StaleIngestRun(
                    source_id=refresh.refreshed.record.source_id,
                    outcome="skipped",
                    message=refresh.message,
                )
            )
            continue

        try:
            ingest_result = run_ingest_job(root, refresh.queue_path)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            processed += 1
            failed += 1
            ingest_items.append(
                StaleIngestRun(
                    source_id=refresh.refreshed.record.source_id,
                    queue_path=refresh.queue_path,
                    outcome="failed",
                    message=str(exc),
                )
            )
            continue

        if ingest_result.no_op:
            skipped += 1
            ingest_items.append(
                StaleIngestRun(
                    source_id=ingest_result.source_id,
                    queue_path=refresh.queue_path,
                    outcome="skipped",
                    message="already ingested for the current pipeline version",
                )
            )
            continue

        processed += 1
        succeeded += 1
        ingest_items.append(
            StaleIngestRun(
                source_id=ingest_result.source_id,
                queue_path=refresh.queue_path,
                outcome="succeeded",
                message=f"run {ingest_result.run_id}",
                run_id=ingest_result.run_id,
                page_path=ingest_result.page_path,
            )
        )

    final_freshness = scan_source_freshness(root) if changed_items else initial_freshness
    if failed:
        status = "failed"
    elif missing_items and (processed or succeeded or skipped):
        status = "partial"
    elif missing_items:
        status = "blocked"
    elif not changed_items:
        status = "no-op"
    else:
        status = "succeeded"

    return StaleIngestResult(
        status=status,
        initial_freshness=initial_freshness,
        final_freshness=final_freshness,
        missing=missing_items,
        refreshed=refreshed_items,
        ingest=ingest_items,
        processed=processed,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
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


def _reconcile_group(root: Path, selector: str) -> list[SourceLookupResult]:
    matches = resolve_source_query_matches(root, selector)
    refs = {canonical_source_ref(match.source) for match in matches}
    if len(refs) != 1:
        ids = ", ".join(match.source.source_id for match in matches[:5])
        suffix = "" if len(matches) <= 5 else ", ..."
        msg = f"Source reconcile selector is ambiguous for {selector!r}: {ids}{suffix}"
        raise ValueError(msg)
    canonical_ref = next(iter(refs))
    group = [
        result
        for result in list_sources(root)
        if canonical_source_ref(result.source) == canonical_ref
    ]
    return sorted(group, key=_latest_source_sort_key)


def _default_reconcile_current(
    selector: str,
    group: list[SourceLookupResult],
    active_group: list[SourceLookupResult],
) -> SourceLookupResult:
    exact_id_matches = [result for result in group if result.source.source_id == selector]
    if exact_id_matches:
        return exact_id_matches[0]
    return max(active_group, key=_latest_source_sort_key)


def _current_reconcile_match(
    root: Path, current_selector: str | None, canonical_ref: str
) -> SourceLookupResult:
    if current_selector is None:
        msg = "--current requires a source selector"
        raise ValueError(msg)
    current_match = _resolve_reconcile_current_exact(root, current_selector)
    if canonical_source_ref(current_match.source) != canonical_ref:
        msg = (
            "Current source version must share the selected canonical source ref: "
            f"expected {canonical_ref}, got {canonical_source_ref(current_match.source)}"
        )
        raise ValueError(msg)
    return current_match


def _resolve_reconcile_current_exact(root: Path, selector: str) -> SourceLookupResult:
    matches = list_sources(root)
    exact_id_matches = [match for match in matches if match.source.source_id == selector]
    if exact_id_matches:
        return exact_id_matches[0]

    exact_identity_matches = [
        match
        for match in matches
        if canonical_source_ref(match.source) == selector
        or (match.source.original_path is not None and match.source.original_path == selector)
        or effective_logical_id(match.source) == selector
        or selector in effective_aliases(match.source)
    ]
    if exact_identity_matches:
        return _single_reconcile_current_match(selector, exact_identity_matches)

    exact_title_matches = [
        match for match in matches if match.source.title.casefold() == selector.casefold()
    ]
    if exact_title_matches:
        return _single_reconcile_current_match(selector, exact_title_matches)

    label = "source ID" if selector.startswith("src-") else "source"
    msg = f"Unknown {label}: {selector}"
    raise FileNotFoundError(msg)


def _single_reconcile_current_match(
    selector: str, matches: list[SourceLookupResult]
) -> SourceLookupResult:
    if len(matches) == 1:
        return matches[0]
    ids = ", ".join(match.source.source_id for match in matches[:5])
    suffix = "" if len(matches) <= 5 else ", ..."
    msg = f"Current source selector is ambiguous for {selector!r}: {ids}{suffix}"
    raise ValueError(msg)


def _reconcile_superseded_ids(group: list[SourceLookupResult], current: SourceRecord) -> list[str]:
    current_supersedes = set(current.supersedes)
    target_ids = {
        result.source.source_id
        for result in group
        if result.source.source_id != current.source_id
        and (
            result.source.superseded_by is None
            or result.source.superseded_by == current.source_id
            or result.source.source_id in current_supersedes
        )
    }
    return [
        result.source.source_id
        for result in sorted(group, key=_latest_source_sort_key)
        if result.source.source_id in target_ids
    ]


def _latest_source_sort_key(result: SourceLookupResult) -> tuple[str, str]:
    return (result.source.added_at, result.source.source_id)


def _existing_materialized_path(root: Path, source: SourceRecord) -> Path | None:
    stored_path_value = effective_materialized_path(source)
    if stored_path_value is None:
        return None
    return resolve_manifest_storage_path(root, stored_path_value)


def _record_source_supersession(
    *,
    requested_match: SourceLookupResult,
    refreshed: RegisteredSource,
) -> RegisteredSource:
    requested = requested_match.source
    current = refreshed.record
    if current.source_id == requested.source_id:
        return refreshed

    if requested.superseded_by != current.source_id:
        updated_requested = SourceRecord.model_validate(
            requested.model_dump(mode="json") | {"superseded_by": current.source_id}
        )
        write_source_record(requested_match.manifest_path, updated_requested)

    current_supersedes = list(current.supersedes)
    if requested.source_id not in current_supersedes:
        current_supersedes.append(requested.source_id)

    updated_current_fields: dict[str, object] = {}
    if current.superseded_by is not None:
        updated_current_fields["superseded_by"] = None
    if current_supersedes != current.supersedes:
        updated_current_fields["supersedes"] = current_supersedes
    if not updated_current_fields:
        return refreshed

    updated_current = SourceRecord.model_validate(
        current.model_dump(mode="json") | updated_current_fields
    )
    write_source_record(refreshed.manifest_path, updated_current)
    return replace(refreshed, record=updated_current)


def render_source_lookup_json(root: Path, results: list[SourceLookupResult]) -> str:
    return json.dumps(
        {"sources": [_source_payload(root, result) for result in results]},
        indent=2,
    )


def render_source_refresh_json(root: Path, result: SourceRefreshResult) -> str:
    mutation_records = source_refresh_written_records(root, result)
    return json.dumps(
        {
            "requested_source_id": result.requested.source_id,
            "requested_logical_id": effective_logical_id(result.requested),
            "source_id": result.refreshed.record.source_id,
            "logical_id": effective_logical_id(result.refreshed.record),
            "supersedes": result.refreshed.record.supersedes,
            "superseded_by": result.refreshed.record.superseded_by,
            "requested_superseded_by": (
                result.refreshed.record.source_id
                if result.changed
                and result.refreshed.record.source_id != result.requested.source_id
                else result.requested.superseded_by
            ),
            "changed": result.changed,
            "queued": result.queued,
            "queue_path": (
                None
                if result.queue_path is None
                else result.queue_path.relative_to(root).as_posix()
            ),
            "message": result.message,
            "mutation": mutation_contract(
                mode="apply" if result.applied else "preview",
                planned=[] if result.applied else mutation_records,
                written=mutation_records if result.applied else [],
            ),
        },
        indent=2,
    )


def render_source_path_update_json(root: Path, result: SourcePathUpdateResult) -> str:
    mutation_records = source_path_update_mutation_records(root, result)
    return json.dumps(
        {
            "applied": result.applied,
            "source_id": result.source.source_id,
            "logical_id": effective_logical_id(result.source),
            "old_path": result.old_path,
            "new_path": result.new_path,
            "status": result.status,
            "source_ref": result.source.source_ref,
            "aliases": result.source.aliases,
            "manifest_checksum": result.manifest_checksum,
            "current_checksum": result.current_checksum,
            "checksum_matches": result.checksum_matches,
            "manifest_path": result.manifest_path.relative_to(root).as_posix(),
            "updated": result.updated,
            "queue_path": None
            if result.queue_path is None
            else result.queue_path.relative_to(root).as_posix(),
            "next_commands": result.next_commands,
            "mutation": mutation_contract(
                mode="apply" if result.applied else "preview",
                planned=[] if result.applied else mutation_records,
                written=mutation_records if result.applied else [],
            ),
        },
        indent=2,
    )


def render_source_reconcile_json(root: Path, result: SourceReconcileResult) -> str:
    mutation_records = [
        mutation_record(
            action="write",
            path=update.manifest_path.relative_to(root).as_posix(),
            kind="source_manifest",
            source_id=update.source.source_id,
        )
        for update in result.updates
    ]
    return json.dumps(
        {
            "applied": result.applied,
            "selector": result.selector,
            "current_selector": result.current_selector,
            "canonical_ref": result.canonical_ref,
            "current_source_id": result.current.source_id,
            "current_manifest_path": result.current_manifest_path.relative_to(root).as_posix(),
            "active_before": [source.source_id for source in result.active_before],
            "summary": {
                "active_before": len(result.active_before),
                "updates": len(result.updates),
            },
            "updates": [_reconcile_update_payload(root, update) for update in result.updates],
            "next_commands": source_reconcile_next_commands(result),
            "mutation": mutation_contract(
                mode="apply" if result.applied else "preview",
                planned=[] if result.applied else mutation_records,
                written=mutation_records if result.applied else [],
            ),
        },
        indent=2,
    )


def source_reconcile_next_commands(result: SourceReconcileResult) -> list[str]:
    if not result.applied and result.updates:
        command = f"splendor source reconcile {shlex.quote(result.selector)}"
        if result.current_selector is not None:
            command += f" --current {shlex.quote(result.current_selector)}"
        command += " --apply"
        return [command]
    return ["splendor lint", "splendor health"]


def source_refresh_written_records(root: Path, result: SourceRefreshResult) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    if result.changed:
        if (
            result.refreshed.storage_mode in {"copy", "pointer", "symlink"}
            and result.refreshed.stored_path is not None
        ):
            records.append(
                mutation_record(
                    action="write",
                    path=result.refreshed.stored_path.relative_to(root).as_posix(),
                    kind="source_artifact",
                    source_id=result.refreshed.record.source_id,
                )
            )
        records.append(
            mutation_record(
                action="write",
                path=result.refreshed.manifest_path.relative_to(root).as_posix(),
                kind="source_manifest",
                source_id=result.refreshed.record.source_id,
            )
        )
        if result.refreshed.record.source_id != result.requested.source_id:
            records.append(
                mutation_record(
                    action="write",
                    path=result.requested_manifest_path.relative_to(root).as_posix(),
                    kind="source_manifest",
                    source_id=result.requested.source_id,
                )
            )
    if result.queued and result.queue_path is not None:
        records.append(
            mutation_record(
                action="write",
                path=result.queue_path.relative_to(root).as_posix(),
                kind="queue_record",
                source_id=result.refreshed.record.source_id,
            )
        )
    return sorted(records, key=lambda item: (item["kind"], item["path"], item["action"]))


def source_path_update_mutation_records(
    root: Path, result: SourcePathUpdateResult
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    if result.updated:
        records.append(
            mutation_record(
                action="write",
                path=result.manifest_path.relative_to(root).as_posix(),
                kind="source_manifest",
                source_id=result.source.source_id,
            )
        )
    if result.queue_path is not None:
        records.append(
            mutation_record(
                action="write",
                path=result.queue_path.relative_to(root).as_posix(),
                kind="queue_record",
                source_id=result.source.source_id,
            )
        )
    return sorted(records, key=lambda item: (item["kind"], item["path"], item["action"]))


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


def render_stale_ingest_json(root: Path, result: StaleIngestResult) -> str:
    return json.dumps(
        {
            "status": result.status,
            "initial_freshness": _freshness_counts(result.initial_freshness),
            "final_freshness": _freshness_counts(result.final_freshness),
            "missing": [_freshness_payload(root, item) for item in result.missing],
            "refreshed": [_stale_ingest_refresh_payload(root, item) for item in result.refreshed],
            "ingest": [_stale_ingest_run_payload(root, item) for item in result.ingest],
            "summary": _stale_ingest_summary(result),
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
        effective_logical_id(source) or "",
        *effective_aliases(source),
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


def _source_path_update_target(root: Path, new_path: Path) -> Path:
    expanded = new_path.expanduser()
    candidate = expanded.resolve() if expanded.is_absolute() else (root / expanded).resolve()
    workspace_root = root.resolve()
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        msg = f"Target source path must stay inside the workspace: {new_path}"
        raise ValueError(msg) from exc
    if not candidate.exists():
        msg = f"Target source path does not exist: {new_path}"
        raise FileNotFoundError(msg)
    if not candidate.is_file():
        msg = f"Target source path must be a file: {new_path}"
        raise IsADirectoryError(msg)
    return candidate


def _ensure_update_path_target_is_unambiguous(root: Path, *, source_id: str, new_ref: str) -> None:
    conflicting = [
        result.source
        for result in list_sources(root)
        if result.source.source_id != source_id
        and result.source.superseded_by is None
        and result.source.source_ref_kind == "workspace_path"
        and result.source.source_ref == new_ref
    ]
    if conflicting:
        ids = ", ".join(source.source_id for source in conflicting[:5])
        suffix = "" if len(conflicting) <= 5 else ", ..."
        msg = f"Target source path is already curated by another active source: {ids}{suffix}"
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
    active_results = [result for result in results if result.source.superseded_by is None]
    latest_result = max(active_results or results, key=_latest_source_sort_key)

    items = []
    for result in results:
        source = result.source
        if source.superseded_by is not None or source.source_id != latest_result.source.source_id:
            items.append(
                SourceFreshnessItem(
                    source=source,
                    manifest_path=result.manifest_path,
                    canonical_path=source_ref,
                    status="historical",
                    manifest_checksum=source.checksum,
                    current_checksum=current_checksum,
                    message=(
                        "superseded source version for this workspace path; "
                        "active manifest is freshness target"
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
                    f"{_source_refresh_command(source_ref)} --apply",
                    "splendor ingest --pending --apply",
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
        "logical_id": effective_logical_id(source),
        "aliases": effective_aliases(source),
        "supersedes": source.supersedes,
        "superseded_by": source.superseded_by,
        "title": source.title,
        "source_ref": canonical_source_ref(source),
        "source_ref_kind": source.source_ref_kind,
        "manifest_checksum": item.manifest_checksum,
        "current_checksum": item.current_checksum,
        "manifest_path": item.manifest_path.relative_to(root).as_posix(),
        "message": item.message,
        "next_commands": item.next_commands,
    }


def _freshness_counts(result: SourceFreshnessResult) -> dict[str, int]:
    return {
        "total": result.total,
        "unchanged": result.unchanged,
        "changed": result.changed,
        "missing": result.missing,
        "unsupported": result.unsupported,
        "historical": result.historical,
    }


def _stale_ingest_summary(result: StaleIngestResult) -> dict[str, int]:
    return {
        "processed": result.processed,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "skipped": result.skipped,
    }


def _stale_ingest_refresh_payload(root: Path, item: StaleIngestRefresh) -> dict[str, object]:
    return {
        "requested_source_id": item.requested_source_id,
        "refreshed_source_id": item.refreshed_source_id,
        "source_ref": item.source_ref,
        "changed": item.changed,
        "queued": item.queued,
        "queue_path": None
        if item.queue_path is None
        else item.queue_path.relative_to(root).as_posix(),
        "status": item.status,
        "message": item.message,
    }


def _stale_ingest_run_payload(root: Path, item: StaleIngestRun) -> dict[str, object]:
    return {
        "source_id": item.source_id,
        "queue_path": None
        if item.queue_path is None
        else item.queue_path.relative_to(root).as_posix(),
        "outcome": item.outcome,
        "message": item.message,
        "run_id": item.run_id,
        "page_path": None
        if item.page_path is None
        else item.page_path.relative_to(root).as_posix(),
    }


def _source_payload(root: Path, result: SourceLookupResult) -> dict[str, object]:
    source = result.source
    return {
        "source_id": source.source_id,
        "logical_id": effective_logical_id(source),
        "aliases": effective_aliases(source),
        "title": source.title,
        "source_type": source.source_type,
        "status": source.status,
        "supersedes": source.supersedes,
        "superseded_by": source.superseded_by,
        "source_ref": canonical_source_ref(source),
        "source_ref_kind": source.source_ref_kind,
        "original_path": source.original_path,
        "checksum": source.checksum,
        "manifest_path": result.manifest_path.relative_to(root).as_posix(),
        "queue_job_id": ingest_job_id(source.source_id),
        "linked_pages": source.linked_pages,
    }


def _reconcile_update_payload(root: Path, update: SourceReconcileUpdate) -> dict[str, object]:
    return {
        "source_id": update.source.source_id,
        "manifest_path": update.manifest_path.relative_to(root).as_posix(),
        "before": {
            "supersedes": update.before_supersedes,
            "superseded_by": update.before_superseded_by,
        },
        "after": {
            "supersedes": update.after_supersedes,
            "superseded_by": update.after_superseded_by,
        },
    }
