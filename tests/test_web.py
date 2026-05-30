import io
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

import splendor.web as web
from splendor.cli import main
from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.commands.planning import (
    create_decision,
    create_milestone,
    create_question,
    create_task,
)
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter, QueueItemRecord, RunRecord
from splendor.state.runtime import write_queue_item, write_run_record
from splendor.state.source_registry import load_source_record
from splendor.web import create_app


def write_wiki_page(path: Path, *, title: str, page_id: str, body: str) -> None:
    frontmatter = KnowledgePageFrontmatter(
        kind="concept",
        title=title,
        page_id=page_id,
        status="active",
        confidence=0.8,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    path.write_text(f"---\n{frontmatter_text}\n---\n\n{body}", encoding="utf-8")


def test_home_page_loads_for_initialized_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Splendor" in response.text
    assert "Wiki content pages" in response.text
    assert "/browse" in response.text
    assert "/planning" in response.text
    assert "/runs" in response.text
    assert "/queue" in response.text
    assert "/status" in response.text


def test_home_page_shows_empty_state_for_initialized_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "No workspace knowledge yet" in response.text
    assert "uv run splendor repo refresh" in response.text
    assert "uv run splendor add-source" in response.text
    assert "Wiki content pages" in response.text
    assert "Source manifests" in response.text


def test_project_identity_uses_wiki_index_heading_and_summary(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "wiki" / "index.md").write_text(
        "# SynthBanshee\n\nLocal code-and-research knowledge workspace.\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "<h1>SynthBanshee</h1>" in response.text
    assert "Local code-and-research knowledge workspace." in response.text
    assert "<title>Home · SynthBanshee · Splendor</title>" in response.text


def test_project_identity_falls_back_to_readme_when_index_is_missing(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "wiki" / "index.md").unlink()
    (tmp_path / "README.md").write_text(
        "# README Project\n\nREADME summary becomes the local web identity.\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/browse")

    assert response.status_code == 200
    assert "<h1>README Project</h1>" in response.text
    assert "README summary becomes the local web identity." in response.text


def test_project_identity_skips_generic_initialized_index_for_readme(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "README.md").write_text(
        "# Real Project\n\nREADME has the real project identity.\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "<h1>Real Project</h1>" in response.text
    assert "README has the real project identity." in response.text
    assert "Splendor Wiki Index" not in response.text


def test_project_identity_falls_back_to_workspace_basename(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert f"<h1>{tmp_path.name}</h1>" in response.text


def test_page_chrome_keeps_visible_route_title(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/browse")

    assert response.status_code == 200
    assert f"<h1>{tmp_path.name}</h1>" in response.text
    assert '<h2 class="page-title">Browse</h2>' in response.text


def test_project_identity_reads_only_bounded_markdown(tmp_path: Path, monkeypatch) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Bounded Project\n\nShort summary.\n\n" + ("extra\n" * 200), encoding="utf-8"
    )

    def fail_read_text(*args, **kwargs):
        raise AssertionError("identity parsing should not read the whole markdown file")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    identity = web._project_identity_from_markdown(readme)

    assert identity == web._ProjectIdentity(name="Bounded Project", summary="Short summary.")


def test_home_page_renders_cockpit_read_model(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "operator-cockpit.md",
        title="Operator cockpit",
        page_id="concept-operator-cockpit",
        body="# Operator cockpit\n",
    )
    write_wiki_page(
        tmp_path / "wiki" / "sources" / "src-web.md",
        title="Source web",
        page_id="source-src-web",
        body="# Source web\n",
    )
    create_milestone(
        tmp_path,
        "Cockpit rollout",
        record_id="milestone-cockpit",
        status="active",
        target_date=None,
        task_refs=["task-home-read-model"],
        decision_refs=["decision-home-scope"],
        question_refs=["question-cockpit-cli"],
    )
    create_task(
        tmp_path,
        "Build home read model",
        record_id="task-home-read-model",
        status="in_progress",
        priority="high",
        owner="codex",
        milestone_refs=["milestone-cockpit"],
        decision_refs=["decision-home-scope"],
        question_refs=["question-cockpit-cli"],
        depends_on=[],
        source_refs=[],
    )
    create_decision(
        tmp_path,
        "Keep home read only",
        record_id="decision-home-scope",
        status="proposed",
        decided_at=None,
        supersedes=[],
        source_refs=[],
        related_tasks=["task-home-read-model"],
        related_questions=["question-cockpit-cli"],
    )
    create_question(
        tmp_path,
        "Should cockpit summary be a CLI command",
        record_id="question-cockpit-cli",
        status="open",
        source_refs=[],
        related_tasks=["task-home-read-model"],
        related_decisions=["decision-home-scope"],
    )
    write_run_record(
        layout.runs_dir / "run-home.json",
        RunRecord(
            run_id="run-home",
            job_id="ingest-src-web",
            job_type="ingest_source",
            started_at="2026-05-01T10:01:00+00:00",
            finished_at="2026-05-01T10:02:00+00:00",
            status="succeeded",
            input_refs=["state/manifests/sources/src-web.json"],
            output_refs=["wiki/sources/src-web.md"],
            pipeline_version="test",
            source_ids=["src-web"],
            page_refs=["wiki/sources/src-web.md"],
        ),
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Current work" in response.text
    assert "Build home read model" in response.text
    assert 'href="/documents/planning/tasks/task-home-read-model.md"' in response.text
    assert "Needs attention" in response.text
    assert "Keep home read only" in response.text
    assert "Knowledge map summary" in response.text
    assert "1 maintained wiki pages" in response.text
    assert "1 generated source summaries" in response.text
    assert "Recent durable activity" in response.text
    assert "succeeded run run-home" in response.text
    assert "Inspect next" in response.text
    assert "Raw workspace counts" in response.text


def test_browse_page_lists_wiki_and_planning_documents(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "web-shell.md",
        title="Web shell",
        page_id="concept-web-shell",
        body="# Web shell\n",
    )
    create_task(
        tmp_path,
        "Ship web shell",
        record_id="task-ship-web-shell",
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/browse")

    assert response.status_code == 200
    assert "Web shell" in response.text
    assert "Ship web shell" in response.text
    assert "wiki/concepts/web-shell.md" in response.text
    assert "planning/tasks/task-ship-web-shell.md" in response.text


def test_home_and_browse_listing_do_not_parse_full_documents(tmp_path: Path, monkeypatch) -> None:
    initialize_workspace(tmp_path)
    wiki_path = tmp_path / "wiki" / "concepts" / "large-web-shell.md"
    write_wiki_page(
        wiki_path,
        title="Large web shell",
        page_id="concept-large-web-shell",
        body="# Large web shell\n\n" + ("Body text that listing should not parse.\n" * 500),
    )
    create_task(
        tmp_path,
        "Track web scaling",
        record_id="task-track-web-scaling",
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )

    def fail_detail(*args, **kwargs):
        raise AssertionError("listing should not use full document detail parsing")

    def fail_wiki_parse(*args, **kwargs):
        raise AssertionError("listing should not parse full wiki documents")

    def fail_planning_parse(*args, **kwargs):
        raise AssertionError("listing should not parse full planning documents")

    monkeypatch.setattr(web, "_document_detail", fail_detail)
    monkeypatch.setattr(web, "parse_wiki_markdown", fail_wiki_parse)
    monkeypatch.setattr(web, "parse_planning_document", fail_planning_parse)
    client = TestClient(create_app(tmp_path))

    home = client.get("/")
    browse = client.get("/browse")

    assert home.status_code == 200
    assert browse.status_code == 200
    assert "Large web shell" in browse.text
    assert "Track web scaling" in browse.text
    assert "wiki/concepts/large-web-shell.md" in browse.text
    assert "planning/tasks/task-track-web-scaling.md" in browse.text


def test_listing_metadata_stops_after_frontmatter_title(tmp_path: Path) -> None:
    path = tmp_path / "listing.md"
    path.write_text(
        "---\n"
        "title: Bounded listing\n"
        "kind: concept\n"
        "status: active\n"
        "---\n"
        "# Body heading that should not be needed\n" + ("body\n" * 100),
        encoding="utf-8",
    )

    metadata = web._read_listing_metadata(path)

    assert metadata == {
        "title": "Bounded listing",
        "kind": "concept",
        "status": "active",
    }


def test_listing_frontmatter_scan_is_bounded_for_malformed_documents() -> None:
    handle = io.StringIO("title: Never closed\n" * (web._LISTING_FRONTMATTER_LINE_LIMIT + 25))

    metadata = web._read_bounded_frontmatter_lines(handle)

    assert metadata is None
    assert handle.readline() != ""


def test_listing_heading_scan_is_bounded_for_frontmatter_light_documents() -> None:
    handle = io.StringIO("body without heading\n" * (web._LISTING_HEADING_LINE_LIMIT + 25))

    heading = web._read_bounded_heading(handle)

    assert heading is None
    assert handle.readline() != ""


def test_browse_page_separates_index_and_log_as_special_files(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/browse")

    assert response.status_code == 200
    assert "No searchable content records yet." in response.text
    assert "Special files" in response.text
    assert "excluded from search results" in response.text
    assert "wiki/index.md" in response.text
    assert "wiki/log.md" in response.text


def test_document_detail_renders_markdown_and_metadata(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "web-shell.md",
        title="Web shell",
        page_id="concept-web-shell",
        body="# Web shell\n\nThis page describes local browsing.\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/wiki/concepts/web-shell.md")

    assert response.status_code == 200
    assert "<h1>Web shell</h1>" in response.text
    assert "This page describes local browsing." in response.text
    assert "concept-web-shell" in response.text
    assert "active" in response.text
    assert '<details class="technical">' in response.text
    assert response.text.index("<article") < response.text.index('<details class="technical">')


def test_document_detail_keeps_human_badges_before_body(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "reviewed.md",
        title="Reviewed page",
        page_id="concept-reviewed",
        body="# Reviewed page\n\nReadable body comes after compact badges.\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/wiki/concepts/reviewed.md")

    assert response.status_code == 200
    assert '<section class="badges">' in response.text
    assert "<strong>Class</strong> wiki" in response.text
    assert "<strong>Kind</strong> concept" in response.text
    assert "<strong>Status</strong> active" in response.text
    assert response.text.index('<section class="badges">') < response.text.index("<article")
    assert response.text.index("<article") < response.text.index('<details class="technical">')


def test_document_detail_preserves_full_metadata_access(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "metadata.md",
        title="Metadata page",
        page_id="concept-metadata",
        body="# Metadata page\n\nReadable body stays primary.\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/wiki/concepts/metadata.md")

    assert response.status_code == 200
    assert "<summary>Technical metadata</summary>" in response.text
    assert "&quot;page_id&quot;: &quot;concept-metadata&quot;" in response.text
    assert "&quot;confidence&quot;: 0.8" in response.text


def test_document_detail_renders_planning_task(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_task(
        tmp_path,
        "Ship web shell",
        record_id="task-ship-web-shell",
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/planning/tasks/task-ship-web-shell.md")

    assert response.status_code == 200
    assert "Ship web shell" in response.text
    assert "todo" in response.text


def test_planning_page_lists_and_links_all_planning_kinds(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_milestone(
        tmp_path,
        "Milestone UI",
        record_id="milestone-ui",
        status="active",
        target_date="2026-05-01",
        task_refs=["task-ship-planning-ui"],
        decision_refs=["decision-read-only-web"],
        question_refs=["question-runtime-state"],
    )
    create_task(
        tmp_path,
        "Ship planning UI",
        record_id="task-ship-planning-ui",
        status="in_progress",
        priority="high",
        owner="codex",
        milestone_refs=["milestone-ui"],
        decision_refs=["decision-read-only-web"],
        question_refs=["question-runtime-state"],
        depends_on=[],
        source_refs=[],
    )
    create_decision(
        tmp_path,
        "Keep web read only",
        record_id="decision-read-only-web",
        status="accepted",
        decided_at="2026-04-30",
        supersedes=[],
        source_refs=[],
        related_tasks=["task-ship-planning-ui"],
        related_questions=["question-runtime-state"],
    )
    create_question(
        tmp_path,
        "How visible should runtime state be",
        record_id="question-runtime-state",
        status="open",
        source_refs=[],
        related_tasks=["task-ship-planning-ui"],
        related_decisions=["decision-read-only-web"],
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/planning")

    assert response.status_code == 200
    assert "Tasks" in response.text
    assert "Milestones" in response.text
    assert "Decisions" in response.text
    assert "Questions" in response.text
    assert 'href="/documents/planning/tasks/task-ship-planning-ui.md"' in response.text
    assert 'href="/documents/planning/milestones/milestone-ui.md"' in response.text
    assert 'href="/documents/planning/decisions/decision-read-only-web.md"' in response.text
    assert 'href="/documents/planning/questions/question-runtime-state.md"' in response.text
    assert "priority=high" in response.text
    assert "owner=codex" in response.text


def test_planning_kind_page_lists_one_kind_and_rejects_unknown_kind(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_task(
        tmp_path,
        "Ship planning UI",
        record_id="task-ship-planning-ui",
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )
    client = TestClient(create_app(tmp_path))

    tasks = client.get("/planning/tasks")
    missing = client.get("/planning/sources")

    assert tasks.status_code == 200
    assert "Ship planning UI" in tasks.text
    assert "planning/tasks/task-ship-planning-ui.md" in tasks.text
    assert missing.status_code == 404
    assert "Planning kind not found" in missing.text


def test_planning_page_reports_invalid_records_without_path_leak(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    bad_task = tmp_path / "planning" / "tasks" / "task-bad.md"
    bad_task.write_text("---\nkind: task\ntask_id: task-bad\nbogus: true\n---\n", encoding="utf-8")
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    response = client.get("/planning")

    assert response.status_code == 500
    assert "invalid planning records" in response.text
    assert str(bad_task) not in response.text


def test_runs_and_queue_pages_show_empty_states(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    runs = client.get("/runs")
    queue = client.get("/queue")

    assert runs.status_code == 200
    assert "No run records yet." in runs.text
    assert "does not start, retry, or mutate jobs" in runs.text
    assert queue.status_code == 200
    assert "No queue records yet." in queue.text
    assert "Queue state is read-only here" in queue.text


def test_runs_and_queue_pages_show_runtime_state(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    write_queue_item(
        layout.queue_dir / "ingest-src-web.json",
        QueueItemRecord(
            job_id="ingest-src-web",
            job_type="ingest_source",
            status="failed",
            created_at="2026-04-30T10:00:00+00:00",
            updated_at="2026-04-30T10:05:00+00:00",
            attempt_count=2,
            max_attempts=3,
            payload_ref="state/manifests/sources/src-web.json",
            last_error="source missing",
        ),
    )
    write_run_record(
        layout.runs_dir / "run-src-web.json",
        RunRecord(
            run_id="run-src-web",
            job_id="ingest-src-web",
            job_type="ingest_source",
            started_at="2026-04-30T10:01:00+00:00",
            finished_at="2026-04-30T10:02:00+00:00",
            status="failed",
            input_refs=["state/manifests/sources/src-web.json"],
            output_refs=[],
            errors=["source missing"],
            pipeline_version="test",
            source_ids=["src-web"],
            page_refs=["wiki/sources/src-web.md"],
        ),
    )
    client = TestClient(create_app(tmp_path))

    runs = client.get("/runs")
    queue = client.get("/queue")

    assert runs.status_code == 200
    assert "run-src-web" in runs.text
    assert "ingest-src-web" in runs.text
    assert "wiki/sources/src-web.md" in runs.text
    assert "source missing" in runs.text
    assert "state/runs/run-src-web.json" in runs.text
    assert queue.status_code == 200
    assert "failed=1" in queue.text
    assert "2/3" in queue.text
    assert "2026-04-30T10:00:00+00:00" in queue.text
    assert "2026-04-30T10:05:00+00:00" in queue.text
    assert "source missing" in queue.text
    assert "state/queue/ingest-src-web.json" in queue.text


def test_runs_and_queue_pages_report_invalid_records_without_path_leak(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    bad_run = tmp_path / "state" / "runs" / "run-bad.json"
    bad_queue = tmp_path / "state" / "queue" / "queue-bad.json"
    bad_run.write_text("{not valid json", encoding="utf-8")
    bad_queue.write_text("{not valid json", encoding="utf-8")
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    runs = client.get("/runs")
    queue = client.get("/queue")

    assert runs.status_code == 500
    assert "invalid run records" in runs.text
    assert str(bad_run) not in runs.text
    assert queue.status_code == 500
    assert "invalid queue records" in queue.text
    assert str(bad_queue) not in queue.text


def test_runs_and_queue_pages_report_schema_invalid_records_without_path_leak(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    bad_run = tmp_path / "state" / "runs" / "run-schema-bad.json"
    bad_queue = tmp_path / "state" / "queue" / "queue-schema-bad.json"
    bad_run.write_text('{"kind": "run", "run_id": "run-schema-bad"}\n', encoding="utf-8")
    bad_queue.write_text(
        '{"kind": "queue_item", "job_id": "queue-schema-bad"}\n',
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    runs = client.get("/runs")
    queue = client.get("/queue")

    assert runs.status_code == 500
    assert "invalid run records" in runs.text
    assert str(bad_run) not in runs.text
    assert queue.status_code == 500
    assert "invalid queue records" in queue.text
    assert str(bad_queue) not in queue.text


def test_document_detail_falls_back_for_invalid_planning_frontmatter(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    task_path = tmp_path / "planning" / "tasks" / "task-bad.md"
    task_path.write_text("# Broken Task\n\nThis task has no frontmatter.\n", encoding="utf-8")
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/planning/tasks/task-bad.md")

    assert response.status_code == 200
    assert "Broken Task" in response.text
    assert "This task has no frontmatter." in response.text


def test_search_returns_query_matches_with_document_links(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "web-shell.md",
        title="Web shell",
        page_id="concept-web-shell",
        body="# Web shell\n\nDeterministic browse search lives here.\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/search", params={"q": "browse search"})

    assert response.status_code == 200
    assert 'href="/documents/wiki/concepts/web-shell.md"' in response.text
    assert "Deterministic browse search lives here." in response.text


def test_status_page_shows_source_run_and_review_counts(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "status-source.md"
    source.write_text("# Status source\n\nWeb status should show source state.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    client = TestClient(create_app(tmp_path))

    response = client.get("/status")

    assert response.status_code == 200
    assert "Synthesis follow-up" in response.text
    assert added.source_id in response.text
    assert f'href="/sources/{added.source_id}"' in response.text
    assert "wiki/sources/" in response.text
    assert "machine-generated" in response.text


def test_status_page_reports_invalid_source_manifest_without_path_leak(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    manifest_path = tmp_path / "state" / "manifests" / "sources" / "src-bad.json"
    manifest_path.write_text("{not valid json", encoding="utf-8")
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    response = client.get("/status")

    assert response.status_code == 500
    assert "invalid records" in response.text
    assert str(tmp_path) not in response.text


def test_source_detail_shows_summary_run_and_synthesis_suggestions(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "dogfood-workflow.md"
    source.write_text(
        "# Dogfood workflow\n\nDogfood workflow polish improves review handoff.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "dogfood-workflow.md",
        title="Dogfood workflow",
        page_id="topic-dogfood-workflow",
        body="# Dogfood workflow\n\nReview handoff uses dogfood workflow polish.\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get(f"/sources/{added.source_id}")

    assert response.status_code == 200
    assert "Generated source-summary pages" in response.text
    assert "Latest ingest run" in response.text
    assert "Affected synthesis-page suggestions" in response.text
    assert "wiki/sources/" in response.text
    assert "Dogfood workflow" in response.text
    assert "wiki/topics/dogfood-workflow.md" in response.text


def test_source_detail_reports_invalid_linked_run_without_path_leak(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "invalid-run.md"
    source.write_text("# Invalid run\n\nSource with a corrupt run record.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    main(["--root", str(tmp_path), "ingest", added.source_id])
    manifest_path = tmp_path / "state" / "manifests" / "sources" / f"{added.source_id}.json"
    run_id = load_source_record(manifest_path).last_run_id
    assert run_id is not None
    (tmp_path / "state" / "runs" / f"{run_id}.json").write_text("{not valid json", encoding="utf-8")
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    response = client.get(f"/sources/{added.source_id}")

    assert response.status_code == 200
    assert "Linked run record" in response.text
    assert "is invalid" in response.text
    assert str(tmp_path) not in response.text


def test_source_detail_returns_not_found_for_unknown_source_id(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/sources/src-missing")

    assert response.status_code == 404
    assert "Source not found" in response.text


def test_document_detail_rejects_unsafe_or_unsupported_paths(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    traversal = client.get("/documents/%2E%2E/pyproject.toml")
    backslash_traversal = client.get("/documents/wiki%5C..%5Csplendor.yaml")
    non_markdown = client.get("/documents/wiki/secrets.yaml")
    unsupported_root = client.get("/documents/raw/source.md")

    assert traversal.status_code == 404
    assert backslash_traversal.status_code == 404
    assert non_markdown.status_code == 404
    assert unsupported_root.status_code == 404


def test_search_returns_generic_error_for_invalid_workspace_record(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    bad_page = tmp_path / "wiki" / "concepts" / "bad.md"
    bad_page.write_text("---\nkind: concept\nbogus: true\n---\n\nbad body\n", encoding="utf-8")
    client = TestClient(create_app(tmp_path))

    response = client.get("/search", params={"q": "bad"})

    assert response.status_code == 500
    assert "invalid records" in response.text
    assert str(bad_page) not in response.text


def test_search_returns_bad_request_for_invalid_query_text(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/search", params={"q": "!!!"})

    assert response.status_code == 400
    assert "Query must contain at least one ASCII letter or number" in response.text


def test_search_empty_state_mentions_special_files_for_sparse_workspace(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/search", params={"q": "splendor"})

    assert response.status_code == 200
    assert "special navigation files" in response.text
    assert "excluded from search" in response.text
    assert "uv run splendor repo refresh" in response.text


def test_document_links_respect_custom_layout_directories(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\n"
        "project_name: custom\n"
        "layout:\n"
        "  wiki_dir: knowledge\n"
        "  planning_dir: plans\n",
        encoding="utf-8",
    )
    initialize_workspace(tmp_path)
    (tmp_path / "knowledge" / "index.md").write_text(
        "# Custom Knowledge\n\nCustom layout identity.\n",
        encoding="utf-8",
    )
    write_wiki_page(
        tmp_path / "knowledge" / "concepts" / "web-shell.md",
        title="Custom web shell",
        page_id="concept-custom-web-shell",
        body="# Custom web shell\n",
    )
    client = TestClient(create_app(tmp_path))

    browse = client.get("/browse")
    detail = client.get("/documents/knowledge/concepts/web-shell.md")
    empty_search = client.get("/search")
    missing_document = client.get("/documents/knowledge/missing.md")

    assert browse.status_code == 200
    assert 'href="/documents/knowledge/concepts/web-shell.md"' in browse.text
    assert detail.status_code == 200
    assert "<h1>Custom web shell</h1>" in detail.text
    assert empty_search.status_code == 200
    assert "<h1>Custom Knowledge</h1>" in empty_search.text
    assert '<h2 class="page-title">Search</h2>' in empty_search.text
    assert missing_document.status_code == 404
    assert "<h1>Custom Knowledge</h1>" in missing_document.text
    assert '<h2 class="page-title">Not Found</h2>' in missing_document.text


def test_web_routes_reject_layout_roots_that_escape_workspace(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\n"
        "project_name: custom\n"
        "layout:\n"
        "  wiki_dir: ..\n"
        "  planning_dir: planning\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    response = client.get("/")

    assert response.status_code == 500
    assert "Workspace configuration is invalid." in response.text


def test_search_rejects_layout_roots_that_escape_workspace(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\n"
        "project_name: custom\n"
        "layout:\n"
        "  wiki_dir: ..\n"
        "  planning_dir: planning\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    response = client.get("/search", params={"q": "secret"})

    assert response.status_code == 500
    assert "Workspace configuration is invalid." in response.text


def test_document_detail_preserves_code_text_while_sanitizing_html(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "code.md",
        title="Code",
        page_id="concept-code",
        body="# Code\n\n```python\nx < y && y > z\n```\n\n<script>alert('x')</script>\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/wiki/concepts/code.md")

    assert response.status_code == 200
    assert "x &lt; y &amp;&amp; y &gt; z" in response.text
    assert "x &amp;lt; y" not in response.text
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;alert" in response.text


def test_document_detail_escapes_raw_html_in_markdown(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "unsafe.md",
        title="Unsafe",
        page_id="concept-unsafe",
        body="# Unsafe\n\n<script>alert('x')</script>\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/wiki/concepts/unsafe.md")

    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;alert" in response.text
