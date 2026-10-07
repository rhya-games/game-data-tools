#!/usr/bin/env bash
# Download the ROenglishRE client item file to pages/downloads/itemInfo.lua and record exactly what was fetched.
#   ITEMINFO_VARIANT=Renewal|Pre-Renewal   which translation to use (default Renewal)
#   ITEMINFO_REF=<branch, tag or commit>   pin a version (default master); the commit it resolved to is saved in itemInfo.lua.meta
# An existing file is kept unless the variant or ref you ask for differs from the one recorded. Set ITEMINFO_REF to update.
set -euo pipefail
root="${GAME_DATA:-$(cd "$(dirname "$0")/.." && pwd)}"
variant="${ITEMINFO_VARIANT:-Renewal}"; ref="${ITEMINFO_REF:-master}"
case "$variant" in Renewal|Pre-Renewal) ;; *) echo "ITEMINFO_VARIANT must be Renewal or Pre-Renewal" >&2; exit 1 ;; esac
repo=llchrisll/ROenglishRE
out="$root/pages/downloads/itemInfo.lua"; meta="$out.meta"
mkdir -p "$root/pages/downloads"
if [ -f "$out" ] && [ -f "$meta" ] && grep -qx "variant: $variant" "$meta" && { [ -z "${ITEMINFO_REF:-}" ] || grep -qx "ref: $ref" "$meta"; }; then
  echo "itemInfo.lua already downloaded ($(grep '^commit:' "$meta"))"; exit 0
fi
commit=$(curl -fsL "https://api.github.com/repos/$repo/commits/$ref" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])') \
  || { echo "Could not resolve $repo@$ref (network, or GitHub API rate limit)." >&2; exit 1; }
url="https://raw.githubusercontent.com/$repo/$commit/Translation/$variant/SystemEN/LuaFiles514/itemInfo.lua"
curl -fsL -o "$out.tmp" "$url" || { rm -f "$out.tmp"; echo "Could not download $url" >&2; exit 1; }
grep -q 'identifiedDisplayName' "$out.tmp" || { rm -f "$out.tmp"; echo "Downloaded file is not an item file: $url" >&2; exit 1; }
mv "$out.tmp" "$out"
printf 'url: %s\nvariant: %s\nref: %s\ncommit: %s\nsaved: %s\nsha256: %s\n' "$url" "$variant" "$ref" "$commit" "$(date -u +%FT%TZ)" \
  "$(shasum -a 256 "$out" | cut -d' ' -f1)" > "$meta"
echo "saved itemInfo.lua ($variant @ ${commit:0:10})"
