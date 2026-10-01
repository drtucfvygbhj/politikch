#!/bin/bash
# Double-click this file in Finder to run the Politikch site locally.
# It first updates this folder from GitHub (so the weekly data job's new data
# shows up here too), then serves the site on http://localhost:8001 and opens it
# in your browser. Close this Terminal window (or press Ctrl+C) to stop the server.

cd "$(dirname "$0")" || exit 1

PORT=8001
URL="http://localhost:$PORT"

# Bring this folder up to date with GitHub. Only a fast-forward: if you have
# local work that would clash, git refuses and nothing is overwritten.
update() {
  echo "Updating from GitHub…"
  if GIT_TERMINAL_PROMPT=0 git pull --ff-only --quiet; then
    echo "Up to date: $(git log -1 --format='%h %s' | cut -c1-72)"
  else
    echo "Couldn't update from GitHub — showing the local copy as it is."
  fi
  echo
}
update

# If it's already running, just open the browser and quit.
if curl -s -o /dev/null "$URL" 2>/dev/null; then
  echo "Politikch is already running at $URL"
  open "$URL"
  exit 0
fi

echo "Starting Politikch at $URL"
echo "(Close this window or press Ctrl+C to stop the server.)"
echo

# Open the browser once the server has had a moment to start.
( sleep 1; open "$URL" ) &

# Serve the site (foreground, so closing this window stops it). This computer
# only, and the browser checks every file each time, so a reload shows new data.
exec python3 scripts/serve.py "$PORT"
