#!/usr/bin/env bash
# Save a page byte-for-byte, unmodified, with a sidecar of fetch metadata.
#   save_page.sh URL              fetch with curl
#   save_page.sh URL --file PATH  store a file you already have (e.g. from the browser pane)
# Raw pages:  <repo>/pages/<host>/<slug>   (+ <slug>.meta)
# Notes go separately in <repo>/notes/<host>/<slug>.md; never edit the raw file.
set -euo pipefail
url="$1"; src="${3:-}"
root="${GAME_DATA:-$(cd "$(dirname "$0")/.." && pwd)}"
host=$(printf '%s' "$url" | sed -E 's#^[a-z]+://([^/]+).*#\1#')
slug=$(printf '%s' "$url" | sed -E 's#^[a-z]+://[^/]+/?##; s#[^A-Za-z0-9._-]+#_#g; s#^_+|_+$##g')
[ -n "$slug" ] || slug=index
dir="$root/pages/$host"; mkdir -p "$dir"
out="$dir/$slug"
if [ "${2:-}" = "--file" ]; then cp "$src" "$out"; how="file"; code="-"
else
  code=$(curl -sL -A 'Mozilla/5.0' --max-time 60 -o "$out" -w '%{http_code}' "$url"); how="curl"
  if [ "$code" != 200 ]; then rm -f "$out"; echo "HTTP $code, not saved" >&2; exit 1; fi
fi
printf 'url: %s\nsaved: %s\nvia: %s\nhttp: %s\nsha256: %s\nbytes: %s\n' "$url" "$(date -u +%FT%TZ)" "$how" "$code" \
  "$(shasum -a 256 "$out" | cut -d' ' -f1)" "$(wc -c <"$out" | tr -d ' ')" > "$out.meta"
mkdir -p "$root/notes/$host"
echo "raw:   $out"; echo "notes: $root/notes/$host/$slug.md"
