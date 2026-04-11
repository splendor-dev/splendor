import json
from pathlib import Path

import pytest
import yaml

from splendor.commands.add_source import add_source
from splendor.commands.ingest import ingest_source
from splendor.commands.init import initialize_workspace
from splendor.schemas import KnowledgePageFrontmatter, QueueItemRecord, RunRecord
from splendor.state.runtime import load_queue_item, load_run_record
from splendor.state.source_registry import load_source_record


def parse_frontmatter(page_path: Path) -> tuple[KnowledgePageFrontmatter, str]:
    raw = page_path.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    frontmatter_text, body = raw.removeprefix("---\n").split("\n---\n", maxsplit=1)
    frontmatter = KnowledgePageFrontmatter.model_validate(yaml.safe_load(frontmatter_text))
    return frontmatter, body


def test_ingest_source_happy_path(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.no_op is False
    assert result.page_path is not None and result.page_path.exists()
    assert result.queue_path is not None and result.queue_path.exists()
    assert result.run_path is not None and result.run_path.exists()

    frontmatter, body = parse_frontmatter(result.page_path)
    assert frontmatter.kind == "source-summary"
    assert frontmatter.page_id == added.source_id
    assert frontmatter.source_refs == [added.source_id]
    assert frontmatter.generated_by_run_ids == [result.run_id]
    assert frontmatter.confidence == 1.0
    assert "## Source" in body
    assert "## Summary" in body
    assert "## Key Facts" in body
    assert "## Extract" in body
    assert "## Provenance" in body

    queue_record = load_queue_item(result.queue_path)
    assert isinstance(queue_record, QueueItemRecord)
    assert queue_record.status == "done"
    assert queue_record.job_type == "ingest_source"

    run_record = load_run_record(result.run_path)
    assert isinstance(run_record, RunRecord)
    assert run_record.status == "succeeded"
    assert result.page_path.relative_to(tmp_path).as_posix() in run_record.output_refs

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "ingested"
    assert source_record.last_run_id == result.run_id
    assert result.page_path.relative_to(tmp_path).as_posix() in source_record.linked_pages

    index_content = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert f"(`{added.source_id}`)" in index_content
    log_content = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert added.source_id in log_content
    assert result.run_id in log_content


def test_ingest_source_is_idempotent_when_current_pipeline_already_succeeded(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    first = ingest_source(tmp_path, added.source_id)
    second = ingest_source(tmp_path, added.source_id)

    assert first.no_op is False
    assert second.no_op is True
    assert second.run_id is None
    assert second.queue_path is None
    assert len(list((tmp_path / "state" / "runs").glob("*.json"))) == 1
    index_content = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert index_content.count(f"(`{added.source_id}`)") == 1
    log_content = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert log_content.count(f"Ingested source `{added.source_id}`") == 1


def test_ingest_source_recreates_missing_page_without_duplicate_index_entries(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    first = ingest_source(tmp_path, added.source_id)
    assert first.page_path is not None
    first.page_path.unlink()

    second = ingest_source(tmp_path, added.source_id)

    assert second.no_op is False
    assert second.page_path is not None and second.page_path.exists()
    index_content = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    assert index_content.count(f"(`{added.source_id}`)") == 1
    log_content = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")
    assert log_content.count(f"Ingested source `{added.source_id}`") == 2


def test_ingest_source_no_op_uses_configured_wiki_layout(tmp_path: Path) -> None:
    (tmp_path / "splendor.yaml").write_text(
        "schema_version: '1'\nproject_name: custom\nlayout:\n  wiki_dir: knowledge\n",
        encoding="utf-8",
    )
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    first = ingest_source(tmp_path, added.source_id)
    second = ingest_source(tmp_path, added.source_id)

    assert first.page_path == tmp_path / "knowledge" / "sources" / f"{added.source_id}.md"
    assert second.no_op is True
    source_record = load_source_record(added.manifest_path)
    assert f"knowledge/sources/{added.source_id}.md" in source_record.linked_pages


def test_ingest_source_rejects_unsupported_type(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "diagram.bin"
    source.write_bytes(b"\x00\x01\x02")
    added = add_source(tmp_path, source)

    with pytest.raises(ValueError, match="Unsupported source type"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert load_queue_item(queue_path).status == "failed"
    assert len(run_paths) == 1
    assert load_run_record(run_paths[0]).status == "failed"
    assert not (tmp_path / "wiki" / "sources" / f"{added.source_id}.md").exists()


def test_ingest_source_rejects_invalid_utf8_text(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "broken.txt"
    source.write_bytes(b"\xff\xfe\xfa")
    added = add_source(tmp_path, source)

    with pytest.raises(ValueError, match="not valid UTF-8"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    assert load_queue_item(queue_path).status == "failed"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert len(run_paths) == 1
    assert load_run_record(run_paths[0]).status == "failed"


def test_ingest_source_requires_workspace_index_file(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    (tmp_path / "wiki" / "index.md").unlink()

    with pytest.raises(RuntimeError, match="missing required wiki files"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "registered"
    assert list((tmp_path / "state" / "queue").glob("*.json")) == []
    assert list((tmp_path / "state" / "runs").glob("*.json")) == []


def test_ingest_source_requires_workspace_log_file(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    (tmp_path / "wiki" / "log.md").unlink()

    with pytest.raises(RuntimeError, match="missing required wiki files"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "registered"
    assert list((tmp_path / "state" / "queue").glob("*.json")) == []
    assert list((tmp_path / "state" / "runs").glob("*.json")) == []


def test_ingest_source_missing_source_id_does_not_create_runtime_state(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    with pytest.raises(FileNotFoundError, match="Unknown source ID"):
        ingest_source(tmp_path, "src-missing")

    assert list((tmp_path / "state" / "queue").glob("*.json")) == []
    assert list((tmp_path / "state" / "runs").glob("*.json")) == []


def test_ingest_source_validates_stored_copy_checksum(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    manifest = json.loads(added.manifest_path.read_text(encoding="utf-8"))
    stored_path = tmp_path / manifest["path"]
    stored_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Stored source checksum mismatch"):
        ingest_source(tmp_path, added.source_id)


def test_ingest_source_extract_uses_safe_fence_for_backticks(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\n```python\nprint('hi')\n```\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    page_content = result.page_path.read_text(encoding="utf-8")
    assert "````text" in page_content
    assert "\n````\n\n## Provenance" in page_content


def test_ingest_source_rolls_back_wiki_on_success_commit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    original_index = (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8")
    original_log = (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8")

    import splendor.commands.ingest as ingest_module

    original_write_source_record = ingest_module.write_source_record

    def fail_on_success_write(path: Path, record) -> Path:
        if getattr(record, "status", None) == "ingested":
            raise OSError("disk full")
        return original_write_source_record(path, record)

    monkeypatch.setattr(ingest_module, "write_source_record", fail_on_success_write)

    with pytest.raises(RuntimeError, match="committing outputs"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "registered"
    assert source_record.last_run_id is None
    assert (tmp_path / "wiki" / "index.md").read_text(encoding="utf-8") == original_index
    assert (tmp_path / "wiki" / "log.md").read_text(encoding="utf-8") == original_log
    assert not (tmp_path / "wiki" / "sources" / f"{added.source_id}.md").exists()
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert load_queue_item(queue_path).status == "failed"
    assert len(run_paths) == 1
    assert load_run_record(run_paths[0]).status == "failed"
