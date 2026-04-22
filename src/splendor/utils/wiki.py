"""Deterministic wiki page parsing and index/log writers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from splendor.layout import ResolvedLayout
from splendor.schemas import KnowledgePageFrontmatter
from splendor.utils.fs import write_text_atomic


@dataclass(frozen=True)
class WikiUpdatePayload:
    page_path: Path
    page_content: str
    index_content: str
    log_content: str
    extra_writes: list[tuple[Path, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedWikiPage:
    frontmatter: KnowledgePageFrontmatter
    body: str


def render_frontmatter(record: KnowledgePageFrontmatter) -> str:
    return yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False).strip()


def parse_wiki_markdown(path: Path) -> ParsedWikiPage:
    raw = path.read_text(encoding="utf-8")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError(f"Wiki page {path} is missing YAML frontmatter")

    try:
        frontmatter_text, body = normalized.removeprefix("---\n").split("\n---\n", maxsplit=1)
    except ValueError as exc:
        raise ValueError(f"Wiki page {path} has malformed YAML frontmatter") from exc

    try:
        payload = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Wiki page {path} has invalid YAML frontmatter") from exc

    try:
        frontmatter = KnowledgePageFrontmatter.model_validate(payload or {})
    except ValidationError as exc:
        raise ValueError(f"Wiki page {path} failed schema validation: {exc}") from exc

    return ParsedWikiPage(frontmatter=frontmatter, body=body)


def _fenced_extract_block(extract: str) -> str:
    max_backtick_run = 0
    current_run = 0
    for char in extract:
        if char == "`":
            current_run += 1
            max_backtick_run = max(max_backtick_run, current_run)
        else:
            current_run = 0

    fence = "`" * max(3, max_backtick_run + 1)
    return f"{fence}text\n{extract}\n{fence}"


def render_source_summary_page(
    frontmatter: KnowledgePageFrontmatter,
    *,
    source_section: str,
    summary: str,
    key_facts: list[str],
    extract: str | None,
    contradictions: list[str] | None = None,
    provenance: list[str],
) -> str:
    key_fact_lines = "\n".join(f"- {line}" for line in key_facts)
    contradiction_section = ""
    if contradictions:
        contradiction_lines = "\n".join(f"- {line}" for line in contradictions)
        contradiction_section = f"## Contradictions\n\n{contradiction_lines}\n\n"
    provenance_lines = "\n".join(f"- {line}" for line in provenance)
    extract_section = ""
    if extract is not None:
        extract_section = f"## Extract\n\n{_fenced_extract_block(extract)}\n\n"
    return (
        f"---\n{render_frontmatter(frontmatter)}\n---\n\n"
        f"# {frontmatter.title}\n\n"
        "## Source\n\n"
        f"{source_section}\n\n"
        "## Summary\n\n"
        f"{summary}\n\n"
        "## Key Facts\n\n"
        f"{key_fact_lines}\n\n"
        f"{extract_section}"
        f"{contradiction_section}"
        "## Provenance\n\n"
        f"{provenance_lines}\n"
    )


def update_index_content(index_content: str, *, source_id: str, title: str, page_name: str) -> str:
    bullet = f"- [{title}](sources/{page_name}) (`{source_id}`)"
    stable_token = f"(`{source_id}`)"
    return upsert_index_section(
        index_content,
        section_header="## Sources",
        bullet=bullet,
        dedupe_predicate=lambda line: stable_token in line,
    )


def upsert_index_section(
    index_content: str,
    *,
    section_header: str,
    bullet: str,
    dedupe_predicate=None,
) -> str:
    lines = index_content.rstrip().splitlines()

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
        line for line in lines[section_index + 1 : next_heading_index] if line.startswith("- [")
    ]
    if dedupe_predicate is None:
        existing_bullets = [line for line in existing_bullets if line != bullet]
    else:
        existing_bullets = [line for line in existing_bullets if not dedupe_predicate(line)]
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
        *payload.extra_writes,
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
