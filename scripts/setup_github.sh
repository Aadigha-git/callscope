#!/usr/bin/env bash
# One-time GitHub setup. Prereqs: gh CLI authenticated with scopes: repo, workflow, project
#   gh auth login && gh auth refresh -s project
# Usage: scripts/setup_github.sh <repo-name> [public|private]
set -euo pipefail
REPO="${1:-callscope}"; VIS="${2:-private}"
OWNER="$(gh api user --jq .login)"
FULL="$OWNER/$REPO"

echo "==> Creating $FULL ($VIS) and pushing main"
git init -b main 2>/dev/null || true
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git add -A
  # Do not swallow hook failures: a failed commit leaves no main and --push breaks.
  git commit -m "chore: bootstrap repository"
fi
if gh repo view "$FULL" >/dev/null 2>&1; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$FULL.git"
  git push -u origin main
else
  gh repo create "$FULL" "--$VIS" --source=. --remote=origin --push
fi

echo "==> Repo settings: squash merge only, delete merged branches"
gh api -X PATCH "repos/$FULL" \
  -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true -F allow_auto_merge=true >/dev/null

echo "==> Security features (secret scanning + push protection + Dependabot alerts)"
gh api -X PATCH "repos/$FULL" \
  -f 'security_and_analysis[secret_scanning][status]=enabled' \
  -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled' >/dev/null || \
  echo "   (could not enable secret scanning via API - enable in Settings > Code security)"
gh api -X PUT "repos/$FULL/vulnerability-alerts" >/dev/null || true

echo "==> Labels"
uv run python - <<'PY'
import subprocess, yaml
for l in yaml.safe_load(open(".github/labels.yml")):
    subprocess.run(["gh","label","create",l["name"],"--color",l["color"],"--force"], check=False)
PY

echo "==> Milestones and issues"
uv run python -m callscope.devtools.backlog milestones
uv run python -m callscope.devtools.backlog issues
uv run python -m callscope.devtools.backlog render
git add -A
git diff --cached --quiet || git commit -m "chore(backlog): link GitHub issues"
git push

echo "==> Environments"
for env in staging demo; do gh api -X PUT "repos/$FULL/environments/$env" >/dev/null; done
echo "   Add secrets DEPLOY_HOST, DEPLOY_USER, DEPLOY_SSH_KEY per environment; add yourself as a required reviewer on 'demo'."

echo "==> Branch protection for main (solo-friendly: PR required, 0 approvals, checks required)"
cat > /tmp/protection.json <<JSON
{
  "required_status_checks": {"strict": true,
    "contexts": ["lint", "typecheck", "test", "security", "artifacts-gate"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {"required_approving_review_count": 0},
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
gh api -X PUT "repos/$FULL/branches/main/protection" --input /tmp/protection.json >/dev/null
echo "   NOTE: required checks only exist after CI has run once. If the call above fails, open a"
echo "   trivial PR to trigger CI, then re-run just this step."

echo "==> Project board (manual final step)"
echo "   gh project create --owner $OWNER --title 'CallScope'"
echo "   Then add a Status field: Backlog, Ready, In progress, In review, Done; add all issues."
echo "Done."
