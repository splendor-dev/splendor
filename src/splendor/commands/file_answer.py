"""Implementation for `splendor file-answer`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter, QueryMatchSnapshot
from splendor.state.query_snapshot import last_query_path_for, load_query_snapshot
from splendor.utils.fs import ensure_directory
from splendor.utils.planning import slugify, validate_record_id
from splendor.utils.time import utc_now_iso
from splendor.utils.wiki import (
    WikiUpdatePayload,
    append_log_entry,
    apply_wiki_updates,
    render_frontmatter,
    upsert_index_section,
)


@dataclass(frozen=True)
class FileAnswerResult:
    page_id: str
    page_path: Path
    query: str
    linked_question_id: str | None


def default_answer_page_id(title: str) -> str:
    slug = slugify(title)
    if not slug:
        raise ValueError("Title must contain at least one ASCII letter or number")
    return validate_record_id(f"answer-{slug}")


def file_answer_from_last_query(
    root: Path,
    *,
    title: str,
    page_id: str | None,
    question_update,
) -> FileAnswerResult:
    layout = resolve_layout(root, load_config(root))
    snapshot = load_query_snapshot(last_query_path_for(layout))
    answer_page_id = validate_record_id(page_id) if page_id else default_answer_page_id(title)
    page_path = layout.wiki_dir / "topics" / f"{answer_page_id}.md"
    if page_path.exists():
        raise ValueError(f"Filed answer page already exists: {page_path.relative_to(root)}")

    page_ref = page_path.relative_to(root).as_posix()
    linked_question_id: str | None = None
    extra_writes: list[tuple[Path, str]] = []
    if question_update is not None:
        extra_writes.append((question_update.path, question_update.content))
        linked_question_id = question_update.record_id

    page_content = _render_answer_page(
        title=title,
        page_id=answer_page_id,
        page_ref=page_ref,
        query=snapshot.query,
        summary=snapshot.summary,
        matches=snapshot.matches,
    )
    index_content = upsert_index_section(
        layout.index_file.read_text(encoding="utf-8"),
        section_header="## Filed Answers",
        bullet=f"- [{title}](topics/{page_path.name}) (`{answer_page_id}`)",
    )
    question_fragment = f" for question `{linked_question_id}`" if linked_question_id else ""
    log_content = append_log_entry(
        layout.log_file.read_text(encoding="utf-8"),
        f"- Filed answer `{answer_page_id}` from query `{snapshot.query}`{question_fragment}.",
    )
    ensure_directory(page_path.parent)
    apply_wiki_updates(
        layout,
        WikiUpdatePayload(
            page_path=page_path,
            page_content=page_content,
            index_content=index_content,
            log_content=log_content,
            extra_writes=extra_writes,
        ),
    )
    return FileAnswerResult(
        page_id=answer_page_id,
        page_path=page_path,
        query=snapshot.query,
        linked_question_id=linked_question_id,
    )


def _render_answer_page(
    *,
    title: str,
    page_id: str,
    page_ref: str,
    query: str,
    summary: str,
    matches: list[QueryMatchSnapshot],
) -> str:
    frontmatter = KnowledgePageFrontmatter(
        kind="topic",
        title=title,
        page_id=page_id,
        status="active",
        source_refs=_dedupe_refs(matches),
        generated_by_run_ids=[],
        confidence=1.0,
        related_pages=[],
        tags=["filed-answer"],
        last_reviewed_at=utc_now_iso(),
    )
    return (
        f"---\n{render_frontmatter(frontmatter)}\n---\n\n"
        f"# {title}\n\n"
        "## Query\n\n"
        f"{query}\n\n"
        "## Summary\n\n"
        f"{summary}\n\n"
        "## Ranked Matches\n\n"
        f"{_render_ranked_matches(matches)}\n\n"
        "## Provenance\n\n"
        f"{_render_provenance(matches, page_ref=page_ref)}\n"
    )


def _dedupe_refs(matches: list[QueryMatchSnapshot]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in matches:
        for ref in match.source_refs:
            if ref not in seen:
                refs.append(ref)
                seen.add(ref)
    return refs


def _render_ranked_matches(matches: list[QueryMatchSnapshot]) -> str:
    if not matches:
        return "- No matches were present in the saved query snapshot."

    lines: list[str] = []
    for match in matches:
        lines.append(f"{match.rank}. **{match.title}** (`{match.kind}`) at `{match.path}`")
        lines.append(f"   Snippet: {match.snippet or '-'}")
        lines.append(
            f"   Source refs: {', '.join(match.source_refs) if match.source_refs else '-'}"
        )
        lines.append(
            "   Run IDs: "
            f"{', '.join(match.generated_by_run_ids) if match.generated_by_run_ids else '-'}"
        )
    return "\n".join(lines)


def _render_provenance(matches: list[QueryMatchSnapshot], *, page_ref: str) -> str:
    lines = [f"- Filed from saved query snapshot into `{page_ref}`."]
    for match in matches:
        lines.append(
            f"- Match {match.rank}: `{match.path}` "
            f"({match.document_class}/{match.kind}, id `{match.record_id}`)."
        )
    return "\n".join(lines)
