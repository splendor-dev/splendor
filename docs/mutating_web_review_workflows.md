# M20-P2.1 Mutating Web Review Workflows Proposal

Status: post-v1 design proposal for issue #119.

Splendor's current local web UI remains read-only. This proposal defines the smallest mutating
browser workflows worth supporting later, and the constraints they must satisfy before any runtime
implementation starts.

## Product Boundary

The web UI may become a review and acceptance surface for existing local-first workflows, not a new
authoritative runtime. The CLI remains the primary contract. Browser-side actions should map to the
same deterministic filesystem writes that already appear in CLI preview/apply output, so users can
review the resulting git diff exactly as if they had run the command by hand.

The first mutating web scope should be limited to three workflows:

1. Accept one maintained wiki compile proposal.
   - The browser displays the same target page, source-summary page, unified diff, source hash,
     target hash, and proposal hash produced by `splendor wiki compile <source> --page <page>`.
   - Acceptance maps to the existing reviewed apply contract:
     `splendor wiki compile <source> --page <page> --apply --proposal-hash <hash>`.
   - Generated source-summary pages remain invalid compile targets.

2. Resolve or mute generated review tasks.
   - The browser may expose generated contradiction-review tasks already visible through
     `splendor task list`.
   - A resolve or mute action maps to the same planning-record update as the CLI task review-state
     commands.
   - The action writes only the selected task record and does not rewrite linked wiki pages,
     source summaries, or historical run records.

3. Accept a previewed source or queue maintenance operation.
   - The browser may render the existing `mutation.planned` records from commands such as
     `source refresh`, `source update-path`, `source forget`, `source reconcile`, `queue clean`, or
     `workspace refresh`.
   - Apply maps to the same command with explicit apply flags.
   - Bulk or destructive operations must keep the same selectors, large-apply guards, skipped
     records, and residual-reference reporting as the CLI.

Everything else stays out of the first mutating web track: freeform page editing, multi-page
synthesis rewrites, background ingestion, hosted collaboration, auth/roles, database-backed state,
mandatory external providers, and automatic GitHub mutation.

## Deterministic State Mapping

Browser mutations should be thin wrappers over CLI-equivalent operations:

- Preview computes a deterministic proposal from the current workspace bytes.
- The proposal includes command-equivalent arguments, affected paths, expected input hashes, and a
  proposal or mutation hash.
- Apply reruns validation against current filesystem state before writing.
- Writes go to normal Splendor files under the configured layout: wiki markdown, planning markdown,
  source manifests, queue records, run records, reports, indexes, or derived artifacts only when
  the underlying CLI command already owns those files.
- The web server never hides writes in a service database or background worker.
- The resulting working-tree diff is the review surface. Commit, push, and PR creation remain
  outside the web UI.

The web layer should reuse command modules directly or shell out through a stable CLI adapter only
when needed. In both cases, the observable contract is the existing CLI mutation object and the
same exit-code/error behavior.

## Conflict Handling

Conflict handling should prefer refusal over repair:

- If the target file, source manifest, queue record, or generated source summary changed after
  preview, apply must fail with a stale-proposal diagnostic and point back to a fresh preview.
- If the proposal hash does not match the recomputed proposal, apply must fail without writes.
- If git context is available and the affected paths contain uncommitted edits unrelated to the
  proposal, the UI should warn before apply. The first implementation may refuse those applies
  rather than attempt a merge.
- If a CLI apply can partially succeed today, the web response must expose the same written,
  skipped, residual, and failed records instead of summarizing them away.
- If a workspace layout becomes unsafe or invalid, the web UI must return a non-mutating error and
  leave repair to the CLI.

This keeps browser acceptance equivalent to a reviewed local command. There is no optimistic
browser-side merge, collaborative editing session, hidden lock table, or asynchronous worker queue.

## First Implementation Shape

The next implementation slice should start with one end-to-end path only: accepting a single
`wiki compile` proposal for a maintained page. That path already has a narrow proposal hash,
source/target inputs, schema validation, and a deterministic one-page write contract.

A minimal implementation can add:

- a read-only proposal detail page that renders the existing compile preview;
- an explicit accept action guarded by the proposal hash and current input hashes;
- a result page that lists written paths and next CLI/git review commands.

It should not add a general mutation framework before that path proves useful. Source/queue
maintenance and task review-state actions can follow after the compile path demonstrates that web
acceptance stays local, deterministic, and git-reviewable.

## Non-Goals

- No runtime behavior changes in `M20-P2.1`.
- No change to current read-only web routes.
- No database, background worker, auth system, hosted service, or mandatory external API.
- No automatic commits, branches, pushes, PRs, or GitHub issue mutation from the web UI.
- No reopening of M19 durability work or hocrgen/hocrsyngen retry work.
