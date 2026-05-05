# Release Artifacts

This document defines the supported release artifact path for trial installs. It keeps release
publishing separate from Splendor runtime behavior.

## Canonical Trial Install

For external v0.3 trial users, prefer the wheel attached to the matching GitHub Release. Start from
the release page so the evaluator sees the release notes, validation status, and known limitations
before installing:

```text
https://github.com/splendor-dev/splendor/releases/tag/<release-tag>
```

Then install the wheel asset for that release:

```bash
TAG="v..."
VERSION="${TAG#v}"
uv tool install "https://github.com/splendor-dev/splendor/releases/download/${TAG}/splendor-${VERSION}-py3-none-any.whl"
splendor --help
```

If the evaluator wants Splendor inside a project-specific virtual environment instead:

```bash
TAG="v..."
VERSION="${TAG#v}"
uv venv .venv
. .venv/bin/activate
uv pip install "https://github.com/splendor-dev/splendor/releases/download/${TAG}/splendor-${VERSION}-py3-none-any.whl"
splendor --help
```

Set `TAG` to the exact published release under evaluation. If the wheel asset name differs, copy
the wheel URL from the GitHub Release page instead of guessing the filename.

## Maintainer Publishing Flow

`.github/workflows/release-artifacts.yml` publishes release artifacts when a `v*` tag is pushed.
Maintainers can also run it manually for an existing tag through `workflow_dispatch`.

The workflow:

- checks out the tag
- verifies that the tag version matches `pyproject.toml` and `src/splendor/__init__.py`
- runs `uv build`
- smoke-installs the built wheel, runs `splendor --version`, `splendor --help`, `splendor init`,
  and `splendor lint` in an isolated workspace
- uploads `dist/*` as a workflow artifact
- requires the matching GitHub Release to already exist with release notes
- uploads the wheel and source distribution to that release

This makes GitHub Releases the canonical trial-install channel while leaving PyPI publishing as a
separate maintainer decision.
