# v1 Release Handoff

This checklist is the release handoff for `M13-P3.2`. It does not add runtime behavior. It records
the final v1 verification path, issue state, GitHub metadata expectations, known non-blockers, and
post-v1 queue after the `M13-P2` redesign and `M13-P3.1` release-hardening audit.

## Release Validation

Run these commands from the repository root before tagging or publishing a v1 release:

```bash
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run splendor lint
```

For a CI-equivalent test job with coverage:

```bash
uv run pytest --cov=splendor --cov-report=term-missing --cov-report=xml
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
- the `Milestone 13` milestone when it exists
- explicit issue linkage for issues that are closed or intentionally kept open

For this handoff:

- #70 is closed and should remain the completed parent feedback loop for the `M13-P2` redesign
- #72 remains open as the parent source-refresh lifecycle and agent-workflow feedback loop
- #41-#46 are closed as completed v1 dogfood issues after closing comments named the shipped scope
  and any deferred work; #79 tracks the deferred mutating compile/update path from #41
- #47 remains open as the real ingest run-duration bug
- #30 remains open as post-v1 repo-scan registration performance work
- #37 remains open as post-v1 web document-list scaling work
- #72 is unblocked after `M14-P2.1`; the `M14-P3.1` source-lifecycle re-evaluation gate records
  that the source-refresh lifecycle pain is materially addressed and recommends closing #72 once
  maintainers accept the gate result
- #86 tracks the planning-document authority and task-oriented agent brief gap addressed by
  `M14-P4.1`
- #79 now owns the M15 reviewed compile/update sequence; `M15-P1.1` starts with explicit
  one-page diff/proposal-hash/apply semantics rather than broad automatic synthesis updates

## Known Non-Blockers

These items are intentionally not v1 release blockers:

- richer post-M14 authority lifecycle policy after the initial planning-doc authority briefs have
  been exercised in real repositories
- ingest run-duration precision for #47
- health remediation hints after source path repair commands exist
- repo-scan bulk registration optimization for #30
- web document-list scaling for #37

## Post-v1 Queue

The conservative next queue after the `M14-P3.1` gate is:

1. Close #72 once maintainers accept the gate PR, because its broad source-refresh lifecycle and PR
   handoff asks have landed and been re-evaluated.
2. Review #86 through `M14-P4.1`, which adds initial planning-document authority metadata and
   task-oriented authority brief ranking.
3. Keep using `splendor pr-summary --since main` during review handoff to explain source
   lifecycle, maintained wiki, source-summary, and mechanical generated-state changes.
4. Use `M14-P1.5` for issue #93 before continuing post-MVP expansion: add an explicit
   `splendor ingest --changed` path for checksum-drifted curated sources whose old queue items are
   already done.
5. `M14-P1.6` handles issue #90: workspace refresh skips missing curated sources and summarizes
   per-source refresh failures with diagnostics while continuing valid refresh work, then exits
   non-zero while unresolved sources remain.
6. `M14-P1.7` handles issue #89: `splendor source update-path` repairs moved active curated
   workspace-backed source paths without manual manifest JSON edits or broad discovery.
7. Use #95 as the likely next Milestone 14 repair slice so health diagnostics can point at the
   concrete `source update-path`, source refresh, and stale-ingest commands now available.
8. Continue #79 through `M15-P1.2` after the open Milestone 14 P1 repair issues are handled.
9. Keep #30 and #37 as independent performance/scaling follow-ups unless real repository use makes
   either one urgent.

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

The retry result is captured in `docs/m14_synthbanshee_reevaluation.md`. After `M14-P4.1`, future
work starts from #79 unless #86 review identifies a narrower follow-up or a new real-agent run
reopens a source-lifecycle regression. The first #79 slice is `M15-P1.1`: keep bare compile
non-mutating, require `--page` for a deterministic diff-backed proposal, and require
`--apply --proposal-hash <hash>` for the explicit reviewed write.

## Tagging Readiness

After the release PR merges, v1 tagging is ready when `main` has:

- package version metadata updated for the intended v1 tag in both `pyproject.toml` and
  `src/splendor/__init__.py`
- a release-notes entry or GitHub release draft that names completed M13 work, validation, and the
  explicit post-v1 queue
- green CI for formatting, linting, tests, and coverage
- a passing `splendor lint` planning-state check
- no open issue mislabeled as a v1 blocker

Use this final tagging sequence after those checks pass:

```bash
git switch main
git pull --ff-only origin main
git tag -a v1.0.0 -m "Splendor v1.0.0"
git push origin v1.0.0
uv build
```

Before publishing artifacts outside GitHub, verify the built wheel/sdist from `dist/` in a clean
environment with:

```bash
uv pip install dist/splendor-*.whl
splendor --version
```
