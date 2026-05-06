"""Project briefing command implementation."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
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

from .planning import is_generated_contradiction_review_task, model_for_planning_kind
from .pr_summary import build_pr_summary
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
_GIT_CONTEXT_LIMIT = 5
_GIT_FILE_LIMIT = 8
_GIT_COMMAND_TIMEOUT_SECONDS = 5
_PROMOTED_THREAD_RELEVANCE_FLOOR = 60
_SUGGESTION_CATEGORY_LIMITS = {
    "work-thread": 4,
    "git-context": 3,
    "source-freshness": 3,
    "queue": 3,
    "wiki-validation": 2,
    "goal-match": 3,
    "authority": 3,
    "planning": 2,
    "contradiction-review": 1,
    "synthesis": 2,
    "wiki-review": 2,
    "maintenance": 2,
    "query": 1,
    "orientation": 1,
}
_WORK_FIRST_CATEGORY_ORDER = {
    "work-thread": 0,
    "git-context": 1,
    "authority": 2,
    "planning": 3,
    "goal-match": 4,
    "source-freshness": 5,
    "queue": 6,
    "wiki-validation": 7,
    "contradiction-review": 8,
    "synthesis": 9,
    "wiki-review": 10,
    "maintenance": 11,
    "query": 12,
    "orientation": 13,
}
_MAINTENANCE_FIRST_CATEGORY_ORDER = {
    "source-freshness": 0,
    "queue": 1,
    "wiki-validation": 2,
    "maintenance": 3,
    "synthesis": 4,
    "wiki-review": 5,
    "contradiction-review": 6,
    "work-thread": 7,
    "git-context": 8,
    "authority": 9,
    "planning": 10,
    "goal-match": 11,
    "query": 12,
    "orientation": 13,
}
_MAINTENANCE_CATEGORIES = {
    "source-freshness",
    "queue",
    "wiki-validation",
    "contradiction-review",
    "synthesis",
    "wiki-review",
    "maintenance",
    "query",
}
_SUGGESTION_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_AUTHORITY_LIMIT = 8
_AUTHORITY_SOURCE_SCORE = {
    "configured-authority": 18,
    "wiki-authority": 16,
    "planning-decision": 14,
    "inferred-authority": 0,
}
_AUTHORITY_ORIGIN_ORDER = {
    "configured-authority": 0,
    "wiki-authority": 0,
    "planning-decision": 0,
    "inferred-authority": 1,
}
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
_AUTHORITY_FRESHNESS_ORDER = {"current": 0, "watch": 1, "stale": 2, "historical": 3}
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
_CONTRADICTION_GOAL_TOKENS = {
    "conflict",
    "conflicts",
    "conflicting",
    "contradiction",
    "contradictions",
    "contradicting",
    "contested",
}
_MAINTENANCE_GOAL_TOKENS = {
    "source",
    "sources",
    "queue",
    "ingest",
    "lint",
    "health",
    "refresh",
    "wiki",
    "review",
    "splendor",
    "maintenance",
    "synthesis",
    "freshness",
}
_MAINTENANCE_GOAL_FILLER_TOKENS = {
    "a",
    "about",
    "after",
    "all",
    "an",
    "and",
    "at",
    "can",
    "check",
    "could",
    "do",
    "for",
    "get",
    "give",
    "go",
    "in",
    "into",
    "is",
    "look",
    "me",
    "my",
    "now",
    "of",
    "on",
    "our",
    "please",
    "run",
    "show",
    "state",
    "status",
    "tell",
    "that",
    "the",
    "this",
    "to",
    "up",
    "what",
    "with",
    "would",
    "you",
}
_INFERRED_CONTEXT_FILLER_TOKENS = _MAINTENANCE_GOAL_FILLER_TOKENS | {
    "agent",
    "critical",
    "current",
    "doc",
    "docs",
    "file",
    "implementation",
    "next",
    "path",
    "plan",
    "planning",
    "project",
    "read",
    "repo",
    "roadmap",
    "step",
    "test",
    "tests",
}


@dataclass(frozen=True)
class BriefMatch:
    rank: int
    score: int
    relevance_score: int
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
    relevance_score: int = 0


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
    origin: str
    curation_state: str
    curation_commands: list[str]
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
    url: str | None = None
    source_id: str | None = None
    source_ref: str | None = None
    record_id: str | None = None
    relevance_score: int = 0


@dataclass(frozen=True)
class MaintenanceCommand:
    category: str
    command: str
    reason: str
    path: str | None = None
    source_id: str | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class GitCommitBrief:
    sha: str
    short_sha: str
    subject: str
    body: str
    paths: list[str]
    relevance_score: int


@dataclass(frozen=True)
class GitThreadBrief:
    kind: str
    number: int
    title: str
    url: str
    state: str
    summary: str
    relevance_score: int
    promoted: bool


@dataclass(frozen=True)
class GitContext:
    enabled: bool
    available: bool
    since: str | None
    base_ref: str | None
    merge_base: str | None
    branch: str | None
    head: str | None
    repository: str | None
    commits: list[GitCommitBrief]
    threads: list[GitThreadBrief]
    read_first_paths: list[str]
    warnings: list[str]


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
    git_context: GitContext
    work_actions: list[SuggestedAction]
    maintenance_actions: list[SuggestedAction]
    maintenance_commands: list[MaintenanceCommand]
    maintenance_notes: list[str]
    provisional_context: list[AuthorityBrief]


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
    generated_review_task_count: int
    git_context: GitContext
    maintenance_goal: bool


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
    work_actions: list[SuggestedAction]
    maintenance_actions: list[SuggestedAction]
    maintenance_commands: list[MaintenanceCommand]
    maintenance_notes: list[str]
    provisional_context: list[AuthorityBrief]
    git_context: GitContext
    next_actions: list[str]


def build_project_brief(
    root: Path, goal: str | None, *, include_git: bool = True, since: str | None = None
) -> ProjectBrief:
    snapshot = _collect_brief_state(root, goal, include_git=include_git, since=since)
    suggested_actions = _ranked_suggestions(snapshot)
    work_actions, maintenance_actions = _split_actions(suggested_actions)
    maintenance_commands, maintenance_notes = _maintenance_guidance(snapshot, maintenance_actions)
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
        work_actions=work_actions,
        maintenance_actions=maintenance_actions,
        maintenance_commands=maintenance_commands,
        maintenance_notes=maintenance_notes,
        provisional_context=_provisional_authority_briefs(snapshot.authority_briefs),
        git_context=snapshot.git_context,
        next_actions=next_actions,
    )


def build_suggest_next(
    root: Path, goal: str | None = None, *, include_git: bool = True, since: str | None = None
) -> SuggestNextResult:
    snapshot = _collect_brief_state(root, goal, include_git=include_git, since=since)
    actions = _ranked_suggestions(snapshot)
    work_actions, maintenance_actions = _split_actions(actions)
    maintenance_commands, maintenance_notes = _maintenance_guidance(snapshot, maintenance_actions)
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
        git_context=snapshot.git_context,
        work_actions=work_actions,
        maintenance_actions=maintenance_actions,
        maintenance_commands=maintenance_commands,
        maintenance_notes=maintenance_notes,
        provisional_context=_provisional_authority_briefs(snapshot.authority_briefs),
    )


def _collect_brief_state(
    root: Path, goal: str | None, *, include_git: bool, since: str | None
) -> BriefStateSnapshot:
    config = load_config(root)
    layout = resolve_layout(root, config)
    status = build_wiki_status(root)
    queue = inspect_queue(root)
    freshness = scan_source_freshness(root)
    normalized_goal = goal.strip() if goal is not None else ""
    goal_tokens = _tokens(normalized_goal)
    goal_phrase = _normalize_goal_phrase(normalized_goal)
    maintenance_goal = _is_maintenance_goal(goal_tokens)
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
            brief_matches = [
                _brief_match(match)
                for match in query_result.matches
                if not _is_generated_review_task_match(match)
            ]
            matches = _rank_brief_matches(
                brief_matches,
                goal_tokens,
                goal_phrase,
            )[:_BRIEF_MATCH_LIMIT]

    planning_items, warnings, generated_review_task_count = _active_planning_items(
        root, layout, normalized_goal or None, goal_phrase
    )
    if query_warning is not None:
        warnings.insert(0, query_warning)
    sources = load_sources(layout)
    sources_by_id = {source.source_id: source for source in sources}
    wiki_pages, invalid_wiki_pages = load_wiki_pages(root, layout)
    authority_briefs, authority_warnings = _authority_briefs(
        root, layout, config, wiki_pages, sources, normalized_goal or None
    )
    warnings.extend(authority_warnings)
    recent_sources = _recent_sources(sources)
    recent_runs = status.recent_runs
    latest_reports = _latest_reports(root, layout)
    last_query = _last_query(layout)
    git_context = _build_git_context(
        root, normalized_goal or None, include_git=include_git, since=since
    )
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
        generated_review_task_count=generated_review_task_count,
        git_context=git_context,
        maintenance_goal=maintenance_goal,
    )


def _brief_match(match: QueryMatch) -> BriefMatch:
    return BriefMatch(
        rank=match.rank,
        score=match.score,
        relevance_score=0,
        document_class=match.document_class,
        kind=match.kind,
        record_id=match.record_id,
        title=match.title,
        path=match.path,
        review_state=match.review_state,
        source_refs=match.source_refs,
        snippet=match.snippet,
    )


def _is_generated_review_task_match(match: QueryMatch) -> bool:
    return (
        match.document_class == "planning"
        and match.kind == "task"
        and match.record_origin == "generated"
        and match.generated_kind == "contradiction-review"
    )


def _rank_brief_matches(
    matches: list[BriefMatch], goal_tokens: set[str], goal_phrase: str
) -> list[BriefMatch]:
    ranked: list[tuple[int, BriefMatch]] = []
    for sequence, match in enumerate(matches):
        lifecycle_bonus = 0
        if match.kind == "source-summary":
            lifecycle_bonus -= 8
        if match.review_state in {"human-reviewed"}:
            lifecycle_bonus += 12
        elif match.review_state in {"contested", "stale"}:
            lifecycle_bonus += 6
        elif match.review_state in {"machine-generated", "draft"}:
            lifecycle_bonus -= 4
        relevance_score = (
            _goal_relevance_score(
                goal_tokens,
                goal_phrase=goal_phrase,
                high_text=" ".join([match.title, match.path, match.record_id]),
                medium_text=" ".join(
                    [
                        match.document_class,
                        match.kind,
                        match.review_state or "",
                        " ".join(match.source_refs),
                    ]
                ),
                low_text=match.snippet,
            )
            + lifecycle_bonus
            + match.score
        )
        ranked.append((sequence, replace(match, relevance_score=relevance_score)))
    ranked.sort(
        key=lambda item: (
            -item[1].relevance_score,
            item[1].rank,
            item[1].title.lower(),
            item[1].path,
            item[0],
        )
    )
    return [replace(match, rank=rank) for rank, (_sequence, match) in enumerate(ranked, start=1)]


def _brief_error(exc: Exception) -> str:
    return " ".join(str(exc).splitlines()).strip() or exc.__class__.__name__


def _active_planning_items(
    root: Path, layout, goal: str | None, goal_phrase: str
) -> tuple[list[BriefPlanningItem], list[BriefWarning], int]:
    items: list[BriefPlanningItem] = []
    warnings: list[BriefWarning] = []
    generated_review_task_count = 0
    goal_tokens = _tokens(goal or "")
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
            if kind == "task" and is_generated_contradiction_review_task(record):
                if record.review_task_state == "active":
                    generated_review_task_count += 1
                continue
            status = record.status
            if status not in statuses:
                continue
            payload = record.model_dump(mode="json")
            record_id = str(getattr(record, id_field))
            refs: list[str] = []
            for key, value in payload.items():
                if key.endswith("_refs") or key in {"supersedes", "superseded_by", "depends_on"}:
                    refs.extend(_flatten_handoff_values(value))
            relevance_score = _goal_relevance_score(
                goal_tokens,
                goal_phrase=goal_phrase,
                high_text=" ".join([record.title, record_id, path.relative_to(root).as_posix()]),
                medium_text=" ".join([kind, status, *refs]),
                low_text=parsed.body,
            )
            items.append(
                BriefPlanningItem(
                    kind=kind,
                    record_id=record_id,
                    title=record.title,
                    status=status,
                    path=path.relative_to(root).as_posix(),
                    relevance_score=relevance_score,
                )
            )
    if goal_tokens:
        items.sort(
            key=lambda item: (
                -item.relevance_score,
                item.kind,
                item.status,
                item.record_id,
            )
        )
    else:
        items.sort(key=lambda item: (item.kind, item.status, item.record_id))
    return items[:_BRIEF_PLANNING_LIMIT], warnings, generated_review_task_count


def _authority_briefs(
    root: Path,
    layout,
    config,
    pages: list[WikiPageSnapshot],
    sources: list[SourceRecord],
    goal: str | None,
):
    items: list[AuthorityBrief] = []
    warnings: list[BriefWarning] = []
    goal_tokens = _tokens(goal or "")
    goal_phrase = _normalize_goal_phrase(goal or "")

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
            origin="configured-authority",
            goal_tokens=goal_tokens,
            goal_phrase=goal_phrase,
            high_text=" ".join([title, path.as_posix(), " ".join(doc.applies_to)]),
            medium_text=" ".join(
                [*doc.issue_refs, *doc.pr_refs, *doc.supersedes, doc.superseded_by or ""]
            ),
            low_text=" ".join([reason, body]),
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
                origin="configured-authority",
                curation_state="configured",
                curation_commands=[],
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
            origin="wiki-authority",
            goal_tokens=goal_tokens,
            goal_phrase=goal_phrase,
            high_text=" ".join(
                [
                    page.frontmatter.title,
                    page.frontmatter.page_id,
                    page.path,
                    " ".join(page.frontmatter.authority_scope),
                ]
            ),
            medium_text=" ".join(
                [
                    " ".join(page.frontmatter.tags),
                    " ".join(page.frontmatter.source_refs),
                    " ".join(page.frontmatter.issue_refs),
                    " ".join(page.frontmatter.pr_refs),
                    " ".join(page.frontmatter.supersedes),
                    page.frontmatter.superseded_by or "",
                ]
            ),
            low_text=" ".join(
                [
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
                origin="wiki-authority",
                curation_state="curated",
                curation_commands=[],
                issue_refs=page.frontmatter.issue_refs,
                pr_refs=page.frontmatter.pr_refs,
                supersedes=page.frontmatter.supersedes,
                superseded_by=page.frontmatter.superseded_by,
            )
        )

    items.extend(_decision_authority_briefs(root, layout, goal_tokens, goal_phrase))
    items.extend(_inferred_authority_briefs(root, config, sources, goal_tokens, goal_phrase, items))
    ranked = sorted(
        enumerate(items),
        key=lambda item: (
            _AUTHORITY_LIFECYCLE_TIER.get(item[1].lifecycle, 99),
            _AUTHORITY_FRESHNESS_ORDER.get(item[1].freshness, 99),
            _AUTHORITY_ORIGIN_ORDER.get(item[1].origin, 99),
            -item[1].score,
            _AUTHORITY_ROLE_ORDER.get(item[1].role, 99),
            _AUTHORITY_LIFECYCLE_ORDER.get(item[1].lifecycle, 99),
            item[0],
            item[1].path,
        ),
    )
    return [
        replace(item, rank=rank)
        for rank, (_sequence, item) in enumerate(ranked[:_AUTHORITY_LIMIT], start=1)
    ], warnings


def _authority_score(
    *,
    role: str,
    freshness: str,
    lifecycle: str,
    origin: str,
    goal_tokens: set[str],
    goal_phrase: str = "",
    high_text: str = "",
    medium_text: str = "",
    low_text: str = "",
    text: str = "",
) -> int:
    score = (
        _AUTHORITY_ROLE_SCORE.get(role, 0)
        + _AUTHORITY_FRESHNESS_SCORE.get(freshness, 0)
        + _AUTHORITY_LIFECYCLE_SCORE.get(lifecycle, 0)
        + _AUTHORITY_SOURCE_SCORE.get(origin, 0)
    )
    score += _goal_relevance_score(
        goal_tokens,
        goal_phrase=goal_phrase,
        high_text=high_text,
        medium_text=medium_text,
        low_text=" ".join([low_text, text]),
    )
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


def _decision_authority_briefs(
    root: Path, layout, goal_tokens: set[str], goal_phrase: str
) -> list[AuthorityBrief]:
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
                    origin="planning-decision",
                    goal_tokens=goal_tokens,
                    goal_phrase=goal_phrase,
                    high_text=" ".join([record.title, record.decision_id, path.name]),
                    medium_text=" ".join(
                        [
                            record.status,
                            record.decided_at or "",
                            " ".join(record.source_refs),
                            " ".join(record.related_tasks),
                            " ".join(record.related_questions),
                            " ".join(record.issue_refs),
                            " ".join(record.pr_refs),
                            " ".join(record.supersedes),
                            record.superseded_by or "",
                        ]
                    ),
                    low_text=text,
                ),
                reason=reason,
                origin="planning-decision",
                curation_state="planning-record",
                curation_commands=[],
                issue_refs=record.issue_refs,
                pr_refs=record.pr_refs,
                supersedes=record.supersedes,
                superseded_by=record.superseded_by,
            )
        )
    return items


def _inferred_authority_briefs(
    root: Path,
    config,
    sources: list[SourceRecord],
    goal_tokens: set[str],
    goal_phrase: str,
    existing_items: list[AuthorityBrief],
) -> list[AuthorityBrief]:
    configured_paths = {doc.path for doc in config.briefing.authority_documents}
    existing_paths = {item.path for item in existing_items}
    excluded_paths = configured_paths | existing_paths
    fallback_context_tokens = _inferred_root_context_tokens(root)
    candidates: list[AuthorityBrief] = []
    for path in _inferred_authority_candidate_paths(root):
        if path.as_posix() in excluded_paths:
            continue
        absolute = root / path
        try:
            body = absolute.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        path_text = path.as_posix()
        title = _title_from_markdown(body) or _inferred_authority_title(path)
        role = _inferred_authority_role(path)
        freshness = "current"
        lifecycle = "current"
        reason = _inferred_authority_reason(path)
        gating_tokens = goal_tokens | fallback_context_tokens
        relevance_score = _goal_relevance_score(
            gating_tokens,
            goal_phrase=goal_phrase,
            high_text=" ".join([title, path_text]),
            low_text=body,
        )
        if _inferred_authority_requires_goal_match(path) and relevance_score <= 0:
            continue
        curated_source = _curated_source_for_path(sources, path_text)
        if curated_source is None:
            curation_state = "provisional-uncurated"
            curation_commands = [
                f"splendor add-source {shlex.quote(path_text)}",
                f"splendor ingest {shlex.quote(path_text)}",
            ]
            reason = (
                f"{reason} Detected by filename/path heuristic; provisional until curated as a "
                "source."
            )
        else:
            curation_state = "curated"
            curation_commands = []
            reason = f"{reason} Detected by filename/path heuristic over a curated source."
        candidates.append(
            AuthorityBrief(
                rank=0,
                path=path_text,
                title=title,
                role=role,
                freshness=freshness,
                lifecycle=lifecycle,
                score=_authority_score(
                    role=role,
                    freshness=freshness,
                    lifecycle=lifecycle,
                    origin="inferred-authority",
                    goal_tokens=goal_tokens,
                    goal_phrase=goal_phrase,
                    high_text=" ".join([title, path_text]),
                    medium_text=reason,
                    low_text=body,
                ),
                reason=reason,
                origin="inferred-authority",
                curation_state=curation_state,
                curation_commands=curation_commands,
                issue_refs=[],
                pr_refs=[],
                supersedes=[],
                superseded_by=None,
            )
        )
    return candidates


def _inferred_authority_candidate_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for name in (".agent-plan.md", "AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md"):
        path = root / name
        if path.is_file():
            candidates.append(Path(name))
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        for path in sorted(docs_dir.rglob("*.md")):
            relative = path.relative_to(root)
            if _is_inferred_docs_authority_path(relative):
                candidates.append(relative)
    tests_dir = root / "tests"
    if tests_dir.is_dir():
        for path in sorted(tests_dir.rglob("test_planning*.py")):
            candidates.append(path.relative_to(root))
    return sorted(dict.fromkeys(candidates), key=lambda item: item.as_posix())


def _inferred_root_context_tokens(root: Path) -> set[str]:
    tokens: set[str] = set()
    for name in (".agent-plan.md", "README.md", "CONTRIBUTING.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tokens.update(_tokens(body) - _INFERRED_CONTEXT_FILLER_TOKENS)
    return tokens


def _inferred_authority_requires_goal_match(path: Path) -> bool:
    return path.as_posix() not in {
        ".agent-plan.md",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "CONTRIBUTING.md",
    }


def _is_inferred_docs_authority_path(path: Path) -> bool:
    name = path.name.lower()
    return any(
        marker in name
        for marker in (
            "roadmap",
            "plan",
            "planning",
            "policy",
            "policies",
            "guideline",
            "guidelines",
        )
    )


def _inferred_authority_role(path: Path) -> str:
    path_text = path.as_posix().lower()
    name = path.name.lower()
    if path_text == ".agent-plan.md" or "roadmap" in name or "plan" in name:
        return "roadmap"
    if path_text in {"agents.md", "claude.md", "readme.md"} or "policy" in name:
        return "current-authority"
    return "reference"


def _inferred_authority_reason(path: Path) -> str:
    path_text = path.as_posix()
    name = path.name.lower()
    if path_text == ".agent-plan.md":
        return "Inferred current planning state from the conventional agent-plan file."
    if path_text in {"AGENTS.md", "CLAUDE.md"}:
        return "Inferred agent policy authority from a conventional repo-root policy file."
    if path_text == "README.md":
        return "Inferred project orientation authority from the repo README."
    if path_text == "CONTRIBUTING.md":
        return "Inferred contributor workflow context from the repo contributing guide."
    if "roadmap" in name or "plan" in name:
        return "Inferred roadmap or planning authority from a conventional docs path."
    if "policy" in name or "guideline" in name:
        return "Inferred policy context from a conventional docs path."
    return "Inferred planning regression context from a conventional tests path."


def _inferred_authority_title(path: Path) -> str:
    if path.as_posix() == ".agent-plan.md":
        return "Agent Plan"
    return path.stem.replace("_", " ").replace("-", " ").title()


def _curated_source_for_path(sources: list[SourceRecord], path: str) -> SourceRecord | None:
    for source in sources:
        if source.superseded_by is not None:
            continue
        identities = {
            source.path,
            canonical_source_ref(source),
            source.original_path or "",
            source.source_ref or "",
            *source.aliases,
        }
        if path in identities:
            return source
    return None


def _provisional_authority_briefs(items: list[AuthorityBrief]) -> list[AuthorityBrief]:
    return [item for item in items if item.curation_state == "provisional-uncurated"]


def _curated_authority_briefs(items: list[AuthorityBrief]) -> list[AuthorityBrief]:
    return [item for item in items if item.curation_state != "provisional-uncurated"]


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
    tokens: set[str] = set()
    for token in _TOKEN_PATTERN.findall(text.lower()):
        tokens.add(token)
        tokens.update(part for part in re.split(r"[-_]+", token) if len(part) > 1)
    return tokens


def _is_maintenance_goal(goal_tokens: set[str]) -> bool:
    meaningful_tokens = goal_tokens - _MAINTENANCE_GOAL_FILLER_TOKENS
    if not meaningful_tokens:
        return False
    maintenance_matches = meaningful_tokens & _MAINTENANCE_GOAL_TOKENS
    if not maintenance_matches:
        return False
    non_maintenance_tokens = meaningful_tokens - _MAINTENANCE_GOAL_TOKENS
    if not non_maintenance_tokens:
        return True
    return len(maintenance_matches) >= 2 and len(maintenance_matches) >= len(non_maintenance_tokens)


def _flatten_handoff_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _normalize_goal_phrase(text: str) -> str:
    lowered = text.lower().replace("-", " ").replace("_", " ")
    return " ".join(_TOKEN_PATTERN.findall(lowered))


def _goal_relevance_score(
    goal_tokens: set[str],
    *,
    goal_phrase: str = "",
    high_text: str = "",
    medium_text: str = "",
    low_text: str = "",
) -> int:
    if not goal_tokens:
        return 0
    score = 0
    for text, weight in ((high_text, 18), (medium_text, 10), (low_text, 4)):
        if not text:
            continue
        text_tokens = _tokens(text)
        overlap = goal_tokens & text_tokens
        if not overlap:
            continue
        score += min(len(overlap), 8) * weight
        if len(overlap) >= 2:
            score += len(overlap) * 5
        if overlap == goal_tokens:
            score += weight
        normalized_text = _normalize_goal_phrase(text)
        if len(goal_tokens) >= 2 and goal_phrase and goal_phrase in normalized_text:
            score += weight * 3
    return score


def _build_git_context(
    root: Path, goal: str | None, *, include_git: bool, since: str | None
) -> GitContext:
    if not include_git:
        return GitContext(
            enabled=False,
            available=False,
            since=since,
            base_ref=None,
            merge_base=None,
            branch=None,
            head=None,
            repository=None,
            commits=[],
            threads=[],
            read_first_paths=[],
            warnings=[],
        )

    warnings: list[str] = []
    inside = _git_output(root, ["rev-parse", "--is-inside-work-tree"], required=False)
    if inside != "true":
        return GitContext(
            enabled=True,
            available=False,
            since=since,
            base_ref=None,
            merge_base=None,
            branch=None,
            head=None,
            repository=None,
            commits=[],
            threads=[],
            read_first_paths=[],
            warnings=["Not inside a git worktree."],
        )

    branch = _git_output(root, ["rev-parse", "--abbrev-ref", "HEAD"], required=False)
    head = _git_output(root, ["rev-parse", "--short", "HEAD"], required=False)
    base_ref = since or _default_main_ref(root)
    merge_base = _merge_base_for_context(root, base_ref) if base_ref else None
    if since is not None and merge_base is None:
        warnings.append(f"Git base ref could not be resolved: {since}")
    commits = _git_commits(
        root,
        goal,
        base_ref=base_ref,
        merge_base=merge_base,
        explicit_since=since is not None,
    )
    repository = _github_repository(root)
    threads: list[GitThreadBrief] = []
    if repository is not None:
        loaded_threads, thread_warnings = _github_threads(root, repository, goal)
        threads = loaded_threads
        warnings.extend(thread_warnings)
    else:
        warnings.append("GitHub remote repository could not be inferred from origin.")
    read_first_paths = _read_first_paths(commits, threads, goal)
    return GitContext(
        enabled=True,
        available=True,
        since=since,
        base_ref=base_ref,
        merge_base=merge_base,
        branch=branch,
        head=head,
        repository=repository,
        commits=commits,
        threads=threads,
        read_first_paths=read_first_paths,
        warnings=warnings,
    )


def _git_output(root: Path, args: list[str], *, required: bool = True) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if required:
            message = result.stderr.strip() or result.stdout.strip() or "git command failed"
            raise ValueError(message)
        return None
    return result.stdout.strip()


def _default_main_ref(root: Path) -> str | None:
    for ref in ("origin/main", "main"):
        if _git_output(root, ["rev-parse", "--verify", f"{ref}^{{commit}}"], required=False):
            return ref
    return None


def _merge_base_for_context(root: Path, base_ref: str | None) -> str | None:
    if base_ref is None:
        return None
    return _git_output(root, ["merge-base", base_ref, "HEAD"], required=False)


def _git_commits(
    root: Path,
    goal: str | None,
    *,
    base_ref: str | None,
    merge_base: str | None,
    explicit_since: bool,
) -> list[GitCommitBrief]:
    range_ref = None
    if base_ref is not None and merge_base is not None:
        range_ref = f"{merge_base}..HEAD"
    args = ["log", "--first-parent", f"--max-count={_GIT_CONTEXT_LIMIT * 4}"]
    if range_ref is not None:
        args.append(range_ref)
    args.append("--pretty=format:%H%x1f%h%x1f%s%x1e")
    output = _git_output(root, args, required=False)
    if not output and range_ref is not None and not explicit_since:
        output = _git_output(
            root,
            [
                "log",
                "--first-parent",
                f"--max-count={_GIT_CONTEXT_LIMIT * 4}",
                "--pretty=format:%H%x1f%h%x1f%s%x1e",
            ],
            required=False,
        )
    goal_tokens = _tokens(goal or "")
    goal_phrase = _normalize_goal_phrase(goal or "")
    commits: list[GitCommitBrief] = []
    for entry in (output or "").split("\x1e"):
        stripped_entry = entry.strip()
        if not stripped_entry:
            continue
        header = stripped_entry.split("\x1f")
        if len(header) < 3:
            continue
        sha, short_sha, subject = header[:3]
        body = _git_output(root, ["log", "-1", "--pretty=format:%B", sha], required=False) or ""
        path_output = (
            _git_output(
                root, ["show", "--pretty=format:", "--name-only", sha, "--"], required=False
            )
            or ""
        )
        paths = sorted(
            dict.fromkeys(line.strip() for line in path_output.splitlines() if line.strip())
        )
        relevance_score = _goal_relevance_score(
            goal_tokens,
            goal_phrase=goal_phrase,
            high_text=" ".join([subject, " ".join(paths)]),
            medium_text=body,
        )
        commits.append(
            GitCommitBrief(
                sha=sha,
                short_sha=short_sha,
                subject=subject.strip(),
                body=body.strip(),
                paths=paths,
                relevance_score=relevance_score,
            )
        )
    if goal_tokens:
        commits.sort(key=lambda item: (-item.relevance_score, item.short_sha))
    return commits[:_GIT_CONTEXT_LIMIT]


def _github_repository(root: Path) -> str | None:
    remote = _git_output(root, ["config", "--get", "remote.origin.url"], required=False)
    if remote is None:
        return None
    remote = remote.strip()
    patterns = (
        r"github\.com[:/](?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?$",
        r"^https://github\.com/(?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.search(pattern, remote)
        if match:
            return match.group("repo")
    return None


def _github_threads(
    root: Path, repository: str, goal: str | None
) -> tuple[list[GitThreadBrief], list[str]]:
    warnings: list[str] = []
    raw_threads: list[dict[str, object]] = []
    commands = [
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--limit",
            "30",
            "--json",
            "number,title,url,body,state,labels",
        ],
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--limit",
            "30",
            "--json",
            "number,title,url,body,state,isDraft,mergedAt,labels",
        ],
    ]
    kinds = ["issue", "pr"]
    for kind, command in zip(kinds, commands, strict=True):
        try:
            result = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            warnings.append(
                f"Timed out after {_GIT_COMMAND_TIMEOUT_SECONDS}s running gh {kind} list."
            )
            continue
        except OSError as exc:
            warnings.append(f"Could not run gh {kind} list: {exc}")
            continue
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"gh {kind} list failed"
            warnings.append(message)
            continue
        try:
            payload = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            warnings.append(f"Could not parse gh {kind} output: {exc}")
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    raw_threads.append({"kind": kind, **item})

    goal_tokens = _tokens(goal or "")
    goal_phrase = _normalize_goal_phrase(goal or "")
    threads: list[GitThreadBrief] = []
    for item in raw_threads:
        title = str(item.get("title") or "")
        body = str(item.get("body") or "")
        url = str(item.get("url") or "")
        number = item.get("number")
        if not isinstance(number, int) or not title or not url:
            continue
        state = str(item.get("state") or "unknown").lower()
        kind = str(item.get("kind") or "thread")
        relevance_score = _goal_relevance_score(
            goal_tokens,
            goal_phrase=goal_phrase,
            high_text=title,
            medium_text=body,
        )
        summary = _one_line(body) or title
        promoted = _promote_git_thread(
            goal_tokens=goal_tokens,
            relevance_score=relevance_score,
            kind=kind,
            text=" ".join([title, body]),
        )
        threads.append(
            GitThreadBrief(
                kind=kind,
                number=number,
                title=title,
                url=url,
                state=state,
                summary=summary,
                relevance_score=relevance_score,
                promoted=promoted,
            )
        )
    if goal_tokens:
        threads.sort(
            key=lambda item: (
                item.state != "open",
                -item.relevance_score,
                item.kind != "issue",
                item.number,
            )
        )
    else:
        threads.sort(key=lambda item: (item.state != "open", item.kind != "issue", item.number))
    return threads[:_GIT_CONTEXT_LIMIT], warnings


def _promote_git_thread(
    *, goal_tokens: set[str], relevance_score: int, kind: str, text: str
) -> bool:
    if not goal_tokens:
        return True
    if relevance_score >= _PROMOTED_THREAD_RELEVANCE_FLOOR:
        return True
    if kind == "pr":
        code_tokens = {
            token for token in goal_tokens if any(character.isdigit() for character in token)
        }
        return bool(code_tokens & _tokens(text))
    return False


def _one_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip(" #\t")
        if stripped:
            return stripped[:160]
    return ""


def _read_first_paths(
    commits: list[GitCommitBrief], threads: list[GitThreadBrief], goal: str | None
) -> list[str]:
    goal_tokens = _tokens(goal or "")
    goal_phrase = _normalize_goal_phrase(goal or "")
    scored: dict[str, int] = {}
    for commit in commits:
        for path in commit.paths:
            scored[path] = max(
                scored.get(path, 0),
                commit.relevance_score
                + _goal_relevance_score(
                    goal_tokens,
                    goal_phrase=goal_phrase,
                    high_text=path,
                    low_text=commit.subject,
                ),
            )
    for thread in threads:
        if not thread.promoted:
            continue
        for path in _repo_paths_in_text(" ".join([thread.title, thread.summary])):
            scored[path] = max(scored.get(path, 0), thread.relevance_score + 20)
    ranked = sorted(scored, key=lambda path: (-scored[path], path))
    return ranked[:_GIT_FILE_LIMIT]


def _repo_paths_in_text(text: str) -> list[str]:
    candidates = re.findall(r"(?<![\w/.-])(?:[\w.-]+/)+[\w.-]+(?:\.[A-Za-z0-9]+)?", text)
    return sorted(dict.fromkeys(candidate.strip("`.,)") for candidate in candidates))


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


def _maintenance_guidance(
    snapshot: BriefStateSnapshot, maintenance_actions: list[SuggestedAction]
) -> tuple[list[MaintenanceCommand], list[str]]:
    commands: list[MaintenanceCommand] = []
    notes: list[str] = []

    def add(
        category: str,
        command: str,
        reason: str,
        *,
        path: str | None = None,
        source_id: str | None = None,
        source_ref: str | None = None,
    ) -> None:
        candidate = MaintenanceCommand(
            category=category,
            command=command,
            reason=reason,
            path=path,
            source_id=source_id,
            source_ref=source_ref,
        )
        if all(existing.command != command for existing in commands):
            commands.append(candidate)

    if snapshot.status.review_needed_pages or snapshot.status.sources_missing_synthesis:
        add(
            "wiki-status",
            "splendor wiki status",
            "Review generated wiki maintenance counts before turning them into human work.",
        )
        notes.append(
            "Wiki review-needed pages and missing synthesis are maintenance state, not default "
            "active human tasks."
        )

    if (
        snapshot.git_context.enabled
        and snapshot.git_context.available
        and snapshot.git_context.base_ref is not None
        and snapshot.git_context.merge_base is not None
        and _has_pr_summary_reviewable_state(snapshot.root, snapshot.git_context.base_ref)
    ):
        add(
            "pr-summary",
            f"splendor pr-summary --since {snapshot.git_context.base_ref}",
            "Review compact committed Splendor state changes before PR handoff.",
        )

    if snapshot.freshness.changed or snapshot.freshness.missing:
        add(
            "source-freshness",
            "splendor source freshness",
            "Inspect the full changed or missing curated source set.",
        )
    queue_cleanup_states = {item.cleanup_state for item in snapshot.queue.items}
    if "orphaned" in queue_cleanup_states:
        add(
            "queue",
            "splendor queue clean --orphaned",
            "Preview stale ingest queue records whose source manifests are gone.",
        )
    if "superseded" in queue_cleanup_states:
        add(
            "queue",
            "splendor queue clean --superseded",
            "Preview stale ingest queue records for superseded source versions.",
        )
    if any(
        item.operator_state
        in {"pending", "failed_due", "expired_leased", "dead_letter", "failed_backoff"}
        for item in snapshot.queue.items
    ):
        add(
            "queue",
            "splendor queue inspect",
            "Inspect generated ingest queue records and operator states.",
        )

    for action in maintenance_actions:
        if action.command is None:
            continue
        add(
            action.category,
            action.command,
            action.reason,
            path=action.path,
            source_id=action.source_id,
            source_ref=action.source_ref,
        )

    if snapshot.generated_review_task_count:
        notes.append(
            "Default task list hides generated contradiction-review tasks; use "
            "`--generated-review` or `--include-generated-review` when reviewing them."
        )

    return commands, list(dict.fromkeys(notes))


def _has_pr_summary_reviewable_state(root: Path, base_ref: str) -> bool:
    try:
        summary = build_pr_summary(root, since=base_ref)
    except (FileNotFoundError, RuntimeError, ValueError):
        return False
    if summary.changed_path_count == 0:
        return False
    compact_review = summary.compact_review
    if compact_review.review_first or compact_review.usually_mechanical:
        return True
    return any(group.id != "uncategorized_changed_paths" for group in compact_review.attention)


def _ranked_suggestions(snapshot: BriefStateSnapshot) -> list[SuggestedAction]:
    actions: list[SuggestedAction] = []
    goal_tokens = _tokens(snapshot.goal or "")
    goal_phrase = _normalize_goal_phrase(snapshot.goal or "")

    def add(priority: str, category: str, title: str, reason: str, command: str | None, **kwargs):
        relevance_score = kwargs.pop(
            "relevance_score",
            _goal_relevance_score(
                goal_tokens,
                goal_phrase=goal_phrase,
                high_text=" ".join(
                    [
                        title,
                        str(kwargs.get("path") or ""),
                        str(kwargs.get("record_id") or ""),
                        str(kwargs.get("source_ref") or ""),
                    ]
                ),
                medium_text=" ".join(
                    [str(kwargs.get("source_id") or ""), command or "", category, priority]
                ),
                low_text=reason,
            ),
        )
        actions.append(
            SuggestedAction(
                rank=0,
                priority=priority,
                category=category,
                title=title,
                reason=reason,
                command=command,
                relevance_score=relevance_score,
                **kwargs,
            )
        )

    if snapshot.git_context.enabled and snapshot.git_context.available:
        for thread in snapshot.git_context.threads:
            if not thread.promoted:
                continue
            priority = "high" if thread.state == "open" else "medium"
            add(
                priority,
                "work-thread",
                f"Review {thread.kind} #{thread.number}: {thread.title}",
                thread.summary,
                None,
                url=thread.url,
                relevance_score=thread.relevance_score,
            )
        for commit in snapshot.git_context.commits:
            add(
                "medium",
                "git-context",
                f"Review commit {commit.short_sha}: {commit.subject}",
                "Recent git context relevant to the stated goal.",
                None,
                record_id=commit.short_sha,
                relevance_score=commit.relevance_score,
            )
        for path in snapshot.git_context.read_first_paths:
            add(
                "medium",
                "git-context",
                f"Read changed file {path}",
                "Recent git or GitHub context points at this file for the work handoff.",
                None,
                path=path,
                relevance_score=_goal_relevance_score(
                    goal_tokens, goal_phrase=goal_phrase, high_text=path
                ),
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
        if item.cleanup_state == "orphaned":
            add(
                "medium",
                "queue",
                f"Close orphaned queue job {item.job_id}",
                "The ingest queue payload source manifest no longer exists.",
                "splendor queue clean --orphaned",
                path=item.record_path.as_posix(),
                source_id=item.source_id,
                source_ref=source_ref,
            )
        elif item.cleanup_state == "superseded":
            add(
                "medium",
                "queue",
                f"Close superseded queue job {item.job_id}",
                "The ingest queue record belongs to a superseded source version.",
                "splendor queue clean --superseded",
                path=item.record_path.as_posix(),
                source_id=item.source_id,
                source_ref=source_ref,
            )
        elif item.operator_state in {"pending", "failed_due", "expired_leased"}:
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

    for page in _review_page_actions(
        snapshot.wiki_pages,
        snapshot.invalid_wiki_pages,
        goal_tokens=goal_tokens,
        goal_phrase=goal_phrase,
    ):
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
            relevance_score=_goal_relevance_score(
                goal_tokens,
                goal_phrase=goal_phrase,
                high_text=" ".join([source.title, source_ref, source_id]),
                medium_text=" ".join([source.review_state, source.status]),
            ),
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
            relevance_score=match.relevance_score,
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
            else f"Read provisional doc {authority.path}"
            if authority.curation_state == "provisional-uncurated"
            else f"Read authority doc {authority.path}"
        )
        command_note = (
            " Curate with: " + "; ".join(authority.curation_commands)
            if authority.curation_commands
            else ""
        )
        add(
            priority,
            "authority",
            title,
            (
                f"{authority.role}/{authority.freshness}/{authority.lifecycle}/"
                f"{authority.origin}/{authority.curation_state}: {authority.reason}"
                f"{command_note}"
            ),
            None,
            path=authority.path,
            relevance_score=authority.score,
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
            relevance_score=item.relevance_score,
        )

    if snapshot.generated_review_task_count and (
        snapshot.maintenance_goal or goal_tokens & _CONTRADICTION_GOAL_TOKENS
    ):
        add(
            "low",
            "contradiction-review",
            "Inspect generated contradiction-review tasks",
            (
                f"{snapshot.generated_review_task_count} generated contradiction-review task(s) "
                "are available for intentional listing, resolution, or muting."
            ),
            "splendor task list --generated-review --review-task-state active",
            relevance_score=1,
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

    return _finalize_suggestions(actions, maintenance_goal=snapshot.maintenance_goal)


def _first_command(commands: list[str]) -> str | None:
    return commands[0] if commands else None


def _finalize_suggestions(
    actions: list[SuggestedAction], *, maintenance_goal: bool
) -> list[SuggestedAction]:
    by_category: dict[str, int] = {}
    capped: list[tuple[int, SuggestedAction]] = []
    category_order = (
        _MAINTENANCE_FIRST_CATEGORY_ORDER if maintenance_goal else _WORK_FIRST_CATEGORY_ORDER
    )
    ordered = sorted(
        enumerate(actions),
        key=lambda item: (
            category_order.get(item[1].category, 99),
            _SUGGESTION_PRIORITY_ORDER.get(item[1].priority, 99),
            -item[1].relevance_score,
            item[0],
        ),
    )
    for sequence, action in ordered:
        current_count = by_category.get(action.category, 0)
        category_limit = _SUGGESTION_CATEGORY_LIMITS.get(action.category, 1)
        if current_count >= category_limit:
            continue
        by_category[action.category] = current_count + 1
        capped.append((sequence, action))

    capped.sort(
        key=lambda item: (
            category_order.get(item[1].category, 99),
            _SUGGESTION_PRIORITY_ORDER.get(item[1].priority, 99),
            -item[1].relevance_score,
            item[0],
        )
    )
    return [
        replace(action, rank=rank)
        for rank, (_sequence, action) in enumerate(capped[:_SUGGESTION_LIMIT], start=1)
    ]


def _split_actions(
    actions: list[SuggestedAction],
) -> tuple[list[SuggestedAction], list[SuggestedAction]]:
    work_actions = [action for action in actions if action.category not in _MAINTENANCE_CATEGORIES]
    maintenance_actions = [
        action for action in actions if action.category in _MAINTENANCE_CATEGORIES
    ]
    return work_actions, maintenance_actions


def _review_page_actions(
    pages: list[WikiPageSnapshot],
    invalid_pages: list[InvalidWikiPageSnapshot],
    *,
    goal_tokens: set[str],
    goal_phrase: str,
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
                "relevance_score": _goal_relevance_score(
                    goal_tokens,
                    goal_phrase=goal_phrase,
                    high_text=invalid.path,
                    low_text=invalid.error,
                ),
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
                "command": "splendor wiki status",
                "path": page.path,
                "record_id": page.frontmatter.page_id,
                "relevance_score": _goal_relevance_score(
                    goal_tokens,
                    goal_phrase=goal_phrase,
                    high_text=" ".join(
                        [page.frontmatter.title, page.frontmatter.page_id, page.path]
                    ),
                    medium_text=" ".join(
                        [
                            page.frontmatter.kind,
                            state,
                            " ".join(page.frontmatter.tags),
                            " ".join(page.frontmatter.source_refs),
                        ]
                    ),
                    low_text=page.body,
                ),
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
            "work_context": {"actions": [asdict(action) for action in result.work_actions]},
            "maintenance_context": {
                "actions": [asdict(action) for action in result.maintenance_actions],
                "commands": [asdict(command) for command in result.maintenance_commands],
                "notes": result.maintenance_notes,
                "status": {
                    "changed_sources": result.freshness.changed,
                    "missing_sources": result.freshness.missing,
                    "queue": result.queue.total,
                    "review_needed": result.status.review_needed_pages,
                    "contested": result.status.contested_pages,
                    "stale": result.status.stale_pages,
                },
            },
            "git_context": asdict(result.git_context),
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
            "provisional_context": {
                "authority": [asdict(brief) for brief in result.provisional_context]
            },
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
            "provisional_context": {
                "authority": [asdict(item) for item in brief.provisional_context]
            },
            "planning_items": [asdict(item) for item in brief.planning_items],
            "recent_sources": [asdict(source) for source in brief.recent_sources],
            "recent_runs": [asdict(run) for run in brief.recent_runs],
            "latest_reports": [asdict(report) for report in brief.latest_reports],
            "last_query": asdict(brief.last_query) if brief.last_query else None,
            "warnings": [asdict(warning) for warning in brief.warnings],
            "git_context": asdict(brief.git_context),
            "suggested_actions": [asdict(action) for action in brief.suggested_actions],
            "work_context": {"actions": [asdict(action) for action in brief.work_actions]},
            "maintenance_context": {
                "actions": [asdict(action) for action in brief.maintenance_actions],
                "commands": [asdict(command) for command in brief.maintenance_commands],
                "notes": brief.maintenance_notes,
            },
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
            "provisional_context": {
                "authority": [asdict(item) for item in brief.provisional_context]
            },
            "source_refs": _agent_context_source_refs(brief),
            "git_context": asdict(brief.git_context),
            "suggested_actions": [asdict(action) for action in brief.suggested_actions],
            "work_context": {"actions": [asdict(action) for action in brief.work_actions]},
            "maintenance_context": {
                "actions": [asdict(action) for action in brief.maintenance_actions],
                "commands": [asdict(command) for command in brief.maintenance_commands],
                "notes": brief.maintenance_notes,
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
            },
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
