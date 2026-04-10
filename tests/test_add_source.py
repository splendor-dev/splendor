import json
from pathlib import Path

import pytest

from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace


def test_add_source_registers_and_copies_file(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    result = add_source(tmp_path, source)

    assert result.source_id.startswith("src-")
    assert result.manifest_path.exists()
    assert result.stored_path.exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["kind"] == "source"
    assert manifest["path"].endswith("note.md")
    assert "/" in manifest["path"]
    assert manifest["checksum"]


def test_add_source_is_deduplicated_by_checksum(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    second = add_source(tmp_path, source)

    assert first.source_id == second.source_id
    assert second.already_registered is True


def test_add_source_reuses_existing_stored_copy_for_same_content(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    first_source = tmp_path / "notes.txt"
    second_source = tmp_path / "renamed-notes.txt"
    first_source.write_text("same-content\n", encoding="utf-8")
    second_source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, first_source)
    second = add_source(tmp_path, second_source)

    assert first.source_id == second.source_id
    assert second.stored_path == first.stored_path
    assert not (tmp_path / "raw" / "sources" / first.source_id / "renamed-notes.txt").exists()


def test_add_source_raises_if_existing_manifest_checksum_mismatches(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    manifest["checksum"] = "b" * 64
    first.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Checksum mismatch"):
        add_source(tmp_path, source)
