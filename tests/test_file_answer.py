from pathlib import Path

import pytest

from splendor.commands.file_answer import default_answer_page_id, file_answer_from_last_query
from splendor.commands.init import initialize_workspace
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter, QueryMatchSnapshot, QuerySnapshot
from splendor.state.query_snapshot import last_query_path_for, write_query_snapshot
from splendor.utils.wiki import render_frontmatter


def _write_queryable_page(path: Path, *, title: str, page_id: str, body: str) -> None:
    record = KnowledgePageFrontmatter(
        kind="topic",
        title=title,
        page_id=page_id,
        status="active",
        confidence=1.0,
        source_refs=[],
        related_pages=[],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{render_frontmatter(record)}\n---\n\n{body}", encoding="utf-8")


def test_default_answer_page_id_rejects_degenerate_titles() -> None:
    with pytest.raises(ValueError, match="ASCII letter or number"):
        default_answer_page_id("!!!")


def test_file_answer_from_last_query_requires_saved_snapshot(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    with pytest.raises(ValueError, match="No saved query snapshot found"):
        file_answer_from_last_query(tmp_path, title="Answer", page_id=None)


def test_file_answer_from_last_query_renders_empty_match_snapshots(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    write_query_snapshot(
        last_query_path_for(layout),
        QuerySnapshot(
            query="nothing",
            summary='No matches found for "nothing".',
            match_count=0,
            created_at="2026-04-21T10:00:00+00:00",
            matches=[],
        ),
    )

    result = file_answer_from_last_query(tmp_path, title="No Match Answer", page_id=None)

    page = result.page_path.read_text(encoding="utf-8")
    assert "- No matches were present in the saved query snapshot." in page
    assert "## Provenance" in page
    assert "Filed from saved query snapshot" in page


def test_file_answer_from_last_query_dedupes_source_refs(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    write_query_snapshot(
        last_query_path_for(layout),
        QuerySnapshot(
            query="ranking",
            summary="Ranking summary",
            match_count=2,
            created_at="2026-04-21T10:00:00+00:00",
            matches=[
                QueryMatchSnapshot(
                    rank=1,
                    score=9,
                    document_class="wiki",
                    kind="topic",
                    record_id="topic-ranking",
                    title="Ranking",
                    path="wiki/topics/ranking.md",
                    status="active",
                    snippet="Ranking evidence.",
                    source_refs=["src-1", "src-2"],
                    generated_by_run_ids=[],
                    tags=[],
                ),
                QueryMatchSnapshot(
                    rank=2,
                    score=8,
                    document_class="wiki",
                    kind="topic",
                    record_id="topic-ranking-2",
                    title="Ranking Follow-up",
                    path="wiki/topics/ranking-2.md",
                    status="active",
                    snippet="More ranking evidence.",
                    source_refs=["src-2", "src-3"],
                    generated_by_run_ids=[],
                    tags=[],
                ),
            ],
        ),
    )

    result = file_answer_from_last_query(tmp_path, title="Ranking Answer", page_id=None)

    page = result.page_path.read_text(encoding="utf-8")
    assert "source_refs:\n- src-1\n- src-2\n- src-3\n" in page
