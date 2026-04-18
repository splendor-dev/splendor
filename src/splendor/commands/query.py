"""Implementation for `splendor query`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.utils.planning import iter_planning_paths, parse_planning_markdown, planning_directory
from splendor.utils.wiki import parse_wiki_markdown

_PLANNING_KINDS = ("task", "milestone", "decision", "question")
_PLANNING_ID_FIELDS = {
    "task": "task_id",
    "milestone": "milestone_id",
    "decision": "decision_id",
    "question": "question_id",
}
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")


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
    snippet: str
    source_refs: list[str]
    generated_by_run_ids: list[str]
    tags: list[str]


@dataclass(frozen=True)
class QueryResult:
    query: str
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
    source_refs: list[str]
    generated_by_run_ids: list[str]
    tags: list[str]
    title_tokens: list[str]
    record_id_tokens: list[str]
    keyword_tokens: list[str]
    body_tokens: list[str]
    snippet_source: str


@dataclass(frozen=True)
class _ScoredDocument:
    score: int
    document: _QueryDocument
    snippet: str


def run_query(root: Path, question: str) -> QueryResult:
    normalized_query = question.strip()
    query_tokens = _query_tokens(normalized_query)
    if not query_tokens:
        raise ValueError("Query must contain at least one ASCII letter or number")

    documents = [*_iter_wiki_documents(root), *_iter_planning_documents(root)]
    scored_documents: list[_ScoredDocument] = []
    for document in documents:
        score = _score_document(document, query_tokens)
        if score <= 0:
            continue
        scored_documents.append(
            _ScoredDocument(
                score=score,
                document=document,
                snippet=_best_snippet(document.snippet_source, query_tokens),
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
            snippet=item.snippet,
            source_refs=item.document.source_refs,
            generated_by_run_ids=item.document.generated_by_run_ids,
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
        summary = f'No matches found for "{normalized_query}".'
    return QueryResult(query=normalized_query, summary=summary, matches=matches)


def _iter_wiki_documents(root: Path) -> list[_QueryDocument]:
    layout = resolve_layout(root, load_config(root))
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
                source_refs=list(frontmatter.source_refs),
                generated_by_run_ids=list(frontmatter.generated_by_run_ids),
                tags=list(frontmatter.tags),
                title_tokens=_content_tokens(frontmatter.title),
                record_id_tokens=_content_tokens(frontmatter.page_id),
                keyword_tokens=_content_tokens(
                    " ".join([frontmatter.kind, frontmatter.status, *frontmatter.tags])
                ),
                body_tokens=_content_tokens(parsed.body),
                snippet_source=parsed.body,
            )
        )
    return documents


def _iter_planning_documents(root: Path) -> list[_QueryDocument]:
    from splendor.commands.planning import _model_for  # imported lazily to avoid duplication

    layout = resolve_layout(root, load_config(root))
    documents: list[_QueryDocument] = []
    for kind in _PLANNING_KINDS:
        model = _model_for(kind)
        for path in iter_planning_paths(planning_directory(layout, kind)):
            record = parse_planning_markdown(path, model)
            payload = record.model_dump(mode="json")
            raw_content = path.read_text(encoding="utf-8")
            record_id = str(payload[_PLANNING_ID_FIELDS[kind]])
            status = payload.get("status")
            source_refs = list(payload.get("source_refs", []))
            keyword_values = [kind]
            if isinstance(status, str):
                keyword_values.append(status)
            search_values = [record.title]
            for key, value in payload.items():
                if key in {"schema_version", "kind", "title", _PLANNING_ID_FIELDS[kind]}:
                    continue
                search_values.extend(_flatten_search_values(value))
            search_values.append(raw_content)
            search_body = "\n".join(search_values)
            snippet_source = _body_after_frontmatter(raw_content)
            documents.append(
                _QueryDocument(
                    document_class="planning",
                    kind=kind,
                    record_id=record_id,
                    title=record.title,
                    path=path.relative_to(root).as_posix(),
                    status=status if isinstance(status, str) else None,
                    source_refs=source_refs,
                    generated_by_run_ids=[],
                    tags=[],
                    title_tokens=_content_tokens(record.title),
                    record_id_tokens=_content_tokens(record_id),
                    keyword_tokens=_content_tokens(" ".join(keyword_values)),
                    body_tokens=_content_tokens(search_body),
                    snippet_source=snippet_source,
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


def _score_document(document: _QueryDocument, query_tokens: list[str]) -> int:
    score = 0
    for token in query_tokens:
        score += 5 * document.title_tokens.count(token)
        score += 4 * document.record_id_tokens.count(token)
        score += 3 * document.keyword_tokens.count(token)
        score += document.body_tokens.count(token)
    return score


def _best_snippet(text: str, query_tokens: list[str]) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    paragraphs = [
        segment.strip() for segment in re.split(r"\n\s*\n", normalized) if segment.strip()
    ]
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    candidates = _unique_in_order([*paragraphs, *lines])
    best = max(
        candidates,
        key=lambda candidate: (_candidate_score(candidate, query_tokens), -len(candidate)),
    )
    if _candidate_score(best, query_tokens) == 0:
        best = paragraphs[0] if paragraphs else lines[0]
    collapsed = _WHITESPACE_PATTERN.sub(" ", best).strip()
    if len(collapsed) <= 240:
        return collapsed
    return collapsed[:237].rstrip() + "..."


def _candidate_score(candidate: str, query_tokens: list[str]) -> int:
    candidate_tokens = _content_tokens(candidate)
    return sum(candidate_tokens.count(token) for token in query_tokens)


def _body_after_frontmatter(raw: str) -> str:
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("---\n") and "\n---\n" in normalized.removeprefix("---\n"):
        return normalized.removeprefix("---\n").split("\n---\n", maxsplit=1)[1]
    return normalized


def _unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        unique.append(value)
        seen.add(value)
    return unique
