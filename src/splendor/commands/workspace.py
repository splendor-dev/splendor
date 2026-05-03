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
from splendor.state.source_compat import canonical_source_ref, effective_logical_id


@dataclass(frozen=True)
class WorkspaceRefreshResult:
    initial_freshness: SourceFreshnessResult
    final_freshness: SourceFreshnessResult
    refreshed: list[SourceRefreshResult]
    ingest: DrainResult | None
    index: WikiIndexRebuildResult | None


def refresh_workspace(
    root: Path,
    *,
    changed: bool,
    ingest: bool = False,
    rebuild_index: bool = False,
) -> WorkspaceRefreshResult:
    if not changed:
        msg = "workspace refresh requires --changed in this release"
        raise ValueError(msg)
    if rebuild_index and not ingest:
        msg = "workspace refresh --rebuild-index requires --ingest"
        raise ValueError(msg)

    initial_freshness = scan_source_freshness(root)
    _raise_if_missing_active_workspace_sources(initial_freshness)
    changed_items = [item for item in initial_freshness.sources if item.status == "changed"]
    refreshed = [_refresh_changed_item(root, item) for item in changed_items]

    ingest_result = _drain_refreshed_ingest_jobs(root, refreshed) if ingest else None
    index_result = None
    if rebuild_index and (ingest_result is None or ingest_result.failed == 0):
        index_result = rebuild_wiki_index(root)
    final_freshness = scan_source_freshness(root)

    return WorkspaceRefreshResult(
        initial_freshness=initial_freshness,
        final_freshness=final_freshness,
        refreshed=refreshed,
        ingest=ingest_result,
        index=index_result,
    )


def render_workspace_refresh_json(root: Path, result: WorkspaceRefreshResult) -> str:
    return json.dumps(
        {
            "initial_freshness": _freshness_counts(result.initial_freshness),
            "final_freshness": _freshness_counts(result.final_freshness),
            "refreshed": [_refresh_payload(root, item) for item in result.refreshed],
            "ingest": None if result.ingest is None else _ingest_payload(root, result.ingest),
            "index": None if result.index is None else asdict(result.index),
        },
        indent=2,
    )


def _refresh_changed_item(root: Path, item: SourceFreshnessItem) -> SourceRefreshResult:
    return refresh_source(root, item.canonical_path)


def _raise_if_missing_active_workspace_sources(result: SourceFreshnessResult) -> None:
    missing_paths = sorted(
        {
            item.canonical_path
            for item in result.sources
            if item.status == "missing" and item.source.superseded_by is None
        }
    )
    if not missing_paths:
        return
    joined = ", ".join(missing_paths)
    msg = f"workspace refresh cannot continue with missing curated sources: {joined}"
    raise FileNotFoundError(msg)


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
