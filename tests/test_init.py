from pathlib import Path

from splendor.commands.init import initialize_workspace


def test_initialize_workspace_creates_layout(tmp_path: Path) -> None:
    result = initialize_workspace(tmp_path)

    assert (tmp_path / "splendor.yaml").exists()
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()
    assert (tmp_path / "state" / "manifests" / "sources").exists()
    assert result.created_directories
    assert result.created_files


def test_initialize_workspace_is_idempotent(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    second = initialize_workspace(tmp_path)

    assert second.created_directories == []
    assert second.created_files == []
