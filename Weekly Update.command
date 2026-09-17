#!/bin/bash
# ============================================================
#  Politikch — weekly update  (double-click this file)
# ------------------------------------------------------------
#  Opens your private review desk in the browser. Everything is
#  done from there — press "Run maintenance" to trigger all the
#  Claude processes (translations + vote overviews), then review,
#  edit and approve. Close this Terminal window (or Ctrl+C) when done.
# ============================================================

cd "$(dirname "$0")" || exit 1

URL="http://127.0.0.1:8777"

echo "Politikch — review desk"
echo "======================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3, then double-click this again."
  echo "(Press any key to close.)"; read -r -n 1; exit 1
fi

echo "Opening the review desk → $URL"
echo "  In the page: click 'Run maintenance' to generate proposals, then"
echo "  approve / edit them. The 'History' tab shows every past run and change."
echo "  (Close this window or press Ctrl+C when finished.)"
echo

# If it's already running, just open the browser.
if curl -s -o /dev/null "$URL" 2>/dev/null; then
  open "$URL"
  echo "Review desk was already running; opened it in your browser."
  exit 0
fi

# Otherwise start it, open the browser once it's up, keep it foreground.
( sleep 1; open "$URL" ) &
python3 scripts/review_server.py

echo
echo "Data files changed and waiting to be published:"
git status --short data/ 2>/dev/null || true
echo "Commit & push to publish approved changes."
echo "(Press any key to close.)"
read -r -n 1
