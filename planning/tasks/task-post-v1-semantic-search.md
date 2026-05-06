---
schema_version: '1'
kind: task
task_id: task-post-v1-semantic-search
title: Revisit semantic search after work-first handoff is correct
status: todo
priority: low
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
- docs/evaluations/v0_3_synthbanshee_followup.md
- docs/evaluations/v0_3_hocrgen_followup.md
run_refs: []
---

## Context

Roadmap slice: `M20-P1.1`.

The v0.3 trials mention token-similarity ranking weakness, but both reports point first to handoff
shape, git blindness, authority ranking, and maintenance noise. A vector index should not be the
next blocker until work-first ranking is correct.

## Expected Outcome

Keep semantic search visible as a post-v1 product bet. Reassess after v0.4 handoff trials prove
that Splendor answers the right work question and needs better retrieval quality rather than better
authority/workflow semantics.
