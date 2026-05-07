import json
import os
import subprocess
from pathlib import Path

import yaml

import splendor.commands.wiki as wiki_module
from splendor.cli import main
from splendor.commands import brief as brief_module
from splendor.commands.add_source import add_source
from splendor.commands.ingest import enqueue_ingest_job
from splendor.commands.init import initialize_workspace
from splendor.commands.wiki import add_topic_page, rebuild_wiki_index
from splendor.config import AuthorityDocumentConfig, load_config, write_config
from splendor.schemas import KnowledgePageFrontmatter, MaintenanceReport, TaskRecord
from splendor.state.runtime import load_queue_item, write_queue_item
from splendor.state.source_registry import load_source_record
from splendor.utils.planning import render_planning_markdown
from splendor.utils.wiki import parse_wiki_markdown


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _init_git_repo(root: Path, *, repo: str = "example/project") -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    _git(root, "remote", "add", "origin", f"git@github.com:{repo}.git")


def _commit_all(root: Path, message: str) -> None:
    _git(root, "add", ".")
    _git(root, "commit", "-m", message)


def _install_fake_gh(
    tmp_path: Path,
    monkeypatch,
    *,
    issues: list[dict[str, object]],
    prs: list[dict[str, object]],
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "gh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        f"issues = {issues!r}\n"
        f"prs = {prs!r}\n"
        "if sys.argv[1:3] == ['issue', 'list']:\n"
        "    print(json.dumps(issues))\n"
        "elif sys.argv[1:3] == ['pr', 'list']:\n"
        "    print(json.dumps(prs))\n"
        "else:\n"
        "    print('unsupported fake gh call', file=sys.stderr)\n"
        "    sys.exit(2)\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")


def _install_marker_gh(tmp_path: Path, monkeypatch, *, sleep_seconds: float = 0) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    marker = tmp_path / "gh-called"
    script = bin_dir / "gh"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "import time\n"
        f"time.sleep({sleep_seconds!r})\n"
        f"pathlib.Path({str(marker)!r}).write_text('called', encoding='utf-8')\n"
        "print('[]')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    return marker


def write_wiki_page(
    path: Path,
    *,
    kind: str,
    title: str,
    page_id: str,
    review_state: str = "draft",
    source_refs: list[str] | None = None,
    tags: list[str] | None = None,
    authority_role: str | None = None,
    authority_freshness: str | None = None,
    authority_lifecycle: str | None = None,
    authority_scope: list[str] | None = None,
    issue_refs: list[str] | None = None,
    pr_refs: list[str] | None = None,
    supersedes: list[str] | None = None,
    superseded_by: str | None = None,
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
        authority_role=authority_role,
        authority_freshness=authority_freshness,
        authority_lifecycle=authority_lifecycle,
        authority_scope=authority_scope or [],
        issue_refs=issue_refs or [],
        pr_refs=pr_refs or [],
        supersedes=supersedes or [],
        superseded_by=superseded_by,
        confidence=0.8,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    path.write_text(f"---\n{frontmatter_text}\n---\n\n{body}", encoding="utf-8")


def test_add_topic_scaffolds_valid_frontmatter_and_rebuilds_index(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source_a = tmp_path / "source-a.md"
    source_b = tmp_path / "source-b.md"
    source_a.write_text("# Source A\n", encoding="utf-8")
    source_b.write_text("# Source B\n", encoding="utf-8")
    added_a = add_source(tmp_path, source_a)
    added_b = add_source(tmp_path, source_b)

    result = add_topic_page(
        tmp_path,
        "Preprocessing Pipeline",
        tags=["preprocessing", "audio", "preprocessing"],
        source_refs=[added_a.source_id, added_b.source_id, added_a.source_id],
        template="research-synthesis",
    )

    assert result.path == "wiki/topics/preprocessing-pipeline.md"
    assert result.page_id == "topic-preprocessing-pipeline"
    assert result.tags == ["preprocessing", "audio"]
    assert result.source_refs == [added_a.source_id, added_b.source_id]
    page = parse_wiki_markdown(tmp_path / result.path)
    assert page.frontmatter.kind == "topic"
    assert page.frontmatter.title == "Preprocessing Pipeline"
    assert page.frontmatter.page_id == "topic-preprocessing-pipeline"
    assert page.frontmatter.status == "active"
    assert page.frontmatter.review_state == "draft"
    assert page.frontmatter.source_refs == [added_a.source_id, added_b.source_id]
    assert "## Source-Backed Findings" in page.body
    index = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert (
        "- [Preprocessing Pipeline](topics/preprocessing-pipeline.md) "
        "(`topic-preprocessing-pipeline`) status=active review=draft"
    ) in index


def test_add_topic_cli_supports_issue_tracker_template_and_json(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "quality.md"
    source.write_text("# Quality\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "add-topic",
            "Audio Quality Issues",
            "--tags",
            "audio,quality",
            "--source-refs",
            added.source_id,
            "--template",
            "issue-tracker",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] == "wiki/topics/audio-quality-issues.md"
    assert payload["page_id"] == "topic-audio-quality-issues"
    assert payload["source_refs"] == [added.source_id]
    assert payload["template"] == "issue-tracker"
    page = parse_wiki_markdown(tmp_path / payload["path"])
    assert "| Issue | Severity | Symptoms | Root Cause | Status | Source Refs |" in page.body


def test_add_topic_rejects_duplicate_slug_without_mutating_index(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    add_topic_page(tmp_path, "Preprocessing Pipeline")
    index_before = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "add-topic", "Preprocessing Pipeline"])

    assert exit_code == 1
    assert "Error: Topic page already exists: wiki/topics/preprocessing-pipeline.md" in (
        capsys.readouterr().out
    )
    assert (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8") == index_before


def test_add_topic_rejects_unknown_source_ref_without_mutating_wiki(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    index_before = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "add-topic",
            "Bogus Ref",
            "--source-refs",
            "src-missing",
        ]
    )

    assert exit_code == 1
    assert "Error: Unknown source ref for topic page: src-missing" in capsys.readouterr().out
    assert not (tmp_path / "wiki" / "topics" / "bogus-ref.md").exists()
    assert (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8") == index_before


def test_add_topic_rejects_uninitialized_workspace_without_partial_writes(
    tmp_path: Path, capsys
) -> None:
    exit_code = main(["--root", str(tmp_path), "add-topic", "No Init"])

    assert exit_code == 1
    assert (
        "Error: Workspace is missing required wiki files: "
        "wiki/index.md, wiki/log.md. Run `splendor init`."
    ) in capsys.readouterr().out
    assert not (tmp_path / "wiki" / "index.md").exists()
    assert not (tmp_path / "wiki" / "topics" / "no-init.md").exists()


def test_rebuild_wiki_index_includes_pages_in_deterministic_sections(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "zeta.md",
        kind="topic",
        title="Zeta Topic",
        page_id="topic-zeta",
        review_state="draft",
    )
    write_wiki_page(
        tmp_path / "wiki" / "architecture" / "alpha.md",
        kind="architecture",
        title="Alpha Architecture",
        page_id="architecture-alpha",
        review_state="machine-generated",
    )
    write_wiki_page(
        tmp_path / "wiki" / "sources" / "src-a.md",
        kind="source-summary",
        title="Source A",
        page_id="source-src-a",
        review_state="machine-generated",
        source_refs=["src-a"],
    )
    (tmp_path / "wiki" / "index.md").write_text("# Drifted\n", encoding="utf-8")

    result = rebuild_wiki_index(tmp_path)
    first_index = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    second_result = rebuild_wiki_index(tmp_path)
    second_index = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")

    assert result.page_count == 3
    assert result.sections == {"architecture": 1, "topic": 1, "source-summary": 1}
    assert second_result == result
    assert second_index == first_index
    assert first_index.index("## Architecture") < first_index.index("## Topics")
    assert first_index.index("## Topics") < first_index.index("## Sources")
    assert "[Alpha Architecture](architecture/alpha.md)" in first_index
    assert "[Zeta Topic](topics/zeta.md)" in first_index
    assert "[Source A](sources/src-a.md)" in first_index


def test_rebuild_wiki_index_loads_pages_once(tmp_path: Path, monkeypatch) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "zeta.md",
        kind="topic",
        title="Zeta Topic",
        page_id="topic-zeta",
    )
    load_calls = 0
    original_load_wiki_pages = wiki_module.load_wiki_pages

    def counted_load_wiki_pages(*args, **kwargs):
        nonlocal load_calls
        load_calls += 1
        return original_load_wiki_pages(*args, **kwargs)

    monkeypatch.setattr(wiki_module, "load_wiki_pages", counted_load_wiki_pages)

    result = rebuild_wiki_index(tmp_path)

    assert result.page_count == 1
    assert load_calls == 1
    assert "[Zeta Topic](topics/zeta.md)" in (tmp_path / "wiki" / "index.md").read_text(
        encoding="utf-8"
    )


def test_wiki_rebuild_index_cli_reports_invalid_frontmatter(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    bad_page = tmp_path / "wiki" / "topics" / "bad.md"
    bad_page.write_text("---\nkind: topic\nbogus: true\n---\n\n# Bad\n", encoding="utf-8")

    exit_code = main(["--root", str(tmp_path), "wiki", "rebuild-index"])

    assert exit_code == 1
    assert "Error: Cannot rebuild index with invalid wiki pages present: wiki/topics/bad.md" in (
        capsys.readouterr().out
    )


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

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending", "--apply"])

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

    exit_code = main(["--root", str(tmp_path), "ingest", "--pending", "--apply"])

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
    assert "Review-needed pages: 1" in out
    assert "Review-needed synthesis pages: 0" in out
    assert "Sources missing synthesis follow-up: 1" in out
    assert "review-needed wiki state is maintenance state" in out
    assert "splendor wiki suggest <source-id>" in out


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
    assert (
        payload["suggestions"][0]["compile_preview_command"]
        == f"splendor wiki compile {added.source_id} --page wiki/topics/wiki-maintenance.md"
    )
    assert payload["suggestions"][0]["compile_preview_args"] == [
        "splendor",
        "wiki",
        "compile",
        added.source_id,
        "--page",
        "wiki/topics/wiki-maintenance.md",
    ]
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

    exit_code = main(["--root", str(tmp_path), "wiki", "suggest", "wiki-maintenance.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Source ref: wiki-maintenance.md" in out
    assert f"Source ID: {added.source_id}" in out
    assert "Suggested pages:" in out
    assert "wiki/topics/wiki-maintenance.md" in out
    assert (
        f"Compile preview: splendor wiki compile {added.source_id} "
        "--page wiki/topics/wiki-maintenance.md"
    ) in out


def test_wiki_suggest_path_includes_all_versions_for_that_path(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "docs" / "wiki-maintenance.md"
    source.parent.mkdir()
    source.write_text("# Wiki maintenance\n\nOriginal source version.\n", encoding="utf-8")
    original = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", original.source_id])
    source.write_text("# Wiki maintenance\n\nUpdated source version.\n", encoding="utf-8")
    updated = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", updated.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "original.md",
        kind="topic",
        title="Original maintenance",
        page_id="topic-original-maintenance",
        source_refs=[original.source_id],
        body="Original source-impact suggestions.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "updated.md",
        kind="topic",
        title="Updated maintenance",
        page_id="topic-updated-maintenance",
        source_refs=[updated.source_id],
        body="Updated source-impact suggestions.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "suggest", "docs/wiki-maintenance.md"])

    assert exit_code == 0
    out = capsys.readouterr().out
    resolved_line = next(
        line for line in out.splitlines() if line.startswith("Resolved source IDs:")
    )
    assert updated.source_id in resolved_line
    assert original.source_id in resolved_line
    assert "wiki/topics/original.md" in out
    assert "wiki/topics/updated.md" in out


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
    assert payload["mutation"] == {
        "mode": "preview",
        "mutates": False,
        "planned": [],
        "written": [],
    }
    assert payload["suggested_pages"] == []
    assert "Run `splendor wiki suggest" in payload["next_steps"][0]
    assert (
        "Create or choose one maintained topic, concept, entity, architecture, or glossary page"
        in payload["next_steps"][1]
    )
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
    assert "Source ref: compile-contract.md" in out
    assert f"Source ID: {added.source_id}" in out
    assert "Compile contract" in out
    assert "Mutates wiki: no" in out
    assert "Suggested compile targets: none" in out
    assert "Next steps:" in out
    assert "Run `splendor wiki suggest" in out
    assert "Create or choose one maintained topic" in out
    assert page_path.read_text(encoding="utf-8") == before


def test_wiki_compile_contract_includes_suggested_page_preview_commands(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-contract.md"
    source.write_text(
        "# Compile contract\n\nSynthesis remains review-gated for wiki maintenance.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile contract.md",
        kind="topic",
        title="Compile contract",
        page_id="topic-compile-contract",
        source_refs=[added.source_id],
        body="Maintained compile contract synthesis.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "wiki", "compile", added.source_id, "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mutates"] is False
    assert payload["suggested_pages"][0]["path"] == "wiki/topics/compile contract.md"
    assert (
        payload["suggested_pages"][0]["compile_preview_command"]
        == f"splendor wiki compile {added.source_id} --page 'wiki/topics/compile contract.md'"
    )
    assert payload["suggested_pages"][0]["compile_preview_args"] == [
        "splendor",
        "wiki",
        "compile",
        added.source_id,
        "--page",
        "wiki/topics/compile contract.md",
    ]
    assert (
        f"Preview `splendor wiki compile {added.source_id} "
        "--page 'wiki/topics/compile contract.md'`."
    ) in payload["next_steps"]

    exit_code = main(["--root", str(tmp_path), "wiki", "compile", added.source_id])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Suggested compile targets:" in out
    assert "wiki/topics/compile contract.md [topic]" in out
    assert (
        f"Compile preview: splendor wiki compile {added.source_id} "
        "--page 'wiki/topics/compile contract.md'"
    ) in out


def test_wiki_compile_reports_unknown_source(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)

    exit_code = main(["--root", str(tmp_path), "wiki", "compile", "src-missing"])

    assert exit_code == 1
    assert "Unknown source ID: src-missing" in capsys.readouterr().out


def test_wiki_compile_proposes_maintained_page_update_without_mutating(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text(
        "# Compile loop\n\n"
        "## Summary\n\n"
        "Reviewed compile turns source evidence into maintained synthesis.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body="# Compile loop\n\n## Summary\n\nExisting synthesis.\n",
    )
    target_path = tmp_path / "wiki" / "topics" / "compile-loop.md"
    before = target_path.read_text(encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "wiki/topics/compile-loop.md",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "proposed"
    assert payload["mode"] == "preview"
    assert payload["mutates"] is False
    assert payload["changed"] is True
    assert payload["mutation"] == {
        "mode": "preview",
        "mutates": False,
        "planned": [
            {
                "action": "write",
                "path": "wiki/topics/compile-loop.md",
                "kind": "maintained_wiki_page",
                "source_id": added.source_id,
            }
        ],
        "written": [],
    }
    assert payload["target_path"] == "wiki/topics/compile-loop.md"
    assert payload["source_summary_path"] == f"wiki/sources/{added.source_id}.md"
    assert added.source_id in payload["proposed_source_refs"]
    assert payload["target_sha256"]
    assert payload["source_summary_sha256"]
    assert payload["proposal_hash"]
    assert "--- wiki/topics/compile-loop.md" in payload["proposed_diff"]
    assert "+++ wiki/topics/compile-loop.md (proposed)" in payload["proposed_diff"]
    assert "<!-- splendor-compile:start" in payload["proposed_markdown"]
    assert "## Compiled Source Evidence" in payload["proposed_markdown"]
    assert "Reviewed compile turns source evidence" in payload["proposed_markdown"]
    assert target_path.read_text(encoding="utf-8") == before


def test_wiki_compile_text_proposal_prints_reviewable_diff_and_hash(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text(
        "# Compile loop\n\n## Summary\n\nText output must be reviewable before apply.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body="# Compile loop\n\n## Summary\n\nExisting synthesis.\n",
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "wiki/topics/compile-loop.md",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Target SHA-256:" in out
    assert "Mutation mode: preview" in out
    assert "Preview only: no wiki pages written." in out
    assert "Source summary SHA-256:" in out
    assert "Proposal hash:" in out
    assert "Proposed diff:" in out
    assert "--- wiki/topics/compile-loop.md" in out
    assert "+++ wiki/topics/compile-loop.md (proposed)" in out
    assert "--apply --proposal-hash" in out


def test_wiki_compile_apply_updates_only_maintained_target_page(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text(
        "# Compile loop\n\n## Summary\n\nCompile apply records evidence with source provenance.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    source_summary_path = tmp_path / "wiki" / "sources" / f"{added.source_id}.md"
    source_summary_before = source_summary_path.read_text(encoding="utf-8")
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body="# Compile loop\n\n## Summary\n\nExisting synthesis.\n",
    )
    capsys.readouterr()

    preview_exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
            "--json",
        ]
    )

    assert preview_exit_code == 0
    preview_payload = json.loads(capsys.readouterr().out)

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
            "--apply",
            "--proposal-hash",
            preview_payload["proposal_hash"],
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "applied"
    assert payload["mode"] == "apply"
    assert payload["mutates"] is True
    assert payload["mutation"] == {
        "mode": "apply",
        "mutates": True,
        "planned": [],
        "written": [
            {
                "action": "write",
                "path": "wiki/topics/compile-loop.md",
                "kind": "maintained_wiki_page",
                "source_id": added.source_id,
            }
        ],
    }
    target = parse_wiki_markdown(tmp_path / "wiki" / "topics" / "compile-loop.md")
    assert target.frontmatter.kind == "topic"
    assert target.frontmatter.source_refs == [added.source_id]
    assert [link.source_id for link in target.frontmatter.provenance_links if link.source_id] == [
        added.source_id
    ]
    assert "## Compiled Source Evidence" in target.body
    assert "### compile loop" in target.body
    assert "Compile apply records evidence" in target.body
    assert source_summary_path.read_text(encoding="utf-8") == source_summary_before

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "no-op"
    assert payload["mode"] == "preview"
    assert payload["mutates"] is False
    assert payload["mutation"] == {
        "mode": "preview",
        "mutates": False,
        "planned": [],
        "written": [],
    }


def test_wiki_compile_inserts_additional_sources_inside_managed_section(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    source_a = tmp_path / "compile-loop-a.md"
    source_b = tmp_path / "compile-loop-b.md"
    source_a.write_text(
        "# Compile loop A\n\n## Summary\n\nFirst accepted evidence.\n", encoding="utf-8"
    )
    source_b.write_text(
        "# Compile loop B\n\n## Summary\n\nSecond accepted evidence.\n", encoding="utf-8"
    )
    added_a = add_source(tmp_path, source_a)
    added_b = add_source(tmp_path, source_b)
    main(["--root", str(tmp_path), "ingest", added_a.source_id])
    main(["--root", str(tmp_path), "ingest", added_b.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body=(
            "# Compile loop\n\n"
            "## Summary\n\n"
            "Existing synthesis.\n\n"
            "## Compiled Source Evidence\n\n"
            "This managed section records reviewed source-summary evidence accepted into this "
            "maintained page.\n\n"
            "## Later Section\n\n"
            "Keep me last.\n"
        ),
    )
    capsys.readouterr()

    for added in (added_a, added_b):
        main(
            [
                "--root",
                str(tmp_path),
                "wiki",
                "compile",
                added.source_id,
                "--page",
                "topic-compile-loop",
                "--json",
            ]
        )
        proposal = json.loads(capsys.readouterr().out)
        exit_code = main(
            [
                "--root",
                str(tmp_path),
                "wiki",
                "compile",
                added.source_id,
                "--page",
                "topic-compile-loop",
                "--apply",
                "--proposal-hash",
                proposal["proposal_hash"],
            ]
        )
        assert exit_code == 0
        capsys.readouterr()

    body = parse_wiki_markdown(tmp_path / "wiki" / "topics" / "compile-loop.md").body
    managed_section = body.split("## Compiled Source Evidence", maxsplit=1)[1].split(
        "## Later Section", maxsplit=1
    )[0]
    assert "First accepted evidence." in managed_section
    assert "Second accepted evidence." in managed_section
    assert body.rstrip().endswith("Keep me last.")


def test_wiki_compile_apply_rejects_stale_proposal_hash(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text(
        "# Compile loop\n\n## Summary\n\nCompile apply needs a fresh proposal.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    target_path = tmp_path / "wiki" / "topics" / "compile-loop.md"
    write_wiki_page(
        target_path,
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body="# Compile loop\n\n## Summary\n\nExisting synthesis.\n",
    )
    capsys.readouterr()
    main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
            "--json",
        ]
    )
    preview_payload = json.loads(capsys.readouterr().out)
    target_path.write_text(
        target_path.read_text(encoding="utf-8") + "\nManual reviewer edit.\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
            "--apply",
            "--proposal-hash",
            preview_payload["proposal_hash"],
        ]
    )

    assert exit_code == 1
    assert "requires the proposal hash from the reviewed preview" in capsys.readouterr().out


def test_wiki_compile_rejects_invalid_wiki_pages(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text(
        "# Compile loop\n\n## Summary\n\nCannot compile with invalid pages.\n", encoding="utf-8"
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body="# Compile loop\n\n## Summary\n\nExisting synthesis.\n",
    )
    (tmp_path / "wiki" / "topics" / "broken.md").write_text("not frontmatter", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
        ]
    )

    assert exit_code == 1
    assert "Cannot compile with invalid wiki pages present" in capsys.readouterr().out


def test_wiki_compile_rejects_source_without_summary_page(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text("# Compile loop\n\nRegistered but not ingested.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body="# Compile loop\n\n## Summary\n\nExisting synthesis.\n",
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
        ]
    )

    assert exit_code == 1
    assert "Source has no generated source-summary page yet" in capsys.readouterr().out


def test_wiki_compile_rejects_unknown_absolute_and_ambiguous_targets(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text(
        "# Compile loop\n\n## Summary\n\nTarget resolution must be exact.\n", encoding="utf-8"
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop-a.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop-a",
        body="# Compile loop\n",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop-b.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop-b",
        body="# Compile loop\n",
    )
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "wiki", "compile", added.source_id, "--page", "missing"]
    )
    assert exit_code == 1
    assert "Unknown compile target page: missing" in capsys.readouterr().out

    outside = tmp_path.parent / "outside-compile-target.md"
    outside.write_text("---\nkind: topic\n---\n", encoding="utf-8")
    exit_code = main(
        ["--root", str(tmp_path), "wiki", "compile", added.source_id, "--page", str(outside)]
    )
    assert exit_code == 1
    assert "Compile target must be inside the workspace" in capsys.readouterr().out

    exit_code = main(
        ["--root", str(tmp_path), "wiki", "compile", added.source_id, "--page", "Compile loop"]
    )
    assert exit_code == 1
    assert "Ambiguous compile target: Compile loop" in capsys.readouterr().out


def test_wiki_compile_rejects_duplicate_source_summary_pages(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text(
        "# Compile loop\n\n## Summary\n\nDuplicate summaries should fail.\n", encoding="utf-8"
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body="# Compile loop\n\n## Summary\n\nExisting synthesis.\n",
    )
    write_wiki_page(
        tmp_path / "wiki" / "sources" / "duplicate-summary.md",
        kind="source-summary",
        title="Duplicate summary",
        page_id="duplicate-summary",
        source_refs=[added.source_id],
        body="# Duplicate summary\n\n## Summary\n\nDuplicate evidence.\n",
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
        ]
    )

    assert exit_code == 1
    assert "Source has multiple source-summary pages" in capsys.readouterr().out


def test_wiki_compile_skips_fenced_extract_contents(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text("# Compile loop\n\n```python\nprint('raw code')\n```\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    summary_path = tmp_path / "wiki" / "sources" / f"{added.source_id}.md"
    summary = parse_wiki_markdown(summary_path)
    summary_frontmatter = yaml.safe_dump(
        summary.frontmatter.model_dump(mode="json"), sort_keys=False
    ).strip()
    summary_path.write_text(
        f"---\n{summary_frontmatter}\n"
        "---\n\n"
        f"# {summary.frontmatter.title}\n\n"
        "## Extract\n\n"
        "```text\n"
        "raw code should not become evidence\n"
        "```\n",
        encoding="utf-8",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "compile-loop.md",
        kind="topic",
        title="Compile loop",
        page_id="topic-compile-loop",
        body="# Compile loop\n\n## Summary\n\nExisting synthesis.\n",
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
        ]
    )

    assert exit_code == 1
    assert "Source summary has no deterministic evidence lines" in capsys.readouterr().out


def test_wiki_compile_rejects_generated_source_summary_target(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text("# Compile loop\n\nSynthesis belongs elsewhere.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            f"wiki/sources/{added.source_id}.md",
        ]
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Compile target must be a maintained synthesis page" in out
    assert "source-summary" in out


def test_wiki_compile_apply_requires_page(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)

    exit_code = main(["--root", str(tmp_path), "wiki", "compile", "src-missing", "--apply"])

    assert exit_code == 1
    assert "wiki compile --apply requires --page" in capsys.readouterr().out


def test_wiki_compile_apply_requires_proposal_hash(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "compile-loop.md"
    source.write_text("# Compile loop\n\nSynthesis belongs elsewhere.\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "wiki",
            "compile",
            added.source_id,
            "--page",
            "topic-compile-loop",
            "--apply",
        ]
    )

    assert exit_code == 1
    assert "wiki compile --apply requires --proposal-hash" in capsys.readouterr().out


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


def test_brief_agent_context_json_packages_handoff_state(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.reviews.contradictions.enabled = False
    write_config(tmp_path, config)
    source = tmp_path / "briefing.md"
    unrelated_source = tmp_path / "unrelated.md"
    source.write_text(
        "# Briefing\n\nAgent context should include source-backed handoff state.",
        encoding="utf-8",
    )
    unrelated_source.write_text("# Unrelated\n\nRecent but irrelevant source.", encoding="utf-8")
    added = add_source(tmp_path, source)
    unrelated = add_source(tmp_path, unrelated_source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    main(["--root", str(tmp_path), "ingest", unrelated.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "agent-context.md",
        kind="topic",
        title="Agent context",
        page_id="topic-agent-context",
        source_refs=[added.source_id],
        body="Agent context packages query matches and planning state.",
    )
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Continue agent context",
            "--id",
            "task-agent-context",
            "--status",
            "in_progress",
        ]
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "agent",
            "context",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent_context"] is True
    assert payload["goal"] == "agent context"
    assert payload["wiki_status"]["source_total"] == 2
    assert payload["source_refs"] == [added.source_id]
    assert unrelated.source_id not in payload["source_refs"]
    assert any(match["path"] == "wiki/topics/agent-context.md" for match in payload["matches"])
    assert payload["suggested_actions"]
    assert payload["suggested_actions"][0]["category"] in {
        "goal-match",
        "planning",
        "synthesis",
        "wiki-review",
    }
    assert payload["active_planning"][0]["record_id"] == "task-agent-context"
    assert any(run["source_ids"] == [added.source_id] for run in payload["recent_runs"])
    assert payload["next_actions"]


def test_brief_agent_context_text_output_is_compact(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "--agent-context"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Agent context" in out
    assert "Suggested next:" in out
    assert "Splendor maintenance:" in out
    assert "Next actions:" in out


def test_brief_agent_context_ranks_configured_authority_docs(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "README.md").write_text(
        "# Project README\n\nAuthority for current agent handoff workflow.\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "roadmap.md").write_text(
        "# Roadmap\n\nRoadmap for future agent handoff work.\n", encoding="utf-8"
    )
    (docs / "old-review.md").write_text(
        "# Old Review\n\nHistorical agent handoff review.\n", encoding="utf-8"
    )
    config = load_config(tmp_path)
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="docs/old-review.md",
            role="historical-review",
            freshness="historical",
            purpose="Older review context.",
            applies_to=["agent handoff"],
        ),
        AuthorityDocumentConfig(
            path="README.md",
            role="current-authority",
            freshness="current",
            purpose="Current project entrypoint.",
            applies_to=["agent handoff"],
        ),
        AuthorityDocumentConfig(
            path="docs/roadmap.md",
            role="roadmap",
            freshness="current",
            purpose="Planned future work.",
            applies_to=["agent handoff"],
        ),
    ]
    write_config(tmp_path, config)
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "brief", "--agent-context", "agent", "handoff", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    authority = payload["authority_briefs"]
    assert [item["path"] for item in authority[:3]] == [
        "README.md",
        "docs/roadmap.md",
        "docs/old-review.md",
    ]
    assert authority[0]["role"] == "current-authority"
    authority_actions = [
        action for action in payload["suggested_actions"] if action["category"] == "authority"
    ]
    assert authority_actions
    assert authority_actions[0]["path"] == "README.md"


def test_brief_agent_context_ranks_authority_lifecycle_and_links(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "current.md").write_text("# Current\n\nCurrent planning authority.\n", encoding="utf-8")
    (docs / "reviewed.md").write_text(
        "# Reviewed\n\nReviewed planning authority.\n", encoding="utf-8"
    )
    (docs / "pr.md").write_text("# PR Linked\n\nPR-linked planning authority.\n", encoding="utf-8")
    (docs / "superseded.md").write_text(
        "# Superseded\n\nSuperseded planning authority.\n", encoding="utf-8"
    )
    (docs / "archived.md").write_text(
        "# Archived\n\nArchived planning authority.\n", encoding="utf-8"
    )
    config = load_config(tmp_path)
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="docs/superseded.md",
            role="current-authority",
            authority_lifecycle="superseded",
            superseded_by="docs/current.md",
            applies_to=["planning authority"],
        ),
        AuthorityDocumentConfig(
            path="docs/archived.md",
            role="current-authority",
            authority_lifecycle="archived",
            applies_to=["planning authority"],
        ),
        AuthorityDocumentConfig(
            path="docs/pr.md",
            role="current-authority",
            authority_lifecycle="pr-linked",
            issue_refs=["#116"],
            pr_refs=["#132"],
            applies_to=["planning authority"],
        ),
        AuthorityDocumentConfig(
            path="docs/reviewed.md",
            role="current-authority",
            authority_lifecycle="reviewed",
            applies_to=["planning authority"],
        ),
        AuthorityDocumentConfig(
            path="docs/current.md",
            role="current-authority",
            authority_lifecycle="current",
            applies_to=["planning authority"],
        ),
    ]
    write_config(tmp_path, config)
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "brief", "--agent-context", "planning", "authority", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    authority = payload["authority_briefs"]
    assert [item["path"] for item in authority[:5]] == [
        "docs/current.md",
        "docs/reviewed.md",
        "docs/pr.md",
        "docs/superseded.md",
        "docs/archived.md",
    ]
    assert authority[2]["lifecycle"] == "pr-linked"
    assert authority[2]["issue_refs"] == ["#116"]
    assert authority[2]["pr_refs"] == ["#132"]
    assert authority[3]["superseded_by"] == "docs/current.md"


def test_brief_agent_context_treats_lifecycle_as_precedence_tier(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "current.md").write_text("# Current\n\nStill authoritative.\n", encoding="utf-8")
    (docs / "archived.md").write_text(
        "# Archived\n\nalpha beta gamma delta epsilon zeta.\n", encoding="utf-8"
    )
    config = load_config(tmp_path)
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="docs/archived.md",
            role="current-authority",
            authority_lifecycle="archived",
            applies_to=["alpha", "beta", "gamma", "delta", "epsilon", "zeta"],
        ),
        AuthorityDocumentConfig(
            path="docs/current.md",
            role="current-authority",
            authority_lifecycle="current",
        ),
    ]
    write_config(tmp_path, config)
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "alpha",
            "beta",
            "gamma",
            "delta",
            "epsilon",
            "zeta",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["path"] for item in payload["authority_briefs"][:2]] == [
        "docs/current.md",
        "docs/archived.md",
    ]
    assert payload["authority_briefs"][1]["score"] > payload["authority_briefs"][0]["score"]


def test_brief_agent_context_keeps_stale_freshness_separate_from_supersession(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "stale.md").write_text("# Stale\n\nNeeds review.\n", encoding="utf-8")
    config = load_config(tmp_path)
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="stale.md",
            role="current-authority",
            freshness="stale",
        )
    ]
    write_config(tmp_path, config)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "--agent-context", "--json"])

    assert exit_code == 0
    authority = json.loads(capsys.readouterr().out)["authority_briefs"][0]
    assert authority["freshness"] == "stale"
    assert authority["lifecycle"] == "current"
    assert authority["superseded_by"] is None


def test_brief_agent_context_warns_but_does_not_rank_missing_authority_docs(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="missing.md",
            role="current-authority",
            freshness="current",
        )
    ]
    write_config(tmp_path, config)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "--agent-context", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["authority_briefs"] == []
    assert all(
        not action["title"].startswith("Read authority doc")
        for action in payload["suggested_actions"]
    )
    assert payload["warnings"] == [
        {
            "area": "authority",
            "path": "missing.md",
            "message": "Configured authority document is missing.",
        }
    ]


def test_agent_context_synthbanshee_retry_bar_is_git_aware_and_work_first(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.reviews.contradictions.enabled = False
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="CLAUDE.md",
            role="current-authority",
            purpose="ASR sanity policy.",
            applies_to=["M17 ASR effective prosody"],
        ),
        AuthorityDocumentConfig(
            path="docs/m17_phase_a_validation_report.md",
            role="reference",
            purpose="M17 ASR validation report.",
            applies_to=["M17 ASR"],
        ),
    ]
    write_config(tmp_path, config)
    (tmp_path / "CLAUDE.md").write_text(
        "# CLAUDE\n\nASR sanity checks gate M17 effective prosody work.\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "m17_phase_a_validation_report.md").write_text(
        "# M17 Phase A Validation Report\n\nASR WER sanity baseline and effective prosody gap.\n",
        encoding="utf-8",
    )
    renderer = tmp_path / "synthbanshee" / "tts" / "renderer.py"
    renderer.parent.mkdir(parents=True)
    renderer.write_text("def _apply_effective_prosody_cap():\n    return 'asr'\n", encoding="utf-8")
    renderer_test = tmp_path / "tests" / "unit" / "test_effective_prosody_cap.py"
    renderer_test.parent.mkdir(parents=True, exist_ok=True)
    renderer_test.write_text(
        "def test_effective_prosody_cap():\n    assert True\n", encoding="utf-8"
    )
    source = tmp_path / "stale.md"
    source.write_text("# Stale\n\nOriginal maintenance source.\n", encoding="utf-8")
    add_source(tmp_path, source)
    source.write_text("# Stale\n\nChanged maintenance source.\n", encoding="utf-8")
    _init_git_repo(tmp_path, repo="SynthBanshee/SynthBanshee")
    _commit_all(tmp_path, "Initial SynthBanshee context")
    renderer.write_text(
        "def _apply_effective_prosody_cap():\n    return 'm17 asr effective prosody'\n",
        encoding="utf-8",
    )
    _commit_all(tmp_path, "M17 effective-prosody cap addresses ASR sanity policy")
    _install_fake_gh(
        tmp_path,
        monkeypatch,
        issues=[
            {
                "number": 89,
                "title": "fix(tts): M17 ASR follow-up after effective-prosody cap",
                "url": "https://github.com/SynthBanshee/SynthBanshee/issues/89",
                "body": "Next open ASR issue: close WER gap. Read synthbanshee/tts/renderer.py "
                "and tests/unit/test_effective_prosody_cap.py.",
                "state": "open",
                "labels": [],
            },
            {
                "number": 118,
                "title": "M20-P1.1 Add advanced semantic search or vector index",
                "url": "https://github.com/SynthBanshee/SynthBanshee/issues/118",
                "body": "Deferred vector search can wait until work-first handoff is correct.",
                "state": "open",
                "labels": [],
            },
        ],
        prs=[
            {
                "number": 90,
                "title": "effective-prosody cap addresses Whisper backdoor",
                "url": "https://github.com/SynthBanshee/SynthBanshee/pull/90",
                "body": "Merged PR context for ASR sanity and "
                "docs/m17_phase_a_validation_report.md.",
                "state": "merged",
                "isDraft": False,
                "mergedAt": "2026-05-06T07:14:00Z",
                "labels": [],
            }
        ],
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "pick",
            "up",
            "M17",
            "ASR",
            "work",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    actions = payload["suggested_actions"]
    assert actions[0]["category"] == "work-thread"
    assert actions[0]["url"] == "https://github.com/SynthBanshee/SynthBanshee/issues/89"
    assert all(
        action.get("url") != "https://github.com/SynthBanshee/SynthBanshee/issues/118"
        for action in actions
    )
    assert payload["git_context"]["threads"][0]["number"] == 89
    irrelevant_threads = [
        thread for thread in payload["git_context"]["threads"] if thread["number"] == 118
    ]
    assert irrelevant_threads and irrelevant_threads[0]["promoted"] is False
    assert any("effective-prosody cap" in item["title"] for item in actions)
    read_first = payload["git_context"]["read_first_paths"]
    assert "synthbanshee/tts/renderer.py" in read_first
    assert "tests/unit/test_effective_prosody_cap.py" in read_first
    authority_paths = [item["path"] for item in payload["authority_briefs"]]
    assert authority_paths[:2] == ["CLAUDE.md", "docs/m17_phase_a_validation_report.md"]
    maintenance_categories = [
        action["category"] for action in payload["maintenance_context"]["actions"]
    ]
    assert "queue" in maintenance_categories or "source-freshness" in maintenance_categories
    flattened_categories = [action["category"] for action in actions]
    assert flattened_categories.index("work-thread") < min(
        flattened_categories.index(category)
        for category in flattened_categories
        if category in {"queue", "source-freshness"}
    )

    suggest_exit = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "pick",
            "up",
            "M17",
            "ASR",
            "work",
            "--json",
        ]
    )
    assert suggest_exit == 0
    suggest_payload = json.loads(capsys.readouterr().out)
    suggest_categories = [action["category"] for action in suggest_payload["actions"]]
    assert suggest_categories[0] == "work-thread"
    assert all(
        action.get("url") != "https://github.com/SynthBanshee/SynthBanshee/issues/118"
        for action in suggest_payload["actions"]
    )
    assert suggest_categories.index("work-thread") < min(
        suggest_categories.index(category)
        for category in suggest_categories
        if category in {"queue", "source-freshness"}
    )


def test_agent_context_hocrgen_retry_bar_ranks_current_planning_before_history(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.reviews.contradictions.enabled = False
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path=".agent-plan.md",
            role="current-authority",
            purpose="Current F3b planning state.",
            applies_to=["hocrgen F3a F3b"],
        ),
        AuthorityDocumentConfig(
            path="docs/HeOCR_hocrgen_long_term_roadmap.md",
            role="roadmap",
            purpose="Roadmap critical path after F3a.",
            applies_to=["hocrgen F3b critical path"],
        ),
        AuthorityDocumentConfig(
            path="docs/modern_handwritten_acquisition_policy.md",
            role="current-authority",
            purpose="Modern handwritten acquisition policy for F3b.",
            applies_to=["hocrgen F3b"],
        ),
        AuthorityDocumentConfig(path="README.md", role="current-authority", applies_to=["hocrgen"]),
        AuthorityDocumentConfig(
            path="CONTRIBUTING.md",
            role="reference",
            applies_to=["hocrgen planning tests"],
        ),
        AuthorityDocumentConfig(
            path="docs/outside_review.md",
            role="historical-review",
            freshness="historical",
            applies_to=["hocrgen F3b"],
        ),
    ]
    write_config(tmp_path, config)
    (tmp_path / ".agent-plan.md").write_text(
        "# Agent Plan\n\nCurrent critical path: F3a complete; next implementation step is F3b.\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# hocrgen\n\nF3b adds typed repo-tracked operator intake manifests.\n",
        encoding="utf-8",
    )
    (tmp_path / "CONTRIBUTING.md").write_text(
        "# Contributing\n\nRun planning tests before changing F3 planning docs.\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "HeOCR_hocrgen_long_term_roadmap.md").write_text(
        "# Roadmap\n\n## Current critical path\n\nF3b follows F3a and precedes F4/F5.\n",
        encoding="utf-8",
    )
    (docs / "modern_handwritten_acquisition_policy.md").write_text(
        "# Modern Handwritten Acquisition Policy\n\n"
        "F3b must implement consent, release terms, privacy screening, and intake manifests.\n",
        encoding="utf-8",
    )
    (docs / "outside_review.md").write_text(
        "# Outside Review\n\nHistorical hocrgen review mentions F3b repeatedly.\n",
        encoding="utf-8",
    )
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Implement",
            "F3b",
            "operator",
            "intake",
            "--id",
            "task-f3b-operator-intake",
            "--status",
            "in_progress",
        ]
    )
    planning_test = tmp_path / "tests" / "test_planning_docs.py"
    planning_test.parent.mkdir(exist_ok=True)
    planning_test.write_text("def test_f3b_planning_docs():\n    assert True\n", encoding="utf-8")
    _init_git_repo(tmp_path, repo="HeOCR/hocrgen")
    _commit_all(tmp_path, "Initial hocrgen planning")
    planning_test.write_text("def test_f3b_planning_docs():\n    assert 'F3b'\n", encoding="utf-8")
    _commit_all(tmp_path, "F3a defines rights-clean modern handwritten acquisition policy")
    _install_fake_gh(
        tmp_path,
        monkeypatch,
        issues=[],
        prs=[
            {
                "number": 63,
                "title": "F3a: Define rights-clean modern handwritten acquisition policy",
                "url": "https://github.com/HeOCR/hocrgen/pull/63",
                "body": "Recent F3a context. Next is F3b with tests/test_planning_docs.py.",
                "state": "merged",
                "isDraft": False,
                "mergedAt": "2026-05-06T07:14:00Z",
                "labels": [],
            }
        ],
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "Resume",
            "hocrgen",
            "planning",
            "after",
            "F3a",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    authority_paths = [item["path"] for item in payload["authority_briefs"]]
    assert authority_paths[0] == ".agent-plan.md"
    current_paths = {
        "docs/HeOCR_hocrgen_long_term_roadmap.md",
        "docs/modern_handwritten_acquisition_policy.md",
        "README.md",
        "CONTRIBUTING.md",
    }
    assert current_paths <= set(authority_paths[:5])
    assert all(
        authority_paths.index("docs/outside_review.md") > authority_paths.index(path)
        for path in current_paths
    )
    assert payload["git_context"]["threads"][0]["number"] == 63
    assert "tests/test_planning_docs.py" in payload["git_context"]["read_first_paths"]
    work_titles = " ".join(action["title"] for action in payload["work_context"]["actions"])
    assert "F3a" in work_titles or "F3b" in work_titles

    suggest_exit = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "Resume",
            "hocrgen",
            "planning",
            "after",
            "F3a",
            "--json",
        ]
    )
    assert suggest_exit == 0
    suggest_payload = json.loads(capsys.readouterr().out)
    suggest_categories = [action["category"] for action in suggest_payload["actions"]]
    assert suggest_categories[0] in {"work-thread", "git-context", "authority", "planning"}
    if "goal-match" in suggest_categories:
        assert suggest_categories.index("authority") < suggest_categories.index("goal-match")

    text_exit = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "Resume",
            "hocrgen",
            "planning",
            "after",
            "F3a",
        ]
    )
    assert text_exit == 0
    out = capsys.readouterr().out
    assert out.index("Authority docs:") < out.index("Splendor maintenance:")
    assert out.index("Active planning:") < out.index("Splendor maintenance:")


def test_agent_context_hocrgen_retry_bar_uses_provisional_uncurated_authority(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.reviews.contradictions.enabled = False
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="docs/outside_review.md",
            role="historical-review",
            freshness="historical",
            applies_to=["hocrgen F3b"],
        )
    ]
    write_config(tmp_path, config)
    (tmp_path / ".agent-plan.md").write_text(
        "# Agent Plan\n\nCurrent critical path: F3a complete; next implementation step is F3b.\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# hocrgen\n\nF3b adds typed repo-tracked operator intake manifests.\n",
        encoding="utf-8",
    )
    (tmp_path / "CONTRIBUTING.md").write_text(
        "# Contributing\n\nRun planning tests before changing F3b planning docs.\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "HeOCR_hocrgen_long_term_roadmap.md").write_text(
        "# Roadmap\n\n## Current critical path\n\nF3b follows F3a and precedes F4/F5.\n",
        encoding="utf-8",
    )
    (docs / "modern_handwritten_acquisition_policy.md").write_text(
        "# Modern Handwritten Acquisition Policy\n\n"
        "F3b requires consent, release terms, privacy screening, and typed intake manifests.\n",
        encoding="utf-8",
    )
    (docs / "outside_review.md").write_text(
        "# Outside Review\n\nHistorical hocrgen review mentions F3b repeatedly.\n",
        encoding="utf-8",
    )
    planning_test = tmp_path / "tests" / "test_planning_docs.py"
    planning_test.parent.mkdir(exist_ok=True)
    planning_test.write_text("def test_f3b_planning_docs():\n    assert 'F3b'\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "--no-git",
            "Resume",
            "hocrgen",
            "planning",
            "after",
            "F3a",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    authority_paths = [item["path"] for item in payload["authority_briefs"]]
    expected_provisional = {
        ".agent-plan.md",
        "docs/HeOCR_hocrgen_long_term_roadmap.md",
        "docs/modern_handwritten_acquisition_policy.md",
        "README.md",
        "CONTRIBUTING.md",
        "tests/test_planning_docs.py",
    }
    assert expected_provisional <= set(authority_paths)
    assert all(
        authority_paths.index(path) < authority_paths.index("docs/outside_review.md")
        for path in expected_provisional
    )
    provisional = payload["provisional_context"]["authority"]
    provisional_by_path = {item["path"]: item for item in provisional}
    assert expected_provisional <= set(provisional_by_path)
    agent_plan = provisional_by_path[".agent-plan.md"]
    assert agent_plan["origin"] == "inferred-authority"
    assert agent_plan["curation_state"] == "provisional-uncurated"
    assert agent_plan["curation_commands"] == [
        "splendor add-source .agent-plan.md",
        "splendor ingest .agent-plan.md",
    ]
    assert (
        payload["authority_briefs"][authority_paths.index("docs/outside_review.md")][
            "curation_state"
        ]
        == "configured"
    )
    authority_actions = [
        action for action in payload["suggested_actions"] if action["category"] == "authority"
    ]
    assert authority_actions[0]["path"] in expected_provisional
    assert "provisional-uncurated" in authority_actions[0]["reason"]

    suggest_exit = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "--no-git",
            "Resume",
            "hocrgen",
            "planning",
            "after",
            "F3a",
            "--json",
        ]
    )
    assert suggest_exit == 0
    suggest_payload = json.loads(capsys.readouterr().out)
    suggest_paths = [item["path"] for item in suggest_payload["authority_briefs"]]
    assert suggest_paths.index(".agent-plan.md") < suggest_paths.index("docs/outside_review.md")
    assert ".agent-plan.md" in {
        item["path"] for item in suggest_payload["provisional_context"]["authority"]
    }

    text_exit = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "--no-git",
            "Resume",
            "hocrgen",
            "planning",
            "after",
            "F3a",
        ]
    )
    assert text_exit == 0
    out = capsys.readouterr().out
    assert "Provisional uncurated docs:" in out
    assert "Curate: splendor add-source .agent-plan.md; splendor ingest .agent-plan.md" in out
    assert out.index("Provisional uncurated docs:") < out.index("Splendor maintenance:")


def test_agent_context_inferred_authority_stays_goal_relevant_and_below_configured(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.reviews.contradictions.enabled = False
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="docs/current_reference.md",
            role="reference",
            freshness="current",
            applies_to=["hocrgen F3b"],
        )
    ]
    write_config(tmp_path, config)
    (tmp_path / ".agent-plan.md").write_text(
        "# Agent Plan\n\nCurrent critical path: F3a complete; next implementation step is F3b.\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# hocrgen\n\nF3b adds typed repo-tracked operator intake manifests.\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "current_reference.md").write_text(
        "# Current Reference\n\nConfigured hocrgen F3b reference.\n",
        encoding="utf-8",
    )
    (docs / "some_other_plan.md").write_text(
        "# Billing Migration Plan\n\nUnrelated rollout plan for billing imports.\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "--no-git",
            "Resume",
            "hocrgen",
            "planning",
            "after",
            "F3a",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    authority_paths = [item["path"] for item in payload["authority_briefs"]]
    assert authority_paths.index("docs/current_reference.md") < authority_paths.index(
        ".agent-plan.md"
    )
    assert "docs/some_other_plan.md" not in authority_paths
    assert "docs/some_other_plan.md" not in {
        item["path"] for item in payload["provisional_context"]["authority"]
    }
    configured = payload["authority_briefs"][authority_paths.index("docs/current_reference.md")]
    assert configured["origin"] == "configured-authority"
    assert configured["curation_state"] == "configured"


def test_brief_plain_text_does_not_call_gh_by_default(tmp_path: Path, capsys, monkeypatch) -> None:
    initialize_workspace(tmp_path)
    _init_git_repo(tmp_path, repo="example/project")
    _commit_all(tmp_path, "Initial context")
    marker = _install_marker_gh(tmp_path, monkeypatch)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "agent", "handoff"])

    assert exit_code == 0
    assert not marker.exists()


def test_agent_context_reports_gh_timeout_as_warning(tmp_path: Path, capsys, monkeypatch) -> None:
    initialize_workspace(tmp_path)
    _init_git_repo(tmp_path, repo="example/project")
    _commit_all(tmp_path, "Initial context")
    _install_marker_gh(tmp_path, monkeypatch, sleep_seconds=1)
    monkeypatch.setattr(brief_module, "_GIT_COMMAND_TIMEOUT_SECONDS", 0.01)
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "brief", "--agent-context", "agent", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert any("Timed out" in warning for warning in payload["git_context"]["warnings"])


def test_agent_context_explicit_since_empty_range_does_not_fallback_to_head(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    initialize_workspace(tmp_path)
    _init_git_repo(tmp_path, repo="example/project")
    _commit_all(tmp_path, "Initial context")
    _install_fake_gh(tmp_path, monkeypatch, issues=[], prs=[])
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "brief", "--agent-context", "--since", "HEAD", "agent", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["git_context"]["commits"] == []


def test_agent_context_multiline_commit_body_does_not_become_changed_paths(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    initialize_workspace(tmp_path)
    context_file = tmp_path / "src" / "context.py"
    context_file.parent.mkdir()
    context_file.write_text("VALUE = 'initial'\n", encoding="utf-8")
    _init_git_repo(tmp_path, repo="example/project")
    _commit_all(tmp_path, "Initial context")
    context_file.write_text("VALUE = 'm18 handoff'\n", encoding="utf-8")
    _git(
        tmp_path,
        "add",
        "src/context.py",
    )
    _git(
        tmp_path,
        "commit",
        "-m",
        "M18 multiline body context",
        "-m",
        "Body mentions docs/not-a-changed-path.md\nand tests/not_a_changed_path.py.",
    )
    _install_fake_gh(tmp_path, monkeypatch, issues=[], prs=[])
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "brief", "--agent-context", "m18", "handoff", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    paths = payload["git_context"]["commits"][0]["paths"]
    assert "src/context.py" in paths
    assert "docs/not-a-changed-path.md" not in paths
    assert "tests/not_a_changed_path.py." not in paths


def test_suggest_next_uses_wiki_authority_metadata_but_skips_source_summaries(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "agent-handoff.md",
        kind="topic",
        title="Agent handoff authority",
        page_id="topic-agent-handoff",
        authority_role="current-authority",
        authority_freshness="current",
        authority_scope=["agent handoff"],
        body="Maintained agent handoff decisions live here.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "sources" / "src-generated.md",
        kind="source-summary",
        title="Generated summary",
        page_id="src-generated",
        authority_role="current-authority",
        authority_freshness="current",
        body="Generated source summaries are not maintained authority.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "suggest-next", "agent", "handoff", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    authority = [action for action in payload["actions"] if action["category"] == "authority"]
    assert authority
    assert authority[0]["path"] == "wiki/topics/agent-handoff.md"
    assert all(action["path"] != "wiki/sources/src-generated.md" for action in authority)


def test_suggest_next_derives_draft_wiki_authority_freshness_as_watch(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "draft-authority.md",
        kind="topic",
        title="Draft authority",
        page_id="topic-draft-authority",
        authority_role="current-authority",
        body="Draft authority notes for agent handoff.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "suggest-next", "agent", "handoff", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    authority_brief = payload["authority_briefs"][0]
    assert authority_brief["path"] == "wiki/topics/draft-authority.md"
    assert authority_brief["freshness"] == "watch"
    authority_actions = [
        action for action in payload["actions"] if action["category"] == "authority"
    ]
    assert authority_actions[0]["reason"].startswith(
        "current-authority/watch/current/wiki-authority/curated:"
    )


def test_suggest_next_includes_lifecycle_aware_decision_authority(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    main(
        [
            "--root",
            str(tmp_path),
            "decision",
            "create",
            "Prefer",
            "lifecycle",
            "authority",
            "ranking",
            "--id",
            "decision-current-authority-ranking",
            "--status",
            "accepted",
            "--decided-at",
            "2026-05-06",
            "--authority-lifecycle",
            "reviewed",
            "--supersedes",
            "decision-old-authority-ranking",
            "--issue-ref",
            "#116",
            "--pr-ref",
            "#133",
        ]
    )
    main(
        [
            "--root",
            str(tmp_path),
            "decision",
            "create",
            "Older",
            "authority",
            "ranking",
            "research",
            "--id",
            "decision-old-authority-ranking",
            "--status",
            "superseded",
            "--decided-at",
            "2026-04-30",
            "--superseded-by",
            "decision-current-authority-ranking",
        ]
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "suggest-next", "authority", "ranking", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    decisions = [item for item in payload["authority_briefs"] if item["role"] == "decision"]
    assert [item["path"] for item in decisions] == [
        "planning/decisions/decision-current-authority-ranking.md",
        "planning/decisions/decision-old-authority-ranking.md",
    ]
    assert decisions[0]["lifecycle"] == "reviewed"
    assert decisions[0]["issue_refs"] == ["#116"]
    assert decisions[0]["pr_refs"] == ["#133"]
    assert decisions[1]["lifecycle"] == "superseded"
    assert decisions[1]["superseded_by"] == "decision-current-authority-ranking"
    authority_actions = [
        action for action in payload["actions"] if action["category"] == "authority"
    ]
    assert authority_actions[0]["title"].startswith("Review decision ")


def test_agent_context_ranks_mock_client_authority_above_stale_token_matches(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "current-spec.md").write_text(
        "# Balance Reconciliation Spec\n\nCurrent balance reconciliation rollout authority.\n",
        encoding="utf-8",
    )
    (docs / "rollout-plan.md").write_text(
        "# Reconciliation Rollout Plan\n\nPR-linked rollout plan for balance reconciliation.\n",
        encoding="utf-8",
    )
    (docs / "generic-authority.md").write_text(
        "# Current Project Authority\n\nGeneral current authority for public readiness.\n",
        encoding="utf-8",
    )
    (docs / "stale-jsonl-note.md").write_text(
        "# JSONL Reconciliation Note\n\n"
        "balance reconciliation rollout balance reconciliation rollout jsonl jsonl jsonl\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(
            path="docs/stale-jsonl-note.md",
            role="current-authority",
            freshness="stale",
            purpose="Older JSONL research note retained for comparison.",
        ),
        AuthorityDocumentConfig(
            path="docs/generic-authority.md",
            role="current-authority",
            freshness="current",
            purpose="Generic current authority that should not outrank task-specific context.",
        ),
        AuthorityDocumentConfig(
            path="docs/rollout-plan.md",
            role="roadmap",
            freshness="current",
            authority_lifecycle="pr-linked",
            purpose="Current rollout plan.",
            applies_to=["balance reconciliation rollout"],
            pr_refs=["#133"],
        ),
        AuthorityDocumentConfig(
            path="docs/current-spec.md",
            role="current-authority",
            freshness="current",
            purpose="Current reviewed spec.",
            applies_to=["balance reconciliation rollout"],
        ),
    ]
    write_config(tmp_path, config)
    write_wiki_page(
        tmp_path / "wiki" / "sources" / "held-entry-research.md",
        kind="source-summary",
        title="Held-entry reconciliation research",
        page_id="source-held-entry-research",
        review_state="contested",
        body="Held-entry research contradicts parts of the balance reconciliation rollout.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "held-entry-research.md",
        kind="topic",
        title="Held-entry research authority",
        page_id="topic-held-entry-research",
        review_state="human-reviewed",
        authority_role="reference",
        authority_freshness="current",
        authority_lifecycle="reviewed",
        authority_scope=["balance reconciliation rollout", "held-entry research"],
        body="Reviewed held-entry research for reconciliation contradictions.",
    )
    main(
        [
            "--root",
            str(tmp_path),
            "decision",
            "create",
            "Use",
            "CSV-first",
            "balance",
            "reconciliation",
            "--id",
            "decision-csv-first-reconciliation",
            "--status",
            "accepted",
            "--authority-lifecycle",
            "reviewed",
            "--issue-ref",
            "#115",
        ]
    )
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "balance",
            "reconciliation",
            "rollout",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    authority_paths = [item["path"] for item in payload["authority_briefs"]]
    assert authority_paths[:2] == [
        "docs/current-spec.md",
        "docs/rollout-plan.md",
    ]
    stale_index = authority_paths.index("docs/stale-jsonl-note.md")
    generic_index = authority_paths.index("docs/generic-authority.md")
    decision_index = authority_paths.index(
        "planning/decisions/decision-csv-first-reconciliation.md"
    )
    research_index = authority_paths.index("wiki/topics/held-entry-research.md")
    assert decision_index < stale_index
    assert research_index < stale_index
    assert decision_index < generic_index
    assert research_index < generic_index
    assert any(
        match["path"] == "wiki/sources/held-entry-research.md" for match in payload["matches"]
    )
    assert payload["suggested_actions"][0]["category"] in {"goal-match", "authority"}


def test_agent_context_preserves_goal_phrase_order_for_authority_ranking(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ordered.md").write_text(
        "# Held Entry Research\n\nUse held entry research for reconciliation.",
        encoding="utf-8",
    )
    (docs / "permuted.md").write_text(
        "# Entry Held Research\n\nUse entry held research for reconciliation.",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(path="docs/permuted.md", role="reference", freshness="current"),
        AuthorityDocumentConfig(path="docs/ordered.md", role="reference", freshness="current"),
    ]
    write_config(tmp_path, config)
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "brief", "--agent-context", "held", "entry", "research", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["path"] for item in payload["authority_briefs"][:2]] == [
        "docs/ordered.md",
        "docs/permuted.md",
    ]


def test_agent_context_orders_active_planning_by_goal_relevance(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Clean up unrelated import scripts",
            "--id",
            "task-import-cleanup",
            "--status",
            "in_progress",
        ]
    )
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Improve agent handoff ranking",
            "--id",
            "task-agent-handoff-ranking",
            "--status",
            "in_progress",
        ]
    )
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "brief", "--agent-context", "agent", "handoff", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_planning"][0]["record_id"] == "task-agent-handoff-ranking"
    planning_actions = [
        action for action in payload["suggested_actions"] if action["category"] == "planning"
    ]
    assert planning_actions[0]["record_id"] == "task-agent-handoff-ranking"


def test_agent_context_hides_generated_review_tasks_from_active_planning(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Continue human handoff plan",
            "--id",
            "task-human-handoff-plan",
            "--status",
            "in_progress",
        ]
    )
    review_task = TaskRecord(
        task_id="task-review-src-a-src-b-1234567890",
        title="Review contradiction: noisy generated task",
        status="todo",
        priority="high",
        record_origin="generated",
        generated_kind="contradiction-review",
        review_task_state="active",
        created_at="2026-05-06T00:00:00Z",
        updated_at="2026-05-06T00:00:00Z",
    )
    task_path = tmp_path / "planning" / "tasks" / f"{review_task.task_id}.md"
    task_path.write_text(
        render_planning_markdown(review_task, title=review_task.title),
        encoding="utf-8",
    )
    capsys.readouterr()

    exit_code = main(
        ["--root", str(tmp_path), "brief", "--agent-context", "human", "handoff", "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["record_id"] for item in payload["active_planning"]] == ["task-human-handoff-plan"]
    assert all(
        action["record_id"] != review_task.task_id
        for action in payload["suggested_actions"]
        if action["record_id"] is not None
    )


def test_suggest_next_caps_review_noise_after_goal_relevance(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    for index in range(8):
        write_wiki_page(
            tmp_path / "wiki" / "topics" / f"generated-noise-{index}.md",
            kind="topic",
            title=f"Generated noise {index}",
            page_id=f"topic-generated-noise-{index}",
            review_state="machine-generated",
            body="Generated review noise without handoff context.",
        )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "agent-handoff-contested.md",
        kind="topic",
        title="Agent handoff contested ranking",
        page_id="topic-agent-handoff-contested-ranking",
        review_state="contested",
        body="Agent handoff ranking needs review because stale notes conflict.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "agent-handoff-authority.md",
        kind="topic",
        title="Agent handoff authority",
        page_id="topic-agent-handoff-authority",
        review_state="human-reviewed",
        authority_role="current-authority",
        authority_freshness="current",
        authority_lifecycle="reviewed",
        authority_scope=["agent handoff ranking"],
        body="Current reviewed handoff ranking authority.",
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "suggest-next", "agent", "handoff", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    categories = [action["category"] for action in payload["actions"]]
    assert categories.index("authority") < categories.index("wiki-review")
    wiki_review = [action for action in payload["actions"] if action["category"] == "wiki-review"]
    assert wiki_review[0]["path"] == "wiki/topics/agent-handoff-contested.md"
    assert len(wiki_review) == 2


def test_suggest_next_json_ranks_changed_sources_before_review_work(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "handoff.md"
    source.write_text("# Handoff\n\nOriginal briefing state.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "handoff.md",
        kind="topic",
        title="Handoff",
        page_id="topic-handoff",
        review_state="contested",
        source_refs=[added.source_id],
        body="Handoff work has contested notes.",
    )
    source.write_text("# Handoff\n\nUpdated briefing state.\n", encoding="utf-8")
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "please",
            "refresh",
            "sources",
            "now",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    actions = payload["actions"]
    assert actions[0]["category"] == "source-freshness"
    assert actions[0]["path"] == "handoff.md"
    assert actions[0]["source_id"] == added.source_id
    assert actions[0]["command"] == "splendor source refresh handoff.md"
    assert any(action["category"] == "wiki-review" for action in actions)
    assert payload["freshness"]["changed"] == 1


def test_suggest_next_text_reports_pending_queue_path_first(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "pending.md"
    source.write_text("# Pending\n\nNeeds ingest.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "pending.md"])
    added = load_source_record(next((tmp_path / "state" / "manifests" / "sources").glob("*.json")))
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "suggest-next"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Suggested next actions" in out
    assert "Drain ingest queue job" in out
    assert "target=pending.md" in out
    assert "command=splendor ingest --pending" in out
    assert added.source_id in out


def test_suggest_next_caps_review_noise_and_preserves_goal_work(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    for index in range(10):
        write_wiki_page(
            tmp_path / "wiki" / "topics" / f"generated-{index}.md",
            kind="topic",
            title=f"Generated {index}",
            page_id=f"topic-generated-{index}",
            review_state="machine-generated",
            body="Generated review noise.",
        )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "handoff.md",
        kind="topic",
        title="Handoff",
        page_id="topic-handoff",
        review_state="human-reviewed",
        body="Handoff work should stay visible in suggest-next results.",
    )
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Continue handoff",
            "--id",
            "task-handoff",
            "--status",
            "in_progress",
        ]
    )
    capsys.readouterr()

    exit_code = main(["--root", str(tmp_path), "suggest-next", "handoff", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    actions = payload["actions"]
    categories = [action["category"] for action in actions]
    assert categories.count("wiki-review") == 2
    assert "goal-match" in categories
    assert "planning" in categories
    assert categories.index("goal-match") < categories.index("wiki-review")


def test_suggest_next_exposes_generated_review_tasks_for_contradiction_goal(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    review_task = TaskRecord(
        task_id="task-review-src-a-src-b-1234567890",
        title="Review contradiction: A vs B",
        status="todo",
        priority="high",
        record_origin="generated",
        generated_kind="contradiction-review",
        review_task_state="active",
        created_at="2026-05-06T00:00:00Z",
        updated_at="2026-05-06T00:00:00Z",
    )
    task_path = tmp_path / "planning" / "tasks" / f"{review_task.task_id}.md"
    task_path.write_text(
        render_planning_markdown(review_task, title=review_task.title),
        encoding="utf-8",
    )
    capsys.readouterr()

    default_exit = main(["--root", str(tmp_path), "suggest-next", "review", "tasks", "--json"])
    default_payload = json.loads(capsys.readouterr().out)
    focused_exit = main(["--root", str(tmp_path), "suggest-next", "contradiction", "--json"])
    focused_payload = json.loads(capsys.readouterr().out)

    assert default_exit == 0
    assert focused_exit == 0
    assert all("task-review" not in match["path"] for match in focused_payload["matches"])
    assert all("task-review" not in str(action["path"]) for action in focused_payload["actions"])
    assert all(
        action["category"] != "contradiction-review" for action in default_payload["actions"]
    )
    contradiction_actions = [
        action
        for action in focused_payload["actions"]
        if action["category"] == "contradiction-review"
    ]
    assert contradiction_actions[0]["command"] == (
        "splendor task list --generated-review --review-task-state active"
    )


def test_maintenance_focused_handoff_exposes_review_and_generated_state_commands(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    reviewed_source = tmp_path / "reviewed.md"
    reviewed_source.write_text("# Reviewed\n\nInitial maintenance source.\n", encoding="utf-8")
    added_reviewed = add_source(tmp_path, reviewed_source)
    main(["--root", str(tmp_path), "ingest", added_reviewed.source_id])
    reviewed_source.write_text("# Reviewed\n\nChanged maintenance source.\n", encoding="utf-8")
    queued_source = tmp_path / "queued.md"
    queued_source.write_text("# Queued\n\nPending ingest source.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", "queued.md"])
    review_task = TaskRecord(
        task_id="task-review-src-a-src-b-1234567890",
        title="Review contradiction: A vs B",
        status="todo",
        priority="high",
        record_origin="generated",
        generated_kind="contradiction-review",
        review_task_state="active",
        created_at="2026-05-06T00:00:00Z",
        updated_at="2026-05-06T00:00:00Z",
    )
    task_path = tmp_path / "planning" / "tasks" / f"{review_task.task_id}.md"
    task_path.write_text(
        render_planning_markdown(review_task, title=review_task.title),
        encoding="utf-8",
    )
    capsys.readouterr()

    suggest_exit = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "wiki",
            "maintenance",
            "review",
            "--json",
        ]
    )
    suggest_payload = json.loads(capsys.readouterr().out)
    brief_exit = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "--no-git",
            "wiki",
            "maintenance",
            "review",
            "--json",
        ]
    )
    brief_payload = json.loads(capsys.readouterr().out)

    assert suggest_exit == 0
    assert brief_exit == 0
    suggest_commands = {
        command["command"] for command in suggest_payload["maintenance_context"]["commands"]
    }
    brief_commands = {
        command["command"] for command in brief_payload["maintenance_context"]["commands"]
    }
    expected_commands = {
        "splendor wiki status",
        f"splendor wiki suggest {added_reviewed.source_id}",
        "splendor source freshness",
        "splendor source refresh reviewed.md",
        "splendor queue inspect",
        "splendor ingest --pending",
        "splendor task list --generated-review --review-task-state active",
    }
    assert expected_commands <= suggest_commands
    assert expected_commands <= brief_commands
    assert "contradiction-review" in {
        action["category"] for action in suggest_payload["maintenance_context"]["actions"]
    }
    assert any(
        "not default active human tasks" in note
        for note in brief_payload["maintenance_context"]["notes"]
    )
    assert brief_payload["active_planning"] == []


def test_implementation_handoff_keeps_maintenance_commands_below_work_context(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Implement",
            "handoff",
            "polish",
            "--id",
            "task-handoff-polish",
            "--status",
            "in_progress",
        ]
    )
    source = tmp_path / "review-needed.md"
    source.write_text("# Review needed\n\nGenerated maintenance state.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    capsys.readouterr()

    json_exit = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "--no-git",
            "implement",
            "handoff",
            "polish",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    text_exit = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "--no-git",
            "implement",
            "handoff",
            "polish",
        ]
    )
    out = capsys.readouterr().out

    assert json_exit == 0
    assert text_exit == 0
    assert payload["work_context"]["actions"]
    assert payload["maintenance_context"]["actions"]
    assert payload["maintenance_context"]["commands"]
    assert all(
        action["category"] not in {"synthesis", "wiki-review", "source-freshness", "queue"}
        for action in payload["work_context"]["actions"]
    )
    assert out.index("Work context:") < out.index("Splendor maintenance:")
    assert out.index("Splendor maintenance:") < out.index("Maintenance commands:")
    assert "Wiki status:" not in out


def test_git_handoff_exposes_pr_summary_as_maintenance_command(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    _init_git_repo(tmp_path)
    _commit_all(tmp_path, "Initial workspace")
    _git(tmp_path, "switch", "-c", "feature")
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Implement",
            "compact",
            "review",
            "--id",
            "task-compact-review",
            "--status",
            "in_progress",
        ]
    )
    source = tmp_path / "generated-state.md"
    source.write_text("# Generated state\n\nNeeds compact review.\n", encoding="utf-8")
    added_source = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added_source.source_id])
    _commit_all(tmp_path, "Add compact review planning task")
    capsys.readouterr()

    brief_exit = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "implement",
            "compact",
            "review",
            "--json",
        ]
    )
    brief_payload = json.loads(capsys.readouterr().out)
    suggest_exit = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "implement",
            "compact",
            "review",
            "--json",
        ]
    )
    suggest_payload = json.loads(capsys.readouterr().out)

    assert brief_exit == 0
    assert suggest_exit == 0
    assert brief_payload["work_context"]["actions"]
    assert suggest_payload["work_context"]["actions"]
    assert all(
        action["category"] != "pr-summary" for action in brief_payload["work_context"]["actions"]
    )
    brief_commands = {
        command["command"] for command in brief_payload["maintenance_context"]["commands"]
    }
    suggest_commands = {
        command["command"] for command in suggest_payload["maintenance_context"]["commands"]
    }
    assert "splendor pr-summary --since main" in brief_commands
    assert "splendor pr-summary --since main" in suggest_commands


def test_git_handoff_skips_pr_summary_for_plain_work_changes(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    _init_git_repo(tmp_path)
    _commit_all(tmp_path, "Initial workspace")
    _git(tmp_path, "switch", "-c", "feature")
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Implement",
            "plain",
            "work",
            "--id",
            "task-plain-work",
            "--status",
            "in_progress",
        ]
    )
    _commit_all(tmp_path, "Add plain work planning task")
    capsys.readouterr()

    brief_exit = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "implement",
            "plain",
            "work",
            "--json",
        ]
    )
    brief_payload = json.loads(capsys.readouterr().out)
    suggest_exit = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "implement",
            "plain",
            "work",
            "--json",
        ]
    )
    suggest_payload = json.loads(capsys.readouterr().out)

    assert brief_exit == 0
    assert suggest_exit == 0
    assert brief_payload["work_context"]["actions"]
    assert suggest_payload["work_context"]["actions"]
    brief_commands = {
        command["command"] for command in brief_payload["maintenance_context"]["commands"]
    }
    suggest_commands = {
        command["command"] for command in suggest_payload["maintenance_context"]["commands"]
    }
    assert "splendor pr-summary --since main" not in brief_commands
    assert "splendor pr-summary --since main" not in suggest_commands


def test_maintenance_guidance_preserves_dead_letter_repair_command(tmp_path: Path, capsys) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "dead-letter.md"
    source.write_text("# Dead letter\n\nNeeds repair.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = load_queue_item(queue_path).model_copy(
        update={"status": "dead_letter", "last_error": "broken ingest"}
    )
    write_queue_item(queue_path, queue_record)
    capsys.readouterr()

    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "wiki",
            "maintenance",
            "review",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    commands = {command["command"] for command in payload["maintenance_context"]["commands"]}
    assert "splendor queue inspect" in commands
    assert f"splendor repair ingest {added.source_id}" in commands


def test_agent_handoff_reports_orphan_queue_cleanup_without_displacing_work(
    tmp_path: Path, capsys
) -> None:
    initialize_workspace(tmp_path)
    main(
        [
            "--root",
            str(tmp_path),
            "task",
            "create",
            "Implement",
            "handoff",
            "cleanup",
            "--id",
            "task-handoff-cleanup",
            "--status",
            "in_progress",
        ]
    )
    source = tmp_path / "orphan.md"
    source.write_text("# Orphan\n\nQueue payload will be removed.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    enqueue_ingest_job(tmp_path, added.source_id)
    added.manifest_path.unlink()
    capsys.readouterr()

    brief_exit = main(
        [
            "--root",
            str(tmp_path),
            "brief",
            "--agent-context",
            "--no-git",
            "implement",
            "handoff",
            "cleanup",
            "--json",
        ]
    )
    brief_payload = json.loads(capsys.readouterr().out)
    suggest_exit = main(
        [
            "--root",
            str(tmp_path),
            "suggest-next",
            "--no-git",
            "implement",
            "handoff",
            "cleanup",
            "--json",
        ]
    )
    suggest_payload = json.loads(capsys.readouterr().out)

    assert brief_exit == 0
    assert suggest_exit == 0
    for payload in [brief_payload, suggest_payload]:
        commands = {command["command"] for command in payload["maintenance_context"]["commands"]}
        assert "splendor queue clean --orphaned" in commands
        assert "splendor queue inspect" in commands
        assert any(
            action["category"] == "queue" and action["command"] == "splendor queue clean --orphaned"
            for action in payload["maintenance_context"]["actions"]
        )
        assert payload["work_context"]["actions"]
        assert all(action["category"] != "queue" for action in payload["work_context"]["actions"])


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
