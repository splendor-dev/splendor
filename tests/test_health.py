import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from splendor import __version__
from splendor.commands.add_source import add_source
from splendor.commands.health import run_health_checks
from splendor.commands.ingest import enqueue_ingest_job
from splendor.commands.init import initialize_workspace
from splendor.config import default_config, load_config, write_config
from splendor.layout import resolve_layout
from splendor.schemas import QueueItemRecord, RunRecord
from splendor.state.runtime import write_queue_item, write_run_record
from splendor.state.source_registry import load_source_record, write_source_record


def _run_health(root: Path):
    layout = resolve_layout(root, load_config(root))
    return run_health_checks(root, layout)


def test_run_health_checks_returns_no_issues_for_initialized_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    result = _run_health(tmp_path)

    assert result.issues == []


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
    z_queue = queue_record.model_copy(
        update={
            "status": "leased",
            "lease_owner": "local-cli:123",
            "lease_expires_at": "2026-04-20T09:00:00Z",
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
        "source-last-run-status-mismatch",
    }


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
    }


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
        "source-last-run-invalid",
        "source-last-run-job-mismatch",
        "source-last-run-status-mismatch",
    }
