"""Runtime record persistence for queue items and runs."""

from __future__ import annotations

import json
from pathlib import Path

from splendor.layout import ResolvedLayout
from splendor.schemas import QueueItemRecord, RunRecord
from splendor.utils.fs import ensure_directory, write_text_atomic


def queue_item_path_for(layout: ResolvedLayout, job_id: str) -> Path:
    return layout.queue_dir / f"{job_id}.json"


def run_record_path_for(layout: ResolvedLayout, run_id: str) -> Path:
    return layout.runs_dir / f"{run_id}.json"


def load_queue_item(path: Path) -> QueueItemRecord:
    return QueueItemRecord.model_validate_json(path.read_text(encoding="utf-8"))


def load_run_record(path: Path) -> RunRecord:
    return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))


def write_queue_item(path: Path, record: QueueItemRecord) -> Path:
    ensure_directory(path.parent)
    write_text_atomic(
        path,
        json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    return path


def write_run_record(path: Path, record: RunRecord) -> Path:
    ensure_directory(path.parent)
    write_text_atomic(
        path,
        json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    return path
