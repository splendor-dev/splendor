"""Implementation for `splendor repo scan`."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from pathlib import Path

from splendor.config import SplendorConfig, load_config
from splendor.ingest_dispatch import IMAGE_SOURCE_TYPES, SUPPORTED_SOURCE_TYPES
from splendor.layout import ResolvedLayout, resolve_layout
from splendor.schemas.types import SourceClass
from splendor.state.source_registry import (
    SourceRegistrationContext,
    load_source_record,
    register_source,
)
from splendor.utils.hashing import sha256_file

_CONFIG_EXTENSIONS = {"json", "yaml", "yml"}
_DOCUMENTATION_EXTENSIONS = {"md", "pdf", "txt"}
_CODE_EXTENSIONS = (
    SUPPORTED_SOURCE_TYPES - _CONFIG_EXTENSIONS - _DOCUMENTATION_EXTENSIONS - IMAGE_SOURCE_TYPES
)
_IGNORED_DIR_NAMES = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "generated",
    "node_modules",
}
_SOURCE_CLASSES: tuple[SourceClass, ...] = ("code", "documentation", "configuration", "other")
LARGE_APPLY_CANDIDATE_LIMIT = 200


@dataclass(frozen=True)
class CuratedSourceInfo:
    source_id: str
    title: str
    checksum: str
    added_at: str


@dataclass(frozen=True)
class RepoScanCandidate:
    path: str
    source_class: SourceClass
    source_labels: list[str]
    already_curated: bool
    source_id: str | None = None
    title: str | None = None
    status: str = "candidate"


@dataclass(frozen=True)
class RepoScanIgnoredPath:
    path: str
    reason: str
    source_class: SourceClass | None = None
    source_labels: list[str] | None = None


@dataclass(frozen=True)
class GitIgnoreContext:
    repo_root: Path | None
    workspace_root: Path


@dataclass(frozen=True)
class RepoScanItem:
    path: str
    source_id: str
    source_class: SourceClass
    source_labels: list[str]
    status: str


@dataclass(frozen=True)
class RepoScanResult:
    mode: str
    scanned: int
    candidates: int
    registered: int
    already_registered: int
    unsupported: int
    ignored: int
    class_counts: dict[str, int]
    class_filters: list[SourceClass]
    include_patterns: list[str]
    exclude_patterns: list[str]
    candidate_sources: list[RepoScanCandidate]
    ignored_paths: list[RepoScanIgnoredPath]
    touched_sources: list[RepoScanItem]
    report_path: str | None = None


def scan_repo(
    root: Path,
    *,
    class_filters: list[SourceClass] | None = None,
    all_classes: bool = False,
) -> RepoScanResult:
    config = load_config(root)
    layout = resolve_layout(root, config)
    return _scan_repo_with_context(
        root,
        config=config,
        layout=layout,
        class_filters=class_filters,
        all_classes=all_classes,
    )


def _scan_repo_with_context(
    root: Path,
    *,
    config: SplendorConfig,
    layout: ResolvedLayout,
    class_filters: list[SourceClass] | None = None,
    all_classes: bool = False,
) -> RepoScanResult:
    selected_classes = _selected_classes(
        configured_default_classes=config.sources.repo_scan_default_classes,
        class_filters=class_filters,
        all_classes=all_classes,
    )
    include_patterns = list(config.sources.include_patterns)
    exclude_patterns = list(config.sources.exclude_patterns)
    curated_sources = _workspace_curated_sources(root, layout)

    supported_paths, ignored_paths, unsupported = _discover_supported_paths(root, layout)
    ignored_by_path = {item.path: item for item in ignored_paths}
    candidate_sources: list[RepoScanCandidate] = []
    class_counts = {name: 0 for name in _SOURCE_CLASSES}

    for path in supported_paths:
        relative_path = path.relative_to(root).as_posix()
        source_class = _classify_path(path, relative_path)
        source_labels = _labels_for(relative_path)
        if not _matches_include_patterns(relative_path, include_patterns):
            ignored_by_path[relative_path] = RepoScanIgnoredPath(
                path=relative_path,
                reason="include_patterns",
                source_class=source_class,
                source_labels=source_labels,
            )
            continue
        if _matches_any_pattern(relative_path, exclude_patterns):
            ignored_by_path[relative_path] = RepoScanIgnoredPath(
                path=relative_path,
                reason="exclude_patterns",
                source_class=source_class,
                source_labels=source_labels,
            )
            continue
        if source_class not in selected_classes:
            ignored_by_path[relative_path] = RepoScanIgnoredPath(
                path=relative_path,
                reason="class_filter",
                source_class=source_class,
                source_labels=source_labels,
            )
            continue

        curated_for_path = curated_sources.get(relative_path, [])
        current_curated = None
        if curated_for_path:
            current_checksum = sha256_file(path)
            current_curated = next(
                (source for source in curated_for_path if source.checksum == current_checksum),
                None,
            )
        previous_curated = _latest_curated_source(curated_for_path)
        status = (
            "already_curated"
            if current_curated is not None
            else "new_version_candidate"
            if previous_curated is not None
            else "candidate"
        )
        class_counts[source_class] += 1
        candidate_sources.append(
            RepoScanCandidate(
                path=relative_path,
                source_class=source_class,
                source_labels=source_labels,
                already_curated=current_curated is not None,
                source_id=(
                    current_curated.source_id
                    if current_curated is not None
                    else previous_curated.source_id
                    if previous_curated is not None
                    else None
                ),
                title=(
                    current_curated.title
                    if current_curated is not None
                    else previous_curated.title
                    if previous_curated is not None
                    else None
                ),
                status=status,
            )
        )

    return RepoScanResult(
        mode="preview",
        scanned=len(supported_paths),
        candidates=len(candidate_sources),
        registered=0,
        already_registered=sum(1 for candidate in candidate_sources if candidate.already_curated),
        unsupported=unsupported,
        ignored=len(ignored_by_path),
        class_counts=class_counts,
        class_filters=list(selected_classes),
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        candidate_sources=candidate_sources,
        ignored_paths=[ignored_by_path[key] for key in sorted(ignored_by_path)],
        touched_sources=[],
    )


def apply_repo_scan(
    root: Path,
    *,
    class_filters: list[SourceClass] | None = None,
    all_classes: bool = False,
    allow_large_apply: bool = False,
) -> RepoScanResult:
    if not class_filters and not all_classes:
        msg = "repo scan --apply requires at least one --class filter or --all"
        raise ValueError(msg)
    config = load_config(root)
    layout = resolve_layout(root, config)
    registration_context = SourceRegistrationContext(config=config, layout=layout)
    preview = _scan_repo_with_context(
        root,
        config=config,
        layout=layout,
        class_filters=class_filters,
        all_classes=all_classes,
    )
    if preview.candidates > LARGE_APPLY_CANDIDATE_LIMIT and not allow_large_apply:
        msg = (
            "repo scan --apply refused "
            f"{preview.candidates} candidates; rerun with --allow-large-apply after reviewing "
            "the preview/report"
        )
        raise RuntimeError(msg)

    registered = 0
    already_registered = 0
    touched_sources: list[RepoScanItem] = []
    for candidate in preview.candidate_sources:
        registered_source = register_source(
            root,
            root / candidate.path,
            source_class=candidate.source_class,
            source_labels=candidate.source_labels,
            discovered_by="repo_scan",
            refresh_existing_metadata=True,
            context=registration_context,
        )
        status = "already_registered" if registered_source.already_registered else "registered"
        if registered_source.already_registered:
            already_registered += 1
        else:
            registered += 1
        touched_sources.append(
            RepoScanItem(
                path=candidate.path,
                source_id=registered_source.record.source_id,
                source_class=candidate.source_class,
                source_labels=candidate.source_labels,
                status=status,
            )
        )

    return RepoScanResult(
        mode="apply",
        scanned=preview.scanned,
        candidates=preview.candidates,
        registered=registered,
        already_registered=already_registered,
        unsupported=preview.unsupported,
        ignored=preview.ignored,
        class_counts=preview.class_counts,
        class_filters=preview.class_filters,
        include_patterns=preview.include_patterns,
        exclude_patterns=preview.exclude_patterns,
        candidate_sources=preview.candidate_sources,
        ignored_paths=preview.ignored_paths,
        touched_sources=touched_sources,
    )


def write_repo_scan_report(result: RepoScanResult, report_path: Path) -> RepoScanResult:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_repo_scan_json(result) + "\n", encoding="utf-8")
    return replace(result, report_path=report_path.as_posix())


def render_repo_scan_json(result: RepoScanResult) -> str:
    payload = {
        "mode": result.mode,
        "scanned": result.scanned,
        "candidates": result.candidates,
        "registered": result.registered,
        "already_registered": result.already_registered,
        "unsupported": result.unsupported,
        "ignored": result.ignored,
        "class_counts": result.class_counts,
        "class_filters": result.class_filters,
        "include_patterns": result.include_patterns,
        "exclude_patterns": result.exclude_patterns,
        "report_path": result.report_path,
        "candidate_sources": [
            {
                "path": item.path,
                "source_class": item.source_class,
                "source_labels": item.source_labels,
                "already_curated": item.already_curated,
                "source_id": item.source_id,
                "title": item.title,
                "status": item.status,
            }
            for item in result.candidate_sources
        ],
        "ignored_paths": [
            {
                "path": item.path,
                "reason": item.reason,
                "source_class": item.source_class,
                "source_labels": item.source_labels or [],
            }
            for item in result.ignored_paths
        ],
        "touched_sources": [
            {
                "path": item.path,
                "source_id": item.source_id,
                "source_class": item.source_class,
                "source_labels": item.source_labels,
                "status": item.status,
            }
            for item in result.touched_sources
        ],
    }
    return json.dumps(payload, indent=2)


def _selected_classes(
    *,
    configured_default_classes: list[SourceClass],
    class_filters: list[SourceClass] | None,
    all_classes: bool,
) -> tuple[SourceClass, ...]:
    if all_classes:
        return _SOURCE_CLASSES
    if class_filters:
        return tuple(dict.fromkeys(class_filters))
    if configured_default_classes:
        return tuple(dict.fromkeys(configured_default_classes))
    return ("documentation",)


def _discover_supported_paths(
    root: Path, layout: ResolvedLayout
) -> tuple[list[Path], list[RepoScanIgnoredPath], int]:
    walked_files: list[Path] = []
    ignored_paths_by_path: dict[str, RepoScanIgnoredPath] = {}
    unsupported = 0
    gitignore = _git_ignore_context(root)

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        filtered_dirnames = []
        gitignore_dir_candidates: dict[str, str] = {}
        for dirname in sorted(dirnames):
            path = current_dir / dirname
            reason = _ignored_dir_reason(path, root, layout)
            if reason is not None:
                continue
            repo_relative = _repo_relative_path(path, gitignore, is_dir=True)
            if repo_relative is not None:
                gitignore_dir_candidates[repo_relative] = dirname
            filtered_dirnames.append(dirname)
        gitignored_dirs = _git_ignored_repo_paths(gitignore_dir_candidates, gitignore)
        if gitignored_dirs:
            filtered_dirnames = [
                dirname
                for dirname in filtered_dirnames
                if dirname
                not in {gitignore_dir_candidates[repo_path] for repo_path in gitignored_dirs}
            ]
        dirnames[:] = filtered_dirnames
        for filename in sorted(filenames):
            path = current_dir / filename
            relative_path = path.relative_to(root).as_posix()
            reason = _ignored_path_reason(path, root, layout)
            if reason is not None:
                ignored_paths_by_path[relative_path] = RepoScanIgnoredPath(
                    path=relative_path,
                    reason=reason,
                )
                continue
            walked_files.append(path)

    gitignored = _git_ignored_paths(root, walked_files, gitignore)
    supported_paths: list[Path] = []
    for path in walked_files:
        relative_path = path.relative_to(root).as_posix()
        if relative_path in gitignored:
            ignored_paths_by_path[relative_path] = RepoScanIgnoredPath(
                path=relative_path,
                reason="gitignore",
            )
            continue
        if path.suffix.lstrip(".") not in SUPPORTED_SOURCE_TYPES:
            unsupported += 1
            continue
        supported_paths.append(path)

    return (
        supported_paths,
        [ignored_paths_by_path[key] for key in sorted(ignored_paths_by_path)],
        unsupported,
    )


def _workspace_curated_sources(
    root: Path, layout: ResolvedLayout
) -> dict[str, list[CuratedSourceInfo]]:
    curated: dict[str, list[CuratedSourceInfo]] = {}
    for manifest_path in sorted(layout.source_records_dir.glob("*.json")):
        record = load_source_record(manifest_path)
        if record.source_ref_kind != "workspace_path":
            continue
        curated.setdefault(record.source_ref, []).append(
            CuratedSourceInfo(
                source_id=record.source_id,
                title=record.title,
                checksum=record.checksum,
                added_at=record.added_at,
            )
        )
    return curated


def _ignored_path_reason(path: Path, root: Path, layout: ResolvedLayout) -> str | None:
    relative = path.relative_to(root)
    if not relative.parts:
        return None
    if _is_managed_layout_path(relative, root, layout) or _has_ignored_dir_name(
        relative.parts, is_dir=False
    ):
        return "managed_or_transient"
    return None


def _ignored_dir_reason(path: Path, root: Path, layout: ResolvedLayout) -> str | None:
    relative = path.relative_to(root)
    if not relative.parts:
        return None
    if _is_managed_layout_path(relative, root, layout) or _has_ignored_dir_name(
        relative.parts, is_dir=True
    ):
        return "managed_or_transient"
    return None


def _is_managed_layout_path(relative: Path, root: Path, layout: ResolvedLayout) -> bool:
    return any(
        _parts_start_with(relative.parts, managed_parts)
        for managed_parts in _managed_layout_parts(root, layout)
    )


def _managed_layout_parts(root: Path, layout: ResolvedLayout) -> tuple[tuple[str, ...], ...]:
    managed_paths = (
        layout.raw_dir,
        layout.derived_dir,
        layout.state_dir,
        layout.reports_dir,
        layout.wiki_dir,
        layout.planning_dir,
    )
    return tuple(path.relative_to(root).parts for path in managed_paths)


def _parts_start_with(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(parts) >= len(prefix) and parts[: len(prefix)] == prefix


def _has_ignored_dir_name(parts: tuple[str, ...], *, is_dir: bool) -> bool:
    directory_parts = parts if is_dir else parts[:-1]
    return any(part in _IGNORED_DIR_NAMES for part in directory_parts)


def _git_ignore_context(root: Path) -> GitIgnoreContext:
    try:
        top_level = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return GitIgnoreContext(repo_root=None, workspace_root=root.resolve())
    if top_level.returncode != 0:
        return GitIgnoreContext(repo_root=None, workspace_root=root.resolve())
    return GitIgnoreContext(
        repo_root=Path(top_level.stdout.strip()).resolve(),
        workspace_root=root.resolve(),
    )


def _git_ignored_paths(root: Path, paths: list[Path], gitignore: GitIgnoreContext) -> set[str]:
    if not paths:
        return set()
    if gitignore.repo_root is None:
        return set()
    repo_paths_by_workspace_path: dict[str, str] = {}
    for path in paths:
        repo_relative = _repo_relative_path(path, gitignore)
        if repo_relative is None:
            continue
        repo_paths_by_workspace_path[repo_relative] = path.relative_to(root).as_posix()
    if not repo_paths_by_workspace_path:
        return set()

    ignored_repo_paths = _git_ignored_repo_paths(repo_paths_by_workspace_path, gitignore)
    return {
        workspace_relative
        for repo_relative, workspace_relative in repo_paths_by_workspace_path.items()
        if repo_relative in ignored_repo_paths
    }


def _git_ignored_repo_paths(
    repo_paths_by_value: dict[str, str], gitignore: GitIgnoreContext
) -> set[str]:
    if not repo_paths_by_value or gitignore.repo_root is None:
        return set()
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(gitignore.repo_root),
                "check-ignore",
                "--stdin",
            ],
            input="\n".join(repo_paths_by_value) + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return set()
    if result.returncode not in {0, 1}:
        return set()

    ignored: set[str] = set()
    normalized_repo_paths = {path.rstrip("/"): path for path in repo_paths_by_value}
    for line in result.stdout.splitlines():
        repo_relative = line.strip()
        if not repo_relative:
            continue
        original_repo_path = normalized_repo_paths.get(repo_relative.rstrip("/"))
        if original_repo_path is not None:
            ignored.add(original_repo_path)
    return ignored


def _repo_relative_path(
    path: Path, gitignore: GitIgnoreContext, *, is_dir: bool = False
) -> str | None:
    if gitignore.repo_root is None:
        return None
    try:
        repo_relative = path.resolve().relative_to(gitignore.repo_root).as_posix()
    except ValueError:
        return None
    if is_dir:
        repo_relative = f"{repo_relative.rstrip('/')}/"
    return repo_relative


def _matches_include_patterns(relative_path: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    return _matches_any_pattern(relative_path, patterns)


def _matches_any_pattern(relative_path: str, patterns: list[str]) -> bool:
    return any(_matches_pattern(relative_path, pattern) for pattern in patterns)


def _matches_pattern(relative_path: str, pattern: str) -> bool:
    normalized_pattern = _normalize_pattern(pattern)
    if not normalized_pattern:
        return False
    path_parts = tuple(part for part in relative_path.split("/") if part)
    pattern_parts = tuple(part for part in normalized_pattern.split("/") if part)
    if len(pattern_parts) == 1 and len(path_parts) != 1:
        return False
    return _match_path_parts(path_parts, pattern_parts)


def _normalize_pattern(pattern: str) -> str:
    normalized = pattern.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def _match_path_parts(path_parts: tuple[str, ...], pattern_parts: tuple[str, ...]) -> bool:
    if not pattern_parts:
        return not path_parts
    pattern_part, *remaining_pattern = pattern_parts
    remaining_pattern_parts = tuple(remaining_pattern)
    if pattern_part == "**":
        return any(
            _match_path_parts(path_parts[index:], remaining_pattern_parts)
            for index in range(len(path_parts) + 1)
        )
    if not path_parts:
        return False
    return fnmatchcase(path_parts[0], pattern_part) and _match_path_parts(
        path_parts[1:], remaining_pattern_parts
    )


def _latest_curated_source(sources: list[CuratedSourceInfo]) -> CuratedSourceInfo | None:
    if not sources:
        return None
    return max(sources, key=lambda source: (source.added_at, source.source_id))


def _classify_path(path: Path, relative_path: str) -> SourceClass:
    suffix = path.suffix.lstrip(".")
    if suffix in _DOCUMENTATION_EXTENSIONS:
        return "documentation"
    if suffix in _CONFIG_EXTENSIONS or relative_path.startswith(".github/workflows/"):
        return "configuration"
    if suffix in _CODE_EXTENSIONS:
        return "code"
    return "other"


def _labels_for(relative_path: str) -> list[str]:
    labels: list[str] = []
    name = Path(relative_path).name
    if relative_path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py"):
        labels.append("test")
    if relative_path.startswith("examples/"):
        labels.append("example")
    if relative_path.startswith(".github/workflows/"):
        labels.append("automation")
    if relative_path in {"AGENTS.md", "llms.txt"}:
        labels.append("agent-instructions")
    return labels
