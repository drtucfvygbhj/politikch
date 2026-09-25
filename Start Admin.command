#!/bin/bash
# Double-click this file in Finder to open the Politikch admin (local only).
# It runs on http://127.0.0.1:8002 and manages the main site's settings, images
# and checks. Start the site itself with "Start Politikch.command" to see the
# preview. Close this Terminal window (or press Ctrl+C) to stop the admin.

cd "$(dirname "$0")" || exit 1

URL="http://127.0.0.1:8002"

if curl -s -o /dev/null "$URL" 2>/dev/null; then
  echo "The admin is already running at $URL"
  open "$URL"
  exit 0
fi

echo "Starting the Politikch admin at $URL (local only)"
echo "(Close this window or press Ctrl+C to stop it.)"
echo

( sleep 1; open "$URL" ) &

exec python3 admin/server.py
