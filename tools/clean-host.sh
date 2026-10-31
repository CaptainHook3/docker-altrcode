#!/usr/bin/env bash
# Removes all data left by docker-altrcode on the host machine.
# Honors XDG variables when set, otherwise uses the default paths.
set -euo pipefail

CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/docker-altrcode"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/docker-altrcode"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/docker-altrcode"

echo "The following directories will be removed:"
for d in "$CONF_DIR" "$STATE_DIR" "$CACHE_DIR"; do
    if [ -e "$d" ]; then
        du -sh "$d" 2>/dev/null && echo "  $d"
    else
        echo "  $d (missing, skipped)"
    fi
done

read -rp "Continue? [y/N] " ans
[[ "${ans,,}" =~ ^(y|yes|o|oui)$ ]] || { echo "Cancelled."; exit 0; }

rm -rf "$CONF_DIR" "$STATE_DIR" "$CACHE_DIR"
echo "Cleanup complete."
