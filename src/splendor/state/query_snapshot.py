"""Persistence helpers for the latest query snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from splendor.layout import ResolvedLayout
from splendor.schemas import QuerySnapshot
from splendor.utils.fs import ensure_directory, write_text_atomic


def last_query_path_for(layout: ResolvedLayout) -> Path:
    return layout.queries_dir / "last-query.json"


def load_query_snapshot(path: Path) -> QuerySnapshot:
    try:
        return QuerySnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("No saved query snapshot found. Run `splendor query` first.") from exc
    except ValidationError as exc:
        raise ValueError(
            "Saved query snapshot is invalid. Run `splendor query` again to regenerate it."
        ) from exc


def write_query_snapshot(path: Path, snapshot: QuerySnapshot) -> Path:
    ensure_directory(path.parent)
    write_text_atomic(
        path,
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    return path
