import json
from pathlib import Path

import yaml

from splendor.cli import main
from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.schemas import KnowledgePageFrontmatter, MaintenanceReport
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
    out = capsys.readouterr().out
    source_record = load_source_record(
        tmp_path / "state" / "manifests" / "sources" / f"{source_id}.json"
    )
    assert source_record.status == "ingested"
    assert f"Next: splendor wiki suggest {source_id}" in out


def test_pending_ingest_multiple_sources_points_back_to_status(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init"])
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n\nFirst source covers workflow polish.\n", encoding="utf-8")
    second.write_text("# Second\n\nSecond source covers web status.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(first)])
    main(["--root", str(tmp_path), "add-source", str(second)])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Drain summary: processed=2 succeeded=2 failed=0 skipped=0" in out
    assert "Next: splendor wiki status" in out


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
    assert payload["review_needed_pages"] == 1
    assert payload["review_needed_synthesis_pages"] == 0
    assert payload["sources_missing_synthesis"] == 1
    assert payload["invalid_pages"] == 0
    assert payload["recent_runs"][0]["source_ids"] == [added.source_id]


def test_wiki_status_text_output_reports_stable_counts(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "status-note.md"
    source.write_text("# Status note\n\nWiki status text output.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "status"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Wiki status" in out
    assert "Sources: total=1 registered=0 ingested=1 failed=0" in out
    assert "Machine-generated pages: 1" in out
    assert "Review-needed synthesis pages: 0" in out


def test_wiki_status_uninitialized_workspace_reports_empty_state(tmp_path: Path, capsys) -> None:
    exit_code = main(["--root", str(tmp_path), "wiki", "status", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_total"] == 0
    assert payload["page_total"] == 0
    assert payload["queue_total"] == 0
    assert payload["run_total"] == 0


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


def test_wiki_status_counts_all_review_needed_pages_and_synthesis_subset(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "sources" / "src-123.md",
        kind="source-summary",
        title="Generated source summary",
        page_id="src-123",
        review_state="machine-generated",
        source_refs=["src-123"],
        body="Generated source summary.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "draft-topic.md",
        kind="topic",
        title="Draft topic",
        page_id="topic-draft",
        review_state="draft",
        body="Draft synthesis page.",
    )

    exit_code = main(["--root", str(tmp_path), "wiki", "status", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["review_needed_pages"] == 2
    assert payload["review_needed_synthesis_pages"] == 1


def test_wiki_status_treats_canonical_source_ref_mentions_as_synthesis_followup(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "canonical-ref.md"
    source.write_text("# Canonical ref\n\nA source cited by path.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "manual-followup.md",
        kind="topic",
        title="Manual follow-up",
        page_id="topic-manual-followup",
        body="This synthesis cites canonical-ref.md directly.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "status", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sources_missing_synthesis"] == 0


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


def test_wiki_suggest_text_output_reports_top_suggestion(tmp_path: Path, capsys) -> None:
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
        body="This page cites deterministic source-impact suggestions.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "suggest", added.source_id])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Suggested pages:" in out
    assert "wiki/topics/wiki-maintenance.md" in out


def test_wiki_suggest_reports_unknown_source(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)

    exit_code = main(["--root", str(tmp_path), "wiki", "suggest", "src-missing"])

    assert exit_code == 1
    assert "Unknown source ID: src-missing" in capsys.readouterr().out


def test_wiki_suggest_scores_two_character_tags(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "ai-note.md"
    source.write_text("# AI note\n\nShort tags should work.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "ai.md",
        kind="topic",
        title="AI",
        page_id="topic-ai",
        tags=["ai"],
        body="Short tag page.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "suggest", added.source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["suggestions"][0]["path"] == "wiki/topics/ai.md"
    assert "tag-overlap:ai" in payload["suggestions"][0]["reasons"]
    assert "term-overlap:ai" not in payload["suggestions"][0]["reasons"]


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


def test_wiki_suggest_ignores_extract_fence_info_string(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "semantic-impact.md"
    source.write_text(
        "# Semantic impact\n\nThis source explains substantivealpha behavior.\n",
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
        tmp_path / "wiki" / "topics" / "fence-info.md",
        kind="topic",
        title="Fence info",
        page_id="topic-fence-info",
        body="This page only mentions text fences.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "suggest", added.source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    suggestion_paths = [suggestion["path"] for suggestion in payload["suggestions"]]
    assert "wiki/topics/substantive-alpha.md" in suggestion_paths
    assert "wiki/topics/fence-info.md" not in suggestion_paths


def test_wiki_compile_reports_review_gated_contract_without_mutating(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-contract.md"
    source.write_text("# Compile contract\n\nSynthesis remains review-gated.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    page_path = tmp_path / "wiki" / "sources" / f"{added.source_id}.md"
    before = page_path.read_text(encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "compile", added.source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_id"] == added.source_id
    assert payload["mutates"] is False
    assert payload["status"] == "contract-only"
    assert "Run `splendor wiki suggest" in payload["next_steps"][0]
    assert page_path.read_text(encoding="utf-8") == before


def test_wiki_compile_text_reports_review_gated_contract_without_mutating(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-contract.md"
    source.write_text("# Compile contract\n\nSynthesis remains review-gated.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    page_path = tmp_path / "wiki" / "sources" / f"{added.source_id}.md"
    before = page_path.read_text(encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "compile", added.source_id])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"Source: {added.source_id}" in out
    assert "Compile contract" in out
    assert "Mutates wiki: no" in out
    assert "Next steps:" in out
    assert "Run `splendor wiki suggest" in out
    assert page_path.read_text(encoding="utf-8") == before


def test_wiki_compile_reports_unknown_source(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)

    exit_code = main(["--root", str(tmp_path), "wiki", "compile", "src-missing"])

    assert exit_code == 1
    assert "Unknown source ID: src-missing" in capsys.readouterr().out


def test_brief_json_includes_goal_state_matches_planning_and_next_actions(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "briefing.md"
    source.write_text(
        "# Briefing\n\nProject briefing should surface wiki context.\n", encoding="utf-8"
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "project-briefing.md",
        kind="topic",
        title="Project briefing",
        page_id="topic-project-briefing",
        source_refs=[added.source_id],
        body="Project briefing assembles source-backed working context.",
    )
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Continue project briefing",
            "--id",
            "task-briefing",
            "--status",
            "in_progress",
        ]
    )
    report = MaintenanceReport(
        command="lint",
        created_at="2026-04-30T00:00:00Z",
        status="passed",
        checked_count=3,
        issue_count=0,
    )
    report_path = tmp_path / "reports" / "lint" / "20260430T000000Z.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "project", "briefing", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal"] == "project briefing"
    assert payload["status"]["source_total"] == 1
    assert "recent_runs" in payload["status"]
    assert "machine_generated_pages" in payload["status"]
    assert payload["matches"][0]["path"] == "wiki/topics/project-briefing.md"
    assert payload["planning_items"][0]["record_id"] == "task-briefing"
    assert payload["recent_sources"][0]["source_id"] == added.source_id
    assert payload["recent_runs"][0]["source_ids"] == [added.source_id]
    assert payload["latest_reports"] == [
        {
            "command": "lint",
            "status": "passed",
            "created_at": "2026-04-30T00:00:00Z",
            "issue_count": 0,
            "path": "reports/lint/20260430T000000Z.json",
        }
    ]
    assert any("Open the top matching" in action for action in payload["next_actions"])


def test_brief_text_output_is_available_without_goal(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Project brief" in out
    assert "Goal: -" in out
    assert "Next actions:" in out


def test_brief_json_output_is_available_without_goal(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal"] is None
    assert "status" in payload
    assert "latest_reports" in payload
    assert "next_actions" in payload


def test_brief_skips_invalid_query_matches_without_failing(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    bad_page = tmp_path / "wiki" / "topics" / "bad.md"
    bad_page.write_text("---\nkind: topic\nbogus: true\n---\n\n# Bad\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "bad", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query_summary"].startswith("Query skipped:")
    assert payload["matches"] == []
    assert payload["status"]["invalid_pages"] == 1
    assert any("invalid wiki pages" in action for action in payload["next_actions"])


def test_brief_skips_invalid_planning_records_without_failing(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    bad_task = tmp_path / "planning" / "tasks" / "bad.md"
    bad_task.write_text("---\nkind: task\nbogus: true\n---\n\n# Bad\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["planning_items"] == []
    assert payload["warnings"][0]["area"] == "planning"
    assert payload["warnings"][0]["path"] == "planning/tasks/bad.md"
    assert any("skipped planning records" in action for action in payload["next_actions"])


def test_brief_skips_invalid_goal_without_failing(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "???", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goal"] == "???"
    assert payload["query_summary"].startswith("Query skipped:")
    assert payload["matches"] == []
