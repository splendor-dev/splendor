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

Direct owner issue/PR threads are part of active-task evidence only when their title/body or
linked planning state directly names the selected slice or task. Related parent, sibling, or
historical threads are not active tasks by themselves.

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

## Extraction Contract

M20-P1.6 should implement classification through deterministic extraction before relevance
scoring. The extractor should not treat every matched slice token as an equally valid candidate.

### Source Priority

For current/next-roadmap goals, read candidate sources in this order:

1. `.agent-plan.md` active state and unchecked task sections.
2. Live open issue/PR state that directly names the goal, selected slice, or linked active
   planning record.
3. Synchronized planning-state blocks in README and roadmap docs.
4. Ordered roadmap or phase tables in roadmap docs.
5. Configured or inferred current-authority docs.
6. Local git/GitHub completion evidence used to reconcile candidates and demote completed work.
7. Generated wiki/source summaries, saved query results, and review transcripts as context only.

Lower-priority sources can explain or corroborate a selected candidate, but they should not
displace a higher-priority active or unchecked task unless the higher-priority source is explicitly
stale and completion evidence identifies the successor.

### Section Priority

Within `.agent-plan.md` and roadmap-like files, prefer sections in this order:

1. Current system state or current work sections.
2. Active task, implementation checklist, or current PR sub-slice sections.
3. Planned next, candidate PR slice, or ordered roadmap sections.
4. Status tables that distinguish complete, current, planned, blocked, or gated work.
5. Retrospective, historical, release-note, review, appendix, or archived sections.

Historical/review/archive sections should not produce current-work candidates unless no active,
unchecked, current, or planned section yields a candidate and the output clearly reports that the
candidate is weak.

### Accepted Candidate Patterns

The extractor should accept a candidate only from lines or table rows that carry task status or
planning intent, such as:

- unchecked markdown checkboxes: `- [ ] F6f2: ...`;
- explicit current-state lines: `Current PR sub-slice: F6f2`;
- explicit next-state lines: `Next planned PR sub-slice: F6f2`;
- status table rows marked `current`, `planned`, `next`, `in progress`, or equivalent;
- open issue/PR titles or bodies that directly name the selected slice and are not merged/closed;
- ordered roadmap rows where all prior rows in the same sequence are completed and this row is the
  first non-complete row.

The extractor should ignore candidate tokens on lines marked or headed as completed, done, merged,
closed, superseded, archived, historical, retrospective, old blocker, or release notes unless they
are used only as predecessor or blocker context.

### Tie-Breakers

When multiple candidates remain after classification:

1. Prefer active/in-progress over unchecked next.
2. Prefer unchecked next over gated follow-on.
3. Prefer candidates from higher-priority sources.
4. Prefer the first non-complete item in the nearest ordered sequence.
5. Prefer candidates directly named by a live open owner issue/PR.
6. Prefer newer synchronized planning-state values over older generated summaries.
7. If still tied, keep the first deterministic file-order candidate and report the conflict.

### Conflict Output

When selected evidence conflicts with other plausible candidates, human output and JSON should
label the conflict instead of hiding it. At minimum, the handoff should name:

- the selected current-work candidate;
- authority path(s) that selected it;
- predecessor or completed candidates that were demoted;
- gated follow-ons;
- blocker/prerequisite context;
- lower-priority conflicting candidates and why they did not win.

## Precedence

For current-work goals, the default precedence is:

1. Active task.
2. Unchecked next task.
3. Reconciled current status row.
4. Gated follow-on context.
5. Related live issue or PR context that does not directly own the selected work.
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
The current `current_planned_work` object already identifies:

- selected slice or task ID, when available;
- planned slice label, when available;
- authority paths;
- predecessor slices;
- selection reason.

M20-P1.6 may add optional fields, but should not remove or rename the existing fields. Useful
additive fields include:

- evidence class;
- predecessor evidence;
- gated follow-ons;
- blocker or prerequisite context;
- lower-priority conflicts;
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
