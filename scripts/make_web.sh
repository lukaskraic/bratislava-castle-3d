#!/bin/bash
# Browser build: castle first (index.pck), the Old Town as separately downloaded packs (city_*.pck).
#   Blender -b -P scripts/build_castle.py -- --web --tag web --split   (-> out/web/castle.glb, city.glb)
#   scripts/make_web.sh                                                (-> build/web/)
# GitHub Pages refuses files over 100 MB, so every pack is checked against 95 MB.
set -euo pipefail
GODOT="${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/out/web"
WEBP="$ROOT/godot_web"
OUTD="$ROOT/build/web"
for f in castle.glb city.glb; do [ -f "$SRC/$f" ] || { echo "Missing $SRC/$f" >&2; exit 1; }; done

# the web project mirrors the desktop one (same scripts, shaders, scene); only models and data differ
mkdir -p "$WEBP/models" "$WEBP/data" "$OUTD"
rsync -a --delete "$ROOT/godot/scripts/" "$WEBP/scripts/"
rsync -a --delete "$ROOT/godot/shaders/" "$WEBP/shaders/"
rsync -a --delete "$ROOT/godot/scenes/" "$WEBP/scenes/"
cp "$ROOT/godot/project.godot" "$WEBP/project.godot"
[ -f "$ROOT/godot/icon.svg" ] && cp "$ROOT/godot/icon.svg" "$WEBP/" || true
mkdir -p "$WEBP/models/props"
rsync -a --include='*.glb' --exclude='*' "$ROOT/godot/models/props/" "$WEBP/models/props/"
cp "$SRC/castle.glb" "$WEBP/models/castle.glb"
cp "$SRC/city.glb" "$WEBP/models/city.glb"
for j in street_cars.json city_routes.json; do [ -f "$SRC/$j" ] && cp "$SRC/$j" "$WEBP/data/"; done
cp "$ROOT/data/ref/fortress/descents_waypoints.json" "$WEBP/data/" 2>/dev/null || true

"$GODOT" --headless --path "$WEBP" --import >/dev/null 2>&1 || true
# keep thin joinery at distance (no auto-LOD), as on desktop
for imp in "$WEBP/models/castle.glb.import" "$WEBP/models/city.glb.import"; do
  [ -f "$imp" ] && sed -i '' 's/^meshes\/generate_lods=true/meshes\/generate_lods=false/' "$imp"
done
"$GODOT" --headless --path "$WEBP" --import 2>&1 | grep -iE "error" | head -5 || true

# main pack: everything except the Old Town; web_packs.json tells the game what to fetch afterwards
rm -f "$WEBP/web_packs.json"
"$GODOT" --headless --path "$WEBP" --export-pack "WebCity" "$OUTD/city_0.pck" 2>&1 | grep -iE "error" | head -5 || true
CB=$(stat -f %z "$OUTD/city_0.pck")
printf '{"packs": [{"file": "city_0.pck", "bytes": %s, "scene": "res://models/city.glb", "label": "Staré Mesto"}]}\n' "$CB" > "$WEBP/web_packs.json"
"$GODOT" --headless --path "$WEBP" --export-release "Web" "$OUTD/index.html" 2>&1 | grep -iE "error" | head -5 || true
touch "$OUTD/.nojekyll"

ls -la "$OUTD"
for f in "$OUTD"/*; do
  s=$(stat -f %z "$f")
  if [ "$s" -gt 99614720 ]; then echo "TOO BIG for GitHub Pages: $f ($((s / 1048576)) MB)" >&2; exit 2; fi
done
echo "web build OK: $(du -sh "$OUTD" | cut -f1)"
