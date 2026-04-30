"""Read-only local web UI for Splendor workspaces."""

from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import bleach
import markdown as markdown_lib
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from splendor.commands.planning import model_for_planning_kind
from splendor.commands.query import QueryMatch, QueryValidationError, run_query
from splendor.config import load_config
from splendor.layout import ResolvedLayout, resolve_layout
from splendor.state.paths import resolve_workspace_path
from splendor.utils.planning import parse_planning_document
from splendor.utils.wiki import parse_wiki_markdown

_LOGGER = logging.getLogger(__name__)
_ALLOWED_MARKDOWN_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "pre",
    "span",
    "img",
    "hr",
    "br",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}
_ALLOWED_MARKDOWN_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": [*bleach.sanitizer.ALLOWED_ATTRIBUTES.get("a", []), "href", "title"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "span": ["class"],
}


@dataclass(frozen=True)
class _DocumentSummary:
    path: str
    title: str
    document_class: str
    kind: str | None
    status: str | None


@dataclass(frozen=True)
class _DocumentDetail:
    path: str
    title: str
    document_class: str
    kind: str | None
    status: str | None
    metadata: dict[str, object]
    body: str


class WebLayoutError(ValueError):
    """Raised when configured web document roots are unsafe to serve."""


def create_app(root: Path) -> FastAPI:
    """Create the read-only Splendor web application for a workspace root."""
    workspace_root = root.resolve()
    app = FastAPI(title="Splendor", docs_url=None, redoc_url=None)

    @app.exception_handler(HTTPException)
    def http_error(_, exc: HTTPException) -> HTMLResponse:
        title = "Not Found" if exc.status_code == 404 else "Request Error"
        if exc.status_code >= 500:
            title = "Workspace Error"
        detail = html.escape(str(exc.detail))
        return _page(title, f'<p class="empty">{detail}</p>', status_code=exc.status_code)

    @app.exception_handler(WebLayoutError)
    def workspace_layout_error(_, __: WebLayoutError) -> HTMLResponse:
        _LOGGER.exception("Workspace configuration error.")
        return _page(
            "Workspace Error",
            '<p class="empty">Workspace configuration is invalid.</p>',
            status_code=500,
        )

    @app.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        documents = _iter_documents(workspace_root, layout)
        wiki_count = sum(1 for item in documents if item.document_class == "wiki")
        planning_count = sum(1 for item in documents if item.document_class == "planning")
        body = (
            '<section class="toolbar">'
            '<form action="/search" method="get">'
            '<input type="search" name="q" placeholder="Search wiki and planning" />'
            '<button type="submit">Search</button>'
            "</form>"
            '<a class="button" href="/browse">Browse documents</a>'
            "</section>"
            '<section class="stats">'
            f"<div><strong>{len(documents)}</strong><span>Documents</span></div>"
            f"<div><strong>{wiki_count}</strong><span>Wiki pages</span></div>"
            f"<div><strong>{planning_count}</strong><span>Planning records</span></div>"
            "</section>"
        )
        return _page("Splendor", body)

    @app.get("/browse", response_class=HTMLResponse)
    def browse() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        documents = _iter_documents(workspace_root, layout)
        rows = "\n".join(_document_row(item) for item in documents)
        body = (
            '<section class="toolbar">'
            '<form action="/search" method="get">'
            '<input type="search" name="q" placeholder="Search wiki and planning" />'
            '<button type="submit">Search</button>'
            "</form>"
            "</section>"
            f"<table><thead><tr><th>Title</th><th>Kind</th><th>Status</th><th>Path</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        return _page("Browse", body)

    @app.get("/documents/{document_path:path}", response_class=HTMLResponse)
    def document(document_path: str) -> HTMLResponse:
        layout = _layout_for(workspace_root)
        path = _safe_document_path(workspace_root, layout, document_path)
        detail = _document_detail(workspace_root, layout, path)
        metadata = html.escape(json.dumps(detail.metadata, indent=2, sort_keys=True))
        body_html = _render_markdown(detail.body)
        body = (
            '<p class="breadcrumbs"><a href="/browse">Browse</a> / '
            f"{html.escape(detail.path)}</p>"
            '<section class="metadata">'
            f"<div><strong>Class</strong><span>{html.escape(detail.document_class)}</span></div>"
            f"<div><strong>Kind</strong><span>{html.escape(detail.kind or '-')}</span></div>"
            f"<div><strong>Status</strong><span>{html.escape(detail.status or '-')}</span></div>"
            f"<pre>{metadata}</pre>"
            "</section>"
            f'<article class="markdown">{body_html}</article>'
        )
        return _page(detail.title, body)

    @app.get("/search", response_class=HTMLResponse)
    def search(q: str = Query(default="")) -> HTMLResponse:
        query = q.strip()
        form = (
            '<section class="toolbar">'
            '<form action="/search" method="get">'
            f'<input type="search" name="q" value="{html.escape(query)}" '
            'placeholder="Search wiki and planning" />'
            '<button type="submit">Search</button>'
            "</form>"
            "</section>"
        )
        if not query:
            return _page("Search", form)
        try:
            result = run_query(workspace_root, query)
        except QueryValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError:
            _LOGGER.exception("Search failed while parsing workspace records.")
            return _page(
                "Search Error",
                f"{form}"
                '<p class="empty">'
                "Search failed because the workspace contains invalid records."
                "</p>",
                status_code=500,
            )

        rows = "\n".join(_search_row(match) for match in result.matches)
        if not rows:
            rows = '<p class="empty">No matches found.</p>'
        body = f"{form}<p>{html.escape(result.summary)}</p><section>{rows}</section>"
        return _page("Search", body)

    return app


def _layout_for(root: Path) -> ResolvedLayout:
    config = load_config(root)
    _validate_layout_root(root, config.layout.wiki_dir, label="wiki_dir")
    _validate_layout_root(root, config.layout.planning_dir, label="planning_dir")
    return resolve_layout(root, config)


def _validate_layout_root(root: Path, value: str, *, label: str) -> None:
    path = Path(value)
    if "\\" in value or path.is_absolute() or not path.parts or ".." in path.parts:
        raise WebLayoutError(f"Configured {label} must be a workspace-relative directory: {value}")
    resolved = (root / path).resolve()
    workspace_root = root.resolve()
    if resolved == workspace_root:
        raise WebLayoutError(f"Configured {label} must not be the workspace root: {value}")
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise WebLayoutError(
            f"Configured {label} must resolve inside the workspace root: {value}"
        ) from exc


def _iter_documents(root: Path, layout: ResolvedLayout) -> list[_DocumentSummary]:
    documents: list[_DocumentSummary] = []
    for path in sorted(layout.wiki_dir.rglob("*.md")):
        if path.name == ".gitkeep" or not path.is_file():
            continue
        documents.append(_document_summary(root, layout, path))
    for path in sorted(layout.planning_dir.rglob("*.md")):
        if path.name == ".gitkeep" or not path.is_file():
            continue
        documents.append(_document_summary(root, layout, path))
    return sorted(documents, key=lambda item: (item.document_class, item.kind or "", item.title))


def _document_summary(root: Path, layout: ResolvedLayout, path: Path) -> _DocumentSummary:
    detail = _document_detail(root, layout, path)
    return _DocumentSummary(
        path=detail.path,
        title=detail.title,
        document_class=detail.document_class,
        kind=detail.kind,
        status=detail.status,
    )


def _document_detail(root: Path, layout: ResolvedLayout, path: Path) -> _DocumentDetail:
    relative_path = path.relative_to(root).as_posix()
    if path.is_relative_to(layout.wiki_dir):
        try:
            parsed = parse_wiki_markdown(path)
        except ValueError:
            body = path.read_text(encoding="utf-8")
            return _DocumentDetail(
                path=relative_path,
                title=_title_from_markdown(body, relative_path),
                document_class="wiki",
                kind=None,
                status=None,
                metadata={},
                body=body,
            )
        frontmatter = parsed.frontmatter
        return _DocumentDetail(
            path=relative_path,
            title=frontmatter.title,
            document_class="wiki",
            kind=frontmatter.kind,
            status=frontmatter.status,
            metadata=frontmatter.model_dump(mode="json"),
            body=parsed.body,
        )

    planning_kind = _planning_kind(layout, path)
    if planning_kind is None:
        body = path.read_text(encoding="utf-8")
        return _DocumentDetail(
            path=relative_path,
            title=_title_from_markdown(body, relative_path),
            document_class="planning",
            kind=None,
            status=None,
            metadata={},
            body=body,
        )
    try:
        parsed = parse_planning_document(path, model_for_planning_kind(planning_kind))
    except ValueError:
        body = path.read_text(encoding="utf-8")
        return _DocumentDetail(
            path=relative_path,
            title=_title_from_markdown(body, relative_path),
            document_class="planning",
            kind=planning_kind,
            status=None,
            metadata={},
            body=body,
        )
    record = parsed.record
    metadata = record.model_dump(mode="json")
    status = metadata.get("status")
    return _DocumentDetail(
        path=relative_path,
        title=record.title,
        document_class="planning",
        kind=planning_kind,
        status=status if isinstance(status, str) else None,
        metadata=metadata,
        body=parsed.body,
    )


def _planning_kind(layout: ResolvedLayout, path: Path) -> str | None:
    relative_parts = path.relative_to(layout.planning_dir).parts
    if not relative_parts:
        return None
    return {
        "tasks": "task",
        "milestones": "milestone",
        "decisions": "decision",
        "questions": "question",
    }.get(relative_parts[0])


def _safe_document_path(root: Path, layout: ResolvedLayout, document_path: str) -> Path:
    pure_path = PurePosixPath(document_path)
    if "\\" in document_path:
        raise HTTPException(status_code=404, detail="Document not found")
    if pure_path.is_absolute() or ".." in pure_path.parts or pure_path.suffix != ".md":
        raise HTTPException(status_code=404, detail="Document not found")
    if not pure_path.parts:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        path = resolve_workspace_path(root, document_path, context="Document")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    allowed_roots = (layout.wiki_dir.resolve(), layout.planning_dir.resolve())
    if not any(path.is_relative_to(allowed_root) for allowed_root in allowed_roots):
        raise HTTPException(status_code=404, detail="Document not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    return path


def _render_markdown(markdown_text: str) -> str:
    rendered = markdown_lib.markdown(
        markdown_text,
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    return bleach.clean(
        rendered,
        tags=_ALLOWED_MARKDOWN_TAGS,
        attributes=_ALLOWED_MARKDOWN_ATTRIBUTES,
    )


def _title_from_markdown(markdown_text: str, fallback: str) -> str:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip() or fallback
    return fallback


def _document_row(document: _DocumentSummary) -> str:
    href = f"/documents/{quote(document.path, safe='/')}"
    return (
        "<tr>"
        f'<td><a href="{href}">{html.escape(document.title)}</a></td>'
        f"<td>{html.escape(document.kind or '-')}</td>"
        f"<td>{html.escape(document.status or '-')}</td>"
        f"<td><code>{html.escape(document.path)}</code></td>"
        "</tr>"
    )


def _search_row(match: QueryMatch) -> str:
    href = f"/documents/{quote(match.path, safe='/')}"
    status = f" · {html.escape(match.status)}" if match.status else ""
    return (
        '<article class="result">'
        f'<h2><a href="{href}">{html.escape(match.title)}</a></h2>'
        f"<p><code>{html.escape(match.path)}</code> · {html.escape(match.kind)}{status}</p>"
        f"<p>{html.escape(match.snippet)}</p>"
        "</article>"
    )


def _page(title: str, body: str, *, status_code: int = 200) -> HTMLResponse:
    escaped_title = html.escape(title)
    return HTMLResponse(
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        f"<title>{escaped_title} · Splendor</title>"
        "<style>"
        ":root{color-scheme:light;--border:#d8dee8;--text:#1f2937;--muted:#5f6b7a;"
        "--surface:#f8fafc;--accent:#0f766e}"
        "body{margin:0;font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"
        "'Segoe UI',sans-serif;"
        "color:var(--text);background:white}"
        "header{border-bottom:1px solid var(--border);padding:18px 28px;background:var(--surface)}"
        "main{max-width:1060px;margin:0 auto;padding:28px}"
        "h1{font-size:28px;margin:0}h2{font-size:18px;margin:0 0 6px}"
        "a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}"
        ".toolbar{display:flex;gap:14px;align-items:center;margin-bottom:22px;flex-wrap:wrap}"
        "form{display:flex;gap:8px;align-items:center;flex:1;min-width:260px}"
        "input{border:1px solid var(--border);border-radius:6px;padding:9px 10px;"
        "font:inherit;flex:1}"
        "button,.button{border:1px solid var(--accent);border-radius:6px;background:var(--accent);"
        "color:white;padding:9px 12px;font:inherit;cursor:pointer}"
        ".stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}"
        ".stats div,.metadata,.result{border:1px solid var(--border);border-radius:8px;"
        "padding:14px}"
        ".stats strong{display:block;font-size:26px}.stats span,.breadcrumbs{color:var(--muted)}"
        "table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid var(--border);"
        "padding:10px;text-align:left;vertical-align:top}th{background:var(--surface)}"
        "code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}"
        "pre{overflow:auto;background:var(--surface);border-radius:6px;padding:12px}"
        ".metadata{display:grid;gap:10px;margin-bottom:24px;background:var(--surface)}"
        ".metadata div{display:flex;gap:10px}.metadata strong{width:70px}"
        ".markdown{max-width:820px}.markdown img{max-width:100%}.result{margin:0 0 12px}"
        ".empty{color:var(--muted)}"
        "</style>"
        "</head>"
        "<body>"
        f"<header><h1>{escaped_title}</h1></header>"
        f"<main>{body}</main>"
        "</body></html>",
        status_code=status_code,
    )
