"""Helpers for building and summarizing structured provenance links."""

from __future__ import annotations

from collections.abc import Iterable

from splendor.schemas import ProvenanceLink
from splendor.schemas.types import ProvenanceRole


def make_provenance_link(
    *,
    source_id: str | None = None,
    page_id: str | None = None,
    run_id: str | None = None,
    path_ref: str | None = None,
    role: ProvenanceRole | None = None,
    note: str | None = None,
) -> ProvenanceLink:
    return ProvenanceLink(
        source_id=source_id,
        page_id=page_id,
        run_id=run_id,
        path_ref=path_ref,
        role=role,
        note=note,
    )


def dedupe_provenance_links(links: Iterable[ProvenanceLink]) -> list[ProvenanceLink]:
    deduped: list[ProvenanceLink] = []
    seen: set[tuple[str | None, str | None, str | None, str | None, str | None, str | None]] = set()
    for link in links:
        key = (
            link.source_id,
            link.page_id,
            link.run_id,
            link.path_ref,
            link.role,
            link.note,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(link)
    return deduped


def summarize_provenance_links(links: Iterable[ProvenanceLink]) -> str:
    parts: list[str] = []
    for link in links:
        label_parts: list[str] = []
        if link.role:
            label_parts.append(link.role)
        if link.source_id:
            label_parts.append(f"source={link.source_id}")
        if link.page_id:
            label_parts.append(f"page={link.page_id}")
        if link.run_id:
            label_parts.append(f"run={link.run_id}")
        if link.path_ref:
            label_parts.append(f"path={link.path_ref}")
        if not label_parts:
            continue
        parts.append(" ".join(label_parts))
    return "; ".join(parts)
