import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from pypdf import PdfWriter

import splendor.utils.contradictions as contradictions_module
from conftest import write_text_pdf
from splendor.commands.add_source import add_source
from splendor.commands.ingest import (
    drain_pending_ingest_jobs,
    enqueue_ingest_job,
    ingest_source,
    run_ingest_job,
)
from splendor.commands.init import initialize_workspace
from splendor.config import load_config, write_config
from splendor.schemas import KnowledgePageFrontmatter, QueueItemRecord, RunRecord
from splendor.schemas.types import SummaryMode
from splendor.state.runtime import load_queue_item, load_run_record, write_queue_item
from splendor.state.source_pointer import load_source_pointer, write_source_pointer
from splendor.state.source_registry import load_source_record, write_source_record


def parse_frontmatter(page_path: Path) -> tuple[KnowledgePageFrontmatter, str]:
    raw = page_path.read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    frontmatter_text, body = raw.removeprefix("---\n").split("\n---\n", maxsplit=1)
    frontmatter = KnowledgePageFrontmatter.model_validate(yaml.safe_load(frontmatter_text))
    return frontmatter, body


def update_summary_modes(
    root: Path,
    *,
    in_repo: SummaryMode | None = None,
    external: SummaryMode | None = None,
) -> None:
    config = load_config(root)
    if in_repo is not None:
        config.sources.summarize_in_repo_extracts_as = in_repo
    if external is not None:
        config.sources.summarize_external_extracts_as = external
    write_config(root, config)


def extract_rendered_extract_section(body: str) -> str:
    after_heading = body.split("## Extract\n\n", maxsplit=1)[1]
    return after_heading.split("\n\n## ", maxsplit=1)[0]


def enable_sidecar_ocr(root: Path, *, suffix: str = ".ocr.txt") -> None:
    config = load_config(root)
    config.sources.ocr_enabled = True
    config.sources.ocr_provider = "sidecar-text"
    config.sources.ocr_sidecar_suffix = suffix
    write_config(root, config)


def rewrite_pointer(
    root: Path,
    source_id: str,
    *,
    source_ref: str = "brief.md",
    checksum: str,
) -> Path:
    pointer_path = root / "raw" / "sources" / source_id / "pointer.json"
    artifact = load_source_pointer(pointer_path)
    updated = artifact.model_copy(update={"source_ref": source_ref, "checksum": checksum})
    write_source_pointer(pointer_path, updated)
    return pointer_path


def rewrite_symlink(root: Path, source_id: str, target: Path) -> Path:
    symlink_path = root / "raw" / "sources" / source_id / "brief.md"
    if symlink_path.exists() or symlink_path.is_symlink():
        symlink_path.unlink()
    symlink_path.parent.mkdir(parents=True, exist_ok=True)
    symlink_path.symlink_to(target)
    return symlink_path


def test_ingest_source_happy_path(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="copy")

    result = ingest_source(tmp_path, added.source_id)

    assert result.no_op is False
    assert result.page_path is not None and result.page_path.exists()
    assert result.queue_path is not None and result.queue_path.exists()
    assert result.run_path is not None and result.run_path.exists()

    frontmatter, body = parse_frontmatter(result.page_path)
    assert frontmatter.kind == "source-summary"
    assert frontmatter.page_id == added.source_id
    assert frontmatter.review_state == "machine-generated"
    assert frontmatter.source_refs == [added.source_id]
    assert frontmatter.generated_by_run_ids == [result.run_id]
    assert frontmatter.last_generated_at is not None
    assert any(link.source_id == added.source_id for link in frontmatter.provenance_links)
    assert any(link.run_id == result.run_id for link in frontmatter.provenance_links)
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
    assert run_record.source_ids == [added.source_id]
    assert run_record.page_ids == [added.source_id]
    assert run_record.page_refs == [result.page_path.relative_to(tmp_path).as_posix()]
    assert any(link.page_id == added.source_id for link in run_record.provenance_links)
    assert result.page_path.relative_to(tmp_path).as_posix() in run_record.output_refs

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "ingested"
    assert source_record.last_run_id == result.run_id
    assert source_record.generated_by_run_ids == [result.run_id]
    assert any(link.page_id == added.source_id for link in source_record.provenance_links)
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
    added = add_source(tmp_path, source, storage_mode="copy")

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
    added = add_source(tmp_path, source, storage_mode="copy")

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
    added = add_source(tmp_path, source, storage_mode="copy")

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
    run_record = load_run_record(run_paths[0])
    assert run_record.status == "failed"
    assert run_record.source_ids == [added.source_id]
    assert run_record.page_ids == []
    assert run_record.output_refs == []
    assert not (tmp_path / "wiki" / "sources" / f"{added.source_id}.md").exists()


def test_ingest_source_pdf_writes_parsed_artifact_and_links_manifest(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "dispatch.pdf"
    write_text_pdf(
        source,
        [
            "Splendor PDF dispatch claim",
            "Text-bearing PDF extraction works.",
        ],
    )
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    frontmatter, body = parse_frontmatter(result.page_path)
    assert frontmatter.tags == ["source-summary", "pdf"]
    assert "Parsed artifact: `derived/parsed/" in body
    assert "Splendor PDF dispatch claim" in body
    assert "Text-bearing PDF extraction works." in body

    parsed_artifact = tmp_path / "derived" / "parsed" / f"{added.source_id}.txt"
    assert parsed_artifact.read_text(encoding="utf-8") == (
        "Splendor PDF dispatch claim\nText-bearing PDF extraction works.\n"
    )

    source_record = load_source_record(added.manifest_path)
    artifact_ref = parsed_artifact.relative_to(tmp_path).as_posix()
    assert source_record.source_ref == "dispatch.pdf"
    assert source_record.storage_mode == "none"
    assert source_record.derived_artifacts == [artifact_ref]
    assert any(link.path_ref == artifact_ref for link in source_record.provenance_links)

    run_record = load_run_record(result.run_path)
    assert artifact_ref in run_record.output_refs
    assert any(
        link.path_ref == artifact_ref
        and link.source_id == added.source_id
        and link.run_id == result.run_id
        and link.role == "output"
        for link in run_record.provenance_links
    )


def test_ingest_source_pdf_recreates_missing_parsed_artifact(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "dispatch.pdf"
    write_text_pdf(source, ["Splendor PDF dispatch claim"])
    added = add_source(tmp_path, source)

    first = ingest_source(tmp_path, added.source_id)
    parsed_artifact = tmp_path / "derived" / "parsed" / f"{added.source_id}.txt"
    parsed_artifact.unlink()

    second = ingest_source(tmp_path, added.source_id)

    assert first.no_op is False
    assert second.no_op is False
    assert parsed_artifact.read_text(encoding="utf-8") == "Splendor PDF dispatch claim\n"


def test_ingest_source_pdf_without_text_fails_without_ocr(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as handle:
        writer.write(handle)
    added = add_source(tmp_path, source)

    with pytest.raises(ValueError, match="OCR/image extraction is not configured"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.derived_artifacts == []
    assert not (tmp_path / "derived" / "parsed" / f"{added.source_id}.txt").exists()
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "failed"
    assert "OCR/image extraction is not configured" in (queue_record.last_error or "")


def test_ingest_source_image_requires_configured_ocr(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "diagram.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    added = add_source(tmp_path, source)

    with pytest.raises(ValueError, match="^OCR/image extraction is not configured: diagram.png$"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.derived_artifacts == []
    assert not (tmp_path / "derived" / "ocr" / f"{added.source_id}.txt").exists()
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "failed"
    assert queue_record.last_error == "OCR/image extraction is not configured: diagram.png"


def test_ingest_source_image_writes_ocr_artifact_and_links_manifest(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    enable_sidecar_ocr(tmp_path)
    source = tmp_path / "diagram.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    Path(f"{source}.ocr.txt").write_text(
        "# Diagram Notes\n\nOCR claim from image source.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    frontmatter, body = parse_frontmatter(result.page_path)
    assert frontmatter.tags == ["source-summary", "png"]
    assert "OCR artifact: `derived/ocr/" in body
    assert "OCR claim from image source." in body
    assert "Parsed artifact:" not in body

    ocr_artifact = tmp_path / "derived" / "ocr" / f"{added.source_id}.txt"
    metadata_artifact = tmp_path / "derived" / "metadata" / f"{added.source_id}.ocr.json"
    assert ocr_artifact.read_text(encoding="utf-8") == (
        "# Diagram Notes\n\nOCR claim from image source.\n"
    )
    metadata = json.loads(metadata_artifact.read_text(encoding="utf-8"))
    assert metadata["kind"] == "ocr_metadata"
    assert metadata["sidecar_ref"] == "diagram.png.ocr.txt"
    assert metadata["sidecar_checksum"]

    source_record = load_source_record(added.manifest_path)
    artifact_ref = ocr_artifact.relative_to(tmp_path).as_posix()
    metadata_ref = metadata_artifact.relative_to(tmp_path).as_posix()
    assert source_record.source_ref == "diagram.png"
    assert source_record.storage_mode == "none"
    assert source_record.derived_artifacts == sorted([artifact_ref, metadata_ref])
    assert any(link.path_ref == artifact_ref for link in source_record.provenance_links)

    run_record = load_run_record(result.run_path)
    assert "diagram.png.ocr.txt" in run_record.input_refs
    assert artifact_ref in run_record.output_refs
    assert metadata_ref in run_record.output_refs
    assert any(
        link.path_ref == artifact_ref
        and link.source_id == added.source_id
        and link.run_id == result.run_id
        and link.role == "output"
        for link in run_record.provenance_links
    )


def test_ingest_source_image_fails_when_configured_ocr_sidecar_missing(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    enable_sidecar_ocr(tmp_path)
    source = tmp_path / "diagram.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    added = add_source(tmp_path, source)

    with pytest.raises(ValueError, match="^OCR sidecar text is missing for diagram.png"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.derived_artifacts == []
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "failed"
    assert (
        queue_record.last_error
        == "OCR sidecar text is missing for diagram.png: diagram.png.ocr.txt"
    )


def test_ingest_source_image_fails_when_ocr_sidecar_is_invalid_utf8(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    enable_sidecar_ocr(tmp_path)
    source = tmp_path / "diagram.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    Path(f"{source}.ocr.txt").write_bytes(b"\xff\xfe\xfa")
    added = add_source(tmp_path, source)

    with pytest.raises(ValueError, match="^OCR sidecar text is not valid UTF-8"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.derived_artifacts == []
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "failed"
    assert queue_record.last_error == "OCR sidecar text is not valid UTF-8: diagram.png.ocr.txt"


def test_ingest_source_image_fails_when_ocr_sidecar_is_empty(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    enable_sidecar_ocr(tmp_path)
    source = tmp_path / "diagram.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    Path(f"{source}.ocr.txt").write_text("  \n\t\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    with pytest.raises(ValueError, match="^OCR sidecar text is empty for diagram.png"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.derived_artifacts == []
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "failed"
    assert (
        queue_record.last_error == "OCR sidecar text is empty for diagram.png: diagram.png.ocr.txt"
    )


def test_ingest_source_image_only_pdf_can_use_configured_ocr_sidecar(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    enable_sidecar_ocr(tmp_path)
    source = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with source.open("wb") as handle:
        writer.write(handle)
    Path(f"{source}.ocr.txt").write_text("OCR text from scanned PDF.\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    frontmatter, body = parse_frontmatter(result.page_path)
    assert frontmatter.tags == ["source-summary", "pdf"]
    assert "OCR artifact: `derived/ocr/" in body
    assert "Parsed artifact:" not in body
    assert "OCR text from scanned PDF." in body
    assert (tmp_path / "derived" / "ocr" / f"{added.source_id}.txt").is_file()
    assert not (tmp_path / "derived" / "parsed" / f"{added.source_id}.txt").exists()


def test_ingest_source_ocr_sidecar_change_forces_reingest(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    enable_sidecar_ocr(tmp_path)
    source = tmp_path / "diagram.png"
    sidecar = Path(f"{source}.ocr.txt")
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    sidecar.write_text("Initial OCR text.\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    first = ingest_source(tmp_path, added.source_id)
    sidecar.write_text("Updated OCR text.\n", encoding="utf-8")
    second = ingest_source(tmp_path, added.source_id)

    assert first.no_op is False
    assert second.no_op is False
    assert first.run_id != second.run_id
    ocr_artifact = tmp_path / "derived" / "ocr" / f"{added.source_id}.txt"
    assert ocr_artifact.read_text(encoding="utf-8") == "Updated OCR text.\n"
    metadata_artifact = tmp_path / "derived" / "metadata" / f"{added.source_id}.ocr.json"
    metadata = json.loads(metadata_artifact.read_text(encoding="utf-8"))
    assert metadata["sidecar_ref"] == "diagram.png.ocr.txt"


def test_ingest_source_ocr_sidecar_change_forces_reingest_with_custom_metadata_dir(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.layout.derived_metadata_dir = "custom-derived/metadata"
    config.sources.ocr_enabled = True
    config.sources.ocr_provider = "sidecar-text"
    write_config(tmp_path, config)
    source = tmp_path / "diagram.png"
    sidecar = Path(f"{source}.ocr.txt")
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    sidecar.write_text("Initial OCR text.\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    first = ingest_source(tmp_path, added.source_id)
    sidecar.write_text("Updated OCR text.\n", encoding="utf-8")
    second = ingest_source(tmp_path, added.source_id)

    assert first.no_op is False
    assert second.no_op is False
    metadata_artifact = tmp_path / "custom-derived" / "metadata" / f"{added.source_id}.ocr.json"
    assert metadata_artifact.is_file()
    manifest = load_source_record(added.manifest_path)
    assert metadata_artifact.relative_to(tmp_path).as_posix() in manifest.derived_artifacts
    ocr_artifact = tmp_path / "derived" / "ocr" / f"{added.source_id}.txt"
    assert ocr_artifact.read_text(encoding="utf-8") == "Updated OCR text.\n"


def test_ingest_source_external_image_uses_original_sidecar_for_copied_source(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    enable_sidecar_ocr(tmp_path)
    external_dir = tmp_path.parent / f"{tmp_path.name}-external-ocr"
    external_dir.mkdir()
    source = external_dir / "diagram.png"
    sidecar = Path(f"{source}.ocr.txt")
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    sidecar.write_text("External OCR text.\n", encoding="utf-8")

    try:
        added = add_source(tmp_path, source)
        result = ingest_source(tmp_path, added.source_id)
    finally:
        source.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        external_dir.rmdir()

    assert result.page_path is not None
    ocr_artifact = tmp_path / "derived" / "ocr" / f"{added.source_id}.txt"
    assert ocr_artifact.read_text(encoding="utf-8") == "External OCR text.\n"
    metadata_artifact = tmp_path / "derived" / "metadata" / f"{added.source_id}.ocr.json"
    metadata = json.loads(metadata_artifact.read_text(encoding="utf-8"))
    assert metadata["sidecar_ref"] == str(sidecar.resolve())

    run_record = load_run_record(result.run_path)
    assert str(sidecar.resolve()) not in run_record.input_refs
    assert any(
        link.role == "input"
        and link.path_ref is None
        and link.note is not None
        and str(sidecar.resolve()) in link.note
        for link in run_record.provenance_links
    )


def test_ingest_source_malformed_pdf_uses_stable_error(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.4\nnot a valid pdf\n")
    added = add_source(tmp_path, source)

    with pytest.raises(ValueError, match="^PDF text extraction failed for broken.pdf$"):
        ingest_source(tmp_path, added.source_id)

    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    queue_record = load_queue_item(queue_path)
    assert queue_record.last_error == "PDF text extraction failed for broken.pdf"


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
    run_record = load_run_record(run_paths[0])
    assert run_record.status == "failed"
    assert run_record.source_ids == [added.source_id]
    assert run_record.page_refs == []


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


def test_enqueue_ingest_job_creates_pending_item_without_attempt_increment(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    queue_path = enqueue_ingest_job(tmp_path, added.source_id)

    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "pending"
    assert queue_record.attempt_count == 0
    assert queue_record.lease_owner is None
    assert queue_record.lease_expires_at is None


def test_enqueue_ingest_job_rejects_unexpired_leased_item(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    leased_queue = load_queue_item(queue_path).model_copy(
        update={
            "status": "leased",
            "lease_owner": "local-cli:123",
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }
    )
    queue_path.write_text(leased_queue.model_dump_json(indent=2) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="already leased"):
        enqueue_ingest_job(tmp_path, added.source_id)

    updated_queue = load_queue_item(queue_path)
    assert updated_queue.status == "leased"
    assert updated_queue.lease_owner == "local-cli:123"


def test_enqueue_ingest_job_refreshes_created_at_when_reenqueuing_terminal_item(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    first_queue = load_queue_item(queue_path)
    terminal_queue = first_queue.model_copy(
        update={"status": "done", "created_at": "2000-01-01T00:00:00+00:00"}
    )
    queue_path.write_text(terminal_queue.model_dump_json(indent=2) + "\n", encoding="utf-8")

    queue_path = enqueue_ingest_job(tmp_path, added.source_id)

    reenqueued_queue = load_queue_item(queue_path)
    assert reenqueued_queue.status == "pending"
    assert reenqueued_queue.created_at != terminal_queue.created_at
    assert reenqueued_queue.attempt_count == first_queue.attempt_count


def test_run_ingest_job_rejects_absolute_queue_payload_ref(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = load_queue_item(queue_path).model_copy(
        update={"payload_ref": "/tmp/outside-manifest.json"}
    )
    queue_path.write_text(queue_record.model_dump_json(indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Queue payload path must be repo-relative"):
        run_ingest_job(tmp_path, queue_path)

    updated_queue = load_queue_item(queue_path)
    assert updated_queue.status == "failed"
    assert (
        updated_queue.last_error
        == "Queue payload path must be repo-relative: /tmp/outside-manifest.json"
    )


def test_run_ingest_job_rejects_escaping_queue_payload_ref(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = load_queue_item(queue_path).model_copy(
        update={"payload_ref": "../outside-manifest.json"}
    )
    queue_path.write_text(queue_record.model_dump_json(indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Queue payload path escapes workspace root"):
        run_ingest_job(tmp_path, queue_path)

    updated_queue = load_queue_item(queue_path)
    assert updated_queue.status == "failed"
    assert (
        updated_queue.last_error
        == "Queue payload path escapes workspace root: ../outside-manifest.json"
    )


def test_run_ingest_job_rejects_missing_queue_manifest(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    added.manifest_path.unlink()

    with pytest.raises(FileNotFoundError, match="Queue payload is missing source manifest"):
        run_ingest_job(tmp_path, queue_path)

    updated_queue = load_queue_item(queue_path)
    assert updated_queue.status == "failed"
    assert "missing source manifest" in updated_queue.last_error


def test_run_ingest_job_rejects_manifest_source_id_mismatch(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    source_record = load_source_record(added.manifest_path).model_copy(
        update={"source_id": "src-other"}
    )
    write_source_record(added.manifest_path, source_record)

    with pytest.raises(ValueError, match="does not match queued job"):
        run_ingest_job(tmp_path, queue_path)

    updated_queue = load_queue_item(queue_path)
    assert updated_queue.status == "failed"
    assert "does not match queued job" in updated_queue.last_error


def test_run_ingest_job_claims_once_and_clears_lease_on_success(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)

    result = run_ingest_job(tmp_path, queue_path)

    assert result.no_op is False
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "done"
    assert queue_record.attempt_count == 1
    assert queue_record.lease_owner is None
    assert queue_record.lease_expires_at is None


def test_drain_pending_ingest_jobs_reclaims_expired_leases(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    queue_record = load_queue_item(queue_path).model_copy(
        update={
            "status": "leased",
            "attempt_count": 2,
            "lease_owner": "local-cli:999",
            "lease_expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        }
    )
    queue_path.write_text(queue_record.model_dump_json(indent=2) + "\n", encoding="utf-8")

    result = drain_pending_ingest_jobs(tmp_path)

    assert result.processed == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert result.skipped == 0
    updated_queue = load_queue_item(queue_path)
    assert updated_queue.status == "done"
    assert updated_queue.attempt_count == 3


def test_drain_pending_ingest_jobs_skips_nonexpired_and_failed_items(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    leased_queue = load_queue_item(queue_path).model_copy(
        update={
            "status": "leased",
            "lease_owner": "local-cli:123",
            "lease_expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }
    )
    queue_path.write_text(leased_queue.model_dump_json(indent=2) + "\n", encoding="utf-8")

    failed_source = tmp_path / "failed.md"
    failed_source.write_bytes(b"\xff\xfe\xfa")
    failed_added = add_source(tmp_path, failed_source)
    failed_queue_path = enqueue_ingest_job(tmp_path, failed_added.source_id)
    failed_queue = load_queue_item(failed_queue_path).model_copy(
        update={
            "status": "failed",
            "next_attempt_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "last_error": "broken",
        }
    )
    failed_queue_path.write_text(failed_queue.model_dump_json(indent=2) + "\n", encoding="utf-8")

    result = drain_pending_ingest_jobs(tmp_path)

    assert result.processed == 0
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.skipped == 2
    assert result.total == 2
    assert len(result.items) == 2
    messages = {item.source_id: item.message for item in result.items}
    assert "lease active until" in messages[added.source_id]
    assert "retry after" in messages[failed_added.source_id]


def test_failed_ingest_sets_retry_backoff_and_clears_lease(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "broken.md"
    source.write_bytes(b"\xff\xfe\xfa")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)

    with pytest.raises(ValueError):
        run_ingest_job(tmp_path, queue_path)

    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "failed"
    assert queue_record.attempt_count == 1
    assert queue_record.last_error is not None
    assert queue_record.lease_owner is None
    assert queue_record.lease_expires_at is None
    assert queue_record.next_attempt_at is not None


def test_due_failed_jobs_are_retried_by_pending_drain(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    failed_queue = load_queue_item(queue_path).model_copy(
        update={
            "status": "failed",
            "attempt_count": 1,
            "last_error": "temporary",
            "next_attempt_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        }
    )
    write_queue_item(queue_path, failed_queue)

    result = drain_pending_ingest_jobs(tmp_path)

    assert result.processed == 1
    assert result.succeeded == 1
    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "done"
    assert queue_record.attempt_count == 2
    assert queue_record.next_attempt_at is None


def test_exhausted_failed_ingest_becomes_dead_letter(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.queue.max_attempts = 1
    write_config(tmp_path, config)
    source = tmp_path / "broken.md"
    source.write_bytes(b"\xff\xfe\xfa")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)

    with pytest.raises(ValueError):
        run_ingest_job(tmp_path, queue_path)

    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "dead_letter"
    assert queue_record.attempt_count == 1
    assert queue_record.max_attempts == 1
    assert queue_record.last_error is not None
    assert queue_record.next_attempt_at is None


def test_direct_ingest_rejects_dead_letter_queue_without_mutation(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    dead_letter = load_queue_item(queue_path).model_copy(
        update={
            "status": "dead_letter",
            "attempt_count": 3,
            "max_attempts": 3,
            "last_error": "broken",
        }
    )
    write_queue_item(queue_path, dead_letter)
    queue_before = queue_path.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="Queue item is dead-lettered"):
        ingest_source(tmp_path, added.source_id)

    assert queue_path.read_text(encoding="utf-8") == queue_before


def test_invalid_failed_next_attempt_is_treated_as_due(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    failed_queue = load_queue_item(queue_path).model_copy(
        update={
            "status": "failed",
            "attempt_count": 1,
            "last_error": "temporary",
            "next_attempt_at": "not-a-timestamp",
        }
    )
    write_queue_item(queue_path, failed_queue)

    result = drain_pending_ingest_jobs(tmp_path)

    assert result.succeeded == 1
    assert load_queue_item(queue_path).status == "done"


def test_failed_ingest_with_empty_backoff_is_immediately_due(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.queue.retry_backoff_seconds = []
    write_config(tmp_path, config)
    source = tmp_path / "broken.md"
    source.write_bytes(b"\xff\xfe\xfa")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)

    with pytest.raises(ValueError):
        run_ingest_job(tmp_path, queue_path)

    queue_record = load_queue_item(queue_path)
    assert queue_record.status == "failed"
    assert queue_record.next_attempt_at is not None
    result = drain_pending_ingest_jobs(tmp_path)
    assert result.failed == 1


def test_drain_pending_reports_dead_letter_and_done_as_skipped(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    dead_source = tmp_path / "dead.md"
    dead_source.write_text("# Dead\n\nhello world\n", encoding="utf-8")
    dead_added = add_source(tmp_path, dead_source)
    dead_queue_path = enqueue_ingest_job(tmp_path, dead_added.source_id)
    write_queue_item(
        dead_queue_path,
        load_queue_item(dead_queue_path).model_copy(
            update={"status": "dead_letter", "last_error": "broken"}
        ),
    )
    done_source = tmp_path / "done.md"
    done_source.write_text("# Done\n\nhello world\n", encoding="utf-8")
    done_added = add_source(tmp_path, done_source)
    done_queue_path = enqueue_ingest_job(tmp_path, done_added.source_id)
    write_queue_item(
        done_queue_path,
        load_queue_item(done_queue_path).model_copy(update={"status": "done"}),
    )

    result = drain_pending_ingest_jobs(tmp_path)

    assert result.processed == 0
    assert result.skipped == 2
    messages = {item.source_id: item.message for item in result.items}
    assert messages[dead_added.source_id] == "status=dead_letter"
    assert messages[done_added.source_id] == "status=done"


def test_run_ingest_job_rejects_future_backoff_and_terminal_records(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    queue_path = enqueue_ingest_job(tmp_path, added.source_id)
    write_queue_item(
        queue_path,
        load_queue_item(queue_path).model_copy(
            update={
                "status": "failed",
                "last_error": "temporary",
                "next_attempt_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }
        ),
    )

    with pytest.raises(RuntimeError, match="retry is not due"):
        run_ingest_job(tmp_path, queue_path)

    write_queue_item(
        queue_path,
        load_queue_item(queue_path).model_copy(
            update={"status": "dead_letter", "last_error": "broken", "next_attempt_at": None}
        ),
    )

    with pytest.raises(RuntimeError, match="Queue item is not runnable"):
        run_ingest_job(tmp_path, queue_path)


def test_drain_pending_ingest_jobs_continues_after_failure(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    ok_source = tmp_path / "brief.md"
    ok_source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    ok_added = add_source(tmp_path, ok_source)
    enqueue_ingest_job(tmp_path, ok_added.source_id)

    bad_source = tmp_path / "broken.bin"
    bad_source.write_bytes(b"\x00\x01\x02")
    bad_added = add_source(tmp_path, bad_source)
    enqueue_ingest_job(tmp_path, bad_added.source_id)

    result = drain_pending_ingest_jobs(tmp_path)

    assert result.processed == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.skipped == 0
    outcomes = {item.source_id: item.outcome for item in result.items}
    assert outcomes[ok_added.source_id] == "succeeded"
    assert outcomes[bad_added.source_id] == "failed"


def test_ingest_source_validates_stored_copy_checksum(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="copy")
    manifest = json.loads(added.manifest_path.read_text(encoding="utf-8"))
    stored_path = tmp_path / manifest["path"]
    stored_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Stored source copy checksum mismatch"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert load_queue_item(queue_path).status == "failed"
    assert len(run_paths) == 1
    run_record = load_run_record(run_paths[0])
    assert run_record.status == "failed"
    assert run_record.input_refs == [
        added.manifest_path.relative_to(tmp_path).as_posix(),
        manifest["path"],
    ]


def test_ingest_source_records_missing_stored_copy_as_failed_attempt(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="copy")
    manifest = json.loads(added.manifest_path.read_text(encoding="utf-8"))
    stored_path = tmp_path / manifest["path"]
    stored_path.unlink()

    with pytest.raises(ValueError, match="Stored source copy is missing"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert load_queue_item(queue_path).status == "failed"
    assert len(run_paths) == 1
    run_record = load_run_record(run_paths[0])
    assert run_record.status == "failed"
    assert run_record.input_refs == [
        added.manifest_path.relative_to(tmp_path).as_posix(),
        manifest["path"],
    ]


def test_ingest_source_legacy_manifest_missing_stored_copy_is_shape_specific(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "legacy.md"
    source.write_text("# Legacy\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="copy")
    source_record = load_source_record(added.manifest_path).model_copy(
        update={
            "source_ref": None,
            "source_ref_kind": None,
            "storage_mode": None,
            "storage_path": None,
            "materialized_at": None,
            "source_commit": None,
        }
    )
    write_source_record(added.manifest_path, source_record)
    stored_path = tmp_path / source_record.path
    stored_path.unlink()

    with pytest.raises(ValueError, match="Legacy stored source copy is missing"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert load_queue_item(queue_path).status == "failed"
    assert len(run_paths) == 1
    run_record = load_run_record(run_paths[0])
    assert run_record.status == "failed"
    assert run_record.input_refs == [
        added.manifest_path.relative_to(tmp_path).as_posix(),
        source_record.path,
    ]


def test_ingest_source_explicit_copy_manifest_failure_uses_storage_path(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="copy")
    manifest = json.loads(added.manifest_path.read_text(encoding="utf-8"))
    (tmp_path / manifest["path"]).unlink()

    with pytest.raises(ValueError, match="Stored source copy is missing"):
        ingest_source(tmp_path, added.source_id)

    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert len(run_paths) == 1
    run_record = load_run_record(run_paths[0])
    assert run_record.status == "failed"
    assert run_record.input_refs == [
        added.manifest_path.relative_to(tmp_path).as_posix(),
        manifest["path"],
    ]


def test_ingest_source_extract_uses_safe_fence_for_backticks(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\n```python\nprint('hi')\n```\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="copy")

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    page_content = result.page_path.read_text(encoding="utf-8")
    assert "````text" in page_content
    assert "\n````\n\n## Provenance" in page_content


def test_ingest_source_workspace_backed_default_uses_excerpt(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text(
        "# Brief\n\n" + "\n".join(f"line {i}" for i in range(120)),
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "## Extract" in body
    assert "line 10" in body
    assert "line 119" not in body
    assert "Extract policy: `excerpt`" in body


def test_ingest_source_excerpt_prefers_claim_bearing_section(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text(
        "# Brief\n\n"
        + "\n".join(f"opening filler {i}" for i in range(60))
        + "\n\n## Product Experience Notes\n\n"
        "- Path-first output should be visible before source IDs.\n"
        "- Generated summaries should stay compact for readable repo files.\n"
        "\n## Later Detail\n\n"
        "This late section should not enter the bounded excerpt.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    extract = extract_rendered_extract_section(body)
    assert "## Product Experience Notes" in extract
    assert "Path-first output should be visible before source IDs." in extract
    assert "opening filler 50" not in extract
    assert "This late section should not enter the bounded excerpt." not in extract


def test_ingest_source_markdown_summary_uses_heading_and_paragraph(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text(
        "# LLM Wiki Pattern\n\n"
        "Persistent knowledge should live in durable markdown pages that agents can inspect.\n\n"
        "## Core Claims\n\n"
        "- Agents need a repo-local memory substrate.\n"
        "- Deterministic search should find curated concepts before review noise.\n",
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert (
        "LLM Wiki Pattern. Persistent knowledge should live in durable markdown pages "
        "that agents can inspect."
    ) in body
    assert "Agents need a repo-local memory substrate." in body
    assert "Deterministic search should find curated concepts before review noise." in body
    assert "Manifest:" in body
    assert "## Extract" in body


def test_ingest_source_workspace_backed_none_omits_extract_section(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    update_summary_modes(tmp_path, in_repo="none")
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "## Extract" not in body
    assert "Workspace source: `brief.md`" in body
    assert "Source file: `brief.md`" in body


def test_ingest_source_workspace_backed_full_renders_full_text(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    update_summary_modes(tmp_path, in_repo="full")
    source = tmp_path / "brief.md"
    source.write_text(
        "# Brief\n\n" + "\n".join(f"line {i}" for i in range(120)),
        encoding="utf-8",
    )
    added = add_source(tmp_path, source)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "## Extract" in body
    assert "line 119" in body


def test_ingest_source_copied_default_renders_full_text(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text(
        "# Brief\n\n" + "\n".join(f"line {i}" for i in range(120)),
        encoding="utf-8",
    )
    added = add_source(tmp_path, source, storage_mode="copy")

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "## Extract" in body
    assert "line 119" in body


def test_ingest_source_external_excerpt_override_uses_bounded_preview(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    update_summary_modes(tmp_path, external="excerpt")
    source = tmp_path / "brief.md"
    source.write_text(
        "# Brief\n\n" + "\n".join(f"line {i}" for i in range(120)),
        encoding="utf-8",
    )
    added = add_source(tmp_path, source, storage_mode="copy")

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "## Extract" in body
    assert "line 10" in body
    assert "line 119" not in body


def test_ingest_source_rolls_back_wiki_on_success_commit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    manifest = json.loads(added.manifest_path.read_text(encoding="utf-8"))
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
    run_record = load_run_record(run_paths[0])
    assert run_record.status == "failed"
    assert run_record.input_refs == [
        added.manifest_path.relative_to(tmp_path).as_posix(),
        manifest["path"],
    ]


def test_ingest_source_workspace_backed_manifest_happy_path(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source_record = load_source_record(added.manifest_path).model_copy(
        update={
            "source_ref": "brief.md",
            "source_ref_kind": "workspace_path",
            "storage_mode": "none",
            "storage_path": None,
        }
    )
    write_source_record(added.manifest_path, source_record)

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "Workspace source: `brief.md`" in body
    assert "registered from `brief.md`" in body
    run_record = load_run_record(result.run_path)
    assert run_record.input_refs == [
        added.manifest_path.relative_to(tmp_path).as_posix(),
        "brief.md",
    ]


def test_ingest_source_supports_mixed_manifest_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    legacy_source = tmp_path / "legacy.md"
    legacy_source.write_text("# Legacy\n\nold world\n", encoding="utf-8")
    workspace_source = tmp_path / "workspace.md"
    workspace_source.write_text("# Workspace\n\nnew world\n", encoding="utf-8")
    copied_source = tmp_path / "copied.md"
    copied_source.write_text("# Copied\n\nstored world\n", encoding="utf-8")
    pointer_source = tmp_path / "pointer.md"
    pointer_source.write_text("# Pointer\n\npointer world\n", encoding="utf-8")
    symlink_source = tmp_path / "symlink.md"
    symlink_source.write_text("# Symlink\n\nsymlink world\n", encoding="utf-8")

    legacy_added = add_source(tmp_path, legacy_source, storage_mode="copy")
    workspace_added = add_source(tmp_path, workspace_source)
    copied_added = add_source(tmp_path, copied_source, storage_mode="copy")
    pointer_added = add_source(tmp_path, pointer_source, storage_mode="pointer")
    symlink_added = add_source(tmp_path, symlink_source, storage_mode="symlink")

    legacy_manifest = load_source_record(legacy_added.manifest_path).model_copy(
        update={
            "source_ref": None,
            "source_ref_kind": None,
            "storage_mode": None,
            "storage_path": None,
            "materialized_at": None,
            "source_commit": None,
        }
    )
    write_source_record(legacy_added.manifest_path, legacy_manifest)

    legacy_result = ingest_source(tmp_path, legacy_added.source_id)
    workspace_result = ingest_source(tmp_path, workspace_added.source_id)
    copied_result = ingest_source(tmp_path, copied_added.source_id)
    pointer_result = ingest_source(tmp_path, pointer_added.source_id)
    symlink_result = ingest_source(tmp_path, symlink_added.source_id)

    legacy_body = legacy_result.page_path.read_text(encoding="utf-8")
    assert "Stored source:" in legacy_body
    assert "registered from `legacy.md`" in legacy_body
    legacy_run = load_run_record(legacy_result.run_path)
    assert legacy_run.input_refs == [
        legacy_added.manifest_path.relative_to(tmp_path).as_posix(),
        legacy_manifest.path,
    ]

    workspace_body = workspace_result.page_path.read_text(encoding="utf-8")
    assert "Workspace source: `workspace.md`" in workspace_body
    assert "registered from `workspace.md`" in workspace_body
    workspace_run = load_run_record(workspace_result.run_path)
    assert workspace_run.input_refs == [
        workspace_added.manifest_path.relative_to(tmp_path).as_posix(),
        "workspace.md",
    ]

    copied_manifest = load_source_record(copied_added.manifest_path)
    copied_body = copied_result.page_path.read_text(encoding="utf-8")
    assert "Stored source:" in copied_body
    assert "registered from `copied.md`" in copied_body
    copied_run = load_run_record(copied_result.run_path)
    assert copied_run.input_refs == [
        copied_added.manifest_path.relative_to(tmp_path).as_posix(),
        copied_manifest.storage_path,
    ]

    pointer_body = pointer_result.page_path.read_text(encoding="utf-8")
    assert "Workspace source: `pointer.md`" in pointer_body
    assert "registered from `pointer.md`" in pointer_body
    pointer_run = load_run_record(pointer_result.run_path)
    assert pointer_run.input_refs == [
        pointer_added.manifest_path.relative_to(tmp_path).as_posix(),
        "pointer.md",
    ]

    symlink_body = symlink_result.page_path.read_text(encoding="utf-8")
    assert "Workspace source: `symlink.md`" in symlink_body
    assert "registered from `symlink.md`" in symlink_body
    symlink_run = load_run_record(symlink_result.run_path)
    assert symlink_run.input_refs == [
        symlink_added.manifest_path.relative_to(tmp_path).as_posix(),
        "symlink.md",
    ]


def test_ingest_source_workspace_backed_manifest_missing_file(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source_record = load_source_record(added.manifest_path).model_copy(
        update={
            "source_ref": "brief.md",
            "source_ref_kind": "workspace_path",
            "storage_mode": "none",
            "storage_path": None,
        }
    )
    write_source_record(added.manifest_path, source_record)
    source.unlink()

    with pytest.raises(ValueError, match="Workspace source is missing"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert load_queue_item(queue_path).status == "failed"
    assert len(run_paths) == 1
    assert load_run_record(run_paths[0]).status == "failed"


def test_ingest_source_workspace_backed_manifest_checksum_drift(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source_record = load_source_record(added.manifest_path).model_copy(
        update={
            "source_ref": "brief.md",
            "source_ref_kind": "workspace_path",
            "storage_mode": "none",
            "storage_path": None,
        }
    )
    write_source_record(added.manifest_path, source_record)
    source.write_text("# Brief\n\nchanged\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Workspace source checksum mismatch"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert load_queue_item(queue_path).status == "failed"
    assert len(run_paths) == 1
    assert load_run_record(run_paths[0]).status == "failed"


def test_ingest_source_pointer_backed_happy_path(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="pointer")

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "Workspace source: `brief.md`" in body
    assert "Source file: `brief.md`" in body
    run_record = load_run_record(result.run_path)
    assert run_record.input_refs == [
        added.manifest_path.relative_to(tmp_path).as_posix(),
        "brief.md",
    ]


def test_ingest_source_pointer_backed_default_uses_excerpt(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text(
        "# Brief\n\n" + "\n".join(f"line {i}" for i in range(120)),
        encoding="utf-8",
    )
    added = add_source(tmp_path, source, storage_mode="pointer")

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "## Extract" in body
    assert "line 10" in body
    assert "line 119" not in body


def test_ingest_source_pointer_backed_missing_artifact(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="pointer")
    assert added.stored_path is not None
    added.stored_path.unlink()

    with pytest.raises(ValueError, match="Pointer artifact is missing"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_pointer_backed_malformed_artifact(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="pointer")
    assert added.stored_path is not None
    added.stored_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Pointer artifact is not valid JSON"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_pointer_backed_mismatched_source_ref(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="pointer")
    rewrite_pointer(
        tmp_path,
        added.source_id,
        source_ref="other.md",
        checksum=load_source_record(added.manifest_path).checksum,
    )

    with pytest.raises(ValueError, match="Pointer artifact source_ref mismatch"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_pointer_backed_missing_workspace_target(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="pointer")
    source.unlink()

    with pytest.raises(ValueError, match="Workspace source is missing"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_pointer_backed_checksum_drift(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="pointer")
    source.write_text("# Brief\n\nchanged\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Workspace source checksum mismatch"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_symlink_backed_happy_path(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="symlink")

    result = ingest_source(tmp_path, added.source_id)

    assert result.page_path is not None
    body = result.page_path.read_text(encoding="utf-8")
    assert "Workspace source: `brief.md`" in body
    assert "registered from `brief.md`" in body
    run_record = load_run_record(result.run_path)
    assert run_record.input_refs == [
        added.manifest_path.relative_to(tmp_path).as_posix(),
        "brief.md",
    ]


def test_ingest_source_symlink_backed_missing_artifact(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="symlink")
    assert added.stored_path is not None
    added.stored_path.unlink()

    with pytest.raises(ValueError, match="Source symlink artifact is missing"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_symlink_backed_regular_file_artifact(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="symlink")
    assert added.stored_path is not None
    added.stored_path.unlink()
    added.stored_path.write_text("not-a-link\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Source symlink artifact is not a symlink"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_symlink_backed_target_mismatch(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("# Other\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="symlink")
    rewrite_symlink(tmp_path, added.source_id, Path("../../../other.md"))

    with pytest.raises(ValueError, match="target does not match manifest source_ref"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_symlink_backed_missing_workspace_target(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="symlink")
    source.unlink()

    with pytest.raises(ValueError, match="Workspace source is missing"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None


def test_ingest_source_symlink_backed_checksum_drift(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="symlink")
    source.write_text("# Brief\n\nchanged\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Workspace source checksum mismatch"):
        ingest_source(tmp_path, added.source_id)

    source_record = load_source_record(added.manifest_path)
    assert source_record.status == "failed"
    assert source_record.last_run_id is not None
    queue_path = tmp_path / "state" / "queue" / f"ingest-{added.source_id}.json"
    run_paths = list((tmp_path / "state" / "runs").glob("*.json"))
    assert load_queue_item(queue_path).status == "failed"
    assert len(run_paths) == 1
    assert load_run_record(run_paths[0]).status == "failed"


def test_ingest_source_records_warning_when_openai_review_is_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_workspace(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source, storage_mode="copy")

    result = ingest_source(tmp_path, added.source_id)

    run_record = load_run_record(result.run_path)
    assert run_record.warnings == [
        "Skipped contradiction review because OPENAI_API_KEY is not configured."
    ]


def test_ingest_source_marks_contradictions_and_creates_review_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_workspace(tmp_path)

    class FakeAnalyzer:
        def detect(self, *, current, candidate):
            if candidate.frontmatter.page_id == current.frontmatter.page_id:
                return []
            return [
                contradictions_module.DetectedContradiction(
                    summary="The pages disagree about the configured storage mode.",
                    current_excerpt="Storage mode is none.",
                    candidate_excerpt="Storage mode is copy.",
                )
            ]

    monkeypatch.setattr(
        contradictions_module,
        "build_contradiction_analyzer",
        lambda config: FakeAnalyzer(),
    )

    first_source = tmp_path / "first.md"
    first_source.write_text("# First\n\nhello world\n", encoding="utf-8")
    first_added = add_source(tmp_path, first_source, storage_mode="copy")
    ingest_source(tmp_path, first_added.source_id)

    second_source = tmp_path / "second.md"
    second_source.write_text("# Second\n\nhello world\n", encoding="utf-8")
    second_added = add_source(tmp_path, second_source, storage_mode="copy")
    second_result = ingest_source(tmp_path, second_added.source_id)

    first_page = parse_frontmatter(tmp_path / "wiki" / "sources" / f"{first_added.source_id}.md")[0]
    second_page = parse_frontmatter(second_result.page_path)[0]

    assert first_page.review_state == "contested"
    assert second_page.review_state == "contested"
    assert len(first_page.contradictions) == 1
    assert (
        first_page.contradictions[0].contradiction_id
        == second_page.contradictions[0].contradiction_id
    )

    task_id = second_page.contradictions[0].review_task_id
    task_path = tmp_path / "planning" / "tasks" / f"{task_id}.md"
    assert task_path.exists()
    task_body = task_path.read_text(encoding="utf-8")
    assert "## Contradiction" in task_body
    assert "## Evidence" in task_body
    assert "## Linked Pages" in task_body
    assert "## Notes" in task_body

    run_record = load_run_record(second_result.run_path)
    assert run_record.task_ids == [task_id]
    assert run_record.contradiction_ids == [second_page.contradictions[0].contradiction_id]


def test_ingest_source_skips_boilerplate_only_contradiction_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_workspace(tmp_path)
    update_summary_modes(tmp_path, external="none")

    class FakeAnalyzer:
        def detect(self, *, current, candidate):
            pytest.fail("boilerplate-only source summaries should not be reviewed")

    monkeypatch.setattr(
        contradictions_module,
        "build_contradiction_analyzer",
        lambda config: FakeAnalyzer(),
    )

    first_source = tmp_path / "first.json"
    first_source.write_text('{"path": "first"}\n', encoding="utf-8")
    first_added = add_source(tmp_path, first_source, storage_mode="copy")
    ingest_source(tmp_path, first_added.source_id)

    second_source = tmp_path / "second.json"
    second_source.write_text('{"path": "second"}\n', encoding="utf-8")
    second_added = add_source(tmp_path, second_source, storage_mode="copy")
    second_result = ingest_source(tmp_path, second_added.source_id)

    first_page = parse_frontmatter(tmp_path / "wiki" / "sources" / f"{first_added.source_id}.md")[0]
    second_page = parse_frontmatter(second_result.page_path)[0]
    assert first_page.contradictions == []
    assert second_page.contradictions == []
    assert list((tmp_path / "planning" / "tasks").glob("task-review-*.md")) == []


def test_ingest_source_dedupes_existing_contradictions_and_review_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_workspace(tmp_path)

    class FakeAnalyzer:
        def detect(self, *, current, candidate):
            return [
                contradictions_module.DetectedContradiction(
                    summary="The pages disagree about the configured storage mode.",
                    current_excerpt="Storage mode is none.",
                    candidate_excerpt="Storage mode is copy.",
                )
            ]

    monkeypatch.setattr(
        contradictions_module,
        "build_contradiction_analyzer",
        lambda config: FakeAnalyzer(),
    )

    first_source = tmp_path / "first.md"
    first_source.write_text("# First\n\nhello world\n", encoding="utf-8")
    first_added = add_source(tmp_path, first_source, storage_mode="copy")
    ingest_source(tmp_path, first_added.source_id)

    second_source = tmp_path / "second.md"
    second_source.write_text("# Second\n\nhello world\n", encoding="utf-8")
    second_added = add_source(tmp_path, second_source, storage_mode="copy")
    first_result = ingest_source(tmp_path, second_added.source_id)
    assert first_result.page_path is not None
    first_result.page_path.unlink()
    second_result = ingest_source(tmp_path, second_added.source_id)

    first_page = parse_frontmatter(first_result.page_path)[0]
    second_page = parse_frontmatter(second_result.page_path)[0]
    task_id = second_page.contradictions[0].review_task_id
    task_paths = list((tmp_path / "planning" / "tasks").glob(f"{task_id}.md"))

    assert len(first_page.contradictions) == 1
    assert len(second_page.contradictions) == 1
    assert len(task_paths) == 1
    assert load_run_record(second_result.run_path).task_ids == [task_id]
