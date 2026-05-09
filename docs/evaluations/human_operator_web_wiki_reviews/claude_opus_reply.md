# Splendor Human Operator Layer: External Review

I've read the full pack. This is a serious product question and the critique is well-formed: the issue is not the FastAPI choice or the file model, it's that the web UI currently exposes *state* without ever constructing *meaning*. Below is a strong outside view, organized to your prompt's structure.

---

## 1. Core thesis

**Splendor's web UI should stop being a viewer onto state files and become a derived "operator cockpit" — a read-only narrative layer whose job is to answer, on arrival, the six questions a returning human asks: *what is this project, where are we, what's stuck, what's new, what's the knowledge shape, what should I look at next.*** The cockpit is not a new runtime, not a new database, not a new authority. It is a deterministic projection — a *read-model* — computed at request time from the same git-tracked files the CLI already produces.

The right framing is additive. You currently have four tracks: agent CLI, deterministic state, review/lint, schema. You need a fifth: **operator comprehension.** Its product contract is different from the others — it is allowed to be *interpretive*, *opinionated about salience*, and *narrative* — because its consumer is a human being holding a coffee, not an agent executing a deterministic plan. The other tracks must remain literal; this one must not.

A useful slogan for the team: **the CLI tells the truth; the cockpit tells the story.** Both are derived from the same files.

The cockpit must obey three invariants to coexist with the rest of Splendor: (a) every cockpit pane must be reproducible from current workspace files alone — no hidden cache, no rolling state, no "last seen" memory; (b) every interpretive judgment ("this is stale", "this needs review", "this is current work") must be traceable back to a specific file or field a reviewer can see in git; (c) the cockpit may *re-rank and re-summarize* but must never *contradict* the underlying records. If the cockpit calls something stale, the user must be able to click through to the field and date that proves it.

---

## 2. Current gaps and failure modes

I'll be concrete because abstraction won't help you here.

**Gap 1 — No project identity.** The header reads "Splendor", not "SynthBanshee — a Splendor workspace". A wiki that doesn't name the project it documents fails the very first cognitive test a returning operator runs. This is one config value (`project.name`, `project.tagline`, `project.summary_page`) plus a header template change. It is embarrassingly small and embarrassingly important.

**Gap 2 — Counts are not comprehension.** "Wiki pages: 47" tells me nothing. The home page is the most-trafficked surface in the product and currently spends its entire screen real estate on four numbers I cannot act on. A returning operator does not ask "how many"; they ask "what changed, what's hot, what's broken, what did we learn." The cockpit needs to answer those four directly.

**Gap 3 — Planning is rendered as a database admin view.** Tables of (title, ID, status, path) are appropriate for a Django admin; they are wrong for a roadmap. Humans reason about plans in shapes — *active now, queued next, recently done, blocked on X, decided then, open questions* — not in alphabetized rows. The information *is in the files* (status, supersession, milestone refs, authority lifecycle); the UI just isn't projecting it into a narrative shape.

**Gap 4 — Page detail violates its own spec.** Section 26 of your spec says explicitly: *"users should not require raw frontmatter inspection."* The current `/documents/{path}` renders a JSON dump above the prose. This is not a small issue — it is a direct contract violation, and it's the single change that would most improve perceived quality the fastest. Frontmatter belongs in a collapsed "Technical details" disclosure at the bottom (or a sidebar), with a 3-4 chip summary at the top showing only the human-relevant facts: review state, freshness, authority, source count.

**Gap 5 — Pages are islands.** `related_pages`, `source_refs`, `supersedes`, `superseded_by`, `provenance_links`, `tags`, `contradictions` are all in the schema. None of them are visible as actual links in the rendered page. Backlinks are not computed. A wiki without dense interlinking is a folder of documents.

**Gap 6 — Status, runs, and queue have no narrative frame.** The current pages answer "what is in the file." The operator question is "is anything wrong?" These are different questions. A status page should lead with a green/yellow/red health summary computed from the same data, then show the table for those who want it.

**Gap 7 — No "since I was last here" surface.** The most valuable single thing for a returning operator is a chronological *log* keyed off git activity and run records: ingests since N days ago, pages whose review state flipped, planning items that closed, contradictions that appeared. `wiki/log.md` is specified but is not the cockpit's spine — it should be.

**Gap 8 — Search is stranded.** Search is a fine feature but it is not a substitute for navigation. A user who needs to search for an entry point has already failed to find one. Currently, with the home page hollow and `/browse` a flat list, search is doing the work that an index should do.

**Gap 9 — `wiki/index.md` and `wiki/log.md` are spec'd but unloved by the web UI.** The product spec already gestures at them as the human entry points. The web UI doesn't render them as the primary navigation. This is a missed alignment between the markdown contract and the rendering contract.

**Failure mode to name explicitly.** The current UI looks like it was built by reading the data model from the bottom up and rendering each table into a route. The cockpit must be built from the *operator's questions* downward — start with "what does a returning human need in 30 seconds" and work back to which fields answer it. This inversion is the actual product change. Tooling and architecture follow.

---

## 3. Proposed operator experience

I'll describe each surface concretely enough to spec.

**Home / Operator Cockpit (`/`)**

The home page is replaced with a single-screen cockpit organized into six panes, each of which is a derived read-model. Top-of-page is a project identity strip: project name, one-line tagline, a "last activity: 3 hours ago" timestamp from the most recent run or git commit, and a quick-stats row (sources, pages, open planning items) demoted to small text. Then six panes:

*Project at a glance.* A 2-3 sentence project summary pulled from a designated `wiki/index.md` lead paragraph or a configured summary page. If absent, render an empty-state with a CLI hint. This pane never shows counts.

*Roadmap snapshot.* The current milestone (latest non-completed `kind: milestone` planning record), its 1-3 active tasks, the next 2-3 queued tasks, and a tiny "recently done" tail (last 3-5 closed in the last 14 days). Each item is a link to its planning detail page. The point is shape, not exhaustiveness.

*Needs attention.* A merged list — capped at maybe 7 items — drawn from: pages with `review_state: contested` or `review_state: needs_review`, sources past freshness thresholds, queue records in failed/stuck states, contradictions detected, and planning items marked blocked. Each item names its concern in one human sentence ("Source `arxiv-2024-0142` ingest failed 2 days ago") and links through.

*Recent insights.* The last 5-10 entries from `wiki/log.md`, or, if that file is sparse, derived from recently-modified maintained synthesis pages plus newly-closed decisions. This is the "what did we learn / what changed" pane.

*Knowledge map.* A tag/topic cloud or cluster view derived from page tags and `related_pages` graphs. Even a flat list of the top 10-15 tags by page count, each linking to a tag-filtered browse, is enough for v1. The point is to communicate *shape* of the knowledge base.

*What to look at next.* This pane is optional in v1, and should reuse the current-work authority model when M20-P1.6 lands. Until then, leave it as a small "Suggested next" panel powered by `suggest-next`.

The cockpit must degrade gracefully. On a fresh workspace, every pane shows its own empty-state with a CLI hint ("`splendor wiki rebuild-index` to populate this view"). The cockpit must never look broken; it must look *quiet*.

**Roadmap / Planning view (`/planning`)**

Replace the four-table layout with a *swim-lane* view: Active, Next, Blocked, Recently done, Open questions, Decisions. Each lane shows cards (not rows) with title, one-sentence detail, status chip, and the relevant secondary chips (milestone, authority lifecycle, freshness). The current four tables remain reachable as `/planning/tasks`, `/planning/milestones`, etc., for users who want the raw view. Lane assignment is computed deterministically from existing fields: `status`, `authority_lifecycle`, `superseded_by`, `last_reviewed_at`. Document the assignment rule so it's reviewable. The page header should read "SynthBanshee Roadmap", not "Planning."

**Trouble spots (`/attention` or merged into status)**

A dedicated surface for the union of: contested pages, stale sources, failed runs, stuck queue items, planning blockers, and review-needed pages. Group by type, not severity, and within each type sort by recency. Each row gets a one-line plain-English explanation of *why* it's flagged, generated from a small templated rule per source field. This is the page an operator opens at 9am.

**Recent insights / Log (`/log`)**

Render `wiki/log.md` as the primary view, with a derived sidebar of automatically-detected events (new sources, run results, review-state flips, contradictions appearing) for the last 30 days, computed from run records and timestamps. Two columns: human-curated narrative on the left, machine-derived events on the right.

**Wiki / topic browsing (`/wiki`, `/wiki/{tag}`, `/browse`)**

`wiki/index.md` becomes the rendered face of `/wiki`. The current `/browse` becomes `/wiki/all` for the dump-everything view. Add `/wiki/tag/{tag}` for tag-filtered browsing. The browse index should call out: pages by section (from index.md), recently-modified pages, pages by review state, contested pages, and orphan pages (no inbound links — useful for cleanup).

**Page detail (`/documents/{path}`)**

The single highest-leverage change. New layout, top-to-bottom:

A small chip strip showing only review state, authority role, last reviewed/generated, and source count. The page title. The markdown body. A *related* sidebar (or footer on narrow viewports) showing: source pages this page is built from, pages this page links to (`related_pages`), pages that link to this one (computed backlinks), supersedes/superseded-by chains, contradictions if any, and tags. A collapsed "Technical details" disclosure at the bottom containing the full frontmatter JSON for those who need it.

The metadata block as it exists today must move. Not be removed — moved. The "agents need this" argument is real, but agents are reading the markdown file directly via the CLI; they are not consuming the rendered HTML.

**Status / Runs / Queue (`/status`, `/runs`, `/queue`)**

Each gets a "what this page is" preamble — two or three sentences — and a health summary at the top. Status leads with: "All clear" / "N items need attention" with the items named. Runs leads with the most recent run, what it did in human terms ("Re-ingested 3 sources, generated 2 summary pages"), and any failures. Queue leads with stuck/failed items, then pending, then idle. The tables remain below, unchanged. This is mostly a layout and templating change with a small rules engine for the health summary.

**Source detail (`/sources/{id}`)**

This page is closest to right already. Add a one-paragraph "what this source is and why it's in the project" block at the top, sourced from the manifest's description field (add one to the schema if it's missing). Add explicit "next action" copy when freshness/run-state warrants it ("This source has not been re-ingested in 47 days; consider `splendor source ingest …`").

**Project identity and orientation**

Add a `project:` block to the workspace config: `name`, `tagline`, `summary_page` (path to a markdown file used as the "Project at a glance" pane), and optional `links` (repo, issue tracker, paper). Render `name` in the global header on every page. Render `tagline` on the home page. Use `summary_page` content (or a fallback) in the cockpit.

---

## 4. Architecture and state model changes

The discipline here is to do the *minimum* state-model change and lean heavily on derivation. Concrete recommendations:

**Derive everything you can.** The cockpit's six panes are all computable at request time from existing files: planning records have status fields, pages have review_state and timestamps, runs have outcomes, the log file already exists. Build a `splendor.cockpit.read_model` module — a set of pure functions that take the workspace root and return typed dataclasses. The web layer renders these. This module is also CLI-callable (`splendor cockpit summary`) which gives you a free, scriptable, agent-friendly view of the same projection. Same data, two renderings.

**Make backlinks deterministic and on-demand.** Computing backlinks by walking the wiki on each request is fine for workspaces of realistic size (hundreds to low thousands of pages). If it becomes slow, add a `splendor wiki rebuild-backlinks` command that writes a `state/backlinks.json` durable record — same pattern as `rebuild-index`. Do not introduce a daemon, watcher, or in-memory cache that survives requests.

**Add small, durable structured state where needed.** Two new structured records earn their keep:

`state/cockpit_health.json` — optional, written by `splendor health snapshot` if you want the health pane to be computable without re-walking everything. Fully derivable from existing state; the file is a cache, not a source of truth, and the CLI can rebuild it.

A `project:` config block in the workspace config (you already have config plumbing). This is not "new state" so much as "config Splendor should already have."

I would *not* introduce: a backlinks database, a vector index for the cockpit, a watcher, an event log beyond `wiki/log.md`, or any persistent cache that a fresh clone wouldn't reproduce.

**Markdown-only stays markdown-only.** `wiki/index.md`, `wiki/log.md`, the project summary page, and all wiki pages remain hand-edited or CLI-rewritten markdown. The cockpit *renders* them; it does not mutate them via the browser.

**Determinism contract for the cockpit.** Add to the spec: "Every cockpit projection must be a pure function of the current workspace tree. Two clones at the same git SHA must render identical cockpit views. The cockpit must not depend on wall-clock state outside what is recorded in files (run timestamps, frontmatter dates, git history)." This is the test contract you can write against.

**Read-only first.** No mutation in v1. Every "next action" affordance is a *displayed CLI command the user can copy*, not a button. ("Run `splendor source ingest arxiv-2024-0142`.") This is faithful to the spec's existing position and avoids opening the mutating-web track prematurely.

**No hosted dependencies.** All identity, summaries, and project metadata come from local config and local files. GitHub integration, when it lands, augments — never replaces — local state.

---

## 5. Spec changes

Concrete edits to `docs/splendor_product_spec.md`:

Add **Section 13.3 — Operator cockpit** alongside the existing 13.2 secondary-interface section. Define the cockpit as the human-facing projection layer, list its six panes, and assert the determinism contract above.

Expand **Section 26 — Local Web UI** with a "Page detail layout" subsection that explicitly states: page title and chip strip first; markdown body second; related/backlinks/sources sidebar third; raw frontmatter only inside a collapsed "Technical details" disclosure at the bottom. This codifies the existing intent and closes the contract violation.

Add a new **Section 12.4 — Project identity** specifying the `project:` config block (`name`, `tagline`, `summary_page`, optional `links`) and that all rendered surfaces must show project name. Make absence of `name` a `splendor lint` warning, not an error.

Update **Section 12.1 — wiki/index.md** to specify that the index file should contain a leading section usable as a "Project at a glance" summary, and that it's the canonical source for `/wiki` rendering.

Update **Section 12.2 — wiki/log.md** to specify it as the canonical recent-insights surface, and define a light append format that the log pane can parse for date/title extraction (without making it brittle — fall back to "render as-is" if the format isn't matched).

Add a **Read-Model Contract** section: pure functions, no caches surviving processes, request-time computation, optional durable rebuilt records following the existing `rebuild-index` precedent.

---

## 6. Roadmap changes

Add an explicit, named track to M20:

**M20-P4 — Human Operator Cockpit and Wiki Navigation.** Sized as roughly six PR slices, ordered roughly by leverage:

*M20-P4.0 — Design and spec slice.* Docs-only PR. Adds spec sections 13.3, 12.4, 26 layout changes, and the read-model contract. No code. This is the gating PR for the rest of the track and is small enough to review carefully. Land first.

*M20-P4.1 — Project identity and page detail layout.* Adds `project:` config block, header rendering across all routes, and the page-detail re-layout (chip strip, body, related sidebar, collapsed frontmatter). Highest user-perceived quality gain per line of code; ship this second. No new state required.

*M20-P4.2 — Cockpit home page (read-model v1).* Implements `splendor.cockpit.read_model` and replaces `/` with the six-pane cockpit. Fully derived; no new structured state. Includes a `splendor cockpit summary` CLI command rendering the same projection in plain text — this gives you both an agent-friendly view and a free integration test surface.

*M20-P4.3 — Roadmap swim-lane view and trouble-spots page.* Replaces `/planning` with the lane layout, adds `/attention`. Pure rendering changes plus a documented lane-assignment rule.

*M20-P4.4 — Wiki interlinking and backlinks.* Adds backlinks computation (request-time first, with optional durable rebuild command), tag-filtered browsing, and renders `wiki/index.md` as `/wiki`. The first slice that materially changes how pages connect.

*M20-P4.5 — Status/runs/queue narrative layer.* Adds health summaries and "what this page is" preambles, group-by-priority for runs and queue. Mostly templating with a small derivation rules module.

*M20-P4.6 — Log/insights surface.* Renders `wiki/log.md` as `/log` with an auto-derived events sidebar. Last because it benefits most from the cockpit primitives being in place.

**Explicitly deferred** within M20-P4 and called out as non-goals in the design slice:
mutating browser actions; collaborative editing; hosted deployment; auth; vector search in the cockpit; GitHub API mandatory dependencies; client-side SPA; persistent caches beyond optional `rebuild-X` records; cockpit personalization or per-user state; a richer dependency graph beyond `related_pages`/`source_refs`/`supersedes`/backlinks.

The current M20-P1.x current-work authority work feeds naturally into M20-P4.2's "what to look at next" pane when it lands; until then, that pane is a thin call to `suggest-next`.

---

## 7. Acceptance criteria

For the design slice (P4.0): the spec PR contains the new sections; cross-references from existing sections are updated; no behavior change; reviewers can summarize the cockpit from the spec without seeing code.

For project identity and page detail (P4.1): every rendered page header shows `project.name` from config; if config is missing, a graceful fallback ("Splendor workspace") with a one-time hint is shown; on a real fixture project (use SynthBanshee) the page-detail view shows the body above the fold and frontmatter is collapsed; the chip strip shows review state, authority, freshness, and source count when present and degrades cleanly when absent; visual diff against current state shows the chip strip ≤ 80px tall.

For cockpit home (P4.2): on a populated fixture, the home page contains six panes, each with non-empty meaningful content; on a sparse fixture, each pane shows an empty-state with a CLI hint; `splendor cockpit summary` outputs the same projection as plain text and exits 0; running the cockpit twice on the same workspace produces identical HTML modulo timestamps; no files are mutated by rendering the home page (file mtime audit in a test).

For swim lanes and trouble spots (P4.3): every planning record appears in exactly one lane; lane assignment rules are documented in the spec and unit-tested; the trouble-spots page lists every record matching defined attention rules and nothing else; each row contains a templated explanation derived from named fields.

For interlinking (P4.4): backlinks for a given page match the set of pages whose `related_pages` includes it (set equality test on a fixture); tag pages list exactly the pages whose frontmatter includes the tag; `/wiki` renders `wiki/index.md` content; orphan detection identifies pages with no inbound links.

For narrative status (P4.5): the health summary on `/status` matches a deterministic rule per attention type; the "what this page is" preamble is present on `/status`, `/runs`, and `/queue`; failed runs appear before successful ones in the runs view.

For log (P4.6): `/log` renders `wiki/log.md` if present and a structured fallback if not; the events sidebar lists the last 30 days of run/state events derived from existing records.

---

## 8. Tests

A few testing patterns worth committing to:

**Golden cockpit projections.** For a small fixture workspace under `tests/fixtures/synthbanshee_mini/`, snapshot the JSON output of `cockpit.read_model.build(root)` and assert equality. Updating the snapshot is an explicit, reviewable diff. This catches regressions in the projection logic without coupling to HTML.

**Determinism tests.** Run `cockpit.read_model.build(root)` twice in the same process, then in two subprocesses on the same git SHA, and assert byte-equal output (after stripping any allowed timestamp fields). This bakes the determinism contract into CI.

**Empty-state coverage.** A fixture with zero sources, zero planning records, zero runs. Every cockpit pane must render its empty-state without raising. Same for `/status`, `/runs`, `/queue`, `/planning`.

**Frontmatter-not-on-top test.** On the page-detail HTML, assert that the index of `<h1>` precedes any element containing the rendered frontmatter JSON. Crude but exactly the regression you want to prevent.

**Backlinks symmetry test.** For every page A whose `related_pages` includes B, assert B appears in A's outbound list and A appears in B's backlinks list.

**No-mutation test.** Capture mtimes of every file in the workspace; render every route; capture mtimes again; assert no changes.

**CLI/web parity test.** Assert `splendor cockpit summary` and the rendered home page describe the same set of items (count and IDs match) for a fixed fixture.

**Project-identity fallback test.** Render the home page with no `project.name` configured; assert a graceful fallback string and a hint are present.

---

## 9. Non-goals and risks

**Non-goals (v1 of the cockpit track).** Any browser mutation. Authentication, user accounts, or per-user state. A client-side SPA framework. Real-time updates, websockets, or polling. Background indexing or watchers. A separate cockpit datastore. GitHub or other external API as a hard dependency. AI-generated summaries in the cockpit (the cockpit interprets *structurally* — assignment rules, lane logic, recency — not *semantically*; semantic summarization is a different product question and belongs to the agent track if anywhere). Personalization. Notifications. A "what's new since I last visited" feature that requires per-user state — instead use "what's new in last 7 days" which is per-workspace.

**Risks worth naming.**

*Salience scope creep.* Once you start interpreting state, every stakeholder will want their thing surfaced ("can the cockpit also show…"). Resist. Make the six panes a contract; new panes require a spec amendment.

*Lane-assignment ambiguity.* Swim-lane rules will have edge cases (a task that is both blocked and recently active). Pick deterministic tie-breakers and document them; resist the urge to make them "smart."

*Backlinks performance.* Realistic workspaces are fine at request time. Very large ones (10k+ pages) will need the durable rebuild path. Keep the request-time path the default; add the rebuild path only when measured.

*Frontmatter-as-API contract.* Moving frontmatter to a collapsed disclosure is a UX change, not a contract change — but be explicit about that in the PR description so no one assumes the field is gone.

*Two-truths drift.* If `wiki/log.md` is hand-curated and the events sidebar is derived, they will sometimes disagree. That's acceptable as long as both are clearly labeled and neither overwrites the other.

*Premature `rebuild-cockpit` path.* Don't add durable cockpit caches until performance demands them. The request-time path is honest and reviewable; a cache is a debt.

*Cockpit fidelity vs. CLI fidelity.* If a returning operator trusts the cockpit and the cockpit lies (stale projection, missed record), trust collapses fast. The determinism contract and the parity tests are how you keep this honest.

---

## 10. Concrete wording you can adapt

For the spec — Section 13.3:

> **13.3 Operator cockpit**
>
> The local web UI includes an operator cockpit: a read-only narrative projection over current workspace files, designed to answer the questions a returning human operator asks on arrival. The cockpit does not introduce new authoritative state. It is a deterministic read-model: every view it renders is a pure function of the current workspace tree at the current git SHA.
>
> The cockpit is composed of six panes: project at a glance, roadmap snapshot, needs attention, recent insights, knowledge map, and what to look at next. Each pane has an empty-state and degrades gracefully on sparse workspaces.
>
> The cockpit may interpret salience — re-ranking, summarizing, grouping — but must not contradict the underlying records. Every interpretive judgment must be traceable to a specific field a reviewer can see in git.
>
> The cockpit projection is also exposed as a CLI command (`splendor cockpit summary`) producing the same data in plain text. Web and CLI cockpit outputs must agree on a fixed workspace.

For the spec — Section 26 (page detail layout subsection):

> **26.x Page detail layout**
>
> Page detail views must show readable page content above the fold. The layout, in order:
>
> A compact chip strip showing only the human-relevant frontmatter facts: review state, authority role, freshness/last-reviewed, and source count. The chip strip omits chips for fields not present on the page.
>
> The page title and the rendered markdown body.
>
> A related-content panel showing source pages, outbound related pages, computed backlinks, supersedes/superseded-by relationships, contradictions, and tags. On narrow viewports this panel renders as a footer.
>
> A collapsed "Technical details" disclosure at the bottom containing the full frontmatter JSON. This disclosure is the only place raw frontmatter appears in the rendered view. Agents reading frontmatter do so through the markdown file directly, not through this rendering.

For the spec — Section 12.4:

> **12.4 Project identity**
>
> The workspace config supports a `project:` block with fields `name`, `tagline` (optional, ≤ 140 chars), `summary_page` (optional path to a markdown file used as the "Project at a glance" cockpit pane), and `links` (optional list of labeled URLs). Every rendered surface — web header, CLI banners, generated index files — must show `project.name` when present, with a graceful fallback otherwise. Absence of `project.name` is a `splendor lint` warning.

For the roadmap — M20-P4 header:

> **M20-P4 — Human operator cockpit and wiki navigation**
>
> Splendor's CLI-first, deterministic, local-first model has matured to the point that the limiting factor for human dogfood quality is no longer state coverage but state *legibility*. M20-P4 adds a derived, read-only operator cockpit and wiki navigation layer that answers the returning-operator questions Splendor's existing surfaces leave implicit: what is this project, where are we, what's stuck, what's new, what's the knowledge shape, what should we look at next. The track preserves all current invariants (CLI-first, local-first, git-native, read-only web, no databases, no daemons) and is implemented as a derivation layer over existing files.

For a home-page hero block (sample render text, not a spec excerpt):

> **SynthBanshee — synthetic vocal latent diffusion (Splendor workspace)**
> Last activity: 3 hours ago · 47 wiki pages · 12 sources · 3 active tasks
>
> *At a glance.* SynthBanshee explores latent-diffusion architectures for controllable singing-voice synthesis, focusing on phoneme-timed expressivity control and low-resource fine-tuning…

---

## Two closing notes worth surfacing

First, the most leveraged single change in this whole document is the page-detail re-layout (P4.1). It directly closes a spec contract violation, requires no new state, and is the change most likely to make a returning user say "oh, the wiki feels real now." Ship that even before the cockpit if you're sequencing for momentum.

Second, the deeper product reframing here is that Splendor has, until now, treated the web UI as a *secondary read view* of the agent runtime. The dogfood result with SynthBanshee shows the web UI is actually the primary surface for *humans*, and humans are first-class users in your spec. The fix is not to make the web UI more capable in the *agent* sense (mutations, complex flows) — it's to make it more capable in the *librarian* sense (orientation, navigation, salience). That framing should travel into the team's shared language; it will pay dividends across many future product decisions.
