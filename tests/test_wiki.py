from splendor.utils.wiki import update_index_content


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
