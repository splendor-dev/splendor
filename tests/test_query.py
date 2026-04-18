import json
from pathlib import Path

import yaml

from splendor.commands.init import initialize_workspace
from splendor.commands.planning import create_question, create_task
from splendor.commands.query import run_query
from splendor.schemas import KnowledgePageFrontmatter


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
    assert result.matches[0].document_class == "planning"
    assert result.matches[0].kind == "question"
    assert result.matches[1].document_class == "wiki"
    assert result.matches[1].generated_by_run_ids == ["run-123"]
    assert result.matches[1].source_refs == ["src-123"]


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
