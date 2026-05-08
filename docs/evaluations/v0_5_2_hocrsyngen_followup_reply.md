Yes, that classification is fair.

I did not capture the `--json` variants. I only ran the text-output forms, so I don’t have those four fixture payloads handy. Also, the workspace has since been initialized/ingested for Splendor, so rerunning now would not reproduce the original cold-start state without deliberately resetting generated Splendor state.

The accurate regression classification is:

- `brief --agent-context`: partial pass, leads with `S8b` from `.agent-plan.md`.
- `suggest-next`: partial pass, leads with `S8b` from `.agent-plan.md`.
- `query`: fail as standalone handoff/answer surface.
- Adoption status for `hocrsyngen`: maybe/use for `brief` and `suggest-next` with manual verification.
- Remaining blockers: onboarding/cold-start flow, stale merged-PR clutter, branch/planning mismatch surfacing, and generated contradiction-review noise.
