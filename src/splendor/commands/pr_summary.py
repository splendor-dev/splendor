"""Read-only PR-oriented generated-state summaries."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from splendor.config import load_config
from splendor.layout import ResolvedLayout, resolve_layout
from splendor.schemas import SourceRecord
from splendor.schemas.maintenance import MaintenanceReport
from splendor.state.source_compat import canonical_source_ref, effective_logical_id
from splendor.state.source_registry import load_source_record


@dataclass(frozen=True)
class ChangedPath:
    status: str
    path: str
    old_path: str | None = None


@dataclass(frozen=True)
class SourceChange:
    action: str
    path: str
    source_id: str
    title: str | None
    source_ref: str | None
    logical_id: str | None
    supersedes: list[str]
    superseded_by: str | None
    old_path: str | None = None


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
    created_at: str | None
    checked_count: int | None
    issue_count: int | None
    fatal_error: str | None


@dataclass(frozen=True)
class PrSummary:
    since: str
    head: str | None
    changed_path_count: int
    curated_sources: list[SourceChange]
    source_summary_pages: PathGroup
    maintained_wiki_pages: PathGroup
    generated_state: dict[str, PathGroup]
    other_paths: PathGroup
    maintenance: dict[str, MaintenanceStatus | None]
    reviewer_notes: list[str]


def build_pr_summary(root: Path, *, since: str) -> PrSummary:
    root = root.resolve()
    _assert_git_ref(root, since)
    layout = resolve_layout(root, load_config(root))
    changes = _changed_paths(root, since=since)
    source_changes = _source_changes(root, since=since, changes=changes)
    source_summary_pages = _group_paths(
        change for change in changes if _is_source_summary_path(change.path)
    )
    maintained_wiki_pages = _group_paths(
        change for change in changes if _is_maintained_wiki_path(change.path)
    )
    generated_state = {
        "queue": _group_paths(
            change for change in changes if change.path.startswith("state/queue/")
        ),
        "runs": _group_paths(change for change in changes if change.path.startswith("state/runs/")),
        "queries": _group_paths(
            change for change in changes if change.path.startswith("state/queries/")
        ),
        "reports": _group_paths(change for change in changes if change.path.startswith("reports/")),
        "derived": _group_paths(change for change in changes if change.path.startswith("derived/")),
    }
    categorized = set()
    for change in changes:
        if _is_categorized_path(change, layout):
            categorized.add(change.path)
    other_paths = _group_paths(change for change in changes if change.path not in categorized)
    maintenance = {
        "lint": _latest_maintenance_status(root, command="lint"),
        "health": _latest_maintenance_status(root, command="health"),
    }
    summary = PrSummary(
        since=since,
        head=_git_text(root, ["rev-parse", "--short", "HEAD"], required=False),
        changed_path_count=len(changes),
        curated_sources=source_changes,
        source_summary_pages=source_summary_pages,
        maintained_wiki_pages=maintained_wiki_pages,
        generated_state=generated_state,
        other_paths=other_paths,
        maintenance=maintenance,
        reviewer_notes=[],
    )
    return PrSummary(
        since=summary.since,
        head=summary.head,
        changed_path_count=summary.changed_path_count,
        curated_sources=summary.curated_sources,
        source_summary_pages=summary.source_summary_pages,
        maintained_wiki_pages=summary.maintained_wiki_pages,
        generated_state=summary.generated_state,
        other_paths=summary.other_paths,
        maintenance=summary.maintenance,
        reviewer_notes=_reviewer_notes(summary),
    )


def render_pr_summary_json(summary: PrSummary) -> str:
    return json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n"


def _assert_git_ref(root: Path, ref: str) -> None:
    _git_text(root, ["rev-parse", "--verify", f"{ref}^{{commit}}"])


def _git_text(root: Path, args: list[str], *, required: bool = True) -> str | None:
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


def _changed_paths(root: Path, *, since: str) -> list[ChangedPath]:
    output = _git_text(root, ["diff", "--name-status", "-M", since, "--"]) or ""
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


def _source_changes(root: Path, *, since: str, changes: list[ChangedPath]) -> list[SourceChange]:
    layout = resolve_layout(root, load_config(root))
    result: list[SourceChange] = []
    for change in changes:
        if not _is_source_manifest_path(change.path, layout):
            continue
        current = _load_current_source(root, change.path)
        previous = _load_source_at_ref(root, since, change.old_path or change.path)
        source = current or previous
        if source is None:
            continue
        action = _source_action(change, current=current, previous=previous)
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
            )
        )
    return result


def _is_source_manifest_path(path: str, layout: ResolvedLayout) -> bool:
    source_dir = layout.source_records_dir.relative_to(layout.root).as_posix()
    return path.startswith(f"{source_dir}/") and path.endswith(".json")


def _load_current_source(root: Path, path: str) -> SourceRecord | None:
    source_path = root / path
    if not source_path.is_file():
        return None
    return load_source_record(source_path)


def _load_source_at_ref(root: Path, ref: str, path: str) -> SourceRecord | None:
    content = _git_text(root, ["show", f"{ref}:{path}"], required=False)
    if content is None:
        return None
    payload = json.loads(content)
    return SourceRecord.model_validate(payload)


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


def _is_source_summary_path(path: str) -> bool:
    return path.startswith("wiki/sources/") and path.endswith(".md")


def _is_maintained_wiki_path(path: str) -> bool:
    return path.startswith("wiki/") and path.endswith(".md") and not _is_source_summary_path(path)


def _in_group(change: ChangedPath, group_key: str) -> bool:
    return change.path.startswith(
        {
            "queue": "state/queue/",
            "runs": "state/runs/",
            "queries": "state/queries/",
            "reports": "reports/",
            "derived": "derived/",
        }[group_key]
    )


def _is_categorized_path(change: ChangedPath, layout: ResolvedLayout) -> bool:
    return (
        _is_source_manifest_path(change.path, layout)
        or _is_source_summary_path(change.path)
        or _is_maintained_wiki_path(change.path)
        or any(_in_group(change, key) for key in ("queue", "runs", "queries", "reports", "derived"))
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


def _latest_maintenance_status(root: Path, *, command: str) -> MaintenanceStatus | None:
    report_dir = root / "reports" / command
    candidates = sorted(report_dir.glob("*.json"))
    if not candidates:
        return None
    latest = candidates[-1]
    try:
        report = MaintenanceReport.model_validate_json(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return MaintenanceStatus(
            command=command,
            status="unreadable",
            path=latest.relative_to(root).as_posix(),
            created_at=None,
            checked_count=None,
            issue_count=None,
            fatal_error=str(exc),
        )
    return MaintenanceStatus(
        command=command,
        status=report.status,
        path=latest.relative_to(root).as_posix(),
        created_at=report.created_at,
        checked_count=report.checked_count,
        issue_count=report.issue_count,
        fatal_error=report.fatal_error,
    )


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
        elif status.status != "passed":
            notes.append(
                f"Latest {command} report is {status.status} at {status.path}; "
                "inspect it before PR review."
            )
    if not notes:
        notes.append("No Splendor generated-state changes were detected since the base ref.")
    return notes
