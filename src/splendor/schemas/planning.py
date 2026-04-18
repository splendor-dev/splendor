"""Planning object schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from splendor.schemas.common import StrictRecord


class TaskRecord(StrictRecord):
    kind: Literal["task"] = "task"
    task_id: str
    title: str
    status: Literal["todo", "in_progress", "blocked", "done"] = "todo"
    priority: Literal["low", "medium", "high"] = "medium"
    milestone_refs: list[str] = Field(default_factory=list)
    decision_refs: list[str] = Field(default_factory=list)
    question_refs: list[str] = Field(default_factory=list)
    owner: str | None = None
    created_at: str
    updated_at: str
    depends_on: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class MilestoneRecord(StrictRecord):
    kind: Literal["milestone"] = "milestone"
    milestone_id: str
    title: str
    status: Literal["planned", "active", "completed"] = "planned"
    target_date: str | None = None
    created_at: str
    updated_at: str
    task_refs: list[str] = Field(default_factory=list)
    decision_refs: list[str] = Field(default_factory=list)
    question_refs: list[str] = Field(default_factory=list)


class DecisionRecord(StrictRecord):
    kind: Literal["decision"] = "decision"
    decision_id: str
    title: str
    status: Literal["proposed", "accepted", "superseded"] = "proposed"
    decided_at: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    related_tasks: list[str] = Field(default_factory=list)
    related_questions: list[str] = Field(default_factory=list)


class QuestionRecord(StrictRecord):
    kind: Literal["question"] = "question"
    question_id: str
    title: str
    status: Literal["open", "answered", "deferred"] = "open"
    created_at: str
    updated_at: str
    answer_page_ref: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    related_tasks: list[str] = Field(default_factory=list)
    related_decisions: list[str] = Field(default_factory=list)
