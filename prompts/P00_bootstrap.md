# P00 - Bootstrap check (run once, right after unpacking the kit)  |  Task T-M0-01

```text
You are helping me build the CallScope project. Do NOT write business logic yet.

1. Read .cursor/rules/*.mdc, README.md, docs/DEV_GUIDE.md, backlog/tasks.yaml and skim
   docs/design/CallScope_Phase3_Design.md (sections 2, 4.1, 12).
2. Verify the environment: run `make setup` then `make ci`. Fix anything that fails (do not lower
   the coverage gate, disable rules, or delete tests). Show me the final green output.
3. Verify `python -m callscope.devtools.backlog validate` and `render` work and that
   docs/BACKLOG.md is committed and current.
4. Check .gitignore blocks .env, audio files, model weights and data/. Check that no secret-like
   strings exist in the repo (run gitleaks if installed).
5. Confirm pre-commit hooks are installed (`pre-commit run --all-files`).
6. Create branch chore/T-M0-01-bootstrap, set status in_progress, and list every remaining
   manual step for T-M0-01 from docs/DEV_GUIDE.md section 2 that I must do myself (GitHub repo
   creation, branch protection, secrets, Project board), as a checklist.
7. Update docs/CHANGELOG.md and docs/SESSION_NOTES.md. Do not mark the task done until I confirm
   CI is green on GitHub and branch protection is active.
```
