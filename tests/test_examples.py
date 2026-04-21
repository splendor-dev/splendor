from pathlib import Path

from splendor.cli import main
from splendor.commands.health import run_health_checks
from splendor.commands.lint import run_lint_checks
from splendor.config import load_config
from splendor.layout import required_directories, resolve_layout
from splendor.schemas import TaskRecord
from splendor.state.query_snapshot import load_query_snapshot
from splendor.state.runtime import load_queue_item, load_run_record
from splendor.state.source_registry import load_source_record
from splendor.utils.planning import parse_planning_document
from splendor.utils.wiki import parse_wiki_markdown


def test_documented_quickstart_flow_succeeds_end_to_end(tmp_path: Path, capsys) -> None:
    exit_code = main(["--root", str(tmp_path), "init"])
    assert exit_code == 0

    source = tmp_path / "product-note.md"
    source.write_text(
        (
            "# Product note\n\n"
            "Splendor is a local-first knowledge compiler for code-and-research repositories.\n"
            "The MVP keeps a durable wiki in git.\n"
        ),
        encoding="utf-8",
    )

    exit_code = main(["--root", str(tmp_path), "add-source", str(source)])
    assert exit_code == 0
    capsys.readouterr()

    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_id = manifest_path.stem

    exit_code = main(["--root", str(tmp_path), "ingest", source_id])
    assert exit_code == 0

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Publish MVP docs",
            "--priority",
            "high",
            "--source-ref",
            source_id,
        ]
    )
    assert exit_code == 0

    exit_code = main(["--root", str(tmp_path), "query", "knowledge", "compiler"])
    assert exit_code == 0

    snapshot = load_query_snapshot(tmp_path / "state" / "queries" / "last-query.json")
    assert snapshot.query == "knowledge compiler"
    assert snapshot.match_count >= 1
    assert any(match.record_id == source_id for match in snapshot.matches)

    exit_code = main(["--root", str(tmp_path), "lint"])
    assert exit_code == 0

    exit_code = main(["--root", str(tmp_path), "health"])
    assert exit_code == 0


def test_committed_example_workspace_is_structurally_valid() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    root = repo_root / "examples" / "in-repo-workspace"

    config = load_config(root)
    layout = resolve_layout(root, config)

    for directory in required_directories(layout):
        assert directory.is_dir(), f"missing required directory: {directory}"

    manifest_paths = sorted(layout.source_records_dir.glob("*.json"))
    assert len(manifest_paths) == 1
    source = load_source_record(manifest_paths[0])

    page_path = root / source.linked_pages[0]
    parsed_page = parse_wiki_markdown(page_path)
    assert parsed_page.frontmatter.page_id == source.source_id
    assert parsed_page.frontmatter.source_refs == [source.source_id]
    assert source.last_run_id in parsed_page.frontmatter.generated_by_run_ids

    task_path = layout.planning_dir / "tasks" / "task-publish-mvp-docs.md"
    task = parse_planning_document(task_path, TaskRecord).record
    assert task.source_refs == [source.source_id]

    queue_path = layout.queue_dir / f"ingest-{source.source_id}.json"
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "done"
    assert queue_record.payload_ref == (f"state/manifests/sources/{source.source_id}.json")

    run_path = layout.runs_dir / f"{source.last_run_id}.json"
    run_record = load_run_record(run_path)
    assert run_record.status == "succeeded"
    assert page_path.relative_to(root).as_posix() in run_record.output_refs

    lint_result = run_lint_checks(root, layout)
    assert lint_result.issues == []

    health_result = run_health_checks(root, layout)
    assert health_result.issues == []
