"""Queue inspection and repair command helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from splendor.commands.ingest import enqueue_ingest_job, is_ingest_current, run_ingest_job
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import QueueItemRecord
from splendor.state.runtime import (
    ingest_job_id,
    load_queue_item,
    queue_item_path_for,
    source_id_from_ingest_job_id,
    write_queue_item,
)
from splendor.state.source_registry import load_source_record, manifest_path_for
from splendor.utils.time import utc_now_iso


@dataclass(frozen=True)
class QueueItemSnapshot:
    job_id: str
    job_type: str
    status: str
    created_at: str
    updated_at: str
    attempt_count: int
    max_attempts: int
    payload_ref: str
    lease_owner: str | None
    lease_expires_at: str | None
    next_attempt_at: str | None
    last_error: str | None
    source_id: str | None
    operator_state: str
    record_path: Path


@dataclass(frozen=True)
class QueueInspectResult:
    total: int
    status_counts: dict[str, int]
    items: list[QueueItemSnapshot]


@dataclass(frozen=True)
class QueueRetryResult:
    item: QueueItemSnapshot


@dataclass(frozen=True)
class RepairIngestResult:
    source_id: str
    outcome: str
    queue_path: Path | None
    run_id: str | None
    run_path: Path | None
    page_path: Path | None
    no_op: bool
    message: str


def inspect_queue(root: Path) -> QueueInspectResult:
    layout = resolve_layout(root, load_config(root))
    items = [
        _snapshot_queue_item(root, queue_path, load_queue_item(queue_path))
        for queue_path in sorted(layout.queue_dir.glob("*.json"))
    ]
    items = sorted(items, key=lambda item: (item.created_at, item.job_id))
    return QueueInspectResult(
        total=len(items),
        status_counts=dict(sorted(Counter(item.status for item in items).items())),
        items=items,
    )


def inspect_queue_job(root: Path, job_id: str) -> QueueItemSnapshot:
    layout = resolve_layout(root, load_config(root))
    queue_path = queue_item_path_for(layout, job_id)
    if not queue_path.exists():
        msg = f"Unknown queue job: {job_id}"
        raise FileNotFoundError(msg)
    return _snapshot_queue_item(root, queue_path, load_queue_item(queue_path))


def retry_queue_job(root: Path, job_id: str) -> QueueRetryResult:
    layout = resolve_layout(root, load_config(root))
    queue_path = queue_item_path_for(layout, job_id)
    if not queue_path.exists():
        msg = f"Unknown queue job: {job_id}"
        raise FileNotFoundError(msg)
    queue_item = load_queue_item(queue_path)
    reset = _reset_failed_ingest_queue_item(queue_item)
    write_queue_item(queue_path, reset)
    return QueueRetryResult(item=_snapshot_queue_item(root, queue_path, reset))


def repair_ingest_source(root: Path, source_id: str) -> RepairIngestResult:
    manifest_path = manifest_path_for(root, source_id)
    if not manifest_path.exists():
        msg = f"Unknown source ID: {source_id}"
        raise FileNotFoundError(msg)

    layout = resolve_layout(root, load_config(root))
    source = load_source_record(manifest_path)
    if source.source_id != source_id:
        msg = f"Source manifest ID does not match requested source: {source_id}"
        raise ValueError(msg)
    if is_ingest_current(root, layout, source):
        return RepairIngestResult(
            source_id=source_id,
            outcome="skipped",
            queue_path=None,
            run_id=None,
            run_path=None,
            page_path=layout.wiki_sources_dir / f"{source_id}.md",
            no_op=True,
            message="already ingested for the current pipeline version",
        )

    job_id = ingest_job_id(source_id)
    queue_path = queue_item_path_for(layout, job_id)
    if not queue_path.exists():
        queue_path = enqueue_ingest_job(root, source_id)
    else:
        queue_item = load_queue_item(queue_path)
        if queue_item.job_type != "ingest_source":
            msg = f"Unsupported queue job type for repair: {queue_item.job_type}"
            raise ValueError(msg)
        if queue_item.status in {"failed", "dead_letter"}:
            write_queue_item(queue_path, _reset_failed_ingest_queue_item(queue_item))
        elif queue_item.status == "done":
            queue_path = enqueue_ingest_job(root, source_id)
            queue_item = load_queue_item(queue_path)
            write_queue_item(queue_path, _ensure_next_attempt_allowed(queue_item))

    result = run_ingest_job(root, queue_path)
    if result.no_op:
        message = "already ingested for the current pipeline version"
        outcome = "skipped"
    else:
        message = f"run {result.run_id}"
        outcome = "succeeded"
    return RepairIngestResult(
        source_id=result.source_id,
        outcome=outcome,
        queue_path=result.queue_path,
        run_id=result.run_id,
        run_path=result.run_path,
        page_path=result.page_path,
        no_op=result.no_op,
        message=message,
    )


def render_queue_inspect_json(result: QueueInspectResult) -> str:
    return json.dumps(
        {
            "total": result.total,
            "status_counts": result.status_counts,
            "items": [_snapshot_payload(item) for item in result.items],
        },
        indent=2,
    )


def render_queue_item_json(item: QueueItemSnapshot) -> str:
    return json.dumps(_snapshot_payload(item), indent=2)


def render_queue_retry_json(result: QueueRetryResult) -> str:
    return json.dumps({"item": _snapshot_payload(result.item)}, indent=2)


def render_repair_ingest_json(root: Path, result: RepairIngestResult) -> str:
    return json.dumps(
        {
            "source_id": result.source_id,
            "outcome": result.outcome,
            "queue_path": _path_payload(root, result.queue_path),
            "run_id": result.run_id,
            "run_path": _path_payload(root, result.run_path),
            "page_path": _path_payload(root, result.page_path),
            "no_op": result.no_op,
            "message": result.message,
        },
        indent=2,
    )


def _reset_failed_ingest_queue_item(queue_item: QueueItemRecord) -> QueueItemRecord:
    if queue_item.job_type != "ingest_source":
        msg = f"Unsupported queue job type for retry: {queue_item.job_type}"
        raise ValueError(msg)
    if queue_item.status == "pending":
        msg = f"Queue item is already pending: {queue_item.job_id}"
        raise RuntimeError(msg)
    if queue_item.status == "leased":
        msg = f"Queue item is already leased: {queue_item.job_id}"
        raise RuntimeError(msg)
    if queue_item.status == "done":
        msg = f"Queue item is already done: {queue_item.job_id}"
        raise RuntimeError(msg)
    if queue_item.status not in {"failed", "dead_letter"}:
        msg = f"Queue item is not retryable: {queue_item.job_id}"
        raise RuntimeError(msg)

    return queue_item.model_copy(
        update={
            "status": "pending",
            "updated_at": utc_now_iso(),
            "max_attempts": _next_attempt_budget(queue_item),
            "lease_owner": None,
            "lease_expires_at": None,
            "next_attempt_at": None,
            "last_error": None,
        }
    )


def _ensure_next_attempt_allowed(queue_item: QueueItemRecord) -> QueueItemRecord:
    return queue_item.model_copy(update={"max_attempts": _next_attempt_budget(queue_item)})


def _next_attempt_budget(queue_item: QueueItemRecord) -> int:
    return max(queue_item.max_attempts, queue_item.attempt_count + 1)


def _snapshot_queue_item(
    root: Path, queue_path: Path, queue_item: QueueItemRecord
) -> QueueItemSnapshot:
    return QueueItemSnapshot(
        job_id=queue_item.job_id,
        job_type=queue_item.job_type,
        status=queue_item.status,
        created_at=queue_item.created_at,
        updated_at=queue_item.updated_at,
        attempt_count=queue_item.attempt_count,
        max_attempts=queue_item.max_attempts,
        payload_ref=queue_item.payload_ref,
        lease_owner=queue_item.lease_owner,
        lease_expires_at=queue_item.lease_expires_at,
        next_attempt_at=queue_item.next_attempt_at,
        last_error=queue_item.last_error,
        source_id=source_id_from_ingest_job_id(queue_item.job_id),
        operator_state=_operator_state(queue_item),
        record_path=queue_path.relative_to(root),
    )


def _snapshot_payload(item: QueueItemSnapshot) -> dict[str, object]:
    return {
        "job_id": item.job_id,
        "job_type": item.job_type,
        "status": item.status,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "attempt_count": item.attempt_count,
        "max_attempts": item.max_attempts,
        "payload_ref": item.payload_ref,
        "lease_owner": item.lease_owner,
        "lease_expires_at": item.lease_expires_at,
        "next_attempt_at": item.next_attempt_at,
        "last_error": item.last_error,
        "source_id": item.source_id,
        "operator_state": item.operator_state,
        "record_path": item.record_path.as_posix(),
    }


def _path_payload(root: Path, path: Path | None) -> str | None:
    return None if path is None else path.relative_to(root).as_posix()


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _operator_state(queue_item: QueueItemRecord) -> str:
    now = datetime.now(UTC).replace(microsecond=0)
    if queue_item.status == "pending":
        return "pending"
    if queue_item.status == "done":
        return "done"
    if queue_item.status == "dead_letter":
        return "dead_letter"
    if queue_item.status == "leased":
        expires_at = _parse_timestamp(queue_item.lease_expires_at)
        if expires_at is None or expires_at <= now:
            return "expired_leased"
        return "active_leased"
    if queue_item.status == "failed":
        next_attempt_at = _parse_timestamp(queue_item.next_attempt_at)
        if next_attempt_at is None or next_attempt_at <= now:
            return "failed_due"
        return "failed_backoff"
    return queue_item.status
