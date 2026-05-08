# Human Operator Web/Wiki Review Synthesis

This document synthesizes the external review thread on Splendor's missing human-operator
web/wiki layer. It summarizes the raw replies, extracts shared themes and disagreements, and records
the product and architecture conclusions that should shape follow-up design work.

Source replies:

- `docs/evaluations/human_operator_web_wiki_reviews/gemini_pro_reply.md`
- `docs/evaluations/human_operator_web_wiki_reviews/gemini_pro_followup_reply.md`
- `docs/evaluations/human_operator_web_wiki_reviews/chatgpt_pro_reply.md`
- `docs/evaluations/human_operator_web_wiki_reviews/claude_opus_reply.md`

This is an evaluation synthesis, not a behavior change or product contract change by itself. It
should feed the next design/spec/roadmap PR for the operator cockpit track.

## Executive Conclusion

All reviewers converged on the same central diagnosis: Splendor's current local web UI exposes
durable state, but it does not construct human meaning from that state. The current implementation
is architecturally conservative in the right way: local FastAPI, server-rendered HTML, deterministic
filesystem inputs, no database, no hidden cache, no background worker, no hosted dependency, and
read-only routes. The problem is not that substrate. The problem is information architecture.

Splendor needs an explicit product track for human operator comprehension. The CLI remains the
deterministic operating surface for agents and explicit mutations. The wiki remains durable,
reviewable project memory. The web UI should become a local human comprehension surface: an
operator cockpit and navigation layer that helps a returning human understand the project, current
work, trouble spots, recent learning, and knowledge graph without reading raw records first.

The strongest formulation came from Claude:

> The CLI tells the truth; the cockpit tells the story.

That is the right framing, with one important constraint: the cockpit's story must be traceable.
Every interpretive claim such as "needs review", "blocked", "contested", "current", or "failed"
must map back to visible local files, frontmatter fields, planning records, run/queue records, or
other git-reviewable evidence. The cockpit may rank, group, and explain; it must not invent,
contradict, or hide the underlying records.

## Reviewer-By-Reviewer Summary

### Gemini Pro First Reply

Gemini's first reply framed the web UI as an "Operator Cockpit" rather than a raw state inspector.
It identified the same high-severity UX failures the user observed:

- wiki detail pages invert the information hierarchy by placing raw JSON metadata before prose;
- the home page lacks project identity;
- status, queue, and run pages expose internals instead of significance;
- planning views are raw tables, not roadmaps.

Gemini proposed a conservative, read-only path:

- render project identity and summary from local markdown;
- surface "Attention Needed" for contested pages and failed runs;
- group planning records into active, blocked, next, and recently completed;
- demote frontmatter into a footer or collapsible technical area;
- expose `related_pages` and `tags` as related context;
- avoid CLI changes and new structured state in the first pass.

The first reply was directionally correct but still high-level. Its strongest contribution was
calling metadata placement a product-level information architecture failure, not just a cosmetic
issue.

### Gemini Pro Follow-Up

The follow-up was more concrete. It proposed specific source-of-truth cascades and a first set of
implementation slices:

- project identity from `wiki/index.md`, then README, then workspace basename;
- active work from `.agent-plan.md` or planning records;
- attention items from `review_state` and failed runs;
- recent insights from `wiki/log.md`;
- page detail metadata moved to a bottom `<details>` block;
- `related_pages` and `tags` rendered after the body;
- a parsing budget for `/`, browse/search, and detail routes.

Useful parts to carry forward:

- define bounded parsing rules for the root page;
- keep detail-page full parsing limited to the requested file;
- make project identity deterministic and fallback-driven;
- start with page detail metadata demotion, then project identity, then cockpit triage.

Corrections needed:

- project identity extraction should not live inside `resolve_layout` unless the product deliberately
  makes it part of layout/config semantics; a web/read-model helper is the safer first home;
- "topmost unchecked item from `.agent-plan.md`" must not be implemented ad hoc, because that risks
  reproducing the hocrgen current-work handoff bug; current-work extraction should reuse or wait for
  the M20-P1.6 authority classifier;
- raw planning tables should not be abandoned, only demoted behind a human roadmap layer;
- `review_state == stale` needs verification against the actual schema before becoming a contract.

### ChatGPT Pro Reply

ChatGPT provided the broadest route-by-route product map and the most detailed acceptance and test
material. Its core framing was:

- Splendor CLI is the deterministic operating surface.
- Splendor web is the local human comprehension surface.
- Splendor wiki is durable, reviewable project memory.

It proposed a home cockpit that answers:

- what project am I looking at;
- what does the knowledge base know;
- what is current, next, blocked, stale, contested, or review-needed;
- what changed recently;
- which pages, sources, plans, runs, and issues are connected;
- where should a human operator look next.

ChatGPT also proposed specific surfaces:

- `/attention` for review-needed, contested, stale, failed, blocked, decision, question, and source
  coverage items;
- `/recent` for log and durable activity;
- `/browse` as a knowledge map rather than a flat list;
- source detail as a trace view;
- status, runs, and queue as interpreted health/activity pages with raw tables demoted.

Its architecture recommendation was a set of pure read-model builders:

- `build_operator_overview`;
- `build_attention_items`;
- `build_knowledge_map`;
- `build_page_relationships`;
- `build_recent_activity`.

These builders should read existing local files, sort deterministically, write nothing, avoid
network calls, avoid hidden caches, and feed both HTML rendering and potential CLI output.

Useful parts to carry forward:

- add an explicit `M20-P4: Human operator cockpit and wiki navigation` track;
- start with a docs/design contract;
- keep raw tables available as audit/debug surfaces;
- treat current-work authority classification as shared infrastructure, not a web-specific duplicate;
- build a SynthBanshee-like fixture for acceptance tests;
- add no-mutation and deterministic-output tests for read-model builders and GET routes.

Corrections needed:

- optional config fields are useful, but the first implementation should probably work without new
  config by deriving identity from existing local files;
- `/attention` and `/recent` are important but probably not first implementation slices;
- suggested optional schema fields such as `operator_note` and page `summary` should be deferred
  unless the design PR proves they remove real ambiguity;
- filesystem mtime should not be used as the sole source of "recent" because it is not durable,
  reviewable project state.

### Claude Opus Reply

Claude gave the crispest product thesis and the most useful sequencing. It named the missing track
as "operator comprehension" and argued that Splendor has been treating the web UI as a secondary
read view of the agent runtime, while dogfooding shows the web UI is the primary surface for human
orientation.

Claude's strongest points:

- the cockpit is a read-only narrative projection, not a new runtime, database, or authority;
- every pane must be reproducible from current workspace files alone;
- every interpretive judgment must be traceable to git-visible evidence;
- the cockpit may re-rank and re-summarize, but must not contradict records;
- page-detail metadata placement is a current product/spec violation and the highest-leverage
  visible fix;
- `wiki/index.md` and `wiki/log.md` already exist in the spec but are underused by the web UI;
- search is useful but cannot compensate for missing navigation.

Claude proposed six cockpit panes:

- project at a glance;
- roadmap snapshot;
- needs attention;
- recent insights;
- knowledge map;
- what to look at next.

Claude also proposed a concrete `M20-P4` sequence:

- `M20-P4.0`: docs/design contract;
- `M20-P4.1`: project identity and page detail layout;
- `M20-P4.2`: cockpit home page read-model v1, possibly with `splendor cockpit summary`;
- `M20-P4.3`: roadmap swim-lanes and trouble spots;
- `M20-P4.4`: wiki interlinking and backlinks;
- `M20-P4.5`: status/runs/queue narrative layer;
- `M20-P4.6`: log/insights surface.

Useful parts to carry forward:

- make P4.0 a docs-only design/spec/roadmap slice;
- treat page-detail re-layout as the fastest high-signal implementation;
- define lane assignment and attention rules deterministically;
- keep browser actions read-only and display CLI commands instead of buttons;
- explicitly defer per-user state, "since I last visited", browser mutation, caches, hosted
  dependencies, and SPA complexity.

Corrections needed:

- do not require a `project:` config block in the first implementation; make config optional and
  derive a fallback first;
- avoid `state/cockpit_health.json` until measured performance requires a durable rebuild artifact;
- replace "same git SHA" determinism wording with "same workspace tree bytes and local records" so
  uncommitted local state remains a first-class Splendor workflow;
- make `splendor cockpit summary` a strong candidate, not an automatic requirement for the first
  implementation slice.

## Major Consensus Themes

### 1. The Web UI Should Become A Human Comprehension Layer

Every reviewer independently described the target as an operator cockpit. They differed in wording,
but the concept was stable: the web UI should translate local state into human answers. It should
not merely expose tables, IDs, paths, counts, JSON, and raw records.

The cockpit should answer these questions on arrival:

- What project is this?
- Where are we in the roadmap?
- What is active, next, blocked, stale, contested, failed, or review-needed?
- What changed recently?
- What has the knowledge base learned or accumulated?
- Which pages, sources, planning records, and runs are connected?
- What should I inspect next?

This is additive to current work. It does not replace the CLI, current-work authority model,
schema contracts, deterministic state, or git-native review.

### 2. Project Identity Is A First-Order Contract

All reviewers agreed that showing "Splendor" as the primary header inside a target workspace is
wrong. Splendor is the tool; the target project is what the human came to understand.

The product should resolve a display identity using a deterministic cascade. The synthesis
recommendation is:

1. Optional explicit config, if and when introduced.
2. `wiki/index.md` H1 and leading paragraph.
3. README H1 and leading paragraph.
4. Workspace directory basename.
5. A quiet fallback such as "Splendor workspace" plus a hint.

The first implementation should not require new config. It should work from existing files and leave
config as a later optional precision mechanism.

### 3. The Home Page Should Not Be A Count Dashboard

The current home page's count cards are not useless, but they are not an entry point. Counts should
support the story, not replace it.

Consensus cockpit sections:

- project identity and summary;
- current work or roadmap snapshot;
- needs attention;
- recent insights or activity;
- knowledge map;
- next inspection links.

Each section needs a sparse-workspace empty state. A sparse workspace should look quiet and useful,
not broken.

### 4. Page Detail Metadata Must Be Demoted

This is the most concrete and urgent UI failure. The reviewers all called out the same issue: raw
metadata appears before readable content. The product spec already says users should not require raw
frontmatter inspection, so the current route violates the intended contract.

The agreed shape:

- top: compact human badges such as kind, status, review state, authority role, freshness, source
  count;
- then page title and markdown body;
- then related context, provenance, source links, planning links, backlinks, contradictions, and
  supersession links when available;
- bottom: full raw metadata in a collapsed "Technical details" section.

Metadata must remain accessible for audit/debug. It should stop dominating the human reading path.

### 5. Planning Should Render As Roadmap, Not Storage

The current planning page is useful as an audit table but poor as a human planning surface.
Reviewers converged on a default grouped view:

- current or active;
- next;
- blocked or gated;
- open decisions;
- open questions;
- recently completed;
- historical or archived.

Raw records, IDs, and paths should remain reachable. The default should answer "where are we and
what matters now?"

The planning view should eventually consume the M20-P1.6 current-work authority classifier rather
than implementing its own unchecked-line heuristics.

### 6. Status, Runs, And Queue Need Interpretation

The current status, run, and queue pages expose internals. Reviewers want them reframed as knowledge
health and recent local activity.

The useful first step is not complex dashboards. It is short explanation blocks and deterministic
grouping:

- healthy vs needs attention;
- failed/stuck before done/noise;
- affected sources/pages visible before technical IDs;
- raw run IDs, payloads, leases, paths, and record files demoted but still inspectable;
- all actions remain CLI-first and read-only in the browser.

### 7. Knowledge Navigation Should Use Existing Relationship Fields

Splendor already has `related_pages`, `tags`, `source_refs`, `issue_refs`, `pr_refs`,
`provenance_links`, `supersedes`, `superseded_by`, and `contradictions`. The feedback was not to
invent a large new graph database. It was to render the links Splendor already knows.

Initial relationship work can be derived from:

- outgoing `related_pages`;
- reverse scans for backlinks;
- source refs;
- planning refs;
- supersession fields;
- contradiction records;
- tags and kinds.

Future durable backlink rebuilds can be considered only after request-time computation is measured
and proves too slow.

### 8. Read Models Are The Right Architecture Boundary

The strongest architecture theme was a pure read-model layer. The web route should not contain all
operator logic inline. Instead, build typed, deterministic helpers that derive operator projections
from local files and are easy to test.

Likely read-model surfaces:

- operator overview;
- attention items;
- page relationships;
- knowledge map;
- recent activity;
- planning lane assignment;
- project identity.

These read models should:

- read local files only;
- write nothing;
- avoid network access;
- avoid hidden caches;
- avoid background workers;
- use stable sorting;
- degrade gracefully when optional metadata is absent;
- expose traceable evidence for interpretive claims.

### 9. Raw Audit Surfaces Must Remain

No reviewer recommended removing raw state. The common recommendation is demotion, not deletion.

Raw state remains important because Splendor is git-native and agent-friendly. Humans need readable
orientation first; agents and debuggers still need full records. The product contract should say
that raw records are available behind detail views, table modes, collapsible sections, and markdown
source files.

### 10. Tests Should Prove Determinism And No Mutation

The most repeated testing recommendations:

- route tests for project identity rendering;
- DOM/order tests that markdown body appears before raw metadata;
- read-model unit tests for overview, attention, relationships, and planning lanes;
- sparse-workspace empty-state tests;
- SynthBanshee-like fixture tests;
- no-mutation tests for GET routes;
- deterministic sorting/output tests;
- raw-table/detail availability tests;
- optional CLI/web parity tests if a cockpit CLI summary is added.

## Disagreements And Design Tensions

### Config First vs Derivation First

Gemini initially leaned toward deriving identity from existing markdown. ChatGPT and Claude both
suggested an explicit `project:` config block. Claude treated it as obviously valuable; ChatGPT
framed it as optional but useful.

Synthesis recommendation: derivation first, optional config later.

Reasoning:

- the immediate UX failure can be fixed without adding schema;
- first-run friction stays low;
- many repositories already have a README or wiki index;
- explicit config can be introduced once the desired fields are clearer;
- absence of config should never make a workspace feel broken.

### Which Implementation Comes First

There are three plausible first implementation slices:

- docs/design contract;
- page detail metadata demotion;
- cockpit home/project identity.

Synthesis recommendation:

1. First land a docs/design/spec/roadmap slice, because this is a product-track addition.
2. First implementation should probably combine minimal project identity with page-detail metadata
   demotion if the patch is still small.
3. Cockpit home should come after the read-model contract is explicit.

Reasoning:

- the product track needs a shared vocabulary before code;
- metadata demotion is the fastest visible quality fix and directly closes an existing spec gap;
- cockpit home risks scope creep if implemented before its pane contract and parsing budget are
  written down.

### CLI `cockpit summary` Now Or Later

ChatGPT and Claude both liked the idea of exposing the same cockpit projection through a CLI command.
This would improve testability and agent consumption.

Synthesis recommendation: good idea, but not mandatory for the first implementation.

Reasoning:

- CLI/web parity is attractive;
- it prevents the cockpit from becoming web-only logic;
- but adding a new CLI surface can broaden the first slice;
- the first design should define the read model so a CLI summary can be added deliberately.

### Durable Cache/Rebuild Artifacts vs Request-Time Derivation

Claude floated optional durable records such as `state/cockpit_health.json` or a future backlinks
record. ChatGPT and Gemini leaned toward request-time derivation.

Synthesis recommendation: request-time first, durable rebuild only when measured.

Reasoning:

- hidden or premature caches undermine the local state model;
- request-time derivation is simpler and more honest for v1;
- existing cheap metadata reads already show the repo can be conservative about parsing;
- durable rebuilt records are acceptable only if explicit CLI commands produce reviewable files.

### `/attention` As Separate Route vs Status Integration

Reviewers split between a standalone `/attention` page and attention as part of `/status`.

Synthesis recommendation: design both concepts, implement incrementally.

Reasoning:

- the home cockpit needs an attention pane regardless;
- `/status` should become more interpretive;
- a dedicated `/attention` page becomes valuable once there are enough attention types;
- first implementation can link from the cockpit to `/status` until `/attention` exists.

### Recent Activity And "Since I Was Last Here"

Claude emphasized the value of "since I was last here", but also named per-user state as a non-goal.
ChatGPT warned against filesystem mtime as the sole durable signal.

Synthesis recommendation: avoid per-user "last seen"; use deterministic, file-backed recent windows
or explicit log entries.

Reasoning:

- per-user state would introduce a new state class;
- filesystem mtime is not reliable git-reviewed state;
- `wiki/log.md`, run records, generated timestamps, and planning timestamps are better sources;
- a "last 7 days" or "latest N durable events" view is deterministic enough if timestamps come from
  records.

### Current Work In The Cockpit

Gemini proposed topmost unchecked `.agent-plan.md` items; ChatGPT and Claude tied this to the
current-work authority model.

Synthesis recommendation: do not duplicate current-work logic in the web layer.

Reasoning:

- the hocrgen/hocrsyngen retry evidence showed exactly how naive current-work extraction can fail;
- M20-P1.6 is intended to define current-work authority classification;
- the cockpit should consume that classifier when available;
- before then, it can show simpler planning status groups with transparent limitations.

## Product Insights Gained

### Insight 1: "Human Useful" Is Not The Same As "Human Visible"

Splendor already makes lots of state visible to humans. The dogfood failure shows that visibility is
not enough. A human operator needs salience, hierarchy, labels, context, and next inspection paths.

The product should explicitly distinguish:

- machine-readable state;
- audit/debug views;
- human comprehension views.

The same files can power all three, but the renderings should not be the same.

### Insight 2: The Web UI Has A Different Job Than The CLI

The CLI should remain exact, explicit, scriptable, and mutation-capable. The web UI should be
read-only, orienting, and interpretive. Trying to make the web UI "more powerful" by adding browser
mutations would solve the wrong problem first.

The immediate product gap is not lack of buttons. It is lack of orientation.

### Insight 3: The Existing Schema Is More Valuable Than The Current UI Shows

Fields like `related_pages`, `tags`, `source_refs`, `provenance_links`, `review_state`,
`authority_role`, and `contradictions` are already enough to create better navigation. The first
operator track should exploit existing contracts before adding new ones.

This means the next design should favor rendering and read-model contracts over new storage.

### Insight 4: The Home Page Should Be Built From Questions, Not Counts

A count dashboard is a system inventory. A cockpit is an answer surface.

The root route should be designed from returning-operator questions:

- What is this?
- What should I know now?
- What is broken or unresolved?
- What changed?
- What should I inspect next?

Counts can appear in support of those answers. They should not be the primary content.

### Insight 5: The Page Detail Fix Is A Trust Fix

Moving raw metadata below the body is not just polish. It changes who the UI appears to be for. The
current detail page tells a human that the machine comes first. The corrected layout says the wiki
is readable first and auditable second.

That is the smallest change with the largest trust impact.

### Insight 6: "Narrative" Must Stay Traceable

The cockpit should tell a story, but it must not become an AI-authored dashboard. The narrative can
be structural and templated:

- this page is contested because its `review_state` says `contested`;
- this run failed because the run record says `failed`;
- this task is blocked because the planning record says `blocked`;
- this page is related because frontmatter says so.

That is enough to give humans meaning without inventing hidden intelligence.

### Insight 7: A New Track Belongs In The Roadmap

The current roadmap has search/handoff, mutating web review, and GitHub integration tracks. It does
not yet have a named human operator cockpit track at the needed level of detail.

The new track should be explicit. Suggested name:

`M20-P4: Human operator cockpit and wiki navigation`

This should not displace current M20 work. It should sit alongside it and reuse it where helpful.
In particular, M20-P1.6 current-work authority should become an input to the cockpit's current-work
pane rather than a competing implementation.

## Recommended Follow-Up Track

### M20-P4.0: Design And Spec Contract

Docs-only. Define the operator comprehension track and update product/spec/roadmap language.

Deliverables:

- product-spec section for human operator cockpit and wiki navigation;
- route-level page contracts for `/`, `/documents/*`, `/planning`, `/status`, `/runs`, `/queue`,
  `/browse`, and future `/attention` or `/recent`;
- read-model architecture contract;
- deterministic project identity contract;
- page-detail metadata visibility contract;
- non-goals and explicit deferrals;
- acceptance criteria and test strategy;
- roadmap sequencing.

No runtime behavior changes.

### M20-P4.1: Page Detail And Project Identity

Narrow implementation. Fix the most visible trust problem and project orientation.

Candidate scope:

- infer project display identity from existing local files;
- show target project name in web header/title where safe;
- render human badges above page content;
- move full metadata into a bottom collapsed technical section;
- show related pages/tags/provenance when already available;
- preserve raw metadata access;
- no new persistent state;
- tests for body-before-metadata and identity fallback.

### M20-P4.2: Cockpit Home Read Model

Introduce the first operator overview.

Candidate scope:

- pure `build_operator_overview` read-model helper;
- root page sections for project summary, current/next work, attention summary, recent durable
  activity, knowledge map summary, and inspect-next links;
- sparse empty states;
- no writes and no external calls;
- current-work pane consumes M20-P1.6 classifier if available, otherwise reports a limited fallback.

### M20-P4.3: Planning Roadmap View

Default planning view becomes human roadmap, while raw tables remain available.

Candidate scope:

- deterministic lane assignment;
- active/next/blocked/questions/decisions/recently done sections;
- technical IDs and paths demoted;
- raw view retained.

### M20-P4.4: Attention And Health Interpretation

Add or extend attention surfaces.

Candidate scope:

- attention item model derived from local files;
- status/runs/queue health summaries;
- failed/stuck/review-needed/contested/blocked groups;
- clear explanatory copy;
- no browser mutation.

### M20-P4.5: Knowledge Map And Relationships

Make wiki navigation graph-like without adding a graph database.

Candidate scope:

- related pages and tags rendered as links;
- backlinks by reverse scan;
- source/planning/provenance/supersession links;
- browse grouped by knowledge shape;
- orphan detection as read-only cleanup hint if cheap.

### M20-P4.6: Recent Insights And Log Rendering

Make `wiki/log.md` and durable activity useful to humans.

Candidate scope:

- render log as a first-class web surface;
- combine explicit log entries with durable run/planning/source events;
- avoid filesystem mtime as sole ordering source;
- no per-user "last seen" state.

## Non-Goals To Preserve

The reviewer set was unusually aligned on what not to do:

- no hosted product;
- no auth/user accounts;
- no collaborative editor;
- no database-backed cockpit;
- no hidden cache;
- no background worker or watcher;
- no mandatory GitHub or external API dependency;
- no complex SPA requirement;
- no browser mutation as the first answer;
- no automatic web-triggered AI summarization;
- no per-user state;
- no source-of-truth migration out of local git-tracked files;
- no replacement of CLI workflows.

## Open Questions For The Design PR

The design/spec PR should resolve these questions explicitly:

1. What exact identity fallback cascade should be normative?
2. Should optional `project:` config be introduced now, later, or only documented as future?
3. Which cockpit panes are required in v1 and which are deferred?
4. Should page-detail/project-identity ship together or as separate implementation slices?
5. What exact statuses count as "attention" under current schemas?
6. How should stale/freshness signals map to existing fields?
7. Which relationship links are cheap enough for request-time rendering?
8. Should `splendor cockpit summary` be part of the first read-model implementation or a later CLI
   parity slice?
9. What raw table/detail modes must remain available for each route?
10. What fixture should represent a realistic high-knowledge workspace for acceptance tests?

## Final Recommendation

Proceed with a new explicit M20-P4 track for human operator cockpit and wiki navigation. Make the
first PR in that track a docs/design/spec/roadmap contract, not an implementation. In that design,
commit to a derived read-model architecture, deterministic project identity, human-first page detail
layout, roadmap-style planning, attention/health interpretation, relationship navigation, and
recent insights/log rendering.

For implementation, fix page detail metadata and project identity before attempting a broad cockpit.
Those two changes are narrow, visible, and directly address the user's dogfood pain without adding
new state or weakening Splendor's CLI-first model.

The larger product insight is that Splendor should not make humans read the machinery first. The
machinery is good and should remain intact. The missing layer is a local, deterministic, traceable
story about the project built from that machinery.
