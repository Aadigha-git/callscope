# Changelog
Format: Keep a Changelog. Versions map to milestones (M1 = 0.1.0 ... M6 = 1.0.0).

## [Unreleased]
### Added
- Engineering environment: CI, backlog tooling, logging/metrics baseline, Cursor rules and prompt library (T-M0-01)
- Backlog of 46 tasks with estimates; schedule re-baselined (D-20260919-01)
- Bootstrap acceptance tests for `.gitignore` secrets/data patterns, GitHub issue linkage, and CI job shape (T-M0-01)
- Spike S-1 (T-M0-02): Hermes 0.19.0 correlation probe under `spikes/T-M0-02/` with scrubbed evidence (D-20260920-04)
- Spike S-4 (T-M0-05): LiveKit Agents 1.8.2 stub worker + browser/headless smoke under `spikes/T-M0-05/` (D-20260920-05)

### Changed
- Design §4.4 / ADR-006 notes: CALL_CONTEXT must be in user message content; API-server `user`/headers do not reach hooks (D-20260920-04)
- ADR-002 / U4 / S-4: confirmed own LiveKit Agents worker; hermes-livekit not adopted; §4.2 config mapping (D-20260920-05)

## [0.0.1]
- Repository bootstrap
