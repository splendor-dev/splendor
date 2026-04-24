"""Implementation for `splendor repo refresh`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from splendor.commands.repo_scan import RepoScanResult, scan_repo
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter
from splendor.utils.fs import write_text_atomic
from splendor.utils.provenance import dedupe_provenance_links, make_provenance_link
from splendor.utils.time import utc_now_iso
from splendor.utils.wiki import render_frontmatter, upsert_index_section

_ARCHITECTURE_PAGE_ID = "architecture-repository-structure"
_TOPIC_PAGE_ID = "topic-repository-sources"


@dataclass(frozen=True)
class RepoRefreshResult:
    scan: RepoScanResult
    generated_page_refs: list[str]
    linked_source_ids: list[str]


def refresh_repo(root: Path) -> RepoRefreshResult:
    scan = scan_repo(root)
    config = load_config(root)
    layout = resolve_layout(root, config)
    generated_at = utc_now_iso()
    linked_source_ids = sorted({item.source_id for item in scan.touched_sources})
    source_refs = linked_source_ids
    provenance_links = dedupe_provenance_links(
        make_provenance_link(
            source_id=item.source_id,
            path_ref=item.path,
            role="supports",
        )
        for item in scan.touched_sources
    )

    architecture_path = layout.wiki_dir / "architecture" / "repository-structure.md"
    topic_path = layout.wiki_dir / "topics" / "repository-sources.md"
    architecture_ref = architecture_path.relative_to(root).as_posix()
    topic_ref = topic_path.relative_to(root).as_posix()

    architecture_page = KnowledgePageFrontmatter(
        kind="architecture",
        title="Repository Structure",
        page_id=_ARCHITECTURE_PAGE_ID,
        status="active",
        review_state="machine-generated",
        source_refs=source_refs,
        last_generated_at=generated_at,
        confidence=1.0,
        related_pages=[_TOPIC_PAGE_ID],
        tags=["repo-refresh", "architecture"],
        provenance_links=provenance_links,
    )
    topic_page = KnowledgePageFrontmatter(
        kind="topic",
        title="Repository Sources",
        page_id=_TOPIC_PAGE_ID,
        status="active",
        review_state="machine-generated",
        source_refs=source_refs,
        last_generated_at=generated_at,
        confidence=1.0,
        related_pages=[_ARCHITECTURE_PAGE_ID],
        tags=["repo-refresh", "sources"],
        provenance_links=provenance_links,
    )

    write_text_atomic(
        architecture_path,
        _render_architecture_page(
            architecture_page, scan=scan, topic_ref="../topics/repository-sources.md"
        ),
    )
    write_text_atomic(
        topic_path,
        _render_sources_page(
            topic_page, scan=scan, architecture_ref="../architecture/repository-structure.md"
        ),
    )
    write_text_atomic(
        layout.index_file,
        _update_index(
            layout.index_file.read_text(encoding="utf-8"),
            architecture_page=architecture_page,
            topic_page=topic_page,
        ),
    )
    write_text_atomic(
        layout.log_file,
        _upsert_log_entry(
            layout.log_file.read_text(encoding="utf-8"),
            f"- Refreshed repo pages `{architecture_ref}` and `{topic_ref}`.",
        ),
    )

    return RepoRefreshResult(
        scan=scan,
        generated_page_refs=[architecture_ref, topic_ref],
        linked_source_ids=linked_source_ids,
    )


def render_repo_refresh_json(result: RepoRefreshResult) -> str:
    payload = {
        "scanned": result.scan.scanned,
        "registered": result.scan.registered,
        "already_registered": result.scan.already_registered,
        "unsupported": result.scan.unsupported,
        "ignored": result.scan.ignored,
        "class_counts": result.scan.class_counts,
        "generated_page_refs": result.generated_page_refs,
        "linked_source_ids": result.linked_source_ids,
    }
    return json.dumps(payload, indent=2)


def _render_architecture_page(
    frontmatter: KnowledgePageFrontmatter, *, scan: RepoScanResult, topic_ref: str
) -> str:
    class_lines = "\n".join(
        f"- {name}: {count}" for name, count in sorted(scan.class_counts.items())
    )
    grouped = _group_paths_by_class(scan)
    group_sections = "\n\n".join(
        [f"### {name.title()}\n\n{_path_bullets(paths)}" for name, paths in grouped.items()]
    )
    if not group_sections:
        group_sections = "No repository sources were discovered."
    return (
        f"---\n{render_frontmatter(frontmatter)}\n---\n\n"
        f"# {frontmatter.title}\n\n"
        "## Summary\n\n"
        "This page is a deterministic repo-refresh view of the workspace structure.\n\n"
        "## Source Classes\n\n"
        f"{class_lines}\n\n"
        "## Discovered Structure\n\n"
        f"{group_sections}\n\n"
        "## Related Pages\n\n"
        f"- [Repository Sources]({topic_ref}) (`{_TOPIC_PAGE_ID}`)\n"
    )


def _render_sources_page(
    frontmatter: KnowledgePageFrontmatter, *, scan: RepoScanResult, architecture_ref: str
) -> str:
    rows = [
        "| Path | Source ID | Class | Labels | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in sorted(scan.touched_sources, key=lambda candidate: candidate.path):
        labels = ", ".join(item.source_labels) if item.source_labels else "-"
        row = (
            f"| `{item.path}` | `{item.source_id}` | {item.source_class} | "
            f"{labels} | {item.status} |"
        )
        rows.append(row)
    if len(rows) == 2:
        rows.append("| - | - | - | - | - |")
    return (
        f"---\n{render_frontmatter(frontmatter)}\n---\n\n"
        f"# {frontmatter.title}\n\n"
        "## Summary\n\n"
        "This page lists repo-native sources discovered by `splendor repo refresh`.\n\n"
        "## Sources\n\n" + "\n".join(rows) + "\n\n"
        "## Related Pages\n\n"
        f"- [Repository Structure]({architecture_ref}) (`{_ARCHITECTURE_PAGE_ID}`)\n"
    )


def _group_paths_by_class(scan: RepoScanResult) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {
        "code": [],
        "documentation": [],
        "configuration": [],
        "other": [],
    }
    for item in sorted(scan.touched_sources, key=lambda candidate: candidate.path):
        grouped[item.source_class].append(item.path)
    return {name: paths for name, paths in grouped.items() if paths}


def _path_bullets(paths: list[str]) -> str:
    return "\n".join(f"- `{path}`" for path in paths)


def _update_index(
    index_content: str,
    *,
    architecture_page: KnowledgePageFrontmatter,
    topic_page: KnowledgePageFrontmatter,
) -> str:
    updated = upsert_index_section(
        index_content,
        section_header="## Architecture",
        bullet=(
            f"- [{architecture_page.title}](architecture/repository-structure.md) "
            f"(`{architecture_page.page_id}`)"
        ),
        dedupe_predicate=lambda line: f"(`{architecture_page.page_id}`)" in line,
    )
    return upsert_index_section(
        updated,
        section_header="## Topics",
        bullet=f"- [{topic_page.title}](topics/repository-sources.md) (`{topic_page.page_id}`)",
        dedupe_predicate=lambda line: f"(`{topic_page.page_id}`)" in line,
    )


def _upsert_log_entry(log_content: str, entry: str) -> str:
    lines = log_content.rstrip().splitlines()
    lines = [line for line in lines if line != entry]
    lines.append(entry)
    return "\n".join(lines).rstrip() + "\n"
