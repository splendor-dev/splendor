"""CLI entrypoint for Splendor."""

from __future__ import annotations

import argparse
from pathlib import Path

from splendor.commands.add_source import add_source
from splendor.commands.ingest import ingest_source
from splendor.commands.init import initialize_workspace


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
    add_source_parser.set_defaults(handler=handle_add_source)

    ingest_parser = subparsers.add_parser("ingest", help="Ingest a registered source into the wiki")
    ingest_parser.add_argument("source_id", help="Registered source identifier to ingest")
    ingest_parser.set_defaults(handler=handle_ingest)
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
    result = add_source(root, source_path)
    action = "Already registered" if result.already_registered else "Registered"
    print(f"{action} source {result.source_id}")
    print(f"Manifest: {result.manifest_path}")
    print(f"Stored copy: {result.stored_path}")
    return 0


def handle_ingest(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        result = ingest_source(root, args.source_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    if result.no_op:
        print(f"Source {result.source_id} is already ingested for the current pipeline version")
        print(f"Page: {result.page_path}")
        return 0

    print(f"Ingested source {result.source_id}")
    print(f"Run: {result.run_id}")
    print(f"Page: {result.page_path}")
    print(f"Queue record: {result.queue_path}")
    print(f"Run record: {result.run_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
