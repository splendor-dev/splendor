import subprocess
from pathlib import Path

import pytest

from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.commands.materialize_source import materialize_source
from splendor.state.source_pointer import load_source_pointer
from splendor.state.source_registry import (
    _effective_storage_mode,
    _replace_path,
    _write_workspace_symlink,
    load_source_record,
    materializing_storage_mode_for_source,
    resolve_manifest_storage_path,
    validate_stored_source_location,
    write_source_record,
)


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def init_git_repo(root: Path) -> None:
    git(root, "init")
    git(root, "config", "user.name", "Test User")
    git(root, "config", "user.email", "test@example.com")


def commit_all(root: Path, message: str) -> None:
    git(root, "add", ".")
    git(root, "commit", "-m", message)


def test_add_source_registers_workspace_file_without_copy_by_default(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    result = add_source(tmp_path, source)

    assert result.source_id.startswith("src-")
    assert result.manifest_path.exists()
    assert result.stored_path is None
    assert result.storage_mode == "none"
    assert result.source_ref == "note.md"

    manifest = load_source_record(result.manifest_path)
    assert manifest.kind == "source"
    assert manifest.path == "note.md"
    assert manifest.source_ref == "note.md"
    assert manifest.source_ref_kind == "workspace_path"
    assert manifest.storage_mode == "none"
    assert manifest.storage_path is None
    assert manifest.materialized_at is None
    assert manifest.original_path == "note.md"
    assert not (tmp_path / "raw" / "sources" / result.source_id).exists()


def test_resolve_manifest_storage_path_rejects_absolute_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes workspace root"):
        resolve_manifest_storage_path(tmp_path, "/tmp/source.md")


def test_resolve_manifest_storage_path_rejects_escaping_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes workspace root"):
        resolve_manifest_storage_path(tmp_path, "../outside.md")


def test_validate_stored_source_location_rejects_paths_outside_raw_sources(tmp_path: Path) -> None:
    raw_sources_dir = tmp_path / "raw" / "sources"
    raw_sources_dir.mkdir(parents=True)
    outside = tmp_path / "elsewhere" / "source.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("hello\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the configured raw source storage area"):
        validate_stored_source_location(
            outside,
            raw_sources_dir,
            "src-123",
            "elsewhere/source.md",
        )


def test_validate_stored_source_location_rejects_wrong_source_directory(tmp_path: Path) -> None:
    raw_sources_dir = tmp_path / "raw" / "sources"
    stored = raw_sources_dir / "src-other" / "source.md"
    stored.parent.mkdir(parents=True)
    stored.write_text("hello\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the expected source directory"):
        validate_stored_source_location(
            stored,
            raw_sources_dir,
            "src-123",
            "raw/sources/src-other/source.md",
        )


def test_add_source_stores_workspace_relative_source_ref_for_nested_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    nested_dir = tmp_path / "docs"
    nested_dir.mkdir()
    source = nested_dir / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    result = add_source(tmp_path, source)

    manifest = load_source_record(result.manifest_path)
    assert result.source_ref == "docs/note.md"
    assert manifest.source_ref == "docs/note.md"
    assert manifest.original_path == "docs/note.md"


def test_add_source_registers_external_sources_as_copies_by_default(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    source = external_dir / "outside.md"
    source.write_text("# outside\n", encoding="utf-8")

    try:
        result = add_source(tmp_path, source)
        manifest = load_source_record(result.manifest_path)
        assert result.stored_path is not None and result.stored_path.exists()
        assert result.storage_mode == "copy"
        assert result.source_ref == str(source.resolve())
        assert manifest.path == manifest.storage_path
        assert manifest.source_ref == str(source.resolve())
        assert manifest.source_ref_kind == "external_path"
        assert manifest.storage_mode == "copy"
        assert manifest.original_path == str(source)
        assert manifest.materialized_at is not None
    finally:
        source.unlink(missing_ok=True)
        external_dir.rmdir()


def test_add_source_supports_explicit_copy_for_workspace_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    result = add_source(tmp_path, source, storage_mode="copy")

    manifest = load_source_record(result.manifest_path)
    assert result.stored_path is not None and result.stored_path.exists()
    assert result.storage_mode == "copy"
    assert result.source_ref == "note.md"
    assert manifest.path.startswith(f"raw/sources/{result.source_id}/")
    assert manifest.storage_path == manifest.path
    assert manifest.source_ref == "note.md"
    assert manifest.source_ref_kind == "workspace_path"
    assert manifest.storage_mode == "copy"


def test_add_source_rejects_external_none_storage_mode(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    source = external_dir / "outside.md"
    source.write_text("# outside\n", encoding="utf-8")

    try:
        with pytest.raises(ValueError, match="not supported for external sources"):
            add_source(tmp_path, source, storage_mode="none")
    finally:
        source.unlink(missing_ok=True)
        external_dir.rmdir()


def test_add_source_supports_pointer_for_workspace_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    result = add_source(tmp_path, source, storage_mode="pointer")

    manifest = load_source_record(result.manifest_path)
    assert result.storage_mode == "pointer"
    assert result.stored_path is not None and result.stored_path.exists()
    assert result.stored_path == tmp_path / "raw" / "sources" / result.source_id / "pointer.json"
    assert manifest.path == f"raw/sources/{result.source_id}/pointer.json"
    assert manifest.storage_path == manifest.path
    assert manifest.source_ref == "note.md"
    assert manifest.source_ref_kind == "workspace_path"
    assert manifest.storage_mode == "pointer"
    assert manifest.materialized_at is not None
    assert not (tmp_path / "raw" / "sources" / result.source_id / "note.md").exists()

    pointer = load_source_pointer(result.stored_path)
    assert pointer.source_id == result.source_id
    assert pointer.source_ref == "note.md"
    assert pointer.source_ref_kind == "workspace_path"
    assert pointer.checksum == manifest.checksum
    assert pointer.created_at == manifest.materialized_at


def test_add_source_rejects_pointer_for_external_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    source = external_dir / "outside.md"
    source.write_text("# outside\n", encoding="utf-8")

    try:
        with pytest.raises(ValueError, match="not implemented yet for external sources"):
            add_source(tmp_path, source, storage_mode="pointer")
    finally:
        source.unlink(missing_ok=True)
        external_dir.rmdir()


def test_add_source_supports_symlink_for_workspace_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    result = add_source(tmp_path, source, storage_mode="symlink")

    manifest = load_source_record(result.manifest_path)
    assert result.storage_mode == "symlink"
    assert result.stored_path is not None and result.stored_path.exists()
    assert result.stored_path == tmp_path / "raw" / "sources" / result.source_id / "note.md"
    assert result.stored_path.is_symlink()
    assert result.stored_path.resolve() == source.resolve()
    assert manifest.path == f"raw/sources/{result.source_id}/note.md"
    assert manifest.storage_path == manifest.path
    assert manifest.source_ref == "note.md"
    assert manifest.source_ref_kind == "workspace_path"
    assert manifest.storage_mode == "symlink"
    assert manifest.materialized_at is not None
    assert result.stored_path.read_text(encoding="utf-8") == "# note\n"


def test_effective_storage_mode_accepts_workspace_symlink() -> None:
    assert (
        _effective_storage_mode(
            source_ref_kind="workspace_path",
            configured_storage_mode="symlink",
        )
        == "symlink"
    )


def test_add_source_rejects_symlink_for_external_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    source = external_dir / "outside.md"
    source.write_text("# outside\n", encoding="utf-8")

    try:
        with pytest.raises(ValueError, match="not implemented yet for external sources"):
            add_source(tmp_path, source, storage_mode="symlink")
    finally:
        source.unlink(missing_ok=True)
        external_dir.rmdir()


def test_replace_path_rejects_existing_directory(tmp_path: Path) -> None:
    existing = tmp_path / "artifact"
    existing.mkdir()

    with pytest.raises(ValueError, match="Cannot replace existing directory"):
        _replace_path(existing)


def test_replace_path_unlinks_existing_file_and_symlink(tmp_path: Path) -> None:
    file_path = tmp_path / "artifact.txt"
    file_path.write_text("hello\n", encoding="utf-8")
    _replace_path(file_path)
    assert not file_path.exists()

    target = tmp_path / "target.txt"
    target.write_text("hello\n", encoding="utf-8")
    symlink_path = tmp_path / "artifact-link"
    symlink_path.symlink_to(target)
    _replace_path(symlink_path)
    assert not symlink_path.exists()


def test_write_workspace_symlink_replaces_stale_artifact(tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    stored_path = tmp_path / "raw" / "sources" / "src-1" / "note.md"
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_text("stale\n", encoding="utf-8")

    _write_workspace_symlink(stored_path, source)

    assert stored_path.is_symlink()
    assert stored_path.resolve() == source.resolve()


def test_write_workspace_symlink_rejects_mismatched_resolution(tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    stored_path = tmp_path / "raw" / "sources" / "src-1" / "note.md"
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    other = tmp_path / "other.md"
    other.write_text("# other\n", encoding="utf-8")
    stored_path.symlink_to(other)

    original_symlink_to = Path.symlink_to

    def fake_symlink_to(self: Path, target: Path, target_is_directory: bool = False) -> None:
        original_symlink_to(self, other, target_is_directory=target_is_directory)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Path, "symlink_to", fake_symlink_to)
    try:
        with pytest.raises(ValueError, match="does not resolve to the canonical workspace source"):
            _write_workspace_symlink(stored_path, source)
    finally:
        monkeypatch.undo()


def test_add_source_is_deduplicated_by_checksum_for_workspace_backed_sources(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    second = add_source(tmp_path, source)

    assert first.source_id == second.source_id
    assert second.already_registered is True
    assert second.storage_mode == "none"
    assert second.stored_path is None


def test_add_source_is_deduplicated_by_checksum_for_copied_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source, storage_mode="copy")
    second = add_source(tmp_path, source, storage_mode="copy")

    assert first.source_id == second.source_id
    assert second.already_registered is True
    assert second.storage_mode == "copy"
    assert second.stored_path == first.stored_path


def test_add_source_is_deduplicated_by_checksum_for_pointer_backed_sources(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source, storage_mode="pointer")
    second = add_source(tmp_path, source, storage_mode="pointer")

    assert first.source_id == second.source_id
    assert second.already_registered is True
    assert second.storage_mode == "pointer"
    assert second.stored_path == first.stored_path


def test_add_source_is_deduplicated_by_checksum_for_symlink_backed_sources(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source, storage_mode="symlink")
    second = add_source(tmp_path, source, storage_mode="symlink")

    assert first.source_id == second.source_id
    assert second.already_registered is True
    assert second.storage_mode == "symlink"
    assert second.stored_path == first.stored_path


def test_add_source_existing_workspace_manifest_missing_file_fails(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    source.unlink()
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("same-content\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Existing source manifest could not be validated during add-source",
    ):
        add_source(tmp_path, replacement)

    manifest = load_source_record(first.manifest_path)
    assert manifest.storage_mode == "none"


def test_add_source_existing_workspace_manifest_checksum_drift_fails(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("same-content\n", encoding="utf-8")

    first = add_source(tmp_path, source)
    source.write_text("changed\n", encoding="utf-8")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("same-content\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Existing source manifest could not be validated during add-source",
    ):
        add_source(tmp_path, replacement)

    manifest = load_source_record(first.manifest_path)
    assert manifest.storage_mode == "none"


def test_add_source_captures_head_for_clean_tracked_workspace_file(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    init_git_repo(tmp_path)
    commit_all(tmp_path, "initial")
    head = git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    result = add_source(tmp_path, source)

    manifest = load_source_record(result.manifest_path)
    assert manifest.source_commit == head


def test_add_source_leaves_source_commit_null_for_untracked_workspace_file(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    init_git_repo(tmp_path)
    commit_all(tmp_path, "initial")
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    result = add_source(tmp_path, source)

    manifest = load_source_record(result.manifest_path)
    assert manifest.source_commit is None


def test_add_source_leaves_source_commit_null_for_dirty_tracked_workspace_file(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    init_git_repo(tmp_path)
    commit_all(tmp_path, "initial")
    source.write_text("# changed\n", encoding="utf-8")

    result = add_source(tmp_path, source)

    manifest = load_source_record(result.manifest_path)
    assert manifest.source_commit is None


def test_add_source_leaves_source_commit_null_for_external_file(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    init_git_repo(tmp_path)
    commit_all(tmp_path, "initial")
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    source = external_dir / "outside.md"
    source.write_text("# outside\n", encoding="utf-8")

    try:
        result = add_source(tmp_path, source)
        manifest = load_source_record(result.manifest_path)
        assert manifest.source_commit is None
    finally:
        source.unlink(missing_ok=True)
        external_dir.rmdir()


def test_add_source_no_capture_override_suppresses_source_commit(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    init_git_repo(tmp_path)
    commit_all(tmp_path, "initial")

    result = add_source(tmp_path, source, capture_source_commit=False)

    manifest = load_source_record(result.manifest_path)
    assert manifest.source_commit is None


def test_add_source_reuses_existing_manifest_authoritatively(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")

    first = add_source(tmp_path, source, storage_mode="copy")
    manifest = load_source_record(first.manifest_path).model_copy(
        update={"source_ref": "docs/custom.md"}
    )
    write_source_record(first.manifest_path, manifest)

    second = add_source(tmp_path, source)

    assert second.already_registered is True
    assert second.source_ref == "docs/custom.md"
    assert second.storage_mode == "copy"


def test_add_source_reuses_mixed_manifest_shapes_authoritatively(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    legacy_source = tmp_path / "legacy.md"
    legacy_source.write_text("# legacy\n", encoding="utf-8")
    workspace_source = tmp_path / "workspace.md"
    workspace_source.write_text("# workspace\n", encoding="utf-8")
    copied_source = tmp_path / "copied.md"
    copied_source.write_text("# copied\n", encoding="utf-8")
    pointer_source = tmp_path / "pointer.md"
    pointer_source.write_text("# pointer\n", encoding="utf-8")
    symlink_source = tmp_path / "symlink.md"
    symlink_source.write_text("# symlink\n", encoding="utf-8")

    legacy_added = add_source(tmp_path, legacy_source, storage_mode="copy")
    add_source(tmp_path, workspace_source)
    add_source(tmp_path, copied_source, storage_mode="copy")
    add_source(tmp_path, pointer_source, storage_mode="pointer")
    add_source(tmp_path, symlink_source, storage_mode="symlink")

    legacy_manifest = load_source_record(legacy_added.manifest_path).model_copy(
        update={
            "source_ref": None,
            "source_ref_kind": None,
            "storage_mode": None,
            "storage_path": None,
            "materialized_at": None,
            "source_commit": None,
        }
    )
    write_source_record(legacy_added.manifest_path, legacy_manifest)

    legacy_repeat = add_source(tmp_path, legacy_source)
    workspace_repeat = add_source(tmp_path, workspace_source, storage_mode="copy")
    copied_repeat = add_source(tmp_path, copied_source)
    pointer_repeat = add_source(tmp_path, pointer_source)
    symlink_repeat = add_source(tmp_path, symlink_source)

    assert legacy_repeat.already_registered is True
    assert legacy_repeat.source_ref == "legacy.md"
    assert legacy_repeat.storage_mode == "copy"

    assert workspace_repeat.already_registered is True
    assert workspace_repeat.source_ref == "workspace.md"
    assert workspace_repeat.storage_mode == "none"
    assert workspace_repeat.stored_path is None

    assert copied_repeat.already_registered is True
    assert copied_repeat.source_ref == "copied.md"
    assert copied_repeat.storage_mode == "copy"
    assert copied_repeat.stored_path is not None

    assert pointer_repeat.already_registered is True
    assert pointer_repeat.source_ref == "pointer.md"
    assert pointer_repeat.storage_mode == "pointer"
    assert pointer_repeat.stored_path is not None

    assert symlink_repeat.already_registered is True
    assert symlink_repeat.source_ref == "symlink.md"
    assert symlink_repeat.storage_mode == "symlink"
    assert symlink_repeat.stored_path is not None


def test_materialize_source_defaults_workspace_none_to_pointer(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source)

    result = materialize_source(tmp_path, registered.source_id)

    manifest = load_source_record(result.manifest_path)
    assert result.storage_mode == "pointer"
    assert (
        result.stored_path == tmp_path / "raw" / "sources" / registered.source_id / "pointer.json"
    )
    assert manifest.storage_mode == "pointer"
    assert manifest.storage_path == manifest.path
    assert manifest.materialized_at is not None


def test_materialize_source_supports_copy_mode(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source)

    result = materialize_source(tmp_path, registered.source_id, storage_mode="copy")

    manifest = load_source_record(result.manifest_path)
    assert result.storage_mode == "copy"
    assert result.stored_path.exists()
    assert manifest.storage_mode == "copy"
    assert manifest.storage_path == manifest.path


def test_materialize_source_refreshes_stale_copy_artifact(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source, storage_mode="copy")
    assert registered.stored_path is not None
    registered.stored_path.write_text("stale\n", encoding="utf-8")

    result = materialize_source(tmp_path, registered.source_id)

    assert result.storage_mode == "copy"
    assert result.stored_path.read_text(encoding="utf-8") == "# note\n"


def test_materialize_source_supports_symlink_mode(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source)

    result = materialize_source(tmp_path, registered.source_id, storage_mode="symlink")

    manifest = load_source_record(result.manifest_path)
    assert result.storage_mode == "symlink"
    assert result.stored_path.is_symlink()
    assert manifest.storage_mode == "symlink"
    assert manifest.storage_path == manifest.path


def test_materialize_source_is_idempotent_for_existing_materialized_mode(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source, storage_mode="pointer")
    first_manifest = load_source_record(registered.manifest_path)

    result = materialize_source(tmp_path, registered.source_id)

    manifest = load_source_record(result.manifest_path)
    assert result.storage_mode == "pointer"
    assert manifest.storage_mode == "pointer"
    assert manifest.materialized_at is not None
    assert manifest.materialized_at >= first_manifest.materialized_at


def test_materialize_source_rejects_external_sources(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    external_dir = tmp_path.parent / f"{tmp_path.name}-external"
    external_dir.mkdir()
    source = external_dir / "outside.md"
    source.write_text("# outside\n", encoding="utf-8")
    try:
        registered = add_source(tmp_path, source)
        with pytest.raises(ValueError, match="Only workspace-backed sources can be materialized"):
            materialize_source(tmp_path, registered.source_id)
    finally:
        source.unlink(missing_ok=True)
        external_dir.rmdir()


def test_materialize_source_rejects_legacy_manifests(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source, storage_mode="copy")
    legacy_manifest = load_source_record(registered.manifest_path).model_copy(
        update={"source_ref": None, "source_ref_kind": None, "storage_mode": None}
    )
    write_source_record(registered.manifest_path, legacy_manifest)

    with pytest.raises(ValueError, match="Legacy stored-artifact manifests cannot be materialized"):
        materialize_source(tmp_path, registered.source_id)


def test_materializing_storage_mode_rejects_legacy_manifest_shape(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source, storage_mode="copy")
    legacy_manifest = load_source_record(registered.manifest_path).model_copy(
        update={"source_ref": None, "source_ref_kind": None, "storage_mode": None}
    )

    with pytest.raises(ValueError, match="Legacy stored-artifact manifests cannot be materialized"):
        materializing_storage_mode_for_source(tmp_path, legacy_manifest)


def test_materialize_source_rejects_missing_workspace_source(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source)
    source.unlink()

    with pytest.raises(ValueError, match="Workspace source is missing"):
        materialize_source(tmp_path, registered.source_id)


def test_materialize_source_rejects_checksum_drift(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# note\n", encoding="utf-8")
    registered = add_source(tmp_path, source)
    source.write_text("# changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Workspace source checksum mismatch for materialization"):
        materialize_source(tmp_path, registered.source_id)
