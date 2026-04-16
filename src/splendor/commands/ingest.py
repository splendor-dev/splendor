"""Implementation for `splendor ingest`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from splendor import __version__
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter, QueueItemRecord, RunRecord, SourceRecord
from splendor.schemas.types import SummaryMode
from splendor.state.runtime import (
    load_queue_item,
    load_run_record,
    queue_item_path_for,
    run_record_path_for,
    write_queue_item,
    write_run_record,
)
from splendor.state.source_compat import (
    canonical_source_ref,
    effective_source_ref_kind,
    effective_storage_mode,
    effective_stored_path,
)
from splendor.state.source_registry import (
    load_source_record,
    manifest_path_for,
    write_source_record,
)
from splendor.state.source_resolver import resolve_source_content
from splendor.utils.fs import write_text_atomic
from splendor.utils.time import utc_now_iso
from splendor.utils.wiki import (
    WikiUpdatePayload,
    append_log_entry,
    apply_wiki_updates,
    render_source_summary_page,
    update_index_content,
)

SUPPORTED_SOURCE_TYPES = {
    "md",
    "txt",
    "json",
    "yaml",
    "yml",
    "py",
    "js",
    "ts",
    "tsx",
    "rs",
    "go",
    "java",
    "c",
    "cpp",
    "h",
    "hpp",
    "sh",
}
LEASE_TTL_SECONDS = 300


@dataclass(frozen=True)
class IngestResult:
    source_id: str
    run_id: str | None
    queue_path: Path | None
    run_path: Path | None
    page_path: Path | None
    no_op: bool
    canonical_ref: str | None
    content_origin_kind: str | None


@dataclass(frozen=True)
class DrainItemResult:
    source_id: str
    queue_path: Path
    outcome: str
    message: str


@dataclass(frozen=True)
class DrainResult:
    processed: int
    succeeded: int
    failed: int
    skipped: int
    items: list[DrainItemResult]


def _make_run_id(source_id: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"run-{source_id}-{stamp}"


def _ingest_job_id(source_id: str) -> str:
    return f"ingest-{source_id}"


def _source_id_from_job_id(job_id: str) -> str:
    if job_id.startswith("ingest-"):
        return job_id.removeprefix("ingest-")
    return job_id


def _lease_owner() -> str:
    return f"local-cli:{os.getpid()}"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _relative_to_root(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _page_path_for(layout_root: Path, source_id: str) -> Path:
    return layout_root / f"{source_id}.md"


def _build_extract(text: str) -> str:
    lines = text.splitlines()
    start_index = 0
    for index, line in enumerate(lines):
        if line.strip():
            start_index = index
            break

    extract_lines: list[str] = []
    char_count = 0
    for line in lines[start_index : start_index + 80]:
        projected_count = char_count + len(line) + 1
        if projected_count > 4000 and extract_lines:
            break
        extract_lines.append(line)
        char_count = projected_count

    return "\n".join(extract_lines).rstrip()


def _summary_mode_for(config, source: SourceRecord) -> SummaryMode:
    if (
        effective_storage_mode(source) in {"none", "pointer", "symlink"}
        and effective_source_ref_kind(source) == "workspace_path"
    ):
        return config.sources.summarize_in_repo_extracts_as
    return config.sources.summarize_external_extracts_as


def _rendered_extract(text: str, mode: SummaryMode) -> str | None:
    if mode == "none":
        return None
    if mode == "excerpt":
        return _build_extract(text)
    return text


def _build_summary(source: SourceRecord) -> str:
    path_fragment = canonical_source_ref(source)
    return (
        f"This page records deterministic ingestion output for source `{source.source_id}`, "
        f"a `{source.source_type}` file registered from `{path_fragment}`."
    )


def _content_origin_kind(storage_mode: str) -> str:
    if storage_mode == "copy":
        return "stored_artifact"
    return "workspace_path"


def _best_available_source_ref(source: SourceRecord) -> str:
    if effective_storage_mode(source) == "none":
        return canonical_source_ref(source)
    return effective_stored_path(source) or canonical_source_ref(source)


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _lease_expires_at(now: datetime) -> str:
    return (now + timedelta(seconds=LEASE_TTL_SECONDS)).isoformat()


def _lease_is_expired(queue_item: QueueItemRecord, now: datetime) -> bool:
    if queue_item.status != "leased":
        return False
    expires_at = _parse_timestamp(queue_item.lease_expires_at)
    if expires_at is None:
        return True
    return expires_at <= now


def _is_queue_eligible(queue_item: QueueItemRecord, now: datetime) -> bool:
    if queue_item.job_type != "ingest_source":
        return False
    if queue_item.status == "pending":
        return True
    return _lease_is_expired(queue_item, now)


def _is_no_op(root: Path, layout, source: SourceRecord) -> bool:
    if source.status != "ingested" or not source.last_run_id:
        return False

    page_path = _page_path_for(layout.wiki_sources_dir, source.source_id)
    page_relpath = _relative_to_root(root, page_path)
    if page_relpath not in source.linked_pages:
        return False

    if not page_path.exists():
        return False

    run_path = layout.runs_dir / f"{source.last_run_id}.json"
    if not run_path.exists():
        return False

    run = load_run_record(run_path)
    return run.status == "succeeded" and run.pipeline_version == __version__


def _validate_workspace_files(layout) -> None:
    required_files = [layout.index_file, layout.log_file]
    missing = [path for path in required_files if not path.exists()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        msg = f"Workspace is missing required wiki files: {joined}. Run `splendor init`."
        raise RuntimeError(msg)


def _load_source_for_queue(root: Path, queue_item: QueueItemRecord) -> tuple[Path, SourceRecord]:
    manifest_path = root / queue_item.payload_ref
    if not manifest_path.exists():
        msg = f"Queue payload is missing source manifest: {manifest_path}"
        raise FileNotFoundError(msg)
    source = load_source_record(manifest_path)
    expected_source_id = _source_id_from_job_id(queue_item.job_id)
    if source.source_id != expected_source_id:
        msg = f"Queue payload source ID does not match queued job: {queue_item.job_id}"
        raise ValueError(msg)
    return manifest_path, source


def _finalize_queue_record(
    queue_path: Path,
    queue_item: QueueItemRecord,
    *,
    status: str,
    last_error: str | None = None,
) -> QueueItemRecord:
    finalized = queue_item.model_copy(
        update={
            "status": status,
            "updated_at": utc_now_iso(),
            "lease_owner": None,
            "lease_expires_at": None,
            "last_error": last_error,
        }
    )
    write_queue_item(queue_path, finalized)
    return finalized


def _mark_attempt_failed(
    *,
    queue_path: Path,
    queue_item: QueueItemRecord,
    run_path: Path,
    run: RunRecord,
    error_message: str,
    manifest_path: Path | None = None,
    source: SourceRecord | None = None,
    run_id: str | None = None,
) -> None:
    failed_run = run.model_copy(
        update={
            "finished_at": utc_now_iso(),
            "status": "failed",
            "errors": [error_message],
        }
    )
    write_run_record(run_path, failed_run)
    _finalize_queue_record(queue_path, queue_item, status="failed", last_error=error_message)
    if manifest_path is not None and source is not None and run_id is not None:
        failed_source = source.model_copy(update={"status": "failed", "last_run_id": run_id})
        write_source_record(manifest_path, failed_source)


def _mark_queue_failed_without_run(
    queue_path: Path,
    queue_item: QueueItemRecord,
    error_message: str,
) -> None:
    _finalize_queue_record(queue_path, queue_item, status="failed", last_error=error_message)


def _commit_success(
    *,
    layout,
    manifest_path: Path,
    success_source: SourceRecord,
    run_path: Path,
    success_run: RunRecord,
    queue_path: Path,
    success_queue: QueueItemRecord,
    wiki_payload: WikiUpdatePayload,
) -> None:
    tracked_paths = [
        manifest_path,
        run_path,
        queue_path,
        wiki_payload.page_path,
        layout.index_file,
        layout.log_file,
    ]
    previous_content: dict[Path, str | None] = {}
    for path in tracked_paths:
        previous_content[path] = path.read_text(encoding="utf-8") if path.exists() else None

    try:
        apply_wiki_updates(layout, wiki_payload)
        write_source_record(manifest_path, success_source)
        write_run_record(run_path, success_run)
        write_queue_item(queue_path, success_queue)
    except Exception:
        for path, content in previous_content.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                write_text_atomic(path, content)
        raise


def enqueue_ingest_job(root: Path, source_id: str) -> Path:
    config = load_config(root)
    layout = resolve_layout(root, config)
    _validate_workspace_files(layout)
    manifest_path = manifest_path_for(root, source_id)
    if not manifest_path.exists():
        msg = f"Unknown source ID: {source_id}"
        raise FileNotFoundError(msg)

    source = load_source_record(manifest_path)
    if source.source_id != source_id:
        msg = f"Source manifest ID does not match requested source: {source_id}"
        raise ValueError(msg)

    now = utc_now_iso()
    queue_path = queue_item_path_for(layout, _ingest_job_id(source_id))
    existing_queue = load_queue_item(queue_path) if queue_path.exists() else None
    queue_item = QueueItemRecord(
        job_id=_ingest_job_id(source_id),
        job_type="ingest_source",
        status="pending",
        created_at=now if existing_queue is None else existing_queue.created_at,
        updated_at=now,
        attempt_count=0 if existing_queue is None else existing_queue.attempt_count,
        max_attempts=3 if existing_queue is None else existing_queue.max_attempts,
        payload_ref=_relative_to_root(root, manifest_path),
        lease_owner=None,
        lease_expires_at=None,
        last_error=None,
    )
    write_queue_item(queue_path, queue_item)
    return queue_path


def _claim_ingest_job(queue_path: Path, queue_item: QueueItemRecord) -> QueueItemRecord:
    now = _utc_now()
    leased_queue = queue_item.model_copy(
        update={
            "status": "leased",
            "updated_at": now.isoformat(),
            "attempt_count": queue_item.attempt_count + 1,
            "lease_owner": _lease_owner(),
            "lease_expires_at": _lease_expires_at(now),
            "last_error": None,
        }
    )
    write_queue_item(queue_path, leased_queue)
    return leased_queue


def run_ingest_job(root: Path, queue_path: Path) -> IngestResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    _validate_workspace_files(layout)
    queue_item = load_queue_item(queue_path)
    if queue_item.job_type != "ingest_source":
        msg = f"Unsupported queue job type for ingest worker: {queue_item.job_type}"
        raise ValueError(msg)

    now = _utc_now()
    if queue_item.status == "leased" and not _lease_is_expired(queue_item, now):
        msg = f"Queue item is already leased: {queue_item.job_id}"
        raise RuntimeError(msg)
    if queue_item.status not in {"pending", "leased"}:
        msg = f"Queue item is not runnable: {queue_item.job_id}"
        raise RuntimeError(msg)

    queue_item = _claim_ingest_job(queue_path, queue_item)

    try:
        manifest_path, source = _load_source_for_queue(root, queue_item)
    except (FileNotFoundError, ValueError) as exc:
        _mark_queue_failed_without_run(queue_path, queue_item, str(exc))
        raise

    if _is_no_op(root, layout, source):
        _finalize_queue_record(queue_path, queue_item, status="done", last_error=None)
        return IngestResult(
            source_id=source.source_id,
            run_id=None,
            queue_path=queue_path,
            run_path=None,
            page_path=_page_path_for(layout.wiki_sources_dir, source.source_id),
            no_op=True,
            canonical_ref=None,
            content_origin_kind=None,
        )

    run_id = _make_run_id(source.source_id)
    run_path = run_record_path_for(layout, run_id)
    run = RunRecord(
        run_id=run_id,
        job_id=queue_item.job_id,
        job_type="ingest_source",
        started_at=utc_now_iso(),
        status="running",
        input_refs=[
            _relative_to_root(root, manifest_path),
            _best_available_source_ref(source),
        ],
        pipeline_version=__version__,
    )
    write_run_record(run_path, run)

    try:
        resolved_source = resolve_source_content(root, source, layout.raw_sources_dir)
        run = run.model_copy(
            update={
                "input_refs": [
                    _relative_to_root(root, manifest_path),
                    resolved_source.resolved_ref,
                ]
            }
        )
        write_run_record(run_path, run)

        if source.source_type not in SUPPORTED_SOURCE_TYPES:
            msg = f"Unsupported source type for ingestion: {source.source_type}"
            raise ValueError(msg)

        try:
            source_text = resolved_source.resolved_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            msg = f"Source file is not valid UTF-8 text: {resolved_source.resolved_path}"
            raise ValueError(msg) from exc

        extract_mode = _summary_mode_for(config, source)
        page_path = _page_path_for(layout.wiki_sources_dir, source.source_id)
        page_relpath = _relative_to_root(root, page_path)
        registered_path = canonical_source_ref(source)
        frontmatter = KnowledgePageFrontmatter(
            kind="source-summary",
            title=source.title,
            page_id=source.source_id,
            status="active",
            source_refs=[source.source_id],
            generated_by_run_ids=[run_id],
            confidence=1.0,
            tags=["source-summary", source.source_type],
        )
        page_content = render_source_summary_page(
            frontmatter,
            source_section="\n".join(
                [
                    f"- Source ID: `{source.source_id}`",
                    f"- Source type: `{source.source_type}`",
                    f"- Registered path: `{registered_path}`",
                    f"- Source file: `{resolved_source.resolved_ref}`",
                ]
            ),
            summary=_build_summary(source),
            key_facts=[
                f"Source ID: `{source.source_id}`",
                f"Source type: `{source.source_type}`",
                f"Checksum: `{source.checksum}`",
                f"Source ref: `{canonical_source_ref(source)}`",
                f"Added at: `{source.added_at}`",
                f"Ingested at: `{utc_now_iso()}`",
            ],
            extract=_rendered_extract(source_text, extract_mode),
            provenance=[
                f"Manifest: `{_relative_to_root(root, manifest_path)}`",
                f"{resolved_source.content_origin_label}: `{resolved_source.resolved_ref}`",
                f"Run ID: `{run_id}`",
                f"Pipeline version: `{__version__}`",
            ],
        )
        index_content = update_index_content(
            layout.index_file.read_text(encoding="utf-8"),
            source_id=source.source_id,
            title=source.title,
            page_name=page_path.name,
        )
        log_entry = (
            f"- {utc_now_iso()} Ingested source `{source.source_id}` "
            f"via run `{run_id}` into `{page_relpath}`."
        )
        log_content = append_log_entry(layout.log_file.read_text(encoding="utf-8"), log_entry)
        updated_source = source.model_copy(
            update={
                "status": "ingested",
                "last_run_id": run_id,
                "linked_pages": sorted(set([*source.linked_pages, page_relpath])),
            }
        )
        success_run = run.model_copy(
            update={
                "finished_at": utc_now_iso(),
                "status": "succeeded",
                "output_refs": [
                    page_relpath,
                    _relative_to_root(root, layout.index_file),
                    _relative_to_root(root, layout.log_file),
                ],
            }
        )
        success_queue = queue_item.model_copy(
            update={
                "status": "done",
                "updated_at": utc_now_iso(),
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error": None,
            }
        )
        _commit_success(
            layout=layout,
            manifest_path=manifest_path,
            success_source=updated_source,
            run_path=run_path,
            success_run=success_run,
            queue_path=queue_path,
            success_queue=success_queue,
            wiki_payload=WikiUpdatePayload(
                page_path=page_path,
                page_content=page_content,
                index_content=index_content,
                log_content=log_content,
            ),
        )
        return IngestResult(
            source_id=source.source_id,
            run_id=run_id,
            queue_path=queue_path,
            run_path=run_path,
            page_path=page_path,
            no_op=False,
            canonical_ref=resolved_source.canonical_ref,
            content_origin_kind=_content_origin_kind(resolved_source.storage_mode),
        )
    except ValueError as exc:
        _mark_attempt_failed(
            queue_path=queue_path,
            queue_item=queue_item,
            run_path=run_path,
            run=run,
            error_message=str(exc),
            manifest_path=manifest_path,
            source=source,
            run_id=run_id,
        )
        raise
    except Exception as exc:
        _mark_attempt_failed(
            queue_path=queue_path,
            queue_item=queue_item,
            run_path=run_path,
            run=run,
            error_message=str(exc),
        )
        raise RuntimeError(f"Ingestion failed while committing outputs: {exc}") from exc


def drain_pending_ingest_jobs(root: Path) -> DrainResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    queue_items: list[tuple[Path, QueueItemRecord]] = []
    for queue_path in sorted(layout.queue_dir.glob("*.json")):
        queue_items.append((queue_path, load_queue_item(queue_path)))

    now = _utc_now()
    ordered_items = sorted(queue_items, key=lambda item: (item[1].created_at, item[1].job_id))

    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0
    item_results: list[DrainItemResult] = []

    for queue_path, queue_item in ordered_items:
        source_id = _source_id_from_job_id(queue_item.job_id)
        if not _is_queue_eligible(queue_item, now):
            skipped += 1
            continue

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
        processed=processed,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        items=item_results,
    )


def ingest_source(root: Path, source_id: str) -> IngestResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    _validate_workspace_files(layout)
    manifest_path = manifest_path_for(root, source_id)
    if not manifest_path.exists():
        msg = f"Unknown source ID: {source_id}"
        raise FileNotFoundError(msg)

    source = load_source_record(manifest_path)
    if source.source_id != source_id:
        msg = f"Source manifest ID does not match requested source: {source_id}"
        raise ValueError(msg)

    if _is_no_op(root, layout, source):
        return IngestResult(
            source_id=source_id,
            run_id=None,
            queue_path=None,
            run_path=None,
            page_path=layout.wiki_sources_dir / f"{source_id}.md",
            no_op=True,
            canonical_ref=None,
            content_origin_kind=None,
        )

    queue_path = enqueue_ingest_job(root, source_id)
    return run_ingest_job(root, queue_path)
