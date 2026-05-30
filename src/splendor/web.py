"""Read-only local web UI for Splendor workspaces."""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import bleach
import markdown as markdown_lib
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from splendor.commands.planning import model_for_planning_kind
from splendor.commands.query import QueryMatch, QueryValidationError, run_query
from splendor.commands.wiki import build_wiki_status, load_sources, suggest_source_pages
from splendor.config import load_config
from splendor.layout import ResolvedLayout, resolve_layout
from splendor.schemas import QueueItemRecord, RunRecord
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import load_queue_item, load_run_record
from splendor.state.source_compat import canonical_source_ref
from splendor.state.source_registry import load_source_record
from splendor.utils.planning import (
    iter_planning_paths,
    parse_planning_document,
    planning_directory,
    record_id_field,
)
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
_LISTING_FRONTMATTER_LINE_LIMIT = 200
_LISTING_FRONTMATTER_CHAR_LIMIT = 64 * 1024
_LISTING_HEADING_LINE_LIMIT = 40
_LISTING_HEADING_CHAR_LIMIT = 16 * 1024
_IDENTITY_LINE_LIMIT = 80
_IDENTITY_CHAR_LIMIT = 32 * 1024
_GENERIC_INDEX_TITLE = "Splendor Wiki Index"
_GENERIC_INDEX_SUMMARY = "This wiki is maintained by Splendor."
_REVIEW_NEEDED_STATES = {"draft", "machine-generated", "contested", "stale"}
_ATTENTION_QUEUE_STATES = {"pending", "leased", "failed", "dead_letter"}
_ATTENTION_RUN_STATES = {"running", "failed"}
_ATTENTION_PLANNING_STATUSES = {"blocked", "proposed", "open"}


@dataclass(frozen=True)
class _DocumentSummary:
    path: str
    title: str
    document_class: str
    kind: str | None
    status: str | None
    review_state: str | None


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
class _ProjectIdentity:
    name: str
    summary: str | None


@dataclass(frozen=True)
class _DocumentDetail:
    path: str
    title: str
    document_class: str
    kind: str | None
    status: str | None
    metadata: dict[str, object]
    body: str


@dataclass(frozen=True)
class _KnowledgeMapItem:
    path: str
    title: str
    document_class: str
    kind: str | None
    status: str | None
    review_state: str | None
    tags: list[str]
    related_pages: list[str]
    source_refs: list[str]
    run_refs: list[str]
    provenance_links: list[dict[str, object]]


@dataclass(frozen=True)
class _DocumentRelationship:
    title: str
    href: str | None
    detail: str


@dataclass(frozen=True)
class _DocumentRelationships:
    related_pages: list[_DocumentRelationship]
    tags: list[_DocumentRelationship]
    sources: list[_DocumentRelationship]
    runs: list[_DocumentRelationship]
    provenance: list[_DocumentRelationship]
    backlinks: list[_DocumentRelationship]
    references: list[_DocumentRelationship]


@dataclass(frozen=True)
class _PlanningSummary:
    path: str
    kind: str
    record_id: str
    title: str
    status: str
    detail: str


@dataclass(frozen=True)
class _PlanningRoadmapLane:
    title: str
    description: str
    items: list[_PlanningSummary]
    empty: str


@dataclass(frozen=True)
class _PlanningRoadmapReadModel:
    lanes: list[_PlanningRoadmapLane]


@dataclass(frozen=True)
class _AttentionItem:
    kind: str
    title: str
    explanation: str
    href: str
    evidence: str
    cli_hint: str | None = None


@dataclass(frozen=True)
class _AttentionReadModel:
    items: list[_AttentionItem]

    @property
    def needs_attention(self) -> bool:
        return bool(self.items)

    @property
    def label(self) -> str:
        return "Needs attention" if self.needs_attention else "Healthy"

    @property
    def explanation(self) -> str:
        if self.needs_attention:
            return (
                "Local records contain review, runtime, queue, or planning state that should be "
                "inspected before relying on the workspace."
            )
        return (
            "No review-needed pages, failed or incomplete runs, queue records needing inspection, "
            "or blocked/open planning records were found."
        )


@dataclass(frozen=True)
class _QueueSummary:
    path: str
    record: QueueItemRecord


@dataclass(frozen=True)
class _RunSummary:
    path: str
    record: RunRecord


@dataclass(frozen=True)
class _CockpitLink:
    title: str
    href: str
    detail: str


@dataclass(frozen=True)
class _LogInsight:
    anchor: str
    title: str
    section: str
    timestamp: str | None


@dataclass(frozen=True)
class _RecentReadModel:
    log_path: str
    log_exists: bool
    log_body: str
    log_insights: list[_LogInsight]
    run_events: list[_CockpitLink]


@dataclass(frozen=True)
class _CockpitSection:
    title: str
    items: list[_CockpitLink]
    empty: str


@dataclass(frozen=True)
class _CockpitHomeReadModel:
    counts: _WorkspaceCounts
    roadmap: list[_CockpitSection]
    attention: _AttentionReadModel
    knowledge: list[_CockpitLink]
    recent_activity: list[_CockpitLink]
    inspect_next: list[_CockpitLink]


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
        return _page(
            title,
            f'<p class="empty">{detail}</p>',
            root=workspace_root,
            layout=_identity_layout_for(workspace_root),
            status_code=exc.status_code,
        )

    @app.exception_handler(WebLayoutError)
    def workspace_layout_error(_, __: WebLayoutError) -> HTMLResponse:
        _LOGGER.exception("Workspace configuration error.")
        return _page(
            "Workspace Error",
            '<p class="empty">Workspace configuration is invalid.</p>',
            root=workspace_root,
            layout=_identity_layout_for(workspace_root),
            status_code=500,
        )

    @app.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        read_model = _build_cockpit_home_read_model(workspace_root, layout)
        empty_state = _empty_workspace_panel() if read_model.counts.is_sparse else ""
        body = (
            '<section class="toolbar">'
            '<form action="/search" method="get">'
            '<input type="search" name="q" placeholder="Search wiki and planning" />'
            '<button type="submit">Search</button>'
            "</form>"
            '<a class="button" href="/browse">Browse documents</a>'
            '<a class="button secondary" href="/planning">Planning</a>'
            '<a class="button secondary" href="/recent">Recent</a>'
            '<a class="button secondary" href="/runs">Runs</a>'
            '<a class="button secondary" href="/queue">Queue</a>'
            '<a class="button secondary" href="/status">Status</a>'
            "</section>"
            f"{empty_state}"
            f"{_attention_summary_panel(read_model.attention)}"
            f"{_attention_section(read_model.attention, limit=4)}"
            '<section class="cockpit-grid">'
            f"{_cockpit_sections(read_model.roadmap)}"
            "</section>"
            '<section class="cockpit-grid">'
            f"{_cockpit_secondary_sections(read_model)}"
            "</section>"
            "<h2>Raw workspace counts</h2>"
            '<section class="stats">'
            f"<div><strong>{read_model.counts.wiki_content_pages}</strong>"
            "<span>Wiki content pages</span></div>"
            f"<div><strong>{read_model.counts.planning_records}</strong>"
            "<span>Planning records</span></div>"
            f"<div><strong>{read_model.counts.source_manifests}</strong>"
            "<span>Source manifests</span></div>"
            f"<div><strong>{read_model.counts.runs}</strong><span>Runs</span></div>"
            "</section>"
        )
        return _page("Home", body, root=workspace_root, layout=layout)

    @app.get("/status", response_class=HTMLResponse)
    def status() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        try:
            status_result = build_wiki_status(workspace_root)
            source_rows = "\n".join(_source_row(source) for source in load_sources(layout))
            attention = _build_attention_read_model(workspace_root, layout)
        except ValueError:
            _LOGGER.exception("Status failed while parsing workspace records.")
            return _page(
                "Status Error",
                '<p class="empty">'
                "Status failed because the workspace contains invalid records."
                "</p>",
                root=workspace_root,
                layout=layout,
                status_code=500,
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
            f"{_health_banner(attention)}"
            f"{_attention_section(attention, limit=8)}"
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
        return _page("Status", body, root=workspace_root, layout=layout)

    @app.get("/planning", response_class=HTMLResponse)
    def planning() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        try:
            grouped = {
                kind: _planning_records(workspace_root, layout, kind)
                for kind in ("task", "milestone", "decision", "question")
            }
        except ValueError:
            _LOGGER.exception("Planning view failed while parsing planning records.")
            return _page(
                "Planning Error",
                '<p class="empty">'
                "Planning view failed because the workspace contains invalid planning records."
                "</p>",
                root=workspace_root,
                layout=layout,
                status_code=500,
            )
        stats = "".join(
            f"<div><strong>{len(grouped[kind])}</strong>"
            f"<span>{html.escape(_planning_label(kind))}</span></div>"
            for kind in ("task", "milestone", "decision", "question")
        )
        roadmap = _build_planning_roadmap(grouped)
        attention = _attention_from_planning(grouped)
        sections = "".join(_planning_section(kind, records) for kind, records in grouped.items())
        body = (
            '<p class="breadcrumbs"><a href="/">Home</a> / Planning</p>'
            '<p class="empty">Planning records are grouped into deterministic roadmap lanes. '
            "Raw kind-specific tables remain available below for audit and debugging.</p>"
            f"{_attention_section(attention, limit=6)}"
            f"{_planning_roadmap(roadmap)}"
            '<details class="technical">'
            "<summary>Raw planning records</summary>"
            f'<section class="stats">{stats}</section>'
            f"{sections}"
            "</details>"
        )
        return _page("Planning", body, root=workspace_root, layout=layout)

    @app.get("/planning/{kind}", response_class=HTMLResponse)
    def planning_kind(kind: str) -> HTMLResponse:
        layout = _layout_for(workspace_root)
        normalized_kind = _normalize_planning_kind(kind)
        try:
            records = _planning_records(workspace_root, layout, normalized_kind)
        except ValueError:
            _LOGGER.exception("Planning view failed while parsing planning records.")
            return _page(
                "Planning Error",
                '<p class="empty">'
                "Planning view failed because the workspace contains invalid planning records."
                "</p>",
                root=workspace_root,
                layout=layout,
                status_code=500,
            )
        body = (
            '<p class="breadcrumbs"><a href="/planning">Planning</a> / '
            f"{html.escape(_planning_label(normalized_kind))}</p>"
            f"{_planning_table(normalized_kind, records)}"
        )
        return _page(_planning_label(normalized_kind), body, root=workspace_root, layout=layout)

    @app.get("/runs", response_class=HTMLResponse)
    def runs() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        try:
            run_records = _run_records(workspace_root, layout)
        except (ValueError, ValidationError):
            _LOGGER.exception("Runs view failed while parsing run records.")
            return _page(
                "Runs Error",
                '<p class="empty">'
                "Runs view failed because the workspace contains invalid run records."
                "</p>",
                root=workspace_root,
                layout=layout,
                status_code=500,
            )
        attention = _attention_from_runs(run_records)
        rows = "\n".join(_run_row(run) for run in _sort_runs_for_attention(run_records)[:25])
        if not rows:
            rows = '<tr><td colspan="9" class="empty">No run records yet.</td></tr>'
        body = (
            '<p class="breadcrumbs"><a href="/">Home</a> / Runs</p>'
            '<p class="empty">Recent run records are shown from durable filesystem state. '
            "This page does not start, retry, or mutate jobs.</p>"
            f"{_attention_section(attention, limit=6)}"
            "<table><thead><tr><th>Run</th><th>Status</th><th>Job</th><th>Started</th>"
            "<th>Finished</th><th>Sources</th><th>Pages</th><th>Warnings / Errors</th>"
            "<th>Record</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        return _page("Runs", body, root=workspace_root, layout=layout)

    @app.get("/queue", response_class=HTMLResponse)
    def queue() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        try:
            queue_records = _queue_records(workspace_root, layout)
        except (ValueError, ValidationError):
            _LOGGER.exception("Queue view failed while parsing queue records.")
            return _page(
                "Queue Error",
                '<p class="empty">'
                "Queue view failed because the workspace contains invalid queue records."
                "</p>",
                root=workspace_root,
                layout=layout,
                status_code=500,
            )
        status_counts: dict[str, int] = {}
        for item in queue_records:
            status_counts[item.record.status] = status_counts.get(item.record.status, 0) + 1
        attention = _attention_from_queue(queue_records)
        rows = "\n".join(_queue_row(item) for item in _sort_queue_for_attention(queue_records)[:50])
        if not rows:
            rows = '<tr><td colspan="11" class="empty">No queue records yet.</td></tr>'
        body = (
            '<p class="breadcrumbs"><a href="/">Home</a> / Queue</p>'
            f"{_attention_section(attention, limit=8)}"
            '<section class="stats">'
            f"<div><strong>{len(queue_records)}</strong><span>Queue records</span></div>"
            f"<div><strong>{html.escape(_format_counts(status_counts)) or '-'}</strong>"
            "<span>Status counts</span></div>"
            "</section>"
            '<p class="empty">Queue state is read-only here. Use CLI commands for ingestion, '
            "repair, retry, or other mutations.</p>"
            "<table><thead><tr><th>Job</th><th>Status</th><th>Type</th><th>Attempts</th>"
            "<th>Created</th><th>Updated</th><th>Payload</th><th>Lease</th>"
            "<th>Next attempt</th><th>Error</th><th>Record</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        return _page("Queue", body, root=workspace_root, layout=layout)

    @app.get("/recent", response_class=HTMLResponse)
    def recent() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        read_model = _build_recent_read_model(workspace_root, layout)
        if read_model.log_exists:
            log_ref = (
                f'<a href="/documents/{quote(read_model.log_path, safe="/")}">'
                f"<code>{html.escape(read_model.log_path)}</code></a>"
            )
            log_article = (
                f'<article class="markdown">{_render_markdown(read_model.log_body)}</article>'
            )
        else:
            log_ref = f"<code>{html.escape(read_model.log_path)}</code> (missing)"
            log_article = (
                '<p class="empty">No <code>wiki/log.md</code> file exists yet. '
                "Run <code>uv run splendor init</code> or restore the workspace log.</p>"
            )
        body = (
            '<p class="breadcrumbs"><a href="/">Home</a> / Recent</p>'
            '<p class="empty">Recent insights are derived from durable local files only: '
            "<code>wiki/log.md</code> and run records. This page does not track per-user "
            "last-seen state or mutate workspace files.</p>"
            f"{_recent_insights_section(read_model.log_insights)}"
            f"{_recent_runs_section(read_model.run_events)}"
            "<h2>Rendered wiki log</h2>"
            f"{log_article}"
            '<details class="technical">'
            "<summary>Raw recent records</summary>"
            f"<p>Wiki log: {log_ref}</p>"
            '<p>Run records: <a href="/runs">/runs</a></p>'
            "</details>"
        )
        return _page("Recent", body, root=workspace_root, layout=layout)

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
        return _page(source.title, body, root=workspace_root, layout=layout)

    @app.get("/browse", response_class=HTMLResponse)
    def browse() -> HTMLResponse:
        layout = _layout_for(workspace_root)
        content_documents = _iter_content_documents(workspace_root, layout)
        special_documents = _iter_special_documents(workspace_root, layout)
        counts = _workspace_counts(layout, content_documents=content_documents)
        knowledge_map = _browse_knowledge_map(workspace_root, layout, content_documents)
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
            f"{knowledge_map}"
            "<h2>Content records</h2>"
            '<p class="empty">Raw browse rows remain available for direct file inspection.</p>'
            "<table><thead><tr><th>Title</th><th>Kind</th><th>Status</th><th>Path</th></tr></thead>"
            f"<tbody>{content_rows}</tbody></table>"
            f"{special_section}"
        )
        return _page("Browse", body, root=workspace_root, layout=layout)

    @app.get("/documents/{document_path:path}", response_class=HTMLResponse)
    def document(document_path: str) -> HTMLResponse:
        layout = _layout_for(workspace_root)
        path = _safe_document_path(workspace_root, layout, document_path)
        detail = _document_detail(workspace_root, layout, path)
        metadata = html.escape(json.dumps(detail.metadata, indent=2, sort_keys=True))
        body_html = _render_markdown(detail.body)
        badges = _document_badges(detail)
        relationships = _document_relationship_section(
            _build_document_relationships(workspace_root, layout, detail)
        )
        body = (
            '<p class="breadcrumbs"><a href="/browse">Browse</a> / '
            f"{html.escape(detail.path)}</p>"
            f"{badges}"
            f'<article class="markdown">{body_html}</article>'
            f"{relationships}"
            '<details class="technical">'
            "<summary>Technical metadata</summary>"
            f"<pre>{metadata}</pre>"
            "</details>"
        )
        return _page(detail.title, body, root=workspace_root, layout=layout)

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
        layout = _layout_for(workspace_root)
        if not query:
            return _page("Search", form, root=workspace_root, layout=layout)
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
                root=workspace_root,
                layout=layout,
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
        return _page("Search", body, root=workspace_root, layout=layout)

    return app


def _layout_for(root: Path) -> ResolvedLayout:
    config = load_config(root)
    _validate_layout_root(root, config.layout.wiki_dir, label="wiki_dir")
    _validate_layout_root(root, config.layout.planning_dir, label="planning_dir")
    return resolve_layout(root, config)


def _identity_layout_for(root: Path) -> ResolvedLayout | None:
    try:
        return _layout_for(root)
    except WebLayoutError:
        return None


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


def _build_cockpit_home_read_model(root: Path, layout: ResolvedLayout) -> _CockpitHomeReadModel:
    content_documents = _iter_content_documents(root, layout)
    counts = _workspace_counts(layout, content_documents=content_documents)
    planning_documents = [
        document for document in content_documents if document.document_class == "planning"
    ]
    wiki_documents = [
        document for document in content_documents if document.document_class == "wiki"
    ]
    attention = _build_attention_read_model(
        root,
        layout,
        content_documents=content_documents,
        planning_documents=planning_documents,
    )
    return _CockpitHomeReadModel(
        counts=counts,
        roadmap=_cockpit_roadmap_sections(planning_documents),
        attention=attention,
        knowledge=_cockpit_knowledge_summary(layout, wiki_documents),
        recent_activity=_cockpit_recent_activity(root, layout),
        inspect_next=_cockpit_inspect_next(
            counts, planning_documents, wiki_documents, attention=attention
        ),
    )


def _cockpit_roadmap_sections(planning_documents: list[_DocumentSummary]) -> list[_CockpitSection]:
    current = _planning_links(
        planning_documents,
        statuses={"in_progress", "active"},
        limit=4,
    )
    next_work = _planning_links(
        planning_documents,
        statuses={"todo", "planned"},
        limit=4,
    )
    completed = _planning_links(
        planning_documents,
        statuses={"done", "completed", "accepted", "answered"},
        limit=3,
    )
    return [
        _CockpitSection(
            title="Current work",
            items=current,
            empty="No active task or milestone records found.",
        ),
        _CockpitSection(
            title="Next planned work",
            items=next_work,
            empty="No todo or planned records found.",
        ),
        _CockpitSection(
            title="Recently completed",
            items=completed,
            empty="No completed planning records found.",
        ),
    ]


def _planning_links(
    planning_documents: list[_DocumentSummary], *, statuses: set[str], limit: int
) -> list[_CockpitLink]:
    links = [
        _CockpitLink(
            title=document.title,
            href=f"/documents/{quote(document.path, safe='/')}",
            detail=f"{document.kind or 'planning'} · {document.status or '-'}",
        )
        for document in planning_documents
        if document.status in statuses
    ]
    return sorted(links, key=lambda item: (item.detail, item.title, item.href))[:limit]


def _cockpit_knowledge_summary(
    layout: ResolvedLayout, wiki_documents: list[_DocumentSummary]
) -> list[_CockpitLink]:
    maintained_pages = sum(
        1 for document in wiki_documents if not document.path.startswith("wiki/sources/")
    )
    source_summary_pages = sum(
        1 for document in wiki_documents if document.path.startswith("wiki/sources/")
    )
    review_needed = sum(
        1 for document in wiki_documents if document.review_state in _REVIEW_NEEDED_STATES
    )
    source_manifest_count = sum(
        1 for path in layout.source_records_dir.glob("*.json") if path.is_file()
    )
    items = [
        _CockpitLink(
            title=f"{maintained_pages} maintained wiki pages",
            href="/browse",
            detail="Human-curated or synthesis pages outside generated source summaries.",
        ),
        _CockpitLink(
            title=f"{source_summary_pages} generated source summaries",
            href="/browse",
            detail="Pages under the configured source-summary wiki root.",
        ),
        _CockpitLink(
            title=f"{source_manifest_count} source manifests",
            href="/status",
            detail="Curated machine-readable source records.",
        ),
    ]
    if review_needed:
        items.append(
            _CockpitLink(
                title=f"{review_needed} wiki pages need review",
                href="/browse",
                detail="Review state is visible in document rows and page badges.",
            )
        )
    return items


def _cockpit_recent_activity(root: Path, layout: ResolvedLayout) -> list[_CockpitLink]:
    read_model = _build_recent_read_model(
        root,
        layout,
        run_limit=3,
        log_limit=3,
        include_log_body=False,
    )
    items: list[_CockpitLink] = []
    if read_model.log_insights:
        latest_log = read_model.log_insights[0]
        items.append(
            _log_insight_link(latest_log),
        )
    items.extend(read_model.run_events[: max(0, 3 - len(items))])
    for insight in read_model.log_insights[1 : max(1, 3 - len(items) + 1)]:
        items.append(_log_insight_link(insight))
    if not items and read_model.log_exists:
        items.append(
            _CockpitLink(
                title="Open wiki log",
                href="/recent",
                detail="Rendered recent-insights surface from wiki/log.md.",
            )
        )
    return items[:3]


def _build_recent_read_model(
    root: Path,
    layout: ResolvedLayout,
    *,
    run_limit: int = 8,
    log_limit: int = 12,
    include_log_body: bool = True,
) -> _RecentReadModel:
    log_path = layout.log_file.relative_to(root).as_posix()
    log_body = ""
    log_exists = layout.log_file.is_file()
    if log_exists and include_log_body:
        try:
            log_body = layout.log_file.read_text(encoding="utf-8")
        except OSError:
            log_exists = False
            log_body = ""
    return _RecentReadModel(
        log_path=log_path,
        log_exists=log_exists,
        log_body=log_body,
        log_insights=_parse_log_insights(layout, limit=log_limit),
        run_events=_recent_run_events(root, layout, limit=run_limit),
    )


def _parse_log_insights(layout: ResolvedLayout, *, limit: int) -> list[_LogInsight]:
    if limit <= 0 or not layout.log_file.is_file():
        return []
    entries: list[_LogInsight] = []
    section = "Log"
    try:
        with layout.log_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                heading = _heading_from_line(stripped) or _subheading_from_line(stripped)
                if heading:
                    section = heading
                    continue
                if not stripped.startswith("- "):
                    continue
                text = stripped.removeprefix("- ").strip()
                if not text:
                    continue
                source_order = len(entries) + 1
                timestamp, title = _split_log_timestamp(text)
                entries.append(
                    _LogInsight(
                        anchor=f"log-entry-{source_order}",
                        title=title,
                        section=section,
                        timestamp=timestamp,
                    )
                )
    except OSError:
        return []
    return list(reversed(entries[-limit:]))


def _log_insight_link(insight: _LogInsight) -> _CockpitLink:
    return _CockpitLink(
        title=insight.title,
        href=f"/recent#{insight.anchor}",
        detail=_log_insight_detail(insight),
    )


def _subheading_from_line(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("## "):
        return stripped.removeprefix("## ").strip()
    if stripped.startswith("### "):
        return stripped.removeprefix("### ").strip()
    return None


def _split_log_timestamp(text: str) -> tuple[str | None, str]:
    match = re.match(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}(?:T[0-9:.+-]+| [0-9:.+-]+)?)\s+"
        r"(?P<title>.+)$",
        text,
    )
    if match is None:
        return None, text
    return match.group("timestamp"), match.group("title").strip()


def _recent_run_events(root: Path, layout: ResolvedLayout, *, limit: int) -> list[_CockpitLink]:
    if limit <= 0:
        return []
    try:
        runs = _run_records(root, layout)
    except (ValueError, ValidationError):
        return [
            _CockpitLink(
                title="Run records need inspection",
                href="/runs",
                detail="At least one durable run record could not be parsed.",
            )
        ]
    links: list[_CockpitLink] = []
    for run in runs[:limit]:
        record = run.record
        finished = record.finished_at or record.started_at
        sources = f"{len(record.source_ids)} sources"
        pages = f"{len(record.page_refs)} pages"
        links.append(
            _CockpitLink(
                title=f"{record.status} run {record.run_id}",
                href="/runs",
                detail=f"{finished} · {sources} · {pages}",
            )
        )
    return links


def _cockpit_inspect_next(
    counts: _WorkspaceCounts,
    planning_documents: list[_DocumentSummary],
    wiki_documents: list[_DocumentSummary],
    *,
    attention: _AttentionReadModel,
) -> list[_CockpitLink]:
    links: list[_CockpitLink] = []
    attention_links = _attention_links(attention, limit=1)
    current = _planning_links(
        planning_documents,
        statuses={"in_progress", "active"},
        limit=1,
    )
    if attention_links:
        links.append(attention_links[0])
    if current:
        links.append(current[0])
    if wiki_documents:
        links.append(
            _CockpitLink(
                title="Browse knowledge records",
                href="/browse",
                detail=f"{counts.wiki_content_pages} wiki pages available.",
            )
        )
    if counts.source_manifests or counts.runs:
        links.append(
            _CockpitLink(
                title="Inspect workspace status",
                href="/status",
                detail="Sources, review state, queue, and recent runs.",
            )
        )
    if not links:
        links.append(
            _CockpitLink(
                title="Seed deterministic workspace knowledge",
                href="/browse",
                detail="Start with repo refresh or add-source, then return here.",
            )
        )
    return _dedupe_cockpit_links(links)[:4]


def _dedupe_cockpit_links(links: list[_CockpitLink]) -> list[_CockpitLink]:
    seen: set[tuple[str, str]] = set()
    result: list[_CockpitLink] = []
    for link in links:
        key = (link.title, link.href)
        if key in seen:
            continue
        seen.add(key)
        result.append(link)
    return result


def _build_attention_read_model(
    root: Path,
    layout: ResolvedLayout,
    *,
    content_documents: list[_DocumentSummary] | None = None,
    planning_documents: list[_DocumentSummary] | None = None,
) -> _AttentionReadModel:
    content_documents = (
        content_documents
        if content_documents is not None
        else _iter_content_documents(root, layout)
    )
    planning_documents = (
        planning_documents
        if planning_documents is not None
        else [document for document in content_documents if document.document_class == "planning"]
    )
    items: list[_AttentionItem] = []
    items.extend(_attention_from_review_documents(content_documents).items)
    try:
        items.extend(_attention_from_sources(layout).items)
    except ValueError:
        items.append(
            _AttentionItem(
                kind="source",
                title="Source manifests need inspection",
                explanation="At least one source manifest could not be parsed.",
                href="/status",
                evidence="state/manifests/sources",
                cli_hint="uv run splendor lint",
            )
        )
    try:
        items.extend(_attention_from_runs(_run_records(root, layout)).items)
    except (ValueError, ValidationError):
        items.append(
            _AttentionItem(
                kind="run",
                title="Run records need inspection",
                explanation="At least one durable run record could not be parsed.",
                href="/runs",
                evidence="state/runs",
                cli_hint="uv run splendor lint",
            )
        )
    try:
        items.extend(_attention_from_queue(_queue_records(root, layout)).items)
    except (ValueError, ValidationError):
        items.append(
            _AttentionItem(
                kind="queue",
                title="Queue records need inspection",
                explanation="At least one durable queue record could not be parsed.",
                href="/queue",
                evidence="state/queue",
                cli_hint="uv run splendor lint",
            )
        )
    items.extend(_attention_from_planning_documents(planning_documents).items)
    return _AttentionReadModel(items=_sort_attention_items(items))


def _attention_from_review_documents(documents: list[_DocumentSummary]) -> _AttentionReadModel:
    items = [
        _AttentionItem(
            kind="review",
            title=document.title,
            explanation=f"Wiki page review state is {document.review_state}.",
            href=f"/documents/{quote(document.path, safe='/')}",
            evidence=f"{document.path} review_state={document.review_state}",
        )
        for document in documents
        if document.document_class == "wiki" and document.review_state in _REVIEW_NEEDED_STATES
    ]
    return _AttentionReadModel(items=_sort_attention_items(items))


def _attention_from_sources(layout: ResolvedLayout) -> _AttentionReadModel:
    items: list[_AttentionItem] = []
    for source in load_sources(layout):
        if source.status == "failed":
            items.append(
                _AttentionItem(
                    kind="source",
                    title=source.title,
                    explanation="Source manifest is marked failed.",
                    href=f"/sources/{quote(source.source_id)}",
                    evidence=f"{source.source_id} status=failed",
                    cli_hint="uv run splendor source freshness",
                )
            )
        if not source.linked_pages:
            items.append(
                _AttentionItem(
                    kind="source",
                    title=source.title,
                    explanation="Source has no linked source-summary page yet.",
                    href=f"/sources/{quote(source.source_id)}",
                    evidence=f"{source.source_id} linked_pages=0",
                    cli_hint=f"uv run splendor ingest {source.source_id}",
                )
            )
    return _AttentionReadModel(items=_sort_attention_items(items))


def _attention_from_runs(runs: list[_RunSummary]) -> _AttentionReadModel:
    items = [
        _AttentionItem(
            kind="run",
            title=f"{run.record.status} run {run.record.run_id}",
            explanation=_run_attention_explanation(run.record),
            href="/runs",
            evidence=run.path,
            cli_hint="uv run splendor ingest --pending" if run.record.status == "failed" else None,
        )
        for run in runs
        if run.record.status in _ATTENTION_RUN_STATES
    ]
    return _AttentionReadModel(items=_sort_attention_items(items))


def _attention_from_queue(queue_records: list[_QueueSummary]) -> _AttentionReadModel:
    items = [
        _AttentionItem(
            kind="queue",
            title=f"{queue.record.status} queue job {queue.record.job_id}",
            explanation=_queue_attention_explanation(queue.record),
            href="/queue",
            evidence=queue.path,
            cli_hint=_queue_cli_hint(queue.record),
        )
        for queue in queue_records
        if queue.record.status in _ATTENTION_QUEUE_STATES
    ]
    return _AttentionReadModel(items=_sort_attention_items(items))


def _attention_from_planning(
    grouped: dict[str, list[_PlanningSummary]],
) -> _AttentionReadModel:
    items: list[_AttentionItem] = []
    for records in grouped.values():
        for record in records:
            if record.status not in _ATTENTION_PLANNING_STATUSES:
                continue
            items.append(_planning_attention_item(record))
    return _AttentionReadModel(items=_sort_attention_items(items))


def _attention_from_planning_documents(
    planning_documents: list[_DocumentSummary],
) -> _AttentionReadModel:
    items = [
        _AttentionItem(
            kind=f"planning-{document.kind or 'record'}",
            title=document.title,
            explanation=_planning_attention_explanation(document.kind, document.status),
            href=f"/documents/{quote(document.path, safe='/')}",
            evidence=f"{document.path} status={document.status}",
        )
        for document in planning_documents
        if document.status in _ATTENTION_PLANNING_STATUSES
    ]
    return _AttentionReadModel(items=_sort_attention_items(items))


def _planning_attention_item(record: _PlanningSummary) -> _AttentionItem:
    return _AttentionItem(
        kind=f"planning-{record.kind}",
        title=record.title,
        explanation=_planning_attention_explanation(record.kind, record.status),
        href=f"/documents/{quote(record.path, safe='/')}",
        evidence=f"{record.record_id} status={record.status}",
    )


def _planning_attention_explanation(kind: str | None, status: str | None) -> str:
    if kind == "task" and status == "blocked":
        return "Task is blocked and needs operator disposition before it can proceed."
    if kind == "decision" and status == "proposed":
        return "Decision is proposed and still needs a durable accepted or superseded outcome."
    if kind == "question" and status == "open":
        return "Question is open and may affect the next safe implementation step."
    return f"Planning record status is {status or '-'}."


def _run_attention_explanation(run: RunRecord) -> str:
    if run.status == "failed":
        detail = _bounded_detail(run.errors)
        if detail != "-":
            return f"Run failed with recorded errors: {detail}."
        return "Run failed and should be inspected before trusting generated state."
    return "Run is still marked running in durable state."


def _queue_attention_explanation(queue: QueueItemRecord) -> str:
    if queue.status == "failed":
        if queue.next_attempt_at:
            return f"Queue job failed and is scheduled to retry at {queue.next_attempt_at}."
        return "Queue job failed and is not currently marked done."
    if queue.status == "dead_letter":
        return "Queue job is in the dead-letter state and requires explicit operator repair."
    if queue.status == "leased":
        if queue.lease_expires_at:
            return f"Queue job is leased until {queue.lease_expires_at}."
        return "Queue job is leased with no visible expiry timestamp."
    return "Queue job is pending and has not completed yet."


def _queue_cli_hint(queue: QueueItemRecord) -> str | None:
    if queue.status == "failed":
        return f"uv run splendor queue retry {queue.job_id}"
    if queue.status == "dead_letter":
        return (
            f"uv run splendor queue retry {queue.job_id} "
            "or uv run splendor repair ingest <source-id>"
        )
    if queue.status in {"pending", "leased"}:
        return "uv run splendor ingest --pending"
    return None


def _sort_attention_items(items: list[_AttentionItem]) -> list[_AttentionItem]:
    return sorted(items, key=lambda item: (_attention_kind_order(item.kind), item.title, item.href))


def _attention_kind_order(kind: str) -> int:
    if kind == "run":
        return 0
    if kind == "queue":
        return 1
    if kind == "review":
        return 2
    if kind.startswith("planning"):
        return 3
    if kind == "source":
        return 4
    return 5


def _attention_links(read_model: _AttentionReadModel, *, limit: int) -> list[_CockpitLink]:
    return [
        _CockpitLink(
            title=item.title,
            href=item.href,
            detail=f"{item.kind} · {item.explanation}",
        )
        for item in read_model.items[:limit]
    ]


def _attention_summary_panel(read_model: _AttentionReadModel) -> str:
    count = len(read_model.items)
    count_text = f"{count} attention item" + ("" if count == 1 else "s")
    if not read_model.needs_attention:
        count_text = "No attention items"
    return (
        '<section class="health-panel">'
        f"<h2>{html.escape(read_model.label)}</h2>"
        f"<p>{html.escape(read_model.explanation)}</p>"
        f"<p><strong>{html.escape(count_text)}</strong></p>"
        "</section>"
    )


def _health_banner(read_model: _AttentionReadModel) -> str:
    return (
        '<section class="health-panel">'
        f"<h2>Workspace health: {html.escape(read_model.label)}</h2>"
        f"<p>{html.escape(read_model.explanation)}</p>"
        "</section>"
    )


def _attention_section(read_model: _AttentionReadModel, *, limit: int) -> str:
    if not read_model.items:
        return (
            '<section class="attention-list">'
            "<h2>Attention interpretation</h2>"
            '<p class="empty">No attention items found for this route.</p>'
            "</section>"
        )
    items = "".join(_attention_item_html(item) for item in read_model.items[:limit])
    if len(read_model.items) > limit:
        items += (
            '<li class="empty">'
            f"{len(read_model.items) - limit} more attention items available in raw records."
            "</li>"
        )
    return (
        '<section class="attention-list">'
        "<h2>Attention interpretation</h2>"
        f"<ul>{items}</ul>"
        "</section>"
    )


def _attention_item_html(item: _AttentionItem) -> str:
    cli = ""
    if item.cli_hint:
        cli = f"<span>CLI hint: <code>{html.escape(item.cli_hint)}</code></span>"
    return (
        "<li>"
        f'<a href="{html.escape(item.href)}">{html.escape(item.title)}</a>'
        f"<span>{html.escape(item.kind)} · {html.escape(item.explanation)}</span>"
        f"<span>Evidence: <code>{html.escape(item.evidence)}</code></span>"
        f"{cli}"
        "</li>"
    )


def _cockpit_section(section: _CockpitSection) -> str:
    items = "".join(_cockpit_link_item(item) for item in section.items)
    if not items:
        items = f'<li class="empty">{html.escape(section.empty)}</li>'
    return (
        '<section class="cockpit-panel">'
        f"<h2>{html.escape(section.title)}</h2>"
        f"<ul>{items}</ul>"
        "</section>"
    )


def _cockpit_sections(sections: list[_CockpitSection]) -> str:
    return "".join(_cockpit_section(section) for section in sections)


def _cockpit_secondary_sections(read_model: _CockpitHomeReadModel) -> str:
    sections = [
        _CockpitSection(
            "Knowledge map summary",
            read_model.knowledge,
            "No knowledge records yet.",
        ),
        _CockpitSection(
            "Recent durable activity",
            read_model.recent_activity,
            "No durable activity beyond workspace initialization yet.",
        ),
        _CockpitSection("Inspect next", read_model.inspect_next, "No inspection links yet."),
    ]
    return "".join(_cockpit_section(section) for section in sections)


def _recent_insights_section(insights: list[_LogInsight]) -> str:
    if not insights:
        return (
            '<section class="recent-panel">'
            "<h2>Recent insights from wiki/log.md</h2>"
            '<p class="empty">No bullet entries found in the wiki log yet.</p>'
            "</section>"
        )
    items = "".join(_log_insight_item(insight) for insight in insights)
    return (
        '<section class="recent-panel">'
        "<h2>Recent insights from wiki/log.md</h2>"
        '<p class="empty">Latest parsed bullet entries, newest first by log order.</p>'
        f"<ol>{items}</ol>"
        "</section>"
    )


def _log_insight_item(insight: _LogInsight) -> str:
    timestamp = ""
    if insight.timestamp:
        timestamp = f"<span>Time: <code>{html.escape(insight.timestamp)}</code></span>"
    return (
        f'<li id="{html.escape(insight.anchor)}">'
        f"<strong>{html.escape(insight.title)}</strong>"
        f"<span>{html.escape(_log_insight_detail(insight))}</span>"
        f"{timestamp}"
        "</li>"
    )


def _log_insight_detail(insight: _LogInsight) -> str:
    detail = f"wiki/log.md · {insight.section}"
    if insight.timestamp:
        detail += f" · {insight.timestamp}"
    return detail


def _recent_runs_section(run_events: list[_CockpitLink]) -> str:
    if not run_events:
        return (
            '<section class="recent-panel">'
            "<h2>Durable run events</h2>"
            '<p class="empty">No run records found.</p>'
            "</section>"
        )
    items = "".join(_cockpit_link_item(event) for event in run_events)
    return (
        '<section class="recent-panel">'
        "<h2>Durable run events</h2>"
        '<p class="empty">Latest run records, sorted by recorded run timestamps.</p>'
        f"<ul>{items}</ul>"
        "</section>"
    )


def _cockpit_link_item(item: _CockpitLink) -> str:
    return (
        "<li>"
        f'<a href="{html.escape(item.href)}">{html.escape(item.title)}</a>'
        f"<span>{html.escape(item.detail)}</span>"
        "</li>"
    )


def _build_project_identity(root: Path, layout: ResolvedLayout | None = None) -> _ProjectIdentity:
    index_path = layout.index_file if layout is not None else root / "wiki" / "index.md"
    index_identity = _project_identity_from_markdown(index_path)
    if index_identity is not None and not _is_generic_index_identity(index_identity):
        return index_identity

    readme_identity = _project_identity_from_markdown(root / "README.md")
    if readme_identity is not None:
        return readme_identity

    basename = root.name.strip()
    if basename:
        return _ProjectIdentity(name=basename, summary=None)
    return _ProjectIdentity(name="Splendor workspace", summary=None)


def _is_generic_index_identity(identity: _ProjectIdentity) -> bool:
    return identity.name == _GENERIC_INDEX_TITLE and identity.summary == _GENERIC_INDEX_SUMMARY


def _project_identity_from_markdown(path: Path) -> _ProjectIdentity | None:
    if not path.is_file():
        return None
    raw = _read_identity_markdown(path)
    if raw is None:
        return None

    lines = _strip_frontmatter(raw).splitlines()
    heading: str | None = None
    heading_index = -1
    for index, line in enumerate(lines):
        heading = _heading_from_line(line)
        if heading:
            heading_index = index
            break
    if heading is None:
        return None

    return _ProjectIdentity(
        name=heading,
        summary=_leading_paragraph(lines[heading_index + 1 :]),
    )


def _read_identity_markdown(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            lines: list[str] = []
            char_count = 0
            for _ in range(_IDENTITY_LINE_LIMIT):
                line = handle.readline()
                if not line:
                    break
                char_count += len(line)
                if char_count > _IDENTITY_CHAR_LIMIT:
                    break
                lines.append(line)
    except OSError:
        return None
    return "".join(lines)


def _strip_frontmatter(markdown_text: str) -> str:
    normalized = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return normalized
    try:
        _frontmatter_text, body = normalized.removeprefix("---\n").split("\n---\n", maxsplit=1)
    except ValueError:
        return normalized
    return body


def _leading_paragraph(lines: list[str]) -> str | None:
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith("#") or stripped.startswith("```"):
            if paragraph:
                break
            continue
        if stripped.startswith(("> ", "- ", "* ", "+ ")) and not paragraph:
            continue
        paragraph.append(stripped)
    if not paragraph:
        return None
    return " ".join(paragraph)


def _normalize_planning_kind(kind: str) -> str:
    normalized = kind.removesuffix("s")
    if normalized not in {"task", "milestone", "decision", "question"}:
        raise HTTPException(status_code=404, detail="Planning kind not found")
    return normalized


def _planning_label(kind: str) -> str:
    return {
        "task": "Tasks",
        "milestone": "Milestones",
        "decision": "Decisions",
        "question": "Questions",
    }[kind]


def _planning_records(root: Path, layout: ResolvedLayout, kind: str) -> list[_PlanningSummary]:
    model = model_for_planning_kind(kind)
    id_field = record_id_field(kind)
    records: list[_PlanningSummary] = []
    for path in iter_planning_paths(planning_directory(layout, kind)):
        parsed = parse_planning_document(path, model)
        record = parsed.record
        metadata = record.model_dump(mode="json")
        record_id = getattr(record, id_field)
        status = metadata.get("status")
        records.append(
            _PlanningSummary(
                path=path.relative_to(root).as_posix(),
                kind=kind,
                record_id=record_id,
                title=record.title,
                status=status if isinstance(status, str) else "-",
                detail=_planning_detail(kind, metadata),
            )
        )
    return sorted(records, key=lambda item: (item.status, item.record_id))


def _build_planning_roadmap(
    grouped: dict[str, list[_PlanningSummary]],
) -> _PlanningRoadmapReadModel:
    def matching(kind: str, statuses: set[str]) -> list[_PlanningSummary]:
        return [record for record in grouped[kind] if record.status in statuses]

    lanes = [
        _PlanningRoadmapLane(
            title="Active / current",
            description="Tasks in progress and active milestones.",
            items=[
                *matching("task", {"in_progress"}),
                *matching("milestone", {"active"}),
            ],
            empty="No task or milestone is marked active.",
        ),
        _PlanningRoadmapLane(
            title="Next",
            description="Todo tasks and planned milestones.",
            items=[
                *matching("task", {"todo"}),
                *matching("milestone", {"planned"}),
            ],
            empty="No todo task or planned milestone found.",
        ),
        _PlanningRoadmapLane(
            title="Blocked or gated",
            description="Planning work that cannot proceed directly.",
            items=matching("task", {"blocked"}),
            empty="No blocked planning tasks found.",
        ),
        _PlanningRoadmapLane(
            title="Open decisions",
            description="Proposed decisions that still need a durable resolution.",
            items=matching("decision", {"proposed"}),
            empty="No proposed decisions found.",
        ),
        _PlanningRoadmapLane(
            title="Open questions",
            description="Questions that still need an answer or disposition.",
            items=matching("question", {"open"}),
            empty="No open questions found.",
        ),
        _PlanningRoadmapLane(
            title="Completed / answered",
            description="Status-based completed, accepted, or answered planning records.",
            items=[
                *matching("task", {"done"}),
                *matching("milestone", {"completed"}),
                *matching("decision", {"accepted"}),
                *matching("question", {"answered"}),
            ],
            empty="No completed planning records found.",
        ),
        _PlanningRoadmapLane(
            title="Historical / archived",
            description="Superseded or deferred planning records kept for context.",
            items=[
                *matching("decision", {"superseded"}),
                *matching("question", {"deferred"}),
            ],
            empty="No superseded decisions or deferred questions found.",
        ),
    ]
    return _PlanningRoadmapReadModel(lanes=lanes)


def _planning_roadmap(read_model: _PlanningRoadmapReadModel) -> str:
    return (
        '<section class="roadmap-grid">'
        + "".join(_planning_roadmap_lane(lane) for lane in read_model.lanes)
        + "</section>"
    )


def _planning_roadmap_lane(lane: _PlanningRoadmapLane) -> str:
    items = "".join(_planning_roadmap_item(item) for item in _sort_roadmap_items(lane.items))
    if not items:
        items = f'<li class="empty">{html.escape(lane.empty)}</li>'
    return (
        '<section class="roadmap-lane">'
        f"<h2>{html.escape(lane.title)}</h2>"
        f"<p>{html.escape(lane.description)}</p>"
        f"<ul>{items}</ul>"
        "</section>"
    )


def _sort_roadmap_items(items: list[_PlanningSummary]) -> list[_PlanningSummary]:
    return sorted(
        items, key=lambda item: (_planning_kind_order(item.kind), item.status, item.title)
    )


def _planning_kind_order(kind: str) -> int:
    return {
        "milestone": 0,
        "task": 1,
        "decision": 2,
        "question": 3,
    }[kind]


def _planning_roadmap_item(item: _PlanningSummary) -> str:
    href = f"/documents/{quote(item.path, safe='/')}"
    return (
        "<li>"
        f'<a href="{href}">{html.escape(item.title)}</a>'
        "<span>"
        f"{html.escape(item.kind)} · {html.escape(item.status)} · "
        f"<code>{html.escape(item.record_id)}</code>"
        "</span>"
        f"<span>{html.escape(item.detail)}</span>"
        "</li>"
    )


def _planning_detail(kind: str, metadata: dict[str, object]) -> str:
    if kind == "task":
        parts = [f"priority={metadata.get('priority', '-')}"]
        owner = metadata.get("owner")
        if owner:
            parts.append(f"owner={owner}")
        depends_on = metadata.get("depends_on")
        if isinstance(depends_on, list) and depends_on:
            parts.append(f"blocked_by={len(depends_on)}")
        milestone_refs = metadata.get("milestone_refs")
        if isinstance(milestone_refs, list) and milestone_refs:
            parts.append(f"milestones={len(milestone_refs)}")
        return " ".join(parts)
    if kind == "milestone":
        parts = []
        target_date = metadata.get("target_date")
        if target_date:
            parts.append(f"target={target_date}")
        task_refs = metadata.get("task_refs")
        if isinstance(task_refs, list):
            parts.append(f"tasks={len(task_refs)}")
        return " ".join(parts) or "-"
    if kind == "decision":
        decided_at = metadata.get("decided_at")
        related_tasks = metadata.get("related_tasks")
        parts = [f"decided={decided_at or '-'}"]
        if isinstance(related_tasks, list) and related_tasks:
            parts.append(f"tasks={len(related_tasks)}")
        return " ".join(parts)
    answer_page = metadata.get("answer_page_ref")
    related_tasks = metadata.get("related_tasks")
    parts = []
    if answer_page:
        parts.append(f"answer={answer_page}")
    if isinstance(related_tasks, list) and related_tasks:
        parts.append(f"tasks={len(related_tasks)}")
    return " ".join(parts) or "-"


def _planning_section(kind: str, records: list[_PlanningSummary]) -> str:
    return (
        f'<h2><a href="/planning/{kind}s">{html.escape(_planning_label(kind))}</a></h2>'
        f"{_planning_table(kind, records)}"
    )


def _planning_table(kind: str, records: list[_PlanningSummary]) -> str:
    rows = "\n".join(_planning_row(item) for item in records)
    if not rows:
        rows = (
            f'<tr><td colspan="5" class="empty">No '
            f"{html.escape(_planning_label(kind).lower())} yet.</td></tr>"
        )
    return (
        "<table><thead><tr><th>Title</th><th>ID</th><th>Status</th><th>Detail</th>"
        f"<th>Path</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _planning_row(item: _PlanningSummary) -> str:
    href = f"/documents/{quote(item.path, safe='/')}"
    return (
        "<tr>"
        f'<td><a href="{href}">{html.escape(item.title)}</a></td>'
        f"<td><code>{html.escape(item.record_id)}</code></td>"
        f"<td>{html.escape(item.status)}</td>"
        f"<td>{html.escape(item.detail)}</td>"
        f"<td><code>{html.escape(item.path)}</code></td>"
        "</tr>"
    )


def _run_records(root: Path, layout: ResolvedLayout) -> list[_RunSummary]:
    records: list[_RunSummary] = []
    for run_path in sorted(layout.runs_dir.glob("*.json")):
        records.append(
            _RunSummary(
                path=run_path.relative_to(root).as_posix(),
                record=load_run_record(run_path),
            )
        )
    return sorted(
        records,
        key=lambda item: (item.record.finished_at or item.record.started_at, item.record.run_id),
        reverse=True,
    )


def _sort_runs_for_attention(records: list[_RunSummary]) -> list[_RunSummary]:
    attention = sorted(
        [item for item in records if item.record.status in _ATTENTION_RUN_STATES],
        key=lambda item: (
            item.record.finished_at or item.record.started_at,
            item.record.run_id,
        ),
        reverse=True,
    )
    other = sorted(
        [item for item in records if item.record.status not in _ATTENTION_RUN_STATES],
        key=lambda item: (
            item.record.finished_at or item.record.started_at,
            item.record.run_id,
        ),
        reverse=True,
    )
    return [*attention, *other]


def _queue_records(root: Path, layout: ResolvedLayout) -> list[_QueueSummary]:
    records: list[_QueueSummary] = []
    for queue_path in sorted(layout.queue_dir.glob("*.json")):
        records.append(
            _QueueSummary(
                path=queue_path.relative_to(root).as_posix(),
                record=load_queue_item(queue_path),
            )
        )
    return sorted(records, key=lambda item: (item.record.status, item.record.job_id))


def _sort_queue_for_attention(records: list[_QueueSummary]) -> list[_QueueSummary]:
    return sorted(
        records,
        key=lambda item: (
            item.record.status not in _ATTENTION_QUEUE_STATES,
            _queue_status_order(item.record.status),
            item.record.updated_at,
            item.record.job_id,
        ),
    )


def _queue_status_order(status: str) -> int:
    return {
        "dead_letter": 0,
        "failed": 1,
        "leased": 2,
        "pending": 3,
        "done": 4,
    }.get(status, 5)


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


def _browse_knowledge_map(
    root: Path, layout: ResolvedLayout, content_documents: list[_DocumentSummary]
) -> str:
    items = [
        _knowledge_map_item(path=root / document.path, summary=document)
        for document in content_documents
    ]
    maintained = [
        item for item in items if item.document_class == "wiki" and item.kind != "source-summary"
    ]
    source_summaries = [
        item for item in items if item.document_class == "wiki" and item.kind == "source-summary"
    ]
    planning = [item for item in items if item.document_class == "planning"]
    review_needed = [item for item in items if item.review_state in _REVIEW_NEEDED_STATES]
    source_backed = [
        item
        for item in items
        if item.source_refs
        or item.run_refs
        or any(link.get("source_id") or link.get("run_id") for link in item.provenance_links)
    ]
    related = [
        item
        for item in items
        if item.related_pages
        or any(link.get("page_id") or link.get("path_ref") for link in item.provenance_links)
    ]
    tag_clusters = _tag_clusters(items)
    orphan_pages = _orphan_knowledge_pages(items)
    sections = [
        _knowledge_map_section(
            "Maintained pages",
            "Human-curated or synthesis pages outside generated source summaries.",
            maintained[:8],
            "No maintained wiki pages yet.",
        ),
        _knowledge_map_section(
            "Generated source summaries",
            "Generated pages backed by curated source manifests.",
            source_summaries[:8],
            "No generated source-summary pages yet.",
        ),
        _knowledge_map_section(
            "Planning records",
            "Tasks, milestones, decisions, and questions with raw files preserved below.",
            planning[:8],
            "No planning records yet.",
        ),
        _knowledge_map_section(
            "Review-needed pages",
            "Wiki pages whose review state asks for operator inspection.",
            review_needed[:8],
            "No review-needed pages found.",
        ),
        _knowledge_map_section(
            "Related-page clusters",
            "Pages with explicit related page or page-level provenance links.",
            related[:8],
            "No explicit related-page metadata found.",
        ),
        _knowledge_map_section(
            "Source-backed pages",
            "Pages connected to source refs, generated runs, or source provenance.",
            source_backed[:8],
            "No source-backed page metadata found.",
        ),
        _knowledge_map_section(
            "Orphan pages",
            "Wiki pages without tags, related pages, source refs, or provenance links.",
            orphan_pages[:8],
            "No orphan wiki pages found.",
        ),
    ]
    tags = _tag_cluster_section(tag_clusters)
    return (
        "<h2>Knowledge map</h2>"
        '<p class="empty">Browse is grouped by page role, tags, relationships, and provenance '
        "before the raw file table.</p>"
        '<section class="knowledge-grid">' + "".join(sections) + tags + "</section>"
    )


def _knowledge_map_item(path: Path, summary: _DocumentSummary) -> _KnowledgeMapItem:
    metadata = _read_relationship_frontmatter(path)
    return _KnowledgeMapItem(
        path=summary.path,
        title=summary.title,
        document_class=summary.document_class,
        kind=summary.kind,
        status=summary.status,
        review_state=summary.review_state,
        tags=_string_list(metadata.get("tags")),
        related_pages=_string_list(metadata.get("related_pages")),
        source_refs=_string_list(metadata.get("source_refs")),
        run_refs=_string_list(metadata.get("generated_by_run_ids")),
        provenance_links=_dict_list(metadata.get("provenance_links")),
    )


def _knowledge_map_section(
    title: str, description: str, items: list[_KnowledgeMapItem], empty: str
) -> str:
    rows = "".join(_knowledge_map_link(item) for item in _sort_knowledge_items(items))
    if not rows:
        rows = f'<li class="empty">{html.escape(empty)}</li>'
    return (
        '<section class="knowledge-panel">'
        f"<h3>{html.escape(title)}</h3>"
        f"<p>{html.escape(description)}</p>"
        f"<ul>{rows}</ul>"
        "</section>"
    )


def _knowledge_map_link(item: _KnowledgeMapItem) -> str:
    href = f"/documents/{quote(item.path, safe='/')}"
    detail_parts = [
        item.kind or item.document_class,
        item.status or "-",
    ]
    if item.tags:
        detail_parts.append("tags=" + ", ".join(item.tags[:3]))
    if item.related_pages:
        detail_parts.append(f"related={len(item.related_pages)}")
    if item.source_refs:
        detail_parts.append(f"sources={len(item.source_refs)}")
    return (
        "<li>"
        f'<a href="{href}">{html.escape(item.title)}</a>'
        f"<span>{html.escape(' · '.join(detail_parts))}</span>"
        f"<code>{html.escape(item.path)}</code>"
        "</li>"
    )


def _tag_clusters(items: list[_KnowledgeMapItem]) -> dict[str, list[_KnowledgeMapItem]]:
    clusters: dict[str, list[_KnowledgeMapItem]] = {}
    for item in items:
        for tag in item.tags:
            clusters.setdefault(tag, []).append(item)
    return clusters


def _tag_cluster_section(clusters: dict[str, list[_KnowledgeMapItem]]) -> str:
    if not clusters:
        rows = '<li class="empty">No tags found in page frontmatter.</li>'
    else:
        rows = ""
        for tag in sorted(clusters):
            items = _sort_knowledge_items(clusters[tag])
            links = ", ".join(
                f'<a href="/documents/{quote(item.path, safe="/")}">{html.escape(item.title)}</a>'
                for item in items[:4]
            )
            extra = f" (+{len(items) - 4})" if len(items) > 4 else ""
            rows += (
                f'<li id="{html.escape(_tag_anchor(tag))}">'
                f"<strong>{html.escape(tag)}</strong>"
                f"<span>{links}{html.escape(extra)}</span>"
                "</li>"
            )
    return (
        '<section class="knowledge-panel">'
        "<h3>Tags</h3>"
        "<p>Topic clusters from page frontmatter.</p>"
        f"<ul>{rows}</ul>"
        "</section>"
    )


def _orphan_knowledge_pages(items: list[_KnowledgeMapItem]) -> list[_KnowledgeMapItem]:
    return [
        item
        for item in items
        if item.document_class == "wiki"
        and not item.tags
        and not item.related_pages
        and not item.source_refs
        and not item.run_refs
        and not item.provenance_links
    ]


def _sort_knowledge_items(items: list[_KnowledgeMapItem]) -> list[_KnowledgeMapItem]:
    return sorted(
        items, key=lambda item: (item.document_class, item.kind or "", item.title, item.path)
    )


def _document_summary(root: Path, layout: ResolvedLayout, path: Path) -> _DocumentSummary:
    relative_path = path.relative_to(root).as_posix()
    metadata = _read_listing_metadata(path)
    if path.is_relative_to(layout.wiki_dir):
        document_class = "wiki"
        default_kind = None
    else:
        document_class = "planning"
        default_kind = _planning_kind(layout, path)
    return _DocumentSummary(
        path=relative_path,
        title=metadata.get("title") or _title_from_path(relative_path),
        document_class=document_class,
        kind=metadata.get("kind") or default_kind,
        status=metadata.get("status"),
        review_state=metadata.get("review_state"),
    )


def _read_listing_metadata(path: Path) -> dict[str, str | None]:
    """Read only frontmatter and the first heading needed for browse rows."""
    heading: str | None = None
    frontmatter: dict[str, object] = {}

    with path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
        if first_line.replace("\r\n", "\n").replace("\r", "\n") == "---\n":
            frontmatter_lines = _read_bounded_frontmatter_lines(handle)
            if frontmatter_lines is not None:
                frontmatter = _load_listing_frontmatter(frontmatter_lines)
        else:
            heading = _heading_from_line(first_line)

        if heading is None and not _frontmatter_string(frontmatter, "title"):
            heading = _read_bounded_heading(handle)

    return {
        "title": _frontmatter_string(frontmatter, "title") or heading,
        "kind": _frontmatter_string(frontmatter, "kind"),
        "status": _frontmatter_string(frontmatter, "status"),
        "review_state": _frontmatter_string(frontmatter, "review_state"),
    }


def _read_bounded_frontmatter_lines(handle) -> list[str] | None:
    lines: list[str] = []
    char_count = 0
    for _ in range(_LISTING_FRONTMATTER_LINE_LIMIT):
        line = handle.readline()
        if not line:
            return None
        normalized = line.replace("\r\n", "\n").replace("\r", "\n")
        if normalized == "---\n":
            return lines
        char_count += len(normalized)
        if char_count > _LISTING_FRONTMATTER_CHAR_LIMIT:
            return None
        lines.append(normalized)
    return None


def _read_bounded_heading(handle) -> str | None:
    char_count = 0
    for _ in range(_LISTING_HEADING_LINE_LIMIT):
        line = handle.readline()
        if not line:
            return None
        char_count += len(line)
        if char_count > _LISTING_HEADING_CHAR_LIMIT:
            return None
        heading = _heading_from_line(line)
        if heading is not None:
            return heading
    return None


def _load_listing_frontmatter(frontmatter_lines: list[str]) -> dict[str, object]:
    try:
        loaded = yaml.safe_load("".join(frontmatter_lines))
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _read_relationship_frontmatter(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            first_line = handle.readline()
            if first_line.replace("\r\n", "\n").replace("\r", "\n") != "---\n":
                return {}
            frontmatter_lines = _read_bounded_frontmatter_lines(handle)
    except OSError:
        return {}
    if frontmatter_lines is None:
        return {}
    return _load_listing_frontmatter(frontmatter_lines)


def _frontmatter_string(frontmatter: dict[str, object], key: str) -> str | None:
    value = frontmatter.get(key)
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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


def _document_badges(detail: _DocumentDetail) -> str:
    badges = [
        ("Class", detail.document_class),
        ("Kind", detail.kind),
        ("Status", detail.status),
        ("Review", _metadata_string(detail.metadata, "review_state")),
        ("Authority", _metadata_string(detail.metadata, "authority_role")),
        ("Freshness", _metadata_string(detail.metadata, "authority_freshness")),
    ]
    source_refs = detail.metadata.get("source_refs")
    if isinstance(source_refs, list) and source_refs:
        badges.append(("Sources", str(len(source_refs))))
    run_refs = detail.metadata.get("generated_by_run_ids")
    if isinstance(run_refs, list) and run_refs:
        badges.append(("Runs", str(len(run_refs))))
    badge_items = "".join(
        f'<span class="badge"><strong>{html.escape(label)}</strong> {html.escape(value)}</span>'
        for label, value in badges
        if value
    )
    if not badge_items:
        return ""
    return f'<section class="badges">{badge_items}</section>'


def _build_document_relationships(
    root: Path, layout: ResolvedLayout, detail: _DocumentDetail
) -> _DocumentRelationships:
    documents = _relationship_documents(root, layout)
    document_lookup = _relationship_lookup(documents)
    target_ids = _relationship_identity_values(detail)
    related_pages = [
        _relationship_for_ref(ref, document_lookup, label="related page")
        for ref in _string_list(detail.metadata.get("related_pages"))
    ]
    tags = [
        _DocumentRelationship(
            title=tag,
            href=f"/browse#{_tag_anchor(tag)}",
            detail="tag",
        )
        for tag in _string_list(detail.metadata.get("tags"))
    ]
    sources = [
        _DocumentRelationship(
            title=source_ref,
            href=f"/sources/{quote(source_ref, safe='')}",
            detail="source ref",
        )
        for source_ref in _string_list(detail.metadata.get("source_refs"))
    ]
    runs = [
        _DocumentRelationship(title=run_id, href="/runs", detail="generated by run")
        for run_id in _string_list(detail.metadata.get("generated_by_run_ids"))
    ]
    provenance = [
        relationship
        for link in _dict_list(detail.metadata.get("provenance_links"))
        for relationship in _provenance_relationships(link, document_lookup)
    ]
    references = _field_reference_relationships(detail.metadata, document_lookup)
    backlinks = [
        _DocumentRelationship(
            title=document.title,
            href=f"/documents/{quote(document.path, safe='/')}",
            detail=_backlink_detail(document, target_ids, detail.path),
        )
        for document in documents
        if document.path != detail.path
        and _document_mentions_target(document, target_ids, detail.path)
    ]
    return _DocumentRelationships(
        related_pages=_dedupe_relationships(related_pages),
        tags=_dedupe_relationships(tags),
        sources=_dedupe_relationships(sources),
        runs=_dedupe_relationships(runs),
        provenance=_dedupe_relationships(provenance),
        backlinks=_dedupe_relationships(backlinks),
        references=_dedupe_relationships(references),
    )


def _relationship_documents(root: Path, layout: ResolvedLayout) -> list[_DocumentDetail]:
    documents: list[_DocumentDetail] = []
    for summary in [*_iter_content_documents(root, layout), *_iter_special_documents(root, layout)]:
        path = root / summary.path
        if path.is_file():
            documents.append(_document_detail(root, layout, path))
    return sorted(documents, key=lambda item: (item.document_class, item.kind or "", item.title))


def _relationship_lookup(
    documents: list[_DocumentDetail],
) -> dict[str, _DocumentDetail]:
    lookup: dict[str, _DocumentDetail] = {}
    for document in documents:
        for value in _relationship_identity_values(document):
            lookup.setdefault(value, document)
    return lookup


def _relationship_identity_values(detail: _DocumentDetail) -> set[str]:
    values = {detail.path}
    for key in (
        "page_id",
        "task_id",
        "milestone_id",
        "decision_id",
        "question_id",
    ):
        value = detail.metadata.get(key)
        if isinstance(value, str) and value:
            values.add(value)
    return values


def _relationship_for_ref(
    ref: str, document_lookup: dict[str, _DocumentDetail], *, label: str
) -> _DocumentRelationship:
    document = document_lookup.get(ref)
    if document is None:
        return _DocumentRelationship(title=ref, href=None, detail=label)
    return _DocumentRelationship(
        title=document.title,
        href=f"/documents/{quote(document.path, safe='/')}",
        detail=f"{label} · {document.kind or document.document_class}",
    )


def _provenance_relationships(
    link: dict[str, object], document_lookup: dict[str, _DocumentDetail]
) -> list[_DocumentRelationship]:
    role = link.get("role")
    detail = f"provenance · {role}" if isinstance(role, str) and role else "provenance"
    relationships: list[_DocumentRelationship] = []
    for key, label in (
        ("page_id", "page"),
        ("path_ref", "path"),
        ("source_id", "source"),
        ("run_id", "run"),
    ):
        value = link.get(key)
        if not isinstance(value, str) or not value:
            continue
        if key in {"page_id", "path_ref"}:
            relationships.append(_relationship_for_ref(value, document_lookup, label=detail))
        elif key == "source_id":
            relationships.append(
                _DocumentRelationship(
                    title=value,
                    href=f"/sources/{quote(value, safe='')}",
                    detail=f"{detail} · {label}",
                )
            )
        else:
            relationships.append(
                _DocumentRelationship(title=value, href="/runs", detail=f"{detail} · {label}")
            )
    return relationships or [_DocumentRelationship(title="-", href=None, detail=detail)]


def _field_reference_relationships(
    metadata: dict[str, object], document_lookup: dict[str, _DocumentDetail]
) -> list[_DocumentRelationship]:
    relationships: list[_DocumentRelationship] = []
    field_labels = {
        "issue_refs": "issue",
        "pr_refs": "pull request",
        "supersedes": "supersedes",
        "superseded_by": "superseded by",
        "depends_on": "depends on",
        "milestone_refs": "milestone",
        "task_refs": "task",
        "decision_refs": "decision",
        "question_refs": "question",
        "related_tasks": "task",
        "related_decisions": "decision",
        "related_questions": "question",
        "answer_page_ref": "answer page",
    }
    for field, label in field_labels.items():
        value = metadata.get(field)
        values = (
            _string_list(value)
            if isinstance(value, list)
            else ([value] if isinstance(value, str) else [])
        )
        for ref in values:
            if not ref:
                continue
            relationships.append(_relationship_for_ref(ref, document_lookup, label=label))
    contradictions = metadata.get("contradictions")
    if isinstance(contradictions, list):
        for item in contradictions:
            if not isinstance(item, dict):
                continue
            task_id = item.get("review_task_id")
            if isinstance(task_id, str) and task_id:
                relationships.append(
                    _relationship_for_ref(task_id, document_lookup, label="review task")
                )
            for source_id in _string_list(item.get("related_source_ids")):
                relationships.append(
                    _DocumentRelationship(
                        title=source_id,
                        href=f"/sources/{quote(source_id, safe='')}",
                        detail="contradiction source",
                    )
                )
    return relationships


def _document_mentions_target(
    document: _DocumentDetail, target_ids: set[str], target_path: str
) -> bool:
    return _metadata_mentions_target(
        document.metadata, target_ids, target_path
    ) or _body_links_target(document.body, target_path)


def _metadata_mentions_target(
    metadata: dict[str, object], target_ids: set[str], target_path: str
) -> bool:
    for value in metadata.values():
        if _value_mentions_target(value, target_ids, target_path):
            return True
    return False


def _value_mentions_target(value: object, target_ids: set[str], target_path: str) -> bool:
    if isinstance(value, str):
        return value in target_ids or value == target_path
    if isinstance(value, list):
        return any(_value_mentions_target(item, target_ids, target_path) for item in value)
    if isinstance(value, dict):
        return any(_value_mentions_target(item, target_ids, target_path) for item in value.values())
    return False


def _body_links_target(body: str, target_path: str) -> bool:
    target_names = {target_path, f"/documents/{target_path}", PurePosixPath(target_path).name}
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", body):
        href = match.group(1).split("#", maxsplit=1)[0].strip()
        if href in target_names or href.endswith("/" + target_path):
            return True
    return False


def _backlink_detail(document: _DocumentDetail, target_ids: set[str], target_path: str) -> str:
    sources: list[str] = []
    if _metadata_mentions_target(document.metadata, target_ids, target_path):
        sources.append("frontmatter")
    if _body_links_target(document.body, target_path):
        sources.append("markdown link")
    return f"{document.kind or document.document_class} · {', '.join(sources)}"


def _document_relationship_section(read_model: _DocumentRelationships) -> str:
    sections = [
        _relationship_section(
            "Related pages", read_model.related_pages, "No related pages recorded."
        ),
        _relationship_section("Tags", read_model.tags, "No tags recorded."),
        _relationship_section("Sources", read_model.sources, "No source refs recorded."),
        _relationship_section("Runs", read_model.runs, "No generated run refs recorded."),
        _relationship_section("Provenance", read_model.provenance, "No provenance links recorded."),
        _relationship_section("Backlinks", read_model.backlinks, "No backlinks found."),
        _relationship_section(
            "Other references",
            read_model.references,
            "No issue, PR, planning, or contradiction refs recorded.",
        ),
    ]
    return (
        '<section class="relationships"><h2>Related context</h2>' + "".join(sections) + "</section>"
    )


def _relationship_section(
    title: str, relationships: list[_DocumentRelationship], empty: str
) -> str:
    rows = "".join(_relationship_item(item) for item in relationships[:10])
    if len(relationships) > 10:
        rows += f'<li class="empty">{len(relationships) - 10} more references in metadata.</li>'
    if not rows:
        rows = f'<li class="empty">{html.escape(empty)}</li>'
    return (
        '<section class="relationship-panel">'
        f"<h3>{html.escape(title)}</h3>"
        f"<ul>{rows}</ul>"
        "</section>"
    )


def _relationship_item(item: _DocumentRelationship) -> str:
    title = html.escape(item.title)
    if item.href:
        title = f'<a href="{html.escape(item.href)}">{title}</a>'
    return f"<li>{title}<span>{html.escape(item.detail)}</span></li>"


def _dedupe_relationships(
    relationships: list[_DocumentRelationship],
) -> list[_DocumentRelationship]:
    seen: set[tuple[str, str | None, str]] = set()
    result: list[_DocumentRelationship] = []
    for relationship in relationships:
        key = (relationship.title, relationship.href, relationship.detail)
        if key in seen:
            continue
        seen.add(key)
        result.append(relationship)
    return sorted(result, key=lambda item: (item.detail, item.title, item.href or ""))


def _tag_anchor(tag: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", tag.lower()).strip("-")
    return f"tag-{normalized or 'untagged'}"


def _metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


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
        heading = _heading_from_line(line)
        if heading is not None:
            return heading or fallback
    return fallback


def _heading_from_line(line: str) -> str | None:
    stripped = line.strip()
    if stripped.startswith("# "):
        return stripped.removeprefix("# ").strip()
    return None


def _title_from_path(path: str) -> str:
    stem = PurePosixPath(path).stem
    title = stem.replace("-", " ").replace("_", " ").strip()
    return title.title() if title else path


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


def _source_row(source) -> str:
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
    try:
        run = load_run_record(run_path)
    except ValueError:
        _LOGGER.exception("Run record failed validation.")
        return (
            "<h2>Latest ingest run</h2>"
            f'<p class="empty">Linked run record <code>{html.escape(run_id)}</code> '
            "is invalid.</p>"
        )
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


def _run_row(item: _RunSummary) -> str:
    run = item.record
    page_refs = ", ".join(run.page_refs[:3])
    if len(run.page_refs) > 3:
        page_refs += f" (+{len(run.page_refs) - 3})"
    source_ids = ", ".join(run.source_ids[:3])
    if len(run.source_ids) > 3:
        source_ids += f" (+{len(run.source_ids) - 3})"
    diagnostics = _bounded_detail([*run.errors, *run.warnings])
    return (
        "<tr>"
        f"<td><code>{html.escape(run.run_id)}</code></td>"
        f"<td>{html.escape(run.status)}</td>"
        f"<td><code>{html.escape(run.job_id)}</code><br />{html.escape(run.job_type)}</td>"
        f"<td>{html.escape(run.started_at)}</td>"
        f"<td>{html.escape(run.finished_at or '-')}</td>"
        f"<td>{html.escape(source_ids or '-')}</td>"
        f"<td>{html.escape(page_refs or '-')}</td>"
        f"<td>{html.escape(diagnostics)}</td>"
        f"<td><code>{html.escape(item.path)}</code></td>"
        "</tr>"
    )


def _queue_row(item: _QueueSummary) -> str:
    queue = item.record
    lease = "-"
    if queue.lease_owner or queue.lease_expires_at:
        lease = f"{queue.lease_owner or '-'} until {queue.lease_expires_at or '-'}"
    return (
        "<tr>"
        f"<td><code>{html.escape(queue.job_id)}</code></td>"
        f"<td>{html.escape(queue.status)}</td>"
        f"<td>{html.escape(queue.job_type)}</td>"
        f"<td>{queue.attempt_count}/{queue.max_attempts}</td>"
        f"<td>{html.escape(queue.created_at)}</td>"
        f"<td>{html.escape(queue.updated_at)}</td>"
        f"<td><code>{html.escape(queue.payload_ref)}</code></td>"
        f"<td>{html.escape(lease)}</td>"
        f"<td>{html.escape(queue.next_attempt_at or '-')}</td>"
        f"<td>{html.escape(queue.last_error or '-')}</td>"
        f"<td><code>{html.escape(item.path)}</code></td>"
        "</tr>"
    )


def _bounded_detail(values: list[str], *, limit: int = 3) -> str:
    if not values:
        return "-"
    detail = "; ".join(values[:limit])
    if len(values) > limit:
        detail += f" (+{len(values) - limit})"
    return detail


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


def _page(
    title: str,
    body: str,
    *,
    root: Path | None = None,
    layout: ResolvedLayout | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    identity = (
        _build_project_identity(root, layout)
        if root is not None
        else _ProjectIdentity(name="Splendor workspace", summary=None)
    )
    escaped_title = html.escape(title)
    escaped_project = html.escape(identity.name)
    escaped_summary = html.escape(identity.summary) if identity.summary else ""
    browser_title = f"{escaped_title} · {escaped_project} · Splendor"
    header_summary = (
        f"<span>{escaped_summary}</span>"
        if escaped_summary
        else '<span class="empty">Local Splendor wiki</span>'
    )
    return HTMLResponse(
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        f"<title>{browser_title}</title>"
        "<style>"
        ":root{color-scheme:light;--border:#d8dee8;--text:#1f2937;--muted:#5f6b7a;"
        "--surface:#f8fafc;--accent:#0f766e}"
        "body{margin:0;font:15px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"
        "'Segoe UI',sans-serif;"
        "color:var(--text);background:white}"
        "header{border-bottom:1px solid var(--border);padding:18px 28px;background:var(--surface)}"
        ".brand{max-width:1060px;margin:0 auto}.brand p{margin:4px 0 0;color:var(--muted)}"
        ".brand .product{font-size:13px;text-transform:uppercase;letter-spacing:.08em}"
        ".brand .page-title{font-size:18px;margin:4px 0 0;color:var(--text)}"
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
        ".cockpit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));"
        "gap:14px;margin:0 0 24px}"
        ".cockpit-panel{border:1px solid var(--border);border-radius:8px;padding:14px}"
        ".cockpit-panel ul{list-style:none;margin:10px 0 0;padding:0}"
        ".cockpit-panel li{border-top:1px solid var(--border);padding:9px 0}"
        ".cockpit-panel li:first-child{border-top:0;padding-top:0}"
        ".cockpit-panel a{font-weight:600}.cockpit-panel span{display:block;color:var(--muted)}"
        ".roadmap-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));"
        "gap:14px;margin:0 0 24px}"
        ".roadmap-lane{border:1px solid var(--border);border-radius:8px;padding:14px;"
        "background:var(--surface)}"
        ".roadmap-lane p{margin:0;color:var(--muted)}"
        ".roadmap-lane ul{list-style:none;margin:10px 0 0;padding:0}"
        ".roadmap-lane li{border-top:1px solid var(--border);padding:9px 0}"
        ".roadmap-lane li:first-child{border-top:0;padding-top:0}"
        ".roadmap-lane a{font-weight:600}.roadmap-lane span{display:block;color:var(--muted)}"
        ".health-panel,.attention-list{border:1px solid var(--border);border-radius:8px;"
        "padding:14px;background:var(--surface);margin:0 0 22px}"
        ".health-panel p{margin:8px 0 0}"
        ".attention-list ul{list-style:none;margin:10px 0 0;padding:0}"
        ".attention-list li{border-top:1px solid var(--border);padding:9px 0}"
        ".attention-list li:first-child{border-top:0;padding-top:0}"
        ".attention-list a{font-weight:600}.attention-list span{display:block;color:var(--muted)}"
        ".knowledge-grid,.relationships{display:grid;"
        "grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin:0 0 24px}"
        ".relationships>h2{grid-column:1/-1}"
        ".knowledge-panel,.relationship-panel{border:1px solid var(--border);border-radius:8px;"
        "padding:14px;background:var(--surface)}"
        ".knowledge-panel h3,.relationship-panel h3{font-size:16px;margin:0 0 6px}"
        ".knowledge-panel p{margin:0;color:var(--muted)}"
        ".knowledge-panel ul,.relationship-panel ul{list-style:none;margin:10px 0 0;padding:0}"
        ".knowledge-panel li,.relationship-panel li{border-top:1px solid var(--border);"
        "padding:9px 0}"
        ".knowledge-panel li:first-child,.relationship-panel li:first-child{border-top:0;"
        "padding-top:0}"
        ".knowledge-panel a,.relationship-panel a{font-weight:600}"
        ".knowledge-panel span,.relationship-panel span{display:block;color:var(--muted)}"
        ".recent-panel{border:1px solid var(--border);border-radius:8px;padding:14px;"
        "background:var(--surface);margin:0 0 22px}"
        ".recent-panel ol,.recent-panel ul{margin:10px 0 0;padding-left:22px}"
        ".recent-panel li{padding:7px 0}.recent-panel span{display:block;color:var(--muted)}"
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
        ".badges{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}"
        ".badge{border:1px solid var(--border);border-radius:999px;padding:4px 9px;"
        "background:var(--surface);font-size:13px;color:var(--muted)}"
        ".badge strong{color:var(--text);font-weight:600}"
        ".technical{margin-top:24px;border-top:1px solid var(--border);padding-top:14px}"
        ".technical summary{cursor:pointer;color:var(--muted)}"
        ".markdown{max-width:820px}.markdown img{max-width:100%}.result{margin:0 0 12px}"
        ".empty{color:var(--muted)}"
        "</style>"
        "</head>"
        "<body>"
        '<header><div class="brand">'
        f"<h1>{escaped_project}</h1>"
        f'<h2 class="page-title">{escaped_title}</h2>'
        f'<p>{header_summary} <span class="product">Splendor</span></p>'
        "</div></header>"
        f"<main>{body}</main>"
        "</body></html>",
        status_code=status_code,
    )
