"""Project briefing command implementation."""

from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path

from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import MaintenanceReport, QuerySnapshot
from splendor.state.query_snapshot import last_query_path_for
from splendor.state.source_compat import canonical_source_ref
from splendor.utils.planning import (
    iter_planning_paths,
    parse_planning_document,
    planning_directory,
    record_id_field,
)

from .planning import model_for_planning_kind
from .query import QueryMatch, QueryValidationError, run_query
from .queue import QueueInspectResult, inspect_queue
from .source import SourceFreshnessResult, scan_source_freshness
from .wiki import (
    _SYNTHESIS_KINDS,
    RecentRunSnapshot,
    WikiStatus,
    _load_wiki_pages,
    build_wiki_status,
    load_sources,
)

_BRIEF_MATCH_LIMIT = 5
_BRIEF_PLANNING_LIMIT = 8
_BRIEF_SOURCE_LIMIT = 5
_BRIEF_REPORT_COMMANDS = ("lint", "health")
_SUGGESTION_LIMIT = 8
_PLANNING_STATUSES = {
    "task": {"todo", "in_progress", "blocked"},
    "milestone": {"planned", "active"},
    "decision": {"proposed"},
    "question": {"open", "deferred"},
}


@dataclass(frozen=True)
class BriefMatch:
    rank: int
    score: int
    document_class: str
    kind: str
    record_id: str
    title: str
    path: str
    review_state: str | None
    source_refs: list[str]
    snippet: str


@dataclass(frozen=True)
class BriefPlanningItem:
    kind: str
    record_id: str
    title: str
    status: str
    path: str


@dataclass(frozen=True)
class BriefWarning:
    area: str
    path: str | None
    message: str


@dataclass(frozen=True)
class BriefSourceItem:
    source_id: str
    title: str
    status: str
    review_state: str
    source_ref: str
    last_run_id: str | None


@dataclass(frozen=True)
class BriefReportSnapshot:
    command: str
    status: str
    created_at: str
    issue_count: int
    path: str


@dataclass(frozen=True)
class BriefLastQuery:
    query: str
    created_at: str
    match_count: int
    summary: str


@dataclass(frozen=True)
class SuggestedAction:
    rank: int
    category: str
    priority: str
    title: str
    reason: str
    command: str | None
    path: str | None = None
    source_id: str | None = None
    source_ref: str | None = None
    record_id: str | None = None


@dataclass(frozen=True)
class SuggestNextResult:
    goal: str | None
    actions: list[SuggestedAction]
    status: WikiStatus
    queue: QueueInspectResult
    freshness: SourceFreshnessResult
    matches: list[BriefMatch]
    planning_items: list[BriefPlanningItem]
    latest_reports: list[BriefReportSnapshot]
    warnings: list[BriefWarning]


@dataclass(frozen=True)
class ProjectBrief:
    goal: str | None
    query_summary: str | None
    status: WikiStatus
    matches: list[BriefMatch]
    planning_items: list[BriefPlanningItem]
    recent_sources: list[BriefSourceItem]
    recent_runs: list[RecentRunSnapshot]
    latest_reports: list[BriefReportSnapshot]
    last_query: BriefLastQuery | None
    warnings: list[BriefWarning]
    suggested_actions: list[SuggestedAction]
    next_actions: list[str]


def build_project_brief(root: Path, goal: str | None) -> ProjectBrief:
    config = load_config(root)
    layout = resolve_layout(root, config)
    status = build_wiki_status(root)
    normalized_goal = goal.strip() if goal is not None else ""
    query_summary: str | None = None
    matches: list[BriefMatch] = []
    if normalized_goal:
        try:
            query_result = run_query(root, normalized_goal)
        except (QueryValidationError, OSError, ValueError) as exc:
            query_result = None
            query_summary = f"Query skipped: {_brief_error(exc)}"
        if query_result is not None:
            query_summary = query_result.summary
            matches = [_brief_match(match) for match in query_result.matches[:_BRIEF_MATCH_LIMIT]]

    planning_items, warnings = _active_planning_items(root, layout)
    recent_sources = _recent_sources(root, layout)
    recent_runs = status.recent_runs
    latest_reports = _latest_reports(root, layout)
    last_query = _last_query(layout)
    suggested_actions = build_suggest_next(root, normalized_goal or None).actions
    next_actions = _next_actions(
        status=status,
        matches=matches,
        planning_items=planning_items,
        warnings=warnings,
        suggested_actions=suggested_actions,
    )
    return ProjectBrief(
        goal=normalized_goal or None,
        query_summary=query_summary,
        status=status,
        matches=matches,
        planning_items=planning_items,
        recent_sources=recent_sources,
        recent_runs=recent_runs,
        latest_reports=latest_reports,
        last_query=last_query,
        warnings=warnings,
        suggested_actions=suggested_actions,
        next_actions=next_actions,
    )


def build_suggest_next(root: Path, goal: str | None = None) -> SuggestNextResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    status = build_wiki_status(root)
    queue = inspect_queue(root)
    freshness = scan_source_freshness(root)
    normalized_goal = goal.strip() if goal is not None else ""
    matches: list[BriefMatch] = []
    warnings: list[BriefWarning] = []
    if normalized_goal:
        try:
            query_result = run_query(root, normalized_goal)
        except (QueryValidationError, OSError, ValueError) as exc:
            warnings.append(
                BriefWarning(area="query", path=None, message=f"Query skipped: {_brief_error(exc)}")
            )
        else:
            matches = [_brief_match(match) for match in query_result.matches[:_BRIEF_MATCH_LIMIT]]

    planning_items, planning_warnings = _active_planning_items(root, layout)
    warnings.extend(planning_warnings)
    latest_reports = _latest_reports(root, layout)
    actions = _ranked_suggestions(
        root=root,
        layout=layout,
        status=status,
        queue=queue,
        freshness=freshness,
        matches=matches,
        planning_items=planning_items,
        latest_reports=latest_reports,
        warnings=warnings,
    )
    return SuggestNextResult(
        goal=normalized_goal or None,
        actions=actions[:_SUGGESTION_LIMIT],
        status=status,
        queue=queue,
        freshness=freshness,
        matches=matches,
        planning_items=planning_items,
        latest_reports=latest_reports,
        warnings=warnings,
    )


def _brief_match(match: QueryMatch) -> BriefMatch:
    return BriefMatch(
        rank=match.rank,
        score=match.score,
        document_class=match.document_class,
        kind=match.kind,
        record_id=match.record_id,
        title=match.title,
        path=match.path,
        review_state=match.review_state,
        source_refs=match.source_refs,
        snippet=match.snippet,
    )


def _brief_error(exc: Exception) -> str:
    return " ".join(str(exc).splitlines()).strip() or exc.__class__.__name__


def _active_planning_items(
    root: Path, layout
) -> tuple[list[BriefPlanningItem], list[BriefWarning]]:
    items: list[BriefPlanningItem] = []
    warnings: list[BriefWarning] = []
    for kind, statuses in _PLANNING_STATUSES.items():
        model = model_for_planning_kind(kind)
        id_field = record_id_field(kind)
        for path in iter_planning_paths(planning_directory(layout, kind)):
            try:
                parsed = parse_planning_document(path, model)
            except (OSError, ValueError) as exc:
                warnings.append(
                    BriefWarning(
                        area="planning",
                        path=path.relative_to(root).as_posix(),
                        message=_brief_error(exc),
                    )
                )
                continue
            record = parsed.record
            status = record.status
            if status not in statuses:
                continue
            items.append(
                BriefPlanningItem(
                    kind=kind,
                    record_id=str(getattr(record, id_field)),
                    title=record.title,
                    status=status,
                    path=path.relative_to(root).as_posix(),
                )
            )
    items.sort(key=lambda item: (item.kind, item.status, item.record_id))
    return items[:_BRIEF_PLANNING_LIMIT], warnings


def _recent_sources(root: Path, layout) -> list[BriefSourceItem]:
    sources = sorted(load_sources(layout), key=lambda source: (source.added_at, source.source_id))
    return [
        BriefSourceItem(
            source_id=source.source_id,
            title=source.title,
            status=source.status,
            review_state=source.review_state,
            source_ref=canonical_source_ref(source),
            last_run_id=source.last_run_id,
        )
        for source in reversed(sources[-_BRIEF_SOURCE_LIMIT:])
    ]


def _latest_reports(root: Path, layout) -> list[BriefReportSnapshot]:
    reports: list[BriefReportSnapshot] = []
    for command in _BRIEF_REPORT_COMMANDS:
        report_paths = sorted((layout.reports_dir / command).glob("*.json"))
        if not report_paths:
            continue
        path = report_paths[-1]
        report = MaintenanceReport.model_validate_json(path.read_text(encoding="utf-8"))
        reports.append(
            BriefReportSnapshot(
                command=command,
                status=report.status,
                created_at=report.created_at,
                issue_count=report.issue_count,
                path=path.relative_to(root).as_posix(),
            )
        )
    return reports


def _last_query(layout) -> BriefLastQuery | None:
    path = last_query_path_for(layout)
    if not path.exists():
        return None
    snapshot = QuerySnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    return BriefLastQuery(
        query=snapshot.query,
        created_at=snapshot.created_at,
        match_count=snapshot.match_count,
        summary=snapshot.summary,
    )


def _next_actions(
    *,
    status: WikiStatus,
    matches: list[BriefMatch],
    planning_items: list[BriefPlanningItem],
    warnings: list[BriefWarning],
    suggested_actions: list[SuggestedAction],
) -> list[str]:
    actions: list[str] = []
    if suggested_actions:
        actions.extend(
            f"{action.title}" + (f" (`{action.command}`)" if action.command is not None else "")
            for action in suggested_actions[:5]
        )
    if status.queue_status_counts.get("pending", 0):
        actions.append("Run `splendor ingest --pending` to drain pending source ingests.")
    if status.invalid_pages:
        actions.append("Fix invalid wiki pages before relying on synthesis or query output.")
    if status.sources_missing_synthesis:
        actions.append(
            "Run `splendor wiki suggest <source-id>` for ingested sources missing "
            "synthesis follow-up."
        )
    if status.review_needed_synthesis_pages:
        actions.append("Review draft, stale, contested, or machine-generated synthesis pages.")
    if matches:
        actions.append("Open the top matching wiki or planning records for the stated goal.")
    if planning_items:
        actions.append("Continue or close the active planning records listed in this brief.")
    if warnings:
        actions.append("Fix skipped planning records so future briefs include the full plan state.")
    if not actions:
        actions.append(
            "Run `splendor add-source <path>` or `splendor query <question>` to extend "
            "the project context."
        )
    return actions


def _ranked_suggestions(
    *,
    root: Path,
    layout,
    status: WikiStatus,
    queue: QueueInspectResult,
    freshness: SourceFreshnessResult,
    matches: list[BriefMatch],
    planning_items: list[BriefPlanningItem],
    latest_reports: list[BriefReportSnapshot],
    warnings: list[BriefWarning],
) -> list[SuggestedAction]:
    sources_by_id = {source.source_id: source for source in load_sources(layout)}
    actions: list[SuggestedAction] = []
    rank = 0

    def add(priority: str, category: str, title: str, reason: str, command: str | None, **kwargs):
        nonlocal rank
        rank += 1
        actions.append(
            SuggestedAction(
                rank=rank,
                priority=priority,
                category=category,
                title=title,
                reason=reason,
                command=command,
                **kwargs,
            )
        )

    for item in freshness.sources:
        source = item.source
        if item.status == "changed":
            add(
                "high",
                "source-freshness",
                f"Refresh changed source {item.canonical_path}",
                "The workspace file differs from the latest curated source manifest.",
                _first_command(item.next_commands),
                path=item.canonical_path,
                source_id=source.source_id,
                source_ref=canonical_source_ref(source),
            )
        elif item.status == "missing":
            add(
                "high",
                "source-freshness",
                f"Resolve missing source {item.canonical_path}",
                "A curated workspace source path no longer exists.",
                _first_command(item.next_commands),
                path=item.canonical_path,
                source_id=source.source_id,
                source_ref=canonical_source_ref(source),
            )

    for item in queue.items:
        source = sources_by_id.get(item.source_id or "")
        source_ref = canonical_source_ref(source) if source is not None else None
        if item.operator_state in {"pending", "failed_due", "expired_leased"}:
            add(
                "high",
                "queue",
                f"Drain ingest queue job {item.job_id}",
                f"Queue job is actionable now: {item.operator_state}.",
                "splendor ingest --pending",
                path=item.record_path.as_posix(),
                source_id=item.source_id,
                source_ref=source_ref,
            )
        elif item.operator_state == "dead_letter":
            command = (
                f"splendor repair ingest {shlex.quote(item.source_id)}"
                if item.source_id
                else f"splendor queue retry {shlex.quote(item.job_id)}"
            )
            add(
                "high",
                "queue",
                f"Repair dead-letter queue job {item.job_id}",
                item.last_error or "Queue job reached dead-letter state.",
                command,
                path=item.record_path.as_posix(),
                source_id=item.source_id,
                source_ref=source_ref,
            )
        elif item.operator_state == "failed_backoff":
            add(
                "medium",
                "queue",
                f"Review backoff queue job {item.job_id}",
                "Queue job failed and is waiting for its next retry window.",
                f"splendor queue inspect {shlex.quote(item.job_id)}",
                path=item.record_path.as_posix(),
                source_id=item.source_id,
                source_ref=source_ref,
            )

    for page in _review_page_actions(root, layout):
        add(**page)

    for source_id in _sources_missing_synthesis(root, layout, sources_by_id):
        source = sources_by_id[source_id]
        source_ref = canonical_source_ref(source)
        add(
            "medium",
            "synthesis",
            f"Review synthesis follow-up for {source_ref}",
            "The source is ingested but has no maintained synthesis-page follow-up.",
            f"splendor wiki suggest {shlex.quote(source_id)}",
            path=source_ref,
            source_id=source_id,
            source_ref=source_ref,
        )

    for report in latest_reports:
        if report.status != "passed" or report.issue_count:
            add(
                "medium",
                "maintenance",
                f"Review latest {report.command} report",
                f"Latest {report.command} report status is {report.status} with "
                f"{report.issue_count} issue(s).",
                f"splendor {report.command}",
                path=report.path,
            )

    for match in matches[:3]:
        add(
            "medium",
            "goal-match",
            f"Open goal match {match.path}",
            f"Matched the stated goal with score {match.score}.",
            None,
            path=match.path,
            record_id=match.record_id,
        )

    for item in planning_items:
        command = f"splendor task list --status {item.status}" if item.kind == "task" else None
        add(
            "low",
            "planning",
            f"Continue {item.kind} {item.record_id}",
            f"Planning record is active with status {item.status}.",
            command,
            path=item.path,
            record_id=item.record_id,
        )

    for warning in warnings:
        add(
            "low",
            warning.area,
            f"Fix skipped {warning.area} record",
            warning.message,
            None,
            path=warning.path,
        )

    if not actions:
        add(
            "low",
            "orientation",
            "Add or query project context",
            "No stale, queued, contested, or active planning work was found.",
            "splendor brief --agent-context",
        )

    return actions


def _first_command(commands: list[str]) -> str | None:
    return commands[0] if commands else None


def _review_page_actions(root: Path, layout) -> list[dict[str, object]]:
    pages, invalid_pages = _load_wiki_pages(root, layout)
    actions: list[dict[str, object]] = []
    for invalid in invalid_pages:
        actions.append(
            {
                "priority": "high",
                "category": "wiki-validation",
                "title": f"Fix invalid wiki page {invalid.path}",
                "reason": invalid.error,
                "command": "splendor lint",
                "path": invalid.path,
            }
        )
    for page in pages:
        state = page.frontmatter.review_state
        if state not in {"contested", "stale", "draft", "machine-generated"}:
            continue
        if page.frontmatter.kind not in _SYNTHESIS_KINDS and state != "contested":
            continue
        priority = "high" if state in {"contested", "stale"} else "medium"
        actions.append(
            {
                "priority": priority,
                "category": "wiki-review",
                "title": f"Review {state} page {page.path}",
                "reason": (
                    f"Page `{page.frontmatter.title}` is {state}; verify current source-backed "
                    "synthesis before relying on it."
                ),
                "command": None,
                "path": page.path,
                "record_id": page.frontmatter.page_id,
            }
        )
    return actions


def _sources_missing_synthesis(root: Path, layout, sources_by_id) -> list[str]:
    pages, _invalid_pages = _load_wiki_pages(root, layout)
    synthesis_source_ids = {
        source_ref
        for page in pages
        if page.frontmatter.kind in _SYNTHESIS_KINDS
        for source_ref in page.frontmatter.source_refs
    }
    synthesis_pages = [page for page in pages if page.frontmatter.kind in _SYNTHESIS_KINDS]
    source_ids = []
    for source_id, source in sources_by_id.items():
        if source.status != "ingested":
            continue
        source_ref = canonical_source_ref(source)
        if source_id in synthesis_source_ids:
            continue
        if any(source_ref in page.body for page in synthesis_pages):
            continue
        source_ids.append(source_id)
    return sorted(source_ids, key=lambda source_id: canonical_source_ref(sources_by_id[source_id]))


def render_suggest_next_json(result: SuggestNextResult) -> str:
    return json.dumps(
        {
            "goal": result.goal,
            "actions": [asdict(action) for action in result.actions],
            "status": {
                "source_total": result.status.source_total,
                "page_total": result.status.page_total,
                "queue_status_counts": result.status.queue_status_counts,
                "review_needed_pages": result.status.review_needed_pages,
                "contested_pages": result.status.contested_pages,
                "stale_pages": result.status.stale_pages,
                "sources_missing_synthesis": result.status.sources_missing_synthesis,
                "invalid_pages": result.status.invalid_pages,
            },
            "freshness": {
                "total": result.freshness.total,
                "changed": result.freshness.changed,
                "missing": result.freshness.missing,
                "unsupported": result.freshness.unsupported,
                "historical": result.freshness.historical,
            },
            "queue": {
                "total": result.queue.total,
                "status_counts": result.queue.status_counts,
            },
            "matches": [asdict(match) for match in result.matches],
            "planning_items": [asdict(item) for item in result.planning_items],
            "latest_reports": [asdict(report) for report in result.latest_reports],
            "warnings": [asdict(warning) for warning in result.warnings],
        },
        indent=2,
    )


def render_project_brief_json(brief: ProjectBrief) -> str:
    return json.dumps(
        {
            "goal": brief.goal,
            "query_summary": brief.query_summary,
            "status": asdict(brief.status),
            "matches": [asdict(match) for match in brief.matches],
            "planning_items": [asdict(item) for item in brief.planning_items],
            "recent_sources": [asdict(source) for source in brief.recent_sources],
            "recent_runs": [asdict(run) for run in brief.recent_runs],
            "latest_reports": [asdict(report) for report in brief.latest_reports],
            "last_query": asdict(brief.last_query) if brief.last_query else None,
            "warnings": [asdict(warning) for warning in brief.warnings],
            "suggested_actions": [asdict(action) for action in brief.suggested_actions],
            "next_actions": brief.next_actions,
        },
        indent=2,
    )


def render_agent_context_json(brief: ProjectBrief) -> str:
    return json.dumps(
        {
            "agent_context": True,
            "goal": brief.goal,
            "query_summary": brief.query_summary,
            "wiki_status": {
                "source_total": brief.status.source_total,
                "page_total": brief.status.page_total,
                "queue_status_counts": brief.status.queue_status_counts,
                "review_needed_pages": brief.status.review_needed_pages,
                "machine_generated_pages": brief.status.machine_generated_pages,
                "contested_pages": brief.status.contested_pages,
                "stale_pages": brief.status.stale_pages,
                "sources_missing_synthesis": brief.status.sources_missing_synthesis,
            },
            "matches": [asdict(match) for match in brief.matches],
            "source_refs": _agent_context_source_refs(brief),
            "suggested_actions": [asdict(action) for action in brief.suggested_actions],
            "active_planning": [asdict(item) for item in brief.planning_items],
            "recent_sources": [asdict(source) for source in brief.recent_sources],
            "recent_runs": [asdict(run) for run in brief.recent_runs],
            "latest_reports": [asdict(report) for report in brief.latest_reports],
            "last_query": asdict(brief.last_query) if brief.last_query else None,
            "warnings": [asdict(warning) for warning in brief.warnings],
            "next_actions": brief.next_actions,
        },
        indent=2,
    )


def _agent_context_source_refs(brief: ProjectBrief) -> list[str]:
    refs: set[str] = set()
    for match in brief.matches:
        refs.update(match.source_refs)
    return sorted(refs)
