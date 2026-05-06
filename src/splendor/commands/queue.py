"""Queue inspection and repair command helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from splendor.commands.ingest import enqueue_ingest_job, is_ingest_current, run_ingest_job
from splendor.commands.mutation import mutation_contract, mutation_record
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import QueueItemRecord, SourceRecord
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import (
    ingest_job_id,
    load_queue_item,
    queue_item_path_for,
    source_id_from_ingest_job_id,
    write_queue_item,
)
from splendor.state.source_registry import load_source_record, manifest_path_for
from splendor.utils.time import parse_aware_timestamp_or_none, utc_now_iso


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
    cleanup_state: str
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
class QueueCleanAction:
    job_id: str
    path: Path
    source_id: str | None
    cleanup_state: str
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class QueueCleanResult:
    applied: bool
    selectors: list[str]
    actions: list[QueueCleanAction]
    written: list[QueueCleanAction]
    skipped: list[QueueCleanAction]


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


def clean_queue(
    root: Path,
    *,
    orphaned: bool = False,
    superseded: bool = False,
    completed: bool = False,
    apply: bool = False,
) -> QueueCleanResult:
    selectors = [
        label
        for label, enabled in [
            ("orphaned", orphaned),
            ("superseded", superseded),
            ("completed", completed),
        ]
        if enabled
    ]
    if not selectors:
        msg = "queue clean requires at least one cleanup selector"
        raise ValueError(msg)

    layout = resolve_layout(root, load_config(root))
    actions: list[QueueCleanAction] = []
    skipped: list[QueueCleanAction] = []
    written: list[QueueCleanAction] = []
    for queue_path in sorted(layout.queue_dir.glob("*.json")):
        planned, skip = _queue_clean_action(
            root,
            queue_path,
            selectors=set(selectors),
        )
        if skip is not None:
            skipped.append(skip)
        if planned is None:
            continue
        actions.append(planned)

    if apply and actions:
        _preflight_queue_clean_targets(root, actions)
        for action in actions:
            target = root / action.path
            if target.is_file() or target.is_symlink():
                target.unlink()
                written.append(action)
            else:
                skipped.append(
                    QueueCleanAction(
                        job_id=action.job_id,
                        path=action.path,
                        source_id=action.source_id,
                        cleanup_state=action.cleanup_state,
                        status="skipped",
                        reason="queue record disappeared before apply",
                    )
                )

    return QueueCleanResult(
        applied=apply,
        selectors=selectors,
        actions=actions,
        written=written,
        skipped=skipped,
    )


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


def render_queue_clean_json(root: Path, result: QueueCleanResult) -> str:
    mutation_records = _queue_clean_mutation_records(root, result.actions)
    written_records = _queue_clean_mutation_records(root, result.written)
    return json.dumps(
        {
            "applied": result.applied,
            "selectors": result.selectors,
            "summary": {
                "planned": len(result.actions),
                "written": len(result.written),
                "skipped": len(result.skipped),
            },
            "actions": [_queue_clean_action_payload(action) for action in result.actions],
            "written": [_queue_clean_action_payload(action) for action in result.written],
            "skipped": [_queue_clean_action_payload(action) for action in result.skipped],
            "mutation": mutation_contract(
                mode="apply" if result.applied else "preview",
                planned=[] if result.applied else mutation_records,
                written=written_records if result.applied else [],
            ),
        },
        indent=2,
    )


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
    operator_state = _operator_state(queue_item)
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
        operator_state=operator_state,
        cleanup_state=_queue_cleanup_state(root, queue_item, operator_state=operator_state),
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
        "cleanup_state": item.cleanup_state,
        "record_path": item.record_path.as_posix(),
    }


def _path_payload(root: Path, path: Path | None) -> str | None:
    return None if path is None else path.relative_to(root).as_posix()


def _operator_state(queue_item: QueueItemRecord) -> str:
    now = datetime.now(UTC).replace(microsecond=0)
    if queue_item.status == "pending":
        return "pending"
    if queue_item.status == "done":
        return "done"
    if queue_item.status == "dead_letter":
        return "dead_letter"
    if queue_item.status == "leased":
        expires_at = parse_aware_timestamp_or_none(queue_item.lease_expires_at)
        if expires_at is None or expires_at <= now:
            return "expired_leased"
        return "active_leased"
    if queue_item.status == "failed":
        next_attempt_at = parse_aware_timestamp_or_none(queue_item.next_attempt_at)
        if next_attempt_at is None or next_attempt_at <= now:
            return "failed_due"
        return "failed_backoff"
    return queue_item.status


def _queue_clean_action(
    root: Path, queue_path: Path, *, selectors: set[str]
) -> tuple[QueueCleanAction | None, QueueCleanAction | None]:
    queue_ref = queue_path.relative_to(root)
    job_id = queue_path.stem
    source_id = source_id_from_ingest_job_id(job_id)
    try:
        queue_item = load_queue_item(queue_path)
    except (OSError, ValueError) as exc:
        return None, QueueCleanAction(
            job_id=job_id,
            path=queue_ref,
            source_id=source_id,
            cleanup_state="invalid_record",
            status="skipped",
            reason=f"queue record is invalid: {exc}",
        )

    source_id = source_id_from_ingest_job_id(queue_item.job_id)
    skip = _queue_clean_skip(root, queue_item, source_id=source_id, queue_ref=queue_ref)
    if skip is not None:
        return None, skip

    cleanup_states = _queue_cleanup_states(
        root, queue_item, operator_state=_operator_state(queue_item)
    )
    selected_states = [state for state in _QUEUE_CLEANUP_SELECTOR_ORDER if state in selectors]
    cleanup_state = next(
        (state for state in selected_states if state in cleanup_states),
        None,
    )
    if cleanup_state is None:
        return None, None

    return QueueCleanAction(
        job_id=queue_item.job_id,
        path=queue_ref,
        source_id=source_id,
        cleanup_state=cleanup_state,
        status="planned",
    ), None


def _queue_clean_skip(
    root: Path, queue_item: QueueItemRecord, *, source_id: str | None, queue_ref: Path
) -> QueueCleanAction | None:
    if queue_item.job_type != "ingest_source":
        return QueueCleanAction(
            job_id=queue_item.job_id,
            path=queue_ref,
            source_id=source_id,
            cleanup_state="unsupported_job_type",
            status="skipped",
            reason=f"unsupported queue job type: {queue_item.job_type}",
        )
    if source_id is None:
        return QueueCleanAction(
            job_id=queue_item.job_id,
            path=queue_ref,
            source_id=None,
            cleanup_state="unsupported_job_id",
            status="skipped",
            reason="queue job is not a source-owned ingest job",
        )
    if _operator_state(queue_item) == "active_leased":
        return QueueCleanAction(
            job_id=queue_item.job_id,
            path=queue_ref,
            source_id=source_id,
            cleanup_state="active_leased",
            status="skipped",
            reason="queue record has an active lease",
        )
    manifest_path, source, reason = _queue_payload_source(root, queue_item, source_id=source_id)
    if source is not None and source.source_id != source_id:
        return QueueCleanAction(
            job_id=queue_item.job_id,
            path=queue_ref,
            source_id=source_id,
            cleanup_state="source_mismatch",
            status="skipped",
            reason=(
                f"queue payload resolves to source_id={source.source_id!r}, "
                f"but job_id expects {source_id!r}"
            ),
        )
    if reason is not None and not reason.startswith("missing source manifest:"):
        return QueueCleanAction(
            job_id=queue_item.job_id,
            path=queue_ref,
            source_id=source_id,
            cleanup_state="invalid_payload",
            status="skipped",
            reason=reason,
        )
    if manifest_path is not None and source is None and reason is None:
        return QueueCleanAction(
            job_id=queue_item.job_id,
            path=queue_ref,
            source_id=source_id,
            cleanup_state="invalid_payload",
            status="skipped",
            reason="queue payload source manifest is invalid",
        )
    return None


def _queue_cleanup_state(
    root: Path, queue_item: QueueItemRecord, *, operator_state: str | None = None
) -> str:
    states = _queue_cleanup_states(root, queue_item, operator_state=operator_state)
    for state in ["orphaned", "superseded", "completed"]:
        if state in states:
            return state
    for state in ["active_leased", "invalid_payload", "source_mismatch"]:
        if state in states:
            return state
    return "not_cleanup_candidate"


_QUEUE_CLEANUP_SELECTOR_ORDER = ["orphaned", "superseded", "completed"]


def _queue_cleanup_states(
    root: Path, queue_item: QueueItemRecord, *, operator_state: str | None = None
) -> set[str]:
    source_id = source_id_from_ingest_job_id(queue_item.job_id)
    operator_state = operator_state or _operator_state(queue_item)
    if queue_item.job_type != "ingest_source" or source_id is None:
        return {"not_cleanup_candidate"}
    if operator_state == "active_leased":
        return {"active_leased"}
    _manifest_path, source, reason = _queue_payload_source(root, queue_item, source_id=source_id)
    states: set[str] = set()
    if queue_item.status == "done":
        states.add("completed")
    if reason is not None:
        if reason.startswith("missing source manifest:"):
            states.add("orphaned")
            return states
        states.add("invalid_payload")
        return states
    if source is None:
        states.add("invalid_payload")
        return states
    if source.source_id != source_id:
        states.add("source_mismatch")
        return states
    if source.superseded_by is not None:
        states.add("superseded")
    if states:
        return states
    return {"not_cleanup_candidate"}


def _queue_payload_source(
    root: Path, queue_item: QueueItemRecord, *, source_id: str
) -> tuple[Path | None, SourceRecord | None, str | None]:
    try:
        manifest_path = resolve_workspace_path(
            root,
            queue_item.payload_ref,
            context="Queue payload",
        )
    except ValueError as exc:
        return None, None, str(exc)
    if not manifest_path.exists():
        return manifest_path, None, f"missing source manifest: {queue_item.payload_ref}"
    expected_manifest_path = manifest_path_for(root, source_id)
    try:
        source = load_source_record(manifest_path)
    except ValueError as exc:
        return manifest_path, None, str(exc)
    if manifest_path.resolve() != expected_manifest_path.resolve():
        return (
            manifest_path,
            source,
            (
                f"queue payload points to {queue_item.payload_ref!r}, but the canonical "
                "manifest path for this source is "
                f"{expected_manifest_path.relative_to(root).as_posix()!r}"
            ),
        )
    return manifest_path, source, None


def _queue_clean_mutation_records(
    root: Path, actions: list[QueueCleanAction]
) -> list[dict[str, str]]:
    del root
    return [
        mutation_record(
            action="delete",
            path=action.path.as_posix(),
            kind="queue_record",
            source_id=action.source_id,
        )
        for action in sorted(actions, key=lambda item: item.path.as_posix())
    ]


def _preflight_queue_clean_targets(root: Path, actions: list[QueueCleanAction]) -> None:
    for action in actions:
        target = root / action.path
        if target.is_dir() and not target.is_symlink():
            msg = f"Queue cleanup target is not a removable file: {action.path.as_posix()}"
            raise ValueError(msg)


def _queue_clean_action_payload(action: QueueCleanAction) -> dict[str, object]:
    return {
        "job_id": action.job_id,
        "path": action.path.as_posix(),
        "source_id": action.source_id,
        "cleanup_state": action.cleanup_state,
        "status": action.status,
        "reason": action.reason,
    }
