#!/bin/bash
# ============================================================
#  Politikch — weekly update  (double-click this file)
# ------------------------------------------------------------
#  Does the whole weekly routine in one click:
#   1. Runs every Claude process (title translations + vote
#      overviews) via your local Claude login — no API key.
#      It does a small batch and stops on its own if you hit a
#      usage limit, so it never runs away.
#   2. Opens the private review desk in your browser, where you
#      approve or edit everything before it goes live.
#  Close this Terminal window (or press Ctrl+C) when you're done.
# ============================================================

cd "$(dirname "$0")" || exit 1

URL="http://127.0.0.1:8777"

echo "Politikch — weekly update"
echo "========================="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3, then double-click this again."
  echo "(Press any key to close.)"; read -r -n 1; exit 1
fi

echo "Step 1 of 2 — running Claude maintenance (translations + vote overviews)…"
echo "  Uses your local Claude login. Stops by itself if you reach a usage limit;"
echo "  whatever it doesn't get to just waits for next week."
echo
python3 scripts/ai_maintain.py
echo

echo "Step 2 of 2 — opening the review desk to check / approve…"
echo "  → $URL   (close this window or press Ctrl+C when finished)"
echo

# If the review desk is already running, just open the browser.
if curl -s -o /dev/null "$URL" 2>/dev/null; then
  open "$URL"
  echo "Review desk was already running; opened it in your browser."
  echo "(Close its Terminal window to stop it.)"
  exit 0
fi

# Otherwise start it, open the browser once it's up, and keep it in the
# foreground so closing this window stops it.
( sleep 1; open "$URL" ) &
python3 scripts/review_server.py

# The server has stopped (you pressed Ctrl+C or closed it).
echo
echo "Done reviewing. Data files changed and waiting to be published:"
git status --short data/ 2>/dev/null || true
echo
echo "To publish approved changes: commit & push (or just run this again next week)."
echo "(Press any key to close.)"
read -r -n 1
