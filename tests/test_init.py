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
    assert [group.label for group in result.review_groups] == [
        "configuration",
        "human workspace",
        "source and derived state",
        "runtime state",
    ]
    assert result.review_groups[-1].paths == ["state", "state/manifests/sources", "reports"]


def test_initialize_workspace_is_idempotent(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    second = initialize_workspace(tmp_path)

    assert second.created_directories == []
    assert second.created_files == []


def test_initialize_workspace_uses_configured_layout_for_keep_files(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "\n".join(
            [
                "schema_version: '1'",
                "project_name: custom",
                "layout:",
                "  raw_dir: .splendor/raw",
                "  raw_sources_dir: .splendor/raw/sources",
                "  raw_assets_dir: .splendor/raw/assets",
                "  raw_imports_dir: .splendor/raw/imports",
                "  derived_dir: .splendor/derived",
                "  derived_ocr_dir: .splendor/derived/ocr",
                "  derived_parsed_dir: .splendor/derived/parsed",
                "  derived_metadata_dir: .splendor/derived/metadata",
                "  derived_summaries_dir: .splendor/derived/summaries",
                "  wiki_dir: .splendor/wiki",
                "  planning_dir: .splendor/planning",
                "  state_dir: .splendor/state",
                "  reports_dir: .splendor/reports",
                "  source_records_dir: .splendor/state/manifests/sources",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = initialize_workspace(tmp_path)

    assert (tmp_path / ".splendor" / "state" / "manifests" / "sources" / ".gitkeep").exists()
    assert (tmp_path / ".splendor" / "wiki" / "index.md").exists()
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / "wiki").exists()
    assert not (tmp_path / "reports").exists()
    assert result.review_groups[-1].paths == [
        ".splendor/state",
        ".splendor/state/manifests/sources",
        ".splendor/reports",
    ]


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
    assert "project_name: ''" not in (tmp_path / "splendor.yaml").read_text(encoding="utf-8")
