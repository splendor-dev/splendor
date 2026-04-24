import json
from pathlib import Path

from splendor.commands.init import initialize_workspace
from splendor.commands.repo_refresh import refresh_repo, render_repo_refresh_json
from splendor.utils.wiki import parse_wiki_markdown


def _remove_workspace_config(root: Path) -> None:
    (root / "splendor.yaml").unlink(missing_ok=True)


def _write_repo_files(root: Path) -> None:
    (root / "README.md").write_text("# Readme\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    src_dir = root / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("print('hi')\n", encoding="utf-8")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    workflows_dir = root / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "ci.yml").write_text("name: CI\n", encoding="utf-8")


def test_repo_refresh_creates_architecture_and_topic_pages(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    _write_repo_files(tmp_path)

    result = refresh_repo(tmp_path)

    assert result.scan.scanned == 5
    assert result.generated_page_refs == [
        "wiki/architecture/repository-structure.md",
        "wiki/topics/repository-sources.md",
    ]
    assert len(result.linked_source_ids) == 5

    architecture = parse_wiki_markdown(tmp_path / result.generated_page_refs[0])
    topic = parse_wiki_markdown(tmp_path / result.generated_page_refs[1])
    assert architecture.frontmatter.kind == "architecture"
    assert architecture.frontmatter.page_id == "architecture-repository-structure"
    assert architecture.frontmatter.review_state == "machine-generated"
    assert architecture.frontmatter.related_pages == ["topic-repository-sources"]
    assert topic.frontmatter.kind == "topic"
    assert topic.frontmatter.page_id == "topic-repository-sources"
    assert topic.frontmatter.related_pages == ["architecture-repository-structure"]
    assert "src/main.py" in architecture.body
    assert "| `README.md` |" in topic.body
    assert architecture.frontmatter.source_refs == result.linked_source_ids
    assert topic.frontmatter.source_refs == result.linked_source_ids


def test_repo_refresh_is_repeatable_without_duplicate_index_or_log_entries(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    _write_repo_files(tmp_path)

    refresh_repo(tmp_path)
    refresh_repo(tmp_path)

    index = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    log = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert index.count("(`architecture-repository-structure`)") == 1
    assert index.count("(`topic-repository-sources`)") == 1
    assert log.count("Refreshed repo pages `wiki/architecture/repository-structure.md`") == 1


def test_render_repo_refresh_json_matches_expected_shape(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _remove_workspace_config(tmp_path)
    _write_repo_files(tmp_path)

    payload = json.loads(render_repo_refresh_json(refresh_repo(tmp_path)))

    assert payload["scanned"] == 5
    assert payload["registered"] == 5
    assert payload["already_registered"] == 0
    assert payload["class_counts"]["code"] == 2
    assert payload["generated_page_refs"] == [
        "wiki/architecture/repository-structure.md",
        "wiki/topics/repository-sources.md",
    ]
    assert len(payload["linked_source_ids"]) == 5
