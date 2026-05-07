from pathlib import Path

import pytest

from splendor import __version__
from splendor.cli import main
from splendor.commands.source_forget import (
    SourceForgetAction,
    _apply_source_forget,
    forget_sources,
)
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import RunRecord
from splendor.state.runtime import write_run_record
from splendor.state.source_registry import load_source_record, write_source_record


def test_source_forget_keeps_run_record_referenced_by_remaining_source(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    forgotten_path = tmp_path / "forgotten.md"
    forgotten_path.write_text("# Forgotten\n\nHas a run.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(forgotten_path)])
    main(["--root", str(tmp_path), "ingest", "--pending", "--apply"])
    forgotten_manifest = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    forgotten = load_source_record(forgotten_manifest)
    assert forgotten.last_run_id is not None

    remaining_path = tmp_path / "remaining.md"
    remaining_path.write_text("# Remaining\n\nKeeps the run ID alive.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(remaining_path)])
    remaining_manifest = next(
        path
        for path in (tmp_path / "state" / "manifests" / "sources").glob("*.json")
        if path != forgotten_manifest
    )
    remaining = load_source_record(remaining_manifest)
    write_source_record(
        remaining_manifest,
        remaining.model_copy(update={"generated_by_run_ids": [forgotten.last_run_id]}),
    )
    run_path = tmp_path / "state" / "runs" / f"{forgotten.last_run_id}.json"
    capsys.readouterr()

    result = forget_sources(tmp_path, selector=forgotten.source_id, apply=True)

    assert not forgotten_manifest.exists()
    assert run_path.exists()
    assert {(action.kind, action.path, action.reason) for action in result.skipped} >= {
        (
            "run_record",
            f"state/runs/{forgotten.last_run_id}.json",
            "run record is referenced by remaining workspace state",
        )
    }
    assert {
        (residual.kind, residual.path, residual.ref_id) for residual in result.residual_references
    } >= {
        (
            "source_run_ref",
            f"state/manifests/sources/{remaining.source_id}.json",
            forgotten.last_run_id,
        )
    }


def test_source_forget_apply_preflights_targets_before_mutating(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init"])
    manifest = tmp_path / "state" / "manifests" / "sources" / "src-manual.json"
    manifest.write_text("{}\n", encoding="utf-8")
    directory_target = tmp_path / "derived" / "parsed" / "not-a-file"
    directory_target.mkdir(parents=True)
    actions = [
        SourceForgetAction(
            kind="source_manifest",
            path="state/manifests/sources/src-manual.json",
            source_id="src-manual",
            status="planned",
        ),
        SourceForgetAction(
            kind="derived_artifact",
            path="derived/parsed/not-a-file",
            source_id="src-manual",
            status="planned",
        ),
    ]

    with pytest.raises(ValueError, match="not a removable file"):
        _apply_source_forget(tmp_path, actions)

    assert manifest.exists()
    assert directory_target.exists()


def test_source_forget_reports_run_id_residuals_from_wiki_and_run_records(
    tmp_path: Path, capsys
) -> None:
    main(["--root", str(tmp_path), "init"])
    source_path = tmp_path / "brief.md"
    source_path.write_text("# Brief\n\nRun references.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "add-source", str(source_path)])
    main(["--root", str(tmp_path), "ingest", "--pending", "--apply"])
    manifest = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source = load_source_record(manifest)
    assert source.last_run_id is not None
    layout = resolve_layout(tmp_path, load_config(tmp_path))
    topic_path = tmp_path / "wiki" / "topics" / "run-ref.md"
    topic_path.parent.mkdir(parents=True, exist_ok=True)
    topic_path.write_text(f"body mentions {source.last_run_id}\n", encoding="utf-8")
    write_run_record(
        layout.runs_dir / "run-followup.json",
        RunRecord(
            run_id="run-followup",
            job_id="followup",
            job_type="maintenance",
            started_at="2026-05-05T00:00:00Z",
            finished_at="2026-05-05T00:00:01Z",
            status="succeeded",
            pipeline_version=__version__,
            provenance_links=[{"run_id": source.last_run_id, "role": "supports"}],
        ),
    )
    capsys.readouterr()

    result = forget_sources(tmp_path, selector=source.source_id)

    assert {
        (residual.kind, residual.path, residual.ref_id) for residual in result.residual_references
    } >= {
        ("wiki_text", "wiki/topics/run-ref.md", source.last_run_id),
        ("run_provenance", "state/runs/run-followup.json", source.last_run_id),
    }
