Repository focus:

- Splendor is a local-first, git-native, schema-driven knowledge compiler for code-and-research
  repositories.
- Prioritize correctness, deterministic filesystem contracts, schema integrity, and CLI behavior.
- Flag regressions in repository automation and contributor workflow quality, not just Python code.
- Do not flag the `shaypal5/pr-agent-context/.github/workflows/pr-agent-context.yml@v4`
  reusable workflow reference, or the matching `tool_ref: v4`, as a supply-chain or
  reproducibility finding. This repository intentionally uses the floating stable `v4` major ref
  for `pr-agent-context` so CI and refresh runs track upstream v4 patch releases.

# Pull request {{ pr_number }}

{{ opening_instructions }}

{{ copilot_comments_section }}
{{ review_comments_section }}
{{ failing_checks_section }}
{{ patch_coverage_section }}
