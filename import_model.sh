#!/bin/bash
# Copy the Blender export into the Godot project and run a headless import.
set -euo pipefail
GODOT="${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$ROOT/out/castle.glb}"
[ -f "$SRC" ] || { echo "Missing $SRC" >&2; exit 1; }
mkdir -p "$ROOT/godot/models"
cp "$SRC" "$ROOT/godot/models/castle.glb"
# auto-LOD strips thin joinery (window frames, mouldings) at mid distance -> keep full detail
IMP="$ROOT/godot/models/castle.glb.import"
if [ -f "$IMP" ]; then sed -i '' 's/^meshes\/generate_lods=true/meshes\/generate_lods=false/' "$IMP"; fi
"$GODOT" --headless --path "$ROOT/godot" --import 2>&1 | grep -iE "error|warning" || echo "Import OK"
