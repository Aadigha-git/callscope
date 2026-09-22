# Milestone review - M6 Hardening and showcase  (2026-09-22)

## Checklist
| Item | Yes/No | Evidence |
|---|---|---|
| Feature implementation complete (all M# tasks done or explicitly deferred) | Yes | T-M6-01..03,05 `done`; T-M6-04 `dropped`; video mp4 operator (D-20260922-47) |
| Code reviewed and merged (PRs linked) | Yes | #103–#105 + this PR |
| Unit tests pass; CI green on main | Yes | Local `make ci` through T-M6-05 |
| Documentation updated | Yes | README, WRITEUP, runbook, showcase, interview notes, OpenAPI unchanged |
| Build artifact created | Pending approval | `pyproject.toml` → `1.0.0`; tag `v1.0.0` prepared — **do not push until approved** |
| Sprint/milestone review completed | Yes | This file |

## Exit criterion (design §12.3)
> **M6 Hardening + telephony (stretch)** — Load test, security suite, retention, SIP stretch, demo polish, write-up. Exit: *Public demo window run; README + write-up complete.*

Local-Mac rescope: SIP dropped; “public demo window” → **local `make demo` + showcase**. Evidence:
- Load: `docs/reports/load/` / D-20260922-45
- Security: `tests/security/` / D-20260922-46
- Showcase + runbook: `docs/showcase/`, `docs/runbooks/demo.md`
- README + WRITEUP + interview materials (T-M6-05)

## Go / no-go
- **Release go** for v1.0.0 after tag approval.
- Follow-ups: volunteer WAVs, live NFR-01 re-measure, operator `demo.mp4`.

## Version bump
```bash
git tag -a v1.0.0 -m "M6 Hardening and showcase"
git push origin v1.0.0
gh release create v1.0.0 --title "v1.0.0" --notes-file docs/sprints/M6-review.md dist/*.whl
```
