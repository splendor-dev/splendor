---
name: "ready-non-draft-pr"
description: "Use when work in this repository should count as complete only after a properly labeled, non-draft GitHub PR with a detailed description is open and assigned to the right milestone."
---

# Ready Non-Draft PR

Use this skill for feature work, bugfix work, or PR work in this repository whenever GitHub
handoff is part of completion.

## Completion gate

Do not treat the work as complete until all of the following are true:

1. The intended changes are committed on the correct branch.
2. The branch is pushed to the remote.
3. A GitHub PR is open and is not a draft.
4. The PR body explains what changed, why it changed, validation performed, and any follow-up work
   or limitations.
5. The PR has focused labels that match the change.
6. The PR is assigned to the appropriate milestone when one exists.

## Planning notation

- Use milestone-slice notation such as `M6-P1` for the parent planned unit.
- Use dotted PR sub-slice notation such as `M6-P1.1`, `M6-P1.2`, or `M6-P2.1` for each concrete
  PR under that parent slice.
- In PR titles, PR bodies, and planning-state updates, prefer the dotted sub-slice when the work is
  only one PR within a larger planned slice.

## Tool routing

- Prefer repo-specific GitHub MCP tools for PR metadata updates.
- Use `gh` only for unsupported GitHub operations such as creating a missing label or milestone or
  opening the PR itself.

## Close-out rule

- If the PR is still draft, missing labels, missing a milestone, or missing a real description, the
  task is still in progress.
- Final handoff should report the branch name, PR URL, validation run, and any remaining follow-up
  items.
