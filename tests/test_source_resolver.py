from pathlib import Path

import pytest

from splendor.schemas import SourceRecord
from splendor.state.source_resolver import resolve_source_content


def make_source_record(**overrides: object) -> SourceRecord:
    payload: dict[str, object] = {
        "source_id": "src-1234567890abcdef",
        "title": "Spec",
        "source_type": "md",
        "path": "raw/sources/src-1234567890abcdef/spec.md",
        "checksum": "a" * 64,
        "added_at": "2026-04-10T15:00:00+00:00",
        "pipeline_version": "0.1.0a0",
    }
    payload.update(overrides)
    return SourceRecord(**payload)


def test_resolve_source_content_legacy_manifest_uses_stored_copy(tmp_path: Path) -> None:
    stored_path = tmp_path / "raw" / "sources" / "src-1234567890abcdef" / "spec.md"
    stored_path.parent.mkdir(parents=True)
    stored_path.write_text("hello\n", encoding="utf-8")
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
        original_path="docs/spec.md",
    )

    resolved = resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")

    assert resolved.canonical_ref == "docs/spec.md"
    assert resolved.canonical_ref_kind == "stored_artifact"
    assert resolved.storage_mode == "copy"
    assert resolved.resolved_path == stored_path.resolve()
    assert resolved.resolved_ref == "raw/sources/src-1234567890abcdef/spec.md"
    assert resolved.content_origin_label == "Stored source"


def test_resolve_source_content_explicit_copy_uses_storage_path(tmp_path: Path) -> None:
    stored_path = tmp_path / "raw" / "sources" / "src-1234567890abcdef" / "copy.md"
    stored_path.parent.mkdir(parents=True)
    stored_path.write_text("hello\n", encoding="utf-8")
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="copy",
        storage_path="raw/sources/src-1234567890abcdef/copy.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    resolved = resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")

    assert resolved.resolved_ref == "raw/sources/src-1234567890abcdef/copy.md"
    assert resolved.canonical_ref == "docs/spec.md"


def test_resolve_source_content_explicit_copy_falls_back_to_path(tmp_path: Path) -> None:
    stored_path = tmp_path / "raw" / "sources" / "src-1234567890abcdef" / "spec.md"
    stored_path.parent.mkdir(parents=True)
    stored_path.write_text("hello\n", encoding="utf-8")
    source = make_source_record(
        storage_mode="copy",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    resolved = resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")

    assert resolved.resolved_ref == "raw/sources/src-1234567890abcdef/spec.md"


def test_resolve_source_content_workspace_source_uses_repo_relative_ref(tmp_path: Path) -> None:
    source_file = tmp_path / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("hello\n", encoding="utf-8")
    source = make_source_record(
        storage_mode="none",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    resolved = resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")

    assert resolved.canonical_ref == "docs/spec.md"
    assert resolved.canonical_ref_kind == "workspace_path"
    assert resolved.storage_mode == "none"
    assert resolved.resolved_path == source_file.resolve()
    assert resolved.resolved_ref == "docs/spec.md"
    assert resolved.content_origin_label == "Workspace source"


def test_resolve_source_content_workspace_source_rejects_absolute_ref(tmp_path: Path) -> None:
    source = make_source_record(
        storage_mode="none",
        source_ref="/tmp/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="repo-relative"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_workspace_source_rejects_escaping_ref(tmp_path: Path) -> None:
    source = make_source_record(
        storage_mode="none",
        source_ref="../spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="escapes workspace root"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_workspace_source_rejects_missing_file(tmp_path: Path) -> None:
    source = make_source_record(
        storage_mode="none",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="Workspace source is missing"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_workspace_source_rejects_checksum_mismatch(tmp_path: Path) -> None:
    source_file = tmp_path / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("changed\n", encoding="utf-8")
    source = make_source_record(
        storage_mode="none",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    with pytest.raises(ValueError, match="Workspace source checksum mismatch"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


@pytest.mark.parametrize("mode", ["pointer", "symlink"])
def test_resolve_source_content_rejects_unsupported_storage_modes(
    tmp_path: Path, mode: str
) -> None:
    source = make_source_record(
        storage_mode=mode,
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match=f"Unsupported storage mode for ingestion: {mode}"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")
