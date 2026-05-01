"""Project briefing command implementation."""

from __future__ import annotations

import json
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
from .wiki import (
    RecentRunSnapshot,
    WikiStatus,
    build_wiki_status,
    load_sources,
)

_BRIEF_MATCH_LIMIT = 5
_BRIEF_PLANNING_LIMIT = 8
_BRIEF_SOURCE_LIMIT = 5
_BRIEF_REPORT_COMMANDS = ("lint", "health")
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
    next_actions = _next_actions(
        status=status,
        matches=matches,
        planning_items=planning_items,
        warnings=warnings,
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
        next_actions=next_actions,
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
) -> list[str]:
    actions: list[str] = []
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
    for source in brief.recent_sources:
        refs.add(source.source_id)
    return sorted(refs)
