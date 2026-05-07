"""Small git helpers for provenance capture."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from os import PathLike
from pathlib import Path
from shutil import which


def git_executable() -> str | None:
    """Return a PATH-resolved git executable, ignoring unsafe PATH entries."""

    return which("git")


def git_command(*args: str | PathLike[str]) -> list[str] | None:
    executable = git_executable()
    if executable is None:
        return None
    return [executable, *(str(arg) for arg in args)]


def run_git(
    root: Path,
    args: Iterable[str | PathLike[str]],
    *,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    args_list = list(args)
    fallback_command = ["git", *(str(arg) for arg in args_list)]
    command = git_command(*args_list)
    if command is None:
        return subprocess.CompletedProcess(
            fallback_command,
            returncode=127,
            stdout="",
            stderr="git executable not found",
        )
    try:
        return subprocess.run(
            command,
            cwd=root,
            input=input,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(
            fallback_command,
            returncode=127,
            stdout="",
            stderr=str(exc),
        )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_git(root, args)


def captured_source_commit(root: Path, source_path: Path) -> str | None:
    """Return HEAD SHA for a clean tracked file, else ``None``."""

    source_rel: str
    try:
        source_rel = source_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None

    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None

    head = _git(root, "rev-parse", "HEAD")
    if head.returncode != 0:
        return None
    head_sha = head.stdout.strip()
    if not head_sha:
        return None

    tracked = _git(root, "ls-files", "--error-unmatch", "--", source_rel)
    if tracked.returncode != 0:
        return None

    status = _git(root, "status", "--porcelain", "--", source_rel)
    if status.returncode != 0 or status.stdout.strip():
        return None

    return head_sha
