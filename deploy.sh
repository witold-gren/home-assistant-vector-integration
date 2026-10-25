#!/bin/sh
# Deploy the integration to /config/custom_components on a mounted Samba share (without HACS).
# Usage: CONFIG=/path/to/mounted/config ./deploy.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${CONFIG:-/Volumes/config}"
[ -d "$CONFIG" ] || { echo "Mount the Home Assistant config share first ($CONFIG)"; exit 1; }
# SMB: --inplace, because writing via a temporary file and renaming it is sometimes rejected
rsync -a --inplace --delete --exclude '__pycache__' --exclude '.DS_Store' \
    "$HERE/custom_components/vector/" "$CONFIG/custom_components/vector/"
echo "Deployed integration $(grep '"version"' "$HERE/custom_components/vector/manifest.json" | tr -d ' ,'); restart Home Assistant"
