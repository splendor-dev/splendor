import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from splendor import __version__
from splendor.commands.add_source import add_source
from splendor.commands.health import run_health_checks
from splendor.commands.ingest import enqueue_ingest_job
from splendor.commands.init import initialize_workspace
from splendor.config import default_config, load_config, write_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter, ProvenanceLink, QueueItemRecord, RunRecord
from splendor.state.runtime import write_queue_item, write_run_record
from splendor.state.source_registry import load_source_record, write_source_record


def _run_health(root: Path):
    layout = resolve_layout(root, load_config(root))
    return run_health_checks(root, layout)


def test_run_health_checks_returns_no_issues_for_initialized_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    result = _run_health(tmp_path)

    assert result.issues == []


def test_run_health_checks_reports_missing_source_derived_artifact(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source_record = load_source_record(added.manifest_path).model_copy(
        update={"derived_artifacts": ["derived/parsed/missing.txt"]}
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["missing-source-derived-artifact"]
    assert result.issues[0].path == added.manifest_path.relative_to(tmp_path).as_posix()


def test_run_health_checks_hints_missing_active_workspace_source_repair(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    add_source(tmp_path, source)
    source.unlink()

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["source-health-check-failed"]
    assert result.issues[0].remediation_hint == (
        "Run splendor source update-path brief.md <new-path>; inspect current freshness first "
        "with splendor source freshness."
    )


def test_run_health_checks_does_not_hint_update_path_for_pointer_source(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    add_source(tmp_path, source, storage_mode="pointer")
    source.unlink()

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["source-health-check-failed"]
    assert result.issues[0].remediation_hint == (
        "Run splendor source freshness to inspect the missing curated source; "
        "pointer-backed sources are not supported by source update-path yet."
    )


def test_run_health_checks_hints_checksum_mismatch_active_workspace_source(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    add_source(tmp_path, source)
    source.write_text("# Brief\n\nupdated\n", encoding="utf-8")

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["source-health-check-failed"]
    assert result.issues[0].remediation_hint == (
        "Run splendor source refresh brief.md, then splendor ingest --pending; for all changed "
        "curated workspace sources run splendor ingest --changed."
    )


def test_run_health_checks_accepts_ocr_derived_artifact_links(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "diagram.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    added = add_source(tmp_path, source)
    artifact = tmp_path / "derived" / "ocr" / f"{added.source_id}.txt"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("Extracted OCR text\n", encoding="utf-8")
    source_record = load_source_record(added.manifest_path).model_copy(
        update={"derived_artifacts": [artifact.relative_to(tmp_path).as_posix()]}
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_health(tmp_path)

    assert result.issues == []


def test_run_health_checks_accepts_superseded_workspace_source_versions(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    refreshed = add_source(tmp_path, source)
    original = load_source_record(added.manifest_path).model_copy(
        update={"superseded_by": refreshed.source_id}
    )
    updated = load_source_record(refreshed.manifest_path).model_copy(
        update={"supersedes": [added.source_id]}
    )
    write_source_record(added.manifest_path, original)
    write_source_record(refreshed.manifest_path, updated)

    result = _run_health(tmp_path)

    assert result.issues == []


def test_run_health_checks_only_exempts_exact_pruned_superseded_summary_refs(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    refreshed = add_source(tmp_path, source)
    original = load_source_record(added.manifest_path).model_copy(
        update={"superseded_by": refreshed.source_id}
    )
    updated = load_source_record(refreshed.manifest_path).model_copy(
        update={"supersedes": [added.source_id]}
    )
    write_source_record(added.manifest_path, original)
    write_source_record(refreshed.manifest_path, updated)
    run = RunRecord(
        run_id="run-pruned",
        job_id=f"ingest-{added.source_id}",
        job_type="ingest_source",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        status="succeeded",
        pipeline_version=__version__,
        source_ids=[added.source_id],
        page_ids=[added.source_id, "topic-missing"],
        page_refs=[f"wiki/sources/{added.source_id}.md", "wiki/topics/missing.md"],
        provenance_links=[
            ProvenanceLink(
                page_id=added.source_id,
                path_ref=f"wiki/sources/{added.source_id}.md",
                role="generated-page",
            ),
            ProvenanceLink(page_id="topic-missing", role="generated-page"),
            ProvenanceLink(path_ref="wiki/topics/missing.md", role="generated-page"),
        ],
    )
    write_run_record(tmp_path / "state" / "runs" / "run-pruned.json", run)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == [
        "missing-run-page-id",
        "missing-run-page-ref",
        "missing-run-provenance-page-ref",
        "missing-run-provenance-path",
    ]


def test_run_health_checks_still_validates_superseded_copied_source_artifacts(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="copy")
    source_record = load_source_record(added.manifest_path).model_copy(
        update={"superseded_by": "src-next"}
    )
    write_source_record(added.manifest_path, source_record)
    assert added.stored_path is not None
    added.stored_path.unlink()

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["source-health-check-failed"]


def test_run_health_checks_reports_invalid_queue_and_run_records(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "state" / "queue" / "ingest-bad.json").write_text("{bad json}\n", encoding="utf-8")
    (tmp_path / "state" / "runs" / "run-bad.json").write_text("{bad json}\n", encoding="utf-8")

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} == {"invalid-queue-record", "invalid-run-record"}


def test_run_health_checks_normalizes_z_timestamps_and_rejects_naive_timestamps(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    expired_lease_z = (
        (datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=5))
        .isoformat()
        .replace("+00:00", "Z")
    )
    z_queue = queue_record.model_copy(
        update={
            "status": "leased",
            "lease_owner": "local-cli:123",
            "lease_expires_at": expired_lease_z,
        }
    )
    write_queue_item(queue_path, z_queue)

    second_source = tmp_path / "naive.md"
    second_source.write_text("# Naive\n\nhello world\n", encoding="utf-8")
    second_added = add_source(tmp_path, second_source)
    second_queue_path = enqueue_ingest_job(tmp_path, second_added.source_id)
    second_queue = QueueItemRecord.model_validate_json(
        second_queue_path.read_text(encoding="utf-8")
    )
    naive_queue = second_queue.model_copy(
        update={
            "status": "leased",
            "lease_owner": "local-cli:456",
            "lease_expires_at": "2026-04-20T09:00:00",
        }
    )
    write_queue_item(second_queue_path, naive_queue)

    result = _run_health(tmp_path)

    issue_codes = [issue.code for issue in result.issues]
    assert "expired-queue-lease" in issue_codes
    assert "invalid-queue-lease-expiry" in issue_codes
    invalid_issue = next(
        issue for issue in result.issues if issue.code == "invalid-queue-lease-expiry"
    )
    assert "must include a timezone offset" in invalid_issue.message


def test_run_health_checks_reports_stale_queue_and_run_runtime_state(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    expired_queue = queue_record.model_copy(
        update={
            "status": "leased",
            "attempt_count": 4,
            "lease_owner": "local-cli:123",
            "lease_expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        }
    )
    write_queue_item(queue_path, expired_queue)

    run_id = f"run-{added.source_id}-stale"
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    run_path = layout.runs_dir / f"{run_id}.json"
    write_run_record(
        run_path,
        RunRecord(
            run_id=run_id,
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            status="running",
            finished_at=None,
            input_refs=[
                added.manifest_path.relative_to(tmp_path).as_posix(),
                "brief.md",
            ],
            pipeline_version=__version__,
        ),
    )

    source_record = load_source_record(added.manifest_path).model_copy(
        update={"status": "ingested", "last_run_id": run_id}
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "expired-queue-lease",
        "queue-attempt-count-exceeded",
        "unfinished-run",
        "source-generated-by-run-mismatch",
        "source-last-run-source-id-mismatch",
        "source-last-run-status-mismatch",
    }


def test_run_health_checks_reports_missing_runtime_provenance_links(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    run_id = f"run-{added.source_id}-ok"
    page_path = tmp_path / "wiki" / "sources" / f"{added.source_id}.md"
    page_path.write_text(
        (
            "---\n"
            f"kind: source-summary\ntitle: Example\npage_id: {added.source_id}\n"
            "status: active\nreview_state: machine-generated\n"
            f"source_refs:\n- {added.source_id}\n"
            "generated_by_run_ids: []\n"
            "confidence: 1.0\n"
            "---\n\nbody\n"
        ),
        encoding="utf-8",
    )
    write_run_record(
        layout.runs_dir / f"{run_id}.json",
        RunRecord(
            run_id=run_id,
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:01:00+00:00",
            status="succeeded",
            input_refs=[added.manifest_path.relative_to(tmp_path).as_posix(), "brief.md"],
            output_refs=[page_path.relative_to(tmp_path).as_posix()],
            pipeline_version=__version__,
            source_ids=[added.source_id],
            page_ids=[],
            page_refs=[],
            provenance_links=[],
        ),
    )
    source_record = load_source_record(added.manifest_path).model_copy(
        update={
            "status": "ingested",
            "last_run_id": run_id,
            "linked_pages": [page_path.relative_to(tmp_path).as_posix()],
            "generated_by_run_ids": [],
        }
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_health(tmp_path)

    assert {
        issue.code
        for issue in result.issues
        if issue.code.endswith("page-ids")
        or issue.code.endswith("page-refs")
        or issue.code.endswith("generated-page-provenance")
        or issue.code.endswith("run-mismatch")
    } == {
        "succeeded-run-missing-page-ids",
        "succeeded-run-missing-page-refs",
        "succeeded-run-missing-generated-page-provenance",
        "source-generated-by-run-mismatch",
        "page-generated-by-run-mismatch",
    }


def test_run_health_checks_reports_missing_task_ids_and_contradiction_ids(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    run_id = f"run-{added.source_id}-ok"
    page_path = tmp_path / "wiki" / "sources" / f"{added.source_id}.md"
    frontmatter = KnowledgePageFrontmatter(
        kind="source-summary",
        title="Example",
        page_id=added.source_id,
        status="active",
        review_state="contested",
        source_refs=[added.source_id],
        generated_by_run_ids=[run_id],
        confidence=1.0,
        contradictions=[
            {
                "contradiction_id": "contradiction-present",
                "summary": "Present contradiction.",
                "detected_at": "2026-04-22T10:00:00+00:00",
                "related_page_ids": [added.source_id],
                "related_source_ids": [added.source_id],
                "review_task_id": "task-review-present",
                "evidence": [
                    {
                        "page_id": added.source_id,
                        "source_id": added.source_id,
                        "run_id": run_id,
                        "path_ref": page_path.relative_to(tmp_path).as_posix(),
                        "excerpt": "Conflict excerpt.",
                    }
                ],
            }
        ],
    )
    page_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    page_path.write_text(
        f"---\n{frontmatter_text}\n---\n\nbody\n",
        encoding="utf-8",
    )
    write_run_record(
        layout.runs_dir / f"{run_id}.json",
        RunRecord(
            run_id=run_id,
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:01:00+00:00",
            status="succeeded",
            input_refs=[added.manifest_path.relative_to(tmp_path).as_posix(), "brief.md"],
            output_refs=[page_path.relative_to(tmp_path).as_posix()],
            pipeline_version=__version__,
            source_ids=[added.source_id],
            page_ids=[added.source_id],
            page_refs=[page_path.relative_to(tmp_path).as_posix()],
            contradiction_ids=["contradiction-missing"],
            task_ids=["task-review-missing"],
            provenance_links=[
                {
                    "page_id": added.source_id,
                    "path_ref": page_path.relative_to(tmp_path).as_posix(),
                    "role": "generated-page",
                }
            ],
        ),
    )
    source_record = load_source_record(added.manifest_path).model_copy(
        update={
            "status": "ingested",
            "last_run_id": run_id,
            "linked_pages": [page_path.relative_to(tmp_path).as_posix()],
            "generated_by_run_ids": [run_id],
        }
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} >= {
        "missing-run-task-id",
        "missing-run-contradiction-id",
    }


def test_run_health_checks_requires_generated_page_role_for_run_provenance(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    run_id = f"run-{added.source_id}-ok"
    page_path = tmp_path / "wiki" / "sources" / f"{added.source_id}.md"
    page_path.write_text(
        (
            "---\n"
            f"kind: source-summary\ntitle: Example\npage_id: {added.source_id}\n"
            "status: active\nreview_state: machine-generated\n"
            f"source_refs:\n- {added.source_id}\n"
            f"generated_by_run_ids:\n- {run_id}\n"
            "confidence: 1.0\n"
            "---\n\nbody\n"
        ),
        encoding="utf-8",
    )
    write_run_record(
        layout.runs_dir / f"{run_id}.json",
        RunRecord(
            run_id=run_id,
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:01:00+00:00",
            status="succeeded",
            input_refs=[added.manifest_path.relative_to(tmp_path).as_posix(), "brief.md"],
            output_refs=[page_path.relative_to(tmp_path).as_posix()],
            pipeline_version=__version__,
            source_ids=[added.source_id],
            page_ids=[added.source_id],
            page_refs=[page_path.relative_to(tmp_path).as_posix()],
            provenance_links=[
                {
                    "page_id": added.source_id,
                    "path_ref": page_path.relative_to(tmp_path).as_posix(),
                    "role": "output",
                }
            ],
        ),
    )
    source_record = load_source_record(added.manifest_path).model_copy(
        update={
            "status": "ingested",
            "last_run_id": run_id,
            "linked_pages": [page_path.relative_to(tmp_path).as_posix()],
            "generated_by_run_ids": [run_id],
        }
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == [
        "succeeded-run-missing-generated-page-provenance"
    ]


def test_run_health_checks_reports_missing_runtime_directories_nonfatally(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    for path in (
        tmp_path / "state" / "manifests" / "sources",
        tmp_path / "state" / "queue",
        tmp_path / "state" / "runs",
    ):
        shutil.rmtree(path)

    result = _run_health(tmp_path)

    assert result.checked_count == 3
    assert [issue.code for issue in result.issues] == [
        "missing-directory",
        "missing-directory",
        "missing-directory",
    ]
    assert {issue.path for issue in result.issues} == {
        "state/manifests/sources",
        "state/queue",
        "state/runs",
    }


def test_run_health_checks_reports_queue_payload_and_last_run_mismatches(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    broken_queue = queue_record.model_copy(
        update={
            "payload_ref": "../outside-manifest.json",
            "last_error": "should not be here",
        }
    )
    write_queue_item(queue_path, broken_queue)

    source_record = load_source_record(added.manifest_path).model_copy(
        update={"status": "failed", "last_run_id": "run-missing"}
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "invalid-queue-error-state",
        "invalid-queue-payload-ref",
        "missing-last-run-record",
    }


def test_run_health_checks_reports_invalid_failed_queue_and_run_shapes(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    invalid_queue = queue_record.model_copy(update={"status": "failed", "last_error": None})
    write_queue_item(queue_path, invalid_queue)

    layout = resolve_layout(tmp_path, load_config(tmp_path))
    run_id = f"run-{added.source_id}-failed"
    write_run_record(
        layout.runs_dir / f"{run_id}.json",
        RunRecord(
            run_id=run_id,
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at=None,
            status="failed",
            input_refs=[
                added.manifest_path.relative_to(tmp_path).as_posix(),
                "brief.md",
            ],
            errors=[],
            pipeline_version=__version__,
        ),
    )

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "invalid-queue-error-state",
        "invalid-run-error-state",
        "invalid-run-finish-state",
    }


def test_run_health_checks_hints_dead_letter_queue_repair(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    dead_letter = queue_record.model_copy(update={"status": "dead_letter", "last_error": None})
    write_queue_item(queue_path, dead_letter)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-queue-error-state"]
    assert result.issues[0].remediation_hint == (
        f"Run splendor repair ingest {added.source_id} or splendor queue retry "
        f"ingest-{added.source_id} after reviewing the dead-letter error."
    )


def test_run_health_checks_reports_queue_and_run_shape_mismatches(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    mismatched_queue = queue_record.model_copy(
        update={
            "job_id": "other-job",
            "job_type": "refresh_topic",
        }
    )
    write_queue_item(queue_path, mismatched_queue)

    layout = resolve_layout(tmp_path, load_config(tmp_path))
    run_path = layout.runs_dir / f"run-{added.source_id}-shape.json"
    write_run_record(
        run_path,
        RunRecord(
            run_id="other-run",
            job_id=f"ingest-{added.source_id}",
            job_type="refresh_topic",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="succeeded",
            input_refs=[],
            errors=[],
            pipeline_version=__version__,
        ),
    )

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "queue-job-id-mismatch",
        "unsupported-queue-job-type",
        "run-id-mismatch",
        "unsupported-run-job-type",
    }
    issue_by_code = {issue.code: issue for issue in result.issues}
    assert issue_by_code["queue-job-id-mismatch"].record_id == queue_path.stem
    assert issue_by_code["unsupported-queue-job-type"].record_id == queue_path.stem
    assert issue_by_code["run-id-mismatch"].record_id == run_path.stem
    assert issue_by_code["unsupported-run-job-type"].record_id == run_path.stem


def test_run_health_checks_reports_invalid_queue_runtime_details(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    invalid_queue = queue_record.model_copy(
        update={
            "status": "pending",
            "lease_owner": "local-cli:123",
            "lease_expires_at": "not-a-timestamp",
        }
    )
    write_queue_item(queue_path, invalid_queue)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-queue-lease-state"]


def test_run_health_checks_reports_invalid_queue_next_attempt_state(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    invalid_queue = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    invalid_queue = invalid_queue.model_copy(
        update={"status": "pending", "next_attempt_at": "2026-04-20T09:00:00+00:00"}
    )
    write_queue_item(queue_path, invalid_queue)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-queue-next-attempt-state"]


def test_run_health_checks_reports_invalid_queue_next_attempt_timestamp(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    invalid_queue = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    invalid_queue = invalid_queue.model_copy(
        update={"status": "failed", "last_error": "temporary", "next_attempt_at": "bad-time"}
    )
    write_queue_item(queue_path, invalid_queue)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-queue-next-attempt"]


def test_run_health_checks_reports_invalid_leased_queue_shape(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    invalid_queue = queue_record.model_copy(
        update={
            "status": "leased",
            "lease_owner": None,
            "lease_expires_at": None,
        }
    )
    write_queue_item(queue_path, invalid_queue)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-queue-lease-state"]


def test_run_health_checks_reports_missing_and_invalid_queue_payloads(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    missing_queue = queue_record.model_copy(
        update={"payload_ref": "state/manifests/sources/missing.json"}
    )
    write_queue_item(queue_path, missing_queue)

    second_source = tmp_path / "broken.md"
    second_source.write_text("# Broken\n\nhello world\n", encoding="utf-8")
    second_added = add_source(tmp_path, second_source)
    enqueue_ingest_job(tmp_path, second_added.source_id)
    manifest_path = second_added.manifest_path
    manifest_path.write_text("{bad json}\n", encoding="utf-8")

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "missing-queue-payload",
        "source-health-check-failed",
    }


def test_run_health_checks_reports_queue_payload_source_and_path_mismatches_for_custom_layout(
    tmp_path: Path,
) -> None:
    config = default_config(project_name="custom")
    config.layout.source_records_dir = "custom/manifests"
    write_config(tmp_path, config)
    initialize_workspace(tmp_path)
    custom_layout = resolve_layout(tmp_path, load_config(tmp_path))
    custom_layout.source_records_dir.mkdir(parents=True, exist_ok=True)

    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))

    wrong_manifest_dir = tmp_path / "state" / "manifests" / "sources"
    wrong_manifest_dir.mkdir(parents=True, exist_ok=True)
    wrong_manifest_path = wrong_manifest_dir / f"{added.source_id}.json"
    wrong_manifest_path.write_text(
        added.manifest_path.read_text(encoding="utf-8").replace(added.source_id, "src-other", 1),
        encoding="utf-8",
    )
    wrong_queue = queue_record.model_copy(
        update={"payload_ref": wrong_manifest_path.relative_to(tmp_path).as_posix()}
    )
    write_queue_item(queue_path, wrong_queue)

    source_record = load_source_record(added.manifest_path).model_copy(
        update={"status": "failed", "last_run_id": None}
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_health(tmp_path)

    issue_codes = {issue.code for issue in result.issues}
    assert "queue-payload-source-mismatch" in issue_codes
    assert "queue-payload-path-mismatch" in issue_codes
    missing_run_issue = next(
        issue for issue in result.issues if issue.code == "source-missing-last-run"
    )
    assert missing_run_issue.path == "custom/manifests/" + added.manifest_path.name


def test_run_health_checks_reports_invalid_payload_manifest_for_valid_source_record(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))

    alternate_manifest = tmp_path / "scratch" / "alternate.json"
    alternate_manifest.parent.mkdir(parents=True, exist_ok=True)
    alternate_manifest.write_text("{bad json}\n", encoding="utf-8")
    broken_queue = queue_record.model_copy(update={"payload_ref": "scratch/alternate.json"})
    write_queue_item(queue_path, broken_queue)

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-queue-payload-manifest"]


def test_run_health_checks_reports_run_state_and_reference_problems(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    run_path = layout.runs_dir / "run-shape.json"
    write_run_record(
        run_path,
        RunRecord(
            run_id="run-shape",
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="running",
            input_refs=["/tmp/absolute.txt"],
            output_refs=["../outside.md"],
            errors=["boom"],
            pipeline_version=__version__,
        ),
    )

    second_run_path = layout.runs_dir / "run-success.json"
    write_run_record(
        second_run_path,
        RunRecord(
            run_id="run-success",
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="succeeded",
            input_refs=[],
            errors=["should not be here"],
            pipeline_version=__version__,
        ),
    )

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "invalid-run-finish-state",
        "unfinished-run",
        "invalid-run-reference",
        "invalid-run-error-state",
        "succeeded-run-missing-page-ids",
        "succeeded-run-missing-page-refs",
        "succeeded-run-missing-generated-page-provenance",
    }


def test_run_health_checks_hints_unknown_source_refs_without_unsafe_repair(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    write_run_record(
        layout.runs_dir / "run-unknown-source.json",
        RunRecord(
            run_id="run-unknown-source",
            job_id="ingest-src-missing",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="failed",
            input_refs=[],
            errors=["source disappeared"],
            pipeline_version=__version__,
            source_ids=["src-missing"],
            provenance_links=[
                ProvenanceLink(source_id="src-missing", role="input"),
                ProvenanceLink(source_id="src-missing", role="input"),
            ],
        ),
    )

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == [
        "missing-run-source-id",
        "missing-run-provenance-source-ref",
    ]
    assert {issue.remediation_hint for issue in result.issues} == {
        "Diagnostic only: inspect the referenced run/page/source records and file a follow-up; "
        "no direct provenance rewrite command is available."
    }
    assert all(
        "source update-path" not in (issue.remediation_hint or "") for issue in result.issues
    )


def test_run_health_checks_resolves_run_sources_against_manifest_store_when_source_drifted(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source.write_text("# Brief\n\nChanged after registration.\n", encoding="utf-8")
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    write_run_record(
        layout.runs_dir / "run-drifted-source.json",
        RunRecord(
            run_id="run-drifted-source",
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="failed",
            input_refs=[],
            errors=["source drifted"],
            pipeline_version=__version__,
            source_ids=[added.source_id],
            provenance_links=[
                ProvenanceLink(source_id=added.source_id, role="input"),
                ProvenanceLink(source_id=added.source_id, role="input"),
            ],
        ),
    )

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == ["source-health-check-failed"]
    assert "checksum mismatch for ingestion" in result.issues[0].message


def test_run_health_checks_accepts_repeated_run_source_provenance_when_manifest_exists(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    write_run_record(
        layout.runs_dir / "run-existing-source.json",
        RunRecord(
            run_id="run-existing-source",
            job_id=f"ingest-{added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="failed",
            input_refs=[],
            errors=["representative failed run"],
            pipeline_version=__version__,
            source_ids=[added.source_id],
            provenance_links=[
                ProvenanceLink(source_id=added.source_id, role="input"),
                ProvenanceLink(source_id=added.source_id, role="input"),
            ],
        ),
    )

    result = _run_health(tmp_path)

    assert result.issues == []


def test_run_health_checks_does_not_repeat_generic_hint_for_missing_page_refs(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    write_run_record(
        layout.runs_dir / "run-missing-page.json",
        RunRecord(
            run_id="run-missing-page",
            job_id="ingest-src-example",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="failed",
            input_refs=[],
            errors=["page disappeared"],
            pipeline_version=__version__,
            page_ids=["missing-page"],
            page_refs=["wiki/topics/missing.md"],
            provenance_links=[
                ProvenanceLink(page_id="missing-page", role="generated-page"),
                ProvenanceLink(path_ref="wiki/topics/missing.md", role="generated-page"),
            ],
        ),
    )

    result = _run_health(tmp_path)

    assert [issue.code for issue in result.issues] == [
        "missing-run-page-id",
        "missing-run-page-ref",
        "missing-run-provenance-page-ref",
        "missing-run-provenance-path",
    ]
    assert all(issue.remediation_hint is None for issue in result.issues)


def test_run_health_checks_reports_source_runtime_cross_reference_problems(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    registered_source = tmp_path / "registered.md"
    registered_source.write_text("# Registered\n\nhello world\n", encoding="utf-8")
    registered_added = add_source(tmp_path, registered_source)
    registered_record = load_source_record(registered_added.manifest_path).model_copy(
        update={"last_run_id": "run-stray"}
    )
    write_source_record(registered_added.manifest_path, registered_record)

    invalid_run_source = tmp_path / "invalid-run.md"
    invalid_run_source.write_text("# Invalid Run\n\nhello world\n", encoding="utf-8")
    invalid_run_added = add_source(tmp_path, invalid_run_source)
    invalid_record = load_source_record(invalid_run_added.manifest_path).model_copy(
        update={"status": "failed", "last_run_id": "run-invalid"}
    )
    write_source_record(invalid_run_added.manifest_path, invalid_record)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    (layout.runs_dir / "run-invalid.json").write_text("{bad json}\n", encoding="utf-8")

    mismatched_job_source = tmp_path / "job-mismatch.md"
    mismatched_job_source.write_text("# Job Mismatch\n\nhello world\n", encoding="utf-8")
    mismatched_job_added = add_source(tmp_path, mismatched_job_source)
    mismatched_run_path = layout.runs_dir / "run-job-mismatch.json"
    write_run_record(
        mismatched_run_path,
        RunRecord(
            run_id="run-job-mismatch",
            job_id="ingest-someone-else",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="succeeded",
            input_refs=[],
            pipeline_version=__version__,
        ),
    )
    mismatched_record = load_source_record(mismatched_job_added.manifest_path).model_copy(
        update={"status": "ingested", "last_run_id": "run-job-mismatch"}
    )
    write_source_record(mismatched_job_added.manifest_path, mismatched_record)

    failed_status_source = tmp_path / "failed-status.md"
    failed_status_source.write_text("# Failed Status\n\nhello world\n", encoding="utf-8")
    failed_status_added = add_source(tmp_path, failed_status_source)
    failed_status_run_path = layout.runs_dir / "run-failed-status.json"
    write_run_record(
        failed_status_run_path,
        RunRecord(
            run_id="run-failed-status",
            job_id=f"ingest-{failed_status_added.source_id}",
            job_type="ingest_source",
            started_at="2026-04-20T09:00:00+00:00",
            finished_at="2026-04-20T09:05:00+00:00",
            status="succeeded",
            input_refs=[],
            pipeline_version=__version__,
        ),
    )
    failed_status_record = load_source_record(failed_status_added.manifest_path).model_copy(
        update={"status": "failed", "last_run_id": "run-failed-status"}
    )
    write_source_record(failed_status_added.manifest_path, failed_status_record)

    result = _run_health(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "registered-source-has-last-run",
        "invalid-run-record",
        "source-generated-by-run-mismatch",
        "source-last-run-invalid",
        "source-last-run-job-mismatch",
        "source-last-run-source-id-mismatch",
        "source-last-run-status-mismatch",
        "succeeded-run-missing-page-ids",
        "succeeded-run-missing-page-refs",
        "succeeded-run-missing-generated-page-provenance",
    }
