from pathlib import Path

import pytest
from pydantic import ValidationError

from splendor.config import default_config, load_config, write_config


def test_default_config_includes_source_policy_defaults() -> None:
    config = default_config(project_name="Example")

    assert config.sources.in_repo_storage_mode == "none"
    assert config.sources.external_storage_mode == "copy"
    assert config.sources.imported_storage_mode == "copy"
    assert config.sources.capture_source_commit is True
    assert config.sources.summarize_in_repo_extracts_as == "excerpt"
    assert config.sources.summarize_external_extracts_as == "full"


def test_load_config_accepts_yaml_without_sources_block(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\nproject_name: Example\nlayout:\n  raw_dir: raw\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.project_name == "Example"
    assert config.sources.in_repo_storage_mode == "none"
    assert config.sources.external_storage_mode == "copy"


def test_load_config_applies_defaults_for_missing_sources(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\nproject_name: Example\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.sources.imported_storage_mode == "copy"
    assert config.sources.capture_source_commit is True


def test_load_config_rejects_invalid_sources_values(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        ("schema_version: '1'\nproject_name: Example\nsources:\n  in_repo_storage_mode: bogus\n"),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_load_config_rejects_unknown_sources_keys(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        ("schema_version: '1'\nproject_name: Example\nsources:\n  external_storage_mdoe: copy\n"),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_load_config_accepts_unknown_top_level_keys(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        (
            "schema_version: '1'\n"
            "project_name: Example\n"
            "experimental_flag: true\n"
            "sources:\n"
            "  in_repo_storage_mode: none\n"
        ),
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.project_name == "Example"
    assert config.sources.in_repo_storage_mode == "none"


def test_load_config_accepts_unknown_layout_keys(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        (
            "schema_version: '1'\n"
            "project_name: Example\n"
            "layout:\n"
            "  raw_dir: raw\n"
            "  extra_layout_experiment: true\n"
        ),
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.project_name == "Example"
    assert config.layout.raw_dir == "raw"


def test_write_config_serializes_sources_block(tmp_path: Path) -> None:
    config = default_config(project_name="Example")

    write_config(tmp_path, config)
    written = (tmp_path / "splendor.yaml").read_text(encoding="utf-8")

    assert "sources:" in written
    assert "in_repo_storage_mode: none" in written
    assert "external_storage_mode: copy" in written
