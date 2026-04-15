"""Small git helpers for provenance capture."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


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
