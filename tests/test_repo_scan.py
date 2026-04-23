import json
from pathlib import Path

from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.commands.repo_scan import render_repo_scan_json, scan_repo
from splendor.state.source_registry import load_source_record


def _manifest_paths(root: Path) -> list[Path]:
    return sorted((root / "state" / "manifests" / "sources").glob("*.json"))


def _remove_workspace_config(root: Path) -> None:
    (root / "splendor.yaml").unlink(missing_ok=True)


def test_repo_scan_registers_and_classifies_supported_workspace_files(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text("name: CI\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert result.scanned == 6
    assert result.registered == 6
    assert result.already_registered == 0
    assert result.class_counts == {
        "code": 2,
        "documentation": 3,
        "configuration": 1,
        "other": 0,
    }
    touched = {item.path: item for item in result.touched_sources}
    assert touched["AGENTS.md"].source_labels == ["agent-instructions"]
    assert touched["README.md"].source_class == "documentation"
    assert touched["docs/guide.md"].source_class == "documentation"
    assert touched["src/main.py"].source_class == "code"
    assert touched["tests/test_main.py"].source_labels == ["test"]
    assert touched[".github/workflows/ci.yml"].source_class == "configuration"
    assert touched[".github/workflows/ci.yml"].source_labels == ["automation"]

    manifest_by_ref = {
        load_source_record(path).source_ref: load_source_record(path)
        for path in _manifest_paths(tmp_path)
    }
    assert manifest_by_ref["AGENTS.md"].discovered_by == "repo_scan"
    assert manifest_by_ref["AGENTS.md"].source_class == "documentation"
    assert manifest_by_ref["AGENTS.md"].source_labels == ["agent-instructions"]
    assert manifest_by_ref["src/main.py"].source_class == "code"


def test_repo_scan_ignores_managed_and_transient_directories(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "wiki" / "sources" / "skip.md").write_text("# Skip\n", encoding="utf-8")
    (tmp_path / "state" / "queue" / "skip.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert result.scanned == 1
    assert result.registered == 1
    assert result.ignored >= 4
    assert [item.path for item in result.touched_sources] == ["README.md"]


def test_repo_scan_reports_unsupported_files(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert result.scanned == 1
    assert result.unsupported == 1


def test_repo_scan_is_idempotent_and_backfills_existing_workspace_metadata(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    source = tmp_path / "README.md"
    source.write_text("# Readme\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    original = load_source_record(added.manifest_path)
    assert original.source_class is None
    assert original.discovered_by is None

    result = scan_repo(tmp_path)

    touched = {item.path: item for item in result.touched_sources}
    assert touched["README.md"].status == "already_registered"
    updated = load_source_record(added.manifest_path)
    assert updated.source_class == "documentation"
    assert updated.discovered_by == "repo_scan"
    assert updated.source_labels == []


def test_repo_scan_registers_new_source_id_after_content_changes(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    source = tmp_path / "README.md"
    source.write_text("# One\n", encoding="utf-8")

    first = scan_repo(tmp_path)
    first_id = {item.path: item for item in first.touched_sources}["README.md"].source_id

    source.write_text("# Two\n", encoding="utf-8")
    second = scan_repo(tmp_path)
    second_id = {item.path: item for item in second.touched_sources}["README.md"].source_id

    assert first_id != second_id
    assert second.registered == 1


def test_render_repo_scan_json_matches_expected_shape(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")

    payload = json.loads(render_repo_scan_json(scan_repo(tmp_path)))

    assert payload["scanned"] == 1
    assert payload["registered"] == 1
    assert payload["already_registered"] == 0
    assert payload["unsupported"] == 0
    assert payload["ignored"] >= 0
    assert payload["class_counts"]["documentation"] == 1
    assert payload["touched_sources"][0]["path"] == "README.md"
    assert payload["touched_sources"][0]["source_class"] == "documentation"
    assert payload["touched_sources"][0]["status"] == "registered"
