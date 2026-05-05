"""CLI entrypoint for Splendor."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from splendor import __version__
from splendor.commands.add_source import add_source, expand_source_paths
from splendor.commands.brief import (
    ProjectBrief,
    build_project_brief,
    build_suggest_next,
    render_agent_context_json,
    render_project_brief_json,
    render_suggest_next_json,
)
from splendor.commands.file_answer import (
    default_answer_page_id,
    file_answer_from_last_query,
)
from splendor.commands.health import run_health_checks
from splendor.commands.ingest import drain_pending_ingest_jobs, enqueue_ingest_job, ingest_source
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
from splendor.commands.pr_summary import (
    PathGroup,
    build_pr_summary,
    render_pr_summary_json,
)
from splendor.commands.query import run_query
from splendor.commands.queue import (
    QueueItemSnapshot,
    inspect_queue,
    inspect_queue_job,
    render_queue_inspect_json,
    render_queue_item_json,
    render_queue_retry_json,
    render_repair_ingest_json,
    repair_ingest_source,
    retry_queue_job,
)
from splendor.commands.repo_refresh import refresh_repo, render_repo_refresh_json
from splendor.commands.repo_scan import (
    apply_repo_scan,
    render_repo_scan_json,
    scan_repo,
    write_repo_scan_report,
)
from splendor.commands.source import (
    SourceLookupResult,
    ingest_changed_sources,
    list_sources,
    lookup_sources,
    reconcile_sources,
    refresh_source,
    render_source_freshness_json,
    render_source_lookup_json,
    render_source_path_update_json,
    render_source_reconcile_json,
    render_source_refresh_json,
    render_stale_ingest_json,
    resolve_source_query_exact,
    scan_source_freshness,
    source_reconcile_next_commands,
    update_source_path,
    write_source_freshness_report,
)
from splendor.commands.source_forget import (
    SourceForgetResult,
    forget_sources,
    render_source_forget_json,
)
from splendor.commands.wiki import (
    add_topic_page,
    build_wiki_status,
    compile_source_into_page,
    describe_wiki_compile_contract,
    rebuild_wiki_index,
    render_topic_scaffold_json,
    render_wiki_compile_contract_json,
    render_wiki_compile_proposal_json,
    render_wiki_index_rebuild_json,
    render_wiki_status_json,
    render_wiki_suggest_json,
    suggest_source_pages,
)
from splendor.commands.workspace import (
    refresh_workspace,
    render_workspace_refresh_json,
)
from splendor.config import load_config
from splendor.layout import resolve_layout
from splendor.schemas import (
    DecisionRecord,
    MilestoneRecord,
    QueryFilterSnapshot,
    QueryMatchSnapshot,
    QuerySnapshot,
    QuestionRecord,
    TaskRecord,
)
from splendor.schemas.types import STORAGE_MODES
from splendor.state.query_snapshot import last_query_path_for, write_query_snapshot
from splendor.state.source_compat import canonical_source_ref, effective_logical_id
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
        nargs="?",
        type=Path,
        help="Path to the source file to register.",
    )
    add_source_parser.add_argument(
        "--glob",
        action="append",
        default=[],
        dest="glob_patterns",
        help="Register all files matching a glob pattern, in deterministic order.",
    )
    add_source_parser.add_argument(
        "--dir",
        action="append",
        default=[],
        dest="directories",
        type=Path,
        help="Register direct child files from a directory, in deterministic order.",
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

    add_topic_parser = subparsers.add_parser("add-topic", help="Scaffold a maintained topic page")
    add_topic_parser.add_argument("title", help="Topic title")
    add_topic_parser.add_argument(
        "--tags",
        action="append",
        default=[],
        help="Comma-separated or repeated topic tags.",
    )
    add_topic_parser.add_argument(
        "--source-refs",
        action="append",
        default=[],
        help="Comma-separated or repeated source IDs to reference.",
    )
    add_topic_parser.add_argument(
        "--template",
        choices=("default", "research-synthesis", "issue-tracker"),
        default="default",
        help="Deterministic markdown scaffold to use.",
    )
    add_topic_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    add_topic_parser.set_defaults(handler=handle_add_topic)

    source_parser = subparsers.add_parser("source", help="Inspect and refresh source records")
    source_subparsers = source_parser.add_subparsers(dest="source_command", required=True)
    source_list_parser = source_subparsers.add_parser(
        "list", help="List registered sources with readable titles and paths"
    )
    source_list_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    source_list_parser.set_defaults(handler=handle_source_list)
    source_lookup_parser = source_subparsers.add_parser(
        "lookup", help="Find source IDs by title, path, or source ID"
    )
    source_lookup_parser.add_argument("query", nargs="?", help="Title, path, or source ID to find")
    source_lookup_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    source_lookup_parser.set_defaults(handler=handle_source_lookup)
    source_refresh_parser = source_subparsers.add_parser(
        "refresh", help="Detect source content changes and queue ingest work"
    )
    source_refresh_parser.add_argument("query", help="Source ID, title, or path to refresh")
    source_refresh_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    source_refresh_parser.set_defaults(handler=handle_source_refresh)
    source_update_path_parser = source_subparsers.add_parser(
        "update-path", help="Repair a workspace-backed source manifest after a file move"
    )
    source_update_path_parser.add_argument(
        "query", help="Source ID, logical ID, title, or current path to repair"
    )
    source_update_path_parser.add_argument(
        "new_path",
        type=Path,
        help="New workspace path for the curated source file",
    )
    source_update_path_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    source_update_path_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow updating a source path even when the current path still exists.",
    )
    source_update_path_parser.set_defaults(handler=handle_source_update_path)
    source_reconcile_parser = source_subparsers.add_parser(
        "reconcile", help="Preview or repair duplicate active source versions"
    )
    source_reconcile_parser.add_argument(
        "selector",
        help="Source ID, logical ID, title, path, or source ref for one canonical source group",
    )
    source_reconcile_parser.add_argument(
        "--current",
        help="Source ID, logical ID, title, path, or source ref to keep active.",
    )
    source_reconcile_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the planned source lifecycle reconciliation.",
    )
    source_reconcile_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    source_reconcile_parser.set_defaults(handler=handle_source_reconcile)
    source_forget_parser = source_subparsers.add_parser(
        "forget", help="Preview or apply source registry cleanup"
    )
    source_forget_parser.add_argument(
        "selector",
        nargs="?",
        help="Exact source ID, logical ID, title, path, or source ref to forget",
    )
    source_forget_parser.add_argument(
        "--matching",
        help="Workspace-relative glob for safe bulk source registry cleanup.",
    )
    source_forget_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the planned cleanup. Without this flag, source forget only previews.",
    )
    source_forget_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    source_forget_parser.set_defaults(handler=handle_source_forget)
    source_freshness_parser = source_subparsers.add_parser(
        "freshness", help="Preview changed workspace-backed source content without mutating"
    )
    source_freshness_parser.add_argument(
        "--report",
        type=Path,
        help=(
            "Write the freshness report JSON to this explicit path. "
            "Relative paths use the current working directory."
        ),
    )
    source_freshness_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    source_freshness_parser.set_defaults(handler=handle_source_freshness)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest registered sources into the wiki")
    ingest_parser.add_argument(
        "source_id",
        nargs="?",
        help="Registered source ID, title, path, or logical ID to ingest",
    )
    ingest_parser.add_argument(
        "--pending",
        action="store_true",
        help="Drain pending ingestion jobs from the queue.",
    )
    ingest_parser.add_argument(
        "--changed",
        action="store_true",
        help="Refresh and ingest checksum-drifted curated workspace-backed sources.",
    )
    ingest_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output for --changed.",
    )
    ingest_parser.set_defaults(handler=handle_ingest)

    queue_parser = subparsers.add_parser("queue", help="Inspect and retry queue jobs")
    queue_subparsers = queue_parser.add_subparsers(dest="queue_command", required=True)
    queue_inspect_parser = queue_subparsers.add_parser(
        "inspect", help="Inspect durable queue records"
    )
    queue_inspect_parser.add_argument("job_id", nargs="?", help="Queue job identifier to inspect")
    queue_inspect_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    queue_inspect_parser.set_defaults(handler=handle_queue_inspect)
    queue_retry_parser = queue_subparsers.add_parser(
        "retry", help="Reset a failed queue job for another ingest attempt"
    )
    queue_retry_parser.add_argument("job_id", help="Queue job identifier to retry")
    queue_retry_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    queue_retry_parser.set_defaults(handler=handle_queue_retry)

    repair_parser = subparsers.add_parser("repair", help="Repair failed Splendor state")
    repair_subparsers = repair_parser.add_subparsers(dest="repair_command", required=True)
    repair_ingest_parser = repair_subparsers.add_parser(
        "ingest", help="Requeue and immediately run ingestion for a source"
    )
    repair_ingest_parser.add_argument("source_id", help="Registered source identifier to repair")
    repair_ingest_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    repair_ingest_parser.set_defaults(handler=handle_repair_ingest)

    wiki_parser = subparsers.add_parser("wiki", help="Inspect and maintain wiki state")
    wiki_subparsers = wiki_parser.add_subparsers(dest="wiki_command", required=True)
    wiki_status_parser = wiki_subparsers.add_parser(
        "status", help="Summarize source, page, queue, run, and review state"
    )
    wiki_status_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    wiki_status_parser.set_defaults(handler=handle_wiki_status)
    wiki_suggest_parser = wiki_subparsers.add_parser(
        "suggest", help="Suggest synthesis pages affected by a source"
    )
    wiki_suggest_parser.add_argument(
        "source_id", help="Registered source ID, title, or path to inspect"
    )
    wiki_suggest_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    wiki_suggest_parser.set_defaults(handler=handle_wiki_suggest)
    wiki_compile_parser = wiki_subparsers.add_parser(
        "compile", help="Describe the review-gated synthesis compile contract for a source"
    )
    wiki_compile_parser.add_argument(
        "source_id", help="Registered source ID, title, or path to inspect"
    )
    wiki_compile_parser.add_argument(
        "--page",
        help=(
            "Maintained synthesis page path, page ID, or exact title to propose updates for. "
            "Without --page the command prints the compile contract only."
        ),
    )
    wiki_compile_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the proposed page update after explicit operator review.",
    )
    wiki_compile_parser.add_argument(
        "--proposal-hash",
        help="Proposal hash from a reviewed `wiki compile --page` preview. Required with --apply.",
    )
    wiki_compile_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    wiki_compile_parser.set_defaults(handler=handle_wiki_compile)
    wiki_rebuild_index_parser = wiki_subparsers.add_parser(
        "rebuild-index", help="Regenerate wiki/index.md from wiki page frontmatter"
    )
    wiki_rebuild_index_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    wiki_rebuild_index_parser.set_defaults(handler=handle_wiki_rebuild_index)

    workspace_parser = subparsers.add_parser(
        "workspace", help="Run safe workspace-level maintenance workflows"
    )
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command", required=True)
    workspace_refresh_parser = workspace_subparsers.add_parser(
        "refresh", help="Refresh changed curated workspace-backed sources"
    )
    workspace_refresh_parser.add_argument(
        "--changed",
        action="store_true",
        help="Refresh only curated workspace-backed sources whose bytes changed.",
    )
    workspace_refresh_parser.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest queue jobs created or reused for refreshed sources.",
    )
    workspace_refresh_parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Rebuild wiki/index.md after a successful pending ingest drain.",
    )
    workspace_refresh_parser.add_argument(
        "--prune-superseded",
        action="store_true",
        help="Delete superseded generated source-summary pages after a successor exists.",
    )
    workspace_refresh_parser.add_argument(
        "--update-topic-refs",
        action="store_true",
        help="Rewrite maintained wiki source_refs from superseded source IDs to active versions.",
    )
    workspace_refresh_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    workspace_refresh_parser.set_defaults(handler=handle_workspace_refresh)

    pr_summary_parser = subparsers.add_parser(
        "pr-summary", help="Summarize PR-relevant Splendor state changes"
    )
    pr_summary_parser.add_argument(
        "--since",
        default="main",
        help="Base git ref to compare against. Defaults to main.",
    )
    pr_summary_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    pr_summary_parser.set_defaults(handler=handle_pr_summary)

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
    query_parser.add_argument("question", nargs="*", help="Question or search phrase.")
    query_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        dest="tags",
        help="Restrict wiki results to pages with this tag. May be repeated.",
    )
    query_parser.add_argument(
        "--source",
        dest="source_id",
        help="Restrict results to records referencing this source ID, title, or path.",
    )
    query_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    query_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not update the last-query snapshot.",
    )
    query_parser.set_defaults(handler=handle_query)

    brief_parser = subparsers.add_parser(
        "brief", help="Assemble a compact project briefing for a goal"
    )
    brief_parser.add_argument("goal", nargs="*", help="Optional goal or search phrase.")
    brief_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    brief_parser.add_argument(
        "--agent-context",
        action="store_true",
        help="Emit a compact coding-agent handoff over brief state.",
    )
    brief_parser.set_defaults(handler=handle_brief)

    suggest_next_parser = subparsers.add_parser(
        "suggest-next", help="Rank deterministic next actions for agent handoff"
    )
    suggest_next_parser.add_argument("goal", nargs="*", help="Optional goal or search phrase.")
    suggest_next_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    suggest_next_parser.set_defaults(handler=handle_suggest_next)

    serve_parser = subparsers.add_parser("serve", help="Run the read-only local web UI")
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind. Defaults to 127.0.0.1.",
    )
    serve_parser.add_argument(
        "--port",
        default=8000,
        type=int,
        help="Port to bind. Defaults to 8000.",
    )
    serve_parser.set_defaults(handler=handle_serve)

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

    repo_parser = subparsers.add_parser("repo", help="Inspect repository-native sources")
    repo_subparsers = repo_parser.add_subparsers(dest="repo_command", required=True)
    repo_scan_parser = repo_subparsers.add_parser(
        "scan", help="Preview repository source candidates without mutating by default"
    )
    repo_scan_parser.add_argument(
        "--apply",
        action="store_true",
        help="Register previewed candidates as sources. Requires --class or --all.",
    )
    repo_scan_parser.add_argument(
        "--class",
        action="append",
        choices=("documentation", "code", "configuration", "other"),
        dest="class_filters",
        help="Limit candidates to a source class. Repeat for multiple classes.",
    )
    repo_scan_parser.add_argument(
        "--all",
        action="store_true",
        dest="all_classes",
        help="Include every supported source class.",
    )
    repo_scan_parser.add_argument(
        "--allow-large-apply",
        action="store_true",
        help="Allow --apply when the candidate set is larger than the safety threshold.",
    )
    repo_scan_parser.add_argument(
        "--report",
        type=Path,
        help="Write the discovery report JSON to this explicit path.",
    )
    repo_scan_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    repo_scan_parser.set_defaults(handler=handle_repo_scan)
    repo_refresh_parser = repo_subparsers.add_parser(
        "refresh", help="Refresh deterministic repo-aware wiki pages"
    )
    repo_refresh_parser.add_argument(
        "--apply-scan",
        action="store_true",
        help="Register scan candidates before refreshing pages. Requires --class or --all.",
    )
    repo_refresh_parser.add_argument(
        "--class",
        action="append",
        choices=("documentation", "code", "configuration", "other"),
        dest="class_filters",
        help="Limit refresh scan candidates to a source class. Repeat for multiple classes.",
    )
    repo_refresh_parser.add_argument(
        "--all",
        action="store_true",
        dest="all_classes",
        help="Include every supported source class in the refresh scan.",
    )
    repo_refresh_parser.add_argument(
        "--allow-large-apply",
        action="store_true",
        help="Allow --apply-scan when the candidate set is larger than the safety threshold.",
    )
    repo_refresh_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    repo_refresh_parser.set_defaults(handler=handle_repo_refresh)
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


def _suggested_answer_title(query: str) -> str:
    words = query.split()
    title = " ".join(words[:6]).strip() or "Filed answer"
    if len(words) > 6:
        title = f"{title} answer"
    return title


def _is_missing_workspace_wiki_error(exc: Exception) -> bool:
    return str(exc).startswith("Workspace is missing required wiki files:")


def handle_add_source(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        source_paths = expand_source_paths(
            root,
            source_path=args.path,
            glob_patterns=args.glob_patterns,
            directories=args.directories,
        )
        if not source_paths:
            print("Error: add-source requires a path, --glob match, or --dir with files")
            return 1
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, ValueError) as exc:
        return _print_error(exc)

    if len(source_paths) > 1:
        results = []
        registration_errors = 0
        queue_warnings = 0
        missing_init_warning = False
        queued = 0
        for source_path in source_paths:
            try:
                result = add_source(
                    root,
                    source_path,
                    storage_mode=args.storage_mode,
                    capture_source_commit=args.capture_source_commit,
                )
            except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
                registration_errors += 1
                print(f"- {source_path}: registration failed: {_error_message(exc)}")
                continue

            results.append(result)
            action = "already registered" if result.already_registered else "registered"
            print(f"- {result.source_ref}: {action} source_id={result.source_id}")
            if result.already_registered:
                continue
            try:
                enqueue_ingest_job(root, result.source_id)
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                queue_warnings += 1
                missing_init_warning = missing_init_warning or _is_missing_workspace_wiki_error(exc)
                print(
                    f"  Warning: source registered but ingest was not queued: {_error_message(exc)}"
                )
                continue
            queued += 1

        print(f"Registered sources: {sum(not result.already_registered for result in results)}")
        print(f"Already registered: {sum(result.already_registered for result in results)}")
        print(f"Registration failures: {registration_errors}")
        print(f"Queued ingest jobs: {queued}")
        print(f"Queue warnings: {queue_warnings}")
        if missing_init_warning:
            print("Next: splendor init")
            print("Then: splendor ingest --pending")
        elif queue_warnings:
            print("Next: splendor queue inspect")
        elif queued:
            print("Next: splendor ingest --pending")
        else:
            print("Next: splendor source lookup")
        return 1 if registration_errors or queue_warnings else 0

    try:
        result = add_source(
            root,
            source_paths[0],
            storage_mode=args.storage_mode,
            capture_source_commit=args.capture_source_commit,
        )
    except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
        return _print_error(exc)
    action = "Already registered" if result.already_registered else "Registered"
    print(f"Source ref: {result.source_ref}")
    logical_id = effective_logical_id(result.record)
    if logical_id is not None:
        print(f"Logical ID: {logical_id}")
    print(f"{action} source {result.source_id}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Storage mode: {result.storage_mode}")
    if result.stored_path is not None:
        print(f"Storage artifact: {result.stored_path}")
    if not result.already_registered:
        try:
            queue_path = enqueue_ingest_job(root, result.source_id)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            warning = _error_message(exc)
            print(f"Warning: source registered but ingest was not queued: {warning}")
            if _is_missing_workspace_wiki_error(exc):
                print("Next: splendor init")
                print(f"Then: splendor ingest {result.source_id}")
            else:
                print(f"Next: splendor ingest {result.source_id}")
            return 0
        print(f"Queued ingest: {queue_path}")
        print("Next: splendor ingest --pending")
    else:
        print(f"Next: splendor ingest {result.source_id}")
    return 0


def _split_repeated_csv(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in value.split(","):
            normalized = part.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result


def handle_add_topic(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = add_topic_page(
            root,
            args.title,
            tags=_split_repeated_csv(args.tags),
            source_refs=_split_repeated_csv(args.source_refs),
            template=args.template,
        )
    except (FileExistsError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_topic_scaffold_json(result))
        return 0

    print(f"Created topic: {result.path}")
    print(f"Page ID: {result.page_id}")
    print(f"Template: {result.template}")
    print("Updated index: wiki/index.md")
    return 0


def handle_source_list(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        results = list_sources(root)
    except (FileNotFoundError, ValueError) as exc:
        return _print_error(exc)
    if args.json_output:
        print(render_source_lookup_json(root, results))
        return 0
    _print_source_lookup_results(results)
    return 0


def handle_source_lookup(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        results = lookup_sources(root, args.query)
    except (FileNotFoundError, ValueError) as exc:
        return _print_error(exc)
    if args.json_output:
        print(render_source_lookup_json(root, results))
        return 0
    _print_source_lookup_results(results)
    return 0


def handle_source_refresh(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = refresh_source(root, args.query)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)
    if args.json_output:
        print(render_source_refresh_json(root, result))
        return 0

    if result.changed:
        print(f"Detected changed source content for {canonical_source_ref(result.requested)}")
        print(f"Requested source ID: {result.requested.source_id}")
        if result.refreshed.record.source_id != result.requested.source_id:
            if result.refreshed.already_registered:
                print(f"Matched existing source version: {result.refreshed.record.source_id}")
            else:
                print(f"Registered refreshed source ID: {result.refreshed.record.source_id}")
            print(
                "Superseded previous source version: "
                f"{result.requested.source_id} -> {result.refreshed.record.source_id}"
            )
    else:
        print(f"No source content change detected for {canonical_source_ref(result.requested)}")
        print(f"Source ID: {result.requested.source_id}")
    print(f"Source ref: {result.refreshed.source_ref}")
    logical_id = effective_logical_id(result.refreshed.record)
    if logical_id is not None:
        print(f"Logical ID: {logical_id}")
    if result.refreshed.record.supersedes:
        print(f"Supersedes: {', '.join(result.refreshed.record.supersedes)}")
    if result.refreshed.record.superseded_by is not None:
        print(f"Superseded by: {result.refreshed.record.superseded_by}")
    if result.queued and result.queue_path is not None:
        print(f"Queued ingest: {result.queue_path}")
        print("Next: splendor ingest --pending")
    else:
        print(f"Refresh skipped: {result.message}")
        print(f"Next: splendor wiki suggest {result.refreshed.record.source_id}")
    return 0


def handle_source_update_path(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = update_source_path(root, args.query, args.new_path, force=args.force)
    except (FileNotFoundError, IsADirectoryError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_source_path_update_json(root, result))
        return 0 if result.status == "repaired" else 1

    print(f"Updated source path for {result.source.source_id}")
    print(f"Status: {result.status}")
    print(f"Old path: {result.old_path}")
    print(f"New path: {result.new_path}")
    logical_id = effective_logical_id(result.source)
    if logical_id is not None:
        print(f"Logical ID: {logical_id}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Manifest checksum: {result.manifest_checksum}")
    print(f"Current checksum: {result.current_checksum}")
    if result.checksum_matches:
        print("Checksum: matches manifest")
        if result.queue_path is not None:
            print(f"Queued ingest: {result.queue_path}")
    else:
        print("Checksum: differs from manifest")
        print("Path was updated, but content refresh is still required.")
    for command in result.next_commands:
        print(f"Next: {command}")
    return 0 if result.status == "repaired" else 1


def handle_source_reconcile(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = reconcile_sources(
            root,
            args.selector,
            current_selector=args.current,
            apply=args.apply,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_source_reconcile_json(root, result))
        return 0

    action = "Applied source reconciliation" if result.applied else "Source reconciliation preview"
    print(action)
    print(f"Canonical source ref: {result.canonical_ref}")
    print(f"Current source ID: {result.current.source_id}")
    print(
        f"Active versions before: {', '.join(source.source_id for source in result.active_before)}"
    )
    if not result.updates:
        print("No reconciliation changes needed.")
    else:
        print("Planned updates:" if not result.applied else "Applied updates:")
        for update in result.updates:
            print(f"- {update.source.source_id}: {update.manifest_path}")
            if update.before_superseded_by != update.after_superseded_by:
                print(
                    "  superseded_by: "
                    f"{update.before_superseded_by or '-'} -> {update.after_superseded_by or '-'}"
                )
            if update.before_supersedes != update.after_supersedes:
                before = ", ".join(update.before_supersedes) or "-"
                after = ", ".join(update.after_supersedes) or "-"
                print(f"  supersedes: {before} -> {after}")
    for command in source_reconcile_next_commands(result):
        print(f"Next: {command}")
    return 0


def handle_source_forget(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = forget_sources(
            root,
            selector=args.selector,
            matching=args.matching,
            apply=args.apply,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_source_forget_json(root, result))
        return 0

    _print_source_forget_result(result)
    return 0


def handle_source_freshness(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = scan_source_freshness(root)
        if args.report is not None:
            result = write_source_freshness_report(root, result, args.report)
    except (FileNotFoundError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_source_freshness_json(root, result))
        return 0

    print("Source freshness preview")
    print(
        "Summary: "
        f"total={result.total} "
        f"unchanged={result.unchanged} "
        f"changed={result.changed} "
        f"missing={result.missing} "
        f"unsupported={result.unsupported} "
        f"historical={result.historical}"
    )
    if result.report_path is not None:
        print(f"Report: {result.report_path}")
    if not result.sources:
        print("No source manifests found.")
        return 0
    for item in result.sources:
        source = item.source
        print(
            f"- {item.canonical_path}: {item.status} "
            f"title={source.title} "
            f"logical_id={effective_logical_id(source) or '-'} "
            f"source_id={source.source_id}"
        )
        print(f"  Manifest: {item.manifest_path}")
        print(f"  Manifest checksum: {item.manifest_checksum}")
        if item.current_checksum is not None:
            print(f"  Current checksum: {item.current_checksum}")
        print(f"  Message: {item.message}")
        for command in item.next_commands:
            print(f"  Next: {command}")
    if result.missing:
        print("Next: restore missing source files or inspect the listed source manifests")
    elif not result.changed:
        print("Next: splendor source lookup")
    return 0


def handle_ingest(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if args.changed:
        return _handle_ingest_changed(args)

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
        succeeded_source_ids = [
            item.source_id for item in result.items if item.outcome == "succeeded"
        ]
        if len(succeeded_source_ids) == 1:
            print(f"Next: splendor wiki suggest {succeeded_source_ids[0]}")
        elif len(succeeded_source_ids) > 1:
            print("Next: splendor wiki status")
        return 1 if result.failed else 0

    try:
        source = resolve_source_query_exact(root, args.source_id).source
        result = ingest_source(root, source.source_id)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if result.no_op:
        print(f"Source {result.source_id} is already ingested for the current pipeline version")
        print(f"Page: {result.page_path}")
        return 0

    print(f"Ingested source: {result.canonical_ref}")
    print(f"Source ID: {result.source_id}")
    print(f"Canonical content: {result.content_origin_kind.replace('_', ' ')}")
    print(f"Run: {result.run_id}")
    print(f"Page: {result.page_path}")
    print(f"Queue record: {result.queue_path}")
    print(f"Run record: {result.run_path}")
    print(f"Next: splendor wiki suggest {result.source_id}")
    print(
        "Generated state: review source-summary, source manifest, queue, and run changes; "
        "commit explicit reports only when they support the reviewed workspace update."
    )
    return 0


def _handle_ingest_changed(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = ingest_changed_sources(root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_stale_ingest_json(root, result))
    elif result.status == "no-op":
        print("No changed curated workspace-backed sources found.")
        print(_format_source_freshness_counts("Freshness", result.initial_freshness))
    else:
        if result.status == "blocked":
            print("Stale ingest blocked")
        elif result.status == "partial":
            print("Stale ingest completed with unresolved sources")
        else:
            print("Stale ingest")
        print(_format_source_freshness_counts("Initial freshness", result.initial_freshness))
        if result.missing:
            print("Missing curated sources:")
            for item in result.missing:
                print(f"- {item.canonical_path}: {item.message}")
            print("Next: repair missing source paths or run splendor source freshness")
        for refreshed in result.refreshed:
            if refreshed.status == "failed":
                print(f"- {refreshed.source_ref}: refresh failed ({refreshed.message})")
                continue
            print(
                f"- {refreshed.source_ref}: refreshed "
                f"{refreshed.requested_source_id} -> {refreshed.refreshed_source_id}"
            )
        for item in result.ingest:
            print(f"{item.source_id}: {item.outcome} ({item.message})")
        print(
            "Stale ingest summary: "
            f"processed={result.processed} "
            f"succeeded={result.succeeded} "
            f"failed={result.failed} "
            f"skipped={result.skipped}"
        )
        print(_format_source_freshness_counts("Final freshness", result.final_freshness))
        if result.succeeded == 1:
            source_id = next(
                item.source_id for item in result.ingest if item.outcome == "succeeded"
            )
            print(f"Next: splendor wiki suggest {source_id}")
        elif result.succeeded > 1:
            print("Next: splendor wiki status")
        elif result.failed:
            print("Next: splendor queue inspect")
    return 1 if result.status in {"blocked", "failed", "partial"} else 0


def _format_source_freshness_counts(label: str, result) -> str:
    return (
        f"{label}: "
        f"total={result.total} "
        f"unchanged={result.unchanged} "
        f"changed={result.changed} "
        f"missing={result.missing} "
        f"unsupported={result.unsupported} "
        f"historical={result.historical}"
    )


def handle_queue_inspect(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        if args.job_id:
            item = inspect_queue_job(root, args.job_id)
            if args.json_output:
                print(render_queue_item_json(item))
                return 0
            _print_queue_item_detail(item)
            return 0

        result = inspect_queue(root)
    except (FileNotFoundError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_queue_inspect_json(result))
        return 0

    print("Queue inspect")
    print(f"Total: {result.total}")
    counts = " ".join(f"{status}={count}" for status, count in result.status_counts.items())
    print(f"Status counts: {counts or '-'}")
    if not result.items:
        print("No queue records yet.")
        return 0
    print("Jobs:")
    for item in result.items:
        print(
            f"- {item.job_id} [{item.status}/{item.operator_state}] type={item.job_type} "
            f"attempts={item.attempt_count}/{item.max_attempts} payload={item.payload_ref}"
        )
    operator_states = {item.operator_state for item in result.items}
    if operator_states.intersection({"pending", "failed_due", "expired_leased"}):
        print("Next: splendor ingest --pending")
    elif "dead_letter" in operator_states:
        print("Next: splendor queue retry <job-id> or splendor repair ingest <source-id>")
    elif "failed_backoff" in operator_states:
        print("Next: wait for retry backoff or run splendor queue retry <job-id>")
    elif result.status_counts.get("failed", 0):
        print("Next: splendor queue retry <job-id>")
    return 0


def handle_queue_retry(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = retry_queue_job(root, args.job_id)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_queue_retry_json(result))
        return 0

    print(f"Retried queue job {result.item.job_id}")
    print(f"Queue record: {result.item.record_path}")
    print("Next: splendor ingest --pending")
    return 0


def handle_repair_ingest(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = repair_ingest_source(root, args.source_id)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_repair_ingest_json(root, result))
        return 0

    if result.no_op:
        print(f"Source {result.source_id} is already ingested for the current pipeline version")
    else:
        print(f"Repaired ingest for source {result.source_id}")
        print(f"Run: {result.run_id}")
    if result.queue_path is not None:
        print(f"Queue record: {result.queue_path}")
    if result.run_path is not None:
        print(f"Run record: {result.run_path}")
    if result.page_path is not None:
        print(f"Page: {result.page_path}")
    print(f"Outcome: {result.outcome} ({result.message})")
    if not result.no_op:
        print(f"Next: splendor wiki suggest {result.source_id}")
    return 0


def _print_queue_item_detail(item: QueueItemSnapshot) -> None:
    print(f"Queue job: {item.job_id}")
    print(f"Status: {item.status}")
    print(f"Job type: {item.job_type}")
    print(f"Attempts: {item.attempt_count}/{item.max_attempts}")
    print(f"Created: {item.created_at}")
    print(f"Updated: {item.updated_at}")
    print(f"Payload: {item.payload_ref}")
    print(f"Source ID: {item.source_id or '-'}")
    print(f"Operator state: {item.operator_state}")
    print(f"Lease owner: {item.lease_owner or '-'}")
    print(f"Lease expires: {item.lease_expires_at or '-'}")
    print(f"Next attempt: {item.next_attempt_at or '-'}")
    print(f"Last error: {item.last_error or '-'}")
    print(f"Record: {item.record_path}")
    if item.status == "dead_letter":
        print(
            f"Next: splendor queue retry {item.job_id} or splendor repair ingest {item.source_id}"
        )
    elif item.operator_state == "failed_backoff":
        print(f"Next: wait for retry backoff or run splendor queue retry {item.job_id}")
    elif item.status == "failed":
        print(f"Next: splendor queue retry {item.job_id}")
    elif item.operator_state in {"pending", "failed_due", "expired_leased"}:
        print("Next: splendor ingest --pending")


def _print_source_lookup_results(results: list[SourceLookupResult]) -> None:
    print(f"Sources: {len(results)}")
    if not results:
        print("No matching sources.")
        return
    for result in results:
        source = result.source
        logical_id = effective_logical_id(source)
        print(
            f"- {canonical_source_ref(source)} [{source.status}] {source.title} "
            f"logical_id={logical_id or '-'} source_id={source.source_id} "
            f"ref={canonical_source_ref(source)}"
        )
        print(f"  Manifest: {result.manifest_path}")
    print("Next: splendor source refresh <source-id|title|path>")


def _print_source_forget_result(result: SourceForgetResult) -> None:
    mode = "applied" if result.applied else "preview"
    print(f"Source forget {mode}")
    print(
        "Summary: "
        f"candidates={len(result.candidates)} "
        f"actions={len(result.actions)} "
        f"skipped={len(result.skipped)} "
        f"residual_references={len(result.residual_references)}"
    )
    if not result.candidates:
        print("No matching sources.")
        return
    print("Sources:")
    for candidate in result.candidates:
        source = candidate.source
        print(
            f"- {canonical_source_ref(source)} title={source.title} "
            f"logical_id={effective_logical_id(source) or '-'} source_id={source.source_id}"
        )
        print(f"  Manifest: {candidate.manifest_path}")
    if result.actions:
        print("Actions:")
        for action in result.actions:
            print(f"- {action.status}: {action.kind} {action.path} source_id={action.source_id}")
    if result.skipped:
        print("Skipped:")
        for action in result.skipped:
            print(
                f"- {action.kind} {action.path} source_id={action.source_id}: "
                f"{action.reason or 'not safe to remove'}"
            )
    if result.residual_references:
        print("Residual references:")
        for residual in result.residual_references:
            ref_suffix = f" ref_id={residual.ref_id}" if residual.ref_id is not None else ""
            print(
                f"- {residual.kind} {residual.path} source_id={residual.source_id}: "
                f"{residual.reason}{ref_suffix}"
            )
    if result.applied:
        if result.residual_references:
            print("Next: review reported residual references")
        print("Next: splendor lint")
        print("Next: splendor health")
    else:
        if result.selector is not None:
            print(f"Next: splendor source forget {shlex.quote(result.selector)} --apply")
        else:
            print(
                "Next: "
                f"splendor source forget --matching {shlex.quote(result.matching or '')} --apply"
            )


def handle_wiki_status(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = build_wiki_status(root)
    except ValueError as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_wiki_status_json(result))
        return 0

    print("Wiki status")
    print(
        "Sources: "
        f"total={result.source_total} "
        f"registered={result.source_counts.get('registered', 0)} "
        f"ingested={result.source_counts.get('ingested', 0)} "
        f"failed={result.source_counts.get('failed', 0)}"
    )
    print(
        "Pages: "
        f"total={result.page_total} "
        + " ".join(f"{kind}={count}" for kind, count in result.page_kind_counts.items())
    )
    print(
        "Queue: "
        f"total={result.queue_total} "
        + " ".join(f"{status}={count}" for status, count in result.queue_status_counts.items())
    )
    print(
        "Runs: "
        f"total={result.run_total} "
        + " ".join(f"{status}={count}" for status, count in result.run_status_counts.items())
    )
    print(
        "Review: "
        + " ".join(f"{state}={count}" for state, count in result.review_state_counts.items())
    )
    print(f"Machine-generated pages: {result.machine_generated_pages}")
    print(f"Contested pages: {result.contested_pages}")
    print(f"Stale pages: {result.stale_pages}")
    print(f"Review-needed synthesis pages: {result.review_needed_synthesis_pages}")
    print(f"Sources missing synthesis follow-up: {result.sources_missing_synthesis}")
    print(f"Invalid wiki pages: {result.invalid_pages}")
    for invalid_page in result.invalid_page_examples:
        print(f"- {invalid_page.path}: {invalid_page.error}")
    if result.recent_runs:
        print("Recent runs:")
        for run in result.recent_runs:
            finished = run.finished_at or "-"
            print(f"- {run.run_id} {run.status} finished={finished}")
    return 0


def handle_wiki_suggest(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = suggest_source_pages(root, args.source_id)
    except (FileNotFoundError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_wiki_suggest_json(result))
        return 0

    print(f"Source ref: {result.source_ref}")
    print(f"Source ID: {result.source_id}")
    if len(result.source_ids) > 1:
        print(f"Resolved source IDs: {', '.join(result.source_ids)}")
    print(f"Title: {result.source_title}")
    print(f"Status: {result.source_status}")
    if not result.suggestions:
        print("No likely synthesis-page matches found")
        return 0
    print("Suggested pages:")
    for suggestion in result.suggestions:
        reasons = ", ".join(suggestion.reasons)
        print(f"- {suggestion.path} [{suggestion.kind}] score={suggestion.score} reasons={reasons}")
        print(f"  Compile preview: {suggestion.compile_preview_command}")
    return 0


def handle_wiki_compile(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if args.apply and not args.page:
        return _print_error(ValueError("wiki compile --apply requires --page"))
    if args.apply and not args.proposal_hash:
        return _print_error(ValueError("wiki compile --apply requires --proposal-hash"))
    if args.proposal_hash and not args.apply:
        return _print_error(
            ValueError("wiki compile --proposal-hash can only be used with --apply")
        )
    try:
        if args.page:
            result = compile_source_into_page(
                root,
                args.source_id,
                page_query=args.page,
                apply=args.apply,
                proposal_hash=args.proposal_hash,
            )
        else:
            result = describe_wiki_compile_contract(root, args.source_id)
    except (FileNotFoundError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        if args.page:
            print(render_wiki_compile_proposal_json(result))
        else:
            print(render_wiki_compile_contract_json(result))
        return 0

    if args.page:
        print(f"Source ref: {result.source_ref}")
        print(f"Source ID: {result.source_id}")
        print(f"Title: {result.source_title}")
        print(f"Status: {result.source_status}")
        print(f"Target page: {result.target_path}")
        print(f"Source summary: {result.source_summary_path}")
        print(f"Compile status: {result.status}")
        print(f"Mutates wiki: {'yes' if result.mutates else 'no'}")
        print(f"Target SHA-256: {result.target_sha256}")
        print(f"Source summary SHA-256: {result.source_summary_sha256}")
        print(f"Proposal hash: {result.proposal_hash}")
        print("Evidence:")
        for line in result.evidence_lines:
            print(f"- {line}")
        if result.proposed_diff:
            print("Proposed diff:")
            print(result.proposed_diff, end="" if result.proposed_diff.endswith("\n") else "\n")
        if not args.apply and result.changed:
            print("Next steps:")
            print(
                f"- Review the diff, then run `splendor wiki compile {result.source_id} "
                f"--page {result.target_path} --apply --proposal-hash {result.proposal_hash}`."
            )
        return 0

    print(f"Source ref: {result.source_ref}")
    print(f"Source ID: {result.source_id}")
    print(f"Title: {result.source_title}")
    print(f"Status: {result.source_status}")
    print("Compile contract: review-gated synthesis maintenance")
    print("Mutates wiki: no")
    for item in result.contract:
        print(f"- {item}")
    if result.suggested_pages:
        print("Suggested compile targets:")
        for suggestion in result.suggested_pages:
            reasons = ", ".join(suggestion.reasons)
            print(
                f"- {suggestion.path} [{suggestion.kind}] score={suggestion.score} "
                f"reasons={reasons}"
            )
            print(f"  Compile preview: {suggestion.compile_preview_command}")
    else:
        print("Suggested compile targets: none")
    print("Next steps:")
    for item in result.next_steps:
        print(f"- {item}")
    return 0


def handle_wiki_rebuild_index(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = rebuild_wiki_index(root)
    except ValueError as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_wiki_index_rebuild_json(result))
        return 0

    print(f"Rebuilt index: {result.path}")
    print(f"Pages indexed: {result.page_count}")
    if result.sections:
        print(
            "Sections: "
            + " ".join(f"{section}={count}" for section, count in result.sections.items())
        )
    return 0


def handle_workspace_refresh(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = refresh_workspace(
            root,
            changed=args.changed,
            ingest=args.ingest,
            rebuild_index=args.rebuild_index,
            prune_superseded=args.prune_superseded,
            update_topic_refs=args.update_topic_refs,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_workspace_refresh_json(root, result))
        if (
            result.skipped_sources
            or result.failed_sources
            or (result.ingest is not None and result.ingest.failed)
        ):
            return 1
        return 0

    print("Workspace refresh")
    print(
        "Initial freshness: "
        f"total={result.initial_freshness.total} "
        f"unchanged={result.initial_freshness.unchanged} "
        f"changed={result.initial_freshness.changed} "
        f"missing={result.initial_freshness.missing} "
        f"unsupported={result.initial_freshness.unsupported} "
        f"historical={result.initial_freshness.historical}"
    )
    if not result.refreshed:
        print("No changed curated workspace-backed sources were refreshed.")
    if result.skipped_sources:
        print("Skipped unresolved curated workspace sources:")
        for item in result.skipped_sources:
            print(f"- {item.canonical_path}: {item.status} ({item.message})")
            print(f"  Source ID: {item.source.source_id}")
            logical_id = effective_logical_id(item.source)
            if logical_id is not None:
                print(f"  Logical ID: {logical_id}")
    for refresh in result.refreshed:
        source_ref = canonical_source_ref(refresh.refreshed.record)
        print(f"- {source_ref}: refreshed source_id={refresh.refreshed.record.source_id}")
        print(f"  Previous source ID: {refresh.requested.source_id}")
        logical_id = effective_logical_id(refresh.refreshed.record)
        if logical_id is not None:
            print(f"  Logical ID: {logical_id}")
        if refresh.queued and refresh.queue_path is not None:
            print(f"  Queued ingest: {refresh.queue_path}")
        else:
            print(f"  Refresh skipped: {refresh.message}")
    if result.failed_sources:
        print("Failed changed-source refreshes:")
        for item in result.failed_sources:
            print(f"- {item.path}: failed ({item.reason})")
            print(f"  Source ID: {item.source_id}")
            if item.logical_id is not None:
                print(f"  Logical ID: {item.logical_id}")

    if result.ingest is not None:
        for item in result.ingest.items:
            print(f"  Ingest {item.source_id}: {item.outcome} ({item.message})")
        print(
            "Ingest summary: "
            f"processed={result.ingest.processed} "
            f"succeeded={result.ingest.succeeded} "
            f"failed={result.ingest.failed} "
            f"skipped={result.ingest.skipped}"
        )

    if result.index is not None:
        print(f"Rebuilt index: {result.index.path}")
        print(f"Pages indexed: {result.index.page_count}")
    if result.pruning is not None:
        if not result.pruning.pruned and not result.pruning.skipped:
            print("Pruned superseded source summaries: none")
        for item in result.pruning.pruned:
            print(f"Pruned superseded source summary: {item.path}")
            print(f"  Source ID: {item.source_id}")
            print(f"  Superseded by: {item.superseded_by}")
        for item in result.pruning.skipped:
            print(f"Skipped superseded source summary: {item.path}")
            print(f"  Source ID: {item.source_id}")
            print(f"  Reason: {item.reason}")
    if result.topic_ref_migration is not None:
        if not result.topic_ref_migration.updated:
            print("Updated topic source refs: none")
        for item in result.topic_ref_migration.updated:
            replacement_text = ", ".join(f"{old}->{new}" for old, new in item.replacements.items())
            print(f"Updated topic source refs: {item.path}")
            print(f"  Replacements: {replacement_text}")
    print(
        "Final freshness: "
        f"total={result.final_freshness.total} "
        f"unchanged={result.final_freshness.unchanged} "
        f"changed={result.final_freshness.changed} "
        f"missing={result.final_freshness.missing} "
        f"unsupported={result.final_freshness.unsupported} "
        f"historical={result.final_freshness.historical}"
    )

    if result.ingest is not None and result.ingest.failed:
        print("Next: splendor queue inspect")
        return 1
    if result.skipped_sources or result.failed_sources:
        print("Workspace refresh completed with unresolved curated sources.")
        print("Next: splendor source freshness")
        return 1
    if result.index is None and result.ingest is None and result.refreshed:
        print("Next: splendor ingest --pending")
    elif result.index is None and result.ingest is not None and result.ingest.succeeded:
        print("Next: splendor wiki rebuild-index")
    else:
        print("Next: splendor source freshness")
    return 0


def handle_pr_summary(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        summary = build_pr_summary(root, since=args.since)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_pr_summary_json(summary))
        return 0

    print(f"PR summary since {summary.since}")
    print(f"Merge base: {summary.merge_base}")
    if summary.head is not None:
        print(f"Head: {summary.head}")
    print(f"Changed paths: {summary.changed_path_count}")
    print("Curated sources:")
    if not summary.curated_sources:
        print("- none")
    for source in summary.curated_sources:
        print(f"- {source.path}: {source.action} source_id={source.source_id}")
        if source.source_ref is not None:
            print(f"  Source ref: {source.source_ref}")
        if source.logical_id is not None:
            print(f"  Logical ID: {source.logical_id}")
        if source.supersedes:
            print(f"  Supersedes: {', '.join(source.supersedes)}")
        if source.superseded_by is not None:
            print(f"  Superseded by: {source.superseded_by}")
        if source.error is not None:
            print(f"  Error: {source.error}")

    _print_path_group("Generated source-summary pages", summary.source_summary_pages)
    _print_path_group("Maintained wiki/topic pages", summary.maintained_wiki_pages)
    print("Generated state:")
    for label, group in summary.generated_state.items():
        _print_path_group(f"- {label}", group, indent="  ")
    _print_path_group("Other changed paths", summary.other_paths)

    print("Latest local maintenance reports (not tied to current HEAD):")
    for command in ("lint", "health"):
        status = summary.maintenance.get(command)
        if status is None:
            print(f"- {command}: no local report found")
            continue
        print(
            f"- {command}: {status.status} path={status.path} "
            f"issues={status.issue_count if status.issue_count is not None else '-'}"
        )
        print(f"  Warning: {status.warning}")

    print("Reviewer notes:")
    for note in summary.reviewer_notes:
        print(f"- {note}")
    return 0


def _print_path_group(label: str, group: PathGroup, *, indent: str = "") -> None:
    print(f"{indent}{label}: total={group.total}")
    for path in group.added:
        print(f"{indent}- added: {path}")
    for path in group.changed:
        print(f"{indent}- changed: {path}")
    for item in group.renamed:
        print(f"{indent}- renamed: {item['from']} -> {item['to']}")
    for path in group.deleted:
        print(f"{indent}- deleted: {path}")


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
        if issue.remediation_hint:
            print(f"  Hint: {issue.remediation_hint}")


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
        result = run_query(
            root,
            " ".join(args.question),
            tags=args.tags,
            source_id=args.source_id,
        )
    except (OSError, ValueError) as exc:
        return _print_error(exc)

    if not args.no_save:
        try:
            layout = resolve_layout(root, load_config(root))
            snapshot = QuerySnapshot(
                query=result.query,
                filters=QueryFilterSnapshot(
                    tags=result.filters.tags,
                    source_id=result.filters.source_id,
                    source_ids=result.filters.source_ids or [],
                ),
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
            "filters": {
                "tags": result.filters.tags,
                "source_id": result.filters.source_id,
                "source_ids": result.filters.source_ids or [],
            },
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
    if result.filters.active:
        print(
            "Filters: "
            f"tags={', '.join(result.filters.tags) if result.filters.tags else '-'} "
            f"source={result.filters.source_id or '-'}"
            + (
                f" resolved={', '.join(result.filters.source_ids)}"
                if result.filters.source_ids and len(result.filters.source_ids) > 1
                else ""
            )
        )
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
    if result.matches and not args.no_save:
        title = _suggested_answer_title(result.query)
        print(f"Next: splendor file-answer --from-last-query --title {shlex.quote(title)}")
    elif result.matches and args.no_save:
        print("Next: rerun without --no-save to enable file-answer")
    return 0


def handle_brief(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    goal = " ".join(args.goal).strip() or None
    try:
        result = build_project_brief(root, goal)
    except (OSError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        if args.agent_context:
            print(render_agent_context_json(result))
        else:
            print(render_project_brief_json(result))
        return 0

    if args.agent_context:
        _print_agent_context(result)
        return 0

    print("Project brief")
    print(f"Goal: {result.goal or '-'}")
    if result.query_summary is not None:
        print(f"Query: {result.query_summary}")
    print(
        "State: "
        f"sources={result.status.source_total} "
        f"pages={result.status.page_total} "
        f"queue={result.status.queue_total} "
        f"runs={result.status.run_total} "
        f"review_needed={result.status.review_needed_pages} "
        f"synthesis_followup={result.status.sources_missing_synthesis}"
    )
    if result.matches:
        print("Relevant records:")
        for match in result.matches:
            print(f"- {match.path} [{match.kind}] score={match.score}: {match.title}")
    if result.authority_briefs:
        print("Authority docs:")
        for item in result.authority_briefs:
            print(f"- {item.path} [{item.role}/{item.freshness}] score={item.score}: {item.title}")
    if result.planning_items:
        print("Active planning:")
        for item in result.planning_items:
            print(f"- {item.record_id} [{item.kind}/{item.status}] {item.title}")
    if result.recent_sources:
        print("Recent sources:")
        for source in result.recent_sources:
            print(
                f"- {source.source_ref} [{source.status}] {source.title} "
                f"source_id={source.source_id}"
            )
    if result.recent_runs:
        print("Recent runs:")
        for run in result.recent_runs:
            finished = run.finished_at or "-"
            print(f"- {run.run_id} {run.status} finished={finished}")
    if result.latest_reports:
        print("Latest maintenance:")
        for report in result.latest_reports:
            print(f"- {report.command}: {report.status} issues={report.issue_count}")
    if result.last_query is not None:
        print(f"Last query: {result.last_query.query} ({result.last_query.match_count} matches)")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            subject = warning.path or warning.area
            print(f"- {subject}: {warning.message}")
    print("Next actions:")
    for action in result.next_actions:
        print(f"- {action}")
    return 0


def _print_agent_context(result: ProjectBrief) -> None:
    print("Agent context")
    print(f"Goal: {result.goal or '-'}")
    if result.suggested_actions:
        print("Suggested next:")
        for action in result.suggested_actions[:5]:
            subject = _suggested_action_target(action)
            command = f" command={action.command}" if action.command else ""
            print(
                f"- [{action.priority}/{action.category}] {action.title} target={subject}{command}"
            )
    print(
        "Wiki status: "
        f"sources={result.status.source_total} "
        f"pages={result.status.page_total} "
        f"queue_pending={result.status.queue_status_counts.get('pending', 0)} "
        f"review_needed={result.status.review_needed_pages}"
    )
    if result.matches:
        print("Relevant matches:")
        for match in result.matches:
            source_refs = ", ".join(match.source_refs) if match.source_refs else "-"
            print(f"- {match.path} [{match.kind}] score={match.score} sources={source_refs}")
            if match.snippet:
                print(f"  {match.snippet}")
    if result.authority_briefs:
        print("Authority docs:")
        for item in result.authority_briefs[:5]:
            print(f"- {item.path} [{item.role}/{item.freshness}] score={item.score} {item.title}")
    if result.planning_items:
        print("Active planning:")
        for item in result.planning_items:
            print(f"- {item.record_id} [{item.kind}/{item.status}] {item.title}")
    if result.recent_sources:
        print("Recent sources:")
        for source in result.recent_sources:
            print(
                f"- {source.source_ref} [{source.status}/{source.review_state}] "
                f"{source.title} source_id={source.source_id}"
            )
    if result.recent_runs:
        print("Recent runs:")
        for run in result.recent_runs:
            finished = run.finished_at or "-"
            print(f"- {run.run_id} {run.status} finished={finished}")
    if result.last_query is not None:
        print(f"Last query: {result.last_query.query} ({result.last_query.match_count} matches)")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            subject = warning.path or warning.area
            print(f"- {subject}: {warning.message}")
    print("Next actions:")
    for action in result.next_actions:
        print(f"- {action}")


def handle_suggest_next(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    goal = " ".join(args.goal).strip() or None
    try:
        result = build_suggest_next(root, goal)
    except (OSError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_suggest_next_json(result))
        return 0

    print("Suggested next actions")
    print(f"Goal: {result.goal or '-'}")
    print(
        "State: "
        f"changed_sources={result.freshness.changed} "
        f"missing_sources={result.freshness.missing} "
        f"queue={result.queue.total} "
        f"review_needed={result.status.review_needed_pages} "
        f"contested={result.status.contested_pages} "
        f"stale={result.status.stale_pages}"
    )
    for action in result.actions:
        target = _suggested_action_target(action)
        command = f" command={action.command}" if action.command else ""
        print(
            f"{action.rank}. [{action.priority}/{action.category}] {action.title} "
            f"target={target}{command}"
        )
        print(f"   Reason: {action.reason}")
    return 0


def _suggested_action_target(action) -> str:
    return action.source_ref or action.path or action.record_id or "-"


def handle_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from splendor.web import create_app

    root = args.root.resolve()
    app = create_app(root)
    print(f"Serving Splendor at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def handle_repo_scan(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        if args.apply:
            result = apply_repo_scan(
                root,
                class_filters=args.class_filters,
                all_classes=args.all_classes,
                allow_large_apply=args.allow_large_apply,
            )
        else:
            result = scan_repo(
                root,
                class_filters=args.class_filters,
                all_classes=args.all_classes,
            )
        if args.report:
            result = write_repo_scan_report(result, args.report.resolve())
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_repo_scan_json(result))
        return 0

    print(
        f"Repo scan summary ({result.mode}): "
        f"scanned={result.scanned} "
        f"candidates={result.candidates} "
        f"registered={result.registered} "
        f"already_registered={result.already_registered} "
        f"unsupported={result.unsupported} "
        f"ignored={result.ignored}"
    )
    print("Class filters: " + ", ".join(result.class_filters))
    print(
        "Class counts: "
        + " ".join(f"{name}={count}" for name, count in result.class_counts.items())
    )
    if result.report_path:
        print(f"Report written: {result.report_path}")
    if result.mode == "preview":
        print(
            "Preview only: no source manifests, wiki pages, derived artifacts, "
            "queues, or runs written."
        )
        if result.candidate_sources:
            class_flags = (
                "--all"
                if args.all_classes
                else " ".join(f"--class {name}" for name in result.class_filters)
            )
            print(f"Apply explicitly: splendor repo scan --apply {class_flags}".rstrip())
    if result.candidate_sources:
        print("Candidate sources:")
        for item in result.candidate_sources:
            labels = ", ".join(item.source_labels) if item.source_labels else "-"
            curated = item.source_id if item.source_id else "-"
            print(
                f"- {item.path}: {item.status} "
                f"(class={item.source_class} labels={labels} source_id={curated})"
            )
    if result.touched_sources:
        print("Touched sources:")
        for item in result.touched_sources:
            labels = ", ".join(item.source_labels) if item.source_labels else "-"
            print(
                f"- {item.path}: {item.status} "
                f"(source_id={item.source_id} class={item.source_class} labels={labels})"
            )
    return 0


def handle_repo_refresh(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = refresh_repo(
            root,
            apply_scan=args.apply_scan,
            class_filters=args.class_filters,
            all_classes=args.all_classes,
            allow_large_apply=args.allow_large_apply,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _print_error(exc)

    if args.json_output:
        print(render_repo_refresh_json(result))
        return 0

    print(
        "Repo refresh summary: "
        f"scanned={result.scan.scanned} "
        f"registered={result.scan.registered} "
        f"already_registered={result.scan.already_registered} "
        f"unsupported={result.scan.unsupported} "
        f"ignored={result.scan.ignored}"
    )
    print("Generated pages:")
    for page_ref in result.generated_page_refs:
        print(f"- {page_ref}")
    print(f"Linked sources: {len(result.linked_source_ids)}")
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
    print(f"Next: review {result.page_path}")
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
    if args.command == "ingest":
        mode_count = sum(bool(value) for value in [args.source_id, args.pending, args.changed])
        if mode_count != 1:
            parser.error("ingest requires exactly one of <source_id>, --pending, or --changed")
        if args.json_output and not args.changed:
            parser.error("ingest --json is currently supported only with --changed")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
