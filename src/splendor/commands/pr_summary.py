"""Read-only PR-oriented generated-state summaries."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from splendor.config import load_config
from splendor.layout import ResolvedLayout, resolve_layout
from splendor.schemas import SourceRecord
from splendor.schemas.maintenance import MaintenanceReport
from splendor.state.source_compat import canonical_source_ref, effective_logical_id
from splendor.state.source_registry import load_source_record
from splendor.utils.git import run_git


@dataclass(frozen=True)
class ChangedPath:
    status: str
    path: str
    old_path: str | None = None


@dataclass(frozen=True)
class SourceChange:
    action: str
    path: str
    source_id: str | None
    title: str | None
    source_ref: str | None
    logical_id: str | None
    supersedes: list[str]
    superseded_by: str | None
    old_path: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PathGroup:
    added: list[str]
    changed: list[str]
    deleted: list[str]
    renamed: list[dict[str, str]]

    @property
    def total(self) -> int:
        return len(self.added) + len(self.changed) + len(self.deleted) + len(self.renamed)


@dataclass(frozen=True)
class MaintenanceStatus:
    command: str
    status: str
    path: str
    scope: str
    warning: str
    created_at: str | None
    checked_count: int | None
    issue_count: int | None
    fatal_error: str | None


@dataclass(frozen=True)
class CompactReviewPath:
    action: str
    path: str
    old_path: str | None = None


@dataclass(frozen=True)
class CompactReviewGroup:
    id: str
    label: str
    review_role: str
    total: int
    paths: list[str]
    path_actions: list[CompactReviewPath]
    action_counts: dict[str, int]
    summary: str


@dataclass(frozen=True)
class CompactReview:
    mode: str
    review_first: list[CompactReviewGroup]
    usually_mechanical: list[CompactReviewGroup]
    attention: list[CompactReviewGroup]


@dataclass(frozen=True)
class PrSummary:
    since: str
    merge_base: str
    head: str | None
    changed_path_count: int
    curated_sources: list[SourceChange]
    source_summary_pages: PathGroup
    maintained_wiki_pages: PathGroup
    generated_state: dict[str, PathGroup]
    other_paths: PathGroup
    maintenance: dict[str, MaintenanceStatus | None]
    compact_review: CompactReview
    reviewer_notes: list[str]


def build_pr_summary(root: Path, *, since: str) -> PrSummary:
    root = root.resolve()
    _assert_git_ref(root, since)
    layout = resolve_layout(root, load_config(root))
    merge_base = _merge_base(root, since=since)
    changes = _changed_paths(root, base_ref=merge_base)
    source_changes = _source_changes(root, base_ref=merge_base, layout=layout, changes=changes)
    source_summary_pages = _group_paths(
        change for change in changes if _is_source_summary_path(change.path, layout)
    )
    maintained_wiki_pages = _group_paths(
        change for change in changes if _is_maintained_wiki_path(change.path, layout)
    )
    generated_state = {
        "queue": _group_paths(
            change for change in changes if _is_layout_child(change.path, layout, layout.queue_dir)
        ),
        "runs": _group_paths(
            change for change in changes if _is_layout_child(change.path, layout, layout.runs_dir)
        ),
        "queries": _group_paths(
            change
            for change in changes
            if _is_layout_child(change.path, layout, layout.queries_dir)
        ),
        "reports": _group_paths(
            change
            for change in changes
            if _is_layout_child(change.path, layout, layout.reports_dir)
        ),
        "derived": _group_paths(
            change
            for change in changes
            if _is_layout_child(change.path, layout, layout.derived_dir)
        ),
    }
    categorized = set()
    for change in changes:
        if _is_categorized_path(change, layout):
            categorized.add(change.path)
    other_paths = _group_paths(change for change in changes if change.path not in categorized)
    maintenance = {
        "lint": _latest_maintenance_status(root, layout=layout, command="lint"),
        "health": _latest_maintenance_status(root, layout=layout, command="health"),
    }
    summary = PrSummary(
        since=since,
        merge_base=merge_base,
        head=_git_text(root, ["rev-parse", "--short", "HEAD"], required=False),
        changed_path_count=len(changes),
        curated_sources=source_changes,
        source_summary_pages=source_summary_pages,
        maintained_wiki_pages=maintained_wiki_pages,
        generated_state=generated_state,
        other_paths=other_paths,
        maintenance=maintenance,
        compact_review=CompactReview(
            mode="compact_committed",
            review_first=[],
            usually_mechanical=[],
            attention=[],
        ),
        reviewer_notes=[],
    )
    compact_review = _compact_review(summary)
    return PrSummary(
        since=summary.since,
        merge_base=summary.merge_base,
        head=summary.head,
        changed_path_count=summary.changed_path_count,
        curated_sources=summary.curated_sources,
        source_summary_pages=summary.source_summary_pages,
        maintained_wiki_pages=summary.maintained_wiki_pages,
        generated_state=summary.generated_state,
        other_paths=summary.other_paths,
        maintenance=summary.maintenance,
        compact_review=compact_review,
        reviewer_notes=_reviewer_notes(summary),
    )


def render_pr_summary_json(summary: PrSummary) -> str:
    return json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n"


def _assert_git_ref(root: Path, ref: str) -> None:
    _git_text(root, ["rev-parse", "--verify", f"{ref}^{{commit}}"])


def _merge_base(root: Path, *, since: str) -> str:
    return _git_text(root, ["merge-base", since, "HEAD"]) or since


def _git_text(root: Path, args: list[str], *, required: bool = True) -> str | None:
    result = run_git(root, args)
    if result.returncode != 0:
        if required:
            message = result.stderr.strip() or result.stdout.strip() or "git command failed"
            raise ValueError(message)
        return None
    return result.stdout.strip()


def _changed_paths(root: Path, *, base_ref: str) -> list[ChangedPath]:
    output = _git_text(root, ["diff", "--name-status", "-M", base_ref, "--"]) or ""
    changes: dict[str, ChangedPath] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) == 3:
            changes[parts[2]] = ChangedPath(status="R", old_path=parts[1], path=parts[2])
        elif len(parts) >= 2:
            changes[parts[1]] = ChangedPath(status=status[0], path=parts[1])

    status_output = _git_text(root, ["status", "--short", "--untracked-files=all"], required=False)
    for line in (status_output or "").splitlines():
        if not line.startswith("?? "):
            continue
        path = line[3:].strip()
        if path and path not in changes:
            changes[path] = ChangedPath(status="A", path=path)
    return sorted(changes.values(), key=lambda change: change.path)


def _source_changes(
    root: Path,
    *,
    base_ref: str,
    layout: ResolvedLayout,
    changes: list[ChangedPath],
) -> list[SourceChange]:
    result: list[SourceChange] = []
    for change in changes:
        if not _is_source_manifest_path(change.path, layout):
            continue
        current, current_error = _load_current_source(root, change.path)
        previous, previous_error = _load_source_at_ref(
            root, base_ref, change.old_path or change.path
        )
        source = current or previous
        error = current_error or previous_error
        if source is None:
            result.append(
                SourceChange(
                    action="invalid",
                    path=change.path,
                    old_path=change.old_path,
                    source_id=Path(change.path).stem,
                    title=None,
                    source_ref=None,
                    logical_id=None,
                    supersedes=[],
                    superseded_by=None,
                    error=error or "source manifest could not be loaded",
                )
            )
            continue
        action = _source_action(change, current=current, previous=previous)
        if error is not None:
            action = "invalid"
        result.append(
            SourceChange(
                action=action,
                path=change.path,
                old_path=change.old_path,
                source_id=source.source_id,
                title=source.title,
                source_ref=canonical_source_ref(source),
                logical_id=effective_logical_id(source),
                supersedes=list(source.supersedes),
                superseded_by=source.superseded_by,
                error=error,
            )
        )
    return result


def _is_source_manifest_path(path: str, layout: ResolvedLayout) -> bool:
    source_dir = layout.source_records_dir.relative_to(layout.root).as_posix()
    return path.startswith(f"{source_dir}/") and path.endswith(".json")


def _load_current_source(root: Path, path: str) -> tuple[SourceRecord | None, str | None]:
    source_path = root / path
    if not source_path.is_file():
        return None, None
    try:
        return load_source_record(source_path), None
    except Exception as exc:
        return None, str(exc)


def _load_source_at_ref(root: Path, ref: str, path: str) -> tuple[SourceRecord | None, str | None]:
    content = _git_text(root, ["show", f"{ref}:{path}"], required=False)
    if content is None:
        return None, None
    try:
        payload = json.loads(content)
        return SourceRecord.model_validate(payload), None
    except Exception as exc:
        return None, str(exc)


def _source_action(
    change: ChangedPath,
    *,
    current: SourceRecord | None,
    previous: SourceRecord | None,
) -> str:
    if change.status == "D":
        return "removed"
    if current is not None and current.supersedes:
        return "refreshed"
    if (
        previous is not None
        and current is not None
        and current.superseded_by != previous.superseded_by
    ):
        return "superseded"
    if change.status == "A":
        return "added"
    if change.status == "R":
        return "renamed"
    return "changed"


def _is_layout_child(path: str, layout: ResolvedLayout, directory: Path) -> bool:
    prefix = directory.relative_to(layout.root).as_posix()
    return path.startswith(f"{prefix}/")


def _is_source_summary_path(path: str, layout: ResolvedLayout) -> bool:
    return _is_layout_child(path, layout, layout.wiki_sources_dir) and path.endswith(".md")


def _is_maintained_wiki_path(path: str, layout: ResolvedLayout) -> bool:
    return (
        _is_layout_child(path, layout, layout.wiki_dir)
        and path.endswith(".md")
        and not _is_source_summary_path(path, layout)
    )


def _is_categorized_path(change: ChangedPath, layout: ResolvedLayout) -> bool:
    return (
        _is_source_manifest_path(change.path, layout)
        or _is_source_summary_path(change.path, layout)
        or _is_maintained_wiki_path(change.path, layout)
        or _is_layout_child(change.path, layout, layout.queue_dir)
        or _is_layout_child(change.path, layout, layout.runs_dir)
        or _is_layout_child(change.path, layout, layout.queries_dir)
        or _is_layout_child(change.path, layout, layout.reports_dir)
        or _is_layout_child(change.path, layout, layout.derived_dir)
    )


def _group_paths(changes: Iterable[ChangedPath]) -> PathGroup:
    added: list[str] = []
    changed: list[str] = []
    deleted: list[str] = []
    renamed: list[dict[str, str]] = []
    for change in changes:
        if change.status == "A":
            added.append(change.path)
        elif change.status == "D":
            deleted.append(change.path)
        elif change.status == "R" and change.old_path is not None:
            renamed.append({"from": change.old_path, "to": change.path})
        else:
            changed.append(change.path)
    return PathGroup(
        added=sorted(added),
        changed=sorted(changed),
        deleted=sorted(deleted),
        renamed=sorted(renamed, key=lambda item: item["to"]),
    )


def _latest_maintenance_status(
    root: Path, *, layout: ResolvedLayout, command: str
) -> MaintenanceStatus | None:
    report_dir = layout.reports_dir / command
    candidates = sorted(report_dir.glob("*.json"))
    if not candidates:
        return None
    latest = candidates[-1]
    warning = "Latest local report only; not tied to the current HEAD or diff."
    try:
        report = MaintenanceReport.model_validate_json(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return MaintenanceStatus(
            command=command,
            status="unreadable",
            path=latest.relative_to(root).as_posix(),
            scope="latest_local_report",
            warning=warning,
            created_at=None,
            checked_count=None,
            issue_count=None,
            fatal_error=str(exc),
        )
    return MaintenanceStatus(
        command=command,
        status=report.status,
        path=latest.relative_to(root).as_posix(),
        scope="latest_local_report",
        warning=warning,
        created_at=report.created_at,
        checked_count=report.checked_count,
        issue_count=report.issue_count,
        fatal_error=report.fatal_error,
    )


def _compact_review(summary: PrSummary) -> CompactReview:
    review_first: list[CompactReviewGroup] = []
    usually_mechanical: list[CompactReviewGroup] = []
    attention: list[CompactReviewGroup] = []

    valid_curated_sources = [
        source for source in summary.curated_sources if source.action != "invalid"
    ]
    if valid_curated_sources:
        review_first.append(
            CompactReviewGroup(
                id="curated_sources",
                label="Curated source manifests",
                review_role="source lifecycle authority",
                total=len(valid_curated_sources),
                paths=sorted(source.path for source in valid_curated_sources),
                path_actions=_source_change_actions(valid_curated_sources),
                action_counts=_action_counts(source.action for source in valid_curated_sources),
                summary=(
                    "Review manifest lifecycle and source identity changes before generated "
                    "wiki or runtime artifacts."
                ),
            )
        )
    if summary.source_summary_pages.total:
        review_first.append(
            _path_group_review(
                "source_summary_pages",
                "Generated source-summary pages",
                "generated knowledge claims",
                summary.source_summary_pages,
                "Review extracted claims and provenance; these pages explain meaningful "
                "generated knowledge changes.",
            )
        )
    if summary.maintained_wiki_pages.total:
        review_first.append(
            _path_group_review(
                "maintained_wiki_pages",
                "Maintained wiki/topic pages",
                "authored synthesis",
                summary.maintained_wiki_pages,
                "Review as authored maintained knowledge, including source_refs migrations.",
            )
        )

    generated_roles = {
        "queue": ("Generated queue records", "mechanical ingest queue evidence"),
        "runs": ("Generated run records", "mechanical ingest run evidence"),
        "queries": ("Generated query snapshots", "mechanical query handoff evidence"),
        "reports": ("Generated report files", "mechanical maintenance report evidence"),
        "derived": ("Derived generated artifacts", "mechanical derived artifact evidence"),
    }
    for key, group in summary.generated_state.items():
        if not group.total:
            continue
        label, role = generated_roles[key]
        usually_mechanical.append(
            _path_group_review(
                f"generated_{key}",
                label,
                role,
                group,
                "Usually review as committed evidence unless a failure or diagnostic changes "
                "the reviewer decision.",
            )
        )

    invalid_sources = [
        source.path for source in summary.curated_sources if source.action == "invalid"
    ]
    if invalid_sources:
        attention.append(
            CompactReviewGroup(
                id="invalid_curated_sources",
                label="Invalid source manifests",
                review_role="blocking source-manifest diagnostics",
                total=len(invalid_sources),
                paths=sorted(invalid_sources),
                path_actions=[
                    CompactReviewPath(action="invalid", path=path)
                    for path in sorted(invalid_sources)
                ],
                action_counts={"invalid": len(invalid_sources)},
                summary="Fix or explain invalid changed source manifests before PR handoff.",
            )
        )
    failed_reports = [
        status.path
        for status in summary.maintenance.values()
        if status is not None and status.status != "passed"
    ]
    if failed_reports:
        attention.append(
            CompactReviewGroup(
                id="non_passing_maintenance_reports",
                label="Non-passing latest maintenance reports",
                review_role="local validation attention",
                total=len(failed_reports),
                paths=sorted(failed_reports),
                path_actions=[
                    CompactReviewPath(action="failed", path=path) for path in sorted(failed_reports)
                ],
                action_counts={"failed": len(failed_reports)},
                summary="Inspect latest local lint/health reports before reviewer handoff.",
            )
        )
    if summary.other_paths.total:
        attention.append(
            _path_group_review(
                "uncategorized_changed_paths",
                "Uncategorized changed paths",
                "ordinary repository changes",
                summary.other_paths,
                "Review as normal code/docs changes outside Splendor generated-state groups.",
            )
        )

    return CompactReview(
        mode="compact_committed",
        review_first=review_first,
        usually_mechanical=usually_mechanical,
        attention=attention,
    )


def _path_group_review(
    group_id: str, label: str, review_role: str, group: PathGroup, summary: str
) -> CompactReviewGroup:
    return CompactReviewGroup(
        id=group_id,
        label=label,
        review_role=review_role,
        total=group.total,
        paths=_path_group_paths(group),
        path_actions=_path_group_actions(group),
        action_counts=_path_group_action_counts(group),
        summary=summary,
    )


def _path_group_paths(group: PathGroup) -> list[str]:
    paths = [*group.added, *group.changed, *group.deleted]
    paths.extend(f"{item['from']} -> {item['to']}" for item in group.renamed)
    return sorted(paths)


def _path_group_actions(group: PathGroup) -> list[CompactReviewPath]:
    actions = [
        *(CompactReviewPath(action="added", path=path) for path in group.added),
        *(CompactReviewPath(action="changed", path=path) for path in group.changed),
        *(CompactReviewPath(action="deleted", path=path) for path in group.deleted),
        *(
            CompactReviewPath(action="renamed", path=item["to"], old_path=item["from"])
            for item in group.renamed
        ),
    ]
    return sorted(actions, key=lambda item: (item.path, item.action, item.old_path or ""))


def _path_group_action_counts(group: PathGroup) -> dict[str, int]:
    return {
        action: count
        for action, count in {
            "added": len(group.added),
            "changed": len(group.changed),
            "deleted": len(group.deleted),
            "renamed": len(group.renamed),
        }.items()
        if count
    }


def _source_change_actions(sources: list[SourceChange]) -> list[CompactReviewPath]:
    actions = [
        CompactReviewPath(action=source.action, path=source.path, old_path=source.old_path)
        for source in sources
    ]
    return sorted(actions, key=lambda item: (item.path, item.action, item.old_path or ""))


def _action_counts(actions: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        counts[action] = counts.get(action, 0) + 1
    return dict(sorted(counts.items()))


def _reviewer_notes(summary: PrSummary) -> list[str]:
    notes: list[str] = []
    if summary.curated_sources:
        notes.append(
            "Review curated source manifests first: added/refreshed/superseded entries explain "
            "the source lifecycle behind generated wiki and runtime churn."
        )
    if summary.source_summary_pages.total:
        notes.append(
            "Review added or changed source-summary pages for extracted claims; deleted "
            "wiki/sources pages are usually mechanical when their source manifest is superseded."
        )
    if summary.maintained_wiki_pages.total:
        notes.append(
            "Review maintained wiki/topic pages as authored synthesis, especially source_refs "
            "updates that redirect from superseded source IDs to active versions."
        )
    runtime_total = sum(summary.generated_state[key].total for key in ("queue", "runs", "reports"))
    if runtime_total:
        notes.append(
            "Treat queue, run, and report files as generated-state evidence unless a failure, "
            "dead-letter, or report issue changes the reviewer decision."
        )
    for command, status in summary.maintenance.items():
        if status is None:
            notes.append(
                f"No local {command} report was found; run `splendor {command}` before handoff."
            )
        else:
            notes.append(
                f"{command} status is from the latest local report, not from this command."
            )
        if status is not None and status.status != "passed":
            notes.append(
                f"Latest {command} report is {status.status} at {status.path}; "
                "inspect it before PR review."
            )
    if not notes:
        notes.append("No Splendor generated-state changes were detected since the base ref.")
    return notes
