# Cursor prompt library

How to use
1. Open the repo root in Cursor. Rules in `.cursor/rules/` load automatically (check Settings > Rules).
2. Use **Agent** mode for implementation, **Ask** mode for design questions and reviews.
3. One task = one fresh chat = one branch = one PR. Paste the prompt block, nothing else needed.
4. Always let Cursor run `make ci` and paste failures back until green. Do not merge red.
5. When a prompt says "verify", make Cursor read the installed package source (`.venv/lib/...`) or
   run the command; hallucinated library APIs are the top risk in this project.
6. End every session with the *session-end* prompt (ceremonies.md) so the next chat can resume.

Order: `P00_bootstrap` -> `ceremonies#sprint-planning` -> milestone files in order (`M0`..`M6`).
Each milestone file lists tasks in dependency order; task IDs match `backlog/tasks.yaml`.
Tip: attach context with `@backlog/tasks.yaml @docs/design/CallScope_Phase3_Design.md` when a
prompt does not already name the files.
