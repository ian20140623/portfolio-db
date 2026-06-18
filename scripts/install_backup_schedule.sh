#!/usr/bin/env bash
# Install (or refresh) the daily portfolio.db cold-backup launchd agent.
#
# macOS-only. Mac mini is 24/7 + master, so a user LaunchAgent running daily is
# enough: it runs without an interactive login and survives reboot. The job just
# calls `python -m portfoliodb backup`, which is a clean no-op until the DB is
# rebuilt, then starts producing Dropbox cold snapshots automatically.
#
# Re-running this script is idempotent: it boots out any existing agent first.
set -euo pipefail

LABEL="com.portfoliodb.backup"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="$HOME/Library/Logs/portfoliodb-backup.log"
HOUR="${BACKUP_HOUR:-3}"
MINUTE="${BACKUP_MINUTE:-30}"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PY}</string>
        <string>-m</string>
        <string>portfoliodb</string>
        <string>backup</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${REPO}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${REPO}</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${HOUR}</integer>
        <key>Minute</key>
        <integer>${MINUTE}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG}</string>
    <key>StandardErrorPath</key>
    <string>${LOG}</string>
</dict>
</plist>
PLIST

# Reload cleanly (ignore "not loaded" on first install).
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"

echo "Installed ${LABEL}"
echo "  schedule : daily ${HOUR}:$(printf '%02d' "${MINUTE}")"
echo "  command  : ${PY} -m portfoliodb backup  (cwd ${REPO})"
echo "  log      : ${LOG}"
echo
echo "Run now to verify:  launchctl kickstart -p gui/$(id -u)/${LABEL}"
