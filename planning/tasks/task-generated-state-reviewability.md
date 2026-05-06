---
schema_version: '1'
kind: task
task_id: task-generated-state-reviewability
title: Reduce generated-state review noise before v1
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
- docs/evaluations/v0_3_hocrgen_evaluation.md
- docs/evaluations/v0_3_hocrgen_followup.md
run_refs: []
---

## Context

Roadmap slice: `M19-P1.1`.

hocrgen confirmed that one successful workspace refresh can still produce a 100+ path generated
diff. `pr-summary` helps explain it, but the normal PR diff remains too noisy for ordinary planning
work.

## Expected Outcome

Design and implement a reviewability strategy for generated state before public v1. Candidate
directions include compact committed mode, clearer reviewer-significant grouping, and moving
queue/run/report churn out of normal PR review unless the PR is about operational state.
