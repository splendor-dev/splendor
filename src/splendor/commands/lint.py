"""Implementation for `splendor lint`."""

from __future__ import annotations

import re
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

    for record in inventory.planning_records:
        if record.record is None or record.record_id is None:
            continue
        checked_count += _planning_ref_count(record.record)
        issues.extend(
            _planning_ref_issues(root, layout, record, valid_planning_ids, valid_source_ids)
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

    return _LintCheckResult(checked_count=checked_count, issues=issues)


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
