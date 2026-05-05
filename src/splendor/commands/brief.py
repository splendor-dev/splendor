"""Project briefing command implementation."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import (
    DecisionRecord,
    KnowledgePageFrontmatter,
    MaintenanceReport,
    QuerySnapshot,
    SourceRecord,
)
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
    SYNTHESIS_KINDS,
    InvalidWikiPageSnapshot,
    RecentRunSnapshot,
    WikiPageSnapshot,
    WikiStatus,
    build_wiki_status,
    load_sources,
    load_wiki_pages,
)

_BRIEF_MATCH_LIMIT = 5
_BRIEF_PLANNING_LIMIT = 8
_BRIEF_SOURCE_LIMIT = 5
_BRIEF_REPORT_COMMANDS = ("lint", "health")
_SUGGESTION_LIMIT = 8
_SUGGESTION_CATEGORY_LIMITS = {
    "source-freshness": 3,
    "queue": 3,
    "wiki-validation": 2,
    "goal-match": 3,
    "authority": 3,
    "planning": 2,
    "synthesis": 2,
    "wiki-review": 2,
    "maintenance": 2,
    "query": 1,
    "orientation": 1,
}
_SUGGESTION_CATEGORY_ORDER = {
    "source-freshness": 0,
    "queue": 1,
    "wiki-validation": 2,
    "goal-match": 3,
    "authority": 4,
    "planning": 5,
    "synthesis": 6,
    "wiki-review": 7,
    "maintenance": 8,
    "query": 9,
    "orientation": 10,
}
_SUGGESTION_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_AUTHORITY_LIMIT = 6
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
_AUTHORITY_ROLE_ORDER = {
    "current-authority": 0,
    "roadmap": 1,
    "decision": 2,
    "reference": 3,
    "proposal": 4,
    "historical-review": 5,
    "generated-summary": 6,
}
_AUTHORITY_ROLE_SCORE = {
    "current-authority": 60,
    "roadmap": 45,
    "decision": 42,
    "reference": 35,
    "proposal": 25,
    "historical-review": 20,
    "generated-summary": 5,
}
_AUTHORITY_FRESHNESS_SCORE = {"current": 25, "watch": 10, "stale": -10, "historical": -20}
_AUTHORITY_LIFECYCLE_ORDER = {
    "current": 0,
    "reviewed": 1,
    "pr-linked": 2,
    "historical": 3,
    "superseded": 4,
    "archived": 5,
}
_AUTHORITY_LIFECYCLE_SCORE = {
    "current": 35,
    "reviewed": 30,
    "pr-linked": 28,
    "historical": -5,
    "superseded": -30,
    "archived": -35,
}
_AUTHORITY_LIFECYCLE_TIER = {
    "current": 0,
    "reviewed": 0,
    "pr-linked": 0,
    "historical": 1,
    "superseded": 2,
    "archived": 3,
}
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
class AuthorityBrief:
    rank: int
    path: str
    title: str
    role: str
    freshness: str
    lifecycle: str
    score: int
    reason: str
    issue_refs: list[str]
    pr_refs: list[str]
    supersedes: list[str]
    superseded_by: str | None


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
    authority_briefs: list[AuthorityBrief]
    planning_items: list[BriefPlanningItem]
    latest_reports: list[BriefReportSnapshot]
    warnings: list[BriefWarning]


@dataclass(frozen=True)
class BriefStateSnapshot:
    root: Path
    goal: str | None
    query_summary: str | None
    layout: object
    status: WikiStatus
    queue: QueueInspectResult
    freshness: SourceFreshnessResult
    matches: list[BriefMatch]
    authority_briefs: list[AuthorityBrief]
    planning_items: list[BriefPlanningItem]
    recent_sources: list[BriefSourceItem]
    recent_runs: list[RecentRunSnapshot]
    latest_reports: list[BriefReportSnapshot]
    last_query: BriefLastQuery | None
    warnings: list[BriefWarning]
    sources_by_id: dict[str, SourceRecord]
    wiki_pages: list[WikiPageSnapshot]
    invalid_wiki_pages: list[InvalidWikiPageSnapshot]


@dataclass(frozen=True)
class ProjectBrief:
    goal: str | None
    query_summary: str | None
    status: WikiStatus
    matches: list[BriefMatch]
    authority_briefs: list[AuthorityBrief]
    planning_items: list[BriefPlanningItem]
    recent_sources: list[BriefSourceItem]
    recent_runs: list[RecentRunSnapshot]
    latest_reports: list[BriefReportSnapshot]
    last_query: BriefLastQuery | None
    warnings: list[BriefWarning]
    suggested_actions: list[SuggestedAction]
    next_actions: list[str]


def build_project_brief(root: Path, goal: str | None) -> ProjectBrief:
    snapshot = _collect_brief_state(root, goal)
    suggested_actions = _ranked_suggestions(snapshot)
    next_actions = _next_actions(
        status=snapshot.status,
        matches=snapshot.matches,
        authority_briefs=snapshot.authority_briefs,
        planning_items=snapshot.planning_items,
        warnings=snapshot.warnings,
        suggested_actions=suggested_actions,
    )
    return ProjectBrief(
        goal=snapshot.goal,
        query_summary=snapshot.query_summary,
        status=snapshot.status,
        matches=snapshot.matches,
        authority_briefs=snapshot.authority_briefs,
        planning_items=snapshot.planning_items,
        recent_sources=snapshot.recent_sources,
        recent_runs=snapshot.recent_runs,
        latest_reports=snapshot.latest_reports,
        last_query=snapshot.last_query,
        warnings=snapshot.warnings,
        suggested_actions=suggested_actions,
        next_actions=next_actions,
    )


def build_suggest_next(root: Path, goal: str | None = None) -> SuggestNextResult:
    snapshot = _collect_brief_state(root, goal)
    actions = _ranked_suggestions(snapshot)
    return SuggestNextResult(
        goal=snapshot.goal,
        actions=actions,
        status=snapshot.status,
        queue=snapshot.queue,
        freshness=snapshot.freshness,
        matches=snapshot.matches,
        authority_briefs=snapshot.authority_briefs,
        planning_items=snapshot.planning_items,
        latest_reports=snapshot.latest_reports,
        warnings=snapshot.warnings,
    )


def _collect_brief_state(root: Path, goal: str | None) -> BriefStateSnapshot:
    config = load_config(root)
    layout = resolve_layout(root, config)
    status = build_wiki_status(root)
    queue = inspect_queue(root)
    freshness = scan_source_freshness(root)
    normalized_goal = goal.strip() if goal is not None else ""
    query_summary: str | None = None
    query_warning: BriefWarning | None = None
    matches: list[BriefMatch] = []
    if normalized_goal:
        try:
            query_result = run_query(root, normalized_goal)
        except (QueryValidationError, OSError, ValueError) as exc:
            query_result = None
            query_summary = f"Query skipped: {_brief_error(exc)}"
            query_warning = BriefWarning(area="query", path=None, message=query_summary)
        if query_result is not None:
            query_summary = query_result.summary
            matches = [_brief_match(match) for match in query_result.matches[:_BRIEF_MATCH_LIMIT]]

    planning_items, warnings = _active_planning_items(root, layout)
    if query_warning is not None:
        warnings.insert(0, query_warning)
    sources = load_sources(layout)
    sources_by_id = {source.source_id: source for source in sources}
    wiki_pages, invalid_wiki_pages = load_wiki_pages(root, layout)
    authority_briefs, authority_warnings = _authority_briefs(root, layout, config, wiki_pages, goal)
    warnings.extend(authority_warnings)
    recent_sources = _recent_sources(sources)
    recent_runs = status.recent_runs
    latest_reports = _latest_reports(root, layout)
    last_query = _last_query(layout)
    return BriefStateSnapshot(
        root=root,
        goal=normalized_goal or None,
        query_summary=query_summary,
        layout=layout,
        status=status,
        queue=queue,
        freshness=freshness,
        matches=matches,
        authority_briefs=authority_briefs,
        planning_items=planning_items,
        recent_sources=recent_sources,
        recent_runs=recent_runs,
        latest_reports=latest_reports,
        last_query=last_query,
        warnings=warnings,
        sources_by_id=sources_by_id,
        wiki_pages=wiki_pages,
        invalid_wiki_pages=invalid_wiki_pages,
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


def _authority_briefs(root: Path, layout, config, pages: list[WikiPageSnapshot], goal: str | None):
    items: list[AuthorityBrief] = []
    warnings: list[BriefWarning] = []
    goal_tokens = _tokens(goal or "")

    for doc in config.briefing.authority_documents:
        path = Path(doc.path)
        absolute = root / path
        if absolute.exists() and absolute.is_file():
            body = absolute.read_text(encoding="utf-8", errors="replace")
        else:
            warnings.append(
                BriefWarning(
                    area="authority",
                    path=path.as_posix(),
                    message="Configured authority document is missing.",
                )
            )
            continue
        title = doc.title or _title_from_markdown(body) or path.name
        reason = doc.purpose or f"{doc.role} document for {path.as_posix()}"
        lifecycle = _configured_authority_lifecycle(
            doc.authority_lifecycle,
            role=doc.role,
            freshness=doc.freshness,
            superseded_by=doc.superseded_by,
        )
        score = _authority_score(
            role=doc.role,
            freshness=doc.freshness,
            lifecycle=lifecycle,
            goal_tokens=goal_tokens,
            text=" ".join([title, reason, " ".join(doc.applies_to), path.as_posix(), body]),
        )
        items.append(
            AuthorityBrief(
                rank=0,
                path=path.as_posix(),
                title=title,
                role=doc.role,
                freshness=doc.freshness,
                lifecycle=lifecycle,
                score=score,
                reason=reason,
                issue_refs=doc.issue_refs,
                pr_refs=doc.pr_refs,
                supersedes=doc.supersedes,
                superseded_by=doc.superseded_by,
            )
        )

    for page in pages:
        if page.frontmatter.kind == "source-summary":
            continue
        if page.frontmatter.authority_role is None:
            continue
        freshness = page.frontmatter.authority_freshness or _derived_authority_freshness(
            page.frontmatter
        )
        lifecycle = _wiki_authority_lifecycle(page.frontmatter, freshness=freshness)
        reason = (
            "Maintained wiki page marked for agent briefing"
            if not page.frontmatter.authority_scope
            else "Applies to " + ", ".join(page.frontmatter.authority_scope)
        )
        score = _authority_score(
            role=page.frontmatter.authority_role,
            freshness=freshness,
            lifecycle=lifecycle,
            goal_tokens=goal_tokens,
            text=" ".join(
                [
                    page.frontmatter.title,
                    page.frontmatter.page_id,
                    page.path,
                    " ".join(page.frontmatter.authority_scope),
                    page.body,
                ]
            ),
        )
        items.append(
            AuthorityBrief(
                rank=0,
                path=page.path,
                title=page.frontmatter.title,
                role=page.frontmatter.authority_role,
                freshness=freshness,
                lifecycle=lifecycle,
                score=score,
                reason=reason,
                issue_refs=page.frontmatter.issue_refs,
                pr_refs=page.frontmatter.pr_refs,
                supersedes=page.frontmatter.supersedes,
                superseded_by=page.frontmatter.superseded_by,
            )
        )

    items.extend(_decision_authority_briefs(root, layout, goal_tokens))
    ranked = sorted(
        enumerate(items),
        key=lambda item: (
            _AUTHORITY_LIFECYCLE_TIER.get(item[1].lifecycle, 99),
            _AUTHORITY_LIFECYCLE_ORDER.get(item[1].lifecycle, 99),
            _AUTHORITY_ROLE_ORDER.get(item[1].role, 99),
            -item[1].score,
            item[0],
            item[1].path,
        ),
    )
    return [
        replace(item, rank=rank)
        for rank, (_sequence, item) in enumerate(ranked[:_AUTHORITY_LIMIT], start=1)
    ], warnings


def _authority_score(
    *, role: str, freshness: str, lifecycle: str, goal_tokens: set[str], text: str
) -> int:
    score = (
        _AUTHORITY_ROLE_SCORE.get(role, 0)
        + _AUTHORITY_FRESHNESS_SCORE.get(freshness, 0)
        + _AUTHORITY_LIFECYCLE_SCORE.get(lifecycle, 0)
    )
    if goal_tokens:
        overlap = goal_tokens & _tokens(text)
        score += min(len(overlap), 6) * 12
    return score


def _configured_authority_lifecycle(
    lifecycle: str | None, *, role: str, freshness: str, superseded_by: str | None
) -> str:
    if lifecycle is not None:
        return lifecycle
    if superseded_by is not None:
        return "superseded"
    if freshness == "historical" or role == "historical-review":
        return "historical"
    return "current"


def _wiki_authority_lifecycle(frontmatter: KnowledgePageFrontmatter, *, freshness: str) -> str:
    if frontmatter.authority_lifecycle is not None:
        return frontmatter.authority_lifecycle
    if frontmatter.superseded_by is not None:
        return "superseded"
    if freshness == "historical" or frontmatter.authority_role == "historical-review":
        return "historical"
    if frontmatter.review_state == "human-reviewed" or frontmatter.last_reviewed_at is not None:
        return "reviewed"
    return "current"


def _decision_authority_briefs(root: Path, layout, goal_tokens: set[str]) -> list[AuthorityBrief]:
    if not goal_tokens:
        return []
    items: list[AuthorityBrief] = []
    for path in iter_planning_paths(planning_directory(layout, "decision")):
        try:
            parsed = parse_planning_document(path, DecisionRecord)
        except (OSError, ValueError):
            continue
        record = parsed.record
        if record.status not in {"accepted", "superseded"}:
            continue
        text = " ".join(
            [
                record.title,
                record.decision_id,
                record.decided_at or "",
                " ".join(record.source_refs),
                " ".join(record.related_tasks),
                " ".join(record.related_questions),
                " ".join(record.issue_refs),
                " ".join(record.pr_refs),
                parsed.body,
            ]
        )
        if not (goal_tokens & _tokens(text)):
            continue
        lifecycle = record.authority_lifecycle or (
            "superseded" if record.status == "superseded" else "reviewed"
        )
        freshness = (
            "historical" if lifecycle in {"historical", "superseded", "archived"} else "current"
        )
        reason = (
            "Accepted planning decision"
            if record.status == "accepted"
            else "Superseded planning decision retained for historical context"
        )
        items.append(
            AuthorityBrief(
                rank=0,
                path=path.relative_to(root).as_posix(),
                title=record.title,
                role="decision",
                freshness=freshness,
                lifecycle=lifecycle,
                score=_authority_score(
                    role="decision",
                    freshness=freshness,
                    lifecycle=lifecycle,
                    goal_tokens=goal_tokens,
                    text=text,
                ),
                reason=reason,
                issue_refs=record.issue_refs,
                pr_refs=record.pr_refs,
                supersedes=record.supersedes,
                superseded_by=record.superseded_by,
            )
        )
    return items


def _derived_authority_freshness(frontmatter: KnowledgePageFrontmatter) -> str:
    if frontmatter.status == "stale" or frontmatter.review_state in {"contested", "stale"}:
        return "stale"
    if frontmatter.status == "draft" or frontmatter.review_state in {"draft", "machine-generated"}:
        return "watch"
    return "current"


def _title_from_markdown(body: str) -> str | None:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip() or None
    return None


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


def _recent_sources(sources: list[SourceRecord]) -> list[BriefSourceItem]:
    sources = sorted(sources, key=lambda source: (source.added_at, source.source_id))
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
    authority_briefs: list[AuthorityBrief],
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
    if authority_briefs:
        actions.append("Read the top authority docs before changing planning-heavy behavior.")
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


def _ranked_suggestions(snapshot: BriefStateSnapshot) -> list[SuggestedAction]:
    actions: list[SuggestedAction] = []

    def add(priority: str, category: str, title: str, reason: str, command: str | None, **kwargs):
        actions.append(
            SuggestedAction(
                rank=0,
                priority=priority,
                category=category,
                title=title,
                reason=reason,
                command=command,
                **kwargs,
            )
        )

    for item in snapshot.freshness.sources:
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

    for item in snapshot.queue.items:
        source = snapshot.sources_by_id.get(item.source_id or "")
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

    for page in _review_page_actions(snapshot.wiki_pages, snapshot.invalid_wiki_pages):
        add(**page)

    for source_id in _sources_missing_synthesis(snapshot.wiki_pages, snapshot.sources_by_id):
        source = snapshot.sources_by_id[source_id]
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

    for report in snapshot.latest_reports:
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

    for match in snapshot.matches[:3]:
        add(
            "medium",
            "goal-match",
            f"Open goal match {match.path}",
            f"Matched the stated goal with score {match.score}.",
            None,
            path=match.path,
            record_id=match.record_id,
        )

    for authority in snapshot.authority_briefs[:3]:
        priority = (
            "medium"
            if authority.lifecycle in {"current", "reviewed", "pr-linked"}
            and authority.role in {"current-authority", "roadmap", "decision"}
            else "low"
        )
        title = (
            f"Review decision {authority.path}"
            if authority.role == "decision"
            else f"Read authority doc {authority.path}"
        )
        add(
            priority,
            "authority",
            title,
            f"{authority.role}/{authority.freshness}/{authority.lifecycle}: {authority.reason}",
            None,
            path=authority.path,
        )

    for item in snapshot.planning_items:
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

    for warning in snapshot.warnings:
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

    return _finalize_suggestions(actions)


def _first_command(commands: list[str]) -> str | None:
    return commands[0] if commands else None


def _finalize_suggestions(actions: list[SuggestedAction]) -> list[SuggestedAction]:
    by_category: dict[str, int] = {}
    capped: list[tuple[int, SuggestedAction]] = []
    for sequence, action in enumerate(actions):
        current_count = by_category.get(action.category, 0)
        category_limit = _SUGGESTION_CATEGORY_LIMITS.get(action.category, 1)
        if current_count >= category_limit:
            continue
        by_category[action.category] = current_count + 1
        capped.append((sequence, action))

    capped.sort(
        key=lambda item: (
            _SUGGESTION_CATEGORY_ORDER.get(item[1].category, 99),
            _SUGGESTION_PRIORITY_ORDER.get(item[1].priority, 99),
            item[0],
        )
    )
    return [
        replace(action, rank=rank)
        for rank, (_sequence, action) in enumerate(capped[:_SUGGESTION_LIMIT], start=1)
    ]


def _review_page_actions(
    pages: list[WikiPageSnapshot], invalid_pages: list[InvalidWikiPageSnapshot]
) -> list[dict[str, object]]:
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
        if page.frontmatter.kind not in SYNTHESIS_KINDS and state != "contested":
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


def _sources_missing_synthesis(
    pages: list[WikiPageSnapshot], sources_by_id: dict[str, SourceRecord]
) -> list[str]:
    synthesis_source_ids = {
        source_ref
        for page in pages
        if page.frontmatter.kind in SYNTHESIS_KINDS
        for source_ref in page.frontmatter.source_refs
    }
    synthesis_pages = [page for page in pages if page.frontmatter.kind in SYNTHESIS_KINDS]
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
            "authority_briefs": [asdict(brief) for brief in result.authority_briefs],
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
            "authority_briefs": [asdict(item) for item in brief.authority_briefs],
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
            "authority_briefs": [asdict(item) for item in brief.authority_briefs],
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
