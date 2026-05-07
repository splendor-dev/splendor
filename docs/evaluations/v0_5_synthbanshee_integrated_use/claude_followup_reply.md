# Repro Snippets

## #160 — goal-phrasing sensitivity

Missed-case command (`renderer.py` and `test_effective_prosody_cap.py` absent):

```bash
~/.local/bin/splendor brief --agent-context "pick up M17 ASR work"
```

Files to read first from that run:

* `docs/audio_generation_v3_design.md`
* `docs/implementation_plan.md`
* `docs/spec.md`
* `synthbanshee/data/taxonomy.yaml`
* `synthbanshee/tts/mixer.py`

Appeared-case command (`renderer.py` present, test file still absent — partial surface):

```bash
~/.local/bin/splendor brief --agent-context "what's the current state of the SynthBanshee active milestone"
```

Files to read first from that run:

* `synthbanshee/data/taxonomy.yaml`
* `synthbanshee/tts/mixer.py`
* `synthbanshee/tts/renderer.py`
* `synthbanshee/script/templates/she_proves/intimate_terror_coercive_control.j2`
* `CLAUDE.md`

Both files are named in `AGENTS.md` (which surfaces in both runs as current-authority/current/current/inferred-authority, top score). The boost is firing for `renderer.py` on the broader goal but suppressed on the narrower M17 goal — so this isn't "boost not implemented", it's a goal-token / score interaction that pushes authority-cited paths off the top-5 when a goal-specific token competes.

Note also that `tests/unit/test_effective_prosody_cap.py` is missed in both outputs above despite being explicitly named in `AGENTS.md` alongside `renderer.py` — a separate signal that test-path boosting may be weaker than implementation-path boosting.

For symmetry, the empty/broken-PATH probe (which strips git context entirely) did surface the test file:

```bash
PATH="/nonexistent:/tmp:/usr/local/bin" ~/.local/bin/splendor brief --agent-context "test"
```

Output:

* Suggested next:
  - `[medium/git-context] Read first file configs/scenes/test_scene_001.yaml`
  - `[medium/git-context] Read first file tests/unit/test_effective_prosody_cap.py`
  - `[medium/git-context] Read first file CLAUDE.md`

This suggests the boost lands when there's nothing else competing for the slot — further pointing at "ranking interaction" rather than "boost wiring missing".

## #163 — JSON schema coexistence

Command:

```bash
~/.local/bin/splendor queue clean --orphaned --json
```

Top-level keys observed:

* `actions`
* `applied`
* `mutation`
* `selectors`
* `skipped`
* `summary`
* `written`

Trimmed body:

```json
{
  "applied": false,
  "selectors": ["orphaned"],
  "summary": { "planned": 1, "written": 0, "skipped": 0 },
  "actions": [
    {
      "job_id": "ingest-src-9d9759e5…",
      "path": "state/queue/ingest-src-9d9759e5….json",
      "source_id": "src-9d9759e5…",
      "cleanup_state": "orphaned",
      "status": "planned",
      "reason": null
    }
  ],
  "written": [],
  "skipped": [],
  "mutation": {
    "mode": "preview",
    "mutates": false,
    "planned": [
      {
        "action": "delete",
        "path": "state/queue/ingest-src-9d9759e5….json",
        "kind": "queue_record",
        "...": "..."
      }
    ]
  }
}
```

Redundancy map:

* `applied` (bool) ≈ `mutation.mutates` (bool)
* `summary.planned` ≈ `len(mutation.planned)`
* `summary.written` ≈ `len(mutation.written)`
* top-level `written` / `skipped` arrays overlap with `actions[].status` filtered views

`actions` and `selectors` are verb-specific payloads (no equivalent in `mutation.*`) and should stay.

Preferred canonical contract:

* Keep `mutation.{mode,mutates,planned,written}` as the single cross-verb mutation contract.
  - It is already used by:
  - source refresh
  - source update-path
  - workspace refresh
  - ingest --pending
  - All mutating verbs already speak it.
* Preserve verb-specific payloads (`actions`, `selectors` for queue clean).
* Mark redundant top-level aliases as deprecated compatibility aliases in v0.5.x release notes:
  - `applied`
  - `summary`
  - `written`
  - `skipped`
* Emit both for one minor release.
* Drop deprecated aliases in v0.6.0.

Rationale:

* Documenting both indefinitely re-creates the v0.4 ambiguity that #163 was filed against.
* Deprecating-then-dropping converges on one source of truth without breaking anything mid-cycle.

## Optional — #161 trailing footer leak

Tail of:

```bash
~/.local/bin/splendor brief --agent-context "pick up M17 ASR work"
```

Output:

* Next actions:
  - Review issue #97: TTS distress cue absent at I3–I5: rate + pitch are not sufficient signal
  - Review issue #87: investigate(tts): #83 residual — Whisper WER regression on high-intensity (I3+) Tier A clips
  - Review issue #92: tts: aggregate Hebrew TTS naturalness backlog from 2026-05-06 listening test
  - Review commit `37c5f62`: `fix(tts): #87 partial — effective-prosody cap addresses Whisper backdoor + helium range (#90)`
  - Review commit `94086a8`: `fix(preprocessing): #78 define loudness contract + metadata trail (does NOT recover Whisper — see #83) (#82)`
  - Run `splendor wiki suggest <source-id>` for ingested sources missing synthesis follow-up.
  - Open the top matching wiki or planning records for the stated goal.
  - Read the top authority docs before changing planning-heavy behavior.

The leaking line is:

```text
Run `splendor wiki suggest <source-id>` for ingested sources missing synthesis follow-up.
```

This is a maintenance verb in the middle of the work-context footer, between commit-review work items and the generic "open top matches" / "read top authority docs" tail.

The other two tail lines are work-context-flavored (read-first guidance), which is fine; only the `wiki suggest` line is misplaced.
