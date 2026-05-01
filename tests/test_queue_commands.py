import json
from datetime import UTC, datetime, timedelta
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
    assert result.item.next_attempt_at is None
    assert result.item.last_error is None
    assert load_queue_item(queue_path).status == "pending"


def test_retry_queue_job_resets_dead_letter_ingest_record(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    dead_letter = load_queue_item(queue_path).model_copy(
        update={
            "status": "dead_letter",
            "attempt_count": 3,
            "max_attempts": 3,
            "last_error": "broken",
        }
    )
    write_queue_item(queue_path, dead_letter)

    result = retry_queue_job(tmp_path, f"ingest-{added.source_id}")

    assert result.item.status == "pending"
    assert result.item.max_attempts == 4
    assert result.item.last_error is None


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
    assert f"ingest-{source_id} [pending/pending]" in out
    assert "Next: splendor ingest --pending" in out

    exit_code = main(["--root", str(tmp_path), "queue", "inspect", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 1
    assert payload["status_counts"] == {"pending": 1}
    assert payload["items"][0]["job_id"] == f"ingest-{source_id}"
    assert payload["items"][0]["operator_state"] == "pending"
    assert payload["items"][0]["next_attempt_at"] is None


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


def test_cli_queue_retry_json_reports_reset_job(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    job_id = f"ingest-{source_id}"
    queue_path = tmp_path / "state" / "queue" / f"{job_id}.json"
    failed = load_queue_item(queue_path).model_copy(
        update={"status": "failed", "attempt_count": 3, "max_attempts": 3, "last_error": "broken"}
    )
    write_queue_item(queue_path, failed)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "queue", "retry", job_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["item"]["job_id"] == job_id
    assert payload["item"]["status"] == "pending"
    assert payload["item"]["max_attempts"] == 4
    assert payload["item"]["last_error"] is None
    assert payload["item"]["next_attempt_at"] is None


def test_cli_queue_inspect_distinguishes_backoff_expired_lease_and_dead_letter(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    paths = []
    for name in ["backoff.md", "expired.md", "dead.md"]:
        source = tmp_path / name
        source.write_text(f"# {name}\n\nhello\n", encoding="utf-8")
        manifests_before = set((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
        main(["--root", str(tmp_path), "add-source", str(source)])
        manifests_after = set((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
        source_id = (manifests_after - manifests_before).pop().stem
        paths.append((source_id, tmp_path / "state" / "queue" / f"ingest-{source_id}.json"))
    backoff_id, backoff_path = paths[0]
    expired_id, expired_path = paths[1]
    dead_id, dead_path = paths[2]
    write_queue_item(
        backoff_path,
        load_queue_item(backoff_path).model_copy(
            update={
                "status": "failed",
                "last_error": "temporary",
                "next_attempt_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }
        ),
    )
    write_queue_item(
        expired_path,
        load_queue_item(expired_path).model_copy(
            update={
                "status": "leased",
                "lease_owner": "local-cli:123",
                "lease_expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            }
        ),
    )
    write_queue_item(
        dead_path,
        load_queue_item(dead_path).model_copy(
            update={"status": "dead_letter", "last_error": "broken"}
        ),
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "queue", "inspect", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    states = {item["source_id"]: item["operator_state"] for item in payload["items"]}
    assert states[backoff_id] == "failed_backoff"
    assert states[expired_id] == "expired_leased"
    assert states[dead_id] == "dead_letter"

    exit_code = main(["--root", str(tmp_path), "queue", "inspect"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dead_letter" in out
    assert "Next: splendor ingest --pending" in out


def test_cli_queue_inspect_prioritizes_runnable_next_action(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    pending_source = tmp_path / "pending.md"
    pending_source.write_text("# Pending\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(pending_source)])
    backoff_source = tmp_path / "backoff.md"
    backoff_source.write_text("# Backoff\n\nhello\n", encoding="utf-8")
    manifests_before = set((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    main(["--root", str(tmp_path), "add-source", str(backoff_source)])
    manifests_after = set((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    backoff_id = (manifests_after - manifests_before).pop().stem
    backoff_path = tmp_path / "state" / "queue" / f"ingest-{backoff_id}.json"
    write_queue_item(
        backoff_path,
        load_queue_item(backoff_path).model_copy(
            update={
                "status": "failed",
                "last_error": "temporary",
                "next_attempt_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }
        ),
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "queue", "inspect"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Next: splendor ingest --pending" in out


def test_cli_queue_inspect_reports_dead_letter_next_action(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "dead.md"
    source.write_text("# Dead\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    write_queue_item(
        queue_path,
        load_queue_item(queue_path).model_copy(
            update={"status": "dead_letter", "last_error": "broken"}
        ),
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "queue", "inspect"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Next: splendor queue retry <job-id> or splendor repair ingest <source-id>" in out


def test_cli_queue_inspect_reports_backoff_next_action(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "backoff.md"
    source.write_text("# Backoff\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    write_queue_item(
        queue_path,
        load_queue_item(queue_path).model_copy(
            update={
                "status": "failed",
                "last_error": "temporary",
                "next_attempt_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }
        ),
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "queue", "inspect"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Next: wait for retry backoff or run splendor queue retry <job-id>" in out


def test_cli_queue_inspect_single_job_dead_letter_and_backoff_next_actions(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    dead_source = tmp_path / "dead.md"
    dead_source.write_text("# Dead\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(dead_source)])
    dead_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    dead_job_id = f"ingest-{dead_id}"
    dead_queue_path = tmp_path / "state" / "queue" / f"{dead_job_id}.json"
    write_queue_item(
        dead_queue_path,
        load_queue_item(dead_queue_path).model_copy(
            update={"status": "dead_letter", "last_error": "broken"}
        ),
    )
    capsys.readouterr()

    assert main(["--root", str(tmp_path), "queue", "inspect", dead_job_id]) == 0
    out = capsys.readouterr().out
    assert f"Next: splendor queue retry {dead_job_id} or splendor repair ingest {dead_id}" in out

    write_queue_item(
        dead_queue_path,
        load_queue_item(dead_queue_path).model_copy(
            update={
                "status": "failed",
                "last_error": "temporary",
                "next_attempt_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }
        ),
    )

    assert main(["--root", str(tmp_path), "queue", "inspect", dead_job_id]) == 0
    out = capsys.readouterr().out
    assert f"Next: wait for retry backoff or run splendor queue retry {dead_job_id}" in out


def test_queue_inspect_handles_z_and_invalid_timestamps(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    z_source = tmp_path / "z.md"
    z_source.write_text("# Z\n\nhello\n", encoding="utf-8")
    z_added = add_source(tmp_path, z_source)
    z_queue_path = enqueue_ingest_job(tmp_path, z_added.source_id)
    invalid_source = tmp_path / "invalid.md"
    invalid_source.write_text("# Invalid\n\nhello\n", encoding="utf-8")
    invalid_added = add_source(tmp_path, invalid_source)
    invalid_queue_path = enqueue_ingest_job(tmp_path, invalid_added.source_id)
    write_queue_item(
        z_queue_path,
        load_queue_item(z_queue_path).model_copy(
            update={
                "status": "failed",
                "last_error": "temporary",
                "next_attempt_at": "2099-01-01T00:00:00Z",
            }
        ),
    )
    write_queue_item(
        invalid_queue_path,
        load_queue_item(invalid_queue_path).model_copy(
            update={
                "status": "failed",
                "last_error": "temporary",
                "next_attempt_at": "not-a-timestamp",
            }
        ),
    )

    result = inspect_queue(tmp_path)

    states = {item.source_id: item.operator_state for item in result.items}
    assert states[z_added.source_id] == "failed_backoff"
    assert states[invalid_added.source_id] == "failed_due"


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


def test_cli_repair_ingest_recovers_dead_letter_source(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.txt"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    write_queue_item(
        queue_path,
        load_queue_item(queue_path).model_copy(
            update={
                "status": "dead_letter",
                "attempt_count": 3,
                "max_attempts": 3,
                "last_error": "x",
            }
        ),
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "repair", "ingest", source_id])

    assert exit_code == 0
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "done"
    assert queue_record.attempt_count == 4
    assert queue_record.max_attempts == 4


def test_repair_ingest_done_requeue_keeps_attempt_budget_valid(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    exhausted_done = load_queue_item(queue_path).model_copy(
        update={"status": "done", "attempt_count": 3, "max_attempts": 3}
    )
    write_queue_item(queue_path, exhausted_done)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "repair", "ingest", source_id])

    assert exit_code == 0
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "done"
    assert queue_record.attempt_count == 4
    assert queue_record.max_attempts == 4


def test_cli_repair_ingest_json_reports_no_op(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", source_id])
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    queue_before = queue_path.read_text(encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "repair", "ingest", source_id, "--json"])

    assert exit_code == 0
    assert queue_path.read_text(encoding="utf-8") == queue_before
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_id"] == source_id
    assert payload["outcome"] == "skipped"
    assert payload["no_op"] is True
    assert payload["queue_path"] is None
    assert payload["run_id"] is None
    assert payload["page_path"] == f"wiki/sources/{source_id}.md"


def test_cli_repair_ingest_no_op_does_not_print_empty_queue_path(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", source_id])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "repair", "ingest", source_id])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Queue record: None" not in out
    assert f"Page: {tmp_path / 'wiki' / 'sources' / f'{source_id}.md'}" in out
