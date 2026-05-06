---
schema_version: '1'
kind: task
task_id: task-git-aware-work-first-agent-handoff
title: Add git-aware, work-first agent handoff
status: todo
priority: high
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
- docs/evaluations/v0_3_hocrgen_evaluation.md
- docs/evaluations/v0_3_hocrgen_followup.md
run_refs: []
---

## Context

Roadmap slice: `M18-P1.1`.

The v0.3 SynthBanshee and hocrgen trials agree that source lifecycle recovery is materially better,
but `brief --agent-context` and `suggest-next` still do not answer the active work question before
reporting Splendor maintenance state.

## Expected Outcome

Add git-aware, work-first handoff by default. Briefing should include recent commits and relevant
PR context, support `--since <ref>` and `--no-git`, lead with open work/current authority/files to
read, and place source drift or queue state under a separated maintenance section unless the goal
is explicitly maintenance-focused.
