# Automated checks in the real engine: walk test, sight test, screenshots, benchmark.
# Usage: .\win\test.ps1            (all)      .\win\test.ps1 -Only walk,sight
param([string[]]$Only = @('walk', 'sight', 'shots', 'bench'))
. "$PSScriptRoot\common.ps1"
$godot = Find-Godot
$ok = $true
function Run([string[]]$extra) { & $godot --path "$Root\godot" -- @extra 2>&1 }
if ($Only -contains 'walk') {
    $r = Run @('--walktest')
    $r | Select-String 'FAILED' | Select-Object -First 8 | ForEach-Object { $_.Line }
    $l = ($r | Select-String 'WALKTEST').Line; Write-Host $l; if ($l -notmatch 'PASS') { $ok = $false }
}
if ($Only -contains 'sight') {
    $r = Run @('--sighttest')
    $l = ($r | Select-String 'SIGHTTEST').Line; Write-Host $l; if ($l -notmatch 'PASS') { $ok = $false }
}
if ($Only -contains 'shots') {
    $dir = "$Root\out\main\shots"
    $r = Run @('--shots', $dir)
    Write-Host ("SHOTS {0} -> {1}" -f (($r | Select-String '^SHOT').Count), $dir)
}
if ($Only -contains 'bench') {
    Run @('--bench') | Select-String 'BENCH' | ForEach-Object { $_.Line }
}
if (-not $ok) { exit 1 }
