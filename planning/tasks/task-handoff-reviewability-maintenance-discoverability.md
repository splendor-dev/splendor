---
schema_version: '1'
kind: task
task_id: task-handoff-reviewability-maintenance-discoverability
title: Improve handoff reviewability and maintenance discoverability
status: todo
priority: medium
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
- docs/evaluations/v0_3_synthbanshee_evaluation.md
- docs/evaluations/v0_3_hocrgen_evaluation.md
run_refs: []
---

## Context

Roadmap slice: `M18-P3.1`.

Both external trials found maintenance signals useful but noisy when mixed with task actions.
hocrgen also reported that `task list` being empty while `wiki status` reports review-needed or
missing-synthesis pages is confusing.

## Expected Outcome

Make maintenance state easier to inspect intentionally. Candidate fixes include a separated
maintenance footer in handoff, `wiki status --review-needed`, `task list --wiki-review`, and clearer
empty-state guidance when no human-authored planning tasks exist.
