# v0.4.0 Work-First Agent Handoff Release Notes

`v0.4.0` is the external retry release for validating Splendor as a practical Codex companion
after the `v0.3.0` SynthBanshee and hocrgen trials. It is still not the public v1 tag. The purpose
is to check whether agents now start with Splendor's local handoff surfaces before falling back to
manual `git`, GitHub, and file inspection.

## Release Purpose

This release packages the v0.4 work-first handoff and pre-v1 workflow durability work:

- `brief --agent-context` and `suggest-next` include git-aware work context from recent local commits
  and promoted GitHub work threads.
- Work items stay separated from maintenance state so stale generated or queue state does not
  displace current implementation work.
- Conventional planning, policy, and handoff files can appear as labeled inferred-authority context
  without mutating source registries.
- Maintenance guidance now points to explicit commands for wiki review state, source freshness,
  generated review tasks, and queue cleanup without making those items the default top work.
- `pr-summary --since <ref>` provides compact committed-state reviewability for Splendor-generated
  and maintained artifacts before PR handoff.
- Reviewed mutating commands expose deterministic JSON mutation contracts with `mode`, `mutates`,
  `planned`, and `written` fields.
- `splendor queue clean` with one of `--orphaned`, `--superseded`, or `--completed` gives stale
  ingest queue records an explicit preview/apply closure path.

## Trial Focus

The next expected action after publishing `v0.4.0` is a fresh external retry against the accepted
v0.4 bar in `docs/evaluations/v0_4_external_retry_bar.md`. The trial should explicitly check:

- whether agents naturally start with `splendor brief --agent-context` and `splendor suggest-next`
  before manual repo spelunking
- whether current work stays ranked above stale generated review tasks, source freshness, and queue
  cleanup
- whether compact PR summaries are useful before handoff
- whether preview/apply and JSON mutation contracts are clear enough for agent-safe operation
- whether queue and registry maintenance now have deterministic closure paths

## Validation Expectations

Before tagging `v0.4.0` after this preparation PR merges, run the full local validation suite from
the repository root and confirm green `main` CI:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run splendor lint
uv run splendor health
uv build
```

The package metadata for this preparation PR is `0.4.0` in both `pyproject.toml` and
`src/splendor/__init__.py`. Create the `v0.4.0` tag only after the release-prep PR merges and
`main` is green.
