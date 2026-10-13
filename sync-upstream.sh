#!/usr/bin/env bash
# Bring your fork up to date with ZeetLex/knitting-library.
# Run it inside a clone of YOUR fork, on a machine with git. Takes about a minute when nothing conflicts.
#
#   ./sync-upstream.sh          rebase your branch on the latest upstream main, then push
#   ./sync-upstream.sh --check  only report: how far behind, and whether the rebase would be clean
set -euo pipefail

BRANCH="${FORK_BRANCH:-jeff}"            # your branch: upstream main + your patches on top
UPSTREAM_URL="https://github.com/ZeetLex/knitting-library.git"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"

git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "$UPSTREAM_URL"
git fetch --quiet upstream "$UPSTREAM_BRANCH"
git checkout --quiet "$BRANCH"

behind=$(git rev-list --count "HEAD..upstream/$UPSTREAM_BRANCH")
ahead=$(git rev-list --count "upstream/$UPSTREAM_BRANCH..HEAD")
echo "Your branch '$BRANCH' is $ahead patch commit(s) ahead and $behind upstream commit(s) behind."

if [ "$behind" -eq 0 ]; then
  echo "Nothing to do."
  exit 0
fi

echo
echo "Upstream changes that touch the files your patches touch:"
patched_files=$(git diff --name-only --diff-filter=M "upstream/$UPSTREAM_BRANCH...HEAD")  # files that exist upstream and that we changed
git log --oneline "HEAD..upstream/$UPSTREAM_BRANCH" -- $patched_files || true
echo

if [ "${1:-}" = "--check" ]; then
  # A trial rebase on a throw-away branch, so nothing of yours changes.
  git checkout --quiet -b "_trial_$$" "$BRANCH"
  if git rebase --quiet "upstream/$UPSTREAM_BRANCH" >/dev/null 2>&1; then
    echo "Result: the rebase would be clean."
    result=0
  else
    git rebase --abort >/dev/null 2>&1 || true
    echo "Result: the rebase would CONFLICT. Upstream changed code your patches touch."
    result=1
  fi
  git checkout --quiet "$BRANCH"
  git branch --quiet -D "_trial_$$"
  exit $result
fi

if ! git rebase "upstream/$UPSTREAM_BRANCH"; then
  echo
  echo "The rebase stopped on a conflict. Fix the files git lists, then:"
  echo "  git add <files> && git rebase --continue"
  echo "Or give up with: git rebase --abort"
  exit 1
fi

echo
echo "Rebased cleanly. Run the backend tests if you can (cd app/backend && python -m pytest -q), then:"
echo "  git push --force-with-lease origin $BRANCH"
echo "The image workflow then builds a new image by itself."
