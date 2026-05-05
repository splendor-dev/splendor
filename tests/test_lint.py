import json
import subprocess
from pathlib import Path

import pytest
import yaml

from splendor.commands.add_source import add_source
from splendor.commands.init import initialize_workspace
from splendor.commands.lint import run_lint_checks
from splendor.commands.planning import create_task
from splendor.commands.source import update_source_path
from splendor.config import AuthorityDocumentConfig, load_config, write_config
from splendor.layout import resolve_layout
from splendor.schemas import (
    ContradictionAnnotation,
    ContradictionEvidence,
    KnowledgePageFrontmatter,
    ProvenanceLink,
    QuestionRecord,
    TaskRecord,
)
from splendor.state.source_registry import load_source_record, write_source_record
from splendor.utils.wiki import parse_wiki_markdown


def _run_lint(root: Path):
    layout = resolve_layout(root, load_config(root))
    return run_lint_checks(root, layout)


def _planning_state_text(*, current: str = "M7-P2.1", lifecycle: str | None = None) -> str:
    lifecycle_value = lifecycle or "branch=in-progress; main=merged"
    return (
        "- Previous completed PR sub-slice: `M7-P1.1`\n"
        "- Current planned slice: `M7-P2`\n"
        f"- Current PR sub-slice: `{current}`\n"
        f"- Current PR lifecycle: `{lifecycle_value}`\n"
        "- Next planned slice: `M8-P1`\n"
        "- Next planned PR sub-slice: `M8-P1.1`\n"
    )


def _write_planning_state_files(
    tmp_path: Path,
    *,
    current: str = "M7-P2.1",
    lifecycle: str | None = None,
) -> None:
    (tmp_path / ".agent-plan.md").write_text(
        "# Agent Plan\n\n## Current System State\n\n"
        + _planning_state_text(current=current, lifecycle=lifecycle),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "## What Comes Next\n\n" + _planning_state_text(current=current, lifecycle=lifecycle),
        encoding="utf-8",
    )
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "splendor_mvp_to_v1_roadmap.md").write_text(
        _planning_state_text(current=current, lifecycle=lifecycle),
        encoding="utf-8",
    )


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


def test_run_lint_checks_skips_planning_state_guard_when_files_are_absent(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)

    result = _run_lint(tmp_path)

    assert all(issue.check_name != "planning-state" for issue in result.issues)


def test_run_lint_checks_reports_planning_state_drift(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _write_planning_state_files(tmp_path)
    (tmp_path / "README.md").write_text(
        "## What Comes Next\n\n"
        + _planning_state_text().replace(
            "Next planned slice: `M8-P1`", "Next planned slice: `M9-P1`"
        ),
        encoding="utf-8",
    )

    result = _run_lint(tmp_path)

    planning_issues = [issue for issue in result.issues if issue.check_name == "planning-state"]
    assert len(planning_issues) == 1
    assert planning_issues[0].code == "planning-state-drift"
    assert planning_issues[0].path == "README.md"


def test_run_lint_checks_reports_missing_planning_state_line(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _write_planning_state_files(tmp_path)
    (tmp_path / "docs" / "splendor_mvp_to_v1_roadmap.md").write_text(
        _planning_state_text().replace(
            "- Current PR lifecycle: `branch=in-progress; main=merged`\n", ""
        ),
        encoding="utf-8",
    )

    result = _run_lint(tmp_path)

    planning_issues = [issue for issue in result.issues if issue.check_name == "planning-state"]
    assert len(planning_issues) == 1
    assert planning_issues[0].code == "missing-planning-state"
    assert planning_issues[0].path == "docs/splendor_mvp_to_v1_roadmap.md"


def test_run_lint_checks_reports_invalid_planning_lifecycle(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _write_planning_state_files(tmp_path, lifecycle="in-progress")

    result = _run_lint(tmp_path)

    planning_issues = [issue for issue in result.issues if issue.check_name == "planning-state"]
    assert len(planning_issues) == 1
    assert planning_issues[0].code == "invalid-planning-lifecycle"
    assert planning_issues[0].record_id == "Current PR lifecycle"


def test_run_lint_checks_reports_stale_planning_state_on_main(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    _write_planning_state_files(tmp_path, current="M7-P1.1")
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "M7-P2.1: repo refresh"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    result = _run_lint(tmp_path)

    planning_issues = [issue for issue in result.issues if issue.check_name == "planning-state"]
    assert len(planning_issues) == 1
    assert planning_issues[0].code == "stale-planning-state"
    assert planning_issues[0].record_id == "Current PR sub-slice"


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


def test_run_lint_checks_reports_missing_authority_document(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    config = load_config(tmp_path)
    config.briefing.authority_documents = [
        AuthorityDocumentConfig(path="missing.md", role="current-authority")
    ]
    write_config(tmp_path, config)

    result = _run_lint(tmp_path)

    issues = [issue for issue in result.issues if issue.check_name == "briefing-authority"]
    assert len(issues) == 1
    assert issues[0].code == "missing-authority-document"
    assert issues[0].path == "missing.md"
    assert issues[0].record_id == "current-authority"


def test_run_lint_checks_reports_missing_source_derived_artifact(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source_record = load_source_record(added.manifest_path).model_copy(
        update={"derived_artifacts": ["derived/parsed/missing.txt"]}
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_lint(tmp_path)

    assert [issue.code for issue in result.issues] == ["missing-source-derived-artifact"]
    assert result.issues[0].path == added.manifest_path.relative_to(tmp_path).as_posix()


def test_run_lint_checks_accepts_ocr_derived_artifact_links(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "diagram.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    added = add_source(tmp_path, source)
    artifact = tmp_path / "derived" / "ocr" / f"{added.source_id}.txt"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("Extracted OCR text\n", encoding="utf-8")
    source_record = load_source_record(added.manifest_path).model_copy(
        update={"derived_artifacts": [artifact.relative_to(tmp_path).as_posix()]}
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_lint(tmp_path)

    assert result.issues == []


def test_run_lint_checks_uses_live_source_ref_after_path_update(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    docs = tmp_path / "docs"
    moved = tmp_path / "moved"
    docs.mkdir()
    moved.mkdir()
    old_source = docs / "brief.md"
    new_source = moved / "brief.md"
    old_source.write_text("# Brief\n\nSame bytes.\n", encoding="utf-8")
    added = add_source(tmp_path, old_source)
    manifest = load_source_record(added.manifest_path).model_copy(
        update={"provenance_links": [ProvenanceLink(path_ref="docs/brief.md", role="input")]}
    )
    write_source_record(added.manifest_path, manifest)
    old_source.rename(new_source)

    update_source_path(tmp_path, "docs/brief.md", Path("moved/brief.md"))
    result = _run_lint(tmp_path)

    source_path_issues = {
        issue.code
        for issue in result.issues
        if issue.code in {"missing-provenance-path", "missing-source-live-path"}
    }
    assert source_path_issues == set()


def test_run_lint_checks_reports_missing_active_source_ref(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nhello world\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source.unlink()

    result = _run_lint(tmp_path)

    assert [issue.code for issue in result.issues] == ["missing-source-live-path"]
    assert result.issues[0].message == "Workspace source live path does not exist: brief.md"
    assert result.issues[0].path == added.manifest_path.relative_to(tmp_path).as_posix()


def test_run_lint_checks_validates_source_supersession_refs(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    refreshed = add_source(tmp_path, source)
    original = load_source_record(added.manifest_path).model_copy(
        update={"superseded_by": refreshed.source_id}
    )
    updated = load_source_record(refreshed.manifest_path).model_copy(
        update={"supersedes": [added.source_id]}
    )
    write_source_record(added.manifest_path, original)
    write_source_record(refreshed.manifest_path, updated)

    result = _run_lint(tmp_path)

    assert result.issues == []


def test_run_lint_checks_reports_broken_source_supersession_refs(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source_record = load_source_record(added.manifest_path).model_copy(
        update={"supersedes": ["src-missing"], "superseded_by": "src-also-missing"}
    )
    write_source_record(added.manifest_path, source_record)

    result = _run_lint(tmp_path)

    assert {issue.code for issue in result.issues} == {
        "missing-source-superseded-by-ref",
        "missing-source-supersedes-ref",
    }


def test_run_lint_checks_reports_one_way_source_supersession_refs(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    added = add_source(tmp_path, source)
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    refreshed = add_source(tmp_path, source)
    original = load_source_record(added.manifest_path).model_copy(
        update={"superseded_by": refreshed.source_id}
    )
    write_source_record(added.manifest_path, original)

    result = _run_lint(tmp_path)

    assert any(issue.code == "invalid-source-supersession-link" for issue in result.issues)


def test_run_lint_checks_reports_multiple_active_source_versions(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source = tmp_path / "brief.md"
    source.write_text("# Brief\n\nOriginal.\n", encoding="utf-8")
    add_source(tmp_path, source)
    source.write_text("# Brief\n\nUpdated.\n", encoding="utf-8")
    add_source(tmp_path, source)

    result = _run_lint(tmp_path)

    assert any(issue.code == "multiple-active-source-versions" for issue in result.issues)


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


def test_run_lint_checks_reports_broken_contradiction_links_and_missing_task_fields(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    page_path = tmp_path / "wiki" / "sources" / "src-123.md"
    _write_wiki_page(
        page_path,
        title="Source summary",
        page_id="src-123",
        source_refs=[],
    )
    _write_wiki_page(
        tmp_path / "wiki" / "sources" / "src-456.md",
        title="Other source summary",
        page_id="src-456",
        source_refs=[],
    )
    page = parse_wiki_markdown(page_path)
    broken_page = page.frontmatter.model_copy(
        update={
            "kind": "source-summary",
            "review_state": "contested",
            "contradictions": [
                ContradictionAnnotation(
                    contradiction_id="contradiction-src-123-src-456-1234567890",
                    summary="The pages disagree about storage mode.",
                    detected_at="2026-04-22T10:05:00+00:00",
                    related_page_ids=["src-123", "src-456"],
                    related_source_ids=["src-123", "src-456"],
                    review_task_id="task-review-src-123-src-456-1234567890",
                    evidence=[
                        ContradictionEvidence(
                            page_id="src-456",
                            source_id="src-456",
                            run_id="run-missing",
                            path_ref="wiki/sources/src-456.md",
                            excerpt="Storage mode is copy.",
                        )
                    ],
                )
            ],
        }
    )
    page_path.write_text(
        "---\n"
        f"{yaml.safe_dump(broken_page.model_dump(mode='json'), sort_keys=False).strip()}\n"
        "---\n\n"
        "## Source\n\n- Source ID: `src-123`\n\n"
        "## Summary\n\nBody\n\n"
        "## Key Facts\n\n- Fact\n\n"
        "## Contradictions\n\n- Broken\n\n"
        "## Provenance\n\n- Run ID: `run-123`\n",
        encoding="utf-8",
    )
    task = TaskRecord(
        task_id="task-review-src-123-src-456-1234567890",
        title="Review contradiction",
        status="todo",
        priority="high",
        created_at="2026-04-22T10:05:00+00:00",
        updated_at="2026-04-22T10:05:00+00:00",
        source_refs=[],
        page_refs=[],
        run_refs=[],
    )
    _write_planning_record(
        tmp_path / "planning" / "tasks" / "task-review-src-123-src-456-1234567890.md",
        task,
    )

    result = _run_lint(tmp_path)

    assert {issue.code for issue in result.issues} >= {
        "contradiction-task-missing-page-refs",
        "contradiction-task-missing-source-refs",
        "missing-contradiction-source-ref",
        "missing-contradiction-run-ref",
        "missing-reciprocal-contradiction",
    }


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
    manifest_issue = next(
        issue
        for issue in result.issues
        if issue.code == "source-summary-provenance-mismatch"
        and issue.message == "Source manifest provenance is missing the generated page link."
    )
    assert manifest_issue.path == added.manifest_path.relative_to(tmp_path).as_posix()


def test_run_lint_checks_requires_expected_provenance_roles_for_source_summary(
    tmp_path: Path,
) -> None:
    initialize_workspace(tmp_path)
    source_path = tmp_path / "brief.md"
    source_path.write_text("hello\n", encoding="utf-8")
    added = add_source(tmp_path, source_path)
    source_summary_path = tmp_path / "wiki" / "sources" / f"{added.source_id}.md"
    source_summary = KnowledgePageFrontmatter(
        kind="source-summary",
        title="Source summary",
        page_id=added.source_id,
        status="active",
        source_refs=[added.source_id],
        confidence=1.0,
        provenance_links=[
            ProvenanceLink(
                source_id=added.source_id,
                path_ref=added.manifest_path.relative_to(tmp_path).as_posix(),
                role="input",
            )
        ],
    )
    frontmatter_text = yaml.safe_dump(
        source_summary.model_dump(mode="json"), sort_keys=False
    ).strip()
    source_summary_path.parent.mkdir(parents=True, exist_ok=True)
    source_summary_path.write_text(f"---\n{frontmatter_text}\n---\n\nSummary\n", encoding="utf-8")

    manifest = load_source_record(added.manifest_path).model_copy(
        update={
            "linked_pages": [source_summary_path.relative_to(tmp_path).as_posix()],
            "provenance_links": [
                ProvenanceLink(
                    page_id=added.source_id,
                    path_ref=source_summary_path.relative_to(tmp_path).as_posix(),
                    role="output",
                )
            ],
        }
    )
    write_source_record(added.manifest_path, manifest)

    result = _run_lint(tmp_path)

    assert [issue.code for issue in result.issues] == [
        "source-summary-provenance-mismatch",
        "source-summary-provenance-mismatch",
    ]


def test_run_lint_checks_rejects_stale_workspace_source_identity(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    source_path = tmp_path / "docs" / "brief.md"
    source_path.parent.mkdir()
    source_path.write_text("hello\n", encoding="utf-8")
    added = add_source(tmp_path, source_path)
    manifest = load_source_record(added.manifest_path)
    write_source_record(
        added.manifest_path,
        manifest.model_copy(
            update={
                "logical_id": "source:docs/other.md",
                "aliases": ["docs/brief.md", "docs/other.md"],
            }
        ),
    )

    result = _run_lint(tmp_path)

    source_identity_issues = {
        issue.code for issue in result.issues if issue.check_name == "source-identity"
    }
    assert source_identity_issues == {
        "invalid-source-logical-id",
        "invalid-source-alias",
    }


def test_run_lint_checks_rejects_source_identity_conflicts(tmp_path: Path) -> None:
    initialize_workspace(tmp_path)
    first_path = tmp_path / "docs" / "first.md"
    second_path = tmp_path / "docs" / "second.md"
    first_path.parent.mkdir()
    first_path.write_text("first\n", encoding="utf-8")
    second_path.write_text("second\n", encoding="utf-8")
    first = add_source(tmp_path, first_path)
    second = add_source(tmp_path, second_path)
    second_manifest = load_source_record(second.manifest_path)
    write_source_record(
        second.manifest_path,
        second_manifest.model_copy(update={"logical_id": "source:docs/first.md"}),
    )

    result = _run_lint(tmp_path)

    conflict_records = {
        issue.record_id for issue in result.issues if issue.code == "conflicting-source-identity"
    }
    assert conflict_records == {first.source_id, second.source_id}


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
