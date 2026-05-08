Short read: no-init still misses `S7a`. After the listed setup, Splendor still misses `S7a`, but `splendor ingest --pending` is preview-only, so this is not a true “indexed retrieval” test. It shows the UX problem clearly: the command that looks like ingestion does not ingest unless `--apply` is added.

I left the generated Splendor state in place for inspection. Current worktree churn is:
```text
## main...origin/main
?? derived/
?? planning/
?? raw/
?? reports/
?? splendor.yaml
?? state/
?? wiki/
```

**No-Init Outputs**
```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor brief --agent-context "Continue hocrsyngen roadmap work after S6h"
```

```text
Agent context
Goal: Continue hocrsyngen roadmap work after S6h
Work context:
Suggested next:
- [medium/work-thread] Review pr #39: S0e: Align post-S4d production-readiness roadmap target=- url=https://github.com/HeOCR/hocrsyngen/pull/39
- [medium/work-thread] Review pr #55: S6h: Close S6 and activate S7 script abstraction target=- url=https://github.com/HeOCR/hocrsyngen/pull/55
- [medium/work-thread] Review pr #32: S3b: Add Hebrew document family recipes target=- url=https://github.com/HeOCR/hocrsyngen/pull/32
- [medium/work-thread] Review pr #34: S3d: Add visual inspection rubric target=- url=https://github.com/HeOCR/hocrsyngen/pull/34
- [medium/git-context] Review commit 1ebb277: S6h: Close S6 and activate S7 script abstraction (#55) target=1ebb277
Git context: branch=main head=1ebb277 base=origin/main merge_base=1ebb277e587d69ea996babbec86b15f208bd90f3
Recent issues and PRs:
- pr #39 [merged] score=78: S0e: Align post-S4d production-readiness roadmap (https://github.com/HeOCR/hocrsyngen/pull/39)
- pr #55 [merged] score=78: S6h: Close S6 and activate S7 script abstraction (https://github.com/HeOCR/hocrsyngen/pull/55)
- pr #32 [merged] score=60: S3b: Add Hebrew document family recipes (https://github.com/HeOCR/hocrsyngen/pull/32)
- pr #34 [merged] score=60: S3d: Add visual inspection rubric (https://github.com/HeOCR/hocrsyngen/pull/34)
- pr #46 [merged] score=60: S5d: Design optional learned-generation packaging boundary (https://github.com/HeOCR/hocrsyngen/pull/46)
Recent commits:
- 1ebb277 score=56: S6h: Close S6 and activate S7 script abstraction (#55)
- 4666b65 score=46: S4c: Add rendering-control condition bundles (#37)
- 61da1ce score=46: S4b: Add deterministic style parameter bundles (#36)
Files to read first:
- AGENTS.md
- llms.txt
- docs/roadmap.md
- src/hocrsyngen/schemas/template_catalog.schema.json
- docs/README.md
Provisional uncurated docs:
- docs/roadmap.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=206 hocrsyngen Roadmap
  Curate: splendor add-source docs/roadmap.md; splendor ingest docs/roadmap.md
- README.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=174 hocrsyngen
  Curate: splendor add-source README.md; splendor ingest README.md
- docs/allograph_character_prototype_plan.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=151 Allograph And Character-Level Prototype Plan
  Curate: splendor add-source docs/allograph_character_prototype_plan.md; splendor ingest docs/allograph_character_prototype_plan.md
- AGENTS.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=147 AGENTS.md
  Curate: splendor add-source AGENTS.md; splendor ingest AGENTS.md
- docs/word_line_assembly_prototype_plan.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=142 Word And Line Assembly Prototype Plan
  Curate: splendor add-source docs/word_line_assembly_prototype_plan.md; splendor ingest docs/word_line_assembly_prototype_plan.md
Splendor maintenance: sources=0 pages=0 queue_pending=0 review_needed=0
Next actions:
- Review pr #39: S0e: Align post-S4d production-readiness roadmap
- Review pr #55: S6h: Close S6 and activate S7 script abstraction
- Review pr #32: S3b: Add Hebrew document family recipes
- Review pr #34: S3d: Add visual inspection rubric
- Review commit 1ebb277: S6h: Close S6 and activate S7 script abstraction (#55)
- Read the top authority docs before changing planning-heavy behavior.
```

```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor suggest-next "Continue hocrsyngen roadmap work after S6h"
```

```text
Suggested next actions
Goal: Continue hocrsyngen roadmap work after S6h
Work actions:
1. [medium/work-thread] Review pr #39: S0e: Align post-S4d production-readiness roadmap target=- url=https://github.com/HeOCR/hocrsyngen/pull/39
   Reason: Planning notation
2. [medium/work-thread] Review pr #55: S6h: Close S6 and activate S7 script abstraction target=- url=https://github.com/HeOCR/hocrsyngen/pull/55
   Reason: Planning notation
3. [medium/work-thread] Review pr #32: S3b: Add Hebrew document family recipes target=- url=https://github.com/HeOCR/hocrsyngen/pull/32
   Reason: Planning notation
4. [medium/work-thread] Review pr #34: S3d: Add visual inspection rubric target=- url=https://github.com/HeOCR/hocrsyngen/pull/34
   Reason: Planning notation
5. [medium/git-context] Review commit 1ebb277: S6h: Close S6 and activate S7 script abstraction (#55) target=1ebb277
   Reason: Recent git context relevant to the stated goal.
6. [medium/git-context] Review commit 4666b65: S4c: Add rendering-control condition bundles (#37) target=4666b65
   Reason: Recent git context relevant to the stated goal.
7. [medium/git-context] Review commit 61da1ce: S4b: Add deterministic style parameter bundles (#36) target=61da1ce
   Reason: Recent git context relevant to the stated goal.
8. [medium/authority] Read provisional doc docs/roadmap.md target=docs/roadmap.md
   Reason: roadmap/current/current/inferred-authority/provisional-uncurated: Inferred roadmap or planning authority from a conventional docs path. Detected by filename/path heuristic; provisional until curated as a source. Curate with: splendor add-source docs/roadmap.md; splendor ingest docs/roadmap.md
Provisional uncurated docs:
- docs/roadmap.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=206 hocrsyngen Roadmap
  Curate: splendor add-source docs/roadmap.md; splendor ingest docs/roadmap.md
- README.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=174 hocrsyngen
  Curate: splendor add-source README.md; splendor ingest README.md
- docs/allograph_character_prototype_plan.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=151 Allograph And Character-Level Prototype Plan
  Curate: splendor add-source docs/allograph_character_prototype_plan.md; splendor ingest docs/allograph_character_prototype_plan.md
- AGENTS.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=147 AGENTS.md
  Curate: splendor add-source AGENTS.md; splendor ingest AGENTS.md
- docs/word_line_assembly_prototype_plan.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=142 Word And Line Assembly Prototype Plan
  Curate: splendor add-source docs/word_line_assembly_prototype_plan.md; splendor ingest docs/word_line_assembly_prototype_plan.md
Splendor maintenance: changed_sources=0 missing_sources=0 queue=0 review_needed=0 contested=0 stale=0
```

```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor query "Start the next S7a script abstraction implementation work"
```

```text
Query: Start the next S7a script abstraction implementation work
Summary: No matches found for "Start the next S7a script abstraction implementation work".
Matches:
```

**Setup Outputs**
```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor init
```

```text
Initialized Splendor workspace at <hocrsyngen-repo>
Created directories: 30
Created files: 29
State review groups:
- configuration: splendor.yaml (project defaults and configurable state locations)
- human workspace: wiki, planning (reviewed wiki and planning markdown)
- source and derived state: raw, derived (imported sources and generated parsed artifacts)
- runtime state: state, state/manifests/sources, reports (machine-readable manifests, queues, runs, and reports)
```

```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor add-source .agent-plan.md --capture-source-commit
```

```text
Source ref: .agent-plan.md
Logical ID: source:.agent-plan.md
Registered source src-f28a2fcdedd6fb327c7016d8d555a17325373368b77dbc8f6784eae8cf2eccb9
Manifest: <hocrsyngen-repo>/state/manifests/sources/src-f28a2fcdedd6fb327c7016d8d555a17325373368b77dbc8f6784eae8cf2eccb9.json
Storage mode: none
Queued ingest: <hocrsyngen-repo>/state/queue/ingest-src-f28a2fcdedd6fb327c7016d8d555a17325373368b77dbc8f6784eae8cf2eccb9.json
Next: splendor ingest --pending
```

```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor add-source README.md --capture-source-commit
```

```text
Source ref: README.md
Logical ID: source:README.md
Registered source src-83c7e75457ba4b9137c42a5df3aa1fda3a5db2bf91eca70ecd0a6bbb30aabe73
Manifest: <hocrsyngen-repo>/state/manifests/sources/src-83c7e75457ba4b9137c42a5df3aa1fda3a5db2bf91eca70ecd0a6bbb30aabe73.json
Storage mode: none
Queued ingest: <hocrsyngen-repo>/state/queue/ingest-src-83c7e75457ba4b9137c42a5df3aa1fda3a5db2bf91eca70ecd0a6bbb30aabe73.json
Next: splendor ingest --pending
```

```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor add-source docs/roadmap.md --capture-source-commit
```

```text
Source ref: docs/roadmap.md
Logical ID: source:docs/roadmap.md
Registered source src-7443c1bcd1427986ba7861563e0b25d7abe3448536127a1b110b5893a41fb95b
Manifest: <hocrsyngen-repo>/state/manifests/sources/src-7443c1bcd1427986ba7861563e0b25d7abe3448536127a1b110b5893a41fb95b.json
Storage mode: none
Queued ingest: <hocrsyngen-repo>/state/queue/ingest-src-7443c1bcd1427986ba7861563e0b25d7abe3448536127a1b110b5893a41fb95b.json
Next: splendor ingest --pending
```

```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor ingest --pending
```

```text
Pending ingest preview
Mutation mode: preview
Preview only: no queue, run, source, or wiki records written.
src-f28a2fcdedd6fb327c7016d8d555a17325373368b77dbc8f6784eae8cf2eccb9: planned (would run ingest job with --apply)
src-83c7e75457ba4b9137c42a5df3aa1fda3a5db2bf91eca70ecd0a6bbb30aabe73: planned (would run ingest job with --apply)
src-7443c1bcd1427986ba7861563e0b25d7abe3448536127a1b110b5893a41fb95b: planned (would run ingest job with --apply)
Drain summary: processed=3 succeeded=0 failed=0 skipped=0
Planned paths:
- write: queue_record state/queue/ingest-src-f28a2fcdedd6fb327c7016d8d555a17325373368b77dbc8f6784eae8cf2eccb9.json
- write: queue_record state/queue/ingest-src-83c7e75457ba4b9137c42a5df3aa1fda3a5db2bf91eca70ecd0a6bbb30aabe73.json
- write: queue_record state/queue/ingest-src-7443c1bcd1427986ba7861563e0b25d7abe3448536127a1b110b5893a41fb95b.json
Next: splendor ingest --pending --apply
```

**Post-Setup Outputs**
```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor brief --agent-context "Continue hocrsyngen roadmap work after S6h"
```

```text
Agent context
Goal: Continue hocrsyngen roadmap work after S6h
Work context:
Suggested next:
- [medium/work-thread] Review pr #39: S0e: Align post-S4d production-readiness roadmap target=- url=https://github.com/HeOCR/hocrsyngen/pull/39
- [medium/work-thread] Review pr #55: S6h: Close S6 and activate S7 script abstraction target=- url=https://github.com/HeOCR/hocrsyngen/pull/55
- [medium/work-thread] Review pr #32: S3b: Add Hebrew document family recipes target=- url=https://github.com/HeOCR/hocrsyngen/pull/32
- [medium/work-thread] Review pr #34: S3d: Add visual inspection rubric target=- url=https://github.com/HeOCR/hocrsyngen/pull/34
- [medium/git-context] Review commit 1ebb277: S6h: Close S6 and activate S7 script abstraction (#55) target=1ebb277
Git context: branch=main head=1ebb277 base=origin/main merge_base=1ebb277e587d69ea996babbec86b15f208bd90f3
Recent issues and PRs:
- pr #39 [merged] score=78: S0e: Align post-S4d production-readiness roadmap (https://github.com/HeOCR/hocrsyngen/pull/39)
- pr #55 [merged] score=78: S6h: Close S6 and activate S7 script abstraction (https://github.com/HeOCR/hocrsyngen/pull/55)
- pr #32 [merged] score=60: S3b: Add Hebrew document family recipes (https://github.com/HeOCR/hocrsyngen/pull/32)
- pr #34 [merged] score=60: S3d: Add visual inspection rubric (https://github.com/HeOCR/hocrsyngen/pull/34)
- pr #46 [merged] score=60: S5d: Design optional learned-generation packaging boundary (https://github.com/HeOCR/hocrsyngen/pull/46)
Recent commits:
- 1ebb277 score=56: S6h: Close S6 and activate S7 script abstraction (#55)
- 4666b65 score=46: S4c: Add rendering-control condition bundles (#37)
- 61da1ce score=46: S4b: Add deterministic style parameter bundles (#36)
Files to read first:
- AGENTS.md
- llms.txt
- docs/roadmap.md
- src/hocrsyngen/schemas/template_catalog.schema.json
- docs/README.md
Authority docs:
- docs/roadmap.md [roadmap/current/current/inferred-authority] score=206 hocrsyngen Roadmap
- README.md [current-authority/current/current/inferred-authority] score=174 hocrsyngen
- .agent-plan.md [roadmap/current/current/inferred-authority] score=132 Current System State
Provisional uncurated docs:
- docs/allograph_character_prototype_plan.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=151 Allograph And Character-Level Prototype Plan
  Curate: splendor add-source docs/allograph_character_prototype_plan.md; splendor ingest docs/allograph_character_prototype_plan.md
- AGENTS.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=147 AGENTS.md
  Curate: splendor add-source AGENTS.md; splendor ingest AGENTS.md
- docs/word_line_assembly_prototype_plan.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=142 Word And Line Assembly Prototype Plan
  Curate: splendor add-source docs/word_line_assembly_prototype_plan.md; splendor ingest docs/word_line_assembly_prototype_plan.md
- docs/decisions/0003-baseline-dependency-policy.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=138 ADR 0003 — Baseline Dependency Policy
  Curate: splendor add-source docs/decisions/0003-baseline-dependency-policy.md; splendor ingest docs/decisions/0003-baseline-dependency-policy.md
- docs/release_cap_handoff_policy.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=138 Release Cap Handoff Policy
  Curate: splendor add-source docs/release_cap_handoff_policy.md; splendor ingest docs/release_cap_handoff_policy.md
Splendor maintenance: sources=3 pages=0 queue_pending=3 review_needed=0
Maintenance actions:
- [high/queue] Drain ingest queue job ingest-src-7443c1bcd1427986ba7861563e0b25d7abe3448536127a1b110b5893a41fb95b target=docs/roadmap.md command=splendor ingest --pending
- [high/queue] Drain ingest queue job ingest-src-f28a2fcdedd6fb327c7016d8d555a17325373368b77dbc8f6784eae8cf2eccb9 target=.agent-plan.md command=splendor ingest --pending
- [high/queue] Drain ingest queue job ingest-src-83c7e75457ba4b9137c42a5df3aa1fda3a5db2bf91eca70ecd0a6bbb30aabe73 target=README.md command=splendor ingest --pending
Maintenance commands:
- [pr-summary] splendor pr-summary --since origin/main target=-
  Reason: Review compact committed Splendor state changes before PR handoff.
- [queue] splendor queue inspect target=-
  Reason: Inspect generated ingest queue records and operator states.
- [queue] splendor ingest --pending target=docs/roadmap.md
  Reason: Queue job is actionable now: pending.
Recent sources:
- docs/roadmap.md [registered/unreviewed] roadmap source_id=src-7443c1bcd1427986ba7861563e0b25d7abe3448536127a1b110b5893a41fb95b
- README.md [registered/unreviewed] README source_id=src-83c7e75457ba4b9137c42a5df3aa1fda3a5db2bf91eca70ecd0a6bbb30aabe73
- .agent-plan.md [registered/unreviewed] .agent plan source_id=src-f28a2fcdedd6fb327c7016d8d555a17325373368b77dbc8f6784eae8cf2eccb9
Last query: Start the next S7a script abstraction implementation work (0 matches)
Next actions:
- Review pr #39: S0e: Align post-S4d production-readiness roadmap
- Review pr #55: S6h: Close S6 and activate S7 script abstraction
- Review pr #32: S3b: Add Hebrew document family recipes
- Review pr #34: S3d: Add visual inspection rubric
- Review commit 1ebb277: S6h: Close S6 and activate S7 script abstraction (#55)
- Run `splendor ingest --pending` to preview pending source ingests, then add `--apply` after review.
- Read the top authority docs before changing planning-heavy behavior.
```

```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor suggest-next "Continue hocrsyngen roadmap work after S6h"
```

```text
Suggested next actions
Goal: Continue hocrsyngen roadmap work after S6h
Work actions:
1. [medium/work-thread] Review pr #39: S0e: Align post-S4d production-readiness roadmap target=- url=https://github.com/HeOCR/hocrsyngen/pull/39
   Reason: Planning notation
2. [medium/work-thread] Review pr #55: S6h: Close S6 and activate S7 script abstraction target=- url=https://github.com/HeOCR/hocrsyngen/pull/55
   Reason: Planning notation
3. [medium/work-thread] Review pr #32: S3b: Add Hebrew document family recipes target=- url=https://github.com/HeOCR/hocrsyngen/pull/32
   Reason: Planning notation
4. [medium/work-thread] Review pr #34: S3d: Add visual inspection rubric target=- url=https://github.com/HeOCR/hocrsyngen/pull/34
   Reason: Planning notation
5. [medium/git-context] Review commit 1ebb277: S6h: Close S6 and activate S7 script abstraction (#55) target=1ebb277
   Reason: Recent git context relevant to the stated goal.
6. [medium/git-context] Review commit 4666b65: S4c: Add rendering-control condition bundles (#37) target=4666b65
   Reason: Recent git context relevant to the stated goal.
7. [medium/git-context] Review commit 61da1ce: S4b: Add deterministic style parameter bundles (#36) target=61da1ce
   Reason: Recent git context relevant to the stated goal.
8. [medium/authority] Read authority doc docs/roadmap.md target=docs/roadmap.md
   Reason: roadmap/current/current/inferred-authority/curated: Inferred roadmap or planning authority from a conventional docs path. Detected by filename/path heuristic over a curated source.
Authority docs:
- docs/roadmap.md [roadmap/current/current/inferred-authority] score=206 hocrsyngen Roadmap
- README.md [current-authority/current/current/inferred-authority] score=174 hocrsyngen
- .agent-plan.md [roadmap/current/current/inferred-authority] score=132 Current System State
Provisional uncurated docs:
- docs/allograph_character_prototype_plan.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=151 Allograph And Character-Level Prototype Plan
  Curate: splendor add-source docs/allograph_character_prototype_plan.md; splendor ingest docs/allograph_character_prototype_plan.md
- AGENTS.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=147 AGENTS.md
  Curate: splendor add-source AGENTS.md; splendor ingest AGENTS.md
- docs/word_line_assembly_prototype_plan.md [roadmap/current/current/inferred-authority/provisional-uncurated] score=142 Word And Line Assembly Prototype Plan
  Curate: splendor add-source docs/word_line_assembly_prototype_plan.md; splendor ingest docs/word_line_assembly_prototype_plan.md
- docs/decisions/0003-baseline-dependency-policy.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=138 ADR 0003 — Baseline Dependency Policy
  Curate: splendor add-source docs/decisions/0003-baseline-dependency-policy.md; splendor ingest docs/decisions/0003-baseline-dependency-policy.md
- docs/release_cap_handoff_policy.md [current-authority/current/current/inferred-authority/provisional-uncurated] score=138 Release Cap Handoff Policy
  Curate: splendor add-source docs/release_cap_handoff_policy.md; splendor ingest docs/release_cap_handoff_policy.md
Splendor maintenance: changed_sources=0 missing_sources=0 queue=3 review_needed=0 contested=0 stale=0
1. [high/queue] Drain ingest queue job ingest-src-7443c1bcd1427986ba7861563e0b25d7abe3448536127a1b110b5893a41fb95b target=docs/roadmap.md command=splendor ingest --pending
   Reason: Queue job is actionable now: pending.
2. [high/queue] Drain ingest queue job ingest-src-f28a2fcdedd6fb327c7016d8d555a17325373368b77dbc8f6784eae8cf2eccb9 target=.agent-plan.md command=splendor ingest --pending
   Reason: Queue job is actionable now: pending.
3. [high/queue] Drain ingest queue job ingest-src-83c7e75457ba4b9137c42a5df3aa1fda3a5db2bf91eca70ecd0a6bbb30aabe73 target=README.md command=splendor ingest --pending
   Reason: Queue job is actionable now: pending.
Maintenance commands:
- [pr-summary] splendor pr-summary --since origin/main target=-
  Reason: Review compact committed Splendor state changes before PR handoff.
- [queue] splendor queue inspect target=-
  Reason: Inspect generated ingest queue records and operator states.
- [queue] splendor ingest --pending target=docs/roadmap.md
  Reason: Queue job is actionable now: pending.
```

```bash
PATH=/tmp/splendor-0.5.1-hocrsyngen-trial/bin:$PATH splendor query "Start the next S7a script abstraction implementation work"
```

```text
Query: Start the next S7a script abstraction implementation work
Summary: No matches found for "Start the next S7a script abstraction implementation work".
Matches:
```
