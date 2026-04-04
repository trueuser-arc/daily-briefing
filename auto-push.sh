#!/bin/bash
# auto-push.sh — pushes unpushed commits from the daily-briefing repo
# Retries every 2 minutes for up to 30 minutes, so the scheduled task
# has time to finish before we attempt the push.
#
# Installed as a launchd agent: com.ian.daily-briefing-push

REPO="$HOME/daily-briefing"
LOG="$REPO/auto-push.log"
MAX_ATTEMPTS=15
WAIT_SECONDS=120

cd "$REPO" || exit 1

echo "[$(date)] auto-push started" >> "$LOG"

for attempt in $(seq 1 $MAX_ATTEMPTS); do
  # Fetch to compare local vs remote
  git fetch origin main --quiet 2>> "$LOG"

  if git status | grep -q "ahead of"; then
    echo "[$(date)] Attempt $attempt: Unpushed commits found — pushing..." >> "$LOG"
    git push origin main >> "$LOG" 2>&1
    if [ $? -eq 0 ]; then
      echo "[$(date)] Push successful." >> "$LOG"
      exit 0
    else
      echo "[$(date)] Push FAILED. Will retry." >> "$LOG"
    fi
  else
    # Check if the briefing task might still be running
    # (no commits yet = task hasn't finished)
    if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
      echo "[$(date)] Attempt $attempt: Nothing to push yet. Waiting ${WAIT_SECONDS}s..." >> "$LOG"
      sleep $WAIT_SECONDS
    else
      echo "[$(date)] No unpushed commits after $MAX_ATTEMPTS attempts. Done." >> "$LOG"
      exit 0
    fi
  fi
done

echo "[$(date)] Exhausted all $MAX_ATTEMPTS attempts. Push may have failed." >> "$LOG"
exit 1
