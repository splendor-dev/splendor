from pathlib import Path

from splendor.commands.init import initialize_workspace
from splendor.config import load_config


def test_initialize_workspace_creates_layout(tmp_path: Path) -> None:
    result = initialize_workspace(tmp_path)

    assert (tmp_path / "splendor.yaml").exists()
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()
    assert (tmp_path / "state" / "manifests" / "sources").exists()
    assert (tmp_path / "state" / "manifests" / ".gitkeep").exists()
    assert (tmp_path / "state" / "manifests" / "sources" / ".gitkeep").exists()
    config = load_config(tmp_path)
    assert config.sources.in_repo_storage_mode == "none"
    assert config.sources.external_storage_mode == "copy"
    assert result.created_directories
    assert result.created_files


def test_initialize_workspace_is_idempotent(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    second = initialize_workspace(tmp_path)

    assert second.created_directories == []
    assert second.created_files == []


def test_initialize_workspace_repairs_blank_project_name(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\nproject_name: ''\nlayout:\n  raw_dir: raw\n",
        encoding="utf-8",
    )

    result = initialize_workspace(tmp_path)

    assert result.root == tmp_path
    config = load_config(tmp_path)
    assert config.project_name == tmp_path.name
    assert config.sources.in_repo_storage_mode == "none"
    assert "project_name: ''" not in (tmp_path / "splendor.yaml").read_text(
        encoding="utf-8"
    )
