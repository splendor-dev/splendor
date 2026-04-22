"""Helpers for ingest-time contradiction detection and review-task linkage."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

from splendor.commands.planning import _model_for
from splendor.config import SplendorConfig
from splendor.layout import ResolvedLayout
from splendor.schemas import (
    ContradictionAnnotation,
    ContradictionEvidence,
    KnowledgePageFrontmatter,
    ProvenanceLink,
    TaskRecord,
)
from splendor.utils.planning import parse_planning_document, planning_path, render_planning_document
from splendor.utils.time import utc_now_iso
from splendor.utils.wiki import parse_wiki_markdown

DEFAULT_OPENAI_CONTRADICTION_MODEL = "gpt-4.1-mini"
_SECTION_PATTERN = re.compile(r"^## (?P<name>[^\n]+)\n\n", re.MULTILINE)
_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class SourceSummarySnapshot:
    page_path: Path
    page_ref: str
    frontmatter: KnowledgePageFrontmatter
    source_section: str
    summary: str
    key_facts: list[str]
    extract: str | None
    provenance_lines: list[str]

    @property
    def source_id(self) -> str | None:
        return self.frontmatter.source_refs[0] if self.frontmatter.source_refs else None

    @property
    def run_id(self) -> str | None:
        if not self.frontmatter.generated_by_run_ids:
            return None
        return self.frontmatter.generated_by_run_ids[-1]


@dataclass(frozen=True)
class DetectedContradiction:
    summary: str
    current_excerpt: str
    candidate_excerpt: str


@dataclass(frozen=True)
class ReviewTaskUpdate:
    task_id: str
    task_path: Path
    content: str
    created: bool


@dataclass(frozen=True)
class ContradictionReviewResult:
    frontmatter: KnowledgePageFrontmatter
    task_updates: list[ReviewTaskUpdate]
    page_updates: list[tuple[Path, str]]
    contradiction_ids: list[str]
    task_ids: list[str]
    warnings: list[str]


class OpenAIContradictionAnalyzer:
    def __init__(self, *, model: str) -> None:
        self.model = model

    def detect(
        self, *, current: SourceSummarySnapshot, candidate: SourceSummarySnapshot
    ) -> list[DetectedContradiction]:
        response = self._request(current=current, candidate=candidate)
        contradictions: list[DetectedContradiction] = []
        for item in response.get("contradictions", []):
            if not isinstance(item, dict):
                continue
            summary = _normalized_summary(str(item.get("summary", "")))
            current_excerpt = _normalized_excerpt(str(item.get("current_excerpt", "")))
            candidate_excerpt = _normalized_excerpt(str(item.get("candidate_excerpt", "")))
            if not summary or not current_excerpt or not candidate_excerpt:
                continue
            contradictions.append(
                DetectedContradiction(
                    summary=summary,
                    current_excerpt=current_excerpt,
                    candidate_excerpt=candidate_excerpt,
                )
            )
        return _dedupe_detected_contradictions(contradictions)

    def _request(
        self, *, current: SourceSummarySnapshot, candidate: SourceSummarySnapshot
    ) -> dict[str, object]:
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Compare two source-summary pages and report only explicit contradictions. "
                        "Do not report omissions, topic differences, or differences in detail "
                        "level. "
                        'Return JSON with a single key "contradictions", whose value is an '
                        "array of "
                        'objects with keys "summary", "current_excerpt", and "candidate_excerpt".'
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "current": _snapshot_payload(current),
                            "candidate": _snapshot_payload(candidate),
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                },
            ],
        }
        req = request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                raw_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI contradiction review failed: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"OpenAI contradiction review failed: {exc.reason}") from exc

        content = raw_payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise RuntimeError("OpenAI contradiction review returned a non-string message payload.")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "OpenAI contradiction review returned invalid JSON content."
            ) from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("OpenAI contradiction review returned a non-object payload.")
        return parsed


def build_contradiction_analyzer(config: SplendorConfig) -> OpenAIContradictionAnalyzer | None:
    contradiction_config = config.reviews.contradictions
    if contradiction_config.provider != "openai":
        return None
    if os.environ.get("OPENAI_API_KEY") is None:
        return None
    model = (
        contradiction_config.model
        or os.environ.get("OPENAI_MODEL")
        or DEFAULT_OPENAI_CONTRADICTION_MODEL
    )
    return OpenAIContradictionAnalyzer(model=model)


def snapshot_from_rendered_page(
    *,
    root: Path,
    page_path: Path,
    frontmatter: KnowledgePageFrontmatter,
    page_content: str,
) -> SourceSummarySnapshot:
    body = page_content.split("\n---\n", maxsplit=1)[1]
    sections = _parse_source_summary_sections(body)
    return SourceSummarySnapshot(
        page_path=page_path,
        page_ref=page_path.relative_to(root).as_posix(),
        frontmatter=frontmatter,
        source_section=sections.get("Source", ""),
        summary=sections.get("Summary", "").strip(),
        key_facts=_parse_bullets(sections.get("Key Facts")),
        extract=_normalize_optional_text(sections.get("Extract")),
        provenance_lines=_parse_bullets(sections.get("Provenance")),
    )


def snapshot_from_existing_page(*, root: Path, page_path: Path) -> SourceSummarySnapshot:
    parsed = parse_wiki_markdown(page_path)
    sections = _parse_source_summary_sections(parsed.body)
    return SourceSummarySnapshot(
        page_path=page_path,
        page_ref=page_path.relative_to(root).as_posix(),
        frontmatter=parsed.frontmatter,
        source_section=sections.get("Source", ""),
        summary=sections.get("Summary", "").strip(),
        key_facts=_parse_bullets(sections.get("Key Facts")),
        extract=_normalize_optional_text(sections.get("Extract")),
        provenance_lines=_parse_bullets(sections.get("Provenance")),
    )


def review_source_summary_contradictions(
    *,
    root: Path,
    layout: ResolvedLayout,
    config: SplendorConfig,
    current_snapshot: SourceSummarySnapshot,
    run_id: str,
) -> ContradictionReviewResult:
    existing_frontmatter = _load_existing_frontmatter(current_snapshot.page_path)
    current_frontmatter = current_snapshot.frontmatter.model_copy(
        update={
            "contradictions": list(existing_frontmatter.contradictions)
            if existing_frontmatter is not None
            else []
        }
    )

    contradiction_config = config.reviews.contradictions
    if not contradiction_config.enabled:
        return ContradictionReviewResult(
            frontmatter=_normalize_review_state(current_frontmatter),
            task_updates=[],
            page_updates=[],
            contradiction_ids=[],
            task_ids=[],
            warnings=[],
        )

    analyzer = build_contradiction_analyzer(config)
    if analyzer is None:
        warning = (
            "Skipped contradiction review because OPENAI_API_KEY is not configured."
            if os.environ.get("OPENAI_API_KEY") is None
            else (
                "Skipped contradiction review because the configured contradiction provider is "
                "unsupported."
            )
        )
        return ContradictionReviewResult(
            frontmatter=_normalize_review_state(current_frontmatter),
            task_updates=[],
            page_updates=[],
            contradiction_ids=[],
            task_ids=[],
            warnings=[warning],
        )

    page_updates: list[tuple[Path, str]] = []
    task_updates: list[ReviewTaskUpdate] = []
    contradiction_ids: list[str] = []
    task_ids: list[str] = []
    for candidate in _load_candidate_snapshots(
        root=root,
        layout=layout,
        current_page=current_snapshot.page_path,
        max_candidates=contradiction_config.max_candidate_pages,
    ):
        for contradiction in analyzer.detect(current=current_snapshot, candidate=candidate):
            annotation = _build_annotation(
                current=current_snapshot,
                candidate=candidate,
                contradiction=contradiction,
                run_id=run_id,
            )
            current_frontmatter = _merge_annotation(current_frontmatter, annotation)
            candidate_frontmatter = _merge_annotation(candidate.frontmatter, annotation)
            task_update = _upsert_review_task(
                layout=layout,
                annotation=annotation,
                current=current_snapshot,
                candidate=candidate,
                priority=contradiction_config.review_task_priority,
                run_id=run_id,
            )
            task_updates.append(task_update)
            contradiction_ids.append(annotation.contradiction_id)
            task_ids.append(annotation.review_task_id)
            page_updates.append(
                (
                    candidate.page_path,
                    render_source_summary_page_content(
                        page_ref=candidate.page_ref,
                        frontmatter=candidate_frontmatter,
                        snapshot=candidate,
                    ),
                )
            )

    return ContradictionReviewResult(
        frontmatter=_normalize_review_state(current_frontmatter),
        task_updates=_dedupe_task_updates(task_updates),
        page_updates=_dedupe_page_updates(page_updates),
        contradiction_ids=sorted(set(contradiction_ids)),
        task_ids=sorted(set(task_ids)),
        warnings=[],
    )


def render_source_summary_page_content(
    *,
    page_ref: str,
    frontmatter: KnowledgePageFrontmatter,
    snapshot: SourceSummarySnapshot,
) -> str:
    from splendor.utils.wiki import render_source_summary_page

    return render_source_summary_page(
        frontmatter,
        source_section=snapshot.source_section,
        summary=snapshot.summary,
        key_facts=snapshot.key_facts,
        extract=snapshot.extract,
        contradictions=render_contradiction_lines(
            page_ref=page_ref,
            contradictions=frontmatter.contradictions,
        ),
        provenance=snapshot.provenance_lines
        or _render_provenance_lines(frontmatter.provenance_links),
    )


def render_contradiction_lines(
    *, page_ref: str, contradictions: list[ContradictionAnnotation]
) -> list[str]:
    lines: list[str] = []
    page_parent = posixpath.dirname(page_ref)
    for contradiction in contradictions:
        task_ref = posixpath.relpath(
            f"planning/tasks/{contradiction.review_task_id}.md",
            start=page_parent,
        )
        pages = ", ".join(f"`{page_id}`" for page_id in contradiction.related_page_ids)
        lines.append(
            f"{contradiction.summary} "
            f"(pages: {pages}; review task: [{contradiction.review_task_id}]({task_ref}))"
        )
    return lines


def _load_existing_frontmatter(path: Path) -> KnowledgePageFrontmatter | None:
    if not path.exists():
        return None
    try:
        return parse_wiki_markdown(path).frontmatter
    except Exception:
        return None


def _load_candidate_snapshots(
    *,
    root: Path,
    layout: ResolvedLayout,
    current_page: Path,
    max_candidates: int,
) -> list[SourceSummarySnapshot]:
    snapshots: list[SourceSummarySnapshot] = []
    for page_path in sorted(layout.wiki_sources_dir.glob("*.md")):
        if page_path == current_page:
            continue
        parsed = parse_wiki_markdown(page_path)
        if parsed.frontmatter.kind != "source-summary":
            continue
        snapshots.append(snapshot_from_existing_page(root=root, page_path=page_path))
        if len(snapshots) >= max_candidates:
            break
    return snapshots


def _build_annotation(
    *,
    current: SourceSummarySnapshot,
    candidate: SourceSummarySnapshot,
    contradiction: DetectedContradiction,
    run_id: str,
) -> ContradictionAnnotation:
    related_page_ids = sorted({current.frontmatter.page_id, candidate.frontmatter.page_id})
    related_source_ids = sorted(
        source_id for source_id in [current.source_id, candidate.source_id] if source_id is not None
    )
    return ContradictionAnnotation(
        contradiction_id=_contradiction_id(
            page_ids=related_page_ids,
            summary=contradiction.summary,
        ),
        summary=contradiction.summary,
        detected_at=utc_now_iso(),
        related_page_ids=related_page_ids,
        related_source_ids=related_source_ids,
        review_task_id=_review_task_id(
            page_ids=related_page_ids,
            summary=contradiction.summary,
        ),
        evidence=[
            ContradictionEvidence(
                page_id=current.frontmatter.page_id,
                source_id=current.source_id,
                run_id=run_id,
                path_ref=current.page_ref,
                excerpt=contradiction.current_excerpt,
            ),
            ContradictionEvidence(
                page_id=candidate.frontmatter.page_id,
                source_id=candidate.source_id,
                run_id=candidate.run_id,
                path_ref=candidate.page_ref,
                excerpt=contradiction.candidate_excerpt,
            ),
        ],
    )


def _merge_annotation(
    frontmatter: KnowledgePageFrontmatter,
    annotation: ContradictionAnnotation,
) -> KnowledgePageFrontmatter:
    contradictions = {item.contradiction_id: item for item in frontmatter.contradictions}
    contradictions[annotation.contradiction_id] = annotation
    merged = sorted(contradictions.values(), key=lambda item: item.contradiction_id)
    return _normalize_review_state(frontmatter.model_copy(update={"contradictions": merged}))


def _normalize_review_state(frontmatter: KnowledgePageFrontmatter) -> KnowledgePageFrontmatter:
    if frontmatter.contradictions:
        return frontmatter.model_copy(update={"review_state": "contested"})
    if frontmatter.review_state == "contested":
        return frontmatter.model_copy(update={"review_state": "machine-generated"})
    return frontmatter


def _upsert_review_task(
    *,
    layout: ResolvedLayout,
    annotation: ContradictionAnnotation,
    current: SourceSummarySnapshot,
    candidate: SourceSummarySnapshot,
    priority: str,
    run_id: str,
) -> ReviewTaskUpdate:
    task_path = planning_path(layout, "task", annotation.review_task_id)
    title = f"Review contradiction: {current.frontmatter.title} vs {candidate.frontmatter.title}"
    timestamp = utc_now_iso()
    if task_path.exists():
        parsed = parse_planning_document(task_path, _model_for("task"))
        assert isinstance(parsed.record, TaskRecord)
        record = parsed.record.model_copy(
            update={
                "title": title,
                "updated_at": timestamp,
                "source_refs": sorted(
                    {
                        *parsed.record.source_refs,
                        *annotation.related_source_ids,
                    }
                ),
                "page_refs": sorted(
                    {
                        *parsed.record.page_refs,
                        current.page_ref,
                        candidate.page_ref,
                    }
                ),
                "run_refs": sorted({*parsed.record.run_refs, f"state/runs/{run_id}.json"}),
            }
        )
        created = False
    else:
        record = TaskRecord(
            task_id=annotation.review_task_id,
            title=title,
            status="todo",
            priority=priority,
            created_at=timestamp,
            updated_at=timestamp,
            source_refs=list(annotation.related_source_ids),
            page_refs=sorted({current.page_ref, candidate.page_ref}),
            run_refs=[f"state/runs/{run_id}.json"],
        )
        created = True

    body = _render_review_task_body(annotation=annotation, current=current, candidate=candidate)
    return ReviewTaskUpdate(
        task_id=annotation.review_task_id,
        task_path=task_path,
        content=render_planning_document(record, body=body),
        created=created,
    )


def _render_review_task_body(
    *,
    annotation: ContradictionAnnotation,
    current: SourceSummarySnapshot,
    candidate: SourceSummarySnapshot,
) -> str:
    current_link = posixpath.relpath(current.page_ref, start="planning/tasks")
    candidate_link = posixpath.relpath(candidate.page_ref, start="planning/tasks")
    evidence_lines = "\n".join(
        f"- `{item.page_id}`: {item.excerpt}" for item in annotation.evidence
    )
    return (
        "\n"
        "## Contradiction\n\n"
        f"{annotation.summary}\n\n"
        "## Evidence\n\n"
        f"{evidence_lines}\n\n"
        "## Linked Pages\n\n"
        f"- [{current.frontmatter.title}]({current_link}) (`{current.frontmatter.page_id}`)\n"
        f"- [{candidate.frontmatter.title}]({candidate_link}) "
        f"(`{candidate.frontmatter.page_id}`)\n\n"
        "## Notes\n\n"
    )


def _render_provenance_lines(links: list[ProvenanceLink]) -> list[str]:
    lines: list[str] = []
    for link in links:
        parts: list[str] = []
        if link.source_id is not None:
            parts.append(f"source=`{link.source_id}`")
        if link.page_id is not None:
            parts.append(f"page=`{link.page_id}`")
        if link.run_id is not None:
            parts.append(f"run=`{link.run_id}`")
        if link.path_ref is not None:
            parts.append(f"path=`{link.path_ref}`")
        if link.role is not None:
            parts.append(f"role=`{link.role}`")
        if parts:
            lines.append("; ".join(parts))
    return lines


def _snapshot_payload(snapshot: SourceSummarySnapshot) -> dict[str, object]:
    return {
        "page_id": snapshot.frontmatter.page_id,
        "title": snapshot.frontmatter.title,
        "summary": snapshot.summary,
        "key_facts": snapshot.key_facts,
        "source_refs": snapshot.frontmatter.source_refs,
        "generated_by_run_ids": snapshot.frontmatter.generated_by_run_ids,
        "provenance": [
            link.model_dump(mode="json") for link in snapshot.frontmatter.provenance_links
        ],
    }


def _parse_source_summary_sections(body: str) -> dict[str, str]:
    matches = list(_SECTION_PATTERN.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group("name")] = body[start:end].strip()
    return sections


def _parse_bullets(body: str | None) -> list[str]:
    if not body:
        return []
    bullets: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped.removeprefix("- ").strip())
    return bullets


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalized_summary(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value.strip())


def _normalized_excerpt(value: str) -> str:
    return value.strip()


def _dedupe_detected_contradictions(
    contradictions: list[DetectedContradiction],
) -> list[DetectedContradiction]:
    deduped: dict[str, DetectedContradiction] = {}
    for contradiction in contradictions:
        deduped[contradiction.summary.lower()] = contradiction
    return sorted(deduped.values(), key=lambda item: item.summary.lower())


def _contradiction_id(*, page_ids: list[str], summary: str) -> str:
    digest = hashlib.sha256(_normalized_summary(summary).lower().encode("utf-8")).hexdigest()[:10]
    return f"contradiction-{'-'.join(page_ids)}-{digest}"


def _review_task_id(*, page_ids: list[str], summary: str) -> str:
    digest = hashlib.sha256(_normalized_summary(summary).lower().encode("utf-8")).hexdigest()[:10]
    pair = "-".join(_short_page_fragment(page_id) for page_id in page_ids)
    return f"task-review-{pair}-{digest}"


def _short_page_fragment(page_id: str) -> str:
    if page_id.startswith("src-"):
        return page_id[:14]
    return page_id[:12]


def _dedupe_page_updates(page_updates: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    deduped: dict[Path, str] = {}
    for path, content in page_updates:
        deduped[path] = content
    return sorted(deduped.items(), key=lambda item: item[0].as_posix())


def _dedupe_task_updates(task_updates: list[ReviewTaskUpdate]) -> list[ReviewTaskUpdate]:
    deduped: dict[str, ReviewTaskUpdate] = {}
    for update in task_updates:
        deduped[update.task_id] = update
    return sorted(deduped.values(), key=lambda item: item.task_id)
