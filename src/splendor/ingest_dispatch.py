"""Source-type dispatch for ingestion content extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from splendor.layout import ResolvedLayout
from splendor.schemas import SourceRecord
from splendor.state.source_resolver import ResolvedSource

TEXT_SOURCE_TYPES = {
    "md",
    "txt",
    "json",
    "yaml",
    "yml",
    "py",
    "js",
    "ts",
    "tsx",
    "rs",
    "go",
    "java",
    "c",
    "cpp",
    "h",
    "hpp",
    "sh",
}
IMAGE_SOURCE_TYPES = {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}
SUPPORTED_SOURCE_TYPES = {*TEXT_SOURCE_TYPES, "pdf", *IMAGE_SOURCE_TYPES}


@dataclass(frozen=True)
class DispatchedSourceContent:
    text: str
    derived_artifact_path: Path | None = None
    derived_artifact_content: str | None = None
    derived_artifact_label: str = "Parsed artifact"


def dispatch_source_content(
    source: SourceRecord,
    resolved_source: ResolvedSource,
    *,
    layout: ResolvedLayout,
    config,
) -> DispatchedSourceContent:
    if source.source_type in TEXT_SOURCE_TYPES:
        return _read_text_source(resolved_source.resolved_path)
    if source.source_type == "pdf":
        return _extract_pdf_source(source, resolved_source, layout=layout, config=config)
    if source.source_type in IMAGE_SOURCE_TYPES:
        return _extract_ocr_source(source, resolved_source, layout=layout, config=config)

    msg = f"Unsupported source type for ingestion: {source.source_type}"
    raise ValueError(msg)


def _read_text_source(path: Path) -> DispatchedSourceContent:
    try:
        return DispatchedSourceContent(text=path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        msg = f"Source file is not valid UTF-8 text: {path}"
        raise ValueError(msg) from exc


def _extract_pdf_source(
    source: SourceRecord,
    resolved_source: ResolvedSource,
    *,
    layout: ResolvedLayout,
    config,
) -> DispatchedSourceContent:
    try:
        reader = PdfReader(str(resolved_source.resolved_path))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        msg = f"PDF text extraction failed for {resolved_source.resolved_ref}"
        raise ValueError(msg) from exc

    extracted_text = _normalize_pdf_text(page_texts)
    if not extracted_text:
        return _extract_ocr_source(source, resolved_source, layout=layout, config=config)

    artifact_content = f"{extracted_text}\n"
    return DispatchedSourceContent(
        text=extracted_text,
        derived_artifact_path=layout.derived_parsed_dir / f"{source.source_id}.txt",
        derived_artifact_content=artifact_content,
    )


def _normalize_pdf_text(page_texts: list[str]) -> str:
    normalized_pages = []
    for page_text in page_texts:
        normalized = page_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if normalized:
            normalized_pages.append(normalized)
    return "\n\n".join(normalized_pages).strip()


def _extract_ocr_source(
    source: SourceRecord,
    resolved_source: ResolvedSource,
    *,
    layout: ResolvedLayout,
    config,
) -> DispatchedSourceContent:
    if not config.sources.ocr_enabled:
        msg = f"OCR/image extraction is not configured: {resolved_source.resolved_ref}"
        raise ValueError(msg)
    if config.sources.ocr_provider != "sidecar-text":
        msg = f"OCR provider is not supported: {config.sources.ocr_provider}"
        raise ValueError(msg)

    sidecar_path = _ocr_sidecar_path(
        resolved_source.resolved_path,
        sidecar_suffix=config.sources.ocr_sidecar_suffix,
    )
    if not sidecar_path.is_file():
        msg = f"OCR sidecar text is missing for {resolved_source.resolved_ref}: {sidecar_path.name}"
        raise ValueError(msg)

    try:
        ocr_text = sidecar_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        msg = f"OCR sidecar text is not valid UTF-8: {sidecar_path.name}"
        raise ValueError(msg) from exc

    extracted_text = _normalize_ocr_text(ocr_text)
    if not extracted_text:
        msg = f"OCR sidecar text is empty for {resolved_source.resolved_ref}: {sidecar_path.name}"
        raise ValueError(msg)

    return DispatchedSourceContent(
        text=extracted_text,
        derived_artifact_path=layout.derived_ocr_dir / f"{source.source_id}.txt",
        derived_artifact_content=f"{extracted_text}\n",
        derived_artifact_label="OCR artifact",
    )


def _ocr_sidecar_path(path: Path, *, sidecar_suffix: str) -> Path:
    return Path(f"{path}{sidecar_suffix}")


def _normalize_ocr_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()
