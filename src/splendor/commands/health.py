"""Implementation for `splendor health`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from splendor.commands.maintenance import MaintenanceCheckResult, workspace_relative_path
from splendor.layout import ResolvedLayout
from splendor.schemas import MaintenanceIssue, QueueItemRecord, RunRecord, SourceRecord
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import load_queue_item, load_run_record
from splendor.state.source_compat import effective_storage_mode
from splendor.state.source_registry import load_source_record
from splendor.state.source_resolver import resolve_source_content


def _source_id_from_job_id(job_id: str) -> str:
    if job_id.startswith("ingest-"):
        return job_id.removeprefix("ingest-")
    return job_id


def _validate_storage_policy(source: SourceRecord) -> None:
    storage_mode = effective_storage_mode(source)
    if storage_mode == "none" and source.source_ref_kind != "workspace_path":
        msg = (
            "Storage mode 'none' requires source_ref_kind=workspace_path; "
            f"got {source.source_ref_kind!r}"
        )
        raise ValueError(msg)
    if storage_mode in {"pointer", "symlink"} and source.source_ref_kind != "workspace_path":
        msg = (
            f"Storage mode {storage_mode!r} requires source_ref_kind=workspace_path; "
            f"got {source.source_ref_kind!r}"
        )
        raise ValueError(msg)
    if storage_mode == "copy" and not source.path:
        raise ValueError("Copied source is missing path")


def _append_issue(
    issues: list[MaintenanceIssue],
    *,
    code: str,
    message: str,
    path: str,
    record_id: str | None = None,
    check_name: str,
) -> None:
    issues.append(
        MaintenanceIssue(
            code=code,
            message=message,
            path=path,
            record_id=record_id,
            check_name=check_name,
        )
    )


def _parse_timestamp(value: str, *, context: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"{context} is not a valid ISO timestamp: {value!r}"
        raise ValueError(msg) from exc


def _require_runtime_directory(path: Path, *, label: str) -> None:
    if not path.is_dir():
        msg = f"{label} directory is missing or unreadable: {path}"
        raise RuntimeError(msg)


def _load_source_records(
    layout: ResolvedLayout,
    *,
    root: Path,
    issues: list[MaintenanceIssue],
) -> tuple[dict[str, SourceRecord], set[str], int]:
    records: dict[str, SourceRecord] = {}
    invalid_ids: set[str] = set()
    checked_count = 0

    for manifest_path in sorted(layout.source_records_dir.glob("*.json")):
        checked_count += 1
        source_id = manifest_path.stem
        manifest_relpath = workspace_relative_path(root, manifest_path)
        try:
            source = load_source_record(manifest_path)
            _validate_storage_policy(source)
            resolve_source_content(root, source, layout.raw_sources_dir)
        except Exception as exc:
            invalid_ids.add(source_id)
            _append_issue(
                issues,
                code="source-health-check-failed",
                message=str(exc),
                path=manifest_relpath,
                record_id=source_id,
                check_name="source-storage",
            )
            continue
        records[source_id] = source

    return records, invalid_ids, checked_count


def _load_queue_records(
    layout: ResolvedLayout,
    *,
    root: Path,
    issues: list[MaintenanceIssue],
) -> tuple[dict[str, tuple[Path, QueueItemRecord]], set[str], int]:
    records: dict[str, tuple[Path, QueueItemRecord]] = {}
    invalid_ids: set[str] = set()
    checked_count = 0

    for queue_path in sorted(layout.queue_dir.glob("*.json")):
        checked_count += 1
        queue_id = queue_path.stem
        queue_relpath = workspace_relative_path(root, queue_path)
        try:
            queue_record = load_queue_item(queue_path)
        except Exception as exc:
            invalid_ids.add(queue_id)
            _append_issue(
                issues,
                code="invalid-queue-record",
                message=str(exc),
                path=queue_relpath,
                record_id=queue_id,
                check_name="queue-record",
            )
            continue
        records[queue_id] = (queue_path, queue_record)

    return records, invalid_ids, checked_count


def _load_run_records(
    layout: ResolvedLayout,
    *,
    root: Path,
    issues: list[MaintenanceIssue],
) -> tuple[dict[str, tuple[Path, RunRecord]], set[str], int]:
    records: dict[str, tuple[Path, RunRecord]] = {}
    invalid_ids: set[str] = set()
    checked_count = 0

    for run_path in sorted(layout.runs_dir.glob("*.json")):
        checked_count += 1
        run_id = run_path.stem
        run_relpath = workspace_relative_path(root, run_path)
        try:
            run_record = load_run_record(run_path)
        except Exception as exc:
            invalid_ids.add(run_id)
            _append_issue(
                issues,
                code="invalid-run-record",
                message=str(exc),
                path=run_relpath,
                record_id=run_id,
                check_name="run-record",
            )
            continue
        records[run_id] = (run_path, run_record)

    return records, invalid_ids, checked_count


def _validate_queue_record(
    *,
    root: Path,
    queue_path: Path,
    queue_record: QueueItemRecord,
    source_records: dict[str, SourceRecord],
    invalid_source_ids: set[str],
    now: datetime,
    issues: list[MaintenanceIssue],
) -> None:
    queue_relpath = workspace_relative_path(root, queue_path)

    if queue_record.job_id != queue_path.stem:
        _append_issue(
            issues,
            code="queue-job-id-mismatch",
            message=(
                f"Queue filename expects job_id={queue_path.stem!r}, "
                f"but record stores {queue_record.job_id!r}"
            ),
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-record",
        )

    if queue_record.job_type != "ingest_source":
        _append_issue(
            issues,
            code="unsupported-queue-job-type",
            message=f"Unsupported queue job type for current runtime: {queue_record.job_type!r}",
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-record",
        )
        return

    if queue_record.status == "leased":
        if not queue_record.lease_owner or not queue_record.lease_expires_at:
            _append_issue(
                issues,
                code="invalid-queue-lease-state",
                message=(
                    "Leased queue items must include both lease_owner and lease_expires_at so "
                    "operators can decide whether to reclaim them."
                ),
                path=queue_relpath,
                record_id=queue_record.job_id,
                check_name="queue-state",
            )
        else:
            try:
                expires_at = _parse_timestamp(
                    queue_record.lease_expires_at,
                    context="Queue lease expiry",
                )
            except ValueError as exc:
                _append_issue(
                    issues,
                    code="invalid-queue-lease-expiry",
                    message=str(exc),
                    path=queue_relpath,
                    record_id=queue_record.job_id,
                    check_name="queue-state",
                )
            else:
                if expires_at <= now:
                    _append_issue(
                        issues,
                        code="expired-queue-lease",
                        message=(
                            "Queue item still claims a lease past its expiry; repair by "
                            "reclaiming or resetting the job."
                        ),
                        path=queue_relpath,
                        record_id=queue_record.job_id,
                        check_name="queue-state",
                    )
    elif queue_record.lease_owner is not None or queue_record.lease_expires_at is not None:
        _append_issue(
            issues,
            code="invalid-queue-lease-state",
            message="Only leased queue items may carry lease_owner or lease_expires_at values.",
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-state",
        )

    if queue_record.status == "failed":
        if not queue_record.last_error:
            _append_issue(
                issues,
                code="invalid-queue-error-state",
                message="Failed queue items should persist last_error for repair diagnostics.",
                path=queue_relpath,
                record_id=queue_record.job_id,
                check_name="queue-state",
            )
    elif queue_record.last_error is not None:
        _append_issue(
            issues,
            code="invalid-queue-error-state",
            message="Only failed queue items should persist last_error details.",
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-state",
        )

    if queue_record.attempt_count > queue_record.max_attempts:
        _append_issue(
            issues,
            code="queue-attempt-count-exceeded",
            message=(
                f"attempt_count={queue_record.attempt_count} exceeds "
                f"max_attempts={queue_record.max_attempts}"
            ),
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-state",
        )

    try:
        manifest_path = resolve_workspace_path(
            root,
            queue_record.payload_ref,
            context="Queue payload",
        )
    except ValueError as exc:
        _append_issue(
            issues,
            code="invalid-queue-payload-ref",
            message=str(exc),
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-payload",
        )
        return

    if not manifest_path.exists():
        _append_issue(
            issues,
            code="missing-queue-payload",
            message=f"Queue payload is missing source manifest: {queue_record.payload_ref}",
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-payload",
        )
        return

    expected_source_id = _source_id_from_job_id(queue_record.job_id)
    if expected_source_id in invalid_source_ids:
        return

    source_record = source_records.get(expected_source_id)
    if source_record is None:
        _append_issue(
            issues,
            code="missing-queue-source-record",
            message=(
                f"Queue job expects source manifest for {expected_source_id!r}, "
                "but no valid source record was loaded."
            ),
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-payload",
        )
        return

    try:
        payload_source = load_source_record(manifest_path)
    except Exception as exc:
        _append_issue(
            issues,
            code="invalid-queue-payload-manifest",
            message=str(exc),
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-payload",
        )
        return

    if payload_source.source_id != expected_source_id:
        _append_issue(
            issues,
            code="queue-payload-source-mismatch",
            message=(
                f"Queue payload resolves to source_id={payload_source.source_id!r}, "
                f"but job_id expects {expected_source_id!r}"
            ),
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-payload",
        )
    if manifest_path.name != f"{source_record.source_id}.json":
        canonical_manifest_relpath = workspace_relative_path(
            root,
            root / "state" / "manifests" / "sources" / f"{source_record.source_id}.json",
        )
        _append_issue(
            issues,
            code="queue-payload-path-mismatch",
            message=(
                f"Queue payload points to {queue_record.payload_ref!r}, but the canonical "
                f"manifest path for this source is {canonical_manifest_relpath!r}"
            ),
            path=queue_relpath,
            record_id=queue_record.job_id,
            check_name="queue-payload",
        )


def _validate_run_record(
    *,
    root: Path,
    run_path: Path,
    run_record: RunRecord,
    issues: list[MaintenanceIssue],
) -> None:
    run_relpath = workspace_relative_path(root, run_path)

    if run_record.run_id != run_path.stem:
        _append_issue(
            issues,
            code="run-id-mismatch",
            message=(
                f"Run filename expects run_id={run_path.stem!r}, "
                f"but record stores {run_record.run_id!r}"
            ),
            path=run_relpath,
            record_id=run_record.run_id,
            check_name="run-record",
        )

    if run_record.job_type != "ingest_source":
        _append_issue(
            issues,
            code="unsupported-run-job-type",
            message=f"Unsupported run job type for current runtime: {run_record.job_type!r}",
            path=run_relpath,
            record_id=run_record.run_id,
            check_name="run-record",
        )
        return

    if run_record.status == "running":
        if run_record.finished_at is not None:
            _append_issue(
                issues,
                code="invalid-run-finish-state",
                message="Running runs must not set finished_at before completion.",
                path=run_relpath,
                record_id=run_record.run_id,
                check_name="run-state",
            )
        _append_issue(
            issues,
            code="unfinished-run",
            message=(
                "Run is still marked running; repair by confirming the worker finished and then "
                "marking the run terminal or retrying the queue item."
            ),
            path=run_relpath,
            record_id=run_record.run_id,
            check_name="run-state",
        )
    elif run_record.finished_at is None:
        _append_issue(
            issues,
            code="invalid-run-finish-state",
            message="Terminal runs must set finished_at for auditability and repair decisions.",
            path=run_relpath,
            record_id=run_record.run_id,
            check_name="run-state",
        )

    if run_record.status == "succeeded" and run_record.errors:
        _append_issue(
            issues,
            code="invalid-run-error-state",
            message="Succeeded runs must not retain errors.",
            path=run_relpath,
            record_id=run_record.run_id,
            check_name="run-state",
        )
    if run_record.status == "failed" and not run_record.errors:
        _append_issue(
            issues,
            code="invalid-run-error-state",
            message="Failed runs should preserve at least one error for repair diagnostics.",
            path=run_relpath,
            record_id=run_record.run_id,
            check_name="run-state",
        )

    for ref in [*run_record.input_refs, *run_record.output_refs]:
        try:
            resolve_workspace_path(root, ref, context="Run reference")
        except ValueError as exc:
            _append_issue(
                issues,
                code="invalid-run-reference",
                message=str(exc),
                path=run_relpath,
                record_id=run_record.run_id,
                check_name="run-state",
            )


def _validate_source_runtime_state(
    *,
    root: Path,
    source_records: dict[str, SourceRecord],
    run_records: dict[str, tuple[Path, RunRecord]],
    invalid_run_ids: set[str],
    issues: list[MaintenanceIssue],
) -> None:
    for source_id, source_record in source_records.items():
        manifest_relpath = f"state/manifests/sources/{source_id}.json"

        if source_record.status == "registered":
            if source_record.last_run_id is not None:
                _append_issue(
                    issues,
                    code="registered-source-has-last-run",
                    message=(
                        "Registered sources should not point at last_run_id before an ingest "
                        "attempt has completed."
                    ),
                    path=manifest_relpath,
                    record_id=source_id,
                    check_name="source-runtime",
                )
            continue

        if source_record.last_run_id is None:
            _append_issue(
                issues,
                code="source-missing-last-run",
                message=(
                    f"Source status {source_record.status!r} requires last_run_id so the "
                    "corresponding ingest attempt can be audited or repaired."
                ),
                path=manifest_relpath,
                record_id=source_id,
                check_name="source-runtime",
            )
            continue

        if source_record.last_run_id in invalid_run_ids:
            _append_issue(
                issues,
                code="source-last-run-invalid",
                message=(
                    f"Source last_run_id points to an unreadable run record: "
                    f"{source_record.last_run_id}"
                ),
                path=manifest_relpath,
                record_id=source_id,
                check_name="source-runtime",
            )
            continue

        run_entry = run_records.get(source_record.last_run_id)
        if run_entry is None:
            _append_issue(
                issues,
                code="missing-last-run-record",
                message=f"Run record is missing for last_run_id={source_record.last_run_id!r}",
                path=manifest_relpath,
                record_id=source_id,
                check_name="source-runtime",
            )
            continue

        _, run_record = run_entry
        expected_job_id = f"ingest-{source_id}"
        if run_record.job_id != expected_job_id:
            _append_issue(
                issues,
                code="source-last-run-job-mismatch",
                message=(
                    f"Source last_run_id points to job_id={run_record.job_id!r}, "
                    f"but expected {expected_job_id!r}"
                ),
                path=manifest_relpath,
                record_id=source_id,
                check_name="source-runtime",
            )
        if source_record.status == "ingested" and run_record.status != "succeeded":
            _append_issue(
                issues,
                code="source-last-run-status-mismatch",
                message=(
                    f"Source is marked ingested, but last_run_id resolved to a "
                    f"{run_record.status!r} run."
                ),
                path=manifest_relpath,
                record_id=source_id,
                check_name="source-runtime",
            )
        if source_record.status == "failed" and run_record.status != "failed":
            _append_issue(
                issues,
                code="source-last-run-status-mismatch",
                message=(
                    f"Source is marked failed, but last_run_id resolved to a "
                    f"{run_record.status!r} run."
                ),
                path=manifest_relpath,
                record_id=source_id,
                check_name="source-runtime",
            )


def run_health_checks(root: Path, layout: ResolvedLayout) -> MaintenanceCheckResult:
    issues: list[MaintenanceIssue] = []
    checked_count = 0
    now = datetime.now(UTC)

    _require_runtime_directory(layout.source_records_dir, label="Source manifest")
    _require_runtime_directory(layout.queue_dir, label="Queue")
    _require_runtime_directory(layout.runs_dir, label="Run")

    source_records, invalid_source_ids, loaded_sources = _load_source_records(
        layout,
        root=root,
        issues=issues,
    )
    queue_records, _, loaded_queues = _load_queue_records(
        layout,
        root=root,
        issues=issues,
    )
    run_records, invalid_run_ids, loaded_runs = _load_run_records(
        layout,
        root=root,
        issues=issues,
    )
    checked_count += loaded_sources + loaded_queues + loaded_runs

    for queue_path, queue_record in queue_records.values():
        _validate_queue_record(
            root=root,
            queue_path=queue_path,
            queue_record=queue_record,
            source_records=source_records,
            invalid_source_ids=invalid_source_ids,
            now=now,
            issues=issues,
        )

    for run_path, run_record in run_records.values():
        _validate_run_record(
            root=root,
            run_path=run_path,
            run_record=run_record,
            issues=issues,
        )

    _validate_source_runtime_state(
        root=root,
        source_records=source_records,
        run_records=run_records,
        invalid_run_ids=invalid_run_ids,
        issues=issues,
    )

    return MaintenanceCheckResult(checked_count=checked_count, issues=issues)
