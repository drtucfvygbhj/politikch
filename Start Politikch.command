#!/bin/bash
# Double-click this file in Finder to run the Politikch site locally.
# It serves the site on http://localhost:8001 and opens it in your browser.
# Close this Terminal window (or press Ctrl+C) to stop the server.

cd "$(dirname "$0")" || exit 1

PORT=8001
URL="http://localhost:$PORT"

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

# Serve the site (foreground, so closing this window stops it).
exec python3 -m http.server "$PORT"
