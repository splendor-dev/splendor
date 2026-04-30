"""Read-only wiki maintenance commands."""

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
from splendor.state.source_registry import load_source_record, manifest_path_for
from splendor.utils.wiki import parse_wiki_markdown

_SYNTHESIS_KINDS = {"architecture", "concept", "entity", "glossary", "topic"}
_REVIEW_NEEDED_STATES = {"draft", "machine-generated", "contested", "stale"}
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")
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


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _load_sources(layout) -> list[SourceRecord]:
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


def _load_wiki_pages(
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
    sources = _load_sources(layout)
    pages, invalid_pages = _load_wiki_pages(root, layout)
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
        if page.frontmatter.kind in _SYNTHESIS_KINDS
        and page.frontmatter.review_state in _REVIEW_NEEDED_STATES
    )

    synthesis_source_ids = {
        source_ref
        for page in pages
        if page.frontmatter.kind in _SYNTHESIS_KINDS
        for source_ref in page.frontmatter.source_refs
    }
    synthesis_pages = [page for page in pages if page.frontmatter.kind in _SYNTHESIS_KINDS]
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
            if active:
                sections.append(raw_line)
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
            " ".join(page.frontmatter.tags),
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
    manifest_path = manifest_path_for(root, source_id)
    if not manifest_path.exists():
        msg = f"Unknown source ID: {source_id}"
        raise FileNotFoundError(msg)

    source = load_source_record(manifest_path)
    pages, _invalid_pages = _load_wiki_pages(root, layout)
    summaries = _source_summary_pages(pages, source_id)
    source_terms = _source_terms(source, summaries)
    suggestions = [
        suggestion
        for page in pages
        if page.frontmatter.kind in _SYNTHESIS_KINDS
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
