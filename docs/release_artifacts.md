# Release Artifacts

This document defines the supported release artifact path for trial installs. It keeps release
publishing separate from Splendor runtime behavior.

## Canonical Trial Install

For external v0.3 trial users, prefer the wheel attached to the matching GitHub Release:

```bash
uv tool install https://github.com/splendor-dev/splendor/releases/download/v0.3.0/splendor-0.3.0-py3-none-any.whl
splendor --help
```

If the evaluator wants Splendor inside a project-specific virtual environment instead:

```bash
uv venv .venv
. .venv/bin/activate
uv pip install https://github.com/splendor-dev/splendor/releases/download/v0.3.0/splendor-0.3.0-py3-none-any.whl
splendor --help
```

Replace `v0.3.0` and `0.3.0` with the exact release tag being evaluated.

## Maintainer Publishing Flow

`.github/workflows/release-artifacts.yml` publishes release artifacts when a `v*` tag is pushed.
Maintainers can also run it manually for an existing tag through `workflow_dispatch`.

The workflow:

- checks out the tag
- verifies that the tag version matches `pyproject.toml` and `src/splendor/__init__.py`
- runs `uv build`
- smoke-installs the built wheel and runs `splendor --version`
- uploads `dist/*` as a workflow artifact
- creates or reuses the matching GitHub Release and uploads the wheel and source distribution

This makes GitHub Releases the canonical trial-install channel while leaving PyPI publishing as a
separate maintainer decision.
