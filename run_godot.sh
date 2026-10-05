#!/bin/bash
# Play the castle walk project (pass -e to open the editor instead).
set -euo pipefail
GODOT="${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}"
exec "$GODOT" --path "$(cd "$(dirname "$0")" && pwd)/godot" "$@"
