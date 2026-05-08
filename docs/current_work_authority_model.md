# Current-Work Authority Model

This design note defines the narrow current-work authority model derived from the v0.5.2
hocrgen/hocrsyngen retry findings. It is a planning and product contract, not a runtime behavior
change by itself.

The goal is to make `brief --agent-context` and `suggest-next` answer current-work handoff
questions from typed local planning evidence instead of treating every relevant sentence as an
equally eligible next action.

## Scope

This model applies when the user goal asks to continue, resume, start, or identify current or next
roadmap work. Examples:

- `continue the current hocrgen roadmap work`
- `pick up the next planned slice`
- `resume after the last merged PR`
- `what should the next agent do?`

It does not turn `splendor query` into an answer engine. Query remains a search/retrieval surface
unless a separate answer-synthesis mode is deliberately designed later.

## Inputs

The handoff model can use only local, deterministic, read-only inputs:

- `.agent-plan.md`
- README planning-state blocks
- ordered roadmap and planning docs
- configured or inferred authority documents
- local git history and branch state
- best-effort read-only GitHub issue/PR state when already part of the handoff path
- existing Splendor wiki, source, run, query, lint, and health records

The model must not require a background worker, database, hosted service, mandatory external API,
or persisted vector index.

## Evidence Classes

Current-work ranking should classify evidence before scoring it.

### Active Task

An active task is an explicitly current or in-progress item in `.agent-plan.md`, a synchronized
planning-state block, or an open live issue/PR that directly owns the requested work.

Active tasks are the strongest current-work evidence.

### Unchecked Next Task

An unchecked next task is the first not-yet-complete item in an ordered checklist, roadmap list, or
phase sequence after completed predecessor items are accounted for.

Unchecked next tasks outrank broad roadmap prose and historical review material.

### Current Status Row

A current status row names the slice or phase that a planning table says is current. It is useful,
but it must be reconciled against explicit completion evidence. If git/GitHub state shows that the
named current slice has merged and the roadmap names a successor, the successor can become the
handoff candidate.

### Gated Follow-On

A gated follow-on is an unchecked item that depends on a prerequisite, missing evidence, or a prior
slice. It should be visible as follow-on context but should not outrank the prerequisite work.

In the v0.5.2 hocrgen retry, `F6g` is a gated follow-on behind `F6f2`.

### Blocker Or Prerequisite Context

Blocker prose explains why work is gated or important. It is not a current slice by itself. A
blocker mention can support an action only when it maps back to an active task, unchecked next
task, or explicit current status row.

In the v0.5.2 hocrgen retry, old `F1c` blocker prose is context for synthetic target scale, not
the current handoff action.

### Completed Work

Completed work includes merged PRs, closed issues, checked roadmap items, release notes, and
commits for already-landed slices. Completed work should be predecessor context for current-work
goals unless the user explicitly asks to review history, audit a PR, or prepare release notes.

### Historical Or Superseded Context

Historical reviews, superseded source summaries, old generated pages, and archived planning notes
can explain prior decisions, but they should not become the top current-work action while fresher
explicit planning state exists.

### Generated Maintenance State

Generated review-needed tasks, source freshness warnings, queue state, missing synthesis follow-up,
and lint/health drift are maintenance context. They can lead only for maintenance-focused goals.

## Precedence

For current-work goals, the default precedence is:

1. Active task.
2. Unchecked next task.
3. Reconciled current status row.
4. Live open issue or PR that directly owns the selected work.
5. Gated follow-on context.
6. Blocker or prerequisite context.
7. Completed work and merged PR predecessor context.
8. Historical, superseded, generated, and maintenance context.

This precedence is a classification rule, not a hard ban on relevance scoring. A lower class can
still appear in the output when it explains the selected work, but it should not displace the
selected current-work candidate.

## Conflict Handling

When sources disagree, Splendor should prefer explicit local planning state that names active or
unchecked work, then reconcile it against completion evidence.

Expected handling:

- If `.agent-plan.md` names an active unchecked task and roadmap prose mentions an older blocker,
  rank the active unchecked task first and keep the blocker as context.
- If planning-state lines name a current slice that has merged and the roadmap lists a successor,
  rank the successor for current/next-roadmap goals.
- If a roadmap says an item is current but `.agent-plan.md` marks a later item active, surface the
  conflict and prefer `.agent-plan.md` only when it clearly names active unchecked work.
- If no active or unchecked item can be extracted, say that no current-work candidate was
  identified instead of promoting merged PRs or generated maintenance state as the answer.

## Output Expectations

Human output should make the selected current-work action and its authority path clear. Supporting
context should be labeled so a reader can tell the difference between the next action, a gated
follow-on, blocker context, and predecessor history.

JSON output should stay additive and deterministic. Existing action fields should remain stable.
Any future `current_planned_work` object should identify:

- selected slice or task ID, when available;
- title;
- authority paths;
- evidence class;
- predecessor evidence;
- gated follow-ons;
- blocker or prerequisite context;
- whether the selection was direct or reconciled from stale current-state text.

## Acceptance Examples

The captured v0.5.2 hocr retry cases define the immediate acceptance bar:

- hocrgen: `brief --agent-context "continue the current hocrgen roadmap work"` ranks `F6f2`
  first.
- hocrgen: `suggest-next "continue the current hocrgen roadmap work"` ranks `F6f2` first.
- hocrgen: `F6g` appears only as gated follow-on context behind `F6f2`.
- hocrgen: `F1c` appears only as blocker or prerequisite context, not as
  `current_planned_work.slice_id`.
- hocrgen: merged PRs do not appear as top current-work actions.
- hocrsyngen: `S8b` remains first for the current-work handoff that v0.5.2 already handled
  partially correctly.

## Non-Goals

- No new mutating web workflows.
- No change to current read-only web behavior.
- No query answer synthesis.
- No mandatory GitHub, hosted service, database, background worker, or external API.
- No broad agent-memory architecture.
- No reopening M19 retry work.
