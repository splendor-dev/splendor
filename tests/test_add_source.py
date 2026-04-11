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
    assert manifest["original_path"] == "note.md"


def test_add_source_stores_workspace_relative_original_path(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    nested_dir = tmp_path / "docs"
    nested_dir.mkdir()
    source = nested_dir / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    result = add_source(tmp_path, source)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["original_path"] == "docs/note.md"


def test_add_source_stores_expanded_original_path_for_external_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    source = external_dir / "outside.md"
    source.write_text("# outside\n", encoding="utf-8")

    try:
        result = add_source(tmp_path, source)
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert manifest["original_path"] == str(source)
    finally:
        source.unlink(missing_ok=True)
        external_dir.rmdir()


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


def test_add_source_rejects_manifest_path_outside_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    manifest["path"] = "../escape.txt"
    first.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes workspace root"):
        add_source(tmp_path, source)


def test_add_source_rejects_manifest_path_outside_raw_sources_dir(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    manifest["path"] = "wiki/index.md"
    first.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside the configured raw source storage area"):
        add_source(tmp_path, source)


def test_add_source_rejects_manifest_path_for_wrong_source_dir(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    manifest["path"] = "raw/sources/src-other/notes.txt"
    first.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside the expected source directory"):
        add_source(tmp_path, source)


def test_add_source_rejects_corrupted_existing_stored_copy(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    first.stored_path.write_text("tampered\n", encoding="utf-8")
    first.manifest_path.unlink()

    with pytest.raises(ValueError, match="Stored source checksum mismatch"):
        add_source(tmp_path, source)


def test_add_source_rejects_missing_existing_stored_copy(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    first.stored_path.unlink()

    with pytest.raises(FileNotFoundError, match="Stored source copy is missing"):
        add_source(tmp_path, source)
