# Session notes (newest first)
Short handoff log so a fresh Cursor chat can resume. Add an entry at the end of every session.

Template:
- Date / task:
- Done:
- Next:
- Open questions / blockers:
- Commands to resume:

## 2026-09-20 / T-M0-01
- Done: Branch `chore/T-M0-01-bootstrap`; fixed CI lint/test/security; added bootstrap acceptance tests; D-20260920-01/02; PR #51 with all checks green (lint, typecheck, test, security, artifacts-gate, build).
- Next: You merge PR #51 after confirming branch protection + Project board; then `make status T=T-M0-01 S=done`.
- Open questions / blockers: Secret scanning API 422 on free private (enable in Settings if available). Project board Status field wiring is manual.
- Commands to resume: `gh pr view 51` · after merge: `git switch main && git pull && make status T=T-M0-01 S=done && make backlog-render`
