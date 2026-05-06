---
schema_version: '1'
kind: task
task_id: task-authority-fallback-uncurated-handoff
title: Add inferred authority and provisional uncurated docs to handoff
status: todo
priority: high
milestone_refs: []
decision_refs: []
question_refs: []
owner: null
created_at: '2026-05-06T08:30:00+00:00'
updated_at: '2026-05-06T08:30:00+00:00'
depends_on:
- task-git-aware-work-first-agent-handoff
source_refs: []
page_refs:
- docs/evaluations/v0_4_external_retry_bar.md
- docs/evaluations/v0_3_hocrgen_evaluation.md
- docs/evaluations/v0_3_hocrgen_followup.md
run_refs: []
---

## Context

Roadmap slice: `M18-P2.1`.

hocrgen feedback clarified that configured authority should win, but repos without explicit config
still need useful inferred authority for conventional files such as `.agent-plan.md`, `AGENTS.md`,
`CLAUDE.md`, `README.md`, roadmap-like docs, and planning tests.

## Expected Outcome

Add labeled inferred-authority fallback and allow important uncurated documentation to appear as
provisional context with exact curation commands. Historical outside reviews must remain visible
without outranking current roadmap, planning state, or policy contracts.
