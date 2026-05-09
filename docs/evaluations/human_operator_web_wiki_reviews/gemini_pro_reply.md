Here is a critical review and ideation for Splendor’s human operator web/wiki layer, structured to align with your requested format.

### 1. Thesis

Splendor’s web UI must evolve from a raw state-inspector into an **Operator Cockpit**. It should act as a read-model translation layer that elevates deterministic, agent-oriented filesystem state into human-readable narrative and triage intelligence, all while strictly maintaining the read-only, local-first, git-native architecture. The UI should allow a human to instantly parse project momentum and health without competing with the machine-readable data structures.

### 2. Current Gaps

Based on the dogfooding feedback and current architecture map, the highest-severity gaps are:

* **Information Architecture (IA) Inversion:** On wiki detail pages (`/documents/{document_path}`), full JSON metadata blocks precede the human-readable markdown. This forces the human to scroll past machine context to find the actual content.
* **Missing Project Identity:** The root path (`/`) renders "Splendor" rather than the actual workspace context (e.g., SynthBanshee). The human operator is completely unanchored.
* **State vs. Significance:** The `/status`, `/queue`, and `/runs` routes expose raw internals, long IDs, and flat counts. They fail to separate healthy deterministic states from attention-needed states (e.g., stale pages, contested review states).
* **Data Tables instead of Roadmaps:** The `/planning` route groups items by kind but renders them as raw data tables. It fails to distinguish active, blocked, or completed work in a narrative way.

### 3. Proposed Operator Experience

The visual execution should prioritize a clean, minimalist aesthetic—utilizing stark white backgrounds with neutral blue accents to separate functional zones without adding visual clutter.

* **Home/Operator Cockpit:** The header must clearly identify the workspace. The top fold should render the project narrative (pulled from `wiki/index.md` or a root README), followed by an "Attention Needed" triage section highlighting contested pages or failed runs.
* **Roadmap/Current-Work View:** Instead of flat tables, group planning records into a narrative flow: *Active Now*, *Blocked*, *Next Up*, and *Recently Completed*.
* **Page Detail Layout:** The human-readable markdown must render at the very top of the page. The frontmatter metadata should be collapsed into a discreet technical sidebar or moved entirely to the footer.
* **Source/Provenance Separation:** Clearly delineate between verified source material and generated inferences. When rendering source-summary pages, use distinct visual framing to separate immutable facts derived from the source from the agent's synthesized context.
* **Wiki Browsing and Interlinking:** Surface the `related_pages` and `tags` already present in the schema as a clean "Related Context" section at the bottom of pages, turning flat directories into a navigable graph.
* **Status/Run Interpretation:** Translate run IDs into human meaning. Group by "Recent Ingests," "Active Syntheses," and "Errors/Warnings" rather than a chronological dump of durable runtime state.

### 4. Data And Architecture

This proposal preserves the zero-database, zero-background-worker, local-first constraints.

* **Derived from existing files:** The project identity on the home page should be derived by parsing the first H1 in the workspace root `README.md` or `wiki/index.md`. The roadmap narrative should be derived from the existing `.agent-plan.md` or ordered planning docs.
* **Web-only rendering change:** The demotion of metadata on `/documents/{document_path}` is strictly a UI template change. The underlying markdown and frontmatter contract remains untouched.
* **A CLI contract change:** Deferred. Do not change the CLI yet.
* **A new structured state record:** Deferred. We should fully exploit existing fields like `review_state`, `confidence`, and `supersedes` before inventing new ones.
* **Preserving Determinism:** All web views remain a deterministic read-model. If the underlying git state changes, a page refresh reflects the new state instantly.

### 5. Spec Changes

Update `docs/splendor_product_spec.md`:

* **Amend Section 26 (Local Web UI):** Explicitly add: "Human-facing web views must prioritize readable content. Machine-readable frontmatter must be visually demoted, collapsed, or placed below human narrative."
* **Add Section 26.1 (Operator Cockpit):** "The root web interface must anchor the user in the specific project context, surface active work priorities, and highlight objects requiring human review (contested state, failing runs)."

### 6. Roadmap Changes

Create a new track specifically for the operator experience, running parallel to the M20 product bets. Slice the implementation to ensure first PRs are small:

* **M20-P4.1:** *Docs/design slice.* Formalize the Operator Cockpit layout in the spec.
* **M20-P4.2:** *Page detail metadata slice.* Update the FastAPI HTML template for `/documents/{document_path}` to move the JSON metadata block to the bottom.
* **M20-P4.3:** *Homepage/cockpit read-only slice.* Update `/` to parse the project name and render a high-level README/index summary instead of just count cards.
* **M20-P4.4:** *Planning/roadmap readability slice.* Group the `/planning` tables into a narrative lifecycle (Active, Blocked, Done).
* **M20-P4.5:** *Status/run/queue explanation slice.* Add logic to group and highlight failed jobs or contested pages on the status routes.

### 7. Acceptance Criteria

We will know the new human operator layer works when:

1. A user can run `splendor serve`, open `/`, and instantly name the project and its top active priority without opening a secondary file.
2. A user can click into any wiki page and begin reading the core text immediately, without scrolling past technical frontmatter.
3. The FastAPI web application remains entirely read-only and requires no background workers to render the new views.

### 8. Tests

* **HTML Structure Tests:** Assert that for `/documents/{document_path}`, the `<main>` readable content node appears before the `<aside>` or `<footer>` metadata node in the DOM.
* **Route Context Tests:** Assert that `create_app` correctly passes the inferred workspace title to the base HTML template.

### 9. Non-Goals

What should explicitly not be done yet:

* Adding a SQLite or hosted database to cache UI views.
* Building a Single Page Application (SPA) framework (e.g., React/Vue) on top of the FastAPI backend.
* Implementing mutating web actions (e.g., editing pages in the browser).

### 10. Concerns With This Direction

* **The Parsing Overhead Trap:** To build a richer home page, the app will need to parse more markdown files on load rather than relying solely on cheap metadata reads. If the wiki grows massive, this could slow down the local server. We must remain disciplined about what data is parsed for the home page.
* **Scope Creep to Dashboards:** Grouping runs and statuses by "meaning" can quickly spiral into building complex log-aggregation dashboards. We must constrain the UI to only show *current* triage priorities, relying on the CLI for deep historical log debugging.
