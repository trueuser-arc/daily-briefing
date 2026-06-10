#!/bin/bash
# auto-push.sh — two-way briefing sync (filename kept for launchd compat).
#
# Since 2026-04-19 the briefing is generated CLOUD-SIDE by the claude.ai
# trigger "daily-tech-briefing" (11:00 UTC daily), which commits and pushes
# weekly/YYYY-WNN.html directly to GitHub. This job runs at 06:45 local and:
#   1. waits for today's commit to appear on origin/main (retry loop)
#   2. pulls it down (rebase keeps any stray local commits on top)
#   3. pushes local commits if any
#   4. converts new day-sections into Obsidian notes (vault-drop.py)
#   5. commits + pushes the vault's AI-News feed
#
# Installed as launchd agent: com.ian.daily-briefing-push

REPO="$HOME/daily-briefing"
VAULT="$HOME/Vault"
LOG="$REPO/auto-push.log"
MAX_ATTEMPTS=10
WAIT_SECONDS=120
TODAY=$(date +%F)

cd "$REPO" || exit 1
echo "[$(date)] sync started" >> "$LOG"

# 1. Wait for today's cloud commit (proceed regardless after MAX_ATTEMPTS —
#    we still want to pull whatever exists)
for attempt in $(seq 1 $MAX_ATTEMPTS); do
  git fetch origin main --quiet 2>> "$LOG"
  remote_date=$(git log -1 --format=%cs origin/main 2>> "$LOG")
  if [ "$remote_date" = "$TODAY" ]; then
    echo "[$(date)] Attempt $attempt: today's briefing is on origin." >> "$LOG"
    break
  fi
  echo "[$(date)] Attempt $attempt: newest remote commit is $remote_date. Waiting ${WAIT_SECONDS}s..." >> "$LOG"
  [ "$attempt" -lt "$MAX_ATTEMPTS" ] && sleep $WAIT_SECONDS
done

# 2. Pull (rebase keeps local-only commits, e.g. script changes)
if ! git pull --rebase --quiet origin main >> "$LOG" 2>&1; then
  echo "[$(date)] PULL FAILED — aborting before vault drop." >> "$LOG"
  exit 1
fi

# 3. Push any local commits
if git status | grep -q "ahead of"; then
  git push origin main >> "$LOG" 2>&1 \
    && echo "[$(date)] Pushed local commits." >> "$LOG" \
    || echo "[$(date)] Push of local commits FAILED." >> "$LOG"
fi

# 4. Drop new digests into the vault (non-fatal)
python3 "$REPO/vault-drop.py" >> "$LOG" 2>&1 \
  || echo "[$(date)] vault-drop failed (non-fatal)" >> "$LOG"

# 5. Commit + push the vault feed (scoped to AI-News only)
cd "$VAULT" || exit 1
git add "03-Resources/AI-News" 2>> "$LOG"
if ! git diff --cached --quiet; then
  git commit -qm "AI-News: digest drop $TODAY" >> "$LOG" 2>&1
  git push --quiet >> "$LOG" 2>&1 \
    && echo "[$(date)] Vault feed committed + pushed." >> "$LOG" \
    || echo "[$(date)] Vault push FAILED (commit is local)." >> "$LOG"
else
  echo "[$(date)] No new vault notes." >> "$LOG"
fi

echo "[$(date)] sync finished" >> "$LOG"
exit 0
