Basis: this review uses the supplied context brief, current web UI architecture map, existing contract excerpts, context-pack README, and review template.

# 1. Core thesis

Splendor’s human web/wiki layer should become a **local operator cockpit for repository knowledge**, not a raw state browser.

The current CLI-first, agent-oriented, deterministic, file-in-git model remains the product center. The web layer should be an additive read-only comprehension surface that translates existing Splendor files into human answers:

* What project am I looking at?
* What does the knowledge base know?
* What is current, next, blocked, stale, contested, or review-needed?
* What changed recently?
* Which pages, sources, plans, runs, and issues are connected?
* Where should a human operator look next?

The product problem is not the FastAPI stack, server-rendered HTML, or local architecture. Those are mostly correct. The product problem is that the UI currently exposes records instead of interpreting them. It shows Splendor’s internal state, but not the project’s operational meaning. The architecture map confirms the current UI is a read-only local FastAPI app with routes for home, status, planning, runs, queue, sources, browse, documents, and search; that is a good substrate, but its information architecture is still record-centric.

The right product framing:

> Splendor CLI is the deterministic operating surface.
> Splendor web is the local human comprehension surface.
> Splendor wiki is the durable, reviewable project memory.

# 2. Current gaps and failure modes

## 2.1 The UI does not identify the actual project

A page titled “Splendor” is product branding, not workspace orientation. For a real target such as SynthBanshee, the operator needs to see:

> SynthBanshee
> Local Splendor knowledge workspace
> Repository path / branch / last knowledge activity
> One-line project summary

Without this, the UI feels like a generic admin console, not a project wiki.

## 2.2 The home page confuses counts with value

Counts are useful only after orientation. “12 pages, 4 planning records, 3 sources, 2 runs” does not answer any operator question. The home page needs a narrative hierarchy:

1. What this project is.
2. What work is active.
3. What needs attention.
4. What changed recently.
5. What knowledge exists.
6. Where to inspect next.

The current brief explicitly says the home page does not answer these questions for the dogfood project.

## 2.3 Planning is exposed as storage, not roadmap

The current planning page lists durable records by kind with title, ID, status, detail, and path. That is useful for auditability, but it is not how humans understand work. A human needs grouping:

* Current milestone.
* Active tasks.
* Next tasks.
* Blockers.
* Open decisions.
* Open questions.
* Completed or historical work.

Long IDs and paths should remain available, but they should not dominate the primary view.

## 2.4 Run, queue, and status pages expose internals without interpretation

Current pages show counts, IDs, job names, attempts, payloads, paths, and raw state. That is good for debugging, but poor for operator comprehension.

The operator needs to know:

* Is the knowledge base healthy?
* Are there failed or stuck jobs?
* Did the latest ingest change anything important?
* Which pages or sources were affected?
* Is any source stale?
* Does a failure require human review, CLI retry, or no action?

The existing status/runs/queue pages should be reframed as “knowledge health” and “recent system activity,” with raw tables demoted.

## 2.5 Wiki detail pages violate the human-first contract

The existing contract says the web UI should make generated versus maintained pages visible without requiring raw frontmatter inspection.

The current detail view does the opposite: it puts a large metadata/JSON block before the readable page body. That is a product bug, not just a cosmetic issue. It tells the human that Splendor is primarily for machines, even when viewing the human wiki.

## 2.6 Weak page linking prevents knowledge navigation

Splendor already has useful metadata: `related_pages`, `tags`, `source_refs`, `generated_by_run_ids`, `issue_refs`, `pr_refs`, `supersedes`, `superseded_by`, `contradictions`, review state, and authority fields. The schema excerpts show that much of the relationship data already exists.

The web UI should turn that into navigation:

* Related pages.
* Backlinks.
* Source-backed evidence.
* Planning records connected to a topic.
* Pages requiring review.
* Pages superseded by newer pages.
* Contradictory or contested pages.

Right now those relationships exist mostly as metadata, not as operator-facing paths through the wiki.

## 2.7 High-knowledge projects amplify the failure

For a code/research repository, the operator is not browsing casual notes. They are trying to recover project state across code, research, generated summaries, planning records, open questions, and agent handoffs.

A flat table UI fails in this setting because:

* the operator does not know which artifacts are authoritative;
* generated pages may look equal to maintained synthesis;
* old decisions may look current;
* stale source summaries may look reliable;
* failed runs may look like noise;
* open questions may be buried as records;
* recent insights are not surfaced as learning.

# 3. Proposed human operator experience

## 3.1 Home page becomes the operator cockpit

Route: `/`

The home page should stop being a count dashboard and become a cockpit.

Recommended layout:

```text
[Project identity]
SynthBanshee
Local Splendor wiki for this repository
One-line project summary
Workspace path · git branch · last Splendor activity · read-only local UI

[What this project is]
2–4 sentence project brief, derived from configured project profile, wiki/index.md, or README.

[Current work]
Current milestone
Active task(s)
Next unchecked task(s)
Blocked/gated follow-ons
Open decisions/questions

[Needs attention]
Review-needed pages
Contested pages
Stale/generated pages
Failed or stuck queue items
Recent failed runs
Unanswered planning questions

[Recent insights]
Latest wiki/log.md entries
Recently generated summaries
Recently changed planning state
Recent source ingest outcomes

[Knowledge map]
Core maintained pages
Generated source-summary pages
Topic clusters/tags
Important sources
Search box

[Inspect next]
3–7 deterministic next links
```

The cockpit should have a clear empty-state version for sparse workspaces, but a populated real workspace should not feel sparse.

Example cockpit copy:

```text
This is the local Splendor workspace for SynthBanshee. It contains maintained project wiki pages,
generated source summaries, planning records, source manifests, and durable run/queue state stored
as reviewable files in this repository.

Start with Current Work to understand what is active, Needs Attention to find review or failure
signals, and Knowledge Map to browse maintained and generated project knowledge.
```

## 3.2 Project identity and workspace orientation

Add a project identity block everywhere, at least in the header.

Derivation priority:

1. Explicit config field, for example `project.display_name`.
2. `wiki/index.md` H1.
3. README H1.
4. Repository directory name.

Optional config:

```yaml
project:
  display_name: SynthBanshee
  one_line_summary: Local synthesis/research workspace for SynthBanshee development.
  operator_entrypoint: wiki/index.md
  primary_roadmap: wiki/roadmap.md
  important_pages:
    - wiki/architecture.md
    - wiki/current-work.md
```

Header example:

```text
SynthBanshee
Splendor local wiki · read-only · repository state
```

Footer or secondary header:

```text
Workspace: /path/to/repo
State source: local files only
Mutations: use Splendor CLI
```

This preserves Splendor’s local-first model while making the target project primary.

## 3.3 Planning becomes roadmap/current-work view

Route: `/planning`

Default view should be a human roadmap, not tables.

Recommended groups:

```text
Current
- active tasks
- active milestone
- current handoff target

Next
- ready tasks
- unchecked follow-ons

Blocked / gated
- blocked tasks
- gated follow-ons
- missing decisions
- unresolved questions

Decisions needed
- pending decisions
- decision records without outcome

Questions
- open questions grouped by project area

Completed / historical
- recently completed
- archived/historical context
```

Each row/card should show:

```text
Title
Human summary or detail
Status badge
Why it matters / current note
Related wiki pages
Related source/manifests if any
Record path and ID collapsed under “technical details”
```

The raw record table should remain available as:

* `/planning?view=table`
* or a collapsed “Raw planning records” section
* or `/planning/table`

Do not remove raw state. Demote it.

## 3.4 Open issues and trouble spots

Add route: `/attention`

This should be the operator’s review queue, derived from existing local state.

Attention item types:

| Type                          | Source                                    | Example operator meaning                    |
| ----------------------------- | ----------------------------------------- | ------------------------------------------- |
| Review needed page            | wiki frontmatter                          | Human should validate or finalize this page |
| Contested page                | `review_state: contested`, contradictions | Conflicting evidence exists                 |
| Stale page/source             | freshness metadata                        | Knowledge may be outdated                   |
| Failed run                    | run record                                | Recent operation failed                     |
| Stuck/failed queue item       | queue record                              | CLI intervention may be needed              |
| Blocked task                  | planning record                           | Work cannot proceed without dependency      |
| Open decision                 | planning decision record                  | Project direction unresolved                |
| Open question                 | planning question record                  | Research/implementation uncertainty         |
| Superseded page               | page metadata                             | Better current page exists                  |
| Source without linked summary | source manifest/status                    | Ingest or linking incomplete                |

Each attention item should include:

```text
Severity: info / warning / critical
Kind: review-needed / failed-run / blocked-task / contested-page
Title
One-sentence explanation
Why this matters
Primary link
Related links
CLI hint when relevant
```

Example:

```text
Contested page: wiki/topic/synthesis-pipeline.md
This page has conflicting source evidence and should not be treated as settled.
Inspect page · View source summaries · View contradictions
```

## 3.5 Recent insights and change log

Add route: `/recent`

This should not be a raw run log. It should combine durable local evidence into a human activity feed.

Sources:

* `wiki/log.md`
* recent run records
* generated page timestamps
* planning record status changes, if recorded
* recent query records, if already persisted
* source ingest records

Recommended groups:

```text
Insights
- human-readable log entries
- query results filed back into wiki
- synthesis follow-ups

Knowledge generation
- generated source summaries
- updated maintained pages
- pages requiring review

System activity
- recent ingests
- rebuild-index events
- failed/succeeded runs
```

In first pass, derive only from explicit durable timestamps in records/frontmatter/log entries. Avoid filesystem mtime as a primary signal because it is not a stable git-reviewed fact.

A useful later convention:

```markdown
## 2026-05-08 — SynthBanshee retry findings

Type: insight
Related pages: wiki/hocr-retry-findings.md, wiki/current-work.md
Related tasks: task:hocr-retry-acceptance

The v0.5.2 retry evidence suggests that current-work handoff ranking needs explicit authority
classification before further retry automation.
```

This remains readable markdown, but gives the renderer enough structure to classify entries.

## 3.6 Wiki browsing becomes a knowledge map

Route: `/browse`

Replace the flat document list as the default with a knowledge map.

Sections:

```text
Maintained synthesis pages
Generated source summaries
Planning pages
Review-needed pages
Contested pages
Recently updated pages
Topic clusters
Sources
```

Navigation dimensions:

* kind;
* status;
* review state;
* authority role;
* tags;
* source references;
* related pages;
* backlinks;
* planning links;
* generated versus maintained.

Recommended behavior:

* Keep cheap metadata reads for the top-level browse view.
* Avoid parsing every markdown body unless needed.
* Show flat list as secondary “All documents” mode.
* Add search within the map.

Example page card:

```text
Current Work Authority Model
Maintained synthesis · reviewed · current
Tags: planning, handoff, authority
Related: M20 roadmap, hocr retry findings, suggest-next
Sources: 3
Open planning items: 1
```

## 3.7 Page detail layout becomes human-first

Route: `/documents/{document_path}`

Recommended structure:

```text
[Title]
Maintained topic page · reviewed · current · confidence high
Generated from / Maintained by human if known
Last reviewed · Last generated if relevant

[Optional warning banner]
This page is contested / stale / superseded / review-needed.

[Readable markdown body]

[Related navigation]
Related pages
Backlinks
Source summaries
Planning records
Issues/PR refs if present
Supersedes / superseded by
Contradictions

[Provenance]
Source refs
Generated run IDs
Review history summary

[Technical details]
Collapsed raw frontmatter / parsed metadata / path / page_id
```

Hard rule:

> The readable markdown body should appear before full raw metadata.

Metadata should be summarized as badges at the top and exposed fully only in a collapsed technical section.

Example header:

```text
Current Work Authority Model

Maintained wiki page · reviewed · current-work authority · local deterministic evidence
Last reviewed: 2026-05-08 · Related tasks: M20-P1.6
```

For generated pages:

```text
Generated source summary · review needed · source-backed
Generated by run: ingest-20260508-...
```

## 3.8 Run, queue, and status pages get explanations

### `/status`: knowledge health

Reframe as:

```text
Knowledge health
- Healthy
- Needs attention
- Recent activity
- Source coverage
- Review state
```

Each count should explain significance.

Bad:

```text
review_needed: 4
```

Better:

```text
4 pages need review
Generated or changed pages exist that have not been human-reviewed.
View review queue
```

### `/runs`: recent local work history

Primary columns:

```text
Meaning
Outcome
When
Affected sources/pages
Warnings/errors
Technical run ID
```

Example:

```text
Ingested source manifest: docs/hocr_retry.md
Succeeded · 3 pages generated · 1 page needs review
Run ID: ...
```

### `/queue`: pending local jobs

Primary groups:

```text
Ready
Running/leased
Failed
Retry scheduled
Done/recent
```

Add stable explanatory copy:

```text
The queue is durable local filesystem state. This page does not start, retry, or mutate jobs.
Use the Splendor CLI for queue operations. Failed or stale jobs are shown here so a human can decide
whether to inspect, retry, or ignore them.
```

The current pages already have read-only notes, but they mostly explain mutation behavior, not operator meaning. The architecture map identifies this exact gap.

## 3.9 Source detail page should become a trace view

Route: `/sources/{source_id}` is already one of the more useful views because it connects manifests, generated pages, latest ingest run, and affected synthesis-page suggestions. Keep that direction.

Improve it with:

```text
Why this source matters
Source type / path / freshness
Generated summaries
Maintained pages affected
Open review items caused by this source
Latest ingest outcome
Related planning records
Technical manifest details collapsed
```

# 4. Architecture and state model changes

## 4.1 First principle: web UI is a derived read model

The web app should remain read-only and derive its display from committed local files.

Add pure builder functions, for example:

```python
build_operator_overview(workspace_root) -> OperatorOverview
build_attention_items(workspace_root) -> list[AttentionItem]
build_knowledge_map(workspace_root) -> KnowledgeMap
build_page_relationships(workspace_root, page_path) -> PageRelationships
build_recent_activity(workspace_root) -> list[RecentActivityItem]
```

These functions should:

* read existing config, wiki pages, planning records, source manifests, run records, queue records, and log files;
* return deterministic data structures;
* sort deterministically;
* not write files;
* not use hidden caches;
* not require network access;
* not require background workers.

The current app already has the right base constraints: read-only local FastAPI, no SPA, no database, no background worker, server-rendered HTML.

## 4.2 What should be derived from existing files

| Operator feature                    | Derive from                                                               |
| ----------------------------------- | ------------------------------------------------------------------------- |
| Project name fallback               | config, `wiki/index.md`, README, repo dirname                             |
| Project summary fallback            | config, `wiki/index.md` intro, README intro                               |
| Page counts                         | existing wiki/planning scans                                              |
| Maintained/generated distinction    | page frontmatter, source-summary paths/kinds                              |
| Review-needed/contested/stale pages | wiki frontmatter and status records                                       |
| Roadmap groups                      | planning records plus current-work authority classifier when available    |
| Open decisions/questions            | planning decision/question records                                        |
| Failed/stuck work                   | queue and run records                                                     |
| Recent activity                     | `wiki/log.md`, run records, explicit record timestamps                    |
| Knowledge clusters                  | tags, kind, authority role, related pages, source refs                    |
| Backlinks                           | reverse scan of `related_pages`, wiki links, planning refs                |
| Source trace                        | source manifests, generated pages, run records, affected-page suggestions |

## 4.3 What should become new structured state or schema

Keep this minimal.

Recommended additions:

### Project identity in config

```yaml
project:
  display_name: SynthBanshee
  one_line_summary: Local code-and-research knowledge workspace.
  description_path: wiki/index.md
  primary_roadmap: wiki/roadmap.md
  operator_entrypoint: wiki/index.md
```

### Optional page summary field

Useful for cards and search results:

```yaml
summary: One-sentence human summary of this page.
```

### Optional planning display fields

```yaml
summary: One-sentence human summary.
operator_note: Why this matters now.
priority: high | normal | low
blocked_by:
  - task:...
related_pages:
  - wiki/current-work-authority-model.md
```

### Optional log entry convention

Keep `wiki/log.md` markdown-readable, but allow headings or small metadata blocks that classify entries:

```text
Type: insight | ingest | planning | review | repair
Related pages:
Related tasks:
```

Do not create a separate operator database or hidden state store.

## 4.4 What should remain markdown-only

Keep these as markdown:

* project narrative;
* wiki topic bodies;
* long-form research notes;
* roadmap prose;
* insight narratives;
* human decision rationale;
* `wiki/index.md`;
* `wiki/log.md`.

Markdown is the right medium for human meaning. Structured records are the right medium for machine state. The operator cockpit should combine both without converting all narrative into schema.

## 4.5 What should remain raw structured state

Keep these as existing durable records:

* source manifests;
* run records;
* queue records;
* planning records;
* status records;
* generated source-summary frontmatter;
* review/authority metadata.

The web UI should interpret these records, not replace them.

## 4.6 How to preserve deterministic filesystem state and git review

Rules:

1. GET requests must not write files.
2. The web server must not create caches.
3. The web server must not call remote APIs.
4. The web server must not start jobs.
5. All mutations remain explicit CLI operations.
6. Any future generated operator index must be created only by an explicit CLI command.
7. Generated files, if introduced, must be committed/reviewable and reproducible.
8. Sorting must be stable and path/timestamp/status based.
9. Missing optional fields must degrade gracefully.

A future explicit CLI command could exist:

```bash
splendor wiki rebuild-operator-index
```

But that should be deferred. First implementation should compute read-only views on request.

## 4.7 Relationship to current-work authority model

The current-work authority model is specified for CLI handoff correctness, using local deterministic inputs and no database/background/hosted dependencies.

Do not duplicate it in the web layer.

Instead:

* implement current-work classification once;
* expose it to CLI handoff and web cockpit;
* let `/planning` and `/` consume the same classifications;
* fallback to simple planning status grouping when the classifier is unavailable.

This makes the human cockpit and agent handoff converge around the same local evidence.

# 5. Product spec changes

Add a new product-spec section:

```markdown
## Human Operator Cockpit And Wiki Navigation

Splendor's local web UI is a read-only human comprehension layer over deterministic local
repository state. It does not replace the CLI, does not become the source of truth, and does not
introduce hidden persistence. Its job is to help a human operator understand the project wiki,
planning state, source coverage, review needs, and recent local activity.

The home page must identify the target project and answer:
- What is this project?
- What knowledge has Splendor built?
- What work is current or next?
- What is blocked, stale, contested, failed, or review-needed?
- What changed recently?
- What should the operator inspect next?
```

Add subsection:

```markdown
### Project Identity

Every web page should display the target project identity. The display name is resolved from
explicit config, then wiki/index.md, then README, then repository directory name. Splendor branding
must be secondary to the project name inside a workspace.
```

Add subsection:

```markdown
### Home Cockpit Contract

The home page is not a count dashboard. It is the operator's entry point. It should show project
summary, current work, attention items, recent insights, knowledge map summary, and next inspection
links. Counts may appear only as supporting context.
```

Add subsection:

```markdown
### Human-First Page Detail Contract

Markdown body content must be visible before full raw metadata. Page detail views should summarize
metadata as badges and warnings, then render readable content, then show relationships and
provenance, with full technical metadata collapsed or demoted.
```

Add subsection:

```markdown
### Attention Model

The web UI should derive attention items from local files: review-needed pages, contested pages,
stale pages, failed runs, stuck queue records, blocked tasks, open decisions, open questions, and
source coverage gaps. Each item should include a human explanation, primary link, and relevant
technical details.
```

Add subsection:

```markdown
### Planning/Roadmap Rendering

Planning records remain structured markdown-backed objects. The default web planning view should
group records by operator meaning: current, next, blocked/gated, decisions needed, open questions,
completed, and historical. Raw record tables remain available but are not the primary view.
```

Add subsection:

```markdown
### Status, Runs, And Queue Interpretation

Status, run, and queue pages should explain what the displayed state means for the knowledge
workflow. Run IDs, queue payloads, and paths are technical details. The primary view should group
state by health, attention, affected artifacts, and recommended inspection path.
```

Add subsection:

```markdown
### Relationship Navigation

The web UI should derive related pages, backlinks, source links, planning links, supersession links,
and contradiction links from existing markdown/frontmatter records. The first pass is read-only and
does not auto-write missing links.
```

# 6. Roadmap changes

Add an explicit product track:

```text
M20-P4: Human operator cockpit and wiki navigation
```

Suggested slices:

## M20-P4.0 — Docs/design-first operator contract

Deliverables:

* product-spec section for human operator cockpit;
* architecture note for derived read models;
* page layout contracts;
* route-level UX notes;
* acceptance criteria;
* no implementation except maybe fixtures.

This should happen before mutating web review workflows. The current roadmap has advanced search, handoff, mutating web review, and integrations, but no explicit operator cockpit track.

## M20-P4.1 — Project identity and cockpit home MVP

Implement:

* project display name resolution;
* project summary resolution;
* `build_operator_overview`;
* home sections for current work, needs attention, recent activity, and knowledge map;
* no writes;
* no new persistent state required.

This is the highest impact first implementation slice.

## M20-P4.2 — Human-first page detail layout

Implement:

* body before full metadata;
* status/review/authority badges;
* generated/maintained banner;
* warning banners for contested/stale/review-needed/superseded;
* collapsed technical metadata;
* related/provenance section.

This directly fixes the most visible wiki-detail failure.

## M20-P4.3 — Planning roadmap view

Implement:

* grouped roadmap view;
* active/next/blocked/done/question/decision sections;
* IDs and paths demoted;
* raw table retained.

Use current-work authority classification if available; otherwise use status-based fallback.

## M20-P4.4 — Attention and health interpretation

Implement:

* `/attention`;
* status page rewritten around health/attention;
* failed/stale/review-needed/contested grouping;
* links to pages, sources, runs, queue records;
* explanatory copy.

## M20-P4.5 — Knowledge map and page relationships

Implement:

* browse clusters;
* related pages;
* backlinks;
* source links;
* planning links;
* supersession/contradiction navigation.

Avoid auto-mutating pages. Show missing-link suggestions only as read-only hints if needed.

## M20-P4.6 — Recent insights and durable log rendering

Implement:

* `/recent`;
* parse `wiki/log.md` entries;
* combine with recent run and planning records;
* classify insight/ingest/planning/review/system events where explicit.

## Explicitly defer

* browser editing;
* browser acceptance/review mutations;
* source-add form expansion;
* hosted collaboration;
* auth;
* databases;
* persistent vector index;
* background summarization;
* mandatory GitHub API;
* complex SPA;
* automatic AI-written cockpit summaries on page load.

# 7. Acceptance criteria

## Slice P4.1: Project identity and cockpit

Acceptance criteria:

* `/` displays the target project name, not only “Splendor.”
* If `project.display_name` exists, it is used.
* If config is absent, a deterministic fallback is used.
* Home page includes sections named or equivalent to:

  * Project summary;
  * Current work;
  * Needs attention;
  * Recent activity or insights;
  * Knowledge map;
  * Inspect next.
* Home page links to at least one wiki page, one planning view, and one status/attention view when those records exist.
* Counts are present only as supporting context.
* GET `/` creates no files and mutates no records.
* Sparse workspaces still render a useful empty state.

## Slice P4.2: Page detail

Acceptance criteria:

* Markdown body appears before full raw metadata.
* Full parsed metadata is collapsed or moved below the body.
* Page header shows human badges for kind/status/review state.
* Generated pages are visually distinguishable from maintained pages.
* Review-needed, contested, stale, and superseded pages show warning banners.
* Related pages and provenance links appear when metadata exists.
* Raw metadata remains accessible for debugging.

## Slice P4.3: Planning roadmap

Acceptance criteria:

* `/planning` default view groups records by human meaning, not just by record kind.
* Active/current/next/blocked/completed/open-question/open-decision records are visually distinct.
* Long IDs and paths are not primary visual content.
* Raw table view remains available.
* Planning detail links still resolve to markdown documents.
* Missing optional planning fields do not break rendering.

## Slice P4.4: Attention/status

Acceptance criteria:

* `/attention` lists review-needed, contested, stale, failed, blocked, and open-question items when present.
* Each item has a one-sentence explanation and a primary inspection link.
* `/status` separates healthy state from attention-needed state.
* Failed runs and queue items are grouped by operator severity.
* Run IDs and payloads are still accessible but secondary.
* No queue/run mutation is possible from these pages.

## Slice P4.5: Knowledge map/interlinking

Acceptance criteria:

* `/browse` default view groups pages by kind/status/tag or equivalent useful clusters.
* Maintained and generated pages are distinguishable.
* Detail pages show outgoing related pages.
* Detail pages show backlinks derived from local wiki metadata/links.
* Source-summary pages link to relevant source detail pages.
* Missing relationship metadata does not produce broken UI.

## Slice P4.6: Recent insights

Acceptance criteria:

* `/recent` shows durable local activity from `wiki/log.md` and run records.
* Insight/log entries are visually distinct from low-level system activity.
* Recent failed activity links to attention/status.
* Recent generated pages link to page detail.
* No filesystem mtime is required as the sole ordering source.

# 8. Tests to add

## Unit tests

Add tests for pure builders:

```text
test_project_identity_prefers_config
test_project_identity_falls_back_to_wiki_index
test_project_identity_falls_back_to_readme
test_project_identity_falls_back_to_repo_name

test_operator_overview_groups_current_work
test_operator_overview_extracts_attention_items
test_operator_overview_handles_empty_workspace
test_operator_overview_sorting_is_deterministic

test_attention_items_include_review_needed_pages
test_attention_items_include_contested_pages
test_attention_items_include_failed_runs
test_attention_items_include_failed_queue_records
test_attention_items_include_blocked_tasks

test_page_relationships_include_related_pages
test_page_relationships_include_backlinks
test_page_relationships_include_source_refs
```

## Route/rendering tests

```text
GET / renders project name
GET / renders operator cockpit sections
GET / does not render only count cards in populated fixture

GET /documents/{path} renders body before technical metadata
GET /documents/{path} collapses raw metadata
GET /documents/{path} shows generated/maintained badge
GET /documents/{path} shows contested warning

GET /planning groups active_next_blocked_done
GET /planning preserves raw table access

GET /attention renders failed run with explanation
GET /attention renders review-needed page with link

GET /status renders health explanation copy
GET /runs demotes run IDs behind human meaning
GET /queue explains failed/stale queue state
```

## Determinism and no-mutation tests

```text
GET routes do not create files
GET routes do not modify existing files
overview output stable across repeated calls
overview output stable under unordered input records
no network calls are made
no background tasks are started
```

## Fixture tests

Create a small `SynthBanshee-like` fixture workspace with:

* project config;
* `wiki/index.md`;
* one maintained page;
* one generated source summary;
* one review-needed page;
* one contested page;
* one active task;
* one blocked task;
* one open question;
* one failed run;
* one failed queue item;
* one source manifest;
* one `wiki/log.md` insight.

This fixture should drive most operator-cockpit acceptance tests.

# 9. Non-goals and risks

## Non-goals

Do not do these in the operator-cockpit track:

* hosted Splendor;
* multi-user collaborative editor;
* auth system;
* database-backed app;
* hidden cache;
* mandatory external GitHub/GitLab API;
* background worker;
* browser-based mutation as first step;
* page editing in browser;
* job retry/start buttons;
* automatic web-triggered AI summarization;
* complex SPA;
* replacing CLI workflows;
* moving source of truth out of git-tracked local files.

## Risks

### Risk: the cockpit becomes another stale artifact

Mitigation: first pass derives from existing durable files at request time. Human narrative belongs in `wiki/index.md`, README, or explicit markdown pages.

### Risk: schema creep

Mitigation: add only a few optional fields: project identity, page summary, planning summary/operator note. Everything must degrade gracefully.

### Risk: misleading severity heuristics

Mitigation: label derived signals clearly. Use conservative severity names: `needs review`, `failed`, `blocked`, `stale`, `contested`. Avoid pretending to know business priority unless planning records say so.

### Risk: overfitting to SynthBanshee

Mitigation: use SynthBanshee as the dogfood fixture, but define generic operator questions and generic local state derivations.

### Risk: performance regression from parsing too much markdown

Mitigation: keep cheap metadata scans for index views. Parse full markdown only for detail, search, or bounded relationship derivation.

### Risk: duplicating current-work authority logic

Mitigation: expose one local deterministic classifier used by both CLI handoff and web cockpit.

### Risk: UI copy becomes verbose noise

Mitigation: use short explanation blocks. Every explanation should answer “what does this mean?” or “why should I care?”

# 10. Concrete wording snippets for Splendor docs

## Product spec snippet

```markdown
## Human Operator Cockpit

The local web UI is Splendor's human comprehension layer. It is read-only by default and derives its
views from deterministic local repository files. It does not replace the CLI, does not introduce a
database or hidden cache, and does not become a hosted collaboration product.

The cockpit should help a human operator answer:
- What project is this?
- What has Splendor learned about it?
- What work is current, next, blocked, or historical?
- What pages, sources, runs, or planning records need attention?
- What changed recently?
- Which wiki pages and source summaries should I inspect next?

Counts and raw records may be shown, but they are supporting evidence. The primary web experience
should be project orientation, roadmap comprehension, attention triage, knowledge navigation, and
provenance inspection.
```

## Home page contract snippet

```markdown
### Home Page Contract

The home page must identify the target project before it identifies Splendor. It should show a
project summary, current work, attention items, recent activity, knowledge-map summary, and
recommended inspection links. A count-only dashboard is not sufficient for a populated workspace.
```

## Page detail contract snippet

```markdown
### Page Detail Contract

Wiki detail pages must render human-readable markdown content before full technical metadata.
Frontmatter and parsed metadata should be summarized as badges, warnings, provenance links, and
relationship links. Full raw metadata remains available in a collapsed technical section for agents,
debugging, and review.
```

## Planning contract snippet

```markdown
### Planning View Contract

Planning records remain durable structured files, but the default web view should present them as a
roadmap. Records should be grouped by operator meaning: current, next, blocked, decisions needed,
open questions, completed, and historical. Raw IDs, paths, and record payloads remain inspectable
but should not dominate the primary planning view.
```

## Attention model snippet

```markdown
### Attention Model

The web UI should derive a read-only attention list from local files. Attention items include
review-needed pages, contested pages, stale pages, failed runs, failed or stale queue records,
blocked tasks, open decisions, open questions, and source coverage gaps. Each item should explain
what it means, why it matters, and where to inspect next.
```

## Architecture snippet

```markdown
### Operator Read Model

Operator views are built from pure read-model functions over existing workspace files. GET requests
must not write files, create caches, start jobs, call hosted services, or depend on external APIs.
Any future generated operator index must be produced by an explicit CLI command and stored as
reviewable filesystem state.
```

## Roadmap snippet

```markdown
### M20-P4: Human Operator Cockpit And Wiki Navigation

Goal: make the local web UI useful as a human operator cockpit while preserving Splendor's
CLI-first, local-first, git-native architecture.

Slices:
- P4.0: docs/design contract for operator cockpit and read models.
- P4.1: project identity and cockpit home MVP.
- P4.2: human-first page detail layout and metadata demotion.
- P4.3: planning roadmap view.
- P4.4: attention and health interpretation.
- P4.5: knowledge map, related pages, and backlinks.
- P4.6: recent insights and log rendering.

Deferred: browser mutation, hosted collaboration, database-backed state, hidden caches, background
workers, mandatory external APIs, and complex SPA behavior.
```

The main product realignment is simple: keep Splendor’s deterministic machinery, but stop making the human operator read the machinery first. The web/wiki layer should present the project, the work, the trouble, the learning, and the navigation graph first; raw records remain available underneath.
