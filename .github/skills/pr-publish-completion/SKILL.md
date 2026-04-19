---
name: "pr-publish-completion"
description: "Finish feature work by publishing a review-ready GitHub PR with full metadata."
---

# PR Publish Completion

Use this skill when a repository task involves implementing a feature, fixing a bug, or otherwise
producing a pull request.

## Rule

Treat the work as incomplete until all of the following are true:

- the intended changes are committed on a descriptive branch
- the branch is pushed to GitHub
- a non-draft pull request is open
- the pull request description is detailed and review-ready
- the pull request has the appropriate labels
- the pull request is assigned to a milestone
- the PR URL and metadata have been verified after publication rather than assumed from a local
  commit or push succeeding

## Publishing checklist

1. Confirm the worktree scope before staging.
2. Run the relevant checks for the change.
3. Commit with a scoped message.
4. Push the branch.
5. Open a non-draft PR with a detailed body covering:
   - what changed
   - why it changed
   - validation performed
   - any follow-up or rollout notes
6. Apply or create the needed labels.
7. Assign the PR to the correct milestone, creating one when the repository does not already have
   a suitable milestone.
8. Verify the published PR URL, state, labels, and milestone before reporting completion.

## Notes

- Do not stop at “code is written” or “commit exists”.
- Do not stop at “tests pass locally” or “the branch is pushed”.
- Do not leave a review-ready feature PR in draft unless the user explicitly asks for that state.
