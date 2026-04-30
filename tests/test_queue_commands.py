import json
from pathlib import Path

import pytest

from splendor.cli import main
from splendor.commands.add_source import add_source
from splendor.commands.ingest import enqueue_ingest_job
from splendor.commands.init import initialize_workspace
from splendor.commands.queue import inspect_queue, inspect_queue_job, retry_queue_job
from splendor.schemas import QueueItemRecord
from splendor.state.runtime import load_queue_item, write_queue_item
from splendor.state.source_registry import load_source_record


def test_inspect_queue_returns_counts_and_stable_order(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    later = tmp_path / "later.md"
    earlier = tmp_path / "earlier.md"
    later.write_text("# Later\n\nhello\n", encoding="utf-8")
    earlier.write_text("# Earlier\n\nhello\n", encoding="utf-8")
    later_added = add_source(tmp_path, later)
    earlier_added = add_source(tmp_path, earlier)
    later_queue_path = enqueue_ingest_job(tmp_path, later_added.source_id)
    earlier_queue_path = enqueue_ingest_job(tmp_path, earlier_added.source_id)
    later_queue = load_queue_item(later_queue_path).model_copy(
        update={"created_at": "2026-04-10T12:00:00+00:00"}
    )
    earlier_queue = load_queue_item(earlier_queue_path).model_copy(
        update={"created_at": "2026-04-10T11:00:00+00:00", "status": "failed", "last_error": "x"}
    )
    write_queue_item(later_queue_path, later_queue)
    write_queue_item(earlier_queue_path, earlier_queue)

    result = inspect_queue(tmp_path)

    assert result.total == 2
    assert result.status_counts == {"failed": 1, "pending": 1}
    assert [item.job_id for item in result.items] == [
        f"ingest-{earlier_added.source_id}",
        f"ingest-{later_added.source_id}",
    ]


def test_inspect_queue_job_returns_detail_and_rejects_missing_job(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)

    item = inspect_queue_job(tmp_path, f"ingest-{added.source_id}")

    assert item.record_path == queue_path.relative_to(tmp_path)
    assert item.source_id == added.source_id
    assert item.payload_ref == f"state/manifests/sources/{added.source_id}.json"
    with pytest.raises(FileNotFoundError, match="Unknown queue job"):
        inspect_queue_job(tmp_path, "ingest-missing")


def test_retry_queue_job_resets_failed_ingest_record(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    failed = load_queue_item(queue_path).model_copy(
        update={
            "status": "failed",
            "attempt_count": 3,
            "max_attempts": 3,
            "lease_owner": "local-cli:123",
            "lease_expires_at": "2026-04-10T12:00:00+00:00",
            "last_error": "broken",
        }
    )
    write_queue_item(queue_path, failed)

    result = retry_queue_job(tmp_path, f"ingest-{added.source_id}")

    assert result.item.status == "pending"
    assert result.item.attempt_count == 3
    assert result.item.max_attempts == 4
    assert result.item.lease_owner is None
    assert result.item.lease_expires_at is None
    assert result.item.last_error is None
    assert load_queue_item(queue_path).status == "pending"


@pytest.mark.parametrize("status", ["pending", "leased", "done"])
def test_retry_queue_job_rejects_non_failed_records(tmp_path: Path, status: str) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue = load_queue_item(queue_path).model_copy(
        update={
            "status": status,
            "lease_owner": "local-cli:123" if status == "leased" else None,
            "lease_expires_at": "2099-01-01T00:00:00+00:00" if status == "leased" else None,
        }
    )
    write_queue_item(queue_path, queue)

    with pytest.raises(RuntimeError):
        retry_queue_job(tmp_path, f"ingest-{added.source_id}")


def test_retry_queue_job_rejects_missing_and_unsupported_jobs(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    with pytest.raises(FileNotFoundError, match="Unknown queue job"):
        retry_queue_job(tmp_path, "ingest-missing")

    unsupported_path = tmp_path / "state" / "queue" / "refresh-page.json"
    write_queue_item(
        unsupported_path,
        QueueItemRecord(
            job_id="refresh-page",
            job_type="refresh_page",
            status="failed",
            created_at="2026-04-10T12:00:00+00:00",
            updated_at="2026-04-10T12:00:00+00:00",
            payload_ref="wiki/index.md",
            last_error="broken",
        ),
    )

    with pytest.raises(ValueError, match="Unsupported queue job type"):
        retry_queue_job(tmp_path, "refresh-page")


def test_cli_queue_inspect_human_and_json_output(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "queue", "inspect"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Queue inspect" in out
    assert f"ingest-{source_id} [pending]" in out
    assert "Next: splendor ingest --pending" in out

    exit_code = main(["--root", str(tmp_path), "queue", "inspect", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 1
    assert payload["status_counts"] == {"pending": 1}
    assert payload["items"][0]["job_id"] == f"ingest-{source_id}"


def test_cli_queue_inspect_single_job_outputs_detail_and_json(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    job_id = f"ingest-{source_id}"
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "queue", "inspect", job_id])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"Queue job: {job_id}" in out
    assert f"Source ID: {source_id}" in out

    exit_code = main(["--root", str(tmp_path), "queue", "inspect", job_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["job_id"] == job_id
    assert payload["record_path"] == f"state/queue/{job_id}.json"


def test_cli_queue_retry_resets_failed_job(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    job_id = f"ingest-{source_id}"
    queue_path = tmp_path / "state" / "queue" / f"{job_id}.json"
    failed = load_queue_item(queue_path).model_copy(
        update={"status": "failed", "last_error": "broken"}
    )
    write_queue_item(queue_path, failed)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "queue", "retry", job_id])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"Retried queue job {job_id}" in out
    assert "Next: splendor ingest --pending" in out
    assert load_queue_item(queue_path).status == "pending"


def test_cli_repair_ingest_requeues_and_runs_fixed_failed_source(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.txt"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.unlink()
    assert main(["--root", str(tmp_path), "ingest", source_id]) == 1
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "repair", "ingest", source_id])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"Repaired ingest for source {source_id}" in out
    assert f"Next: splendor wiki suggest {source_id}" in out
    queue_record = load_queue_item(tmp_path / "state" / "queue" / f"ingest-{source_id}.json")
    source_record = load_source_record(
        tmp_path / "state" / "manifests" / "sources" / f"{source_id}.json"
    )
    assert queue_record.status == "done"
    assert source_record.status == "ingested"


def test_cli_repair_ingest_json_reports_no_op(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", source_id])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "repair", "ingest", source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_id"] == source_id
    assert payload["outcome"] == "skipped"
    assert payload["no_op"] is True
    assert payload["run_id"] is None
    assert payload["page_path"].endswith(f"wiki/sources/{source_id}.md")
