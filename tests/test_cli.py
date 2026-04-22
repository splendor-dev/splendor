import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import splendor.cli as cli_module
from splendor import __version__
from splendor.cli import build_parser, main
from splendor.commands.ingest import enqueue_ingest_job
from splendor.schemas import KnowledgePageFrontmatter, MaintenanceIssue, MaintenanceReport
from splendor.state.query_snapshot import load_query_snapshot
from splendor.state.runtime import load_queue_item


def latest_report_paths(root: Path, command: str) -> tuple[Path, Path]:
    report_dir = root / "reports" / command
    json_reports = sorted(report_dir.glob("*.json"))
    markdown_reports = sorted(report_dir.glob("*.md"))
    assert json_reports, f"expected JSON reports in {report_dir}"
    assert markdown_reports, f"expected Markdown reports in {report_dir}"
    return json_reports[-1], markdown_reports[-1]


def test_cli_init_command(tmp_path: Path, capsys) -> None:
    exit_code = main(["--root", str(tmp_path), "init"])

    assert exit_code == 0
    assert (tmp_path / "wiki" / "index.md").exists()
    captured = capsys.readouterr()
    assert "Initialized Splendor workspace" in captured.out


def test_cli_version_flag_prints_package_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"splendor {__version__}\n"


def test_cli_add_source_capture_source_commit_flags_are_tri_state() -> None:
    parser = build_parser()

    no_flag = parser.parse_args(["add-source", "brief.md"])
    yes_flag = parser.parse_args(["add-source", "--capture-source-commit", "brief.md"])
    no_capture_flag = parser.parse_args(["add-source", "--no-capture-source-commit", "brief.md"])

    assert no_flag.capture_source_commit is None
    assert yes_flag.capture_source_commit is True
    assert no_capture_flag.capture_source_commit is False


def test_cli_add_source_command_reports_workspace_backed_registration(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "add-source", str(source)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Registered source" in captured.out
    assert "Source ref: brief.md" in captured.out
    assert "Storage mode: none" in captured.out
    assert "Storage artifact:" not in captured.out


def test_cli_add_source_resolves_relative_paths_against_root(tmp_path: Path, capsys) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    docs_dir = repo_root / "docs"
    docs_dir.mkdir()
    source = docs_dir / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    main(["--root", str(repo_root), "init"])
    exit_code = main(["--root", str(repo_root), "add-source", "docs/brief.md"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Source ref: docs/brief.md" in captured.out
    assert "Storage mode: none" in captured.out


def test_cli_add_source_expands_user_paths(tmp_path: Path, capsys, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    source = fake_home / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))

    main(["--root", str(repo_root), "init"])
    exit_code = main(["--root", str(repo_root), "add-source", "~/brief.md"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Registered source" in captured.out
    assert "Storage mode: copy" in captured.out
    assert "Storage artifact:" in captured.out


def test_cli_add_source_supports_explicit_copy_for_workspace_files(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "add-source", "--storage-mode", "copy", str(source)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Source ref: brief.md" in captured.out
    assert "Storage mode: copy" in captured.out
    assert "Storage artifact:" in captured.out


def test_cli_add_source_supports_pointer_for_workspace_files(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    exit_code = main(
        ["--root", str(tmp_path), "add-source", "--storage-mode", "pointer", str(source)]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Source ref: brief.md" in captured.out
    assert "Storage mode: pointer" in captured.out
    assert "Storage artifact:" in captured.out


def test_cli_add_source_supports_symlink_for_workspace_files(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    exit_code = main(
        ["--root", str(tmp_path), "add-source", "--storage-mode", "symlink", str(source)]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Source ref: brief.md" in captured.out
    assert "Storage mode: symlink" in captured.out
    assert "Storage artifact:" in captured.out


def test_cli_add_source_reports_unsupported_mode_combinations(tmp_path: Path, capsys) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    source = fake_home / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    main(["--root", str(repo_root), "init"])
    exit_code = main(
        ["--root", str(repo_root), "add-source", "--storage-mode", "none", str(source)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not supported for external sources" in captured.out


def test_cli_add_source_reports_pointer_as_unsupported_for_external_files(
    tmp_path: Path, capsys
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    source = fake_home / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    main(["--root", str(repo_root), "init"])
    exit_code = main(
        ["--root", str(repo_root), "add-source", "--storage-mode", "pointer", str(source)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not implemented yet for external sources" in captured.out


def test_cli_add_source_reports_symlink_as_unsupported_for_external_files(
    tmp_path: Path, capsys
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    source = fake_home / "brief.md"
    source.write_text("hello\n", encoding="utf-8")

    main(["--root", str(repo_root), "init"])
    exit_code = main(
        ["--root", str(repo_root), "add-source", "--storage-mode", "symlink", str(source)]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "not implemented yet for external sources" in captured.out


def test_cli_ingest_command(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])

    manifest_paths = list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_paths[0].stem
    exit_code = main(["--root", str(tmp_path), "ingest", source_id])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Ingested source" in captured.out
    assert "Source ref: brief.md" in captured.out
    assert "Canonical content: workspace path" in captured.out


def test_cli_ingest_command_reports_stored_artifact_for_copied_workspace_source(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "--storage-mode", "copy", str(source)])

    manifest_paths = list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_paths[0].stem
    exit_code = main(["--root", str(tmp_path), "ingest", source_id])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Source ref: brief.md" in captured.out
    assert "Canonical content: stored artifact" in captured.out


def test_cli_ingest_command_no_op(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])

    manifest_paths = list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_paths[0].stem
    main(["--root", str(tmp_path), "ingest", source_id])
    exit_code = main(["--root", str(tmp_path), "ingest", source_id])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "already ingested" in captured.out


def test_cli_ingest_command_reports_missing_source(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])

    exit_code = main(["--root", str(tmp_path), "ingest", "src-missing"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Unknown source ID" in captured.out


def test_cli_ingest_requires_exactly_one_target_mode() -> None:
    with pytest.raises(SystemExit):
        main(["ingest"])

    with pytest.raises(SystemExit):
        main(["ingest", "src-123", "--pending"])


def test_cli_ingest_pending_reports_no_jobs(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No pending ingest jobs" in captured.out


def test_cli_ingest_pending_reports_skipped_items(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])

    manifest_paths = list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_paths[0].stem
    queue_path = enqueue_ingest_job(tmp_path, source_id)
    queue_record = load_queue_item(queue_path).model_copy(
        update={
            "status": "leased",
            "lease_owner": "local-cli:123",
            "lease_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )
    queue_path.write_text(queue_record.model_dump_json(indent=2) + "\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"{source_id}: skipped (lease active until 2099-01-01T00:00:00+00:00)" in captured.out
    assert "Drain summary: processed=0 succeeded=0 failed=0 skipped=1" in captured.out
    assert "No pending ingest jobs" not in captured.out


def test_cli_ingest_pending_prints_summary(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])

    manifest_paths = list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_paths[0].stem
    enqueue_ingest_job(tmp_path, source_id)

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"{source_id}: succeeded" in captured.out
    assert "Drain summary: processed=1 succeeded=1 failed=0 skipped=0" in captured.out


def test_cli_ingest_pending_continues_after_failure(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])

    ok_source = tmp_path / "brief.md"
    ok_source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(ok_source)])
    ok_manifest = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    ok_source_id = ok_manifest.stem
    enqueue_ingest_job(tmp_path, ok_source_id)

    bad_source = tmp_path / "broken.bin"
    bad_source.write_bytes(b"\x00\x01\x02")
    main(["--root", str(tmp_path), "add-source", str(bad_source)])
    manifest_paths = sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    bad_source_id = next(path.stem for path in manifest_paths if path.stem != ok_source_id)
    enqueue_ingest_job(tmp_path, bad_source_id)

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert f"{ok_source_id}: succeeded" in captured.out
    assert f"{bad_source_id}: failed" in captured.out
    assert "Drain summary: processed=2 succeeded=1 failed=1 skipped=0" in captured.out


def test_cli_ingest_pending_reports_failed_and_skipped_mix(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])

    skipped_source = tmp_path / "skipped.md"
    skipped_source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(skipped_source)])
    skipped_source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", skipped_source_id])
    capsys.readouterr()
    enqueue_ingest_job(tmp_path, skipped_source_id)

    missing_source = tmp_path / "missing.md"
    missing_source.write_text("missing file content\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(missing_source)])
    manifest_paths = sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    failing_source_id = next(path.stem for path in manifest_paths if path.stem != skipped_source_id)
    missing_source.unlink()
    enqueue_ingest_job(tmp_path, failing_source_id)

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        f"{skipped_source_id}: skipped (already ingested for the current pipeline version)"
        in captured.out
    )
    assert f"{failing_source_id}: failed (Workspace source is missing: missing.md)" in captured.out
    assert "Drain summary: processed=1 succeeded=0 failed=1 skipped=1" in captured.out


def test_cli_materialize_source_command(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    manifest_paths = list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_paths[0].stem

    exit_code = main(["--root", str(tmp_path), "materialize-source", source_id])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Materialized source" in captured.out
    assert "Source ref: brief.md" in captured.out
    assert "Storage mode: pointer" in captured.out
    assert "Storage artifact:" in captured.out


def test_cli_health_command_passes_for_valid_sources(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "--storage-mode", "pointer", str(source)])

    exit_code = main(["--root", str(tmp_path), "health"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Checked records: 1" in captured.out
    assert "Health check passed" in captured.out
    json_report, markdown_report = latest_report_paths(tmp_path, "health")
    assert json_report.stem == markdown_report.stem
    assert re.fullmatch(r"\d{8}T\d{6}Z(?:-\d+)?", json_report.stem)
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["command"] == "health"
    assert payload["status"] == "passed"
    assert payload["checked_count"] == 1
    assert payload["issue_count"] == 0
    markdown = markdown_report.read_text(encoding="utf-8")
    assert "# Splendor Health Report" in markdown
    assert "- Status: `passed`" in markdown
    assert "- Issues: `0`" in markdown


def test_cli_health_command_fails_for_invalid_sources(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "--storage-mode", "pointer", str(source)])
    pointer = next((tmp_path / "raw" / "sources").glob("*/pointer.json"))
    pointer.write_text("{not-json}\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "health"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Health check failed: 1 issue(s)" in captured.out
    json_report, markdown_report = latest_report_paths(tmp_path, "health")
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["issue_count"] == 1
    assert payload["issues"][0]["record_id"]
    assert payload["issues"][0]["code"] == "source-health-check-failed"
    assert payload["issues"][0]["path"].startswith("state/manifests/sources/")
    markdown = markdown_report.read_text(encoding="utf-8")
    assert "## Issues" in markdown
    assert "[source-health-check-failed]" in markdown


def test_cli_health_command_reports_top_level_errors(tmp_path: Path, capsys) -> None:
    (tmp_path / "splendor.yaml").write_text("sources: [\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "health"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("Error: ")
    json_report, markdown_report = latest_report_paths(tmp_path, "health")
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["fatal_error"]
    assert "# Splendor Health Report" in markdown_report.read_text(encoding="utf-8")


def test_cli_health_command_fails_when_source_manifest_dir_is_missing(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source_records_dir = tmp_path / "state" / "manifests" / "sources"
    shutil.rmtree(source_records_dir)

    exit_code = main(["--root", str(tmp_path), "health"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Health check failed: 1 issue(s)" in captured.out
    assert "Source manifest directory is missing or unreadable" in captured.out
    payload = json.loads(latest_report_paths(tmp_path, "health")[0].read_text(encoding="utf-8"))
    assert payload["issues"][0]["code"] == "missing-directory"
    assert payload["issues"][0]["path"] == "state/manifests/sources"


def test_cli_health_command_supports_json_output(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "health", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "health"
    assert payload["status"] == "passed"
    assert payload["issue_count"] == 0


def test_cli_health_command_uses_issue_code_when_no_subject_fields_exist(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = MaintenanceReport(
        command="health",
        created_at="2026-04-21T10:00:00+00:00",
        status="failed",
        checked_count=0,
        issue_count=1,
        issues=[MaintenanceIssue(code="fallback-code", message="fallback message")],
    )

    fake_result = SimpleNamespace(exit_code=1, report=report)

    monkeypatch.setattr(
        cli_module,
        "execute_maintenance_command",
        lambda *args, **kwargs: fake_result,
    )

    exit_code = main(["--root", str(tmp_path), "health"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "- fallback-code: fallback message" in captured.out


def test_cli_query_command_collapses_multiline_errors(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli_module,
        "run_query",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("first line\nsecond line")),
    )

    exit_code = main(["--root", str(tmp_path), "query", "test"])

    assert exit_code == 1
    assert capsys.readouterr().out == "Error: first line second line\n"


def test_cli_lint_command_passes_for_initialized_workspace(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])

    exit_code = main(["--root", str(tmp_path), "lint"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Checked items:" in captured.out
    assert "Lint check passed" in captured.out
    json_report, markdown_report = latest_report_paths(tmp_path, "lint")
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["command"] == "lint"
    assert payload["status"] == "passed"
    assert payload["issue_count"] == 0
    assert "# Splendor Lint Report" in markdown_report.read_text(encoding="utf-8")


def test_cli_lint_command_fails_when_required_directory_is_missing(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    shutil.rmtree(tmp_path / "planning" / "tasks")

    exit_code = main(["--root", str(tmp_path), "lint"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Lint check failed: 1 issue(s)" in captured.out
    assert "Required workspace directory is missing" in captured.out
    payload = json.loads(latest_report_paths(tmp_path, "lint")[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["issues"][0]["code"] == "missing-directory"
    assert payload["issues"][0]["path"] == "planning/tasks"


def test_cli_lint_command_fails_when_required_bootstrap_file_is_missing(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    (tmp_path / "wiki" / "index.md").unlink()

    exit_code = main(["--root", str(tmp_path), "lint"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Required bootstrap file is missing" in captured.out
    payload = json.loads(latest_report_paths(tmp_path, "lint")[0].read_text(encoding="utf-8"))
    assert payload["issues"][0]["code"] == "missing-file"
    assert payload["issues"][0]["path"] == "wiki/index.md"


def test_cli_lint_command_supports_json_output(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "lint", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "lint"
    assert payload["status"] == "passed"
    assert payload["issue_count"] == 0


def test_cli_lint_command_reports_dirty_workspace_issues_in_json_output(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()
    bad_page = tmp_path / "wiki" / "concepts" / "bad.md"
    bad_page.write_text("---\nkind: concept\nbogus: true\n---\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "lint", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "lint"
    assert payload["status"] == "failed"
    assert payload["issue_count"] == 1
    assert payload["issues"][0]["code"] == "invalid-wiki-frontmatter"
    json_report, markdown_report = latest_report_paths(tmp_path, "lint")
    assert json.loads(json_report.read_text(encoding="utf-8"))["status"] == "failed"
    assert "invalid-wiki-frontmatter" in markdown_report.read_text(encoding="utf-8")


def write_queryable_wiki_page(path: Path, *, title: str, page_id: str, body: str) -> None:
    frontmatter = KnowledgePageFrontmatter(
        kind="concept",
        title=title,
        page_id=page_id,
        status="active",
        confidence=0.8,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    path.write_text(
        f"---\n{frontmatter_text}\n---\n\n{body}",
        encoding="utf-8",
    )


def test_cli_query_command_prints_text_results(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    write_queryable_wiki_page(
        tmp_path / "wiki" / "concepts" / "query.md",
        title="Deterministic query",
        page_id="concept-deterministic-query",
        body="# Deterministic query\n\nThis page covers local retrieval.\n",
    )
    main(["--root", str(tmp_path), "task", "create", "Ship", "query"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "deterministic", "query"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Query: deterministic query" in captured.out
    assert "Summary: Found 2 matching records." in captured.out
    assert "Matches:" in captured.out
    assert "planning/tasks/task-ship-query.md" in captured.out
    assert "wiki/concepts/query.md" in captured.out


def test_cli_query_command_supports_json_output(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Ship", "query", "--source-ref", "src-123"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "query", "--json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["query"] == "query"
    assert payload["match_count"] == 1
    assert payload["matches"][0]["path"] == "planning/tasks/task-ship-query.md"
    assert payload["matches"][0]["generated_by_run_ids"] == []
    assert payload["matches"][0]["review_state"] is None
    assert payload["matches"][0]["last_generated_at"] is None
    assert payload["matches"][0]["provenance_links"] == []
    assert payload["matches"][0]["tags"] == []


def test_cli_query_command_persists_last_query_snapshot(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Ship", "query"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "query"])

    assert exit_code == 0
    snapshot = load_query_snapshot(tmp_path / "state" / "queries" / "last-query.json")
    assert snapshot.query == "query"
    assert snapshot.match_count == 1


def test_cli_query_command_persists_snapshot_for_json_output(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Ship", "query"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "query", "--json"])

    assert exit_code == 0
    snapshot = load_query_snapshot(tmp_path / "state" / "queries" / "last-query.json")
    assert snapshot.query == "query"


def test_cli_query_command_reports_snapshot_write_failure(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Ship", "query"])
    capsys.readouterr()

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(cli_module, "write_query_snapshot", fail_write)

    exit_code = main(["--root", str(tmp_path), "query", "query"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error: disk full" in captured.out


def test_cli_query_command_reports_no_matches(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "nothing"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert 'Summary: No matches found for "nothing".' in captured.out


def test_cli_query_command_rejects_degenerate_queries(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "!!!"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Query must contain at least one ASCII letter or number" in captured.out
    assert not (tmp_path / "state" / "queries" / "last-query.json").exists()


def test_cli_query_command_prints_review_state_and_provenance(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    page = tmp_path / "wiki" / "sources" / "src-123.md"
    frontmatter = KnowledgePageFrontmatter(
        kind="source-summary",
        title="Generated source summary",
        page_id="src-123",
        status="active",
        review_state="machine-generated",
        source_refs=["src-123"],
        generated_by_run_ids=["run-123"],
        last_generated_at="2026-04-22T10:00:00+00:00",
        confidence=1.0,
        provenance_links=[
            {
                "source_id": "src-123",
                "run_id": "run-123",
                "path_ref": "wiki/sources/src-123.md",
                "role": "generated-from",
            }
        ],
    )
    page.parent.mkdir(parents=True, exist_ok=True)
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    page.write_text(f"---\n{frontmatter_text}\n---\n\nGenerated body\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "generated"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Review state: machine-generated" in out
    assert "Last generated: 2026-04-22T10:00:00+00:00" in out
    assert "Provenance:" in out


def test_cli_file_answer_reports_invalid_saved_query_snapshot(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    snapshot_path = tmp_path / "state" / "queries" / "last-query.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text("{not valid json", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Broken snapshot answer",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Saved query snapshot is invalid" in captured.out


def test_cli_query_command_fails_for_invalid_wiki_frontmatter(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()
    bad_page = tmp_path / "wiki" / "concepts" / "bad.md"
    bad_page.write_text("---\nkind: concept\nbogus: true\n---\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "query", "concept"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("Error: Wiki page")


def test_cli_task_create_command(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Write",
            "CLI",
            "docs",
            "--priority",
            "high",
            "--owner",
            "codex",
            "--milestone-ref",
            "milestone-m3-p1",
            "--source-ref",
            "src-123",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Created task task-write-cli-docs" in captured.out
    assert "planning/tasks/task-write-cli-docs.md" in captured.out


def test_cli_file_answer_from_last_query_creates_topic_page_and_updates_index_and_log(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    write_queryable_wiki_page(
        tmp_path / "wiki" / "topics" / "ranking.md",
        title="Ranking note",
        page_id="topic-ranking-note",
        body="Ranking evidence appears here.\n",
    )
    main(["--root", str(tmp_path), "query", "ranking"])
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Ranking answer",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Filed answer answer-ranking-answer" in captured.out
    page_path = tmp_path / "wiki" / "topics" / "answer-ranking-answer.md"
    page = page_path.read_text(encoding="utf-8")
    assert "## Query" in page
    assert "## Ranked Matches" in page
    assert "Ranking note" in page
    assert "filed-answer" in page
    assert "## Filed Answers" in (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert "answer-ranking-answer" in (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")


def test_cli_file_answer_updates_explicit_question(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "question", "create", "What", "is", "ranking"])
    main(["--root", str(tmp_path), "query", "ranking"])
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Ranking answer",
            "--question-id",
            "question-what-is-ranking",
        ]
    )

    assert exit_code == 0
    question_path = tmp_path / "planning" / "questions" / "question-what-is-ranking.md"
    question = question_path.read_text(encoding="utf-8")
    assert "status: answered" in question
    assert "answer_page_ref: wiki/topics/answer-ranking-answer.md" in question
    assert "## Answer" in question
    assert "[Ranking answer](../../wiki/topics/answer-ranking-answer.md)" in question


def test_cli_file_answer_reports_write_failure(tmp_path: Path, capsys, monkeypatch) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "query", "nothing"])
    capsys.readouterr()

    def fail_file_answer(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(cli_module, "file_answer_from_last_query", fail_file_answer)

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Ranking answer",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error: read-only file system" in captured.out


def test_cli_file_answer_errors_without_saved_query(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Ranking answer",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No saved query snapshot found" in captured.out


def test_cli_file_answer_errors_for_unknown_question_without_writing_page(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "query", "nothing"])
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Ranking answer",
            "--question-id",
            "question-missing",
        ]
    )

    assert exit_code == 1
    assert not (tmp_path / "wiki" / "topics" / "answer-ranking-answer.md").exists()


def test_cli_file_answer_uses_create_only_semantics(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "query", "nothing"])
    main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Ranking answer",
        ]
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Ranking answer",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Filed answer page already exists" in captured.out


def test_cli_file_answer_accepts_custom_page_id(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "query", "nothing"])
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "file-answer",
            "--from-last-query",
            "--title",
            "Ranking answer",
            "--page-id",
            "answer-custom",
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "wiki" / "topics" / "answer-custom.md").exists()


def test_cli_task_list_command_supports_filters(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Write",
            "CLI",
            "docs",
            "--priority",
            "high",
            "--milestone-ref",
            "milestone-m3-p1",
        ]
    )
    main(["--root", str(tmp_path), "task", "create", "Ship", "query", "--priority", "low"])

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "task",
            "list",
            "--priority",
            "high",
            "--milestone-ref",
            "milestone-m3-p1",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.startswith("task-")]
    assert lines == ["task-write-cli-docs  todo  high  Write CLI docs"]


def test_cli_milestone_create_and_list_commands(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(
        [
            "--root",
            str(tmp_path),
            "milestone",
            "create",
            "Milestone",
            "3",
            "Slice",
            "--status",
            "active",
            "--target-date",
            "2026-05-01",
        ]
    )

    exit_code = main(["--root", str(tmp_path), "milestone", "list", "--status", "active"])

    assert exit_code == 0
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.startswith("milestone-")]
    assert lines == ["milestone-milestone-3-slice  active  2026-05-01  Milestone 3 Slice"]


def test_cli_decision_create_command(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "decision",
            "create",
            "Use",
            "planning",
            "markdown",
            "--related-task",
            "task-write-cli-docs",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Created decision decision-use-planning-markdown" in captured.out


def test_cli_question_create_command(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "question",
            "create",
            "How",
            "should",
            "query",
            "ranking",
            "work",
            "--related-decision",
            "decision-use-planning-markdown",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Created question question-how-should-query-ranking-work" in captured.out


def test_cli_task_create_command_rejects_duplicate_ids(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Write", "CLI", "docs"])

    exit_code = main(["--root", str(tmp_path), "task", "create", "Write", "CLI", "docs"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Task ID already exists: task-write-cli-docs" in captured.out


def test_cli_task_list_fails_for_invalid_frontmatter(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()
    task_path = tmp_path / "planning" / "tasks" / "task-invalid.md"
    task_path.write_text("---\nkind: task\nbogus: true\n---\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "task", "list"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("Error: Planning record")
