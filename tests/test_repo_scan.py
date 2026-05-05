import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import splendor.commands.repo_scan as repo_scan_module
import splendor.state.source_registry as source_registry_module
from conftest import write_text_pdf
from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.commands.repo_scan import (
    apply_repo_scan,
    render_repo_scan_json,
    scan_repo,
    write_repo_scan_report,
)
from splendor.state.source_registry import load_source_record, write_source_record


def _manifest_paths(root: Path) -> list[Path]:
    return sorted((root / "state" / "manifests" / "sources").glob("*.json"))


def _remove_workspace_config(root: Path) -> None:
    (root / "splendor.yaml").unlink(missing_ok=True)


def _require_git() -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable is required for gitignore scan tests")


def _write_mixed_repo(root: Path) -> None:
    (root / "README.md").write_text("# Readme\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    docs_dir = root / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    write_text_pdf(docs_dir / "research.pdf", ["Research PDF"])
    src_dir = root / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    workflows_dir = root / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text("name: CI\n", encoding="utf-8")


def _write_populated_ignored_dirs(root: Path) -> None:
    ignored_sources = {
        ".claude/settings.local.json": "{}\n",
        ".mypy_cache/module.data.json": "{}\n",
        ".pytest_cache/v/cache/nodeids": "[]\n",
        ".ruff_cache/0.11.0/file.py": "print('ignored')\n",
        ".venv/lib/site-packages/pkg.py": "print('ignored')\n",
        "build/lib/generated.py": "print('ignored')\n",
        "dist/package.json": "{}\n",
        "src/__pycache__/main.py": "print('ignored')\n",
    }
    for relative_path, contents in ignored_sources.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


def test_repo_scan_previews_and_classifies_supported_workspace_files(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    _write_mixed_repo(tmp_path)

    result = scan_repo(tmp_path, all_classes=True)

    assert result.mode == "preview"
    assert result.scanned == 7
    assert result.candidates == 7
    assert result.registered == 0
    assert result.already_registered == 0
    assert result.class_counts == {
        "code": 2,
        "documentation": 4,
        "configuration": 1,
        "other": 0,
    }
    candidates = {item.path: item for item in result.candidate_sources}
    assert candidates["AGENTS.md"].source_labels == ["agent-instructions"]
    assert candidates["README.md"].source_class == "documentation"
    assert candidates["docs/guide.md"].source_class == "documentation"
    assert candidates["docs/research.pdf"].source_class == "documentation"
    assert candidates["src/main.py"].source_class == "code"
    assert candidates["tests/test_main.py"].source_labels == ["test"]
    assert candidates[".github/workflows/ci.yml"].source_class == "configuration"
    assert candidates[".github/workflows/ci.yml"].source_labels == ["automation"]
    assert _manifest_paths(tmp_path) == []


def test_repo_scan_apply_registers_and_classifies_supported_workspace_files(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    _write_mixed_repo(tmp_path)

    result = apply_repo_scan(tmp_path, all_classes=True)

    assert result.mode == "apply"
    assert result.scanned == 7
    assert result.candidates == 7
    assert result.registered == 7
    assert result.already_registered == 0
    manifest_by_ref = {
        load_source_record(path).source_ref: load_source_record(path)
        for path in _manifest_paths(tmp_path)
    }
    assert manifest_by_ref["AGENTS.md"].discovered_by == "repo_scan"
    assert manifest_by_ref["AGENTS.md"].source_class == "documentation"
    assert manifest_by_ref["AGENTS.md"].source_labels == ["agent-instructions"]
    assert manifest_by_ref["src/main.py"].source_class == "code"


def test_repo_scan_apply_reuses_config_and_layout_for_bulk_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_workspace(tmp_path)
    config_path = tmp_path / "splendor.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["layout"]["state_dir"] = "custom-state"
    config["layout"]["source_records_dir"] = "custom-state/manifests/sources"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    for index in range(3):
        (tmp_path / f"doc-{index}.md").write_text(f"# Doc {index}\n", encoding="utf-8")

    load_config_calls = 0
    resolve_layout_calls = 0
    real_load_config = repo_scan_module.load_config
    real_resolve_layout = repo_scan_module.resolve_layout

    def counting_load_config(root: Path):
        nonlocal load_config_calls
        load_config_calls += 1
        return real_load_config(root)

    def counting_resolve_layout(root: Path, config):
        nonlocal resolve_layout_calls
        resolve_layout_calls += 1
        return real_resolve_layout(root, config)

    def fail_source_registry_load_config(root: Path):
        raise AssertionError(f"unexpected per-source config load for {root}")

    def fail_source_registry_resolve_layout(root: Path, config):
        raise AssertionError(f"unexpected per-source layout resolution for {root}")

    monkeypatch.setattr(repo_scan_module, "load_config", counting_load_config)
    monkeypatch.setattr(repo_scan_module, "resolve_layout", counting_resolve_layout)
    monkeypatch.setattr(source_registry_module, "load_config", fail_source_registry_load_config)
    monkeypatch.setattr(
        source_registry_module,
        "resolve_layout",
        fail_source_registry_resolve_layout,
    )

    result = repo_scan_module.apply_repo_scan(tmp_path, class_filters=["documentation"])

    assert result.registered == 3
    assert load_config_calls == 1
    assert resolve_layout_calls == 1
    assert _manifest_paths(tmp_path) == []
    custom_manifest_paths = sorted(
        (tmp_path / "custom-state" / "manifests" / "sources").glob("*.json")
    )
    assert len(custom_manifest_paths) == 3
    assert {load_source_record(path).source_ref for path in custom_manifest_paths} == {
        "doc-0.md",
        "doc-1.md",
        "doc-2.md",
    }


def test_repo_scan_classifies_image_sources_as_other(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    result = scan_repo(tmp_path, all_classes=True)

    assert result.scanned == 1
    assert result.class_counts == {
        "code": 0,
        "documentation": 0,
        "configuration": 0,
        "other": 1,
    }
    assert result.candidate_sources[0].path == "diagram.png"
    assert result.candidate_sources[0].source_class == "other"


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
    packages_dir = tmp_path / "packages" / "app"
    packages_dir.mkdir(parents=True)
    nested_node_modules = packages_dir / "node_modules"
    nested_node_modules.mkdir()
    (nested_node_modules / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")
    nested_cache = tmp_path / "src" / "__pycache__"
    nested_cache.mkdir(parents=True)
    (nested_cache / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")
    generated_docs = tmp_path / "docs" / "generated"
    generated_docs.mkdir(parents=True)
    (generated_docs / "ignored.md").write_text("# Ignored\n", encoding="utf-8")

    result = scan_repo(tmp_path, all_classes=True)

    assert result.scanned == 1
    assert result.registered == 0
    assert [item.path for item in result.candidate_sources] == ["README.md"]


def test_repo_scan_default_excludes_populated_local_tooling_dirs(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _write_populated_ignored_dirs(tmp_path)

    result = scan_repo(tmp_path)

    assert [item.path for item in result.candidate_sources] == [
        "README.md",
        "docs/guide.md",
    ]
    ignored = {item.path: item.reason for item in result.ignored_paths}
    assert ignored[".claude/"] == "managed_or_transient"
    assert ignored[".mypy_cache/"] == "managed_or_transient"
    assert ignored[".pytest_cache/"] == "managed_or_transient"
    assert ignored[".ruff_cache/"] == "managed_or_transient"
    assert ignored[".venv/"] == "managed_or_transient"
    assert ignored["build/"] == "managed_or_transient"
    assert ignored["dist/"] == "managed_or_transient"
    assert ignored["src/__pycache__/"] == "managed_or_transient"


def test_repo_scan_all_and_class_filters_exclude_populated_local_tooling_dirs(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _write_populated_ignored_dirs(tmp_path)

    all_result = scan_repo(tmp_path, all_classes=True)
    class_filtered_result = scan_repo(tmp_path, class_filters=["documentation", "code"])

    assert [item.path for item in all_result.candidate_sources] == [
        "README.md",
        "src/main.py",
    ]
    assert [item.path for item in class_filtered_result.candidate_sources] == [
        "README.md",
        "src/main.py",
    ]
    assert all(
        not item.path.startswith((".claude", ".mypy_cache", ".pytest_cache", ".ruff_cache"))
        for item in all_result.candidate_sources
    )


def test_repo_scan_apply_excludes_populated_local_tooling_dirs(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _write_populated_ignored_dirs(tmp_path)

    result = apply_repo_scan(tmp_path, all_classes=True)

    assert [item.path for item in result.touched_sources] == ["README.md", "src/main.py"]
    manifest_refs = {load_source_record(path).source_ref for path in _manifest_paths(tmp_path)}
    assert manifest_refs == {"README.md", "src/main.py"}


def test_render_repo_scan_json_reports_pruned_ignored_directories(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    _write_populated_ignored_dirs(tmp_path)

    payload = json.loads(render_repo_scan_json(scan_repo(tmp_path, all_classes=True)))

    ignored = {item["path"]: item["reason"] for item in payload["ignored_paths"]}
    assert ignored[".claude/"] == "managed_or_transient"
    assert ignored[".mypy_cache/"] == "managed_or_transient"
    assert ignored[".pytest_cache/"] == "managed_or_transient"
    assert ignored[".ruff_cache/"] == "managed_or_transient"
    assert ignored[".venv/"] == "managed_or_transient"
    assert ignored["build/"] == "managed_or_transient"
    assert ignored["dist/"] == "managed_or_transient"


def test_repo_scan_reports_unsupported_files(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    result = scan_repo(tmp_path, all_classes=True)

    assert result.scanned == 1
    assert result.unsupported == 1


def test_repo_scan_preview_does_not_hash_new_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")

    def fail_hash(path: Path) -> str:
        raise AssertionError(f"unexpected preview hash for {path}")

    monkeypatch.setattr("splendor.commands.repo_scan.sha256_file", fail_hash)

    result = scan_repo(tmp_path)

    assert [item.path for item in result.candidate_sources] == ["README.md"]
    assert result.candidate_sources[0].status == "candidate"


def test_repo_scan_preview_is_non_mutating_for_existing_workspace_metadata(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    source = tmp_path / "README.md"
    source.write_text("# Readme\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    original = load_source_record(added.manifest_path)
    assert original.source_class is None
    assert original.discovered_by is None

    result = scan_repo(tmp_path)

    candidates = {item.path: item for item in result.candidate_sources}
    assert candidates["README.md"].status == "already_curated"
    assert candidates["README.md"].source_id == added.source_id
    updated = load_source_record(added.manifest_path)
    assert updated.source_class is None
    assert updated.discovered_by is None
    assert updated.source_labels == []


def test_repo_scan_apply_is_idempotent_and_backfills_existing_workspace_metadata(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    source = tmp_path / "README.md"
    source.write_text("# Readme\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    result = apply_repo_scan(tmp_path, class_filters=["documentation"])

    touched = {item.path: item for item in result.touched_sources}
    assert touched["README.md"].status == "already_registered"
    updated = load_source_record(added.manifest_path)
    assert updated.source_class == "documentation"
    assert updated.discovered_by == "repo_scan"
    assert updated.source_labels == []


def test_repo_scan_apply_registers_new_source_id_after_content_changes(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    source = tmp_path / "README.md"
    source.write_text("# One\n", encoding="utf-8")

    first = apply_repo_scan(tmp_path, class_filters=["documentation"])
    first_id = {item.path: item for item in first.touched_sources}["README.md"].source_id

    source.write_text("# Two\n", encoding="utf-8")
    preview = scan_repo(tmp_path)
    preview_candidate = {item.path: item for item in preview.candidate_sources}["README.md"]
    assert preview_candidate.status == "new_version_candidate"
    assert preview_candidate.already_curated is False
    assert preview_candidate.source_id == first_id

    second = apply_repo_scan(tmp_path, class_filters=["documentation"])
    second_id = {item.path: item for item in second.touched_sources}["README.md"].source_id

    assert first_id != second_id
    assert second.registered == 1


def test_repo_scan_preview_uses_latest_manifest_for_changed_workspace_path(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    source = tmp_path / "README.md"
    source.write_text("# One\n", encoding="utf-8")
    first = add_source(tmp_path, source)
    first_record = load_source_record(first.manifest_path)
    write_source_record(
        first.manifest_path,
        first_record.model_copy(update={"added_at": "2026-01-01T00:00:00+00:00"}),
    )

    source.write_text("# Two\n", encoding="utf-8")
    second = add_source(tmp_path, source)
    second_record = load_source_record(second.manifest_path)
    write_source_record(
        second.manifest_path,
        second_record.model_copy(update={"added_at": "2026-01-02T00:00:00+00:00"}),
    )

    source.write_text("# Three\n", encoding="utf-8")

    preview = scan_repo(tmp_path)
    preview_candidate = {item.path: item for item in preview.candidate_sources}["README.md"]

    assert preview_candidate.status == "new_version_candidate"
    assert preview_candidate.source_id == second.source_id


def test_render_repo_scan_json_matches_expected_shape(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")

    payload = json.loads(render_repo_scan_json(scan_repo(tmp_path)))

    assert payload["mode"] == "preview"
    assert payload["scanned"] == 1
    assert payload["candidates"] == 1
    assert payload["registered"] == 0
    assert payload["already_registered"] == 0
    assert payload["unsupported"] == 0
    assert payload["ignored"] >= 0
    assert payload["class_counts"]["documentation"] == 1
    assert payload["candidate_sources"][0]["path"] == "README.md"
    assert payload["candidate_sources"][0]["source_class"] == "documentation"
    assert payload["candidate_sources"][0]["status"] == "candidate"


def test_repo_scan_defaults_to_configured_default_classes(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert [item.path for item in result.candidate_sources] == ["README.md"]
    assert [item.path for item in result.ignored_paths if item.reason == "class_filter"] == [
        "src/main.py"
    ]


def test_repo_scan_class_filter_includes_code(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")

    result = scan_repo(tmp_path, class_filters=["code"])

    assert [item.path for item in result.candidate_sources] == ["src/main.py"]
    assert result.class_counts["code"] == 1


def test_repo_scan_include_exclude_patterns_are_workspace_relative(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    config_path = tmp_path / "splendor.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["sources"]["include_patterns"] = ["docs/**", "README.md"]
    config["sources"]["exclude_patterns"] = ["docs/drafts/**", "*.tmp.md"]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    drafts_dir = docs_dir / "drafts"
    drafts_dir.mkdir()
    (drafts_dir / "skip.md").write_text("# Skip\n", encoding="utf-8")
    (tmp_path / "note.tmp.md").write_text("# Skip\n", encoding="utf-8")
    (tmp_path / "other.md").write_text("# Other\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert [item.path for item in result.candidate_sources] == ["README.md", "docs/guide.md"]
    ignored = {item.path: item.reason for item in result.ignored_paths}
    assert ignored["docs/drafts/skip.md"] == "exclude_patterns"
    assert ignored["note.tmp.md"] == "include_patterns"
    assert ignored["other.md"] == "include_patterns"


def test_repo_scan_separatorless_globs_match_only_workspace_root(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    config_path = tmp_path / "splendor.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["sources"]["include_patterns"] = ["README.md"]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "README.md").write_text("# Nested\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert [item.path for item in result.candidate_sources] == ["README.md"]
    assert {item.path: item.reason for item in result.ignored_paths}["docs/README.md"] == (
        "include_patterns"
    )


def test_repo_scan_globs_are_path_segment_aware(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    config_path = tmp_path / "splendor.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["sources"]["include_patterns"] = ["docs/*", "configs/**/*.yml"]
    config["sources"]["exclude_patterns"] = ["docs/private/*", "configs/scenes/*.yml"]
    config["sources"]["repo_scan_default_classes"] = ["documentation", "configuration"]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    nested_docs_dir = docs_dir / "nested"
    nested_docs_dir.mkdir()
    (nested_docs_dir / "deep.md").write_text("# Deep\n", encoding="utf-8")
    private_dir = docs_dir / "private"
    private_dir.mkdir()
    (private_dir / "note.md").write_text("# Private\n", encoding="utf-8")
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "root.yml").write_text("root: true\n", encoding="utf-8")
    scenes_dir = configs_dir / "scenes"
    scenes_dir.mkdir()
    (scenes_dir / "generated.yml").write_text("generated: true\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert [item.path for item in result.candidate_sources] == [
        "configs/root.yml",
        "docs/guide.md",
    ]
    ignored = {item.path: item.reason for item in result.ignored_paths}
    assert ignored["docs/nested/deep.md"] == "include_patterns"
    assert ignored["docs/private/note.md"] == "include_patterns"
    assert ignored["configs/scenes/generated.yml"] == "exclude_patterns"


def test_repo_scan_globstar_matches_zero_or_more_path_segments(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    config_path = tmp_path / "splendor.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["sources"]["include_patterns"] = ["docs/**/*.md"]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    nested_docs_dir = docs_dir / "nested"
    nested_docs_dir.mkdir()
    (nested_docs_dir / "deep.md").write_text("# Deep\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")

    result = scan_repo(tmp_path)

    assert [item.path for item in result.candidate_sources] == [
        "docs/guide.md",
        "docs/nested/deep.md",
    ]
    assert {item.path: item.reason for item in result.ignored_paths}["README.md"] == (
        "include_patterns"
    )


def test_repo_scan_respects_gitignore(tmp_path: Path) -> None:
    _require_git()
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / ".gitignore").write_text("generated.md\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "generated.md").write_text("# Generated\n", encoding="utf-8")

    git_init = subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert git_init.returncode == 0

    result = scan_repo(tmp_path, all_classes=True)

    assert [item.path for item in result.candidate_sources] == ["README.md"]
    assert {item.path: item.reason for item in result.ignored_paths}["generated.md"] == "gitignore"


def test_repo_scan_respects_gitignore_when_workspace_is_repository_subdirectory(
    tmp_path: Path,
) -> None:
    _require_git()
    repo_root = tmp_path / "project"
    workspace_root = repo_root / "workspace"
    workspace_root.mkdir(parents=True)
    initialize_workspace(workspace_root)
    _remove_workspace_config(workspace_root)
    (repo_root / ".gitignore").write_text("workspace/generated.md\n", encoding="utf-8")
    (workspace_root / "README.md").write_text("# Readme\n", encoding="utf-8")
    (workspace_root / "generated.md").write_text("# Generated\n", encoding="utf-8")

    git_init = subprocess.run(
        ["git", "init"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert git_init.returncode == 0

    result = scan_repo(workspace_root, all_classes=True)

    assert [item.path for item in result.candidate_sources] == ["README.md"]
    assert {item.path: item.reason for item in result.ignored_paths}["generated.md"] == "gitignore"


def test_repo_scan_prunes_gitignored_directories_before_walking(tmp_path: Path) -> None:
    _require_git()
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / ".gitignore").write_text("vendor/\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "skip.md").write_text("# Ignored\n", encoding="utf-8")

    git_init = subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert git_init.returncode == 0

    result = scan_repo(tmp_path, all_classes=True)

    assert [item.path for item in result.candidate_sources] == ["README.md"]
    assert "vendor/skip.md" not in {item.path for item in result.ignored_paths}
    assert {item.path: item.reason for item in result.ignored_paths}["vendor/"] == "gitignore"


def test_repo_scan_respects_splendorignore_file_patterns(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / ".splendorignore").write_text(
        "# local scan policy\nsecret.md\ndocs/private/*.md\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "secret.md").write_text("# Secret\n", encoding="utf-8")
    private_dir = tmp_path / "docs" / "private"
    private_dir.mkdir(parents=True)
    (private_dir / "note.md").write_text("# Private\n", encoding="utf-8")
    (private_dir / "keep.txt").write_text("Keep\n", encoding="utf-8")

    result = scan_repo(tmp_path, all_classes=True)

    assert [item.path for item in result.candidate_sources] == [
        "README.md",
        "docs/private/keep.txt",
    ]
    ignored = {item.path: item.reason for item in result.ignored_paths}
    assert ignored["secret.md"] == "splendorignore"
    assert ignored["docs/private/note.md"] == "splendorignore"


def test_repo_scan_respects_splendorignore_directory_patterns(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    (tmp_path / ".splendorignore").write_text(
        "local-agent/\ndocs/private-cache/\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    local_agent_dir = tmp_path / "local-agent"
    local_agent_dir.mkdir()
    (local_agent_dir / "settings.json").write_text("{}\n", encoding="utf-8")
    private_cache_dir = tmp_path / "docs" / "private-cache"
    private_cache_dir.mkdir(parents=True)
    (private_cache_dir / "skip.md").write_text("# Skip\n", encoding="utf-8")

    result = scan_repo(tmp_path, all_classes=True)

    assert [item.path for item in result.candidate_sources] == ["README.md"]
    ignored = {item.path: item.reason for item in result.ignored_paths}
    assert ignored["local-agent/"] == "splendorignore"
    assert ignored["docs/private-cache/"] == "splendorignore"
    assert "local-agent/settings.json" not in ignored


def test_repo_scan_apply_requires_explicit_class_or_all(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")

    with pytest.raises(ValueError, match="requires at least one --class filter or --all"):
        apply_repo_scan(tmp_path)


def test_repo_scan_apply_refuses_large_candidate_set_without_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_workspace(tmp_path)
    for index in range(3):
        (tmp_path / f"doc-{index}.md").write_text(f"# Doc {index}\n", encoding="utf-8")
    monkeypatch.setattr("splendor.commands.repo_scan.LARGE_APPLY_CANDIDATE_LIMIT", 2)

    with pytest.raises(RuntimeError, match="refused 3 candidates"):
        apply_repo_scan(tmp_path, class_filters=["documentation"])

    result = apply_repo_scan(
        tmp_path,
        class_filters=["documentation"],
        allow_large_apply=True,
    )
    assert result.registered == 3


def test_repo_scan_report_writes_only_requested_report(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")

    result = write_repo_scan_report(scan_repo(tmp_path), tmp_path / "scan-report.json")
    payload = json.loads((tmp_path / "scan-report.json").read_text(encoding="utf-8"))

    assert result.report_path.endswith("scan-report.json")
    assert payload["candidate_sources"][0]["path"] == "README.md"
    assert _manifest_paths(tmp_path) == []
