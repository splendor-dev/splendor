"""Implementation for `splendor query`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from splendor.commands.source import resolve_source_query_matches
from splendor.config import load_config
from splendor.layout import ResolvedLayout, resolve_layout
from splendor.schemas import ProvenanceLink
from splendor.state.source_registry import load_source_record, manifest_path_for
from splendor.utils.planning import (
    iter_planning_paths,
    parse_planning_document,
    planning_directory,
    record_id_field,
)
from splendor.utils.wiki import parse_wiki_markdown

_PLANNING_KINDS = ("task", "milestone", "decision", "question")
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_CLAIM_SECTION_HEADINGS = {
    "core claims",
    "design implications",
    "product experience notes",
    "extract",
    "summary",
    "key facts",
}
_BOILERPLATE_PREFIXES = (
    "- Source ID:",
    "- Source type:",
    "- Source ref:",
    "- Checksum:",
    "- Added at:",
    "- Ingested at:",
    "- Pipeline version:",
    "- Storage mode:",
)
_BOILERPLATE_TERMS = {
    "checksum",
    "generated",
    "ingested",
    "machine",
    "metadata",
    "pipeline",
    "provenance",
    "source",
    "version",
}
_SEMANTIC_ALIASES = {
    "asr": ("automatic", "speech", "recognition"),
    "ci": ("continuous", "integration"),
    "cli": ("command", "line", "interface"),
    "ocr": ("optical", "character", "recognition"),
    "pr": ("pull", "request"),
    "ui": ("user", "interface"),
}


class QueryValidationError(ValueError):
    """Raised when the query text itself is invalid."""


@dataclass(frozen=True)
class QueryFilters:
    tags: list[str]
    source_id: str | None = None
    source_ids: list[str] | None = None

    @property
    def active(self) -> bool:
        return bool(self.tags or self.source_id or self.source_ids)


@dataclass(frozen=True)
class QueryMatch:
    rank: int
    score: int
    document_class: str
    kind: str
    record_id: str
    title: str
    path: str
    status: str | None
    record_origin: str | None
    generated_kind: str | None
    review_task_state: str | None
    review_state: str | None
    last_generated_at: str | None
    snippet: str
    source_refs: list[str]
    generated_by_run_ids: list[str]
    provenance_links: list[ProvenanceLink]
    contradiction_count: int
    review_task_ids: list[str]
    tags: list[str]


@dataclass(frozen=True)
class QueryResult:
    query: str
    filters: QueryFilters
    summary: str
    matches: list[QueryMatch]

    @property
    def match_count(self) -> int:
        return len(self.matches)


@dataclass(frozen=True)
class _QueryDocument:
    document_class: str
    kind: str
    record_id: str
    title: str
    path: str
    status: str | None
    record_origin: str | None
    generated_kind: str | None
    review_task_state: str | None
    review_state: str | None
    last_generated_at: str | None
    source_refs: list[str]
    generated_by_run_ids: list[str]
    provenance_links: list[ProvenanceLink]
    contradiction_count: int
    review_task_ids: list[str]
    tags: list[str]
    title_tokens: list[str]
    record_id_tokens: list[str]
    keyword_tokens: list[str]
    body_tokens: list[str]
    semantic_tokens: list[str]
    snippet_source: str


@dataclass(frozen=True)
class _ScoredDocument:
    score: int
    document: _QueryDocument
    snippet: str


def run_query(
    root: Path,
    question: str,
    *,
    tags: list[str] | None = None,
    source_id: str | None = None,
) -> QueryResult:
    normalized_query = question.strip()
    filters = _normalize_filters(root, tags=tags or [], source_id=source_id)
    query_tokens = _query_tokens(normalized_query) if normalized_query else []
    if normalized_query and not query_tokens:
        raise QueryValidationError("Query must contain at least one ASCII letter or number")
    if not query_tokens and not filters.active:
        raise QueryValidationError("Query must contain at least one ASCII letter or number")

    layout = resolve_layout(root, load_config(root))
    documents = [*_iter_wiki_documents(root, layout), *_iter_planning_documents(root, layout)]
    scored_documents: list[_ScoredDocument] = []
    for document in documents:
        if not _matches_filters(document, filters):
            continue
        score = _score_document(document, query_tokens) if query_tokens else _filter_score(document)
        if score <= 0:
            continue
        snippet = (
            _best_snippet(document.snippet_source, query_tokens)
            if query_tokens
            else _default_snippet(document.snippet_source)
        )
        scored_documents.append(
            _ScoredDocument(
                score=score,
                document=document,
                snippet=snippet,
            )
        )

    scored_documents.sort(
        key=lambda item: (-item.score, item.document.title.lower(), item.document.path)
    )
    matches = [
        QueryMatch(
            rank=index,
            score=item.score,
            document_class=item.document.document_class,
            kind=item.document.kind,
            record_id=item.document.record_id,
            title=item.document.title,
            path=item.document.path,
            status=item.document.status,
            record_origin=item.document.record_origin,
            generated_kind=item.document.generated_kind,
            review_task_state=item.document.review_task_state,
            review_state=item.document.review_state,
            last_generated_at=item.document.last_generated_at,
            snippet=item.snippet,
            source_refs=item.document.source_refs,
            generated_by_run_ids=item.document.generated_by_run_ids,
            provenance_links=item.document.provenance_links,
            contradiction_count=item.document.contradiction_count,
            review_task_ids=item.document.review_task_ids,
            tags=item.document.tags,
        )
        for index, item in enumerate(scored_documents, start=1)
    ]
    if matches:
        best = matches[0]
        summary = (
            f'Found {len(matches)} matching records. Best match: "{best.title}" ({best.path}).'
        )
    else:
        query_label = normalized_query or _filter_summary(filters)
        summary = f'No matches found for "{query_label}".'
    return QueryResult(query=normalized_query, filters=filters, summary=summary, matches=matches)


def _normalize_filters(root: Path, *, tags: list[str], source_id: str | None) -> QueryFilters:
    normalized_tags = _normalize_tags(tags)
    normalized_source_id = source_id.strip() if source_id is not None else None
    normalized_source_ids: list[str] | None = None
    if normalized_source_id:
        resolved_sources = resolve_source_query_matches(root, normalized_source_id)
        normalized_source_ids = [match.source.source_id for match in resolved_sources]
        normalized_source_id = normalized_source_ids[0]
        for resolved_source_id in normalized_source_ids:
            manifest_path = manifest_path_for(root, resolved_source_id)
            if not manifest_path.exists():
                msg = f"Unknown source ID: {resolved_source_id}"
                raise FileNotFoundError(msg)
            source = load_source_record(manifest_path)
            if source.source_id != resolved_source_id:
                msg = f"Source manifest ID does not match requested source: {resolved_source_id}"
                raise ValueError(msg)
    return QueryFilters(
        tags=normalized_tags,
        source_id=normalized_source_id,
        source_ids=normalized_source_ids,
    )


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = tag.strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        normalized.append(value)
        seen.add(key)
    return normalized


def _matches_filters(document: _QueryDocument, filters: QueryFilters) -> bool:
    if filters.source_ids is not None and not set(filters.source_ids).intersection(
        document.source_refs
    ):
        return False
    if filters.tags:
        document_tags = {tag.casefold() for tag in document.tags}
        if not all(tag.casefold() in document_tags for tag in filters.tags):
            return False
    return True


def _filter_score(document: _QueryDocument) -> int:
    score = 1
    if document.document_class == "wiki":
        score += 2
    if document.kind == "source-summary":
        score += 1
    return score


def _filter_summary(filters: QueryFilters) -> str:
    parts: list[str] = []
    if filters.tags:
        parts.append("tags " + ", ".join(filters.tags))
    if filters.source_id is not None:
        parts.append(f"source {filters.source_id}")
    return "; ".join(parts) or "filters"


def _iter_wiki_documents(root: Path, layout: ResolvedLayout) -> list[_QueryDocument]:
    documents: list[_QueryDocument] = []
    for path in sorted(layout.wiki_dir.rglob("*.md")):
        if path.name == ".gitkeep":
            continue
        if path == layout.index_file or path == layout.log_file:
            continue
        parsed = parse_wiki_markdown(path)
        frontmatter = parsed.frontmatter
        documents.append(
            _QueryDocument(
                document_class="wiki",
                kind=frontmatter.kind,
                record_id=frontmatter.page_id,
                title=frontmatter.title,
                path=path.relative_to(root).as_posix(),
                status=frontmatter.status,
                record_origin=None,
                generated_kind=None,
                review_task_state=None,
                review_state=frontmatter.review_state,
                last_generated_at=frontmatter.last_generated_at,
                source_refs=list(frontmatter.source_refs),
                generated_by_run_ids=list(frontmatter.generated_by_run_ids),
                provenance_links=list(frontmatter.provenance_links),
                contradiction_count=len(frontmatter.contradictions),
                review_task_ids=sorted(
                    {item.review_task_id for item in frontmatter.contradictions}
                ),
                tags=list(frontmatter.tags),
                title_tokens=_content_tokens(frontmatter.title),
                record_id_tokens=_content_tokens(frontmatter.page_id),
                keyword_tokens=_content_tokens(
                    " ".join([frontmatter.kind, frontmatter.status, *frontmatter.tags])
                ),
                body_tokens=_content_tokens(parsed.body),
                semantic_tokens=_semantic_tokens(
                    " ".join(
                        [
                            frontmatter.title,
                            frontmatter.page_id,
                            frontmatter.kind,
                            frontmatter.status,
                            " ".join(frontmatter.tags),
                            parsed.body,
                        ]
                    )
                ),
                snippet_source=parsed.body,
            )
        )
    return documents


def _iter_planning_documents(root: Path, layout: ResolvedLayout) -> list[_QueryDocument]:
    from splendor.commands.planning import model_for_planning_kind

    documents: list[_QueryDocument] = []
    for kind in _PLANNING_KINDS:
        model = model_for_planning_kind(kind)
        for path in iter_planning_paths(planning_directory(layout, kind)):
            parsed = parse_planning_document(path, model)
            record = parsed.record
            payload = record.model_dump(mode="json")
            record_id = str(getattr(record, record_id_field(kind)))
            status = payload.get("status")
            record_origin = payload.get("record_origin")
            generated_kind = payload.get("generated_kind")
            review_task_state = payload.get("review_task_state")
            source_refs = list(payload.get("source_refs", []))
            keyword_values = [kind]
            if isinstance(status, str):
                keyword_values.append(status)
            search_values = [record.title]
            for key, value in payload.items():
                if key in {"schema_version", "kind", "title", record_id_field(kind)}:
                    continue
                search_values.extend(_flatten_search_values(value))
            search_values.append(parsed.body)
            search_body = "\n".join(search_values)
            documents.append(
                _QueryDocument(
                    document_class="planning",
                    kind=kind,
                    record_id=record_id,
                    title=record.title,
                    path=path.relative_to(root).as_posix(),
                    status=status if isinstance(status, str) else None,
                    record_origin=record_origin if isinstance(record_origin, str) else None,
                    generated_kind=generated_kind if isinstance(generated_kind, str) else None,
                    review_task_state=(
                        review_task_state if isinstance(review_task_state, str) else None
                    ),
                    review_state=None,
                    last_generated_at=None,
                    source_refs=source_refs,
                    generated_by_run_ids=[],
                    provenance_links=[],
                    contradiction_count=0,
                    review_task_ids=[],
                    tags=[],
                    title_tokens=_content_tokens(record.title),
                    record_id_tokens=_content_tokens(record_id),
                    keyword_tokens=_content_tokens(" ".join(keyword_values)),
                    body_tokens=_content_tokens(search_body),
                    semantic_tokens=_semantic_tokens(
                        " ".join([record.title, record_id, " ".join(keyword_values), search_body])
                    ),
                    snippet_source=parsed.body,
                )
            )
    return documents


def _flatten_search_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _query_tokens(text: str) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_PATTERN.findall(text.lower()):
        if token not in seen:
            deduped.append(token)
            seen.add(token)
    return deduped


def _content_tokens(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _semantic_tokens(text: str) -> list[str]:
    tokens = _content_tokens(text)
    semantic: list[str] = []
    for token in tokens:
        semantic.extend(_SEMANTIC_ALIASES.get(token, ()))

    for alias, phrase in _SEMANTIC_ALIASES.items():
        if _contains_token_sequence(tokens, phrase):
            semantic.append(alias)
    return semantic


def _contains_token_sequence(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    if not phrase or len(phrase) > len(tokens):
        return False
    return any(tuple(tokens[index : index + len(phrase)]) == phrase for index in range(len(tokens)))


def _score_document(document: _QueryDocument, query_tokens: list[str]) -> int:
    lexical_score = 0
    for token in query_tokens:
        lexical_score += 5 * document.title_tokens.count(token)
        lexical_score += 4 * document.record_id_tokens.count(token)
        lexical_score += 3 * document.keyword_tokens.count(token)
        lexical_score += document.body_tokens.count(token)
    semantic_score = sum(document.semantic_tokens.count(token) for token in query_tokens)
    semantic_boost = min(1, semantic_score)
    return lexical_score + semantic_boost if lexical_score > 0 else semantic_boost


def _best_snippet(text: str, query_tokens: list[str]) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    paragraphs = _candidate_segments(normalized)
    lines = _snippet_lines(normalized)
    candidates = _unique_in_order([*paragraphs, *lines])
    if not candidates:
        return ""
    best = max(
        candidates,
        key=lambda candidate: (
            _candidate_score(candidate, query_tokens),
            -_boilerplate_score(candidate),
            -len(candidate),
        ),
    )
    if _candidate_score(best, query_tokens) <= 0:
        best = paragraphs[0] if paragraphs else lines[0]
    collapsed = _WHITESPACE_PATTERN.sub(" ", _strip_candidate_heading(best)).strip()
    if len(collapsed) <= 240:
        return collapsed
    return collapsed[:237].rstrip() + "..."


def _default_snippet(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""
    candidates = _unique_in_order([*_candidate_segments(normalized), *_snippet_lines(normalized)])
    if not candidates:
        return ""
    collapsed = _WHITESPACE_PATTERN.sub(" ", _strip_candidate_heading(candidates[0])).strip()
    if len(collapsed) <= 240:
        return collapsed
    return collapsed[:237].rstrip() + "..."


def _candidate_score(candidate: str, query_tokens: list[str]) -> int:
    candidate_tokens = _content_tokens(candidate)
    token_score = sum(candidate_tokens.count(token) for token in query_tokens)
    semantic_score = sum(_semantic_tokens(candidate).count(token) for token in query_tokens)
    if token_score == 0 and semantic_score == 0:
        return 0
    heading = _candidate_heading(candidate)
    heading_bonus = 0
    if heading in _CLAIM_SECTION_HEADINGS:
        heading_bonus = 3
    boilerplate_penalty = _boilerplate_score(candidate)
    semantic_boost = min(1, semantic_score)
    if token_score == 0:
        return semantic_boost - boilerplate_penalty
    return token_score + semantic_boost + heading_bonus - boilerplate_penalty


def _candidate_segments(text: str) -> list[str]:
    segments: list[str] = []
    active_heading: str | None = None
    active_lines: list[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not in_fence and _is_heading(line):
            if active_lines:
                segments.extend(_section_segments(active_heading, active_lines))
            active_heading = line.lstrip("#").strip().strip("#").strip().lower()
            active_lines = []
            continue
        active_lines.append(raw_line)
    if active_lines:
        segments.extend(_section_segments(active_heading, active_lines))
    return segments


def _snippet_lines(text: str) -> list[str]:
    lines: list[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _is_fence(line):
            in_fence = not in_fence
            continue
        if in_fence or not line or _is_heading(line):
            continue
        lines.append(line)
    return lines


def _section_segments(heading: str | None, lines: list[str]) -> list[str]:
    text = "\n".join(lines).strip()
    if not text:
        return []
    prefix = f"__heading__:{heading}\n" if heading else ""
    return [
        prefix + segment.strip()
        for segment in re.split(r"\n\s*\n", text)
        if segment.strip() and not _is_boilerplate_line(segment.strip())
    ]


def _candidate_heading(candidate: str) -> str | None:
    if not candidate.startswith("__heading__:"):
        return None
    first_line, *_rest = candidate.split("\n", 1)
    return first_line.removeprefix("__heading__:") or None


def _strip_candidate_heading(candidate: str) -> str:
    if not candidate.startswith("__heading__:"):
        return candidate
    return candidate.split("\n", 1)[1] if "\n" in candidate else ""


def _boilerplate_score(candidate: str) -> int:
    stripped = _strip_candidate_heading(candidate)
    if _is_boilerplate_line(stripped):
        return 4
    tokens = set(_content_tokens(stripped))
    return min(3, len(tokens & _BOILERPLATE_TERMS))


def _is_boilerplate_line(line: str) -> bool:
    return line.startswith(_BOILERPLATE_PREFIXES)


def _is_heading(line: str) -> bool:
    return line.startswith("#")


def _is_fence(line: str) -> bool:
    return line.startswith("```") or line.startswith("~~~")


def _unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return unique
