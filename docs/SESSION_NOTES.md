# Session notes (newest first)
Short handoff log so a fresh Cursor chat can resume. Add an entry at the end of every session.

Template:
- Date / task:
- Done:
- Next:
- Open questions / blockers:
- Commands to resume:

## 2026-09-20 / T-M0-01
- Done: Branch `chore/T-M0-01-bootstrap`; fixed CI lint/test/security failures; added bootstrap acceptance tests; logged D-20260920-01.
- Next: Open PR; wait for green GitHub CI; confirm branch protection + Project board Status field; then mark `in_review` / merge / `done`.
- Open questions / blockers: Secret scanning API still 422 on free private (enable in Settings if available). Project board wiring is manual.
- Commands to resume: `git switch chore/T-M0-01-bootstrap && make ci && gh pr create`
