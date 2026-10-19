#!/bin/bash
# Copy the Blender export into the Godot project and run a headless import.
set -euo pipefail
GODOT="${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$ROOT/out/castle.glb}"
[ -f "$SRC" ] || { echo "Missing $SRC" >&2; exit 1; }
mkdir -p "$ROOT/godot/models"
cp "$SRC" "$ROOT/godot/models/castle.glb"
# walk/shot tools read out/probes.json: keep it in sync with the imported build
PRB="$(dirname "$SRC")/probes.json"
if [ -f "$PRB" ] && [ "$PRB" != "$ROOT/out/probes.json" ]; then cp "$PRB" "$ROOT/out/probes.json"; fi
RTS="$(dirname "$SRC")/city_routes.json"
if [ -f "$RTS" ] && [ "$RTS" != "$ROOT/out/city_routes.json" ]; then cp "$RTS" "$ROOT/out/city_routes.json"; fi
CRS="$(dirname "$SRC")/street_cars.json"
if [ -f "$CRS" ] && [ "$CRS" != "$ROOT/out/street_cars.json" ]; then cp "$CRS" "$ROOT/out/street_cars.json"; fi
# auto-LOD strips thin joinery (window frames, mouldings) at mid distance -> keep full detail
IMP="$ROOT/godot/models/castle.glb.import"
if [ -f "$IMP" ]; then sed -i '' 's/^meshes\/generate_lods=true/meshes\/generate_lods=false/' "$IMP"; fi
"$GODOT" --headless --path "$ROOT/godot" --import 2>&1 | grep -iE "error|warning" || echo "Import OK"
