#!/usr/bin/env bash
# Download the ROenglishRE quest list (OngoingQuests.lub: titles and descriptions of ~11,000 quests) to pages/downloads/.
#   ITEMINFO_VARIANT=Renewal|Pre-Renewal   same variant as the item file (default Renewal)
# Uses the commit recorded for the item file when there is one, so both come from the same version.
set -euo pipefail
root="${GAME_DATA:-$(cd "$(dirname "$0")/.." && pwd)}"
variant="${ITEMINFO_VARIANT:-Renewal}"
case "$variant" in Renewal|Pre-Renewal) ;; *) echo "ITEMINFO_VARIANT must be Renewal or Pre-Renewal" >&2; exit 1 ;; esac
repo=llchrisll/ROenglishRE
out="$root/pages/downloads/OngoingQuests.lub"; meta="$out.meta"
mkdir -p "$root/pages/downloads"
if [ -f "$out" ] && [ -f "$meta" ] && grep -qx "variant: $variant" "$meta"; then echo "OngoingQuests.lub already downloaded ($(grep '^commit:' "$meta"))"; exit 0; fi
commit=""
[ -f "$root/pages/downloads/itemInfo.lua.meta" ] && commit=$(sed -n 's/^commit: //p' "$root/pages/downloads/itemInfo.lua.meta")
if [ -z "$commit" ]; then
  commit=$(curl -fsL "https://api.github.com/repos/$repo/commits/master" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])') \
    || { echo "Could not resolve $repo@master (network, or GitHub API rate limit)." >&2; exit 1; }
fi
url="https://raw.githubusercontent.com/$repo/$commit/Translation/$variant/SystemEN/OngoingQuests.lub"
curl -fsL -o "$out.tmp" "$url" || { rm -f "$out.tmp"; echo "Could not download $url" >&2; exit 1; }
grep -q 'QuestInfoList' "$out.tmp" || { rm -f "$out.tmp"; echo "Downloaded file is not a quest list: $url" >&2; exit 1; }
mv "$out.tmp" "$out"
printf 'url: %s\nvariant: %s\ncommit: %s\nsaved: %s\nsha256: %s\n' "$url" "$variant" "$commit" "$(date -u +%FT%TZ)" "$(shasum -a 256 "$out" | cut -d' ' -f1)" > "$meta"
echo "saved OngoingQuests.lub ($variant @ ${commit:0:10})"
