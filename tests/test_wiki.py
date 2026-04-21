import pytest

from splendor.commands.init import initialize_workspace
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter
from splendor.utils.wiki import (
    WikiUpdatePayload,
    apply_wiki_updates,
    parse_wiki_markdown,
    render_frontmatter,
    update_index_content,
)


def test_update_index_content_replaces_existing_source_entry_by_source_id() -> None:
    original = (
        "# Splendor Wiki Index\n\n## Sources\n\n- [Old title](sources/old-page.md) (`src-123`)\n"
    )

    updated = update_index_content(
        original,
        source_id="src-123",
        title="New title",
        page_name="new-page.md",
    )

    assert "- [Old title](sources/old-page.md) (`src-123`)" not in updated
    assert "- [New title](sources/new-page.md) (`src-123`)" in updated
    assert updated.count("(`src-123`)") == 1


def test_parse_wiki_markdown_rejects_invalid_yaml(tmp_path) -> None:
    page = tmp_path / "bad.md"
    page.write_text("---\nkind: [\n---\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        parse_wiki_markdown(page)


def test_parse_wiki_markdown_rejects_schema_failure(tmp_path) -> None:
    page = tmp_path / "bad.md"
    page.write_text("---\nkind: concept\ntitle: Missing page id\n---\n", encoding="utf-8")

    with pytest.raises(ValueError, match="failed schema validation"):
        parse_wiki_markdown(page)


def test_parse_wiki_markdown_accepts_valid_page(tmp_path) -> None:
    record = KnowledgePageFrontmatter(
        kind="concept",
        title="Valid",
        page_id="concept-valid",
        status="active",
        confidence=1.0,
        source_refs=[],
        related_pages=[],
    )
    page = tmp_path / "valid.md"
    page.write_text(
        f"---\n{render_frontmatter(record)}\n---\n\nBody.\n",
        encoding="utf-8",
    )

    parsed = parse_wiki_markdown(page)

    assert parsed.frontmatter.page_id == "concept-valid"
    assert "Body." in parsed.body


def test_apply_wiki_updates_rolls_back_when_extra_write_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_workspace(tmp_path)
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    page_path = layout.wiki_dir / "topics" / "answer.md"
    original_index = layout.index_file.read_text(encoding="utf-8")
    original_log = layout.log_file.read_text(encoding="utf-8")
    extra_path = tmp_path / "planning" / "questions" / "question.md"

    import splendor.utils.wiki as wiki_module

    original_write_text_atomic = wiki_module.write_text_atomic

    def fail_on_extra(path, content):
        if path == extra_path:
            raise OSError("disk full")
        return original_write_text_atomic(path, content)

    monkeypatch.setattr(wiki_module, "write_text_atomic", fail_on_extra)

    with pytest.raises(OSError, match="disk full"):
        apply_wiki_updates(
            layout,
            WikiUpdatePayload(
                page_path=page_path,
                page_content="page content\n",
                index_content=original_index + "\n- changed\n",
                log_content=original_log + "- changed\n",
                extra_writes=[(extra_path, "question content\n")],
            ),
        )

    assert not page_path.exists()
    assert layout.index_file.read_text(encoding="utf-8") == original_index
    assert layout.log_file.read_text(encoding="utf-8") == original_log
    assert not extra_path.exists()
