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
from splendor.commands.wiki import build_wiki_status, load_sources, suggest_source_pages
from splendor.config import load_config
from splendor.layout import ResolvedLayout, resolve_layout
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import load_run_record
from splendor.state.source_compat import canonical_source_ref
from splendor.state.source_registry import load_source_record
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
class _WorkspaceCounts:
    wiki_content_pages: int
    planning_records: int
    source_manifests: int
    runs: int

    @property
    def is_sparse(self) -> bool:
        return (
            self.wiki_content_pages == 0
            and self.planning_records == 0
            and self.source_manifests == 0
            and self.runs == 0
        )


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
        content_documents = _iter_content_documents(workspace_root, layout)
        counts = _workspace_counts(layout, content_documents=content_documents)
        empty_state = _empty_workspace_panel() if counts.is_sparse else ""
        body = (
            '<section class="toolbar">'
            '<form action="/search" method="get">'
            '<input type="search" name="q" placeholder="Search wiki and planning" />'
            '<button type="submit">Search</button>'
            "</form>"
            '<a class="button" href="/browse">Browse documents</a>'
            '<a class="button secondary" href="/status">Status</a>'
            "</section>"
            f"{empty_state}"
            '<section class="stats">'
            f"<div><strong>{counts.wiki_content_pages}</strong>"
            "<span>Wiki content pages</span></div>"
            f"<div><strong>{counts.planning_records}</strong><span>Planning records</span></div>"
            f"<div><strong>{counts.source_manifests}</strong><span>Source manifests</span></div>"
            f"<div><strong>{counts.runs}</strong><span>Runs</span></div>"
            "</section>"
        )
        return _page("Splendor", body)

    @app.get("/status", response_class=HTMLResponse)
    def status() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        status_result = build_wiki_status(workspace_root)
        source_rows = "\n".join(
            _source_row(workspace_root, source) for source in load_sources(layout)
        )
        if not source_rows:
            source_rows = '<tr><td colspan="5" class="empty">No source manifests yet.</td></tr>'
        recent_runs = "\n".join(
            "<li>"
            f"<code>{html.escape(run.run_id)}</code> {html.escape(run.status)} "
            f"finished={html.escape(run.finished_at or '-')}"
            "</li>"
            for run in status_result.recent_runs
        )
        if not recent_runs:
            recent_runs = '<li class="empty">No runs yet.</li>'
        invalid_pages = "\n".join(
            f"<li><code>{html.escape(page.path)}</code>: {html.escape(page.error)}</li>"
            for page in status_result.invalid_page_examples
        )
        invalid_section = ""
        if invalid_pages:
            invalid_section = f"<h2>Invalid wiki pages</h2><ul>{invalid_pages}</ul>"
        body = (
            '<p class="breadcrumbs"><a href="/">Home</a> / Status</p>'
            '<section class="stats">'
            f"<div><strong>{status_result.source_total}</strong><span>Sources</span></div>"
            f"<div><strong>{status_result.page_total}</strong><span>Pages</span></div>"
            f"<div><strong>{status_result.queue_total}</strong><span>Queue records</span></div>"
            f"<div><strong>{status_result.run_total}</strong><span>Runs</span></div>"
            f"<div><strong>{status_result.review_needed_pages}</strong>"
            "<span>Review needed</span></div>"
            f"<div><strong>{status_result.sources_missing_synthesis}</strong>"
            "<span>Synthesis follow-up</span></div>"
            "</section>"
            "<h2>Review state</h2>"
            f"<p>{html.escape(_format_counts(status_result.review_state_counts)) or '-'}</p>"
            "<h2>Queue</h2>"
            f"<p>{html.escape(_format_counts(status_result.queue_status_counts)) or '-'}</p>"
            "<h2>Recent runs</h2>"
            f"<ul>{recent_runs}</ul>"
            f"{invalid_section}"
            "<h2>Sources</h2>"
            "<table><thead><tr><th>Source</th><th>Status</th><th>Review</th>"
            "<th>Summary page</th><th>Source ref</th></tr></thead>"
            f"<tbody>{source_rows}</tbody></table>"
        )
        return _page("Status", body)

    @app.get("/sources/{source_id}", response_class=HTMLResponse)
    def source_detail(source_id: str) -> HTMLResponse:
        layout = _layout_for(workspace_root)
        source = _load_source_for_web(layout, source_id)
        summary_links = "".join(
            f'<li><a href="/documents/{quote(path, safe="/")}">'
            f"<code>{html.escape(path)}</code></a></li>"
            for path in source.linked_pages
        )
        if not summary_links:
            summary_links = '<li class="empty">No generated source-summary page linked yet.</li>'
        run_section = _source_run_section(workspace_root, layout, source.last_run_id)
        suggestions = suggest_source_pages(workspace_root, source.source_id).suggestions
        suggestion_rows = "\n".join(_suggestion_row(suggestion) for suggestion in suggestions)
        if not suggestion_rows:
            suggestion_rows = (
                '<tr><td colspan="4" class="empty">'
                "No likely synthesis-page matches found.</td></tr>"
            )
        manifest_ref = (layout.source_records_dir / f"{source.source_id}.json").relative_to(
            workspace_root
        )
        body = (
            '<p class="breadcrumbs"><a href="/status">Status</a> / '
            f"{html.escape(source.source_id)}</p>"
            '<section class="metadata">'
            f"<div><strong>Status</strong><span>{html.escape(source.status)}</span></div>"
            f"<div><strong>Review</strong><span>{html.escape(source.review_state)}</span></div>"
            f"<div><strong>Type</strong><span>{html.escape(source.source_type)}</span></div>"
            f"<div><strong>Storage</strong><span>{html.escape(source.storage_mode or '-')}"
            "</span></div>"
            f"<div><strong>Manifest</strong><span><code>{html.escape(manifest_ref.as_posix())}"
            "</code></span></div>"
            "</section>"
            "<h2>Source ref</h2>"
            f"<p><code>{html.escape(canonical_source_ref(source))}</code></p>"
            "<h2>Generated source-summary pages</h2>"
            f"<ul>{summary_links}</ul>"
            f"{run_section}"
            "<h2>Affected synthesis-page suggestions</h2>"
            "<table><thead><tr><th>Page</th><th>Kind</th><th>Score</th><th>Reasons</th></tr></thead>"
            f"<tbody>{suggestion_rows}</tbody></table>"
        )
        return _page(source.title, body)

    @app.get("/browse", response_class=HTMLResponse)
    def browse() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        content_documents = _iter_content_documents(workspace_root, layout)
        special_documents = _iter_special_documents(workspace_root, layout)
        counts = _workspace_counts(layout, content_documents=content_documents)
        content_rows = "\n".join(_document_row(item) for item in content_documents)
        special_rows = "\n".join(_document_row(item) for item in special_documents)
        if not content_rows:
            content_rows = (
                '<tr><td colspan="4" class="empty">No searchable content records yet.</td></tr>'
            )
        special_section = ""
        if special_rows:
            special_section = (
                "<h2>Special files</h2>"
                '<p class="empty">Index and log files are navigation records shown here, '
                "but excluded from search results.</p>"
                "<table><thead><tr><th>Title</th><th>Kind</th><th>Status</th><th>Path</th></tr></thead>"
                f"<tbody>{special_rows}</tbody></table>"
            )
        empty_state = _empty_workspace_panel() if counts.is_sparse else ""
        body = (
            '<section class="toolbar">'
            '<form action="/search" method="get">'
            '<input type="search" name="q" placeholder="Search wiki and planning" />'
            '<button type="submit">Search</button>'
            "</form>"
            "</section>"
            f"{empty_state}"
            "<h2>Content records</h2>"
            "<table><thead><tr><th>Title</th><th>Kind</th><th>Status</th><th>Path</th></tr></thead>"
            f"<tbody>{content_rows}</tbody></table>"
            f"{special_section}"
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
        layout = _layout_for(workspace_root)
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
            content_documents = _iter_content_documents(workspace_root, layout)
            counts = _workspace_counts(layout, content_documents=content_documents)
            if counts.is_sparse:
                rows = (
                    '<p class="empty">No matches found. This workspace only has special '
                    "navigation files like index/log, which are excluded from search. "
                    "Use <code>uv run splendor repo refresh</code> or "
                    "<code>uv run splendor add-source &lt;path&gt;</code> to add searchable "
                    "knowledge records.</p>"
                )
            else:
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


def _iter_content_documents(root: Path, layout: ResolvedLayout) -> list[_DocumentSummary]:
    documents: list[_DocumentSummary] = []
    for path in sorted(layout.wiki_dir.rglob("*.md")):
        if path.name == ".gitkeep" or not path.is_file():
            continue
        if path in {layout.index_file, layout.log_file}:
            continue
        documents.append(_document_summary(root, layout, path))
    for path in sorted(layout.planning_dir.rglob("*.md")):
        if path.name == ".gitkeep" or not path.is_file():
            continue
        documents.append(_document_summary(root, layout, path))
    return sorted(documents, key=lambda item: (item.document_class, item.kind or "", item.title))


def _iter_special_documents(root: Path, layout: ResolvedLayout) -> list[_DocumentSummary]:
    documents: list[_DocumentSummary] = []
    for path in (layout.index_file, layout.log_file):
        if path.is_file():
            documents.append(_document_summary(root, layout, path))
    return documents


def _workspace_counts(
    layout: ResolvedLayout, *, content_documents: list[_DocumentSummary]
) -> _WorkspaceCounts:
    return _WorkspaceCounts(
        wiki_content_pages=sum(1 for item in content_documents if item.document_class == "wiki"),
        planning_records=sum(1 for item in content_documents if item.document_class == "planning"),
        source_manifests=sum(
            1 for path in layout.source_records_dir.glob("*.json") if path.is_file()
        ),
        runs=sum(1 for path in layout.runs_dir.glob("*.json") if path.is_file()),
    )


def _format_counts(counts: dict[str, int]) -> str:
    return " ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _empty_workspace_panel() -> str:
    return (
        '<section class="empty-state">'
        "<h2>No workspace knowledge yet</h2>"
        "<p>This workspace has only navigation files. Seed it with deterministic repo pages or "
        "register a source before browsing/searching knowledge records.</p>"
        "<p><code>uv run splendor repo refresh</code></p>"
        "<p><code>uv run splendor add-source &lt;path&gt;</code></p>"
        "</section>"
    )


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


def _source_row(root: Path, source) -> str:
    href = f"/sources/{quote(source.source_id)}"
    summary = source.linked_pages[0] if source.linked_pages else "-"
    summary_html = html.escape(summary)
    if source.linked_pages:
        summary_href = f"/documents/{quote(summary, safe='/')}"
        summary_html = f'<a href="{summary_href}"><code>{summary_html}</code></a>'
    return (
        "<tr>"
        f'<td><a href="{href}">{html.escape(source.title)}</a><br />'
        f"<code>{html.escape(source.source_id)}</code></td>"
        f"<td>{html.escape(source.status)}</td>"
        f"<td>{html.escape(source.review_state)}</td>"
        f"<td>{summary_html}</td>"
        f"<td><code>{html.escape(canonical_source_ref(source))}</code></td>"
        "</tr>"
    )


def _load_source_for_web(layout: ResolvedLayout, source_id: str):
    if "\\" in source_id or "/" in source_id or ".." in source_id:
        raise HTTPException(status_code=404, detail="Source not found")
    manifest_path = layout.source_records_dir / f"{source_id}.json"
    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        return load_source_record(manifest_path)
    except ValueError:
        _LOGGER.exception("Source manifest failed validation.")
        raise HTTPException(status_code=500, detail="Source manifest is invalid") from None


def _source_run_section(root: Path, layout: ResolvedLayout, run_id: str | None) -> str:
    if run_id is None:
        return '<h2>Latest ingest run</h2><p class="empty">No ingest run linked yet.</p>'
    run_path = layout.runs_dir / f"{run_id}.json"
    if not run_path.is_file():
        return (
            "<h2>Latest ingest run</h2>"
            f'<p class="empty">Linked run <code>{html.escape(run_id)}</code> is missing.</p>'
        )
    run = load_run_record(run_path)
    run_ref = run_path.relative_to(root).as_posix()
    pages = ", ".join(run.page_refs) if run.page_refs else "-"
    return (
        "<h2>Latest ingest run</h2>"
        '<section class="metadata">'
        f"<div><strong>Run</strong><span><code>{html.escape(run.run_id)}</code></span></div>"
        f"<div><strong>Status</strong><span>{html.escape(run.status)}</span></div>"
        f"<div><strong>Finished</strong><span>{html.escape(run.finished_at or '-')}</span></div>"
        f"<div><strong>Record</strong><span><code>{html.escape(run_ref)}</code></span></div>"
        f"<div><strong>Pages</strong><span>{html.escape(pages)}</span></div>"
        "</section>"
    )


def _suggestion_row(suggestion) -> str:
    href = f"/documents/{quote(suggestion.path, safe='/')}"
    reasons = ", ".join(suggestion.reasons) if suggestion.reasons else "-"
    return (
        "<tr>"
        f'<td><a href="{href}">{html.escape(suggestion.title)}</a><br />'
        f"<code>{html.escape(suggestion.path)}</code></td>"
        f"<td>{html.escape(suggestion.kind)}</td>"
        f"<td>{suggestion.score}</td>"
        f"<td>{html.escape(reasons)}</td>"
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
        ".button.secondary{background:white;color:var(--accent)}"
        ".stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}"
        ".stats div,.metadata,.result,.empty-state{border:1px solid var(--border);"
        "border-radius:8px;"
        "padding:14px}"
        ".stats strong{display:block;font-size:26px}.stats span,.breadcrumbs{color:var(--muted)}"
        ".empty-state{background:var(--surface);margin-bottom:22px}"
        ".empty-state h2{margin-bottom:8px}"
        ".empty-state p{margin:8px 0}"
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
