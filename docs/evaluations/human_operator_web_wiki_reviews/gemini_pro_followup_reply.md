Here are the exact contracts, derivation rules, and sequencing to implement the human operator layer as a read-only, deterministic projection of existing state.

### 1 & 2. Cockpit Elements and Source of Truth

The home page (`/`) must answer core orientation questions without full-repository parses.

* **Project Identity (Title & Summary):**
* *Source:* The first `# H1` and the subsequent paragraph from `wiki/index.md`.
* *Fallback:* The first `# H1` and paragraph from `README.md`. If missing, the workspace directory basename.
* *State change:* None. Derived at runtime.


* **Active Objective / Current Work:**
* *Source:* The topmost unchecked item or summary block from `.agent-plan.md`.
* *Fallback:* The highest-authority open task from planning records (e.g., `status: in_progress`).
* *State change:* None. Derived from existing current-work handoff logic.


* **Attention Needed (Triage):**
* *Source:* `state/` records where `review_state == "contested"` or `review_state == "stale"`, plus the most recent run record from `state/runs/` if its status is `failed`.
* *Fallback:* Empty state (meaning the project is healthy).
* *State change:* None. Exposes existing data structures.


* **Recent Insights / Log:**
* *Source:* The top 3-5 entries from `wiki/log.md`.
* *Fallback:* Hide section.
* *State change:* None. Parses the top of an existing append-only file.



### 3. Deterministic Project-Identity Contract

To prevent config burden, identity inference is an ordered cascade executed by `resolve_layout(workspace_root)`:

1. Attempt to read `wiki/index.md`. Extract the first Markdown AST `Heading(level=1)` as the project name, and the first `Paragraph` as the summary.
2. If `wiki/index.md` is missing or lacks an H1, attempt the same extraction on `README.md`.
3. If neither exists, use `os.path.basename(workspace_root)` as the title, and "A Splendor workspace" as the summary.

The resulting `title` and `summary` strings are injected into the base FastAPI HTML template, replacing the generic "Splendor" header.

### 4. Minimum Useful Planning/Roadmap View

The `/planning` route must abandon the generic `groupBy(kind)` table and adopt a lifecycle narrative. Derive this strictly from existing planning and handoff contracts:

* **Active:** Filter planning records where `status == "in_progress"`. Cross-reference with `.agent-plan.md` to order items if an agent has explicitly claimed them.
* **Blocked:** Filter records where `status == "blocked"`. Include a sub-query for any `open questions` linked to these tasks via `issue_refs` or `related_pages`.
* **Next Up:** Filter records where `status == "todo"`. Sort by `milestone` affiliation, then by ID.
* **Recently Done:** Filter records where `status == "done"`. Limit to the last 10 to respect the parsing budget.

This requires no new structured state; it is entirely a read-model translation over the existing `splendor/state.py` loaders.

### 5. Page-Detail Layout Contract

The `/documents/{document_path}` route must prioritize human-readable markdown.

* **Inline/Top (Human Badges):** Only render critical triage metadata next to the page H1. This includes `review_state` (especially `contested`), `status`, and `authority_role` (if defined). Render these as small, inline HTML badges.
* **Hidden by Default (Technical Sidebar/Footer):** The full JSON dump (`schema_version`, `page_id`, `generated_by_run_ids`, `source_refs`, `confidence`) must be relocated to a `<details>` block at the absolute bottom of the page, titled "Technical Metadata", or placed in a collapsible right-hand column.
* **Extracted to Footer:** Map `related_pages` and `tags` into a "Related Context" section immediately following the markdown body to establish wiki interlinking without cluttering the header.

### 6. Parsing and Performance Budget

To maintain a fast local server, adhere to this strict budget:

* **Root Route (`/`):** * *Allowed:* Read JSON state files (runs, queue, planning counts). Parse the first 50 lines of `wiki/index.md` or `README.md` for identity. Parse the top 50 lines of `wiki/log.md`.
* *Forbidden:* Full AST parsing of the entire `wiki/` directory.


* **Search / Browse Routes:**
* *Allowed:* File path traversal and cheap regex/frontmatter extraction (as currently implemented).
* *Forbidden:* Loading full document bodies into memory unless executing a specific search query.


* **Detail Routes (`/documents/*`):**
* *Allowed:* Full Markdown AST parsing and rendering for the requested file only.



### 7. Proposed Docs Changes

**Update `docs/splendor_product_spec.md`:**
Add under *26. Local Web UI*:

> **26.1 Operator Cockpit and Page Layout**
> The root web interface (`/`) is the human Operator Cockpit. It must identify the project by parsing `wiki/index.md` or `README.md`, surface active planning objectives, and highlight contested pages or failing runs.
> **26.2 Metadata Visibility**
> Wiki detail pages must render human-readable markdown first. Machine-facing frontmatter (e.g., `page_id`, `run_ids`) must be visually demoted to a collapsible footer or technical sidebar. Only human-actionable states (`review_state`, `status`) may be rendered inline at the top of the page.

**Update `docs/schema_contracts.md`:**

> *Clarification:* Frontmatter fields like `related_pages` and `tags` should be parsed by the web UI to generate visible "Related Context" links at the bottom of rendered wiki pages, turning flat structures into navigable graphs.

**Roadmap Updates:**
Add to *Milestone 20 - Post-v1 product bets*:

> * M20-P4.1 Implement read-only web UI page layout contract (metadata demotion).
> * M20-P4.2 Implement deterministic project identity extraction for the web header.
> * M20-P4.3 Implement Operator Cockpit triage surfaces (contested state and run failure visibility).
>
>

**Non-Goals:**

> * Do not implement background caching for the web UI.
> * Do not introduce a web-specific database; the filesystem remains the sole source of truth.
> * Do not build browser-based mutation or editing tools.
>
>

### 8. First 3 Implementation Slices (PRs)

**PR 1: Page Detail Metadata Demotion (M20-P4.1)**

* *Scope:* Modify the FastAPI HTML template for `/documents/{document_path}`. Move the raw metadata dictionary from the top of the content block to a `<details>` tag at the bottom. Render `review_state` as an inline span next to the title.
* *Acceptance Criteria:* Opening any wiki page displays the markdown body immediately below the title. Raw metadata requires a click to expand at the bottom of the page.
* *Tests:* Assert the HTML response places the markdown rendering container before the metadata container in the DOM hierarchy.

**PR 2: Deterministic Project Identity (M20-P4.2)**

* *Scope:* Update `create_app` and the `/` route to execute the identity cascade (`wiki/index.md` -> `README.md` -> basename). Inject this into the global header template.
* *Acceptance Criteria:* Running `splendor serve` in the SynthBanshee repo displays "SynthBanshee" in the web header and root page title instead of "Splendor".
* *Tests:* Provide fixtures with and without a `wiki/index.md` H1. Assert the `/` route returns the correct parsed string or fallback.

**PR 3: Cockpit Triage Surface (M20-P4.3)**

* *Scope:* Update the `/` route handler. Query existing page status functions for any file with `review_state: contested`. Query run state for the latest run. Pass a `triage_items` list to the root template.
* *Acceptance Criteria:* If a source-summary is contested, the home page displays a highly visible "Attention Needed" block linking to the contested file. If healthy, the block does not render.
* *Tests:* Mock a filesystem state with one `contested` page. Assert the `/` route HTML contains the "Attention Needed" section. Mock a clean state; assert the section is omitted.
