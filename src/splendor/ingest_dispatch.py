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
SUPPORTED_SOURCE_TYPES = {*TEXT_SOURCE_TYPES, "pdf"}


@dataclass(frozen=True)
class DispatchedSourceContent:
    text: str
    derived_artifact_path: Path | None = None
    derived_artifact_content: str | None = None


def dispatch_source_content(
    source: SourceRecord,
    resolved_source: ResolvedSource,
    *,
    layout: ResolvedLayout,
) -> DispatchedSourceContent:
    if source.source_type in TEXT_SOURCE_TYPES:
        return _read_text_source(resolved_source.resolved_path)
    if source.source_type == "pdf":
        return _extract_pdf_source(source, resolved_source, layout=layout)

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
) -> DispatchedSourceContent:
    try:
        reader = PdfReader(str(resolved_source.resolved_path))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        msg = f"PDF text extraction failed for {resolved_source.resolved_ref}: {exc}"
        raise ValueError(msg) from exc

    extracted_text = _normalize_pdf_text(page_texts)
    if not extracted_text:
        msg = (
            "PDF source has no extractable text; OCR/image extraction is not supported: "
            f"{resolved_source.resolved_ref}"
        )
        raise ValueError(msg)

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
