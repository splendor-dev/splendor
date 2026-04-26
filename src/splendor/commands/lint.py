"""Implementation for `splendor lint`."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from splendor.commands.maintenance import MaintenanceCheckResult, workspace_relative_path
from splendor.layout import ResolvedLayout, required_directories
from splendor.schemas import (
    DecisionRecord,
    KnowledgePageFrontmatter,
    MaintenanceIssue,
    MilestoneRecord,
    QuestionRecord,
    SourceRecord,
    TaskRecord,
)
from splendor.state.paths import resolve_workspace_path
from splendor.state.source_registry import load_source_record
from splendor.utils.planning import iter_planning_paths, parse_planning_document, planning_directory
from splendor.utils.wiki import parse_wiki_markdown

_MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+]\(([^)]+)\)")
_PLANNING_STATE_LABELS = (
    "Previous completed PR sub-slice",
    "Current planned slice",
    "Current PR sub-slice",
    "Current PR lifecycle",
    "Next planned slice",
    "Next planned PR sub-slice",
)
_PLANNING_STATE_PATTERN = re.compile(
    r"^- (?P<label>Previous completed PR sub-slice|Current planned slice|"
    r"Current PR sub-slice|Current PR lifecycle|Next planned slice|"
    r"Next planned PR sub-slice): (?P<value>`[^`]+`|.+)$",
    re.MULTILINE,
)
_PLANNING_LIFECYCLE_VALUE = "branch=in-progress; main=merged"
_PLANNING_SLICE_PATTERN = re.compile(r"^(?P<slice>M\d+-P\d+(?:\.\d+)?)\b")
_PLANNING_MODELS = {
    "task": TaskRecord,
    "milestone": MilestoneRecord,
    "decision": DecisionRecord,
    "question": QuestionRecord,
}
_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class _WikiPageInventory:
    path: Path
    body: str | None
    frontmatter: KnowledgePageFrontmatter | None

    @property
    def page_id(self) -> str | None:
        if self.frontmatter is None:
            return None
        return self.frontmatter.page_id


@dataclass(frozen=True)
class _PlanningInventory:
    kind: str
    path: Path
    body: str | None
    record: TaskRecord | MilestoneRecord | DecisionRecord | QuestionRecord | None

    @property
    def record_id(self) -> str | None:
        if self.record is None:
            return None
        field = {
            "task": "task_id",
            "milestone": "milestone_id",
            "decision": "decision_id",
            "question": "question_id",
        }[self.kind]
        return str(getattr(self.record, field))


@dataclass(frozen=True)
class _SourceInventory:
    manifest_path: Path
    record: SourceRecord | None

    @property
    def source_id(self) -> str | None:
        if self.record is None:
            return None
        return self.record.source_id


@dataclass(frozen=True)
class _LintInventory:
    wiki_pages: list[_WikiPageInventory]
    planning_records: list[_PlanningInventory]
    source_manifests: list[_SourceInventory]


def run_lint_checks(root: Path, layout: ResolvedLayout) -> MaintenanceCheckResult:
    workspace_result = _run_workspace_checks(root, layout)
    inventory_result = _inventory_content_records(root, layout)
    reference_result = _run_reference_integrity_checks(root, layout, inventory_result)
    return MaintenanceCheckResult(
        checked_count=(
            workspace_result.checked_count
            + inventory_result.checked_count
            + reference_result.checked_count
        ),
        issues=[*workspace_result.issues, *inventory_result.issues, *reference_result.issues],
    )


@dataclass(frozen=True)
class _LintCheckContext:
    inventory: _LintInventory


@dataclass(frozen=True)
class _LintCheckResult:
    checked_count: int
    issues: list[MaintenanceIssue]
    context: _LintCheckContext | None = None


def _run_workspace_checks(root: Path, layout: ResolvedLayout) -> _LintCheckResult:
    issues: list[MaintenanceIssue] = []
    checked_count = 0

    for directory in required_directories(layout):
        checked_count += 1
        if directory.is_dir():
            continue
        issues.append(
            MaintenanceIssue(
                code="missing-directory",
                message="Required workspace directory is missing",
                path=workspace_relative_path(layout.root, directory),
                check_name="workspace-layout",
            )
        )

    for path in (layout.index_file, layout.log_file):
        checked_count += 1
        if path.is_file():
            continue
        issues.append(
            MaintenanceIssue(
                code="missing-file",
                message="Required bootstrap file is missing",
                path=workspace_relative_path(layout.root, path),
                check_name="workspace-bootstrap",
            )
        )

    return _LintCheckResult(checked_count=checked_count, issues=issues)


def _inventory_content_records(root: Path, layout: ResolvedLayout) -> _LintCheckResult:
    checked_count = 0
    issues: list[MaintenanceIssue] = []

    wiki_pages: list[_WikiPageInventory] = []
    for path in sorted(layout.wiki_dir.rglob("*.md")):
        if path.name == ".gitkeep" or path in {layout.index_file, layout.log_file}:
            continue
        checked_count += 1
        try:
            parsed = parse_wiki_markdown(path)
        except Exception as exc:
            issues.append(
                MaintenanceIssue(
                    code="invalid-wiki-frontmatter",
                    message=_normalize_issue_exception(root, path, exc),
                    path=workspace_relative_path(root, path),
                    check_name="wiki-schema",
                )
            )
            wiki_pages.append(_WikiPageInventory(path=path, body=None, frontmatter=None))
            continue
        wiki_pages.append(
            _WikiPageInventory(path=path, body=parsed.body, frontmatter=parsed.frontmatter)
        )

    planning_records: list[_PlanningInventory] = []
    for kind, model in _PLANNING_MODELS.items():
        for path in iter_planning_paths(planning_directory(layout, kind)):
            checked_count += 1
            try:
                parsed = parse_planning_document(path, model)
            except Exception as exc:
                issues.append(
                    MaintenanceIssue(
                        code="invalid-planning-frontmatter",
                        message=_normalize_issue_exception(root, path, exc),
                        path=workspace_relative_path(root, path),
                        check_name="planning-schema",
                    )
                )
                planning_records.append(
                    _PlanningInventory(kind=kind, path=path, body=None, record=None)
                )
                continue
            planning_records.append(
                _PlanningInventory(kind=kind, path=path, body=parsed.body, record=parsed.record)
            )

    source_manifests: list[_SourceInventory] = []
    if layout.source_records_dir.is_dir():
        for path in sorted(layout.source_records_dir.glob("*.json")):
            checked_count += 1
            try:
                record = load_source_record(path)
            except Exception as exc:
                issues.append(
                    MaintenanceIssue(
                        code="invalid-source-manifest",
                        message=_normalize_issue_exception(root, path, exc),
                        path=workspace_relative_path(root, path),
                        check_name="source-manifest",
                    )
                )
                source_manifests.append(_SourceInventory(manifest_path=path, record=None))
                continue
            source_manifests.append(_SourceInventory(manifest_path=path, record=record))

    return _LintCheckResult(
        checked_count=checked_count,
        issues=issues,
        context=_LintCheckContext(
            inventory=_LintInventory(
                wiki_pages=wiki_pages,
                planning_records=planning_records,
                source_manifests=source_manifests,
            )
        ),
    )


def _run_reference_integrity_checks(
    root: Path, layout: ResolvedLayout, inventory_result: _LintCheckResult
) -> _LintCheckResult:
    if inventory_result.context is None:
        return _LintCheckResult(checked_count=0, issues=[])

    checked_count = 0
    issues: list[MaintenanceIssue] = []
    inventory = inventory_result.context.inventory

    wiki_by_id: dict[str, list[_WikiPageInventory]] = {}
    wiki_by_path: dict[str, _WikiPageInventory] = {}
    for page in inventory.wiki_pages:
        if page.frontmatter is None:
            continue
        wiki_by_id.setdefault(page.frontmatter.page_id, []).append(page)
        wiki_by_path[workspace_relative_path(root, page.path)] = page

    planning_by_kind: dict[str, dict[str, list[_PlanningInventory]]] = {
        kind: {} for kind in _PLANNING_MODELS
    }
    for record in inventory.planning_records:
        if record.record is None or record.record_id is None:
            continue
        planning_by_kind[record.kind].setdefault(record.record_id, []).append(record)

    source_by_id: dict[str, list[_SourceInventory]] = {}
    for manifest in inventory.source_manifests:
        if manifest.record is None:
            continue
        source_by_id.setdefault(manifest.record.source_id, []).append(manifest)

    for code, values in (
        ("duplicate-page-id", wiki_by_id),
        ("duplicate-source-id", source_by_id),
    ):
        checked_count += len(values)
        issues.extend(_duplicate_id_issues(root, code, values))

    for values in planning_by_kind.values():
        checked_count += len(values)
        issues.extend(_duplicate_id_issues(root, "duplicate-record-id", values))

    valid_page_ids = set(wiki_by_id)
    valid_source_ids = set(source_by_id)
    valid_planning_ids = {kind: set(values) for kind, values in planning_by_kind.items()}
    valid_run_refs = {
        workspace_relative_path(root, path)
        for path in sorted(layout.runs_dir.glob("*.json"))
        if path.is_file()
    }
    contradiction_task_ids = {
        contradiction.review_task_id
        for page in inventory.wiki_pages
        if page.frontmatter is not None
        for contradiction in page.frontmatter.contradictions
    }

    for page in inventory.wiki_pages:
        if page.frontmatter is None:
            continue
        checked_count += len(page.frontmatter.source_refs)
        issues.extend(
            _missing_ref_issues(
                refs=page.frontmatter.source_refs,
                valid_refs=valid_source_ids,
                code="missing-source-ref",
                message_prefix="Wiki page references unknown source",
                path=workspace_relative_path(root, page.path),
                record_id=page.frontmatter.page_id,
            )
        )
        checked_count += len(page.frontmatter.related_pages)
        issues.extend(
            _missing_ref_issues(
                refs=page.frontmatter.related_pages,
                valid_refs=valid_page_ids,
                code="missing-page-ref",
                message_prefix="Wiki page references unknown related page",
                path=workspace_relative_path(root, page.path),
                record_id=page.frontmatter.page_id,
            )
        )
        page_link_count, page_link_issues = _markdown_link_issues(
            root,
            page.path,
            page.body or "",
            check_name="wiki-links",
            record_id=page.frontmatter.page_id,
        )
        checked_count += page_link_count
        issues.extend(page_link_issues)
        checked_count += len(page.frontmatter.provenance_links)
        issues.extend(
            _provenance_link_issues(
                root=root,
                path=workspace_relative_path(root, page.path),
                record_id=page.frontmatter.page_id,
                links=page.frontmatter.provenance_links,
                valid_source_ids=valid_source_ids,
                valid_page_ids=valid_page_ids,
                check_name="wiki-provenance",
            )
        )
        checked_count += len(page.frontmatter.contradictions)
        issues.extend(
            _contradiction_issues(
                root=root,
                page=page,
                wiki_by_id=wiki_by_id,
                valid_source_ids=valid_source_ids,
                valid_run_refs=valid_run_refs,
                valid_task_ids=valid_planning_ids["task"],
            )
        )
        issues.extend(
            _source_summary_alignment_issues(
                root=root,
                page=page,
                source_by_id=source_by_id,
            )
        )

    for record in inventory.planning_records:
        if record.record is None or record.record_id is None:
            continue
        checked_count += _planning_ref_count(record.record)
        issues.extend(
            _planning_ref_issues(
                root,
                layout,
                record,
                valid_planning_ids,
                valid_source_ids,
                valid_run_refs,
                contradiction_task_ids,
            )
        )
        link_count, link_issues = _markdown_link_issues(
            root,
            record.path,
            record.body or "",
            check_name="planning-links",
            record_id=record.record_id,
        )
        checked_count += link_count
        issues.extend(link_issues)

    for manifest in inventory.source_manifests:
        if manifest.record is None:
            continue
        checked_count += len(manifest.record.linked_pages)
        issues.extend(_linked_page_issues(root, manifest, wiki_by_path))
        checked_count += len(manifest.record.provenance_links)
        issues.extend(
            _provenance_link_issues(
                root=root,
                path=workspace_relative_path(root, manifest.manifest_path),
                record_id=manifest.record.source_id,
                links=manifest.record.provenance_links,
                valid_source_ids=valid_source_ids,
                valid_page_ids=valid_page_ids,
                check_name="source-provenance",
            )
        )

    planning_state_checked_count, planning_state_issues = _planning_state_issues(root)
    checked_count += planning_state_checked_count
    issues.extend(planning_state_issues)

    return _LintCheckResult(checked_count=checked_count, issues=issues)


def _planning_state_issues(root: Path) -> tuple[int, list[MaintenanceIssue]]:
    paths = {
        "agent-plan": root / ".agent-plan.md",
        "readme": root / "README.md",
        "roadmap": root / "docs" / "splendor_mvp_to_v1_roadmap.md",
    }
    if not all(path.is_file() for path in paths.values()):
        return 0, []

    checked_count = len(_PLANNING_STATE_LABELS) * len(paths)
    parsed = {
        name: _parse_planning_state(path.read_text(encoding="utf-8"))
        for name, path in paths.items()
    }
    issues: list[MaintenanceIssue] = []
    for name, values in parsed.items():
        path = workspace_relative_path(root, paths[name])
        for label in _PLANNING_STATE_LABELS:
            if label in values:
                continue
            issues.append(
                MaintenanceIssue(
                    code="missing-planning-state",
                    message=f"Planning state line is missing: {label}",
                    path=path,
                    record_id=label,
                    check_name="planning-state",
                )
            )

    canonical = parsed["agent-plan"]
    for name in ("readme", "roadmap"):
        path = workspace_relative_path(root, paths[name])
        for label in _PLANNING_STATE_LABELS:
            if label not in canonical or label not in parsed[name]:
                continue
            if parsed[name][label] == canonical[label]:
                continue
            issues.append(
                MaintenanceIssue(
                    code="planning-state-drift",
                    message=(
                        f"{label} does not match .agent-plan.md: "
                        f"expected {canonical[label]}, found {parsed[name][label]}"
                    ),
                    path=path,
                    record_id=label,
                    check_name="planning-state",
                )
            )
    lifecycle = canonical.get("Current PR lifecycle")
    if lifecycle is not None and lifecycle != _PLANNING_LIFECYCLE_VALUE:
        issues.append(
            MaintenanceIssue(
                code="invalid-planning-lifecycle",
                message=(f"Current PR lifecycle must be exactly {_PLANNING_LIFECYCLE_VALUE!r}"),
                path=workspace_relative_path(root, paths["agent-plan"]),
                record_id="Current PR lifecycle",
                check_name="planning-state",
            )
        )
    head_slice = _current_main_head_slice(root)
    current_slice = canonical.get("Current PR sub-slice")
    if head_slice is not None and current_slice is not None and head_slice != current_slice:
        issues.append(
            MaintenanceIssue(
                code="stale-planning-state",
                message=(
                    "Current PR sub-slice does not match latest main commit: "
                    f"expected {head_slice}, found {current_slice}"
                ),
                path=workspace_relative_path(root, paths["agent-plan"]),
                record_id="Current PR sub-slice",
                check_name="planning-state",
            )
        )
    return checked_count, issues


def _parse_planning_state(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _PLANNING_STATE_PATTERN.finditer(text):
        value = match.group("value").strip()
        if value.startswith("`") and value.endswith("`"):
            value = value[1:-1]
        values[match.group("label")] = value
    return values


def _current_main_head_slice(root: Path) -> str | None:
    branch = _git_output(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        return None
    subject = _git_output(root, "log", "-1", "--pretty=%s")
    if subject is None:
        return None
    match = _PLANNING_SLICE_PATTERN.match(subject)
    if match is None:
        return None
    return match.group("slice")


def _git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _duplicate_id_issues(
    root: Path,
    code: str,
    values: dict[str, list[_WikiPageInventory] | list[_PlanningInventory] | list[_SourceInventory]],
) -> list[MaintenanceIssue]:
    issues: list[MaintenanceIssue] = []
    for record_id, records in sorted(values.items()):
        if len(records) < 2:
            continue
        paths = sorted(_inventory_issue_path(root, record) for record in records)
        issues.append(
            MaintenanceIssue(
                code=code,
                message=f"Duplicate identifier {record_id!r} appears in: {', '.join(paths)}",
                path=paths[0],
                record_id=record_id,
                check_name="reference-integrity",
            )
        )
    return issues


def _inventory_issue_path(
    root: Path, record: _WikiPageInventory | _PlanningInventory | _SourceInventory
) -> str:
    path = (
        record.path
        if isinstance(record, _WikiPageInventory | _PlanningInventory)
        else record.manifest_path
    )
    return workspace_relative_path(root, path)


def _missing_ref_issues(
    *,
    refs: list[str],
    valid_refs: set[str],
    code: str,
    message_prefix: str,
    path: str,
    record_id: str,
) -> list[MaintenanceIssue]:
    issues: list[MaintenanceIssue] = []
    for ref in refs:
        if ref in valid_refs:
            continue
        issues.append(
            MaintenanceIssue(
                code=code,
                message=f"{message_prefix}: {ref}",
                path=path,
                record_id=record_id,
                check_name="reference-integrity",
            )
        )
    return issues


def _planning_ref_count(
    record: TaskRecord | MilestoneRecord | DecisionRecord | QuestionRecord,
) -> int:
    if isinstance(record, TaskRecord):
        return (
            len(record.milestone_refs)
            + len(record.decision_refs)
            + len(record.question_refs)
            + len(record.depends_on)
            + len(record.source_refs)
            + len(record.page_refs)
            + len(record.run_refs)
        )
    if isinstance(record, MilestoneRecord):
        return len(record.task_refs) + len(record.decision_refs) + len(record.question_refs)
    if isinstance(record, DecisionRecord):
        return (
            len(record.supersedes)
            + len(record.source_refs)
            + len(record.related_tasks)
            + len(record.related_questions)
        )
    return (
        len(record.source_refs)
        + len(record.related_tasks)
        + len(record.related_decisions)
        + (1 if record.answer_page_ref is not None else 0)
    )


def _planning_ref_issues(
    root: Path,
    layout: ResolvedLayout,
    record: _PlanningInventory,
    valid_planning_ids: dict[str, set[str]],
    valid_source_ids: set[str],
    valid_run_refs: set[str],
    contradiction_task_ids: set[str],
) -> list[MaintenanceIssue]:
    assert record.record is not None
    assert record.record_id is not None
    path = workspace_relative_path(root, record.path)

    if isinstance(record.record, TaskRecord):
        return [
            *_missing_ref_issues(
                refs=record.record.milestone_refs,
                valid_refs=valid_planning_ids["milestone"],
                code="missing-milestone-ref",
                message_prefix="Task references unknown milestone",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.decision_refs,
                valid_refs=valid_planning_ids["decision"],
                code="missing-decision-ref",
                message_prefix="Task references unknown decision",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.question_refs,
                valid_refs=valid_planning_ids["question"],
                code="missing-question-ref",
                message_prefix="Task references unknown question",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.depends_on,
                valid_refs=valid_planning_ids["task"],
                code="missing-task-ref",
                message_prefix="Task depends on unknown task",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.source_refs,
                valid_refs=valid_source_ids,
                code="missing-source-ref",
                message_prefix="Task references unknown source",
                path=path,
                record_id=record.record_id,
            ),
            *_existing_workspace_path_issues(
                root=root,
                refs=record.record.page_refs,
                code="missing-page-ref",
                message_prefix="Task references unknown page",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.run_refs,
                valid_refs=valid_run_refs,
                code="missing-run-ref",
                message_prefix="Task references unknown run",
                path=path,
                record_id=record.record_id,
            ),
            *(
                []
                if record.record_id not in contradiction_task_ids or record.record.source_refs
                else [
                    MaintenanceIssue(
                        code="contradiction-task-missing-source-refs",
                        message="Contradiction-linked tasks must persist source_refs.",
                        path=path,
                        record_id=record.record_id,
                        check_name="reference-integrity",
                    )
                ]
            ),
            *(
                []
                if record.record_id not in contradiction_task_ids or record.record.page_refs
                else [
                    MaintenanceIssue(
                        code="contradiction-task-missing-page-refs",
                        message="Contradiction-linked tasks must persist page_refs.",
                        path=path,
                        record_id=record.record_id,
                        check_name="reference-integrity",
                    )
                ]
            ),
        ]

    if isinstance(record.record, MilestoneRecord):
        return [
            *_missing_ref_issues(
                refs=record.record.task_refs,
                valid_refs=valid_planning_ids["task"],
                code="missing-task-ref",
                message_prefix="Milestone references unknown task",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.decision_refs,
                valid_refs=valid_planning_ids["decision"],
                code="missing-decision-ref",
                message_prefix="Milestone references unknown decision",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.question_refs,
                valid_refs=valid_planning_ids["question"],
                code="missing-question-ref",
                message_prefix="Milestone references unknown question",
                path=path,
                record_id=record.record_id,
            ),
        ]

    if isinstance(record.record, DecisionRecord):
        return [
            *_missing_ref_issues(
                refs=record.record.supersedes,
                valid_refs=valid_planning_ids["decision"],
                code="missing-decision-ref",
                message_prefix="Decision supersedes unknown decision",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.source_refs,
                valid_refs=valid_source_ids,
                code="missing-source-ref",
                message_prefix="Decision references unknown source",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.related_tasks,
                valid_refs=valid_planning_ids["task"],
                code="missing-task-ref",
                message_prefix="Decision references unknown task",
                path=path,
                record_id=record.record_id,
            ),
            *_missing_ref_issues(
                refs=record.record.related_questions,
                valid_refs=valid_planning_ids["question"],
                code="missing-question-ref",
                message_prefix="Decision references unknown question",
                path=path,
                record_id=record.record_id,
            ),
        ]

    assert isinstance(record.record, QuestionRecord)
    issues = [
        *_missing_ref_issues(
            refs=record.record.source_refs,
            valid_refs=valid_source_ids,
            code="missing-source-ref",
            message_prefix="Question references unknown source",
            path=path,
            record_id=record.record_id,
        ),
        *_missing_ref_issues(
            refs=record.record.related_tasks,
            valid_refs=valid_planning_ids["task"],
            code="missing-task-ref",
            message_prefix="Question references unknown task",
            path=path,
            record_id=record.record_id,
        ),
        *_missing_ref_issues(
            refs=record.record.related_decisions,
            valid_refs=valid_planning_ids["decision"],
            code="missing-decision-ref",
            message_prefix="Question references unknown decision",
            path=path,
            record_id=record.record_id,
        ),
    ]
    if record.record.answer_page_ref is not None and not _is_existing_wiki_markdown_path(
        root, layout, record.record.answer_page_ref
    ):
        issues.append(
            MaintenanceIssue(
                code="missing-answer-page",
                message=(
                    "Question answer page ref does not point to an existing wiki markdown file: "
                    f"{record.record.answer_page_ref}"
                ),
                path=path,
                record_id=record.record_id,
                check_name="reference-integrity",
            )
        )
    return issues


def _linked_page_issues(
    root: Path, source_manifest: _SourceInventory, wiki_by_path: dict[str, _WikiPageInventory]
) -> list[MaintenanceIssue]:
    assert source_manifest.record is not None
    source = source_manifest.record
    issues: list[MaintenanceIssue] = []
    for linked_page in source.linked_pages:
        try:
            resolved = resolve_workspace_path(root, linked_page, context="Linked page")
        except ValueError as exc:
            issues.append(
                MaintenanceIssue(
                    code="invalid-linked-page-ref",
                    message=str(exc),
                    path=workspace_relative_path(root, source_manifest.manifest_path),
                    record_id=source.source_id,
                    check_name="reference-integrity",
                )
            )
            continue
        if not resolved.is_file():
            issues.append(
                MaintenanceIssue(
                    code="missing-linked-page",
                    message=f"Source manifest references missing linked page: {linked_page}",
                    path=workspace_relative_path(root, source_manifest.manifest_path),
                    record_id=source.source_id,
                    check_name="reference-integrity",
                )
            )
            continue
        normalized_linked_page = workspace_relative_path(root, resolved)
        page = wiki_by_path.get(normalized_linked_page)
        if page is None or page.frontmatter is None:
            continue
        if source.source_id in page.frontmatter.source_refs:
            continue
        issues.append(
            MaintenanceIssue(
                code="linked-page-source-mismatch",
                message=(
                    "Linked wiki page does not include the source ID in source_refs: "
                    f"{normalized_linked_page}"
                ),
                path=normalized_linked_page,
                record_id=source.source_id,
                check_name="reference-integrity",
            )
        )
    return issues


def _contradiction_issues(
    *,
    root: Path,
    page: _WikiPageInventory,
    wiki_by_id: dict[str, list[_WikiPageInventory]],
    valid_source_ids: set[str],
    valid_run_refs: set[str],
    valid_task_ids: set[str],
) -> list[MaintenanceIssue]:
    assert page.frontmatter is not None
    path = workspace_relative_path(root, page.path)
    issues: list[MaintenanceIssue] = []
    if page.frontmatter.review_state == "contested" and not page.frontmatter.contradictions:
        issues.append(
            MaintenanceIssue(
                code="contested-page-missing-contradictions",
                message="Contested pages must persist contradiction annotations.",
                path=path,
                record_id=page.frontmatter.page_id,
                check_name="reference-integrity",
            )
        )
    for contradiction in page.frontmatter.contradictions:
        for page_id in contradiction.related_page_ids:
            if page_id not in wiki_by_id:
                issues.append(
                    MaintenanceIssue(
                        code="missing-contradiction-page-ref",
                        message=f"Contradiction references unknown page: {page_id}",
                        path=path,
                        record_id=page.frontmatter.page_id,
                        check_name="reference-integrity",
                    )
                )
        for source_id in contradiction.related_source_ids:
            if source_id not in valid_source_ids:
                issues.append(
                    MaintenanceIssue(
                        code="missing-contradiction-source-ref",
                        message=f"Contradiction references unknown source: {source_id}",
                        path=path,
                        record_id=page.frontmatter.page_id,
                        check_name="reference-integrity",
                    )
                )
        if contradiction.review_task_id not in valid_task_ids:
            issues.append(
                MaintenanceIssue(
                    code="missing-contradiction-task-ref",
                    message=(
                        "Contradiction references unknown review task: "
                        f"{contradiction.review_task_id}"
                    ),
                    path=path,
                    record_id=page.frontmatter.page_id,
                    check_name="reference-integrity",
                )
            )
        for evidence in contradiction.evidence:
            if evidence.source_id is not None and evidence.source_id not in valid_source_ids:
                issues.append(
                    MaintenanceIssue(
                        code="missing-contradiction-source-ref",
                        message=(
                            "Contradiction evidence references unknown source: "
                            f"{evidence.source_id}"
                        ),
                        path=path,
                        record_id=page.frontmatter.page_id,
                        check_name="reference-integrity",
                    )
                )
            if evidence.page_id not in wiki_by_id:
                issues.append(
                    MaintenanceIssue(
                        code="missing-contradiction-page-ref",
                        message=(
                            f"Contradiction evidence references unknown page: {evidence.page_id}"
                        ),
                        path=path,
                        record_id=page.frontmatter.page_id,
                        check_name="reference-integrity",
                    )
                )
            if (
                evidence.run_id is not None
                and f"state/runs/{evidence.run_id}.json" not in valid_run_refs
            ):
                issues.append(
                    MaintenanceIssue(
                        code="missing-contradiction-run-ref",
                        message=f"Contradiction evidence references unknown run: {evidence.run_id}",
                        path=path,
                        record_id=page.frontmatter.page_id,
                        check_name="reference-integrity",
                    )
                )
        counterpart_ids = [
            page_id
            for page_id in contradiction.related_page_ids
            if page_id != page.frontmatter.page_id
        ]
        for counterpart_id in counterpart_ids:
            counterpart_entries = wiki_by_id.get(counterpart_id, [])
            if not counterpart_entries:
                continue
            counterpart = counterpart_entries[0]
            if counterpart.frontmatter is None:
                continue
            if any(
                item.contradiction_id == contradiction.contradiction_id
                for item in counterpart.frontmatter.contradictions
            ):
                continue
            issues.append(
                MaintenanceIssue(
                    code="missing-reciprocal-contradiction",
                    message=(
                        "Contradiction annotation is missing from counterpart page: "
                        f"{counterpart_id}"
                    ),
                    path=path,
                    record_id=page.frontmatter.page_id,
                    check_name="reference-integrity",
                )
            )
    return issues


def _provenance_link_issues(
    *,
    root: Path,
    path: str,
    record_id: str,
    links,
    valid_source_ids: set[str],
    valid_page_ids: set[str],
    check_name: str,
) -> list[MaintenanceIssue]:
    issues: list[MaintenanceIssue] = []
    for link in links:
        if link.source_id is not None and link.source_id not in valid_source_ids:
            issues.append(
                MaintenanceIssue(
                    code="missing-provenance-source-ref",
                    message=f"Provenance references unknown source: {link.source_id}",
                    path=path,
                    record_id=record_id,
                    check_name=check_name,
                )
            )
        if link.page_id is not None and link.page_id not in valid_page_ids:
            issues.append(
                MaintenanceIssue(
                    code="missing-provenance-page-ref",
                    message=f"Provenance references unknown page: {link.page_id}",
                    path=path,
                    record_id=record_id,
                    check_name=check_name,
                )
            )
        if link.path_ref is None:
            continue
        try:
            resolved = resolve_workspace_path(root, link.path_ref, context="Provenance path")
        except ValueError as exc:
            issues.append(
                MaintenanceIssue(
                    code="invalid-provenance-path-ref",
                    message=str(exc),
                    path=path,
                    record_id=record_id,
                    check_name=check_name,
                )
            )
            continue
        if not resolved.exists():
            issues.append(
                MaintenanceIssue(
                    code="missing-provenance-path",
                    message=f"Provenance path does not exist: {link.path_ref}",
                    path=path,
                    record_id=record_id,
                    check_name=check_name,
                )
            )
    return issues


def _existing_workspace_path_issues(
    *,
    root: Path,
    refs: list[str],
    code: str,
    message_prefix: str,
    path: str,
    record_id: str,
) -> list[MaintenanceIssue]:
    issues: list[MaintenanceIssue] = []
    for ref in refs:
        try:
            resolved = resolve_workspace_path(root, ref, context="Workspace path")
        except ValueError as exc:
            issues.append(
                MaintenanceIssue(
                    code="invalid-workspace-ref",
                    message=str(exc),
                    path=path,
                    record_id=record_id,
                    check_name="reference-integrity",
                )
            )
            continue
        if resolved.is_file():
            continue
        issues.append(
            MaintenanceIssue(
                code=code,
                message=f"{message_prefix}: {ref}",
                path=path,
                record_id=record_id,
                check_name="reference-integrity",
            )
        )
    return issues


def _source_summary_alignment_issues(
    *,
    root: Path,
    page: _WikiPageInventory,
    source_by_id: dict[str, list[_SourceInventory]],
) -> list[MaintenanceIssue]:
    if page.frontmatter is None or page.frontmatter.kind != "source-summary":
        return []

    page_id = page.frontmatter.page_id
    page_path = workspace_relative_path(root, page.path)
    issues: list[MaintenanceIssue] = []
    if page_id not in page.frontmatter.source_refs:
        issues.append(
            MaintenanceIssue(
                code="source-summary-source-ref-mismatch",
                message=f"Source summary page should reference its source ID: {page_id}",
                path=page_path,
                record_id=page_id,
                check_name="reference-integrity",
            )
        )
    source_entries = source_by_id.get(page_id, [])
    if not source_entries:
        return issues
    source = source_entries[0].record
    assert source is not None
    if page_path not in source.linked_pages:
        issues.append(
            MaintenanceIssue(
                code="source-summary-linked-page-mismatch",
                message="Source summary page is not listed in the source manifest linked_pages.",
                path=page_path,
                record_id=page_id,
                check_name="reference-integrity",
            )
        )
    if not any(
        link.source_id == page_id and link.role == "generated-from" and link.path_ref is not None
        for link in page.frontmatter.provenance_links
    ):
        issues.append(
            MaintenanceIssue(
                code="source-summary-provenance-mismatch",
                message="Source summary page provenance is missing its generated-from source link.",
                path=page_path,
                record_id=page_id,
                check_name="reference-integrity",
            )
        )
    if not any(
        link.page_id == page_id and link.role == "generated-page" and link.path_ref is not None
        for link in source.provenance_links
    ):
        issues.append(
            MaintenanceIssue(
                code="source-summary-provenance-mismatch",
                message="Source manifest provenance is missing the generated page link.",
                path=workspace_relative_path(root, source_entries[0].manifest_path),
                record_id=page_id,
                check_name="reference-integrity",
            )
        )
    return issues


def _normalize_issue_exception(root: Path, path: Path, exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__

    absolute_path = str(path)
    workspace_path = workspace_relative_path(root, path)
    patterns = [
        f"Wiki page {absolute_path} ",
        f"Planning record {absolute_path} ",
        f"{absolute_path} ",
        absolute_path,
    ]
    for pattern in patterns:
        if message.startswith(pattern):
            message = message.removeprefix(pattern)
            break

    message = message.replace(absolute_path, workspace_path)
    return _WHITESPACE_PATTERN.sub(" ", message).strip()


def _markdown_link_issues(
    root: Path, path: Path, body: str, *, check_name: str, record_id: str
) -> tuple[int, list[MaintenanceIssue]]:
    checked_count = 0
    issues: list[MaintenanceIssue] = []
    for target in _MARKDOWN_LINK_PATTERN.findall(body):
        resolved = _resolve_local_markdown_target(root, path, target.strip())
        if resolved is None:
            continue
        checked_count += 1
        if resolved.is_file():
            continue
        issues.append(
            MaintenanceIssue(
                code="broken-markdown-link",
                message=f"Markdown link target does not exist: {target}",
                path=workspace_relative_path(root, path),
                record_id=record_id,
                check_name=check_name,
            )
        )
    return checked_count, issues


def _resolve_local_markdown_target(root: Path, path: Path, target: str) -> Path | None:
    if not target or target.startswith("#"):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None
    candidate_text = parsed.path
    if not candidate_text.endswith(".md"):
        return None
    if candidate_text.startswith("/"):
        candidate = root / candidate_text.lstrip("/")
    else:
        candidate = path.parent / candidate_text
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
        return resolved
    except (OSError, RuntimeError, ValueError):
        return None


def _is_existing_wiki_markdown_path(
    root: Path, layout: ResolvedLayout, answer_page_ref: str
) -> bool:
    try:
        path = resolve_workspace_path(root, answer_page_ref, context="Answer page")
    except ValueError:
        return False
    if path.suffix != ".md" or not path.is_file():
        return False
    try:
        path.relative_to(layout.wiki_dir.resolve())
    except ValueError:
        return False
    return True
