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
    assert config.queue.max_attempts == 3
    assert config.queue.lease_ttl_seconds == 300
    assert config.queue.retry_backoff_seconds == [60, 300, 900]
    assert config.briefing.authority_documents == []


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


def test_load_config_accepts_queue_policy(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        (
            "schema_version: '1'\n"
            "project_name: Example\n"
            "queue:\n"
            "  max_attempts: 5\n"
            "  lease_ttl_seconds: 120\n"
            "  retry_backoff_seconds: [1, 2, 3]\n"
        ),
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.queue.max_attempts == 5
    assert config.queue.lease_ttl_seconds == 120
    assert config.queue.retry_backoff_seconds == [1, 2, 3]


def test_load_config_accepts_briefing_authority_documents(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        (
            "schema_version: '1'\n"
            "project_name: Example\n"
            "briefing:\n"
            "  authority_documents:\n"
            "    - path: README.md\n"
            "      role: current-authority\n"
            "      freshness: current\n"
            "      purpose: Current project entrypoint.\n"
            "      applies_to: [agent handoff]\n"
        ),
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    authority = config.briefing.authority_documents[0]
    assert authority.path == "README.md"
    assert authority.role == "current-authority"
    assert authority.applies_to == ["agent handoff"]


def test_load_config_rejects_unknown_briefing_keys(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        ("schema_version: '1'\nproject_name: Example\nbriefing:\n  authority_documentz: []\n"),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_config(tmp_path)


@pytest.mark.parametrize(
    "path", ["/etc/hosts", "../README.md", "docs/../README.md", "docs\\brief.md", ""]
)
def test_load_config_rejects_non_repo_relative_authority_document_paths(
    tmp_path: Path, path: str
) -> None:
    (tmp_path / "splendor.yaml").write_text(
        (
            "schema_version: '1'\n"
            "project_name: Example\n"
            "briefing:\n"
            "  authority_documents:\n"
            f"    - path: {path!r}\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_load_config_rejects_unknown_queue_keys(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        ("schema_version: '1'\nproject_name: Example\nqueue:\n  max_attemptz: 5\n"),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_load_config_rejects_negative_queue_backoff(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        ("schema_version: '1'\nproject_name: Example\nqueue:\n  retry_backoff_seconds: [60, -1]\n"),
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
    assert "queue:" in written
    assert "in_repo_storage_mode: none" in written
    assert "external_storage_mode: copy" in written
