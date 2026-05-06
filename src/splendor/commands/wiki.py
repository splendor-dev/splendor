"""Wiki maintenance commands."""

from __future__ import annotations

import json
import posixpath
import re
import shlex
from collections import Counter
from dataclasses import asdict, dataclass, field
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import ValidationError

from splendor.commands.mutation import mutation_contract, mutation_record
from splendor.commands.source import resolve_source_query, resolve_source_query_matches
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter, QueueItemRecord, RunRecord, SourceRecord
from splendor.state.runtime import load_queue_item, load_run_record
from splendor.state.source_compat import canonical_source_ref
from splendor.state.source_registry import load_source_record
from splendor.utils.fs import write_text_atomic
from splendor.utils.provenance import dedupe_provenance_links, make_provenance_link
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
    compile_preview_args: list[str] = field(default_factory=list)
    compile_preview_command: str = ""


@dataclass(frozen=True)
class WikiSuggestResult:
    source_id: str
    source_ids: list[str]
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
    suggested_pages: list[WikiSuggestion]
    next_steps: list[str]


@dataclass(frozen=True)
class WikiCompileProposal:
    source_id: str
    source_title: str
    source_ref: str
    source_status: str
    target_path: str
    target_page_id: str
    target_title: str
    target_kind: str
    source_summary_path: str
    mode: str
    status: str
    mutates: bool
    applied: bool
    changed: bool
    evidence_lines: list[str]
    evidence_sections: list[str]
    proposed_source_refs: list[str]
    target_sha256: str
    source_summary_sha256: str
    proposal_hash: str
    proposed_diff: str
    proposed_markdown: str


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


def plan_wiki_index_rebuild(root: Path) -> WikiIndexRebuildResult:
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
    section_counts = Counter(entry.kind for entry in entries)
    return WikiIndexRebuildResult(
        path=_relative(root, layout.index_file),
        page_count=len(entries),
        sections={kind: section_counts[kind] for kind in _INDEX_KIND_ORDER if section_counts[kind]},
    )


def rebuild_wiki_index(root: Path) -> WikiIndexRebuildResult:
    result = plan_wiki_index_rebuild(root)
    config = load_config(root)
    layout = resolve_layout(root, config)
    pages, _invalid_pages = load_wiki_pages(root, layout)
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
    write_text_atomic(layout.index_file, _render_rebuilt_index(entries))
    return result


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
        compile_preview_args=[],
        compile_preview_command="",
    )


def _score_page_for_sources(
    *,
    sources: list[SourceRecord],
    page: WikiPageSnapshot,
    source_terms: set[str],
) -> WikiSuggestion | None:
    scored = [
        suggestion
        for source in sources
        for suggestion in [_score_page(source=source, page=page, source_terms=source_terms)]
        if suggestion is not None
    ]
    if not scored:
        return None
    best = max(scored, key=lambda suggestion: (suggestion.score, -len(suggestion.reasons)))
    reasons = sorted({reason for suggestion in scored for reason in suggestion.reasons})
    return WikiSuggestion(
        path=best.path,
        page_id=best.page_id,
        title=best.title,
        kind=best.kind,
        score=max(suggestion.score for suggestion in scored),
        reasons=reasons,
        compile_preview_args=[],
        compile_preview_command="",
    )


def suggest_source_pages(root: Path, source_id: str) -> WikiSuggestResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    source_matches = resolve_source_query_matches(root, source_id)
    sources = [match.source for match in source_matches]
    source = sources[0]
    pages, _invalid_pages = load_wiki_pages(root, layout)
    source_terms: set[str] = set()
    for matched_source in sources:
        summaries = _source_summary_pages(pages, matched_source.source_id)
        source_terms.update(_source_terms(matched_source, summaries))
    suggestions = [
        suggestion
        for page in pages
        if page.frontmatter.kind in SYNTHESIS_KINDS
        for suggestion in [
            _score_page_for_sources(sources=sources, page=page, source_terms=source_terms)
        ]
        if suggestion is not None
    ]
    suggestions.sort(key=lambda suggestion: (-suggestion.score, suggestion.path))
    suggestions = [
        WikiSuggestion(
            path=suggestion.path,
            page_id=suggestion.page_id,
            title=suggestion.title,
            kind=suggestion.kind,
            score=suggestion.score,
            reasons=suggestion.reasons,
            compile_preview_args=_compile_preview_args(source.source_id, suggestion.path),
            compile_preview_command=_compile_preview_command(source.source_id, suggestion.path),
        )
        for suggestion in suggestions
    ]
    return WikiSuggestResult(
        source_id=source.source_id,
        source_ids=[matched_source.source_id for matched_source in sources],
        source_title=source.title,
        source_ref=canonical_source_ref(source),
        source_status=source.status,
        suggestions=suggestions,
    )


def describe_wiki_compile_contract(root: Path, source_id: str) -> WikiCompileContract:
    suggest_result = suggest_source_pages(root, source_id)
    return WikiCompileContract(
        source_id=suggest_result.source_id,
        source_title=suggest_result.source_title,
        source_ref=suggest_result.source_ref,
        source_status=suggest_result.source_status,
        mutates=False,
        status="contract-only",
        contract=[
            "Validate the source record and current source-summary page.",
            "Use ranked maintained-page suggestions to choose one explicit compile target.",
            "Propose synthesis-page edits with source refs, provenance links, run state, "
            "and review state.",
            "Keep generated source-summary pages separate from maintained synthesis pages.",
            "Require human review before mutating wiki synthesis pages.",
        ],
        suggested_pages=suggest_result.suggestions,
        next_steps=[
            f"Run `splendor wiki suggest {suggest_result.source_id}` to inspect ranking reasons.",
            *[
                f"Preview `{suggestion.compile_preview_command}`."
                for suggestion in suggest_result.suggestions[:3]
            ],
            *(
                []
                if suggest_result.suggestions
                else [
                    "Create or choose one maintained topic, concept, entity, architecture, "
                    "or glossary page, then rerun `splendor wiki compile "
                    f"{suggest_result.source_id} --page <page>`."
                ]
            ),
        ],
    )


def _compile_preview_args(source_id: str, page_path: str) -> list[str]:
    return ["splendor", "wiki", "compile", source_id, "--page", page_path]


def _compile_preview_command(source_id: str, page_path: str) -> str:
    return shlex.join(_compile_preview_args(source_id, page_path))


def compile_source_into_page(
    root: Path,
    source_id: str,
    *,
    page_query: str,
    apply: bool = False,
    proposal_hash: str | None = None,
) -> WikiCompileProposal:
    config = load_config(root)
    layout = resolve_layout(root, config)
    source = resolve_source_query(root, source_id).source
    pages, invalid_pages = load_wiki_pages(root, layout)
    if invalid_pages:
        msg = f"Cannot compile with invalid wiki pages present: {invalid_pages[0].path}"
        raise ValueError(msg)

    target_page = _resolve_compile_target_page(root, layout, pages, page_query)
    if target_page.frontmatter.kind not in SYNTHESIS_KINDS:
        msg = (
            "Compile target must be a maintained synthesis page "
            f"({', '.join(sorted(SYNTHESIS_KINDS))}), got {target_page.frontmatter.kind}: "
            f"{target_page.path}"
        )
        raise ValueError(msg)

    summary_page = _single_source_summary_page(pages, source.source_id)
    evidence_lines, evidence_sections = _compile_evidence_lines(summary_page.body)
    if not evidence_lines:
        msg = f"Source summary has no deterministic evidence lines: {summary_page.path}"
        raise ValueError(msg)

    proposed_frontmatter = _compile_frontmatter(
        target_page.frontmatter,
        source_id=source.source_id,
        summary_page_id=summary_page.frontmatter.page_id,
        summary_path=summary_page.path,
    )
    proposed_body = _compile_body(
        target_page.body,
        source=source,
        target_path=target_page.path,
        summary_path=summary_page.path,
        evidence_lines=evidence_lines,
    )
    proposed_markdown = _render_wiki_page(proposed_frontmatter, proposed_body)
    _validate_compiled_markdown(target_page.path, proposed_markdown)

    target_path = root / target_page.path
    current_markdown = target_path.read_text(encoding="utf-8")
    summary_markdown = (root / summary_page.path).read_text(encoding="utf-8")
    target_sha = _sha256_text(current_markdown)
    summary_sha = _sha256_text(summary_markdown)
    computed_proposal_hash = _compile_proposal_hash(
        source_id=source.source_id,
        target_path=target_page.path,
        target_sha256=target_sha,
        source_summary_path=summary_page.path,
        source_summary_sha256=summary_sha,
        proposed_markdown=proposed_markdown,
    )
    proposed_diff = _render_compile_diff(
        target_path=target_page.path,
        current_markdown=current_markdown,
        proposed_markdown=proposed_markdown,
    )
    changed = current_markdown != proposed_markdown
    if apply and proposal_hash != computed_proposal_hash:
        msg = (
            "wiki compile --apply requires the proposal hash from the reviewed preview. "
            f"Expected {computed_proposal_hash} for the current inputs."
        )
        raise ValueError(msg)
    if apply and changed:
        write_text_atomic(target_path, proposed_markdown)

    status = "applied" if apply and changed else "no-op" if not changed else "proposed"
    return WikiCompileProposal(
        source_id=source.source_id,
        source_title=source.title,
        source_ref=canonical_source_ref(source),
        source_status=source.status,
        target_path=target_page.path,
        target_page_id=target_page.frontmatter.page_id,
        target_title=target_page.frontmatter.title,
        target_kind=target_page.frontmatter.kind,
        source_summary_path=summary_page.path,
        mode="apply" if apply else "preview",
        status=status,
        mutates=apply and changed,
        applied=apply and changed,
        changed=changed,
        evidence_lines=evidence_lines,
        evidence_sections=evidence_sections,
        proposed_source_refs=proposed_frontmatter.source_refs,
        target_sha256=target_sha,
        source_summary_sha256=summary_sha,
        proposal_hash=computed_proposal_hash,
        proposed_diff=proposed_diff,
        proposed_markdown=proposed_markdown,
    )


def _resolve_compile_target_page(
    root: Path,
    layout,
    pages: list[WikiPageSnapshot],
    page_query: str,
) -> WikiPageSnapshot:
    raw_path = Path(page_query)
    candidate_paths: list[Path] = []
    if raw_path.is_absolute():
        candidate_paths.append(raw_path)
    else:
        candidate_paths.extend([root / raw_path, layout.wiki_dir / raw_path])

    for candidate_path in candidate_paths:
        if not candidate_path.exists():
            continue
        resolved = candidate_path.resolve()
        if not resolved.is_relative_to(root):
            msg = f"Compile target must be inside the workspace: {page_query}"
            raise ValueError(msg)
        page_ref = _relative(root, resolved)
        matches = [page for page in pages if page.path == page_ref]
        if matches:
            return matches[0]

    exact_matches = [
        page
        for page in pages
        if page.frontmatter.page_id == page_query or page.frontmatter.title == page_query
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        msg = f"Ambiguous compile target: {page_query}"
        raise ValueError(msg)
    msg = f"Unknown compile target page: {page_query}"
    raise ValueError(msg)


def _single_source_summary_page(pages: list[WikiPageSnapshot], source_id: str) -> WikiPageSnapshot:
    summary_pages = _source_summary_pages(pages, source_id)
    if len(summary_pages) == 1:
        return summary_pages[0]
    if not summary_pages:
        msg = f"Source has no generated source-summary page yet: {source_id}"
        raise ValueError(msg)
    msg = f"Source has multiple source-summary pages: {source_id}"
    raise ValueError(msg)


def _compile_frontmatter(
    frontmatter: KnowledgePageFrontmatter,
    *,
    source_id: str,
    summary_page_id: str,
    summary_path: str,
) -> KnowledgePageFrontmatter:
    source_refs = _dedupe_preserve_order([*frontmatter.source_refs, source_id])
    provenance_links = dedupe_provenance_links(
        [
            *frontmatter.provenance_links,
            make_provenance_link(
                source_id=source_id,
                role="supports",
                note="Compiled source evidence accepted into maintained synthesis.",
            ),
            make_provenance_link(
                page_id=summary_page_id,
                path_ref=summary_path,
                role="generated-from",
                note="Generated source-summary page used as compile evidence.",
            ),
        ]
    )
    return frontmatter.model_copy(
        update={"source_refs": source_refs, "provenance_links": provenance_links}
    )


def _compile_body(
    body: str,
    *,
    source: SourceRecord,
    target_path: str,
    summary_path: str,
    evidence_lines: list[str],
) -> str:
    start_marker = f"<!-- splendor-compile:start source={source.source_id} -->"
    if start_marker in body:
        return body
    summary_link = posixpath.relpath(summary_path, start=posixpath.dirname(target_path))
    evidence = "\n".join(f"- {line}" for line in evidence_lines)
    block = (
        f"### {source.title}\n\n"
        f"{start_marker}\n"
        f"- Source ref: `{canonical_source_ref(source)}`\n"
        f"- Source summary: [{summary_path}]({summary_link})\n\n"
        "#### Evidence\n\n"
        f"{evidence}\n"
        f"<!-- splendor-compile:end source={source.source_id} -->\n"
    )
    section_heading = "## Compiled Source Evidence"
    section_intro = (
        "This managed section records reviewed source-summary evidence accepted into this "
        "maintained page.\n"
    )
    if section_heading in body:
        return _append_to_compiled_evidence_section(body, section_heading, block)
    return body.rstrip() + f"\n\n{section_heading}\n\n{section_intro}\n{block}"


def _append_to_compiled_evidence_section(body: str, section_heading: str, block: str) -> str:
    lines = body.rstrip().splitlines()
    section_index = next(
        (index for index, line in enumerate(lines) if line.strip() == section_heading),
        None,
    )
    if section_index is None:
        return body.rstrip() + "\n\n" + block
    next_section_index = next(
        (
            index
            for index, line in enumerate(lines[section_index + 1 :], start=section_index + 1)
            if line.startswith("## ") and line.strip() != section_heading
        ),
        len(lines),
    )
    before = "\n".join(lines[:next_section_index]).rstrip()
    after = "\n".join(lines[next_section_index:]).strip()
    updated = before + "\n\n" + block.rstrip()
    if after:
        updated += "\n\n" + after
    return updated + "\n"


def _compile_evidence_lines(summary_body: str) -> tuple[list[str], list[str]]:
    return _compile_evidence_lines_from_sections(summary_body, ["summary", "key facts"])


def _compile_evidence_lines_from_sections(
    summary_body: str, headings: list[str]
) -> tuple[list[str], list[str]]:
    section_text = _section_text(summary_body, set(headings))
    lines: list[str] = []
    in_fence = False
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("#"):
            continue
        if line.startswith(_GENERATED_KEY_FACT_PREFIXES):
            continue
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if len(line) > 180:
            line = line[:177].rstrip() + "..."
        if line not in lines:
            lines.append(line)
        if len(lines) == 5:
            break
    return lines, headings if lines else []


def _render_wiki_page(frontmatter: KnowledgePageFrontmatter, body: str) -> str:
    normalized_body = body.strip()
    return f"---\n{render_frontmatter(frontmatter)}\n---\n\n{normalized_body}\n"


def _validate_compiled_markdown(page_ref: str, content: str) -> None:
    try:
        frontmatter_text, body = content.removeprefix("---\n").split("\n---\n", maxsplit=1)
    except ValueError as exc:
        msg = f"Compiled page {page_ref} has malformed YAML frontmatter"
        raise ValueError(msg) from exc
    try:
        payload = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        msg = f"Compiled page {page_ref} has invalid YAML frontmatter"
        raise ValueError(msg) from exc
    try:
        KnowledgePageFrontmatter.model_validate(payload)
    except ValidationError as exc:
        msg = f"Compiled page {page_ref} failed schema validation: {exc}"
        raise ValueError(msg) from exc
    if not body.startswith("\n"):
        msg = f"Compiled page lost markdown body separation: {page_ref}"
        raise ValueError(msg)


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _compile_proposal_hash(
    *,
    source_id: str,
    target_path: str,
    target_sha256: str,
    source_summary_path: str,
    source_summary_sha256: str,
    proposed_markdown: str,
) -> str:
    payload = {
        "source_id": source_id,
        "target_path": target_path,
        "target_sha256": target_sha256,
        "source_summary_path": source_summary_path,
        "source_summary_sha256": source_summary_sha256,
        "proposed_markdown_sha256": _sha256_text(proposed_markdown),
    }
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _render_compile_diff(
    *,
    target_path: str,
    current_markdown: str,
    proposed_markdown: str,
) -> str:
    diff_lines = unified_diff(
        current_markdown.splitlines(),
        proposed_markdown.splitlines(),
        fromfile=target_path,
        tofile=f"{target_path} (proposed)",
        lineterm="",
    )
    diff_text = "\n".join(diff_lines)
    if diff_text:
        return diff_text + "\n"
    return ""


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
            "source_ids": result.source_ids,
            "source_title": result.source_title,
            "source_ref": result.source_ref,
            "source_status": result.source_status,
            "suggestions": [asdict(suggestion) for suggestion in result.suggestions],
        },
        indent=2,
    )


def render_wiki_compile_contract_json(result: WikiCompileContract) -> str:
    payload = asdict(result)
    payload["mutation"] = mutation_contract(mode="preview")
    return json.dumps(payload, indent=2)


def render_wiki_compile_proposal_json(result: WikiCompileProposal) -> str:
    payload = asdict(result)
    record = mutation_record(
        action="write",
        path=result.target_path,
        kind="maintained_wiki_page",
        source_id=result.source_id,
    )
    payload["mutation"] = mutation_contract(
        mode=result.mode,
        planned=[record] if result.mode == "preview" and result.changed else [],
        written=[record] if result.mode == "apply" and result.changed else [],
    )
    return json.dumps(payload, indent=2)


def render_topic_scaffold_json(result: TopicScaffoldResult) -> str:
    return json.dumps(asdict(result), indent=2)


def render_wiki_index_rebuild_json(result: WikiIndexRebuildResult) -> str:
    return json.dumps(asdict(result), indent=2)
