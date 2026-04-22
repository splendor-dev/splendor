import json
from pathlib import Path

import pytest
import yaml

from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.commands.lint import run_lint_checks
from splendor.commands.planning import create_task
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import KnowledgePageFrontmatter, ProvenanceLink, QuestionRecord, TaskRecord
from splendor.state.source_registry import load_source_record, write_source_record


def _run_lint(root: Path):
    layout = resolve_layout(root, load_config(root))
    return run_lint_checks(root, layout)


def _write_wiki_page(
    path: Path,
    *,
    title: str,
    page_id: str,
    body: str = "",
    source_refs: list[str] | None = None,
    related_pages: list[str] | None = None,
) -> None:
    frontmatter = KnowledgePageFrontmatter(
        kind="concept",
        title=title,
        page_id=page_id,
        status="active",
        confidence=0.8,
        source_refs=source_refs or [],
        related_pages=related_pages or [],
    )
    frontmatter_text = yaml.safe_dump(frontmatter.model_dump(mode="json"), sort_keys=False).strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter_text}\n---\n\n{body}", encoding="utf-8")


def _write_planning_record(path: Path, record: TaskRecord | QuestionRecord, body: str = "") -> None:
    frontmatter_text = yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False).strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter_text}\n---\n\n{body}", encoding="utf-8")


def test_run_lint_checks_returns_no_issues_for_initialized_workspace(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    result = _run_lint(tmp_path)

    assert result.issues == []


def test_run_lint_checks_reports_invalid_wiki_frontmatter_without_fatal_error(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    bad_page = tmp_path / "wiki" / "concepts" / "bad.md"
    bad_page.write_text("---\nkind: concept\nbogus: true\n---\n", encoding="utf-8")

    result = _run_lint(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-wiki-frontmatter"]
    assert result.issues[0].path == "wiki/concepts/bad.md"
    assert "\n" not in result.issues[0].message
    assert str(tmp_path) not in result.issues[0].message


def test_run_lint_checks_reports_invalid_planning_frontmatter_without_fatal_error(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    bad_task = tmp_path / "planning" / "tasks" / "task-bad.md"
    bad_task.write_text("---\nkind: task\nbogus: true\n---\n", encoding="utf-8")

    result = _run_lint(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-planning-frontmatter"]
    assert result.issues[0].path == "planning/tasks/task-bad.md"
    assert "\n" not in result.issues[0].message
    assert str(tmp_path) not in result.issues[0].message


def test_run_lint_checks_reports_invalid_source_manifest(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    manifest_path = tmp_path / "state" / "manifests" / "sources" / "bad.json"
    manifest_path.write_text("{bad json}\n", encoding="utf-8")

    result = _run_lint(tmp_path)

    assert [issue.code for issue in result.issues] == ["invalid-source-manifest"]
    assert "\n" not in result.issues[0].message
    assert str(tmp_path) not in result.issues[0].message


def test_run_lint_checks_reports_missing_wiki_refs_and_related_pages(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _write_wiki_page(
        tmp_path / "wiki" / "concepts" / "refs.md",
        title="Missing refs",
        page_id="concept-missing-refs",
        source_refs=["src-missing"],
        related_pages=["concept-nowhere"],
    )

    result = _run_lint(tmp_path)

    assert {issue.code for issue in result.issues} == {"missing-page-ref", "missing-source-ref"}


def test_run_lint_checks_reports_missing_planning_refs_and_answer_page(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    create_task(
        tmp_path,
        "Broken task",
        record_id="task-broken",
        status="todo",
        priority="medium",
        owner=None,
        milestone_refs=["milestone-missing"],
        decision_refs=["decision-missing"],
        question_refs=["question-missing"],
        depends_on=["task-missing"],
        source_refs=["src-missing"],
    )
    question = QuestionRecord(
        question_id="question-broken",
        title="Broken question",
        status="answered",
        created_at="2026-04-19T00:00:00+00:00",
        updated_at="2026-04-19T00:00:00+00:00",
        answer_page_ref="wiki/topics/answer-missing.md",
        source_refs=["src-missing"],
        related_tasks=["task-missing"],
        related_decisions=["decision-missing"],
    )
    _write_planning_record(
        tmp_path / "planning" / "questions" / "question-broken.md",
        question,
        body="Broken refs.\n",
    )

    result = _run_lint(tmp_path)

    assert {
        issue.code
        for issue in result.issues
        if issue.record_id in {"task-broken", "question-broken"}
    } == {
        "missing-answer-page",
        "missing-decision-ref",
        "missing-milestone-ref",
        "missing-question-ref",
        "missing-source-ref",
        "missing-task-ref",
    }


def test_run_lint_checks_reports_missing_linked_pages_and_source_ref_mismatch(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source_path = tmp_path / "brief.md"
    source_path.write_text("hello\n", encoding="utf-8")
    add_source(tmp_path, source_path)
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_record = load_source_record(manifest_path)
    linked_page = tmp_path / "wiki" / "sources" / f"{source_record.source_id}.md"
    _write_wiki_page(
        linked_page,
        title="Source summary",
        page_id=f"concept-{source_record.source_id}",
        source_refs=[],
    )
    updated_record = source_record.model_copy(
        update={
            "linked_pages": [
                f"./{linked_page.relative_to(tmp_path).as_posix()}",
                "wiki/sources/missing.md",
            ]
        }
    )
    write_source_record(manifest_path, updated_record)

    result = _run_lint(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "linked-page-source-mismatch",
        "missing-linked-page",
    }
    mismatch_issue = next(
        issue for issue in result.issues if issue.code == "linked-page-source-mismatch"
    )
    assert mismatch_issue.path == linked_page.relative_to(tmp_path).as_posix()


def test_run_lint_checks_reports_invalid_linked_page_refs_separately(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source_path = tmp_path / "brief.md"
    source_path.write_text("hello\n", encoding="utf-8")
    add_source(tmp_path, source_path)
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_record = load_source_record(manifest_path)
    updated_record = source_record.model_copy(
        update={"linked_pages": ["../outside.md", "/tmp/absolute.md"]}
    )
    write_source_record(manifest_path, updated_record)

    result = _run_lint(tmp_path)

    assert {issue.code for issue in result.issues} == {"invalid-linked-page-ref"}
    assert len(result.issues) == 2
    assert all(
        issue.path == manifest_path.relative_to(tmp_path).as_posix() for issue in result.issues
    )


def test_run_lint_checks_reports_broken_provenance_refs_and_paths(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source_path = tmp_path / "brief.md"
    source_path.write_text("hello\n", encoding="utf-8")
    added = add_source(tmp_path, source_path)
    manifest = load_source_record(added.manifest_path).model_copy(
        update={
            "provenance_links": [
                ProvenanceLink(page_id="missing-page", role="generated-page"),
                ProvenanceLink(path_ref="../outside.md", role="input"),
            ]
        }
    )
    write_source_record(added.manifest_path, manifest)
    source_summary_path = tmp_path / "wiki" / "sources" / f"{manifest.source_id}.md"
    _write_wiki_page(
        source_summary_path,
        title="Source summary",
        page_id=manifest.source_id,
        source_refs=[],
    )
    source_summary_path.write_text(
        source_summary_path.read_text(encoding="utf-8").replace(
            "kind: concept", "kind: source-summary"
        ),
        encoding="utf-8",
    )

    result = _run_lint(tmp_path)

    assert {
        issue.code
        for issue in result.issues
        if issue.code.startswith("missing-provenance")
        or issue.code.startswith("invalid-provenance")
        or issue.code.startswith("source-summary")
    } == {
        "missing-provenance-page-ref",
        "invalid-provenance-path-ref",
        "source-summary-source-ref-mismatch",
        "source-summary-linked-page-mismatch",
        "source-summary-provenance-mismatch",
    }


def test_run_lint_checks_ignores_markdown_target_resolution_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize_workspace(tmp_path)
    _write_wiki_page(
        tmp_path / "wiki" / "concepts" / "links.md",
        title="Links",
        page_id="concept-links",
        body="[loop](loop.md)\n",
    )

    original_resolve = Path.resolve

    def bad_resolve(self: Path, *args, **kwargs):
        if self.name == "loop.md":
            raise RuntimeError("symlink loop")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", bad_resolve)

    result = _run_lint(tmp_path)

    assert result.issues == []


def test_run_lint_checks_reports_duplicate_ids_once_per_duplicate_value(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _write_wiki_page(
        tmp_path / "wiki" / "concepts" / "one.md",
        title="One",
        page_id="concept-dup",
    )
    _write_wiki_page(
        tmp_path / "wiki" / "topics" / "two.md",
        title="Two",
        page_id="concept-dup",
    )
    task_record = TaskRecord(
        task_id="task-dup",
        title="Duplicate task",
        status="todo",
        priority="medium",
        milestone_refs=[],
        decision_refs=[],
        question_refs=[],
        owner=None,
        created_at="2026-04-19T00:00:00+00:00",
        updated_at="2026-04-19T00:00:00+00:00",
        depends_on=[],
        source_refs=[],
    )
    _write_planning_record(tmp_path / "planning" / "tasks" / "task-dup-a.md", task_record)
    _write_planning_record(tmp_path / "planning" / "tasks" / "task-dup-b.md", task_record)
    source_path = tmp_path / "source.md"
    source_path.write_text("source\n", encoding="utf-8")
    add_source(tmp_path, source_path)
    manifest_path = next((tmp_path / "state" / "manifests" / "sources").glob("*.json"))
    source_record = load_source_record(manifest_path)
    duplicate_manifest = tmp_path / "state" / "manifests" / "sources" / "duplicate.json"
    duplicate_manifest.write_text(
        json.dumps(source_record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = _run_lint(tmp_path)

    assert [issue.code for issue in result.issues].count("duplicate-page-id") == 1
    assert [issue.code for issue in result.issues].count("duplicate-record-id") == 1
    assert [issue.code for issue in result.issues].count("duplicate-source-id") == 1


def test_run_lint_checks_reports_broken_markdown_links_and_ignores_external_links(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    _write_wiki_page(
        tmp_path / "wiki" / "concepts" / "links.md",
        title="Links",
        page_id="concept-links",
        body=(
            "[broken](missing.md)\n"
            "[external](https://example.com/x.md)\n"
            "[fragment](#section)\n"
            "[mail](mailto:test@example.com)\n"
        ),
    )

    result = _run_lint(tmp_path)

    assert [issue.code for issue in result.issues] == ["broken-markdown-link"]
