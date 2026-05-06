---
schema_version: '1'
kind: task
task_id: task-agent-safe-preview-apply-consistency
title: Make mutating command preview and apply semantics consistent
status: todo
priority: medium
milestone_refs: []
decision_refs: []
question_refs: []
owner: null
created_at: '2026-05-06T08:30:00+00:00'
updated_at: '2026-05-06T08:30:00+00:00'
depends_on: []
source_refs: []
page_refs:
- docs/evaluations/v0_3_synthbanshee_evaluation.md
- docs/evaluations/v0_3_synthbanshee_followup.md
run_refs: []
---

## Context

Roadmap slice: `M19-P2.1`.

SynthBanshee feedback called out the cognitive cost of commands where some preview by default and
others mutate immediately. `ingest --pending --json` and `workspace refresh` are especially easy
for agents to run while exploring.

## Expected Outcome

Make mutating commands consistently preview-by-default or otherwise apply-gated before v1, with
clear compatibility notes and deterministic JSON output for both preview and apply modes.
