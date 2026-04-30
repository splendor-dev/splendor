import json
from pathlib import Path

import yaml

from splendor.cli import main
from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.schemas import KnowledgePageFrontmatter
from splendor.state.source_registry import load_source_record


def write_wiki_page(
    path: Path,
    *,
    kind: str,
    title: str,
    page_id: str,
    review_state: str = "draft",
    source_refs: list[str] | None = None,
    tags: list[str] | None = None,
    body: str = "",
) -> None:
    frontmatter = KnowledgePageFrontmatter(
        kind=kind,
        title=title,
        page_id=page_id,
        status="active",
        review_state=review_state,
        source_refs=source_refs or [],
        tags=tags or [],
        confidence=0.8,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    path.write_text(f"---\n{frontmatter_text}\n---\n\n{body}", encoding="utf-8")


def test_add_source_queues_pending_ingest_for_cli_handoff(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nThis source covers wiki maintenance.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "add-source", str(source)])

    assert exit_code == 0
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    queue_path = tmp_path / "state" / "queue" / f"ingest-{source_id}.json"
    assert queue_path.exists()
    out = capsys.readouterr().out
    assert "Queued ingest:" in out
    assert "Next: splendor ingest --pending" in out

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending"])

    assert exit_code == 0
    source_record = load_source_record(
        tmp_path / "state" / "manifests" / "sources" / f"{source_id}.json"
    )
    assert source_record.status == "ingested"


def test_add_source_reports_warning_when_queue_handoff_fails(tmp_path: Path, capsys) -> None:
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nThis source is registered before init.\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "add-source", str(source)])

    assert exit_code == 0
    source_id = next((tmp_path / "state" / "manifests" / "sources").glob("*.json")).stem
    assert not (tmp_path / "state" / "queue" / f"ingest-{source_id}.json").exists()
    out = capsys.readouterr().out
    assert f"Registered source {source_id}" in out
    assert "Warning: source registered but ingest was not queued:" in out
    assert "Next: splendor init" in out
    assert f"Then: splendor ingest {source_id}" in out


def test_wiki_status_reports_state_counts(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "status-note.md"
    source.write_text(
        "# Status note\n\nWiki status should find missing synthesis.\n", encoding="utf-8"
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "status", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_counts"]["ingested"] == 1
    assert payload["page_kind_counts"]["source-summary"] == 1
    assert payload["queue_status_counts"]["done"] == 1
    assert payload["run_status_counts"]["succeeded"] == 1
    assert payload["machine_generated_pages"] == 1
    assert payload["review_needed_pages"] == 0
    assert payload["review_needed_synthesis_pages"] == 0
    assert payload["sources_missing_synthesis"] == 1
    assert payload["invalid_pages"] == 0
    assert payload["recent_runs"][0]["source_ids"] == [added.source_id]


def test_wiki_status_reports_invalid_pages_without_failing(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    bad_page = tmp_path / "wiki" / "topics" / "bad.md"
    bad_page.write_text("---\nkind: topic\nbogus: true\n---\n\n# Bad\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "wiki", "status", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["page_total"] == 0
    assert payload["invalid_pages"] == 1
    assert payload["invalid_page_examples"][0]["path"] == "wiki/topics/bad.md"
    assert "failed schema validation" in payload["invalid_page_examples"][0]["error"]


def test_wiki_suggest_ranks_source_impact_pages(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "wiki-maintenance.md"
    source.write_text(
        "# Wiki maintenance\n\nThis source explains deterministic wiki suggest workflows.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "wiki-maintenance.md",
        kind="topic",
        title="Wiki maintenance workflow",
        page_id="topic-wiki-maintenance",
        source_refs=[added.source_id],
        tags=["wiki", "maintenance"],
        body="This page cites deterministic source-impact suggestions.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "architecture" / "unrelated.md",
        kind="architecture",
        title="Storage layout",
        page_id="architecture-storage-layout",
        body="This page covers raw artifact storage.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "suggest", added.source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_id"] == added.source_id
    assert payload["suggestions"][0]["path"] == "wiki/topics/wiki-maintenance.md"
    assert "frontmatter-source-ref" in payload["suggestions"][0]["reasons"]
    assert all(
        suggestion["path"] != "wiki/architecture/unrelated.md"
        for suggestion in payload["suggestions"]
    )


def test_wiki_suggest_ignores_source_summary_boilerplate_terms(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "semantic-impact.md"
    source.write_text(
        "# Semantic impact\n\nThis source explains substantivealpha maintenance behavior.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "substantive-alpha.md",
        kind="topic",
        title="Substantive alpha",
        page_id="topic-substantive-alpha",
        body="This page discusses substantivealpha behavior.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "generated-boilerplate.md",
        kind="topic",
        title="Generated boilerplate",
        page_id="topic-generated-boilerplate",
        body="This page only mentions checksum provenance pipeline version and run id.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "suggest", added.source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    suggestion_paths = [suggestion["path"] for suggestion in payload["suggestions"]]
    assert "wiki/topics/substantive-alpha.md" in suggestion_paths
    assert "wiki/topics/generated-boilerplate.md" not in suggestion_paths
