# Ceremonies and artifact prompts

## Sprint planning
```text
Plan sprint {{S#}}. Capacity: {{hours}} hours. Read @backlog/tasks.yaml and @docs/BACKLOG.md,
@docs/SESSION_NOTES.md and the latest sprint report in docs/sprints/.
1. Propose the sprint goal (one sentence) and a task list that respects dependencies and capacity
   (use estimates; reduce for tasks that slipped last sprint by the observed velocity ratio).
2. Flag risks and any task that needs a spike first. Propose cuts if over capacity (see the cut
   order in design 12.3).
3. After I approve: `make sprint N={{S#}} T=<comma separated IDs>`, `make backlog-render`,
   create docs/sprints/{{S#}}-plan.md from docs/sprints/TEMPLATE.md, mark the first task `ready`.
4. Commit on branch docs/sprint-{{S#}}-plan with [skip-artifacts] in the PR title.
```

## Session start (every new chat)
```text
Resume work. Read @docs/SESSION_NOTES.md (latest entry), @docs/BACKLOG.md and the task I name:
{{TASK_ID}}. Summarise: where we left off, what is next, any blocker. Run `git status` and
`make ci` to confirm a clean baseline before changing anything.
```

## Session end (every session)
```text
Wrap up the session. 1) Make sure everything is committed on the task branch. 2) Update
docs/DECISIONS.md if any decision was made. 3) Append a docs/SESSION_NOTES.md entry (done, next,
open questions, exact commands to resume). 4) Update task status via `make status`, then
`make backlog-render`. 5) Print a 5-line summary I can paste into the PR.
```

## PR self-review (before merging)
```text
Review the diff of this branch against main as a strict senior reviewer (Ask mode). Check:
correctness vs the acceptance criteria, error handling and degradation paths, async safety,
security rules in .cursor/rules/30-security.mdc, PII in logs, test quality and missing edge cases,
API/schema/doc updates, naming, dead code. List findings by severity with file:line. Then fix the
must-fix items, re-run `make ci`, and give me the final checklist status.
```

## Decision log entry
```text
We just decided/learned: {{describe}}. Write a docs/DECISIONS.md entry using the template, with
evidence (run IDs, measurements, links), alternatives, consequences and design-doc impact. If it
changes an ADR, edit the ADR status in docs/design/CallScope_Phase3_Design.md and note it in the
CHANGELOG. If it creates follow-up work, add tasks to backlog/tasks.yaml and validate.
```

## Add or change a task (grooming)
```text
Add these tasks to backlog/tasks.yaml with all required fields (next free IDs, requirement IDs
that exist in design section 1, dependencies, acceptance criteria, owner BAG, estimate, priority,
status backlog, sprint null, issue null, prompt pointer): {{describe}}.
Run `python -m callscope.devtools.backlog validate`, `make backlog-render`, then
`make issues` (dry run first: `python -m callscope.devtools.backlog issues --dry-run`).
```

## Sprint close and report
```text
Close sprint {{S#}}. Run `make report SPRINT={{S#}}`, then fill EVERY TODO in
docs/sprints/{{S#}}-report.md using real evidence: merged PRs, CI status, coverage, measured
latency/eval numbers with run IDs, decisions made (link DECISIONS.md), estimate-vs-actual hours
(ask me for actual hours), risks. Move unfinished tasks to the next sprint (`make sprint`),
update the risk register if risks changed, `make backlog-render`, and open a docs PR.
End with 3 concrete process improvements for the next sprint.
```

## Milestone close (run when the last task of a milestone is done)
```text
Close milestone {{M#}}. Use docs/sprints/MILESTONE_REVIEW_TEMPLATE.md to create
docs/sprints/{{M#}}-review.md and verify EVERY checklist row with evidence:
1. All {{M#}} tasks are done (or explicitly deferred with a task + reason).
2. All PRs merged, self-review done; list PR numbers.
3. `make ci` green on main; paste the summary.
4. Documentation updated: README, docs/api/openapi.yaml, db/schema.sql, runbooks, design-doc
   deviations recorded in DECISIONS.md, CHANGELOG has a section for the release.
5. Build artifact: bump version in pyproject.toml, move Unreleased to [x.y.0] in CHANGELOG,
   run `make build`, and prepare the tag command (`git tag -a vX.Y.0 -m "{{M#}}"`). Do not push
   the tag until I approve.
6. Quote the milestone exit criterion from design section 12.3 and show the evidence.
7. Write the go/no-go for the next milestone and any re-estimate of remaining work.
```

## Spike write-up
```text
Write up spike {{TASK_ID}} in docs/DECISIONS.md: question, method (commands, versions), raw
results (tables with numbers), verdict against the exit criterion, chosen fallback if any,
impact on design/ADRs and on task estimates. Keep throwaway code under spikes/{{TASK_ID}}/ with a
README explaining how to rerun. Do not put spike code in callscope/.
```

## Retro / re-estimate (every 2 sprints)
```text
Compare estimated vs actual hours per completed task (I will supply actuals). Compute the
velocity ratio, identify what drove overruns, re-estimate remaining tasks in backlog/tasks.yaml
accordingly, and tell me whether the milestone dates in the plan still hold. Propose cuts using
the design cut order if not. Record the outcome as a DECISIONS.md entry.
```

## Hotfix
```text
Bug: {{describe, with call_id / run_id if any}}. Reproduce with a failing test first, fix on branch
fix/{{slug}}, add a regression test, run `make ci`, add a CHANGELOG Fixed entry, and add a
DECISIONS.md note if the root cause reveals a design gap. Create a bug task in tasks.yaml if it
is not fixed in this session.
```
