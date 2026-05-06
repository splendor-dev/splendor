# v0.3.0 Recovery Evaluation Release Notes

`v0.3.0` is the recovery evaluation release for sending Splendor back through the
SynthBanshee/Claude Code workflow after the `v0.2.0` trial. It is still not the public v1 tag. The
purpose is to validate that the concrete v0.2 blocker set has been addressed in a real agent
workflow.

## Release Purpose

This release packages the v0.3 source-hygiene, registry-recovery, validation-correctness, and
public-readiness work:

- repo scans honor `.gitignore`, `.splendorignore`, built-in ignores, class filters, `--all`, and
  explicit apply paths
- polluted source registries can be cleaned with `splendor source forget` instead of manual
  manifest deletion
- duplicate active canonical source refs can be reconciled with `splendor source reconcile`
- lint and health diagnostics use the live source model after refresh, path repair, and
  supersession repair
- workspace maintenance actions can run independently or as part of changed-source refresh
- pending ingest drains and queue state expose JSON output for agent handoff
- GitHub Release wheels are the canonical external trial-install artifact
- public mock-client acceptance fixtures cover source refresh, polluted-registry recovery,
  renamed-source repair, authority ranking, and contradiction-review task noise
- `brief --agent-context` and `suggest-next` rank current authority, accepted decisions, and active
  human-authored planning above stale, token-similar, superseded, archived, or generated-review
  noise

## Trial Focus

The next expected action after publishing `v0.3.0` is a fresh SynthBanshee/Claude Code retry. The
trial should explicitly re-check the issue set that came out of the `v0.2.0` evaluation:

- #111 repo-scan hygiene
- #109 source-registry cleanup
- #110 duplicate canonical source reconciliation
- #112 health false positives
- #113 live-path lint checks
- #121 workspace maintenance flag coupling
- #122 JSON pending-ingest output
- #120 release artifact install path
- #114 public mock-client acceptance coverage
- #116 planning authority lifecycle
- #115 deterministic agent-handoff ranking
- #117 contradiction-review task noise

## Validation Expectations

Before tagging `v0.3.0` after this preparation PR merges, run the full local validation suite from
the repository root and confirm green `main` CI:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run splendor lint
uv run splendor health
uv build
```

The package metadata for this preparation PR is `0.3.0` in both `pyproject.toml` and
`src/splendor/__init__.py`. Create the `v0.3.0` tag only after the release-prep PR merges and
`main` is green.
