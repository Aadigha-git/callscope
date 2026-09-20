# P01 - Generic task prompt (use when a task has no dedicated prompt, or to wrap any of them)

```text
Implement task {{TASK_ID}}.

Follow .cursor/rules/20-workflow-artifacts.mdc exactly:
- Read the task in @backlog/tasks.yaml (requirements, approach, dependencies, acceptance criteria)
  and the design sections it references in @docs/design/CallScope_Phase3_Design.md.
- If any dependency is not `done`, stop and tell me.
- Create the branch, set status in_progress, and give me a short plan (files, tests, risks)
  BEFORE editing. Wait for my "go" only if the plan has an open question.
- Implement in small commits with tests. Never invent third-party API details; read installed
  package source or docs and cite what you found.
- Record every decision/deviation in docs/DECISIONS.md.
- Run `make ci` until green. Then update CHANGELOG (Unreleased), docs/api/openapi.yaml and
  db/schema.sql if applicable, set status in_review, run `make backlog-render`, and append to
  docs/SESSION_NOTES.md.
- Finish by printing: (a) the acceptance-criteria checklist with evidence for each item,
  (b) the PR description filled from the template, (c) any follow-up tasks you propose
  (as ready-to-paste tasks.yaml entries).
```
