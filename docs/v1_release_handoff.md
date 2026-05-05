# v1 Release Handoff

This checklist is the release handoff for `M13-P3.2`. It does not add runtime behavior. It records
the final v1 verification path, issue state, GitHub metadata expectations, known non-blockers, and
post-v1 queue after the `M13-P2` redesign and `M13-P3.1` release-hardening audit.

## v0.2.0 Evaluation Release Note

The immediate tag target after the post-M15 issue-disposition pass is `v0.2.0`, not `v1.0.0`.
This document remains the historical v1-style handoff and validation checklist, but the current
release-prep PR uses it only to avoid stale release-state claims. The `v0.2.0` tag should be
created only after the release-prep PR merges, `main` is green, and the version metadata plus
`docs/v0_2_0_release_notes.md` are present on `main`.

## Release Validation

Run these commands from the repository root before tagging or publishing the `v0.2.0` evaluation
release:

```bash
env -u OPENAI_API_KEY uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run splendor lint
uv run splendor health
uv build
```

The pytest command intentionally unsets `OPENAI_API_KEY` so release validation uses the
deterministic offline path instead of attempting live contradiction-review calls when local
credentials are configured.

For a CI-equivalent test job with coverage, also use the deterministic offline path:

```bash
env -u OPENAI_API_KEY uv run pytest --cov=splendor --cov-report=term-missing --cov-report=xml
```

Before publishing release notes, verify that:

- the `README.md` "What Comes Next" block, `.agent-plan.md`, and
  `docs/splendor_mvp_to_v1_roadmap.md` planning-state lines match
- `docs/splendor_product_spec.md` acceptance criteria still match shipped behavior
- `docs/schema_contracts.md` still names schema version `1` and legacy manifest compatibility
- `docs/quickstart.md` demonstrates the current safe source workflow
- `docs/ci_and_repo_automation.md` and `docs/github_automation_architecture.md` still describe
  GitHub automation as optional around the local CLI

## GitHub Handoff

Release PRs should be non-draft and should carry:

- a detailed body covering changes, validation, limitations, and follow-up work
- focused labels such as `type/docs`, `area/docs`, `area/planning`, and `release/post-mvp`
- the most relevant milestone when one exists; this `v0.2.0` release-prep PR has no issue-backed
  milestone unless maintainers create a dedicated evaluation-release milestone
- explicit issue linkage for issues that are closed or intentionally kept open

For the current `v0.2.0` evaluation-release handoff:

- GitHub has no open issues as of the release-prep handoff.
- #70 remains the completed parent feedback loop for the `M13-P2` redesign.
- #72, #86, #94, #47, #30, #37, and #79 are closed or dispositioned by merged M14/M15 follow-ups.
- #79's reviewed compile/update scope is represented by `M15-P1.1`, `M15-P1.2`, and the
  `M15-P1.3` disposition: one-page proposal diffs, proposal hashes, explicit apply semantics,
  ranked compile-target suggestions, schema-bound frontmatter validation, and generated/maintained
  page separation.
- No new issue-backed implementation slice is required before the `v0.2.0` tag unless the
  release-prep validation suite finds a concrete blocker.

## Known Non-Blockers

These items are intentionally not `v0.2.0` release blockers:

- richer post-M14 authority lifecycle policy after the initial planning-doc authority briefs have
  been exercised in real repositories
- historical ingest run records may still show zero duration because `M10-P3.1` does not rewrite
  old runtime ledger entries
- source identity extensions beyond curated workspace-backed source lifecycle semantics, if real
  repository use identifies a concrete remaining gap after #94
- repo-scan and web-listing work beyond the closed #30 and #37 follow-ups, if renewed evaluation
  identifies a concrete scaling gap

## Post-v1 Queue

The historical post-v1 queue recorded by `M13-P3.2` has now been worked down through the M14 and
M15 follow-ups. The current queue before tagging `v0.2.0` is release validation only: confirm local
tests, formatting, lint, Splendor lint/health, build output, green `main` CI, package metadata
`0.2.0`, release notes, and no open GitHub issues. After `v0.2.0` is released, the next product
step is sending Splendor back to evaluation by the Claude Code agent user developing
SynthBanshee.

The internal source-lifecycle re-evaluation gate is now complete in `M14-P3.1`. The completed retry
bundle is:

1. `M14-P0.1` Split #72 into child issues and assign release metadata.
2. `M14-P1.1` Stable logical source identities above content-addressed source IDs.
3. `M14-P1.2` Supersession-aware source refresh, so changed files do not leave stale runs or
   health failures for agents to clean manually.
4. `M14-P1.3` Safe workspace refresh path covering changed-source detection, refresh, ingest,
   index rebuild, and a health-clean end state.
5. `M14-P1.4` Superseded generated-state pruning and topic-ref migration.
6. `M14-P2.1` PR summary and lower-noise generated-state review handoff, including
   `splendor pr-summary --since main`.
7. `M14-P3.1` Re-evaluate the comparable source-lifecycle workflow against the current command set,
   including a controlled changed-source exercise, and record the close-or-split recommendation for
   #72.

The retry result is captured in `docs/m14_synthbanshee_reevaluation.md`. The subsequent
`M14-P4.1`, `M15-P1.1`, `M15-P1.2`, and `M15-P1.3` work is also complete: planning-authority
briefs landed, the reviewed one-page compile/apply loop landed, compile-target discovery landed,
and #79 was dispositioned. Future work should now come from the post-`v0.2.0`
SynthBanshee/Claude Code evaluation rather than from the closed historical issue queue.

## Tagging Readiness

After the release-prep PR merges, `v0.2.0` tagging is ready when `main` has:

- package version metadata updated to `0.2.0` in both `pyproject.toml` and
  `src/splendor/__init__.py`
- `docs/v0_2_0_release_notes.md` or a GitHub release draft that names completed stabilization,
  validation, current no-open-issues state, and the post-release SynthBanshee/Claude Code
  evaluation step
- green CI for formatting, linting, tests, and coverage
- a passing `splendor lint` planning-state check
- no open GitHub issues unless a newly found release blocker has been deliberately filed

Use this final tagging sequence after those checks pass:

```bash
git switch main
git pull --ff-only origin main
uv build
uv pip install dist/splendor-*.whl
splendor --version
git tag -a v0.2.0 -m "Splendor v0.2.0"
git push origin v0.2.0
```

The build and wheel smoke test must pass before the tag is pushed. If either fails, fix the release
prep on a PR branch instead of publishing and then repairing a bad tag.
