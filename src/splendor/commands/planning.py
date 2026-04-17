"""Implementation for planning object commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import DecisionRecord, MilestoneRecord, QuestionRecord, TaskRecord
from splendor.utils.planning import (
    default_record_id,
    iter_planning_paths,
    parse_planning_markdown,
    planning_directory,
    planning_path,
    record_id_field,
    render_planning_markdown,
    write_planning_markdown,
)
from splendor.utils.time import utc_now_iso

_RECORD_MODELS = {
    "task": TaskRecord,
    "milestone": MilestoneRecord,
    "decision": DecisionRecord,
    "question": QuestionRecord,
}


@dataclass(frozen=True)
class CreatePlanningResult:
    kind: str
    record_id: str
    path: Path
    title: str


@dataclass(frozen=True)
class TaskListRow:
    task_id: str
    status: str
    priority: str
    title: str


@dataclass(frozen=True)
class MilestoneListRow:
    milestone_id: str
    status: str
    target_date: str | None
    title: str


def _model_for(kind: str):
    try:
        return _RECORD_MODELS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported planning kind: {kind}") from exc


def create_task(
    root: Path,
    title: str,
    *,
    record_id: str | None,
    status: str,
    priority: str,
    owner: str | None,
    milestone_refs: list[str],
    decision_refs: list[str],
    question_refs: list[str],
    depends_on: list[str],
    source_refs: list[str],
) -> CreatePlanningResult:
    timestamp = utc_now_iso()
    task_id = record_id or default_record_id("task", title)
    record = TaskRecord(
        task_id=task_id,
        title=title,
        status=status,
        priority=priority,
        milestone_refs=milestone_refs,
        decision_refs=decision_refs,
        question_refs=question_refs,
        owner=owner,
        created_at=timestamp,
        updated_at=timestamp,
        depends_on=depends_on,
        source_refs=source_refs,
    )
    return _write_record(root, record, title=title)


def create_milestone(
    root: Path,
    title: str,
    *,
    record_id: str | None,
    status: str,
    target_date: str | None,
    task_refs: list[str],
    decision_refs: list[str],
    question_refs: list[str],
) -> CreatePlanningResult:
    timestamp = utc_now_iso()
    milestone_id = record_id or default_record_id("milestone", title)
    record = MilestoneRecord(
        milestone_id=milestone_id,
        title=title,
        status=status,
        target_date=target_date,
        created_at=timestamp,
        updated_at=timestamp,
        task_refs=task_refs,
        decision_refs=decision_refs,
        question_refs=question_refs,
    )
    return _write_record(root, record, title=title)


def create_decision(
    root: Path,
    title: str,
    *,
    record_id: str | None,
    status: str,
    decided_at: str | None,
    supersedes: list[str],
    source_refs: list[str],
    related_tasks: list[str],
    related_questions: list[str],
) -> CreatePlanningResult:
    decision_id = record_id or default_record_id("decision", title)
    record = DecisionRecord(
        decision_id=decision_id,
        title=title,
        status=status,
        decided_at=decided_at,
        supersedes=supersedes,
        source_refs=source_refs,
        related_tasks=related_tasks,
        related_questions=related_questions,
    )
    return _write_record(root, record, title=title)


def create_question(
    root: Path,
    title: str,
    *,
    record_id: str | None,
    status: str,
    source_refs: list[str],
    related_tasks: list[str],
    related_decisions: list[str],
) -> CreatePlanningResult:
    timestamp = utc_now_iso()
    question_id = record_id or default_record_id("question", title)
    record = QuestionRecord(
        question_id=question_id,
        title=title,
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
        source_refs=source_refs,
        related_tasks=related_tasks,
        related_decisions=related_decisions,
    )
    return _write_record(root, record, title=title)


def list_tasks(
    root: Path,
    *,
    status: str | None,
    priority: str | None,
    milestone_ref: str | None,
) -> list[TaskListRow]:
    rows: list[TaskListRow] = []
    for record in _load_records(root, "task"):
        if status is not None and record.status != status:
            continue
        if priority is not None and record.priority != priority:
            continue
        if milestone_ref is not None and milestone_ref not in record.milestone_refs:
            continue
        rows.append(
            TaskListRow(
                task_id=record.task_id,
                status=record.status,
                priority=record.priority,
                title=record.title,
            )
        )
    return rows


def list_milestones(root: Path, *, status: str | None) -> list[MilestoneListRow]:
    rows: list[MilestoneListRow] = []
    for record in _load_records(root, "milestone"):
        if status is not None and record.status != status:
            continue
        rows.append(
            MilestoneListRow(
                milestone_id=record.milestone_id,
                status=record.status,
                target_date=record.target_date,
                title=record.title,
            )
        )
    return rows


def _write_record(root: Path, record, *, title: str) -> CreatePlanningResult:
    kind = record.kind
    layout = resolve_layout(root, load_config(root))
    record_id = getattr(record, record_id_field(kind))
    path = planning_path(layout, kind, record_id)
    if path.exists():
        raise ValueError(f"{kind.capitalize()} ID already exists: {record_id}")
    content = render_planning_markdown(record, title=title)
    write_planning_markdown(path, content)
    return CreatePlanningResult(kind=kind, record_id=record_id, path=path, title=title)


def _load_records(root: Path, kind: str):
    layout = resolve_layout(root, load_config(root))
    model = _model_for(kind)
    rows = []
    for path in iter_planning_paths(planning_directory(layout, kind)):
        rows.append(parse_planning_markdown(path, model))
    rows.sort(key=lambda record: getattr(record, record_id_field(kind)))
    return rows
