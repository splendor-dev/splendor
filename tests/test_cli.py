import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import splendor.cli as cli_module
import splendor.commands.workspace as workspace_module
from splendor import __version__
from splendor.cli import build_parser, main
from splendor.commands.ingest import enqueue_ingest_job
from splendor.commands.lint import run_lint_checks
from splendor.commands.source import ingest_changed_sources, refresh_source
from splendor.config import load_config, write_config
from splendor.layout import resolve_layout
from splendor.schemas import (
    KnowledgePageFrontmatter,
    MaintenanceIssue,
    MaintenanceReport,
    ProvenanceLink,
    QueueItemRecord,
    RunRecord,
)
from splendor.state.query_snapshot import last_query_path_for, load_query_snapshot
from splendor.state.runtime import load_queue_item, write_queue_item, write_run_record
from splendor.state.source_registry import load_source_record, write_source_record


def latest_report_paths(root: Path, command: str) -> tuple[Path, Path]:
    report_dir = root / "reports" / command
    json_reports = sorted(report_dir.glob("*.json"))
    markdown_reports = sorted(report_dir.glob("*.md"))
    assert json_reports, f"expected JSON reports in {report_dir}"
    assert markdown_reports, f"expected Markdown reports in {report_dir}"
    return json_reports[-1], markdown_reports[-1]


def lint_issue_codes(root: Path) -> list[str]:
    layout = resolve_layout(root, load_config(root))
    return [issue.code for issue in run_lint_checks(root, layout).issues]


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
    glob_flag = parser.parse_args(["add-source", "--glob", "docs/*.md"])
    dir_flag = parser.parse_args(["add-source", "--dir", "docs"])
    yes_flag = parser.parse_args(["add-source", "--capture-source-commit", "brief.md"])
    no_capture_flag = parser.parse_args(["add-source", "--no-capture-source-commit", "brief.md"])

    assert no_flag.capture_source_commit is None
    assert glob_flag.glob_patterns == ["docs/*.md"]
    assert dir_flag.directories == [Path("docs")]
    assert yes_flag.capture_source_commit is True
    assert no_capture_flag.capture_source_commit is False


def test_cli_add_topic_parser_accepts_template_tags_source_refs_and_json() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "add-topic",
            "Preprocessing Pipeline",
            "--tags",
            "preprocessing,audio",
            "--tags",
            "filter",
            "--source-refs",
            "src-a,src-b",
            "--template",
            "research-synthesis",
            "--json",
        ]
    )

    assert args.command == "add-topic"
    assert args.title == "Preprocessing Pipeline"
    assert args.tags == ["preprocessing,audio", "filter"]
    assert args.source_refs == ["src-a,src-b"]
    assert args.template == "research-synthesis"
    assert args.json_output is True


def test_cli_source_parser_accepts_lookup_and_refresh_json_flags() -> None:
    parser = build_parser()

    lookup = parser.parse_args(["source", "lookup", "brief", "--json"])
    refresh = parser.parse_args(["source", "refresh", "docs/brief.md", "--json"])
    update_path = parser.parse_args(
        ["source", "update-path", "docs/old.md", "docs/new.md", "--force", "--json"]
    )
    reconcile = parser.parse_args(
        ["source", "reconcile", "docs/brief.md", "--current", "src-a", "--apply", "--json"]
    )
    freshness = parser.parse_args(
        ["source", "freshness", "--report", "reports/freshness.json", "--json"]
    )
    forget = parser.parse_args(
        ["source", "forget", "--matching", ".mypy_cache/**", "--apply", "--json"]
    )

    assert lookup.command == "source"
    assert lookup.source_command == "lookup"
    assert lookup.query == "brief"
    assert lookup.json_output is True
    assert refresh.source_command == "refresh"
    assert refresh.query == "docs/brief.md"
    assert refresh.json_output is True
    assert update_path.source_command == "update-path"
    assert update_path.query == "docs/old.md"
    assert update_path.new_path == Path("docs/new.md")
    assert update_path.force is True
    assert update_path.json_output is True
    assert reconcile.source_command == "reconcile"
    assert reconcile.selector == "docs/brief.md"
    assert reconcile.current == "src-a"
    assert reconcile.apply is True
    assert reconcile.json_output is True
    assert freshness.source_command == "freshness"
    assert freshness.report == Path("reports/freshness.json")
    assert freshness.json_output is True
    assert forget.source_command == "forget"
    assert forget.matching == ".mypy_cache/**"
    assert forget.apply is True
    assert forget.json_output is True


def test_cli_source_reconcile_repairs_duplicate_active_versions(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])
    source_path.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])
    manifest_paths = sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    before_text = {path.name: path.read_text(encoding="utf-8") for path in manifest_paths}
    records = [load_source_record(path) for path in manifest_paths]
    expected_current = max(records, key=lambda record: (record.added_at, record.source_id))
    superseded_ids = sorted(
        record.source_id for record in records if record.source_id != expected_current.source_id
    )
    assert "multiple-active-source-versions" in lint_issue_codes(tmp_path)
    capsys.readouterr()

    preview_code = main(["--root", str(tmp_path), "source", "reconcile", "brief.md", "--json"])

    assert preview_code == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["applied"] is False
    assert preview["canonical_ref"] == "brief.md"
    assert preview["current_source_id"] == expected_current.source_id
    assert preview["summary"] == {"active_before": 2, "updates": 2}
    assert preview["next_commands"] == ["splendor source reconcile brief.md --apply"]
    assert {path.name: path.read_text(encoding="utf-8") for path in manifest_paths} == before_text

    ambiguous_current_code = main(
        ["--root", str(tmp_path), "source", "reconcile", "brief.md", "--current", "brief.md"]
    )

    assert ambiguous_current_code == 1
    assert "Current source selector is ambiguous" in capsys.readouterr().out
    assert {path.name: path.read_text(encoding="utf-8") for path in manifest_paths} == before_text

    apply_code = main(["--root", str(tmp_path), "source", "reconcile", "brief.md", "--apply"])

    assert apply_code == 0
    out = capsys.readouterr().out
    assert "Applied source reconciliation" in out
    assert f"Current source ID: {expected_current.source_id}" in out
    assert "Next: splendor lint" in out
    after_records = {
        path.stem: load_source_record(path)
        for path in sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    }
    assert after_records[expected_current.source_id].supersedes == superseded_ids
    assert after_records[expected_current.source_id].superseded_by is None
    for source_id in superseded_ids:
        assert after_records[source_id].superseded_by == expected_current.source_id
    assert lint_issue_codes(tmp_path) == []


def test_cli_source_reconcile_explicit_source_id_selects_current(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source_path.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "source", "reconcile", original_id, "--apply", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["current_source_id"] == original_id
    records = {
        path.stem: load_source_record(path)
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
    }
    assert records[original_id].superseded_by is None
    assert records[original_id].supersedes
    assert all(
        record.superseded_by == original_id
        for source_id, record in records.items()
        if source_id != original_id
    )
    superseded_id = next(source_id for source_id in records if source_id != original_id)

    rejected_code = main(["--root", str(tmp_path), "source", "reconcile", superseded_id])

    assert rejected_code == 1
    assert "Current source version is already superseded" in capsys.readouterr().out


def test_cli_source_reconcile_repairs_partial_same_canonical_graph(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source_path.write_text("# Brief\n\nRepo scan duplicate.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])
    source_path.write_text("# Brief\n\nRefreshed repo scan duplicate.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])

    records = {
        path.stem: load_source_record(path)
        for path in sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    }
    current_id = max(
        records.values(), key=lambda record: (record.added_at, record.source_id)
    ).source_id
    middle_id = next(
        source_id for source_id in records if source_id not in {original_id, current_id}
    )
    middle_path = tmp_path / "state" / "manifests" / "sources" / f"{middle_id}.json"
    current_path = tmp_path / "state" / "manifests" / "sources" / f"{current_id}.json"
    write_source_record(
        middle_path,
        records[middle_id].model_copy(update={"superseded_by": current_id}),
    )
    write_source_record(
        current_path,
        records[current_id].model_copy(update={"supersedes": [middle_id]}),
    )
    assert "multiple-active-source-versions" in lint_issue_codes(tmp_path)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "reconcile", "brief.md", "--apply"])

    assert exit_code == 0
    after_records = {
        path.stem: load_source_record(path)
        for path in sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    }
    assert after_records[original_id].superseded_by == current_id
    assert after_records[middle_id].superseded_by == current_id
    assert after_records[current_id].superseded_by is None
    assert set(after_records[current_id].supersedes) == {original_id, middle_id}
    assert lint_issue_codes(tmp_path) == []


def test_cli_source_reconcile_rejects_ambiguous_or_cross_canonical_current(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = tmp_path / "a" / "brief.md"
    second = tmp_path / "b" / "brief.md"
    first.write_text("# First\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "a/brief.md"])
    main(["--root", str(tmp_path), "add-source", "b/brief.md"])
    ids_by_ref = {
        load_source_record(path).source_ref: path.stem
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
    }
    capsys.readouterr()

    ambiguous_code = main(["--root", str(tmp_path), "source", "reconcile", "brief"])

    assert ambiguous_code == 1
    assert "ambiguous" in capsys.readouterr().out

    cross_code = main(
        [
            "--root",
            str(tmp_path),
            "source",
            "reconcile",
            ids_by_ref["a/brief.md"],
            "--current",
            ids_by_ref["b/brief.md"],
        ]
    )

    assert cross_code == 1
    assert "must share the selected canonical source ref" in capsys.readouterr().out


def test_cli_source_reconcile_noops_for_single_active_source(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "reconcile", "brief.md", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"active_before": 1, "updates": 0}
    assert payload["next_commands"] == ["splendor lint", "splendor health"]


def test_cli_source_forget_preview_is_non_mutating(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nKeep preview safe.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    manifest_path = tmp_path / "state" / "manifests" / "sources" / f"{source_id}.json"
    summary_path = tmp_path / "wiki" / "sources" / f"{source_id}.md"
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    source_record = load_source_record(manifest_path)
    run_path = tmp_path / "state" / "runs" / f"{source_record.last_run_id}.json"
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is False
    assert payload["summary"]["candidates"] == 1
    assert {action["status"] for action in payload["actions"]} == {"planned"}
    assert manifest_path.exists()
    assert summary_path.exists()
    assert queue_path.exists()
    assert run_path.exists()


def test_cli_source_forget_apply_removes_source_owned_state(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nRemove generated state.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    manifest_path = tmp_path / "state" / "manifests" / "sources" / f"{source_id}.json"
    summary_path = tmp_path / "wiki" / "sources" / f"{source_id}.md"
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    derived_path = tmp_path / "derived" / "parsed" / f"{source_id}.txt"
    derived_path.parent.mkdir(parents=True, exist_ok=True)
    derived_path.write_text("derived text\n", encoding="utf-8")
    source_record = load_source_record(manifest_path)
    run_path = tmp_path / "state" / "runs" / f"{source_record.last_run_id}.json"
    write_source_record(
        manifest_path,
        source_record.model_copy(
            update={"derived_artifacts": [derived_path.relative_to(tmp_path).as_posix()]}
        ),
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", source_id, "--apply", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is True
    assert {action["status"] for action in payload["actions"]} == {"removed"}
    assert not manifest_path.exists()
    assert not summary_path.exists()
    assert not queue_path.exists()
    assert not run_path.exists()
    assert not derived_path.exists()
    assert f"`{source_id}`" not in (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")


def test_cli_source_forget_matching_removes_only_globbed_sources(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    polluted = tmp_path / ".mypy_cache" / "cache.py"
    keep = tmp_path / "docs" / "keep.md"
    polluted.parent.mkdir()
    keep.parent.mkdir()
    polluted.write_text("cache\n", encoding="utf-8")
    keep.write_text("keep\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(polluted)])
    main(["--root", str(tmp_path), "add-source", str(keep)])
    sources = {
        load_source_record(path).source_ref: path
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
    }
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "source",
            "forget",
            "--matching",
            ".mypy_cache/**",
            "--apply",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [source["source_ref"] for source in payload["sources"]] == [".mypy_cache/cache.py"]
    assert not sources[".mypy_cache/cache.py"].exists()
    assert sources["docs/keep.md"].exists()


@pytest.mark.parametrize("selector", ["docs/brief.md", "source:docs/brief.md", "brief"])
def test_cli_source_forget_resolves_exact_selectors(tmp_path: Path, capsys, selector: str) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "docs" / "brief.md"
    source_path.parent.mkdir()
    source_path.write_text("# Brief\n\nSelector test.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", selector, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [source["source_id"] for source in payload["sources"]] == [source_id]


def test_cli_source_forget_reports_residual_maintained_refs(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nReferenced by a topic.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "add-topic", "Brief Notes", "--source-refs", source_id])
    topic_path = tmp_path / "wiki" / "topics" / "brief-notes.md"
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", source_id, "--apply", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["residual_references"] == [
        {
            "kind": "wiki_source_ref",
            "path": "wiki/topics/brief-notes.md",
            "source_id": source_id,
            "reason": "maintained wiki page source_refs contains source ID",
        },
        {
            "kind": "wiki_text",
            "path": "wiki/topics/brief-notes.md",
            "source_id": source_id,
            "reason": "wiki page text contains source ID",
        },
    ]
    assert source_id in topic_path.read_text(encoding="utf-8")


def test_cli_source_forget_rejects_ambiguous_titles(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    first = tmp_path / "a" / "brief.md"
    second = tmp_path / "b" / "brief.md"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first\n", encoding="utf-8")
    second.write_text("second\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(first)])
    main(["--root", str(tmp_path), "add-source", str(second)])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", "brief"])

    assert exit_code == 1
    assert "Source lookup is ambiguous" in capsys.readouterr().out


def test_cli_source_forget_rejects_missing_or_duplicate_selection_modes(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])

    no_selector = main(["--root", str(tmp_path), "source", "forget"])
    both_selectors = main(
        [
            "--root",
            str(tmp_path),
            "source",
            "forget",
            "src-123",
            "--matching",
            "docs/**",
        ]
    )
    empty_matching = main(["--root", str(tmp_path), "source", "forget", "--matching", ""])
    absolute_matching = main(["--root", str(tmp_path), "source", "forget", "--matching", "/tmp/**"])

    output = capsys.readouterr().out
    assert no_selector == 1
    assert both_selectors == 1
    assert empty_matching == 1
    assert absolute_matching == 1
    assert "requires exactly one" in output
    assert "requires a non-empty workspace-relative glob" in output
    assert "must be a workspace-relative glob" in output


def test_cli_source_forget_matching_can_preview_no_matches(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "source", "forget", "--matching", ".mypy_cache/**", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {
        "candidates": 0,
        "actions": 0,
        "skipped": 0,
        "residual_references": 0,
    }
    assert payload["sources"] == []


def test_cli_source_forget_reports_skipped_unsafe_cleanup(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nUnsafe cleanup branches.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    manifest_path = tmp_path / "state" / "manifests" / "sources" / f"{source_id}.json"
    source_summary = tmp_path / "wiki" / "sources" / f"{source_id}.md"
    source_summary.parent.mkdir(parents=True, exist_ok=True)
    source_summary.write_text("not frontmatter\n", encoding="utf-8")
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    queue_path.write_text("{bad json}\n", encoding="utf-8")
    unsafe_artifact = tmp_path / "scratch" / f"{source_id}.txt"
    unsafe_artifact.parent.mkdir()
    unsafe_artifact.write_text("unsafe\n", encoding="utf-8")
    source_record = load_source_record(manifest_path)
    write_source_record(
        manifest_path,
        source_record.model_copy(
            update={
                "derived_artifacts": [
                    "../outside.txt",
                    unsafe_artifact.relative_to(tmp_path).as_posix(),
                ],
                "linked_pages": [
                    source_summary.relative_to(tmp_path).as_posix(),
                    "../bad.md",
                ],
            }
        ),
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    skipped = {(item["kind"], item["path"]) for item in payload["skipped"]}
    assert ("source_summary_page", f"wiki/sources/{source_id}.md") in skipped
    assert ("source_summary_page", "../bad.md") in skipped
    assert ("queue_record", f"state/queue/ingest-{source_id}.json") in skipped
    assert ("artifact", "../outside.txt") in skipped
    assert ("artifact", f"scratch/{source_id}.txt") in skipped


def test_cli_source_forget_reports_valid_but_unsupported_queue_records(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nQueue mismatch.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    queue = QueueItemRecord.model_validate_json(queue_path.read_text(encoding="utf-8"))
    write_queue_item(queue_path, queue.model_copy(update={"job_type": "other"}))
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {(item["kind"], item["path"], item["reason"]) for item in payload["skipped"]} == {
        (
            "queue_record",
            f"state/queue/ingest-{source_id}.json",
            "queue record is not the expected source-owned ingest job",
        )
    }


def test_cli_source_forget_reports_mixed_run_and_provenance_residuals(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nMixed references.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    mixed_run_path = layout.runs_dir / "run-mixed.json"
    write_run_record(
        mixed_run_path,
        RunRecord(
            run_id="run-mixed",
            job_id="custom-job",
            job_type="ingest_source",
            started_at="2026-05-05T00:00:00Z",
            finished_at="2026-05-05T00:00:01Z",
            status="succeeded",
            pipeline_version=__version__,
            source_ids=[source_id, "src-other"],
        ),
    )
    invalid_run_path = layout.runs_dir / "run-invalid.json"
    invalid_run_path.write_text("{bad json}\n", encoding="utf-8")
    other_run_path = layout.runs_dir / "run-other.json"
    write_run_record(
        other_run_path,
        RunRecord(
            run_id="run-other",
            job_id="ingest-src-other",
            job_type="ingest_source",
            started_at="2026-05-05T00:00:00Z",
            finished_at="2026-05-05T00:00:01Z",
            status="succeeded",
            pipeline_version=__version__,
            source_ids=["src-other"],
        ),
    )
    page_path = tmp_path / "wiki" / "topics" / "provenance.md"
    frontmatter = KnowledgePageFrontmatter(
        kind="topic",
        title="Provenance",
        page_id="topic-provenance",
        status="active",
        source_refs=[],
        provenance_links=[ProvenanceLink(source_id=source_id, role="supports")],
    )
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        f"---\n{yaml.safe_dump(frontmatter.model_dump(mode='json'), sort_keys=False)}"
        "---\n\nBody.\n",
        encoding="utf-8",
    )
    malformed_page = tmp_path / "wiki" / "topics" / "malformed.md"
    malformed_page.write_text(f"body mentions {source_id}\n", encoding="utf-8")
    planning_path = tmp_path / "planning" / "tasks" / "task-ref.md"
    planning_path.write_text(f"mentions {source_id}\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {
        (item["kind"], item["path"]) for item in payload["skipped"] if item["kind"] == "run_record"
    } == {("run_record", "state/runs/run-mixed.json")}
    assert {(item["kind"], item["path"]) for item in payload["residual_references"]} == {
        ("planning_text", "planning/tasks/task-ref.md"),
        ("wiki_text", "wiki/topics/malformed.md"),
        ("wiki_provenance", "wiki/topics/provenance.md"),
    }


def test_cli_source_forget_human_output_reports_next_commands(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nHuman output.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    capsys.readouterr()

    preview_exit = main(["--root", str(tmp_path), "source", "forget", source_id])
    preview_output = capsys.readouterr().out
    apply_exit = main(["--root", str(tmp_path), "source", "forget", source_id, "--apply"])
    apply_output = capsys.readouterr().out

    assert preview_exit == 0
    assert "Source forget preview" in preview_output
    assert f"Next: splendor source forget {source_id} --apply" in preview_output
    assert apply_exit == 0
    assert "Source forget applied" in apply_output
    assert "Next: splendor lint" in apply_output
    assert "Next: splendor health" in apply_output


def test_cli_source_forget_human_output_reports_empty_matching_preview(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", "--matching", "missing/**"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Source forget preview" in output
    assert "No matching sources." in output


def test_cli_source_forget_removes_materialized_copy_artifacts(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "external.md"
    source_path.write_text("# External\n\nCopied.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path), "--storage-mode", "copy"])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    manifest_path = tmp_path / "state" / "manifests" / "sources" / f"{source_id}.json"
    materialized_path = tmp_path / "raw" / "sources" / source_id / "external.md"
    assert materialized_path.exists()
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "forget", source_id, "--apply", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {(item["kind"], item["path"]) for item in payload["actions"]} >= {
        ("materialized_artifact", f"raw/sources/{source_id}/external.md"),
        ("source_manifest", f"state/manifests/sources/{source_id}.json"),
    }
    assert not materialized_path.exists()
    assert not materialized_path.parent.exists()
    assert not manifest_path.exists()


def test_cli_workspace_refresh_parser_accepts_safe_refresh_flags() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["workspace", "refresh", "--changed", "--ingest", "--rebuild-index", "--json"]
    )

    assert args.command == "workspace"
    assert args.workspace_command == "refresh"
    assert args.changed is True
    assert args.ingest is True
    assert args.rebuild_index is True
    assert args.json_output is True


def test_cli_pr_summary_parser_accepts_since_and_json() -> None:
    parser = build_parser()

    args = parser.parse_args(["pr-summary", "--since", "origin/main", "--json"])

    assert args.command == "pr-summary"
    assert args.since == "origin/main"
    assert args.json_output is True


def test_cli_query_parser_accepts_filters_and_no_question() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["query", "--tag", "preprocessing", "--tag", "audio", "--source", "src-123", "--json"]
    )

    assert args.command == "query"
    assert args.question == []
    assert args.tags == ["preprocessing", "audio"]
    assert args.source_id == "src-123"
    assert args.json_output is True


def test_cli_brief_parser_accepts_agent_context() -> None:
    parser = build_parser()

    args = parser.parse_args(["brief", "--agent-context", "query", "handoff", "--json"])

    assert args.command == "brief"
    assert args.agent_context is True
    assert args.goal == ["query", "handoff"]
    assert args.json_output is True


def test_cli_suggest_next_parser_accepts_goal_and_json() -> None:
    parser = build_parser()

    args = parser.parse_args(["suggest-next", "agent", "handoff", "--json"])

    assert args.command == "suggest-next"
    assert args.goal == ["agent", "handoff"]
    assert args.json_output is True


def test_cli_repo_scan_parser_accepts_preview_apply_and_report_flags() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "repo",
            "scan",
            "--apply",
            "--class",
            "documentation",
            "--class",
            "code",
            "--all",
            "--allow-large-apply",
            "--report",
            "reports/repo-scan.json",
            "--json",
        ]
    )

    assert args.command == "repo"
    assert args.repo_command == "scan"
    assert args.apply is True
    assert args.class_filters == ["documentation", "code"]
    assert args.all_classes is True
    assert args.allow_large_apply is True
    assert args.report == Path("reports/repo-scan.json")
    assert args.json_output is True


def test_cli_repo_refresh_parser_accepts_apply_scan_flags() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "repo",
            "refresh",
            "--apply-scan",
            "--class",
            "documentation",
            "--all",
            "--allow-large-apply",
            "--json",
        ]
    )

    assert args.command == "repo"
    assert args.repo_command == "refresh"
    assert args.apply_scan is True
    assert args.class_filters == ["documentation"]
    assert args.all_classes is True
    assert args.allow_large_apply is True
    assert args.json_output is True


def test_cli_wiki_rebuild_index_parser_accepts_json_flag() -> None:
    parser = build_parser()

    args = parser.parse_args(["wiki", "rebuild-index", "--json"])

    assert args.command == "wiki"
    assert args.wiki_command == "rebuild-index"
    assert args.json_output is True


def test_cli_wiki_compile_parser_accepts_reviewed_apply_page() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "wiki",
            "compile",
            "src-example",
            "--page",
            "wiki/topics/example.md",
            "--apply",
            "--proposal-hash",
            "abc123",
            "--json",
        ]
    )

    assert args.command == "wiki"
    assert args.wiki_command == "compile"
    assert args.source_id == "src-example"
    assert args.page == "wiki/topics/example.md"
    assert args.apply is True
    assert args.proposal_hash == "abc123"
    assert args.json_output is True


def test_cli_serve_parser_uses_default_host_and_port() -> None:
    parser = build_parser()

    args = parser.parse_args(["serve"])

    assert args.command == "serve"
    assert args.host == "127.0.0.1"
    assert args.port == 8000


def test_cli_serve_parser_accepts_host_and_port() -> None:
    parser = build_parser()

    args = parser.parse_args(["serve", "--host", "0.0.0.0", "--port", "8123"])

    assert args.command == "serve"
    assert args.host == "0.0.0.0"
    assert args.port == 8123


def test_cli_repo_refresh_command_generates_pages(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    (tmp_path / "splendor.yaml").unlink()
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "repo", "refresh"])

    assert exit_code == 0
    assert (tmp_path / "wiki" / "architecture" / "repository-structure.md").exists()
    assert (tmp_path / "wiki" / "topics" / "repository-sources.md").exists()
    captured = capsys.readouterr()
    assert "Repo refresh summary:" in captured.out
    assert "wiki/architecture/repository-structure.md" in captured.out


def test_cli_repo_refresh_json_command(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    (tmp_path / "splendor.yaml").unlink()
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "repo", "refresh", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scanned"] == 1
    assert payload["generated_page_refs"] == [
        "wiki/architecture/repository-structure.md",
        "wiki/topics/repository-sources.md",
    ]


def test_cli_repo_scan_preview_shows_source_id_for_new_version_candidate(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    (tmp_path / "splendor.yaml").unlink()
    source = tmp_path / "README.md"
    source.write_text("# One\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = load_source_record(
        next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    ).source_id
    source.write_text("# Two\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "repo", "scan"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "README.md: new_version_candidate" in captured.out
    assert f"source_id={source_id}" in captured.out


def test_cli_repo_scan_json_repeated_class_filters_honor_ignored_dirs(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    (tmp_path / "splendor.yaml").unlink()
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.local.json").write_text("{}\n", encoding="utf-8")
    cache_dir = tmp_path / ".mypy_cache"
    cache_dir.mkdir()
    (cache_dir / "module.py").write_text("print('ignored')\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "repo",
            "scan",
            "--class",
            "documentation",
            "--class",
            "code",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["path"] for item in payload["candidate_sources"]] == [
        "README.md",
        "src/main.py",
    ]
    assert payload["class_filters"] == ["documentation", "code"]
    ignored = {item["path"]: item["reason"] for item in payload["ignored_paths"]}
    assert ignored[".claude/"] == "managed_or_transient"
    assert ignored[".mypy_cache/"] == "managed_or_transient"


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


def test_cli_add_source_glob_registers_sources_in_deterministic_order(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "zeta.md").write_text("# Zeta\n", encoding="utf-8")
    (docs / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (docs / "ignore.txt").write_text("Ignore\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "add-source", "--glob", "docs/*.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Registered sources: 2" in out
    assert out.index("docs/alpha.md") < out.index("docs/zeta.md")
    manifests = sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    assert len(manifests) == 2
    refs = sorted(load_source_record(path).source_ref for path in manifests)
    assert refs == ["docs/alpha.md", "docs/zeta.md"]
    assert len(list((tmp_path / "state" / "queue").glob("*.json"))) == 2


def test_cli_add_source_dir_registers_direct_child_files(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    docs = tmp_path / "docs"
    nested = docs / "nested"
    nested.mkdir(parents=True)
    (docs / "brief.md").write_text("# Brief\n", encoding="utf-8")
    (nested / "skip.md").write_text("# Skip\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "add-source", "--dir", "docs"])

    assert exit_code == 0
    manifests = list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    assert len(manifests) == 1
    assert load_source_record(manifests[0]).source_ref == "docs/brief.md"


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


def test_cli_source_lookup_maps_readable_path_to_source_id(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "audio-quality-feedback.md"
    source.write_text("# Audio Quality Feedback\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "lookup", "audio quality"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Sources: 1" in out
    assert "Audio Quality Feedback" in out or "audio quality feedback" in out
    assert "docs/audio-quality-feedback.md" in out
    assert "logical_id=source:docs/audio-quality-feedback.md" in out
    assert out.index("docs/audio-quality-feedback.md") < out.index("source_id=src-")


def test_cli_source_list_reports_registered_sources(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "list"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Sources: 1" in out
    assert "brief" in out
    assert "ref=brief.md" in out


def test_cli_source_lookup_matches_stable_logical_id(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "docs" / "brief.md"
    source.parent.mkdir()
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "source", "lookup", "source:docs/brief.md", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [source["source_id"] for source in payload["sources"]] == [source_id]
    assert payload["sources"][0]["logical_id"] == "source:docs/brief.md"


def test_cli_source_list_json_reports_registered_sources(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "list", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [source["source_id"] for source in payload["sources"]] == [source_id]
    assert payload["sources"][0]["logical_id"] == "source:brief.md"
    assert payload["sources"][0]["aliases"] == ["brief.md", "source:brief.md"]
    assert payload["sources"][0]["source_ref"] == "brief.md"


def test_cli_source_lookup_json_reports_source_payload(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "lookup", "brief", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sources"] == [
        {
            "source_id": source_id,
            "logical_id": "source:brief.md",
            "aliases": ["brief.md", "source:brief.md"],
            "title": "brief",
            "source_type": "md",
            "status": "registered",
            "supersedes": [],
            "superseded_by": None,
            "source_ref": "brief.md",
            "source_ref_kind": "workspace_path",
            "original_path": "brief.md",
            "checksum": load_source_record(
                tmp_path / "state" / "manifests" / "sources" / f"{source_id}.json"
            ).checksum,
            "manifest_path": f"state/manifests/sources/{source_id}.json",
            "queue_job_id": f"ingest-{source_id}",
            "linked_pages": [],
        }
    ]


def test_cli_source_lookup_does_not_match_copy_storage_paths(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    external_source = external_dir / "outside.md"
    external_source.write_text("# Outside\n", encoding="utf-8")
    try:
        main(["--root", str(tmp_path), "add-source", str(external_source)])
        capsys.readouterr()

        exit_code = main(["--root", str(tmp_path), "source", "lookup", "raw/sources"])

        assert exit_code == 0
        assert "Sources: 0" in capsys.readouterr().out
    finally:
        external_source.unlink(missing_ok=True)
        external_dir.rmdir()


def test_cli_source_refresh_registers_changed_workspace_source_and_queues_it(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    original_manifest = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    original_id = original_manifest.stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Detected changed source content for brief.md" in out
    assert f"Requested source ID: {original_id}" in out
    manifests = sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    assert len(manifests) == 2
    refreshed_id = [path.stem for path in manifests if path.stem != original_id][0]
    assert f"Registered refreshed source ID: {refreshed_id}" in out
    assert (tmp_path / "state" / "queue" / f"ingest-{refreshed_id}.json").exists()
    records = [load_source_record(path) for path in manifests]
    assert {record.logical_id for record in records} == {"source:brief.md"}
    assert {tuple(record.aliases) for record in records} == {("brief.md",)}
    records_by_id = {record.source_id: record for record in records}
    assert records_by_id[original_id].superseded_by == refreshed_id
    assert records_by_id[refreshed_id].supersedes == [original_id]
    assert records_by_id[refreshed_id].superseded_by is None


def test_cli_source_refresh_reports_existing_version_match(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "source", "refresh", "brief.md"])
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"Matched existing source version: {original_id}" in out
    assert f"Registered refreshed source {original_id}" not in out
    records = {
        load_source_record(path).source_id: load_source_record(path)
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
    }
    refreshed_id = next(source_id for source_id in records if source_id != original_id)
    assert records[refreshed_id].superseded_by == original_id
    assert records[original_id].supersedes == [refreshed_id]
    assert records[original_id].superseded_by is None


def test_source_refresh_noop_returns_existing_materialized_path(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "--storage-mode", "copy", str(source)])
    capsys.readouterr()

    result = refresh_source(tmp_path, "brief.md")

    assert result.changed is False
    assert result.refreshed.stored_path == (
        tmp_path / "raw" / "sources" / result.refreshed.record.source_id / "brief.md"
    )
    assert result.refreshed.stored_path.exists()


def test_cli_source_refresh_json_reports_queue_handoff(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    refreshed_ids = [
        path.stem
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path.stem != original_id
    ]
    assert payload == {
        "requested_source_id": original_id,
        "requested_logical_id": "source:brief.md",
        "source_id": refreshed_ids[0],
        "logical_id": "source:brief.md",
        "supersedes": [original_id],
        "superseded_by": None,
        "requested_superseded_by": refreshed_ids[0],
        "changed": True,
        "queued": True,
        "queue_path": f"state/queue/ingest-{refreshed_ids[0]}.json",
        "message": "queued ingest",
    }


def test_cli_source_refresh_preserves_no_commit_capture_intent(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "--no-capture-source-commit", str(source)])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    manifest = load_source_record(manifest_path)
    assert manifest.source_commit_capture is False
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("source commit capture should remain disabled")

    monkeypatch.setattr("splendor.state.source_registry.captured_source_commit", fail_if_called)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 0
    refreshed_records = [
        load_source_record(path)
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path != manifest_path
    ]
    assert refreshed_records[0].source_commit_capture is False


def test_cli_source_refresh_preserves_positive_commit_capture_intent(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    manifest = load_source_record(manifest_path)
    write_source_record(
        manifest_path,
        manifest.model_copy(update={"source_commit_capture": True, "source_commit": None}),
    )
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    monkeypatch.setattr(
        "splendor.state.source_registry.captured_source_commit",
        lambda *_args, **_kwargs: "new",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 0
    refreshed_records = [
        load_source_record(path)
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path != manifest_path
    ]
    assert refreshed_records[0].source_commit_capture is True
    assert refreshed_records[0].source_commit == "new"


def test_cli_source_refresh_uses_config_default_for_legacy_commit_capture_intent(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    manifest_payload = load_source_record(manifest_path).model_dump(mode="json")
    manifest_payload.pop("source_commit_capture")
    manifest_payload["source_commit"] = None
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    monkeypatch.setattr(
        "splendor.state.source_registry.captured_source_commit",
        lambda *_args, **_kwargs: "legacy-new",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 0
    refreshed_records = [
        load_source_record(path)
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path != manifest_path
    ]
    assert refreshed_records[0].source_commit_capture is None
    assert refreshed_records[0].source_commit == "legacy-new"


def test_cli_source_refresh_preserves_legacy_positive_commit_capture_intent(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    main(["--root", str(tmp_path), "init"])
    config = load_config(tmp_path)
    config.sources.capture_source_commit = False
    write_config(tmp_path, config)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    manifest_payload = load_source_record(manifest_path).model_dump(mode="json")
    manifest_payload.pop("source_commit_capture")
    manifest_payload["source_commit"] = "legacy-old"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    monkeypatch.setattr(
        "splendor.state.source_registry.captured_source_commit",
        lambda *_args, **_kwargs: "legacy-new",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 0
    refreshed_records = [
        load_source_record(path)
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path != manifest_path
    ]
    assert refreshed_records[0].source_commit_capture is True
    assert refreshed_records[0].source_commit == "legacy-new"


def test_cli_source_refresh_supports_original_path_legacy_manifest(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    manifest = load_source_record(manifest_path)
    write_source_record(
        manifest_path,
        manifest.model_copy(
            update={
                "source_ref": None,
                "source_ref_kind": None,
                "storage_mode": None,
                "storage_path": None,
                "path": "raw/sources/legacy/brief.md",
            }
        ),
    )
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 0
    assert "Detected changed source content" in capsys.readouterr().out


def test_cli_source_refresh_by_path_uses_latest_matching_source_ref(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "source", "refresh", "brief.md"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "ambiguous" not in out
    assert "No source content change detected" in out


def test_cli_source_update_path_repairs_missing_workspace_source(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    docs = tmp_path / "docs"
    docs.mkdir()
    moved = tmp_path / "moved"
    moved.mkdir()
    old_source = docs / "brief.md"
    new_source = moved / "brief.md"
    old_source.write_text("# Brief\n\nSame bytes.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "docs/brief.md"])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_path.stem
    old_source.rename(new_source)
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "source", "update-path", "docs/brief.md", "moved/brief.md"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"Updated source path for {source_id}" in out
    assert "Old path: docs/brief.md" in out
    assert "New path: moved/brief.md" in out
    assert "Status: repaired" in out
    assert "Logical ID: source:docs/brief.md" in out
    assert "Checksum: matches manifest" in out
    assert f"Queued ingest: {tmp_path / 'state' / 'queue' / f'ingest-{source_id}.json'}" in out
    assert "Next: splendor ingest --pending" in out
    updated = load_source_record(manifest_path)
    assert updated.source_id == source_id
    assert updated.source_ref == "moved/brief.md"
    assert updated.path == "moved/brief.md"
    assert updated.original_path == "docs/brief.md"
    assert updated.logical_id == "source:docs/brief.md"
    assert updated.aliases == ["docs/brief.md", "moved/brief.md"]
    assert len(list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))) == 1

    lookup_code = main(
        ["--root", str(tmp_path), "source", "lookup", "source:docs/brief.md", "--json"]
    )
    assert lookup_code == 0
    lookup_payload = json.loads(capsys.readouterr().out)
    assert lookup_payload["sources"][0]["source_id"] == source_id

    freshness_code = main(["--root", str(tmp_path), "source", "freshness", "--json"])
    assert freshness_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unchanged"] == 1
    assert payload["missing"] == 0

    health_code = main(["--root", str(tmp_path), "health"])
    assert health_code == 0


def test_cli_source_update_path_json_reports_deterministic_payload(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    old_source = tmp_path / "old.md"
    new_source = tmp_path / "new.md"
    old_source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "old.md"])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    manifest = load_source_record(manifest_path)
    old_source.rename(new_source)
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "source", "update-path", manifest.source_id, "new.md", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "source_id": manifest.source_id,
        "logical_id": "source:old.md",
        "old_path": "old.md",
        "new_path": "new.md",
        "status": "repaired",
        "source_ref": "new.md",
        "aliases": ["old.md", "new.md"],
        "manifest_checksum": manifest.checksum,
        "current_checksum": manifest.checksum,
        "checksum_matches": True,
        "manifest_path": f"state/manifests/sources/{manifest.source_id}.json",
        "updated": True,
        "queue_path": f"state/queue/ingest-{manifest.source_id}.json",
        "next_commands": [
            "splendor ingest --pending",
            "splendor source freshness",
        ],
    }


@pytest.mark.parametrize(
    ("target_name", "target_content", "expected_message"),
    [
        ("missing.md", None, "Target source path does not exist"),
        ("unsupported.bin", b"binary", "Target source type is not supported"),
    ],
)
def test_cli_source_update_path_rejects_invalid_targets(
    tmp_path: Path,
    capsys,
    target_name: str,
    target_content: bytes | None,
    expected_message: str,
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "old.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "old.md"])
    source.unlink()
    if target_content is not None:
        (tmp_path / target_name).write_bytes(target_content)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "update-path", "old.md", target_name])

    assert exit_code == 1
    assert expected_message in capsys.readouterr().out


def test_cli_source_update_path_rejects_directory_and_ambiguous_target(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    moved = tmp_path / "moved.md"
    first.write_text("# First\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "first.md"])
    first_manifest = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    main(["--root", str(tmp_path), "add-source", "second.md"])
    capsys.readouterr()

    existing_exit = main(
        ["--root", str(tmp_path), "source", "update-path", "first.md", "second.md"]
    )
    assert existing_exit == 1
    assert "still exists" in capsys.readouterr().out

    first.rename(moved)
    directory_exit = main(["--root", str(tmp_path), "source", "update-path", "first.md", "."])
    assert directory_exit == 1
    assert "Target source path must be a file" in capsys.readouterr().out

    target_exit = main(
        [
            "--root",
            str(tmp_path),
            "source",
            "update-path",
            first_manifest.stem,
            "second.md",
            "--force",
        ]
    )
    assert target_exit == 1
    assert "already curated by another active source" in capsys.readouterr().out


def test_cli_source_update_path_does_not_mutate_maintained_synthesis(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    topic = tmp_path / "wiki" / "topics" / "briefing.md"
    topic.write_text("# Maintained Topic\n\nSource refs stay manual.\n", encoding="utf-8")
    source = tmp_path / "old.md"
    replacement = tmp_path / "new.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "old.md"])
    source.rename(replacement)
    topic_before = topic.read_text(encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "update-path", "old.md", "new.md"])

    assert exit_code == 0
    assert topic.read_text(encoding="utf-8") == topic_before


def test_cli_source_update_path_reingests_same_byte_move_to_refresh_provenance(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "old.md"
    replacement = tmp_path / "new.md"
    source.write_text("# Brief\n\nSame bytes.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "old.md"])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_path.stem
    main(["--root", str(tmp_path), "ingest", "--pending"])
    page_path = tmp_path / "wiki" / "sources" / f"{source_id}.md"
    assert "old.md" in page_path.read_text(encoding="utf-8")
    source.rename(replacement)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "update-path", "old.md", "new.md"])

    assert exit_code == 0
    updated = load_source_record(manifest_path)
    assert updated.status == "registered"
    assert updated.last_run_id is not None
    assert (tmp_path / "state" / "queue" / f"ingest-{source_id}.json").exists()

    ingest_code = main(["--root", str(tmp_path), "ingest", "--pending"])

    assert ingest_code == 0
    page_text = page_path.read_text(encoding="utf-8")
    assert "new.md" in page_text


def test_cli_source_update_path_changed_bytes_reports_partial_repair(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "old.md"
    replacement = tmp_path / "new.md"
    source.write_text("# Brief\n\nOld bytes.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "old.md"])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source.rename(replacement)
    replacement.write_text("# Brief\n\nNew bytes.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "source", "update-path", "old.md", "new.md", "--json"]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "partial"
    assert payload["checksum_matches"] is False
    assert payload["queue_path"] is None
    assert payload["next_commands"] == [
        "splendor source refresh new.md",
        "splendor ingest --pending",
        "splendor source freshness",
    ]
    updated = load_source_record(manifest_path)
    assert updated.source_ref == "new.md"
    assert updated.status == "registered"


def test_cli_source_freshness_reports_changed_workspace_sources_without_mutating(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_path.stem
    before_manifest = manifest_path.read_text(encoding="utf-8")
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "freshness"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Source freshness preview" in out
    assert "changed=1" in out
    assert (
        f"- brief.md: changed title=brief logical_id=source:brief.md source_id={source_id}" in out
    )
    assert "Manifest checksum:" in out
    assert "Current checksum:" in out
    assert "Next: splendor source refresh brief.md" in out
    assert "Next: splendor ingest --pending" in out
    assert "Next: splendor source refresh <path>" not in out
    assert manifest_path.read_text(encoding="utf-8") == before_manifest
    assert len(list((tmp_path / "state" / "manifests" / "sources").glob("*.json"))) == 1
    assert not list((tmp_path / "reports").glob("**/*.json"))


def test_cli_source_freshness_quotes_changed_source_path_next_command(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief with spaces.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "freshness", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["sources"][0]
    assert item["status"] == "changed"
    assert item["next_commands"] == [
        "splendor source refresh 'brief with spaces.md'",
        "splendor ingest --pending",
    ]


def test_cli_source_freshness_json_reports_unchanged_missing_and_unsupported(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    unchanged = tmp_path / "unchanged.md"
    missing = tmp_path / "missing.md"
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    external = external_dir / "outside.md"
    unchanged.write_text("# Unchanged\n", encoding="utf-8")
    missing.write_text("# Missing\n", encoding="utf-8")
    external.write_text("# Outside\n", encoding="utf-8")
    try:
        main(["--root", str(tmp_path), "add-source", str(unchanged)])
        main(["--root", str(tmp_path), "add-source", str(missing)])
        main(["--root", str(tmp_path), "add-source", str(external)])
        missing.unlink()
        capsys.readouterr()

        exit_code = main(["--root", str(tmp_path), "source", "freshness", "--json"])

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["total"] == 3
        assert payload["unchanged"] == 1
        assert payload["missing"] == 1
        assert payload["unsupported"] == 1
        statuses = {source["path"]: source for source in payload["sources"]}
        assert statuses["unchanged.md"]["status"] == "unchanged"
        assert (
            statuses["unchanged.md"]["current_checksum"]
            == statuses["unchanged.md"]["manifest_checksum"]
        )
        assert statuses["missing.md"]["status"] == "missing"
        assert statuses["missing.md"]["current_checksum"] is None
        assert statuses["missing.md"]["next_commands"] == [
            f"splendor source lookup {statuses['missing.md']['source_id']}"
        ]
        assert statuses["unchanged.md"]["next_commands"] == [
            f"splendor ingest {statuses['unchanged.md']['source_id']}"
        ]
        assert statuses[external.resolve().as_posix()]["status"] == "unsupported"
        assert statuses[external.resolve().as_posix()]["next_commands"] == []
    finally:
        external.unlink(missing_ok=True)
        external_dir.rmdir()


def test_cli_source_freshness_suggests_wiki_work_only_after_current_ingest(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nCurrent.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", "--pending"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "freshness", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["sources"][0]
    assert item["status"] == "unchanged"
    assert item["next_commands"] == [f"splendor wiki suggest {source_id}"]


def test_cli_source_freshness_marks_old_versions_historical_when_current_manifest_exists(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "source", "refresh", "brief.md"])
    refreshed_id = next(
        path.stem
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path.stem != original_id
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "freshness", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["changed"] == 0
    assert payload["unchanged"] == 1
    assert payload["historical"] == 1
    statuses = {source["source_id"]: source for source in payload["sources"]}
    assert statuses[original_id]["status"] == "historical"
    assert statuses[original_id]["next_commands"] == []
    assert statuses[refreshed_id]["status"] == "unchanged"


def test_cli_source_freshness_targets_latest_manifest_when_file_reverts(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    original_text = "# Brief\n\nOriginal.\n"
    source.write_text(original_text, encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "source", "refresh", "brief.md"])
    refreshed_id = next(
        path.stem
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path.stem != original_id
    )
    source.write_text(original_text, encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "freshness", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["changed"] == 1
    assert payload["unchanged"] == 0
    assert payload["historical"] == 1
    statuses = {source["source_id"]: source for source in payload["sources"]}
    assert statuses[original_id]["status"] == "historical"
    assert statuses[refreshed_id]["status"] == "changed"
    assert statuses[refreshed_id]["next_commands"] == [
        "splendor source refresh brief.md",
        "splendor ingest --pending",
    ]


def test_cli_source_freshness_report_writes_only_explicit_report(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    manifest_paths_before = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
    )
    queue_paths_before = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in (tmp_path / "state" / "queue").glob("*.json")
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "source",
            "freshness",
            "--report",
            str(tmp_path / "reports" / "source-freshness.json"),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_path"] == (tmp_path / "reports" / "source-freshness.json").as_posix()
    report_payload = json.loads((tmp_path / "reports" / "source-freshness.json").read_text())
    assert report_payload["unchanged"] == 1
    assert (
        sorted(
            path.relative_to(tmp_path).as_posix()
            for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        )
        == manifest_paths_before
    )
    assert (
        sorted(
            path.relative_to(tmp_path).as_posix()
            for path in (tmp_path / "state" / "queue").glob("*.json")
        )
        == queue_paths_before
    )
    assert not list((tmp_path / "wiki").glob("sources/*.md"))
    assert not list((tmp_path / "state" / "runs").glob("*.json"))


def test_cli_source_freshness_relative_report_uses_current_working_directory(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    root = tmp_path / "workspace"
    cwd = tmp_path / "caller"
    root.mkdir()
    cwd.mkdir()
    main(["--root", str(root), "init"])
    source = root / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(root), "add-source", str(source)])
    monkeypatch.chdir(cwd)
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(root),
            "source",
            "freshness",
            "--report",
            "reports/source-freshness.json",
            "--json",
        ]
    )

    expected_report = cwd / "reports" / "source-freshness.json"
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_path"] == expected_report.as_posix()
    assert expected_report.exists()
    assert not (root / "reports" / "source-freshness.json").exists()


def test_cli_workspace_refresh_requires_maintenance_action(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "workspace", "refresh"])

    assert exit_code == 1
    assert "Error: workspace refresh requires at least one maintenance action" in (
        capsys.readouterr().out
    )


def test_cli_workspace_refresh_ingest_requires_changed(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "workspace", "refresh", "--ingest"])

    assert exit_code == 1
    assert "Error: workspace refresh --ingest requires --changed" in capsys.readouterr().out


def test_cli_workspace_refresh_rebuilds_index_standalone(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "workspace", "refresh", "--rebuild-index", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["refreshed"] == []
    assert payload["ingest"] is None
    assert payload["index"]["path"] == "wiki/index.md"
    assert payload["index"]["page_count"] == 0


def test_cli_workspace_refresh_changed_ingests_and_rebuilds_index(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "workspace",
            "refresh",
            "--changed",
            "--ingest",
            "--rebuild-index",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["initial_freshness"]["changed"] == 1
    assert payload["final_freshness"]["changed"] == 0
    assert payload["ingest"]["failed"] == 0
    assert payload["ingest"]["succeeded"] == 1
    assert payload["index"]["path"] == "wiki/index.md"
    refreshed = payload["refreshed"][0]
    assert refreshed["path"] == "brief.md"
    assert refreshed["requested_source_id"] == original_id
    assert refreshed["logical_id"] == "source:brief.md"
    refreshed_id = refreshed["source_id"]
    assert refreshed_id != original_id
    assert refreshed["supersedes"] == [original_id]
    assert (tmp_path / "wiki" / "sources" / f"{refreshed_id}.md").exists()
    index_text = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert f"sources/{refreshed_id}.md" in index_text

    assert main(["--root", str(tmp_path), "lint"]) == 0
    assert main(["--root", str(tmp_path), "health"]) == 0


def test_cli_workspace_refresh_prunes_superseded_summaries_standalone(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    config = load_config(tmp_path)
    config.reviews.contradictions.enabled = False
    write_config(tmp_path, config)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    main(
        [
            "--root",
            str(tmp_path),
            "workspace",
            "refresh",
            "--changed",
            "--ingest",
            "--rebuild-index",
        ]
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "workspace",
            "refresh",
            "--prune-superseded",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    refreshed_id = payload["pruning"]["pruned"][0]["superseded_by"]
    assert payload["refreshed"] == []
    assert payload["ingest"] is None
    assert payload["pruning"]["pruned"] == [
        {
            "path": f"wiki/sources/{original_id}.md",
            "source_id": original_id,
            "superseded_by": refreshed_id,
            "manifest_path": f"state/manifests/sources/{original_id}.json",
        }
    ]
    assert not (tmp_path / "wiki" / "sources" / f"{original_id}.md").exists()
    original_manifest = load_source_record(
        tmp_path / "state" / "manifests" / "sources" / f"{original_id}.json"
    )
    assert f"wiki/sources/{original_id}.md" not in original_manifest.linked_pages


def test_cli_workspace_refresh_changed_rebuilds_index_without_ingest(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "workspace", "refresh", "--changed", "--rebuild-index"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Rebuilt index: " in out
    assert "Next: splendor ingest --pending, then splendor wiki rebuild-index" in out
    assert list((tmp_path / "state" / "queue").glob("ingest-*.json"))


def test_cli_workspace_refresh_prunes_superseded_summaries_and_updates_topic_refs(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    config = load_config(tmp_path)
    config.reviews.contradictions.enabled = False
    write_config(tmp_path, config)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(
        [
            "--root",
            str(tmp_path),
            "add-topic",
            "Brief Synthesis",
            "--source-refs",
            original_id,
        ]
    )
    topic_path = tmp_path / "wiki" / "topics" / "brief-synthesis.md"
    topic_path.write_text(
        topic_path.read_text(encoding="utf-8")
        + "\nHistorical note: keep old source id in prose "
        + f"`{original_id}`.\n\n"
        + "```text\n"
        + f"`{original_id}`\n"
        + "```\n\n"
        + "## Historical\n\n"
        + f"- `{original_id}`\n",
        encoding="utf-8",
    )
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "workspace",
            "refresh",
            "--changed",
            "--ingest",
            "--rebuild-index",
            "--prune-superseded",
            "--update-topic-refs",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    refreshed_id = payload["refreshed"][0]["source_id"]
    assert payload["pruning"]["pruned"] == [
        {
            "path": f"wiki/sources/{original_id}.md",
            "source_id": original_id,
            "superseded_by": refreshed_id,
            "manifest_path": f"state/manifests/sources/{original_id}.json",
        }
    ]
    assert payload["topic_ref_migration"]["updated"] == [
        {
            "path": "wiki/topics/brief-synthesis.md",
            "replacements": {original_id: refreshed_id},
        }
    ]
    assert not (tmp_path / "wiki" / "sources" / f"{original_id}.md").exists()
    assert (tmp_path / "wiki" / "sources" / f"{refreshed_id}.md").exists()
    original_manifest = load_source_record(
        tmp_path / "state" / "manifests" / "sources" / f"{original_id}.json"
    )
    assert f"wiki/sources/{original_id}.md" not in original_manifest.linked_pages

    topic_text = (tmp_path / "wiki" / "topics" / "brief-synthesis.md").read_text(encoding="utf-8")
    frontmatter_text = topic_text.removeprefix("---\n").split("\n---\n", maxsplit=1)[0]
    topic_frontmatter = yaml.safe_load(frontmatter_text)
    assert topic_frontmatter["source_refs"] == [refreshed_id]
    assert f"- `{refreshed_id}`" in topic_text
    assert f"Historical note: keep old source id in prose `{original_id}`." in topic_text
    assert f"```text\n`{original_id}`\n```" in topic_text
    assert f"## Historical\n\n- `{original_id}`" in topic_text
    index_text = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert f"sources/{original_id}.md" not in index_text
    assert f"sources/{refreshed_id}.md" in index_text

    assert main(["--root", str(tmp_path), "lint"]) == 0
    assert main(["--root", str(tmp_path), "health"]) == 0


def test_cli_workspace_refresh_reports_skipped_superseded_prune_candidates(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    main(
        [
            "--root",
            str(tmp_path),
            "workspace",
            "refresh",
            "--changed",
            "--ingest",
            "--rebuild-index",
        ]
    )
    old_summary = tmp_path / "wiki" / "sources" / f"{original_id}.md"
    old_summary.write_text("not frontmatter\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "workspace",
            "refresh",
            "--prune-superseded",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pruning"]["candidates"] == 1
    assert payload["pruning"]["pruned"] == []
    assert payload["pruning"]["skipped"][0]["path"] == f"wiki/sources/{original_id}.md"
    assert payload["pruning"]["skipped"][0]["source_id"] == original_id
    assert "missing YAML frontmatter" in payload["pruning"]["skipped"][0]["reason"]
    assert old_summary.exists()


def test_cli_workspace_refresh_ingests_only_refreshed_sources(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    changed_source = tmp_path / "changed.md"
    pending_source = tmp_path / "pending.md"
    changed_source.write_text("# Changed\n\nOriginal.\n", encoding="utf-8")
    pending_source.write_text("# Pending\n\nQueued separately.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(changed_source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    main(["--root", str(tmp_path), "add-source", str(pending_source)])
    pending_id = next(
        load_source_record(path).source_id
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if load_source_record(path).source_ref == "pending.md"
    )
    changed_source.write_text("# Changed\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "workspace", "refresh", "--changed", "--ingest", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ingest"]["total"] == 1
    assert payload["ingest"]["succeeded"] == 1
    assert load_queue_item(tmp_path / "state" / "queue" / f"ingest-{pending_id}.json").status == (
        "pending"
    )
    assert not (tmp_path / "wiki" / "sources" / f"{pending_id}.md").exists()


def test_cli_workspace_refresh_reports_missing_source_as_unresolved(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "missing.md"
    source.write_text("# Missing\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source.unlink()
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "workspace", "refresh", "--changed"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Workspace refresh" in out
    assert "No changed curated workspace-backed sources were refreshed." in out
    assert "Skipped unresolved curated workspace sources:" in out
    assert "- missing.md: missing (canonical workspace source file is missing)" in out
    assert "Workspace refresh completed with unresolved curated sources." in out


def test_cli_workspace_refresh_continues_valid_changed_source_when_another_source_is_missing(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    changed_source = tmp_path / "changed.md"
    missing_source = tmp_path / "missing.md"
    changed_source.write_text("# Changed\n\nOriginal.\n", encoding="utf-8")
    missing_source.write_text("# Missing\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(changed_source)])
    main(["--root", str(tmp_path), "add-source", str(missing_source)])
    changed_id = next(
        load_source_record(path).source_id
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if load_source_record(path).source_ref == "changed.md"
    )
    changed_source.write_text("# Changed\n\nUpdated.\n", encoding="utf-8")
    missing_source.unlink()
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "workspace", "refresh", "--changed"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Initial freshness: total=2 unchanged=0 changed=1 missing=1" in out
    assert "Final freshness: total=3 unchanged=1 changed=0 missing=1" in out
    assert "- missing.md: missing (canonical workspace source file is missing)" in out
    assert re.search(r"- changed\.md: refreshed source_id=src-[a-f0-9]{16}", out)
    assert f"Previous source ID: {changed_id}" in out
    refreshed_records = [
        load_source_record(path)
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if load_source_record(path).source_ref == "changed.md"
        and load_source_record(path).superseded_by is None
    ]
    assert len(refreshed_records) == 1
    assert refreshed_records[0].source_id != changed_id
    assert not (tmp_path / "wiki" / "topics").exists() or not list(
        (tmp_path / "wiki" / "topics").glob("*.md")
    )


def test_cli_workspace_refresh_json_reports_skipped_missing_and_final_freshness(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    changed_source = tmp_path / "changed.md"
    missing_source = tmp_path / "missing.md"
    changed_source.write_text("# Changed\n\nOriginal.\n", encoding="utf-8")
    missing_source.write_text("# Missing\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(changed_source)])
    main(["--root", str(tmp_path), "add-source", str(missing_source)])
    changed_source.write_text("# Changed\n\nUpdated.\n", encoding="utf-8")
    missing_source.unlink()
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "workspace", "refresh", "--changed", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["initial_freshness"] == {
        "total": 2,
        "unchanged": 0,
        "changed": 1,
        "missing": 1,
        "unsupported": 0,
        "historical": 0,
    }
    assert payload["final_freshness"]["total"] == 3
    assert payload["final_freshness"]["changed"] == 0
    assert payload["final_freshness"]["missing"] == 1
    assert payload["skipped_sources"][0]["path"] == "missing.md"
    assert payload["skipped_sources"][0]["status"] == "missing"
    assert payload["refreshed"][0]["path"] == "changed.md"
    assert payload["ingest"] is None


def test_cli_workspace_refresh_ingests_refreshed_valid_sources_despite_missing_source(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    changed_source = tmp_path / "changed.md"
    missing_source = tmp_path / "missing.md"
    pending_source = tmp_path / "pending.md"
    changed_source.write_text("# Changed\n\nOriginal.\n", encoding="utf-8")
    missing_source.write_text("# Missing\n\nOriginal.\n", encoding="utf-8")
    pending_source.write_text("# Pending\n\nQueued separately.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(changed_source)])
    main(["--root", str(tmp_path), "add-source", str(missing_source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    main(["--root", str(tmp_path), "add-source", str(pending_source)])
    pending_id = next(
        load_source_record(path).source_id
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if load_source_record(path).source_ref == "pending.md"
    )
    changed_source.write_text("# Changed\n\nUpdated.\n", encoding="utf-8")
    missing_source.unlink()
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "workspace", "refresh", "--changed", "--ingest", "--json"]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["skipped_sources"][0]["path"] == "missing.md"
    assert payload["ingest"]["total"] == 1
    assert payload["ingest"]["succeeded"] == 1
    assert load_queue_item(tmp_path / "state" / "queue" / f"ingest-{pending_id}.json").status == (
        "pending"
    )
    refreshed_id = payload["refreshed"][0]["source_id"]
    assert (tmp_path / "wiki" / "sources" / f"{refreshed_id}.md").exists()
    assert not (tmp_path / "wiki" / "sources" / f"{pending_id}.md").exists()


def test_cli_workspace_refresh_continues_after_changed_source_refresh_failure(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    main(["--root", str(tmp_path), "init"])
    ok_source = tmp_path / "ok.md"
    broken_source = tmp_path / "broken.md"
    ok_source.write_text("# OK\n\nOriginal.\n", encoding="utf-8")
    broken_source.write_text("# Broken\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(ok_source)])
    main(["--root", str(tmp_path), "add-source", str(broken_source)])
    broken_id = next(
        load_source_record(path).source_id
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if load_source_record(path).source_ref == "broken.md"
    )
    ok_source.write_text("# OK\n\nUpdated.\n", encoding="utf-8")
    broken_source.write_text("# Broken\n\nUpdated.\n", encoding="utf-8")

    def fail_one_source(root: Path, query: str):
        if query == "broken.md":
            raise RuntimeError("simulated refresh failure")
        return refresh_source(root, query)

    monkeypatch.setattr(workspace_module, "refresh_source", fail_one_source)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "workspace", "refresh", "--changed"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert re.search(r"- ok\.md: refreshed source_id=src-[a-f0-9]{16}", out)
    assert "Failed changed-source refreshes:" in out
    assert "- broken.md: failed (simulated refresh failure)" in out
    assert f"Source ID: {broken_id}" in out
    assert "Final freshness: total=3 unchanged=1 changed=1 missing=0" in out
    assert "Workspace refresh completed with unresolved curated sources." in out


def test_cli_workspace_refresh_json_reports_failed_refresh_and_ingests_successes(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    main(["--root", str(tmp_path), "init"])
    ok_source = tmp_path / "ok.md"
    broken_source = tmp_path / "broken.md"
    pending_source = tmp_path / "pending.md"
    ok_source.write_text("# OK\n\nOriginal.\n", encoding="utf-8")
    broken_source.write_text("# Broken\n\nOriginal.\n", encoding="utf-8")
    pending_source.write_text("# Pending\n\nQueued separately.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(ok_source)])
    main(["--root", str(tmp_path), "add-source", str(broken_source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    main(["--root", str(tmp_path), "add-source", str(pending_source)])
    pending_id = next(
        load_source_record(path).source_id
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if load_source_record(path).source_ref == "pending.md"
    )
    ok_source.write_text("# OK\n\nUpdated.\n", encoding="utf-8")
    broken_source.write_text("# Broken\n\nUpdated.\n", encoding="utf-8")

    def fail_one_source(root: Path, query: str):
        if query == "broken.md":
            raise ValueError("simulated refresh failure")
        return refresh_source(root, query)

    monkeypatch.setattr(workspace_module, "refresh_source", fail_one_source)
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "workspace", "refresh", "--changed", "--ingest", "--json"]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["initial_freshness"]["changed"] == 2
    assert payload["final_freshness"]["changed"] == 1
    assert payload["skipped_sources"] == []
    assert payload["failed_sources"] == [
        {
            "path": "broken.md",
            "source_id": payload["failed_sources"][0]["source_id"],
            "logical_id": "source:broken.md",
            "title": "broken",
            "manifest_path": (
                f"state/manifests/sources/{payload['failed_sources'][0]['source_id']}.json"
            ),
            "phase": "refresh",
            "reason": "simulated refresh failure",
        }
    ]
    assert payload["refreshed"][0]["path"] == "ok.md"
    assert payload["ingest"]["total"] == 1
    assert payload["ingest"]["succeeded"] == 1
    assert load_queue_item(tmp_path / "state" / "queue" / f"ingest-{pending_id}.json").status == (
        "pending"
    )
    refreshed_id = payload["refreshed"][0]["source_id"]
    assert (tmp_path / "wiki" / "sources" / f"{refreshed_id}.md").exists()
    assert not (tmp_path / "wiki" / "sources" / f"{pending_id}.md").exists()


def test_cli_workspace_refresh_human_output_is_path_first(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "workspace", "refresh", "--changed"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Workspace refresh" in out
    assert "Initial freshness:" in out
    assert "Final freshness:" in out
    assert "changed=1" in out
    assert "changed=0" in out
    assert re.search(r"- brief\.md: refreshed source_id=src-[a-f0-9]{16}", out)
    assert f"Previous source ID: {original_id}" in out
    assert "Next: splendor ingest --pending" in out


def test_cli_pr_summary_reports_generated_state_without_mutating(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    _git_init_main(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    main(["--root", str(tmp_path), "lint"])
    main(["--root", str(tmp_path), "health"])
    capsys.readouterr()
    report_paths_before = sorted(
        path.relative_to(tmp_path).as_posix() for path in tmp_path.glob("reports/**/*.json")
    )

    exit_code = main(["--root", str(tmp_path), "pr-summary", "--since", "main", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    source_manifest = payload["curated_sources"][0]
    assert source_manifest["action"] == "added"
    assert source_manifest["path"].startswith("state/manifests/sources/")
    assert source_manifest["source_ref"] == "brief.md"
    assert source_manifest["logical_id"] == "source:brief.md"
    assert payload["source_summary_pages"]["added"] == [
        f"wiki/sources/{source_manifest['source_id']}.md"
    ]
    assert payload["generated_state"]["queue"]["added"] == [
        f"state/queue/ingest-{source_manifest['source_id']}.json"
    ]
    assert payload["generated_state"]["runs"]["added"]
    assert payload["maintenance"]["lint"]["status"] == "passed"
    assert payload["maintenance"]["lint"]["scope"] == "latest_local_report"
    assert "not tied to the current HEAD" in payload["maintenance"]["lint"]["warning"]
    assert payload["maintenance"]["health"]["status"] == "passed"
    assert any("queue, run, and report files" in note for note in payload["reviewer_notes"])
    assert (
        sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.glob("reports/**/*.json"))
        == report_paths_before
    )


def test_cli_pr_summary_human_output_is_path_first(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    _git_init_main(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "pr-summary", "--since", "main"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PR summary since main" in out
    assert "Merge base:" in out
    assert re.search(r"- state/manifests/sources/src-[a-f0-9]+\.json: added", out)
    assert "Source ref: brief.md" in out
    assert "Generated state:" in out
    assert "- queue: total=1" in out
    assert "No local lint report was found" in out


def test_cli_pr_summary_uses_merge_base_when_main_advances(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    _git_init_main(tmp_path)
    _git_run(tmp_path, ["git", "switch", "-c", "feature"])
    feature_path = tmp_path / "feature.md"
    feature_path.write_text("# Feature\n", encoding="utf-8")
    _git_run(tmp_path, ["git", "add", "feature.md"])
    _git_run(tmp_path, ["git", "commit", "-m", "feature change"])
    _git_run(tmp_path, ["git", "switch", "main"])
    main_path = tmp_path / "main-only.md"
    main_path.write_text("# Main only\n", encoding="utf-8")
    _git_run(tmp_path, ["git", "add", "main-only.md"])
    _git_run(tmp_path, ["git", "commit", "-m", "main change"])
    _git_run(tmp_path, ["git", "switch", "feature"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "pr-summary", "--since", "main", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["merge_base"] != _git_stdout(tmp_path, ["git", "rev-parse", "main"])
    assert payload["other_paths"]["added"] == ["feature.md"]
    assert "main-only.md" not in json.dumps(payload)


def test_cli_pr_summary_respects_custom_layout_paths(tmp_path: Path, capsys) -> None:
    config = load_config(tmp_path)
    config.layout.wiki_dir = "knowledge"
    config.layout.state_dir = "custom-state"
    config.layout.reports_dir = "custom-reports"
    config.layout.source_records_dir = "custom-state/manifests/sources"
    write_config(tmp_path, config)
    main(["--root", str(tmp_path), "init"])
    _git_init_main(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    main(["--root", str(tmp_path), "ingest", "--pending"])
    main(["--root", str(tmp_path), "lint"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "pr-summary", "--since", "main", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    source_id = payload["curated_sources"][0]["source_id"]
    assert payload["curated_sources"][0]["path"] == (
        f"custom-state/manifests/sources/{source_id}.json"
    )
    assert payload["source_summary_pages"]["added"] == [f"knowledge/sources/{source_id}.md"]
    assert payload["generated_state"]["queue"]["added"] == [
        f"custom-state/queue/ingest-{source_id}.json"
    ]
    assert payload["generated_state"]["reports"]["added"]
    assert payload["maintenance"]["lint"]["path"].startswith("custom-reports/lint/")


def test_cli_pr_summary_reports_invalid_source_manifest_without_aborting(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    _git_init_main(tmp_path)
    manifest = tmp_path / "state" / "manifests" / "sources" / "src-bad.json"
    manifest.write_text("{bad json}\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "pr-summary", "--since", "main", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["curated_sources"]) == 1
    invalid_source = payload["curated_sources"][0]
    assert invalid_source["action"] == "invalid"
    assert "Invalid JSON" in invalid_source["error"]
    assert invalid_source["path"] == "state/manifests/sources/src-bad.json"
    assert invalid_source["source_id"] == "src-bad"


def _git_init_main(root: Path) -> None:
    subprocesses = [
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "splendor@example.test"],
        ["git", "config", "user.name", "Splendor Tests"],
        ["git", "add", "."],
        ["git", "commit", "-m", "baseline"],
    ]
    for command in subprocesses:
        _git_run(root, command)


def _git_run(root: Path, command: list[str]) -> None:
    result = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _git_stdout(root: Path, command: list[str]) -> str:
    result = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_cli_source_refresh_preserves_active_lease_protection(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    queue = load_queue_item(queue_path).model_copy(
        update={
            "status": "leased",
            "lease_owner": "local-cli:test",
            "lease_expires_at": "2999-01-01T00:00:00+00:00",
        }
    )
    queue_path.write_text(queue.model_dump_json(indent=2) + "\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 1
    assert f"Error: Queue item is already leased: ingest-{source_id}" in capsys.readouterr().out


def test_cli_source_refresh_preserves_dead_letter_protection(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    queue = load_queue_item(queue_path).model_copy(
        update={"status": "dead_letter", "last_error": "too many failures"}
    )
    queue_path.write_text(queue.model_dump_json(indent=2) + "\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "source", "refresh", "brief.md"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "dead-lettered" in out
    assert "splendor queue retry" in out


def test_cli_bulk_add_source_queues_successes_before_later_registration_failure(
    tmp_path: Path, capsys
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    workspace_source = repo_root / "brief.md"
    external_source = external_dir / "outside.md"
    workspace_source.write_text("# Brief\n", encoding="utf-8")
    external_source.write_text("# Outside\n", encoding="utf-8")

    main(["--root", str(repo_root), "init"])
    capsys.readouterr()
    exit_code = main(
        [
            "--root",
            str(repo_root),
            "add-source",
            "--storage-mode",
            "none",
            str(workspace_source),
            "--glob",
            str(external_source),
        ]
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Registration failures: 1" in out
    assert "Queued ingest jobs: 1" in out
    source_id = next((repo_root / "state" / "manifests" / "sources").glob("*.json")).stem
    assert (repo_root / "state" / "queue" / f"ingest-{source_id}.json").exists()


def test_cli_bulk_add_source_returns_nonzero_when_queue_handoff_fails(
    tmp_path: Path, capsys
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "add-source", "--glob", "*.md"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Queue warnings: 2" in out
    assert "Next: splendor init" in out
    assert "Then: splendor ingest --pending" in out


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


def test_cli_ingest_command_accepts_stable_logical_id(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "docs" / "brief.md"
    source.parent.mkdir()
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem

    exit_code = main(["--root", str(tmp_path), "ingest", "source:docs/brief.md"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert f"Source ID: {source_id}" in captured.out
    assert "Source ref: docs/brief.md" in captured.out


def test_cli_ingest_command_rejects_fuzzy_source_match(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "docs" / "brief.md"
    source.parent.mkdir()
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "ingest", "doc"])

    assert exit_code == 1
    assert "Unknown source: doc" in capsys.readouterr().out


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


def test_cli_ingest_changed_refreshes_completed_queue_source(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", original_id])
    manual_page = tmp_path / "wiki" / "topics" / "manual.md"
    manual_page.parent.mkdir(parents=True, exist_ok=True)
    manual_content = (
        "---\nschema_version: '1'\nkind: topic\ntitle: Manual\npage_id: manual\n---\nKept.\n"
    )
    manual_page.write_text(manual_content, encoding="utf-8")
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "ingest", "--changed"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Stale ingest" in out
    assert "Stale ingest summary: processed=1 succeeded=1 failed=0 skipped=0" in out
    manifests = sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    assert len(manifests) == 2
    records = {path.stem: load_source_record(path) for path in manifests}
    refreshed_id = next(source_id for source_id in records if source_id != original_id)
    assert records[original_id].superseded_by == refreshed_id
    assert records[refreshed_id].supersedes == [original_id]
    assert load_queue_item(tmp_path / "state" / "queue" / f"ingest-{original_id}.json").status == (
        "done"
    )
    assert load_queue_item(tmp_path / "state" / "queue" / f"ingest-{refreshed_id}.json").status == (
        "done"
    )
    assert (tmp_path / "wiki" / "sources" / f"{refreshed_id}.md").exists()
    assert manual_page.read_text(encoding="utf-8") == manual_content


def test_cli_ingest_changed_noops_for_unchanged_workspace(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", source_id])
    before_manifests = sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    before_runs = sorted((tmp_path / "state" / "runs").glob("*.json"))
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "ingest", "--changed"])

    assert exit_code == 0
    assert "No changed curated workspace-backed sources found." in capsys.readouterr().out
    assert sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json")) == before_manifests
    assert sorted((tmp_path / "state" / "runs").glob("*.json")) == before_runs


def test_ingest_changed_sources_returns_typed_noop_result(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", source_id])

    result = ingest_changed_sources(tmp_path)

    assert result.status == "no-op"
    assert result.initial_freshness == result.final_freshness
    assert result.processed == 0
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.skipped == 0


def test_cli_ingest_changed_reports_missing_sources_and_continues_valid_refresh(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    changed_source = tmp_path / "changed.md"
    changed_source.write_text("# Changed\n\nOriginal.\n", encoding="utf-8")
    missing_source = tmp_path / "missing.md"
    missing_source.write_text("# Missing\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(changed_source)])
    changed_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", changed_id])
    main(["--root", str(tmp_path), "add-source", str(missing_source)])
    missing_id = next(
        path.stem
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path.stem != changed_id
    )
    changed_source.write_text("# Changed\n\nUpdated.\n", encoding="utf-8")
    missing_source.unlink()
    before_manifest = (
        tmp_path / "state" / "manifests" / "sources" / f"{missing_id}.json"
    ).read_text(encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "ingest", "--changed"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Stale ingest completed with unresolved sources" in out
    assert "- missing.md: canonical workspace source file is missing" in out
    assert "Stale ingest summary: processed=1 succeeded=1 failed=0 skipped=0" in out
    manifests = sorted((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    assert len(manifests) == 3
    refreshed_id = next(
        path.stem for path in manifests if path.stem not in {changed_id, missing_id}
    )
    assert load_queue_item(tmp_path / "state" / "queue" / f"ingest-{refreshed_id}.json").status == (
        "done"
    )
    assert (tmp_path / "wiki" / "sources" / f"{refreshed_id}.md").exists()
    assert (tmp_path / "state" / "manifests" / "sources" / f"{missing_id}.json").read_text(
        encoding="utf-8"
    ) == before_manifest


def test_cli_ingest_changed_json_reports_refreshed_ingest(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    original_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", original_id])
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "ingest", "--changed", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "succeeded"
    assert payload["initial_freshness"]["changed"] == 1
    assert payload["final_freshness"]["changed"] == 0
    assert payload["summary"] == {"processed": 1, "succeeded": 1, "failed": 0, "skipped": 0}
    assert payload["refreshed"][0]["requested_source_id"] == original_id
    refreshed_id = payload["refreshed"][0]["refreshed_source_id"]
    assert payload["ingest"][0]["source_id"] == refreshed_id
    assert payload["ingest"][0]["outcome"] == "succeeded"
    load_source_record(tmp_path / "state" / "manifests" / "sources" / f"{refreshed_id}.json")


def test_cli_ingest_changed_json_includes_final_freshness_for_noop_and_blocked(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    main(["--root", str(tmp_path), "ingest", source_id])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "ingest", "--changed", "--json"])

    assert exit_code == 0
    noop_payload = json.loads(capsys.readouterr().out)
    assert noop_payload["status"] == "no-op"
    assert noop_payload["initial_freshness"] == noop_payload["final_freshness"]

    source.unlink()

    exit_code = main(["--root", str(tmp_path), "ingest", "--changed", "--json"])

    assert exit_code == 1
    blocked_payload = json.loads(capsys.readouterr().out)
    assert blocked_payload["status"] == "blocked"
    assert blocked_payload["initial_freshness"] == blocked_payload["final_freshness"]
    assert blocked_payload["missing"][0]["source_id"] == source_id


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

    with pytest.raises(SystemExit):
        main(["ingest", "src-123", "--changed"])

    with pytest.raises(SystemExit):
        main(["ingest", "--pending", "--json"])


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
    # add-source now creates one source manifest and one pending queue record.
    assert "Checked records: 2" in captured.out
    assert "Health check passed" in captured.out
    json_report, markdown_report = latest_report_paths(tmp_path, "health")
    assert json_report.stem == markdown_report.stem
    assert re.fullmatch(r"\d{8}T\d{6}Z(?:-\d+)?", json_report.stem)
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["command"] == "health"
    assert payload["status"] == "passed"
    assert payload["checked_count"] == 2
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


def test_cli_health_command_renders_remediation_hints_in_stdout_and_reports(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("hello\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source)])
    source.unlink()
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "health"])

    assert exit_code == 1
    captured = capsys.readouterr()
    expected_hint = (
        "Run splendor source update-path brief.md <new-path>; inspect current freshness first "
        "with splendor source freshness."
    )
    assert f"Hint: {expected_hint}" in captured.out
    json_report, markdown_report = latest_report_paths(tmp_path, "health")
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["issues"][0]["remediation_hint"] == expected_hint
    markdown = markdown_report.read_text(encoding="utf-8")
    assert f"hint: {expected_hint}" in markdown


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


def write_queryable_wiki_page(
    path: Path,
    *,
    title: str,
    page_id: str,
    body: str,
    source_refs: list[str] | None = None,
    tags: list[str] | None = None,
    contradictions: list[dict] | None = None,
) -> None:
    frontmatter = KnowledgePageFrontmatter(
        kind="concept",
        title=title,
        page_id=page_id,
        status="active",
        source_refs=source_refs or [],
        confidence=0.8,
        tags=tags or [],
        contradictions=contradictions or [],
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
    assert payload["matches"][0]["contradiction_count"] == 0
    assert payload["matches"][0]["review_task_ids"] == []
    assert payload["matches"][0]["tags"] == []


def test_cli_query_command_json_reports_active_filters(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "brief.md"])
    source_id = load_source_record(
        next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    ).source_id
    write_queryable_wiki_page(
        tmp_path / "wiki" / "topics" / "preprocessing.md",
        title="Preprocessing pipeline",
        page_id="topic-preprocessing-pipeline",
        source_refs=[source_id],
        tags=["preprocessing"],
        body="Preprocessing pipeline notes.",
    )
    write_queryable_wiki_page(
        tmp_path / "wiki" / "topics" / "deployment.md",
        title="Deployment pipeline",
        page_id="topic-deployment-pipeline",
        tags=["deployment"],
        body="Deployment pipeline notes.",
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "query",
            "--tag",
            "preprocessing",
            "--source",
            source_id,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == ""
    assert payload["filters"] == {
        "tags": ["preprocessing"],
        "source_id": source_id,
        "source_ids": [source_id],
    }
    assert payload["match_count"] == 1
    assert payload["matches"][0]["path"] == "wiki/topics/preprocessing.md"


def test_cli_query_command_rejects_unknown_source_filter(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "--source", "src-missing", "brief"])

    assert exit_code == 1
    assert capsys.readouterr().out == "Error: Unknown source ID: src-missing\n"


def test_cli_query_command_persists_last_query_snapshot(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Ship", "query"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "query"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Next: splendor file-answer --from-last-query --title query" in captured.out
    snapshot = load_query_snapshot(tmp_path / "state" / "queries" / "last-query.json")
    assert snapshot.query == "query"
    assert snapshot.match_count == 1


def test_cli_query_command_shell_escapes_file_answer_title_hint(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    write_queryable_wiki_page(
        tmp_path / "wiki" / "topics" / "quoted.md",
        title='Quoted "ranking" note',
        page_id="topic-quoted-ranking",
        body='Quoted "ranking" evidence appears here.\n',
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", 'quoted "ranking"'])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert (
        "Next: splendor file-answer --from-last-query --title 'quoted \"ranking\"'" in captured.out
    )


def test_cli_query_command_persists_snapshot_for_json_output(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Ship", "query"])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "query", "--json"])

    assert exit_code == 0
    snapshot = load_query_snapshot(tmp_path / "state" / "queries" / "last-query.json")
    assert snapshot.query == "query"


def test_cli_query_command_no_save_skips_last_query_snapshot(tmp_path: Path, capsys) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\nproject_name: custom\nlayout:\n  state_dir: custom-state\n",
        encoding="utf-8",
    )
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Ship", "query"])
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "--no-save", "query"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Summary: Found 1 matching records." in captured.out
    assert "Next: rerun without --no-save to enable file-answer" in captured.out
    assert not last_query_path_for(layout).exists()


def test_cli_query_command_no_save_json_preserves_output_shape(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    main(["--root", str(tmp_path), "task", "create", "Ship", "query"])
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "--no-save", "query", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "query"
    assert payload["match_count"] == 1
    assert payload["matches"][0]["path"] == "planning/tasks/task-ship-query.md"
    assert not last_query_path_for(layout).exists()


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


def test_cli_query_command_prints_contradictions_and_review_tasks(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    write_queryable_wiki_page(
        tmp_path / "wiki" / "sources" / "src-123.md",
        title="Generated source summary",
        page_id="src-123",
        contradictions=[
            {
                "contradiction_id": "contradiction-src-123-src-456-1234567890",
                "summary": "The pages disagree about the configured storage mode.",
                "detected_at": "2026-04-22T10:05:00+00:00",
                "related_page_ids": ["src-123", "src-456"],
                "related_source_ids": ["src-123", "src-456"],
                "review_task_id": "task-review-src-123-src-456-1234567890",
                "evidence": [
                    {
                        "page_id": "src-123",
                        "source_id": "src-123",
                        "run_id": "run-123",
                        "path_ref": "wiki/sources/src-123.md",
                        "excerpt": "Storage mode is none.",
                    }
                ],
            }
        ],
        body="# Generated source summary\n\nThis page covers local retrieval.\n",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "query", "generated"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Contradictions: 1" in out
    assert "Review tasks: task-review-src-123-src-456-1234567890" in out


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
    assert "Next: review" in captured.out
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
