# Session notes (newest first)
Short handoff log so a fresh Cursor chat can resume. Add an entry at the end of every session.

Template:
- Date / task:
- Done:
- Next:
- Open questions / blockers:
- Commands to resume:

## 2026-09-20 / T-M0-05
- Done: Spike S-4 — LiveKit Agents 1.8.2 stub worker (EchoSTT/CannedLLM/SineTTS), docker livekit-server v1.9.1, headless `SMOKE_OK`, §4.2 mapping, hermes-livekit 0.4.0 review; D-20260920-05; ADR-002 confirmed (own worker). Also marked T-M0-01/T-M0-02 done after #52 merge.
- Next: PR in_review; after merge mark done. Next S1 tasks: T-M0-07 or T-M1-01 (T-M0-05 deps satisfied for later worker).
- Open questions / blockers: none for S-4. Tokens need `RoomAgentDispatch` or workers are not dispatched.
- Commands to resume: `git switch spike/T-M0-05-livekit-agents && gh pr view`

## 2026-09-20 / T-M0-02
- Done: Spike S-1 against hermes-agent 0.19.0; correlation matrix + SSE source analysis; D-20260920-04; design §4.4/ADR-006/U1 notes; scrubbed evidence under `spikes/T-M0-02/results/`. Merged #52.
- Next: T-M0-05 (started).
- Open questions / blockers: PyPI latest Hermes is 0.19.0 (design mentioned 0.20.0).
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M0-01
- Done: Bootstrap CI fixes merged (PR #51); status to be marked done with T-M0-02/05 housekeeping.
- Next: T-M0-02 / T-M0-05.
- Open questions / blockers: Secret scanning may need Settings enable on free private.
- Commands to resume: `git switch main && git pull`
