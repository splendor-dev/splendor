"""Source registry forget/recovery command helpers."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Literal

from splendor.commands.source import (
    SourceLookupResult,
    list_sources,
    resolve_source_query_exact,
)
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import SourceRecord
from splendor.state.paths import resolve_workspace_path
from splendor.state.runtime import ingest_job_id, load_queue_item, load_run_record
from splendor.state.source_compat import (
    canonical_source_ref,
    effective_aliases,
    effective_logical_id,
    effective_materialized_path,
)
from splendor.utils.fs import write_text_atomic
from splendor.utils.wiki import parse_wiki_markdown

SourceForgetActionKind = Literal[
    "source_manifest",
    "source_summary_page",
    "queue_record",
    "run_record",
    "derived_artifact",
    "materialized_artifact",
    "artifact",
    "wiki_index_entry",
]
SourceForgetActionStatus = Literal["planned", "removed", "skipped"]
SourceForgetResidualKind = Literal[
    "source_run_ref",
    "source_provenance_run",
    "wiki_source_ref",
    "wiki_provenance",
    "wiki_generated_by_run",
    "wiki_run_provenance",
    "wiki_text",
    "planning_text",
    "run_provenance",
]


@dataclass(frozen=True)
class SourceForgetAction:
    kind: SourceForgetActionKind
    path: str
    source_id: str
    status: SourceForgetActionStatus
    reason: str | None = None


@dataclass(frozen=True)
class SourceForgetResidualReference:
    kind: SourceForgetResidualKind
    path: str
    source_id: str
    reason: str
    ref_id: str | None = None


@dataclass(frozen=True)
class SourceForgetResult:
    applied: bool
    selector: str | None
    matching: str | None
    candidates: list[SourceLookupResult]
    actions: list[SourceForgetAction]
    skipped: list[SourceForgetAction]
    residual_references: list[SourceForgetResidualReference]


def forget_sources(
    root: Path,
    *,
    selector: str | None = None,
    matching: str | None = None,
    apply: bool = False,
) -> SourceForgetResult:
    if (selector is None) == (matching is None):
        msg = "source forget requires exactly one of selector or --matching"
        raise ValueError(msg)

    candidates = (
        [resolve_source_query_exact(root, selector)]
        if selector is not None
        else _matching_forget_candidates(root, matching or "")
    )
    actions, skipped, residuals = _plan_source_forget(root, candidates)
    if apply:
        _apply_source_forget(root, actions)
        actions = [replace(action, status="removed") for action in actions]
    return SourceForgetResult(
        applied=apply,
        selector=selector,
        matching=matching,
        candidates=candidates,
        actions=actions,
        skipped=skipped,
        residual_references=residuals,
    )


def render_source_forget_json(root: Path, result: SourceForgetResult) -> str:
    return json.dumps(
        {
            "applied": result.applied,
            "selector": result.selector,
            "matching": result.matching,
            "summary": {
                "candidates": len(result.candidates),
                "actions": len(result.actions),
                "skipped": len(result.skipped),
                "residual_references": len(result.residual_references),
            },
            "sources": [_source_payload(root, candidate) for candidate in result.candidates],
            "actions": [_forget_action_payload(action) for action in result.actions],
            "skipped": [_forget_action_payload(action) for action in result.skipped],
            "residual_references": [
                _residual_reference_payload(residual) for residual in result.residual_references
            ],
            "next_commands": forget_next_commands(result),
        },
        indent=2,
    )


def forget_next_commands(result: SourceForgetResult) -> list[str]:
    if not result.applied:
        base = "splendor source forget"
        if result.selector is not None:
            command = f"{base} {shlex.quote(result.selector)} --apply"
        else:
            command = f"{base} --matching {shlex.quote(result.matching or '')} --apply"
        return [command]
    commands = ["splendor lint", "splendor health"]
    if result.residual_references:
        commands.insert(0, "review reported residual references")
    return commands


def _matching_forget_candidates(root: Path, pattern: str) -> list[SourceLookupResult]:
    normalized = pattern.strip()
    if not normalized:
        msg = "--matching requires a non-empty workspace-relative glob"
        raise ValueError(msg)
    if Path(normalized).is_absolute() or ".." in Path(normalized).parts:
        msg = "--matching must be a workspace-relative glob that does not escape the workspace"
        raise ValueError(msg)

    candidates = [
        result
        for result in list_sources(root)
        if any(fnmatchcase(value, normalized) for value in _forget_match_values(result.source))
    ]
    return sorted(candidates, key=lambda result: result.source.source_id)


def _forget_match_values(source: SourceRecord) -> list[str]:
    return _dedupe_values(
        [
            canonical_source_ref(source),
            source.path,
            source.original_path,
            source.source_ref,
            effective_logical_id(source),
            *effective_aliases(source),
        ]
    )


def _plan_source_forget(
    root: Path, candidates: list[SourceLookupResult]
) -> tuple[
    list[SourceForgetAction],
    list[SourceForgetAction],
    list[SourceForgetResidualReference],
]:
    layout = resolve_layout(root, load_config(root))
    selected_ids = {candidate.source.source_id for candidate in candidates}
    remaining_sources = [
        result.source
        for result in list_sources(root)
        if result.source.source_id not in selected_ids
    ]
    actions: list[SourceForgetAction] = []
    skipped: list[SourceForgetAction] = []
    residuals: list[SourceForgetResidualReference] = []

    for candidate in candidates:
        source = candidate.source
        source_id = source.source_id
        manifest_ref = candidate.manifest_path.relative_to(root).as_posix()
        actions.append(
            SourceForgetAction(
                kind="source_manifest",
                path=manifest_ref,
                source_id=source_id,
                status="planned",
            )
        )
        _plan_source_summary_forget(root, layout, source, actions, skipped)
        _plan_source_queue_forget(root, layout, source_id, actions, skipped)
        _plan_source_run_forget(root, layout, source_id, actions, skipped)
        _plan_source_artifact_forget(
            root,
            layout,
            source=source,
            remaining_sources=remaining_sources,
            actions=actions,
            skipped=skipped,
        )
        residuals.extend(_source_residual_references(root, layout, source_id))

    _plan_index_cleanup(root, layout, selected_ids, actions)
    actions, skipped, run_residuals = _protect_referenced_run_records(
        root, layout, actions, skipped, remaining_sources
    )
    residuals.extend(run_residuals)
    actions = _dedupe_forget_actions(actions)
    skipped = _dedupe_forget_actions(skipped)
    residuals = _dedupe_residuals(residuals)
    return actions, skipped, residuals


def _plan_source_summary_forget(
    root: Path,
    layout,
    source: SourceRecord,
    actions: list[SourceForgetAction],
    skipped: list[SourceForgetAction],
) -> None:
    source_id = source.source_id
    expected_ref = f"wiki/sources/{source_id}.md"
    page_refs = _dedupe_values([expected_ref, *source.linked_pages])
    for page_ref in page_refs:
        try:
            page_path = resolve_workspace_path(root, page_ref, context="Linked source page")
        except ValueError as exc:
            skipped.append(
                SourceForgetAction(
                    kind="source_summary_page",
                    path=page_ref,
                    source_id=source_id,
                    status="skipped",
                    reason=str(exc),
                )
            )
            continue
        if not page_path.is_file():
            continue
        page_relpath = page_path.relative_to(root).as_posix()
        if not _is_safe_source_summary_page(page_path, source_id):
            skipped.append(
                SourceForgetAction(
                    kind="source_summary_page",
                    path=page_relpath,
                    source_id=source_id,
                    status="skipped",
                    reason="wiki page is not the expected generated source-summary page",
                )
            )
            continue
        if not _path_is_within(page_path, layout.wiki_sources_dir):
            skipped.append(
                SourceForgetAction(
                    kind="source_summary_page",
                    path=page_relpath,
                    source_id=source_id,
                    status="skipped",
                    reason="source summary page is outside wiki/sources",
                )
            )
            continue
        actions.append(
            SourceForgetAction(
                kind="source_summary_page",
                path=page_relpath,
                source_id=source_id,
                status="planned",
            )
        )


def _is_safe_source_summary_page(page_path: Path, source_id: str) -> bool:
    try:
        parsed = parse_wiki_markdown(page_path)
    except ValueError:
        return False
    return (
        parsed.frontmatter.kind == "source-summary"
        and parsed.frontmatter.page_id == source_id
        and source_id in parsed.frontmatter.source_refs
    )


def _plan_source_queue_forget(
    root: Path,
    layout,
    source_id: str,
    actions: list[SourceForgetAction],
    skipped: list[SourceForgetAction],
) -> None:
    queue_path = layout.queue_dir / f"{ingest_job_id(source_id)}.json"
    if not queue_path.is_file():
        return
    queue_ref = queue_path.relative_to(root).as_posix()
    try:
        queue = load_queue_item(queue_path)
    except ValueError as exc:
        skipped.append(
            SourceForgetAction(
                kind="queue_record",
                path=queue_ref,
                source_id=source_id,
                status="skipped",
                reason=f"queue record is invalid: {exc}",
            )
        )
        return
    if queue.job_id != ingest_job_id(source_id) or queue.job_type != "ingest_source":
        skipped.append(
            SourceForgetAction(
                kind="queue_record",
                path=queue_ref,
                source_id=source_id,
                status="skipped",
                reason="queue record is not the expected source-owned ingest job",
            )
        )
        return
    actions.append(
        SourceForgetAction(
            kind="queue_record",
            path=queue_ref,
            source_id=source_id,
            status="planned",
        )
    )


def _plan_source_run_forget(
    root: Path,
    layout,
    source_id: str,
    actions: list[SourceForgetAction],
    skipped: list[SourceForgetAction],
) -> None:
    for run_path in sorted(layout.runs_dir.glob("*.json")):
        if not run_path.is_file():
            continue
        try:
            run = load_run_record(run_path)
        except ValueError:
            continue
        if source_id not in run.source_ids:
            continue
        run_ref = run_path.relative_to(root).as_posix()
        if (
            run.job_type == "ingest_source"
            and run.job_id == ingest_job_id(source_id)
            and set(run.source_ids) == {source_id}
        ):
            actions.append(
                SourceForgetAction(
                    kind="run_record",
                    path=run_ref,
                    source_id=source_id,
                    status="planned",
                )
            )
            continue
        skipped.append(
            SourceForgetAction(
                kind="run_record",
                path=run_ref,
                source_id=source_id,
                status="skipped",
                reason="run also references other state or is not a source-owned ingest run",
            )
        )


def _plan_source_artifact_forget(
    root: Path,
    layout,
    *,
    source: SourceRecord,
    remaining_sources: list[SourceRecord],
    actions: list[SourceForgetAction],
    skipped: list[SourceForgetAction],
) -> None:
    source_id = source.source_id
    artifact_refs = _dedupe_values([*source.derived_artifacts, effective_materialized_path(source)])
    remaining_refs = {
        ref
        for remaining in remaining_sources
        for ref in [*remaining.derived_artifacts, effective_materialized_path(remaining)]
        if ref is not None
    }
    for artifact_ref in artifact_refs:
        if artifact_ref is None or artifact_ref in remaining_refs:
            continue
        try:
            artifact_path = resolve_workspace_path(root, artifact_ref, context="Source artifact")
        except ValueError as exc:
            skipped.append(
                SourceForgetAction(
                    kind="artifact",
                    path=artifact_ref,
                    source_id=source_id,
                    status="skipped",
                    reason=str(exc),
                )
            )
            continue
        if not artifact_path.exists() and not artifact_path.is_symlink():
            continue
        artifact_relpath = artifact_path.relative_to(root).as_posix()
        if _path_is_within(artifact_path, layout.derived_dir):
            kind: SourceForgetActionKind = "derived_artifact"
        elif _path_is_within(artifact_path, layout.raw_sources_dir / source_id):
            kind = "materialized_artifact"
        else:
            skipped.append(
                SourceForgetAction(
                    kind="artifact",
                    path=artifact_relpath,
                    source_id=source_id,
                    status="skipped",
                    reason="artifact is outside source-owned generated directories",
                )
            )
            continue
        actions.append(
            SourceForgetAction(
                kind=kind,
                path=artifact_relpath,
                source_id=source_id,
                status="planned",
            )
        )


def _plan_index_cleanup(
    root: Path,
    layout,
    selected_ids: set[str],
    actions: list[SourceForgetAction],
) -> None:
    if not layout.index_file.is_file():
        return
    index_text = layout.index_file.read_text(encoding="utf-8")
    for source_id in sorted(selected_ids):
        if f"(`{source_id}`)" in index_text:
            actions.append(
                SourceForgetAction(
                    kind="wiki_index_entry",
                    path=layout.index_file.relative_to(root).as_posix(),
                    source_id=source_id,
                    status="planned",
                )
            )


def _source_residual_references(
    root: Path, layout, source_id: str
) -> list[SourceForgetResidualReference]:
    residuals: list[SourceForgetResidualReference] = []
    for wiki_path in sorted(layout.wiki_dir.rglob("*.md")):
        if wiki_path.name == ".gitkeep" or wiki_path in {layout.index_file, layout.log_file}:
            continue
        page_ref = wiki_path.relative_to(root).as_posix()
        if page_ref == f"wiki/sources/{source_id}.md":
            continue
        try:
            parsed = parse_wiki_markdown(wiki_path)
        except ValueError:
            text = wiki_path.read_text(encoding="utf-8")
            if source_id in text:
                residuals.append(
                    SourceForgetResidualReference(
                        kind="wiki_text",
                        path=page_ref,
                        source_id=source_id,
                        reason="wiki page text contains source ID",
                    )
                )
            continue
        if source_id in parsed.frontmatter.source_refs:
            residuals.append(
                SourceForgetResidualReference(
                    kind="wiki_source_ref",
                    path=page_ref,
                    source_id=source_id,
                    reason="maintained wiki page source_refs contains source ID",
                )
            )
        if any(link.source_id == source_id for link in parsed.frontmatter.provenance_links):
            residuals.append(
                SourceForgetResidualReference(
                    kind="wiki_provenance",
                    path=page_ref,
                    source_id=source_id,
                    reason="maintained wiki page provenance contains source ID",
                )
            )
        if source_id in parsed.body:
            residuals.append(
                SourceForgetResidualReference(
                    kind="wiki_text",
                    path=page_ref,
                    source_id=source_id,
                    reason="wiki page text contains source ID",
                )
            )

    for planning_path in sorted(layout.planning_dir.rglob("*.md")):
        if planning_path.name == ".gitkeep" or not planning_path.is_file():
            continue
        if source_id not in planning_path.read_text(encoding="utf-8"):
            continue
        residuals.append(
            SourceForgetResidualReference(
                kind="planning_text",
                path=planning_path.relative_to(root).as_posix(),
                source_id=source_id,
                reason="planning record contains source ID",
            )
        )
    return residuals


def _protect_referenced_run_records(
    root: Path,
    layout,
    actions: list[SourceForgetAction],
    skipped: list[SourceForgetAction],
    remaining_sources: list[SourceRecord],
) -> tuple[
    list[SourceForgetAction],
    list[SourceForgetAction],
    list[SourceForgetResidualReference],
]:
    kept_actions: list[SourceForgetAction] = []
    run_residuals: list[SourceForgetResidualReference] = []
    deleted_page_refs = {action.path for action in actions if action.kind == "source_summary_page"}
    for action in actions:
        if action.kind != "run_record":
            kept_actions.append(action)
            continue
        run_id = Path(action.path).stem
        residuals = _run_residual_references(
            root,
            layout,
            source_id=action.source_id,
            run_id=run_id,
            deleted_page_refs=deleted_page_refs,
            remaining_sources=remaining_sources,
        )
        if not residuals:
            kept_actions.append(action)
            continue
        skipped.append(
            replace(
                action,
                status="skipped",
                reason="run record is referenced by remaining workspace state",
            )
        )
        run_residuals.extend(residuals)
    return kept_actions, skipped, run_residuals


def _run_residual_references(
    root: Path,
    layout,
    *,
    source_id: str,
    run_id: str,
    deleted_page_refs: set[str],
    remaining_sources: list[SourceRecord],
) -> list[SourceForgetResidualReference]:
    residuals: list[SourceForgetResidualReference] = []
    for source in sorted(remaining_sources, key=lambda item: item.source_id):
        source_path = layout.source_records_dir / f"{source.source_id}.json"
        source_ref = source_path.relative_to(root).as_posix()
        if source.last_run_id == run_id or run_id in source.generated_by_run_ids:
            residuals.append(
                SourceForgetResidualReference(
                    kind="source_run_ref",
                    path=source_ref,
                    source_id=source_id,
                    ref_id=run_id,
                    reason="remaining source manifest references run ID",
                )
            )
        if any(link.run_id == run_id for link in source.provenance_links):
            residuals.append(
                SourceForgetResidualReference(
                    kind="source_provenance_run",
                    path=source_ref,
                    source_id=source_id,
                    ref_id=run_id,
                    reason="remaining source manifest provenance references run ID",
                )
            )

    for wiki_path in sorted(layout.wiki_dir.rglob("*.md")):
        if wiki_path.name == ".gitkeep" or wiki_path in {layout.index_file, layout.log_file}:
            continue
        page_ref = wiki_path.relative_to(root).as_posix()
        if page_ref in deleted_page_refs:
            continue
        try:
            parsed = parse_wiki_markdown(wiki_path)
        except ValueError:
            text = wiki_path.read_text(encoding="utf-8")
            if run_id in text:
                residuals.append(
                    SourceForgetResidualReference(
                        kind="wiki_text",
                        path=page_ref,
                        source_id=source_id,
                        ref_id=run_id,
                        reason="wiki page text contains run ID",
                    )
                )
            continue
        if run_id in parsed.frontmatter.generated_by_run_ids:
            residuals.append(
                SourceForgetResidualReference(
                    kind="wiki_generated_by_run",
                    path=page_ref,
                    source_id=source_id,
                    ref_id=run_id,
                    reason="maintained wiki page generated_by_run_ids contains run ID",
                )
            )
        if any(link.run_id == run_id for link in parsed.frontmatter.provenance_links):
            residuals.append(
                SourceForgetResidualReference(
                    kind="wiki_run_provenance",
                    path=page_ref,
                    source_id=source_id,
                    ref_id=run_id,
                    reason="maintained wiki page provenance contains run ID",
                )
            )
        if run_id in parsed.body:
            residuals.append(
                SourceForgetResidualReference(
                    kind="wiki_text",
                    path=page_ref,
                    source_id=source_id,
                    ref_id=run_id,
                    reason="wiki page text contains run ID",
                )
            )

    for planning_path in sorted(layout.planning_dir.rglob("*.md")):
        if planning_path.name == ".gitkeep" or not planning_path.is_file():
            continue
        if run_id not in planning_path.read_text(encoding="utf-8"):
            continue
        residuals.append(
            SourceForgetResidualReference(
                kind="planning_text",
                path=planning_path.relative_to(root).as_posix(),
                source_id=source_id,
                ref_id=run_id,
                reason="planning record contains run ID",
            )
        )

    for run_path in sorted(layout.runs_dir.glob("*.json")):
        if run_path.stem == run_id or not run_path.is_file():
            continue
        try:
            run = load_run_record(run_path)
        except ValueError:
            continue
        if not any(link.run_id == run_id for link in run.provenance_links):
            continue
        residuals.append(
            SourceForgetResidualReference(
                kind="run_provenance",
                path=run_path.relative_to(root).as_posix(),
                source_id=source_id,
                ref_id=run_id,
                reason="remaining run record provenance references run ID",
            )
        )
    return residuals


def _apply_source_forget(root: Path, actions: list[SourceForgetAction]) -> None:
    layout = resolve_layout(root, load_config(root))
    _preflight_source_forget_targets(root, actions)
    for action in actions:
        if action.kind == "wiki_index_entry":
            continue
        target = resolve_workspace_path(root, action.path, context="Forget target")
        if target.exists() or target.is_symlink():
            target.unlink()
            _remove_empty_source_artifact_parents(layout.raw_sources_dir, target)

    if any(action.kind == "wiki_index_entry" for action in actions):
        _apply_index_cleanup(
            layout,
            {action.source_id for action in actions if action.kind == "wiki_index_entry"},
        )


def _preflight_source_forget_targets(root: Path, actions: list[SourceForgetAction]) -> None:
    for action in actions:
        if action.kind == "wiki_index_entry":
            continue
        target = resolve_workspace_path(root, action.path, context="Forget target")
        if target.is_dir() and not target.is_symlink():
            msg = f"Forget target is not a removable file: {action.path}"
            raise ValueError(msg)


def _apply_index_cleanup(layout, selected_ids: set[str]) -> None:
    index_path = layout.index_file
    if not index_path.is_file():
        return
    lines = index_path.read_text(encoding="utf-8").splitlines()
    cleaned = [
        line
        for line in lines
        if not any(
            line.startswith("- [") and f"(`{source_id}`)" in line for source_id in selected_ids
        )
    ]
    write_text_atomic(index_path, "\n".join(cleaned).rstrip() + "\n")


def _remove_empty_source_artifact_parents(raw_sources_dir: Path, target: Path) -> None:
    raw_sources_root = raw_sources_dir.resolve()
    current = target.parent
    while current != raw_sources_root:
        try:
            current.relative_to(raw_sources_root)
        except ValueError:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _dedupe_values(values: list[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _dedupe_forget_actions(actions: list[SourceForgetAction]) -> list[SourceForgetAction]:
    deduped: list[SourceForgetAction] = []
    seen: set[tuple[str, str, str]] = set()
    for action in sorted(actions, key=lambda item: (item.kind, item.path, item.source_id)):
        key = (action.kind, action.path, action.source_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _dedupe_residuals(
    residuals: list[SourceForgetResidualReference],
) -> list[SourceForgetResidualReference]:
    deduped: list[SourceForgetResidualReference] = []
    seen: set[tuple[str, str, str, str, str | None]] = set()
    for residual in sorted(
        residuals,
        key=lambda item: (
            item.kind,
            item.path,
            item.source_id,
            item.reason,
            item.ref_id or "",
        ),
    ):
        key = (
            residual.kind,
            residual.path,
            residual.source_id,
            residual.reason,
            residual.ref_id,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(residual)
    return deduped


def _forget_action_payload(action: SourceForgetAction) -> dict[str, object]:
    return {
        "kind": action.kind,
        "path": action.path,
        "source_id": action.source_id,
        "status": action.status,
        "reason": action.reason,
    }


def _residual_reference_payload(
    residual: SourceForgetResidualReference,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": residual.kind,
        "path": residual.path,
        "source_id": residual.source_id,
        "reason": residual.reason,
    }
    if residual.ref_id is not None:
        payload["ref_id"] = residual.ref_id
    return payload


def _source_payload(root: Path, result: SourceLookupResult) -> dict[str, object]:
    source = result.source
    return {
        "source_id": source.source_id,
        "logical_id": effective_logical_id(source),
        "aliases": effective_aliases(source),
        "title": source.title,
        "source_type": source.source_type,
        "status": source.status,
        "supersedes": source.supersedes,
        "superseded_by": source.superseded_by,
        "source_ref": canonical_source_ref(source),
        "source_ref_kind": source.source_ref_kind,
        "original_path": source.original_path,
        "checksum": source.checksum,
        "manifest_path": result.manifest_path.relative_to(root).as_posix(),
        "queue_job_id": ingest_job_id(source.source_id),
        "linked_pages": source.linked_pages,
    }
