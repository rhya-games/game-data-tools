#!/usr/bin/env bash
# Fetch the public database repos and build the indexes. Run from the repo root.
# Set GAME_DATA to use another folder (default: this folder).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="${GAME_DATA:-$here}"
cd "$root"
[ -d hercules ] || git clone --depth 1 --branch stable https://github.com/HerculesWS/Hercules.git hercules
[ -d rathena ] || git clone --depth 1 --branch master https://github.com/rathena/rathena.git rathena
python3 -c 'import yaml' 2>/dev/null || { echo "Install PyYAML first: pip install -r requirements.txt" >&2; exit 1; }
mkdir -p pages index notes
export GAME_DATA="$root"
"$here"/bin/fetch_iteminfo.sh && "$here"/bin/parse_iteminfo.py --index || echo "Skipping the client item index: see README, step 3." >&2
[ -f pages/nn.ai4rei.net/dev_viewlist ] || "$here"/bin/fetch_sprites.sh || echo "Could not save the sprite lists: see README, step 4." >&2
[ -f pages/nn.ai4rei.net/dev_viewlist ] && "$here"/bin/parse_sprites.py --index
echo "Done."
