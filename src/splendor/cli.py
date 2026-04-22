"""CLI entrypoint for Splendor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from splendor import __version__
from splendor.commands.add_source import add_source
from splendor.commands.file_answer import (
    default_answer_page_id,
    file_answer_from_last_query,
)
from splendor.commands.health import run_health_checks
from splendor.commands.ingest import drain_pending_ingest_jobs, ingest_source
from splendor.commands.init import initialize_workspace
from splendor.commands.lint import run_lint_checks
from splendor.commands.maintenance import execute_maintenance_command, render_report_json
from splendor.commands.materialize_source import materialize_source
from splendor.commands.planning import (
    create_decision,
    create_milestone,
    create_question,
    create_task,
    list_milestones,
    list_tasks,
    update_question_answer,
)
from splendor.commands.query import run_query
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import (
    DecisionRecord,
    MilestoneRecord,
    QueryMatchSnapshot,
    QuerySnapshot,
    QuestionRecord,
    TaskRecord,
)
from splendor.schemas.types import STORAGE_MODES
from splendor.state.query_snapshot import last_query_path_for, write_query_snapshot
from splendor.utils.provenance import summarize_provenance_links
from splendor.utils.time import utc_now_iso


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="splendor", description="Splendor knowledge compiler CLI")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--root",
        default=Path.cwd(),
        type=Path,
        help="Workspace root to operate on. Defaults to the current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a Splendor workspace")
    init_parser.set_defaults(handler=handle_init)

    add_source_parser = subparsers.add_parser("add-source", help="Register a new immutable source")
    add_source_parser.add_argument(
        "path",
        type=Path,
        help="Path to the source file to register.",
    )
    add_source_parser.add_argument(
        "--storage-mode",
        choices=STORAGE_MODES,
        help="Override the configured storage mode for this source.",
    )
    capture_group = add_source_parser.add_mutually_exclusive_group()
    capture_group.add_argument(
        "--capture-source-commit",
        dest="capture_source_commit",
        action="store_true",
        help="Capture the current HEAD commit for clean tracked workspace files.",
    )
    capture_group.add_argument(
        "--no-capture-source-commit",
        dest="capture_source_commit",
        action="store_false",
        help="Do not capture git provenance for this registration.",
    )
    add_source_parser.set_defaults(capture_source_commit=None)
    add_source_parser.set_defaults(handler=handle_add_source)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest registered sources into the wiki")
    ingest_parser.add_argument(
        "source_id",
        nargs="?",
        help="Registered source identifier to ingest",
    )
    ingest_parser.add_argument(
        "--pending",
        action="store_true",
        help="Drain pending ingestion jobs from the queue.",
    )
    ingest_parser.set_defaults(handler=handle_ingest)

    materialize_parser = subparsers.add_parser(
        "materialize-source", help="Create or refresh a source storage artifact"
    )
    materialize_parser.add_argument(
        "source_id",
        help="Registered source identifier to materialize.",
    )
    materialize_parser.add_argument(
        "--storage-mode",
        choices=tuple(mode for mode in STORAGE_MODES if mode != "none"),
        help="Override the target storage mode for this materialization.",
    )
    materialize_parser.set_defaults(handler=handle_materialize_source)

    lint_parser = subparsers.add_parser("lint", help="Run deterministic maintenance checks")
    lint_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    lint_parser.set_defaults(handler=handle_lint)

    health_parser = subparsers.add_parser("health", help="Validate source storage state")
    health_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    health_parser.set_defaults(handler=handle_health)

    query_parser = subparsers.add_parser("query", help="Query maintained wiki and planning records")
    query_parser.add_argument("question", nargs="+", help="Question or search phrase.")
    query_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    query_parser.set_defaults(handler=handle_query)

    file_answer_parser = subparsers.add_parser(
        "file-answer", help="File a saved query result back into the wiki"
    )
    file_answer_parser.add_argument(
        "--from-last-query",
        action="store_true",
        help="Use the latest saved query snapshot from state/queries/last-query.json.",
    )
    file_answer_parser.add_argument(
        "--title",
        required=True,
        help="Title for the filed answer page.",
    )
    file_answer_parser.add_argument("--page-id", help="Explicit page identifier override.")
    file_answer_parser.add_argument("--question-id", help="Explicit question to mark answered.")
    file_answer_parser.set_defaults(handler=handle_file_answer)

    task_parser = subparsers.add_parser("task", help="Create or inspect task records")
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)
    task_create_parser = task_subparsers.add_parser("create", help="Create a task record")
    task_create_parser.add_argument("title", nargs="+", help="Task title")
    task_create_parser.add_argument("--id", dest="record_id", help="Explicit task identifier")
    task_create_parser.add_argument(
        "--status",
        choices=TaskRecord.model_fields["status"].annotation.__args__,
        default=TaskRecord.model_fields["status"].default,
        help="Initial task status.",
    )
    task_create_parser.add_argument(
        "--priority",
        choices=TaskRecord.model_fields["priority"].annotation.__args__,
        default=TaskRecord.model_fields["priority"].default,
        help="Task priority.",
    )
    task_create_parser.add_argument("--owner", help="Task owner")
    task_create_parser.add_argument(
        "--milestone-ref", action="append", default=[], help="Linked milestone reference"
    )
    task_create_parser.add_argument(
        "--decision-ref", action="append", default=[], help="Linked decision reference"
    )
    task_create_parser.add_argument(
        "--question-ref", action="append", default=[], help="Linked question reference"
    )
    task_create_parser.add_argument(
        "--depends-on", action="append", default=[], help="Task dependency reference"
    )
    task_create_parser.add_argument(
        "--source-ref", action="append", default=[], help="Linked source reference"
    )
    task_create_parser.set_defaults(handler=handle_task_create)
    task_list_parser = task_subparsers.add_parser("list", help="List task records")
    task_list_parser.add_argument(
        "--status",
        choices=TaskRecord.model_fields["status"].annotation.__args__,
        help="Filter by task status.",
    )
    task_list_parser.add_argument(
        "--priority",
        choices=TaskRecord.model_fields["priority"].annotation.__args__,
        help="Filter by task priority.",
    )
    task_list_parser.add_argument("--milestone-ref", help="Filter by milestone reference")
    task_list_parser.set_defaults(handler=handle_task_list)

    milestone_parser = subparsers.add_parser(
        "milestone", help="Create or inspect milestone records"
    )
    milestone_subparsers = milestone_parser.add_subparsers(dest="milestone_command", required=True)
    milestone_create_parser = milestone_subparsers.add_parser(
        "create", help="Create a milestone record"
    )
    milestone_create_parser.add_argument("title", nargs="+", help="Milestone title")
    milestone_create_parser.add_argument(
        "--id", dest="record_id", help="Explicit milestone identifier"
    )
    milestone_create_parser.add_argument(
        "--status",
        choices=MilestoneRecord.model_fields["status"].annotation.__args__,
        default=MilestoneRecord.model_fields["status"].default,
        help="Initial milestone status.",
    )
    milestone_create_parser.add_argument("--target-date", help="Milestone target date")
    milestone_create_parser.add_argument(
        "--task-ref", action="append", default=[], help="Linked task reference"
    )
    milestone_create_parser.add_argument(
        "--decision-ref", action="append", default=[], help="Linked decision reference"
    )
    milestone_create_parser.add_argument(
        "--question-ref", action="append", default=[], help="Linked question reference"
    )
    milestone_create_parser.set_defaults(handler=handle_milestone_create)
    milestone_list_parser = milestone_subparsers.add_parser("list", help="List milestone records")
    milestone_list_parser.add_argument(
        "--status",
        choices=MilestoneRecord.model_fields["status"].annotation.__args__,
        help="Filter by milestone status.",
    )
    milestone_list_parser.set_defaults(handler=handle_milestone_list)

    decision_parser = subparsers.add_parser("decision", help="Create decision records")
    decision_subparsers = decision_parser.add_subparsers(dest="decision_command", required=True)
    decision_create_parser = decision_subparsers.add_parser(
        "create", help="Create a decision record"
    )
    decision_create_parser.add_argument("title", nargs="+", help="Decision title")
    decision_create_parser.add_argument("--id", dest="record_id", help="Explicit decision ID")
    decision_create_parser.add_argument(
        "--status",
        choices=DecisionRecord.model_fields["status"].annotation.__args__,
        default=DecisionRecord.model_fields["status"].default,
        help="Initial decision status.",
    )
    decision_create_parser.add_argument("--decided-at", help="Decision date")
    decision_create_parser.add_argument(
        "--supersedes", action="append", default=[], help="Superseded decision reference"
    )
    decision_create_parser.add_argument(
        "--source-ref", action="append", default=[], help="Linked source reference"
    )
    decision_create_parser.add_argument(
        "--related-task", action="append", default=[], help="Related task reference"
    )
    decision_create_parser.add_argument(
        "--related-question", action="append", default=[], help="Related question reference"
    )
    decision_create_parser.set_defaults(handler=handle_decision_create)

    question_parser = subparsers.add_parser("question", help="Create question records")
    question_subparsers = question_parser.add_subparsers(dest="question_command", required=True)
    question_create_parser = question_subparsers.add_parser(
        "create", help="Create a question record"
    )
    question_create_parser.add_argument("title", nargs="+", help="Question title")
    question_create_parser.add_argument("--id", dest="record_id", help="Explicit question ID")
    question_create_parser.add_argument(
        "--status",
        choices=QuestionRecord.model_fields["status"].annotation.__args__,
        default=QuestionRecord.model_fields["status"].default,
        help="Initial question status.",
    )
    question_create_parser.add_argument(
        "--source-ref", action="append", default=[], help="Linked source reference"
    )
    question_create_parser.add_argument(
        "--related-task", action="append", default=[], help="Related task reference"
    )
    question_create_parser.add_argument(
        "--related-decision", action="append", default=[], help="Related decision reference"
    )
    question_create_parser.set_defaults(handler=handle_question_create)
    return parser


def handle_init(args: argparse.Namespace) -> int:
    result = initialize_workspace(args.root.resolve())
    print(f"Initialized Splendor workspace at {result.root}")
    print(f"Created directories: {len(result.created_directories)}")
    print(f"Created files: {len(result.created_files)}")
    return 0


def _error_message(exc: Exception) -> str:
    message = " ".join(str(exc).splitlines()).strip()
    return message or exc.__class__.__name__


def _print_error(exc: Exception) -> int:
    print(f"Error: {_error_message(exc)}")
    return 1


def handle_add_source(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    candidate_path = args.path.expanduser()
    source_path = candidate_path if candidate_path.is_absolute() else root / candidate_path
    try:
        result = add_source(
            root,
            source_path,
            storage_mode=args.storage_mode,
            capture_source_commit=args.capture_source_commit,
        )
    except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
        return _print_error(exc)
    action = "Already registered" if result.already_registered else "Registered"
    print(f"{action} source {result.source_id}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Source ref: {result.source_ref}")
    print(f"Storage mode: {result.storage_mode}")
    if result.stored_path is not None:
        print(f"Storage artifact: {result.stored_path}")
    return 0


def handle_ingest(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if args.pending:
        try:
            result = drain_pending_ingest_jobs(root)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            return _print_error(exc)

        if result.total == 0:
            print("No pending ingest jobs")
            return 0

        for item in result.items:
            print(f"{item.source_id}: {item.outcome} ({item.message})")
        print(
            "Drain summary: "
            f"processed={result.processed} "
            f"succeeded={result.succeeded} "
            f"failed={result.failed} "
            f"skipped={result.skipped}"
        )
        return 1 if result.failed else 0

    try:
        result = ingest_source(root, args.source_id)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if result.no_op:
        print(f"Source {result.source_id} is already ingested for the current pipeline version")
        print(f"Page: {result.page_path}")
        return 0

    print(f"Ingested source {result.source_id}")
    print(f"Source ref: {result.canonical_ref}")
    print(f"Canonical content: {result.content_origin_kind.replace('_', ' ')}")
    print(f"Run: {result.run_id}")
    print(f"Page: {result.page_path}")
    print(f"Queue record: {result.queue_path}")
    print(f"Run record: {result.run_path}")
    return 0


def handle_materialize_source(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = materialize_source(root, args.source_id, storage_mode=args.storage_mode)
    except (FileNotFoundError, ValueError) as exc:
        return _print_error(exc)

    print(f"Materialized source {result.source_id}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Source ref: {result.source_ref}")
    print(f"Storage mode: {result.storage_mode}")
    print(f"Storage artifact: {result.stored_path}")
    return 0


def _print_maintenance_stdout(command: str, report, *, json_output: bool) -> None:
    if json_output:
        print(render_report_json(report), end="")
        return

    if report.status == "error":
        print(f"Error: {_error_message(ValueError(report.fatal_error or 'unknown error'))}")
        return

    label = "records" if command == "health" else "items"
    print(f"Checked {label}: {report.checked_count}")
    if report.status == "passed":
        print(f"{command.title()} check passed")
        return

    print(f"{command.title()} check failed: {report.issue_count} issue(s)")
    for issue in report.issues:
        subject = issue.record_id or issue.path or issue.check_name or issue.code
        print(f"- {subject}: {issue.message}")


def handle_lint(args: argparse.Namespace) -> int:
    result = execute_maintenance_command(
        args.root.resolve(),
        command="lint",
        run_checks=run_lint_checks,
    )
    _print_maintenance_stdout("lint", result.report, json_output=args.json_output)
    return result.exit_code


def handle_health(args: argparse.Namespace) -> int:
    result = execute_maintenance_command(
        args.root.resolve(),
        command="health",
        run_checks=run_health_checks,
    )
    _print_maintenance_stdout("health", result.report, json_output=args.json_output)
    return result.exit_code


def handle_query(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = run_query(root, " ".join(args.question))
    except ValueError as exc:
        return _print_error(exc)

    try:
        layout = resolve_layout(root, load_config(root))
        snapshot = QuerySnapshot(
            query=result.query,
            summary=result.summary,
            match_count=result.match_count,
            created_at=utc_now_iso(),
            matches=[
                QueryMatchSnapshot(
                    rank=match.rank,
                    score=match.score,
                    document_class=match.document_class,
                    kind=match.kind,
                    record_id=match.record_id,
                    title=match.title,
                    path=match.path,
                    status=match.status,
                    review_state=match.review_state,
                    last_generated_at=match.last_generated_at,
                    snippet=match.snippet,
                    source_refs=match.source_refs,
                    generated_by_run_ids=match.generated_by_run_ids,
                    provenance_links=match.provenance_links,
                    contradiction_count=match.contradiction_count,
                    review_task_ids=match.review_task_ids,
                    tags=match.tags,
                )
                for match in result.matches
            ],
        )
        write_query_snapshot(last_query_path_for(layout), snapshot)
    except OSError as exc:
        return _print_error(exc)

    if args.json_output:
        payload = {
            "query": result.query,
            "summary": result.summary,
            "match_count": result.match_count,
            "matches": [
                {
                    "rank": match.rank,
                    "score": match.score,
                    "document_class": match.document_class,
                    "kind": match.kind,
                    "record_id": match.record_id,
                    "title": match.title,
                    "path": match.path,
                    "status": match.status,
                    "review_state": match.review_state,
                    "last_generated_at": match.last_generated_at,
                    "snippet": match.snippet,
                    "source_refs": match.source_refs,
                    "generated_by_run_ids": match.generated_by_run_ids,
                    "provenance_links": [
                        link.model_dump(mode="json") for link in match.provenance_links
                    ],
                    "contradiction_count": match.contradiction_count,
                    "review_task_ids": match.review_task_ids,
                    "tags": match.tags,
                }
                for match in result.matches
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Query: {result.query}")
    print(f"Summary: {result.summary}")
    print("Matches:")
    for match in result.matches:
        print(f"{match.rank}. {match.title} [{match.kind}]")
        print(f"   Path: {match.path}")
        print(f"   Snippet: {match.snippet}")
        if match.review_state is not None:
            print(f"   Review state: {match.review_state}")
        if match.last_generated_at is not None:
            print(f"   Last generated: {match.last_generated_at}")
        print(f"   Source refs: {', '.join(match.source_refs) if match.source_refs else '-'}")
        if match.generated_by_run_ids:
            print(f"   Generated by runs: {', '.join(match.generated_by_run_ids)}")
        if match.provenance_links:
            print(f"   Provenance: {summarize_provenance_links(match.provenance_links)}")
        if match.contradiction_count:
            print(f"   Contradictions: {match.contradiction_count}")
        if match.review_task_ids:
            print(f"   Review tasks: {', '.join(match.review_task_ids)}")
    return 0


def handle_file_answer(args: argparse.Namespace) -> int:
    if not args.from_last_query:
        return _print_error(ValueError("file-answer currently requires --from-last-query"))

    root = args.root.resolve()
    question_update = None
    if args.question_id:
        try:
            answer_page_id = args.page_id or default_answer_page_id(args.title)
            question_update = update_question_answer(
                root,
                question_id=args.question_id,
                answer_page_ref=f"wiki/topics/{answer_page_id}.md",
                answer_title=args.title,
            )
        except ValueError as exc:
            return _print_error(exc)

    try:
        result = file_answer_from_last_query(
            root,
            title=args.title,
            page_id=args.page_id,
            question_update=question_update,
        )
    except (OSError, ValueError) as exc:
        return _print_error(exc)

    print(f"Filed answer {result.page_id}")
    print(f"Page: {result.page_path}")
    print(f"Query: {result.query}")
    if result.linked_question_id is not None:
        print(f"Updated question: {result.linked_question_id}")
    return 0


def _title_from_args(args: argparse.Namespace) -> str:
    return " ".join(args.title)


def handle_task_create(args: argparse.Namespace) -> int:
    try:
        result = create_task(
            args.root.resolve(),
            _title_from_args(args),
            record_id=args.record_id,
            status=args.status,
            priority=args.priority,
            owner=args.owner,
            milestone_refs=args.milestone_ref,
            decision_refs=args.decision_ref,
            question_refs=args.question_ref,
            depends_on=args.depends_on,
            source_refs=args.source_ref,
            page_refs=[],
            run_refs=[],
        )
    except ValueError as exc:
        return _print_error(exc)

    print(f"Created task {result.record_id}")
    print(f"Path: {result.path}")
    return 0


def handle_task_list(args: argparse.Namespace) -> int:
    try:
        rows = list_tasks(
            args.root.resolve(),
            status=args.status,
            priority=args.priority,
            milestone_ref=args.milestone_ref,
        )
    except ValueError as exc:
        return _print_error(exc)

    for row in rows:
        print(f"{row.task_id}  {row.status}  {row.priority}  {row.title}")
    return 0


def handle_milestone_create(args: argparse.Namespace) -> int:
    try:
        result = create_milestone(
            args.root.resolve(),
            _title_from_args(args),
            record_id=args.record_id,
            status=args.status,
            target_date=args.target_date,
            task_refs=args.task_ref,
            decision_refs=args.decision_ref,
            question_refs=args.question_ref,
        )
    except ValueError as exc:
        return _print_error(exc)

    print(f"Created milestone {result.record_id}")
    print(f"Path: {result.path}")
    return 0


def handle_milestone_list(args: argparse.Namespace) -> int:
    try:
        rows = list_milestones(args.root.resolve(), status=args.status)
    except ValueError as exc:
        return _print_error(exc)

    for row in rows:
        target_date = row.target_date or "-"
        print(f"{row.milestone_id}  {row.status}  {target_date}  {row.title}")
    return 0


def handle_decision_create(args: argparse.Namespace) -> int:
    try:
        result = create_decision(
            args.root.resolve(),
            _title_from_args(args),
            record_id=args.record_id,
            status=args.status,
            decided_at=args.decided_at,
            supersedes=args.supersedes,
            source_refs=args.source_ref,
            related_tasks=args.related_task,
            related_questions=args.related_question,
        )
    except ValueError as exc:
        return _print_error(exc)

    print(f"Created decision {result.record_id}")
    print(f"Path: {result.path}")
    return 0


def handle_question_create(args: argparse.Namespace) -> int:
    try:
        result = create_question(
            args.root.resolve(),
            _title_from_args(args),
            record_id=args.record_id,
            status=args.status,
            source_refs=args.source_ref,
            related_tasks=args.related_task,
            related_decisions=args.related_decision,
        )
    except ValueError as exc:
        return _print_error(exc)

    print(f"Created question {result.record_id}")
    print(f"Path: {result.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest" and bool(args.source_id) == bool(args.pending):
        parser.error("ingest requires exactly one of <source_id> or --pending")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
