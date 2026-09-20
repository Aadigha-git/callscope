# Session notes (newest first)
Short handoff log so a fresh Cursor chat can resume. Add an entry at the end of every session.

Template:
- Date / task:
- Done:
- Next:
- Open questions / blockers:
- Commands to resume:

## 2026-09-20 / T-M0-02
- Done: Spike S-1 against hermes-agent 0.19.0; correlation matrix + SSE source analysis; D-20260920-04; design §4.4/ADR-006/U1 notes; scrubbed evidence under `spikes/T-M0-02/results/`.
- Next: PR in_review; merge after green CI; then mark done. Downstream: BrainBackend must send user-message CALL_CONTEXT (T-M1-09).
- Open questions / blockers: PyPI latest is 0.19.0 (design mentioned 0.20.0). Re-check if 0.20+ publishes later.
- Commands to resume: `git switch spike/T-M0-02-hermes-call-id && gh pr view`

## 2026-09-20 / T-M0-01
- Done: Bootstrap CI fixes merged (PR #51); T-M0-01 done.
- Next: T-M0-02 spike (in progress / in_review).
- Open questions / blockers: Secret scanning stance may still need D-20260920-03 merged if not on main.
- Commands to resume: `git switch main && git pull`
