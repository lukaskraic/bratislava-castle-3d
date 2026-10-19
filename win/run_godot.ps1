# Play the castle walk (pass -Editor to open the Godot editor instead).
param([switch]$Editor)
. "$PSScriptRoot\common.ps1"
$godot = Find-Godot
if ($Editor) { & $godot -e --path "$Root\godot" } else { & $godot --path "$Root\godot" }
