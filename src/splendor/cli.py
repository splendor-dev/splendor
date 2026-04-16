"""CLI entrypoint for Splendor."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from splendor.commands.add_source import add_source
from splendor.commands.health import run_health
from splendor.commands.ingest import drain_pending_ingest_jobs, ingest_source
from splendor.commands.init import initialize_workspace
from splendor.commands.materialize_source import materialize_source
from splendor.schemas.types import STORAGE_MODES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="splendor", description="Splendor knowledge compiler CLI")
    parser.add_argument(
        "--root",
        default=Path.cwd(),
        type=Path,
        help="Repository root to operate on. Defaults to the current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a Splendor workspace")
    init_parser.set_defaults(handler=handle_init)

    add_source_parser = subparsers.add_parser("add-source", help="Register a new immutable source")
    add_source_parser.add_argument("path", type=Path, help="Path to the source file to register")
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
    materialize_parser.add_argument("source_id", help="Registered source identifier to materialize")
    materialize_parser.add_argument(
        "--storage-mode",
        choices=tuple(mode for mode in STORAGE_MODES if mode != "none"),
        help="Override the target storage mode for this materialization.",
    )
    materialize_parser.set_defaults(handler=handle_materialize_source)

    health_parser = subparsers.add_parser("health", help="Validate source storage state")
    health_parser.set_defaults(handler=handle_health)
    return parser


def handle_init(args: argparse.Namespace) -> int:
    result = initialize_workspace(args.root.resolve())
    print(f"Initialized Splendor workspace at {result.root}")
    print(f"Created directories: {len(result.created_directories)}")
    print(f"Created files: {len(result.created_files)}")
    return 0


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
        print(f"Error: {exc}")
        return 1
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
            print(f"Error: {exc}")
            return 1

        if not result.items:
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
        print(f"Error: {exc}")
        return 1

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
        print(f"Error: {exc}")
        return 1

    print(f"Materialized source {result.source_id}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Source ref: {result.source_ref}")
    print(f"Storage mode: {result.storage_mode}")
    print(f"Storage artifact: {result.stored_path}")
    return 0


def handle_health(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = run_health(root)
    except (ValueError, RuntimeError, OSError, yaml.YAMLError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Checked sources: {result.checked_sources}")
    if not result.issues:
        print("Health check passed")
        return 0

    print(f"Health check failed: {len(result.issues)} issue(s)")
    for issue in result.issues:
        print(f"- {issue.source_id}: {issue.message}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest" and bool(args.source_id) == bool(args.pending):
        parser.error("ingest requires exactly one of <source_id> or --pending")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
