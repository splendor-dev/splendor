"""Pointer artifact persistence and validation helpers."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from splendor.schemas import SourcePointerArtifact
from splendor.utils.fs import write_text_atomic


def pointer_artifact_relpath(source_id: str) -> str:
    return f"raw/sources/{source_id}/pointer.json"


def load_source_pointer(path: Path) -> SourcePointerArtifact:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        msg = f"Pointer artifact is missing: {path}"
        raise ValueError(msg) from None

    try:
        return SourcePointerArtifact.model_validate_json(raw)
    except ValidationError as exc:
        if any(error["type"] == "json_invalid" for error in exc.errors()):
            msg = f"Pointer artifact is not valid JSON: {path}"
            raise ValueError(msg) from exc
        msg = f"Pointer artifact is invalid: {path}"
        raise ValueError(msg) from exc


def write_source_pointer(path: Path, artifact: SourcePointerArtifact) -> Path:
    write_text_atomic(
        path,
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    return path
