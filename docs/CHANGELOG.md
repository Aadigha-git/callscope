# Changelog
Format: Keep a Changelog. Versions map to milestones (M1 = 0.1.0 ... M6 = 1.0.0).

## [Unreleased]
### Added
- Engineering environment: CI, backlog tooling, logging/metrics baseline, Cursor rules and prompt library (T-M0-01)
- Backlog of 46 tasks with estimates; schedule re-baselined (D-20260919-01)
- Bootstrap acceptance tests for `.gitignore` secrets/data patterns, GitHub issue linkage, and CI job shape (T-M0-01)

### Fixed
- CI lint (ruff PT023 on integration marker), Settings defaults under `CALLSCOPE_ENV=test`, and pip-audit `--strict` vs editable install (T-M0-01, D-20260920-01)
- Pre-commit ruff pin aligned to 0.16.8 with project tooling (D-20260920-02)

## [0.0.1]
- Repository bootstrap
