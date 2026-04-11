"""Deterministic wiki page and index/log writers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from splendor.layout import ResolvedLayout
from splendor.schemas import KnowledgePageFrontmatter
from splendor.utils.fs import write_text_atomic


@dataclass(frozen=True)
class WikiUpdatePayload:
    page_path: Path
    page_content: str
    index_content: str
    log_content: str


def render_frontmatter(record: KnowledgePageFrontmatter) -> str:
    return yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False).strip()


def render_source_summary_page(
    frontmatter: KnowledgePageFrontmatter,
    *,
    source_section: str,
    summary: str,
    key_facts: list[str],
    extract: str,
    provenance: list[str],
) -> str:
    key_fact_lines = "\n".join(f"- {line}" for line in key_facts)
    provenance_lines = "\n".join(f"- {line}" for line in provenance)
    return (
        f"---\n{render_frontmatter(frontmatter)}\n---\n\n"
        f"# {frontmatter.title}\n\n"
        "## Source\n\n"
        f"{source_section}\n\n"
        "## Summary\n\n"
        f"{summary}\n\n"
        "## Key Facts\n\n"
        f"{key_fact_lines}\n\n"
        "## Extract\n\n"
        "```text\n"
        f"{extract}\n"
        "```\n\n"
        "## Provenance\n\n"
        f"{provenance_lines}\n"
    )


def update_index_content(index_content: str, *, source_id: str, title: str, page_name: str) -> str:
    bullet = f"- [{title}](sources/{page_name}) (`{source_id}`)"
    lines = index_content.rstrip().splitlines()
    section_header = "## Sources"

    try:
        section_index = lines.index(section_header)
    except ValueError:
        lines.extend(["", section_header, "", bullet])
        return "\n".join(lines) + "\n"

    next_heading_index = len(lines)
    for index in range(section_index + 1, len(lines)):
        if lines[index].startswith("## "):
            next_heading_index = index
            break

    existing_bullets = [
        line
        for line in lines[section_index + 1 : next_heading_index]
        if line.startswith("- [") and f"(`{source_id}`)" not in line
    ]
    existing_bullets.append(bullet)
    section_lines = ["", *sorted(existing_bullets)]
    new_lines = lines[: section_index + 1] + section_lines + lines[next_heading_index:]
    return "\n".join(new_lines).rstrip() + "\n"


def append_log_entry(log_content: str, entry: str) -> str:
    stripped = log_content.rstrip()
    return f"{stripped}\n{entry}\n"


def apply_wiki_updates(layout: ResolvedLayout, payload: WikiUpdatePayload) -> None:
    targets = [
        (payload.page_path, payload.page_content),
        (layout.index_file, payload.index_content),
        (layout.log_file, payload.log_content),
    ]
    previous_content: dict[Path, str | None] = {}

    for path, _ in targets:
        previous_content[path] = path.read_text(encoding="utf-8") if path.exists() else None

    try:
        for path, content in targets:
            write_text_atomic(path, content)
    except Exception:
        for path, content in previous_content.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                write_text_atomic(path, content)
        raise
