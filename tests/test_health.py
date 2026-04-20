from datetime import UTC, datetime, timedelta
from pathlib import Path

from splendor import __version__
from splendor.commands.add_source import add_source
from splendor.commands.health import run_health_checks
from splendor.commands.ingest import enqueue_ingest_job
from splendor.commands.init import initialize_workspace
from splendor.config import load_config
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
