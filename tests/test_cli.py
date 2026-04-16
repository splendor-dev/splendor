import shutil
from pathlib import Path

import pytest

from splendor.cli import build_parser, main
from splendor.commands.ingest import enqueue_ingest_job


def test_cli_init_command(tmp_path: Path, capsys) -> None:
    exit_code = main(["--root", str(tmp_path), "init"])

    assert exit_code == 0
    assert (tmp_path / "wiki" / "index.md").exists()
    captured = capsys.readouterr()
    assert "Initialized Splendor workspace" in captured.out


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
    assert "Checked sources: 1" in captured.out
    assert "Health check passed" in captured.out


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


def test_cli_health_command_reports_top_level_errors(tmp_path: Path, capsys) -> None:
    (tmp_path / "splendor.yaml").write_text("sources: [\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "health"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("Error: ")


def test_cli_health_command_fails_when_source_manifest_dir_is_missing(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source_records_dir = tmp_path / "state" / "manifests" / "sources"
    shutil.rmtree(source_records_dir)

    exit_code = main(["--root", str(tmp_path), "health"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Source manifest directory is missing or unreadable" in captured.out
