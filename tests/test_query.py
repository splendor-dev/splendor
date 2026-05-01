import json
from pathlib import Path

import yaml

from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.commands.planning import create_question, create_task
from splendor.commands.query import run_query
from splendor.schemas import KnowledgePageFrontmatter
from splendor.state.query_snapshot import load_query_snapshot


def write_wiki_page(
    path: Path,
    *,
    title: str,
    page_id: str,
    kind: str = "concept",
    status: str = "active",
    source_refs: list[str] | None = None,
    generated_by_run_ids: list[str] | None = None,
    tags: list[str] | None = None,
    contradictions: list[dict] | None = None,
    body: str = "",
) -> None:
    frontmatter = KnowledgePageFrontmatter(
        kind=kind,
        title=title,
        page_id=page_id,
        status=status,
        source_refs=source_refs or [],
        generated_by_run_ids=generated_by_run_ids or [],
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


def test_run_query_returns_ranked_matches_from_wiki_and_planning(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "query-ranking.md",
        title="Query ranking overview",
        page_id="concept-query-ranking",
        source_refs=["src-123"],
        generated_by_run_ids=["run-123"],
        tags=["ranking"],
        body="# Query ranking overview\n\nThis page explains deterministic query ranking.\n",
    )
    create_question(
        tmp_path,
        "How should query ranking work",
        record_id=None,
        status="open",
        source_refs=["src-123"],
        related_tasks=[],
        related_decisions=[],
    )

    result = run_query(tmp_path, "query ranking")

    assert result.match_count == 2
    assert {match.document_class for match in result.matches} == {"planning", "wiki"}
    assert {match.kind for match in result.matches} == {"question", "concept"}
    wiki_match = next(match for match in result.matches if match.document_class == "wiki")
    assert wiki_match.generated_by_run_ids == ["run-123"]
    assert wiki_match.source_refs == ["src-123"]
    assert wiki_match.review_state == "draft"
    assert wiki_match.last_generated_at is None
    assert wiki_match.provenance_links == []
    assert wiki_match.contradiction_count == 0
    assert wiki_match.review_task_ids == []


def test_run_query_filters_by_wiki_tag(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "preprocessing.md",
        title="Preprocessing pipeline",
        page_id="topic-preprocessing-pipeline",
        tags=["preprocessing", "audio"],
        body="Lowpass filter notes for the preprocessing pipeline.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "deployment.md",
        title="Deployment pipeline",
        page_id="topic-deployment-pipeline",
        tags=["deployment"],
        body="Deployment pipeline notes mention preprocessing only as background.",
    )

    result = run_query(tmp_path, "pipeline", tags=["preprocessing"])

    assert result.filters.tags == ["preprocessing"]
    assert [match.path for match in result.matches] == ["wiki/topics/preprocessing.md"]


def test_run_query_filters_by_source_ref_and_allows_filter_only_lookup(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "briefing.md",
        title="Briefing notes",
        page_id="topic-briefing-notes",
        source_refs=[added.source_id],
        body="Briefing notes carry source-backed context.",
    )
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "other.md",
        title="Other notes",
        page_id="topic-other-notes",
        body="Other notes do not reference the source.",
    )

    result = run_query(tmp_path, "", source_id=added.source_id)

    assert result.query == ""
    assert result.filters.source_id == added.source_id
    assert result.match_count == 1
    assert result.matches[0].path == "wiki/topics/briefing.md"


def test_run_query_rejects_unknown_source_filter(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    try:
        run_query(tmp_path, "briefing", source_id="src-missing")
    except FileNotFoundError as exc:
        assert str(exc) == "Unknown source ID: src-missing"
    else:
        raise AssertionError("Expected unknown source filter failure")


def test_run_query_excludes_index_and_log(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "wiki" / "index.md").write_text(
        "# Splendor Wiki Index\n\nsecretphrase\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "log.md").write_text(
        "# Splendor Wiki Log\n\nsecretphrase\n",
        encoding="utf-8",
    )

    result = run_query(tmp_path, "secretphrase")

    assert result.match_count == 0


def test_run_query_respects_custom_layout_directories(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\n"
        "project_name: custom\n"
        "layout:\n"
        "  wiki_dir: knowledge\n"
        "  planning_dir: plans\n",
        encoding="utf-8",
    )
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "knowledge" / "topics" / "deterministic-query.md",
        title="Deterministic query",
        page_id="topic-deterministic-query",
        body="# Deterministic query\n\nThis wiki page mentions retrieval.\n",
    )
    create_task(
        tmp_path,
        "Ship query",
        record_id=None,
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )

    result = run_query(tmp_path, "query")

    assert {match.path for match in result.matches} == {
        "knowledge/topics/deterministic-query.md",
        "plans/tasks/task-ship-query.md",
    }


def test_run_query_fails_for_invalid_planning_frontmatter(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    bad_task = tmp_path / "planning" / "tasks" / "task-bad.md"
    bad_task.write_text("---\nkind: task\nbogus: true\n---\n", encoding="utf-8")

    try:
        run_query(tmp_path, "task")
    except ValueError as exc:
        assert "Planning record" in str(exc)
    else:
        raise AssertionError("Expected invalid planning record failure")


def test_run_query_fails_for_invalid_wiki_frontmatter(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    bad_page = tmp_path / "wiki" / "concepts" / "bad.md"
    bad_page.write_text("---\nkind: concept\nbogus: true\n---\n", encoding="utf-8")

    try:
        run_query(tmp_path, "concept")
    except ValueError as exc:
        assert "Wiki page" in str(exc)
    else:
        raise AssertionError("Expected invalid wiki page failure")


def test_run_query_prefers_title_and_id_hits_over_body_only_hits(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_task(
        tmp_path,
        "General note",
        record_id="task-body-only",
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )
    body_only_path = tmp_path / "planning" / "tasks" / "task-body-only.md"
    body_only_path.write_text(
        (
            body_only_path.read_text(encoding="utf-8")
            + "\nThis note mentions ranking in the body only.\n"
        ),
        encoding="utf-8",
    )
    create_question(
        tmp_path,
        "Ranking strategy",
        record_id="question-ranking-strategy",
        status="open",
        source_refs=[],
        related_tasks=[],
        related_decisions=[],
    )

    result = run_query(tmp_path, "ranking")

    assert result.matches[0].record_id == "question-ranking-strategy"
    assert result.matches[1].record_id == "task-body-only"


def test_run_query_uses_best_matching_snippet_and_truncates(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    long_text = " ".join(["padding"] * 80)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "snippets.md",
        title="Snippet behavior",
        page_id="topic-snippet-behavior",
        body=(
            "# Snippet behavior\n\n"
            f"{long_text}\n\n"
            "The retrieval snippet should include the ranking evidence line exactly once.\n"
        ),
    )

    result = run_query(tmp_path, "ranking evidence")

    assert result.matches[0].snippet == (
        "The retrieval snippet should include the ranking evidence line exactly once."
    )


def test_run_query_prefers_claim_sections_over_source_summary_boilerplate(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "sources" / "src-claim.md",
        title="Generated source summary",
        page_id="src-claim",
        kind="source-summary",
        source_refs=["src-claim"],
        body=(
            "# Generated source summary\n\n"
            "## Key Facts\n\n"
            "- Source ID: src-claim\n"
            "- Source type: markdown\n\n"
            "## Core Claims\n\n"
            "Dogfood workflow polish should keep source-summary pages separate from "
            "maintained synthesis pages.\n"
        ),
    )

    result = run_query(tmp_path, "source summary pages")

    assert result.matches[0].snippet == (
        "Dogfood workflow polish should keep source-summary pages separate from maintained "
        "synthesis pages."
    )


def test_run_query_ignores_fenced_blocks_when_selecting_snippets(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "topics" / "fenced-snippet.md",
        title="Fenced snippet",
        page_id="topic-fenced-snippet",
        body=(
            "# Fenced snippet\n\n"
            "```text\n"
            "ranking evidence inside generated fenced metadata should not win\n"
            "```\n\n"
            "The prose ranking evidence should become the selected snippet.\n"
        ),
    )

    result = run_query(tmp_path, "ranking evidence")

    assert result.matches[0].snippet == (
        "The prose ranking evidence should become the selected snippet."
    )


def test_run_query_result_is_json_serializable(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_task(
        tmp_path,
        "Ship query",
        record_id=None,
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )

    result = run_query(tmp_path, "query")
    payload = {
        "query": result.query,
        "summary": result.summary,
        "match_count": result.match_count,
        "matches": [match.__dict__ for match in result.matches],
    }

    parsed = json.loads(json.dumps(payload))
    assert parsed["query"] == "query"
    assert parsed["match_count"] == 1
    assert parsed["matches"][0]["path"] == "planning/tasks/task-ship-query.md"


def test_run_query_surfaces_wiki_provenance_fields(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
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
                "path_ref": "state/manifests/sources/src-123.json",
                "role": "generated-from",
            }
        ],
    )
    path = tmp_path / "wiki" / "sources" / "src-123.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    path.write_text(f"---\n{frontmatter_text}\n---\n\nGenerated body\n", encoding="utf-8")

    result = run_query(tmp_path, "generated")

    match = result.matches[0]
    assert match.review_state == "machine-generated"
    assert match.last_generated_at == "2026-04-22T10:00:00+00:00"
    assert match.provenance_links[0].run_id == "run-123"


def test_run_query_surfaces_contradiction_counts_and_review_tasks(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "sources" / "src-123.md",
        title="Generated source summary",
        page_id="src-123",
        kind="source-summary",
        status="active",
        source_refs=["src-123"],
        generated_by_run_ids=["run-123"],
        contradictions=[
            {
                "contradiction_id": "contradiction-src-123-src-456-1234567890",
                "summary": "The pages disagree about the active storage mode.",
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
        body=(
            "## Source\n\n- Source ID: `src-123`\n\n"
            "## Summary\n\nGenerated summary.\n\n"
            "## Key Facts\n\n- Fact\n\n"
            "## Contradictions\n\n"
            "- Contradiction.\n\n"
            "## Provenance\n\n- Run ID: `run-123`\n"
        ),
    )

    result = run_query(tmp_path, "generated")

    match = result.matches[0]
    assert match.contradiction_count == 1
    assert match.review_task_ids == ["task-review-src-123-src-456-1234567890"]


def test_run_query_ranks_dogfood_concept_above_review_task_noise(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "llm-wiki-pattern.md",
        title="LLM Wiki Persistent Knowledge",
        page_id="concept-llm-wiki-persistent-knowledge",
        kind="concept",
        tags=["llm-wiki", "persistent-knowledge"],
        body=(
            "# LLM Wiki Persistent Knowledge\n\n"
            "LLM Wiki persistent knowledge keeps durable project memory in markdown pages "
            "that agents can search and inspect.\n"
        ),
    )
    create_task(
        tmp_path,
        "Review contradiction: LLM Wiki persistent knowledge source summary path mismatch",
        record_id="task-review-llm-wiki-persistent-knowledge-source-summary-path-mismatch",
        status="todo",
        priority="high",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
        page_refs=[],
        run_refs=[],
    )

    result = run_query(tmp_path, "LLM Wiki persistent knowledge")

    assert result.match_count >= 2
    assert result.matches[0].path == "wiki/concepts/llm-wiki-pattern.md"
    assert result.matches[1].path == (
        "planning/tasks/task-review-llm-wiki-persistent-knowledge-source-summary-path-mismatch.md"
    )


def test_query_snapshot_schema_round_trip(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_task(
        tmp_path,
        "Ship query",
        record_id=None,
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )

    result = run_query(tmp_path, "query")
    snapshot_path = tmp_path / "state" / "queries" / "last-query.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "query": result.query,
                "summary": result.summary,
                "match_count": result.match_count,
                "created_at": "2026-04-18T00:00:00+00:00",
                "matches": [match.__dict__ for match in result.matches],
            }
        ),
        encoding="utf-8",
    )

    snapshot = load_query_snapshot(snapshot_path)
    assert snapshot.query == "query"
    assert snapshot.matches[0].record_id == "task-ship-query"
