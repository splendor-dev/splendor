from pathlib import Path

import yaml

from splendor.commands.init import initialize_workspace
from splendor.commands.planning import (
    MilestoneListRow,
    TaskListRow,
    create_decision,
    create_milestone,
    create_question,
    create_task,
    list_milestones,
    list_tasks,
)
from splendor.schemas import DecisionRecord, MilestoneRecord, QuestionRecord, TaskRecord
from splendor.utils.planning import parse_planning_markdown


def parse_frontmatter(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    frontmatter_text, _body = raw.removeprefix("---\n").split("\n---\n", maxsplit=1)
    return yaml.safe_load(frontmatter_text)


def test_create_task_writes_markdown_with_frontmatter(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    result = create_task(
        tmp_path,
        "Write CLI docs",
        record_id=None,
        status="in_progress",
        priority="high",
        owner="codex",
        milestone_refs=["milestone-m3-p1"],
        decision_refs=["decision-markdown"],
        question_refs=["question-query"],
        depends_on=["task-roadmap"],
        source_refs=["src-123"],
    )

    payload = parse_frontmatter(result.path)
    assert payload["task_id"] == "task-write-cli-docs"
    assert payload["status"] == "in_progress"
    assert payload["priority"] == "high"
    assert payload["owner"] == "codex"
    assert payload["milestone_refs"] == ["milestone-m3-p1"]
    assert payload["decision_refs"] == ["decision-markdown"]
    assert payload["question_refs"] == ["question-query"]
    assert payload["depends_on"] == ["task-roadmap"]
    assert payload["source_refs"] == ["src-123"]
    body = result.path.read_text(encoding="utf-8")
    assert "# Write CLI docs" in body
    assert "## Notes" in body


def test_create_milestone_round_trips_with_schema(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    result = create_milestone(
        tmp_path,
        "Milestone 3 Slice",
        record_id="milestone-m3-p1",
        status="active",
        target_date="2026-05-01",
        task_refs=["task-write-cli-docs"],
        decision_refs=["decision-markdown"],
        question_refs=["question-query"],
    )

    record = parse_planning_markdown(result.path, MilestoneRecord)
    assert record.milestone_id == "milestone-m3-p1"
    assert record.status == "active"
    assert record.target_date == "2026-05-01"
    assert record.task_refs == ["task-write-cli-docs"]


def test_create_decision_round_trips_with_schema(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    result = create_decision(
        tmp_path,
        "Use planning markdown",
        record_id=None,
        status="accepted",
        decided_at="2026-04-17",
        supersedes=["decision-old"],
        source_refs=["src-123"],
        related_tasks=["task-write-cli-docs"],
        related_questions=["question-query"],
    )

    record = parse_planning_markdown(result.path, DecisionRecord)
    assert record.decision_id == "decision-use-planning-markdown"
    assert record.status == "accepted"
    assert record.decided_at == "2026-04-17"
    assert record.related_tasks == ["task-write-cli-docs"]


def test_create_question_round_trips_with_schema(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    result = create_question(
        tmp_path,
        "How should query ranking work",
        record_id=None,
        status="open",
        source_refs=["src-123"],
        related_tasks=["task-write-cli-docs"],
        related_decisions=["decision-use-planning-markdown"],
    )

    record = parse_planning_markdown(result.path, QuestionRecord)
    assert record.question_id == "question-how-should-query-ranking-work"
    assert record.status == "open"
    assert record.related_decisions == ["decision-use-planning-markdown"]


def test_list_tasks_is_sorted_and_filtered(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_task(
        tmp_path,
        "Write CLI docs",
        record_id="task-b",
        status="todo",
        priority="high",
        owner=None,
        milestone_refs=["milestone-m3-p1"],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )
    create_task(
        tmp_path,
        "Ship query",
        record_id="task-a",
        status="done",
        priority="low",
        owner=None,
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        depends_on=[],
        source_refs=[],
    )

    rows = list_tasks(tmp_path, status="todo", priority="high", milestone_ref="milestone-m3-p1")

    assert rows == [
        TaskListRow(
            task_id="task-b",
            status="todo",
            priority="high",
            title="Write CLI docs",
        )
    ]


def test_list_milestones_is_sorted_and_filtered(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_milestone(
        tmp_path,
        "Milestone 4",
        record_id="milestone-b",
        status="planned",
        target_date=None,
        task_refs=[],
        decision_refs=[],
        question_refs=[],
    )
    create_milestone(
        tmp_path,
        "Milestone 3",
        record_id="milestone-a",
        status="active",
        target_date="2026-05-01",
        task_refs=[],
        decision_refs=[],
        question_refs=[],
    )

    rows = list_milestones(tmp_path, status="active")

    assert rows == [
        MilestoneListRow(
            milestone_id="milestone-a",
            status="active",
            target_date="2026-05-01",
            title="Milestone 3",
        )
    ]


def test_parse_planning_markdown_rejects_invalid_frontmatter(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    task_path = tmp_path / "planning" / "tasks" / "task-invalid.md"
    task_path.write_text(
        "---\nkind: task\ntask_id: task-invalid\ntitle: Broken\nbogus: true\n---\n",
        encoding="utf-8",
    )

    try:
        parse_planning_markdown(task_path, TaskRecord)
    except ValueError as exc:
        assert "failed schema validation" in str(exc)
    else:
        raise AssertionError("Expected planning frontmatter validation failure")
