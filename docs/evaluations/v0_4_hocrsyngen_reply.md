**Verdict**
I would not recommend adding Splendor to `hocrsyngen` yet. It was somewhat useful as a file index and PR-context aggregator, but it failed the core trial: it did not reliably conclude “S4c is merged/done; S4d is next.” Direct `git`, GitHub MCP, and `rg` were faster, clearer, and less noisy.

**Commands Run**
Recorded/protected repo state:

```bash
git status --short --branch
git log --oneline --decorate -12
git switch -c trial/splendor-v0.4-first-pass
```

Baseline:

```bash
git diff --stat main...HEAD
rg -n "S4c|S4d|condition|controls.condition|condition bundle|style consistency|Phase S4" .agent-plan.md README.md docs src tests
```

GitHub MCP:

```text
_get_pr_info HeOCR/hocrsyngen #37
_list_pr_changed_filenames HeOCR/hocrsyngen #37
_fetch_pr_comments HeOCR/hocrsyngen #37
```

Splendor:

```bash
splendor --version
splendor --help
splendor init
splendor health
splendor repo scan --class documentation --json
splendor repo scan --class configuration --json
splendor repo scan --class code --json
splendor add-source ... --capture-source-commit
splendor ingest --pending
splendor brief --agent-context "Review the current S4c condition-control bundle PR and identify remaining handoff work"
splendor suggest-next "Continue hocrsyngen roadmap work after S4c"
splendor pr-summary --since main
splendor queue inspect
splendor lint
splendor query "S4d style consistency checks"
splendor query "current roadmap item after S4c"
```

**Baseline Answer Without Splendor**
Normal inspection says the user-provided ground truth is now stale in this checkout. Initial branch was `main`, not `feature/s4c-condition-control-bundles`. GitHub MCP says PR `#37` is closed and merged, non-draft, with merge commit `4666b65`.

Handoff coherence: the S4c PR body is coherent and the changed-file set matches the stated work. But repo handoff docs are stale after merge: `.agent-plan.md` still says active branch/PR/item is S4c, and `docs/roadmap.md` still says S4c is current. The next roadmap work should be `S4d: Style consistency checks`.

**Splendor Answer/Handoff Summary**
Splendor correctly found PR `#37`, recent commit `4666b65`, `.agent-plan.md`, `README.md`, `docs/roadmap.md`, manifest docs, and integration docs. The `brief` output was useful as a reading list.

But it still suggested “Review PR #37” as the top next action and pulled in older PRs like `#35`, `#36`, `#17`. `suggest-next` did not surface S4d at all. A direct `splendor query "current roadmap item after S4c"` found the roadmap page, but still did not answer “S4d.”

**Ground-Truth Match Table**
| Fact | Direct Inspection | Splendor |
|---|---:|---:|
| Current branch is feature branch | No, checkout was `main` | No, saw trial branch |
| Active PR is `#37` | No, `#37` is merged | Found `#37`, but still treated review as next |
| Active roadmap item S4c | Docs say yes, reality says stale | Treated S4c as current |
| Last completed PR S4b/#36 | Stale; S4c/#37 is now completed | Did not correct this |
| Phase S4 | Yes | Yes |
| Next should be S4d | Yes via roadmap/direct reasoning | No |
| Important files surfaced | Yes | Mostly yes, with noise |
| `.agent-plan.md` as dynamic current state | Yes, but checked against git/PR | Not enough; over-trusted stale state |

**First-Use Friction**
`splendor` was not on `PATH`; I found `~/.local/bin/splendor`. PyPI had no `splendor` package. `npm`, `uv`, `pipx`, and `brew` were unavailable on PATH.

`add-source --capture-source-commit` initially crashed with:

```text
NotADirectoryError: [Errno 20] Not a directory: 'git'
```

Cause: the Codex `PATH` included a non-directory arg0 shim before `/usr/bin`; Splendor’s subprocess git lookup did not tolerate that. Sanitizing `PATH` fixed it.

`ingest --pending` was silent for roughly a minute, then succeeded.

**State/Worktree Churn Observed**
`splendor init` created top-level `derived/`, `planning/`, `raw/`, `reports/`, `state/`, `wiki/`, and `splendor.yaml`.

After minimal seeding/ingest, Splendor created 87 untracked files. Queue records stayed present even after completion. `pr-summary --since main` reported 86 changed paths, almost entirely Splendor state.

I removed the Splendor trial files I created and switched back to `main`; final worktree is clean.

**Must-Fix Issues**
1. Next-work ranking must combine git/GitHub state with roadmap state. If PR `#37` is merged and the roadmap lists `S4d` after `S4c`, `suggest-next` should say S4d, not older PR review.
2. First-run state should not explode into visible top-level repo churn by default. Use a hidden/local ignored workspace, or make the commit-vs-local state model explicit before writing 80+ files.

**Nice-To-Have Improvements**
- Fix `PATH`/subprocess git lookup robustness.
- Add progress output for ingest.
- Fix lint false positives: it reported README links like `docs/roadmap.md` as missing even though they exist.
- Make scan ranking more opinionated: core handoff files should outrank licenses, fixture corpora, and broad docs.
- Mark generated contradiction tasks as secondary unless they block the user’s stated goal.
