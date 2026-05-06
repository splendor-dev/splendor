Pick **A first**.

For the hocrsyngen trial, the decisive failure was not noise or setup friction; it was that Splendor had the available signals and still gave the wrong handoff. A tool meant for agent continuity has to reconcile stale dynamic docs against git/GitHub reality and roadmap order. If S4c is merged and S4d is the next roadmap item, the brief should say that plainly.

B is a close second because first-run repo churn made the tool feel unsafe. But I can work around noisy state with a throwaway branch/worktree. I cannot safely rely on a handoff tool that over-trusts stale `.agent-plan.md` and sends the next agent back to already-merged work.

C should be split: the PATH crash is a real bug, not polish, but it is narrower than A. Ingest progress, scan ranking, and lint false positives can follow.

My priority order for a second hocrsyngen trial:

1. **A:** current-state reasoning.
2. **B:** cold-start/local state ergonomics.
3. **C-critical:** PATH-safe git lookup.
4. **C-polish:** progress, ranking, lint cleanup.
