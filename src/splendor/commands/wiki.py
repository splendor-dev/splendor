"""Wiki maintenance commands."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter, QueueItemRecord, RunRecord, SourceRecord
from splendor.state.runtime import load_queue_item, load_run_record
from splendor.state.source_compat import canonical_source_ref
from splendor.state.source_registry import load_source_record
from splendor.utils.fs import write_text_atomic
from splendor.utils.wiki import parse_wiki_markdown, render_frontmatter

SYNTHESIS_KINDS = {"architecture", "concept", "entity", "glossary", "topic"}
_REVIEW_NEEDED_STATES = {"draft", "machine-generated", "contested", "stale"}
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
_SLUG_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_SOURCE_TERM_SECTIONS = {"summary", "key facts", "extract"}
_GENERATED_KEY_FACT_PREFIXES = (
    "- Source ID:",
    "- Source type:",
    "- Checksum:",
    "- Source ref:",
    "- Added at:",
    "- Ingested at:",
)
_STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "into",
    "md",
    "source",
    "sources",
    "summary",
    "the",
    "this",
    "that",
    "wiki",
    "with",
}
_TOPIC_TEMPLATES = {"default", "research-synthesis", "issue-tracker"}
_INDEX_SECTION_LABELS = {
    "architecture": "Architecture",
    "concept": "Concepts",
    "entity": "Entities",
    "glossary": "Glossary",
    "topic": "Topics",
    "source-summary": "Sources",
}
_INDEX_KIND_ORDER = ("architecture", "concept", "entity", "glossary", "topic", "source-summary")


@dataclass(frozen=True)
class WikiPageSnapshot:
    path: str
    frontmatter: KnowledgePageFrontmatter
    body: str


@dataclass(frozen=True)
class InvalidWikiPageSnapshot:
    path: str
    error: str


@dataclass(frozen=True)
class RecentRunSnapshot:
    run_id: str
    status: str
    finished_at: str | None
    source_ids: list[str]
    page_refs: list[str]


@dataclass(frozen=True)
class WikiStatus:
    source_total: int
    source_counts: dict[str, int]
    page_total: int
    page_kind_counts: dict[str, int]
    queue_total: int
    queue_status_counts: dict[str, int]
    run_total: int
    run_status_counts: dict[str, int]
    review_state_counts: dict[str, int]
    machine_generated_pages: int
    contested_pages: int
    stale_pages: int
    review_needed_pages: int
    review_needed_synthesis_pages: int
    sources_missing_synthesis: int
    invalid_pages: int
    invalid_page_examples: list[InvalidWikiPageSnapshot]
    recent_runs: list[RecentRunSnapshot]


@dataclass(frozen=True)
class WikiSuggestion:
    path: str
    page_id: str
    title: str
    kind: str
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WikiSuggestResult:
    source_id: str
    source_title: str
    source_ref: str
    source_status: str
    suggestions: list[WikiSuggestion]


@dataclass(frozen=True)
class WikiCompileContract:
    source_id: str
    source_title: str
    source_ref: str
    source_status: str
    mutates: bool
    status: str
    contract: list[str]
    next_steps: list[str]


@dataclass(frozen=True)
class TopicScaffoldResult:
    title: str
    page_id: str
    path: str
    tags: list[str]
    source_refs: list[str]
    template: str


@dataclass(frozen=True)
class WikiIndexEntry:
    kind: str
    title: str
    page_id: str
    path: str
    status: str
    review_state: str


@dataclass(frozen=True)
class WikiIndexRebuildResult:
    path: str
    page_count: int
    sections: dict[str, int]


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _require_initialized_wiki(root: Path, layout) -> None:
    missing = [
        _relative(root, path) for path in (layout.index_file, layout.log_file) if not path.exists()
    ]
    if missing:
        joined = ", ".join(missing)
        msg = f"Workspace is missing required wiki files: {joined}. Run `splendor init`."
        raise ValueError(msg)


def _validated_source_refs(layout, source_refs: list[str]) -> list[str]:
    validated_refs = _dedupe_preserve_order(source_refs)
    for source_ref in validated_refs:
        manifest_path = layout.source_records_dir / f"{source_ref}.json"
        if not manifest_path.exists():
            msg = f"Unknown source ref for topic page: {source_ref}"
            raise ValueError(msg)
        load_source_record(manifest_path)
    return validated_refs


def _slugify_title(title: str) -> str:
    slug = "-".join(_SLUG_TOKEN_PATTERN.findall(title.lower()))
    if not slug:
        msg = f"Could not derive a topic slug from title: {title!r}"
        raise ValueError(msg)
    return slug


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _render_source_ref_lines(source_refs: list[str]) -> str:
    if not source_refs:
        return "- Add source refs as this topic is synthesized.\n"
    return "".join(f"- `{source_ref}`\n" for source_ref in source_refs)


def _render_topic_body(frontmatter: KnowledgePageFrontmatter, *, template: str) -> str:
    source_ref_lines = _render_source_ref_lines(frontmatter.source_refs)
    if template == "research-synthesis":
        body = (
            "## Summary\n\n"
            "Draft the cross-source synthesis here.\n\n"
            "## Source-Backed Findings\n\n"
            "- Finding: TBD\n"
            "  - Sources: TBD\n\n"
            "## Open Questions\n\n"
            "- TBD\n\n"
            "## Source References\n\n"
            f"{source_ref_lines}"
        )
    elif template == "issue-tracker":
        body = (
            "## Summary\n\n"
            "Track related symptoms, root causes, and resolution status here.\n\n"
            "## Issues\n\n"
            "| Issue | Severity | Symptoms | Root Cause | Status | Source Refs |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| TBD | TBD | TBD | TBD | open | TBD |\n\n"
            "## Source References\n\n"
            f"{source_ref_lines}"
        )
    else:
        body = (
            "## Summary\n\n"
            "Draft the maintained topic synthesis here.\n\n"
            "## Notes\n\n"
            "- TBD\n\n"
            "## Source References\n\n"
            f"{source_ref_lines}"
        )
    return f"---\n{render_frontmatter(frontmatter)}\n---\n\n# {frontmatter.title}\n\n{body}"


def add_topic_page(
    root: Path,
    title: str,
    *,
    tags: list[str] | None = None,
    source_refs: list[str] | None = None,
    template: str = "default",
) -> TopicScaffoldResult:
    if template not in _TOPIC_TEMPLATES:
        msg = f"Unknown topic template: {template}"
        raise ValueError(msg)
    config = load_config(root)
    layout = resolve_layout(root, config)
    _require_initialized_wiki(root, layout)
    validated_source_refs = _validated_source_refs(layout, source_refs or [])
    slug = _slugify_title(title)
    page_id = f"topic-{slug}"
    page_path = layout.wiki_dir / "topics" / f"{slug}.md"
    page_ref = _relative(root, page_path)
    if page_path.exists():
        msg = f"Topic page already exists: {page_ref}"
        raise FileExistsError(msg)

    pages, invalid_pages = load_wiki_pages(root, layout)
    if invalid_pages:
        msg = f"Cannot add topic with invalid wiki pages present: {invalid_pages[0].path}"
        raise ValueError(msg)
    duplicate_path = next(
        (page.path for page in pages if page.frontmatter.page_id == page_id),
        None,
    )
    if duplicate_path is not None:
        msg = f"Topic page_id already exists in {duplicate_path}: {page_id}"
        raise FileExistsError(msg)

    frontmatter = KnowledgePageFrontmatter(
        kind="topic",
        title=title,
        page_id=page_id,
        status="active",
        review_state="draft",
        source_refs=validated_source_refs,
        tags=_dedupe_preserve_order(tags or []),
        confidence=0.0,
    )
    page_content = _render_topic_body(frontmatter, template=template)
    write_text_atomic(page_path, page_content)
    try:
        parse_wiki_markdown(page_path)
        rebuild_wiki_index(root)
    except Exception:
        page_path.unlink(missing_ok=True)
        raise

    return TopicScaffoldResult(
        title=title,
        page_id=page_id,
        path=page_ref,
        tags=frontmatter.tags,
        source_refs=frontmatter.source_refs,
        template=template,
    )


def rebuild_wiki_index(root: Path) -> WikiIndexRebuildResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    pages, invalid_pages = load_wiki_pages(root, layout)
    if invalid_pages:
        msg = f"Cannot rebuild index with invalid wiki pages present: {invalid_pages[0].path}"
        raise ValueError(msg)

    entries = [
        WikiIndexEntry(
            kind=page.frontmatter.kind,
            title=page.frontmatter.title,
            page_id=page.frontmatter.page_id,
            path=page.path,
            status=page.frontmatter.status,
            review_state=page.frontmatter.review_state,
        )
        for page in pages
    ]
    entries.sort(key=lambda entry: (entry.kind, entry.title.casefold(), entry.path))
    content = _render_rebuilt_index(entries)
    write_text_atomic(layout.index_file, content)
    section_counts = Counter(entry.kind for entry in entries)
    return WikiIndexRebuildResult(
        path=_relative(root, layout.index_file),
        page_count=len(entries),
        sections={kind: section_counts[kind] for kind in _INDEX_KIND_ORDER if section_counts[kind]},
    )


def _render_rebuilt_index(entries: list[WikiIndexEntry]) -> str:
    lines = [
        "# Splendor Wiki Index",
        "",
        "This wiki is maintained by Splendor.",
        "",
        "## Navigation",
        "",
        "- `wiki/sources/` for deterministic source summary pages.",
        "- `wiki/topics/` for maintained topic synthesis pages.",
        "- `planning/` for milestones, tasks, decisions, and questions.",
        "- `state/` for machine-readable queue, run, and manifest records.",
    ]
    for kind in _INDEX_KIND_ORDER:
        section_entries = [entry for entry in entries if entry.kind == kind]
        if not section_entries:
            continue
        lines.extend(["", f"## {_INDEX_SECTION_LABELS[kind]}", ""])
        lines.extend(_index_bullet(entry) for entry in section_entries)
    return "\n".join(lines).rstrip() + "\n"


def _index_bullet(entry: WikiIndexEntry) -> str:
    link = entry.path.removeprefix("wiki/")
    return (
        f"- [{entry.title}]({link}) (`{entry.page_id}`) "
        f"status={entry.status} review={entry.review_state}"
    )


def load_sources(layout) -> list[SourceRecord]:
    sources: list[SourceRecord] = []
    for manifest_path in sorted(layout.source_records_dir.glob("*.json")):
        sources.append(load_source_record(manifest_path))
    return sources


def _load_queue(layout) -> list[QueueItemRecord]:
    records: list[QueueItemRecord] = []
    for queue_path in sorted(layout.queue_dir.glob("*.json")):
        records.append(load_queue_item(queue_path))
    return records


def _load_runs(layout) -> list[RunRecord]:
    records: list[RunRecord] = []
    for run_path in sorted(layout.runs_dir.glob("*.json")):
        records.append(load_run_record(run_path))
    return records


def load_wiki_pages(
    root: Path, layout
) -> tuple[list[WikiPageSnapshot], list[InvalidWikiPageSnapshot]]:
    pages: list[WikiPageSnapshot] = []
    invalid_pages: list[InvalidWikiPageSnapshot] = []
    for page_path in sorted(layout.wiki_dir.rglob("*.md")):
        if page_path in {layout.index_file, layout.log_file}:
            continue
        page_ref = _relative(root, page_path)
        try:
            parsed = parse_wiki_markdown(page_path)
        except ValueError as exc:
            invalid_pages.append(InvalidWikiPageSnapshot(path=page_ref, error=str(exc)))
            continue
        pages.append(
            WikiPageSnapshot(
                path=page_ref,
                frontmatter=parsed.frontmatter,
                body=parsed.body,
            )
        )
    return pages, invalid_pages


def _sorted_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _recent_runs(runs: list[RunRecord]) -> list[RecentRunSnapshot]:
    ordered = sorted(
        runs,
        key=lambda run: (run.finished_at or run.started_at, run.run_id),
        reverse=True,
    )
    return [
        RecentRunSnapshot(
            run_id=run.run_id,
            status=run.status,
            finished_at=run.finished_at,
            source_ids=run.source_ids,
            page_refs=run.page_refs,
        )
        for run in ordered[:5]
    ]


def build_wiki_status(root: Path) -> WikiStatus:
    config = load_config(root)
    layout = resolve_layout(root, config)
    sources = load_sources(layout)
    pages, invalid_pages = load_wiki_pages(root, layout)
    queue_records = _load_queue(layout)
    runs = _load_runs(layout)

    source_counts = Counter(source.status for source in sources)
    page_kind_counts = Counter(page.frontmatter.kind for page in pages)
    queue_status_counts = Counter(record.status for record in queue_records)
    run_status_counts = Counter(run.status for run in runs)
    review_state_counts = Counter(page.frontmatter.review_state for page in pages)
    review_needed_pages = sum(
        1 for page in pages if page.frontmatter.review_state in _REVIEW_NEEDED_STATES
    )
    review_needed_synthesis_pages = sum(
        1
        for page in pages
        if page.frontmatter.kind in SYNTHESIS_KINDS
        and page.frontmatter.review_state in _REVIEW_NEEDED_STATES
    )

    synthesis_source_ids = {
        source_ref
        for page in pages
        if page.frontmatter.kind in SYNTHESIS_KINDS
        for source_ref in page.frontmatter.source_refs
    }
    synthesis_pages = [page for page in pages if page.frontmatter.kind in SYNTHESIS_KINDS]
    ingested_source_ids = {
        source.source_id
        for source in sources
        if source.status == "ingested"
        and not (
            source.source_id in synthesis_source_ids
            or any(canonical_source_ref(source) in page.body for page in synthesis_pages)
        )
    }

    return WikiStatus(
        source_total=len(sources),
        source_counts=_sorted_counts(source_counts),
        page_total=len(pages),
        page_kind_counts=_sorted_counts(page_kind_counts),
        queue_total=len(queue_records),
        queue_status_counts=_sorted_counts(queue_status_counts),
        run_total=len(runs),
        run_status_counts=_sorted_counts(run_status_counts),
        review_state_counts=_sorted_counts(review_state_counts),
        machine_generated_pages=review_state_counts["machine-generated"],
        contested_pages=review_state_counts["contested"],
        stale_pages=review_state_counts["stale"],
        review_needed_pages=review_needed_pages,
        review_needed_synthesis_pages=review_needed_synthesis_pages,
        sources_missing_synthesis=len(ingested_source_ids),
        invalid_pages=len(invalid_pages),
        invalid_page_examples=invalid_pages[:5],
        recent_runs=_recent_runs(runs),
    )


def _tokens(*values: str) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for token in _TOKEN_PATTERN.findall(value.lower()):
            normalized = token.strip("_-")
            if normalized and normalized not in _STOPWORDS:
                tokens.add(normalized)
    return tokens


def _source_summary_pages(pages: list[WikiPageSnapshot], source_id: str) -> list[WikiPageSnapshot]:
    return [
        page
        for page in pages
        if page.frontmatter.kind == "source-summary" and source_id in page.frontmatter.source_refs
    ]


def _section_text(body: str, included_headings: set[str]) -> str:
    sections: list[str] = []
    active_heading: str | None = None
    active = False
    in_fence = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence and line.startswith("#"):
            heading = line.lstrip("#").strip().strip("#").strip().lower()
            active_heading = heading
            active = heading in included_headings
            continue
        if active:
            if active_heading == "key facts" and raw_line.startswith(_GENERATED_KEY_FACT_PREFIXES):
                continue
            sections.append(raw_line)
    return "\n".join(sections)


def _source_terms(source: SourceRecord, summary_pages: list[WikiPageSnapshot]) -> set[str]:
    summary_text = " ".join(
        _section_text(page.body, _SOURCE_TERM_SECTIONS) for page in summary_pages
    )
    label_text = " ".join(source.source_labels)
    return _tokens(
        source.title,
        Path(canonical_source_ref(source)).stem,
        label_text,
        summary_text,
    )


def _score_page(
    *,
    source: SourceRecord,
    page: WikiPageSnapshot,
    source_terms: set[str],
) -> WikiSuggestion | None:
    score = 0
    reasons: list[str] = []
    page_text = " ".join(
        [
            page.frontmatter.title,
            page.frontmatter.page_id,
            page.path,
            page.body,
        ]
    )
    page_terms = _tokens(page_text)

    if source.source_id in page.frontmatter.source_refs:
        score += 100
        reasons.append("frontmatter-source-ref")
    if source.source_id in page.body:
        score += 80
        reasons.append("body-source-id")
    if canonical_source_ref(source) in page.body:
        score += 60
        reasons.append("body-source-ref")

    tag_overlap = source_terms & _tokens(" ".join(page.frontmatter.tags))
    if tag_overlap:
        score += min(45, len(tag_overlap) * 15)
        reasons.append("tag-overlap:" + ",".join(sorted(tag_overlap)))

    term_overlap = source_terms & page_terms
    if term_overlap:
        score += min(50, len(term_overlap) * 5)
        reasons.append("term-overlap:" + ",".join(sorted(term_overlap)[:8]))

    if score == 0:
        return None

    return WikiSuggestion(
        path=page.path,
        page_id=page.frontmatter.page_id,
        title=page.frontmatter.title,
        kind=page.frontmatter.kind,
        score=score,
        reasons=reasons,
    )


def suggest_source_pages(root: Path, source_id: str) -> WikiSuggestResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    manifest_path = layout.source_records_dir / f"{source_id}.json"
    if not manifest_path.exists():
        msg = f"Unknown source ID: {source_id}"
        raise FileNotFoundError(msg)

    source = load_source_record(manifest_path)
    pages, _invalid_pages = load_wiki_pages(root, layout)
    summaries = _source_summary_pages(pages, source_id)
    source_terms = _source_terms(source, summaries)
    suggestions = [
        suggestion
        for page in pages
        if page.frontmatter.kind in SYNTHESIS_KINDS
        for suggestion in [_score_page(source=source, page=page, source_terms=source_terms)]
        if suggestion is not None
    ]
    suggestions.sort(key=lambda suggestion: (-suggestion.score, suggestion.path))
    return WikiSuggestResult(
        source_id=source.source_id,
        source_title=source.title,
        source_ref=canonical_source_ref(source),
        source_status=source.status,
        suggestions=suggestions,
    )


def describe_wiki_compile_contract(root: Path, source_id: str) -> WikiCompileContract:
    config = load_config(root)
    layout = resolve_layout(root, config)
    manifest_path = layout.source_records_dir / f"{source_id}.json"
    if not manifest_path.exists():
        msg = f"Unknown source ID: {source_id}"
        raise FileNotFoundError(msg)

    source = load_source_record(manifest_path)
    return WikiCompileContract(
        source_id=source.source_id,
        source_title=source.title,
        source_ref=canonical_source_ref(source),
        source_status=source.status,
        mutates=False,
        status="contract-only",
        contract=[
            "Validate the source record and current source-summary page.",
            "Use `splendor wiki suggest <source-id>` to identify affected synthesis pages.",
            "Propose synthesis-page edits with source refs, provenance links, run state, "
            "and review state.",
            "Keep generated source-summary pages separate from maintained synthesis pages.",
            "Require human review before mutating wiki synthesis pages.",
        ],
        next_steps=[
            f"Run `splendor wiki suggest {source.source_id}`.",
            "Review suggested synthesis pages and apply changes through a reviewed future "
            "compile loop.",
        ],
    )


def render_wiki_status_json(status: WikiStatus) -> str:
    return json.dumps(
        {
            "source_total": status.source_total,
            "source_counts": status.source_counts,
            "page_total": status.page_total,
            "page_kind_counts": status.page_kind_counts,
            "queue_total": status.queue_total,
            "queue_status_counts": status.queue_status_counts,
            "run_total": status.run_total,
            "run_status_counts": status.run_status_counts,
            "review_state_counts": status.review_state_counts,
            "machine_generated_pages": status.machine_generated_pages,
            "contested_pages": status.contested_pages,
            "stale_pages": status.stale_pages,
            "review_needed_pages": status.review_needed_pages,
            "review_needed_synthesis_pages": status.review_needed_synthesis_pages,
            "sources_missing_synthesis": status.sources_missing_synthesis,
            "invalid_pages": status.invalid_pages,
            "invalid_page_examples": [asdict(page) for page in status.invalid_page_examples],
            "recent_runs": [asdict(run) for run in status.recent_runs],
        },
        indent=2,
    )


def render_wiki_suggest_json(result: WikiSuggestResult) -> str:
    return json.dumps(
        {
            "source_id": result.source_id,
            "source_title": result.source_title,
            "source_ref": result.source_ref,
            "source_status": result.source_status,
            "suggestions": [asdict(suggestion) for suggestion in result.suggestions],
        },
        indent=2,
    )


def render_wiki_compile_contract_json(result: WikiCompileContract) -> str:
    return json.dumps(asdict(result), indent=2)


def render_topic_scaffold_json(result: TopicScaffoldResult) -> str:
    return json.dumps(asdict(result), indent=2)


def render_wiki_index_rebuild_json(result: WikiIndexRebuildResult) -> str:
    return json.dumps(asdict(result), indent=2)
