from pathlib import Path

import pytest

from splendor.schemas import SourcePointerArtifact, SourceRecord
from splendor.state.source_compat import symlink_source_error_label
from splendor.state.source_pointer import write_source_pointer
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


def write_pointer(
    root: Path,
    *,
    source_id: str = "src-1234567890abcdef",
    source_ref: str = "docs/spec.md",
    source_ref_kind: str = "workspace_path",
    checksum: str = "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
) -> Path:
    path = root / "raw" / "sources" / source_id / "pointer.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_source_pointer(
        path,
        SourcePointerArtifact(
            source_id=source_id,
            source_ref=source_ref,
            source_ref_kind=source_ref_kind,
            checksum=checksum,
            created_at="2026-04-10T15:01:00+00:00",
        ),
    )
    return path


def write_symlink_artifact(root: Path, *, source_id: str = "src-1234567890abcdef") -> Path:
    source_file = root / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    artifact = root / "raw" / "sources" / source_id / "spec.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.symlink_to(Path("../../../docs/spec.md"))
    return artifact


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


def test_resolve_source_content_pointer_source_uses_workspace_target(tmp_path: Path) -> None:
    source_file = tmp_path / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("hello\n", encoding="utf-8")
    write_pointer(tmp_path)
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/pointer.json",
        storage_mode="pointer",
        storage_path="raw/sources/src-1234567890abcdef/pointer.json",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    resolved = resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")

    assert resolved.canonical_ref == "docs/spec.md"
    assert resolved.canonical_ref_kind == "workspace_path"
    assert resolved.storage_mode == "pointer"
    assert resolved.resolved_path == source_file.resolve()
    assert resolved.resolved_ref == "docs/spec.md"
    assert resolved.content_origin_label == "Workspace source"


def test_resolve_source_content_pointer_source_rejects_missing_pointer_artifact(
    tmp_path: Path,
) -> None:
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/pointer.json",
        storage_mode="pointer",
        storage_path="raw/sources/src-1234567890abcdef/pointer.json",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="Pointer artifact is missing"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_pointer_source_rejects_malformed_pointer_artifact(
    tmp_path: Path,
) -> None:
    pointer_path = tmp_path / "raw" / "sources" / "src-1234567890abcdef" / "pointer.json"
    pointer_path.parent.mkdir(parents=True)
    pointer_path.write_text("{not-json}\n", encoding="utf-8")
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/pointer.json",
        storage_mode="pointer",
        storage_path="raw/sources/src-1234567890abcdef/pointer.json",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="Pointer artifact is not valid JSON"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_pointer_source_rejects_source_ref_mismatch(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("hello\n", encoding="utf-8")
    write_pointer(tmp_path, source_ref="docs/other.md")
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/pointer.json",
        storage_mode="pointer",
        storage_path="raw/sources/src-1234567890abcdef/pointer.json",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    with pytest.raises(ValueError, match="Pointer artifact source_ref mismatch"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_pointer_source_rejects_missing_workspace_target(
    tmp_path: Path,
) -> None:
    write_pointer(tmp_path)
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/pointer.json",
        storage_mode="pointer",
        storage_path="raw/sources/src-1234567890abcdef/pointer.json",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    with pytest.raises(ValueError, match="Workspace source is missing"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_uses_workspace_target(tmp_path: Path) -> None:
    source_file = tmp_path / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("hello\n", encoding="utf-8")
    write_symlink_artifact(tmp_path)
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    resolved = resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")

    assert resolved.canonical_ref == "docs/spec.md"
    assert resolved.canonical_ref_kind == "workspace_path"
    assert resolved.storage_mode == "symlink"
    assert resolved.resolved_path == source_file.resolve()
    assert resolved.resolved_ref == "docs/spec.md"
    assert resolved.content_origin_label == "Workspace source"


def test_resolve_source_content_symlink_source_rejects_missing_artifact(
    tmp_path: Path,
) -> None:
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="Source symlink artifact is missing"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_absolute_artifact_ref(
    tmp_path: Path,
) -> None:
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="/tmp/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="Symlink artifact path must be repo-relative"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_escaping_artifact_ref(
    tmp_path: Path,
) -> None:
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="../spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="Symlink artifact path escapes workspace root"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_regular_file_artifact(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "raw" / "sources" / "src-1234567890abcdef" / "spec.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("not-a-link\n", encoding="utf-8")
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="Source symlink artifact is not a symlink"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_missing_source_ref(
    tmp_path: Path,
) -> None:
    source = make_source_record(
        storage_mode="symlink",
        source_ref=None,
        source_ref_kind="workspace_path",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
    )

    with pytest.raises(ValueError, match="Symlink-backed source is missing source_ref"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_wrong_source_ref_kind(
    tmp_path: Path,
) -> None:
    source = make_source_record(
        storage_mode="symlink",
        source_ref="docs/spec.md",
        source_ref_kind="external_path",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
    )

    with pytest.raises(ValueError, match="must use source_ref_kind=workspace_path"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_target_outside_workspace(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    artifact = tmp_path / "raw" / "sources" / "src-1234567890abcdef" / "spec.md"
    artifact.parent.mkdir(parents=True)
    artifact.symlink_to(outside)
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
    )

    with pytest.raises(ValueError, match="target escapes workspace root"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_target_mismatch(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "spec.md").write_text("hello\n", encoding="utf-8")
    other = docs / "other.md"
    other.write_text("hello\n", encoding="utf-8")
    artifact = tmp_path / "raw" / "sources" / "src-1234567890abcdef" / "spec.md"
    artifact.parent.mkdir(parents=True)
    artifact.symlink_to(Path("../../../docs/other.md"))
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    with pytest.raises(ValueError, match="target does not match manifest source_ref"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_missing_workspace_target(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "raw" / "sources" / "src-1234567890abcdef" / "spec.md"
    artifact.parent.mkdir(parents=True)
    artifact.symlink_to(Path("../../../docs/spec.md"))
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    with pytest.raises(ValueError, match="Workspace source is missing"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_rejects_checksum_drift(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("changed\n", encoding="utf-8")
    write_symlink_artifact(tmp_path)
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    with pytest.raises(ValueError, match="Workspace source checksum mismatch"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_resolve_source_content_symlink_source_wraps_resolution_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_file = tmp_path / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("hello\n", encoding="utf-8")
    artifact = write_symlink_artifact(tmp_path)
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/spec.md",
        storage_mode="symlink",
        storage_path="raw/sources/src-1234567890abcdef/spec.md",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )
    original_resolve = Path.resolve

    def fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if self == artifact:
            raise RuntimeError("loop")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(ValueError, match="Source symlink artifact could not be resolved"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")


def test_symlink_source_error_label_covers_legacy_shape() -> None:
    legacy = make_source_record(source_ref=None, storage_mode=None)

    assert symlink_source_error_label(legacy) == "Legacy stored source symlink"


def test_resolve_source_content_pointer_source_rejects_checksum_drift(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "docs" / "spec.md"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("changed\n", encoding="utf-8")
    write_pointer(tmp_path)
    source = make_source_record(
        path="raw/sources/src-1234567890abcdef/pointer.json",
        storage_mode="pointer",
        storage_path="raw/sources/src-1234567890abcdef/pointer.json",
        source_ref="docs/spec.md",
        source_ref_kind="workspace_path",
        checksum="5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03",
    )

    with pytest.raises(ValueError, match="Workspace source checksum mismatch"):
        resolve_source_content(tmp_path, source, tmp_path / "raw" / "sources")
