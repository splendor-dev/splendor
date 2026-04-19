---
name: "feature-pr-finish"
description: "Treat feature work as complete only after a published, fully-metadata'd, non-draft PR exists on GitHub."
---

# Feature PR Finish

Use this skill whenever a task produces a feature branch, bug-fix branch, or any other reviewable
change set that should result in a pull request.

## Completion rule

Do not report the work as complete when code is only local. Completion requires all of the
following:

- the changes are committed on a descriptive branch
- the branch is pushed to GitHub
- a non-draft PR is open on GitHub
- the PR body is detailed enough for handoff and review
- the PR has intentional labels
- the PR is assigned to a milestone

## Required PR body sections

- summary of the change
- why the change was made
- tests or checks run
- follow-up notes or known limits when relevant

## Required final verification

Before reporting completion, verify:

- the PR URL
- the PR is open and not draft
- the expected labels are present
- the milestone is set

If any of those are missing, the work is still in progress.
