⏺ A — but the choice is closer than the safety/quality framing makes it look.

  By frequency of workflow drag, B wins: every M17 handoff today still needs a follow-up gh issue list because #87 (parent), #88, #92 don't surface.
  That's friction on every session. A's failure mode is rare but catastrophic — drain the queue once and recovery means git-revert + careful
  re-ingest.

  I'd still pick A first, for two reasons that aren't in your framing:

  1. v0.4.0 made the asymmetry worse, not better. queue clean now previews by default — so an agent that learned "v0.4 commands preview" will reach
  for ingest --pending --json expecting the same and drain the queue. The convention used to cover a uniformly-mutating surface; now it has to cover a
   half-mutating one — harder to remember, easier to violate.
  2. The convention is load-bearing on memory I just wrote. Both the v0.3.0 and v0.4.0 splendor memos contain the exact warning "ingest --pending is a
   drain verb, not a preview." Every fresh agent, every compressed session, every external caller has to relearn it. A removes that
  institutional-memory tax outright; B and C don't replace any existing mitigation.

  Sequence: A → B → C. B isn't polish — it's the frequency-weighted handoff-quality fix and belongs second, not bundled with C.
