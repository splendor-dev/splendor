"""Deterministic planning object helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from splendor.layout import ResolvedLayout
from splendor.utils.fs import write_text_atomic

PlanningRecord = TypeVar("PlanningRecord", bound=BaseModel)

_KIND_TO_SUBDIR = {
    "task": "tasks",
    "milestone": "milestones",
    "decision": "decisions",
    "question": "questions",
}

_KIND_TO_ID_FIELD = {
    "task": "task_id",
    "milestone": "milestone_id",
    "decision": "decision_id",
    "question": "question_id",
}

_RECORD_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def planning_directory(layout: ResolvedLayout, kind: str) -> Path:
    try:
        subdir = _KIND_TO_SUBDIR[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported planning kind: {kind}") from exc
    return layout.planning_dir / subdir


def planning_path(layout: ResolvedLayout, kind: str, record_id: str) -> Path:
    validate_record_id(record_id)
    return planning_directory(layout, kind) / f"{record_id}.md"


def record_id_field(kind: str) -> str:
    try:
        return _KIND_TO_ID_FIELD[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported planning kind: {kind}") from exc


def default_record_id(kind: str, title: str) -> str:
    slug = slugify(title)
    if not slug:
        raise ValueError("Title must contain at least one ASCII letter or number")
    return f"{kind}-{slug}"


def slugify(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def validate_record_id(record_id: str) -> str:
    if not _RECORD_ID_PATTERN.fullmatch(record_id):
        raise ValueError(
            "Record ID must match ^[a-z0-9]+(?:-[a-z0-9]+)*$ and may not contain path separators"
        )
    return record_id


def render_frontmatter(record: BaseModel) -> str:
    return yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False).strip()


def render_planning_markdown(record: BaseModel, *, title: str) -> str:
    return f"---\n{render_frontmatter(record)}\n---\n\n# {title}\n\n## Notes\n\n"


def write_planning_markdown(path: Path, content: str) -> None:
    write_text_atomic(path, content)


def parse_planning_markdown(path: Path, model: type[PlanningRecord]) -> PlanningRecord:
    raw = path.read_text(encoding="utf-8")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError(f"Planning record {path} is missing YAML frontmatter")

    try:
        frontmatter_text, _body = normalized.removeprefix("---\n").split("\n---\n", maxsplit=1)
    except ValueError as exc:
        raise ValueError(f"Planning record {path} has malformed YAML frontmatter") from exc

    try:
        payload = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Planning record {path} has invalid YAML frontmatter") from exc

    try:
        return model.model_validate(payload or {})
    except ValidationError as exc:
        raise ValueError(f"Planning record {path} failed schema validation: {exc}") from exc


def iter_planning_paths(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path for path in directory.glob("*.md") if path.name != ".gitkeep" and path.is_file()
    )
