from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from splendor.commands.init import initialize_workspace
from splendor.commands.planning import create_task
from splendor.schemas import KnowledgePageFrontmatter
from splendor.web import create_app


def write_wiki_page(path: Path, *, title: str, page_id: str, body: str) -> None:
    frontmatter = KnowledgePageFrontmatter(
        kind="concept",
        title=title,
        page_id=page_id,
        status="active",
        confidence=0.8,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    path.write_text(f"---\n{frontmatter_text}\n---\n\n{body}", encoding="utf-8")


def test_home_page_loads_for_initialized_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Splendor" in response.text
    assert "Wiki content pages" in response.text
    assert "/browse" in response.text


def test_home_page_shows_empty_state_for_initialized_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "No workspace knowledge yet" in response.text
    assert "uv run splendor repo refresh" in response.text
    assert "uv run splendor add-source" in response.text
    assert "Wiki content pages" in response.text
    assert "Source manifests" in response.text


def test_browse_page_lists_wiki_and_planning_documents(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "web-shell.md",
        title="Web shell",
        page_id="concept-web-shell",
        body="# Web shell\n",
    )
    create_task(
        tmp_path,
        "Ship web shell",
        record_id="task-ship-web-shell",
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/browse")

    assert response.status_code == 200
    assert "Web shell" in response.text
    assert "Ship web shell" in response.text
    assert "wiki/concepts/web-shell.md" in response.text
    assert "planning/tasks/task-ship-web-shell.md" in response.text


def test_browse_page_separates_index_and_log_as_special_files(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/browse")

    assert response.status_code == 200
    assert "No searchable content records yet." in response.text
    assert "Special files" in response.text
    assert "excluded from search results" in response.text
    assert "wiki/index.md" in response.text
    assert "wiki/log.md" in response.text


def test_document_detail_renders_markdown_and_metadata(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "web-shell.md",
        title="Web shell",
        page_id="concept-web-shell",
        body="# Web shell\n\nThis page describes local browsing.\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/wiki/concepts/web-shell.md")

    assert response.status_code == 200
    assert "<h1>Web shell</h1>" in response.text
    assert "This page describes local browsing." in response.text
    assert "concept-web-shell" in response.text
    assert "active" in response.text


def test_document_detail_renders_planning_task(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_task(
        tmp_path,
        "Ship web shell",
        record_id="task-ship-web-shell",
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/planning/tasks/task-ship-web-shell.md")

    assert response.status_code == 200
    assert "Ship web shell" in response.text
    assert "todo" in response.text


def test_document_detail_falls_back_for_invalid_planning_frontmatter(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    task_path = tmp_path / "planning" / "tasks" / "task-bad.md"
    task_path.write_text("# Broken Task\n\nThis task has no frontmatter.\n", encoding="utf-8")
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/planning/tasks/task-bad.md")

    assert response.status_code == 200
    assert "Broken Task" in response.text
    assert "This task has no frontmatter." in response.text


def test_search_returns_query_matches_with_document_links(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "web-shell.md",
        title="Web shell",
        page_id="concept-web-shell",
        body="# Web shell\n\nDeterministic browse search lives here.\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/search", params={"q": "browse search"})

    assert response.status_code == 200
    assert 'href="/documents/wiki/concepts/web-shell.md"' in response.text
    assert "Deterministic browse search lives here." in response.text


def test_document_detail_rejects_unsafe_or_unsupported_paths(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    traversal = client.get("/documents/%2E%2E/pyproject.toml")
    backslash_traversal = client.get("/documents/wiki%5C..%5Csplendor.yaml")
    non_markdown = client.get("/documents/wiki/secrets.yaml")
    unsupported_root = client.get("/documents/raw/source.md")

    assert traversal.status_code == 404
    assert backslash_traversal.status_code == 404
    assert non_markdown.status_code == 404
    assert unsupported_root.status_code == 404


def test_search_returns_generic_error_for_invalid_workspace_record(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    bad_page = tmp_path / "wiki" / "concepts" / "bad.md"
    bad_page.write_text("---\nkind: concept\nbogus: true\n---\n\nbad body\n", encoding="utf-8")
    client = TestClient(create_app(tmp_path))

    response = client.get("/search", params={"q": "bad"})

    assert response.status_code == 500
    assert "invalid records" in response.text
    assert str(bad_page) not in response.text


def test_search_returns_bad_request_for_invalid_query_text(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/search", params={"q": "!!!"})

    assert response.status_code == 400
    assert "Query must contain at least one ASCII letter or number" in response.text


def test_search_empty_state_mentions_special_files_for_sparse_workspace(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/search", params={"q": "splendor"})

    assert response.status_code == 200
    assert "special navigation files" in response.text
    assert "excluded from search" in response.text
    assert "uv run splendor repo refresh" in response.text


def test_document_links_respect_custom_layout_directories(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\n"
        "project_name: custom\n"
        "layout:\n"
        "  wiki_dir: knowledge\n"
        "  planning_dir: plans\n",
        encoding="utf-8",
    )
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "knowledge" / "concepts" / "web-shell.md",
        title="Custom web shell",
        page_id="concept-custom-web-shell",
        body="# Custom web shell\n",
    )
    client = TestClient(create_app(tmp_path))

    browse = client.get("/browse")
    detail = client.get("/documents/knowledge/concepts/web-shell.md")

    assert browse.status_code == 200
    assert 'href="/documents/knowledge/concepts/web-shell.md"' in browse.text
    assert detail.status_code == 200
    assert "<h1>Custom web shell</h1>" in detail.text


def test_web_routes_reject_layout_roots_that_escape_workspace(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\n"
        "project_name: custom\n"
        "layout:\n"
        "  wiki_dir: ..\n"
        "  planning_dir: planning\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    response = client.get("/")

    assert response.status_code == 500
    assert "Workspace configuration is invalid." in response.text


def test_search_rejects_layout_roots_that_escape_workspace(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\n"
        "project_name: custom\n"
        "layout:\n"
        "  wiki_dir: ..\n"
        "  planning_dir: planning\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False)

    response = client.get("/search", params={"q": "secret"})

    assert response.status_code == 500
    assert "Workspace configuration is invalid." in response.text


def test_document_detail_preserves_code_text_while_sanitizing_html(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "code.md",
        title="Code",
        page_id="concept-code",
        body="# Code\n\n```python\nx < y && y > z\n```\n\n<script>alert('x')</script>\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/wiki/concepts/code.md")

    assert response.status_code == 200
    assert "x &lt; y &amp;&amp; y &gt; z" in response.text
    assert "x &amp;lt; y" not in response.text
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;alert" in response.text


def test_document_detail_escapes_raw_html_in_markdown(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    write_wiki_page(
        tmp_path / "wiki" / "concepts" / "unsafe.md",
        title="Unsafe",
        page_id="concept-unsafe",
        body="# Unsafe\n\n<script>alert('x')</script>\n",
    )
    client = TestClient(create_app(tmp_path))

    response = client.get("/documents/wiki/concepts/unsafe.md")

    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;alert" in response.text
