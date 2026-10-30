#!/bin/sh
# Fork-only (q-design): follow rlaope/oh-my-hermes and keep the OMP look on top of it.
#
#   1. fast-forward main to upstream/main and push it to origin;
#   2. rebase q-design onto it (rerere replays conflict fixes seen before);
#   3. run the look's tests and the upstream tests the fork touches;
#   4. push q-design and reinstall OMH from it (`--install`).
#
# Exit codes: 0 up to date or synced, 2 rebase conflict (rebase aborted, tree clean),
# 3 tests failed after a clean rebase (q-design left rebased locally, not pushed), 4 install failed.
# `--install` reinstalls OMH from the fork when the installed commit ($OMH_HOME/q-design-installed) is not HEAD.
# Output is stable (no timestamps) so a cron monitor can hash it.
set -eu
cd "$(dirname "$0")/.."
PY=.venv/bin/python
FORK_ZIP=https://github.com/foxion37/oh-my-hermes/archive/refs/heads/q-design.zip
TESTS="test_omp_look*.py test_skin_pack.py test_theme_command.py test_theme_picker.py test_hermes_display_release.py \
test_model_chains_command.py test_delegation_view_color.py test_tui_*.py"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "DIRTY: uncommitted changes in $(pwd); sync skipped"
  exit 2
fi
git fetch -q upstream main
git fetch -q origin
git switch -q main
# A fork commit on the published main (now merged) means main is no longer a
# strict prefix of upstream/main, so merge instead of insisting on a
# fast-forward; with main's tree kept at upstream's, the merge is upstream's.
if ! git merge -q --ff-only upstream/main 2>/dev/null; then
  git merge -q --no-edit upstream/main
fi
git push -q origin main
git switch -q q-design

install_if_new() {
  # Reinstall OMH only when the installed q-design commit is not this one.
  [ "${1:-}" = "--install" ] || return 0
  head=$(git rev-parse --short HEAD)
  stamp="${OMH_HOME:-$HOME/.omh}/q-design-installed"
  [ "$(cat "$stamp" 2>/dev/null)" = "$head" ] && return 0
  git push -q --force-with-lease origin q-design
  if omh update --package-url "$FORK_ZIP" --source-ref "q-design@$head" --channel preview --yes --no-interactive >/dev/null 2>&1; then
    echo "$head" > "$stamp"
    echo "INSTALLED: omh from q-design@$head"
  else
    echo "INSTALL_FAILED: omh update from q-design@$head failed (previous generation kept)"
    exit 4
  fi
}

if git merge-base --is-ancestor upstream/main q-design; then
  echo "UP_TO_DATE: q-design already on upstream $(git rev-parse --short upstream/main)"
  install_if_new "${1:-}"
  exit 0
fi

before=$(git rev-parse HEAD)
if ! git rebase -q upstream/main >/dev/null 2>&1; then
  files=$(git diff --name-only --diff-filter=U | tr '\n' ' ')
  git rebase --abort
  echo "CONFLICT: q-design ($(git rev-parse --short "$before")) onto upstream $(git rev-parse --short upstream/main)"
  echo "FILES: $files"
  exit 2
fi

"$PY" -m pip install -q -e . >/dev/null 2>&1
failed=""
for t in $TESTS; do
  if ! "$PY" -m unittest discover -s tests -p "$t" >/dev/null 2>&1; then failed="$failed $t"; fi
done
if [ -n "$failed" ]; then
  echo "TESTS_FAILED: q-design rebased locally onto upstream $(git rev-parse --short upstream/main), not pushed"
  echo "FAILED:$failed"
  echo "PREVIOUS: $before"
  exit 3
fi

git push -q --force-with-lease origin q-design
echo "SYNCED: q-design $(git rev-parse --short HEAD) on upstream $(git rev-parse --short upstream/main)"

install_if_new "${1:-}"
