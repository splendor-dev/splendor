"""Implementation for `splendor ingest`."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from splendor import __version__
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import (
    KnowledgePageFrontmatter,
    ProvenanceLink,
    QueueItemRecord,
    RunRecord,
    SourceRecord,
)
from splendor.schemas.types import SummaryMode
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import (
    ingest_job_id,
    load_queue_item,
    load_run_record,
    queue_item_path_for,
    run_record_path_for,
    source_id_from_ingest_job_id,
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
from splendor.utils.contradictions import (
    render_contradiction_lines,
    review_source_summary_contradictions,
    snapshot_from_rendered_page,
)
from splendor.utils.fs import write_text_atomic
from splendor.utils.provenance import dedupe_provenance_links, make_provenance_link
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
_MARKDOWN_HEADING_PATTERN = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_CLAIM_SECTION_HEADINGS = {
    "core claims",
    "design implications",
    "implementation pattern",
    "implementation patterns",
    "key facts",
    "claims",
    "findings",
}


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
    total: int
    processed: int
    succeeded: int
    failed: int
    skipped: int
    items: list[DrainItemResult]


def _make_run_id(source_id: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"run-{source_id}-{stamp}"


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


def _build_summary(source: SourceRecord, source_text: str) -> str:
    path_fragment = canonical_source_ref(source)
    content_summary = _build_content_summary(source_text)
    if source.source_type in {"md", "txt"} and content_summary is not None:
        return f"{content_summary} registered from `{path_fragment}`."
    return (
        f"This page records deterministic ingestion output for source `{source.source_id}`, "
        f"a `{source.source_type}` file registered from `{path_fragment}`."
    )


def _build_content_summary(text: str) -> str | None:
    heading: str | None = None
    paragraph_lines: list[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line:
            if paragraph_lines:
                break
            continue
        heading_match = _MARKDOWN_HEADING_PATTERN.match(line)
        if heading_match:
            if heading is None:
                heading = _strip_markdown_inline(heading_match.group("title"))
            if paragraph_lines:
                break
            continue
        if line.startswith(("- ", "* ", "+ ", ">")):
            continue
        paragraph_lines.append(_strip_markdown_inline(line))
        if len(paragraph_lines) >= 3:
            break

    paragraph = _bounded_summary_text(" ".join(paragraph_lines).strip())
    if heading and paragraph:
        return f"{heading}. {paragraph}"
    if paragraph:
        return paragraph
    if heading:
        return heading
    return None


def _bounded_summary_text(text: str) -> str:
    if len(text) <= 360:
        return text
    return text[:357].rstrip() + "..."


def _build_content_key_facts(text: str) -> list[str]:
    facts: list[str] = []
    active = False
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading_match = _MARKDOWN_HEADING_PATTERN.match(line)
        if heading_match:
            heading = _strip_markdown_inline(heading_match.group("title")).lower()
            active = heading in _CLAIM_SECTION_HEADINGS
            continue
        if not active:
            continue
        if line.startswith(("- ", "* ", "+ ")):
            fact = _strip_markdown_inline(line[2:].strip())
            if fact:
                facts.append(fact)
        elif line and not line.startswith(">"):
            fact = _strip_markdown_inline(line)
            if fact:
                facts.append(fact)
        if len(facts) >= 6:
            break
    return facts


def _strip_markdown_inline(text: str) -> str:
    stripped = text.strip().strip("#").strip()
    stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = stripped.replace("**", "").replace("__", "").replace("*", "")
    return " ".join(stripped.split())


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
    normalized_value = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _dead_letter_recovery_message(job_id: str, source_id: str) -> str:
    return (
        f"Queue item is dead-lettered: {job_id}. Run "
        f"`splendor queue retry {job_id}` or `splendor repair ingest {source_id}`."
    )


def _lease_expires_at(now: datetime, lease_ttl_seconds: int) -> str:
    return (now + timedelta(seconds=lease_ttl_seconds)).isoformat()


def _lease_is_expired(queue_item: QueueItemRecord, now: datetime) -> bool:
    if queue_item.status != "leased":
        return False
    expires_at = _parse_timestamp(queue_item.lease_expires_at)
    if expires_at is None:
        return True
    return expires_at <= now


def _page_provenance_links(
    *,
    source_id: str,
    run_id: str,
    manifest_ref: str,
    resolved_ref: str,
) -> list[ProvenanceLink]:
    return dedupe_provenance_links(
        [
            make_provenance_link(
                source_id=source_id,
                path_ref=manifest_ref,
                role="generated-from",
            ),
            make_provenance_link(run_id=run_id, role="generated-from"),
            make_provenance_link(path_ref=resolved_ref, role="input"),
        ]
    )


def _source_provenance_links(
    *,
    source_id: str,
    run_id: str,
    page_id: str,
    page_ref: str,
    existing_links: list[ProvenanceLink],
) -> list[ProvenanceLink]:
    return dedupe_provenance_links(
        [
            *existing_links,
            make_provenance_link(page_id=page_id, path_ref=page_ref, role="generated-page"),
            make_provenance_link(run_id=run_id, source_id=source_id, role="output"),
        ]
    )


def _run_input_provenance_links(
    *,
    source_id: str,
    manifest_ref: str,
    resolved_ref: str,
) -> list[ProvenanceLink]:
    return dedupe_provenance_links(
        [
            make_provenance_link(source_id=source_id, path_ref=manifest_ref, role="input"),
            make_provenance_link(source_id=source_id, path_ref=resolved_ref, role="input"),
        ]
    )


def _run_success_provenance_links(
    *,
    source_id: str,
    manifest_ref: str,
    resolved_ref: str,
    page_id: str,
    page_ref: str,
    run_id: str,
) -> list[ProvenanceLink]:
    return dedupe_provenance_links(
        [
            *_run_input_provenance_links(
                source_id=source_id,
                manifest_ref=manifest_ref,
                resolved_ref=resolved_ref,
            ),
            make_provenance_link(page_id=page_id, path_ref=page_ref, role="generated-page"),
            make_provenance_link(run_id=run_id, page_id=page_id, role="output"),
        ]
    )


def _next_attempt_is_due(queue_item: QueueItemRecord, now: datetime) -> bool:
    next_attempt_at = _parse_timestamp(queue_item.next_attempt_at)
    return next_attempt_at is None or next_attempt_at <= now


def _is_queue_eligible(queue_item: QueueItemRecord, now: datetime) -> bool:
    if queue_item.job_type != "ingest_source":
        return False
    if queue_item.status == "pending":
        return True
    if queue_item.status == "failed":
        return _next_attempt_is_due(queue_item, now)
    return _lease_is_expired(queue_item, now)


def _skip_message(queue_item: QueueItemRecord, now: datetime) -> str:
    if queue_item.status == "failed":
        next_attempt_at = _parse_timestamp(queue_item.next_attempt_at)
        if next_attempt_at is not None and next_attempt_at > now:
            return f"retry after {queue_item.next_attempt_at}"
        return "status=failed"
    if queue_item.status == "dead_letter":
        return "status=dead_letter"
    if queue_item.status == "done":
        return "status=done"
    if queue_item.status == "leased":
        expires_at = _parse_timestamp(queue_item.lease_expires_at)
        if expires_at is None:
            return "leased with no expiry"
        if expires_at > now:
            return f"lease active until {queue_item.lease_expires_at}"
        return f"expired lease at {queue_item.lease_expires_at}"
    return f"status={queue_item.status}"


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


def is_ingest_current(root: Path, layout, source: SourceRecord) -> bool:
    return _is_no_op(root, layout, source)


def _validate_workspace_files(layout) -> None:
    required_files = [layout.index_file, layout.log_file]
    missing = [path for path in required_files if not path.exists()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        msg = f"Workspace is missing required wiki files: {joined}. Run `splendor init`."
        raise RuntimeError(msg)


def _load_source_for_queue(root: Path, queue_item: QueueItemRecord) -> tuple[Path, SourceRecord]:
    manifest_path = resolve_workspace_path(root, queue_item.payload_ref, context="Queue payload")
    if not manifest_path.exists():
        msg = f"Queue payload is missing source manifest: {manifest_path}"
        raise FileNotFoundError(msg)
    source = load_source_record(manifest_path)
    expected_source_id = source_id_from_ingest_job_id(queue_item.job_id)
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
    next_attempt_at: str | None = None,
) -> QueueItemRecord:
    finalized = queue_item.model_copy(
        update={
            "status": status,
            "updated_at": utc_now_iso(),
            "lease_owner": None,
            "lease_expires_at": None,
            "next_attempt_at": next_attempt_at,
            "last_error": last_error,
        }
    )
    write_queue_item(queue_path, finalized)
    return finalized


def _mark_attempt_failed(
    *,
    root: Path,
    queue_path: Path,
    queue_item: QueueItemRecord,
    run_path: Path,
    run: RunRecord,
    error_message: str,
    manifest_path: Path | None = None,
    source: SourceRecord | None = None,
    run_id: str | None = None,
) -> None:
    config = load_config(root)
    failed_run = run
    if manifest_path is not None and source is not None:
        manifest_ref = _relative_to_root(root, manifest_path)
        resolved_ref = _best_available_source_ref(source)
        failed_run = run.model_copy(
            update={
                "source_ids": [source.source_id],
                "provenance_links": _run_input_provenance_links(
                    source_id=source.source_id,
                    manifest_ref=manifest_ref,
                    resolved_ref=resolved_ref,
                ),
            }
        )
    failed_run = run.model_copy(
        update={
            "source_ids": failed_run.source_ids,
            "finished_at": utc_now_iso(),
            "status": "failed",
            "errors": [error_message],
            "provenance_links": failed_run.provenance_links,
        }
    )
    write_run_record(run_path, failed_run)
    status = "dead_letter" if queue_item.attempt_count >= queue_item.max_attempts else "failed"
    next_attempt_at = None
    if status == "failed":
        next_attempt_at = _next_attempt_at_for_failure(
            queue_item, config.queue.retry_backoff_seconds
        )
    _finalize_queue_record(
        queue_path,
        queue_item,
        status=status,
        last_error=error_message,
        next_attempt_at=next_attempt_at,
    )
    if manifest_path is not None and source is not None and run_id is not None:
        failed_source = source.model_copy(update={"status": "failed", "last_run_id": run_id})
        write_source_record(manifest_path, failed_source)


def _mark_queue_failed_without_run(
    queue_path: Path,
    queue_item: QueueItemRecord,
    error_message: str,
    backoff_seconds: list[int],
) -> None:
    status = "dead_letter" if queue_item.attempt_count >= queue_item.max_attempts else "failed"
    next_attempt_at = None
    if status == "failed":
        next_attempt_at = _next_attempt_at_for_failure(queue_item, backoff_seconds)
    _finalize_queue_record(
        queue_path,
        queue_item,
        status=status,
        last_error=error_message,
        next_attempt_at=next_attempt_at,
    )


def _next_attempt_at_for_failure(queue_item: QueueItemRecord, backoff_seconds: list[int]) -> str:
    if not backoff_seconds:
        return utc_now_iso()
    backoff_index = max(0, min(queue_item.attempt_count - 1, len(backoff_seconds) - 1))
    return (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=backoff_seconds[backoff_index])
    ).isoformat()


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

    now = _utc_now()
    queue_path = queue_item_path_for(layout, ingest_job_id(source_id))
    existing_queue = load_queue_item(queue_path) if queue_path.exists() else None
    if existing_queue is not None and existing_queue.status == "dead_letter":
        msg = _dead_letter_recovery_message(existing_queue.job_id, source_id)
        raise RuntimeError(msg)
    if (
        existing_queue is not None
        and existing_queue.status == "leased"
        and not _lease_is_expired(existing_queue, now)
    ):
        msg = f"Queue item is already leased: {existing_queue.job_id}"
        raise RuntimeError(msg)

    created_at = now.isoformat()
    if existing_queue is not None and existing_queue.status in {"pending", "leased"}:
        created_at = existing_queue.created_at

    queue_item = QueueItemRecord(
        job_id=ingest_job_id(source_id),
        job_type="ingest_source",
        status="pending",
        created_at=created_at,
        updated_at=now.isoformat(),
        attempt_count=0 if existing_queue is None else existing_queue.attempt_count,
        max_attempts=config.queue.max_attempts
        if existing_queue is None
        else existing_queue.max_attempts,
        payload_ref=_relative_to_root(root, manifest_path),
        lease_owner=None,
        lease_expires_at=None,
        next_attempt_at=None,
        last_error=None,
    )
    write_queue_item(queue_path, queue_item)
    return queue_path


def _claim_ingest_job(
    queue_path: Path, queue_item: QueueItemRecord, *, lease_ttl_seconds: int
) -> QueueItemRecord:
    now = _utc_now()
    leased_queue = queue_item.model_copy(
        update={
            "status": "leased",
            "updated_at": now.isoformat(),
            "attempt_count": queue_item.attempt_count + 1,
            "lease_owner": _lease_owner(),
            "lease_expires_at": _lease_expires_at(now, lease_ttl_seconds),
            "next_attempt_at": None,
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
    if queue_item.status not in {"pending", "leased", "failed"}:
        msg = f"Queue item is not runnable: {queue_item.job_id}"
        raise RuntimeError(msg)
    if queue_item.status == "failed" and not _next_attempt_is_due(queue_item, now):
        msg = f"Queue item retry is not due until {queue_item.next_attempt_at}: {queue_item.job_id}"
        raise RuntimeError(msg)

    queue_item = _claim_ingest_job(
        queue_path, queue_item, lease_ttl_seconds=config.queue.lease_ttl_seconds
    )

    try:
        manifest_path, source = _load_source_for_queue(root, queue_item)
    except (FileNotFoundError, ValueError) as exc:
        _mark_queue_failed_without_run(
            queue_path, queue_item, str(exc), config.queue.retry_backoff_seconds
        )
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
        source_ids=[source.source_id],
        provenance_links=_run_input_provenance_links(
            source_id=source.source_id,
            manifest_ref=_relative_to_root(root, manifest_path),
            resolved_ref=_best_available_source_ref(source),
        ),
    )
    write_run_record(run_path, run)

    try:
        resolved_source = resolve_source_content(root, source, layout.raw_sources_dir)
        run = run.model_copy(
            update={
                "input_refs": [
                    _relative_to_root(root, manifest_path),
                    resolved_source.resolved_ref,
                ],
                "provenance_links": _run_input_provenance_links(
                    source_id=source.source_id,
                    manifest_ref=_relative_to_root(root, manifest_path),
                    resolved_ref=resolved_source.resolved_ref,
                ),
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
        finished_at = utc_now_iso()
        frontmatter = KnowledgePageFrontmatter(
            kind="source-summary",
            title=source.title,
            page_id=source.source_id,
            status="active",
            review_state="machine-generated",
            source_refs=[source.source_id],
            generated_by_run_ids=[run_id],
            last_generated_at=finished_at,
            confidence=1.0,
            tags=["source-summary", source.source_type],
            provenance_links=_page_provenance_links(
                source_id=source.source_id,
                run_id=run_id,
                manifest_ref=_relative_to_root(root, manifest_path),
                resolved_ref=resolved_source.resolved_ref,
            ),
        )
        source_section = "\n".join(
            [
                f"- Source ID: `{source.source_id}`",
                f"- Source type: `{source.source_type}`",
                f"- Registered path: `{registered_path}`",
                f"- Source file: `{resolved_source.resolved_ref}`",
            ]
        )
        key_facts = [
            f"Source ID: `{source.source_id}`",
            f"Source type: `{source.source_type}`",
            f"Checksum: `{source.checksum}`",
            f"Source ref: `{canonical_source_ref(source)}`",
            f"Added at: `{source.added_at}`",
            f"Ingested at: `{finished_at}`",
            *_build_content_key_facts(source_text),
        ]
        provenance_lines = [
            f"Manifest: `{_relative_to_root(root, manifest_path)}`",
            f"{resolved_source.content_origin_label}: `{resolved_source.resolved_ref}`",
            f"Run ID: `{run_id}`",
            f"Pipeline version: `{__version__}`",
        ]
        page_content = render_source_summary_page(
            frontmatter,
            source_section=source_section,
            summary=_build_summary(source, source_text),
            key_facts=key_facts,
            extract=_rendered_extract(source_text, extract_mode),
            contradictions=render_contradiction_lines(
                page_ref=page_relpath, contradictions=frontmatter.contradictions
            ),
            provenance=provenance_lines,
        )
        current_snapshot = snapshot_from_rendered_page(
            root=root,
            page_path=page_path,
            frontmatter=frontmatter,
            page_content=page_content,
        )
        contradiction_review = review_source_summary_contradictions(
            root=root,
            layout=layout,
            config=config,
            current_snapshot=current_snapshot,
            run_id=run_id,
        )
        frontmatter = contradiction_review.frontmatter
        page_content = render_source_summary_page(
            frontmatter,
            source_section=source_section,
            summary=_build_summary(source, source_text),
            key_facts=key_facts,
            extract=_rendered_extract(source_text, extract_mode),
            contradictions=render_contradiction_lines(
                page_ref=page_relpath, contradictions=frontmatter.contradictions
            ),
            provenance=provenance_lines,
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
                "generated_by_run_ids": sorted(set([*source.generated_by_run_ids, run_id])),
                "linked_pages": sorted(set([*source.linked_pages, page_relpath])),
                "provenance_links": _source_provenance_links(
                    source_id=source.source_id,
                    run_id=run_id,
                    page_id=source.source_id,
                    page_ref=page_relpath,
                    existing_links=source.provenance_links,
                ),
            }
        )
        success_run = run.model_copy(
            update={
                "finished_at": finished_at,
                "status": "succeeded",
                "output_refs": [
                    page_relpath,
                    _relative_to_root(root, layout.index_file),
                    _relative_to_root(root, layout.log_file),
                    *[
                        _relative_to_root(root, path)
                        for path, _content in contradiction_review.page_updates
                    ],
                    *[
                        _relative_to_root(root, update.task_path)
                        for update in contradiction_review.task_updates
                    ],
                ],
                "page_ids": [source.source_id],
                "page_refs": [page_relpath],
                "contradiction_ids": contradiction_review.contradiction_ids,
                "task_ids": contradiction_review.task_ids,
                "warnings": [*run.warnings, *contradiction_review.warnings],
                "provenance_links": _run_success_provenance_links(
                    source_id=source.source_id,
                    manifest_ref=_relative_to_root(root, manifest_path),
                    resolved_ref=resolved_source.resolved_ref,
                    page_id=source.source_id,
                    page_ref=page_relpath,
                    run_id=run_id,
                ),
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
                extra_writes=[
                    *contradiction_review.page_updates,
                    *[
                        (update.task_path, update.content)
                        for update in contradiction_review.task_updates
                    ],
                ],
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
            root=root,
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
            root=root,
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

    total = len(ordered_items)
    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0
    item_results: list[DrainItemResult] = []

    for queue_path, queue_item in ordered_items:
        source_id = source_id_from_ingest_job_id(queue_item.job_id) or queue_item.job_id
        if not _is_queue_eligible(queue_item, now):
            skipped += 1
            item_results.append(
                DrainItemResult(
                    source_id=source_id,
                    queue_path=queue_path,
                    outcome="skipped",
                    message=_skip_message(queue_item, now),
                )
            )
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
        total=total,
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
