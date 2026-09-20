## Task
Closes #<issue>  |  Task ID: T-M?-??  |  Requirement IDs: FR-??

## What and why
<!-- 2-4 sentences. Link the design section (docs/design) that this implements. -->

## How it was tested
- [ ] `make ci` passes locally
- [ ] New/updated unit tests (list the key cases)
- [ ] Contract/integration tests where APIs, schema or providers changed

## Artifacts (the CI artifact gate checks these)
- [ ] `docs/CHANGELOG.md` updated under **Unreleased**
- [ ] `backlog/tasks.yaml` status updated (`make status T=... S=in_review`) and `make backlog-render` run
- [ ] `docs/api/openapi.yaml` updated if endpoints/contracts changed
- [ ] `db/schema.sql` + migration updated if the database changed
- [ ] `docs/DECISIONS.md` entry added for any design decision or deviation from the design doc
- [ ] Docs/README/runbook updated if behaviour or setup changed

## Security and privacy
- [ ] No secrets, tokens, real PII or recordings committed
- [ ] Logs contain no transcripts, tool args or phone numbers
- [ ] New inputs from callers are treated as untrusted

## Risk and rollback
<!-- What could break, and how to revert. -->
