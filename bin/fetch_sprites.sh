#!/usr/bin/env bash
# Save the ai4rei viewlist and every npclist page (qq=0,1,2,... until the site returns 404 or an empty page).
# Also saves the dotalux npclist (2009); a failure there is not fatal.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="${GAME_DATA:-$(cd "$here/.." && pwd)}"
export GAME_DATA="$root"
base=https://nn.ai4rei.net/dev
"$here/save_page.sh" "$base/viewlist/" >/dev/null
echo "saved viewlist"
n=0
while :; do
  page="$root/pages/nn.ai4rei.net/dev_npclist_qq_$n"
  for try in 1 2 3 4; do
    err=$("$here/save_page.sh" "$base/npclist/?qq=$n" 2>&1 >/dev/null) && { err=; break; }
    case "$err" in *"HTTP 404"*) break ;; esac   # past the last page
    [ "$try" -lt 4 ] || { echo "npclist page $n failed after retries ($err). Saved $n pages; re-run to continue." >&2; exit 1; }
    sleep $((try * ${FETCH_RETRY_DELAY:-3}))
  done
  [ -z "$err" ] || break
  if ! grep -q 'ID: [0-9]' "$page"; then rm -f "$page" "$page.meta"; break; fi
  n=$((n + 1))
done
[ "$n" -gt 0 ] || { echo "No npclist pages saved: the site may be down or its layout changed." >&2; exit 1; }
echo "saved $n npclist pages"
"$here/save_page.sh" https://dotalux.com/ro/npclist/ >/dev/null && echo "saved dotalux npclist" || echo "dotalux npclist not saved (optional)" >&2
