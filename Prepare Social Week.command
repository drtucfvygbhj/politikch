#!/bin/bash
# Double-click this file in Finder on the weekend to prepare the coming week's
# X posts. It updates this folder from GitHub, then builds the week's pack and
# opens it in your browser: every post in time order, one tab per language, to
# schedule by hand on x.com. It posts nothing.
# After a ballot, double-click it again once Monday's data job is through: the
# results are added to the same pack.

cd "$(dirname "$0")" || exit 1

# Only a fast-forward: if you have local work that would clash, git refuses and
# nothing is overwritten.
echo "Updating from GitHub…"
if GIT_TERMINAL_PROMPT=0 git pull --ff-only --quiet; then
  echo "Up to date: $(git log -1 --format='%h %s' | cut -c1-72)"
else
  echo "Couldn't update from GitHub — using the local copy as it is."
fi
echo

# First run only: the renderer's dependencies, pinned in the requirements file.
if [ ! -x .venv-social/bin/python ]; then
  echo "Setting up the card renderer (first time only)…"
  python3 -m venv .venv-social || exit 1
  .venv-social/bin/pip install --quiet -r scripts/requirements-social.txt || exit 1
fi

# Only reads the switch, for the warning on the page (SEC-10: never changes it).
OFFLINE=""
[ -f MAINTENANCE_MODE ] && OFFLINE="--site-offline"

.venv-social/bin/python scripts/social/pack.py --open $OFFLINE
